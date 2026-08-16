"""Streamlit entry point for the governed analytics command center."""

from __future__ import annotations

import re
from html import escape

import pandas as pd
import streamlit as st
import yaml

from analytics_command_center.errors import AccessDenied, ConfigurationError, safe_live_error
from analytics_command_center.models import AnalysisRequest
from analytics_command_center.presentation import format_result_scope, prepare_summary_display
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
    .block-container {{ max-width: 1180px; padding: 3rem 0 5.5rem; }}
    h1, h2, h3, p, label {{ color: {COLORS['ink']}; font-family: {STYLE_CONFIG['fonts']['sans']}; }}
    [data-testid='stSidebar'] {{ display: none; }}
    [data-testid='stHeader'] {{ background: transparent; }}
    .st-key-workspace-header {{ padding-bottom: 17px; border-bottom: 1px solid {COLORS['border']}; }}
    .workspace-brand {{ margin: 0; font-size: 1rem; font-weight: 700; letter-spacing: -.025em; }}
    .st-key-workspace-header [data-testid='stHorizontalBlock'] {{ gap: 8px !important; align-items: flex-start !important; }}
    .st-key-workspace-header [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child {{ flex: 1 1 auto !important; width: auto !important; min-width: 0 !important; }}
    .st-key-workspace-header [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(2) {{ flex: 0 0 128px !important; width: 128px !important; min-width: 128px !important; }}
    .st-key-workspace-header [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(3) {{ flex: 0 0 166px !important; width: 166px !important; min-width: 166px !important; }}
    .st-key-user-session, .st-key-database-session {{ display: flex; justify-content: flex-end; }}
    .st-key-user-session, .st-key-database-session {{ align-items: flex-start; }}
    .st-key-database-session [data-testid='stPopoverButton'] {{ width: 166px !important; }}
    .st-key-user-session [data-testid='stPopoverButton'] > div,
    .st-key-database-session [data-testid='stPopoverButton'] > div {{
      display: flex !important; align-items: center !important; flex-wrap: nowrap !important;
      width: 100% !important; white-space: nowrap !important;
    }}
    .st-key-user-session [data-testid='stPopoverButton'] [data-testid='stMarkdownContainer'],
    .st-key-database-session [data-testid='stPopoverButton'] [data-testid='stMarkdownContainer'] {{ white-space: nowrap !important; }}
    [data-testid='stPopoverButton'] [data-testid='stMarkdownContainer'] p {{
      display: flex !important; align-items: center !important; flex-wrap: nowrap !important;
      margin: 0 !important; white-space: nowrap !important;
    }}
    .st-key-user-session [data-testid='stPopoverButton'],
    .st-key-database-session [data-testid='stPopoverButton'] {{
      width: 128px !important;
      min-height: 36px !important;
      height: 36px !important;
      padding: 0 11px !important;
      border: 1px solid {COLORS['border']};
      border-radius: {STYLE_CONFIG['layout']['border_radius']}px;
      background: rgba(255, 255, 255, .76);
      color: {COLORS['control_ink']};
      font-size: .82rem;
      font-weight: 550;
      line-height: 1;
      transition: transform 180ms cubic-bezier(.16, 1, .3, 1), border-color 180ms cubic-bezier(.16, 1, .3, 1), background 180ms cubic-bezier(.16, 1, .3, 1);
    }}
    .st-key-user-session [data-testid='stPopoverButton'] {{ width: 128px !important; }}
    .st-key-database-session [data-testid='stPopoverButton'] {{ width: 166px !important; }}
    [data-testid='stPopoverButton']:hover, [data-testid='stPopoverButton']:focus-visible {{
      transform: translateY(-1px);
      border-color: {COLORS['accent_border']};
      background: {COLORS['surface']};
    }}
    [data-testid='stPopoverButton'] [data-testid='stMarkdownContainer'] strong {{
      display: inline-grid; width: 19px; height: 19px; place-items: center; margin-right: 7px;
      border-radius: 50%; background: {COLORS['avatar_surface']}; color: {COLORS['avatar_ink']}; font-size: 9px; font-weight: 750; line-height: 1;
    }}
    [data-testid='stPopoverBody'] {{ width: 176px !important; min-width: 176px !important; max-width: 176px !important; box-sizing: border-box !important; padding: 5px !important; }}
    [role='dialog'] [data-testid='stButton'] {{ margin: 0 !important; }}
    [role='dialog'] [data-testid='stButton'] > button {{
      min-height: 36px !important; height: 36px !important; justify-content: flex-start !important;
      padding: 0 8px !important; text-align: left !important; border: 0 !important; border-radius: 4px;
      background: transparent !important; box-shadow: none !important;
      font-size: .82rem; font-weight: 550;
    }}
    [role='dialog'] [data-testid='stButton'] > button > div {{
      display: flex !important; width: 100% !important; justify-content: flex-start !important;
    }}
    [role='dialog'] [data-testid='stMarkdownContainer'] {{ width: 100% !important; text-align: left !important; }}
    [role='dialog'] [data-testid='stMarkdownContainer'] strong {{
      display: inline-grid; width: 19px; height: 19px; place-items: center; margin-right: 7px;
      border-radius: 50%; background: {COLORS['avatar_surface']}; color: {COLORS['avatar_ink']}; font-size: 9px; font-weight: 750; line-height: 1;
    }}
    [role='dialog'] [data-testid='stButton'] > button:disabled {{ background: {COLORS['accent_faint']} !important; border-color: transparent !important; color: {COLORS['accent']} !important; }}
    [role='dialog'] [data-testid='stButton'] > button:disabled::after {{ content: '✓'; margin-left: auto; color: {COLORS['accent']} !important; font-size: .75rem; }}
    .st-key-composer-workspace {{ width: 100%; margin: 4rem auto 0; }}
    .query-copy {{ margin: 0 0 1rem; }}
    .query-copy .starting-title {{ margin: 0 0 4px; font-size: 21px; line-height: 1.3; font-weight: 670; letter-spacing: -.028em; }}
    .query-copy .starting-copy {{ margin: 0; color: {COLORS['muted']}; font-size: 14px; line-height: 1.4; }}
    .empty-workspace {{ max-width: 34rem; margin: 6rem auto; text-align: center; }}
    .empty-workspace h2 {{ font-size: 1.4rem; font-weight: 600; margin-bottom: .35rem; }}
    .empty-workspace p {{ color: {COLORS['muted']}; line-height: 1.55; }}
    .empty-workspace .empty-support {{ margin-top: .65rem; font-size: .9rem; }}
    .st-key-source-workspace {{ max-width: 1010px; margin: 64px auto 0; }}
    .database-prompt {{ margin: 0; }}
    .database-prompt h1 {{ margin: 0 0 4px; color: {COLORS['ink']}; font-size: 21px; line-height: 1.3; font-weight: 670; letter-spacing: -.028em; }}
    .database-prompt p {{ margin: 0; color: {COLORS['muted']}; font-size: 14px; line-height: 1.4; }}
    .st-key-source-selection {{ margin-top: 32px; border-top: 1px solid {COLORS['border']}; }}
    .st-key-source-selection [data-testid='stButton'] {{ margin: 0 !important; }}
    .st-key-source-selection [data-testid='stButton'] > button {{ display: flex !important; height: 64px !important; min-height: 64px !important; border: 0; border-bottom: 1px solid {COLORS['border']}; border-radius: 0; background: transparent; color: {COLORS['ink']}; justify-content: flex-start !important; padding: 0 3px 0 0; text-align: left !important; font-size: 15px; font-weight: 670; line-height: 1.3; transition: transform 180ms cubic-bezier(.16, 1, .3, 1), color 180ms cubic-bezier(.16, 1, .3, 1), border-color 180ms cubic-bezier(.16, 1, .3, 1); }}
    .st-key-source-selection [data-testid='stButton'] > button {{ position: relative !important; }}
    .st-key-source-selection [data-testid='stButton'] > button > div {{ position: static !important; width: auto !important; }}
    .st-key-source-selection [data-testid='stButton'] button [data-testid='stMarkdownContainer'] {{ position: static !important; width: auto !important; text-align: left !important; white-space: nowrap; }}
    .st-key-source-selection [data-testid='stButton'] button [data-testid='stMarkdownContainer'] p {{ position: absolute !important; left: 0 !important; top: 50%; width: max-content !important; margin: 0 !important; transform: translateY(-50%); text-align: left !important; white-space: nowrap; font-weight: 670 !important; }}
    .st-key-source-selection [data-testid='stButton'] button,
    .st-key-source-selection [data-testid='stButton'] button p,
    .st-key-source-selection [data-testid='stButton'] button span {{ font-weight: 670 !important; }}
    .st-key-source-selection [data-testid='stButton'] button::after {{ content: '→'; margin-left: auto; color: {COLORS['ink']}; font-size: 20px; font-weight: 300; }}
    .st-key-source-selection [data-testid='stButton'] button:hover, .st-key-source-selection [data-testid='stButton'] button:focus-visible {{ background: transparent; color: {COLORS['accent']}; border-bottom-color: {COLORS['accent_muted']}; transform: translateX(4px); }}
    .st-key-source-selection [data-testid='stButton'] button:hover::after {{ color: {COLORS['accent']}; transform: translateX(3px); }}
    .st-key-source-workspace .database-prompt h1 a,
    .st-key-source-workspace [data-testid='stHeadingWithActionElements'] a {{ display: none !important; }}
    .st-key-query-composer [data-testid='stHorizontalBlock'],
    .st-key-query-composer-running [data-testid='stHorizontalBlock'] {{ display: flex !important; width: 100% !important; gap: 8px !important; align-items: center !important; }}
    .st-key-query-composer [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child,
    .st-key-query-composer-running [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child {{ flex: 1 1 auto !important; width: auto !important; min-width: 0 !important; }}
    .st-key-query-composer [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(2),
    .st-key-query-composer-running [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(2) {{ flex: 0 0 76px !important; width: 76px !important; min-width: 76px !important; }}
    .st-key-query-composer [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(3) {{ flex: 0 0 74px !important; width: 74px !important; min-width: 74px !important; }}
    .st-key-query-composer-running [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(3) {{ flex: 0 0 98px !important; width: 98px !important; min-width: 98px !important; }}
    [data-testid='stTextInput'] input {{ height: 42px; border-color: {COLORS['control_border']}; border-radius: {STYLE_CONFIG['layout']['border_radius']}px; background: rgba(255, 255, 255, .84); color: {COLORS['ink']}; font-size: 14px; line-height: 1.4; }}
    [data-testid='stTextInput'] input:focus {{ border-color: {COLORS['accent']}; box-shadow: 0 0 0 1px {COLORS['accent']}; }}
    [data-testid='stButton'] button {{ min-height: 42px; height: 42px; border-radius: {STYLE_CONFIG['layout']['border_radius']}px; box-shadow: none; transition: transform 150ms cubic-bezier(.16, 1, .3, 1), border-color 150ms cubic-bezier(.16, 1, .3, 1), background 150ms cubic-bezier(.16, 1, .3, 1); }}
    [data-testid='stButton'] button:active {{ transform: translateY(1px) scale(.985); }}
    .st-key-query-composer [data-testid='stButton'] button,
    .st-key-query-composer-running [data-testid='stButton'] button {{ min-height: 42px; color: {COLORS['control_ink']}; font-size: .82rem; font-weight: 600; line-height: 1.2; padding: 0 8px; }}
    .st-key-query-composer [data-testid='stButton'] button[kind='primary'],
    .st-key-query-composer-running [data-testid='stButton'] button[kind='primary'],
    .st-key-query-composer [data-testid='stBaseButton-primary'],
    .st-key-query-composer-running [data-testid='stBaseButton-primary'] {{ background: {COLORS['accent']}; border-color: {COLORS['accent']}; color: {COLORS['surface']} !important; white-space: nowrap !important; }}
    .st-key-query-composer [data-testid='stButton'] button[kind='primary'] *,
    .st-key-query-composer-running [data-testid='stButton'] button[kind='primary'] *,
    .st-key-query-composer [data-testid='stBaseButton-primary'] *,
    .st-key-query-composer-running [data-testid='stBaseButton-primary'] * {{ color: {COLORS['surface']} !important; }}
    .st-key-query-composer-running [data-testid='stButton'] button {{ min-width: 94px !important; white-space: nowrap !important; }}
    .st-key-query-composer [data-testid='stButton'] > button > div,
    .st-key-query-composer-running [data-testid='stButton'] > button > div {{ display: flex !important; align-items: center !important; justify-content: center !important; line-height: 1 !important; }}
    .st-key-query-composer [data-testid='stPopoverButton'],
    .st-key-query-composer-running [data-testid='stPopoverButton'] {{ width: 76px !important; height: 42px !important; min-height: 42px !important; padding: 0 8px !important; line-height: 1 !important; }}
    .st-key-query-composer [data-testid='stPopoverButton'] > div,
    .st-key-query-composer-running [data-testid='stPopoverButton'] > div {{ display: flex !important; align-items: center !important; justify-content: center !important; width: 100% !important; line-height: 1 !important; }}
    .st-key-query-composer [data-testid='stPopoverButton'] [data-testid='stMarkdownContainer'] p,
    .st-key-query-composer-running [data-testid='stPopoverButton'] [data-testid='stMarkdownContainer'] p {{ margin: 0 !important; line-height: 1 !important; }}
    .st-key-query-composer [data-testid='stPopoverButton'] [data-testid='stIconMaterial'],
    .st-key-query-composer-running [data-testid='stPopoverButton'] [data-testid='stIconMaterial'] {{ display: none !important; }}
    [data-testid='stTabs'] [data-baseweb='tab-list'] {{ gap: 1.25rem; border-bottom: 1px solid {COLORS['border']}; }}
    [data-testid='stTabs'] [data-baseweb='tab'] {{ padding-left: 0; padding-right: 0; }}
    [data-testid='stPlotlyChart'], [data-testid='stPlotlyChart'] > div {{ background: transparent; border: 0; box-shadow: none; }}
    .st-key-result-workspace [data-testid='stCaptionContainer'] {{ margin-top: .45rem; margin-bottom: 0; color: {COLORS['muted']}; font-size: .75rem; line-height: 1.4; }}
    .st-key-result-workspace [data-testid='stCaptionContainer'] p {{ margin: 0; color: {COLORS['muted']}; }}
    .st-key-example-row {{ margin-top: 1rem; }}
    .st-key-example-row [data-testid='stHorizontalBlock'] {{ display: flex !important; justify-content: flex-start; align-items: baseline !important; gap: 15px !important; }}
    .st-key-example-row [data-testid='stColumn'] {{ flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }}
    .st-key-example-row [data-testid='stMarkdownContainer'] p {{ margin: 0 !important; color: {COLORS['muted']}; font-size: 12px; line-height: 1.4; white-space: nowrap; transform: translateY(-1px); }}
    .st-key-example-row [data-testid='stButton'] {{ margin: 0 !important; }}
    .st-key-example-row [data-testid='stButton'] button {{ min-height: 0; height: auto; border: 0; padding: 0; color: {COLORS['muted']}; background: transparent; font-size: 12px; line-height: 1.4; font-weight: 550; white-space: nowrap; }}
    .st-key-example-row [data-testid='stButton'] button:hover {{ color: {COLORS['accent']}; background: transparent; }}
    .st-key-analytical-stage {{ min-height: 330px; margin-top: 3rem; padding-top: 2rem; border-top: 1px solid {COLORS['border']}; }}
    .analysis-loading {{ min-height: 350px; display: grid; place-items: center; text-align: center; }}
    .analysis-loading-mark {{ position: relative; display: block; width: 40px; height: 40px; margin: 0 auto 20px; }}
    .analysis-loading-mark::before, .analysis-loading-mark::after {{ content: ''; position: absolute; border: 1.5px solid {COLORS['accent_faint']}; border-radius: 50%; }}
    .analysis-loading-mark::before {{ inset: 2px; }}
    .analysis-loading-mark::after {{ inset: 9px; border-color: {COLORS['accent']}; border-top-color: transparent; animation: analysis-orbit 1.5s linear infinite; }}
    .analysis-loading-mark i {{ position: absolute; inset: 16px; display: block; border-radius: 50%; background: {COLORS['accent']}; animation: analysis-breathe 1.5s cubic-bezier(.16, 1, .3, 1) infinite alternate; }}
    .analysis-loading h2 {{ margin: 0; font-size: 20px; letter-spacing: -.028em; font-weight: 670; }}
    .analysis-loading p {{ margin: 5px 0 0; color: {COLORS['muted']}; font-size: 14px; }}
    .st-key-result-workspace {{ margin: 0; }}
    .st-key-answer-summary .analysis-summary {{ max-width: 720px; margin: 0; }}
    .st-key-answer-summary .analysis-summary p {{ margin: 0; max-width: 720px; color: {COLORS['ink']}; }}
    .st-key-answer-summary .analysis-summary.headline p {{ font-size: 1.75rem; line-height: 1.2; letter-spacing: -.035em; font-weight: 680; text-wrap: balance; }}
    .st-key-answer-summary .analysis-summary.body p {{ font-size: 1.08rem; line-height: 1.5; letter-spacing: -.005em; font-weight: 500; text-wrap: pretty; }}
    .st-key-answer-summary [data-testid='stMarkdownContainer'] ul {{ margin-top: .7rem; padding-left: 1.25rem; }}
    .st-key-result-workspace .scope-context {{ margin-top: .7rem; margin-bottom: 1.8rem; color: {COLORS['muted']}; font-size: .82rem; font-weight: 500; }}
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
        st.session_state["selected_database_id"] = None
        st.session_state["show_source_selection"] = True
    if st.session_state.pop("show_source_selection", False):
        return
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
    # Identity changes intentionally land on source selection so the new
    # session's scope is explicit, even when only one database is granted.
    st.session_state["selected_database_id"] = None
    st.session_state["show_source_selection"] = True


def _select_database(database_id: str) -> None:
    if database_id != st.session_state.get("selected_database_id"):
        clear_analytical_state(st.session_state)
        st.session_state["selected_database_id"] = database_id


def _initials(display_name: str) -> str:
    parts = [part for part in display_name.split() if part]
    if len(parts) == 1:
        return parts[0][:2].upper()
    return "".join(part[0] for part in parts)[:2].upper()


def _example_label(label: str) -> str:
    display_label = re.sub(r"^[^A-Za-z0-9]+\s*", "", label)
    return {
        "Top revenue": "Top revenue countries",
        "Trend": "Revenue over time",
        "Genres": "Revenue by genre",
    }.get(display_label, display_label)


def _render_header(store, user_id: str, grants: list[str]) -> None:
    user = store.user(user_id)
    with st.container(key="workspace-header"):
        brand, user_slot, database_slot = st.columns([7.2, 1.45, 1.8], gap="small")
        with brand:
            st.markdown("<p class='workspace-brand'>Analytics Command Center</p>", unsafe_allow_html=True)
        with user_slot, st.container(key="user-session"):
            initials = _initials(user["display_name"])
            with st.popover(f"**{initials}** {user['display_name']}", width="content"):
                st.caption("Switch demo user")
                for candidate_id, candidate in store.acl()["users"].items():
                    active = candidate_id == user_id
                    label = f"**{_initials(candidate['display_name'])}**  {candidate['display_name']}"
                    if st.button(label, key=f"demo_user_{candidate_id}", width="stretch", disabled=active):
                        _switch_demo_user(store, candidate_id)
                        st.rerun()
        selected = st.session_state.get("selected_database_id")
        database_label = store.database(selected)["display_name"] if selected else "Select database"
        with database_slot, st.container(key="database-session"), st.popover(database_label, width="content"):
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
        columns = st.columns(len(examples) + 1, gap="small")
        with columns[0]:
            st.markdown("<p class='example-intro'>Or choose an example</p>", unsafe_allow_html=True)
        for column, example in zip(columns[1:], examples):
            column.button(
                _example_label(example["label"]),
                key=f"example_{database['display_name']}_{example['label']}",
                on_click=_set_example,
                args=(example["question"],),
            )


def _render_analysis_loading(database_name: str) -> None:
    st.markdown(
        f"<section class='analysis-loading'><div><span class='analysis-loading-mark'><i></i></span>"
        f"<h2>Analysing {escape(database_name)}</h2><p>Preparing your result…</p></div></section>",
        unsafe_allow_html=True,
    )


def _begin_analysis() -> None:
    if not st.session_state.get("question_draft", "").strip():
        st.session_state["analysis_error"] = "Enter a question before running analysis."
        return
    st.session_state["analysis_running"] = True


def _submit_request(user_id: str, database_id: str, database_name: str, stage_placeholder) -> None:
    question = st.session_state.get("question_draft", "")
    if not question.strip():
        st.session_state["analysis_error"] = "Enter a question before running analysis."
        return
    question = record_submitted_question(st.session_state)
    visualization_hint = _request_visualization_hint()
    try:
        with stage_placeholder.container():
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
        st.session_state["analysis_error"] = str(error)
    except AccessDenied:
        st.session_state["analysis_error"] = "Access denied before any analysis was started."
    except Exception as error:  # noqa: BLE001 - safe_live_error prevents raw provider errors reaching the UI.
        st.session_state["analysis_error"] = safe_live_error(error)
    finally:
        st.session_state["analysis_running"] = False


def _render_query(user_id: str, database: dict) -> None:
    running = bool(st.session_state.get("analysis_running"))
    composer_key = "query-composer-running" if running else "query-composer"
    with st.container(key="composer-workspace"):
        st.markdown(
            "<div class='query-copy'><p class='starting-title'>Start with a question</p><p class='starting-copy'>Ask for a comparison, trend, or ranking from the selected source.</p></div>",
            unsafe_allow_html=True,
        )
        with st.container(key=composer_key):
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
                if running:
                    st.button("Running...", type="primary", width="stretch", key="run_analysis_busy", disabled=True)
                else:
                    st.button("Run", type="primary", width="stretch", key="run_analysis", on_click=_begin_analysis)
        _render_examples(database)
        with st.container(key="analytical-stage"):
            stage_placeholder = st.empty()

    if running:
        _submit_request(user_id, database["id"], database["display_name"], stage_placeholder)
        st.rerun()

    _revisualize_if_requested()
    with stage_placeholder.container():
        analysis_error = st.session_state.pop("analysis_error", None)
        if analysis_error:
            st.error(analysis_error)
        _render_result(database)


def _render_source_selection(store, grants: list[str]) -> None:
    with st.container(key="source-workspace"):
        st.markdown(
            "<section class='database-prompt'><h1>Choose a data source</h1>"
            "<p>Select a source to begin an analysis.</p></section>",
            unsafe_allow_html=True,
        )
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
                summary_mode, summary_html = prepare_summary_display(result.analysis.summary)
                st.markdown(
                    f"<div class='analysis-summary {summary_mode}'><p>{summary_html}</p></div>",
                    unsafe_allow_html=True,
                )
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


if __name__ == "__main__":
    main()
