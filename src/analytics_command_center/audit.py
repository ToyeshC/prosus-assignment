"""Small replaceable audit sink for safe governance events."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Protocol


class AuditSink(Protocol):
    def record(self, **event: object) -> None: ...


class JsonlAuditSink:
    """Append only bounded metadata; never accepts result rows or credentials."""

    def __init__(self, path: Path):
        self.path = path

    def record(self, **event: object) -> None:
        safe = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": event.get("run_id"),
            "user": event.get("user"),
            "database": event.get("database"),
            "action": event.get("action"),
            "decision": event.get("decision"),
            "outcome": event.get("outcome"),
            "policy": event.get("policy"),
            "sql_executed": bool(event.get("sql_executed")),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, ensure_ascii=False) + "\n")
