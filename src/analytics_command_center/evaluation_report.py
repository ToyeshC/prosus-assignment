"""Executable evidence reporting for the governed analytics assignment."""

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .benchmark import (
    CHINOOK_GENRE_QUESTION,
    CHINOOK_REVENUE_QUESTION,
    CHINOOK_TEMPORAL_QUESTION,
    NORTHWIND_CATEGORY_REVENUE_QUESTION,
    SAKILA_CATEGORY_REVENUE_QUESTION,
    verify_chinook_genre_run,
    verify_chinook_revenue_run,
    verify_chinook_temporal_run,
    verify_northwind_category_revenue_run,
    verify_sakila_category_revenue_run,
)
from .database import SQLiteAdapter
from .models import AnalysisRequest
from .onboarding import DatabaseOnboardingService
from .registry import ConfigStore
from .service import AnalyticsService
from .settings import Settings


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    database: str
    category: str
    execution: Literal["deterministic/local", "live GPT-5"]
    expected: str
    passed: bool
    result: str
    outcome: str | None = None
    sql_repairs: int | None = None
    analysis_agent_calls: int | None = None
    sql_execution_count: int | None = None
    visualization_type: str | None = None
    latency_ms: int | None = None


LOCAL_CASES = (
    ("Top-k revenue reference", "Chinook", "Analysis correctness", "Reference top-five country revenue"),
    ("Temporal and genre references", "Chinook", "Analysis correctness", "Bounded temporal and multi-table genre revenue"),
    ("Ranking and distribution lenses", "Fixture", "Analysis correctness", "Requested lens controls analysis semantics"),
    ("Lens conflict", "Fixture", "Analysis correctness", "Conflicting explicit lens is rejected before SQL"),
    ("Categorical chart semantics", "Fixture", "Visualization semantics", "Auto and explicit entity labels remain distinct"),
    ("Post-analysis chart override", "Fixture", "Visualization semantics", "Revisualization reuses analysis without SQL rerun"),
    ("Custom visualization boundary", "Fixture", "Visualization semantics", "Supported chart works; unsupported chart is explicit"),
    ("Authorization boundary", "Fixture", "Governance & security", "Denied user reaches no schema, agent, or query"),
    ("Read-only request block", "Fixture", "Governance & security", "Mutation request is blocked before agent work"),
    ("Restricted-column policy", "Sakila-shaped fixture", "Governance & security", "Hidden fields and table-scoped wildcards are governed"),
    ("Bounded result and safe audit", "Fixture", "Governance & security", "Result cap and audit metadata protection"),
    ("Typed failure outcomes", "Fixture", "Robustness", "No data, unsupported, and blocked remain distinct"),
    ("Bounded SQL repair", "Fixture", "Robustness", "Exactly one repair; a second failure stops"),
    ("Dynamic onboarding", "Sakila-shaped fixture", "Database generalization", "Catalog/register/grant are configuration-driven"),
    ("Supplied Sakila reference", "Sakila", "Database generalization", "Real category-revenue reference is available"),
    ("Northwind declared-relationship boundary", "Northwind", "Database generalization", "Zero declared foreign keys is cataloged faithfully"),
)

LOCAL_NODE_IDS = (
    "tests/test_deterministic_core.py::test_supplied_chinook_reference_query_has_known_top_five",
    "tests/test_deterministic_core.py::test_supplied_chinook_temporal_and_genre_references_are_real_and_bounded",
    "tests/test_governance_and_controls.py::test_distribution_lens_changes_customer_observations_to_distribution_chart",
    "tests/test_governance_and_controls.py::test_explicit_incompatible_lenses_are_rejected_before_agent_work",
    "tests/test_governance_and_controls.py::test_auto_and_explicit_bar_share_entity_display_identity_and_ranking_order",
    "tests/test_governance_and_controls.py::test_post_analysis_visualization_reuses_analysis_and_records_revision",
    "tests/test_governance_and_controls.py::test_supported_custom_heatmap_and_unsupported_sankey_never_fall_back",
    "tests/test_governance_and_controls.py::test_denied_user_has_zero_schema_agent_and_query_exposure",
    "tests/test_governance_and_controls.py::test_destructive_and_ml_requests_are_typed_outcomes_without_agent_work",
    "tests/test_governance_and_controls.py::test_wildcard_policy_is_scoped_to_the_referenced_table",
    "tests/test_governance_and_controls.py::test_truncation_reaches_analysis_and_run_details",
    "tests/test_governance_and_controls.py::test_all_typed_outcomes_are_preserved_by_the_coordinator",
    "tests/test_governance_and_controls.py::test_one_safe_sql_repair_succeeds_and_second_failure_stops",
    "tests/test_deterministic_core.py::test_onboarding_separates_config_and_catalog",
    "tests/test_deterministic_core.py::test_supplied_sakila_category_revenue_reference_is_real",
    "tests/test_deterministic_core.py::test_supplied_northwind_catalog_has_no_declared_foreign_keys",
)


