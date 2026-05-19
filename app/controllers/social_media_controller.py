import json
from html.parser import HTMLParser

from flask import render_template, request

from database import (
    get_backlink,
    get_generation_history_item,
    list_backlinks,
    record_generation,
)
from generators.content_generator import count_html_words
from generators.social_media_generator import generate_neutral_blog_article
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_prompt, publish_generation_status
from app.services.provider_service import generation_error_message, get_provider


def neutral_blog_generator():
    state = {
        "topic": "",
        "suggested_content": "",
        "selected_medium_id": "",
        "selected_medium": None,
        "selected_title": "",
        "meta_description": "",
        "content": "",
        "visual": "",
        "post_link": "",
        "history_id": "",
        "tag_suggestions": [],
        "reference_links": [],
        "quality_report": None,
        "error": None,
        "success": None,
        "mediums": list_backlinks(),
    }
    selected_medium = request.args.get("medium_id", "").strip()
    if request.method == "GET" and selected_medium.isdigit():
        state["selected_medium_id"] = selected_medium
    edit_history_id = request.args.get("edit_history_id", "").strip()
    if request.method == "GET" and edit_history_id.isdigit():
        _load_history_item(state, int(edit_history_id))

    if request.method == "POST":
        action = request.form.get("action", "generate_content").strip()
        if action == "save_generated_blog":
            _handle_save_neutral_post(state)
        else:
            _handle_generate_neutral_article(state)

    return render_template("social_media_activator.html", **base_template_context(), **state)


