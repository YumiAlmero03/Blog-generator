from datetime import datetime, timedelta, timezone

from database.common import get_connection
from app import create_app
from database.website_index import delete_website_index_url, delete_website_index_urls_by_domain, list_due_website_index_submission_urls, list_due_website_index_urls, upsert_website_index_urls
from app.controllers.tool_controller import _website_index_dashboard_sort_key


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


def test_upsert_website_index_urls_returns_new_insert_count():
    url = "https://website-index-test.example/insert-count"

    try:
        assert upsert_website_index_urls([url, url]) == 1
        assert upsert_website_index_urls([url]) == 0
    finally:
        with get_connection() as connection:
            connection.execute("DELETE FROM website_index_urls WHERE url = ?", (url,))


def test_upsert_website_index_urls_saves_and_updates_keywords():
    url = "https://website-index-keywords.example/page"
    try:
        assert upsert_website_index_urls([{"url": url, "page_keywords": ["alpha", "beta"]}]) == 1
        assert upsert_website_index_urls([{"url": url, "page_keywords": "gamma, beta"}]) == 0
        with get_connection() as connection:
            row = connection.execute(
                "SELECT page_keywords FROM website_index_urls WHERE url = ?",
                (url,),
            ).fetchone()
        assert row["page_keywords"] == "gamma, beta"
    finally:
        with get_connection() as connection:
            connection.execute("DELETE FROM website_index_urls WHERE url = ?", (url,))


def test_due_website_index_urls_use_30_minute_window():
    fresh_url = "https://website-index-test.example/fresh-30-minute"
    due_url = "https://website-index-test.example/due-30-minute"
    fresh_checked_at = (datetime.now(timezone.utc) - timedelta(minutes=29)).isoformat(timespec="seconds")
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


def test_due_website_index_submission_urls_only_include_not_indexed():
    not_indexed_url = "https://website-index-submit-test.example/not-indexed"
    fresh_not_indexed_url = "https://website-index-submit-test.example/fresh-not-indexed"
    unchecked_url = "https://website-index-submit-test.example/unchecked"
    error_url = "https://website-index-submit-test.example/error"
    old_checked_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec="seconds")
    fresh_checked_at = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat(timespec="seconds")

    try:
        upsert_website_index_urls([not_indexed_url, fresh_not_indexed_url, unchecked_url, error_url])
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'not-indexed'
                WHERE url = ?
                """,
                (old_checked_at, not_indexed_url),
            )
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'not-indexed'
                WHERE url = ?
                """,
                (fresh_checked_at, fresh_not_indexed_url),
            )
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = '', google_status = ''
                WHERE url = ?
                """,
                (unchecked_url,),
            )
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'error'
                WHERE url = ?
                """,
                (old_checked_at, error_url),
            )

        test_urls = {not_indexed_url, fresh_not_indexed_url, unchecked_url, error_url}
        due_submit_urls = {
            item["url"]
            for item in list_due_website_index_submission_urls()
            if item["url"] in test_urls
        }

        assert due_submit_urls == {not_indexed_url}
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?, ?, ?)",
                (not_indexed_url, fresh_not_indexed_url, unchecked_url, error_url),
            )


def test_due_website_index_urls_prioritize_never_inspected_urls():
    old_checked_url = "https://website-index-test.example/old-checked"
    never_checked_url = "https://website-index-test.example/never-checked"
    older_checked_url = "https://website-index-test.example/older-checked"
    old_checked_at = (datetime.now(timezone.utc) - timedelta(minutes=32)).isoformat(timespec="seconds")
    older_checked_at = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat(timespec="seconds")

    try:
        upsert_website_index_urls([old_checked_url, never_checked_url, older_checked_url])
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'not-indexed'
                WHERE url = ?
                """,
                (old_checked_at, old_checked_url),
            )
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = '', google_status = ''
                WHERE url = ?
                """,
                (never_checked_url,),
            )
            connection.execute(
                """
                UPDATE website_index_urls
                SET last_checked_at = ?, google_status = 'not-indexed'
                WHERE url = ?
                """,
                (older_checked_at, older_checked_url),
            )

        ordered_urls = [
            item["url"]
            for item in list_due_website_index_urls()
            if item["url"] in {old_checked_url, never_checked_url, older_checked_url}
        ]

        assert ordered_urls == [never_checked_url, older_checked_url, old_checked_url]
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?, ?)",
                (old_checked_url, never_checked_url, older_checked_url),
            )


def test_delete_website_index_urls_by_domain_only_removes_matching_domain():
    delete_urls = [
        "https://delete-domain-test.example/",
        "https://delete-domain-test.example/page",
    ]
    keep_url = "https://keep-domain-test.example/page"

    try:
        upsert_website_index_urls([*delete_urls, keep_url])

        deleted_count = delete_website_index_urls_by_domain("delete-domain-test.example")

        assert deleted_count == 2
        with get_connection() as connection:
            remaining = {
                row["url"]
                for row in connection.execute(
                    "SELECT url FROM website_index_urls WHERE url IN (?, ?, ?)",
                    (*delete_urls, keep_url),
                ).fetchall()
            }
        assert remaining == {keep_url}
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?, ?)",
                (*delete_urls, keep_url),
            )


def test_delete_website_index_url_removes_only_exact_url():
    delete_url = "https://delete-url-test.example/page"
    keep_url = "https://delete-url-test.example/other-page"

    try:
        upsert_website_index_urls([delete_url, keep_url])

        assert delete_website_index_url(delete_url) == 1

        with get_connection() as connection:
            remaining = {
                row["url"]
                for row in connection.execute(
                    "SELECT url FROM website_index_urls WHERE url IN (?, ?)",
                    (delete_url, keep_url),
                ).fetchall()
            }
        assert remaining == {keep_url}
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?)",
                (delete_url, keep_url),
            )


def test_website_index_dashboard_can_remove_specific_url():
    delete_url = "https://dashboard-delete-url-test.example/page"
    keep_url = "https://dashboard-delete-url-test.example/other-page"

    try:
        upsert_website_index_urls([delete_url, keep_url])
        app = create_app()
        app.testing = True

        response = app.test_client().post(
            "/website-index-dashboard",
            data={"action": "delete_url", "url": delete_url},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Removed that URL from Website Index." in html
        assert "Download CSV" in html
        with get_connection() as connection:
            remaining = {
                row["url"]
                for row in connection.execute(
                    "SELECT url FROM website_index_urls WHERE url IN (?, ?)",
                    (delete_url, keep_url),
                ).fetchall()
            }
        assert remaining == {keep_url}
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?)",
                (delete_url, keep_url),
            )


def test_website_index_dashboard_sort_prioritizes_due_urls():
    rows = [
        {"id": 1, "is_due": False, "last_checked_at": ""},
        {"id": 2, "is_due": True, "last_checked_at": "2026-06-26T10:20:00+00:00"},
        {"id": 3, "is_due": True, "last_checked_at": ""},
        {"id": 4, "is_due": False, "last_checked_at": "2026-06-26T10:10:00+00:00"},
    ]

    ordered_ids = [item["id"] for item in sorted(rows, key=_website_index_dashboard_sort_key)]

    assert ordered_ids == [3, 2, 1, 4]
