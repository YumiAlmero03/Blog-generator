from flask import render_template, request

from app.controllers.helpers import base_template_context
from app.services.website_content_service import collect_website_content
from logger import logger


def website_content():
    site_url = request.form.get("site_url", "").strip()
    limit = request.form.get("limit", "1000")
    result = None
    error = ""
    if request.method == "POST":
        try:
            count = int(limit)
            if not 1 <= count <= 1000:
                raise ValueError("Page limit must be between 1 and 1000.")
            result = collect_website_content(site_url, count)
        except ValueError:
            error = "Enter a valid public website URL and a page limit between 1 and 1000."
        except Exception:
            logger.exception("Website content extraction failed")
            error = "The website could not be read. Please try again."
    return render_template("website_content.html", **base_template_context(), site_url=site_url, limit=limit, result=result, error=error,
                           export_rows=[[page["post_date"], page["title"], page["meta_description"]] for page in result["pages"]] if result else [])
