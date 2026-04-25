from flask import render_template, request

from app.controllers.helpers import base_template_context
from app.services.document_service import build_docx_response


def text_tools():
    return render_template("text_tools.html", **base_template_context())


def preview():
    return render_template(
        "preview.html",
        title=request.form.get("selected_title", ""),
        keyword=request.form.get("keyword", ""),
        supporting_keyword=request.form.get("supporting_keyword", ""),
        meta_description=request.form.get("meta_description", ""),
        content_html=request.form.get("content_html", ""),
    )


def download_doc():
    return build_docx_response(
        title=request.form.get("selected_title", ""),
        keyword=request.form.get("keyword", ""),
        supporting_keyword=request.form.get("supporting_keyword", ""),
        meta_description=request.form.get("meta_description", ""),
        content_html=request.form.get("content_html", ""),
    )
