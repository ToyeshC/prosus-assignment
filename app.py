"""Streamlit entry point for the governed analytics command center."""

from __future__ import annotations

import re
from contextlib import nullcontext
from html import escape

import pandas as pd
import streamlit as st
import yaml

from analytics_command_center.errors import AccessDenied, ConfigurationError, safe_live_error
from analytics_command_center.models import AnalysisRequest
from analytics_command_center.presentation import format_result_scope
from analytics_command_center.rendering import CompanyStyle, render_chart
from analytics_command_center.runtime import analytics_service, config_store, project_root
from analytics_command_center.visualization_capabilities import QUICK_CHOICES
from analytics_command_center.workspace_state import (
    clear_analytical_state,
    initialize_question_state,
    record_submitted_question,
    select_example_question,
)

ROOT = project_root()
STYLE_CONFIG = yaml.safe_load((ROOT / "config" / "company_style.yaml").read_text())
COLORS = STYLE_CONFIG["colors"]

st.set_page_config(page_title="Analytics Command Center", page_icon="◌", layout="wide")
st.markdown(
    f"""<style>
    .stApp {{
      background-color: {COLORS['canvas']};
      background-image: radial-gradient(circle at 1px 1px, {COLORS['dot']} 1px, transparent 1.1px);
      background-size: 20px 20px;
      color: {COLORS['ink']};
    }}
    .block-container {{ max-width: 980px; padding-top: 2.4rem; padding-bottom: 3.5rem; }}
    h1, h2, h3, p, label {{ color: {COLORS['ink']}; font-family: {STYLE_CONFIG['fonts']['sans']}; }}
    [data-testid='stSidebar'] {{ display: none; }}
    [data-testid='stHeader'] {{ background: transparent; }}
    .workspace-brand {{ font-size: .9rem; font-weight: 700; letter-spacing: -.02em; margin: 0; }}
    .workspace-subtitle {{ display: none; }}
    [data-testid='stPopoverButton'] > button {{
      min-height: 34px;
      border: 1px solid {COLORS['border']};
      border-radius: {STYLE_CONFIG['layout']['border_radius']}px;
      background: rgba(255, 255, 255, .76);
      color: {COLORS['control_ink']};
      font-size: .78rem;
      font-weight: 500;
      transition: transform 180ms cubic-bezier(.16, 1, .3, 1), border-color 180ms cubic-bezier(.16, 1, .3, 1), background 180ms cubic-bezier(.16, 1, .3, 1);
    }}
    [data-testid='stPopoverButton'] > button:hover, [data-testid='stPopoverButton'] > button:focus-visible {{
      transform: translateY(-1px);
      border-color: {COLORS['accent_border']};
      background: {COLORS['surface']};
    }}
    .scope-context {{ color: {COLORS['muted']}; font-size: .88rem; margin: .2rem 0 1.15rem; }}
    .st-key-starting-surface {{ max-width: 815px; margin: 4.35rem auto 0; padding-top: 1.4rem; border-top: 1px solid {COLORS['border']}; }}
    .st-key-starting-surface p {{ margin: 0 0 1rem; }}
    .st-key-starting-surface .starting-title {{ font-size: 1.06rem; font-weight: 650; letter-spacing: -.025em; }}
    .st-key-starting-surface .starting-copy, .example-intro {{ color: {COLORS['muted']}; font-size: .82rem; }}
    .empty-workspace {{ max-width: 34rem; margin: 6rem auto; text-align: center; }}
    .empty-workspace h2 {{ font-size: 1.4rem; font-weight: 600; margin-bottom: .35rem; }}
    .empty-workspace p {{ color: {COLORS['muted']}; line-height: 1.55; }}
    .empty-workspace .empty-support {{ margin-top: .65rem; font-size: .9rem; }}
    .database-prompt {{ margin: 4.8rem auto 0; max-width: 680px; color: {COLORS['muted']}; }}
    .database-prompt strong {{ color: {COLORS['ink']}; font-size: 1.06rem; font-weight: 650; letter-spacing: -.025em; }}
    .st-key-source-selection {{ max-width: 680px; margin: 1.2rem auto 0; border-top: 1px solid {COLORS['border']}; }}
    .st-key-source-selection [data-testid='stButton'] button {{ border: 0; border-bottom: 1px solid {COLORS['border']}; border-radius: 0; background: transparent; color: {COLORS['ink']}; justify-content: space-between; padding: .88rem 0; text-align: left; font-size: .88rem; font-weight: 600; transition: transform 180ms cubic-bezier(.16, 1, .3, 1), color 180ms cubic-bezier(.16, 1, .3, 1), border-color 180ms cubic-bezier(.16, 1, .3, 1); }}
    .st-key-source-selection [data-testid='stButton'] button [data-testid='stMarkdownContainer'] {{ width: 100%; text-align: left; }}
    .st-key-source-selection [data-testid='stButton'] button::after {{ content: '→'; color: {COLORS['ink']}; font-size: 1.12rem; font-weight: 400; }}
    .st-key-source-selection [data-testid='stButton'] button:hover, .st-key-source-selection [data-testid='stButton'] button:focus-visible {{ background: transparent; color: {COLORS['accent']}; border-bottom-color: {COLORS['accent_muted']}; transform: translateX(4px); }}
    .st-key-source-selection [data-testid='stButton'] button:hover::after {{ color: {COLORS['accent']}; transform: translateX(3px); }}
    [data-testid='stTextInput'] input {{ height: 42px; border-color: {COLORS['control_border']}; border-radius: {STYLE_CONFIG['layout']['border_radius']}px; background: rgba(255, 255, 255, .84); color: {COLORS['ink']}; font-size: .82rem; }}
    [data-testid='stTextInput'] input:focus {{ border-color: {COLORS['accent']}; box-shadow: 0 0 0 1px {COLORS['accent']}; }}
    [data-testid='stButton'] button {{ min-height: 42px; border-radius: {STYLE_CONFIG['layout']['border_radius']}px; box-shadow: none; transition: transform 150ms cubic-bezier(.16, 1, .3, 1), border-color 150ms cubic-bezier(.16, 1, .3, 1), background 150ms cubic-bezier(.16, 1, .3, 1); }}
    [data-testid='stButton'] button:active {{ transform: translateY(1px) scale(.985); }}
    .st-key-query-composer [data-testid='stButton'] button {{ min-height: 42px; color: {COLORS['control_ink']}; font-size: .82rem; font-weight: 600; }}
    .st-key-query-composer [data-testid='stButton'] button[kind='primary'] {{ background: {COLORS['accent']}; border-color: {COLORS['accent']}; color: {COLORS['surface']}; }}
    [data-testid='stTabs'] [data-baseweb='tab-list'] {{ gap: 1.25rem; border-bottom: 1px solid {COLORS['border']}; }}
    [data-testid='stTabs'] [data-baseweb='tab'] {{ padding-left: 0; padding-right: 0; }}
    [data-testid='stPlotlyChart'], [data-testid='stPlotlyChart'] > div {{ background: transparent; border: 0; box-shadow: none; }}
    .st-key-example-row {{ margin-top: 1rem; }}
    .st-key-example-row [data-testid='stHorizontalBlock'] {{ justify-content: flex-start; gap: 15px; }}
    .st-key-example-row [data-testid='stColumn'] {{ flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }}
    .st-key-example-row [data-testid='stButton'] button {{ min-height: 0; border: 0; padding: 0; color: {COLORS['muted']}; background: transparent; font-size: .76rem; }}
    .st-key-example-row [data-testid='stButton'] button:hover {{ color: {COLORS['accent']}; background: transparent; }}
    .analysis-loading {{ min-height: 28rem; display: grid; place-items: center; text-align: center; }}
    .analysis-loading-mark {{ position: relative; display: block; width: 38px; height: 38px; margin: 0 auto 1.15rem; }}
    .analysis-loading-mark::before, .analysis-loading-mark::after {{ content: ''; position: absolute; border: 1.5px solid {COLORS['accent_faint']}; border-radius: 50%; }}
    .analysis-loading-mark::before {{ inset: 2px; }}
    .analysis-loading-mark::after {{ inset: 9px; border-color: {COLORS['accent']}; border-top-color: transparent; animation: analysis-orbit 1.5s linear infinite; }}
    .analysis-loading-mark {{ background: radial-gradient(circle at center, {COLORS['accent']} 0 5px, transparent 5.5px); animation: analysis-breathe 1.5s cubic-bezier(.16, 1, .3, 1) infinite alternate; }}
    .analysis-loading h2 {{ margin: 0; font-size: 1.2rem; letter-spacing: -.025em; font-weight: 650; }}
    .analysis-loading p {{ margin: .3rem 0 0; color: {COLORS['muted']}; font-size: .84rem; }}
    .st-key-result-workspace {{ max-width: 815px; margin: 3rem auto 0; }}
    .st-key-answer-summary [data-testid='stMarkdownContainer'] > :first-child {{ max-width: 650px; margin-top: 0; font-size: 1.55rem; line-height: 1.28; letter-spacing: -.03em; font-weight: 650; }}
    .st-key-answer-summary [data-testid='stMarkdownContainer'] p {{ max-width: 650px; line-height: 1.55; }}
    .st-key-answer-summary [data-testid='stMarkdownContainer'] ul {{ margin-top: .7rem; padding-left: 1.25rem; }}
    .st-key-result-workspace .scope-context {{ margin-top: .55rem; margin-bottom: 1.45rem; color: {COLORS['muted']}; font-size: .76rem; font-weight: 500; }}
    .st-key-result-workspace .scope-context strong {{ color: {COLORS['control_ink']}; font-weight: 650; }}
    @keyframes analysis-orbit {{ to {{ transform: rotate(360deg); }} }}
    @keyframes analysis-breathe {{ to {{ transform: scale(.76); opacity: .7; }} }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        animation-duration: .01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: .01ms !important;
      }}
    }}
    </style>""",
    unsafe_allow_html=True,
)

