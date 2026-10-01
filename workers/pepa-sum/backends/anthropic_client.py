"""Call Claude for the comprehension layer, the default backend, capping
in-flight requests with a global semaphore and retrying transient errors
with backoff.
"""
import random
import threading
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)
_MAX_ATTEMPTS = 5
DEFAULT_MAX_TOKENS = 2000

# API ceiling is 100k requests per batch; stay under it.
_BATCH_MAX_REQUESTS = 90000
# API caps total request size at 256 MB. sum_ prompts embed the full paper text,
# so a large run hits the size ceiling long before the count one: split on both.
# Conservative byte budget (margin under 256 MB, and chars under-count UTF-8).
_BATCH_MAX_BYTES = 180_000_000

# Anthropic models expose a 200k-token context window. A prompt that, with its
# reserved output, would exceed it returns a fatal 400 mid-run, and a single
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


class Truncated(Exception):
    """The model stopped at max_tokens with the output unfinished. Carries the
    partial text (`.text`) so the caller can save it for eval before treating the
    paper as a per-paper failure and letting a re-run regenerate it."""

    def __init__(self, text):
        super().__init__("output stopped at the max_tokens limit")
        self.text = text


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
    """Cumulative token usage tallied from API responses since the last reset:
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

    key = config.load('ANTHROPIC_API_KEY')
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


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, flag_truncation=False):
    """One live completion. With flag_truncation, a response that stops at the
    max_tokens limit raises Truncated (carrying the partial text) instead of
    returning a silently cut-off body; used by the sum_ brief, whose trailing
    fields (conclusion, future research) are the first thing a short cap drops."""
    if would_overflow(system, prompt, max_tokens):
        est = request_token_estimate(system, prompt, max_tokens)
        raise PromptTooLong(
            f"prompt ~{est:,} tokens exceeds the {CONTEXT_LIMIT_TOKENS:,}-token "
            "context window: paper skipped (lower the text budget to shorten it)"
        )
    client = _client()
    import anthropic

    last = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with _governor():
                msg = client.messages.create(
                    model=config.load('ANTHROPIC_MODEL'),
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
            text = "".join(
                b.text for b in msg.content if getattr(b, "type", None) == "text"
            ).strip()
            if flag_truncation and getattr(msg, "stop_reason", None) == "max_tokens":
                raise Truncated(text)
            return text
        except anthropic.APIStatusError as e:
            status = getattr(e, "status_code", None)
            detail = str(getattr(e, "message", e))
            if status == 400 and "too long" in detail.lower():
                # Estimate missed it: skip this paper rather than abort the run.
                raise PromptTooLong(f"prompt rejected as too long: paper skipped ({detail})")
            if status not in _RETRYABLE:
                # A non-transient API error (bad request, auth, model): fatal.
                raise SystemExit(f"Anthropic API error {status}: {detail}")
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_backoff(attempt, e))
        except anthropic.APIConnectionError as e:
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_backoff(attempt))

    # Transient errors exhausted retries: recoverable per paper, not fatal to the
    # whole batch: the caller logs it and moves on (re-run picks the paper up).
    raise RuntimeError(f"Anthropic API unavailable after {_MAX_ATTEMPTS} attempts: {last}")


# Message Batches API: same model and request shape as complete() above
# (model, max_tokens, temperature=0.2, system, single user message), so a paper
# summarised via a batch is drawn from the identical model and configuration as
# the live path, only the transport differs. 50% cheaper, asynchronous.


def run_batch(requests, on_progress=None):
    """Run many LLM calls through the Messages Batches API.

    Args:
        requests: list of {custom_id, system, prompt, max_tokens}.
        on_progress: called with each poll's status while the batch runs.

    Returns:
        `results`, {custom_id: text} for every request that succeeded (failed or
        expired ones are simply absent, so the caller treats a missing id as a
        per-paper failure retried next run), and `truncated`, the set of
        custom_ids whose output stopped at the max_tokens limit (present in
        results but cut off).

    Polls until the batch ends; on Ctrl-C the in-flight batch is cancelled to
    stop spend, then the interrupt propagates.
    """
    client = _client()
    model = config.load('ANTHROPIC_MODEL')
    poll = config.batch_poll_seconds()
    results = {}
    truncated = set()
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
        _wait_for_batch(client, batch.id, poll, on_progress)
        collected = _collect_batch(client, batch.id)
        results.update(collected["results"])
        truncated |= collected["truncated"]
    return {"results": results, "truncated": truncated}


def _wait_for_batch(client, batch_id, poll, on_progress):
    """Poll until the batch ends, cancelling it if the user interrupts."""
    try:
        while True:
            status = client.messages.batches.retrieve(batch_id)
            if on_progress:
                on_progress(status)
            if status.processing_status == "ended":
                return
            time.sleep(poll)
    except KeyboardInterrupt:
        try:
            client.messages.batches.cancel(batch_id)
        except Exception:
            pass
        raise


def _record_usage(msg):
    """Add one finished message's token counts to the run's usage totals."""
    u = getattr(msg, "usage", None)
    if u is None:
        return
    with _usage_lock:
        _usage["batch_input"] += getattr(u, "input_tokens", 0) or 0
        _usage["batch_output"] += getattr(u, "output_tokens", 0) or 0
        _usage["calls"] += 1


def _collect_batch(client, batch_id):
    """The finished batch's succeeded `results`, and the `truncated` ids cut off at max_tokens."""
    results = {}
    truncated = set()
    for res in client.messages.batches.results(batch_id):
        if res.result.type != "succeeded":
            continue
        msg = res.result.message
        results[res.custom_id] = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        ).strip()
        if getattr(msg, "stop_reason", None) == "max_tokens":
            truncated.add(res.custom_id)
        _record_usage(msg)
    return {"results": results, "truncated": truncated}


def _sub_batches(seq, max_count, max_bytes):
    """Split requests into batches under BOTH the count and the total-size ceiling.
    A single request larger than max_bytes still goes out on its own (one paper's
    text is well under the limit); the size guard only prevents many papers from
    summing past it. Size is estimated from prompt+system chars plus per-request
    overhead: cheap, and the budget keeps margin for the under-count vs UTF-8."""
    batches = []
    batch, size = [], 0
    for r in seq:
        r_bytes = len(r["system"]) + len(r["prompt"]) + 256
        if batch and (len(batch) >= max_count or size + r_bytes > max_bytes):
            batches.append(batch)
            batch, size = [], 0
        batch.append(r)
        size += r_bytes
    if batch:
        batches.append(batch)
    return batches
