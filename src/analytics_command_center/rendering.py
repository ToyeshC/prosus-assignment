"""Deterministic Plotly renderer consuming only validated ChartSpec and shared tokens."""

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yaml

from .models import AnalysisResult, ChartSpec
from .visualization_capabilities import CAPABILITY_IDS

_RANK_DISPLAY_LIMIT = 12
_TEMPORAL_FIELD_CUES = re.compile(r"(?:date|time|month|year|quarter|week|day|period)", re.IGNORECASE)
_EXPLICIT_CURRENCY = re.compile(r"(?:\$|€|£|¥|\b(?:USD|EUR|GBP|JPY)\b)", re.IGNORECASE)
_EXPLICIT_PERCENT = re.compile(r"(?:%|\bpercent(?:age)?\b)", re.IGNORECASE)


@dataclass(frozen=True)
class _ChartPolicy:
    """Small deterministic presentation policy for one chart family."""

    height_key: str
    x_grid: bool = False
    y_grid: bool = True
    x_line: bool = False
    y_line: bool = True
    x_ticks: str = ""
    y_ticks: str = "outside"
    x_zeroline: bool = False
    y_zeroline: bool = False
    margins_key: str = "standard"


@dataclass(frozen=True)
class _PreparedFrame:
    frame: pd.DataFrame
    temporal: bool = False
    temporal_display_field: str | None = None
    temporal_tickformat: str | None = None


_CHART_POLICIES = {
    "bar": _ChartPolicy("categorical", x_zeroline=True, y_zeroline=True),
    "line": _ChartPolicy("categorical"),
    "scatter": _ChartPolicy("categorical", x_zeroline=True, y_zeroline=True),
    "histogram": _ChartPolicy("distribution", x_zeroline=True, y_zeroline=True),
    "box": _ChartPolicy("distribution"),
    "heatmap": _ChartPolicy("heatmap", x_grid=False, y_grid=False, x_line=False, y_line=False),
    "pie": _ChartPolicy("pie", x_grid=False, y_grid=False, x_line=False, y_line=False, margins_key="compact"),
    "donut": _ChartPolicy("pie", x_grid=False, y_grid=False, x_line=False, y_line=False, margins_key="compact"),
}


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
    category_orders = None
    if spec.label_fields:
        missing = [field for field in spec.label_fields if field not in frame.columns]
        if missing:
            raise ValueError("Chart label fields are not present in the analysis result")
        frame = frame.copy()
        frame["__display_label"] = frame[spec.label_fields].fillna("").astype(str).agg(" · ".join, axis=1)
        category_orders = {"__display_label": frame["__display_label"].tolist()}
        spec = spec.model_copy(update={"x": "__display_label"})
    if frame.empty:
        return None
    _validate_chart_spec_for_frame(spec, frame)
    prepared = _prepare_plot_frame(frame, spec)
    frame = prepared.frame
    custom_data_fields = _custom_data_fields(spec, prepared)
    palette = _chart_palette(style)
    discrete_color = [style.colors["accent"]]
    if spec.chart_type == "bar":
        figure = px.bar(frame, x=spec.x, y=spec.y, color_discrete_sequence=discrete_color, custom_data=custom_data_fields, category_orders=category_orders)
    elif spec.chart_type == "line":
        figure = px.line(frame, x=spec.x, y=spec.y, color_discrete_sequence=discrete_color, custom_data=custom_data_fields, category_orders=category_orders)
    elif spec.chart_type == "scatter":
        figure = px.scatter(frame, x=spec.x, y=spec.y, color_discrete_sequence=discrete_color, custom_data=custom_data_fields, category_orders=category_orders)
    elif spec.chart_type == "histogram":
        figure = px.histogram(frame, x=spec.x, color_discrete_sequence=discrete_color)
    elif spec.chart_type == "pie":
        if spec.notes and len(frame) > 12 and isinstance(spec.y, str):
            frame = _top_categories(frame, spec.x, spec.y)
        figure = px.pie(frame, names=spec.x, values=spec.y, color_discrete_sequence=palette, custom_data=custom_data_fields, category_orders=category_orders)
    elif spec.chart_type == "donut":
        if spec.notes and len(frame) > 12 and isinstance(spec.y, str):
            frame = _top_categories(frame, spec.x, spec.y)
        figure = px.pie(frame, names=spec.x, values=spec.y, hole=0.45, color_discrete_sequence=palette, custom_data=custom_data_fields, category_orders=category_orders)
    elif spec.chart_type == "box":
        figure = px.box(frame, x=spec.x, y=spec.y, color_discrete_sequence=discrete_color, custom_data=custom_data_fields, category_orders=category_orders)
    elif spec.chart_type == "heatmap":
        if not isinstance(spec.y, str):
            raise ValueError("Heatmaps require one y field")
        figure = px.density_heatmap(
            frame,
            x=spec.x,
            y=spec.y,
            color_continuous_scale=[style.colors.get("accent_soft", style.colors["surface"]), style.colors["accent"]],
        )
    else:
        raise ValueError(f"Unsupported chart type: {spec.chart_type}")
    _apply_layout_policy(figure, style, spec, frame, prepared, display_note)
    _apply_trace_policy(figure, style, spec, frame)
    x_axis_title = _axis_title(spec, "x", temporal=prepared.temporal)
    y_axis_title = _axis_title(spec, "y", temporal=prepared.temporal)
    x_numeric = _is_numeric_column(frame, spec.x)
    y_numeric = _is_numeric_column(frame, spec.y)
    x_tickformat = _axis_number_format(spec, frame[spec.x]) if x_numeric else None
    y_tickformat = _axis_number_format(spec, frame[spec.y]) if y_numeric and isinstance(spec.y, str) else None
    _apply_axis_policy(
        figure,
        style,
        spec,
        prepared,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        x_tickformat=x_tickformat,
        y_tickformat=y_tickformat,
    )
    _apply_hover_format(
        figure,
        spec,
        x_axis_title,
        x_numeric=x_numeric,
        y_numeric=y_numeric,
        temporal_display_index=_temporal_display_index(spec, prepared),
    )
    return figure


