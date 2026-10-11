"""Ask OpenAlex and Crossref about a paper, and read the DOIs it prints on its first pages.
The lookup tries these free sources before the paid title search.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import config
from biblio.references import TITLE_SHARE, has_author, title_share

OPENALEX_FIELDS = "id,doi,title,authorships,publication_year,primary_location,cited_by_count,referenced_works,type"
CROSSREF_CANDIDATES = 3
PAUSE_SECONDS = 0.15
TIMEOUT_SECONDS = 30
# A DOI as papers print it; a regular expression because its shape has no simpler test.
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
DOI_TRAILING = ".,;:)]}'"
# Only the first pages, where a paper prints its own DOI; references further on cite other papers' DOIs.
OWN_DOI_CHARACTERS = 8000
OWN_DOIS_TRIED = 5
# A Crossref title also has to give back this share of its own words to the paper's name, which turns
# away a review or a translation that only quotes the title.
CROSSREF_REVERSE_SHARE = 0.5


def get_json(url, headers):
    """One JSON reply, or None when there is no such record or the service cannot be reached.

    Raises:
        SystemExit: OpenAlex says today's budget is used up, or a service answered with an error.
    """
    time.sleep(PAUSE_SECONDS)
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
            return json.loads(reply.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code == 429:
            raise SystemExit("OpenAlex or Crossref says today's budget is used up. Try again tomorrow.")
        raise SystemExit(f"A citation service answered with error {error.code}.")
    except (urllib.error.URLError, TimeoutError):
        return None


def openalex_url(path, parameters):
    """An OpenAlex address with the fields wanted and the key, when there is one."""
    query = dict(parameters, select=OPENALEX_FIELDS)
    if config.setting("openalex_api_key"):
        query["api_key"] = config.setting("openalex_api_key")
    return config.setting("openalex_url").rstrip("/") + path + "?" + urllib.parse.urlencode(query)


def openalex_by_doi(doi):
    """The OpenAlex work with this DOI, or None; OpenAlex charges nothing for a lookup by DOI."""
    return get_json(openalex_url("/works/https://doi.org/" + urllib.parse.quote(doi, safe="/"), {}), {})


def openalex_by_title(title):
    """OpenAlex's best match for a title, or None; each title search is paid."""
    reply = get_json(openalex_url("/works", {"search": title, "per-page": 1}), {})
    if not reply or not reply.get("results"):
        return None
    return reply["results"][0]


def own_dois(text_paths):
    """The DOIs printed on a paper's first pages, in the order they appear, without repeats."""
    if not text_paths:
        return []
    start = text_paths[0].read_text(encoding="utf-8", errors="replace")[:OWN_DOI_CHARACTERS]
    found = []
    for match in DOI_PATTERN.findall(start):
        doi = match.rstrip(DOI_TRAILING).lower()
        if doi not in found:
            found.append(doi)
    return found[:OWN_DOIS_TRIED]


def crossref_dois(work):
    """The DOIs of Crossref's closest records whose title and first author both match the paper name."""
    authors, _, title = work.partition("_")
    query = urllib.parse.urlencode({"query.bibliographic": f"{title} {authors}", "rows": CROSSREF_CANDIDATES, "select": "DOI,title,author"})
    reply = get_json(config.setting("crossref_url").rstrip("/") + "?" + query, {"User-Agent": "pepa-review"})
    if not reply:
        return []
    found = []
    for item in reply.get("message", {}).get("items", []):
        found_title = (item.get("title") or [""])[0]
        surnames = [author.get("family", "") for author in item.get("author", [])]
        if title_share(title, found_title) < TITLE_SHARE:
            continue
        if title_share(found_title.partition(":")[0], title) < CROSSREF_REVERSE_SHARE:
            continue
        if not has_author(work, surnames):
            continue
        found.append(item["DOI"])
    return found
