from datetime import datetime, timedelta, timezone

from database.common import get_connection
from database.website_index import list_due_website_index_urls, upsert_website_index_urls


def test_due_website_index_urls_skip_google_indexed_urls():
    indexed_url = "https://website-index-test.example/indexed"
    pending_url = "https://website-index-test.example/pending"
    old_checked_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")

    try:
        upsert_website_index_urls([indexed_url, pending_url])
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'indexed'
                WHERE url = ?
                """,
                (old_checked_at, indexed_url),
            )
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'not-indexed'
                WHERE url = ?
                """,
                (old_checked_at, pending_url),
            )

        due_urls = {item["url"] for item in list_due_website_index_urls()}

        assert indexed_url not in due_urls
        assert pending_url in due_urls
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?)",
                (indexed_url, pending_url),
            )


def test_due_website_index_urls_use_30_minute_window():
    fresh_url = "https://website-index-test.example/fresh-30-minute"
    due_url = "https://website-index-test.example/due-30-minute"
    fresh_checked_at = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(timespec="seconds")
    due_checked_at = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat(timespec="seconds")

    try:
        upsert_website_index_urls([fresh_url, due_url])
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'not-indexed'
                WHERE url = ?
                """,
                (fresh_checked_at, fresh_url),
            )
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'not-indexed'
                WHERE url = ?
                """,
                (due_checked_at, due_url),
            )

        due_urls = {item["url"] for item in list_due_website_index_urls()}

        assert fresh_url not in due_urls
        assert due_url in due_urls
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?)",
                (fresh_url, due_url),
            )
