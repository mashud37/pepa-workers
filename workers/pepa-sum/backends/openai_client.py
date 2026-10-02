"""Call any server that accepts OpenAI's chat format, such as DeepSeek, Kimi, Qwen, Ollama or vLLM, through OpenAI's own library."""
import threading

import openai

import config

TEMPERATURE = 0.2
TIMEOUT_SECONDS = 600
RETRIES = 4
NO_KEY = "no-key"

_lock = threading.Lock()
_clients = {}
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
    """One semaphore sized to MAX_CONCURRENCY, so every thread together stays under the cap."""
    with _lock:
        if _gate["semaphore"] is None:
            _gate["semaphore"] = threading.BoundedSemaphore(config.max_concurrency())
        return _gate["semaphore"]


def drop_thinking(text):
    """Remove the reasoning some open models write between think tags before their answer."""
    answer = text.strip()
    if answer.startswith("<think>") and "</think>" in answer:
        answer = answer.split("</think>", 1)[1]
    return answer.strip()


def complete(system, prompt, max_tokens):
    """Send one system and user message pair and return the answer.

    Returns:
        dict with "text", the answer, and "truncated", True when it stopped at max_tokens.

    Raises:
        RuntimeError: the server stayed busy or unreachable, or the paper is too long for the
            model's context; the paper is skipped and a re-run tries it again.
        SystemExit: the server refused the request, for example a wrong key or model name.
    """
    connection = config.llm_connection()
    client = make_client(connection)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    try:
        with calls_in_flight():
            reply = client.chat.completions.create(
                model=connection["model"],
                messages=messages,
                max_tokens=max_tokens,
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