def _chart_palette(style: CompanyStyle) -> list[str]:
    """Return the deterministic tonal palette used by categorical circular charts."""
    palette = style.colors.get("chart_palette")
    return list(palette) if palette else [style.colors["accent"]]


def _custom_data_fields(spec: ChartSpec, prepared: _PreparedFrame) -> list[str] | None:
    fields: list[str] = []
    if spec.identity_field:
        fields.append(spec.identity_field)
    if prepared.temporal_display_field:
        fields.append(prepared.temporal_display_field)
    return fields or None


def _temporal_display_index(spec: ChartSpec, prepared: _PreparedFrame) -> int | None:
    if not prepared.temporal_display_field:
        return None
    return 1 if spec.identity_field else 0


def _prepare_plot_frame(frame: pd.DataFrame, spec: ChartSpec) -> _PreparedFrame:
    """Prepare a renderer-only plotting copy without changing analytical rows."""
    if spec.chart_type not in {"line", "scatter"} or not isinstance(spec.x, str):
        return _PreparedFrame(frame)
    if spec.x not in frame.columns or not _TEMPORAL_FIELD_CUES.search(spec.x):
        return _PreparedFrame(frame)

    values = frame[spec.x]
    non_null = values.dropna()
    if non_null.empty:
        return _PreparedFrame(frame)
    parsed = _parse_temporal_values(non_null, spec.x)
    if parsed is None or parsed.isna().any():
        return _PreparedFrame(frame)

    prepared = frame.copy()
    prepared["__temporal_display"] = values.map(_temporal_display_value)
    parsed_full = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    parsed_full.loc[non_null.index] = parsed.to_numpy()
    prepared[spec.x] = parsed_full
    return _PreparedFrame(
        prepared,
        temporal=True,
        temporal_display_field="__temporal_display",
        temporal_tickformat=_temporal_tickformat(parsed),
    )


def _parse_temporal_values(values: pd.Series, field_name: str) -> pd.Series | None:
    """Parse only clearly temporal fields; numeric data is not treated as dates by accident."""
    if pd.api.types.is_numeric_dtype(values):
        if not re.search(r"year", field_name, re.IGNORECASE):
            return None
        integers = pd.to_numeric(values, errors="coerce")
        if integers.isna().any() or not integers.between(1000, 9999).all():
            return None
        return pd.to_datetime(integers.astype(int).astype(str), format="%Y", errors="coerce")
    return pd.to_datetime(values, errors="coerce", format="mixed")


def _temporal_display_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _temporal_tickformat(parsed: pd.Series) -> str:
    span_days = max((parsed.max() - parsed.min()).days, 0)
    if span_days <= 45:
        return "%b %d, %Y"
    if span_days <= 8 * 365:
        return "%b %Y"
    return "%Y"


def _chart_policy(spec: ChartSpec, temporal: bool) -> _ChartPolicy:
    if temporal and spec.chart_type in {"line", "scatter"}:
        return _ChartPolicy("temporal")
    return _CHART_POLICIES.get(spec.chart_type, _ChartPolicy("categorical"))


def _chart_height(style: CompanyStyle, policy: _ChartPolicy) -> int:
    heights = style.layout.get("chart_heights", {})
    return int(heights.get(policy.height_key, style.layout.get("chart_height", 430)))


