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
    assert "$" not in (figure.layout.yaxis.tickformat or "")
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


def test_display_labels_never_append_numeric_measure_values():
    analysis = _analysis(
        columns=["category", "sales"],
        rows=[{"category": "Beverages", "sales": 267868.18}, {"category": "Dairy", "sales": 234507.285}],
    )
    spec = ChartSpec(
        chart_type="bar",
        x="category",
        y="sales",
        title="Category sales",
        label_fields=["category", "sales"],
    )

    figure = render_chart(analysis, spec, _style())

    assert list(figure.data[0].x) == ["Beverages", "Dairy"]
    assert all("267868" not in str(value) and "234507" not in str(value) for value in figure.data[0].x)


def test_display_labels_reject_numeric_measure_strings_too():
    analysis = _analysis(
        columns=["category", "sales_text", "score"],
        rows=[
            {"category": "Beverages", "sales_text": "267868.18", "score": 1},
            {"category": "Dairy", "sales_text": "234507.285", "score": 2},
        ],
    )
    spec = ChartSpec(chart_type="bar", x="category", y="score", title="Category sales", label_fields=["category", "sales_text"])

    figure = render_chart(analysis, spec, _style())

    assert list(figure.data[0].x) == ["Beverages", "Dairy"]


def test_composite_labels_keep_only_safe_human_readable_fields():
    analysis = _analysis(
        columns=["customer_id", "first_name", "last_name", "total_spent"],
        rows=[
            {"customer_id": 7, "first_name": "Frank", "last_name": "Ralston", "total_spent": 43.62},
            {"customer_id": 2, "first_name": "Frank", "last_name": "Harris", "total_spent": 37.62},
        ],
    )
    spec = ChartSpec(
        chart_type="bar",
        x="first_name",
        y="total_spent",
        title="Customers",
        label_fields=["first_name", "last_name", "total_spent"],
        identity_field="customer_id",
    )

    figure = render_chart(analysis, spec, _style())

    assert list(figure.data[0].x) == ["Frank · Ralston", "Frank · Harris"]
    assert all("43.62" not in str(value) and "37.62" not in str(value) for value in figure.data[0].x)


def test_temporal_normalization_precedes_label_handling_and_keeps_every_point():
    rows = [
        {"month": "2024-01", "revenue": 10.0},
        {"month": "2024-02", "revenue": 20.0},
        {"month": "2024-03", "revenue": 30.0},
    ]
    analysis = _analysis(columns=["month", "revenue"], rows=rows)
    spec = ChartSpec(
        chart_type="line",
        x="month",
        y="revenue",
        title="Revenue over time",
        label_fields=["month", "revenue"],
    )

    figure = render_chart(analysis, spec, _style())

    assert len(figure.data[0].x) == len(rows)
    assert figure.layout.xaxis.type == "date"
    assert all(" · " not in str(value) for value in figure.data[0].x)
    assert "customdata[0]" in figure.data[0].hovertemplate
    assert analysis.rows == rows


def test_question_duplicate_chart_title_is_suppressed_but_useful_title_remains():
    analysis = _analysis(
        columns=["country", "revenue"],
        rows=[{"country": "USA", "revenue": 523.06}],
    )
    duplicate = render_chart(
        AnalysisResult(
            database_id="sample",
            question="Top countries by revenue?",
            summary="x",
            columns=analysis.columns,
            rows=analysis.rows,
        ),
        ChartSpec(chart_type="bar", x="country", y="revenue", title="Top countries by revenue?"),
        _style(),
    )
    useful = render_chart(analysis, ChartSpec(chart_type="bar", x="country", y="revenue", title="Top countries"), _style())

    assert duplicate.layout.title.text == ""
    assert useful.layout.title.text == "Top countries"


def test_dense_ranked_categories_use_horizontal_bar_orientation_without_changing_chart_type():
    rows = [{"category": f"A very long category label {index}", "value": 100 - index} for index in range(13)]
    analysis = _analysis(columns=["category", "value"], rows=rows)

    figure = render_chart(
        analysis,
        ChartSpec(chart_type="bar", x="category", y="value", title="Ranking", sort="descending"),
        _style(),
    )

    assert figure.data[0].type == "bar"
    assert figure.data[0].orientation == "h"
    assert list(figure.data[0].y) == [row["category"] for row in rows[:12]]
    assert figure.layout.xaxis.showgrid is True
    assert figure.layout.yaxis.showgrid is False
    assert len(analysis.rows) == 13


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
