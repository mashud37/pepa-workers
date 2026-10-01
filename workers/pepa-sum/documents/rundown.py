"""Build para_<name>.md, one sentence per paragraph in document order,
using either the `llm` method (abstractive, batched) or `extractive` (most
central sentence, no model call).
"""
import re
from concurrent.futures import ThreadPoolExecutor

import config
from backends import RUNDOWN_SYSTEM, build_rundown_prompt, complete
from extract.paragraphs import body_span, split_paragraphs, extractive_rundown

# Paragraphs per LLM call. One constant, shared by the live and batch paths, so
# both chunk a paper identically.
CHUNK = 15

# Generous empty-result fallback the renderer recognises.
NO_PARAGRAPHS = "_No paragraphs detected._"


def build(text):
    paragraphs = _paragraphs(text)
    if not paragraphs:
        return NO_PARAGRAPHS
    bullets = (extractive_rundown(paragraphs) if config.load('PARA_METHOD') == "extractive"
               else _llm_rundown(paragraphs))
    return _format(bullets)


def _paragraphs(text):
    return split_paragraphs(body_span(text), min_chars=400)


def _chunks(paragraphs):
    return [paragraphs[start:start + CHUNK] for start in range(0, len(paragraphs), CHUNK)]


def _format(bullets):
    return "\n".join(f"{i}. {b}" for i, b in enumerate(bullets, 1))


def _chunk_max_tokens(chunk):
    return 60 * len(chunk) + 200


def _complete_chunk(chunk):
    return complete(RUNDOWN_SYSTEM, build_rundown_prompt(chunk), max_tokens=_chunk_max_tokens(chunk))


def _llm_rundown(paragraphs):
    chunks = _chunks(paragraphs)
    workers = min(config.max_workers(), len(chunks))
    if workers <= 1:
        texts = [_complete_chunk(c) for c in chunks]
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            texts = list(ex.map(_complete_chunk, chunks))
    return _bullets_from(texts)


def _bullets_from(texts):
    bullets = []
    for text in texts:
        lines = text.splitlines()
        items = [re.match(r"\s*\d+[.)]\s*(.+)", line) for line in lines]
        items = [m.group(1).strip() for m in items if m]
        bullets.extend(items or [line.strip() for line in lines if line.strip()])
    return bullets


# ---- Batch path ----
# Same chunking, prompts, max_tokens, and parsing as above, so a batch-built
# rundown is identical in shape to the live one.

def chunk_paragraphs(text):
    """The paragraph chunks for one paper, each becoming one batch request."""
    return _chunks(_paragraphs(text))


def chunk_request(chunk):
    """The `system`, `prompt` and `max_tokens` for one chunk, mirrors _complete_chunk."""
    return {
        "system": RUNDOWN_SYSTEM,
        "prompt": build_rundown_prompt(chunk),
        "max_tokens": _chunk_max_tokens(chunk),
    }


def assemble_rundown(chunk_texts):
    """Stitch the chunk responses (in order) into the final numbered rundown."""
    return _format(_bullets_from(chunk_texts))

