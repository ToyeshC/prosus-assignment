"""The deterministic trust boundary coordinating agents and safe database work."""

from datetime import datetime
from pathlib import Path
import re

from .agents import AnalysisAgent, AnalysisAgentProtocol, VisualizationAgent, VisualizationAgentProtocol
from .database import SQLiteAdapter
from .errors import AccessDenied, ConfigurationError, QueryExecutionError, UnsafeSQL
from .governance import SchemaGovernancePolicy
from .models import AnalysisRequest, AnalysisResult, AnalyticsRunResult, ChartSpec, RunTelemetry
from .registry import ConfigStore
from .settings import Settings
from .sql_safety import SafeQueryExecutor
from .visualization_capabilities import explicit_capability, unsupported_visualization_requested


def request_capability_outcome(request: AnalysisRequest) -> AnalysisResult | None:
    """Refuse requests that should never be silently reinterpreted as read-only analytics."""
    question = request.question.lower()
    if re.search(r"\b(delete|drop|truncate|insert|update|alter|create)\b", question):
        return AnalysisResult(
            database_id=request.database_id,
            question=request.question,
            outcome="blocked",
            summary="This analytics environment is read-only and cannot mutate database records. No deletion or other change was performed.",
            warnings=["You can ask for a clearly labeled hypothetical calculation instead."],
        )
    if re.search(r"\b(neural network|machine learning|train(?:ing)? model|predict(?:ion|ive)? model)\b", question):
        return AnalysisResult(
            database_id=request.database_id,
            question=request.question,
            outcome="unsupported",
            summary="This environment supports SQL-based analysis, not model training. The database does not establish a target definition for predictive modeling.",
            warnings=["I can prepare clearly labeled SQL features after you define a target such as churn."],
        )
    return None


