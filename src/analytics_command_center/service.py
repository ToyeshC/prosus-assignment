"""The deterministic trust boundary coordinating agents and safe database work."""

from datetime import datetime
from itertools import combinations
from pathlib import Path
import re

from .agents import AnalysisAgent, AnalysisAgentProtocol, VisualizationAgent, VisualizationAgentProtocol
from .audit import AuditSink, JsonlAuditSink
from .database import SQLiteAdapter
from .errors import AccessDenied, ConfigurationError, QueryExecutionError, UnsafeSQL
from .governance import SchemaGovernancePolicy
from .models import AnalysisRequest, AnalysisResult, AnalyticsRunResult, ChartSpec, QueryResult, RunTelemetry
from .registry import ConfigStore
from .settings import Settings
from .sql_safety import SafeQueryExecutor
from .visualization_capabilities import explicit_capability, unsupported_visualization_requested


_TEMPORAL_CUES = re.compile(r"\b(over time|trend|changed|change|monthly|quarterly|yearly|by month|by year|date)\b", re.I)
_MUTATION_CUES = re.compile(r"\b(delete|drop|truncate|insert|update|alter|create|set\s+.+\s+to)\b", re.I)
_MODEL_TRAINING_CUES = re.compile(r"\b(neural network|machine learning|deep learning|train(?:ing)? (?:a )?(?:model|classifier|regressor)|predict(?:ion|ive)? model|classif(?:ication|ier) model|regress(?:ion|or) model)\b", re.I)
_TEMPORAL_FIELD_CUES = re.compile(r"(?:date|time|month|year|quarter|week|day)", re.I)
_ENTITY_CATEGORICAL_CHARTS = frozenset({"bar", "pie", "donut", "box", "scatter", "line"})


def request_capability_outcome(request: AnalysisRequest) -> AnalysisResult | None:
    """Refuse requests that should never be silently reinterpreted as analytics."""
    if _MUTATION_CUES.search(request.question):
        return AnalysisResult(
            database_id=request.database_id, question=request.question, outcome="blocked",
            summary="This analytics environment is read-only and cannot mutate database records. No deletion or other change was performed.",
            warnings=["You can ask for a clearly labeled hypothetical calculation instead."], analysis_lens=request.analysis_lens,
        )
    if _MODEL_TRAINING_CUES.search(request.question):
        return AnalysisResult(
            database_id=request.database_id, question=request.question, outcome="unsupported",
            summary="This environment supports SQL-based analysis, not model training. The database does not establish a target definition for predictive modeling.",
            warnings=["I can prepare clearly labeled SQL features after you define a target such as churn."], analysis_lens=request.analysis_lens,
        )
    return None


def lens_conflict_outcome(request: AnalysisRequest) -> AnalysisResult | None:
    """Small deterministic contract: an explicit lens is visibly applied or rejected."""
    if request.analysis_lens == "auto" or request.analysis_lens == "custom":
        return None
    temporal_goal = bool(_TEMPORAL_CUES.search(request.question))
    if request.analysis_lens == "trend" and not temporal_goal:
        reason = "The trend lens requires a time-based analysis, but this question asks for a non-temporal result."
    elif request.analysis_lens == "ranking" and temporal_goal:
        reason = "The ranking lens conflicts with this time-based question. Choose Trend or remove the explicit lens."
    else:
        return None
    return AnalysisResult(
        database_id=request.database_id, question=request.question, outcome="unsupported", summary=reason,
        warnings=["No SQL query was executed."], analysis_lens=request.analysis_lens,
    )


