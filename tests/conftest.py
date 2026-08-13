import sqlite3
from pathlib import Path

import pytest

from analytics_command_center.registry import ConfigStore


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    path = tmp_path / "sample.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE customer (id INTEGER PRIMARY KEY, country TEXT);
            CREATE TABLE invoice (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL,
                FOREIGN KEY(customer_id) REFERENCES customer(id));
            INSERT INTO customer VALUES (1, 'NL'), (2, 'US');
            INSERT INTO invoice VALUES (1, 1, 10.0), (2, 1, 20.0), (3, 2, 30.0);
        """)
    return path


@pytest.fixture
def store(tmp_path: Path, sample_db: Path) -> ConfigStore:
    registry, acl = tmp_path / "registry.yaml", tmp_path / "acl.yaml"
    registry.write_text(f"databases:\n  sample:\n    display_name: Sample\n    adapter: sqlite\n    path: {sample_db}\n    enabled: true\n")
    acl.write_text("users:\n  toyesh:\n    display_name: Toyesh\n    databases: [sample]\n  donne:\n    display_name: Donné\n    databases: []\n")
    return ConfigStore(registry, acl)
