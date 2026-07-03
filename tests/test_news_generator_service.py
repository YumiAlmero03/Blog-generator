from app.controllers import news_controller


def test_reference_context_stops_when_all_links_are_unreadable(monkeypatch):
    state = {
        "links": [{"url": "https://www.fifa.com/example"}],
        "reference_fetches": [],
        "error": None,
    }
    progress_messages = []

    monkeypatch.setattr(
        news_controller,
        "fetch_reference_context",
        lambda links: (
            "",
            [
                {
                    "url": "https://www.fifa.com/example",
                    "status": "error",
                    "error": "Could not extract enough readable article text.",
                }
            ],
        ),
    )

    context = news_controller._reference_context_for_state(state, progress_messages.append)

    assert context == ""
    assert state["error"] == "Reference links could not be read, so News Generator stopped instead of writing from unsupported context."
    assert state["reference_fetches"][0]["status"] == "error"
    assert "Generation stopped" in progress_messages[-1]


def test_reference_fetch_summary_counts_failures():
    summary = news_controller._reference_fetch_summary(
        [
            {"status": "fetched"},
            {"status": "error"},
            {"status": "skipped"},
        ]
    )

    assert summary == {"fetched": 1, "failed": 2, "total": 3}
