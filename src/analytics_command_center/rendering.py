"""Deterministic Plotly renderer consuming only validated ChartSpec and shared tokens."""

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yaml

from .models import AnalysisResult, ChartSpec
from .visualization_capabilities import CAPABILITY_IDS

_RANK_DISPLAY_LIMIT = 12
_CURRENCY_CONTEXT = re.compile(r"(?:revenue|sales|amount|cost|currency|usd|\$)", re.IGNORECASE)


class CompanyStyle:
    def __init__(self, path: Path):
        payload = yaml.safe_load(path.read_text())
        self.colors = payload["colors"]
        self.fonts = payload["fonts"]
        self.layout = payload["layout"]


def render_chart(analysis: AnalysisResult, spec: ChartSpec, style: CompanyStyle) -> go.Figure | None:
    if spec.chart_type not in CAPABILITY_IDS:
        raise ValueError(f"Unsupported chart type: {spec.chart_type}")
    if spec.chart_type in {"none", "table"}:
        return None
    frame, display_note = _display_frame(analysis, spec)
    x_axis_title = spec.x_label or spec.x
    category_orders = None
    if spec.label_fields:
        missing = [field for field in spec.label_fields if field not in frame.columns]
        if missing:
            raise ValueError("Chart label fields are not present in the analysis result")
        frame = frame.copy()
        frame["__display_label"] = frame[spec.label_fields].fillna("").astype(str).agg(" · ".join, axis=1)
        category_orders = {"__display_label": frame["__display_label"].tolist()}
        spec = spec.model_copy(update={"x": "__display_label"})
        x_axis_title = spec.x_label or "Category"
    if frame.empty:
        return None
    if spec.chart_type == "bar":
        figure = px.bar(frame, x=spec.x, y=spec.y, color_discrete_sequence=[style.colors["accent"]], custom_data=[spec.identity_field] if spec.identity_field else None, category_orders=category_orders)
    elif spec.chart_type == "line":
        figure = px.line(frame, x=spec.x, y=spec.y, color_discrete_sequence=[style.colors["accent"]], custom_data=[spec.identity_field] if spec.identity_field else None, category_orders=category_orders)
    elif spec.chart_type == "scatter":
        figure = px.scatter(frame, x=spec.x, y=spec.y, color_discrete_sequence=[style.colors["accent"]], custom_data=[spec.identity_field] if spec.identity_field else None, category_orders=category_orders)
    elif spec.chart_type == "histogram":
        figure = px.histogram(frame, x=spec.x, color_discrete_sequence=[style.colors["accent"]])
    elif spec.chart_type == "pie":
        if spec.notes and len(frame) > 12 and isinstance(spec.y, str):
            frame = _top_categories(frame, spec.x, spec.y)
        figure = px.pie(frame, names=spec.x, values=spec.y, color_discrete_sequence=[style.colors["accent"]], custom_data=[spec.identity_field] if spec.identity_field else None, category_orders=category_orders)
    elif spec.chart_type == "donut":
        if spec.notes and len(frame) > 12 and isinstance(spec.y, str):
            frame = _top_categories(frame, spec.x, spec.y)
        figure = px.pie(frame, names=spec.x, values=spec.y, hole=0.45, color_discrete_sequence=[style.colors["accent"]], custom_data=[spec.identity_field] if spec.identity_field else None, category_orders=category_orders)
    elif spec.chart_type == "box":
        figure = px.box(frame, x=spec.x, y=spec.y, color_discrete_sequence=[style.colors["accent"]], custom_data=[spec.identity_field] if spec.identity_field else None, category_orders=category_orders)
    elif spec.chart_type == "heatmap":
        if not isinstance(spec.y, str):
            raise ValueError("Heatmaps require one y field")
        figure = px.density_heatmap(frame, x=spec.x, y=spec.y, color_continuous_scale=[style.colors["surface"], style.colors["accent"]])
    else:
        raise ValueError(f"Unsupported chart type: {spec.chart_type}")
    figure.update_layout(
        title=spec.title,
        height=style.layout["chart_height"],
        paper_bgcolor=style.colors["transparent"],
        plot_bgcolor=style.colors["transparent"],
        font={"family": style.fonts["sans"], "color": style.colors["ink"]},
        margin={"l": 24, "r": 24, "t": 60, "b": 30},
        meta={"display_note": display_note},
    )
    axis_style = {
        "gridcolor": style.colors["grid"],
        "zerolinecolor": style.colors["grid"],
        "linecolor": style.colors["border"],
        "tickcolor": style.colors["border"],
        "showline": True,
        "ticks": "outside",
    }
    x_numeric = _is_numeric_column(frame, spec.x)
    y_numeric = _is_numeric_column(frame, spec.y)
    figure.update_xaxes(title=x_axis_title, tickformat=_numeric_tick_format(spec) if x_numeric else None, **axis_style)
    figure.update_yaxes(title=spec.y_label or spec.y, tickformat=_numeric_tick_format(spec) if y_numeric else None, **axis_style)
    _apply_hover_format(figure, spec, x_axis_title, x_numeric=x_numeric, y_numeric=y_numeric)
    return figure


