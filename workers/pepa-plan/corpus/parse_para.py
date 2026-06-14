import re


def parse(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    sentences = []
    for line in lines:
        m = re.match(r"^\s*(\d+)\.\s+(.+)", line)
        if m:
            sentences.append(m.group(2).strip())
    return sentences
