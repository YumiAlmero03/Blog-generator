import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from logger import logger
from app.services.indexnow_service import GOOGLE_WEBMASTERS_READONLY_SCOPE, google_access_token_from_service_account_json, search_console_property_for_url
from prompts.shared import build_language_instruction
from utils import extract_json_string
from word_bank import build_banned_words_prompt_section


GOOGLE_SEARCH_ANALYTICS_ENDPOINT = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site_url}/searchAnalytics/query"


@dataclass
class GscPerformanceResult:
    site_url: str
    start_date: str
    end_date: str
    row_limit: int
    target_url: str
    rows: list[dict]
    daily_rows: list[dict]
    summary: str


def generate_gsc_seo_report(
    provider,
    brand: str,
    target_url: str,
    gsc_notes: str,
    brand_context: str = "",
    gsc_api_summary: str = "",
    backlink_summary: str = "",
    language: str = "English",
    progress_callback=None,
) -> dict:
    cleaned_notes = _clean_multiline(gsc_notes)
    prompt = _build_report_prompt(
        brand=brand,
        target_url=target_url,
        gsc_notes=cleaned_notes,
        brand_context=brand_context,
        gsc_api_summary=_clean_multiline(gsc_api_summary),
        backlink_summary=_clean_multiline(backlink_summary),
        language=language,
    )
    _publish_progress(progress_callback, prompt, kind="prompt")
    raw = provider.generate_json(prompt)
    try:
        data = json.loads(extract_json_string(raw))
    except Exception as exc:
        logger.exception("gsc planner report failed. Raw response: %s", raw)
        raise ValueError("Could not parse the GSC SEO report output.") from exc
    return _normalize_report(data)


def answer_gsc_planner_chat(
    provider,
    question: str,
    report: dict,
    brand: str,
    target_url: str,
    gsc_notes: str = "",
    brand_context: str = "",
    language: str = "English",
    chat_history: list[dict] | None = None,
    progress_callback=None,
) -> str:
    cleaned_question = _clean_multiline(question)
    if not cleaned_question:
        raise ValueError("Enter a question for the SEO assistant.")

    prompt = f"""
You are an SEO planning assistant helping execute a Google Search Console action plan.

Brand: {_clean_text(brand)}
Target URL: {_clean_text(target_url)}
{build_language_instruction(language)}

Brand context:
{brand_context or "No saved brand context."}

Original GSC notes:
{_clean_multiline(gsc_notes) or "No notes provided."}

SEO report JSON:
{json.dumps(report or {}, ensure_ascii=True)}

Recent chat:
{json.dumps(chat_history or [], ensure_ascii=True)}

User question:
{cleaned_question}

Rules:
- Give practical next steps, not generic SEO theory.
- Refer to the report priorities when useful.
- Include concrete content, internal-link, metadata, or technical checks when relevant.
- Keep the answer concise but complete.
- Write in {language}.
- Return valid JSON only.
- Start with "{{" and end with "}}".

Return JSON only:
{{
  "answer": "Helpful next-step answer"
}}
"""
    _publish_progress(progress_callback, prompt, kind="prompt")
    raw = provider.generate_json(prompt)
    try:
        data = json.loads(extract_json_string(raw))
    except Exception as exc:
        logger.exception("gsc planner chat failed. Raw response: %s", raw)
        raise ValueError("Could not parse the GSC planner chat answer.") from exc
    return _clean_multiline(data.get("answer", "")) or "I could not generate a useful answer."


