#!/usr/bin/env python3
"""Build a 16:9 PowerPoint deck from a Markdown outline with python-pptx.

Outline syntax, one construct per line:

    # Deck title              title slide; plain lines after it become the subtitle
    ## Slide heading          starts a new content slide
    - bullet                  bullet; indent with 2 or 4 spaces to nest (also * and +)
    ### Sub-heading           bold paragraph without a bullet
    plain text                paragraph without a bullet
    ![alt](images/pic.png)    picture, path relative to the outline file
    ```chart                  native chart from JSON, see CHART_HELP below
    Notes: text               one paragraph of speaker notes for the slide
    <!-- comment -->, ---     ignored

Paired **markers** make a bold span; a lone ** is kept as text. The outline
must be UTF-8 (a byte-order mark is fine). A template may be a .pptx, .potx or
.ppsx file; the last two are retyped in memory because python-pptx opens only
presentation packages.

Run:  uv run --with python-pptx python pptx_build.py outline.md -o deck.pptx
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
    from pptx.enum.shapes import PP_PLACEHOLDER
    from pptx.enum.text import MSO_AUTO_SIZE
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Emu, Inches, Pt
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write("python-pptx is not installed. Run with: uv run --with python-pptx python pptx_build.py ...\n")
    sys.exit(1)

CHART_HELP = """A chart block is a fenced code block with language "chart" containing JSON:

    ```chart
    {"type": "bar", "title": "Revenue by quarter",
     "categories": ["Q1", "Q2", "Q3", "Q4"],
     "series": [{"name": "2025", "values": [12, 15, 14, 19]}],
     "data_labels": true, "number_format": "#,##0"}
    ```

