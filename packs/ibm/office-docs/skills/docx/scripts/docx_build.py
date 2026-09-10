#!/usr/bin/env python3
"""Build a Word (.docx) document from a JSON spec, optionally on top of a template.

Run with:
    uv run --with python-docx python docx_build.py spec.json --out report.docx

Spec format (a JSON object; a bare JSON list of blocks is also accepted):

{
  "title": "Quarterly report",              (optional, document property)
  "author": "Jane Doe",                     (optional, document property)
  "orientation": "portrait" | "landscape",  (optional, applied to every section)
  "blocks": [
    {"type": "heading",   "text": "Overview", "level": 1},
    {"type": "paragraph", "text": "Plain text", "style": "Normal", "align": "justify"},
    {"type": "paragraph", "runs": [{"text": "Bold ", "bold": true}, {"text": "normal"}]},
    {"type": "bullets",   "items": ["one", "two", {"text": "nested", "level": 1}]},
    {"type": "numbered",  "items": ["first", "second"], "restart": true},
    {"type": "table",     "header": ["Name", "Qty"], "rows": [["Apples", 3]],
                          "style": "Table Grid", "col_widths_in": [3, 1]},
    {"type": "image",     "path": "chart.png", "width_in": 5, "caption": "Figure 1"},
    {"type": "page_break"},
    {"type": "section",   "orientation": "landscape"}
  ]
}

Relative image paths are resolved against the directory of the spec file.
Heading level 0 produces the "Title" style; levels 1 to 9 map to "Heading N".
When --template is given the template's styles, headers and footers are kept
and its body content is removed unless --keep-body is passed. A multi-section
template collapses to its last section, which keeps the headers and footers it
showed in Word (references inherited from earlier sections are copied over).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import copy
import json
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.enum.section import WD_ORIENT, WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.image.exceptions import UnrecognizedImageError
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
except ImportError:  # pragma: no cover - environment problem, not a code path to test
    sys.exit(
        "python-docx is not installed. Run this script with:\n"
        "  uv run --with python-docx python docx_build.py SPEC --out OUT.docx"
    )

ALIGNMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}

DEFAULT_CONTENT_WIDTH = Inches(6)


class SpecError(Exception):
    """Raised for problems in the JSON spec."""


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


# --------------------------------------------------------------------------- spec


def load_spec(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecError(f"{path} is not valid JSON: {exc}") from exc
    if isinstance(data, list):
        data = {"blocks": data}
    if not isinstance(data, dict):
        raise SpecError("spec must be a JSON object or a JSON list of blocks")
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        raise SpecError('spec needs a "blocks" list')
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or "type" not in block:
            raise SpecError(f'block {index} must be an object with a "type" key')
    return data


# ------------------------------------------------------------------ document tools


def has_style(doc, name: str) -> bool:
    try:
        doc.styles[name]
    except KeyError:
        return False
    return True


def pick_style(doc, wanted: str | None, fallback: str | None, what: str, note: str = "") -> str | None:
    """Return a style name that exists in the document, or None for the default.

    `note` is appended to the warning when neither style exists.
    """
    if wanted and has_style(doc, wanted):
        return wanted
    if fallback and fallback != wanted and has_style(doc, fallback):
        if wanted:
            warn(f'{what}: style "{wanted}" is not in the document, using "{fallback}"')
        return fallback
    if wanted:
        warn(f'{what}: style "{wanted}" is not in the document, writing {what} without a style{note}')
    return None


HEADER_FOOTER_REFS = (qn("w:headerReference"), qn("w:footerReference"))


def inherit_header_footer_refs(body) -> None:
    """Copy inherited header/footer references onto the trailing section properties.

    Word stores a header or footer reference on the section that defines it; a
    later section that is "linked to previous" carries no reference at all. When
    the earlier sections are removed the last section would lose those headers,
    so every reference it inherited is copied onto it first.
    """
    final = body.find(qn("w:sectPr"))
    if final is None:
        return
    inherited: dict[tuple[str, str | None], object] = {}
    for sectpr in body.iter(qn("w:sectPr")):
        if sectpr is final:
            continue
        for ref in sectpr:
            if ref.tag in HEADER_FOOTER_REFS:
                inherited[(ref.tag, ref.get(qn("w:type")))] = ref
    own = {(ref.tag, ref.get(qn("w:type"))) for ref in final if ref.tag in HEADER_FOOTER_REFS}
    position = 0  # header/footer references come first in the sectPr schema order
    for key, ref in inherited.items():
        if key not in own:
            final.insert(position, copy.deepcopy(ref))
            position += 1


def clear_body(doc) -> None:
    """Remove every body element except the trailing section properties."""
    body = doc.element.body
    inherit_header_footer_refs(body)
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def apply_orientation(section, orientation: str) -> None:
    wanted = WD_ORIENT.LANDSCAPE if orientation == "landscape" else WD_ORIENT.PORTRAIT
    if section.orientation == wanted:
        return
    width, height = section.page_width, section.page_height
    section.orientation = wanted
    if width is not None and height is not None:
        section.page_width, section.page_height = height, width


def content_width(doc):
    """Usable width between the margins of the last section (EMU)."""
    section = doc.sections[-1]
    try:
        return section.page_width - section.left_margin - section.right_margin
    except TypeError:
        return DEFAULT_CONTENT_WIDTH


def style_num_id(doc, style_name: str) -> int | None:
    """numId used by a list style, or None if the style has no numbering."""
    style = doc.styles[style_name]
    ppr = style.element.pPr
    if ppr is None:
        return None
    numpr = ppr.find(qn("w:numPr"))
    if numpr is None:
        return None
    numid = numpr.find(qn("w:numId"))
    return int(numid.get(qn("w:val"))) if numid is not None else None


def new_num_instance(doc, base_num_id: int) -> int | None:
    """Clone a numbering instance so a list restarts at 1. Returns the new numId."""
    numbering = doc.part.numbering_part.element
    abstract_id = None
    last_num = None
    max_id = 0
    for num in numbering.findall(qn("w:num")):
        last_num = num
        current = int(num.get(qn("w:numId")))
        max_id = max(max_id, current)
        if current == base_num_id:
            abstract = num.find(qn("w:abstractNumId"))
            if abstract is not None:
                abstract_id = abstract.get(qn("w:val"))
    if abstract_id is None or last_num is None:
        return None
    new_id = max_id + 1
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(new_id))
    abstract = OxmlElement("w:abstractNumId")
    abstract.set(qn("w:val"), abstract_id)
    num.append(abstract)
    override = OxmlElement("w:lvlOverride")
    override.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:startOverride")
    start.set(qn("w:val"), "1")
    override.append(start)
    num.append(override)
    last_num.addnext(num)
    return new_id


def set_paragraph_numbering(paragraph, num_id: int, level: int) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    numpr = ppr.get_or_add_numPr()
    numpr.get_or_add_ilvl().val = level
    numpr.get_or_add_numId().val = num_id


# ------------------------------------------------------------------------- blocks


def add_runs(paragraph, runs: list) -> None:
    for spec in runs:
        if isinstance(spec, str):
            spec = {"text": spec}
        run = paragraph.add_run(str(spec.get("text", "")))
        if spec.get("bold"):
            run.bold = True
        if spec.get("italic"):
            run.italic = True
        if spec.get("underline"):
            run.underline = True
        if spec.get("size_pt"):
            run.font.size = Pt(float(spec["size_pt"]))
        if spec.get("font"):
            run.font.name = str(spec["font"])
        if spec.get("color"):
            run.font.color.rgb = RGBColor.from_string(str(spec["color"]).lstrip("#"))


def add_heading(doc, block: dict) -> None:
    level = int(block.get("level", 1))
    if not 0 <= level <= 9:
        raise SpecError(f"heading level must be 0..9, got {level}")
    text = str(block.get("text", ""))
    style_name = "Title" if level == 0 else f"Heading {level}"
    if has_style(doc, style_name):
        paragraph = doc.add_paragraph(text, style=style_name)
    else:
        warn(f'style "{style_name}" is missing, writing a bold paragraph instead')
        paragraph = doc.add_paragraph()
        paragraph.add_run(text).bold = True
    if block.get("align") in ALIGNMENTS:
        paragraph.alignment = ALIGNMENTS[block["align"]]


def add_paragraph(doc, block: dict) -> None:
    style = pick_style(doc, block.get("style"), None, "paragraph")
    paragraph = doc.add_paragraph(style=style)
    if "runs" in block:
        add_runs(paragraph, block["runs"])
    else:
        add_runs(paragraph, [{k: v for k, v in block.items() if k != "type"}])
    if block.get("align") in ALIGNMENTS:
        paragraph.alignment = ALIGNMENTS[block["align"]]
    if block.get("rtl"):
        set_right_to_left(paragraph)


def set_right_to_left(paragraph) -> None:
    """Mark a paragraph as right-to-left (Hebrew, Arabic) and align it right."""
    ppr = paragraph._p.get_or_add_pPr()
    if ppr.find(qn("w:bidi")) is None:
        # w:bidi must precede these siblings in the pPr schema order.
        ppr.insert_element_before(
            OxmlElement("w:bidi"),
            "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
            "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
            "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
        )
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for run in paragraph.runs:
        rpr = run._r.get_or_add_rPr()
        if rpr.find(qn("w:rtl")) is None:
            rpr.insert_element_before(
                OxmlElement("w:rtl"), "w:cs", "w:em", "w:lang", "w:eastAsianLayout", "w:specVanish", "w:oMath"
            )


def add_list(doc, block: dict, numbered: bool) -> None:
    items = block.get("items")
    if not isinstance(items, list):
        raise SpecError('list block needs an "items" list')
    base = "List Number" if numbered else "List Bullet"
    restart_id = None
    if numbered and block.get("restart", True) and has_style(doc, base):
        base_num = style_num_id(doc, base)
        if base_num is not None:
            restart_id = new_num_instance(doc, base_num)
    counters: dict[int, int] = {}  # text-marker fallback: running number per level
    warned = False
    for item in items:
        if isinstance(item, str):
            item = {"text": item}
        level = int(item.get("level", 0))
        style_name = base if level == 0 else f"{base} {level + 1}"
        if has_style(doc, style_name):
            paragraph = doc.add_paragraph(style=style_name)
        elif has_style(doc, base):
            paragraph = doc.add_paragraph(style=base)
            paragraph.paragraph_format.left_indent = Inches(0.25 * (level + 1))
        else:
            if not warned:
                warn(f'style "{base}" is missing, writing plain paragraphs with text markers')
                warned = True
            paragraph = doc.add_paragraph()
            if numbered:
                for deeper in [k for k in counters if k > level]:
                    del counters[deeper]
                counters[level] = counters.get(level, 0) + 1
                marker = f"{counters[level]}. "
            else:
                marker = "- "
            paragraph.add_run("    " * level + marker)
        if "runs" in item:
            add_runs(paragraph, item["runs"])
        else:
            add_runs(paragraph, [item])
        if restart_id is not None and level == 0:
            set_paragraph_numbering(paragraph, restart_id, 0)


def add_table(doc, block: dict) -> None:
    header = block.get("header")
    rows = block.get("rows", [])
    if header is not None and not isinstance(header, list):
        raise SpecError('table "header" must be a list')
    if not isinstance(rows, list) or any(not isinstance(r, list) for r in rows):
        raise SpecError('table "rows" must be a list of lists')
    ncols = max([len(header or [])] + [len(r) for r in rows])
    if ncols == 0:
        raise SpecError("table has no columns")
    table = doc.add_table(rows=0, cols=ncols)
    style = pick_style(doc, block.get("style", "Table Grid"), "Table Grid", "table", " (no borders)")
    if style:
        table.style = style
    if header:
        cells = table.add_row().cells
        for index, value in enumerate(header):
            paragraph = cells[index].paragraphs[0]
            run = paragraph.add_run("" if value is None else str(value))
            run.bold = block.get("header_bold", True)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = "" if value is None else str(value)
    widths = block.get("col_widths_in")
    if widths:
        table.autofit = False
        for row in table.rows:
            for index, width in enumerate(widths[:ncols]):
                row.cells[index].width = Inches(float(width))
    if block.get("align") in ALIGNMENTS:
        from docx.enum.table import WD_TABLE_ALIGNMENT

        table.alignment = {
            "left": WD_TABLE_ALIGNMENT.LEFT,
            "center": WD_TABLE_ALIGNMENT.CENTER,
            "right": WD_TABLE_ALIGNMENT.RIGHT,
        }.get(block["align"], WD_TABLE_ALIGNMENT.LEFT)
    # A table directly followed by another table merges in Word; keep a spacer.
    doc.add_paragraph()


def add_image(doc, block: dict, base_dir: Path) -> None:
    raw = block.get("path")
    if not raw:
        raise SpecError('image block needs a "path"')
    path = Path(raw)
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        raise SpecError(f"image not found: {path}")
    max_width = content_width(doc)
    width = block.get("width_in")
    try:
        if width is not None:
            if float(width) <= 0:
                raise SpecError(f"image {path.name}: width_in must be greater than 0, got {width}")
            requested = Inches(float(width))
            if requested > max_width:
                warn(f"image {path.name}: width {width} in exceeds the page, clamped")
                requested = max_width
            doc.add_picture(str(path), width=requested)
        else:
            doc.add_picture(str(path))
            shape = doc.inline_shapes[-1]
            if shape.width > max_width:
                warn(
                    f"image {path.name}: native width {shape.width / Inches(1):.1f} in exceeds the page, "
                    f"clamped to {max_width / Inches(1):.1f} in"
                )
                shape.height = int(shape.height * max_width / shape.width)
                shape.width = max_width
    except UnrecognizedImageError as exc:
        raise SpecError(f"image {path} is not a supported image file (PNG, JPEG, GIF, BMP, TIFF)") from exc
    picture_paragraph = doc.paragraphs[-1]
    picture_paragraph.alignment = ALIGNMENTS.get(block.get("align", "center"))
    caption = block.get("caption")
    if caption:
        style = pick_style(doc, "Caption", None, "caption")
        paragraph = doc.add_paragraph(style=style)
        run = paragraph.add_run(str(caption))
        if style is None:
            run.italic = True
        paragraph.alignment = ALIGNMENTS.get(block.get("align", "center"))


def add_section(doc, block: dict) -> None:
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    orientation = block.get("orientation")
    if orientation:
        apply_orientation(section, orientation)


def render_blocks(doc, blocks: list, base_dir: Path) -> None:
    handlers = {
        "heading": lambda b: add_heading(doc, b),
        "paragraph": lambda b: add_paragraph(doc, b),
        "bullets": lambda b: add_list(doc, b, numbered=False),
        "numbered": lambda b: add_list(doc, b, numbered=True),
        "table": lambda b: add_table(doc, b),
        "image": lambda b: add_image(doc, b, base_dir),
        "page_break": lambda b: doc.add_page_break(),
        "section": lambda b: add_section(doc, b),
    }
    for index, block in enumerate(blocks):
        handler = handlers.get(block["type"])
        if handler is None:
            raise SpecError(
                f'block {index}: unknown type "{block["type"]}" '
                f"(expected one of {', '.join(sorted(handlers))})"
            )
        try:
            handler(block)
        except SpecError:
            raise
        except Exception as exc:  # surface the block that failed
            detail = str(exc) or type(exc).__name__
            raise SpecError(f'block {index} ({block["type"]}): {detail}') from exc


# ----------------------------------------------------------------------------- main


def build(args: argparse.Namespace) -> Path:
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise SpecError(f"spec file not found: {spec_path}")
    spec = load_spec(spec_path)
    out = Path(args.out)
    if out.suffix.lower() != ".docx":
        raise SpecError("--out must end with .docx")
    if not out.parent.is_dir():
        raise SpecError(f"output directory does not exist: {out.parent}")

    if args.template:
        template = Path(args.template)
        if not template.is_file():
            raise SpecError(f"template not found: {template}")
        if template.suffix.lower() in (".doc", ".rtf", ".odt"):
            raise SpecError(
                f"template {template.name}: python-docx opens .docx files only; convert it first "
                f"(for example: soffice --headless --convert-to docx {template.name})"
            )
        if template.resolve() == out.resolve():
            raise SpecError("--out must differ from --template")
        try:
            doc = Document(str(template))
        except Exception as exc:  # python-docx raises several types for a bad package
            detail = str(exc) or type(exc).__name__
            raise SpecError(f"cannot open template {template}: {detail}") from exc
        if not args.keep_body:
            clear_body(doc)
    else:
        doc = Document()

    title = args.title or spec.get("title")
    author = args.author or spec.get("author")
    if title:
        doc.core_properties.title = str(title)
    if author:
        doc.core_properties.author = str(author)
        doc.core_properties.last_modified_by = str(author)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    doc.core_properties.created = now
    doc.core_properties.modified = now
    orientation = args.orientation or spec.get("orientation")
    if orientation:
        if orientation not in ("portrait", "landscape"):
            raise SpecError('orientation must be "portrait" or "landscape"')
        for section in doc.sections:
            apply_orientation(section, orientation)

    render_blocks(doc, spec["blocks"], spec_path.parent)
    doc.save(str(out))
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a .docx from a JSON spec of blocks (see the module docstring).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("spec", help="JSON spec file")
    parser.add_argument("--out", required=True, help="output .docx path")
    parser.add_argument("--template", help="base .docx whose styles, headers and footers are kept")
    parser.add_argument(
        "--keep-body",
        action="store_true",
        help="append after the template's existing body instead of replacing it",
    )
    parser.add_argument("--title", help="document title property (overrides the spec)")
    parser.add_argument("--author", help="document author property (overrides the spec)")
    parser.add_argument(
        "--orientation", choices=["portrait", "landscape"], help="page orientation (overrides the spec)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        out = build(args)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(str(out.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
