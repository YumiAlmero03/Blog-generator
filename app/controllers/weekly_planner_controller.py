from datetime import date, timedelta

from flask import render_template

from app.controllers.helpers import base_template_context


def weekly_planner():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    days = []
    for offset in range(7):
        current = week_start + timedelta(days=offset)
        days.append(
            {
                "key": current.isoformat(),
                "label": current.strftime("%A"),
                "date_label": current.strftime("%b %d"),
                "is_today": current == today,
            }
        )

    return render_template(
        "weekly_planner.html",
        **base_template_context(),
        today=today.isoformat(),
        days=days,
    )
