# Governance Diagnosis and Evaluation Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct over-broad SQLite wildcard protection, retain secure policy telemetry, and generate a reproducible human-readable evaluation report from deterministic and explicitly live evidence.

**Architecture:** SQL safety will receive table-qualified restricted fields rather than a database-wide set of names, allowing the parser to decide whether a wildcard expands a restricted table. Reporting will orchestrate existing benchmark verifiers and pytest-derived deterministic results without duplicating analytical logic; live evaluation is explicit and restores the canonical demo state in a `finally` block.

**Tech Stack:** Python 3, sqlglot, Pydantic, pytest, Typer, SQLite, Markdown/JSON.

## Global Constraints

- Product functionality remains frozen: no new analysis capabilities, agents, UI, adapters, or orchestration.
- Explicit `staff.password` and `staff.*` access remains blocked before execution; unrelated `category.*` is allowed.
- Normal agent schema filtering remains unchanged and never reveals restricted values.
- `pytest` never calls OpenAI; live calls occur only through `analytics eval --live` or the existing `agent_eval` marker.
- Sakila live evaluation must restore Toyesh/Alfred/Donné and registry state through the existing demo reset service.
- Preserve unrelated local configuration edits until the requested canonical reset occurs.

---

### Task 1: Table-scoped restricted-column policy

**Files:**
- Modify: `src/analytics_command_center/governance.py`
- Modify: `src/analytics_command_center/sql_safety.py`
- Modify: `src/analytics_command_center/service.py`
- Test: `tests/test_governance_and_controls.py`

**Interfaces:**
- Consumes: `SchemaCatalog`, sqlglot `exp.Column`, `exp.Star`, and `SchemaGovernancePolicy`.
- Produces: `validate_read_only_sql(sql, restricted_fields)` with safe, table-qualified `UnsafeSQL` messages and `RunTelemetry.restricted_reference` populated from a deterministic rejection.

- [ ] **Step 1: Write failing tests**

```python
assert executor.execute("SELECT * FROM category").columns == ["category_id", "name"]
with pytest.raises(UnsafeSQL, match="staff\.password"):
    executor.execute("SELECT password FROM staff")
with pytest.raises(UnsafeSQL, match="staff\.\*"):
    executor.execute("SELECT * FROM staff")
```

- [ ] **Step 2: Run the focused test to verify database-global wildcard handling fails**

Run: `PYTHONPATH=src pytest -q tests/test_governance_and_controls.py -k wildcard`

Expected: `SELECT * FROM category` is rejected because the current implementation has a database-global wildcard rule.

- [ ] **Step 3: Implement qualified restriction lookup**

```python
restricted_fields = {"staff": {"password"}}
# Explicit column: reject only a referenced restricted table/column.
# Wildcard: reject only `staff.*` or an unqualified wildcard whose FROM scope includes staff.
```

- [ ] **Step 4: Populate safe policy telemetry from the `UnsafeSQL` reason**

```python
telemetry.restricted_reference = "staff.password"  # or "staff.*"
```

- [ ] **Step 5: Run focused governance tests**

Run: `PYTHONPATH=src pytest -q tests/test_governance_and_controls.py -k 'restricted or wildcard'`

Expected: explicit field and staff wildcard block pre-execution; category wildcard executes.

### Task 2: Benchmark reporting layer

**Files:**
- Create: `src/analytics_command_center/evaluation_report.py`
- Modify: `src/analytics_command_center/cli.py`
- Modify: `src/analytics_command_center/benchmark.py`
- Create: `reports/evaluation.json`
- Create: `reports/evaluation.md`
- Test: `tests/test_evaluation_report.py`

**Interfaces:**
- Consumes: existing `verify_*_run` functions, `AnalyticsRunResult.telemetry`, and `DemoStateService`.
- Produces: `write_evaluation_report(path, deterministic_cases, live_cases)` and `analytics eval --live`.

- [ ] **Step 1: Write failing report tests**

```python
payload = build_evaluation_payload(deterministic_cases=[passed_case], live_cases=[])
assert payload["deterministic_checks"] == {"passed": 1, "total": 1}
assert "Live GPT-5 evaluations" in render_evaluation_markdown(payload)
```

- [ ] **Step 2: Run report tests to verify the reporting API is absent**

Run: `PYTHONPATH=src pytest -q tests/test_evaluation_report.py`

Expected: import failure until the reporting module exists.

- [ ] **Step 3: Implement report rendering from case records**

```python
@dataclass(frozen=True)
class EvaluationCase:
    name: str
    database: str
    category: str
    execution: Literal["deterministic/local", "live GPT-5"]
    expected: str
    passed: bool
    result: str
```

- [ ] **Step 4: Add explicit live CLI orchestration**

```python
@evaluation_app.command("live")
def run_live_evaluation():
    # execute configured real cases; temporary Sakila onboarding in try/finally
    # always demo_state_service().reset() in finally
```

- [ ] **Step 5: Run report tests**

Run: `PYTHONPATH=src pytest -q tests/test_evaluation_report.py`

Expected: JSON uses actual case counts and Markdown has concise category/case tables.

### Task 3: Evidence generation, limitation documentation, and freeze verification

**Files:**
- Modify: `README.md`
- Create/Update: `reports/evaluation.json`
- Create/Update: `reports/evaluation.md`
- Test: `tests/test_agent_evals.py`

**Interfaces:**
- Consumes: the report writer and explicit `analytics eval live` command.
- Produces: committed reproducible report outputs plus documented multi-intent/churn limitation.

- [ ] **Step 1: Add the limitation statement**

```markdown
Complex multi-objective questions may require decomposition into multiple analytical runs. Predictive concepts such as churn also require an explicit target/definition before analysis.
```

- [ ] **Step 2: Run deterministic report generation and tests**

Run: `PYTHONPATH=src python3 -m analytics_command_center.cli eval local && PYTHONPATH=src pytest -q`

Expected: report differentiates deterministic/local checks from zero or recorded live GPT-5 cases; no API call occurs.

- [ ] **Step 3: Run explicit live benchmark**

Run: `PYTHONPATH=src python3 -m analytics_command_center.cli eval live`

Expected: report includes actual pass/fail evidence and safe telemetry; Sakila is temporary.

- [ ] **Step 4: Verify canonical reset and final integrity**

Run: `PYTHONPATH=src python3 -m analytics_command_center.cli demo check && python3 -m compileall -q src app.py && git diff --check && PYTHONPATH=src pytest -q`

Expected: canonical pre-demo state, compile success, clean diff, and deterministic test suite pass.

- [ ] **Step 5: Commit the scoped post-freeze evidence checkpoint**

```bash
git add src tests reports README.md docs/superpowers/plans
git commit -m "feat: report governed analytics evaluation"
```

## Self-review

- Scope is limited to existing safety semantics, telemetry, executable benchmark evidence, and limitation documentation.
- The plan neither adds analytical capabilities nor model routing, MCP, UI, adapters, or agent roles.
- Each production behavior has a focused deterministic test; all live invocations remain explicit.
