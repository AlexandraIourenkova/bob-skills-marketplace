#!/usr/bin/env python3
"""Storyboard model and parser shared by deck_build.py, storyboard_check.py and deck_inspect.py.

A storyboard is a Markdown file, one construct per line (full spec in
references/storyboard-format.md):

    ---                       optional front matter: key: value lines
    title: Deck title         (title, subtitle, author, date, footer, language)
    ---
    # Deck title              first '#' = title slide; later '#' lines = section slides
    Subtitle line             plain lines under '#' become subtitle lines
    ## Headline               new content slide; the headline states the point
    layout: big-number        optional explicit layout (first line after the headline)
    - bullet                  bullets; indent 2 spaces per level; '1.' makes numbers
    ### Column title          column heading (two-column) or bold sub-heading
    plain text                paragraph
    > quote                   quote; a following line starting with '--' or an em dash is the attribution
    ![alt](images/pic.png)    picture, path relative to the storyboard
    ```chart ... ```          native chart, JSON (type, categories, series, ...)
    | a | b |                 table rows ('|---|' separator rows are skipped)
    - 42% | Label | detail    big-number items or timeline steps (value | label | detail)
    Takeaway: text            callout under the content
    Source: text              small source line at the bottom of the slide
    Notes: text               one paragraph of speaker notes

Only the standard library is used, so every script can import this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LAYOUTS = (
    "title", "section", "bullets", "two-column", "big-number", "quote", "statement",
    "image", "chart", "timeline", "table", "closing", "split", "icons",
)
CHART_TYPES = ("bar", "column", "barh", "stacked", "barh-stacked", "line", "pie", "doughnut", "area")

FRONT_RE = re.compile(r"^---\s*$")
TITLE_RE = re.compile(r"^#\s+(.*\S)\s*$")
SLIDE_RE = re.compile(r"^##\s+(.*\S)\s*$")
HEADING_RE = re.compile(r"^###\s+(.*\S)\s*$")
LAYOUT_RE = re.compile(r"^layout:\s*([a-z-]+)\s*$", re.I)
BULLET_RE = re.compile(r"^(\s*)([-*+])\s+(.*\S)\s*$")
NUMBER_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*\S)\s*$")
IMAGE_RE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$")
FENCE_RE = re.compile(r"^\s*```\s*([A-Za-z0-9_-]*)\s*$")
TABLE_RE = re.compile(r"^\s*\|(.*)\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
QUOTE_RE = re.compile(r"^>\s?(.*)$")
ATTRIB_RE = re.compile(r"^\s*(?:--|—|–)\s*(.*\S)\s*$")
NOTES_RE = re.compile(r"^\s*Notes:\s*(.*)$", re.I)
SOURCE_RE = re.compile(r"^\s*Source:\s*(.*\S)\s*$", re.I)
TAKEAWAY_RE = re.compile(r"^\s*Takeaway:\s*(.*\S)\s*$", re.I)
COMMENT_RE = re.compile(r"^\s*<!--.*-->\s*$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
RTL_LANGUAGES = ("he", "ar", "fa", "ur", "yi")


class StoryboardError(Exception):
    pass


@dataclass
class Item:
    kind: str  # bullet | number | para | code | heading | quote | attribution | image | chart | row
    text: str = ""
    level: int = 0
    path: Path | None = None
    alt: str = ""
    chart: dict | None = None
    cells: list[str] = field(default_factory=list)
    line: int = 0

    @property
    def fields(self) -> list[str]:
        """'value | label | detail' split on pipes, for big-number and timeline items."""
        return [part.strip() for part in self.text.split("|")]


@dataclass
class Slide:
    kind: str  # title | section | content
    title: str  # plain text, markers removed
    line: int
    layout: str | None = None
    title_markup: str = ""  # the headline as written, **bold** markers kept for the renderers
    chapter: str = ""  # the section this slide belongs to, for the label above the headline
    chapter_number: int = 0
    appendix: bool = False  # slides after an "Appendix" section: numbered A1, A2, and left out of the timing
    subtitle: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source: str = ""
    takeaway: str = ""
    appendix_number: int = 0

    def of(self, *kinds: str) -> list[Item]:
        return [i for i in self.items if i.kind in kinds]

    @property
    def bullets(self) -> list[Item]:
        return self.of("bullet", "number")

    @property
    def text_items(self) -> list[Item]:
        return self.of("bullet", "number", "para", "heading", "code")

    @property
    def visuals(self) -> list[Item]:
        return self.of("image", "chart")

    @property
    def columns(self) -> list[Item]:
        return self.of("heading")

    @property
    def rows(self) -> list[Item]:
        return self.of("row")

    @property
    def quote(self) -> str:
        return " ".join(i.text for i in self.of("quote")).strip()

    @property
    def attribution(self) -> str:
        return " ".join(i.text for i in self.of("attribution")).strip()

    def effective_layout(self) -> str:
        if self.layout:
            return self.layout
        if self.kind == "title":
            return "title"
        if self.kind == "section":
            return "section"
        if self.rows:
            return "table"
        if self.of("quote"):
            return "quote"
        if len(self.columns) >= 2:
            return "two-column"
        text, visuals = self.text_items, self.visuals
        only_paras = bool(text) and all(i.kind == "para" for i in text)
        if visuals and not text:
            return "image" if all(v.kind == "image" for v in visuals) else "chart"
        if visuals and only_paras and all(v.kind == "image" for v in visuals):
            return "image"  # pictures with a caption line
        if not text and not visuals:
            return "statement"
        if only_paras and not visuals and len(text) <= 2 and sum(len(i.text) for i in text) <= 240:
            return "statement"  # one or two short sentences under a headline
        return "bullets"

    @property
    def words(self) -> int:
        text = [self.title, *self.subtitle, self.takeaway]
        text += [i.text for i in self.items if i.kind not in ("image", "chart")]
        return sum(len(t.split()) for t in text if t)


@dataclass
class Storyboard:
    meta: dict
    slides: list[Slide]
    path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        if self.meta.get("title"):
            return str(self.meta["title"])
        for slide in self.slides:
            if slide.kind == "title":
                return slide.title
        return self.slides[0].title if self.slides else ""

    @property
    def rtl(self) -> bool:
        language = str(self.meta.get("language", self.meta.get("lang", ""))).lower()[:2]
        return language in RTL_LANGUAGES or str(self.meta.get("direction", "")).lower() == "rtl"

    @property
    def content_slides(self) -> list[Slide]:
        return [s for s in self.slides if s.kind == "content"]

    def headline_outline(self) -> list[str]:
        lines = []
        for number, slide in enumerate(self.slides, start=1):
            marker = {"title": "#", "section": "=", "content": " "}[slide.kind]
            label = f" A{slide.appendix_number}" if slide.appendix and slide.appendix_number else ""
            lines.append(f"{number:>2} {marker} {slide.title}  [{slide.effective_layout()}]{label}")
        return lines

    def estimated_minutes(self, words_per_minute: int = 130) -> float:
        """Speaking time: notes at the given pace; a slide without notes counts 45 seconds. The appendix is not presented."""
        total = 0.0
        for slide in self.slides:
            if slide.appendix:
                continue
            notes_words = sum(len(n.split()) for n in slide.notes)
            total += notes_words / words_per_minute if notes_words else 0.75
        return round(total, 1)


# --------------------------------------------------------------------------- helpers
UNIT_AFTER_NUMBER = re.compile(r"(?<=\d)[ \t]+(%|pp|x|K|M|B|bn|USD|EUR|GBP|kg|km|GB|TB|ms|h|min|days?|weeks?|months?|quarters?|years?|people|FTE)(?![\w-])")
RANGE_BETWEEN_NUMBERS = re.compile(r"(?<=\d)\s?-\s?(?=\d)")
NBSP = "\u00a0"
EN_DASH = "\u2013"


def typographic(text: str) -> str:
    """House typography for anything drawn on a slide.

    A number never parts from its unit at a line break (12 M, 61 %, 30 days), and a range
    between two numbers takes an en dash (2025-2026 becomes 2025\u20132026). Nothing else is
    changed: quotes, apostrophes and hyphenated words stay as the author wrote them.
    """
    text = UNIT_AFTER_NUMBER.sub(NBSP + r"\1", text)
    return RANGE_BETWEEN_NUMBERS.sub(EN_DASH, text)


def inline_clean(text: str) -> str:
    """Strip paired **bold** markers for measurements and plain-text output."""
    return BOLD_RE.sub(r"\1", text)


def bold_parts(text: str) -> list[tuple[str, bool]]:
    """Split text on paired ** markers into (text, bold) pieces; a lone ** stays text."""
    parts = BOLD_RE.split(text)
    return [(part, index % 2 == 1) for index, part in enumerate(parts) if part]


def parse_front_matter(lines: list[str]) -> tuple[dict, int]:
    """Read 'key: value' lines between two '---' lines at the top. Returns (meta, lines consumed)."""
    if not lines or not FRONT_RE.match(lines[0]):
        return {}, 0
    meta: dict = {}
    for index in range(1, len(lines)):
        if FRONT_RE.match(lines[index]):
            return meta, index + 1
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            raise StoryboardError(f"line {index + 1}: front matter line is not 'key: value': {raw.strip()}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key.strip().lower()] = value
    raise StoryboardError("front matter is not closed with '---'")


def normalise_chart(spec: object, line_no: int) -> dict:
    if not isinstance(spec, dict):
        raise StoryboardError(f"line {line_no}: chart block must be a JSON object")
    chart_type = str(spec.get("type", "bar")).lower()
    if chart_type not in CHART_TYPES:
        raise StoryboardError(f"line {line_no}: unknown chart type '{chart_type}'; use one of {', '.join(CHART_TYPES)}")
    categories = spec.get("categories")
    if not isinstance(categories, list) or not categories:
        raise StoryboardError(f"line {line_no}: chart needs a non-empty 'categories' list")
    categories = [str(c) for c in categories]
    raw_series = spec.get("series")
    series: list[tuple[str, list[float]]] = []
    if isinstance(raw_series, dict):
        raw_series = [{"name": name, "values": values} for name, values in raw_series.items()]
    if not isinstance(raw_series, list) or not raw_series:
        raise StoryboardError(f"line {line_no}: chart needs 'series' (a list of {{name, values}} or an object)")
    for entry in raw_series:
        if not isinstance(entry, dict) or "values" not in entry:
            raise StoryboardError(f"line {line_no}: each series needs 'name' and 'values'")
        values = entry["values"]
        if not isinstance(values, list) or len(values) != len(categories):
            raise StoryboardError(f"line {line_no}: series '{entry.get('name', '')}' has {len(values) if isinstance(values, list) else 'no'} values for {len(categories)} categories")
        try:
            numbers = [float(v) if v is not None else 0.0 for v in values]
        except (TypeError, ValueError):
            raise StoryboardError(f"line {line_no}: series '{entry.get('name', '')}' has a non-numeric value") from None
        series.append((str(entry.get("name", f"Series {len(series) + 1}")), numbers))
    if chart_type in ("pie", "doughnut") and len(series) != 1:
        raise StoryboardError(f"line {line_no}: a {chart_type} chart takes exactly one series")
    highlight = spec.get("highlight", [])
    if not isinstance(highlight, list):
        highlight = [highlight]
    annotations = [a for a in (spec.get("annotations") or []) if isinstance(a, dict) and a.get("category")]
    for note in annotations:
        if str(note["category"]) not in categories:
            raise StoryboardError(f"line {line_no}: annotation points at '{note['category']}', which is not one of the categories")
    target = spec.get("target")
    if target is not None and not isinstance(target, (int, float, dict)):
        raise StoryboardError(f"line {line_no}: 'target' must be a number or {{value, label}}")
    return {
        "type": chart_type,
        "title": str(spec.get("title", "") or ""),
        "categories": categories,
        "series": series,
        "data_labels": bool(spec.get("data_labels", False)),
        "number_format": spec.get("number_format"),
        "legend": spec.get("legend"),
        "highlight": [str(h) for h in highlight],
        "unit": str(spec.get("unit", "") or ""),
        "annotations": annotations,  # short notes with a leader line, drawn where they fit
        "target": target,  # a reference line: a number, or {"value": 12, "label": "Plan"}
    }


NUMERIC_CELL = re.compile(r"^[-+\u2212(]?[$\u20ac\u00a3]?\s?\d[\d,.\s]*\s?(%|pp|x|[KkMmBb]n?|days?|h|min)?\)?$")


def is_numeric(text: str) -> bool:
    return bool(NUMERIC_CELL.match(inline_clean(text).strip()))


def numeric_columns(rows: list[list[str]]) -> list[bool]:
    """A column is numeric when every non-empty body cell is a number, a percentage or an amount with a short unit."""
    if not rows:
        return []
    width = max(len(r) for r in rows)
    result = []
    for c in range(width):
        cells = [r[c] for r in rows[1:] if c < len(r) and inline_clean(r[c]).strip()]
        result.append(bool(cells) and all(is_numeric(cell) for cell in cells))
    return result


def split_table_row(text: str) -> list[str]:
    inner = text.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in inner.split("|")]


# --------------------------------------------------------------------------- parser
def parse_storyboard(text: str, base_dir: Path | None = None, path: Path | None = None) -> Storyboard:
    base_dir = Path(base_dir or ".")
    lines = text.lstrip("\ufeff").splitlines()
    meta, start = parse_front_matter(lines)
    board = Storyboard(meta=meta, slides=[], path=path)
    current: Slide | None = None
    seen_title = False
    index = start
    while index < len(lines):
        raw = lines[index]
        line_no = index + 1
        index += 1
        stripped = raw.strip()
        if not stripped or COMMENT_RE.match(raw) or (stripped == "---" and current is None):
            continue
        if stripped == "---":
            continue
        match = TITLE_RE.match(raw)
        if match:
            kind = "section" if seen_title else "title"
            seen_title = True
            current = Slide(kind=kind, title=inline_clean(match.group(1)), line=line_no, title_markup=match.group(1))
            board.slides.append(current)
            continue
        match = SLIDE_RE.match(raw)
        if match:
            current = Slide(kind="content", title=inline_clean(match.group(1)), line=line_no, title_markup=match.group(1))
            board.slides.append(current)
            continue
        if current is None:
            raise StoryboardError(f"line {line_no}: content before the first '#' or '##' heading")
        match = LAYOUT_RE.match(raw)
        if match:
            layout = match.group(1).lower()
            if layout not in LAYOUTS:
                raise StoryboardError(f"line {line_no}: unknown layout '{layout}'; use one of {', '.join(LAYOUTS)}")
            current.layout = layout
            continue
        match = NOTES_RE.match(raw)
        if match:
            current.notes.append(match.group(1).strip())
            continue
        match = SOURCE_RE.match(raw)
        if match:
            current.source = match.group(1)
            continue
        match = TAKEAWAY_RE.match(raw)
        if match:
            current.takeaway = match.group(1)
            continue
        match = FENCE_RE.match(raw)
        if match:
            language = match.group(1).lower()
            body: list[str] = []
            while index < len(lines) and not FENCE_RE.match(lines[index]):
                body.append(lines[index])
                index += 1
            if index >= len(lines):
                raise StoryboardError(f"line {line_no}: code fence is not closed")
            index += 1
            if language == "chart":
                try:
                    spec = json.loads("\n".join(body))
                except json.JSONDecodeError as error:
                    raise StoryboardError(f"line {line_no}: chart JSON is invalid: {error}") from None
                current.items.append(Item(kind="chart", chart=normalise_chart(spec, line_no), line=line_no))
            else:
                for body_line in body:
                    current.items.append(Item(kind="code", text=body_line, line=line_no))
            continue
        match = IMAGE_RE.match(raw)
        if match:
            target = match.group(2).strip()
            current.items.append(Item(kind="image", alt=match.group(1).strip(), path=base_dir / target, text=target, line=line_no))
            continue
        match = HEADING_RE.match(raw)
        if match:
            current.items.append(Item(kind="heading", text=match.group(1), line=line_no))
            continue
        if TABLE_RE.match(raw):
            if TABLE_SEP_RE.match(raw):
                continue
            current.items.append(Item(kind="row", cells=split_table_row(raw), line=line_no))
            continue
        match = QUOTE_RE.match(raw)
        if match:
            current.items.append(Item(kind="quote", text=match.group(1).strip(), line=line_no))
            continue
        match = ATTRIB_RE.match(raw)
        if match and current.of("quote"):
            current.items.append(Item(kind="attribution", text=match.group(1), line=line_no))
            continue
        match = BULLET_RE.match(raw) or NUMBER_RE.match(raw)
        if match:
            indent = len(match.group(1).replace("\t", "    "))
            level = min(indent // 2, 3) if indent < 4 else min(indent // 4 + (1 if indent % 4 >= 2 else 0), 3)
            kind = "number" if match.re is NUMBER_RE else "bullet"
            current.items.append(Item(kind=kind, text=match.group(3), level=level, line=line_no))
            continue
        if current.kind in ("title", "section") and not current.items:
            current.subtitle.append(stripped)
        else:
            current.items.append(Item(kind="para", text=stripped, line=line_no))
    if not board.slides:
        raise StoryboardError("the storyboard has no slides: add '# Deck title' and '## Headline' lines")
    mark_chapters(board)
    return board


APPENDIX_TITLES = ("appendix", "backup", "annex", "приложение", "запасные слайды")


def mark_chapters(board: "Storyboard") -> None:
    """Carry the chapter down to its slides, and letter the appendix."""
    chapter, number, appendix, letter = "", 0, False, 0
    for slide in board.slides:
        if slide.kind == "section":
            number += 1
            chapter = slide.title
            if slide.title.strip().lower().rstrip(":").split()[0] in APPENDIX_TITLES:
                appendix = True
        slide.chapter, slide.chapter_number, slide.appendix = chapter, number, appendix
        if appendix and slide.kind == "content":
            letter += 1
            slide.appendix_number = letter


def appendix_label(slide: "Slide") -> str:
    """A1, A2 for appendix slides; an empty string for the rest."""
    return f"A{getattr(slide, 'appendix_number', 0)}" if slide.appendix and getattr(slide, "appendix_number", 0) else ""


def load_storyboard(path: Path) -> Storyboard:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise StoryboardError(f"{path} is not UTF-8; save the storyboard as UTF-8") from None
    return parse_storyboard(text, base_dir=path.parent, path=path)


if __name__ == "__main__":  # quick look: python storyboard.py storyboard.md
    import sys

    board = load_storyboard(Path(sys.argv[1]))
    print("\n".join(board.headline_outline()))
    print(f"{len(board.slides)} slides, about {board.estimated_minutes()} minutes of talk")
