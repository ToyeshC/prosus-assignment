"""Streamlit entry point for the governed analytics command center."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st
import yaml

from analytics_command_center.errors import AccessDenied, ConfigurationError, safe_live_error
from analytics_command_center.models import AnalysisRequest
from analytics_command_center.presentation import format_result_scope
from analytics_command_center.rendering import CompanyStyle, render_chart
from analytics_command_center.runtime import analytics_service, config_store, project_root
from analytics_command_center.visualization_capabilities import QUICK_CHOICES

ROOT = project_root()
STYLE_CONFIG = yaml.safe_load((ROOT / "config" / "company_style.yaml").read_text())
COLORS = STYLE_CONFIG["colors"]

st.set_page_config(page_title="Analytics Command Center", page_icon="◌", layout="wide")
st.markdown(
    f"""<style>
    .stApp {{ background: {COLORS['canvas']}; color: {COLORS['ink']}; }}
    .block-container {{ max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem; }}
    h1, h2, h3, p, label {{ color: {COLORS['ink']}; font-family: {STYLE_CONFIG['fonts']['sans']}; }}
    [data-testid='stSidebar'] {{ display: none; }}
    [data-testid='stHeader'] {{ background: transparent; }}
    .workspace-brand {{ font-size: 1rem; font-weight: 700; letter-spacing: -.02em; margin: 0; }}
    .workspace-subtitle {{ color: {COLORS['muted']}; font-size: .9rem; margin: .15rem 0 0; }}
    .scope-context {{ color: {COLORS['muted']}; font-size: .88rem; margin: .2rem 0 1.15rem; }}
    .empty-workspace {{ max-width: 34rem; margin: 7rem auto; text-align: center; }}
    .empty-workspace h2 {{ font-size: 1.4rem; font-weight: 600; margin-bottom: .35rem; }}
    .empty-workspace p {{ color: {COLORS['muted']}; line-height: 1.55; }}
    .database-prompt {{ margin: 5rem auto; max-width: 34rem; color: {COLORS['muted']}; text-align: center; }}
    .database-prompt strong {{ color: {COLORS['ink']}; font-weight: 600; }}
    [data-testid='stForm'] {{ border: 0; padding: 0; }}
    [data-testid='stTextInput'] input {{ border-color: {COLORS['border']}; border-radius: 6px; background: {COLORS['surface']}; }}
    [data-testid='stTextInput'] input:focus {{ border-color: {COLORS['accent']}; box-shadow: 0 0 0 1px {COLORS['accent']}; }}
    [data-testid='stButton'] button {{ border-radius: 6px; box-shadow: none; }}
    [data-testid='stTabs'] [data-baseweb='tab-list'] {{ gap: 1.25rem; border-bottom: 1px solid {COLORS['border']}; }}
    [data-testid='stTabs'] [data-baseweb='tab'] {{ padding-left: 0; padding-right: 0; }}
    .st-key-example-row [data-testid='stButton'] button {{ border: 0; padding: 0; color: {COLORS['muted']}; background: transparent; font-size: .88rem; }}
    .st-key-example-row [data-testid='stButton'] button:hover {{ color: {COLORS['accent']}; background: transparent; }}
    </style>""",
    unsafe_allow_html=True,
)

LENS_OPTIONS = ("Auto", "Ranking", "Trend", "Compare", "Distribution", "Relationship", "Custom")
_ANALYTICAL_STATE = (
    "last_result",
    "result_context",
    "visualization_source",
    "post_run_visualization",
    "post_run_visualization_guidance",
)
_ANALYTICAL_WIDGET_DEFAULTS = {
    "question_input": "",
    "initial_visualization": "Auto",
    "initial_visualization_guidance": "",
    "analysis_lens": "Auto",
    "analysis_guidance": "",
}


def _set_example(question: str) -> None:
    st.session_state["question_input"] = question


def _clear_analytical_state() -> None:
    for key in _ANALYTICAL_STATE:
        st.session_state.pop(key, None)
    st.session_state.update(_ANALYTICAL_WIDGET_DEFAULTS)


def _initialize_session(store) -> None:
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
    _clear_analytical_state()
    st.session_state["demo_user_id"] = user_id
    st.session_state["selected_database_id"] = None
    _reconcile_database_selection(store)


def _select_database(database_id: str) -> None:
    if database_id != st.session_state.get("selected_database_id"):
        st.session_state.pop("last_result", None)
        st.session_state.pop("result_context", None)
        st.session_state["selected_database_id"] = database_id


def _initials(display_name: str) -> str:
    return "".join(part[0] for part in display_name.split() if part)[:2].upper()


def _example_label(label: str) -> str:
    return re.sub(r"^[^A-Za-z0-9]+\s*", "", label)


def _render_header(store, user_id: str, grants: list[str]) -> None:
    user = store.user(user_id)
    brand, _, user_slot, database_slot = st.columns([5, 2, 2, 2])
    with brand:
        st.markdown("<p class='workspace-brand'>Analytics Command Center</p>", unsafe_allow_html=True)
        st.markdown("<p class='workspace-subtitle'>Explore your data</p>", unsafe_allow_html=True)
    with user_slot, st.popover(f"{_initials(user['display_name'])}  {user['display_name']}", width="stretch"):
        st.caption("Switch demo user")
        for candidate_id, candidate in store.acl()["users"].items():
            active = candidate_id == user_id
            label = f"{_initials(candidate['display_name'])}  {candidate['display_name']}"
            if st.button(label, key=f"demo_user_{candidate_id}", width="stretch", disabled=active):
                _switch_demo_user(store, candidate_id)
                st.rerun()
    selected = st.session_state.get("selected_database_id")
    database_label = store.database(selected)["display_name"] if selected else "Select database"
    with database_slot, st.popover(database_label, width="stretch"):
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
        columns = st.columns(len(examples))
        for column, example in zip(columns, examples):
            column.button(
                _example_label(example["label"]),
                key=f"example_{database['display_name']}_{example['label']}",
                on_click=_set_example,
                args=(example["question"],),
            )


def _submit_request(user_id: str, database_id: str) -> None:
    question = st.session_state.get("question_input", "")
    if not question.strip():
        st.warning("Enter a question before running analysis.")
        return
    visualization_hint = _request_visualization_hint()
    try:
        with st.spinner("Running analysis..."):
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


def _render_query(user_id: str, database: dict) -> None:
    query_column, options_column = st.columns([8, 1])
    with options_column:
        _render_options()
    with query_column, st.form("analysis_request", clear_on_submit=False):
        question_column, run_column = st.columns([8, 1])
        with question_column:
            st.text_input(
                "Ask your data",
                key="question_input",
                placeholder=f"Ask a question about {database['display_name']}…",
                label_visibility="collapsed",
            )
        with run_column:
            submitted = st.form_submit_button("Run", type="primary", width="stretch")
    _render_examples(database)
    if submitted:
        _submit_request(user_id, database["id"])


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
    answer_tab, data_tab, details_tab = st.tabs(["Answer", "Data", "Run details"])
    with answer_tab:
        st.write(result.analysis.summary)
        st.markdown(
            f"<p class='scope-context'>{database['display_name']} · {format_result_scope(result.analysis, result.chart_spec)}</p>",
            unsafe_allow_html=True,
        )
        if result.chart_spec:
            try:
                figure = render_chart(result.analysis, result.chart_spec, CompanyStyle(ROOT / "config" / "company_style.yaml"))
                if figure:
                    st.plotly_chart(figure, width="stretch")
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
            f"<section class='empty-workspace'><h2>{user['display_name']}</h2><p>No data sources assigned.</p></section>",
            unsafe_allow_html=True,
        )
        return

    database_id = st.session_state.get("selected_database_id")
    if not database_id:
        st.markdown(
            "<p class='database-prompt'><strong>Choose a data source</strong><br>Use the database control in the header to begin an analysis.</p>",
            unsafe_allow_html=True,
        )
        return

    database = {**store.database(database_id), "id": database_id}
    _render_query(user_id, database)
    _revisualize_if_requested()
    _render_result(database)


if __name__ == "__main__":
    main()
