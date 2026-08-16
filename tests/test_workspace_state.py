from analytics_command_center.workspace_state import (
    clear_analytical_state,
    initialize_question_state,
    record_submitted_question,
    select_example_question,
)


def test_hot_reload_preserves_the_canonical_draft_over_a_legacy_widget_value():
    state = {
        "question_draft": "Who is the best employee?",
        "question_input": "How has revenue changed over time?",
    }

    initialize_question_state(state)

    assert state["question_draft"] == "Who is the best employee?"
    assert "question_input" not in state


def test_example_selection_updates_the_same_draft_that_submission_records():
    state: dict[str, object] = {}

    select_example_question(state, "Show revenue by country")
    submitted = record_submitted_question(state)

    assert state["question_draft"] == "Show revenue by country"
    assert submitted == "Show revenue by country"
    assert state["submitted_question"] == "Show revenue by country"


def test_editing_a_draft_does_not_change_the_question_attached_to_the_prior_result():
    state: dict[str, object] = {"question_draft": "Question A"}
    record_submitted_question(state)

    state["question_draft"] = "Question B"

    assert state["question_draft"] == "Question B"
    assert state["submitted_question"] == "Question A"


def test_scope_switch_clears_question_draft_submitted_question_and_result():
    state: dict[str, object] = {
        "question_draft": "Question A",
        "submitted_question": "Question A",
        "last_result": object(),
        "result_context": object(),
        "analysis_error": "A temporary error",
        "analysis_running": True,
    }

    clear_analytical_state(state)

    assert state["question_draft"] == ""
    assert state["submitted_question"] is None
    assert "last_result" not in state
    assert "result_context" not in state
    assert "analysis_error" not in state
    assert "analysis_running" not in state
