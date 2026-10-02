"""Create and run the local web console, a browser face over the same child apps.
It listens on this machine only, and every form post must carry this run's token.
"""
import atexit
import logging
import secrets
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, current_app, request

from cli import ui
from registry import APPS, INSTALLED
from web import jobs, mascot, routes
from web.settings import SETTINGS

FOLDER = Path(__file__).resolve().parent
LOCAL_HOSTS = [
    "127.0.0.1",
    "localhost",
]
BROWSER_DELAY_SECONDS = 0.8
CONTENT_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    f"frame-src 'self' http://127.0.0.1:{SETTINGS['read_port']} http://localhost:{SETTINGS['read_port']}; "
    "object-src 'self'; base-uri 'none'; form-action 'self'"
)
BYTES_PER_MEGABYTE = 1024 * 1024


def check_request():
    """Refuse requests addressed to any other host name, and posts without this run's token."""
    host_name = request.host.split(":")[0]
    if host_name not in LOCAL_HOSTS:
        abort(403)
    if request.method != "POST":
        return None
    sent = request.form.get("token", "")
    if not secrets.compare_digest(sent, current_app.config["CONSOLE_TOKEN"]):
        abort(403)
    return None


def template_values():
    """Values every template can use: the token, the apps, job labels, the log interval, and the mascot."""
    return {
        "token": current_app.config["CONSOLE_TOKEN"],
        "apps": APPS,
        "installed": INSTALLED,
        "status_label": jobs.STATUS_LABEL,
        "running": jobs.running_count(),
        "poll_ms": SETTINGS["poll_ms"],
        "draw_mascot": mascot.svg,
    }


def add_security_headers(response):
    """Allow only this console's own script, so text shown from a file can never run as code."""
    response.headers.setdefault("Content-Security-Policy", CONTENT_POLICY)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def create_app():
    """Build the Flask app with its request guard, template values, and routes."""
    app = Flask(__name__, template_folder=str(FOLDER / "templates"), static_folder=str(FOLDER / "static"))
    token = secrets.token_urlsafe(32)
    app.secret_key = token
    app.config["CONSOLE_TOKEN"] = token
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.config["MAX_CONTENT_LENGTH"] = SETTINGS["upload_limit_mb"] * BYTES_PER_MEGABYTE
    app.before_request(check_request)
    app.after_request(add_security_headers)
    app.context_processor(template_values)
    app.register_blueprint(routes.bp)
    return app


def run(port=None, open_browser=True):
    """Serve the console until Ctrl+C, stopping every job it started on the way out."""
    port = port or SETTINGS["port"]
    url = f"http://{SETTINGS['host']}:{port}/"
    ui.step(f"serving pepa-console at {url}")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    atexit.register(jobs.stop_all)
    app = create_app()
    if open_browser:
        threading.Timer(BROWSER_DELAY_SECONDS, webbrowser.open, [url]).start()
    ui.info("press Ctrl+C to stop; jobs started here stop with it")
    app.run(host=SETTINGS["host"], port=port, debug=False, threaded=True)
