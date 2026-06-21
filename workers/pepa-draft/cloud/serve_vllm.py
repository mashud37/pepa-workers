"""Cloud Run service — token-guarded proxy in front of a local vLLM server.

POST /generate?token=...  {messages: [...]}  -> {text}
GET  /healthz             liveness probe (returns immediately)

/healthz returns OK the moment the proxy is up — it does NOT wait for vLLM —
so Cloud Run's startup probe passes while vLLM loads in the background.
/generate returns 503 until vLLM's own /health is ready.
"""
import json
import os
import time
import urllib.error
import urllib.request

from flask import Flask, abort, jsonify, request

_READY_WAIT = 280

app = Flask(__name__)
_TOKEN = os.environ.get("JOB_TOKEN", "")
_MODEL = os.environ.get("DRAFT_MODEL", "Qwen/Qwen3-32B-AWQ")
_VLLM = "http://127.0.0.1:8001"


def _vllm_ready() -> bool:
    try:
        with urllib.request.urlopen(_VLLM + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/generate")
def generate():
    if not _TOKEN or request.args.get("token") != _TOKEN:
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    messages = data.get("messages")
    if not messages:
        abort(400, "missing messages")
    deadline = time.time() + _READY_WAIT
    while not _vllm_ready():
        if time.time() > deadline:
            abort(503, "model still loading")
        time.sleep(2)

    body = json.dumps({
        "model": _MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(
        _VLLM + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        abort(502, f"vllm error: {e.read().decode('utf-8', 'replace')[:300]}")
    text = out["choices"][0]["message"]["content"].strip()
    return jsonify({"text": text})
