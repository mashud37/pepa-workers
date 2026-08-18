"""Per-book refinement engine: signals feed gates feed repairs; dry-run or apply."""
import re
import statistics
from pathlib import Path

from extract import shape

from . import headings, seams, signals, toc_text, zones

_MIN_UNIT = signals.MIN_UNIT_CHARS
_NEAR_SPLIT = 5
_OPENER_LINES = 5
_SNAP_LINES = 40
_MIN_CHAIN = 5
_QUAR_MAX_SHARE = 0.30
_TOC_OVERLAP = 0.5
_DEFAULT_TOC_WORDS = ("contents", "table of contents", "inhalt", "inhaltsverzeichnis")
_HEAD_MARK_RE = re.compile(r"^#+\s*")
_ACTION_LABELS = (
    ("demoted", "demote"),
    ("merged", "merges"),
    ("split", "splits"),
    ("joined", "joins"),
    ("quarantined", "quarantine"),
)


def load_book(stem: str, group: list) -> dict:
    paths = [p for _, p in group]
    texts = [p.read_text(encoding="utf-8").splitlines() for p in paths]
    lines: list = []
    starts = []
    for t in texts:
        starts.append(len(lines))
        lines.extend(t)
    return {"stem": stem, "paths": paths, "lines": lines, "starts": starts}


def _context(book: dict, cfg: dict) -> dict:
    lines = book["lines"]
    heads = signals.headings(lines)
    offs = signals.char_offsets(lines)
    lex = signals.lexicon(lines)
    fw, vocab = lex["function_words"], lex["vocab"]
    demoted = set(headings.false_headings(lines, heads, fw))
    sound = [h for h in heads if h["line"] not in demoted]
    recur = headings.recurring(sound, offs)
    demoted |= set(recur["running"])
    live = [h for h in sound if h["line"] not in demoted]
    cands = signals.anchor_heads(lines, sound)
    words = {w.casefold() for w in cfg.get("toc_headings", _DEFAULT_TOC_WORDS)}
    toc = toc_text.recover(lines, sound, words, cands)
    anchors = toc["anchors"] if toc else []
    return {
        "heads": heads,
        "offs": offs,
        "fw": fw,
        "vocab": vocab,
        "demoted": demoted,
        "live": {h["line"] for h in live},
        "live_heads": live,
        "cands": cands,
        "recur": recur,
        "toc": toc,
        "anchor_lines": {ln for ln, _ in anchors},
    }


def _opener_lines(lines: list, start: int) -> list:
    out = []
    for i in range(start, min(start + 30, len(lines))):
        if lines[i].strip():
            out.append(i)
            if len(out) >= _OPENER_LINES:
                break
    return out


def _opens_anchored(ctx: dict, opener: list) -> bool:
    return any(i in ctx["anchor_lines"] for i in opener)


def _opens_demoted_only(ctx: dict, lines: list, opener: list) -> bool:
    if any(i in ctx["live"] for i in opener):
        return False
    return any(i in ctx["demoted"] for i in opener)


def _merge_bounds(book: dict, ctx: dict) -> set:
    lines = book["lines"]
    removed = set()
    for b in book["starts"][1:]:
        opener = _opener_lines(lines, b)
        if _opens_anchored(ctx, opener):
            continue
        if seams.broken_seam(lines, b):
            removed.add(b)
            continue
        if _opens_demoted_only(ctx, lines, opener):
            cos = seams.seam_cohesion(lines, b, ctx["fw"])
            if cos is None or cos >= seams.MERGE_BLOCK:
                removed.add(b)
    return removed


_TERMINAL_PUNCT = tuple(".!?:;,\"'”’)]…")


def _title_like(text: str) -> bool:
    first = ""
    for c in text:
        if c.isalpha():
            first = c
            break
    return (len(text) <= 60 and not text.endswith(_TERMINAL_PUNCT)
            and not first.islower())


def _walk_up(lines: list, gline: int, floor: int) -> int:
    top = gline
    j = gline - 1
    while j > floor:
        t = lines[j].strip()
        if not t:
            j -= 1
            continue
        if t.startswith("#") or _title_like(t):
            top = j
            j -= 1
            continue
        break
    return top


