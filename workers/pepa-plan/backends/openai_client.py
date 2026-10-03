"""Call any server that accepts OpenAI's chat format, such as DeepSeek, Kimi, Qwen, Ollama or vLLM, through OpenAI's own library."""
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse

import openai

import config

TEMPERATURE = 0.3
TIMEOUT_SECONDS = 600
RETRIES = 4
NO_KEY = "no-key"
CLOUD_RUN_HOST = ".run.app"
SIGN_IN_SECONDS = 1800

_lock = threading.Lock()
_clients = {}
_sign_in = {"token": "", "fetched": 0.0}
_gate = {"semaphore": None}


def make_client(connection):
    """One client per server and key, shared by every thread so they share its connections."""
    key = connection["api_key"] or NO_KEY
    with _lock:
        if (connection["base_url"], key) not in _clients:
            _clients[(connection["base_url"], key)] = openai.OpenAI(
                base_url=connection["base_url"],
                api_key=key,
                timeout=TIMEOUT_SECONDS,
                max_retries=RETRIES,
            )
        return _clients[(connection["base_url"], key)]


def calls_in_flight():
    """One semaphore sized to the concurrency setting, so every thread together stays under the cap."""
    with _lock:
        if _gate["semaphore"] is None:
            _gate["semaphore"] = threading.BoundedSemaphore(config.load()["concurrency"])
        return _gate["semaphore"]


def cloud_run_headers(base_url):
    """Google's sign-in for a model on Cloud Run, which admits only your own account; nothing for any other server.
    The token comes from gcloud and is reused for half an hour, half its lifetime, since fetching one takes seconds."""
    host = urlparse(base_url).hostname or ""
    if not host.endswith(CLOUD_RUN_HOST):
        return {}
    with _lock:
        expired = time.monotonic() - _sign_in["fetched"] > SIGN_IN_SECONDS
        if not _sign_in["token"] or expired:
            gcloud = shutil.which("gcloud")
            if gcloud is None:
                raise SystemExit("A model on Cloud Run needs the gcloud command, signed in with: gcloud auth login")
            made = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True)
            if made.returncode != 0:
                raise SystemExit(f"gcloud could not sign in to Cloud Run: {made.stderr.strip()}")
            _sign_in["token"] = made.stdout.strip()
            _sign_in["fetched"] = time.monotonic()
        return {"X-Serverless-Authorization": f"Bearer {_sign_in['token']}"}


def drop_thinking(text):
    """Remove the reasoning some open models write between think tags before their answer."""
    answer = text.strip()
    if answer.startswith("<think>") and "</think>" in answer:
        answer = answer.split("</think>", 1)[1]
    return answer.strip()


def complete(system, prompt, max_tokens, quality=False):
    """Send one system and user message pair and return the answer, from the quality model when asked.

    Returns:
        dict with "text", the answer, and "truncated", True when it stopped at max_tokens.

    Raises:
        RuntimeError: the server stayed busy or unreachable, or the prompt is too long for the
            model's context; the paper is skipped and a re-run tries it again.
        SystemExit: the server refused the request, for example a wrong key or model name.
    """
    connection = config.llm_connection()
    client = make_client(connection)
    model = connection["model"]
    if quality:
        model = connection["quality_model"]
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    try:
        with calls_in_flight():
            reply = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                extra_headers=cloud_run_headers(connection["base_url"]),
                temperature=TEMPERATURE,
            )
    except (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError) as error:
        raise RuntimeError(f"LLM server unavailable at {connection['base_url']}: {error}")
    except openai.BadRequestError as error:
        if "context" in str(error).lower():
            raise RuntimeError(f"prompt too long for the model's context: {error}")
        raise SystemExit(f"LLM server refused the request: {error}")
    except openai.APIStatusError as error:
        raise SystemExit(f"LLM server error {error.status_code}: {error}")
    choice = reply.choices[0]
    return {
        "text": drop_thinking(choice.message.content or ""),
        "truncated": choice.finish_reason == "length",
    }
