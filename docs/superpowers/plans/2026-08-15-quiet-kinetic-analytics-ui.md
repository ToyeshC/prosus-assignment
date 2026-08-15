# Quiet Kinetic Analytics UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reproduce the approved quiet-kinetic concept in the Streamlit workspace without changing governed analytics behavior.

**Architecture:** Keep `app.py` as the Streamlit composition layer and all current service calls, state keys, and controls. Extend `company_style.yaml` as the single visual-token source; make renderer-only display transformations on copied pandas frames so `AnalysisResult` stays untouched.

**Tech Stack:** Streamlit 1.61, Plotly, pandas, YAML tokens, pytest, Ruff.

## Global Constraints

- Canonical reference: `/Users/toyesh/.codex/visualizations/2026/08/13/019ffc32-1d31-7320-9586-2f6a6b14d215/quiet-kinetic-analytics-concept.html`.
- Preserve agents, SQL, ACL/governance, result contracts, onboarding, evaluations, result rows, and revisualization semantics.
- Preserve `question_draft` / `submitted_question` behavior and keep technical evidence under Run details.
- Do not open a browser, use the visual companion, inspect screenshots, or claim visual acceptance.
- Do not touch or stage the pre-existing dirty files: `config/acl.yaml`, `config/registry.yaml`, `reports/evaluation.json`, `reports/evaluation.md`, `src/analytics_command_center/benchmark.py`.
- Keep real interactions as Streamlit controls. Restrict HTML/CSS to decoration and presentational layout; add no dependencies.

## File map

| File | Change |
| --- | --- |
| `docs/superpowers/specs/2026-08-15-quiet-analytical-instrument-design.md` | Existing approved design spec, amended with quiet-kinetic refinements. |
| `config/company_style.yaml` | Adds the concept's `faint` and `accent_soft` tokens to shared tokens. |
| `app.py` | Scoped styles, tactile controls, central loading placeholder, and stronger result presentation. |
| `src/analytics_command_center/rendering.py` | Display-copy, stable Plotly numeric formatting, and chart-only high-cardinality policy. |
| `tests/test_deterministic_core.py` | Shared-token integration assertion. |
| `tests/test_workspace_state.py` | Existing state regression coverage remains intact. |
| `tests/test_rendering_presentation.py` | New pure chart presentation tests. |

---

### Task 1: Establish shared quiet-kinetic tokens and canvas

**Files:**
- Modify: `config/company_style.yaml`
- Modify: `app.py:17-49`
- Modify: `tests/test_deterministic_core.py`

**Interfaces:**
- Consumes: `CompanyStyle.colors`, `.fonts`, `.layout`.
- Produces: `colors.faint == "#98A2B3"` and `colors.accent_soft == "#EDF2FC"` for app and Plotly styling.

- [ ] Snapshot scope with `git status --short`; confirm the five preserved files are dirty before touching UI files.
- [ ] Add `faint: "#98A2B3"` and `accent_soft: "#EDF2FC"` to `config/company_style.yaml`; retain existing canvas, transparent, semantic, fonts, and layout tokens.
- [ ] In `app.py`, update the existing `<style>` block to apply the concept's faint dot field to `.stApp`:

```css
.stApp {
  background-color: #F7F8FA;
  background-image: radial-gradient(circle at 1px 1px, rgba(22,24,29,.055) 1px, transparent 1.1px);
  background-size: 18px 18px;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
```

- [ ] Keep component rounding at 6–7px, add 150–180ms non-layout interaction transitions, and do not introduce workspace card/shadow treatment.
- [ ] Extend `test_renderer_uses_shared_company_tokens` with assertions for `faint` and `accent_soft`.
- [ ] Verify with:

```bash
.venv/bin/pytest -q tests/test_deterministic_core.py::test_renderer_uses_shared_company_tokens
.venv/bin/ruff check app.py src/analytics_command_center/rendering.py tests/test_deterministic_core.py
git diff --check
```

- [ ] Commit only `config/company_style.yaml`, `app.py`, and `tests/test_deterministic_core.py` as `style: establish quiet kinetic visual tokens`.

### Task 2: Recompose working Streamlit controls to the approved geometry

**Files:**
- Modify: `app.py:77-181`
- Test: `tests/test_workspace_state.py`

**Interfaces:**
- Consumes: `_switch_demo_user`, `_select_database`, `_set_example`, `_submit_request`, and current popover/button behavior.
- Produces: the same interactions rendered as avatar header controls, full-row data sources, and `[question] [Options] [Run]` composer.

