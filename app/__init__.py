from flask import Flask

from app.routes.web import web


def create_app():
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.register_blueprint(web)
    return app
