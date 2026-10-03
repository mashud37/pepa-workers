"""Create the search UI's Flask app and run it on this machine. Its guard refuses other host names and
other sites, so no web page reads or changes the library."""
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, request

import config
from cli import ui

_ROOT = Path(__file__).resolve().parent

LOCAL_HOSTS = [
    "127.0.0.1",
    "localhost",
]
CONTENT_POLICY = "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'"


def check_request():
    """Refuse requests addressed to another host name, and changes asked for by another site."""
    if request.host.split(":")[0] not in LOCAL_HOSTS:
        abort(403)
    origin = request.headers.get("Origin")
    if request.method != "GET" and origin and urlparse(origin).netloc != request.host:
        abort(403)


def add_security_headers(response):
    """Allow only the reader's own script, so text shown from a paper can never run as code."""
    response.headers.setdefault("Content-Security-Policy", CONTENT_POLICY)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
    app.before_request(check_request)
    app.after_request(add_security_headers)

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
