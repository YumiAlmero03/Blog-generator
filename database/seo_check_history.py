import json

from database.common import get_connection, rows_to_dicts


HISTORY_LIST_LIMIT = 12


def record_seo_check_history(result: dict, checker_version: str = "v1") -> int:
    summary = result.get("summary", {}) or {}
    with get_connection() as connection:
        return connection.execute(
            """
            INSERT INTO seo_check_history (
                checker_version,
                source_url,
                base_url,
                page_limit,
                average_score,
                average_grade,
                checked_count,
                error_count,
                issue_count,
                not_found_link_count,
                redirect_link_count,
                broken_link_count,
                unreachable_link_count,
                internal_link_count,
                schema_count,
                result_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checker_version,
                result.get("source_url", ""),
                result.get("base_url", ""),
                int(result.get("limit", 0) or 0),
                int(summary.get("average_score", 0) or 0),
                summary.get("average_grade", ""),
                int(summary.get("checked_count", 0) or 0),
                int(summary.get("error_count", 0) or 0),
                int(summary.get("issue_count", 0) or 0),
                int(summary.get("not_found_link_count", 0) or 0),
                int(summary.get("redirect_link_count", 0) or 0),
                int(summary.get("broken_link_count", 0) or 0),
                int(summary.get("unreachable_link_count", 0) or 0),
                int(summary.get("internal_link_count", 0) or 0),
                int(summary.get("schema_count", 0) or 0),
                json.dumps(result),
            ),
        ).lastrowid


def list_seo_check_history(limit: int = HISTORY_LIST_LIMIT, base_url: str = "", checker_version: str = "") -> list[dict]:
    clauses = []
    params = []
    if base_url:
        clauses.append("base_url = ?")
        params.append(base_url)
    if checker_version:
        clauses.append("checker_version = ?")
        params.append(checker_version)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, int(limit or HISTORY_LIST_LIMIT)))
    with get_connection() as connection:
        return rows_to_dicts(
            connection.execute(
                f"""
                SELECT
                    id,
                    created_at,
                    checker_version,
                    source_url,
                    base_url,
                    page_limit,
                    average_score,
                    average_grade,
                    checked_count,
                    error_count,
                    issue_count,
                    not_found_link_count,
                    redirect_link_count,
                    broken_link_count,
                    unreachable_link_count,
                    internal_link_count,
                    schema_count
                FROM seo_check_history
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        )


def get_previous_seo_check_history(base_url: str, current_id: int, checker_version: str = "") -> dict | None:
    if not base_url:
        return None

    clauses = ["base_url = ?", "id < ?"]
    params = [base_url, int(current_id or 0)]
    if checker_version:
        clauses.append("checker_version = ?")
        params.append(checker_version)

    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT
                id,
                created_at,
                checker_version,
                source_url,
                base_url,
                page_limit,
                average_score,
                average_grade,
                checked_count,
                error_count,
                issue_count,
                not_found_link_count,
                redirect_link_count,
                broken_link_count,
                unreachable_link_count,
                internal_link_count,
                schema_count
            FROM seo_check_history
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    return dict(row) if row else None


def get_seo_check_history_result(history_id: int, checker_version: str = "") -> dict | None:
    clauses = ["id = ?"]
    params = [int(history_id or 0)]
    if checker_version:
        clauses.append("checker_version = ?")
        params.append(checker_version)

    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT id, created_at, checker_version, source_url, base_url, page_limit, result_json
            FROM seo_check_history
            WHERE {' AND '.join(clauses)}
            LIMIT 1
            """,
            params,
        ).fetchone()
    if not row:
        return None

    record = dict(row)
    try:
        result = json.loads(record.pop("result_json") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(result, dict) or not result:
        return None
    record["result"] = result
    return record
