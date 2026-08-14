"""Narrow agent wrappers. Neither agent receives credentials or unrestricted DB access."""

import json
from typing import Literal, Protocol

from agents import Agent, Runner
from pydantic import BaseModel, Field

from .models import AnalysisResult, ChartSpec, QueryResult, SchemaCatalog
from .settings import Settings
from .visualization_capabilities import capability_names


class SQLProposal(BaseModel):
    outcome: Literal["success", "unsupported", "blocked"] = "success"
    sql: str | None = Field(default=None, description="A single read-only SQLite SELECT query when outcome is success")
    tables_used: list[str] = Field(default_factory=list)
    analysis_type: str | None = None
    message: str | None = None
    interpretation_warning: str | None = None


class AnalysisNarrative(BaseModel):
    summary: str
    warnings: list[str] = Field(default_factory=list)


class AnalysisAgentProtocol(Protocol):
    def propose(self, question: str, analysis_lens: str, analysis_hint: str | None, catalog: SchemaCatalog) -> SQLProposal: ...

    def repair(self, question: str, proposal: SQLProposal, error: str, catalog: SchemaCatalog) -> SQLProposal: ...

    def summarize(
        self, question: str, database_id: str, proposal: SQLProposal, result: QueryResult
    ) -> AnalysisResult: ...


class VisualizationAgentProtocol(Protocol):
    def choose(self, analysis: AnalysisResult, visualization_hint: str | None) -> ChartSpec: ...


class AnalysisAgent:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _run(self, instructions: str, input_text: str, output_type: type[BaseModel]) -> BaseModel:
        agent = Agent(
            name="Data Analysis Agent",
            model=self.settings.openai_default_model,
            instructions=instructions,
            output_type=output_type,
        )
        return Runner.run_sync(agent, input_text, max_turns=self.settings.max_agent_turns).final_output

    def propose(self, question: str, analysis_lens: str, analysis_hint: str | None, catalog: SchemaCatalog) -> SQLProposal:
        payload = {"question": question, "analysis_lens": analysis_lens, "analysis_guidance": analysis_hint, "schema": catalog.model_dump(mode="json")}
        return self._run(
            "You are the analysis-planning stage. Natural-language question is authoritative. The selected analysis lens is a material "
            "constraint unless it conflicts with the question; in a genuine conflict return outcome='unsupported' with a concise explanation. "
            "Lens meanings: ranking=ordered entities, trend=time change, compare=group comparison, distribution=measure across observations, "
            "relationship=association between variables, custom=the supplied non-visual analytical guidance, auto=infer approach. "
            "For outcome='success', return exactly one SQLite read-only SELECT query. Use only tables and columns in supplied schema. "
            "Never invent targets, unavailable variables, or definitions. For unsupported requests (including ML training without a defined target), "
            "return outcome='unsupported', no SQL, and a clear message. Do not use NULL placeholder queries. If the requested business entity "
            "does not exist and you use a close available entity, set interpretation_warning so the user sees the interpretation. "
            "Do not claim conclusions: execution and summarization happen downstream.",
            json.dumps(payload),
            SQLProposal,
        )  # type: ignore[return-value]

    def repair(self, question: str, proposal: SQLProposal, error: str, catalog: SchemaCatalog) -> SQLProposal:
        payload = {
            "question": question,
            "failed_sql": proposal.sql,
            "sanitized_error": error,
            "schema": catalog.model_dump(mode="json"),
        }
        return self._run(
            "Repair the failed SQLite query once. Return outcome='success' with a single read-only SELECT query using only supplied schema, "
            "or outcome='unsupported' with no SQL if the request cannot be completed legitimately. Do not emit more than one statement.",
            json.dumps(payload),
            SQLProposal,
        )  # type: ignore[return-value]

    def summarize(
        self, question: str, database_id: str, proposal: SQLProposal, result: QueryResult
    ) -> AnalysisResult:
        payload = {"question": question, "columns": result.columns, "rows": result.rows, "truncated": result.truncated, "row_limit": result.row_limit}
        narrative = self._run(
            "Summarize only the supplied query result. State data limitations plainly and never infer facts absent from it. "
            "If no rows match, say no matching records were found rather than presenting an aggregate zero as a complete fact. "
            "Do not mention chart suitability or implementation fields.",
            json.dumps(payload, default=str),
            AnalysisNarrative,
        )
        warnings = list(narrative.warnings)  # type: ignore[union-attr]
        if result.truncated:
            warnings.append("Result was capped by the configured row limit.")
        return AnalysisResult(
            database_id=database_id,
            question=question,
            analysis_type=proposal.analysis_type,
            sql_queries=[proposal.sql],
            columns=result.columns,
            rows=result.rows,
            summary=narrative.summary,  # type: ignore[union-attr]
            tables_used=proposal.tables_used,
            warnings=warnings,
            row_count=len(result.rows),
            outcome="no_data" if not result.rows else "success",
            truncated=result.truncated,
            row_limit=result.row_limit,
        )


class VisualizationAgent:
    def __init__(self, settings: Settings):
        self.settings = settings

    def choose(self, analysis: AnalysisResult, visualization_hint: str | None) -> ChartSpec:
        agent = Agent(
            name="Data Visualization Agent",
            model=self.settings.openai_default_model,
            instructions=(
                "Choose how to communicate the supplied completed analysis. Return a ChartSpec only. "
                f"Allowed chart types: {', '.join(capability_names())}, table, none. "
                "You have no database access and must not change the analysis or request new data."
            ),
            output_type=ChartSpec,
        )
        payload = {"analysis": analysis.model_dump(mode="json"), "visualization_hint": visualization_hint}
        return Runner.run_sync(agent, json.dumps(payload, default=str), max_turns=self.settings.max_agent_turns).final_output
