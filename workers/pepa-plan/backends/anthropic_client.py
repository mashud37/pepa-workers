"""Claude (Anthropic) client — default generation backend.

Adapted from pepa-sum/backends/anthropic_client.py. A global semaphore caps how
many requests are ever in flight at once (so the move-labelling pool can't outrun
the account's rate limit), transient overload/rate-limit is ridden out with
backoff that honors Retry-After, and token usage is tallied per model for the
post-run cost estimate. The Message Batches API (run_batch) is the same model and
request shape as complete(), only asynchronous and ~50% cheaper.
"""
import random
import threading
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)
_MAX_ATTEMPTS = 5

_lock = threading.Lock()
_cached = {"key": None, "client": None}

_gate_lock = threading.Lock()
_gate = {"limit": None, "sem": None}

# Token usage keyed by model, so a run that mixes the fast labelling model and the
# quality synthesis model is costed against each model's own price. `batch_*` are
# Message Batches tokens, billed at 50% (the cost estimate halves them).
_usage_lock = threading.Lock()
_usage = {}


def usage_snapshot():
    """Per-model cumulative token usage tallied from API responses since the last
    reset — the basis for the run's cost estimate. Safe to read from any thread."""
    with _usage_lock:
        return {m: dict(u) for m, u in _usage.items()}


def reset_usage():
    with _usage_lock:
        _usage.clear()


def _tally(model, msg, batch=False):
    u = getattr(msg, "usage", None)
    if u is None:
        return
    inp = getattr(u, "input_tokens", 0) or 0
    out = getattr(u, "output_tokens", 0) or 0
    with _usage_lock:
        rec = _usage.setdefault(
            model, {"input": 0, "output": 0, "batch_input": 0, "batch_output": 0, "calls": 0}
        )
        if batch:
            rec["batch_input"] += inp
            rec["batch_output"] += out
        else:
            rec["input"] += inp
            rec["output"] += out
        rec["calls"] += 1


def _governor():
    """One BoundedSemaphore sized to config.concurrency(), shared by every thread,
    so total simultaneous API calls stay within the configured cap."""
    limit = config.concurrency()
    with _gate_lock:
        if _gate["sem"] is None or _gate["limit"] != limit:
            _gate["limit"] = limit
            _gate["sem"] = threading.BoundedSemaphore(limit)
        return _gate["sem"]


def _client():
    """One thread-safe client, reused across calls (and threads) so the concurrent
    labelling pool shares its connection pool instead of each opening a new one."""
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic package missing. Run: pip install -r requirements.txt")

    key = config.anthropic_api_key()
    if not key:
        raise SystemExit(
            "No ANTHROPIC_API_KEY. Set it in secrets.yaml or the ANTHROPIC_API_KEY env "
            "var. Run: python manage.py install"
        )

    with _lock:
        if _cached["client"] is None or _cached["key"] != key:
            _cached["key"] = key
            _cached["client"] = anthropic.Anthropic(api_key=key)
        return _cached["client"]


def _backoff(attempt, error=None):
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


def complete(system, prompt, max_tokens=4000, model=None):
    client = _client()
    import anthropic

    model = model or config.anthropic_model()
    last = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with _governor():
                msg = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0.3,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
            _tally(model, msg)
            return "".join(
                b.text for b in msg.content if getattr(b, "type", None) == "text"
            ).strip()
        except anthropic.APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status not in _RETRYABLE:
                raise SystemExit(f"Anthropic API error {status}: {getattr(e, 'message', e)}")
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_backoff(attempt, e))
        except anthropic.APIConnectionError as e:
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_backoff(attempt))

    # Transient errors exhausted retries: recoverable per paper, not fatal to the
    # whole run — the caller logs it and moves on (a re-run picks the paper up).
    raise RuntimeError(f"Anthropic API unavailable after {_MAX_ATTEMPTS} attempts: {last}")


# Message Batches API: same model, max_tokens, temperature, system, and single
# user message as complete() above, so a paper labelled via a batch is drawn from
# the identical model and configuration as the live path — only the transport
# differs. 50% cheaper, asynchronous.
_BATCH_MAX_REQUESTS = 90000       # API ceiling is 100k; stay under it
_BATCH_MAX_BYTES = 180_000_000    # API caps total request size at 256 MB; keep margin


def run_batch(requests, on_progress=None, on_created=None):
    """Run many LLM calls through the Messages Batches API.

    `requests` is a list of {custom_id, system, prompt, max_tokens, model}.
    Returns {custom_id: text} for every request that succeeded; failed/expired ones
    are simply absent (the caller treats a missing id as a per-paper failure, to be
    retried on the next run). Polls until the batch ends; on Ctrl-C the in-flight
    batch is cancelled to stop spend, then the interrupt propagates.

    `on_created(batch_id)` fires as soon as each sub-batch is submitted, so the
    caller can record the id — a completed batch's results stay retrievable from the
    API for 29 days, so the id is the key to recovering paid work after any crash."""
    client = _client()
    default_model = config.anthropic_model()
    poll = config.batch_poll_seconds()
    results = {}
    for sub in _sub_batches(requests, _BATCH_MAX_REQUESTS, _BATCH_MAX_BYTES):
        batch = _submit_sub_batch(client, sub, default_model)
        if on_created:
            on_created(batch.id)
        _poll_until_ended(client, batch.id, poll, on_progress)
        _collect_results(client, batch.id, sub, default_model, results)
    return results


def _submit_sub_batch(client, sub, default_model):
    return client.messages.batches.create(requests=[
        {
            "custom_id": r["custom_id"],
            "params": {
                "model": r.get("model", default_model),
                "max_tokens": r["max_tokens"],
                "temperature": 0.3,
                "system": r["system"],
                "messages": [{"role": "user", "content": r["prompt"]}],
            },
        }
        for r in sub
    ])


def _poll_until_ended(client, batch_id, poll, on_progress):
    """Block until the batch ends, reporting progress each poll. On Ctrl-C the
    in-flight batch is cancelled to stop spend, then the interrupt propagates."""
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


def _collect_results(client, batch_id, sub, default_model, results):
    """Merge this sub-batch's succeeded results into `results` and tally usage."""
    models = {r["custom_id"]: r.get("model", default_model) for r in sub}
    for res in client.messages.batches.results(batch_id):
        if res.result.type != "succeeded":
            continue
        msg = res.result.message
        results[res.custom_id] = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        ).strip()
        _tally(models.get(res.custom_id, default_model), msg, batch=True)


def _sub_batches(seq, max_count, max_bytes):
    """Split requests into batches under BOTH the count and total-size ceiling. A
    single request larger than max_bytes still goes out on its own; the size guard
    only prevents many requests from summing past it."""
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
