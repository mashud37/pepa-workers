"""para_<name>.md — one sentence per paragraph, in document order.

Two methods, chosen by the PARA_METHOD setting: `llm` condenses each paragraph
abstractively (batched so it scales and works on either backend); `extractive`
picks each paragraph's most central sentence verbatim, with no model call.
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
    bullets = (extractive_rundown(paragraphs) if config.para_method() == "extractive"
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
        bullets.extend(_parse_numbered(text))
    return bullets


# --- batch path: same chunking, prompts, max_tokens, and parsing as above, so a
# batch-built rundown is identical in shape to the live one. ---

def chunk_paragraphs(text):
    """The paragraph chunks for one paper, each becoming one batch request."""
    return _chunks(_paragraphs(text))


def chunk_request(chunk):
    """(system, prompt, max_tokens) for one chunk — mirrors _complete_chunk."""
    return RUNDOWN_SYSTEM, build_rundown_prompt(chunk), _chunk_max_tokens(chunk)


def assemble_rundown(chunk_texts):
    """Stitch the chunk responses (in order) into the final numbered rundown."""
    return _format(_bullets_from(chunk_texts))


def _parse_numbered(text):
    items = [re.match(r"\s*\d+[.)]\s*(.+)", line) for line in text.splitlines()]
    items = [m.group(1).strip() for m in items if m]
    return items or [line.strip() for line in text.splitlines() if line.strip()]
