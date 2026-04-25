import os

from app import create_app


app = create_app()


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("APP_PORT", "3444"))
    debug = os.getenv("FLASK_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug)
