"""Developer CLI for governed database onboarding."""

from pathlib import Path
from typing import Optional

import typer

from .models import DatabaseRegistration
from .benchmark import (
    CHINOOK_GENRE_QUESTION,
    CHINOOK_REVENUE_QUESTION,
    CHINOOK_TEMPORAL_QUESTION,
    SAKILA_CATEGORY_REVENUE_QUESTION,
    VerificationResult,
    verify_chinook_genre_run,
    verify_chinook_revenue_run,
    verify_chinook_temporal_run,
    verify_sakila_category_revenue_run,
)
from .database import SQLiteAdapter
from .evaluation_report import build_evaluation_payload, run_live_evaluations, run_local_evaluations, write_evaluation_report
from .errors import safe_live_error
from .models import AnalysisRequest
from .runtime import analytics_service, config_store, demo_state_service, onboarding_service, project_root
from .settings import get_settings

app = typer.Typer(help="Governed Analytics Command Center CLI")
database_app = typer.Typer(help="Database onboarding commands")
demo_app = typer.Typer(help="Reproducible state for the Donné → Sakila demo")
verify_app = typer.Typer(help="Explicit paid, real-model verification runs")
evaluation_app = typer.Typer(help="Reproducible deterministic and live evaluation reports")
app.add_typer(database_app, name="db")
app.add_typer(demo_app, name="demo")
app.add_typer(verify_app, name="verify")
app.add_typer(evaluation_app, name="eval")


@database_app.command("add")
def add_database(
    name: str = typer.Option(..., help="Stable lowercase database identifier"),
    path: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    grant: Optional[str] = typer.Option(None, help="User ID that receives this database grant"),
) -> None:
    """Validate, catalog, register, and optionally grant an SQLite database."""
    typer.echo("Validating database...")
    catalog = onboarding_service().register(
        DatabaseRegistration(name=name, path=str(path), grant_user_id=grant)
    )
    typer.echo("✓ SQLite database detected")
    typer.echo("✓ Read-only connection established")
    typer.echo(f"✓ Tables discovered: {len(catalog.tables)}")
    typer.echo("✓ Columns/types and primary/foreign keys discovered")
    restricted = onboarding_service().restricted_fields(catalog)
    if restricted:
        typer.echo(f"⚠ Restricted fields excluded from agent schema: {', '.join(restricted)}")
    typer.echo("✓ Schema catalog created")
    typer.echo(f'✓ Registered "{name}"')
    if grant:
        typer.echo(f"✓ Granted access to {grant}")


