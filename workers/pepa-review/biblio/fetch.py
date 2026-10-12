"""Look each summarised paper up on OpenAlex, free sources first, and store what it finds in biblio.db.
Reviews anchor debates on it; the console reads citations.json.
"""
import json

import config
from biblio.ingest import upsert_citations, upsert_works
from biblio.references import TITLE_SHARE, export_doi, has_author, same_title
from biblio.schema import connect, ensure_schema
from biblio.sources import crossref_dois, openalex_by_doi, openalex_by_title, own_dois
from cli import ui
from corpus.metadata import work_list

# OpenAlex list price for one title search; lookups by DOI and Crossref searches are free.
SEARCH_DOLLARS = 0.001
CITATIONS_FILE = config.DATA_DIR / "citations.json"
# How a work was found, as stored in biblio.db, and how the run log words it.
SOURCE_NAMES = {
    "own_doi": "the DOI on its own pages",
    "export": "your Zotero references",
    "crossref": "a Crossref title search",
    "paid_search": "a paid OpenAlex title search",
}


# ---- Which papers ----

def work_of(base):
    """The work a paper belongs to: a book for one of its chapters, which pepa-prep names `<book>_<number>`."""
    head, _, tail = base.rpartition("_")
    if tail.isdigit() and "_" in head:
        return head
    return base


def works_to_fetch(force):
    """Each work still to look up, with the paper names it covers: a book once for all its chapters."""
    known = set()
    if config.BIBLIO_DB.exists() and not force:
        con = connect()
        ensure_schema(con)
        known = {row["base"] for row in con.execute("SELECT base FROM works").fetchall()}
        con.close()
    works = {}
    for paper in work_list():
        if paper["base"] not in known:
            works.setdefault(work_of(paper["base"]), []).append(paper["base"])
    return works


def text_paths(work):
    """The prepared text a work's own DOI is read from: the paper, or a book's first chapter."""
    paths = []
    for name in [f"text_{work}.md", f"text_{work}_01.md"]:
        if (config.TEXT_DIR / name).exists():
            paths.append(config.TEXT_DIR / name)
    return paths


# ---- Finding each work ----

def author_names(found):
    """The author names of an OpenAlex work."""
    names = []
    for authorship in found.get("authorships", []):
        names.append(authorship.get("author", {}).get("display_name", ""))
    return names


def first_confirmed(work, dois, need_author):
    """The first DOI whose OpenAlex work has the paper's title, and its author when asked, with how sure the match is, or None.

    Args:
        need_author: True for DOIs found by a search, where only the author tells a namesake apart.
    """
    title = work.partition("_")[2]
    for doi in dois:
        found = openalex_by_doi(doi)
        if found is None:
            continue
        share = same_title(title, found.get("title") or "")
        if share < TITLE_SHARE:
            continue
        if need_author and not has_author(work, author_names(found)):
            continue
        return {"work": found, "confidence": round(share, 2)}
    return None


def free_match(work, records):
    """The OpenAlex work for a paper from the free sources, with the source that gave its DOI, or None."""
    from_export = export_doi(work, records)
    sources = [
        {"key": "own_doi", "dois": own_dois(text_paths(work))},
        {"key": "export", "dois": [from_export] if from_export else []},
    ]
    for source in sources:
        match = first_confirmed(work, source["dois"], False)
        if match:
            return dict(match, source=source["key"])
    match = first_confirmed(work, crossref_dois(work), True)
    if match:
        return dict(match, source="crossref")
    return None


def paid_match(work):
    """The OpenAlex work for a paper from a paid title search, or None when the best result has another title."""
    title = work.partition("_")[2]
    found = openalex_by_title(title)
    if found is None:
        return None
    share = same_title(title, found.get("title") or "")
    if share < TITLE_SHARE or not has_author(work, author_names(found)):
        return None
    return {"work": found, "confidence": round(share, 2), "source": "paid_search"}