def _build_report_prompt(
    brand: str,
    target_url: str,
    gsc_notes: str,
    brand_context: str,
    gsc_api_summary: str,
    backlink_summary: str,
    language: str,
) -> str:
    return f"""
You are a senior SEO strategist. Create a complete SEO report from Google Search Console evidence.

Brand: {_clean_text(brand)}
Target URL / GSC reference link: {_clean_text(target_url)}
{build_language_instruction(language)}
{build_banned_words_prompt_section()}

Saved brand context:
{brand_context or "No saved brand context."}

Manual GSC notes and context:
{gsc_notes or "No manually pasted notes."}

Search Console API performance data:
<gsc_api_data>
{gsc_api_summary or "No Search Console API data was fetched."}
</gsc_api_data>

Saved backlink / medium snapshot:
<backlink_data>
{backlink_summary or "No saved backlink data was available."}
</backlink_data>

Report requirements:
- Diagnose likely SEO issues from the GSC data: clicks, impressions, CTR, position, queries, pages, country/device/date context when provided.
- Prefer Search Console API data over manual notes when API data is available.
- Consider backlink count and high-authority/low-authority saved backlinks as supporting evidence only. Explain whether backlinks may affect SEO, but do not claim causation without Search Console or backlink-change evidence.
- If no readable GSC metrics are provided, clearly state that limitation and create a practical SEO planning report from the brand context and URL only.
- Separate quick wins from deeper content/technical work.
- Recommend title/meta description changes when CTR looks weak.
- Recommend content sections, query targeting, internal links, schema, indexing, and cannibalization checks when relevant.
- Include backlink quality/diversity checks when the backlink snapshot suggests weak authority, missing DP/DA/DR data, or overreliance on low-authority placements.
- Include an execution plan with priority, effort, expected impact, and owner-friendly next action.
- Include what to monitor in GSC after changes.
- Be specific to the brand, URL, page type, and visible GSC data.
- Do not invent exact metrics, queries, pages, date ranges, countries, or devices that were not provided.
- Write in {language}.
- Return valid JSON only.
- Start with "{{" and end with "}}".

Return JSON only in this format:
{{
  "executive_summary": "Short summary",
  "gsc_diagnosis": [
    {{"finding": "Finding", "evidence": "Metric or observation", "meaning": "Why it matters"}}
  ],
  "opportunities": [
    {{"opportunity": "Opportunity", "reason": "Why", "recommended_action": "Action"}}
  ],
  "recommendations": [
    {{"priority": "High", "area": "Metadata", "recommendation": "Specific recommendation", "impact": "Expected impact", "effort": "Low"}}
  ],
  "backlink_analysis": [
    {{"finding": "Backlink finding", "evidence": "Backlink count or authority observation", "seo_effect": "How backlinks may affect SEO", "recommended_action": "What to check or do next"}}
  ],
  "content_plan": [
    {{"section_or_asset": "Section or asset", "target_query": "Query", "notes": "What to add or improve"}}
  ],
  "technical_checks": [
    {{"check": "Check", "why": "Why", "how": "How to verify"}}
  ],
  "monitoring_plan": [
    {{"metric": "Metric", "target": "Target or direction", "timing": "When to check"}}
  ],
  "next_steps": [
    {{"step": "Action", "priority": "High", "effort": "Low"}}
  ]
}}
"""


