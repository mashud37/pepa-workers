"""OpenCitations COCI API client — references and citation lookups by DOI.

Returns lists of DOI strings so callers stay decoupled from the raw API shape.
All requests use stdlib urllib. A 0.25 s delay respects the service's fair-use
guidance; OpenCitations has no hard rate limit but requests politeness.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

_BASE = "https://opencitations.net/index/api/v1"
_TIMEOUT = 20
_DELAY = 0.25


def _get(url: str) -> list:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data if isinstance(data, list) else []
    except (urllib.error.URLError, urllib.error.HTTPError):
        return []


def references(doi: str) -> list[str]:
    """DOIs of papers that this paper cites."""
    time.sleep(_DELAY)
    url = f"{_BASE}/references/{urllib.parse.quote(doi, safe='/')}"
    return [item.get("cited", "") for item in _get(url) if item.get("cited")]


def citations(doi: str) -> list[str]:
    """DOIs of papers that cite this paper."""
    time.sleep(_DELAY)
    url = f"{_BASE}/citations/{urllib.parse.quote(doi, safe='/')}"
    return [item.get("citing", "") for item in _get(url) if item.get("citing")]
