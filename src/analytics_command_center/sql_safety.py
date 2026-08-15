"""Deterministic SQL policy and bounded executor."""

import re
from collections.abc import Mapping

from sqlglot import exp, parse

from .database import SQLiteAdapter
from .errors import UnsafeSQL
from .models import QueryResult


FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|VACUUM|REINDEX)\b", re.I)


def validate_read_only_sql(sql: str, restricted_fields_by_table: Mapping[str, set[str]] | None = None) -> str:
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
    restricted = {
        table.lower(): {column.lower() for column in columns}
        for table, columns in (restricted_fields_by_table or {}).items()
    }
    _validate_restricted_references(statement, restricted)
    return statement.sql(dialect="sqlite")


def _validate_restricted_references(statement: exp.Expression, restricted: Mapping[str, set[str]]) -> None:
    if not restricted:
        return
    aliases = {
        table.alias_or_name.lower(): table.name.lower()
        for table in statement.find_all(exp.Table)
        if table.name
    }
    referenced_tables = set(aliases.values())
    for column in statement.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            table_name = aliases.get(column.table.lower(), column.table.lower()) if column.table else None
            if table_name in restricted:
                raise UnsafeSQL(f"Wildcard selection references restricted table: {table_name}.*")
            continue
        if not column.name:
            continue
        table_name = aliases.get(column.table.lower(), column.table.lower()) if column.table else None
        if table_name and column.name.lower() in restricted.get(table_name, set()):
            raise UnsafeSQL(f"Query references restricted field: {table_name}.{column.name.lower()}")
        if not table_name:
            blocked_table = next(
                (table for table in referenced_tables if column.name.lower() in restricted.get(table, set())),
                None,
            )
            if blocked_table:
                raise UnsafeSQL(f"Query references restricted field: {blocked_table}.{column.name.lower()}")
    if any(isinstance(projection, exp.Star) for select in statement.find_all(exp.Select) for projection in select.expressions):
        blocked_table = next((table for table in referenced_tables if table in restricted), None)
        if blocked_table:
            raise UnsafeSQL(f"Wildcard selection references restricted table: {blocked_table}.*")


class SafeQueryExecutor:
    def __init__(self, adapter: SQLiteAdapter, max_rows: int, timeout_seconds: float, restricted_fields_by_table: Mapping[str, set[str]] | None = None):
        self.adapter = adapter
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
        self.restricted_fields_by_table = restricted_fields_by_table or {}

    def execute(self, sql: str) -> QueryResult:
        safe_sql = validate_read_only_sql(sql, self.restricted_fields_by_table)
        return self.adapter.execute(safe_sql, self.max_rows, self.timeout_seconds)
