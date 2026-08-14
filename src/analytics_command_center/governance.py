"""Minimal deterministic schema governance before any agent receives schema context."""

from dataclasses import dataclass, field
import re

from .models import SchemaCatalog, TableCatalog


DEFAULT_RESTRICTED_COLUMN_PATTERNS = (
    r"^password$", r"^passwd$", r"^password_hash$", r"^secret$", r"^api_key$",
    r"^access_token$", r"^refresh_token$", r"^private_key$",
)


@dataclass(frozen=True)
class SchemaGovernancePolicy:
    restricted_patterns: tuple[str, ...] = DEFAULT_RESTRICTED_COLUMN_PATTERNS
    _compiled: tuple[re.Pattern[str], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_compiled", tuple(re.compile(pattern, re.I) for pattern in self.restricted_patterns))

    def is_restricted(self, column_name: str) -> bool:
        return any(pattern.match(column_name) for pattern in self._compiled)

    def restricted_fields(self, catalog: SchemaCatalog) -> list[str]:
        return [f"{table.name}.{column.name}" for table in catalog.tables for column in table.columns if self.is_restricted(column.name)]

    def governed_catalog(self, catalog: SchemaCatalog) -> SchemaCatalog:
        tables = [
            TableCatalog(
                name=table.name,
                columns=[column for column in table.columns if not self.is_restricted(column.name)],
                row_count=table.row_count,
            )
            for table in catalog.tables
        ]
        return catalog.model_copy(update={"tables": tables})

    def restricted_column_names(self, catalog: SchemaCatalog) -> set[str]:
        return {column.name.lower() for table in catalog.tables for column in table.columns if self.is_restricted(column.name)}
