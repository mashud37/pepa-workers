"""Read the citation facts pepa-review stores after looking papers up on OpenAlex, and start a lookup.
The Citations tab and each paper page show them.
"""
import os
import urllib.error
import urllib.request
from pathlib import Path

from web import connections, estimates, jobs, paths

CITATIONS_FILE = Path("pepa-review") / "data" / "citations.json"
# The reference export the lookup takes DOIs from, kept in the project so the next lookup finds it again.
EXPORT_FILE = Path("pepa-console") / "references"
EXPORT_SUFFIXES = [
    ".json",
    ".bib",
    ".ris",
]
SHOWN = 20
# Zotero's local API, which pepa-review reads the library through; the same variable moves both.
ZOTERO_URL = os.environ.get("PEPAREVIEW_ZOTERO_URL", "http://localhost:23119/api")
ZOTERO_TIMEOUT_SECONDS = 2
# How pepa-review found each paper, as it stores it, worded for the page.
FOUND_THROUGH = {
    "own_doi": "The DOI printed in the paper",
    "export": "Your Zotero references",
    "crossref": "A Crossref title search",
    "paid_search": "A paid OpenAlex title search",
}
# The RIS type of each OpenAlex work type; any other type is exported as generic.
RIS_TYPES = {
    "article": "JOUR",
    "book": "BOOK",
    "book-chapter": "CHAP",
}


def citation_data():
    """Every looked-up paper's facts, keyed by paper name, or None before the first lookup."""
    path = paths.project_folder() / CITATIONS_FILE
    if not path.exists():
        return None
    return connections.load_json(path)


def paper_facts(stem):
    """One paper's year, venue, DOI, citation count and its citations within the library, or None."""
    data = citation_data()
    if data is None or stem not in data:
        return None
    facts = dict(data[stem])
    facts["found_through"] = FOUND_THROUGH.get(facts.get("found_through", ""), "")
    facts["cites"] = [connections.named(other) for other in facts["cites"]]
    facts["cited_by"] = [connections.named(other) for other in facts["cited_by"]]
    return facts


def ranked(data, key):
    """The papers with the highest number under `key`, highest first, each named with that number."""
    rows = []
    for stem, facts in data.items():
        paper = connections.named(stem)
        paper["count"] = key(facts)
        paper["year"] = facts["year"]
        if paper["count"]:
            rows.append(paper)
    rows.sort(key=lambda paper: -paper["count"])
    return rows[:SHOWN]


def found_counts(data):
    """How many papers each source found, most first, with the source worded for the page."""
    counts = {}
    for facts in data.values():
        source = FOUND_THROUGH.get(facts.get("found_through", ""), "Not recorded")
        counts[source] = counts.get(source, 0) + 1
    rows = []
    for source, count in counts.items():
        rows.append({"source": source, "count": count})
    rows.sort(key=lambda row: -row["count"])
    return rows


def overview():
    """What the Citations tab shows: how many papers are looked up and how, the most cited, and the most cited here."""
    data = citation_data()
    if data is None:
        return None
    return {
        "papers": len(data),
        "found": found_counts(data),
        "most_cited": ranked(data, key=lambda facts: facts["cited_by_count"]),
        "most_cited_here": ranked(data, key=lambda facts: len(facts["cited_by"])),
    }


def export_file():
    """The kept reference export, or None when none has been added."""
    for suffix in EXPORT_SUFFIXES:
        path = paths.project_folder() / EXPORT_FILE.with_suffix(suffix)
        if path.is_file():
            return path
    return None


def save_export(upload):
    """Keep an uploaded reference export in the project, replacing the one before.

    Raises:
        ValueError: the file is not CSL JSON, BibTeX or RIS.
    """
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in EXPORT_SUFFIXES:
        raise ValueError("Export from Zotero as CSL JSON, BibTeX or RIS.")
    kept = export_file()
    if kept is not None:
        kept.unlink()
    path = paths.project_folder() / EXPORT_FILE.with_suffix(suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    upload.save(path)


def zotero_status():
    """How Zotero answers: "connected" with its number of items, "off" when its local API is not enabled, or "closed"."""
    url = ZOTERO_URL.rstrip("/") + "/users/0/items/top?limit=1&format=keys"
    try:
        with urllib.request.urlopen(url, timeout=ZOTERO_TIMEOUT_SECONDS) as reply:
            return {"state": "connected", "count": int(reply.headers.get("Total-Results", "0"))}
    except urllib.error.HTTPError:
        return {"state": "off", "count": 0}
    except (urllib.error.URLError, TimeoutError):
        return {"state": "closed", "count": 0}


def reference_source():
    """Where the lookup reads reference records from: the running Zotero app when it can, else the kept export, else nowhere."""
    status = zotero_status()
    if status["state"] == "connected":
        noun = "item" if status["count"] == 1 else "items"
        return {"zotero": True, "export": None, "words": f"Using your Zotero library, {status['count']:,} {noun}."}
    kept = export_file()
    if kept is not None:
        return {"zotero": False, "export": kept, "words": f"Using your export {kept.name}."}
    return {"zotero": False, "export": None, "words": ""}


def lookup_estimate(source):
    """What looking the papers up will cost, worded, or None when pepa-review could not say."""
    flags = ["fetch"]
    if source["zotero"]:
        flags = flags + ["--zotero-local"]
    elif source["export"]:
        flags = flags + ["--zotero", str(source["export"])]
    return estimates.estimate("pepa-review", "biblio", flags)


def start_lookup(paid_search):
    """Start pepa-review looking the papers up as a job, with a paid title search for the rest when asked, and return the job's id."""
    source = reference_source()
    values = {"subcmd": "fetch"}
    if source["zotero"]:
        values["--zotero-local"] = "on"
    elif source["export"]:
        values["--zotero"] = str(source["export"])
    if paid_search:
        values["--paid-search"] = "on"
    return jobs.start_job("pepa-review", "biblio", values)


def ris_record(stem, facts):
    """One paper as an RIS record, from what OpenAlex holds on it, or from its file name when it was not looked up."""
    name = connections.named(stem)
    authors = facts.get("authors") or [name["authors"]]
    lines = [f"TY  - {RIS_TYPES.get(facts.get('type', ''), 'GEN')}"]
    for author in authors:
        lines.append(f"AU  - {author}")
    lines.append(f"TI  - {facts.get('title') or name['title']}")
    if facts.get("year"):
        lines.append(f"PY  - {facts['year']}")
    if facts.get("venue"):
        lines.append(f"T2  - {facts['venue']}")
    if facts.get("doi"):
        lines.append(f"DO  - {facts['doi']}")
    lines.append("ER  - ")
    return "\n".join(lines)


def ris_text(stems):
    """The papers as an RIS file that Zotero, EndNote or Mendeley can import."""
    data = citation_data() or {}
    records = []
    for stem in stems:
        records.append(ris_record(stem, data.get(stem, {})))
    return "\n\n".join(records) + "\n"