LENS_OPTIONS = ("Auto", "Ranking", "Trend", "Compare", "Distribution", "Relationship", "Custom")
def _set_example(question: str) -> None:
    select_example_question(st.session_state, question)


def _initialize_session(store) -> None:
    initialize_question_state(st.session_state)
    if "demo_user_id" not in st.session_state:
        st.session_state["demo_user_id"] = "toyesh"
        st.session_state["selected_database_id"] = "chinook"
    _reconcile_database_selection(store)


def _reconcile_database_selection(store) -> None:
    user_id = st.session_state["demo_user_id"]
    grants = store.accessible_databases(user_id)
    selected = st.session_state.get("selected_database_id")
    if selected in grants:
        return
    st.session_state["selected_database_id"] = grants[0] if len(grants) == 1 else None


def _switch_demo_user(store, user_id: str) -> None:
    if user_id == st.session_state.get("demo_user_id"):
        return
    clear_analytical_state(st.session_state)
    st.session_state["demo_user_id"] = user_id
    st.session_state["selected_database_id"] = None
    _reconcile_database_selection(store)


def _select_database(database_id: str) -> None:
    if database_id != st.session_state.get("selected_database_id"):
        clear_analytical_state(st.session_state)
        st.session_state["selected_database_id"] = database_id


def _initials(display_name: str) -> str:
    return "".join(part[0] for part in display_name.split() if part)[:2].upper()


