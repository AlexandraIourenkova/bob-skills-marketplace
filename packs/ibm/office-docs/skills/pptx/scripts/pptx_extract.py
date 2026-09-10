#!/usr/bin/env python3
"""Extract the outline of a PowerPoint deck to Markdown with python-pptx.

One section per slide, in the same syntax pptx_build.py reads:
titles as "## Slide N: title", placeholder text as bullets (nested by level,
bold runs wrapped in **), bold lines without a bullet as "### ", text boxes as
plain paragraphs, tables as Markdown tables, charts as ```chart JSON blocks,
pictures as "Image:" lines (or ![..](..) links with --images-dir) and speaker
notes as "Notes:" lines.

--plain writes an outline that pptx_build.py rebuilds as is: the file header
becomes a comment, headings lose the "Slide N:" prefix, the deck's title slide
becomes "# title" and pictures that are not saved become comments.

Run:  uv run --with python-pptx python pptx_extract.py deck.pptx -o outline.md
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.enum.shapes import PP_PLACEHOLDER
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write("python-pptx is not installed. Run with: uv run --with python-pptx python pptx_extract.py ...\n")
    sys.exit(1)

EMU_PER_INCH = 914400
TITLE_TYPES = (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE)
BODY_TYPES = (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT)

# chart types pptx_build.py can rebuild, matched against XL_CHART_TYPE names in order
CHART_TYPE_NAMES = (
    ("DOUGHNUT", "doughnut"), ("PIE", "pie"), ("LINE", "line"), ("AREA", "area"),
    ("COLUMN_STACKED", "stacked"), ("BAR_STACKED", "barh-stacked"), ("COLUMN", "bar"), ("BAR", "barh"),
)

PRESENTATION_MAIN = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
RETYPE_MAIN_RE = re.compile(r"application/vnd\.openxmlformats-officedocument\.presentationml\.(?:template|slideshow)\.main\+xml")
RETYPE_SUFFIXES = (".potx", ".ppsx")


def open_presentation(path: Path):
    """Open a deck; .potx/.ppsx packages are retyped in memory so python-pptx accepts them."""
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


def inches(value: int | None) -> str:
    return "?" if value is None else f"{value / EMU_PER_INCH:.2f}"


def shape_kind(shape) -> str:
    try:
        return shape.shape_type.name if shape.shape_type is not None else "shape"
    except Exception:
        return "shape"


def iter_shapes(shapes):
    """Yield shapes in document order, descending into groups."""
    for shape in shapes:
        if shape_kind(shape) == "GROUP":
            yield from iter_shapes(shape.shapes)
        else:
            yield shape


def is_placeholder_of(shape, types: tuple) -> bool:
    return shape.is_placeholder and shape.placeholder_format.type in types


def md_cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|") or " "


def has_no_bullet(paragraph) -> bool:
    p_pr = paragraph._p.pPr
    return p_pr is not None and any(child.tag.endswith("}buNone") for child in p_pr)


def all_bold(paragraph) -> bool:
    runs = [run for run in paragraph.runs if run.text.strip()]
    return bool(runs) and all(run.font.bold for run in runs)


def paragraph_text(paragraph, mark_bold: bool) -> str:
    """Paragraph text with a space for each <a:br> line break and ** around bold runs.

    paragraph.runs skips line breaks and fields, so the children of the <a:p>
    element are walked in order instead.
    """
    runs = iter(paragraph.runs)
    parts: list[str] = []
    bold_open = False
    for child in paragraph._p:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "r":
            run = next(runs)
            is_bold = mark_bold and bool(run.font.bold) and bool(run.text.strip())
            if is_bold != bold_open:
                parts.append("**")
                bold_open = is_bold
            parts.append(run.text)
        elif tag == "br":
            parts.append(" ")
        elif tag == "fld":  # slide number, date
            parts.append("".join(t.text or "" for t in child.iter() if t.tag.endswith("}t")))
    if bold_open:
        parts.append("**")
    return "".join(parts).strip()


def text_lines(text_frame, as_bullets: bool) -> list[str]:
    lines: list[str] = []
    for paragraph in text_frame.paragraphs:
        heading = as_bullets and has_no_bullet(paragraph) and all_bold(paragraph)
        text = paragraph_text(paragraph, mark_bold=not heading)
        if not text:
            continue
        if heading:
            lines.append("### " + text)
        elif as_bullets and not has_no_bullet(paragraph):
            lines.append("  " * paragraph.level + "- " + text)
        else:
            lines.append(text)
    return lines


def table_lines(table) -> list[str]:
    rows = [[md_cell(cell.text) for cell in row.cells] for row in table.rows]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    rows = [row + [" "] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return lines


def chart_type_name(chart) -> tuple[str, str | None]:
    """Return (outline chart type, note); the note says when the original type cannot be rebuilt."""
    try:
        raw = chart.chart_type.name
    except Exception:
        return "bar", "chart type could not be read; shown as bar"
    for needle, name in CHART_TYPE_NAMES:
        if needle in raw:
            return name, None
    return "bar", f"original chart type {raw} is not supported by pptx_build.py; shown as bar with the series values"


def chart_lines(chart) -> list[str]:
    ctype, note = chart_type_name(chart)
    spec: dict = {"type": ctype}
    try:
        if chart.has_title:
            spec["title"] = chart.chart_title.text_frame.text
    except Exception:
        pass
    try:
        plot = chart.plots[0]
        spec["categories"] = [str(c) for c in plot.categories]
        spec["series"] = [
            {"name": series.name, "values": [v for v in series.values]} for series in plot.series
        ]
    except Exception as error:
        note = f"could not read chart data: {error}"
    try:  # label and legend flags are optional; scatter plots have no data-label element
        spec["data_labels"] = bool(plot.has_data_labels)
        if spec["data_labels"] and not plot.data_labels.number_format_is_linked:
            spec["number_format"] = plot.data_labels.number_format
        spec["legend"] = bool(chart.has_legend)
    except Exception:
        pass
    if note:
        spec["note"] = note
    return ["```chart", json.dumps(spec, ensure_ascii=False), "```"]


def picture_line(shape, slide_no: int, index: int, images_dir: Path | None, plain: bool, link_base: Path | None = None) -> str:
    size = f"{inches(shape.width)} x {inches(shape.height)} in at ({inches(shape.left)}, {inches(shape.top)})"
    name = shape.name or f"picture {index}"
    try:
        image = shape.image
    except Exception:
        image = None
    if image is not None and images_dir is not None:
        target = images_dir / f"slide{slide_no}_image{index}.{image.ext}"
        target.write_bytes(image.blob)
        link = target
        if link_base is not None:
            try:
                link = target.resolve().relative_to(link_base.resolve())
            except ValueError:
                link = target.resolve()
        return f"![{name}]({link.as_posix()})"
    detail = f"{image.ext}, {size}" if image is not None else f"{size}, not embedded"
    line = f"Image: {name}, {detail}"
    return f"<!-- {line} -->" if plain else line


def extract(deck: Path, images_dir: Path | None, include_layout: bool, plain: bool, link_base: Path | None = None) -> tuple[str, int]:
    """Return (markdown, slide count)."""
    prs = open_presentation(deck)
    size = f"{inches(prs.slide_width)} x {inches(prs.slide_height)} in"
    if plain:
        out: list[str] = [f"<!-- {deck.name}: {len(prs.slides)} slides, {size} -->", ""]
    else:
        out = [f"# {deck.name}", "", f"Slides: {len(prs.slides)}; slide size: {size}", ""]
    for slide_no, slide in enumerate(prs.slides, start=1):
        shapes = list(iter_shapes(slide.shapes))
        title_shape = next((s for s in shapes if s.has_text_frame and is_placeholder_of(s, TITLE_TYPES)), None)
        title = " ".join(title_shape.text_frame.text.split()) if title_shape is not None else ""
        is_title_slide = title_shape is not None and title_shape.placeholder_format.type == PP_PLACEHOLDER.CENTER_TITLE
        if plain:
            out.append((("# " if is_title_slide else "## ") + title).rstrip())
        else:
            out.append(f"## Slide {slide_no}: {title}".rstrip())
        if include_layout:
            out.append(f"<!-- layout: {slide.slide_layout.name} -->")
        out.append("")
        picture_index = 0
        for shape in shapes:
            if shape is title_shape:
                continue
            if shape.has_table:
                out += table_lines(shape.table) + [""]
            elif shape.has_chart:
                out += chart_lines(shape.chart) + [""]
            elif shape_kind(shape) == "PICTURE" or (shape.is_placeholder and shape.placeholder_format.type == PP_PLACEHOLDER.PICTURE and hasattr(shape, "image")):
                picture_index += 1
                out += [picture_line(shape, slide_no, picture_index, images_dir, plain, link_base), ""]
            elif shape.has_text_frame:
                lines = text_lines(shape.text_frame, as_bullets=is_placeholder_of(shape, BODY_TYPES))
                if lines:
                    out += lines + [""]
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text
            note_lines = [f"Notes: {line.strip()}" for line in notes.splitlines() if line.strip()]
            if note_lines:
                out += note_lines + [""]
    return "\n".join(out).rstrip() + "\n", len(prs.slides)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract titles, bullets, tables, charts and speaker notes of a .pptx deck to Markdown.")
    parser.add_argument("deck", help="input .pptx file (.potx and .ppsx are read too)")
    parser.add_argument("-o", "--output", help="write Markdown here (default: standard output)")
    parser.add_argument("--images-dir", help="also save embedded pictures into this existing directory and link them")
    parser.add_argument("--layouts", action="store_true", help="add a '<!-- layout: name -->' comment under each slide heading")
    parser.add_argument("--plain", action="store_true", help="rebuildable outline: no file header, no 'Slide N:' prefixes, unsaved pictures as comments")
    args = parser.parse_args(argv)

    deck = Path(args.deck)
    if not deck.is_file():
        sys.stderr.write(f"error: deck not found: {deck}\n")
        return 1
    images_dir = None
    if args.images_dir:
        images_dir = Path(args.images_dir)
        if not images_dir.is_dir():
            sys.stderr.write(f"error: --images-dir is not an existing directory: {images_dir}\n")
            return 1
    try:
        link_base = Path(args.output).parent if getattr(args, "output", None) else Path.cwd()
        markdown, slide_count = extract(deck, images_dir, args.layouts, args.plain, link_base)
    except Exception as error:  # corrupt or non-pptx input
        sys.stderr.write(f"error: cannot read {deck}: {error}\n")
        return 1
    if args.output:
        output = Path(args.output)
        if not output.parent.exists():
            sys.stderr.write(f"error: output directory does not exist: {output.parent}\n")
            return 1
        output.write_text(markdown, encoding="utf-8")
        print(f"Wrote {output}: {markdown.count(chr(10))} lines for {slide_count} slides")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
