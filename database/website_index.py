from datetime import datetime, timedelta, timezone

from database.common import get_connection, row_to_dict


def upsert_website_index_urls(urls: list[str]) -> int:
    cleaned_urls = []
    seen = set()
    for url in urls:
        cleaned = (url or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        cleaned_urls.append(cleaned)

    with get_connection() as connection:
        for url in cleaned_urls:
            connection.execute(
                """
                INSERT INTO website_index_urls (url)
                VALUES (?)
                ON CONFLICT(url) DO NOTHING
                """,
                (url,),
            )
    return len(cleaned_urls)


def list_website_index_urls() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM website_index_urls
            ORDER BY id DESC
            """
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def website_index_stats() -> dict:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                SUM(CASE WHEN google_status = 'indexed' THEN 1 ELSE 0 END) AS indexed_count,
                SUM(CASE WHEN google_status = 'not-indexed' THEN 1 ELSE 0 END) AS not_indexed_count,
                SUM(CASE WHEN google_status = 'error' THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN TRIM(COALESCE(last_checked_at, '')) = '' THEN 1 ELSE 0 END) AS unchecked_count,
                SUM(CASE WHEN bing_status = 'manual' THEN 1 ELSE 0 END) AS bing_manual_count,
                SUM(CASE WHEN yahoo_status = 'manual' THEN 1 ELSE 0 END) AS yahoo_manual_count
            FROM website_index_urls
            """
        ).fetchone()
    stats = row_to_dict(row) or {}
    return {
        "total_count": stats.get("total_count") or 0,
        "indexed_count": stats.get("indexed_count") or 0,
        "not_indexed_count": stats.get("not_indexed_count") or 0,
        "error_count": stats.get("error_count") or 0,
        "unchecked_count": stats.get("unchecked_count") or 0,
        "bing_manual_count": stats.get("bing_manual_count") or 0,
        "yahoo_manual_count": stats.get("yahoo_manual_count") or 0,
    }


def list_due_website_index_urls(hours: float = 0.5) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(0.1, hours))
    cutoff_text = cutoff.isoformat(timespec="seconds")
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM website_index_urls
            WHERE COALESCE(google_status, '') <> 'indexed'
              AND (
                TRIM(COALESCE(last_checked_at, '')) = ''
                OR last_checked_at <= ?
              )
            ORDER BY id
            """,
            (cutoff_text,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def update_website_index_google_result(item) -> None:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE website_index_urls
            SET last_checked_at = ?,
                check_status = ?,
                google_status = ?,
                google_verdict = ?,
                google_coverage_state = ?,
                google_robots_txt_state = ?,
                google_indexing_state = ?,
                google_last_crawl_time = ?,
                last_error = ?
            WHERE url = ?
            """,
            (
                checked_at,
                "done" if item.status != "error" else "error",
                item.status,
                item.verdict,
                item.coverage_state,
                item.robots_txt_state,
                item.indexing_state,
                item.last_crawl_time,
                item.detail if item.status == "error" else "",
                item.url,
            ),
        )


def mark_website_index_urls_checking(urls: list[str]) -> None:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection() as connection:
        for url in urls:
            connection.execute(
                """
                UPDATE website_index_urls
                SET check_status = 'checking',
                    last_checked_at = ?
                WHERE url = ?
                """,
                (checked_at, url),
            )


def update_website_index_bing_yahoo_weekly_result(urls: list[str]) -> None:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bing_detail = "Bing index status is not checked by a public Google-style URL Inspection API here. Use Bing Webmaster Tools or IndexNow Insights for verified Bing reporting."
    yahoo_detail = "Yahoo does not provide a separate public URL Inspection API here. Yahoo search reporting should be checked through its available webmaster/search partner tools."
    with get_connection() as connection:
        for url in urls:
            connection.execute(
                """
                UPDATE website_index_urls
                SET check_status = 'manual',
                    bing_status = 'manual',
                    bing_last_checked_at = ?,
                    bing_detail = ?,
                    yahoo_status = 'manual',
                    yahoo_last_checked_at = ?,
                    yahoo_detail = ?
                WHERE url = ?
                """,
                (checked_at, bing_detail, checked_at, yahoo_detail, url),
            )
