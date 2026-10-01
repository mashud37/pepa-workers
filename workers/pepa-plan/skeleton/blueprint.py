"""Synthesise a within-section paragraph blueprint for each skeleton's
major moves, gathering real sections from example papers and asking
Sonnet for the recurring progression.
"""
import json
import random
import statistics
from datetime import datetime, timezone

import config
from backends import anthropic_client, llm, prompt
from cli import ui
from corpus import join
from skeleton import build

MAJOR_SHARE = 0.10          # a move worth blueprinting (rarer ones don't generalise)
MIN_SECTIONS = 4            # below this there isn't enough evidence, skip the move
MAX_SECTIONS = 40           # sections shown to the model per move
SECTION_CHAR_BUDGET = 24_000
SEED = 0


def build_blueprints(skeletons=None, sequences=None):
    skeletons = skeletons if skeletons is not None else _load_skeletons()
    sequences = sequences if sequences is not None else _load_sequences()
    moves_by_base = {s["base"]: s["moves"] for s in sequences}

    plan = [(sk, _major_moves(sk)) for sk in skeletons]
    total = sum(len(moves) for _, moves in plan)
    _show_plan(plan, total)

    anthropic_client.reset_usage()
    blueprints, done = {}, 0
    for sk, major in plan:
        blueprints[sk["id"]] = {}
        for move, intent in major:
            done += 1
            ui.info(f"[{done}/{total}] {sk['id']} · {move}")
            secs = _gather(sk, move, moves_by_base)
            if len(secs) < MIN_SECTIONS:
                ui.warn(f"    only {len(secs)} section(s), skipped")
                continue
            blueprints[sk["id"]][move] = _synthesise_move(sk, move, intent, secs)
    build._report_cost()
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "major_share": MAJOR_SHARE,
        "blueprints": blueprints,
    }


# ---- Blueprint synthesis ----

def _major_moves(skeleton):
    """The skeleton's stages worth blueprinting: share over the floor, deduped by
    move (a move can recur across stages) keeping its first/highest-share intent."""
    seen, out = set(), []
    stages = sorted(skeleton.get("stages", []),
                    key=lambda s: float(s.get("typical_share", 0) or 0), reverse=True)
    for st in stages:
        m = st.get("move")
        if m in seen or float(st.get("typical_share", 0) or 0) < MAJOR_SHARE:
            continue
        seen.add(m)
        out.append((m, st.get("intent", "")))
    return out


def _gather(skeleton, move, moves_by_base):
    secs = []
    for base in skeleton.get("example_bases", []):
        moves = moves_by_base.get(base)
        if not moves:
            continue
        secs.extend(join.sections(join.paired(base, moves), move))
    return secs


def _synthesise_move(skeleton, move, intent, sections):
    lengths = [len(s) for s in sections]
    raw = llm.complete(
        prompt.blueprint_system(),
        prompt.blueprint_prompt(skeleton, move, intent, _sample(sections)),
        max_tokens=1500,
        quality=True,
    )
    data = _parse_json(raw)
    return {
        "move": move,
        "intent": intent,
        "typical_paragraphs": _length_band(lengths),
        "n_sections_observed": len(sections),
        "progression": data.get("progression", []),
        "reads_like": data.get("reads_like", ""),
        "validation": {},
    }


def _sample(sections):
    """Prefer multi-paragraph sections (single-paragraph runs show no progression),
    then draw reproducibly within a character budget so the call stays bounded."""
    rng = random.Random(SEED)
    pool = sorted(sections, key=len, reverse=True)[:MAX_SECTIONS * 2]
    rng.shuffle(pool)
    chosen, chars = [], 0
    for s in pool:
        block = sum(len(t) for t in s)
        if chosen and chars + block > SECTION_CHAR_BUDGET:
            continue
        chosen.append(s)
        chars += block
        if len(chosen) >= MAX_SECTIONS:
            break
    return chosen


def _length_band(lengths):
    """[p25, p75] paragraph count, or [min, max] when too few sections to quantile."""
    s = sorted(lengths)
    if not s:
        return [0, 0]
    if len(s) < 4:
        return [s[0], s[-1]]
    q = statistics.quantiles(s, n=4)
    return [max(1, round(q[0])), max(1, round(q[2]))]


def _parse_json(raw):
    """Tolerant parse: one move failing to return clean JSON shouldn't abort the
    whole run, so a bad reply yields an empty progression with a warning."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        ui.warn("    could not parse blueprint JSON, left empty")
        return {}


# ---- Reporting and persistence ----

def _show_plan(plan, total):
    ui.step("Plan")
    ui.info(f"blueprint {total} major move(s) across {len(plan)} skeleton(s)")
    for sk, major in plan:
        moves = ", ".join(m for m, _ in major) or "(none over threshold)"
        ui.info(f"  {sk['id']}: {moves}")


def _load_skeletons():
    if not config.SKELETONS_FILE.exists():
        raise SystemExit("No skeleton library, run 'Build skeletons' first.")
    return json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8")).get("skeletons", [])


def _load_sequences():
    if not config.SEQUENCES_FILE.exists():
        raise SystemExit("No labelled sequences, run 'Build skeletons' first.")
    data = json.loads(config.SEQUENCES_FILE.read_text(encoding="utf-8"))
    return [s for s in data if s.get("moves")]


def save(library):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.BLUEPRINTS_FILE.write_text(
        json.dumps(library, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load():
    if not config.BLUEPRINTS_FILE.exists():
        return None
    return json.loads(config.BLUEPRINTS_FILE.read_text(encoding="utf-8"))
