"""Canonical demo state for the Donné onboarding narrative."""

from dataclasses import dataclass
from pathlib import Path

from .registry import ConfigStore


CANONICAL_REGISTRY = {
    "databases": {
        "chinook": {
            "display_name": "Chinook",
            "adapter": "sqlite",
            "path": "datasets/chinook.db",
            "enabled": True,
        },
        "northwind": {
            "display_name": "Northwind",
            "adapter": "sqlite",
            "path": "datasets/northwind_small.sqlite",
            "enabled": True,
        },
    }
}

CANONICAL_ACL = {
    "users": {
        "toyesh": {"display_name": "Toyesh", "databases": ["chinook", "northwind"]},
        "alfred": {"display_name": "Alfred", "databases": ["chinook"]},
        "donne": {"display_name": "Donné", "databases": []},
    }
}


@dataclass(frozen=True)
class DemoCheck:
    is_canonical: bool
    messages: list[str]


class DemoStateService:
    def __init__(self, config_store: ConfigStore, catalog_directory: Path):
        self.config_store = config_store
        self.catalog_directory = catalog_directory

    def check(self) -> DemoCheck:
        registry_ok = self._registry_matches_canonical(self.config_store.registry())
        acl_ok = self.config_store.acl() == CANONICAL_ACL
        messages = [
            f"Registry: {'canonical' if registry_ok else 'changed'}",
            f"ACL: {'canonical' if acl_ok else 'changed'}",
            "Sakila: unregistered" if "sakila" not in self.config_store.registry().get("databases", {}) else "Sakila: registered",
        ]
        return DemoCheck(is_canonical=registry_ok and acl_ok, messages=messages)

    def reset(self) -> DemoCheck:
        current_databases = self.config_store.registry().get("databases", {})
        restored_databases = {
            database_id: {**current_databases.get(database_id, {}), **canonical_registration}
            for database_id, canonical_registration in CANONICAL_REGISTRY["databases"].items()
        }
        self.config_store._write(self.config_store.registry_path, {"databases": restored_databases})
        self.config_store._write(self.config_store.acl_path, CANONICAL_ACL)
        sakila_catalog = self.catalog_directory / "sakila.json"
        if sakila_catalog.exists():
            sakila_catalog.unlink()
        return self.check()

    @staticmethod
    def _registry_matches_canonical(registry: dict) -> bool:
        databases = registry.get("databases", {})
        canonical_databases = CANONICAL_REGISTRY["databases"]
        return (
            set(databases) == set(canonical_databases)
            and all(
                all(databases[database_id].get(key) == value for key, value in canonical_registration.items())
                for database_id, canonical_registration in canonical_databases.items()
            )
        )
