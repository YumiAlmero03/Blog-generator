from flask import Flask

from app.routes.web import web
from app.services.image_tool_cleanup_scheduler import start_image_tool_cleanup_scheduler
from app.services.website_index_scheduler import start_website_index_scheduler
from app.services.websocket_status_server import start_websocket_status_server


def create_app():
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.register_blueprint(web)
    start_website_index_scheduler()
    start_image_tool_cleanup_scheduler()
    start_websocket_status_server()
    return app