def _load_history_item(state: dict, history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    selected_medium = _find_medium_from_history(prompt_inputs, item.get("medium_name", ""))
    state["history_id"] = str(item.get("id", ""))
    state["topic"] = item.get("primary_keyword", "") if item.get("primary_keyword") != "random topic" else prompt_inputs.get("topic", "")
    state["suggested_content"] = prompt_inputs.get("suggested_content", "") or ""
    state["selected_medium"] = selected_medium
    state["selected_medium_id"] = str(selected_medium.get("id", "")) if selected_medium else str(prompt_inputs.get("medium_id", ""))
    state["selected_title"] = item.get("title", "") or ""
    state["meta_description"] = item.get("meta_description", "") or ""
    state["content"] = item.get("content", "") or ""
    state["visual"] = prompt_inputs.get("visual", "") or ""
    state["post_link"] = item.get("post_link", "") or ""
    state["tag_suggestions"] = [tag.strip() for tag in (item.get("tags", "") or "").split(",") if tag.strip()]
    state["reference_links"] = prompt_inputs.get("reference_links", []) if isinstance(prompt_inputs.get("reference_links", []), list) else []
    state["quality_report"] = _loads(item.get("quality_report", "{}"))


def _find_medium_from_history(prompt_inputs: dict, medium_name: str) -> dict | None:
    medium_id = str(prompt_inputs.get("medium_id", "") or prompt_inputs.get("publishing_medium_id", "")).strip()
    if medium_id.isdigit():
        medium = get_backlink(int(medium_id))
        if medium:
            return medium
    return _find_medium_by_name(medium_name)


def _find_medium_by_name(medium_name: str) -> dict | None:
    cleaned = (medium_name or "").strip().lower()
    normalized = cleaned.replace(" · ", " ").replace(" - ", " ")
    for medium in list_backlinks():
        website_name = (medium.get("website_name", "") or "").strip().lower()
        account_name = (medium.get("blog_name", "") or medium.get("account_name", "") or "").strip().lower()
        display_name = _medium_display_name(medium).lower()
        if display_name == cleaned or (website_name == cleaned and not account_name):
            return medium
        if website_name and account_name and website_name in normalized and account_name in normalized:
            return medium
    return None


def _handle_generate_neutral_article(state: dict):
    state["topic"] = request.form.get("topic", "").strip()
    state["suggested_content"] = request.form.get("suggested_content", "").strip()
    state["selected_medium_id"] = request.form.get("selected_medium_id", "").strip()
    state["history_id"] = request.form.get("history_id", "").strip()

    if not state["selected_medium_id"].isdigit():
        state["error"] = "Please select a medium."
        return

    state["selected_medium"] = get_backlink(int(state["selected_medium_id"]))
    if not state["selected_medium"]:
        state["error"] = "The selected medium could not be found."
        return

    try:
        provider = get_provider()
        progress = _progress_callback("Neutral blog", request.form.get("generation_status_token", ""))
        progress("Generating neutral title...")
        result = generate_neutral_blog_article(
            provider,
            topic=state["topic"],
            suggested_content=state["suggested_content"],
            medium=state["selected_medium"],
            progress_callback=progress,
        )
        state["selected_title"] = result.get("title", "")
        state["meta_description"] = result.get("meta_description", "")
        state["content"] = result.get("content", "")
        state["visual"] = result.get("visual", "")
        state["tag_suggestions"] = result.get("tags", [])
        state["reference_links"] = result.get("reference_links", [])
        state["quality_report"] = _quality_report(state)
        state["history_id"] = str(record_generation(
            content_type="Neutral Post",
            title=state["selected_title"],
            primary_keyword=state["topic"] or "random topic",
            medium_name=_medium_display_name(state["selected_medium"]),
            word_count=state["quality_report"]["word_count"],
            meta_description=state["meta_description"],
            tags=state["tag_suggestions"],
            prompt_inputs={
                "topic": state["topic"],
                "suggested_content": state["suggested_content"],
                "medium_id": state["selected_medium_id"],
                "medium": _medium_context(state["selected_medium"]),
                "visual": state["visual"],
                "reference_links": state["reference_links"],
            },
            content=state["content"],
            quality_report=state["quality_report"],
            history_id=state["history_id"],
        ))
        clear_generation_status(request.form.get("generation_status_token", ""))
    except Exception as exc:
        logger.exception("neutral_blog_generator generation failed")
        state["error"] = generation_error_message(
            "An error occurred while generating the neutral post. Check logs/app.log for details.",
            exc,
        )


def _handle_save_neutral_post(state: dict):
    state["topic"] = request.form.get("topic", "").strip()
    state["suggested_content"] = request.form.get("suggested_content", "").strip()
    state["selected_medium_id"] = request.form.get("selected_medium_id", "").strip()
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["meta_description"] = request.form.get("meta_description", "").strip()
    state["content"] = request.form.get("content_html", "").strip()
    state["visual"] = request.form.get("visual", "").strip()
    state["post_link"] = _normalize_post_link(request.form.get("post_link", ""))
    state["history_id"] = request.form.get("history_id", "").strip()
    tags = [tag.strip() for tag in request.form.get("tags", "").split(",") if tag.strip()]
    state["tag_suggestions"] = tags
    state["reference_links"] = _parse_reference_links(request.form.get("reference_links", ""))

    if state["selected_medium_id"].isdigit():
        state["selected_medium"] = get_backlink(int(state["selected_medium_id"]))

    if not state["selected_medium"]:
        state["error"] = "The selected medium could not be found."
        return
    if not state["selected_title"]:
        state["error"] = "There is no generated neutral title to save."
        return
    if not state["content"]:
        state["error"] = "There is no generated neutral post to save."
        return
    if not _valid_post_link(state["post_link"]):
        state["error"] = "Please enter a valid post link before saving."
        return

    state["quality_report"] = _quality_report(state)
    failed_checks = [
        check.get("name", "Validator")
        for check in state["quality_report"].get("checks", [])
        if check.get("status") == "fail"
    ]
    if failed_checks:
        state["error"] = "Please fix the neutral post validator before saving: " + ", ".join(failed_checks)
        return

    state["history_id"] = str(record_generation(
        content_type="Neutral Post",
        title=state["selected_title"],
        primary_keyword=state["topic"] or "random topic",
        medium_name=_medium_display_name(state["selected_medium"]),
        word_count=state["quality_report"].get("word_count", count_html_words(state["content"])),
        meta_description=state["meta_description"],
        post_link=state["post_link"],
        tags=state["tag_suggestions"],
        prompt_inputs={
            "topic": state["topic"],
            "suggested_content": state["suggested_content"],
            "medium_id": state["selected_medium_id"],
            "medium": _medium_context(state["selected_medium"]),
            "visual": state["visual"],
            "reference_links": state["reference_links"],
            "manual_save": True,
        },
        content=state["content"],
        quality_report=state["quality_report"],
        history_id=state["history_id"],
    ))
    state["success"] = "Generated neutral post saved to history."


def _quality_report(state: dict) -> dict:
    medium = state["selected_medium"] or {}
    report = analyze_generated_content(
        state["content"],
        title=state["selected_title"],
        keyword=state["topic"],
        meta_description=state["meta_description"],
        min_words=_int_or_zero(medium.get("min_words", 0)),
        max_words=_int_or_zero(medium.get("max_characters", 0)),
        required_url="",
    )
    report["checks"].extend(_neutral_validator_checks(state, report))
    return report


def _neutral_validator_checks(state: dict, report: dict) -> list[dict]:
    title = (state.get("selected_title") or "").strip()
    meta_description = (state.get("meta_description") or "").strip()
    visual = (state.get("visual") or "").strip()
    tags = state.get("tag_suggestions") or []
    references = state.get("reference_links") or []
    content = state.get("content") or ""
    content_links = _extract_links(content)
    reference_urls = [item.get("url", "").strip() for item in references if item.get("url", "").strip()]
    missing_reference_urls = [url for url in reference_urls if url not in content_links and url not in content]
    reference_positions = sorted(content.find(url) for url in reference_urls if url and url in content)
    references_are_clustered = len(reference_positions) >= 2 and reference_positions[-1] - reference_positions[0] < 200

    return [
        _validator_check(
            "Neutral title",
            "pass" if title else "fail",
            title or "Missing generated title",
            "Generate or add a clear neutral title before saving.",
        ),
        _validator_check(
            "Neutral meta",
            "pass" if 120 <= len(meta_description) <= 140 else "fail",
            f"{len(meta_description)} characters",
            "Keep the generated meta description between 120 and 140 characters.",
        ),
        _validator_check(
            "Neutral tags",
            "pass" if len(tags) >= 3 else "warn",
            f"{len(tags)} tag(s)",
            "Keep at least a few relevant tags for organization and publishing.",
        ),
        _validator_check(
            "Visual ideas",
            "pass" if visual else "warn",
            "Present" if visual else "Missing visual ideas",
            "Add visual or image directions before publishing when the medium benefits from it.",
        ),
        _validator_check(
            "Reference links in content",
            "pass" if not missing_reference_urls and not references_are_clustered else "fail",
            _reference_detail(reference_urls, missing_reference_urls, references_are_clustered),
            "Place every reference URL naturally inside the article body and spread links across relevant sections.",
        ),
        _validator_check(
            "Neutral link policy",
            "pass",
            f"{report.get('link_count', 0)} editorial link(s); no required target link",
            "Neutral Blog should use only editorial/reference links, not a required promotional post link.",
        ),
    ]


def _validator_check(name: str, status: str, detail: str, recommendation: str) -> dict:
    return {"name": name, "status": status, "detail": detail, "recommendation": recommendation}


def _reference_detail(reference_urls: list[str], missing_urls: list[str], clustered: bool) -> str:
    if not reference_urls:
        return "No reference links supplied"
    if missing_urls:
        return f"{len(missing_urls)} reference URL(s) missing from content"
    if clustered:
        return "Reference links are too close together"
    return f"{len(reference_urls)} reference URL(s) placed in content"


def _extract_links(content: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(content or "")
    return parser.links


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = {name.lower(): (value or "") for name, value in attrs}
        href = attrs_dict.get("href", "").strip()
        if href:
            self.links.append(href)


def _medium_context(medium: dict) -> dict:
    return {
        "website_name": medium.get("website_name", ""),
        "blog_name": medium.get("blog_name", "") or medium.get("account_name", ""),
        "website_type": medium.get("website_type", ""),
        "post_type": medium.get("post_type", ""),
        "min_words": medium.get("min_words", 0),
        "max_words": medium.get("max_characters", 0),
        "content_guidelines": medium.get("content_guidelines", ""),
    }


def _medium_display_name(medium: dict) -> str:
    name = (medium.get("website_name") or "").strip()
    account = (medium.get("blog_name") or medium.get("account_name") or "").strip()
    if name and account:
        return f"{name} · {account}"
    return name


def _parse_reference_links(raw: str) -> list[dict]:
    items = []
    for line in (raw or "").splitlines():
        title, _separator, url = line.partition("|")
        if title.strip() and url.strip():
            items.append({"title": title.strip(), "url": url.strip()})
    return items


def _int_or_zero(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _valid_post_link(value: str) -> bool:
    cleaned = (value or "").strip().lower()
    return cleaned.startswith("https://") or cleaned.startswith("http://")


def _normalize_post_link(value: str) -> str:
    cleaned = (value or "").strip()
    lowered = cleaned.lower()
    if lowered.startswith(("http://", "https://")):
        return cleaned
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"
    return cleaned


def _progress_callback(label: str, token: str):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    return publish
