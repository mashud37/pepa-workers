"""Read a reference manager's export (CSL JSON, BibTeX or RIS) and find the DOI it holds for a paper.
The OpenAlex lookup tries these DOIs before any title search.
"""
import json
from pathlib import Path

# A record matches a paper when at least this share of the paper name's title words are in its title.
TITLE_SHARE = 0.7
SUFFIXES = [
    ".json",
    ".bib",
    ".ris",
]


def name_words(text):
    """The words of a title or paper name longer than two letters, lower case, without punctuation."""
    spaced = ""
    for character in text.lower():
        spaced += character if character.isalnum() else " "
    words = []
    for word in spaced.split():
        if len(word) > 2:
            words.append(word)
    return words


def title_share(wanted, found):
    """The share of the wanted title's words that appear in the found title, from 0 to 1.

    A word also counts when the found title has it split, as file names write "enduser" for "End-user".
    """
    wanted_words = name_words(wanted)
    found_words = set(name_words(found))
    found_joined = "".join(name_words(found))
    if not wanted_words:
        return 0.0
    matched = 0
    for word in wanted_words:
        if word in found_words or word in found_joined:
            matched += 1
    return matched / len(wanted_words)


def has_author(work, names):
    """True when the first surname in a paper name is among the given author names, however hyphenated."""
    wanted = name_words(work.partition("_")[0])
    if not wanted:
        return True
    return wanted[0] in "".join(name_words(" ".join(names)))


def same_title(name_title, found):
    """How well a paper name's title and a found title agree, either way round, since either may be cut short."""
    return max(title_share(name_title, found), title_share(found, name_title))


def csl_records(entries):
    """Records from CSL JSON entries, as Zotero's "CSL JSON" export and its local API give them."""
    records = []
    for entry in entries:
        families = [author.get("family", "") for author in entry.get("author", [])]
        records.append({"title": entry.get("title", ""), "doi": entry.get("DOI", ""), "authors": families})
    return records


def bibtex_value(line):
    """The value of one `key = {value},` line of a BibTeX entry, without braces or quotes."""
    value = line.partition("=")[2].strip().rstrip(",").strip()
    return value.replace("{", "").replace("}", "").strip('"')


def bibtex_record(entry):
    """One BibTeX entry's title, DOI and author surnames, one field per line as Zotero writes it."""
    record = {"title": "", "doi": "", "authors": []}
    for line in entry.splitlines():
        key = line.partition("=")[0].strip().lower()
        if key == "title":
            record["title"] = bibtex_value(line)
        elif key == "doi":
            record["doi"] = bibtex_value(line)
        elif key == "author":
            for name in bibtex_value(line).split(" and "):
                record["authors"].append(name.partition(",")[0].strip())
    return record


def bibtex_records(text):
    """Records from a BibTeX export."""
    records = []
    for entry in ("\n" + text).split("\n@")[1:]:
        records.append(bibtex_record(entry))
    return records


def ris_records(text):
    """Records from an RIS export: TI or T1 the title, DO the DOI, AU each author, ER the end."""
    records = []
    record = {"title": "", "doi": "", "authors": []}
    for line in text.splitlines():
        tag = line[:2]
        value = line[6:].strip()
        if tag in ("TI", "T1") and not record["title"]:
            record["title"] = value
        elif tag == "DO":
            record["doi"] = value
        elif tag == "AU":
            record["authors"].append(value.partition(",")[0].strip())
        elif tag == "ER":
            records.append(record)
            record = {"title": "", "doi": "", "authors": []}
    return records


def load_references(path_text):
    """Every record of an export file, each {"title", "doi", "authors"}, or [] when no file is given.

    Raises:
        SystemExit: the file is missing or is not CSL JSON, BibTeX or RIS.
    """
    if not path_text:
        return []
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"Reference export not found: {path_text}")
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return csl_records(json.loads(text))
    if suffix == ".bib":
        return bibtex_records(text)
    if suffix == ".ris":
        return ris_records(text)
    raise SystemExit("Export from Zotero as CSL JSON, BibTeX or RIS.")


def export_doi(work, records):
    """The DOI an export holds for a paper, matched by title words and first author, or ""."""
    authors, _, title = work.partition("_")
    first_author = name_words(authors)[0] if name_words(authors) else ""
    for record in records:
        if not record["doi"] or title_share(title, record["title"]) < TITLE_SHARE:
            continue
        surnames = " ".join(record["authors"]).lower()
        if not first_author or first_author in surnames:
            return record["doi"].strip()
    return ""
