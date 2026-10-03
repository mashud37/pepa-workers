"""CLI layer for manual chapter correction of extracted books."""
import difflib
import tempfile
from pathlib import Path

from extract import split as split_mod

from . import ui

_MAX_STEM = 60
_PAGE = 20


def _trunc(s: str) -> str:
    return s if len(s) <= _MAX_STEM else s[: _MAX_STEM - 3] + "..."


def _state(book: split_mod.Book) -> str:
    kb = f"{book.size / 1024:,.0f} KB"
    if book.kind == "single":
        return f"single block, {kb}"
    return f"{book.nchap} chapters, {kb}"


def run(cfg: dict, file: str | None = None) -> None:
    out_dir = Path(cfg["output_folder"]) / "text"
    if not out_dir.is_dir():
        raise SystemExit(f"No extracted text found in {out_dir}: run extract first")

    books = split_mod.list_books(out_dir)
    if not books:
        ui.ok("No extracted books found: run extract first")
        return

    book = _resolve_file(file, books) if file else _pick_book(books)
    if book is None:
        return

    _run_editor(book, out_dir)


def _resolve_file(file: str, books: dict[str, split_mod.Book]) -> split_mod.Book:
    """Map a --file path or stem to a known book."""
    name = Path(file).name
    m = split_mod._CHAPTER_FILE_RE.match(name)
    if m:
        stem = m.group(1)
    elif name.startswith("text_") and name.endswith(".md"):
        stem = name[len("text_"):-len(".md")]
    else:
        stem = name.removesuffix(".md").removeprefix("text_")

    book = books.get(stem)
    if book is None:
        raise SystemExit(
            f"'{stem}' is not a known book.\n"
            f"Run without --file to search the list."
        )
    return book


def _pick_book(books: dict[str, split_mod.Book]) -> split_mod.Book | None:
    stems = sorted(books)
    ui.step(f"Books available for manual correction  [{len(stems)} total]")
    ui.info("To mark chapter starts on pictures of the pages instead, use the Papers page in pepa-console.")

    while True:
        query = ui.ask("Search author/title (blank = list all, 0 = back)", default="")
        if query == "0":
            return None
        terms = query.lower().split()
        matches = [s for s in stems if all(_mentions(s, t) for t in terms)]
        if not matches:
            ui.warn("No books match, try a different term")
            continue
        book = _choose(books, matches)
        if book is not None:
            return book


def _mentions(stem: str, term: str) -> bool:
    """True when the term is in the book's name, or close to one of its words, so a typo still finds it."""
    words = stem.lower().replace("_", " ").split()
    return term in stem.lower() or bool(difflib.get_close_matches(term, words, cutoff=0.8))


def _choose(books: dict[str, split_mod.Book],
            matches: list[str]) -> split_mod.Book | None:
    offset = 0
    while True:
        batch = matches[offset: offset + _PAGE]
        options = [(_trunc(s), _state(books[s])) for s in batch]
        more = offset + _PAGE < len(matches)
        if more:
            options.append(("More …", f"next {min(_PAGE, len(matches) - offset - _PAGE)}"))

        idx = ui.menu(
            f"Select a book  [{offset + 1}–{offset + len(batch)} of {len(matches)}]",
            options,
        )
        if idx is None:
            return None
        if more and idx == len(batch):
            offset += _PAGE
            continue
        return books[batch[idx]]


def _run_editor(book: split_mod.Book, out_dir: Path) -> None:
    ui.step(f"Correct: {_trunc(book.stem)}")
    ui.info(f"State: {_state(book)}")
    ui.info("")
    if book.kind == "single":
        ui.info("The file will open in your editor.")
        ui.info("Add a line containing exactly:  <!-- chapter -->")
        ui.info("at each point where a new chapter begins, then save and close.")
    else:
        ui.info("The chapters will open as one file, current boundaries marked.")
        ui.info("Move, add, or remove  <!-- chapter -->  lines, then save and close.")

    if not ui.confirm("Open editor now?"):
        ui.info("Cancelled")
        return

    with tempfile.NamedTemporaryFile(
        suffix=".md", prefix=f"pepa_split_{book.stem[:30]}_",
        delete=False, dir=out_dir, mode="w", encoding="utf-8"
    ) as tf:
        tmp_path = Path(tf.name)

    try:
        split_mod.prepare_editor_file(book, tmp_path)
        split_mod.open_editor(tmp_path)

        ui.step("Applying markers")
        applied = split_mod.apply_markers(tmp_path, book, out_dir)
        count, warnings = applied["count"], applied["warnings"]

        for w in warnings:
            ui.warn(w)

        if count >= 2:
            ui.ok(f"Wrote {count} chapter file(s):")
            width = max(2, len(str(count)))
            for i in range(1, count + 1):
                name = f"text_{book.stem}_{i:0{width}d}.md"
                size = (out_dir / name).stat().st_size
                ui.info(f"  {name}  ({size:,} bytes)")
        elif count == 1:
            ui.warn("Merged into a single chapter file (text_..._01.md)")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
