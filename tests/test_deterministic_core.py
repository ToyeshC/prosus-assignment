from pathlib import Path

import pytest

from analytics_command_center.benchmark import (
    chinook_genre_reference,
    chinook_revenue_reference,
    chinook_temporal_reference,
    is_non_increasing,
    rows_match,
    sakila_category_revenue_reference,
)
from analytics_command_center.database import SQLiteAdapter
from analytics_command_center.demo import CANONICAL_ACL, CANONICAL_REGISTRY, DemoStateService
from analytics_command_center.errors import AccessDenied, UnsafeSQL, safe_live_error
from analytics_command_center.models import (
    AnalysisRequest,
    AnalysisResult,
    ChartSpec,
    DatabaseRegistration,
)
from analytics_command_center.onboarding import DatabaseOnboardingService
from analytics_command_center.rendering import CompanyStyle, render_chart
from analytics_command_center.service import AnalyticsService
from analytics_command_center.settings import Settings
from analytics_command_center.sql_safety import SafeQueryExecutor, validate_read_only_sql


@pytest.mark.parametrize("sql", ["DELETE FROM invoice", "SELECT 1; SELECT 2", "ATTACH DATABASE 'x' AS x"])
def test_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeSQL):
        validate_read_only_sql(sql)


def test_allows_read_cte():
    assert "WITH" in validate_read_only_sql("WITH x AS (SELECT 1 AS id) SELECT * FROM x")


def test_executor_caps_rows(sample_db):
    result = SafeQueryExecutor(SQLiteAdapter(sample_db), max_rows=2, timeout_seconds=1).execute("SELECT id FROM invoice ORDER BY id")
    assert len(result.rows) == 2
    assert result.truncated is True


def test_catalog_discovers_columns_and_relationships(sample_db):
    catalog = SQLiteAdapter(sample_db).schema_catalog("sample")
    assert {table.name for table in catalog.tables} == {"customer", "invoice"}
    assert catalog.foreign_keys[0].from_table == "invoice"


def test_onboarding_separates_config_and_catalog(store, sample_db, tmp_path):
    catalog = DatabaseOnboardingService(store, tmp_path / "catalogs").register(DatabaseRegistration(name="sakila", path=str(sample_db), grant_user_id="donne"))
    assert store.authorize("donne", "sakila").allowed
    assert (tmp_path / "catalogs" / "sakila.json").is_file()
    assert catalog.database_id == "sakila"


def test_denied_request_stops_before_live_agent_check(store, tmp_path):
    service = AnalyticsService(store, tmp_path / "catalogs", Settings(openai_api_key=None))
    with pytest.raises(AccessDenied):
        service.run(AnalysisRequest(user_id="donne", database_id="sample", question="Show revenue"))


def test_missing_key_has_clear_error_after_authorization(store, tmp_path):
    service = AnalyticsService(store, tmp_path / "catalogs", Settings(openai_api_key=None))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        service.run(AnalysisRequest(user_id="toyesh", database_id="sample", question="Show revenue"))


def test_renderer_uses_shared_company_tokens():
    root = Path(__file__).parents[1]
    analysis = AnalysisResult(database_id="sample", question="x", summary="x", columns=["country", "total"], rows=[{"country": "NL", "total": 30}])
    style = CompanyStyle(root / "config" / "company_style.yaml")
    figure = render_chart(analysis, ChartSpec(chart_type="bar", x="country", y="total", title="Revenue"), style)
    assert figure.layout.paper_bgcolor == style.colors["transparent"]
    assert figure.layout.plot_bgcolor == style.colors["transparent"]
    assert figure.layout.font.color == style.colors["ink"]
    assert figure.data[0].marker.color == style.colors["accent"]


def test_table_chart_returns_no_plot():
    analysis = AnalysisResult(database_id="sample", question="x", summary="x")
    assert render_chart(analysis, ChartSpec(chart_type="table", title="Data"), CompanyStyle(Path(__file__).parents[1] / "config" / "company_style.yaml")) is None


def test_demo_reset_restores_the_canonical_pre_onboarding_state(store, tmp_path):
    store.register_database("sakila", "datasets/sakila.db")
    store.grant("donne", "sakila")
    demo = DemoStateService(store, tmp_path / "catalogs")
    assert not demo.check().is_canonical
    assert demo.reset().is_canonical
    assert store.accessible_databases("donne") == []
    assert "sakila" not in store.registry()["databases"]


