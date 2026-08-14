"""Deterministic SQL policy and bounded executor."""

import re

from sqlglot import exp, parse

from .database import SQLiteAdapter
from .errors import UnsafeSQL
from .models import QueryResult


FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|VACUUM|REINDEX)\b", re.I)


def validate_read_only_sql(sql: str, restricted_column_names: set[str] | None = None) -> str:
    if not sql.strip():
        raise UnsafeSQL("SQL must not be empty")
    if FORBIDDEN.search(sql):
        raise UnsafeSQL("Only read-only SELECT statements are allowed")
    try:
        statements = parse(sql, read="sqlite")
    except Exception as error:
        raise UnsafeSQL("SQL could not be parsed") from error
    if len(statements) != 1:
        raise UnsafeSQL("Exactly one SQL statement is allowed")
    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union)):
        raise UnsafeSQL("Only SELECT queries and read-oriented CTEs are allowed")
    if statement.find(exp.Command):
        raise UnsafeSQL("SQLite commands are not allowed")
    restricted = {name.lower() for name in restricted_column_names or set()}
    requested = {column.name.lower() for column in statement.find_all(exp.Column) if column.name}
    if restricted & requested:
        raise UnsafeSQL("Query references a restricted column")
    if restricted and any(isinstance(node, exp.Star) for node in statement.walk()):
        raise UnsafeSQL("Wildcard selection is not allowed when a schema contains restricted columns")
    return statement.sql(dialect="sqlite")


class SafeQueryExecutor:
    def __init__(self, adapter: SQLiteAdapter, max_rows: int, timeout_seconds: float, restricted_column_names: set[str] | None = None):
        self.adapter = adapter
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
        self.restricted_column_names = restricted_column_names or set()

    def execute(self, sql: str) -> QueryResult:
        safe_sql = validate_read_only_sql(sql, self.restricted_column_names)
        return self.adapter.execute(safe_sql, self.max_rows, self.timeout_seconds)