type: bar (vertical columns), column, barh (horizontal), stacked, barh-stacked, line, pie, doughnut, area.
series may also be an object {"name": [values, ...]}. Values must be numbers.
Optional keys: title, data_labels (bool), number_format (Excel format string), legend (bool)."""

CHART_TYPES = {
    "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "barh": XL_CHART_TYPE.BAR_CLUSTERED,
    "stacked": XL_CHART_TYPE.COLUMN_STACKED,
    "barh-stacked": XL_CHART_TYPE.BAR_STACKED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
    "area": XL_CHART_TYPE.AREA,
}
STACKED_TYPES = ("stacked", "barh-stacked")

TITLE_LAYOUT_NAMES = ("title slide", "title")
CONTENT_LAYOUT_NAMES = ("title and content", "title, content", "content")
TITLE_ONLY_LAYOUT_NAMES = ("title only",)

BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
IMAGE_RE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$")
FENCE_RE = re.compile(r"^\s*```\s*([A-Za-z0-9_-]*)\s*$")
NOTES_RE = re.compile(r"^\s*Notes:\s*(.*)$", re.I)  # plural only: 'Note: ...' stays a paragraph
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")  # only paired markers toggle bold

# 16:9 widescreen, the exact size PowerPoint uses (13.333 x 7.5 in)
WIDESCREEN_WIDTH = 12192000
WIDESCREEN_HEIGHT = 6858000

PRESENTATION_MAIN = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
RETYPE_MAIN_RE = re.compile(r"application/vnd\.openxmlformats-officedocument\.presentationml\.(?:template|slideshow)\.main\+xml")
RETYPE_SUFFIXES = (".potx", ".ppsx")


def open_presentation(path: Path):
    """Open a deck; .potx/.ppsx packages are retyped in memory so python-pptx accepts them.

    python-pptx refuses a package whose main part is a template or slideshow.
    Only the content type in [Content_Types].xml differs, so rewriting it to the
    presentation type yields a package that opens and saves as a normal .pptx.
    Raises the python-pptx or zipfile error for anything that is not a deck.
    """
    if path.suffix.lower() not in RETYPE_SUFFIXES:
        return Presentation(str(path))
    buffer = io.BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info)
            if info.filename == "[Content_Types].xml":
                data = RETYPE_MAIN_RE.sub(PRESENTATION_MAIN, data.decode("utf-8")).encode("utf-8")
            target.writestr(info, data)
    buffer.seek(0)
    return Presentation(buffer)


# --------------------------------------------------------------------------- model
@dataclass
class Item:
    kind: str  # bullet | para | heading | code | image | chart
    text: str = ""
    level: int = 0
    bold: bool = False
    path: Path | None = None
    alt: str = ""
    chart: dict | None = None
    line: int = 0


@dataclass
class SlideSpec:
    kind: str  # title | content
    title: str
    line: int
    subtitle: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def bullets(self) -> list[Item]:
        return [i for i in self.items if i.kind == "bullet"]

    @property
    def text_items(self) -> list[Item]:
        return [i for i in self.items if i.kind in ("bullet", "para", "heading", "code")]

    @property
    def visuals(self) -> list[Item]:
        return [i for i in self.items if i.kind in ("image", "chart")]


class OutlineError(Exception):
    pass


# --------------------------------------------------------------------------- parsing
def parse_outline(text: str, base_dir: Path) -> list[SlideSpec]:
    slides: list[SlideSpec] = []
    current: SlideSpec | None = None
    indent_stack: list[int] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line_no = i + 1
        stripped = raw.strip()
        i += 1

        fence = FENCE_RE.match(raw)
        if fence:
            lang = fence.group(1).lower()
            block: list[str] = []
            closed = False
            while i < len(lines):
                if FENCE_RE.match(lines[i]) and lines[i].strip().startswith("```"):
                    closed = True
                    i += 1
                    break
                block.append(lines[i])
                i += 1
            if not closed:
                raise OutlineError(f"line {line_no}: fenced block is never closed")
            if current is None:
                raise OutlineError(f"line {line_no}: content before the first '#' or '##' heading")
            if lang == "chart":
                try:
                    spec = json.loads("\n".join(block))
                except json.JSONDecodeError as error:
                    raise OutlineError(f"line {line_no}: chart block is not valid JSON ({error})") from None
                current.items.append(Item(kind="chart", chart=normalise_chart(spec, line_no), line=line_no))
            else:
                current.items.append(Item(kind="code", text="\n".join(block), line=line_no))
            continue

        if not stripped or stripped == "---" or stripped.startswith("<!--"):
            continue

        if stripped == "#" or stripped.startswith("# "):
            current = SlideSpec(kind="title", title=inline_clean(stripped[1:]), line=line_no)
            slides.append(current)
            indent_stack = []
            continue
        if stripped == "##" or stripped.startswith("## "):
            current = SlideSpec(kind="content", title=inline_clean(stripped[2:]), line=line_no)
            slides.append(current)
            indent_stack = []
            continue
        if current is None:
            raise OutlineError(f"line {line_no}: content before the first '#' or '##' heading")

        notes = NOTES_RE.match(raw)
        if notes:
            current.notes.append(notes.group(1).strip())
            continue

        image = IMAGE_RE.match(raw)
        if image:
            path = Path(image.group(2).strip())
            if not path.is_absolute():
                path = base_dir / path
            current.items.append(Item(kind="image", alt=image.group(1).strip(), path=path, line=line_no))
            continue

        if stripped.startswith("### "):
            current.items.append(Item(kind="heading", text=stripped[4:].strip(), bold=True, line=line_no))
            continue

        bullet = BULLET_RE.match(raw)
        if bullet:
            indent = len(bullet.group(1).replace("\t", "    "))
            while indent_stack and indent < indent_stack[-1]:
                indent_stack.pop()
            if not indent_stack or indent > indent_stack[-1]:
                indent_stack.append(indent)
            level = min(len(indent_stack) - 1, 4)
            if current.kind == "title":
                current.subtitle.append(bullet.group(2))
            else:
                current.items.append(Item(kind="bullet", text=bullet.group(2), level=level, line=line_no))
            continue

        if current.kind == "title":
            current.subtitle.append(stripped)
        else:
            current.items.append(Item(kind="para", text=stripped, line=line_no))
    if not slides:
        raise OutlineError("the outline has no '# Title' or '## Heading' lines")
    return slides


def inline_clean(text: str) -> str:
    """Drop paired bold markers from a heading; a lone '**' is kept."""
    return BOLD_RE.sub(r"\1", text).strip()


def normalise_chart(spec: object, line_no: int) -> dict:
    if not isinstance(spec, dict):
        raise OutlineError(f"line {line_no}: chart JSON must be an object")
    ctype = str(spec.get("type", "bar")).lower()
    if ctype not in CHART_TYPES:
        raise OutlineError(f"line {line_no}: unknown chart type '{ctype}'; use one of {', '.join(CHART_TYPES)}")
    categories = spec.get("categories")
    if not isinstance(categories, list) or not categories:
        raise OutlineError(f"line {line_no}: chart needs a non-empty 'categories' list")
    raw_series = spec.get("series")
    series: list[tuple[str, list[float]]] = []
    if isinstance(raw_series, dict):
        raw_series = [{"name": k, "values": v} for k, v in raw_series.items()]
    if not isinstance(raw_series, list) or not raw_series:
        raise OutlineError(f"line {line_no}: chart needs a non-empty 'series' list")
    for index, entry in enumerate(raw_series):
        if not isinstance(entry, dict) or "values" not in entry:
            raise OutlineError(f"line {line_no}: series {index + 1} must be an object with 'name' and 'values'")
        values = entry["values"]
        if not isinstance(values, list) or len(values) != len(categories):
            raise OutlineError(
                f"line {line_no}: series '{entry.get('name', index + 1)}' has {len(values) if isinstance(values, list) else 'no'}"
                f" values but there are {len(categories)} categories"
            )
        numbers: list[float] = []
        for value in values:
            if value is None:
                numbers.append(None)  # type: ignore[arg-type]
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise OutlineError(f"line {line_no}: chart value {value!r} is not a number")
            else:
                numbers.append(value)
        series.append((str(entry.get("name", f"Series {index + 1}")), numbers))
    if ctype in ("pie", "doughnut") and len(series) > 1:
        raise OutlineError(f"line {line_no}: a {ctype} chart takes exactly one series")
    return {
        "type": ctype,
        "title": str(spec.get("title", "")),
        "categories": [str(c) for c in categories],
        "series": series,
        "data_labels": bool(spec.get("data_labels", ctype in ("pie", "doughnut"))),
        "number_format": spec.get("number_format"),
        "legend": spec.get("legend"),
    }


# --------------------------------------------------------------------------- pptx helpers
def find_layout(prs, names: tuple[str, ...], fallback_index: int | None, override: str | None):
    layouts = list(prs.slide_layouts)
    if override:
        for layout in layouts:
            if layout.name.strip().lower() == override.strip().lower():
                return layout
        available = ", ".join(repr(layout.name) for layout in layouts)
        raise OutlineError(f"layout {override!r} not found in the template; available: {available}")
    for wanted in names:
        for layout in layouts:
            if layout.name.strip().lower() == wanted:
                return layout
    if fallback_index is not None and fallback_index < len(layouts):
        return layouts[fallback_index]
    return layouts[0]


def placeholder_of(slide, types: tuple) -> object | None:
    for shape in slide.placeholders:
        if shape.placeholder_format.type in types:
            return shape
    return None


def remove_shape(shape) -> None:
    element = shape._element
    element.getparent().remove(element)


def remove_all_slides(prs) -> int:
    sld_id_lst = prs.slides._sldIdLst
    count = 0
    for sld_id in list(sld_id_lst):
        prs.part.drop_rel(sld_id.rId)
        sld_id_lst.remove(sld_id)
        count += 1
    return count


def set_runs(paragraph, text: str, size_pt: float, bold: bool = False, mono: bool = False) -> None:
    """Fill a paragraph with runs; paired '**markers**' make a bold span (odd split indexes)."""
    for existing in list(paragraph.runs):
        existing._r.getparent().remove(existing._r)
    parts = BOLD_RE.split(text)
    for index, part in enumerate(parts):
        if not part:
            continue
        run = paragraph.add_run()
        run.text = part
        run.font.size = Pt(size_pt)
        if bold or index % 2 == 1:
            run.font.bold = True
        if mono:
            run.font.name = "Courier New"
    if not paragraph.runs:  # empty text still needs a run to carry the size
        run = paragraph.add_run()
        run.text = ""
        run.font.size = Pt(size_pt)


def no_bullet(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    for child in list(p_pr):
        if child.tag.endswith("}buNone") or child.tag.endswith("}buChar") or child.tag.endswith("}buAutoNum"):
            p_pr.remove(child)
    p_pr.insert_element_before(OxmlElement("a:buNone"), "a:tabLst", "a:defRPr", "a:extLst")
    p_pr.set("marL", "0")
    p_pr.set("indent", "0")


def body_size(level: int, base: float) -> float:
    return max(18.0, base - 2 * min(level, 3))


def fill_text_frame(text_frame, items: list[Item], base_size: float) -> None:
    text_frame.word_wrap = True
    text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    first = True
    for item in items:
        if item.kind == "code":
            lines = item.text.splitlines() or [""]
        else:
            lines = [item.text]
        for line in lines:
            paragraph = text_frame.paragraphs[0] if first else text_frame.add_paragraph()
            first = False
            if item.kind == "bullet":
                paragraph.level = item.level
                set_runs(paragraph, line, body_size(item.level, base_size))
            elif item.kind == "heading":
                set_runs(paragraph, line, base_size, bold=True)
                no_bullet(paragraph)
                paragraph.space_before = Pt(8)
            elif item.kind == "code":
                set_runs(paragraph, line, body_size(1, base_size), mono=True)
                no_bullet(paragraph)
            else:
                set_runs(paragraph, line, base_size)
                no_bullet(paragraph)


def split_box(box: tuple[int, int, int, int], count: int, columns: bool, gap: int) -> list[tuple[int, int, int, int]]:
    left, top, width, height = box
    if count <= 1:
        return [box]
    if columns:
        cell = (width - gap * (count - 1)) // count
        return [(left + i * (cell + gap), top, cell, height) for i in range(count)]
    cell = (height - gap * (count - 1)) // count
    return [(left, top + i * (cell + gap), width, cell) for i in range(count)]


def add_image(slide, item: Item, box: tuple[int, int, int, int]) -> None:
    if item.path is None or not item.path.is_file():
        raise OutlineError(f"line {item.line}: image not found: {item.path}")
    left, top, width, height = box
    try:
        picture = slide.shapes.add_picture(str(item.path), left, top)
    except Exception as error:  # unreadable or unsupported image
        raise OutlineError(f"line {item.line}: cannot insert image {item.path}: {error}") from None
    scale = min(width / picture.width, height / picture.height)
    picture.width = int(picture.width * scale)
    picture.height = int(picture.height * scale)
    picture.left = left + (width - picture.width) // 2
    picture.top = top + (height - picture.height) // 2
    if item.alt:
        try:
            picture._element._nvXxPr.cNvPr.set("descr", item.alt)
        except Exception:
            pass


def add_chart(slide, item: Item, box: tuple[int, int, int, int]) -> None:
    spec = item.chart or {}
    data = CategoryChartData()
    data.categories = spec["categories"]
    for name, values in spec["series"]:
        data.add_series(name, values)
    left, top, width, height = box
    chart = slide.shapes.add_chart(CHART_TYPES[spec["type"]], left, top, width, height, data).chart
    chart.font.size = Pt(14)
    is_pie = spec["type"] in ("pie", "doughnut")
    show_legend = spec["legend"] if spec["legend"] is not None else (is_pie or len(spec["series"]) > 1)
    chart.has_legend = bool(show_legend)
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.RIGHT if is_pie else XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(12)
    if spec["title"]:
        chart.has_title = True
        chart.chart_title.text_frame.text = spec["title"]
        for paragraph in chart.chart_title.text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(16)
                run.font.bold = True
    else:
        chart.has_title = False
    plot = chart.plots[0]
    plot.vary_by_categories = is_pie
    if spec["data_labels"]:
        plot.has_data_labels = True
        labels = plot.data_labels
        labels.font.size = Pt(12)
        if is_pie:
            labels.show_percentage = True
            labels.show_value = False
            labels.number_format = "0%"
            labels.number_format_is_linked = False
        else:
            labels.position = XL_LABEL_POSITION.CENTER if spec["type"] in STACKED_TYPES else XL_LABEL_POSITION.OUTSIDE_END
            if spec["number_format"]:
                labels.number_format = str(spec["number_format"])
                labels.number_format_is_linked = False
    if not is_pie:
        try:
            chart.category_axis.tick_labels.font.size = Pt(12)
            chart.value_axis.tick_labels.font.size = Pt(12)
            chart.value_axis.has_major_gridlines = True
            if spec["number_format"]:
                chart.value_axis.tick_labels.number_format = str(spec["number_format"])
                chart.value_axis.tick_labels.number_format_is_linked = False
        except Exception:
            pass


# --------------------------------------------------------------------------- building
class Builder:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.warnings: list[str] = []
        self.using_template = args.template is not None
        if self.using_template:
            template = Path(args.template)
            if not template.is_file():
                raise OutlineError(f"template not found: {template}")
            try:
                self.prs = open_presentation(template)
            except Exception as error:  # not a zip, not a deck, or a damaged package
                raise OutlineError(f"cannot open template {template}: {error}") from None
            if not args.keep_template_slides:
                remove_all_slides(self.prs)
        else:
            self.prs = Presentation()
            self.prs.slide_width = Emu(WIDESCREEN_WIDTH)
            self.prs.slide_height = Emu(WIDESCREEN_HEIGHT)
        self.width = self.prs.slide_width
        self.height = self.prs.slide_height
        self.margin = Inches(0.5)
        self.gap = Inches(0.3)
        self.title_layout = find_layout(self.prs, TITLE_LAYOUT_NAMES, 0, args.title_layout)
        self.content_layout = find_layout(self.prs, CONTENT_LAYOUT_NAMES, 1, args.content_layout)
        self.title_only_layout = find_layout(self.prs, TITLE_ONLY_LAYOUT_NAMES, 5, args.title_only_layout)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        sys.stderr.write(f"warning: {message}\n")

    # geometry ---------------------------------------------------------------
    def default_title_box(self) -> tuple[int, int, int, int]:
        return (self.margin, Inches(0.35), self.width - 2 * self.margin, Inches(1.2))

    def default_body_box(self) -> tuple[int, int, int, int]:
        top = Inches(1.75)
        return (self.margin, top, self.width - 2 * self.margin, self.height - top - self.margin)

    def title_slide_boxes(self) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
        """Title and subtitle boxes for the built-in template: full width, centred vertically."""
        width = self.width - 2 * self.margin
        title_height = Inches(1.6)
        subtitle_height = Inches(1.4)
        top = (self.height - title_height - self.gap - subtitle_height) // 2
        title_box = (self.margin, top, width, title_height)
        subtitle_box = (self.margin, top + title_height + self.gap, width, subtitle_height)
        return title_box, subtitle_box

    def place(self, shape, box: tuple[int, int, int, int]) -> None:
        shape.left, shape.top, shape.width, shape.height = (Emu(v) for v in box)

    def content_box(self, slide, body) -> tuple[int, int, int, int]:
        if not self.using_template:
            return self.default_body_box()
        if body is not None:
            return (body.left, body.top, body.width, body.height)
        title = slide.shapes.title
        if title is not None and title.top is not None:
            top = title.top + title.height + self.gap
            return (self.margin, top, self.width - 2 * self.margin, self.height - top - self.margin)
        return self.default_body_box()

    # slides -----------------------------------------------------------------
    def build(self, specs: list[SlideSpec]) -> None:
        for number, spec in enumerate(specs, start=1):
            if spec.kind == "title":
                self.build_title_slide(spec, number)
            else:
                self.build_content_slide(spec, number)

    def set_title(self, slide, text: str, size: float, number: int, box: tuple[int, int, int, int] | None = None) -> None:
        box = box or self.default_title_box()
        title = slide.shapes.title
        if title is None:
            title = slide.shapes.add_textbox(*box)
        elif not self.using_template:
            self.place(title, box)
        frame = title.text_frame
        frame.word_wrap = True
        set_runs(frame.paragraphs[0], text, size)
        if not text:
            self.warn(f"slide {number}: the heading is empty")
        elif len(text) > 70:
            self.warn(f"slide {number}: the heading has {len(text)} characters; keep headlines short")

    def build_title_slide(self, spec: SlideSpec, number: int) -> None:
        slide = self.prs.slides.add_slide(self.title_layout)
        title_box, subtitle_box = self.title_slide_boxes()
        # the deck title is 4 pt larger than the headings but never above 40 pt
        self.set_title(slide, spec.title, min(self.args.title_size + 4, 40), number, title_box)
        subtitle = placeholder_of(slide, (PP_PLACEHOLDER.SUBTITLE, PP_PLACEHOLDER.BODY))
        if spec.subtitle:
            if subtitle is None:  # a template layout without a subtitle: text box under the title
                left, top, width, _ = self.default_body_box()
                subtitle = slide.shapes.add_textbox(left, top, width, Inches(1.5))
            elif not self.using_template:  # the built-in 4:3 layout box would sit off-centre on 16:9
                self.place(subtitle, subtitle_box)
            frame = subtitle.text_frame
            frame.word_wrap = True
            for index, line in enumerate(spec.subtitle):
                paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                set_runs(paragraph, line, self.args.body_size)
        for item in spec.items:
            self.warn(f"line {item.line}: {item.kind} on the title slide is ignored")
        self.finish_slide(slide, spec)

    def build_content_slide(self, spec: SlideSpec, number: int) -> None:
        text_items = spec.text_items
        visuals = spec.visuals
        layout = self.content_layout if text_items else self.title_only_layout
        slide = self.prs.slides.add_slide(layout)
        self.set_title(slide, spec.title, self.args.title_size, number)

        bullet_count = len(spec.bullets)
        if bullet_count > self.args.max_bullets:
            self.warn(f"slide {number} '{spec.title}': {bullet_count} bullets, more than {self.args.max_bullets}; split the slide")
        if not text_items and not visuals:
            self.warn(f"slide {number} '{spec.title}': no content")

        body = placeholder_of(slide, (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT))
        area = self.content_box(slide, body)
        if text_items:
            if body is None:
                body = slide.shapes.add_textbox(*area)
            if visuals:
                text_box, visual_area = split_box(area, 2, columns=True, gap=self.gap)
                self.place(body, text_box)
            else:
                visual_area = area
                if not self.using_template:
                    self.place(body, area)
            fill_text_frame(body.text_frame, text_items, self.args.body_size)
            boxes = split_box(visual_area, len(visuals), columns=False, gap=self.gap)
        else:
            boxes = split_box(area, len(visuals), columns=True, gap=self.gap)
        for item, box in zip(visuals, boxes):
            if item.kind == "image":
                add_image(slide, item, box)
            else:
                add_chart(slide, item, box)
        self.finish_slide(slide, spec)

    def finish_slide(self, slide, spec: SlideSpec) -> None:
        if spec.notes:
            slide.notes_slide.notes_text_frame.text = "\n".join(spec.notes)
        for shape in list(slide.placeholders):
            if shape.has_text_frame and not shape.text_frame.text.strip():
                remove_shape(shape)


# --------------------------------------------------------------------------- cli
def list_layouts(template: Path) -> int:
    if not template.is_file():
        sys.stderr.write(f"error: template not found: {template}\n")
        return 1
    try:
        prs = open_presentation(template)
    except Exception as error:  # not a zip, not a deck, or a damaged package
        sys.stderr.write(f"error: cannot open template {template}: {error}\n")
        return 1
    print(f"{template.name}: {len(prs.slide_layouts)} layouts, slide {prs.slide_width / 914400:.2f} x {prs.slide_height / 914400:.2f} in")
    for index, layout in enumerate(prs.slide_layouts):
        names = [f"{ph.placeholder_format.type.name.lower()}[{ph.placeholder_format.idx}]" for ph in layout.placeholders]
        print(f"  {index:2d}  {layout.name}  ({', '.join(names) or 'no placeholders'})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a 16:9 PowerPoint deck from a Markdown outline.",
        epilog=__doc__.split("Run:")[0] + "\n" + CHART_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("outline", help="Markdown outline file")
    parser.add_argument("-o", "--output", help="output .pptx path (required unless --list-layouts)")
    parser.add_argument("--template", help="existing .pptx (or .potx/.ppsx) whose slide layouts, size and theme are used")
    parser.add_argument("--keep-template-slides", action="store_true", help="keep the slides already in the template")
    parser.add_argument("--list-layouts", action="store_true", help="print the layouts of --template (or the outline path if it is a .pptx) and exit")
    parser.add_argument("--title-layout", help="layout name for the title slide (default: 'Title Slide')")
    parser.add_argument("--content-layout", help="layout name for bullet slides (default: 'Title and Content')")
    parser.add_argument("--title-only-layout", help="layout name for image/chart-only slides (default: 'Title Only')")
    parser.add_argument("--title-size", type=float, default=36, help="heading size in pt, 36 to 40 (default 36; the title slide adds 4, capped at 40)")
    parser.add_argument("--body-size", type=float, default=24, help="top-level bullet size in pt, 18 to 24 (default 24; nested levels step down to 18)")
    parser.add_argument("--max-bullets", type=int, default=6, help="warn when a slide has more bullets than this (default 6)")
    parser.add_argument("--strict", action="store_true", help="exit 1 without writing the deck when there are warnings")
    args = parser.parse_args(argv)

    if args.list_layouts:
        target = Path(args.template) if args.template else Path(args.outline)
        return list_layouts(target)

    if not 36 <= args.title_size <= 40:
        parser.error("--title-size must be between 36 and 40")
    if not 18 <= args.body_size <= 24:
        parser.error("--body-size must be between 18 and 24")
    if not args.output:
        parser.error("-o/--output is required")
    outline = Path(args.outline)
    if not outline.is_file():
        sys.stderr.write(f"error: outline not found: {outline}\n")
        return 1
    output = Path(args.output)
    if output.suffix.lower() != ".pptx":
        sys.stderr.write("error: the output path must end with .pptx\n")
        return 1
    if not output.parent.exists():
        sys.stderr.write(f"error: output directory does not exist: {output.parent}\n")
        return 1

    try:
        text = outline.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        sys.stderr.write(f"error: outline is not UTF-8: {outline} (save it as UTF-8 and run again)\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"error: cannot read outline {outline}: {error}\n")
        return 1

    try:
        specs = parse_outline(text, outline.parent.resolve())
        builder = Builder(args)
        builder.build(specs)
    except OutlineError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    if builder.warnings and args.strict:
        sys.stderr.write(f"error: --strict and there were {len(builder.warnings)} warnings; nothing was written\n")
        return 1
    try:
        builder.prs.save(str(output))
    except OSError as error:
        sys.stderr.write(f"error: cannot write {output}: {error}\n")
        return 1

    titles = sum(1 for s in specs if s.kind == "title")
    charts = sum(len([i for i in s.items if i.kind == "chart"]) for s in specs)
    images = sum(len([i for i in s.items if i.kind == "image"]) for s in specs)
    noted = sum(1 for s in specs if s.notes)
    kept = len(builder.prs.slides) - len(specs)
    print(
        f"Wrote {output}: {len(builder.prs.slides)} slides ({titles} title, {len(specs) - titles} content"
        f"{f', {kept} kept from the template' if kept else ''}), "
        f"{images} images, {charts} charts, {noted} slides with notes, {len(builder.warnings)} warnings"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
