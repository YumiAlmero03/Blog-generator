from types import SimpleNamespace

from app.services import reference_link_service, sportsbook_odds_extractor
from prompts.news import build_news_content_prompt, build_news_title_prompt
from prompts.revisions import build_scoped_content_revision_prompt


def test_format_match_odds_data_resolves_teams_splits_and_ordering():
    raw_data = {
        "kind": "match",
        "competition": "Brazil Copa do Brasil",
        "scoreboard": "Gremio FBPA RS\n06 Dec 18:00\nvs\nFinal\nSE Palmeiras SP",
        "markets": [
            {
                "wid": "ExhaustiveMarketCardWrapper-1x2_group-grouped",
                "title": "1X2",
                "order": 0,
                "percentages": [
                    {"side": "home", "value": "49%"},
                    {"side": "draw", "value": "33%"},
                    {"side": "away", "value": "18%"},
                ],
                "tabs": [
                    {
                        "tab": "FT",
                        "buttons": [
                            {"id": "oddsBtn-1|300289194|1x2|h|0", "text": "1 5.00"},
                            {"id": "oddsBtn-1|300289194|1x2|d|0", "text": "X 3.40"},
                            {"id": "oddsBtn-1|300289194|1x2|a|0", "text": "2 1.75"},
                        ],
                    },
                    {
                        "tab": "1H",
                        "buttons": [
                            {"id": "oddsBtn-1|300289194|1x2_1st|h|0", "text": "1 5.80"},
                        ],
                    },
                ],
            },
            {
                "wid": "ExhaustiveMarketCardWrapper-hfcs",
                "title": "HT/FT Correct Score",
                "order": 1,
                "percentages": [],
                "tabs": [
                    {
                        "tab": "",
                        "buttons": [
                            {"id": "oddsBtn-1|300289194|hfcs|0-0&0-0|0", "text": "0-0 & 0-0 8.40"},
                        ],
                    }
                ],
            },
            {
                "wid": "ExhaustiveMarketCardWrapper-ah",
                "title": "Handicap",
                "order": 2,
                "percentages": [
                    {"side": "home", "value": "45%"},
                    {"side": "away", "value": "55%"},
                ],
                "tabs": [
                    {
                        "tab": "",
                        "buttons": [
                            {"id": "oddsBtn-1|300289194|ah|h|0", "text": "+0.5/1 1.84"},
                            {"id": "oddsBtn-1|300289194|ah|a|0", "text": "-0.5/1 1.98"},
                        ],
                    }
                ],
            },
            {
                "wid": "ExhaustiveMarketCardWrapper-ou",
                "title": "Goals: Over/Under",
                "order": 3,
                "percentages": [
                    {"side": "home", "value": "56%"},
                    {"side": "away", "value": "44%"},
                ],
                "tabs": [
                    {
                        "tab": "",
                        "buttons": [
                            {"id": "oddsBtn-1|300289194|ou|ov|2", "text": "O 2.5 2.29"},
                            {"id": "oddsBtn-1|300289194|ou|ud|2", "text": "U 2.5 1.57"},
                        ],
                    }
                ],
            },
            {
                "wid": "ExhaustiveMarketCardWrapper-tw-grouped",
                "title": "Team Wins in Regular Time",
                "order": 4,
                "percentages": [],
                "tabs": [
                    {
                        "tab": "",
                        "buttons": [
                            {"id": "oddsBtn-1|300289194|h-tw|y|0", "text": "4.00"},
                            {"id": "oddsBtn-1|300289194|a-tw|y|0", "text": "1.63"},
                        ],
                    }
                ],
            },
            {
                "wid": "ExhaustiveMarketCardWrapper-dc&ou_group-grouped",
                "title": "Double Chance & Goals: Over/Under",
                "order": 5,
                "percentages": [],
                "tabs": [
                    {
                        "tab": "FT",
                        "buttons": [
                            {"id": "oddsBtn-1|300289194|dc&ou|h-d&ov|0|1.5", "text": "O 1.5 3.30"},
                        ],
                    }
                ],
            },
        ],
    }

    formatted = sportsbook_odds_extractor.format_sportsbook_odds_data(raw_data)

    assert formatted is not None
    assert formatted["structured_odds"] is True
    assert formatted["title"] == "Gremio FBPA RS vs SE Palmeiras SP Odds | Brazil Copa do Brasil"
    text = formatted["text"]
    assert "Competition: Brazil Copa do Brasil - Final" in text
    assert "Match: Gremio FBPA RS vs SE Palmeiras SP (06 Dec 18:00)" in text
    assert "Betting split: Gremio FBPA RS 49%, Draw 33%, SE Palmeiras SP 18%" in text
    assert "[FT] Gremio FBPA RS (1) @ 5.00 | Draw (X) @ 3.40 | SE Palmeiras SP (2) @ 1.75" in text
    assert "[1H] Gremio FBPA RS (1) @ 5.80" in text
    assert "Gremio FBPA RS +0.5/1 @ 1.84 | SE Palmeiras SP -0.5/1 @ 1.98" in text
    assert "Betting split: Over 56%, Under 44%" in text
    assert "O 2.5 @ 2.29 | U 2.5 @ 1.57" in text
    assert "Gremio FBPA RS Yes @ 4.00 | SE Palmeiras SP Yes @ 1.63" in text
    assert "Gremio FBPA RS/Draw & Over (O 1.5) @ 3.30" in text
    # Late dense matrix market is pushed after core and secondary markets.
    assert text.index("## Double Chance & Goals: Over/Under") < text.index("## HT/FT Correct Score")


