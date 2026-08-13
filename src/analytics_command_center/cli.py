"""Developer CLI for governed database onboarding."""

from pathlib import Path
from typing import Optional

import typer

from .models import DatabaseRegistration
from .benchmark import CHINOOK_REVENUE_QUESTION, verify_chinook_revenue_run
from .database import SQLiteAdapter
from .errors import safe_live_error
from .models import AnalysisRequest
from .runtime import analytics_service, config_store, demo_state_service, onboarding_service

app = typer.Typer(help="Governed Analytics Command Center CLI")
database_app = typer.Typer(help="Database onboarding commands")
demo_app = typer.Typer(help="Reproducible state for the Donné → Sakila demo")
verify_app = typer.Typer(help="Explicit paid, real-model verification runs")
app.add_typer(database_app, name="db")
app.add_typer(demo_app, name="demo")
app.add_typer(verify_app, name="verify")


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


@verify_app.command("chinook-revenue")
def verify_chinook_revenue() -> None:
    """Run one live, billable agent pipeline and verify it against Chinook ground truth."""
    store = config_store()
    database = store.database("chinook")
    try:
        run = analytics_service().run(
            AnalysisRequest(user_id="toyesh", database_id="chinook", question=CHINOOK_REVENUE_QUESTION)
        )
    except Exception as error:
        typer.echo(safe_live_error(error), err=True)
        raise typer.Exit(code=1) from None
    verification = verify_chinook_revenue_run(run, SQLiteAdapter(database["path"]))
    typer.echo(f"Question: {CHINOOK_REVENUE_QUESTION}")
    typer.echo(f"Analysis SQL: {run.analysis.sql_queries[0] if run.analysis.sql_queries else 'not available'}")
    typer.echo(f"Rows: {run.analysis.rows}")
    typer.echo(f"Chart: {run.chart_spec.chart_type if run.chart_spec else 'not available'}")
    typer.echo(f"Repair count: {run.telemetry.sql_repairs}")
    typer.echo(f"Trace ID: {run.telemetry.trace_id}")
    typer.echo(f"Verification: {'PASS' if verification.passed else 'FAIL'} — {verification.message}")
    if not verification.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
