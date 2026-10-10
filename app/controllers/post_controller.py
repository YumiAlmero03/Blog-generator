"""Save and download the same post fields from all three article generators."""
import json
from io import BytesIO
from urllib.parse import urlsplit

from flask import jsonify, request, send_file

from app.services.content_quality_service import analyze_generated_content
from app.services.word_limit_settings import get_blog_word_limits, get_page_word_limits
from app.services.post_export_service import GENERATORS, export_post, normalize_post, normalize_category
from database import get_generation_history_item, record_generation
from generators.content_generator import count_html_words
from logger import logger


def _request_data():
    # A custom header plus JSON prevents cross-site form submissions. No CORS is enabled.
    origin = request.headers.get("Origin")
    if (request.headers.get("X-Requested-With") != "XMLHttpRequest"
            or not request.is_json
            or (origin and urlsplit(origin).netloc != request.host)):
        raise ValueError("Please save or download from the generator page.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Invalid post data.")
    return data


def save_post():
    try:
        data = _request_data()
        post = normalize_post(data, draft=data.get("autosave") is True)
        raw_id = str(data.get("history_id") or "")
        if raw_id and (not raw_id.isdecimal() or int(raw_id) <= 0):
            raise ValueError("Invalid history entry.")
        existing = get_generation_history_item(int(raw_id)) if raw_id else None
        if raw_id and not existing:
            raise ValueError("The saved post could not be found. Reload the page.")
        inputs = json.loads(existing["prompt_inputs"] or "{}") if existing else {}
        if existing and (existing["content_type"] != GENERATORS[post["generator"]]
                         or bool(inputs.get("news_generator")) != (post["generator"] == "news")):
            raise ValueError("This history entry belongs to a different generator.")
        for key in ("supporting_keyword", "supporting_keywords", "suggested_h2s", "language", "tone", "visual", "source_url", "source_title", "old_brand", "rework_content_type", "manual_supporting_keywords", "focus_keyword", "target_audience", "target_country", "current_date"):
            if key in data and isinstance(data[key], str):
                inputs[key] = data[key].strip()
        for key, field in (("links", "links_json"), ("generation_log", "generation_log_json"), ("reference_fetches", "reference_fetches_json")):
            if field in data:
                value = json.loads(data[field] or "[]")
                if not isinstance(value, list):
                    raise ValueError(f"Invalid {key}.")
                inputs[key] = value
        if "include_money_site" in data:
            inputs["include_money_site"] = data["include_money_site"] == "1"
        inputs["category_mode"] = "auto" if normalize_category(data.get("category")) == "Auto" else "manual"
        inputs.update(category=post["category"], news_generator=post["generator"] == "news")
        min_words, max_words = (get_page_word_limits() if post["generator"] == "rework" and inputs.get("rework_content_type") == "page" else get_blog_word_limits())
        quality_report = analyze_generated_content(
            post["content_html"], title=post["title"], keyword=post["primary_keyword"],
            meta_description=post["meta_description"], min_words=min_words, max_words=max_words,
        ) if post["content_html"] else {}
        history_id = record_generation(
            content_type=GENERATORS[post["generator"]], brand_name=post["brand"],
            title=post["title"], primary_keyword=post["primary_keyword"],
            content=post["content_html"], meta_description=post["meta_description"],
            tags=post["tags"], word_count=count_html_words(post["content_html"]),
            prompt_inputs=inputs, history_id=raw_id,
            post_link=existing.get("post_link", "") if existing else "",
            quality_report=quality_report,
        )
        return jsonify(history_id=history_id, category=post["category"], message="Meta description and draft saved." if data.get("autosave") is True else "Post saved to history.")
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        logger.exception("Could not save generated post")
        return jsonify(error="Could not save the post. Please try again."), 500


def download_post():
    try:
        data = _request_data()
        post = normalize_post(data)
        format = data.get("format", "json")
        payload, mimetype = export_post(post, format)
        extension = "json" if format == "json" else "xml"
        return send_file(BytesIO(payload), mimetype=mimetype, as_attachment=True,
                         download_name=f"{post['slug'][:100]}.{extension}")
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400
