from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".chem4all" / "name_cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS name_cache (
    smiles      TEXT NOT NULL,
    name_type   TEXT NOT NULL,
    source      TEXT NOT NULL,
    name        TEXT,
    found       INTEGER NOT NULL,
    queried_at  TEXT NOT NULL,
    PRIMARY KEY (smiles, name_type, source)
);
"""


def _connect(db_path: Path | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    return conn


def get_cached(
    smiles: str, name_type: str, source: str, db_path: Path | None = None
) -> tuple[str | None, bool] | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT name, found FROM name_cache WHERE smiles = ? AND name_type = ? AND source = ?",
            (smiles, name_type, source),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    name, found = row
    return (name, bool(found))


def set_cached(
    smiles: str, name_type: str, source: str, name: str | None, db_path: Path | None = None
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO name_cache (smiles, name_type, source, name, found, queried_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(smiles, name_type, source) DO UPDATE SET
                name = excluded.name,
                found = excluded.found,
                queried_at = excluded.queried_at
            """,
            (smiles, name_type, source, name, int(name is not None), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
