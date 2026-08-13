"""Deterministic Plotly renderer consuming only validated ChartSpec and shared tokens."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yaml

from .models import AnalysisResult, ChartSpec


class CompanyStyle:
    def __init__(self, path: Path):
        payload = yaml.safe_load(path.read_text())
        self.colors = payload["colors"]
        self.fonts = payload["fonts"]
        self.layout = payload["layout"]


def render_chart(analysis: AnalysisResult, spec: ChartSpec, style: CompanyStyle) -> go.Figure | None:
    if spec.chart_type in {"none", "table"}:
        return None
    frame = pd.DataFrame(analysis.rows, columns=analysis.columns)
    if frame.empty:
        return None
    if spec.chart_type == "bar":
        figure = px.bar(frame, x=spec.x, y=spec.y, color_discrete_sequence=[style.colors["mint"]])
    elif spec.chart_type == "line":
        figure = px.line(frame, x=spec.x, y=spec.y, color_discrete_sequence=[style.colors["mint"]])
    elif spec.chart_type == "scatter":
        figure = px.scatter(frame, x=spec.x, y=spec.y, color_discrete_sequence=[style.colors["mint"]])
    elif spec.chart_type == "histogram":
        figure = px.histogram(frame, x=spec.x, color_discrete_sequence=[style.colors["mint"]])
    else:
        raise ValueError(f"Unsupported chart type: {spec.chart_type}")
    figure.update_layout(
        title=spec.title,
        height=style.layout["chart_height"],
        paper_bgcolor=style.colors["canvas"],
        plot_bgcolor=style.colors["canvas"],
        font={"family": style.fonts["sans"], "color": style.colors["ink"]},
        margin={"l": 24, "r": 24, "t": 60, "b": 30},
    )
    figure.update_xaxes(title=spec.x_label or spec.x, gridcolor=style.colors["surface"])
    figure.update_yaxes(title=spec.y_label or spec.y, gridcolor=style.colors["surface"])
    return figure