def _example_label(label: str) -> str:
    return re.sub(r"^[^A-Za-z0-9]+\s*", "", label)


def _render_header(store, user_id: str, grants: list[str]) -> None:
    user = store.user(user_id)
    brand, _, user_slot, database_slot = st.columns([5.5, 1.1, 1.7, 1.7])
    with brand:
        st.markdown("<p class='workspace-brand'>Analytics Command Center</p>", unsafe_allow_html=True)
    with user_slot, st.popover(f"{user['display_name']}  ▾", width="stretch"):
        st.caption("Switch demo user")
        for candidate_id, candidate in store.acl()["users"].items():
            active = candidate_id == user_id
            label = f"{_initials(candidate['display_name'])}  {candidate['display_name']}"
            if st.button(label, key=f"demo_user_{candidate_id}", width="stretch", disabled=active):
                _switch_demo_user(store, candidate_id)
                st.rerun()
    selected = st.session_state.get("selected_database_id")
    database_label = store.database(selected)["display_name"] if selected else "Select database"
    with database_slot, st.popover(f"{database_label}  ▾", width="stretch"):
        if not grants:
            st.caption("No data sources assigned")
        else:
            for database_id in grants:
                database = store.database(database_id)
                active = database_id == selected
                label = database["display_name"]
                if st.button(label, key=f"database_{database_id}", width="stretch", disabled=active):
                    _select_database(database_id)
                    st.rerun()


