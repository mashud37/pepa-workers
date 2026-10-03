"""Forward OpenAI-format requests to a local vLLM server on Cloud Run, holding each until the model
has loaded, so pepa-draft reaches it like any other openai-compatible address.
"""
import json
import time
import urllib.error
import urllib.request

from flask import Flask, Response, abort, request

READY_WAIT_SECONDS = 280
VLLM = "http://127.0.0.1:8001"
NO_THINKING = {"enable_thinking": False}

app = Flask(__name__)


def vllm_ready():
    try:
        with urllib.request.urlopen(VLLM + "/health", timeout=2) as reply:
            return reply.status == 200
    except (urllib.error.URLError, OSError):
        return False


@app.get("/healthz")
def healthz():
    return "ok"


@app.route("/v1/<path:path>", methods=["GET", "POST"])
def forward(path):
    """Pass the request and its key on to vLLM, which checks the key; Qwen3's thinking is off
    unless the caller asks for it."""
    deadline = time.time() + READY_WAIT_SECONDS
    while not vllm_ready():
        if time.time() > deadline:
            abort(503, "model still loading")
        time.sleep(2)

    body = None
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        data.setdefault("chat_template_kwargs", NO_THINKING)
        body = json.dumps(data).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": request.headers.get("Authorization", ""),
    }
    forwarded = urllib.request.Request(f"{VLLM}/v1/{path}", data=body, headers=headers, method=request.method)
    try:
        with urllib.request.urlopen(forwarded, timeout=600) as reply:
            return Response(reply.read(), status=reply.status, content_type="application/json")
    except urllib.error.HTTPError as error:
        return Response(error.read(), status=error.code, content_type="application/json")
