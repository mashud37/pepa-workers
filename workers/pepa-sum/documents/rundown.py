"""para_<name>.md — one sentence per paragraph, in document order.

Two methods, chosen by the PARA_METHOD setting: `llm` condenses each paragraph
abstractively (batched so it scales and works on either backend); `extractive`
picks each paragraph's most central sentence verbatim, with no model call.
"""
import re

import config
from backends import RUNDOWN_SYSTEM, build_rundown_prompt, complete
from extract.paragraphs import body_span, split_paragraphs, extractive_rundown


def build(text):
    paragraphs = split_paragraphs(body_span(text), min_chars=400)
    if not paragraphs:
        return "_No paragraphs detected._"
    bullets = (extractive_rundown(paragraphs) if config.para_method() == "extractive"
               else _llm_rundown(paragraphs))
    return "\n".join(f"{i}. {b}" for i, b in enumerate(bullets, 1))


def _llm_rundown(paragraphs, batch=15):
    bullets = []
    for start in range(0, len(paragraphs), batch):
        chunk = paragraphs[start:start + batch]
        text = complete(RUNDOWN_SYSTEM, build_rundown_prompt(chunk), max_tokens=60 * len(chunk) + 200)
        bullets.extend(_parse_numbered(text))
    return bullets


def _parse_numbered(text):
    items = [re.match(r"\s*\d+[.)]\s*(.+)", line) for line in text.splitlines()]
    items = [m.group(1).strip() for m in items if m]
    return items or [line.strip() for line in text.splitlines() if line.strip()]
