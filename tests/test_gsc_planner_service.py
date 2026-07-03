import json

from app import create_app
from app.services import gsc_planner_service
from app.services.gsc_planner_service import answer_gsc_planner_chat, fetch_gsc_performance_data, generate_gsc_seo_report, normalize_search_console_property


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.response)


def test_generate_gsc_seo_report_normalizes_sections():
    provider = FakeProvider(
        {
            "executive_summary": "Improve CTR and expand content for visible queries.",
            "gsc_diagnosis": [{"finding": "Low CTR", "evidence": "High impressions, low clicks", "meaning": "Snippet is weak"}],
            "opportunities": [{"opportunity": "Rewrite title", "reason": "CTR gap", "recommended_action": "Test clearer intent"}],
            "recommendations": [{"priority": "High", "area": "Metadata", "recommendation": "Rewrite title", "impact": "More clicks", "effort": "Low"}],
            "content_plan": [{"section_or_asset": "FAQ", "target_query": "brand pricing", "notes": "Answer pricing intent"}],
            "technical_checks": [{"check": "Indexing", "why": "Confirm eligibility", "how": "Inspect URL"}],
            "monitoring_plan": [{"metric": "CTR", "target": "Increase", "timing": "After 14 days"}],
            "next_steps": [{"step": "Rewrite metadata", "priority": "High", "effort": "Low"}],
        }
    )

    result = generate_gsc_seo_report(
        provider,
        brand="Example Brand",
        target_url="https://example.com/page",
        gsc_notes="Clicks: 10\nImpressions: 1000\nCTR: 1%",
        brand_context="Known brand: Example Brand",
    )

    assert result["executive_summary"] == "Improve CTR and expand content for visible queries."
    assert result["recommendations"][0]["area"] == "Metadata"
    assert "Clicks: 10" in provider.prompts[0]
    assert "Known brand: Example Brand" in provider.prompts[0]


def test_answer_gsc_planner_chat_returns_answer():
    provider = FakeProvider({"answer": "Start with metadata because the report shows a CTR gap."})

    answer = answer_gsc_planner_chat(
        provider,
        question="What should I do first?",
        report={"executive_summary": "CTR gap"},
        brand="Example Brand",
        target_url="https://example.com/page",
    )

    assert "metadata" in answer
    assert "What should I do first?" in provider.prompts[0]


def test_generate_gsc_seo_report_allows_empty_notes():
    provider = FakeProvider(
        {
            "executive_summary": "No readable GSC metrics were provided, so this report focuses on planning.",
            "gsc_diagnosis": [{"finding": "Metrics unavailable", "evidence": "No notes or API data", "meaning": "Recommendations need validation"}],
        }
    )

    result = generate_gsc_seo_report(
        provider,
        brand="Example Brand",
        target_url="https://example.com/page",
        gsc_notes="",
        brand_context="Known brand: Example Brand",
    )

    assert "planning" in result["executive_summary"]
    assert "No manually pasted notes" in provider.prompts[0]
    assert "Do not invent exact metrics" in provider.prompts[0]


class FakeResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def test_generate_gsc_seo_report_wraps_api_summary():
    provider = FakeProvider(
        {
            "executive_summary": "Search Console API shows CTR opportunity.",
            "gsc_diagnosis": [{"finding": "Low CTR", "evidence": "CTR 0.8%", "meaning": "Snippet may be weak"}],
        }
    )

    generate_gsc_seo_report(
        provider,
        brand="Example Brand",
        target_url="https://example.com/page",
        gsc_notes="",
        gsc_api_summary="Totals from returned rows: clicks=100, impressions=12000, ctr=0.83%, weighted_average_position=9.4",
    )

    prompt = provider.prompts[0]
    assert "<gsc_api_data>" in prompt
    assert "clicks=100" in prompt
    assert "weighted_average_position=9.4" in prompt
    assert "</gsc_api_data>" in prompt


def test_fetch_gsc_performance_data_builds_summary(monkeypatch):
    captured = {}
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data.decode("utf-8")))
        captured["url"] = request.full_url
        captured["payload"] = requests[0]
        if requests[-1]["dimensions"] == ["date"]:
            return FakeResponse(
                {
                    "rows": [
                        {"keys": ["2026-06-01"], "clicks": 20, "impressions": 2000, "ctr": 0.01, "position": 7.5},
                        {"keys": ["2026-06-02"], "clicks": 10, "impressions": 1000, "ctr": 0.01, "position": 8.5},
                    ]
                }
            )
        return FakeResponse(
            {
                "rows": [
                    {
                        "keys": ["best casino guide", "https://example.com/page"],
                        "clicks": 10,
                        "impressions": 1000,
                        "ctr": 0.01,
                        "position": 8.5,
                    }
                ]
            }
        )

    monkeypatch.setattr(gsc_planner_service, "urlopen", fake_urlopen)

    result = fetch_gsc_performance_data(
        target_url="https://example.com/page",
        start_date="2026-06-01",
        end_date="2026-06-28",
        access_token="token",
        row_limit=10,
    )

    assert "sites/https%3A%2F%2Fexample.com%2F/searchAnalytics/query" in captured["url"]
    assert captured["payload"]["dimensions"] == ["query", "page"]
    assert requests[1]["dimensions"] == ["date"]
    assert captured["payload"]["dimensionFilterGroups"][0]["filters"][0]["expression"] == "https://example.com/page"
    assert result.rows[0]["query"] == "best casino guide"
    assert result.daily_rows[0]["date"] == "2026-06-01"
    assert result.daily_rows[1]["clicks"] == 10
    assert "clicks=10" in result.summary
    assert "Daily trend rows:" in result.summary
    assert "best casino guide" in result.summary


def test_fetch_gsc_performance_data_accepts_domain_property(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse({"rows": []})

    monkeypatch.setattr(gsc_planner_service, "urlopen", fake_urlopen)

    result = fetch_gsc_performance_data(
        target_url="https://www.example.com/page",
        site_url="sc-domain:example.com",
        start_date="2026-06-01",
        end_date="2026-06-28",
        access_token="token",
    )

    assert "sites/sc-domain%3Aexample.com/searchAnalytics/query" in captured["url"]
    assert result.site_url == "sc-domain:example.com"


def test_normalize_search_console_property():
    assert normalize_search_console_property("sc-domain:Example.com/") == "sc-domain:example.com"
    assert normalize_search_console_property("https://example.com") == "https://example.com/"
    assert normalize_search_console_property("example.com") == ""


def test_gsc_planner_page_renders():
    app = create_app()
    app.testing = True
    response = app.test_client().get("/gsc-planner")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "GSC Planner" in html
    assert "Start Date" in html
    assert "End Date" in html
    assert "Search Console Property" in html
    assert "sc-domain:example.com" in html
    assert "Search Console API" in html
    assert "brandWebsites" in html
    assert "data-background-submit" in html
