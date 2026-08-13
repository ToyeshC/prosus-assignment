"""Deterministic SQL policy and bounded executor."""

import re

from sqlglot import exp, parse

from .database import SQLiteAdapter
from .errors import UnsafeSQL
from .models import QueryResult


FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|VACUUM|REINDEX)\b", re.I)


def validate_read_only_sql(sql: str) -> str:
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
    return statement.sql(dialect="sqlite")


class SafeQueryExecutor:
    def __init__(self, adapter: SQLiteAdapter, max_rows: int, timeout_seconds: float):
        self.adapter = adapter
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds

    def execute(self, sql: str) -> QueryResult:
        safe_sql = validate_read_only_sql(sql)
        return self.adapter.execute(safe_sql, self.max_rows, self.timeout_seconds)