def test_demo_reset_preserves_non_governance_registry_metadata(tmp_path):
    from analytics_command_center.registry import ConfigStore

    registry = {
        "databases": {
            **CANONICAL_REGISTRY["databases"],
        }
    }
    registry["databases"]["chinook"] = {
        **registry["databases"]["chinook"],
        "examples": [{"label": "Top revenue", "question": "Which countries generate the most revenue?"}],
    }
    registry_path, acl_path = tmp_path / "registry.yaml", tmp_path / "acl.yaml"
    import yaml
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False))
    acl_path.write_text(yaml.safe_dump(CANONICAL_ACL, sort_keys=False))
    demo = DemoStateService(ConfigStore(registry_path, acl_path), tmp_path / "catalogs")

    assert demo.check().is_canonical
    assert demo.reset().is_canonical
    assert ConfigStore(registry_path, acl_path).database("chinook")["examples"] == registry["databases"]["chinook"]["examples"]


def test_supplied_chinook_reference_query_has_known_top_five():
    database = Path(__file__).parents[1] / "datasets" / "chinook.db"
    if not database.is_file():
        pytest.skip("Supplied Chinook database is not present")
    assert chinook_revenue_reference(SQLiteAdapter(database)) == [
        {"country": "USA", "revenue": 523.06},
        {"country": "Canada", "revenue": 303.96},
        {"country": "France", "revenue": 195.1},
        {"country": "Brazil", "revenue": 190.1},
        {"country": "Germany", "revenue": 156.48},
    ]


def test_live_error_message_does_not_echo_exception_content():
    assert safe_live_error(RuntimeError("credential-like text must not be shown")) == (
        "Live agent request failed. Check connectivity and OpenAI configuration, then try again."
    )


def test_benchmark_compares_numeric_values_with_tolerance_but_categories_exactly():
    assert rows_match(
        [{"country": "USA", "revenue": 523.06}],
        [{"country": "USA", "revenue": 523.0600000000003}],
    )
    assert not rows_match(
        [{"country": "USA", "revenue": 523.06}],
        [{"country": "Canada", "revenue": 523.0600000000003}],
    )
    assert not rows_match(
        [{"country": "USA", "revenue": 523.06}],
        [{"country": "USA", "revenue": 523.07}],
    )


def test_benchmark_allows_tie_order_only_when_the_case_does_not_require_it():
    expected = [{"genre": "Classical", "revenue": 40.59}, {"genre": "R&B/Soul", "revenue": 40.59}]
    actual = [{"genre": "R&B/Soul", "revenue": 40.59}, {"genre": "Classical", "revenue": 40.59}]
    assert not rows_match(expected, actual)
    assert rows_match(expected, actual, order_required=False)
    assert is_non_increasing(actual, "revenue")


def test_default_model_is_gpt_5():
    assert Settings(openai_api_key=None).openai_default_model == "gpt-5"


def test_supplied_chinook_temporal_and_genre_references_are_real_and_bounded():
    adapter = SQLiteAdapter(Path(__file__).parents[1] / "datasets" / "chinook.db")
    monthly = chinook_temporal_reference(adapter)
    genres = chinook_genre_reference(adapter)
    assert len(monthly) == 60
    assert monthly[0] == {"month": "2009-01", "revenue": 35.64}
    assert monthly[-1] == {"month": "2013-12", "revenue": 38.62}
    assert genres[:3] == [
        {"genre": "Rock", "revenue": 826.65},
        {"genre": "Latin", "revenue": 382.14},
        {"genre": "Metal", "revenue": 261.36},
    ]


def test_supplied_sakila_category_revenue_reference_is_real():
    database = Path(__file__).parents[1] / "datasets" / "sakila.db"
    if not database.is_file():
        pytest.skip("Supplied Sakila database is not present")
    rows = sakila_category_revenue_reference(SQLiteAdapter(database))
    assert len(rows) == 16
    assert rows[0]["revenue"] >= rows[-1]["revenue"]


def test_supplied_northwind_catalog_has_no_declared_foreign_keys():
    database = Path(__file__).parents[1] / "datasets" / "northwind_small.sqlite"
    if not database.is_file():
        pytest.skip("Supplied Northwind database is not present")
    catalog = SQLiteAdapter(database).schema_catalog("northwind")
    assert len(catalog.foreign_keys) == 0
    assert {"Category", "Product", "OrderDetail"}.issubset({table.name for table in catalog.tables})