def test_format_list_odds_data():
    raw_data = {
        "kind": "list",
        "events": [
            {
                "competition": "Brazil Copa do Brasil",
                "kickoff": "06 Dec 18:00",
                "home_team": "Gremio FBPA RS",
                "away_team": "SE Palmeiras SP",
                "buttons": [
                    {"id": "oddsBtn-1|300289194|1x2|h|0", "text": "1 5.00"},
                    {"id": "oddsBtn-1|300289194|1x2|d|0", "text": "X 3.40"},
                    {"id": "oddsBtn-1|300289194|1x2|a|0", "text": "2 1.75"},
                ],
            }
        ],
    }

    formatted = sportsbook_odds_extractor.format_sportsbook_odds_data(raw_data)

    assert formatted is not None
    assert formatted["structured_odds"] is True
    assert "Displayed Sportsbook Odds (Match List)" in formatted["text"]
    assert "Gremio FBPA RS (1) @ 5.00 ; Draw (X) @ 3.40 ; SE Palmeiras SP (2) @ 1.75" in formatted["text"]


def test_extract_sportsbook_odds_ignores_mock_page_without_evaluate():
    assert sportsbook_odds_extractor.extract_sportsbook_odds_from_page(SimpleNamespace(url="https://example.com")) is None


def test_fetch_reference_context_gives_structured_odds_higher_char_budget(monkeypatch):
    long_odds_body = sportsbook_odds_extractor.SPORTSBOOK_ODDS_HEADER + "\n" + ("1X2 market line 1.75 | " * 500)
    monkeypatch.setattr(
        reference_link_service,
        "_fetch_url_text_with_options",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("Needs browser")),
    )
    monkeypatch.setattr(
        reference_link_service,
        "_fetch_url_rendered_text_with_options",
        lambda *args, **kwargs: {
            "title": "Match Odds",
            "text": long_odds_body,
            "structured_odds": True,
        },
    )

    context, fetched = reference_link_service.fetch_reference_context(
        [{"url": "https://2bet52.com/sportEvents/match/300289194"}],
        use_browser=True,
    )

    assert len(fetched[0]["excerpt"]) > reference_link_service.MAX_TEXT_PER_LINK
    assert fetched[0]["structured_odds"] is True
    assert "Match Odds" in context


def test_news_and_revision_prompts_apply_displayed_odds_rules():
    odds_body = sportsbook_odds_extractor.SPORTSBOOK_ODDS_HEADER + "\n## 1X2\n[FT] Home (1) @ 5.00 | Away (2) @ 1.75\n" + ("Extra market data. " * 400)
    title_prompt = build_news_title_prompt(keyword="Gremio vs Palmeiras", reference_context=odds_body)
    content_prompt = build_news_content_prompt(title="Gremio vs Palmeiras Odds", keyword="Gremio vs Palmeiras", reference_context=odds_body)
    revision_prompt = build_scoped_content_revision_prompt(
        title="Gremio vs Palmeiras Odds",
        existing_content="<p>Draft</p>",
        change_request="Add market table",
        reference_context=odds_body + "TRAILING_ODDS_MARKER",
    )

    assert "Displayed odds writing rules:" in title_prompt
    assert "Displayed odds writing rules:" in content_prompt
    assert "lower decimal odds indicate a stronger market favorite" in content_prompt
    assert "strictly accurate to the supplied sportsbook markets above" in revision_prompt
    assert "TRAILING_ODDS_MARKER" in revision_prompt
