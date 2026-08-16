from pathlib import Path

import pytest

from analytics_command_center.models import AnalysisResult, ChartSpec
from analytics_command_center.rendering import CompanyStyle, render_chart

ROOT = Path(__file__).parents[1]


def _analysis(*, columns, rows):
    return AnalysisResult(database_id="sample", question="x", summary="x", columns=columns, rows=rows)


def _style():
    return CompanyStyle(ROOT / "config" / "company_style.yaml")


def _bar_spec(*, x="country", y="revenue", sort="descending", **kwargs):
    return ChartSpec(chart_type="bar", x=x, y=y, title="Revenue", sort=sort, **kwargs)


def test_renderer_formats_decimal_hover_values_without_inferring_currency():
    value = 39.899999999999996
    analysis = _analysis(columns=["country", "revenue"], rows=[{"country": "USA", "revenue": value}])

    figure = render_chart(analysis, _bar_spec(), _style())

    assert "revenue=%{y:,.2f}" in figure.data[0].hovertemplate
    assert "$" not in figure.data[0].hovertemplate
    assert analysis.rows[0]["revenue"] == value


def test_renderer_uses_currency_format_only_for_explicit_unit():
    analysis = _analysis(columns=["country", "revenue"], rows=[{"country": "USA", "revenue": 39.899999999999996}])
    spec = _bar_spec(y="revenue", y_label="Revenue (USD)")

    figure = render_chart(analysis, spec, _style())

    assert "Revenue (USD)=%{y:$,.2f}" in figure.data[0].hovertemplate


def test_ranked_categorical_bar_uses_top_twelve_display_rows_only():
    rows = [{"genre": f"Genre {index}", "revenue": 30 - index} for index in range(25)]
    analysis = _analysis(columns=["genre", "revenue"], rows=rows)

    figure = render_chart(analysis, _bar_spec(x="genre", y="revenue"), _style())

    assert len(figure.data[0].x) == 12
    assert figure.layout.meta["display_note"] == "Showing top 12 of 25 results"
    assert len(analysis.rows) == 25


def test_temporal_line_does_not_apply_ranked_display_limit():
    rows = [{"month": f"2024-{index:02d}", "revenue": float(index)} for index in range(1, 26)]
    analysis = _analysis(columns=["month", "revenue"], rows=rows)
    spec = ChartSpec(chart_type="line", x="month", y="revenue", title="Revenue over time", sort="ascending")

    figure = render_chart(analysis, spec, _style())

    assert len(figure.data[0].x) == 25
    assert figure.layout.meta["display_note"] is None


def test_pie_retains_existing_top_categories_and_other_policy():
    rows = [{"genre": f"Genre {index}", "revenue": 30 - index} for index in range(25)]
    analysis = _analysis(columns=["genre", "revenue"], rows=rows)
    spec = ChartSpec(chart_type="pie", x="genre", y="revenue", title="Revenue", notes="Top categories")

    figure = render_chart(analysis, spec, _style())

    assert len(figure.data[0].labels) == 12
    assert "Other" in figure.data[0].labels
    assert len(analysis.rows) == 25


def test_renderer_rejects_malformed_categorical_chart_without_reinterpreting_data():
    analysis = _analysis(
        columns=["country", "revenue"],
        rows=[{"country": "USA", "revenue": 523.06}, {"country": "Canada", "revenue": 303.96}],
    )
    malformed = ChartSpec(
        chart_type="bar",
        x="revenue",
        y="revenue",
        title="Top countries by revenue",
        x_label="Country",
        y_label="Revenue (USD)",
    )

    with pytest.raises(ValueError, match="categorical x field and a numeric y field"):
        render_chart(analysis, malformed, _style())

    assert analysis.rows[0] == {"country": "USA", "revenue": 523.06}
