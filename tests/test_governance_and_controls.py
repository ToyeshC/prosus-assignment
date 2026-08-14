from pathlib import Path

import pytest

from analytics_command_center.agents import AnalysisAgent, SQLProposal
from analytics_command_center.database import SQLiteAdapter
from analytics_command_center.errors import AccessDenied, UnsafeSQL
from analytics_command_center.governance import SchemaGovernancePolicy
from analytics_command_center.models import AnalysisRequest, AnalysisResult, ChartSpec
from analytics_command_center.rendering import CompanyStyle, render_chart
from analytics_command_center.service import AnalyticsService
from analytics_command_center.settings import Settings
from analytics_command_center.sql_safety import SafeQueryExecutor


class FakeAnalysisAgent:
    def __init__(self, proposals: list[SQLProposal]):
        self.proposals = proposals
        self.propose_calls = 0
        self.repair_calls = 0
        self.last_lens = None

    def propose(self, question, analysis_lens, analysis_hint, catalog):
        self.propose_calls += 1
        self.last_lens = analysis_lens
        return self.proposals[0]

    def repair(self, question, proposal, error, catalog):
        self.repair_calls += 1
        return self.proposals[self.repair_calls]

    def summarize(self, question, database_id, proposal, result):
        return AnalysisResult(
            database_id=database_id,
            question=question,
            summary="Deterministic fake summary.",
            sql_queries=[proposal.sql],
            columns=result.columns,
            rows=result.rows,
            row_count=len(result.rows),
            truncated=result.truncated,
            row_limit=result.row_limit,
        )


class FakeVisualizationAgent:
    def __init__(self):
        self.calls = 0

    def choose(self, analysis, visualization_hint):
        self.calls += 1
        return ChartSpec(chart_type="bar", x="country", y="total", title="Fake")


def service(store, tmp_path, analysis, visualization=None):
    return AnalyticsService(
        store,
        tmp_path / "catalogs",
        Settings(openai_api_key="test-key"),
        analysis_agent=analysis,
        visualization_agent=visualization or FakeVisualizationAgent(),
    )


def test_schema_policy_hides_obvious_credentials_and_allows_ordinary_columns(tmp_path):
    db = tmp_path / "governed.db"
    import sqlite3
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE staff (id INTEGER, email TEXT, password TEXT)")
    raw = SQLiteAdapter(db).schema_catalog("governed")
    policy = SchemaGovernancePolicy()
    governed = policy.governed_catalog(raw)
    assert policy.restricted_fields(raw) == ["staff.password"]
    assert [column.name for column in governed.tables[0].columns] == ["id", "email"]
    executor = SafeQueryExecutor(SQLiteAdapter(db), 10, 1, policy.restricted_column_names(raw))
    with pytest.raises(UnsafeSQL, match="restricted"):
        executor.execute("SELECT password FROM staff")
    with pytest.raises(UnsafeSQL, match="Wildcard"):
        executor.execute("SELECT * FROM staff")
    assert executor.execute("SELECT email FROM staff").columns == ["email"]


def test_denied_user_has_zero_schema_agent_and_query_exposure(store, tmp_path, monkeypatch):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT id FROM customer")])
    visualization = FakeVisualizationAgent()
    schema_calls = 0

    def forbidden_adapter(*args, **kwargs):
        nonlocal schema_calls
        schema_calls += 1
        raise AssertionError("Schema access must not occur")

    monkeypatch.setattr("analytics_command_center.service.SQLiteAdapter", forbidden_adapter)
    with pytest.raises(AccessDenied):
        service(store, tmp_path, agent, visualization).run(
            AnalysisRequest(user_id="donne", database_id="sample", question="Show revenue")
        )
    assert schema_calls == 0
    assert agent.propose_calls == 0
    assert visualization.calls == 0


