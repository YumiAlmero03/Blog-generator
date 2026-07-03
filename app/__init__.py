import os

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from app.routes.web import web
from app.controllers.helpers import base_template_context
from app.services.image_tool_cleanup_scheduler import start_image_tool_cleanup_scheduler
from app.services.website_index_scheduler import start_website_index_scheduler
from app.services.websocket_status_server import start_websocket_status_server


def create_app():
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config["MAX_CONTENT_LENGTH"] = _bytes_from_env("MAX_CONTENT_LENGTH_MB", 32) * 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = _bytes_from_env("MAX_FORM_MEMORY_SIZE_MB", 16) * 1024 * 1024
    app.register_error_handler(RequestEntityTooLarge, _handle_request_entity_too_large)
    app.register_blueprint(web)
    start_website_index_scheduler()
    start_image_tool_cleanup_scheduler()
    start_websocket_status_server()
    return app


def _bytes_from_env(name: str, default_mb: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default_mb))))
    except ValueError:
        return default_mb


def _handle_request_entity_too_large(exc):
    message = (
        "The upload is too large. Capture a smaller browser area, upload a compressed screenshot, "
        "or lower the screenshot resolution before generating the report."
    )
    if request.path.startswith("/background-jobs") or "application/json" in request.headers.get("Accept", ""):
        return jsonify({"error": message}), 413
    return render_template("error.html", **base_template_context(), error=message), 413
