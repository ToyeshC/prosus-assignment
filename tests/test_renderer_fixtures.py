from pathlib import Path

import pytest

from analytics_command_center.models import AnalysisResult, ChartSpec
from analytics_command_center.rendering import CompanyStyle, render_chart

ROOT = Path(__file__).parents[1]


def _style() -> CompanyStyle:
    return CompanyStyle(ROOT / "config" / "company_style.yaml")


def _analysis(columns: list[str], rows: list[dict]) -> AnalysisResult:
    return AnalysisResult(database_id="fixture", question="fixture", summary="fixture", columns=columns, rows=rows)


def test_five_value_ranking_keeps_order_and_uses_categorical_policy():
    rows = [{"country": country, "revenue": value} for country, value in [
        ("USA", 523.06),
        ("Canada", 303.96),
        ("France", 195.10),
        ("Brazil", 190.10),
        ("Germany", 156.48),
    ]]
    analysis = _analysis(["country", "revenue"], rows)
    figure = render_chart(
        analysis,
        ChartSpec(chart_type="bar", x="country", y="revenue", title="Top countries", sort="descending"),
        _style(),
    )

    assert figure is not None
    assert list(figure.data[0].x) == [row["country"] for row in rows]
    assert figure.layout.xaxis.showgrid is False
    assert figure.layout.yaxis.showgrid is True
    assert figure.layout.height == 340


def test_twenty_five_value_ranking_limits_only_chart_display():
    rows = [{"genre": f"Genre {index}", "total": 100 - index} for index in range(25)]
    analysis = _analysis(["genre", "total"], rows)
    figure = render_chart(
        analysis,
        ChartSpec(chart_type="bar", x="genre", y="total", title="Top genres", sort="descending"),
        _style(),
    )

    assert figure is not None
    assert len(figure.data[0].x) == 12
    assert len(analysis.rows) == 25
    assert figure.layout.meta["display_note"] == "Showing top 12 of 25 results"


@pytest.mark.parametrize("count", [6, 60])
def test_temporal_line_normalizes_copy_and_bounds_ticks(count: int):
    rows = [
        {
            "month": f"{2009 + (index - 1) // 12:04d}-{((index - 1) % 12) + 1:02d}",
            "revenue": float(index),
        }
        for index in range(1, count + 1)
    ]
    analysis = _analysis(["month", "revenue"], rows)
    figure = render_chart(
        analysis,
        ChartSpec(chart_type="line", x="month", y="revenue", title="Revenue over time", sort="ascending"),
        _style(),
    )

    assert figure is not None
    assert len(figure.data[0].x) == count
    assert figure.layout.xaxis.type == "date"
    assert figure.layout.xaxis.nticks == 6
    assert figure.layout.xaxis.tickangle == 0
    assert figure.data[0].mode == ("lines+markers" if count == 6 else "lines")
    assert analysis.rows == rows


def test_numeric_scatter_prioritizes_marks_over_category_treatment():
    analysis = _analysis(
        ["height", "weight"],
        [{"height": 1.6, "weight": 55}, {"height": 1.8, "weight": 72}, {"height": 1.9, "weight": 84}],
    )
    figure = render_chart(
        analysis,
        ChartSpec(chart_type="scatter", x="height", y="weight", title="Height and weight"),
        _style(),
    )

    assert figure is not None
    assert figure.data[0].marker.size == 8
    assert figure.layout.xaxis.showgrid is False
    assert figure.layout.yaxis.showgrid is True


def test_temporal_scatter_uses_same_temporal_policy_as_line():
    analysis = _analysis(
        ["date", "value"],
        [{"date": "2024-01-01", "value": 2}, {"date": "2024-02-01", "value": 4}],
    )
    figure = render_chart(
        analysis,
        ChartSpec(chart_type="scatter", x="date", y="value", title="Values over time"),
        _style(),
    )

    assert figure is not None
    assert figure.layout.xaxis.type == "date"
    assert figure.layout.xaxis.tickformat == "%b %d, %Y"


@pytest.mark.parametrize(
    ("chart_type", "spec", "columns", "rows"),
    [
        (
            "histogram",
            ChartSpec(chart_type="histogram", x="value", title="Distribution"),
            ["value"],
            [{"value": value} for value in [1.1, 1.2, 1.4, 1.8, 2.1, 2.2]],
        ),
        (
            "box",
            ChartSpec(chart_type="box", x="group", y="value", title="Grouped values"),
            ["group", "value"],
            [{"group": "A", "value": 1}, {"group": "A", "value": 2}, {"group": "B", "value": 3}],
        ),
        (
            "heatmap",
            ChartSpec(chart_type="heatmap", x="column", y="row", title="Matrix"),
            ["column", "row"],
            [{"column": "A", "row": "X"}, {"column": "B", "row": "X"}, {"column": "A", "row": "Y"}],
        ),
    ],
)
def test_distribution_and_matrix_families_render_with_family_layout(chart_type, spec, columns, rows):
    figure = render_chart(_analysis(columns, rows), spec, _style())

    assert figure is not None
    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figure.layout.plot_bgcolor == "rgba(0,0,0,0)"
    if chart_type == "heatmap":
        assert figure.layout.height == 380
        assert figure.layout.coloraxis.colorbar.thickness == 10


@pytest.mark.parametrize("chart_type", ["pie", "donut"])
def test_circular_families_keep_small_category_set_and_tonal_palette(chart_type: str):
    rows = [{"category": category, "total": total} for category, total in [("A", 4), ("B", 3), ("C", 2)]]
    figure = render_chart(
        _analysis(["category", "total"], rows),
        ChartSpec(chart_type=chart_type, x="category", y="total", title="Share"),
        _style(),
    )

    assert figure is not None
    assert figure.layout.showlegend is True
    assert len(figure.data[0].labels) == 3


def test_large_circular_result_preserves_existing_other_policy():
    rows = [{"category": f"Category {index}", "total": 100 - index} for index in range(25)]
    figure = render_chart(
        _analysis(["category", "total"], rows),
        ChartSpec(chart_type="donut", x="category", y="total", title="Share", notes="Top categories"),
        _style(),
    )

    assert figure is not None
    assert len(figure.data[0].labels) == 12
    assert "Other" in figure.data[0].labels