class AnalyticsService:
    def __init__(
        self, config_store: ConfigStore, catalog_directory: Path, settings: Settings,
        analysis_agent: AnalysisAgentProtocol | None = None, visualization_agent: VisualizationAgentProtocol | None = None,
        audit_sink: AuditSink | None = None,
    ):
        self.config_store = config_store
        self.catalog_directory = catalog_directory
        self.settings = settings
        self.analysis_agent = analysis_agent or AnalysisAgent(settings)
        self.visualization_agent = visualization_agent or VisualizationAgent(settings)
        self.schema_policy = SchemaGovernancePolicy()
        self.audit_sink = audit_sink or JsonlAuditSink(catalog_directory.parent / "audit" / "events.jsonl")

    def _audit(self, request: AnalysisRequest, telemetry: RunTelemetry, action: str = "analysis_request") -> None:
        decision = "ALLOWED" if telemetry.acl_decision and telemetry.acl_decision.allowed else "DENIED"
        self.audit_sink.record(
            run_id=telemetry.run_id, user=request.user_id, database=request.database_id, action=action,
            decision=decision, outcome=telemetry.outcome, policy=telemetry.governance_policy,
            sql_executed=telemetry.sql_executed,
        )

    @staticmethod
    def _finish(telemetry: RunTelemetry, analysis: AnalysisResult) -> None:
        telemetry.outcome = analysis.outcome
        telemetry.ended_at = datetime.utcnow()

    def run(self, request: AnalysisRequest) -> AnalyticsRunResult:
        telemetry = RunTelemetry()
        decision = self.config_store.authorize(request.user_id, request.database_id)
        telemetry.acl_decision = decision
        if not decision.allowed:
            telemetry.outcome = "blocked"
            self._audit(request, telemetry, action="authorization")
            raise AccessDenied(decision.reason)

        for early_outcome in (request_capability_outcome(request), lens_conflict_outcome(request)):
            if early_outcome:
                telemetry.analysis_agent_status = telemetry.visualization_agent_status = "not_needed"
                telemetry.governance_policy = "read_only" if early_outcome.outcome == "blocked" else "capability_boundary"
                self._finish(telemetry, early_outcome)
                self._audit(request, telemetry)
                return AnalyticsRunResult(analysis=early_outcome, telemetry=telemetry)
        if not self.settings.live_agents_available:
            raise ConfigurationError("Live analysis is unavailable: OPENAI_API_KEY is not configured.")

        database = self.config_store.database(request.database_id)
        adapter = SQLiteAdapter(database["path"])
        raw_catalog = adapter.schema_catalog(request.database_id)
        catalog = self.schema_policy.governed_catalog(raw_catalog)
        restricted_fields = self.schema_policy.restricted_fields(raw_catalog)
        executor = SafeQueryExecutor(adapter, self.settings.max_result_rows, self.settings.query_timeout_seconds, self.schema_policy.restricted_column_names(raw_catalog))
        telemetry.schema_provenance = [
            f"Governed catalog supplied: {len(catalog.tables)} tables",
            f"Declared relationships supplied: {len(catalog.foreign_keys)}",
            f"Restricted fields excluded: {len(restricted_fields)}",
        ]
        telemetry.analysis_agent_status = "running"
        telemetry.analysis_agent_calls += 1
        proposal = self.analysis_agent.propose(request.question, request.analysis_lens, request.analysis_hint, catalog)
        if proposal.outcome != "success" or not proposal.sql:
            analysis = AnalysisResult(
                database_id=request.database_id, question=request.question, analysis_type=proposal.analysis_type,
                analysis_lens=request.analysis_lens, outcome="unsupported",
                summary=proposal.message or "I could not complete this request with the available schema and SQL-only capabilities.",
                warnings=["No SQL query was executed."],
            )
            telemetry.analysis_agent_status, telemetry.visualization_agent_status = "completed", "not_needed"
            self._finish(telemetry, analysis)
            self._audit(request, telemetry)
            return AnalyticsRunResult(analysis=analysis, telemetry=telemetry)

        try:
            query_result = executor.execute(proposal.sql)
            telemetry.sql_execution_count += 1
            telemetry.sql_executed = True
        except UnsafeSQL as error:
            analysis = self._blocked_sql_analysis(request, telemetry, restricted_fields, str(error))
            self._audit(request, telemetry, action="restricted_column_request" if telemetry.governance_policy == "restricted_column" else "unsafe_sql_request")
            return AnalyticsRunResult(analysis=analysis, telemetry=telemetry)
        except QueryExecutionError as first_error:
            telemetry.sql_execution_count += 1
            telemetry.sql_executed = True
            if self.settings.max_sql_repairs < 1:
                failed = self._failed_analysis(request, telemetry)
                self._audit(request, telemetry)
                return failed
            telemetry.sql_repairs = 1
            telemetry.analysis_agent_calls += 1
            try:
                proposal = self.analysis_agent.repair(request.question, proposal, str(first_error), catalog)
                if proposal.outcome != "success" or not proposal.sql:
                    failed = self._failed_analysis(request, telemetry)
                    self._audit(request, telemetry)
                    return failed
                query_result = executor.execute(proposal.sql)
                telemetry.sql_execution_count += 1
            except UnsafeSQL as error:
                analysis = self._blocked_sql_analysis(request, telemetry, restricted_fields, str(error))
                self._audit(request, telemetry, action="restricted_column_request" if telemetry.governance_policy == "restricted_column" else "unsafe_sql_request")
                return AnalyticsRunResult(analysis=analysis, telemetry=telemetry)
            except QueryExecutionError:
                telemetry.sql_execution_count += 1
                failed = self._failed_analysis(request, telemetry)
                self._audit(request, telemetry)
                return failed

        analysis = self._analysis_from_query(request, proposal, query_result)
        telemetry.analysis_agent_status = "completed"
        telemetry.tables_used, telemetry.sql_queries = analysis.tables_used, analysis.sql_queries
        telemetry.rows_returned, telemetry.row_limit, telemetry.truncated = analysis.row_count, analysis.row_limit, analysis.truncated
        if analysis.outcome == "success":
            telemetry.visualization_agent_status = "running"
            try:
                chart_spec, warning = self.choose_visualization(analysis, request.visualization_hint)
                telemetry.visualization_agent_status = "completed"
                telemetry.visualization_runs = 1
                telemetry.chart_type = chart_spec.chart_type if chart_spec else None
            except Exception:
                chart_spec, warning = None, "Visualization could not be generated; the analysis and data remain available."
                telemetry.visualization_agent_status = "failed"
                telemetry.warnings.append(warning)
        else:
            chart_spec, warning = None, None
            telemetry.visualization_agent_status = "not_needed"
        self._finish(telemetry, analysis)
        self._audit(request, telemetry)
        return AnalyticsRunResult(analysis=analysis, chart_spec=chart_spec, visualization_warning=warning, telemetry=telemetry)

    def _analysis_from_query(self, request: AnalysisRequest, proposal, result: QueryResult) -> AnalysisResult:
        if self._zero_match_aggregate(result):
            return AnalysisResult(
                database_id=request.database_id, question=request.question, analysis_type=proposal.analysis_type,
                analysis_lens=request.analysis_lens, outcome="no_data", sql_queries=[proposal.sql],
                summary="No matching records were found for this request.", tables_used=proposal.tables_used,
                warnings=["The aggregate is zero because no matching records were found."], row_limit=result.row_limit,
            )
        analysis = self.analysis_agent.summarize(request.question, request.database_id, proposal, result)
        analysis.analysis_lens = request.analysis_lens
        if proposal.interpretation_warning:
            analysis.warnings.append(proposal.interpretation_warning)
        if request.analysis_lens == "distribution":
            analysis.analysis_type = "distribution"
            analysis.warnings.append("Distribution lens applied to the returned observation-level measure.")
        return analysis

    @staticmethod
    def _zero_match_aggregate(result: QueryResult) -> bool:
        count_columns = [column for column in result.columns if column.lower() in {"matching_row_count", "match_count", "matching_count"}]
        return bool(count_columns and result.rows and all(row.get(column) == 0 for column in count_columns for row in result.rows))

    def _blocked_sql_analysis(self, request: AnalysisRequest, telemetry: RunTelemetry, restricted_fields: list[str], error: str) -> AnalysisResult:
        restricted = "restricted" in error.lower()
        telemetry.analysis_agent_status = "completed"
        telemetry.visualization_agent_status = "not_needed"
        telemetry.governance_policy = "restricted_column" if restricted else "sql_safety"
        telemetry.restricted_reference = next((field for field in restricted_fields if field.split(".", 1)[1].lower() in request.question.lower()), None)
        analysis = AnalysisResult(
            database_id=request.database_id, question=request.question, analysis_lens=request.analysis_lens, outcome="blocked",
            summary="This request references a governed field that is unavailable for analysis." if restricted else "This SQL request is outside the read-only analytics policy.",
            warnings=["No SQL query was executed."],
        )
        self._finish(telemetry, analysis)
        return analysis

    def choose_visualization(self, analysis: AnalysisResult, visualization_hint: str | None) -> tuple[ChartSpec | None, str | None]:
        """Revisualize a completed result without database or analysis-agent work."""
        if analysis.outcome != "success":
            return None, None
        if visualization_hint and visualization_hint not in {"Auto", "Prefer chart", "Prefer table"} and unsupported_visualization_requested("Custom…", visualization_hint):
            return None, "That visualization is not currently supported. Available types include bar, line, pie, donut, scatter, histogram, box, and heatmap."
        requested = explicit_capability(visualization_hint) or explicit_capability("Custom…", visualization_hint)
        if requested == "table":
            return ChartSpec(chart_type="table", title="Table only"), None
        if requested:
            spec, reason = self._deterministic_chart_spec(analysis, requested)
        elif analysis.analysis_lens == "distribution":
            spec, reason = self._deterministic_chart_spec(analysis, "histogram")
        else:
            spec, reason = self.visualization_agent.choose(analysis, visualization_hint), None
        if spec is None:
            return None, reason
        return self._with_safe_categorical_identity(analysis, spec)

    def revisualize(self, result: AnalyticsRunResult, visualization_hint: str | None) -> AnalyticsRunResult:
        """Mutate only presentation state for a persisted AnalysisResult."""
        spec, warning = self.choose_visualization(result.analysis, visualization_hint)
        result.chart_spec, result.visualization_warning = spec, warning
        result.telemetry.analysis_reused = True
        result.telemetry.visualization_runs += 1
        result.telemetry.visualization_revision += 1
        result.telemetry.chart_type = spec.chart_type if spec else None
        result.telemetry.visualization_agent_status = "not_needed" if explicit_capability(visualization_hint) or explicit_capability("Custom…", visualization_hint) else "completed"
        return result

    @staticmethod
    def _deterministic_chart_spec(analysis: AnalysisResult, chart_type: str) -> tuple[ChartSpec | None, str | None]:
        numeric = [column for column in analysis.columns if any(isinstance(row.get(column), (int, float)) and not isinstance(row.get(column), bool) for row in analysis.rows)]
        categorical = [column for column in analysis.columns if column not in numeric]
        x = categorical[0] if categorical else (numeric[0] if numeric else None)
        y = numeric[-1] if numeric else None
        if chart_type == "scatter":
            if not x or not y:
                return None, "A scatter chart requires an x field and a numeric y field. The answer and data remain available."
        elif chart_type in {"bar", "line", "pie", "donut", "box", "heatmap"} and (not x or not y):
            return None, f"A {chart_type} chart is not suitable for this result's available fields. The answer and data remain available."
        if chart_type == "histogram":
            if not numeric:
                return None, "A histogram requires a numeric result field. The answer and data remain available."
            x, y = numeric[-1], None
        spec = ChartSpec(chart_type=chart_type, x=x, y=y, title=analysis.question)
        if chart_type in {"pie", "donut"} and len(analysis.rows) > 12:
            spec.notes = "To keep this readable, the renderer shows the top 11 categories and combines the rest as Other."
        return spec, None

    @staticmethod
    def _with_safe_categorical_identity(analysis: AnalysisResult, spec: ChartSpec) -> tuple[ChartSpec | None, str | None]:
        """Attach a stable ID and human-readable label to entity-like categorical results.

        Chart selection is deliberately upstream of this step: Auto and explicit chart choices
        produce a ChartSpec first, then share this deterministic semantic normalization.
        """
        if (
            spec.chart_type not in _ENTITY_CATEGORICAL_CHARTS
            or not spec.x
            or not analysis.rows
            or spec.x not in analysis.columns
            or analysis.analysis_lens == "distribution"
            or _TEMPORAL_FIELD_CUES.search(spec.x)
        ):
            return spec, None

        identity_fields = [
            column for column in analysis.columns
            if column.lower().endswith("id") and len({row.get(column) for row in analysis.rows}) == len(analysis.rows)
        ]
        if not identity_fields or spec.x not in {*identity_fields, *[column for column in analysis.columns if any(isinstance(row.get(column), str) and row.get(column) for row in analysis.rows)]}:
            return spec, None

        text_fields = [
            column for column in analysis.columns
            if all(isinstance(row.get(column), str) and row.get(column) for row in analysis.rows)
        ]
        candidate_fields = AnalyticsService._display_label_fields(text_fields, spec.x, analysis.rows)
        if candidate_fields is None:
            if spec.x in identity_fields:
                return spec.model_copy(update={"identity_field": identity_fields[0]}), None
            return None, "Distinct entities share this chart label and no safe unique display label could be derived. The answer and data remain available."
        return spec.model_copy(update={"label_fields": candidate_fields, "identity_field": identity_fields[0]}), None

    @staticmethod
    def _display_label_fields(text_fields: list[str], x: str, rows: list[dict]) -> list[str] | None:
        """Prefer a concise composite label, retaining the chosen categorical field first."""
        ordered_fields = ([x] if x in text_fields else []) + [field for field in text_fields if field != x]
        for length in range(2, len(ordered_fields) + 1):
            for fields in combinations(ordered_fields, length):
                labels = [tuple(row.get(field) for field in fields) for row in rows]
                if len(labels) == len(set(labels)):
                    return list(fields)
        unique_text = next(
            (field for field in ordered_fields if len({row.get(field) for row in rows}) == len(rows)),
            None,
        )
        return [unique_text] if unique_text else None

    @staticmethod
    def _failed_analysis(request: AnalysisRequest, telemetry: RunTelemetry) -> AnalyticsRunResult:
        telemetry.analysis_agent_status = "failed"
        telemetry.warnings.append("The analysis query could not be executed after one controlled repair attempt.")
        analysis = AnalysisResult(
            database_id=request.database_id, question=request.question, analysis_lens=request.analysis_lens,
            summary="I could not safely complete this analysis with the available schema.",
            warnings=["Query execution failed safely. Try a more specific question."], outcome="unsupported",
        )
        telemetry.outcome = analysis.outcome
        telemetry.ended_at = datetime.utcnow()
        return AnalyticsRunResult(analysis=analysis, telemetry=telemetry)
