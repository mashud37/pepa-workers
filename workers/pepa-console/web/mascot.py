"""Draw the pepa and kopi mascots as pixel-art SVG from character grids, and hold pepa's tips.
Every page shows pepa in its corner, where it gives these tips.
"""
from markupsafe import Markup

PEPA = [
    "..oooooooo......",
    "..owwwwwwoo.....",
    "..owbbbbwofo....",
    "..owwwwwwoffo...",
    "..owwwwwwooooo..",
    "..owwwwwwwwwso..",
    "..owbbbbbbwwso..",
    "..owwwwwwwwwso..",
    "..owwEwwwwEwso..",
    "..owwewwwwewso..",
    "..owpwwwwwwpso..",
    "..owwwwoowwwso..",
    "..owwwwwwwwwso..",
    "..oooooooooooo..",
    "....o......o....",
    "...oo......oo...",
]

KOPI = [
    ".....gggggggg...",
    ".....gvvvvvvgg..",
    ".....gvllllvghg.",
    ".oooooooooovggg.",
    ".owwwwwwwsovvvg.",
    ".owrrrrwwsollvg.",
    ".owwwwwwwsovvvg.",
    ".owbbbbbwsollvg.",
    ".owwEwwEwsovvvg.",
    ".owwewwewsovvvg.",
    ".owpwwwwpsogggg.",
    ".owwwoowwso.....",
    ".owwwwwwwso.....",
    ".oooooooooo.....",
    "...o....o.......",
    "..oo....oo......",
]

COLOURS = {
    "o": "#1f1f1f",
    "w": "#ffffff",
    "s": "#e3eaf5",
    "f": "#c9d6ea",
    "b": "#0b57d0",
    "r": "#d93025",
    "p": "#f6b8b3",
    "e": "#1f1f1f",
    "E": "#1f1f1f",
    "g": "#80868b",
    "v": "#f8f9fa",
    "l": "#bdc1c6",
    "h": "#dadce0",
}

PARTS = {
    "b": "ink",
    "r": "ink",
    "e": "eye",
    "E": "eye",
    "g": "twin",
    "v": "twin",
    "l": "twin",
    "h": "twin",
}

MASCOTS = {
    "pepa": PEPA,
    "kopi": KOPI,
}

# What pepa says when clicked, by the first part of the page's address.
TIPS = {
    "": [
        "Press Process papers and I read everything new. Papers already done are skipped.",
        "Each number opens what is behind it.",
        "Copy PDFs in, or link a folder you already keep papers in.",
        "Tick papers to process only those, or to skip them in a stage.",
        "Mark chapters splits a book where you say.",
    ],
    "apps": [
        "Every app works on its own. Open one to see what it can do.",
        "Each app page has a Settings card for how it runs.",
    ],
    "read": [
        "Search one part of a brief: methods:interviews author:smith.",
        "Plain words search the whole paper too.",
    ],
    "jobs": [
        "Every run keeps its log here, finished or not.",
    ],
    "folders": [
        "Link the folder your reference manager uses. I only read from it.",
    ],
    "models": [
        "Claude Haiku is the cheapest. Sonnet writes a better review.",
        "A model on this computer keeps every paper on this computer.",
        "Show models asks the server which models it has.",
    ],
    "keys": [
        "Keys are kept on this computer, outside your project folder.",
    ],
    "guide": [
        "Each worker has its own page in the guide.",
    ],
}
GREETING = "Hello! Click me for a tip."


def pixel(column, row, colour):
    """One square of the drawing; its column lets the stylesheet stagger an animation."""
    return f'<rect x="{column}" y="{row}" width="1" height="1" fill="{colour}" style="--i:{column}"/>'


def svg(name, scale):
    """The named mascot as inline SVG, with each part grouped so the stylesheet can animate it.

    An upper eye pixel ("E") also gets a white lid on top, which the blink animation shows.

    Args:
        scale: screen pixels per drawing pixel.
    """
    grid = MASCOTS[name]
    groups = {"twin": [], "body": [], "ink": [], "eye": [], "lid": []}
    for row, line in enumerate(grid):
        for column, character in enumerate(line):
            if character == ".":
                continue
            part = PARTS.get(character, "body")
            groups[part].append(pixel(column, row, COLOURS[character]))
            if part == "eye":
                groups["body"].append(pixel(column, row, COLOURS["w"]))
            if character == "E":
                groups["lid"].append(pixel(column, row, COLOURS["w"]))

    drawing = []
    for part, rects in groups.items():
        drawing.append(f'<g class="{part}">{"".join(rects)}</g>')
    cells = len(grid)
    size = cells * scale
    opening = f'<svg class="mascot mascot-{name}" viewBox="0 0 {cells} {cells}" width="{size}" height="{size}" shape-rendering="crispEdges" role="img" aria-label="{name}">'
    return Markup(opening + '<g class="figure">' + "".join(drawing) + "</g></svg>")
