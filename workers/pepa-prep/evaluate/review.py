"""Round-trip between a predicted stream and a hand-correctable tag file.

The artifact shows one source line per row, each prefixed with the predictor's
guess. Correcting is retagging — never retyping — so the gold line order stays
identical to the stream and scoring aligns by index.
"""
import re

from .predict import CONT, DROP, HEAD, LIST, PARA

_TAGS = {HEAD: "⟦HEAD⟧", PARA: "⟦PARA⟧", CONT: "⟦CONT⟧", LIST: "⟦LIST⟧", DROP: "⟦DROP⟧"}
_TAG_RE = re.compile(r"^\s*⟦(HEAD|PARA|CONT|LIST|DROP)⟧ ?(.*)$")

_LEGEND = (
    "# Correction file — fix the tag on any wrong line, then save.\n"
    "#   ⟦HEAD⟧ heading   ⟦PARA⟧ new paragraph   ⟦CONT⟧ continues previous   ⟦LIST⟧ list item\n"
    "#   ⟦DROP⟧ line should NOT be in output (running header/footer, page noise, OCR garbage)\n"
    "# Change only the tags. Do not add, delete, reorder, or edit the line text.\n"
)


def render(texts: list, labels: list) -> str:
    body = "\n".join(f"{_TAGS[lab]} {txt}" for lab, txt in zip(labels, texts))
    return _LEGEND + "\n" + body + "\n"


def parse(text: str) -> tuple[list, list]:
    labels, texts = [], []
    for line in text.splitlines():
        m = _TAG_RE.match(line)
        if m:
            labels.append(m.group(1))
            texts.append(m.group(2))
    return labels, texts
