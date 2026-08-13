"""Streamlit entry point for the governed analytics command center."""

import pandas as pd
import streamlit as st
import yaml

from analytics_command_center.errors import AccessDenied, ConfigurationError
from analytics_command_center.models import AnalysisRequest
from analytics_command_center.rendering import CompanyStyle, render_chart
from analytics_command_center.runtime import analytics_service, config_store, project_root

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
    analysis_mode = st.sidebar.selectbox("Analysis", ["Auto", "Trend", "Compare", "Distribution", "Relationship", "Ranking", "Custom"])
    custom_hint = st.sidebar.text_input("Custom analysis guidance") if analysis_mode == "Custom" else ""
    visualization_hint = st.sidebar.selectbox("Visualization", ["Auto", "Prefer chart", "Prefer table"])
    st.sidebar.markdown("<p class='access-ok'>✓ Authorized</p>", unsafe_allow_html=True)
    question = st.text_input("Ask your data", placeholder="Which markets grew fastest?")
    examples = {"🌍 Top revenue": "Which five countries generate the most revenue?", "📈 Trend": "How has revenue changed over time?", "🎵 Genres": "Which music genres generate the most revenue?"}
    for column, (label, example) in zip(st.columns(3), examples.items()):
        if column.button(label, use_container_width=True):
            question = example
    if st.button("Run analysis", type="primary"):
        if not question:
            st.warning("Enter a question before running analysis.")
            return
        hint = None if analysis_mode == "Auto" else custom_hint or f"Focus on {analysis_mode.lower()}."
        try:
            with st.spinner("Running governed analysis..."):
                st.session_state["last_result"] = analytics_service().run(AnalysisRequest(user_id=user_id, database_id=database_id, question=question, analysis_hint=hint, visualization_hint=None if visualization_hint == "Auto" else visualization_hint))
        except ConfigurationError as error:
            st.error(str(error))
            return
        except AccessDenied:
            st.error("Access denied before any analysis was started.")
            return
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
            except Exception:
                st.warning("Visualization could not be rendered; the answer and data remain available.")
        if result.visualization_warning:
            st.warning(result.visualization_warning)
    with data_tab:
        st.dataframe(pd.DataFrame(result.analysis.rows, columns=result.analysis.columns), use_container_width=True)
        for warning in result.analysis.warnings:
            st.caption(warning)
    with details_tab:
        telemetry = result.telemetry
        st.metric("Authorization", "ALLOWED" if telemetry.acl_decision and telemetry.acl_decision.allowed else "DENIED")
        st.write({"run_id": telemetry.run_id, "tables_used": telemetry.tables_used, "rows_returned": telemetry.rows_returned, "sql_repairs": telemetry.sql_repairs, "visualization": telemetry.chart_type})
        with st.expander("Generated SQL"):
            st.code("\n\n".join(telemetry.sql_queries) or "No query executed", language="sql")


if __name__ == "__main__":
    main()
