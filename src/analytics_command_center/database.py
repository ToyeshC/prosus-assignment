"""Read-only SQLite discovery and query primitives."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import QueryExecutionError
from .models import ColumnCatalog, ForeignKeyCatalog, QueryResult, SchemaCatalog, TableCatalog


class SQLiteAdapter:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def test_connection(self) -> None:
        if not self.path.is_file():
            raise FileNotFoundError(f"SQLite database file does not exist: {self.path}")
        with self.connection() as connection:
            connection.execute("SELECT 1")

    @contextmanager
    def connection(self):
        uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def schema_catalog(self, database_id: str, include_row_counts: bool = True) -> SchemaCatalog:
        self.test_connection()
        tables: list[TableCatalog] = []
        foreign_keys: list[ForeignKeyCatalog] = []
        with self.connection() as connection:
            names = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for table in names:
                quoted = self.quote_identifier(table)
                info = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
                columns = [
                    ColumnCatalog(
                        name=row["name"],
                        declared_type=row["type"] or None,
                        nullable=not bool(row["notnull"]),
                        primary_key_position=row["pk"],
                    )
                    for row in info
                ]
                row_count = None
                if include_row_counts:
                    row_count = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
                tables.append(TableCatalog(name=table, columns=columns, row_count=row_count))
                for foreign_key in connection.execute(f"PRAGMA foreign_key_list({quoted})").fetchall():
                    foreign_keys.append(
                        ForeignKeyCatalog(
                            from_table=table,
                            from_column=foreign_key["from"],
                            to_table=foreign_key["table"],
                            to_column=foreign_key["to"],
                        )
                    )
        return SchemaCatalog(database_id=database_id, tables=tables, foreign_keys=foreign_keys)

    def execute(self, sql: str, limit: int, timeout_seconds: float) -> QueryResult:
        import time

        started = time.perf_counter()
        try:
            with self.connection() as connection:
                connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
                deadline = time.monotonic() + timeout_seconds
                connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1_000)
                cursor = connection.execute(sql)
                rows = cursor.fetchmany(limit + 1)
        except sqlite3.Error as error:
            raise QueryExecutionError(self.sanitize_error(error)) from None
        truncated = len(rows) > limit
        rows = rows[:limit]
        return QueryResult(
            columns=[item[0] for item in cursor.description or []],
            rows=[dict(row) for row in rows],
            truncated=truncated,
            row_limit=limit,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def quote_identifier(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    @staticmethod
    def sanitize_error(error: sqlite3.Error) -> str:
        message = str(error).replace("\n", " ")
        return message[:300]
