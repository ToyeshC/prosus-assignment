"""Deterministic Plotly renderer consuming only validated ChartSpec and shared tokens."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yaml

from .models import AnalysisResult, ChartSpec
from .visualization_capabilities import CAPABILITY_IDS


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
    frame = pd.DataFrame(analysis.rows, columns=analysis.columns)
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
    )
    axis_style = {
        "gridcolor": style.colors["grid"],
        "zerolinecolor": style.colors["grid"],
        "linecolor": style.colors["border"],
        "tickcolor": style.colors["border"],
        "showline": True,
        "ticks": "outside",
    }
    figure.update_xaxes(title=x_axis_title, **axis_style)
    figure.update_yaxes(title=spec.y_label or spec.y, **axis_style)
    return figure


def _top_categories(frame: pd.DataFrame, category: str | None, value: str) -> pd.DataFrame:
    if not category:
        return frame
    ordered = frame.sort_values(value, ascending=False)
    top = ordered.head(11).copy()
    remainder = ordered.iloc[11:]
    if not remainder.empty:
        top.loc[len(top)] = {category: "Other", value: remainder[value].sum()}
    return top
