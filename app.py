"""Streamlit entry point for the governed analytics command center."""

import pandas as pd
import streamlit as st
import yaml

from analytics_command_center.errors import AccessDenied, ConfigurationError, safe_live_error
from analytics_command_center.models import AnalysisRequest
from analytics_command_center.rendering import CompanyStyle, render_chart
from analytics_command_center.runtime import analytics_service, config_store, project_root
from analytics_command_center.visualization_capabilities import QUICK_CHOICES

ROOT = project_root()
STYLE_CONFIG = yaml.safe_load((ROOT / "config" / "company_style.yaml").read_text())
COLORS = STYLE_CONFIG["colors"]

st.set_page_config(page_title="Analytics Command Center", page_icon="◌", layout="wide")
st.markdown(f"""<style>
.stApp {{ background: {COLORS['canvas']}; color: {COLORS['ink']}; }}
[data-testid='stSidebar'] {{ background: {COLORS['canvas']}; border-right: 1px solid {COLORS['muted_plum']}44; }}
h1, h2, h3 {{ color: {COLORS['ink']}; }}
.eyebrow {{ color: {COLORS['muted_plum']}; font: 600 .72rem 'Courier New', monospace; letter-spacing: .11em; }}
.access-ok {{ color: {COLORS['mint']}; font-weight: 700; }}
.empty-state {{ border: 1px solid {COLORS['muted_plum']}55; border-radius: 10px; padding: 1rem; color: {COLORS['muted_plum']}; }}
</style>""", unsafe_allow_html=True)

LENS_OPTIONS = ("Auto", "Ranking", "Trend", "Compare", "Distribution", "Relationship", "Custom")


def _set_example(question: str) -> None:
    st.session_state["question_input"] = question


def _reset_result_for_context(user_id: str, database_id: str) -> None:
    context = (user_id, database_id)
    if st.session_state.get("result_context") not in {None, context}:
        st.session_state.pop("last_result", None)
    st.session_state["result_context"] = context


def _examples(database: dict) -> list[dict[str, str]]:
    return database.get("examples", [])


def _render_result() -> None:
    result = st.session_state.get("last_result")
    if not result:
        return
    answer_tab, data_tab, details_tab = st.tabs(["Answer", "Data", "Run details"])
    with answer_tab:
        st.markdown("<p class='eyebrow'>INSIGHT</p>", unsafe_allow_html=True)
        st.write(result.analysis.summary)
        if result.chart_spec:
            try:
                figure = render_chart(result.analysis, result.chart_spec, CompanyStyle(ROOT / "config" / "company_style.yaml"))
                if figure:
                    st.plotly_chart(figure, use_container_width=True)
                if result.chart_spec.notes:
                    st.caption(result.chart_spec.notes)
            except Exception:
                st.warning("Visualization could not be rendered; the answer and data remain available.")
        if result.visualization_warning:
            st.warning(result.visualization_warning)
    with data_tab:
        if result.analysis.rows:
            st.dataframe(pd.DataFrame(result.analysis.rows, columns=result.analysis.columns), use_container_width=True)
        else:
            st.info("No tabular rows were produced for this request.")
        if result.analysis.truncated:
            st.warning(f"Showing the first {result.analysis.row_limit} rows; additional matching rows were not returned.")
        for warning in result.analysis.warnings:
            st.caption(warning)
    with details_tab:
        telemetry = result.telemetry
        st.metric("Authorization", "ALLOWED" if telemetry.acl_decision and telemetry.acl_decision.allowed else "DENIED")
        st.write({
            "run_id": telemetry.run_id,
            "tables_used": telemetry.tables_used,
            "rows_returned": telemetry.rows_returned,
            "row_limit": telemetry.row_limit,
            "truncated": telemetry.truncated,
            "sql_repairs": telemetry.sql_repairs,
            "visualization": telemetry.chart_type,
        })
        with st.expander("Schema provenance"):
            for item in telemetry.schema_provenance:
                st.write(item)
        with st.expander("Generated SQL"):
            st.code("\n\n".join(telemetry.sql_queries) or "No query executed", language="sql")