def _chart_margins(style: CompanyStyle, policy: _ChartPolicy) -> dict[str, int]:
    margins = style.layout.get("chart_margins", {})
    default = {"l": 56, "r": 18, "t": 44, "b": 42}
    return dict(margins.get(policy.margins_key, default))


def _apply_layout_policy(
    figure: go.Figure,
    style: CompanyStyle,
    spec: ChartSpec,
    frame: pd.DataFrame,
    prepared: _PreparedFrame,
    display_note: str | None,
) -> None:
    policy = _chart_policy(spec, prepared.temporal)
    chart = style.layout.get("chart", {})
    circular = spec.chart_type in {"pie", "donut"}
    figure.update_layout(
        title={
            "text": spec.title,
            "x": 0,
            "xanchor": "left",
            "y": 0.98,
            "yanchor": "top",
            "font": {"family": style.fonts["sans"], "size": chart.get("title_size", 15), "color": style.colors["ink"]},
        },
        height=_chart_height(style, policy),
        paper_bgcolor=style.colors["transparent"],
        plot_bgcolor=style.colors["transparent"],
        font={
            "family": style.fonts["sans"],
            "size": chart.get("axis_size", 11),
            "color": style.colors["ink"],
        },
        margin=_chart_margins(style, policy),
        hoverlabel={
            "bgcolor": style.colors["surface"],
            "bordercolor": style.colors["border"],
            "font": {"family": style.fonts["sans"], "size": chart.get("hover_size", 12), "color": style.colors["ink"]},
        },
        showlegend=circular,
        meta={"display_note": display_note},
    )
    if circular:
        figure.update_layout(
            legend={
                "font": {"family": style.fonts["sans"], "size": chart.get("axis_size", 11), "color": style.colors["ink"]},
                "itemsizing": "constant",
                "orientation": "v",
                "x": 1.02,
                "xanchor": "left",
                "y": 0.5,
                "yanchor": "middle",
            }
        )


def _apply_axis_policy(
    figure: go.Figure,
    style: CompanyStyle,
    spec: ChartSpec,
    prepared: _PreparedFrame,
    *,
    x_axis_title: str | None,
    y_axis_title: str | None,
    x_tickformat: str | None,
    y_tickformat: str | None,
) -> None:
    if spec.chart_type in {"pie", "donut"}:
        return
    policy = _chart_policy(spec, prepared.temporal)
    chart = style.layout.get("chart", {})
    axis_common = {
        "gridcolor": style.colors["grid"],
        "gridwidth": 1,
        "zerolinecolor": style.colors["grid"],
        "linecolor": style.colors["border"],
        "linewidth": 1,
        "tickcolor": style.colors["border"],
        "tickfont": {"family": style.fonts["sans"], "size": chart.get("axis_size", 11), "color": style.colors["muted"]},
    }
    x_options = {
        **axis_common,
        "showgrid": policy.x_grid,
        "showline": policy.x_line,
        "ticks": policy.x_ticks,
        "zeroline": policy.x_zeroline,
        "tickformat": x_tickformat,
        "tickangle": 0,
        "title": {"text": x_axis_title or "", "font": {"size": chart.get("axis_size", 11), "color": style.colors["muted"]}},
    }
    y_options = {
        **axis_common,
        "showgrid": policy.y_grid,
        "showline": policy.y_line,
        "ticks": policy.y_ticks,
        "zeroline": policy.y_zeroline,
        "tickformat": y_tickformat,
        "title": {"text": y_axis_title or "", "font": {"size": chart.get("axis_size", 11), "color": style.colors["muted"]}},
    }
    if prepared.temporal:
        x_options.update(type="date", tickformat=prepared.temporal_tickformat, nticks=6)
    figure.update_xaxes(**x_options)
    figure.update_yaxes(**y_options)
    if spec.chart_type == "heatmap":
        figure.update_coloraxes(
            colorbar={
                "thickness": 10,
                "outlinewidth": 0,
                "tickfont": {"family": style.fonts["sans"], "size": chart.get("axis_size", 11), "color": style.colors["muted"]},
            }
        )