def work_row(base, match):
    """One works-table row from a found OpenAlex work, with how it was found."""
    found = match["work"]
    names = author_names(found)
    source = (found.get("primary_location") or {}).get("source") or {}
    return {
        "base": base,
        "doi": (found.get("doi") or "").replace("https://doi.org/", ""),
        "ext_id": found.get("id"),
        "title": found.get("title") or "",
        "authors": "; ".join(names),
        "venue": source.get("display_name", ""),
        "year": found.get("publication_year"),
        "type": found.get("type", ""),
        "cited_by_count": found.get("cited_by_count", 0),
        "concepts": "",
        "match_confidence": match["confidence"],
        "found_through": match["source"],
    }


# ---- The run ----

def fetch_estimate(records, force):
    """How many works the free sources should find and the most a paid title search for the rest could cost."""
    works = works_to_fetch(force)
    by_doi = 0
    for work in works:
        if own_dois(text_paths(work)) or export_doi(work, records):
            by_doi += 1
    by_search = len(works) - by_doi
    return {
        "papers": sum(len(bases) for bases in works.values()),
        "works": len(works),
        "by_doi": by_doi,
        "by_search": by_search,
        "dollars": 0.0,
        "paid_upto": by_search * SEARCH_DOLLARS,
        "model": "OpenAlex",
    }


def store(con, bases, match):
    """Store one found work for every paper it covers, with the works it cites."""
    for base in bases:
        upsert_works(con, [work_row(base, match)], None)
        con.execute("DELETE FROM citations WHERE citing_base = ?", (base,))
        cited = []
        for reference in match["work"].get("referenced_works", []):
            cited.append({"citing_base": base, "cited_ext_id": reference})
        upsert_citations(con, cited)


def forget(con, bases):
    """Drop what an earlier lookup stored for these papers, so a match no longer found does not linger."""
    for base in bases:
        con.execute("DELETE FROM works WHERE base = ?", (base,))
        con.execute("DELETE FROM citations WHERE citing_base = ?", (base,))
    con.commit()


def fetch(records, force, paid_search):
    """Look every work still missing up, free sources first and a paid title search only when asked, then rewrite citations.json."""
    works = works_to_fetch(force)
    ui.header("Look up citations on OpenAlex")
    ui.info(f"{len(works)} work(s) to look up; {len(records)} reference record(s)")
    order = "the DOI on its own pages, your Zotero references, Crossref"
    if paid_search:
        order += ", then a paid OpenAlex title search"
    ui.info(f"Order: {order}")
    con = connect()
    ensure_schema(con)
    counts = {}
    for number, work in enumerate(works, start=1):
        ui.info(f"[{number}/{len(works)}] {work}")
        match = free_match(work, records)
        if match is None and paid_search:
            match = paid_match(work)
        if match is None:
            counts["not found"] = counts.get("not found", 0) + 1
            ui.warn("  not found")
            forget(con, works[work])
            continue
        source = SOURCE_NAMES[match["source"]]
        counts[f"by {source}"] = counts.get(f"by {source}", 0) + 1
        ui.info(f"  found through {source}")
        store(con, works[work], match)
    con.close()
    write_citations_file()
    summary = ", ".join(f"{count} {source}" for source, count in counts.items())
    ui.ok(f"{summary}; citations.json written")


def write_citations_file():
    """Write each stored paper's facts and its citations within the library to data/citations.json."""
    con = connect()
    ensure_schema(con)
    papers = {}
    for row in con.execute("SELECT * FROM works WHERE match_confidence >= ?", (config.BIBLIO_MIN_CONFIDENCE,)).fetchall():
        authors = row["authors"].split("; ") if row["authors"] else []
        papers[row["base"]] = {
            "title": row["title"] or "",
            "authors": authors,
            "type": row["type"] or "",
            "found_through": row["found_through"] or "",
            "year": row["year"],
            "venue": row["venue"] or "",
            "doi": row["doi"] or "",
            "cited_by_count": row["cited_by_count"] or 0,
            "cites": [],
            "cited_by": [],
        }
    for edge in con.execute("SELECT citing_base, cited_base FROM citations WHERE cited_base IS NOT NULL").fetchall():
        if edge["citing_base"] in papers and edge["cited_base"] in papers:
            papers[edge["citing_base"]]["cites"].append(edge["cited_base"])
            papers[edge["cited_base"]]["cited_by"].append(edge["citing_base"])
    con.close()
    CITATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CITATIONS_FILE.write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
