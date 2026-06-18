"""Claude (Anthropic) client for the comprehension layer — the default backend.

Pay-per-use, so idle cost is zero; far better quality and speed than the
self-hosted CPU model. The API key comes from ANTHROPIC_API_KEY (env or
env.yaml). A global semaphore caps how many requests are ever in flight at once
(so the batch's nested pools can't outrun the account's rate limit), and
transient overload/rate-limit is ridden out with backoff that honors Retry-After.
"""
import random
import threading
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)
_MAX_ATTEMPTS = 5

# Anthropic models expose a 200k-token context window. A prompt that, with its
# reserved output, would exceed it returns a fatal 400 mid-run — and a single
# oversized paper would otherwise abort the whole batch (serial re-raises the
# SystemExit; a batch request just fails silently and re-fails on every re-run).
# A cheap characters-based estimate (dense academic text runs ~3.5 chars/token)
# trips before the call so the paper is skipped cleanly; the API's own 400 is the
# authoritative backstop for anything the estimate under-counts.
CONTEXT_LIMIT_TOKENS = 200_000
_CHARS_PER_TOKEN = 3.5
_CONTEXT_MARGIN_TOKENS = 1_000


class PromptTooLong(Exception):
    """A request would exceed the model's context window. Recoverable per paper:
    the caller logs it and moves on, the paper is simply not produced."""


def _estimate_tokens(text):
    return int(len(text) / _CHARS_PER_TOKEN)


def request_token_estimate(system, prompt, max_tokens):
    """Conservative tokens this request occupies: input text plus reserved output."""
    return _estimate_tokens(system) + _estimate_tokens(prompt) + max_tokens


def would_overflow(system, prompt, max_tokens):
    """Whether the request is too large for the context window (estimate only)."""
    est = request_token_estimate(system, prompt, max_tokens)
    return est + _CONTEXT_MARGIN_TOKENS > CONTEXT_LIMIT_TOKENS

_lock = threading.Lock()
_cached = {"key": None, "client": None}

_gate_lock = threading.Lock()
_gate = {"limit": None, "sem": None}

_usage_lock = threading.Lock()
# `input`/`output` are live (full-price) tokens; `batch_input`/`batch_output`
# are Message Batches tokens, billed at 50% (the cost estimate halves them).
_usage = {"input": 0, "output": 0, "calls": 0, "batch_input": 0, "batch_output": 0}


def usage_snapshot():
    """Cumulative token usage tallied from API responses since the last reset —
    the basis for the run's cost estimate. Safe to read from any thread."""
    with _usage_lock:
        return dict(_usage)


def reset_usage():
    with _usage_lock:
        _usage.update(input=0, output=0, calls=0, batch_input=0, batch_output=0)


def _governor():
    """One BoundedSemaphore sized to config.max_concurrency(), shared by every
    thread, so total simultaneous API calls stay within the configured cap."""
    limit = config.max_concurrency()
    with _gate_lock:
        if _gate["sem"] is None or _gate["limit"] != limit:
            _gate["limit"] = limit
            _gate["sem"] = threading.BoundedSemaphore(limit)
        return _gate["sem"]


def _client():
    """One thread-safe client, reused across calls (and threads) so concurrent
    rundown batches share its connection pool instead of each opening a new one."""
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic package missing. Run: pip install -r requirements.txt")

    key = config.anthropic_api_key()
    if not key:
        raise SystemExit(
            "No ANTHROPIC_API_KEY. Set it in env.yaml or the ANTHROPIC_API_KEY env "
            "var (run: python manage.py install)."
        )

    with _lock:
        if _cached["client"] is None or _cached["key"] != key:
            _cached["key"] = key
            _cached["client"] = anthropic.Anthropic(api_key=key)
        return _cached["client"]


def _backoff(attempt, error=None):
    """Seconds to wait before the next attempt: honor a Retry-After header when
    the API sends one, else exponential backoff with jitter."""
    after = _retry_after(error)
    if after is not None:
        return after
    return min(2 ** attempt + random.uniform(0, 1), 30)


