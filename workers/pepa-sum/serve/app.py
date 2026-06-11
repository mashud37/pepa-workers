"""Cloud Run summariser service — a thin HTTP wrapper over the local model.

POST /summarize?token=...  {system, prompt} -> {summary}
GET  /healthz              liveness probe

The token guards the endpoint (same value as JOB_TOKEN in env.yaml). The
service is configured with min-instances=0, so it scales to zero between runs.
"""
import os

from flask import Flask, request, jsonify, abort

from serve.model import generate

app = Flask(__name__)
_TOKEN = os.environ.get("JOB_TOKEN", "")


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/summarize")
def summarize():
    if not _TOKEN or request.args.get("token") != _TOKEN:
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        abort(400, "missing prompt")
    summary = generate(data.get("system", ""), prompt)
    return jsonify({"summary": summary})
