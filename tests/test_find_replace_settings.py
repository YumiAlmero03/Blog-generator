from uuid import uuid4

from app import create_app
from database import delete_find_replace_rule, get_find_replace_rule, list_find_replace_rules


def test_find_replace_settings_page_saves_and_lists_rule():
    app = create_app()
    app.testing = True
    client = app.test_client()
    unique = uuid4().hex
    find_text = f"old phrase {unique}"
    replace_text = f"new phrase {unique}"
    saved_rule_id = None

    try:
        response = client.post(
            "/find-replace-settings",
            data={
                "action": "save",
                "find_text": find_text,
                "replace_text": replace_text,
                "is_active": "1",
                "notes": "route smoke test",
            },
        )

        assert response.status_code == 200
        assert b"Find and replace rule saved." in response.data
        assert find_text.encode() in response.data
        assert replace_text.encode() in response.data

        saved_rule = next(
            rule for rule in list_find_replace_rules() if rule["find_text"] == find_text
        )
        saved_rule_id = saved_rule["id"]
        assert saved_rule["replace_text"] == replace_text
        assert saved_rule["is_active"] == 1
    finally:
        if saved_rule_id:
            delete_find_replace_rule(saved_rule_id)


def test_find_replace_settings_page_edits_rule():
    app = create_app()
    app.testing = True
    client = app.test_client()
    unique = uuid4().hex
    original = f"original {unique}"
    updated = f"updated {unique}"
    saved_rule_id = None

    try:
        create_response = client.post(
            "/find-replace-settings",
            data={
                "action": "save",
                "find_text": original,
                "replace_text": "replacement",
                "is_active": "1",
            },
        )
        assert create_response.status_code == 200
        saved_rule_id = next(
            rule["id"] for rule in list_find_replace_rules() if rule["find_text"] == original
        )

        edit_response = client.post(
            "/find-replace-settings",
            data={
                "action": "save",
                "rule_id": str(saved_rule_id),
                "find_text": updated,
                "replace_text": "",
                "notes": "updated note",
            },
        )

        assert edit_response.status_code == 200
        saved_rule = get_find_replace_rule(saved_rule_id)
        assert saved_rule["find_text"] == updated
        assert saved_rule["replace_text"] == ""
        assert saved_rule["is_active"] == 0
    finally:
        if saved_rule_id:
            delete_find_replace_rule(saved_rule_id)
