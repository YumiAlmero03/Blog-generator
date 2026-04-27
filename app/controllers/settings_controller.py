from flask import render_template, request

from database import get_setting, set_setting

from app.controllers.helpers import base_template_context


def settings():
    state = {
        "money_site": get_setting("money_site", ""),
        "success": None,
        "error": None,
    }

    if request.method == "POST":
        state["money_site"] = request.form.get("money_site", "").strip()
        set_setting("money_site", state["money_site"])
        state["success"] = "Settings saved."

    return render_template("settings.html", **base_template_context(), **state)
