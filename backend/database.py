"""
database.py — SQLite cache layer.
Schema: one table, name is primary key (case-insensitive).
Cache hit → skip API + scraper entirely.
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path("components.db")


def init_db() -> None:
    """Create table if it doesn't exist. Called once on startup."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS components (
                name          TEXT PRIMARY KEY COLLATE NOCASE,
                description   TEXT    NOT NULL DEFAULT '',
                specs         TEXT    NOT NULL DEFAULT '{}',
                datasheet_url TEXT    NOT NULL DEFAULT '',
                cached_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def get_cached(name: str) -> dict | None:
    """Return cached component dict or None if not in DB."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM components WHERE name = ? COLLATE NOCASE",
            (name,)
        ).fetchone()

    if not row:
        return None

    return {
        "name":          row["name"],
        "description":   row["description"],
        "specs":         json.loads(row["specs"]),
        "datasheet_url": row["datasheet_url"],
        "source":        "cache",
    }


def save_component(data: dict) -> None:
    """Insert or replace a component record."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO components
                (name, description, specs, datasheet_url)
            VALUES (?, ?, ?, ?)
        """, (
            data["name"],
            data.get("description", ""),
            json.dumps(data.get("specs", {})),
            data.get("datasheet_url", ""),
        ))
        conn.commit()