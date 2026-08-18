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
    # Local single-user dev tool: always pick up template/static edits on the
    # next request instead of caching them for the life of the process, since
    # debug=False (required: never expose the Werkzeug debugger) would
    # otherwise leave TEMPLATES_AUTO_RELOAD off and static files cached.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    from web.routes import bp
    app.register_blueprint(bp)
    return app


def run(port: int | None = None, open_browser: bool = True):
    port = port or config.PORT
    url = f"http://{config.HOST}:{port}/"
    ui.step(f"serving pepa-reader at {url}")
    app = create_app()
    if open_browser:
        threading.Timer(0.7, webbrowser.open, [url]).start()
    ui.info("press Ctrl+C to stop")
    app.run(host=config.HOST, port=port, debug=False)