def _nearest_snap(lines: list, bounds: list, targets: set, window: int) -> list:
    out = []
    for b in bounds:
        near = [t for t in targets if abs(t - b) <= window]
        if b == 0 or not near:
            out.append(b)
            continue
        target = min(near, key=lambda t: abs(t - b))
        others = [x for x in bounds if x != b]
        if others and min(abs(target - x) for x in others) < abs(target - b):
            out.append(b)
            continue
        floor = max((x for x in out if x < target), default=0)
        out.append(_walk_up(lines, target, floor))
    return sorted(set(out))


def _chain(ctx: dict) -> list:
    """Longest 1..N same-level run of short ordinal headings (N >= 5)."""
    hits = []
    for h in ctx["live_heads"]:
        t = h["text"].strip()
        if signals.ordinal_opener(t):
            hits.append((h["line"], h["level"], shape.ordinals([t])[0]))
    best: list = []
    for i, (ln, lvl, n) in enumerate(hits):
        if n != 1:
            continue
        run = [(ln, lvl, n)]
        for nxt in hits[i + 1:]:
            if nxt[1] == lvl and nxt[2] == run[-1][2] + 1:
                run.append(nxt)
        if len(run) > len(best):
            best = run
    return [ln for ln, _, _ in best] if len(best) >= _MIN_CHAIN else []


def _adopt_chain(book: dict, ctx: dict, bounds: list) -> dict:
    """When a clean Chapter-1..N heading chain exists, it defines the units
    between its first and last member; stray boundaries inside merge away.

    Returns:
        {"bounds": list of boundary line numbers, "chained": count of
        boundaries the chain moved or added}.
    """
    chain = _chain(ctx)
    if not chain:
        return {"bounds": bounds, "chained": 0}
    offs = ctx["offs"]
    spans = [offs[z] - offs[a] for a, z in zip(chain, chain[1:])]
    if statistics.median(spans) < 4 * signals.PAGE_CHARS:
        return {"bounds": bounds, "chained": 0}
    lines = book["lines"]
    keep = {0} | {_walk_up(lines, ln, 0) for ln in chain} | set(chain)
    keep |= ctx["anchor_lines"]
    out = [b for b in bounds
           if b < chain[0] or b > chain[-1]
           or any(abs(b - k) <= _NEAR_SPLIT for k in keep)]
    added = [ln for ln in chain
             if all(abs(ln - b) > _NEAR_SPLIT for b in out)]
    dropped = len(bounds) - len([b for b in bounds if b in out])
    return {"bounds": sorted(set(out) | set(added)), "chained": dropped + len(added)}


def _template_hits(ctx: dict, a: int, z: int) -> list:
    best: list = []
    for ls in ctx["recur"]["template"].values():
        inside = [ln for ln in ls if a < ln < z]
        if len(inside) >= 2 and (len(inside), -inside[0]) > (len(best), -(best or [a])[0]):
            best = inside
    return best


def _ordinal_hits(ctx: dict, missing: set) -> list:
    rng = ctx["toc"]["rng"] if ctx["toc"] else range(0)
    hits = []
    for h in ctx["live_heads"]:
        t = h["text"].strip()
        if h["line"] in rng:
            continue
        if signals.ordinal_opener(t) and shape.ordinals([t])[0] in missing:
            hits.append(h["line"])
    return hits


def _split_candidates(book: dict, ctx: dict, bounds: list) -> list:
    lines, offs = book["lines"], ctx["offs"]
    stops = bounds[1:] + [len(lines)]
    missing = signals.missing_ordinals(signals.unit_titles(bounds, lines, ctx["heads"]))
    cands = [("ordinal", ln) for ln in _ordinal_hits(ctx, missing)]
    for a, z in zip(bounds, stops):
        inside = [ln for ln, _ in (ctx["toc"]["anchors"] if ctx["toc"] else [])
                  if a < ln < z]
        cands += [("anchor", ln) for ln in inside]
        oversized = offs[z] - offs[a] >= signals.OVERSIZED_CHARS
        if oversized and not inside:
            cands += [("template", ln) for ln in _template_hits(ctx, a, z)]
    return cands


