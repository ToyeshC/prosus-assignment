"""Small, explicit reference checks for real-data analytical behavior."""

from dataclasses import dataclass

from .database import SQLiteAdapter
from .models import AnalysisResult, AnalyticsRunResult
from .sql_safety import SafeQueryExecutor


CHINOOK_REVENUE_QUESTION = (
    "Which five billing countries generated the most invoice revenue? "
    "Return exactly the columns country and revenue, ranked from highest to lowest revenue."
)
CHINOOK_REVENUE_REFERENCE_SQL = """
SELECT
  BillingCountry AS country,
  ROUND(SUM(Total), 2) AS revenue
FROM invoices
GROUP BY BillingCountry
ORDER BY revenue DESC, country ASC
LIMIT 5
"""


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    message: str


def chinook_revenue_reference(adapter: SQLiteAdapter) -> list[dict]:
    """Execute the independent, deterministic ground-truth query on supplied Chinook."""
    return SafeQueryExecutor(adapter, max_rows=10, timeout_seconds=5).execute(
        CHINOOK_REVENUE_REFERENCE_SQL
    ).rows


def verify_chinook_revenue_run(run: AnalyticsRunResult, adapter: SQLiteAdapter) -> VerificationResult:
    analysis: AnalysisResult = run.analysis
    reference_rows = chinook_revenue_reference(adapter)
    if analysis.columns != ["country", "revenue"]:
        return VerificationResult(False, f"Expected columns country, revenue; received {analysis.columns}")
    if analysis.rows != reference_rows:
        return VerificationResult(False, "Agent result does not match deterministic Chinook reference data")
    if run.chart_spec is None or run.chart_spec.chart_type != "bar":
        chosen = run.chart_spec.chart_type if run.chart_spec else "none"
        return VerificationResult(False, f"Expected a bar chart for country ranking; received {chosen}")
    if run.chart_spec.x != "country" or run.chart_spec.y != "revenue":
        return VerificationResult(False, "Bar chart does not map country to revenue")
    return VerificationResult(True, "Analysis rows and bar-chart semantics match the deterministic reference")
