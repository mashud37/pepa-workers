"""Look each summarised paper up on OpenAlex, by DOI from a Zotero export or else by title, into biblio.db.
Reviews anchor debates on it; the console reads citations.json.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config
from biblio.ingest import upsert_citations, upsert_works
from biblio.schema import connect, ensure_schema
from cli import ui
from corpus.metadata import work_list

OPENALEX_FIELDS = "id,doi,title,authorships,publication_year,primary_location,cited_by_count,referenced_works,type"
# OpenAlex list prices: a lookup by DOI is free, a title search costs $1 per thousand.
SEARCH_DOLLARS = 0.001
PAUSE_SECONDS = 0.12
TIMEOUT_SECONDS = 20
# A Zotero record matches a paper when at least this many of the paper name's words are in its title or authors.
ZOTERO_MATCH_WORDS = 2
CITATIONS_FILE = config.DATA_DIR / "citations.json"


# ---- Zotero ----

def load_zotero(zotero_file):
    """The records of a Zotero CSL-JSON export, or an empty list when no file is given."""
    if not zotero_file:
        return []
    path = Path(zotero_file)
    if not path.exists():
        raise SystemExit(f"Zotero file not found: {zotero_file}")
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SystemExit(f"Expected a CSL-JSON list in {zotero_file}; export from Zotero as CSL JSON.")
    return records


def name_words(base):
    """The words of a paper name longer than two letters, lower case."""
    words = []
    for word in base.replace("_", " ").replace("-", " ").lower().split():
        if len(word) > 2:
            words.append(word)
    return words


def zotero_doi(base, records):
    """The DOI of the Zotero record that best matches this paper name, or "" when none matches well enough."""
    words = name_words(base)
    best_doi = ""
    best_count = ZOTERO_MATCH_WORDS - 1
    for record in records:
        title = record.get("title", "").lower()
        authors = ""
        for author in record.get("author", []):
            authors += " " + author.get("family", "").lower()
        count = 0
        for word in words:
            if word in title or word in authors:
                count += 1
        if count > best_count:
            best_count = count
            best_doi = (record.get("DOI") or "").strip()
    return best_doi


# ---- OpenAlex ----

def openalex_get(path, parameters):
    """One OpenAlex reply as a dict, or None when it has no such work or cannot be reached."""
    query = dict(parameters, select=OPENALEX_FIELDS)
    if config.setting("openalex_api_key"):
        query["api_key"] = config.setting("openalex_api_key")
    url = config.setting("openalex_url").rstrip("/") + path + "?" + urllib.parse.urlencode(query)
    time.sleep(PAUSE_SECONDS)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as reply:
            return json.loads(reply.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code == 429:
            raise SystemExit("OpenAlex says today's budget is used up. Try again tomorrow, or add an OpenAlex key.")
        raise SystemExit(f"OpenAlex answered with error {error.code}.")
    except urllib.error.URLError:
        return None


def look_up(base, doi):
    """The OpenAlex work for a paper and how sure the match is: 1.0 by DOI, the share of title words matched by title."""
    if doi:
        found = openalex_get("/works/https://doi.org/" + urllib.parse.quote(doi, safe="/"), {})
        if found:
            return {"work": found, "confidence": 1.0}
    title = base.split("_", 1)[-1]
    reply = openalex_get("/works", {"search": title, "per-page": 1})
    if not reply or not reply.get("results"):
        return {"work": None, "confidence": 0.0}
    found = reply["results"][0]
    wanted = name_words(title)
    found_title = (found.get("title") or "").lower()
    matched = 0
    for word in wanted:
        if word in found_title:
            matched += 1
    return {"work": found, "confidence": round(matched / max(1, len(wanted)), 2)}


def work_row(base, found, confidence):
    """One works-table row from an OpenAlex work."""
    names = []
    for authorship in found.get("authorships", []):
        names.append(authorship.get("author", {}).get("display_name", ""))
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
        "match_confidence": confidence,
    }


# ---- The run ----

def papers_to_fetch(force):
    """Every summarised paper, less those biblio.db already holds unless `force`."""
    bases = [work["base"] for work in work_list()]
    if force or not config.BIBLIO_DB.exists():
        return bases
    con = connect()
    ensure_schema(con)
    known = {row["base"] for row in con.execute("SELECT base FROM works").fetchall()}
    con.close()
    return [base for base in bases if base not in known]


def fetch_estimate(zotero_file, force):
    """How many lookups a fetch makes, by DOI (free) and by title (paid), and their cost at list price."""
    records = load_zotero(zotero_file)
    bases = papers_to_fetch(force)
    by_doi = 0
    for base in bases:
        if zotero_doi(base, records):
            by_doi += 1
    by_title = len(bases) - by_doi
    return {"papers": len(bases), "by_doi": by_doi, "by_title": by_title, "dollars": by_title * SEARCH_DOLLARS, "model": "OpenAlex"}


def fetch(zotero_file, force):
    """Look every paper still missing up on OpenAlex, store each one as it arrives, and rewrite citations.json."""
    records = load_zotero(zotero_file)
    bases = papers_to_fetch(force)
    ui.header("Look up citations on OpenAlex")
    ui.info(f"{len(bases)} paper(s) to look up; {len(records)} Zotero record(s) to match DOIs from")
    con = connect()
    ensure_schema(con)
    found_count = 0
    for number, base in enumerate(bases, start=1):
        ui.info(f"[{number}/{len(bases)}] {base}")
        result = look_up(base, zotero_doi(base, records))
        if result["work"] is None:
            ui.warn("  not found on OpenAlex")
            continue
        upsert_works(con, [work_row(base, result["work"], result["confidence"])], None)
        con.execute("DELETE FROM citations WHERE citing_base = ?", (base,))
        cited = []
        for reference in result["work"].get("referenced_works", []):
            cited.append({"citing_base": base, "cited_ext_id": reference})
        upsert_citations(con, cited)
        found_count += 1
    con.close()
    write_citations_file()
    ui.ok(f"{found_count} of {len(bases)} found; citations.json written")


def write_citations_file():
    """Write each stored paper's facts and its citations within the library to data/citations.json."""
    con = connect()
    ensure_schema(con)
    papers = {}
    for row in con.execute("SELECT * FROM works WHERE match_confidence >= ?", (config.BIBLIO_MIN_CONFIDENCE,)).fetchall():
        papers[row["base"]] = {
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
