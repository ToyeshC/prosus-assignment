from pathlib import Path

import pytest

from analytics_command_center.agents import AnalysisAgent, SQLProposal
from analytics_command_center.audit import JsonlAuditSink
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
        self.last_catalog = None

    def propose(self, question, analysis_lens, analysis_hint, catalog):
        self.propose_calls += 1
        self.last_lens = analysis_lens
        self.last_catalog = catalog
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


class CustomerIdVisualizationAgent:
    """Simulates Auto selecting a stable ID instead of a display field."""

    def choose(self, analysis, visualization_hint):
        return ChartSpec(chart_type="bar", x="customer_id", y="total_spent", title="Customers")


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
    executor = SafeQueryExecutor(SQLiteAdapter(db), 10, 1, policy.restricted_fields_by_table(raw))
    with pytest.raises(UnsafeSQL, match="staff.password"):
        executor.execute("SELECT password FROM staff")
    with pytest.raises(UnsafeSQL, match="staff.\\*"):
        executor.execute("SELECT * FROM staff")
    assert executor.execute("SELECT email FROM staff").columns == ["email"]


@pytest.mark.parametrize(("sql", "reference"), [("SELECT password FROM staff", "staff.password"), ("SELECT * FROM staff", "staff.*")])
def test_restricted_sql_policy_records_a_safe_known_reference(store, tmp_path, sql, reference):
    import sqlite3

    staff_db = tmp_path / "staff.db"
    with sqlite3.connect(staff_db) as connection:
        connection.execute("CREATE TABLE staff (staff_id INTEGER, password TEXT)")
    store.register_database("staff", str(staff_db))
    store.grant("toyesh", "staff")
    run = service(store, tmp_path, FakeAnalysisAgent([SQLProposal(sql=sql)])).run(
        AnalysisRequest(user_id="toyesh", database_id="staff", question="Show staff data")
    )

    assert run.analysis.outcome == "blocked"
    assert run.telemetry.governance_policy == "restricted_column"
    assert run.telemetry.restricted_reference == reference
    assert run.telemetry.sql_executed is False


def test_wildcard_policy_is_scoped_to_the_referenced_table(tmp_path):
    import sqlite3

    db = tmp_path / "governed.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            "CREATE TABLE staff (id INTEGER, password TEXT); "
            "CREATE TABLE category (category_id INTEGER, name TEXT); "
            "INSERT INTO category VALUES (1, 'Action');"
        )
    adapter = SQLiteAdapter(db)
    policy = SchemaGovernancePolicy()
    executor = SafeQueryExecutor(adapter, 10, 1, policy.restricted_fields_by_table(adapter.schema_catalog("governed")))

    assert executor.execute("SELECT * FROM category").rows == [{"category_id": 1, "name": "Action"}]
    assert executor.execute("SELECT COUNT(*) AS category_count FROM category").rows == [{"category_count": 1}]
    with pytest.raises(UnsafeSQL, match=r"staff\.\*"):
        executor.execute("SELECT * FROM staff")


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
    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figure.layout.plot_bgcolor == "rgba(0,0,0,0)"


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


def test_duplicate_categorical_display_values_are_disambiguated_without_merging(store, tmp_path):
    agent = FakeAnalysisAgent([
        SQLProposal(sql="SELECT 'Frank' AS first_name, 'Ralston' AS last_name, 1 AS customer_id, 43.62 AS total_spent UNION ALL SELECT 'Frank', 'Harris', 2, 37.62")
    ])
    run = service(store, tmp_path, agent).run(
        AnalysisRequest(user_id="toyesh", database_id="sample", question="Which customers spend the most money?", visualization_hint="Bar")
    )
    assert run.chart_spec is not None
    assert run.chart_spec.label_fields == ["first_name", "last_name"]
    figure = render_chart(run.analysis, run.chart_spec, CompanyStyle(Path(__file__).parents[1] / "config" / "company_style.yaml"))
    assert list(figure.data[0].x) == ["Frank · Ralston", "Frank · Harris"]


def test_auto_and_explicit_bar_share_entity_display_identity_and_ranking_order(store, tmp_path):
    analysis = AnalysisResult(
        database_id="sample", question="Which customers spend the most money?", summary="x",
        columns=["customer_id", "first_name", "last_name", "total_spent"],
        rows=[
            {"customer_id": 7, "first_name": "Frank", "last_name": "Ralston", "total_spent": 43.62},
            {"customer_id": 2, "first_name": "Frank", "last_name": "Harris", "total_spent": 37.62},
        ],
    )
    svc = service(store, tmp_path, FakeAnalysisAgent([]), CustomerIdVisualizationAgent())
    auto, auto_warning = svc.choose_visualization(analysis, "Auto")
    explicit, explicit_warning = svc.choose_visualization(analysis, "Bar")
    assert auto_warning is explicit_warning is None
    assert auto and explicit
    assert auto.label_fields == explicit.label_fields == ["first_name", "last_name"]
    assert auto.identity_field == explicit.identity_field == "customer_id"
    figure = render_chart(analysis, auto, CompanyStyle(Path(__file__).parents[1] / "config" / "company_style.yaml"))
    assert list(figure.data[0].x) == ["Frank · Ralston", "Frank · Harris"]


