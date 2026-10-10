from datetime import date

from flask import make_response, render_template


def build_seo_performance_summary_response(result: dict):
    report = _performance_summary_context(result or {})
    response = make_response(render_template("seo_performance_summary_download.html", report=report))
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Content-Disposition"] = f"attachment; filename={report['filename']}.html"
    return response


def _performance_summary_context(result: dict) -> dict:
    summary = result.get("summary", {}) or {}
    pages = [
        page
        for page in result.get("pages", []) or []
        if page.get("status") == "checked" and page.get("result")
    ]
    audits = [page.get("result", {}) or {} for page in pages]
    stats = [audit.get("stats", {}) or {} for audit in audits]
    checked_count = len(audits)
    discovered_count = int(summary.get("discovered_count", 0) or len(result.get("pages", []) or []))
    average_score = int(summary.get("average_score", 0) or 0)
    average_grade = summary.get("average_grade", "") or _summary_grade(average_score)

    successful_pages = sum(1 for audit in audits if 200 <= int(audit.get("status_code", 0) or 0) < 400)
    ssl_pages = sum(1 for item in stats if item.get("ssl_verified", False))
    title_lengths = [int(item.get("title_length", 0) or 0) for item in stats]
    word_counts = [int(item.get("word_count", 0) or 0) for item in stats]
    schema_total = int(summary.get("schema_count", 0) or sum(len(item.get("schemas", []) or []) for item in stats))
    valid_schema = int(summary.get("valid_schema_count", 0) or sum(
        1 for item in stats for schema in item.get("schemas", []) or [] if schema.get("valid")
    ))
    not_found_count = int(summary.get("not_found_link_count", 0) or 0)
    issue_count = int(summary.get("issue_count", 0) or 0)

    snapshot_rows = [
        _snapshot_row("Page Accessibility", _ratio_status(successful_pages, checked_count), f"{successful_pages} of {checked_count} checked pages returned a successful HTTP response."),
        _snapshot_row("SSL / HTTPS", _ratio_status(ssl_pages, checked_count), f"SSL verification succeeded on {ssl_pages} of {checked_count} checked pages."),
        _check_snapshot(audits, "Meta Titles", ("Meta title",)),
        _check_snapshot(audits, "Meta Descriptions", ("Meta description",)),
        _check_snapshot(audits, "Heading Structure", ("Heading structure",)),
        _check_snapshot(audits, "Canonical Tags", ("Canonical URL",)),
        _schema_snapshot(valid_schema, schema_total),
        _check_snapshot(audits, "Image Alt Coverage", ("Image alt text",)),
        _check_snapshot(audits, "Sitemap & Robots", ("Sitemap", "Robots.txt")),
        _check_snapshot(audits, "Social Metadata", ("Social cards",)),
        _check_snapshot(audits, "Internal Linking", ("Internal links", "Sample link health")),
    ]

    recommendations = []
    seen_recommendations = set()
    for audit in audits:
        for check in audit.get("checks", []) or []:
            recommendation = str(check.get("recommendation", "") or "").strip()
            key = recommendation.casefold()
            if check.get("status") in {"warn", "fail"} and recommendation and key not in seen_recommendations:
                seen_recommendations.add(key)
                recommendations.append(recommendation)
    if not recommendations:
        recommendations = [
            "Keep titles and descriptions aligned with page intent.",
            "Maintain heading, canonical, schema, and image alt coverage as pages change.",
            "Review internal links and 404 reports after each content release.",
            "Continue publishing useful content and connecting related pages.",
        ]

    domain = result.get("base_url", "") or result.get("source_url", "") or "Website"
    clean_domain = domain.split("://", 1)[-1].rstrip("/") or "website"
    return {
        "title": f"SEO Performance Summary - {clean_domain}",
        "domain": clean_domain,
        "base_url": domain,
        "filename": _safe_filename(f"SEO Performance Summary {clean_domain}"),
        "date": date.today().strftime("%d %b %Y"),
        "grade": average_grade,
        "score": average_score,
        "metrics": [
            {"label": "Pages Audited", "value": f"{checked_count}/{discovered_count}", "note": "Checked page set"},
            {"label": "HTTP Success", "value": _percentage(successful_pages, checked_count), "note": f"{successful_pages} successful"},
            {"label": "SSL Coverage", "value": _percentage(ssl_pages, checked_count), "note": f"{ssl_pages} verified"},
            {"label": "Valid Schema", "value": f"{valid_schema}/{schema_total}", "note": "JSON-LD blocks"},
            {"label": "Avg. Title Length", "value": _average(title_lengths), "note": "Characters"},
            {"label": "Avg. Content Length", "value": _average(word_counts, thousands=True), "note": "Words per page"},
        ],
        "snapshot_rows": snapshot_rows,
        "highlights": [
            {"title": "Overall SEO Score", "text": f"The audit produced grade {average_grade} with an average score of {average_score}/100 across {checked_count} checked pages."},
            {"title": "Page Accessibility", "text": f"{successful_pages} of {checked_count} checked pages returned successful HTTP responses."},
            {"title": "Structured Data Coverage", "text": f"{valid_schema} of {schema_total} detected schema blocks were valid JSON-LD."},
            {"title": "Content Depth", "text": f"Audited pages contain an average of {_average(word_counts, thousands=True)} words."},
            {"title": "Link Health", "text": f"The site-wide audit identified {not_found_count} content link(s) returning HTTP 404."},
            {"title": "Items To Review", "text": f"The rule-based audit recorded {issue_count} warning or fix item(s) across the checked pages."},
        ],
        "assessment_lead": f"{clean_domain} received grade {average_grade} with an average SEO score of {average_score}/100.",
        "assessment": (
            f"The audit checked {checked_count} of {discovered_count} discovered pages, recorded {schema_total} schema blocks, "
            f"and found {not_found_count} content link(s) returning HTTP 404. The snapshot reflects technical and on-page "
            "signals collected by Website SEO Checker V2 at the time of this check."
        ),
        "recommendations": recommendations[:8],
    }


