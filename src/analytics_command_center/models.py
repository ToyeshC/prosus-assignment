"""Typed contracts shared by interfaces, deterministic services, and agents."""

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    user_id: str
    database_id: str
    question: str = Field(min_length=1)
    analysis_hint: str | None = None
    visualization_hint: str | None = None


class AccessDecision(BaseModel):
    user_id: str
    database_id: str
    allowed: bool
    reason: str


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool = False
    elapsed_ms: float = 0.0


class AnalysisResult(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    database_id: str
    question: str
    analysis_type: str | None = None
    sql_queries: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    summary: str
    tables_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    row_count: int = 0


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "scatter", "histogram", "table", "none"]
    x: str | None = None
    y: str | list[str] | None = None
    title: str
    x_label: str | None = None
    y_label: str | None = None
    sort: Literal["ascending", "descending", "none"] = "none"
    notes: str | None = None


class ColumnCatalog(BaseModel):
    name: str
    declared_type: str | None = None
    nullable: bool = True
    primary_key_position: int = 0


class ForeignKeyCatalog(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class TableCatalog(BaseModel):
    name: str
    columns: list[ColumnCatalog]
    row_count: int | None = None


class SchemaCatalog(BaseModel):
    database_id: str
    adapter: str = "sqlite"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tables: list[TableCatalog]
    foreign_keys: list[ForeignKeyCatalog] = Field(default_factory=list)


class DatabaseRegistration(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    path: str
    grant_user_id: str | None = None


class RunTelemetry(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None
    acl_decision: AccessDecision | None = None
    analysis_agent_status: str = "not_started"
    visualization_agent_status: str = "not_started"
    tables_used: list[str] = Field(default_factory=list)
    sql_queries: list[str] = Field(default_factory=list)
    sql_repairs: int = 0
    rows_returned: int = 0
    chart_type: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AnalyticsRunResult(BaseModel):
    analysis: AnalysisResult
    chart_spec: ChartSpec | None = None
    visualization_warning: str | None = None
    telemetry: RunTelemetry