@pytest.mark.parametrize("chart_type", ["pie", "donut", "box", "scatter"])
def test_entity_labels_remain_distinct_across_categorical_charts(store, tmp_path, chart_type):
    analysis = AnalysisResult(
        database_id="sample", question="Customer spend", summary="x",
        columns=["customer_id", "first_name", "last_name", "total_spent"],
        rows=[
            {"customer_id": 7, "first_name": "Frank", "last_name": "Ralston", "total_spent": 43.62},
            {"customer_id": 2, "first_name": "Frank", "last_name": "Harris", "total_spent": 37.62},
        ],
    )
    spec, warning = service(store, tmp_path, FakeAnalysisAgent([]))._with_safe_categorical_identity(
        analysis, ChartSpec(chart_type=chart_type, x="first_name", y="total_spent", title="Customers")
    )
    assert warning is None
    assert spec and spec.label_fields == ["first_name", "last_name"]
    figure = render_chart(analysis, spec, CompanyStyle(Path(__file__).parents[1] / "config" / "company_style.yaml"))
    assert "Frank · Ralston" in list(figure.data[0].x if spec.chart_type not in {"pie", "donut"} else figure.data[0].labels)
    assert "Frank · Harris" in list(figure.data[0].x if spec.chart_type not in {"pie", "donut"} else figure.data[0].labels)


def test_entity_identity_normalization_does_not_change_distribution_or_temporal_ordering(store, tmp_path):
    distribution = AnalysisResult(
        database_id="sample", question="Spend distribution", summary="x", analysis_lens="distribution",
        columns=["customer_id", "total_spent"], rows=[{"customer_id": 7, "total_spent": 43.62}, {"customer_id": 2, "total_spent": 37.62}],
    )
    temporal = AnalysisResult(
        database_id="sample", question="Revenue over time", summary="x",
        columns=["month", "revenue"], rows=[{"month": "2024-01", "revenue": 10.0}, {"month": "2024-02", "revenue": 20.0}],
    )
    svc = service(store, tmp_path, FakeAnalysisAgent([]))
    histogram, histogram_warning = svc.choose_visualization(distribution, "Auto")
    line, line_warning = svc.choose_visualization(temporal, "Line")
    assert histogram_warning is line_warning is None
    assert histogram and histogram.chart_type == "histogram" and histogram.label_fields == []
    assert line and line.chart_type == "line" and line.label_fields == []
    figure = render_chart(temporal, line, CompanyStyle(Path(__file__).parents[1] / "config" / "company_style.yaml"))
    assert [str(value)[:7] for value in figure.data[0].x] == ["2024-01", "2024-02"]
    assert temporal.rows == [{"month": "2024-01", "revenue": 10.0}, {"month": "2024-02", "revenue": 20.0}]


def test_distribution_lens_changes_customer_observations_to_distribution_chart(store, tmp_path):
    agent = FakeAnalysisAgent([
        SQLProposal(sql="SELECT customer_id, total FROM (SELECT 1 AS customer_id, 10.0 AS total UNION ALL SELECT 2, 20.0)")
    ])
    run = service(store, tmp_path, agent).run(
        AnalysisRequest(user_id="toyesh", database_id="sample", question="Which customers spend the most money?", analysis_lens="distribution")
    )
    assert run.analysis.outcome == "success"
    assert run.analysis.analysis_lens == "distribution"
    assert run.chart_spec is not None and run.chart_spec.chart_type == "histogram"


def test_explicit_incompatible_lenses_are_rejected_before_agent_work(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT id FROM customer")])
    svc = service(store, tmp_path, agent)
    trend = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Which customers spend the most money?", analysis_lens="trend"))
    ranking = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="How has revenue changed over time?", analysis_lens="ranking"))
    assert trend.analysis.outcome == ranking.analysis.outcome == "unsupported"
    assert agent.propose_calls == 0


def test_scatter_allows_temporal_or_categorical_x_with_numeric_y(store, tmp_path):
    analysis = AnalysisResult(
        database_id="sample", question="Revenue over time", summary="x", columns=["month", "revenue"],
        rows=[{"month": "2024-01", "revenue": 10.0}, {"month": "2024-02", "revenue": 20.0}],
    )
    spec, warning = service(store, tmp_path, FakeAnalysisAgent([])).choose_visualization(analysis, "Scatter")
    assert warning is None
    assert spec and spec.chart_type == "scatter" and spec.x == "month" and spec.y == "revenue"