def _render_options() -> None:
    with st.popover("Options"):
        st.selectbox(
            "Analysis lens",
            LENS_OPTIONS,
            key="analysis_lens",
            help="Shapes the analytical approach; your question remains authoritative.",
        )
        if st.session_state.get("analysis_lens") == "Custom":
            st.text_input("Custom analysis guidance", key="analysis_guidance", help="Describe the analytical approach, not a chart type.")
        st.selectbox(
            "Visualization",
            QUICK_CHOICES,
            key="initial_visualization",
            help="Auto selects presentation from the analytical result; an explicit choice overrides it.",
        )
        if st.session_state.get("initial_visualization") == "Custom…":
            st.text_input(
                "Custom visualization guidance",
                key="initial_visualization_guidance",
                help="For example: show this as a box plot grouped by country.",
            )


def _request_visualization_hint() -> str:
    choice = st.session_state.get("initial_visualization", "Auto")
    return st.session_state.get("initial_visualization_guidance", "") if choice == "Custom…" else choice


def _render_examples(database: dict) -> None:
    examples = database.get("examples", [])
    if not examples:
        return
    with st.container(key="example-row"):
        st.markdown("<p class='example-intro'>Or choose an example</p>", unsafe_allow_html=True)
        columns = st.columns(len(examples))
        for column, example in zip(columns, examples):
            column.button(
                _example_label(example["label"]),
                key=f"example_{database['display_name']}_{example['label']}",
                on_click=_set_example,
                args=(example["question"],),
            )


def _render_analysis_loading(database_name: str) -> None:
    st.markdown(
        f"<section class='analysis-loading'><div><span class='analysis-loading-mark'></span>"
        f"<h2>Analysing {escape(database_name)}</h2><p>Preparing your result…</p></div></section>",
        unsafe_allow_html=True,
    )


def _submit_request(user_id: str, database_id: str, database_name: str) -> None:
    question = st.session_state.get("question_draft", "")
    if not question.strip():
        st.warning("Enter a question before running analysis.")
        return
    question = record_submitted_question(st.session_state)
    visualization_hint = _request_visualization_hint()
    loading_placeholder = st.empty()
    try:
        with loading_placeholder.container():
            _render_analysis_loading(database_name)
        st.session_state["last_result"] = analytics_service().run(
            AnalysisRequest(
                user_id=user_id,
                database_id=database_id,
                question=question,
                analysis_lens=st.session_state.get("analysis_lens", "Auto").lower(),
                analysis_hint=st.session_state.get("analysis_guidance") or None,
                visualization_hint=visualization_hint,
            )
        )
        st.session_state["visualization_source"] = visualization_hint
    except ConfigurationError as error:
        st.error(str(error))
    except AccessDenied:
        st.error("Access denied before any analysis was started.")
    except Exception as error:  # noqa: BLE001 - safe_live_error prevents raw provider errors reaching the UI.
        st.error(safe_live_error(error))
    finally:
        loading_placeholder.empty()


def _render_query(user_id: str, database: dict) -> None:
    no_result_yet = not st.session_state.get("last_result")
    surface = st.container(key="starting-surface") if no_result_yet else nullcontext()
    with surface:
        if no_result_yet:
            st.markdown(
                "<p class='starting-title'>Start with a question</p><p class='starting-copy'>Ask for a comparison, trend, or ranking from the selected source.</p>",
                unsafe_allow_html=True,
            )
        with st.container(key="query-composer"):
            question_column, options_column, run_column = st.columns([8, 1.35, 1])
            with question_column:
                st.text_input(
                    "Ask your data",
                    key="question_draft",
                    placeholder=f"Ask a question about {database['display_name']}…",
                    label_visibility="collapsed",
                )
            with options_column:
                _render_options()
            with run_column:
                submitted = st.button("Run", type="primary", width="stretch", key="run_analysis")
        _render_examples(database)
    if submitted:
        _submit_request(user_id, database["id"], database["display_name"])


def _render_source_selection(store, grants: list[str]) -> None:
    st.markdown("<p class='database-prompt'><strong>Choose a data source</strong><br>Select a source to begin an analysis.</p>", unsafe_allow_html=True)
    with st.container(key="source-selection"):
        for database_id in grants:
            database = store.database(database_id)
            if st.button(database["display_name"], key=f"source_{database_id}", width="stretch"):
                _select_database(database_id)
                st.rerun()


