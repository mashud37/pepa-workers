"""Run the bibliography enrichment pipeline: match pepa-sum files to Zotero records,
fetch OpenAlex metadata, and write one biblio JSON file per paper.
"""
from pathlib import Path

from biblio import match, openalex, opencitations, write
from extract import config as cfg_mod

from . import ui


def _access_note(api_key: str, email: str) -> str:
    if api_key:
        return "premium key set"
    if email:
        return f"polite pool: {email}"
    return "free route (set openalex_email in config.yaml for the polite pool)"


def run(cfg: dict, zotero=None, cite=False, force=False, quiet=False) -> None:
    corpus_dir = Path(cfg.get("biblio_corpus", "../pepa-sum/output"))
    out_dir = Path(cfg.get("biblio_output", cfg.get("output_folder", "./output"))) / "biblio"
    email = cfg.get("openalex_email", "")
    api_key = cfg_mod.openalex_api_key()

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

    # Announce the full pipeline before any blocking call (liveness rule)
    ui.header("pepa-prep: bibliography enrichment")
    ui.info(f"{n} paper(s) found in corpus")
    ui.info(f"Output folder: {out_dir.resolve()}")
    ui.info(f"OpenAlex: {_access_note(api_key, email)}")
    _show_plan(cite, total_steps)

    ui.step(f"Step 1/{total_steps}: Match Zotero library")
    records = match.load_zotero(zotero_path)
    ui.info(f"loaded {len(records)} records from {Path(zotero_path).name}")
    matches = match.match_all(stems, records)
    n_matched = sum(1 for v in matches.values() if v)
    ui.ok(f"{n_matched}/{n} matched  ·  {n - n_matched} will use OpenAlex title search")

    ui.step(f"Step 2/{total_steps}: Fetch OpenAlex + write output")
    opts = {"email": email, "api_key": api_key, "force": force, "quiet": quiet}
    result = _fetch_and_write(stems, matches, out_dir, opts)
    ui.ok(f"{result['done']} written  ·  {result['skipped']} skipped  ·  "
          f"{result['errors']} failed")

    if not cite:
        _done_summary(out_dir, result["done"])
        return

    ui.step(f"Step 4/{total_steps}: Fetch citation networks (OpenCitations)")
    cited = _fetch_citations(stems, out_dir, quiet)
    ui.ok(f"{cited['done']} enriched  ·  {cited['skipped']} skipped (no DOI)")
    _done_summary(out_dir, result["done"])


def _fetch_and_write(stems: list, matches: dict, out_dir: Path, opts: dict) -> dict:
    """Fetch bibliographic data for each stem and write it to disk.

    Returns:
        {"done": files written, "skipped": files left as-is, "errors": failed lookups}.
    """
    n = len(stems)
    done = skipped = errors = 0
    for i, stem in enumerate(stems, 1):
        ui.info(f"[{i}/{n}] {stem}")  # always before the blocking API call

        if not opts["force"] and write.exists(out_dir, stem):
            skipped += 1
            if not opts["quiet"]:
                ui.info("  · skip (exists)")
            continue

        try:
            zrec = matches.get(stem)
            fetched = _fetch_one(stem, zrec, opts["email"], opts["api_key"], opts["quiet"])
            biblio_data = fetched["data"]
            biblio_data.update({
                "source_file": f"sum_{stem}.md",
                "stem": stem,
                "match_source": fetched["source"],
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
    return {"done": done, "skipped": skipped, "errors": errors}


def _fetch_citations(stems: list, out_dir: Path, quiet: bool) -> dict:
    """Fetch citation networks for every stem that already has a DOI on file.

    Returns:
        {"done": files enriched, "skipped": files with no biblio record or no DOI}.
    """
    n = len(stems)
    done = skipped = 0
    for i, stem in enumerate(stems, 1):
        ui.info(f"[{i}/{n}] {stem}")  # always before the blocking API call
        existing = write.load(out_dir, stem)
        if not existing:
            skipped += 1
            continue
        doi = existing.get("doi", "")
        if not doi:
            skipped += 1
            if not quiet:
                ui.info("  · no DOI, skipping")
            continue
        existing["references"] = opencitations.references(doi)
        existing["cited_by"] = opencitations.citations(doi)
        write.save(out_dir, stem, existing)
        done += 1
    return {"done": done, "skipped": skipped}


def _show_plan(cite: bool, total_steps: int) -> None:
    steps = [
        f"[1/{total_steps}] match Zotero",
        f"[2/{total_steps}] fetch OpenAlex",
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
        "Multiple JSON files found in input/, specify one with --zotero <file>.\n"
        + "\n".join(f"  {p}" for p in unique)
    )


def _fetch_one(stem: str, zrec: dict | None, email: str, api_key: str, quiet: bool) -> dict:
    """Fetch from OpenAlex; fall back to Zotero fields or a stem-derived title search.

    Returns:
        {"data": biblio fields, "source": "openalex_doi" | "openalex_title" | "zotero" | "none"}.
    """
    doi = (zrec.get("DOI", "") or "").strip() if zrec else ""

    if doi:
        msg = openalex.by_doi(doi, email, api_key)
        if msg:
            if not quiet:
                ui.info("  · OpenAlex DOI hit")
            return {"data": openalex.extract(msg), "source": "openalex_doi"}

    title_hint = (zrec.get("title", "") or "").strip() if zrec else ""
    if not title_hint:
        title_hint = stem.replace("_", " ")

    if title_hint:
        msg = openalex.by_title(title_hint, email, api_key)
        if msg:
            if not quiet:
                ui.info("  · OpenAlex title match")
            return {"data": openalex.extract(msg), "source": "openalex_title"}

    if zrec:
        if not quiet:
            ui.info("  · Zotero fields only (OpenAlex returned nothing)")
        return {"data": _from_zotero(zrec), "source": "zotero"}

    if not quiet:
        ui.warn("  · no match found")
    return {"data": {}, "source": "none"}


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
    if isinstance(container, str):
        journal = container
    elif container:
        journal = container[0]
    else:
        journal = ""
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
