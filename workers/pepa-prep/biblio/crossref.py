"""Crossref REST API client — DOI lookup and fuzzy title search.

All requests use stdlib urllib so no extra dependency is needed.
Rate limiting: 0.12 s between calls without an email, which keeps us under
the anonymous cap of ~10 req/s. Set CROSSREF_EMAIL / crossref_email in
config.yaml to join the polite pool (~50 req/s).
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

_BASE = "https://api.crossref.org"
_TIMEOUT = 20
_DELAY = 0.12
_TITLE_FIELDS = (
    "DOI,title,author,published,published-print,published-online,"
    "abstract,container-title,publisher,ISSN,volume,issue,page"
)


def _get(url: str, email: str = "") -> dict | None:
    headers = {}
    if email:
        headers["User-Agent"] = f"pepa-prep/1.0 (mailto:{email})"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise SystemExit(f"Crossref HTTP {e.code}: {e.reason}")
    except urllib.error.URLError:
        return None


def by_doi(doi: str, email: str = "") -> dict | None:
    time.sleep(_DELAY)
    url = f"{_BASE}/works/{urllib.parse.quote(doi, safe='/')}"
    data = _get(url, email)
    if not data or data.get("status") != "ok":
        return None
    return data["message"]


def by_title(title: str, email: str = "") -> dict | None:
    time.sleep(_DELAY)
    q = urllib.parse.quote(title)
    url = f"{_BASE}/works?query.title={q}&rows=1&select={_TITLE_FIELDS}"
    data = _get(url, email)
    if not data or data.get("status") != "ok":
        return None
    items = data["message"].get("items", [])
    return items[0] if items else None


def extract(msg: dict) -> dict:
    """Normalise a Crossref works message into a flat biblio dict."""
    if not msg:
        return {}

    title_parts = msg.get("title", [])
    title = title_parts[0] if title_parts else ""

    authors = [
        {"family": a.get("family", ""), "given": a.get("given", "")}
        for a in msg.get("author", [])
        if a.get("family")
    ]

    year = None
    for key in ("published", "published-print", "published-online", "created"):
        pub = msg.get(key)
        if pub and pub.get("date-parts"):
            try:
                year = int(pub["date-parts"][0][0])
                break
            except (IndexError, TypeError, ValueError):
                pass

    raw_abstract = msg.get("abstract", "") or ""
    abstract = re.sub(r"<[^>]+>", "", raw_abstract)
    abstract = re.sub(r"\s+", " ", abstract).strip()

    container = msg.get("container-title", [])
    journal = container[0] if container else ""

    issn_list = msg.get("ISSN", [])
    doi = msg.get("DOI", "")

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "doi": doi,
        "abstract": abstract,
        "publisher": msg.get("publisher", ""),
        "issn": issn_list[0] if issn_list else None,
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "pages": msg.get("page"),
        "url": f"https://doi.org/{doi}" if doi else "",
    }
