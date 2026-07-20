"""CLI layer for the bibliography enrichment workflow.

Matches pepa-sum sum_*.md files to a Zotero CSL-JSON library, fetches full
metadata from Crossref (by DOI for matched papers, title search for unmatched),
and optionally enriches each record with citation networks from OpenCitations.

Output: one biblio_{stem}.json per paper in the configured output folder.
Existing files are skipped unless --force is set.

Pipeline:
    [1] Match sum_*.md stems to Zotero records
    [2] Fetch metadata from Crossref (DOI or title search)
    [3] Write biblio JSON files           <- interleaved with step 2
   ([4] Fetch citation networks)          <- only with --cite
"""
from pathlib import Path

from biblio import crossref, match, opencitations, write

from . import ui


def run(cfg: dict, zotero=None, cite=False, force=False, quiet=False) -> None:
    corpus_dir = Path(cfg.get("biblio_corpus", "../pepa-sum/output"))
    out_dir = Path(cfg.get("biblio_output", cfg.get("output_folder", "./output"))) / "biblio"
    email = cfg.get("crossref_email", "")

    if not corpus_dir.exists():
        raise SystemExit(
            f"Corpus directory not found: {corpus_dir}\n"
            "Set biblio_corpus in config.yaml or pass --corpus."
        )

    stems = sorted(f.stem[4:] for f in corpus_dir.glob("sum_*.md"))
    if not stems:
        raise SystemExit(f"No sum_*.md files found in {corpus_dir}")

    zotero_path = _resolve_zotero(zotero, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)

    n = len(stems)
    total_steps = 4 if cite else 3
    email_note = f"polite pool: {email}" if email else "set crossref_email in config.yaml for polite pool"

    # Announce the full pipeline before any blocking call (liveness rule)
    ui.header("pepa-prep  —  bibliography enrichment")
    ui.info(f"{n} paper(s) found in corpus")
    ui.info(f"Output folder: {out_dir.resolve()}")
    ui.info(f"Crossref: {email_note}")
    _show_plan(cite, total_steps)

    # Step 1: match Zotero
    ui.step(f"Step 1/{total_steps}: Match Zotero library")
    records = match.load_zotero(zotero_path)
    ui.info(f"loaded {len(records)} records from {Path(zotero_path).name}")
    matches = match.match_all(stems, records)
    n_matched = sum(1 for v in matches.values() if v)
    ui.ok(f"{n_matched}/{n} matched  ·  {n - n_matched} will use Crossref title search")

    # Step 2+3: Crossref fetch + write (interleaved so progress shows per paper)
    done = skipped = errors = 0
    ui.step(f"Step 2/{total_steps}: Fetch Crossref + write output")
    for i, stem in enumerate(stems, 1):
        ui.info(f"[{i}/{n}] {stem}")  # always before the blocking API call

        if not force and write.exists(out_dir, stem):
            skipped += 1
            if not quiet:
                ui.info("  · skip (exists)")
            continue

        try:
            zrec = matches.get(stem)
            biblio_data, source = _fetch_one(stem, zrec, email, quiet)
            biblio_data.update({
                "source_file": f"sum_{stem}.md",
                "stem": stem,
                "match_source": source,
            })
            if biblio_data.get("title"):
                biblio_data["apa"] = write.apa_string(
                    biblio_data.get("title", ""),
                    biblio_data.get("authors", []),
                    biblio_data.get("year"),
                    biblio_data.get("journal", ""),
                )
            write.save(out_dir, stem, biblio_data)
            done += 1
        except Exception as e:
            errors += 1
            ui.error(f"  · failed: {e}")

    ui.ok(f"{done} written  ·  {skipped} skipped  ·  {errors} failed")

    if not cite:
        _done_summary(out_dir, done)
        return

    # Step 4: OpenCitations citation networks
    cite_done = cite_skip = 0
    ui.step(f"Step 4/{total_steps}: Fetch citation networks (OpenCitations)")
    for i, stem in enumerate(stems, 1):
        ui.info(f"[{i}/{n}] {stem}")  # always before the blocking API call
        existing = write.load(out_dir, stem)
        if not existing:
            cite_skip += 1
            continue
        doi = existing.get("doi", "")
        if not doi:
            cite_skip += 1
            if not quiet:
                ui.info("  · no DOI — skipping")
            continue
        existing["references"] = opencitations.references(doi)
        existing["cited_by"] = opencitations.citations(doi)
        write.save(out_dir, stem, existing)
        cite_done += 1

    ui.ok(f"{cite_done} enriched  ·  {cite_skip} skipped (no DOI)")
    _done_summary(out_dir, done)


