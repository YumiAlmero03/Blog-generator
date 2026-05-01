from flask import render_template, request

from app.controllers.helpers import base_template_context
from app.services.document_service import build_docx_response
from app.services.seo_checker_service import run_seo_audit
from logger import logger


def text_tools():
    return render_template("text_tools.html", **base_template_context())


def seo_checker():
    state = {
        "url": "",
        "ignore_ssl_errors": False,
        "result": None,
        "error": None,
    }

    if request.method == "POST":
        state["url"] = request.form.get("url", "").strip()
        state["ignore_ssl_errors"] = request.form.get("ignore_ssl_errors") == "1"
        try:
            state["result"] = run_seo_audit(state["url"], verify_ssl=not state["ignore_ssl_errors"])
        except Exception as exc:
            logger.exception("seo_checker action failed")
            state["error"] = str(exc) or "Could not complete the SEO check."

    return render_template("seo_checker.html", **base_template_context(), **state)


def preview():
    return render_template(
        "preview.html",
        title=request.form.get("selected_title", ""),
        keyword=request.form.get("keyword", ""),
        supporting_keyword=request.form.get("supporting_keyword", ""),
        meta_description=request.form.get("meta_description", ""),
        medium_name=request.form.get("medium_name", ""),
        tags=request.form.get("tags", ""),
        content_html=request.form.get("content_html", ""),
    )


def download_doc():
    return build_docx_response(
        title=request.form.get("selected_title", ""),
        keyword=request.form.get("keyword", ""),
        supporting_keyword=request.form.get("supporting_keyword", ""),
        meta_description=request.form.get("meta_description", ""),
        medium_name=request.form.get("medium_name", ""),
        tags=request.form.get("tags", ""),
        content_html=request.form.get("content_html", ""),
    )
