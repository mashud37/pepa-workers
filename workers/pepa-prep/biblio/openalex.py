"""Look up works on OpenAlex by DOI or fuzzy title match over the REST API,
using stdlib urllib only.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

_BASE = "https://api.openalex.org"
_TIMEOUT = 20
_DELAY = 0.12
_SELECT_FIELDS = (
    "doi,title,authorships,publication_year,primary_location,"
    "abstract_inverted_index,biblio"
)


def _query(email: str, api_key: str) -> str:
    params = {"select": _SELECT_FIELDS}
    if email:
        params["mailto"] = email
    if api_key:
        params["api_key"] = api_key
    return urllib.parse.urlencode(params)


def _get(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise SystemExit(f"OpenAlex HTTP {e.code}: {e.reason}")
    except urllib.error.URLError:
        return None


def by_doi(doi: str, email: str = "", api_key: str = "") -> dict | None:
    time.sleep(_DELAY)
    encoded_doi = urllib.parse.quote(doi, safe="/")
    url = f"{_BASE}/works/https://doi.org/{encoded_doi}?{_query(email, api_key)}"
    return _get(url)


def by_title(title: str, email: str = "", api_key: str = "") -> dict | None:
    time.sleep(_DELAY)
    q = urllib.parse.quote(title)
    url = f"{_BASE}/works?search={q}&per-page=1&{_query(email, api_key)}"
    data = _get(url)
    if not data:
        return None
    items = data.get("results", [])
    return items[0] if items else None


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """Turn OpenAlex's word-to-positions index back into a plain sentence."""
    if not inverted_index:
        return ""
    slots = []
    for word, positions in inverted_index.items():
        for position in positions:
            slots.append((position, word))
    slots.sort()
    return " ".join(word for _, word in slots)


def extract(msg: dict) -> dict:
    """Normalise an OpenAlex work into a flat biblio dict."""
    if not msg:
        return {}

    authors = []
    for authorship in msg.get("authorships", []):
        name = authorship.get("author", {}).get("display_name", "")
        if not name:
            continue
        name_parts = name.split()
        family = name_parts[-1] if name_parts else ""
        given = " ".join(name_parts[:-1])
        authors.append({"family": family, "given": given})

    source = (msg.get("primary_location") or {}).get("source") or {}
    biblio_info = msg.get("biblio") or {}
    first_page = biblio_info.get("first_page")
    last_page = biblio_info.get("last_page")
    if first_page and last_page:
        pages = f"{first_page}-{last_page}"
    else:
        pages = first_page or ""

    doi = (msg.get("doi") or "").replace("https://doi.org/", "")

    return {
        "title": msg.get("title") or "",
        "authors": authors,
        "year": msg.get("publication_year"),
        "journal": source.get("display_name", ""),
        "doi": doi,
        "abstract": _reconstruct_abstract(msg.get("abstract_inverted_index")),
        "publisher": source.get("host_organization_name") or "",
        "issn": source.get("issn_l"),
        "volume": biblio_info.get("volume"),
        "issue": biblio_info.get("issue"),
        "pages": pages,
        "url": f"https://doi.org/{doi}" if doi else "",
    }
