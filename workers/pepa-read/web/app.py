"""Flask app factory and local dev-server runner for the search UI."""
import threading
import webbrowser
from pathlib import Path

from flask import Flask

import config
from cli import ui

_ROOT = Path(__file__).resolve().parent


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(_ROOT / "templates"),
        static_folder=str(_ROOT / "static"),
    )
    from web.routes import bp
    app.register_blueprint(bp)
    return app


def run(port: int | None = None, open_browser: bool = True):
    port = port or config.PORT
    url = f"http://{config.HOST}:{port}/"
    ui.step(f"serving pepa-reader at {url}")
    app = create_app()
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    ui.info("press Ctrl+C to stop")
    app.run(host=config.HOST, port=port, debug=False)
