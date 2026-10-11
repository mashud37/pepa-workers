"""Read the citation facts pepa-review stores after looking papers up on OpenAlex, and start a lookup.
The Citations tab and each paper page show them.
"""
from pathlib import Path

from web import connections, estimates, jobs, paths

CITATIONS_FILE = Path("pepa-review") / "data" / "citations.json"
# The Zotero export the lookup matches DOIs from, kept in the project so the next lookup finds it again.
ZOTERO_FILE = Path("pepa-console") / "zotero.json"
SHOWN = 20


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


def overview():
    """What the Citations tab shows: how many papers are looked up, the most cited, and the most cited here."""
    data = citation_data()
    if data is None:
        return None
    return {
        "papers": len(data),
        "most_cited": ranked(data, key=lambda facts: facts["cited_by_count"]),
        "most_cited_here": ranked(data, key=lambda facts: len(facts["cited_by"])),
    }


def zotero_file():
    """The kept Zotero export, or None when none has been added."""
    path = paths.project_folder() / ZOTERO_FILE
    return path if path.is_file() else None


def save_zotero(upload):
    """Keep an uploaded Zotero CSL-JSON export in the project, replacing the one before.

    Raises:
        ValueError: the file is not a .json file.
    """
    if not upload.filename.lower().endswith(".json"):
        raise ValueError("Export from Zotero as CSL JSON; the file ends in .json.")
    path = paths.project_folder() / ZOTERO_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    upload.save(path)


def lookup_flags():
    """The arguments a lookup runs with: fetch, and the Zotero export when there is one."""
    flags = ["fetch"]
    if zotero_file():
        flags = flags + ["--zotero", str(zotero_file())]
    return flags


def lookup_estimate():
    """What looking the papers up will cost, worded, or None when pepa-review could not say."""
    return estimates.estimate("pepa-review", "biblio", lookup_flags())


def start_lookup():
    """Start pepa-review looking the papers up on OpenAlex as a job, and return the job's id."""
    values = {"subcmd": "fetch"}
    if zotero_file():
        values["--zotero"] = str(zotero_file())
    return jobs.start_job("pepa-review", "biblio", values)
