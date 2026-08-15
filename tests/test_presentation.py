from analytics_command_center.models import AnalysisResult, ChartSpec
from analytics_command_center.presentation import format_result_scope


def _analysis(*, columns, rows, row_count=0, truncated=False):
    return AnalysisResult(
        database_id="chinook",
        question="x",
        summary="x",
        columns=columns,
        rows=rows,
        row_count=row_count,
        truncated=truncated,
    )


def test_result_scope_prefers_a_clear_time_range():
    analysis = _analysis(
        columns=["month", "revenue"],
        rows=[{"month": "2024-01-01", "revenue": 10}, {"month": "2024-03-01", "revenue": 20}],
        row_count=2,
    )

    assert format_result_scope(analysis, ChartSpec(chart_type="line", x="month", y="revenue", title="Revenue")) == "Jan 2024–Mar 2024"


def test_result_scope_uses_an_explicit_display_label_with_safe_pluralization():
    analysis = _analysis(
        columns=["country", "revenue"],
        rows=[{"country": "NL", "revenue": 10}, {"country": "DE", "revenue": 20}],
        row_count=2,
    )

    assert format_result_scope(analysis, ChartSpec(chart_type="bar", x="country", y="revenue", title="Revenue", x_label="Country")) == "2 countries"


def test_result_scope_falls_back_to_a_neutral_row_count_without_a_display_label():
    analysis = _analysis(columns=["value"], rows=[{"value": 10}, {"value": 20}], row_count=2)

    assert format_result_scope(analysis, ChartSpec(chart_type="bar", x="value", y="value", title="Values")) == "2 rows"


def test_result_scope_marks_truncated_output_as_bounded():
    analysis = _analysis(columns=["value"], rows=[{"value": 10}], row_count=100, truncated=True)

    assert format_result_scope(analysis, ChartSpec(chart_type="bar", x="value", y="value", title="Values")) == "100 rows shown (bounded)"
