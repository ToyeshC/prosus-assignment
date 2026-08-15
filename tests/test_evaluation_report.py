from analytics_command_center.evaluation_report import EvaluationCase, build_evaluation_payload, render_evaluation_markdown


def test_evaluation_payload_keeps_local_and_live_evidence_separate():
    local = EvaluationCase(
        name="Restricted wildcard policy",
        database="Sakila fixture",
        category="Governance & security",
        execution="deterministic/local",
        expected="Category wildcard allowed; staff wildcard blocked",
        passed=True,
        result="passed",
    )
    live = EvaluationCase(
        name="Chinook revenue ranking",
        database="Chinook",
        category="Analysis correctness",
        execution="live GPT-5",
        expected="Reference rows and bar semantics",
        passed=False,
        result="Reference comparison failed",
    )

    payload = build_evaluation_payload("gpt-5", [local], [live])

    assert payload["deterministic_checks"] == {"passed": 1, "total": 1}
    assert payload["live_gpt5_evaluations"] == {"passed": 0, "total": 1}
    assert payload["categories"]["Governance & security"] == {"passed": 1, "total": 1}
    assert "Live GPT-5 evaluations" in render_evaluation_markdown(payload)
    assert "Reference comparison failed" in render_evaluation_markdown(payload)
