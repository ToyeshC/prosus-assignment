"""Single source of truth for deterministic visualization support."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class VisualizationCapability:
    identifier: str
    label: str


CAPABILITIES: tuple[VisualizationCapability, ...] = (
    VisualizationCapability("bar", "Bar"),
    VisualizationCapability("line", "Line"),
    VisualizationCapability("pie", "Pie"),
    VisualizationCapability("donut", "Donut"),
    VisualizationCapability("scatter", "Scatter"),
    VisualizationCapability("histogram", "Histogram"),
    VisualizationCapability("box", "Box plot"),
    VisualizationCapability("heatmap", "Heatmap"),
    VisualizationCapability("table", "Table only"),
    VisualizationCapability("none", "No chart"),
)
CAPABILITY_IDS = frozenset(capability.identifier for capability in CAPABILITIES)

QUICK_CHOICES = ("Auto", "Bar", "Line", "Pie / Donut", "Scatter", "Histogram", "Table only", "Custom…")
_QUICK_TO_CAPABILITY = {
    "Bar": "bar",
    "Line": "line",
    "Pie / Donut": "pie",
    "Scatter": "scatter",
    "Histogram": "histogram",
    "Table only": "table",
}


def capability_names() -> list[str]:
    return [capability.identifier for capability in CAPABILITIES if capability.identifier not in {"none", "table"}]


def explicit_capability(choice: str | None, custom_guidance: str | None = None) -> str | None:
    """Return an explicit supported type, or None when Auto needs semantic selection."""
    if choice in _QUICK_TO_CAPABILITY:
        return _QUICK_TO_CAPABILITY[choice]
    if choice != "Custom…" or not custom_guidance:
        return None
    words = set(re.findall(r"[a-z]+", custom_guidance.lower()))
    aliases = {
        "bar": "bar", "line": "line", "pie": "pie", "donut": "donut", "doughnut": "donut",
        "scatter": "scatter", "histogram": "histogram", "box": "box", "heatmap": "heatmap",
        "table": "table",
    }
    return next((capability for word, capability in aliases.items() if word in words), None)


def unsupported_visualization_requested(choice: str | None, custom_guidance: str | None = None) -> bool:
    if choice != "Custom…" or not custom_guidance:
        return False
    words = set(re.findall(r"[a-z]+", custom_guidance.lower()))
    chart_words = {"chart", "plot", "graph", "map", "treemap", "violin", "waterfall", "radar", "sankey", "funnel", "bubble"}
    return bool(words & chart_words) and explicit_capability(choice, custom_guidance) is None
