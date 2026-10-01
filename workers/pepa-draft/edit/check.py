"""Post-draft quality checks: sentence length, filler phrases."""
import re

FILLERS = [
    "it is important to note",
    "it should be noted",
    "needless to say",
    "as mentioned above",
    "as noted above",
    "in order to",
    "due to the fact that",
    "at this point in time",
    "the fact that",
    "it is worth noting",
    "in terms of",
    "with regard to",
    "with respect to",
]


def check(text: str) -> list[dict]:
    """Return a list of issues found in text.

    Returns:
        List of dicts: {type, sentence, detail}
    """
    issues = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sent in sentences:
        words = sent.split()
        if len(words) > 45:
            issues.append({"type": "long_sentence", "sentence": sent[:80] + "...", "detail": f"{len(words)} words"})
        for filler in FILLERS:
            if filler.lower() in sent.lower():
                issues.append({"type": "filler", "sentence": sent[:80] + "...", "detail": filler})
    return issues