def _check_snapshot(audits: list[dict], area: str, check_names: tuple[str, ...]) -> dict:
    checks = [
        check
        for audit in audits
        for check in audit.get("checks", []) or []
        if check.get("name") in check_names
    ]
    if not checks:
        return _snapshot_row(area, "unknown", "No matching check data was recorded.")
    pass_count = sum(1 for check in checks if check.get("status") == "pass")
    status = "pass" if pass_count == len(checks) else "fix" if any(check.get("status") == "fail" for check in checks) else "warning"
    return _snapshot_row(area, status, f"{pass_count} of {len(checks)} recorded checks passed.")


def _schema_snapshot(valid_count: int, total_count: int) -> dict:
    status = _ratio_status(valid_count, total_count)
    return _snapshot_row("Schema Markup", status, f"{valid_count} of {total_count} detected schema blocks were valid.")


def _snapshot_row(area: str, status: str, summary: str) -> dict:
    labels = {"pass": "PASS", "warning": "WARNING", "fix": "FIX", "unknown": "NO DATA"}
    return {"area": area, "status": status, "status_label": labels.get(status, "NO DATA"), "summary": summary}


def _ratio_status(value: int, total: int) -> str:
    if total <= 0:
        return "unknown"
    if value == total:
        return "pass"
    if value <= 0:
        return "fix"
    return "warning"


def _percentage(value: int, total: int) -> str:
    return f"{round((value / total) * 100) if total else 0}%"


def _average(values: list[int], thousands: bool = False) -> str:
    average = round(sum(values) / len(values), 1) if values else 0
    if thousands:
        return f"{average:,.1f}".rstrip("0").rstrip(".")
    return f"{average:.1f}".rstrip("0").rstrip(".")


def _summary_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _safe_filename(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return "_".join(part for part in cleaned.split("_") if part) or "SEO_Performance_Summary"
