"""Call any server that accepts OpenAI's chat format, such as DeepSeek, Kimi, Qwen, Ollama or vLLM, through OpenAI's own library."""
import threading

import openai

import config

TIMEOUT_SECONDS = 600
RETRIES = 4
NO_KEY = "no-key"

_lock = threading.Lock()
_clients = {}


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


def drop_thinking(text):
    """Remove the reasoning some open models write between think tags before their answer."""
    answer = text.strip()
    if answer.startswith("<think>") and "</think>" in answer:
        answer = answer.split("</think>", 1)[1]
    return answer.strip()


def complete(system, prompt, max_tokens, model):
    """Send one system and user message pair to the model and return the answer.

    Raises:
        SystemExit: the server stayed unreachable or refused the request.
    """
    connection = config.llm_connection()
    client = make_client(connection)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    try:
        reply = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
    except openai.APIConnectionError as error:
        raise SystemExit(f"Could not reach the LLM server at {connection['base_url']}: {error}")
    except openai.APIStatusError as error:
        raise SystemExit(f"LLM server error {error.status_code}: {error}")
    return drop_thinking(reply.choices[0].message.content or "")