def _display_frame(analysis: AnalysisResult, spec: ChartSpec) -> tuple[pd.DataFrame, str | None]:
    """Return a copied chart frame and an optional chart-only display caption."""
    frame = pd.DataFrame(analysis.rows, columns=analysis.columns).copy()
    if not _is_ranked_categorical_bar(spec, frame):
        return frame, None

    assert isinstance(spec.y, str)
    ordered = frame.sort_values(spec.y, ascending=spec.sort == "ascending", kind="stable")
    if len(ordered) <= _RANK_DISPLAY_LIMIT:
        return ordered, None
    return ordered.head(_RANK_DISPLAY_LIMIT), f"Showing top {_RANK_DISPLAY_LIMIT} of {len(ordered)} results"


def _is_ranked_categorical_bar(spec: ChartSpec, frame: pd.DataFrame) -> bool:
    """Return true only for sorted Bar charts with categorical x and numeric y."""
    return (
        spec.chart_type == "bar"
        and spec.sort in {"ascending", "descending"}
        and isinstance(spec.x, str)
        and isinstance(spec.y, str)
        and _is_numeric_column(frame, spec.y)
        and not _is_numeric_column(frame, spec.x)
    )


def _is_currency_context(spec: ChartSpec) -> bool:
    """Return true only for explicit currency/revenue/sales/amount/cost labels."""
    labels = " ".join(value for value in (spec.title, spec.y_label) if value)
    return bool(_CURRENCY_CONTEXT.search(labels))


def _numeric_tick_format(spec: ChartSpec) -> str:
    """Return `$,.2f` for currency context and `,.2f` otherwise."""
    return "$,.2f" if _is_currency_context(spec) else ",.2f"


def _is_numeric_column(frame: pd.DataFrame, column: str | list[str] | None) -> bool:
    return isinstance(column, str) and column in frame.columns and pd.api.types.is_numeric_dtype(frame[column])


def _apply_hover_format(
    figure: go.Figure,
    spec: ChartSpec,
    x_axis_title: str | None,
    *,
    x_numeric: bool,
    y_numeric: bool,
) -> None:
    number_format = _numeric_tick_format(spec)
    x_value = f"%{{x:{number_format}}}" if x_numeric else "%{x}"
    y_value = f"%{{y:{number_format}}}" if y_numeric else "%{y}"
    x_label = x_axis_title or spec.x or "Value"
    y_label = spec.y_label or spec.y or "Value"

    if spec.chart_type in {"pie", "donut"}:
        figure.update_traces(hovertemplate=f"{x_label}=%{{label}}<br>{y_label}=%{{value:{number_format}}}<extra></extra>")
    elif spec.chart_type == "heatmap":
        figure.update_traces(hovertemplate=f"{x_label}=%{{x}}<br>{y_label}=%{{y}}<br>Count=%{{z:,.0f}}<extra></extra>")
    elif spec.chart_type == "histogram":
        figure.update_traces(hovertemplate=f"{x_label}={x_value}<br>Count=%{{y:,.0f}}<extra></extra>")
    else:
        figure.update_traces(hovertemplate=f"{x_label}={x_value}<br>{y_label}={y_value}<extra></extra>")


def _top_categories(frame: pd.DataFrame, category: str | None, value: str) -> pd.DataFrame:
    if not category:
        return frame
    ordered = frame.sort_values(value, ascending=False)
    top = ordered.head(11).copy()
    remainder = ordered.iloc[11:]
    if not remainder.empty:
        top.loc[len(top)] = {category: "Other", value: remainder[value].sum()}
    return top