def fetch_gsc_performance_data(
    target_url: str,
    start_date: str,
    end_date: str,
    site_url: str = "",
    access_token: str = "",
    service_account_json: str = "",
    row_limit: int = 25,
    timeout: int = 30,
) -> GscPerformanceResult:
    cleaned_target_url = _clean_text(target_url)
    cleaned_site_url = normalize_search_console_property(site_url) or search_console_property_for_url(cleaned_target_url)
    if not cleaned_site_url:
        raise ValueError("Enter a valid page URL or Search Console property.")

    token = (access_token or "").strip() or google_access_token_from_service_account_json(
        service_account_json,
        scopes=[GOOGLE_WEBMASTERS_READONLY_SCOPE],
    )
    if not token:
        raise ValueError("Add a Google OAuth access token or service account JSON in Settings first.")

    cleaned_start_date = _clean_text(start_date)
    cleaned_end_date = _clean_text(end_date)
    if not cleaned_start_date or not cleaned_end_date:
        raise ValueError("Choose a GSC start date and end date.")

    limited_rows = max(5, min(100, int(row_limit or 25)))
    filters = [
        {
            "dimension": "page",
            "operator": "equals",
            "expression": cleaned_target_url,
        }
    ]
    payload = {
        "startDate": cleaned_start_date,
        "endDate": cleaned_end_date,
        "dimensions": ["query", "page"],
        "rowLimit": limited_rows,
        "startRow": 0,
        "dimensionFilterGroups": [
            {
                "filters": filters
            }
        ],
    }
    daily_payload = {
        "startDate": cleaned_start_date,
        "endDate": cleaned_end_date,
        "dimensions": ["date"],
        "rowLimit": 500,
        "startRow": 0,
        "dimensionFilterGroups": [
            {
                "filters": filters
            }
        ],
    }
    endpoint = GOOGLE_SEARCH_ANALYTICS_ENDPOINT.format(site_url=quote(cleaned_site_url, safe=""))
    data = _post_gsc_search_analytics(endpoint, payload, token, timeout)
    daily_data = _post_gsc_search_analytics(endpoint, daily_payload, token, timeout)

    rows = _normalize_gsc_rows(data.get("rows", []))
    daily_rows = _normalize_gsc_daily_rows(daily_data.get("rows", []))
    return GscPerformanceResult(
        site_url=cleaned_site_url,
        start_date=cleaned_start_date,
        end_date=cleaned_end_date,
        row_limit=limited_rows,
        target_url=cleaned_target_url,
        rows=rows,
        daily_rows=daily_rows,
        summary=summarize_gsc_performance_rows(rows, cleaned_site_url, cleaned_start_date, cleaned_end_date, cleaned_target_url, daily_rows=daily_rows),
    )


def _post_gsc_search_analytics(endpoint: str, payload: dict, token: str, timeout: int) -> dict:
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw or "{}")
    except HTTPError as exc:
        raise ValueError(_gsc_api_error_message(exc.code)) from exc
    except URLError as exc:
        raise ValueError(str(exc.reason) if getattr(exc, "reason", None) else "Could not reach Search Console API.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Search Console API returned unreadable data.") from exc


