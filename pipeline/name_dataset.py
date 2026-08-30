from __future__ import annotations
import sqlite3
from pathlib import Path

import pystow


def dataset_path() -> Path:
    return Path(pystow.join("chem4all", "naming")) / "names.sqlite"


def is_dataset_ready() -> bool:
    return dataset_path().exists()


def lookup(inchikey: str, db_path: Path | None = None) -> tuple[str | None, str | None]:
    """Returns (iupac_name, trivial_name); both None if inchikey isn't in the dataset.
    Raises sqlite3.Error if the dataset file is missing or unreadable. Opened read-only
    so a missing file raises immediately instead of sqlite3 silently creating an empty
    database at that path."""
    path = db_path or dataset_path()
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT iupac_name, trivial_name FROM names WHERE inchikey = ?",
            (inchikey,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return (None, None)
    return (row[0], row[1])
