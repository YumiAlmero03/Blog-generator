from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from database.common import get_connection, row_to_dict


def upsert_website_index_urls(urls: list) -> int:
    cleaned_items = []
    seen = set()
    for item in urls:
        cleaned = (item.get("url") if isinstance(item, dict) else item or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        keywords = ""
        if isinstance(item, dict):
            keywords = _clean_page_keywords(item.get("page_keywords", ""))
        cleaned_items.append({"url": cleaned, "page_keywords": keywords})

    inserted_count = 0
    with get_connection() as connection:
        for item in cleaned_items:
            existing = connection.execute(
                "SELECT id FROM website_index_urls WHERE url = ?",
                (item["url"],),
            ).fetchone()
            if existing:
                if item["page_keywords"]:
                    connection.execute(
                        "UPDATE website_index_urls SET page_keywords = ? WHERE url = ?",
                        (item["page_keywords"], item["url"]),
                    )
                continue
            connection.execute(
                """
                INSERT INTO website_index_urls (url, page_keywords)
                VALUES (?, ?)
                """,
                (item["url"], item["page_keywords"]),
            )
            inserted_count += 1
    return inserted_count


def _clean_page_keywords(value) -> str:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    keywords = []
    seen = set()
    for item in raw_items:
        cleaned = " ".join(str(item or "").split()).strip()
        normalized = cleaned.casefold()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            keywords.append(cleaned)
    return ", ".join(keywords[:20])


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


def list_website_index_site_roots() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT url
            FROM website_index_urls
            ORDER BY id
            """
        ).fetchall()

    roots_by_domain = {}
    for row in rows:
        parsed = urlparse(row["url"] or "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        domain = parsed.netloc.lower()
        roots_by_domain.setdefault(
            domain,
            {
                "domain": domain,
                "base_url": f"{parsed.scheme}://{parsed.netloc}",
            },
        )
    return sorted(roots_by_domain.values(), key=lambda item: item["domain"])


def delete_website_index_urls_by_domain(domain: str) -> int:
    cleaned_domain = (domain or "").strip().lower()
    if not cleaned_domain:
        return 0

    with get_connection() as connection:
        rows = connection.execute("SELECT id, url FROM website_index_urls").fetchall()
        matching_ids = [
            row["id"]
            for row in rows
            if urlparse(row["url"] or "").netloc.lower() == cleaned_domain
        ]
        if not matching_ids:
            return 0

        placeholders = ",".join("?" for _item in matching_ids)
        connection.execute(
            f"DELETE FROM website_index_urls WHERE id IN ({placeholders})",
            tuple(matching_ids),
        )
        return len(matching_ids)


def delete_website_index_url(url: str) -> int:
    cleaned_url = (url or "").strip()
    if not cleaned_url:
        return 0

    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM website_index_urls WHERE url = ?",
            (cleaned_url,),
        )
        return max(0, cursor.rowcount)


def delete_website_index_urls(urls: list[str]) -> int:
    cleaned_urls = []
    seen = set()
    for url in urls or []:
        cleaned = (url or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            cleaned_urls.append(cleaned)
    if not cleaned_urls:
        return 0

    placeholders = ",".join("?" for _url in cleaned_urls)
    with get_connection() as connection:
        cursor = connection.execute(
            f"DELETE FROM website_index_urls WHERE url IN ({placeholders})",
            tuple(cleaned_urls),
        )
        return max(0, cursor.rowcount)


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
            ORDER BY
                CASE WHEN TRIM(COALESCE(last_checked_at, '')) = '' THEN 0 ELSE 1 END,
                last_checked_at,
                id
            """,
            (cutoff_text,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def list_due_website_index_submission_urls(hours: float = 24) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(0.1, hours))
    cutoff_text = cutoff.isoformat(timespec="seconds")
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM website_index_urls
            WHERE google_status = 'not-indexed'
              AND (
                TRIM(COALESCE(last_checked_at, '')) = ''
                OR last_checked_at <= ?
              )
            ORDER BY
                CASE WHEN TRIM(COALESCE(last_checked_at, '')) = '' THEN 0 ELSE 1 END,
                last_checked_at,
                id
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
