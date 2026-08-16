"""Presentation-only helpers for concise, human-useful result context."""

from __future__ import annotations

import re
from html import escape

import pandas as pd

from .models import AnalysisResult, ChartSpec

_TIME_DIMENSION = re.compile(r"(?:date|day|week|month|quarter|year|time|period)", re.IGNORECASE)
_DISPLAY_LABEL = re.compile(r"^[A-Za-z]+(?:[ -][A-Za-z]+)?$")


def prepare_summary_display(summary: str) -> tuple[str, str]:
    """Return a controlled typography mode and escaped plain-text HTML."""
    text = summary.strip()
    list_like = bool(
        re.search(r"(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+", text)
        or text.count(",") >= 3
        or text.count(";") >= 2
    )
    mode = "body" if len(text) > 180 or "\n" in text or list_like else "headline"
    return mode, escape(text).replace("\n", "<br>")


def format_result_scope(analysis: AnalysisResult, spec: ChartSpec | None) -> str:
    """Return a concise scope label without reinterpreting analytical dimensions."""
    if spec:
        time_range = _time_range(analysis, spec)
        if time_range:
            return _bounded_suffix(time_range, analysis.truncated)
        if _is_trustworthy_label(spec.x_label):
            count = _display_count(analysis)
            return _bounded_suffix(f"{count} {_pluralize(spec.x_label, count)}", analysis.truncated)

    count = _display_count(analysis)
    noun = "row" if count == 1 else "rows"
    return _bounded_suffix(f"{count} {noun}", analysis.truncated)


def _time_range(analysis: AnalysisResult, spec: ChartSpec) -> str | None:
    if not isinstance(spec.x, str) or not _TIME_DIMENSION.search(f"{spec.x} {spec.x_label or ''}"):
        return None
    values = [row.get(spec.x) for row in analysis.rows if row.get(spec.x) is not None]
    if not values:
        return None
    parsed = pd.to_datetime(values, errors="coerce")
    if parsed.isna().any():
        return None
    start = parsed.min()
    end = parsed.max()
    if start == end:
        return start.strftime("%b %Y")
    return f"{start.strftime('%b %Y')}–{end.strftime('%b %Y')}"


def _is_trustworthy_label(label: str | None) -> bool:
    return bool(label and _DISPLAY_LABEL.fullmatch(label.strip()) and " by " not in label.lower())


def _pluralize(label: str, count: int) -> str:
    if count == 1:
        return label.lower()
    words = label.lower().split()
    noun = words[-1]
    if noun.endswith("y") and len(noun) > 1 and noun[-2] not in "aeiou":
        words[-1] = f"{noun[:-1]}ies"
    elif noun.endswith(("s", "x", "z", "ch", "sh")):
        words[-1] = f"{noun}es"
    else:
        words[-1] = f"{noun}s"
    return " ".join(words)


def _display_count(analysis: AnalysisResult) -> int:
    return analysis.row_count if analysis.row_count else len(analysis.rows)


def _bounded_suffix(scope: str, truncated: bool) -> str:
    return f"{scope} shown (bounded)" if truncated else scope
