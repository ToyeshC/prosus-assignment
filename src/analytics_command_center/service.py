"""The deterministic trust boundary coordinating agents and safe database work."""

from datetime import datetime
from pathlib import Path

from .agents import AnalysisAgent, AnalysisAgentProtocol, VisualizationAgent, VisualizationAgentProtocol
from .database import SQLiteAdapter
from .errors import AccessDenied, ConfigurationError, QueryExecutionError, UnsafeSQL
from .models import AnalysisRequest, AnalysisResult, AnalyticsRunResult, RunTelemetry
from .registry import ConfigStore
from .settings import Settings
from .sql_safety import SafeQueryExecutor


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

    def run(self, request: AnalysisRequest) -> AnalyticsRunResult:
        telemetry = RunTelemetry()
        decision = self.config_store.authorize(request.user_id, request.database_id)
        telemetry.acl_decision = decision
        if not decision.allowed:
            raise AccessDenied(decision.reason)
        if not self.settings.live_agents_available:
            raise ConfigurationError("Live analysis is unavailable: OPENAI_API_KEY is not configured.")

        database = self.config_store.database(request.database_id)
        adapter = SQLiteAdapter(database["path"])
        catalog = adapter.schema_catalog(request.database_id)
        executor = SafeQueryExecutor(adapter, self.settings.max_result_rows, self.settings.query_timeout_seconds)
        telemetry.analysis_agent_status = "running"
        proposal = self.analysis_agent.propose(request.question, request.analysis_hint, catalog)
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
                query_result = executor.execute(proposal.sql)
            except (QueryExecutionError, UnsafeSQL) as second_error:
                return self._failed_analysis(request, telemetry, str(second_error))

        analysis = self.analysis_agent.summarize(request.question, request.database_id, proposal, query_result)
        telemetry.analysis_agent_status = "completed"
        telemetry.tables_used = analysis.tables_used
        telemetry.sql_queries = analysis.sql_queries
        telemetry.rows_returned = analysis.row_count
        telemetry.visualization_agent_status = "running"
        try:
            chart_spec = self.visualization_agent.choose(analysis, request.visualization_hint)
            telemetry.visualization_agent_status = "completed"
            telemetry.chart_type = chart_spec.chart_type
            warning = None
        except Exception:
            chart_spec = None
            warning = "Visualization could not be generated; the analysis and data remain available."
            telemetry.visualization_agent_status = "failed"
            telemetry.warnings.append(warning)
        telemetry.ended_at = datetime.utcnow()
        return AnalyticsRunResult(analysis=analysis, chart_spec=chart_spec, visualization_warning=warning, telemetry=telemetry)

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
        )
        return AnalyticsRunResult(analysis=analysis, telemetry=telemetry)