def _retry_after(error):
    resp = getattr(error, "response", None)
    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def complete(system, prompt, max_tokens=2000):
    if would_overflow(system, prompt, max_tokens):
        est = request_token_estimate(system, prompt, max_tokens)
        raise PromptTooLong(
            f"prompt ~{est:,} tokens exceeds the {CONTEXT_LIMIT_TOKENS:,}-token "
            "context window — paper skipped (lower the text budget to shorten it)"
        )
    client = _client()
    import anthropic

    last = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with _governor():
                msg = client.messages.create(
                    model=config.anthropic_model(),
                    max_tokens=max_tokens,
                    temperature=0.2,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
            u = getattr(msg, "usage", None)
            if u is not None:
                with _usage_lock:
                    _usage["input"] += getattr(u, "input_tokens", 0) or 0
                    _usage["output"] += getattr(u, "output_tokens", 0) or 0
                    _usage["calls"] += 1
            return "".join(
                b.text for b in msg.content if getattr(b, "type", None) == "text"
            ).strip()
        except anthropic.APIStatusError as e:
            status = getattr(e, "status_code", None)
            detail = str(getattr(e, "message", e))
            if status == 400 and "too long" in detail.lower():
                # Estimate missed it: skip this paper rather than abort the run.
                raise PromptTooLong(f"prompt rejected as too long — paper skipped ({detail})")
            if status not in _RETRYABLE:
                # A non-transient API error (bad request, auth, model) — fatal.
                raise SystemExit(f"Anthropic API error {status}: {detail}")
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_backoff(attempt, e))
        except anthropic.APIConnectionError as e:
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_backoff(attempt))

    # Transient errors exhausted retries: recoverable per paper, not fatal to the
    # whole batch — the caller logs it and moves on (re-run picks the paper up).
    raise RuntimeError(f"Anthropic API unavailable after {_MAX_ATTEMPTS} attempts: {last}")


# Message Batches API: same model and request shape as complete() above
# (model, max_tokens, temperature=0.2, system, single user message), so a paper
# summarised via a batch is drawn from the identical model and configuration as
# the live path — only the transport differs. 50% cheaper, asynchronous.
_BATCH_MAX_REQUESTS = 90000       # API ceiling is 100k; stay under it
# API caps total request size at 256 MB. sum_ prompts embed the full paper text,
# so a large run hits the size ceiling long before the count one — split on both.
# Conservative byte budget (margin under 256 MB, and chars under-count UTF-8).
_BATCH_MAX_BYTES = 180_000_000


def run_batch(requests, on_progress=None):
    """Run many LLM calls through the Messages Batches API.

    `requests` is a list of {custom_id, system, prompt, max_tokens}. Returns
    {custom_id: text} for every request that succeeded; failed/expired ones are
    simply absent (the caller treats a missing id as a per-paper failure and the
    paper is retried on the next run). Polls until the batch ends; on Ctrl-C the
    in-flight batch is cancelled to stop spend, then the interrupt propagates."""
    client = _client()
    model = config.anthropic_model()
    poll = config.batch_poll_seconds()
    results = {}
    for sub in _sub_batches(requests, _BATCH_MAX_REQUESTS, _BATCH_MAX_BYTES):
        batch = client.messages.batches.create(requests=[
            {
                "custom_id": r["custom_id"],
                "params": {
                    "model": model,
                    "max_tokens": r["max_tokens"],
                    "temperature": 0.2,
                    "system": r["system"],
                    "messages": [{"role": "user", "content": r["prompt"]}],
                },
            }
            for r in sub
        ])
        try:
            while True:
                status = client.messages.batches.retrieve(batch.id)
                if on_progress:
                    on_progress(status)
                if status.processing_status == "ended":
                    break
                time.sleep(poll)
        except KeyboardInterrupt:
            try:
                client.messages.batches.cancel(batch.id)
            except Exception:
                pass
            raise
        for res in client.messages.batches.results(batch.id):
            if res.result.type != "succeeded":
                continue
            msg = res.result.message
            results[res.custom_id] = "".join(
                b.text for b in msg.content if getattr(b, "type", None) == "text"
            ).strip()
            u = getattr(msg, "usage", None)
            if u is not None:
                with _usage_lock:
                    _usage["batch_input"] += getattr(u, "input_tokens", 0) or 0
                    _usage["batch_output"] += getattr(u, "output_tokens", 0) or 0
                    _usage["calls"] += 1
    return results


def _sub_batches(seq, max_count, max_bytes):
    """Split requests into batches under BOTH the count and the total-size ceiling.
    A single request larger than max_bytes still goes out on its own (one paper's
    text is well under the limit); the size guard only prevents many papers from
    summing past it. Size is estimated from prompt+system chars plus per-request
    overhead — cheap, and the budget keeps margin for the under-count vs UTF-8."""
    batch, size = [], 0
    for r in seq:
        r_bytes = len(r["system"]) + len(r["prompt"]) + 256
        if batch and (len(batch) >= max_count or size + r_bytes > max_bytes):
            yield batch
            batch, size = [], 0
        batch.append(r)
        size += r_bytes
    if batch:
        yield batch