def _gate_splits(book: dict, ctx: dict, bounds: list, cands: list) -> list:
    lines, offs = book["lines"], ctx["offs"]
    taken = sorted(bounds)
    out = []
    for kind, raw in sorted(cands, key=lambda c: c[1]):
        floor = max(b for b in taken if b <= raw) if any(b <= raw for b in taken) else 0
        s = _walk_up(lines, raw, floor)
        if any(abs(s - b) <= _NEAR_SPLIT for b in taken):
            continue
        below = max(b for b in taken if b < s)
        above = min((b for b in taken if b > s), default=len(lines))
        if offs[s] - offs[below] < _MIN_UNIT or offs[above] - offs[s] < _MIN_UNIT:
            continue
        cos = seams.seam_cohesion(lines, s, ctx["fw"])
        if cos is not None and cos >= seams.SPLIT_BLOCK:
            continue
        taken.append(s)
        taken.sort()
        out.append((kind, s))
    return out


def _splits(book: dict, ctx: dict, bounds: list, cfg: dict) -> list:
    gated = _gate_splits(book, ctx, bounds, _split_candidates(book, ctx, bounds))
    for dropped in ((), ("template",), ("template", "ordinal")):
        chosen = [s for kind, s in gated if kind not in dropped]
        test = sorted(set(bounds) | set(chosen))
        if not chosen or signals.plausible(signals.unit_spans(test, ctx["offs"]), cfg)["ok"]:
            return chosen
    return []


def _merge_small(bounds: list, ctx: dict) -> list:
    offs = ctx["offs"]
    out = list(bounds)
    i = 0
    while i < len(out) and len(out) > 1:
        stop = out[i + 1] if i + 1 < len(out) else len(offs) - 1
        anchored = any(out[i] <= ln < out[i] + 15 for ln in ctx["anchor_lines"])
        if i == 0 or anchored or offs[stop] - offs[out[i]] >= _MIN_UNIT:
            i += 1
            continue
        out.pop(i + 1 if i + 1 < len(out) else i)
    return out


def _toc_share(ctx: dict, a: int, z: int) -> float:
    if not ctx["toc"]:
        return 0.0
    rng = ctx["toc"]["rng"]
    return len(set(rng) & set(range(a, z))) / max(1, z - a)


def _quar_reason(ctx: dict, lines: list, rng: tuple, first: bool) -> str | None:
    a, z = rng
    if any(a <= ln < z for ln in ctx["anchor_lines"]):
        return None
    verdict = zones.is_apparatus(lines[a:z], ctx["fw"])
    if verdict["apparatus"]:
        return "; ".join(verdict["reasons"])
    if _toc_share(ctx, a, z) >= _TOC_OVERLAP:
        return "contents pages"
    if first and ctx["offs"][z] - ctx["offs"][a] < _MIN_UNIT:
        return "sub-minimum front matter"
    return None


def _quarantines(book: dict, ctx: dict, bounds: list) -> list:
    lines, offs = book["lines"], ctx["offs"]
    total = offs[-1] or 1
    stops = bounds[1:] + [len(lines)]
    out = []
    for i, (a, z) in enumerate(zip(bounds, stops)):
        edge = i == 0 or i >= len(bounds) - 2
        big = (offs[z] - offs[a]) / total > _QUAR_MAX_SHARE
        if not edge or big or len(bounds) - len(out) <= 1:
            continue
        reason = _quar_reason(ctx, lines, (a, z), i == 0)
        if reason:
            out.append((i, reason))
    return out