- [ ] Run `.venv/bin/pytest -q tests/test_workspace_state.py`; expected: all four state ownership/scope tests pass before visual recomposition.
- [ ] In `_render_header`, preserve each existing popover, lookup, active disabled state, and callback. Update the label/decorative treatment to show `_initials(display_name)` as a circular avatar beside the name, with the database control unchanged functionally.
- [ ] In `_render_source_selection`, retain the existing `st.button`, `_select_database`, and rerun. Render `f"{database['display_name']}  →"` and style `.st-key-source-selection` as full-width transparent rows: bottom separator, accent/border response, and `translateX(4px)` arrow/row movement on hover/focus. Do not add cards or metadata.
- [ ] In `_render_query`, retain the one `st.form("analysis_request")` and `key="question_draft"`. Change columns to this visual order:

```python
question_column, options_column, run_column = st.columns([8, 1.35, 1])
```

Render `_render_options()` in `options_column` and `st.form_submit_button("Run", type="primary", width="stretch")` in `run_column`. Make all composer controls visually 42px high and centered through scoped CSS; examples remain current lightweight buttons with current `on_click` behavior.
- [ ] Verify with:

```bash
.venv/bin/pytest -q tests/test_workspace_state.py
.venv/bin/ruff check app.py tests/test_workspace_state.py
.venv/bin/python -m compileall -q app.py
git diff --check
```

- [ ] Commit only `app.py` as `style: compose tactile analytics workspace controls`.

### Task 3: Replace inline spinner with a real central loading state

**Files:**
- Modify: `app.py:132-224`
- Test: `tests/test_workspace_state.py`

**Interfaces:**
- Consumes: synchronous `analytics_service().run()`, existing error handling, `last_result`, and `visualization_source` session state.
- Produces: `_render_analysis_loading(database_name: str) -> None`, decorative loading markup shown only while a real analysis is executing.

- [ ] Add `import html` and a private renderer:

```python
def _render_analysis_loading(database_name: str) -> None:
    st.markdown(
        f"<section class='analysis-loading'><span class='analysis-loading-mark'></span>"
        f"<h2>Analysing {html.escape(database_name)}</h2><p>Preparing your result…</p></section>",
        unsafe_allow_html=True,
    )
```

- [ ] Add scoped CSS for the concept’s orbit/breathe mark. It must loop only while displayed, honor the Task 1 reduced-motion override, and contain no invented agent/tool stages.
- [ ] Change `_submit_request` to accept `database_name`. Before the current synchronous live call, create a `placeholder = st.empty()` and render the new state inside `with placeholder.container():`. Clear it in `finally: placeholder.empty()` while preserving every current `try` / `except`, request field, and session update.
- [ ] Call `_submit_request(user_id, database["id"], database["display_name"])` from `_render_query`; do not change how the question is recorded or how errors surface.
- [ ] Wrap result presentation in a keyed container and update CSS so the answer is approximately 25px/650 weight, context is quiet, and the integrated Plotly chart gets the full result width. Preserve tabs, Data, notes, warnings, and Run details content exactly.
- [ ] Verify with:

```bash
.venv/bin/pytest -q tests/test_workspace_state.py tests/test_deterministic_core.py::test_missing_key_has_clear_error_after_authorization tests/test_deterministic_core.py::test_denied_request_stops_before_live_agent_check
.venv/bin/ruff check app.py
.venv/bin/python -m compileall -q app.py
git diff --check
```

- [ ] Commit only `app.py` as `style: add central analytics loading state`.

### Task 4: Format chart values safely and limit only ranked categorical Bar displays

**Files:**
- Modify: `src/analytics_command_center/rendering.py`
- Modify: `app.py:187-208`
- Create: `tests/test_rendering_presentation.py`

**Interfaces:**
- Consumes: `AnalysisResult`, `ChartSpec`, and `CompanyStyle`.
- Produces: unchanged `render_chart(analysis, spec, style) -> go.Figure | None`, backed by a copied display frame and optional renderer display note held in figure layout metadata.

- [ ] Create failing tests using real renderer objects, with helper constructors for one-row analysis/spec/style. Cover all of:

```python
def test_renderer_formats_decimal_hover_values_without_mutating_analysis():
    analysis = _analysis(rows=[{"country": "USA", "revenue": 39.899999999999996}])
    figure = render_chart(analysis, _bar_spec(), _style())
    assert ".2f" in figure.data[0].hovertemplate
    assert analysis.rows[0]["revenue"] == 39.899999999999996

def test_ranked_categorical_bar_uses_top_twelve_display_rows_only():
    analysis = _analysis(rows=[{"genre": f"Genre {i}", "revenue": 30 - i} for i in range(25)])
    figure = render_chart(analysis, _bar_spec(x="genre", y="revenue", sort="descending"), _style())
    assert len(figure.data[0].x) == 12
    assert len(analysis.rows) == 25
```