class AnalyticsService:
    def __init__(
        self,
        config_store: ConfigStore,
        catalog_directory: Path,
        settings: Settings,
        analysis_agent: AnalysisAgentProtocol | None = None,
        visualization_agent: VisualizationAgentProtocol | None = None,
    ):
        self.config_store = config_store
        self.catalog_directory = catalog_directory
        self.settings = settings
        self.analysis_agent = analysis_agent or AnalysisAgent(settings)
        self.visualization_agent = visualization_agent or VisualizationAgent(settings)
        self.schema_policy = SchemaGovernancePolicy()

    def run(self, request: AnalysisRequest) -> AnalyticsRunResult:
        telemetry = RunTelemetry()
        decision = self.config_store.authorize(request.user_id, request.database_id)
        telemetry.acl_decision = decision
        if not decision.allowed:
            raise AccessDenied(decision.reason)

        preflight = request_capability_outcome(request)
        if preflight:
            telemetry.analysis_agent_status = "not_needed"
            telemetry.visualization_agent_status = "not_needed"
            telemetry.ended_at = datetime.utcnow()
            return AnalyticsRunResult(analysis=preflight, telemetry=telemetry)
        if not self.settings.live_agents_available:
            raise ConfigurationError("Live analysis is unavailable: OPENAI_API_KEY is not configured.")

        database = self.config_store.database(request.database_id)
        adapter = SQLiteAdapter(database["path"])
        raw_catalog = adapter.schema_catalog(request.database_id)
        catalog = self.schema_policy.governed_catalog(raw_catalog)
        restricted_names = self.schema_policy.restricted_column_names(raw_catalog)
        telemetry.schema_provenance = [
            f"Governed catalog supplied: {len(catalog.tables)} tables",
            f"Declared relationships supplied: {len(catalog.foreign_keys)}",
            f"Restricted fields excluded: {len(self.schema_policy.restricted_fields(raw_catalog))}",
        ]
        executor = SafeQueryExecutor(adapter, self.settings.max_result_rows, self.settings.query_timeout_seconds, restricted_names)
        telemetry.analysis_agent_status = "running"
        proposal = self.analysis_agent.propose(request.question, request.analysis_lens, request.analysis_hint, catalog)
        if proposal.outcome != "success" or not proposal.sql:
            telemetry.analysis_agent_status = "completed"
            telemetry.visualization_agent_status = "not_needed"
            telemetry.ended_at = datetime.utcnow()
            return AnalyticsRunResult(
                analysis=AnalysisResult(
                    database_id=request.database_id,
                    question=request.question,
                    analysis_type=proposal.analysis_type,
                    outcome="unsupported",
                    summary=proposal.message or "I could not complete this request with the available schema and SQL-only capabilities.",
                    warnings=["No SQL query was executed."],
                ),
                telemetry=telemetry,
            )
        try:
            query_result = executor.execute(proposal.sql)
        except UnsafeSQL:
            # Governance policy failures are final: only executable-but-invalid SQL gets one repair.
            raise
        except QueryExecutionError as first_error:
            if self.settings.max_sql_repairs < 1:
                return self._failed_analysis(request, telemetry, str(first_error))
            telemetry.sql_repairs = 1
            try:
                proposal = self.analysis_agent.repair(request.question, proposal, str(first_error), catalog)
                if proposal.outcome != "success" or not proposal.sql:
                    return self._failed_analysis(request, telemetry, "Repair could not produce a valid query")
                query_result = executor.execute(proposal.sql)
            except (QueryExecutionError, UnsafeSQL) as second_error:
                return self._failed_analysis(request, telemetry, str(second_error))

        analysis = self.analysis_agent.summarize(request.question, request.database_id, proposal, query_result)
        if proposal.interpretation_warning:
            analysis.warnings.append(proposal.interpretation_warning)
        telemetry.analysis_agent_status = "completed"
        telemetry.tables_used = analysis.tables_used
        telemetry.sql_queries = analysis.sql_queries
        telemetry.rows_returned = analysis.row_count
        telemetry.row_limit = analysis.row_limit
        telemetry.truncated = analysis.truncated
        telemetry.visualization_agent_status = "running"
        try:
            chart_spec, warning = self.choose_visualization(analysis, request.visualization_hint)
            telemetry.visualization_agent_status = "completed"
            telemetry.chart_type = chart_spec.chart_type if chart_spec else None
        except Exception:
            chart_spec = None
            warning = "Visualization could not be generated; the analysis and data remain available."
            telemetry.visualization_agent_status = "failed"
            telemetry.warnings.append(warning)
        telemetry.ended_at = datetime.utcnow()
        return AnalyticsRunResult(analysis=analysis, chart_spec=chart_spec, visualization_warning=warning, telemetry=telemetry)

    def choose_visualization(self, analysis: AnalysisResult, visualization_hint: str | None) -> tuple[ChartSpec | None, str | None]:
        """Revisualize an existing completed analysis without database or analysis-agent work."""
        if analysis.outcome != "success":
            return None, None
        if visualization_hint and visualization_hint not in {"Auto", "Prefer chart", "Prefer table"} and unsupported_visualization_requested("Custom…", visualization_hint):
            return None, f"That visualization is not currently supported. Available types include bar, line, pie, donut, scatter, histogram, box, and heatmap."
        requested = explicit_capability(visualization_hint) or explicit_capability("Custom…", visualization_hint)
        if requested == "table":
            return ChartSpec(chart_type="table", title="Table only"), None
        if requested:
            spec, reason = self._deterministic_chart_spec(analysis, requested)
            return spec, reason
        return self.visualization_agent.choose(analysis, visualization_hint), None

    @staticmethod
    def _deterministic_chart_spec(analysis: AnalysisResult, chart_type: str):
        numeric = [column for column in analysis.columns if any(isinstance(row.get(column), (int, float)) and not isinstance(row.get(column), bool) for row in analysis.rows)]
        categorical = [column for column in analysis.columns if column not in numeric]
        x = categorical[0] if categorical else (numeric[0] if numeric else None)
        y = numeric[-1] if numeric else None
        if chart_type in {"bar", "line", "pie", "donut", "scatter", "box", "heatmap"} and (not x or not y or (chart_type == "scatter" and len(numeric) < 2)):
            return None, f"A {chart_type} chart is not suitable for this result's available fields. The answer and data remain available."
        if chart_type == "scatter":
            x, y = numeric[0], numeric[1]
        if chart_type == "histogram" and not numeric:
            return None, "A histogram requires a numeric result field. The answer and data remain available."
        spec = ChartSpec(chart_type=chart_type, x=x if chart_type != "histogram" else numeric[0], y=y, title=analysis.question)
        if chart_type in {"pie", "donut"} and len(analysis.rows) > 12:
            spec.notes = "To keep this readable, the renderer shows the top 11 categories and combines the rest as Other."
        return spec, None

    @staticmethod
    def _failed_analysis(request: AnalysisRequest, telemetry: RunTelemetry, error: str) -> AnalyticsRunResult:
        telemetry.analysis_agent_status = "failed"
        telemetry.warnings.append("The analysis query could not be executed after one controlled repair attempt.")
        telemetry.ended_at = datetime.utcnow()
        analysis = AnalysisResult(
            database_id=request.database_id,
            question=request.question,
            summary="I could not safely complete this analysis with the available schema.",
            warnings=["Query execution failed safely. Try a more specific question."],
            outcome="unsupported",
        )
        return AnalyticsRunResult(analysis=analysis, telemetry=telemetry)