@database_app.command("catalog")
def catalog_database(
    name: str = typer.Option(..., help="Stable database identifier for generated metadata"),
    path: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Discover and cache a schema without registering the database or changing ACLs."""
    catalog = onboarding_service().catalog(name, str(path))
    typer.echo(f"✓ Catalog written for {name}: {len(catalog.tables)} tables, {len(catalog.foreign_keys)} foreign keys")
    restricted = onboarding_service().restricted_fields(catalog)
    if restricted:
        typer.echo(f"⚠ Restricted fields excluded from agent schema: {', '.join(restricted)}")


@demo_app.command("check")
def check_demo() -> None:
    """Report whether registry and ACL match the canonical pre-onboarding demo state."""
    check = demo_state_service().check()
    for message in check.messages:
        typer.echo(message)
    if not check.is_canonical:
        raise typer.Exit(code=1)


@demo_app.command("reset")
def reset_demo() -> None:
    """Restore the pre-onboarding state and remove only Sakila's generated catalog."""
    check = demo_state_service().reset()
    for message in check.messages:
        typer.echo(message)
    typer.echo("✓ Demo state reset")


def _verify_chinook_case(question: str, verify_run) -> None:
    """Run one live, billable agent pipeline and print its evidence-backed verdict."""
    store = config_store()
    database = store.database("chinook")
    try:
        run = analytics_service().run(
            AnalysisRequest(user_id="toyesh", database_id="chinook", question=question)
        )
    except Exception as error:
        typer.echo(safe_live_error(error), err=True)
        raise typer.Exit(code=1) from None
    verification: VerificationResult = verify_run(run, SQLiteAdapter(database["path"]))
    typer.echo(f"Question: {question}")
    typer.echo(f"Analysis SQL: {run.analysis.sql_queries[0] if run.analysis.sql_queries else 'not available'}")
    typer.echo(f"Rows: {run.analysis.rows}")
    typer.echo(f"Chart: {run.chart_spec.chart_type if run.chart_spec else 'not available'}")
    typer.echo(f"Repair count: {run.telemetry.sql_repairs}")
    typer.echo(f"Run ID: {run.telemetry.run_id}")
    typer.echo(f"Verification: {'PASS' if verification.passed else 'FAIL'} — {verification.message}")
    if not verification.passed:
        raise typer.Exit(code=1)


@verify_app.command("chinook-revenue")
def verify_chinook_revenue() -> None:
    """Verify country-ranking aggregation and bar-chart semantics against Chinook."""
    _verify_chinook_case(CHINOOK_REVENUE_QUESTION, verify_chinook_revenue_run)


@verify_app.command("chinook-temporal")
def verify_chinook_temporal() -> None:
    """Verify monthly temporal aggregation and line-chart semantics against Chinook."""
    _verify_chinook_case(CHINOOK_TEMPORAL_QUESTION, verify_chinook_temporal_run)


@verify_app.command("chinook-genres")
def verify_chinook_genres() -> None:
    """Verify join-heavy genre revenue and bar-chart semantics against Chinook."""
    _verify_chinook_case(CHINOOK_GENRE_QUESTION, verify_chinook_genre_run)


@verify_app.command("sakila-category-revenue")
def verify_sakila_category_revenue() -> None:
    """After onboarding, verify Donné's unseen-schema Sakila category-revenue run."""
    store = config_store()
    database = store.database("sakila")
    try:
        run = analytics_service().run(
            AnalysisRequest(user_id="donne", database_id="sakila", question=SAKILA_CATEGORY_REVENUE_QUESTION)
        )
    except Exception as error:
        typer.echo(safe_live_error(error), err=True)
        raise typer.Exit(code=1) from None
    verification = verify_sakila_category_revenue_run(run, SQLiteAdapter(database["path"]))
    typer.echo(f"Verification: {'PASS' if verification.passed else 'FAIL'} — {verification.message}")
    if not verification.passed:
        raise typer.Exit(code=1)


def _write_report(*, live: bool) -> None:
    root = project_root()
    deterministic_cases = run_local_evaluations(root)
    try:
        live_cases = run_live_evaluations(root, get_settings()) if live else []
    except Exception as error:
        typer.echo(safe_live_error(error), err=True)
        raise typer.Exit(code=1) from None
    payload = build_evaluation_payload(get_settings().openai_default_model, deterministic_cases, live_cases)
    json_path, markdown_path = write_evaluation_report(root, payload)
    typer.echo(f"✓ Wrote {json_path.relative_to(root)}")
    typer.echo(f"✓ Wrote {markdown_path.relative_to(root)}")
    typer.echo(
        f"Deterministic/local: {payload['deterministic_checks']['passed']} / {payload['deterministic_checks']['total']} | "
        f"Live GPT-5: {payload['live_gpt5_evaluations']['passed']} / {payload['live_gpt5_evaluations']['total']}"
    )


@evaluation_app.command("local")
def evaluate_local() -> None:
    """Run selected deterministic evidence cases and write the report without API calls."""
    _write_report(live=False)


@evaluation_app.command("live")
def evaluate_live() -> None:
    """Intentionally run billable GPT-5 cases, then restore canonical demo state."""
    _write_report(live=True)


if __name__ == "__main__":
    app()
