import json

from database.common import get_connection, rows_to_dicts


def list_folder_image_optimizer_runs(limit: int = 10) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM folder_image_optimizer_runs
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (max(1, int(limit or 10)),),
        ).fetchall()
        return [_format_run(row) for row in rows_to_dicts(rows)]


def list_folder_image_optimizer_seen_folders(limit: int = 24) -> list[str]:
    seen = []
    seen_keys = set()
    for run in list_folder_image_optimizer_runs(limit=100):
        folders = run.get("seen_folders_list") or [run.get("source_folder", "")]
        for folder in folders:
            cleaned = (folder or "").strip()
            key = cleaned.lower()
            if cleaned and key not in seen_keys:
                seen_keys.add(key)
                seen.append(cleaned)
            if len(seen) >= limit:
                return seen
    return seen


def save_folder_image_optimizer_run(result: dict | None, status: str = "success", message: str = "") -> dict:
    result = result or {}
    seen_folders = result.get("seen_folders") or []
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO folder_image_optimizer_runs (
                mode, source_folder, output_folder, output_format, quality, recursive,
                overwrite_original, total_count, optimized_count, error_count,
                saved_total_label, seen_folders, status, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (result.get("mode") or "").strip(),
                (result.get("source_folder") or "").strip(),
                (result.get("output_folder") or "").strip(),
                (result.get("output_format") or "").strip(),
                int(result.get("quality") or 0),
                1 if result.get("recursive") else 0,
                1 if result.get("overwrite_original") else 0,
                int(result.get("total_count") or 0),
                int(result.get("optimized_count") or 0),
                int(result.get("error_count") or 0),
                (result.get("saved_total_label") or "").strip(),
                json.dumps(seen_folders, ensure_ascii=True),
                (status or "").strip(),
                (message or "").strip(),
            ),
        )
        row = connection.execute("SELECT * FROM folder_image_optimizer_runs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _format_run(dict(row)) if row else {}


def _format_run(row: dict) -> dict:
    try:
        row["seen_folders_list"] = json.loads(row.get("seen_folders") or "[]")
    except json.JSONDecodeError:
        row["seen_folders_list"] = []
    row["recursive"] = bool(row.get("recursive"))
    row["overwrite_original"] = bool(row.get("overwrite_original"))
    return row