Also assert a 25-point temporal Line remains whole; a Pie retains its existing top-category behavior; and a `y_label`/title containing `revenue`, `sales`, `amount`, `cost`, or a currency marker is the only basis for `$,.2f` formatting.
- [ ] Run `.venv/bin/pytest -q tests/test_rendering_presentation.py`; expected: fail because helpers/display policy do not yet exist.
- [ ] Add private helpers to `rendering.py`:

```python
def _display_frame(analysis: AnalysisResult, spec: ChartSpec) -> tuple[pd.DataFrame, str | None]:
    """Return a copied chart frame and an optional chart-only display caption."""

def _is_ranked_categorical_bar(spec: ChartSpec, frame: pd.DataFrame) -> bool:
    """Return true only for sorted Bar charts with categorical x and numeric y."""

def _is_currency_context(spec: ChartSpec) -> bool:
    """Return true only for explicit currency/revenue/sales/amount/cost labels."""

def _numeric_tick_format(spec: ChartSpec) -> str:
    """Return `$,.2f` for currency context and `,.2f` otherwise."""
```

`_display_frame` copies the DataFrame and returns `"Showing top 12 of 25 genres"` only when `chart_type == "bar"`, `spec.sort` is ascending/descending, x is non-numeric/categorical, y is numeric, and the frame exceeds 12 rows. It sorts by `spec.y` respecting `spec.sort`, takes 12, and does not alter analysis rows, SQL, spec semantics, temporal charts, distribution charts, relationship charts, Pie, or Donut.
- [ ] Build figures from the copied display frame, retaining all existing data mapping, local label-field handling, title, category order, custom data, fallback, and chart choice. Apply Plotly `tickformat` / trace `hovertemplate` with `,.2f` or `$,.2f` as appropriate. Do not round the original values.
- [ ] Store the display note in `figure.layout.meta["display_note"]`; in `_render_result`, read that value after `render_chart()` and render it as a small chart caption. Never write it into `AnalysisResult`, `ChartSpec`, or telemetry.
- [ ] Verify with:

```bash
.venv/bin/pytest -q tests/test_rendering_presentation.py tests/test_deterministic_core.py::test_renderer_uses_shared_company_tokens tests/test_presentation.py
.venv/bin/ruff check src/analytics_command_center/rendering.py app.py tests/test_rendering_presentation.py
.venv/bin/python -m compileall -q src/analytics_command_center app.py tests/test_rendering_presentation.py
git diff --check
```

- [ ] Commit only `src/analytics_command_center/rendering.py`, `app.py`, and `tests/test_rendering_presentation.py` as `style: polish chart display formatting`.

### Task 5: Freeze-preserving verification and handoff

**Files:**
- Modify: none unless verification exposes a defect in a UI-pass file.

**Interfaces:**
- Consumes: all UI-only commits above.
- Produces: a scoped verification record and user-owned visual acceptance handoff.

- [ ] Run the reliable deterministic suite:

```bash
.venv/bin/pytest -q tests/test_workspace_state.py tests/test_presentation.py tests/test_rendering_presentation.py tests/test_deterministic_core.py
```

Do not run agent evaluations or spend API credits. If the known broad-suite collection issue occurs, report it rather than changing unrelated infrastructure.
- [ ] Run source checks:

```bash
.venv/bin/ruff check app.py src/analytics_command_center/rendering.py src/analytics_command_center/presentation.py tests/test_workspace_state.py tests/test_presentation.py tests/test_rendering_presentation.py tests/test_deterministic_core.py
.venv/bin/python -m compileall -q app.py src/analytics_command_center tests/test_workspace_state.py tests/test_presentation.py tests/test_rendering_presentation.py tests/test_deterministic_core.py
git diff --check
```

- [ ] Prove stage scope with `git status --short` and `git diff --cached --name-only`. The five preserved dirty files must be untouched and unstaged.
- [ ] Commit only any final UI-pass fix if one is necessary; otherwise do not make an empty commit.
- [ ] Report changed files, commits, and actual non-visual results. Explicitly state that visual/browser validation was deliberately not performed and stop for user screenshots.

## Plan self-review

- Canvas, header, sources, composer, session styling, loading, result hierarchy, chart styling, number formatting, high-cardinality policy, Run-details isolation, and reduced motion each have an implementing task.
- The high-cardinality policy is explicitly limited to sorted categorical Bar charts; the existing Pie/Donut behavior remains intact.
- The display frame is copied and renderer metadata is presentation-only, preserving typed results and analysis truth.
- No task alters application services, model prompts, SQL, ACL decisions, evaluation code, onboarding, or the five preserved dirty files.
