"""Presentation-only Streamlit workspace state helpers."""

from collections.abc import MutableMapping
from typing import Any

QUESTION_DRAFT_KEY = "question_draft"
SUBMITTED_QUESTION_KEY = "submitted_question"
_LEGACY_QUESTION_WIDGET_KEY = "question_input"
_RESULT_STATE_KEYS = (
    "last_result",
    "result_context",
    "visualization_source",
    "post_run_visualization",
    "post_run_visualization_guidance",
)
_WIDGET_DEFAULTS = {
    QUESTION_DRAFT_KEY: "",
    SUBMITTED_QUESTION_KEY: None,
    "initial_visualization": "Auto",
    "initial_visualization_guidance": "",
    "analysis_lens": "Auto",
    "analysis_guidance": "",
}


def initialize_question_state(state: MutableMapping[str, Any]) -> None:
    """Migrate the old ambiguous widget key without replacing a live draft."""
    state.pop(_LEGACY_QUESTION_WIDGET_KEY, None)
    state.setdefault(QUESTION_DRAFT_KEY, "")
    state.setdefault(SUBMITTED_QUESTION_KEY, None)


def select_example_question(state: MutableMapping[str, Any], question: str) -> None:
    state[QUESTION_DRAFT_KEY] = question


def record_submitted_question(state: MutableMapping[str, Any]) -> str:
    question = state.get(QUESTION_DRAFT_KEY, "")
    if not isinstance(question, str):
        raise TypeError("Question drafts must be text")
    state[SUBMITTED_QUESTION_KEY] = question
    return question


def clear_analytical_state(state: MutableMapping[str, Any]) -> None:
    for key in _RESULT_STATE_KEYS:
        state.pop(key, None)
    state.update(_WIDGET_DEFAULTS)
