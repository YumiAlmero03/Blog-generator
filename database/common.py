import sqlite3
from pathlib import Path
from typing import Optional


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"
LEGACY_DB_PATH = DATA_DIR / "app_db.json"


def normalize_brand_name(brand: str) -> str:
    return " ".join((brand or "").strip().lower().split())


def normalize_keyword(keyword: str) -> str:
    return " ".join((keyword or "").strip().lower().split())


def split_keywords(*keyword_groups: str) -> list[str]:
    items = []
    for group in keyword_groups:
        if not group:
            continue
        for part in group.split(","):
            cleaned = part.strip()
            if cleaned:
                items.append(cleaned)

    unique = []
    seen = set()
    for item in items:
        normalized = normalize_keyword(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(item)
    return unique


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]