def test_supported_custom_heatmap_and_unsupported_sankey_never_fall_back(store, tmp_path):
    analysis = AnalysisResult(
        database_id="sample", question="x", summary="x", columns=["country", "revenue"],
        rows=[{"country": "NL", "revenue": 10.0}, {"country": "US", "revenue": 20.0}],
    )
    svc = service(store, tmp_path, FakeAnalysisAgent([]))
    heatmap, heatmap_warning = svc.choose_visualization(analysis, "Show this as a heatmap")
    sankey, sankey_warning = svc.choose_visualization(analysis, "Show this as a sankey diagram")
    assert heatmap_warning is None and heatmap and heatmap.chart_type == "heatmap"
    assert sankey is None and sankey_warning and "not currently supported" in sankey_warning


def test_post_analysis_visualization_reuses_analysis_and_records_revision(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT country, total FROM invoice JOIN customer ON customer.id = invoice.customer_id")])
    visualization = FakeVisualizationAgent()
    svc = service(store, tmp_path, agent, visualization)
    run = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Compare revenue"))
    changed = svc.revisualize(run, "Pie / Donut")
    assert changed.telemetry.run_id == run.telemetry.run_id
    assert changed.telemetry.analysis_agent_calls == 1
    assert changed.telemetry.sql_execution_count == 1
    assert changed.telemetry.visualization_runs == 2
    assert changed.telemetry.analysis_reused is True
    assert agent.propose_calls == 1 and visualization.calls == 1


def test_filtered_aggregate_with_zero_match_count_is_typed_no_data(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT COUNT(*) AS matching_row_count, COALESCE(SUM(total), 0) AS revenue FROM invoice WHERE id > 999")])
    run = service(store, tmp_path, agent).run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Revenue in 2200"))
    assert run.analysis.outcome == "no_data"
    assert run.analysis.rows == []
    assert "No matching" in run.analysis.summary


def test_restricted_sql_is_typed_blocked_result_with_safe_policy_telemetry(store, tmp_path):
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT password FROM customer")])
    # The sample schema has no restricted field, so simulate the executor boundary through the service policy.
    svc = service(store, tmp_path, agent)
    from analytics_command_center.errors import UnsafeSQL
    from analytics_command_center.sql_safety import SafeQueryExecutor

    original_execute = SafeQueryExecutor.execute
    def blocked_execute(self, sql):
        raise UnsafeSQL("Query references a restricted column")
    SafeQueryExecutor.execute = blocked_execute
    try:
        run = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Show password"))
    finally:
        SafeQueryExecutor.execute = original_execute
    assert run.analysis.outcome == "blocked"
    assert run.telemetry.governance_policy == "restricted_column"
    assert run.telemetry.sql_executed is False


def test_all_typed_outcomes_are_preserved_by_the_coordinator(store, tmp_path):
    success_agent = FakeAnalysisAgent([SQLProposal(sql="SELECT id FROM customer LIMIT 1")])
    no_data_agent = FakeAnalysisAgent([SQLProposal(sql="SELECT COUNT(*) AS matching_row_count FROM customer WHERE id > 999")])
    assert service(store, tmp_path, success_agent).run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Show a customer")).analysis.outcome == "success"
    assert service(store, tmp_path, no_data_agent).run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Show future customers")).analysis.outcome == "no_data"
    assert service(store, tmp_path, FakeAnalysisAgent([])).run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Train a classifier model")).analysis.outcome == "unsupported"
    assert service(store, tmp_path, FakeAnalysisAgent([])).run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Update all invoices")).analysis.outcome == "blocked"


def test_audit_sink_records_only_safe_governance_metadata(store, tmp_path):
    audit_path = tmp_path / "audit" / "events.jsonl"
    svc = AnalyticsService(
        store, tmp_path / "catalogs", Settings(openai_api_key=None),
        analysis_agent=FakeAnalysisAgent([]), audit_sink=JsonlAuditSink(audit_path),
    )
    result = svc.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Delete all invoices"))
    event = audit_path.read_text(encoding="utf-8")
    assert result.analysis.outcome == "blocked"
    assert '"action": "analysis_request"' in event
    assert '"decision": "ALLOWED"' in event
    assert '"outcome": "blocked"' in event
    assert "Delete all invoices" not in event
    assert "OPENAI_API_KEY" not in event


def test_normal_agent_context_omits_restricted_columns_but_same_table_remains_usable(store, tmp_path):
    import sqlite3
    staff_db = tmp_path / "staff.db"
    with sqlite3.connect(staff_db) as connection:
        connection.executescript("CREATE TABLE staff (staff_id INTEGER, first_name TEXT, password TEXT, revenue REAL); INSERT INTO staff VALUES (1, 'Ada', 'secret', 50.0);")
    store.register_database("staff", str(staff_db))
    store.grant("toyesh", "staff")
    agent = FakeAnalysisAgent([SQLProposal(sql="SELECT staff_id, first_name, revenue FROM staff")])
    run = service(store, tmp_path, agent).run(AnalysisRequest(user_id="toyesh", database_id="staff", question="Show staff revenue"))
    governed_staff = next(table for table in agent.last_catalog.tables if table.name == "staff")
    assert [column.name for column in governed_staff.columns] == ["staff_id", "first_name", "revenue"]
    assert run.analysis.outcome == "success"
