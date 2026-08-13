"""Configuration-backed database registry and access control."""

from pathlib import Path

import yaml

from .models import AccessDecision


class ConfigStore:
    def __init__(self, registry_path: Path, acl_path: Path):
        self.registry_path = registry_path
        self.acl_path = acl_path

    @staticmethod
    def _read(path: Path) -> dict:
        return yaml.safe_load(path.read_text()) or {}

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))

    def registry(self) -> dict:
        return self._read(self.registry_path)

    def acl(self) -> dict:
        return self._read(self.acl_path)

    def database(self, database_id: str) -> dict:
        try:
            return self.registry()["databases"][database_id]
        except KeyError as error:
            raise KeyError(f"Unknown database: {database_id}") from error

    def user(self, user_id: str) -> dict:
        try:
            return self.acl()["users"][user_id]
        except KeyError as error:
            raise KeyError(f"Unknown user: {user_id}") from error

    def accessible_databases(self, user_id: str) -> list[str]:
        return list(self.user(user_id).get("databases", []))

    def authorize(self, user_id: str, database_id: str) -> AccessDecision:
        if database_id in self.accessible_databases(user_id):
            return AccessDecision(
                user_id=user_id, database_id=database_id, allowed=True, reason="User has database grant"
            )
        return AccessDecision(
            user_id=user_id,
            database_id=database_id,
            allowed=False,
            reason="User has no grant for this database",
        )

    def register_database(self, database_id: str, path: str) -> None:
        registry = self.registry()
        registry.setdefault("databases", {})[database_id] = {
            "display_name": database_id.replace("_", " ").title(),
            "adapter": "sqlite",
            "path": path,
            "enabled": True,
        }
        self._write(self.registry_path, registry)

    def grant(self, user_id: str, database_id: str) -> None:
        acl = self.acl()
        user = acl.setdefault("users", {}).get(user_id)
        if user is None:
            raise KeyError(f"Unknown user: {user_id}")
        grants = user.setdefault("databases", [])
        if database_id not in grants:
            grants.append(database_id)
        self._write(self.acl_path, acl)