def _show_plan(cite: bool, total_steps: int) -> None:
    steps = [
        f"[1/{total_steps}] match Zotero",
        f"[2/{total_steps}] fetch Crossref",
        f"[3/{total_steps}] write output",
    ]
    if cite:
        steps.append(f"[4/{total_steps}] fetch citations")
    ui.info("  →  ".join(steps))


def _done_summary(out_dir: Path, count: int) -> None:
    ui.step("Done")
    if count:
        ui.ok(f"biblio JSON files in {out_dir.resolve()}")


def _resolve_zotero(zotero, cfg: dict) -> str:
    if zotero:
        p = Path(zotero)
        if not p.exists():
            raise SystemExit(f"Zotero file not found: {zotero}")
        return str(p)

    configured = cfg.get("biblio_zotero", "")
    if configured:
        p = Path(configured)
        if p.exists():
            return str(p)

    input_dir = Path(cfg.get("input_folder", "./input"))
    candidates = [
        p for p in (list(input_dir.glob("*.json")) + list(Path(".").glob("*.json")))
        if "biblio_" not in p.name
    ]
    unique = list({p.resolve() for p in candidates})

    if len(unique) == 1:
        ui.info(f"Auto-detected Zotero file: {unique[0]}")
        return str(unique[0])
    if not unique:
        raise SystemExit(
            "No Zotero CSL-JSON export found.\n"
            "Drop it in input/ or pass --zotero <file>."
        )
    raise SystemExit(
        "Multiple JSON files found in input/ — specify one with --zotero <file>.\n"
        + "\n".join(f"  {p}" for p in unique)
    )


def _fetch_one(stem: str, zrec: dict | None, email: str, quiet: bool) -> tuple[dict, str]:
    """Fetch from Crossref; fall back to Zotero fields or a stem-derived title search."""
    doi = (zrec.get("DOI", "") or "").strip() if zrec else ""

    if doi:
        msg = crossref.by_doi(doi, email)
        if msg:
            if not quiet:
                ui.info("  · Crossref DOI hit")
            return crossref.extract(msg), "crossref_doi"

    title_hint = (zrec.get("title", "") or "").strip() if zrec else ""
    if not title_hint:
        title_hint = stem.replace("_", " ")

    if title_hint:
        msg = crossref.by_title(title_hint, email)
        if msg:
            if not quiet:
                ui.info("  · Crossref title match")
            return crossref.extract(msg), "crossref_title"

    if zrec:
        if not quiet:
            ui.info("  · Zotero fields only (Crossref returned nothing)")
        return _from_zotero(zrec), "zotero"

    if not quiet:
        ui.warn("  · no match found")
    return {}, "none"


def _from_zotero(rec: dict) -> dict:
    """Extract normalised biblio fields from a Zotero CSL-JSON record."""
    authors = [
        {"family": a.get("family", ""), "given": a.get("given", "")}
        for a in rec.get("author", []) if a.get("family")
    ]
    year = None
    issued = rec.get("issued", {})
    if issued.get("date-parts"):
        try:
            year = int(issued["date-parts"][0][0])
        except (IndexError, TypeError, ValueError):
            pass
    container = rec.get("container-title", "")
    journal = container if isinstance(container, str) else (container[0] if container else "")
    doi = rec.get("DOI", "") or ""
    return {
        "title": rec.get("title", ""),
        "authors": authors,
        "year": year,
        "journal": journal,
        "doi": doi,
        "abstract": "",
        "publisher": rec.get("publisher", ""),
        "issn": None,
        "volume": rec.get("volume"),
        "issue": rec.get("issue"),
        "pages": rec.get("page"),
        "url": f"https://doi.org/{doi}" if doi else "",
    }