def test_lens_is_forwarded_and_explicit_chart_reuses_completed_analysis(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT country, total FROM invoice JOIN customer ON customer.id = invoice.customer_id")])
    visualization = FakeVisualizationAgent()
    run = service(store, tmp_path, agent, visualization).run(
        AnalysisRequest(user_id="toyesh", database_id="sample", question="Compare revenue", analysis_lens="compare", visualization_hint="Auto")
    )
    assert agent.last_lens == "compare"
    assert visualization.calls == 1
    spec, warning = service(store, tmp_path, agent, visualization).choose_visualization(run.analysis, "Pie / Donut")
    assert warning is None
    assert spec and spec.chart_type == "pie"
    assert agent.propose_calls == 1
    assert visualization.calls == 1
    table, warning = service(store, tmp_path, agent, visualization).choose_visualization(run.analysis, "Table only")
    assert warning is None and table and table.chart_type == "table"
    assert run.analysis.summary == "Deterministic fake summary."


@pytest.mark.parametrize("chart_type", ["bar", "line", "pie", "donut", "scatter", "histogram", "box", "heatmap"])
def test_registered_chart_types_have_a_deterministic_renderer(chart_type):
    analysis = AnalysisResult(
        database_id="sample",
        question="x",
        summary="x",
        columns=["category", "first_value", "second_value"],
        rows=[
            {"category": "A", "first_value": 10, "second_value": 5},
            {"category": "B", "first_value": 20, "second_value": 9},
        ],
    )
    if chart_type == "scatter":
        spec = ChartSpec(chart_type=chart_type, x="first_value", y="second_value", title="x")
    elif chart_type == "histogram":
        spec = ChartSpec(chart_type=chart_type, x="first_value", title="x")
    else:
        spec = ChartSpec(chart_type=chart_type, x="category", y="first_value", title="x")
    figure = render_chart(analysis, spec, CompanyStyle(Path(__file__).parents[1] / "config" / "company_style.yaml"))
    assert figure is not None


def test_destructive_and_ml_requests_are_typed_outcomes_without_agent_work(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT id FROM customer")])
    svc = service(store, tmp_path, agent)
    blocked = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Delete all invoices"))
    unsupported = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Train a neural network to predict churn"))
    assert blocked.analysis.outcome == "blocked"
    assert "read-only" in blocked.analysis.summary
    assert unsupported.analysis.outcome == "unsupported"
    assert "target" in unsupported.analysis.summary
    assert agent.propose_calls == 0


def test_deterministic_block_is_available_without_an_api_key(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT id FROM customer")])
    svc = AnalyticsService(store, tmp_path / "catalogs", Settings(openai_api_key=None), analysis_agent=agent)
    result = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Delete all invoices"))
    assert result.analysis.outcome == "blocked"
    assert agent.propose_calls == 0


def test_truncation_reaches_analysis_and_run_details(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT id FROM invoice ORDER BY id")])
    svc = service(store, tmp_path, agent)
    svc.settings.max_result_rows = 2
    run = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Show all invoices"))
    assert run.analysis.truncated is True
    assert run.analysis.row_limit == 2
    assert run.telemetry.truncated is True
    assert run.telemetry.rows_returned == 2


def test_one_safe_sql_repair_succeeds_and_second_failure_stops(store, tmp_path, monkeypatch):
    original_execute = SQLiteAdapter.execute
    attempts = 0

    def counted_execute(self, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        return original_execute(self, *args, **kwargs)

    monkeypatch.setattr(SQLiteAdapter, "execute", counted_execute)
    good_repair = FakeAnalysisAgent([
        SQLProposal(sql="SELECT definitely_missing_column FROM customer"),
        SQLProposal(sql="SELECT id FROM customer LIMIT 1"),
    ])
    success = service(store, tmp_path, good_repair).run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Show a customer"))
    assert success.analysis.outcome == "success"
    assert success.telemetry.sql_repairs == 1
    assert attempts == 2

    attempts = 0
    bad_repair = FakeAnalysisAgent([
        SQLProposal(sql="SELECT definitely_missing_column FROM customer"),
        SQLProposal(sql="SELECT another_missing_column FROM customer"),
    ])
    failure = service(store, tmp_path, bad_repair).run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Show a customer"))
    assert failure.analysis.outcome == "unsupported"
    assert failure.telemetry.sql_repairs == 1
    assert attempts == 2


def test_real_analysis_agent_repair_invokes_its_wrapper_with_one_instruction(monkeypatch, sample_db):
    captured = []

    def fake_run(self, instructions, input_text, output_type):
        captured.append((instructions, input_text, output_type))
        return SQLProposal(sql="SELECT id FROM customer LIMIT 1")

    monkeypatch.setattr(AnalysisAgent, "_run", fake_run)
    catalog = SQLiteAdapter(sample_db).schema_catalog("sample")
    proposal = AnalysisAgent(Settings(openai_api_key="test-key")).repair(
        "Show a customer", SQLProposal(sql="SELECT missing FROM customer"), "no such column", catalog
    )
    assert proposal.sql == "SELECT id FROM customer LIMIT 1"
    assert len(captured) == 1
