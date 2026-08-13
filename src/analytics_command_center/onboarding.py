"""Deterministic database onboarding; never an LLM responsibility."""

import json
from pathlib import Path

from .database import SQLiteAdapter
from .models import DatabaseRegistration, SchemaCatalog
from .registry import ConfigStore


class DatabaseOnboardingService:
    def __init__(self, config_store: ConfigStore, catalog_directory: Path):
        self.config_store = config_store
        self.catalog_directory = catalog_directory

    def register(self, request: DatabaseRegistration) -> SchemaCatalog:
        catalog = self.catalog(request.name, request.path)
        self.config_store.register_database(request.name, request.path)
        if request.grant_user_id:
            self.config_store.grant(request.grant_user_id, request.name)

        return catalog

    def catalog(self, database_id: str, path: str) -> SchemaCatalog:
        """Create generated discovery metadata without changing registry or ACL state."""
        adapter = SQLiteAdapter(path)
        catalog = adapter.schema_catalog(database_id)
        self.catalog_directory.mkdir(parents=True, exist_ok=True)
        (self.catalog_directory / f"{database_id}.json").write_text(
            json.dumps(catalog.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )
        return catalog
