"""Small, explicit reference checks for real-data analytical behavior."""

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any

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

CHINOOK_TEMPORAL_QUESTION = (
    "How has invoice revenue changed over time? Aggregate by calendar month and return exactly "
    "the columns month and revenue in chronological order."
)
CHINOOK_TEMPORAL_REFERENCE_SQL = """
SELECT
  strftime('%Y-%m', InvoiceDate) AS month,
  ROUND(SUM(Total), 2) AS revenue
FROM invoices
GROUP BY month
ORDER BY month ASC
"""

CHINOOK_GENRE_QUESTION = (
    "Which ten music genres generated the most invoice-line revenue? Return exactly the columns "
    "genre and revenue, ranked from highest to lowest revenue."
)
CHINOOK_GENRE_REFERENCE_SQL = """
SELECT
  g.Name AS genre,
  ROUND(SUM(ii.UnitPrice * ii.Quantity), 2) AS revenue
FROM invoice_items AS ii
JOIN tracks AS t ON t.TrackId = ii.TrackId
JOIN genres AS g ON g.GenreId = t.GenreId
GROUP BY g.GenreId, g.Name
ORDER BY revenue DESC, genre ASC
LIMIT 10
"""

SAKILA_CATEGORY_REVENUE_QUESTION = (
    "Which film categories generated the most payment revenue? Return exactly the columns category and revenue, "
    "ranked from highest to lowest revenue."
)
SAKILA_CATEGORY_REVENUE_REFERENCE_SQL = """
SELECT
  c.name AS category,
  ROUND(SUM(p.amount), 2) AS revenue
FROM payment AS p
JOIN rental AS r ON r.rental_id = p.rental_id
JOIN inventory AS i ON i.inventory_id = r.inventory_id
JOIN film_category AS fc ON fc.film_id = i.film_id
JOIN category AS c ON c.category_id = fc.category_id
GROUP BY c.category_id, c.name
ORDER BY revenue DESC, category ASC
"""


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    message: str


def rows_match(
    expected: list[dict[str, Any]], actual: list[dict[str, Any]], *, order_required: bool = True
) -> bool:
    """Compare analytical results with exact categories and tolerant numeric values."""
    if len(expected) != len(actual):
        return False
    unmatched = list(actual)
    for index, expected_row in enumerate(expected):
        candidates = [actual[index]] if order_required else unmatched
        match = next((candidate for candidate in candidates if row_matches(expected_row, candidate)), None)
        if match is None:
            return False
        if not order_required:
            unmatched.remove(match)
    return True


def row_matches(expected_row: dict[str, Any], actual_row: dict[str, Any]) -> bool:
    if list(expected_row) != list(actual_row):
        return False
    for key, expected_value in expected_row.items():
        actual_value = actual_row[key]
        if isinstance(expected_value, Real) and not isinstance(expected_value, bool):
            if not isinstance(actual_value, Real) or isinstance(actual_value, bool):
                return False
            if not math.isclose(float(expected_value), float(actual_value), rel_tol=1e-9, abs_tol=1e-9):
                return False
        elif expected_value != actual_value:
            return False
    return True


def is_non_increasing(rows: list[dict[str, Any]], column: str) -> bool:
    values = [row.get(column) for row in rows]
    return all(
        isinstance(left, Real)
        and not isinstance(left, bool)
        and isinstance(right, Real)
        and not isinstance(right, bool)
        and left >= right
        for left, right in zip(values, values[1:])
    )


def chinook_reference(adapter: SQLiteAdapter, sql: str) -> list[dict]:
    """Execute an independent, deterministic ground-truth query on supplied Chinook."""
    return SafeQueryExecutor(adapter, max_rows=500, timeout_seconds=5).execute(sql).rows


def chinook_revenue_reference(adapter: SQLiteAdapter) -> list[dict]:
    return chinook_reference(adapter, CHINOOK_REVENUE_REFERENCE_SQL)


def chinook_temporal_reference(adapter: SQLiteAdapter) -> list[dict]:
    return chinook_reference(adapter, CHINOOK_TEMPORAL_REFERENCE_SQL)


def chinook_genre_reference(adapter: SQLiteAdapter) -> list[dict]:
    return chinook_reference(adapter, CHINOOK_GENRE_REFERENCE_SQL)


def sakila_category_revenue_reference(adapter: SQLiteAdapter) -> list[dict]:
    return chinook_reference(adapter, SAKILA_CATEGORY_REVENUE_REFERENCE_SQL)


def verify_chinook_run(
    run: AnalyticsRunResult,
    expected_rows: list[dict[str, Any]],
    expected_columns: list[str],
    expected_chart_type: str,
    expected_x: str,
    expected_y: str,
    case_name: str,
    order_required: bool = True,
    ranking_column: str | None = None,
) -> VerificationResult:
    analysis: AnalysisResult = run.analysis
    if analysis.columns != expected_columns:
        return VerificationResult(False, f"Expected columns {expected_columns}; received {analysis.columns}")
    if not rows_match(expected_rows, analysis.rows, order_required=order_required):
        return VerificationResult(False, f"Agent result does not match deterministic {case_name} reference data")
    if ranking_column and not is_non_increasing(analysis.rows, ranking_column):
        return VerificationResult(False, f"Agent rows are not ranked by {ranking_column} from highest to lowest")
    if run.chart_spec is None or run.chart_spec.chart_type != expected_chart_type:
        chosen = run.chart_spec.chart_type if run.chart_spec else "none"
        return VerificationResult(False, f"Expected a {expected_chart_type} chart; received {chosen}")
    if run.chart_spec.x != expected_x or run.chart_spec.y != expected_y:
        return VerificationResult(False, f"Chart does not map {expected_x} to {expected_y}")
    return VerificationResult(True, f"Analysis rows and chart semantics match the deterministic {case_name} reference")


def verify_chinook_revenue_run(run: AnalyticsRunResult, adapter: SQLiteAdapter) -> VerificationResult:
    return verify_chinook_run(
        run,
        chinook_revenue_reference(adapter),
        ["country", "revenue"],
        "bar",
        "country",
        "revenue",
        "revenue",
        ranking_column="revenue",
    )


def verify_chinook_temporal_run(run: AnalyticsRunResult, adapter: SQLiteAdapter) -> VerificationResult:
    return verify_chinook_run(
        run,
        chinook_temporal_reference(adapter),
        ["month", "revenue"],
        "line",
        "month",
        "revenue",
        "temporal revenue",
    )


def verify_chinook_genre_run(run: AnalyticsRunResult, adapter: SQLiteAdapter) -> VerificationResult:
    return verify_chinook_run(
        run,
        chinook_genre_reference(adapter),
        ["genre", "revenue"],
        "bar",
        "genre",
        "revenue",
        "genre revenue",
        order_required=False,
        ranking_column="revenue",
    )


def verify_sakila_category_revenue_run(run: AnalyticsRunResult, adapter: SQLiteAdapter) -> VerificationResult:
    return verify_chinook_run(
        run,
        sakila_category_revenue_reference(adapter),
        ["category", "revenue"],
        "bar",
        "category",
        "revenue",
        "Sakila category revenue",
        ranking_column="revenue",
    )