def normalize_search_console_property(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    if cleaned.lower().startswith("sc-domain:"):
        domain = cleaned.split(":", 1)[1].strip().strip("/")
        if not domain:
            return ""
        return f"sc-domain:{domain.lower()}"
    if cleaned.startswith(("http://", "https://")):
        return cleaned if cleaned.endswith("/") else f"{cleaned}/"
    return ""


def summarize_gsc_performance_rows(
    rows: list[dict],
    site_url: str,
    start_date: str,
    end_date: str,
    target_url: str,
    daily_rows: list[dict] | None = None,
) -> str:
    total_clicks = sum(float(row.get("clicks", 0) or 0) for row in rows)
    total_impressions = sum(float(row.get("impressions", 0) or 0) for row in rows)
    average_ctr = total_clicks / total_impressions if total_impressions else 0
    weighted_position = (
        sum(float(row.get("position", 0) or 0) * float(row.get("impressions", 0) or 0) for row in rows) / total_impressions
        if total_impressions
        else 0
    )
    lines = [
        f"Search Console property: {site_url}",
        f"Target page: {target_url}",
        f"Date range: {start_date} to {end_date}",
        f"Rows returned: {len(rows)}",
        f"Totals from returned rows: clicks={total_clicks:.0f}, impressions={total_impressions:.0f}, ctr={average_ctr:.2%}, weighted_average_position={weighted_position:.1f}",
    ]
    if rows:
        lines.append("Top query/page rows:")
    for index, row in enumerate(rows[:30], start=1):
        query = row.get("query", "")
        page = row.get("page", "")
        lines.append(
            f"{index}. query={query or 'n/a'} | page={page or 'n/a'} | clicks={row.get('clicks', 0):.0f} | "
            f"impressions={row.get('impressions', 0):.0f} | ctr={row.get('ctr', 0):.2%} | position={row.get('position', 0):.1f}"
        )
    if not rows:
        lines.append("No rows returned for this page and date range.")
    if daily_rows:
        lines.append("Daily trend rows:")
        for row in daily_rows[:90]:
            lines.append(
                f"{row.get('date', 'n/a')}: clicks={row.get('clicks', 0):.0f}, "
                f"impressions={row.get('impressions', 0):.0f}, ctr={row.get('ctr', 0):.2%}, position={row.get('position', 0):.1f}"
            )
    return "\n".join(lines)


def _normalize_gsc_rows(rows) -> list[dict]:
    normalized = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        keys = item.get("keys") if isinstance(item.get("keys"), list) else []
        normalized.append(
            {
                "query": _clean_text(keys[0]) if len(keys) > 0 else "",
                "page": _clean_text(keys[1]) if len(keys) > 1 else "",
                "clicks": float(item.get("clicks", 0) or 0),
                "impressions": float(item.get("impressions", 0) or 0),
                "ctr": float(item.get("ctr", 0) or 0),
                "position": float(item.get("position", 0) or 0),
            }
        )
    return normalized


def _normalize_gsc_daily_rows(rows) -> list[dict]:
    normalized = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        keys = item.get("keys") if isinstance(item.get("keys"), list) else []
        normalized.append(
            {
                "date": _clean_text(keys[0]) if keys else "",
                "clicks": float(item.get("clicks", 0) or 0),
                "impressions": float(item.get("impressions", 0) or 0),
                "ctr": float(item.get("ctr", 0) or 0),
                "position": float(item.get("position", 0) or 0),
            }
        )
    return sorted(normalized, key=lambda item: item.get("date", ""))


def _gsc_api_error_message(status_code: int) -> str:
    return {
        400: "Search Console rejected the request. Check the page URL, property, and date range.",
        401: "Google authentication failed. Refresh the OAuth token or service account JSON.",
        403: "Google denied access. Make sure the account is added to this Search Console property.",
        404: "Search Console property was not found for this URL.",
        429: "Search Console API quota was exceeded. Try again later.",
    }.get(status_code, f"Search Console API returned HTTP {status_code}.")


def _normalize_report(data: dict) -> dict:
    return {
        "executive_summary": _clean_multiline(data.get("executive_summary", "")),
        "gsc_diagnosis": _normalize_list_of_dicts(data.get("gsc_diagnosis", []), ("finding", "evidence", "meaning")),
        "opportunities": _normalize_list_of_dicts(data.get("opportunities", []), ("opportunity", "reason", "recommended_action")),
        "recommendations": _normalize_list_of_dicts(data.get("recommendations", []), ("priority", "area", "recommendation", "impact", "effort")),
        "backlink_analysis": _normalize_list_of_dicts(data.get("backlink_analysis", []), ("finding", "evidence", "seo_effect", "recommended_action")),
        "content_plan": _normalize_list_of_dicts(data.get("content_plan", []), ("section_or_asset", "target_query", "notes")),
        "technical_checks": _normalize_list_of_dicts(data.get("technical_checks", []), ("check", "why", "how")),
        "monitoring_plan": _normalize_list_of_dicts(data.get("monitoring_plan", []), ("metric", "target", "timing")),
        "next_steps": _normalize_list_of_dicts(data.get("next_steps", []), ("step", "priority", "effort")),
    }


def _normalize_list_of_dicts(items, keys: tuple[str, ...]) -> list[dict]:
    normalized = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        cleaned = {key: _clean_multiline(item.get(key, "")) for key in keys}
        if any(cleaned.values()):
            normalized.append(cleaned)
    return normalized


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _clean_multiline(value: str) -> str:
    lines = [" ".join(line.split()).strip() for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("gsc planner progress callback failed")