def build_evaluation_payload(model: str, deterministic_cases: list[EvaluationCase], live_cases: list[EvaluationCase]) -> dict:
    all_cases = [*deterministic_cases, *live_cases]
    categories: dict[str, dict[str, int]] = {}
    for case in all_cases:
        summary = categories.setdefault(case.category, {"passed": 0, "total": 0})
        summary["total"] += 1
        summary["passed"] += int(case.passed)
    return {
        "title": "Governed Analytics Evaluation",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "model": model,
        "deterministic_checks": _summary(deterministic_cases),
        "live_gpt5_evaluations": _summary(live_cases),
        "categories": categories,
        "cases": [asdict(case) for case in all_cases],
        "limitation": (
            "Complex multi-objective questions may require decomposition into multiple analytical runs. "
            "Predictive concepts such as churn also require an explicit target/definition before analysis."
        ),
    }


def render_evaluation_markdown(payload: dict) -> str:
    deterministic = payload["deterministic_checks"]
    live = payload["live_gpt5_evaluations"]
    executed_total = deterministic["total"] + live["total"]
    executed_passed = deterministic["passed"] + live["passed"]
    lines = [
        "# Governed self-service analytics — evaluation evidence",
        "",
        "Agentic where reasoning helps. Deterministic where correctness matters.",
        "",
        "Models propose; deterministic components authorize, execute, and render.",
        "",
        f"Model: `{payload['model']}`",
        f"Generated: `{payload['generated_at']}`",
        "",
        "## Result",
        "",
        "| Evaluation layer | Result |",
        "| --- | ---: |",
        f"| Deterministic / local | **{deterministic['passed']} / {deterministic['total']}** |",
        f"| Live GPT-5 evaluations | **{live['passed']} / {live['total']}** |",
        f"| Executed evaluation cases | **{executed_passed} / {executed_total}** |",
        "",
        (
            "Live cases execute the real agent workflow and compare returned analytical rows and "
            "visualization semantics against independently computed deterministic references."
        ),
        "",
        "Evaluated against executable references, not judged by screenshots.",
        "",
        "## Category results",
        "",
        "| Category | Passed |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {category} | {summary['passed']} / {summary['total']} |" for category, summary in payload["categories"].items())
    lines.extend(["", "## Cases", "", "| Case | Database | Type | Execution | Expected | Result | Status |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for case in payload["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        lines.append(
            f"| {case['name']} | {case['database']} | {case['category']} | {case['execution']} | "
            f"{case['expected']} | {case['result']} | {status} |"
        )
    lines.extend([
        "",
        "## Current limitation",
        "",
        payload["limitation"],
        "",
        "## Scope of evidence",
        "",
        (
            "These benchmarks demonstrate correctness on the supplied databases and representative "
            "governance and failure paths; they are not a claim of universal natural-language-to-SQL accuracy."
        ),
        "",
    ])
    return "\n".join(lines)


def write_evaluation_report(root: Path, payload: dict) -> tuple[Path, Path]:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    json_path, markdown_path = reports / "evaluation.json", reports / "evaluation.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_evaluation_markdown(payload), encoding="utf-8")
    return json_path, markdown_path


def run_local_evaluations(root: Path) -> list[EvaluationCase]:
    environment = {
        **os.environ,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": _python_path(root),
    }
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-vv", *LOCAL_NODE_IDS], cwd=root, env=environment,
        capture_output=True, text=True, check=False,
    )
    output = completed.stdout + completed.stderr
    cases = []
    for definition, node_id in zip(LOCAL_CASES, LOCAL_NODE_IDS):
        status = _node_status(output, node_id)
        passed = status == "PASSED"
        result = "passed" if passed else status.lower() if status else _compact_result(output)
        name, database, category, expected = definition
        cases.append(EvaluationCase(name, database, category, "deterministic/local", expected, passed, result))
    return cases


def run_live_evaluations(root: Path, settings: Settings) -> list[EvaluationCase]:
    if not settings.live_agents_available:
        raise RuntimeError("Live evaluation is unavailable: OPENAI_API_KEY is not configured.")
    store = ConfigStore(root / "config" / "registry.yaml", root / "config" / "acl.yaml")
    from .demo import DemoStateService
    from .models import DatabaseRegistration

    demo = DemoStateService(store, root / "catalogs")
    demo.reset()
    cases: list[EvaluationCase] = []
    live_definitions = (
        ("Chinook top revenue countries", "chinook", CHINOOK_REVENUE_QUESTION, verify_chinook_revenue_run, "Analysis correctness", "Reference rows and bar semantics"),
        ("Chinook temporal revenue", "chinook", CHINOOK_TEMPORAL_QUESTION, verify_chinook_temporal_run, "Analysis correctness", "Reference rows and line semantics"),
        ("Chinook genre revenue", "chinook", CHINOOK_GENRE_QUESTION, verify_chinook_genre_run, "Analysis correctness", "Reference rows and bar semantics"),
        ("Northwind category revenue", "northwind", NORTHWIND_CATEGORY_REVENUE_QUESTION, verify_northwind_category_revenue_run, "Database generalization", "Reference rows across undeclared relationships"),
    )
    try:
        service = AnalyticsService(store, root / "catalogs", settings)
        for name, database_id, question, verifier, category, expected in live_definitions:
            cases.append(_run_live_case(service, store, name, database_id, question, verifier, category, expected))

        onboarding = DatabaseOnboardingService(store, root / "catalogs")
        onboarding.register(DatabaseRegistration(name="sakila", path=str(root / "datasets" / "sakila.db"), grant_user_id="donne"))
        cases.append(_run_live_case(
            AnalyticsService(store, root / "catalogs", settings), store, "Sakila category revenue", "sakila",
            SAKILA_CATEGORY_REVENUE_QUESTION, verify_sakila_category_revenue_run, "Database generalization",
            "Reference rows and bar semantics after temporary onboarding",
        ))
    finally:
        demo.reset()
    return cases


def _run_live_case(service, store, name: str, database_id: str, question: str, verifier, category: str, expected: str) -> EvaluationCase:
    started = datetime.utcnow()
    try:
        run = service.run(AnalysisRequest(user_id="donne" if database_id == "sakila" else "toyesh", database_id=database_id, question=question))
        verification = verifier(run, SQLiteAdapter(Path(store.database(database_id)["path"])))
        telemetry = run.telemetry
        return EvaluationCase(
            name, database_id.title(), category, "live GPT-5", expected, verification.passed, verification.message,
            run.analysis.outcome, telemetry.sql_repairs, telemetry.analysis_agent_calls, telemetry.sql_execution_count,
            telemetry.chart_type, int((datetime.utcnow() - started).total_seconds() * 1000),
        )
    except Exception:
        return EvaluationCase(name, database_id.title(), category, "live GPT-5", expected, False, "Live evaluation failed safely")


def _summary(cases: list[EvaluationCase]) -> dict[str, int]:
    return {"passed": sum(case.passed for case in cases), "total": len(cases)}


def _compact_result(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:180] if lines else "test command returned no result"


def _node_status(output: str, node_id: str) -> str | None:
    line = next((line for line in output.splitlines() if node_id in line), "")
    return next((status for status in ("PASSED", "FAILED", "SKIPPED") if status in line), None)


def _python_path(root: Path) -> str:
    source = str(root / "src")
    inherited = os.environ.get("PYTHONPATH")
    return source if not inherited else f"{source}{os.pathsep}{inherited}"
