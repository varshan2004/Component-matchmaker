"""
database.py — SQLite cache layer.
Schema: one table, name is primary key (case-insensitive).

Fix: never cache empty results — if description and all specs
are empty, skip saving so next search retries live sources.
"""

import sqlite3
import json
import time
from pathlib import Path

DB_PATH = Path("components.db")


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS components (
                name          TEXT PRIMARY KEY COLLATE NOCASE,
                description   TEXT    NOT NULL DEFAULT '',
                specs         TEXT    NOT NULL DEFAULT '{}',
                datasheet_url TEXT    NOT NULL DEFAULT '',
                pricing       TEXT    NOT NULL DEFAULT '{}',
                cached_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add pricing column if upgrading from old schema
        try:
            conn.execute("ALTER TABLE components ADD COLUMN pricing TEXT NOT NULL DEFAULT '{}'")
        except Exception:
            pass  # already exists
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

    specs = json.loads(row["specs"])

    # Reject stale empty cache entries — force re-fetch
    if not row["description"] and not any(specs.values()):
        print(f"[cache] '{name}' cached empty — ignoring, will re-fetch")
        return None

    try:
        pricing = json.loads(row["pricing"])
    except Exception:
        pricing = {}

    return {
        "name":          row["name"],
        "description":   row["description"],
        "specs":         specs,
        "datasheet_url": row["datasheet_url"],
        "pricing":       pricing,
        "source":        "cache",
    }


def save_component(data: dict) -> None:
    """
    Insert or replace a component record.
    Skips save if both description and specs are empty
    — prevents caching failed lookups.
    """
    description = data.get("description", "").strip()
    specs       = data.get("specs", {})
    has_specs   = any(v for v in specs.values() if v)

    if not description and not has_specs:
        print(f"[cache] skipping save for '{data.get('name')}' — empty result")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO components
                (name, description, specs, datasheet_url, pricing)
            VALUES (?, ?, ?, ?, ?)
        """, (
            data["name"],
            description,
            json.dumps(specs),
            data.get("datasheet_url", ""),
            json.dumps(data.get("pricing", {})),
        ))
        conn.commit()