def _apply_trace_policy(figure: go.Figure, style: CompanyStyle, spec: ChartSpec, frame: pd.DataFrame) -> None:
    chart = style.layout.get("chart", {})
    accent = style.colors["accent"]
    if spec.chart_type == "line":
        dense = len(frame) > 24
        figure.update_traces(
            mode="lines" if dense else "lines+markers",
            line={"color": accent, "width": chart.get("line_width", 2.25)},
            marker={
                "size": chart.get("dense_marker_size", 3) if dense else chart.get("marker_size", 7),
                "color": style.colors["canvas"],
                "line": {"color": accent, "width": 1.5},
            },
        )
    elif spec.chart_type == "scatter":
        figure.update_traces(
            marker={
                "size": chart.get("scatter_marker_size", 8),
                "color": accent,
                "opacity": 0.86,
                "line": {"color": style.colors["surface"], "width": 1},
            }
        )
    elif spec.chart_type == "bar":
        figure.update_layout(bargap=0.32)
        figure.update_traces(marker={"color": accent})
    elif spec.chart_type == "histogram":
        figure.update_layout(bargap=0.08)
        figure.update_traces(marker={"color": accent, "line": {"color": style.colors["surface"], "width": 0.5}})
    elif spec.chart_type == "box":
        figure.update_traces(
            marker={"color": accent, "size": chart.get("box_marker_size", 5), "opacity": 0.72},
            line={"color": accent, "width": 1.5},
            fillcolor=style.colors.get("accent_soft", style.colors["surface"]),
        )
    elif spec.chart_type in {"pie", "donut"}:
        figure.update_traces(
            marker={"line": {"color": style.colors["surface"], "width": 1}},
            textfont={"family": style.fonts["sans"], "size": chart.get("axis_size", 11), "color": style.colors["ink"]},
        )


def _axis_title(spec: ChartSpec, axis: str, *, temporal: bool) -> str | None:
    explicit = spec.x_label if axis == "x" else spec.y_label
    if explicit:
        return explicit
    if axis == "x" and temporal:
        return None
    if spec.chart_type in {"scatter", "heatmap"}:
        value = spec.x if axis == "x" else spec.y
        return value if isinstance(value, str) else None
    return None


def _unit_kind(spec: ChartSpec) -> str | None:
    """Return a unit only when the spec states one explicitly."""
    labels = " ".join(value for value in (spec.title, spec.y_label) if value)
    if not labels:
        return None
    if _EXPLICIT_CURRENCY.search(labels):
        if "$" in labels or re.search(r"\bUSD\b", labels, re.IGNORECASE):
            return "usd"
        if "€" in labels or re.search(r"\bEUR\b", labels, re.IGNORECASE):
            return "eur"
        if "£" in labels or re.search(r"\bGBP\b", labels, re.IGNORECASE):
            return "gbp"
        if "¥" in labels or re.search(r"\bJPY\b", labels, re.IGNORECASE):
            return "jpy"
    if _EXPLICIT_PERCENT.search(labels):
        return "percent"
    return None


def _unit_prefix(unit: str | None) -> str:
    return {"usd": "$", "eur": "€", "gbp": "£", "jpy": "¥"}.get(unit, "")


def _axis_precision(values: pd.Series) -> int:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return 0
    magnitude = float(numeric.abs().max())
    if magnitude >= 10:
        return 0
    if magnitude >= 1:
        return 1
    return 2


def _axis_number_format(spec: ChartSpec, values: pd.Series) -> str:
    unit = _unit_kind(spec)
    precision = _axis_precision(values)
    if unit == "percent":
        return f".{max(0, min(1, precision))}%"
    return f"{_unit_prefix(unit)},.{precision}f"


def _hover_number_format(spec: ChartSpec) -> str:
    unit = _unit_kind(spec)
    if unit == "percent":
        return ".2%"
    return f"{_unit_prefix(unit)},.2f"


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


def _is_numeric_column(frame: pd.DataFrame, column: str | list[str] | None) -> bool:
    return isinstance(column, str) and column in frame.columns and pd.api.types.is_numeric_dtype(frame[column])


def _validate_chart_spec_for_frame(spec: ChartSpec, frame: pd.DataFrame) -> None:
    """Reject malformed categorical chart mappings without guessing a replacement."""
    if spec.chart_type not in {"bar", "pie", "donut", "box"}:
        return
    if not isinstance(spec.x, str) or not isinstance(spec.y, str):
        raise TypeError(f"A {spec.chart_type} chart requires a categorical x field and a numeric y field")
    if spec.x not in frame.columns or spec.y not in frame.columns:
        raise ValueError("Chart fields are not present in the analysis result")
    if _is_numeric_column(frame, spec.x) or not _is_numeric_column(frame, spec.y):
        raise ValueError(f"A {spec.chart_type} chart requires a categorical x field and a numeric y field")


def _apply_hover_format(
    figure: go.Figure,
    spec: ChartSpec,
    x_axis_title: str | None,
    *,
    x_numeric: bool,
    y_numeric: bool,
    temporal_display_index: int | None,
) -> None:
    number_format = _hover_number_format(spec)
    x_value = f"%{{x:{number_format}}}" if x_numeric else "%{x}"
    if temporal_display_index is not None:
        x_value = f"%{{customdata[{temporal_display_index}]}}"
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