def main() -> None:
    store = config_store()
    st.sidebar.markdown("<p class='eyebrow'>CONTEXT</p>", unsafe_allow_html=True)
    user_id = st.sidebar.selectbox("User", list(store.acl()["users"]), format_func=lambda u: store.user(u)["display_name"])
    grants = store.accessible_databases(user_id)
    st.title("ANALYTICS COMMAND CENTER")
    st.caption("Governed analysis across your data")
    if not grants:
        st.sidebar.markdown("### Database\nNo databases assigned")
        st.sidebar.markdown("### Access\nNo active permissions")
        st.sidebar.markdown("<div class='empty-state'>An administrator can grant access when a database is onboarded.</div>", unsafe_allow_html=True)
        st.info("No databases are currently assigned to this user.")
        return
    database_id = st.sidebar.selectbox("Database", grants, format_func=lambda db: store.database(db)["display_name"])
    database = store.database(database_id)
    _reset_result_for_context(user_id, database_id)
    st.sidebar.markdown("<p class='access-ok'>✓ Authorized</p>", unsafe_allow_html=True)

    examples = _examples(database)
    if examples:
        for column, example in zip(st.columns(len(examples)), examples):
            column.button(example["label"], key=f"example_{database_id}_{example['label']}", use_container_width=True, on_click=_set_example, args=(example["question"],))

    with st.form("analysis_request", clear_on_submit=False):
        question = st.text_input("Ask your data", key="question_input", placeholder="Which markets grew fastest?")
        left, right = st.columns(2)
        with left:
            lens_label = st.selectbox("Analysis lens", LENS_OPTIONS, help="Shapes the analytical approach; your question remains authoritative.")
            analysis_guidance = st.text_input("Custom analysis guidance", help="Describe the analytical approach, not a chart type.") if lens_label == "Custom" else ""
        with right:
            initial_visualization = st.selectbox("Visualization", QUICK_CHOICES, help="Use Auto for semantic selection; explicit choices override it.")
            visualization_guidance = st.text_input("Custom visualization guidance", help="For example: Show this as a box plot grouped by country.") if initial_visualization == "Custom…" else ""
        submitted = st.form_submit_button("Run analysis", type="primary")

    if submitted:
        if not question.strip():
            st.warning("Enter a question before running analysis.")
        else:
            visualization_hint = visualization_guidance if initial_visualization == "Custom…" else initial_visualization
            try:
                with st.spinner("Running governed analysis..."):
                    st.session_state["last_result"] = analytics_service().run(
                        AnalysisRequest(
                            user_id=user_id,
                            database_id=database_id,
                            question=question,
                            analysis_lens=lens_label.lower(),
                            analysis_hint=analysis_guidance or None,
                            visualization_hint=visualization_hint,
                        )
                    )
                    st.session_state["visualization_source"] = visualization_hint
                    st.session_state["post_run_visualization"] = (
                        initial_visualization if initial_visualization in QUICK_CHOICES[:-1] else "Auto"
                    )
            except ConfigurationError as error:
                st.error(str(error))
            except AccessDenied:
                st.error("Access denied before any analysis was started.")
            except Exception as error:
                st.error(safe_live_error(error))

    result = st.session_state.get("last_result")
    if result and result.analysis.outcome == "success":
        st.markdown("<p class='eyebrow'>VISUALIZATION</p>", unsafe_allow_html=True)
        choice = st.selectbox("Change chart without rerunning analysis", QUICK_CHOICES[:-1], key="post_run_visualization")
        if choice != st.session_state.get("visualization_source"):
            try:
                spec, warning = analytics_service().choose_visualization(result.analysis, choice)
                result.chart_spec = spec
                result.visualization_warning = warning
                result.telemetry.chart_type = spec.chart_type if spec else None
                result.telemetry.visualization_agent_status = "not_needed" if choice != "Auto" else "completed"
                st.session_state["visualization_source"] = choice
            except Exception:
                result.chart_spec = None
                result.visualization_warning = "Visualization could not be generated; the answer and data remain available."
    _render_result()


if __name__ == "__main__":
    main()
