import json

from flask import abort, render_template

from database import generation_dashboard_stats, get_generation_history_item, list_generation_history

from app.controllers.helpers import base_template_context


def dashboard():
    stats = generation_dashboard_stats()
    return render_template("dashboard.html", **base_template_context(), stats=stats)


def generation_history():
    return render_template(
        "generation_history.html",
        **base_template_context(),
        history_items=list_generation_history(120),
    )


def generation_history_detail(history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        abort(404)
    item["prompt_inputs_data"] = _loads(item.get("prompt_inputs", "{}"))
    item["quality_report_data"] = _loads(item.get("quality_report", "{}"))
    return render_template("generation_history_detail.html", **base_template_context(), item=item)


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
