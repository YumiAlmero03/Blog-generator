from database.common import get_connection, rows_to_dicts


CHECKLIST_TYPES = ("website", "blog", "page")


def list_checklist_items(checklist_type: str | None = None, active_only: bool = False) -> list[dict]:
    conditions = []
    params = []
    if checklist_type:
        conditions.append("checklist_type = ?")
        params.append(_normalize_type(checklist_type))
    if active_only:
        conditions.append("is_active = 1")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM checklist_items
            {where}
            ORDER BY checklist_type, sort_order, id
            """,
            params,
        ).fetchall()
        return rows_to_dicts(rows)


def checklist_items_by_type(active_only: bool = False) -> dict[str, list[dict]]:
    grouped = {key: [] for key in CHECKLIST_TYPES}
    for item in list_checklist_items(active_only=active_only):
        grouped.setdefault(item.get("checklist_type", "website"), []).append(item)
    return grouped


def save_checklist_item(
    label: str,
    checklist_type: str = "website",
    sort_order: int | str = 0,
    is_active: int | bool | str = 1,
    item_id: int | None = None,
) -> dict:
    cleaned_label = " ".join(str(label or "").split()).strip()
    if not cleaned_label:
        raise ValueError("Checklist item label is required.")
    cleaned_type = _normalize_type(checklist_type)
    cleaned_sort = _to_int(sort_order)
    cleaned_active = _to_flag(is_active)
    with get_connection() as connection:
        if item_id:
            connection.execute(
                """
                UPDATE checklist_items
                SET checklist_type = ?, label = ?, sort_order = ?, is_active = ?
                WHERE id = ?
                """,
                (cleaned_type, cleaned_label, cleaned_sort, cleaned_active, item_id),
            )
            row = connection.execute("SELECT * FROM checklist_items WHERE id = ?", (item_id,)).fetchone()
            return dict(row) if row else {}
        cursor = connection.execute(
            """
            INSERT INTO checklist_items (checklist_type, label, sort_order, is_active)
            VALUES (?, ?, ?, ?)
            """,
            (cleaned_type, cleaned_label, cleaned_sort, cleaned_active),
        )
        row = connection.execute("SELECT * FROM checklist_items WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row) if row else {}


def delete_checklist_item(item_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
        return cursor.rowcount > 0


def reorder_checklist_items(checklist_type: str, item_ids: list[int] | tuple[int, ...]) -> None:
    cleaned_type = _normalize_type(checklist_type)
    cleaned_ids = [int(item_id) for item_id in item_ids if str(item_id).isdigit()]
    if not cleaned_ids:
        raise ValueError("Checklist order is empty.")
    with get_connection() as connection:
        for sort_order, item_id in enumerate(cleaned_ids, start=1):
            connection.execute(
                """
                UPDATE checklist_items
                SET sort_order = ?
                WHERE id = ? AND checklist_type = ?
                """,
                (sort_order, item_id, cleaned_type),
            )


def list_checklist_states(
    checklist_type: str = "website",
    subject_type: str | None = None,
    subject_id: str | int | None = None,
) -> list[dict]:
    conditions = ["checklist_type = ?", "is_checked = 1"]
    params = [_normalize_type(checklist_type)]
    if subject_type:
        conditions.append("subject_type = ?")
        params.append(_normalize_subject_type(subject_type))
    if subject_id is not None:
        conditions.append("subject_id = ?")
        params.append(str(subject_id))
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM checklist_item_states
            WHERE {' AND '.join(conditions)}
            ORDER BY updated_at DESC, id DESC
            """,
            params,
        ).fetchall()
        return rows_to_dicts(rows)


def save_checklist_subject_state(
    checklist_type: str,
    subject_type: str,
    subject_id: str | int,
    checked_item_ids: list[int] | tuple[int, ...] | set[int],
) -> None:
    cleaned_type = _normalize_type(checklist_type)
    cleaned_subject_type = _normalize_subject_type(subject_type)
    cleaned_subject_id = str(subject_id or "").strip()
    cleaned_ids = sorted({int(item_id) for item_id in checked_item_ids if str(item_id).isdigit()})
    if not cleaned_subject_id:
        raise ValueError("Checklist subject is required.")
    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM checklist_item_states
            WHERE checklist_type = ? AND subject_type = ? AND subject_id = ?
            """,
            (cleaned_type, cleaned_subject_type, cleaned_subject_id),
        )
        for item_id in cleaned_ids:
            connection.execute(
                """
                INSERT INTO checklist_item_states (
                    checklist_type, subject_type, subject_id, checklist_item_id, is_checked, updated_at
                )
                VALUES (?, ?, ?, ?, 1, datetime('now'))
                """,
                (cleaned_type, cleaned_subject_type, cleaned_subject_id, item_id),
            )


def seed_default_checklist_items() -> None:
    defaults = {
        "website": [
            "Logo uploaded",
            "Website URL saved",
            "Main keywords saved",
            "Brand or medium rules reviewed",
            "Posting target confirmed",
        ],
        "blog": [
            "Title selected",
            "Meta description selected",
            "Content proofread",
            "Links checked",
            "Tags reviewed",
        ],
        "page": [
            "Title copied",
            "Meta description copied",
            "HTML copied",
            "Formatting checked",
            "WordPress paste reviewed",
        ],
    }
    with get_connection() as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM checklist_items").fetchone()["count"]
        if count:
            return
        for checklist_type, labels in defaults.items():
            for index, label in enumerate(labels, start=1):
                connection.execute(
                    """
                    INSERT INTO checklist_items (checklist_type, label, sort_order, is_active)
                    VALUES (?, ?, ?, 1)
                    """,
                    (checklist_type, label, index),
                )


def _normalize_type(value: str) -> str:
    cleaned = (value or "website").strip().lower()
    return cleaned if cleaned in CHECKLIST_TYPES else "website"


def _normalize_subject_type(value: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in {"brand", "medium"} else "brand"


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_flag(value) -> int:
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"1", "true", "yes", "on"} else 0
    return 1 if value else 0
