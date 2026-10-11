"""Answer one question about the literature and keep it in a conversation file in output/.
The console's Ask page runs each question as a job and reads the kept conversations.
"""
import json
from datetime import datetime
from pathlib import Path

import config
from backends import llm
from backends import prompt as prompts
from cli import costs
from cli.explore import format_hits
from corpus.metadata import list_bases

WORKS_IN_CONTEXT = 40
QUESTIONS_REMEMBERED = 6
ANSWER_TOKENS = 2000
ARGUMENTS_SHOWN = 500
CONCLUSIONS_SHOWN = 300
CONVERSATION_NAME = "ask_%Y%m%d_%H%M%S.json"


def short_brief_chars(record):
    """How many characters one paper adds to a question's prompt, cut the way format_hits cuts it."""
    names = len(record.get("authors", "")) + len(record.get("title", "")) + len(record.get("question", ""))
    arguments = min(ARGUMENTS_SHOWN, len(record.get("arguments_text", "")))
    conclusions = min(CONCLUSIONS_SHOWN, len(record.get("conclusions", "")))
    return names + arguments + conclusions


def ask_estimate(records):
    """The cost of one question, answered from the papers a question would draw on."""
    shown = min(WORKS_IN_CONTEXT, len(records))
    total = 0
    for record in records:
        total += short_brief_chars(record)
    per_paper = total // max(1, len(records))
    result = costs.estimate([{"input_chars": shown * per_paper, "output_tokens": ANSWER_TOKENS}], quality=False)
    result["papers"] = shown
    return result


def load_conversation(name):
    """A kept conversation by its file name in output/, or None when there is none by that name yet."""
    path = config.OUTPUT_DIR / Path(name).name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def works_for(question, conversation, list_file, records):
    """The papers a question is answered from: the conversation's own, else the closest ones, from a list when given."""
    from index.store import retrieve_hybrid
    if conversation is not None:
        by_base = {}
        for record in records:
            by_base[record["base"]] = record
        return [by_base[base] for base in conversation["works"] if base in by_base]
    wanted = set(list_bases(list_file)) if list_file else None
    return retrieve_hybrid(question, k=WORKS_IN_CONTEXT, restrict_bases=wanted)


def run(question, conversation_name=None, list_file=None, only_estimate=False):
    from index.store import checked_index
    records = checked_index()["records"]
    if list_file:
        wanted = set(list_bases(list_file))
        records = [record for record in records if record["base"] in wanted]
    if only_estimate:
        print(json.dumps(ask_estimate(records)))
        return
    if not question:
        raise SystemExit("Ask a question with --question.")

    conversation = load_conversation(conversation_name) if conversation_name else None
    works = works_for(question, conversation, list_file, records)
    if not works:
        raise SystemExit("No papers to answer from. Is the review index built?")
    earlier = []
    if conversation is not None:
        for turn in conversation["turns"][-QUESTIONS_REMEMBERED:]:
            earlier.append(turn["question"])
    answer = llm.complete(prompts.explore_system(), prompts.explore_prompt(question, format_hits(works), "\n".join(earlier)), max_tokens=ANSWER_TOKENS)

    now = datetime.now()
    if conversation is None:
        conversation_name = Path(conversation_name).name if conversation_name else now.strftime(CONVERSATION_NAME)
        conversation = {"title": question, "list": "", "works": [work["base"] for work in works], "turns": []}
        if list_file:
            conversation["list"] = Path(list_file).stem
    conversation["turns"].append({"question": question, "answer": answer, "when": now.isoformat(timespec="seconds")})
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUTPUT_DIR / conversation_name).write_text(json.dumps(conversation, indent=2, ensure_ascii=False), encoding="utf-8")

    print(answer)
    print(f"\nKept in {config.OUTPUT_DIR / conversation_name}")