def _revisualize_if_requested() -> None:
    result = st.session_state.get("last_result")
    if not result or result.analysis.outcome != "success":
        return
    source = _request_visualization_hint()
    if source == st.session_state.get("visualization_source"):
        return
    try:
        st.session_state["last_result"] = analytics_service().revisualize(result, source)
        st.session_state["visualization_source"] = source
    except Exception:  # noqa: BLE001 - visualization failure must preserve the successful analysis result.
        result.chart_spec = None
        result.visualization_warning = "Visualization could not be generated; the answer and data remain available."


def _render_result(database: dict) -> None:
    result = st.session_state.get("last_result")
    if not result:
        return
    with st.container(key="result-workspace"):
        answer_tab, data_tab, details_tab = st.tabs(["Answer", "Data", "Run details"])
        with answer_tab:
            with st.container(key="answer-summary"):
                st.write(result.analysis.summary)
            st.markdown(
                f"<p class='scope-context'><strong>{database['display_name']}</strong> · {format_result_scope(result.analysis, result.chart_spec)}</p>",
                unsafe_allow_html=True,
            )
            if result.chart_spec:
                try:
                    figure = render_chart(result.analysis, result.chart_spec, CompanyStyle(ROOT / "config" / "company_style.yaml"))
                    if figure:
                        st.plotly_chart(figure, width="stretch")
                        display_note = figure.layout.meta.get("display_note") if isinstance(figure.layout.meta, dict) else None
                        if display_note:
                            st.caption(display_note)
                    if result.chart_spec.notes:
                        st.caption(result.chart_spec.notes)
                except Exception:  # noqa: BLE001 - renderer failure must preserve the successful analysis result.
                    st.warning("Visualization could not be rendered; the answer and data remain available.")
            if result.visualization_warning:
                st.warning(result.visualization_warning)
        with data_tab:
            if result.analysis.rows:
                st.dataframe(pd.DataFrame(result.analysis.rows, columns=result.analysis.columns), width="stretch")
            else:
                st.info("No tabular rows were produced for this request.")
            if result.analysis.truncated:
                st.warning(f"Showing the first {result.analysis.row_limit} matching rows.")
            for warning in result.analysis.warnings:
                st.caption(warning)
        with details_tab:
            telemetry = result.telemetry
            st.json(
                {
                    "authorization": "allowed" if telemetry.acl_decision and telemetry.acl_decision.allowed else "denied",
                    "submitted_question": result.analysis.question,
                    "analysis_run_id": telemetry.run_id,
                    "outcome": telemetry.outcome,
                    "policy": telemetry.governance_policy,
                    "restricted_reference": telemetry.restricted_reference,
                    "analysis_agent_calls": telemetry.analysis_agent_calls,
                    "sql_execution_count": telemetry.sql_execution_count,
                    "visualization_runs": telemetry.visualization_runs,
                    "visualization_revision": telemetry.visualization_revision,
                    "analysis_reused": telemetry.analysis_reused,
                    "sql_executed": telemetry.sql_executed,
                    "tables_used": telemetry.tables_used,
                    "rows_returned": telemetry.rows_returned,
                    "row_limit": telemetry.row_limit,
                    "truncated": telemetry.truncated,
                    "sql_repairs": telemetry.sql_repairs,
                    "visualization": telemetry.chart_type,
                }
            )
            with st.expander("Schema provenance"):
                for item in telemetry.schema_provenance:
                    st.write(item)
            with st.expander("Generated SQL"):
                st.code("\n\n".join(telemetry.sql_queries) or "No query executed", language="sql")


def main() -> None:
    store = config_store()
    _initialize_session(store)
    user_id = st.session_state["demo_user_id"]
    grants = store.accessible_databases(user_id)
    _render_header(store, user_id, grants)

    if not grants:
        user = store.user(user_id)
        st.markdown(
            f"<section class='empty-workspace'><h2>{user['display_name']}</h2><p>No data sources assigned.</p><p class='empty-support'>Sources appear here when access is granted.</p></section>",
            unsafe_allow_html=True,
        )
        return

    database_id = st.session_state.get("selected_database_id")
    if not database_id:
        _render_source_selection(store, grants)
        return

    database = {**store.database(database_id), "id": database_id}
    _render_query(user_id, database)
    _revisualize_if_requested()
    _render_result(database)


if __name__ == "__main__":
    main()