def analyse(book: dict, cfg: dict) -> dict:
    """Compute the full repair plan for one book without touching disk.

    Returns:
        {"bounds", "demote", "merges", "splits", "quarantine", "joins",
         "n_before", "n_after", "notes"} where bounds are global line indices
        of unit starts after all repairs.
    """
    ctx = _context(book, cfg)
    removed = _merge_bounds(book, ctx)
    bounds = sorted((set(book["starts"]) - removed) | {0})
    bounds = _nearest_snap(book["lines"], bounds, ctx["anchor_lines"], _SNAP_LINES)
    splits = _splits(book, ctx, bounds, cfg)
    bounds = sorted(set(bounds) | set(splits))
    chain_result = _adopt_chain(book, ctx, bounds)
    bounds, chained = chain_result["bounds"], chain_result["chained"]
    bounds = _merge_small(bounds, ctx)
    quarantine = _quarantines(book, ctx, bounds)
    joins = seams.dehyphen_points(book["lines"], ctx["vocab"])
    titles = signals.unit_titles(bounds, book["lines"], ctx["heads"])
    notes = signals.diagnose(signals.unit_spans(bounds, ctx["offs"]), titles)
    if chained:
        notes.insert(0, "adopted ordinal heading chain")
    if ctx["toc"]:
        notes.insert(0, f"toc: {len(ctx['anchor_lines'])}/{ctx['toc']['expected']} "
                        "titles anchored")
    return {
        "bounds": bounds,
        "demote": sorted(ctx["demoted"]),
        "merges": sorted(removed),
        "splits": sorted(splits),
        "quarantine": quarantine,
        "joins": joins,
        "n_before": len(book["starts"]),
        "n_after": len(bounds) - len(quarantine),
        "notes": notes,
    }


def has_actions(plan: dict) -> bool:
    return bool(plan["demote"] or plan["merges"] or plan["splits"]
                or plan["quarantine"] or plan["joins"])


def actions_summary(plan: dict) -> str:
    parts = [f"{label} {len(plan[key])}" for label, key in _ACTION_LABELS if plan[key]]
    return " · ".join(parts)


def write_report(rows: list, path: Path) -> None:
    changed = [(s, p) for s, p in rows if has_actions(p)]
    out = [
        "# Markdown refinement report",
        "",
        f"{len(rows)} book(s) analysed · {len(changed)} with planned repairs",
        "",
        "| book | units | actions | diagnosis |",
        "|------|------:|---------|-----------|",
    ]
    for stem, p in changed:
        units = (f"{p['n_before']} → {p['n_after']}"
                 if p["n_before"] != p["n_after"] else str(p["n_before"]))
        out.append(f"| {stem} | {units} | {actions_summary(p)} | "
                   f"{' · '.join(p['notes'])} |")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _alnum(text: str) -> str:
    return "".join(c for c in text if c.isalnum())


def _edit_unit(lines: list, a: int, z: int, plan: dict) -> str:
    demote = set(plan["demote"])
    joins = set(plan["joins"])
    out: list = []
    i = a
    while i < z:
        ln = lines[i]
        if i in demote:
            ln = _HEAD_MARK_RE.sub("", ln)
        while i in joins and i + 1 < z:
            i += 1
            ln = ln.rstrip()[:-1] + lines[i].lstrip()
        out.append(ln)
        i += 1
    return "\n".join(out).strip() + "\n"


def apply_plan(book: dict, plan: dict, out_dir: Path) -> int:
    """Write the repaired unit files; returns the number of files written.

    Verifies alnum-level content invariance before any write and raises
    ValueError instead of writing when it fails.
    """
    bounds = plan["bounds"]
    stops = bounds[1:] + [len(book["lines"])]
    units = [_edit_unit(book["lines"], a, z, plan) for a, z in zip(bounds, stops)]
    if _alnum("".join(units)) != _alnum("\n".join(book["lines"])):
        raise ValueError("content invariance check failed: nothing written")
    quarantined = {i for i, _ in plan["quarantine"]}
    review = out_dir / "_review"
    for i in quarantined:
        review.mkdir(exist_ok=True)
        (review / f"text_{book['stem']}_{i + 1:02d}.apparatus.md").write_text(
            units[i], encoding="utf-8")
    keepers = [u for i, u in enumerate(units) if i not in quarantined]
    width = max(2, len(str(len(keepers))))
    names = [f"text_{book['stem']}_{i:0{width}d}.md" for i in range(1, len(keepers) + 1)]
    for name, content in zip(names, keepers):
        (out_dir / name).write_text(content, encoding="utf-8")
    for p in book["paths"]:
        if p.name not in names:
            p.unlink(missing_ok=True)
    return len(keepers)
