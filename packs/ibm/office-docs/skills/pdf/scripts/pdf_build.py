#!/usr/bin/env python3
"""Build a PDF from a JSON spec with reportlab platypus.

Run with:
    uv run --with pypdf --with pdfplumber --with reportlab python pdf_build.py spec.json -o out.pdf

Spec format (all keys except "blocks" are optional):
{
  "title": "Quarterly report",          # document title, drawn on top and stored in metadata
  "author": "Finance team",
  "subject": "Q3 figures",
  "page_size": "A4",                     # or "Letter"
  "orientation": "portrait",             # or "landscape"
  "margins_mm": 20,
  "font": "/path/to/font.ttf",           # override the automatic Unicode font search
  "font_size": 10.5,
  "header": "Quarterly report",          # header text on every page (default: title, "" disables)
  "footer": "Internal use only",         # footer text; page numbers are added on the right
  "page_numbers": true,
  "show_title": true,
  "blocks": [
    {"type": "heading", "text": "Summary", "level": 1},
    {"type": "paragraph", "text": "Plain text. & < > are escaped for you."},
    {"type": "paragraph", "text": "With <b>markup</b>", "markup": true, "align": "justify"},
    {"type": "paragraph", "text": "Hebrew or Arabic text", "rtl": true},
    {"type": "bullets", "items": ["first", "second"]},
    {"type": "numbered", "items": ["step one", "step two"]},
    {"type": "table", "rows": [["Name", "Qty"], ["Bolt", "12"]], "header": true,
     "col_widths_mm": [80, 30]},
    {"type": "image", "path": "chart.png", "width_mm": 120, "caption": "Figure 1"},
    {"type": "spacer", "height_mm": 8},
    {"type": "page_break"}
  ]
}

Relative image paths are resolved against the directory of the spec file.
Right-to-left text (Hebrew, Arabic) is detected in the title, headings, paragraphs, list items,
table cells, header and footer and reversed for display; blocks with "markup": true are left
in logical order and reported. Table widths wider than the text area are scaled down.
Exit codes: 0 ok, 1 bad spec or build failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

FONT_CANDIDATES = [
    # (regular file name, bold file name or None) in order of preference
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("Arial Unicode.ttf", None),
    ("ArialUnicode.ttf", None),
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
]

FONT_DIRS = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.fonts",
    "~/.local/share/fonts",
    "/Library/Fonts",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "~/Library/Fonts",
    "C:/Windows/Fonts",
]

MM = 72.0 / 25.4


def help_epilog(marker: str) -> str | None:
    """Return the module docstring from the line that starts with marker (for --help)."""
    doc = __doc__ or ""
    start = doc.find("\n" + marker)
    return doc[start + 1:] if start >= 0 else None


def find_font_files() -> dict[str, str]:
    """Map lower-cased .ttf file names to paths, scanning the usual font folders."""
    found: dict[str, str] = {}
    for raw in FONT_DIRS:
        root = Path(os.path.expanduser(raw))
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            if len(Path(dirpath).parts) - base_depth >= 4:
                dirnames[:] = []
            for name in filenames:
                if name.lower().endswith(".ttf"):
                    found.setdefault(name.lower(), os.path.join(dirpath, name))
    return found


def register_unicode_font(explicit: str | None) -> tuple[str, str, str | None]:
    """Register a TrueType font family. Returns (regular_name, bold_name, path_or_None)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular_path = bold_path = None
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_file():
            raise FileNotFoundError(f"font file not found: {explicit}")
        regular_path = str(candidate)
        sibling = candidate.with_name(candidate.stem.replace("-Regular", "") + "-Bold" + candidate.suffix)
        if sibling.is_file():
            bold_path = str(sibling)
    else:
        available = find_font_files()
        for regular, bold in FONT_CANDIDATES:
            if regular.lower() in available:
                regular_path = available[regular.lower()]
                if bold and bold.lower() in available:
                    bold_path = available[bold.lower()]
                break

    if not regular_path:
        return "Helvetica", "Helvetica-Bold", None

    pdfmetrics.registerFont(TTFont("DocSans", regular_path))
    bold_name = "DocSans"
    if bold_path:
        pdfmetrics.registerFont(TTFont("DocSans-Bold", bold_path))
        bold_name = "DocSans-Bold"
    pdfmetrics.registerFontFamily("DocSans", normal="DocSans", bold=bold_name,
                                  italic="DocSans", boldItalic=bold_name)
    return "DocSans", bold_name, regular_path


def is_rtl_char(ch: str) -> bool:
    code = ord(ch)
    return (0x0590 <= code <= 0x08FF) or (0xFB1D <= code <= 0xFDFF) or (0xFE70 <= code <= 0xFEFF)


def looks_rtl(text: str) -> bool:
    rtl = sum(1 for ch in text if is_rtl_char(ch))
    ltr = sum(1 for ch in text if ch.isalpha() and not is_rtl_char(ch))
    return rtl > 0 and rtl >= ltr


def visual_rtl_lines(text: str, font_name: str, font_size: float, width: float) -> list[str]:
    """Fallback bidi: wrap words to the frame width, then reverse each line for display.

    Runs of left-to-right characters (digits, Latin) inside a line keep their order.
    Correct for Hebrew; Arabic letters render in isolated forms without a shaping library.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines: list[list[str]] = [[]]
    for word in text.split():
        trial = " ".join(lines[-1] + [word])
        if lines[-1] and stringWidth(trial, font_name, font_size) > width:
            lines.append([word])
        else:
            lines[-1].append(word)

    result = []
    for words in lines:
        line = " ".join(words)
        reversed_line = line[::-1]
        # restore the reading order of embedded LTR runs (numbers, Latin words)
        out, run = [], []
        for ch in reversed_line:
            if ch.isalnum() and not is_rtl_char(ch):
                run.append(ch)
            else:
                if run:
                    out.extend(reversed(run))
                    run = []
                out.append(ch)
        if run:
            out.extend(reversed(run))
        result.append("".join(out))
    return result


def build(spec: dict, spec_dir: Path, output: Path, font_override: str | None) -> dict:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, LETTER, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (Image, ListFlowable, ListItem, PageBreak, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

    try:
        from reportlab.pdfgen.textobject import rtlSupport
    except ImportError:
        rtlSupport = False

    warnings: list[str] = []
    font_name, bold_name, font_path = register_unicode_font(font_override or spec.get("font"))
    if font_path is None:
        warnings.append("no Unicode TrueType font found; using built-in Helvetica "
                        "(Latin-1 only: Hebrew, Arabic, Cyrillic will not render). "
                        "Install DejaVu Sans or pass --font /path/to/font.ttf")

    size_name = str(spec.get("page_size", "A4")).lower()
    if size_name not in ("a4", "letter"):
        raise ValueError("page_size must be 'A4' or 'Letter'")
    page_size = A4 if size_name == "a4" else LETTER
    if str(spec.get("orientation", "portrait")).lower() == "landscape":
        page_size = landscape(page_size)
    margin = float(spec.get("margins_mm", 20)) * MM
    body_size = float(spec.get("font_size", 10.5))
    # SimpleDocTemplate's frame keeps 6 pt of padding on each side of the text area
    avail_width = page_size[0] - 2 * margin - 12

    styles = getSampleStyleSheet()
    body = ParagraphStyle("DocBody", parent=styles["Normal"], fontName=font_name,
                          fontSize=body_size, leading=body_size * 1.35, spaceAfter=body_size * 0.6)
    title_style = ParagraphStyle("DocTitle", parent=styles["Title"], fontName=bold_name,
                                 fontSize=body_size * 2.2, leading=body_size * 2.6, spaceAfter=body_size * 1.2)
    heading_styles = {}
    for level, (mult, space) in {1: (1.6, 1.0), 2: (1.3, 0.8), 3: (1.15, 0.6), 4: (1.05, 0.5)}.items():
        heading_styles[level] = ParagraphStyle(
            f"DocH{level}", parent=styles["Normal"], fontName=bold_name,
            fontSize=body_size * mult, leading=body_size * mult * 1.3,
            spaceBefore=body_size * space, spaceAfter=body_size * 0.5)
    cell_style = ParagraphStyle("DocCell", parent=body, fontSize=body_size * 0.92,
                                leading=body_size * 1.2, spaceAfter=0)
    cell_head = ParagraphStyle("DocCellHead", parent=cell_style, fontName=bold_name)
    caption_style = ParagraphStyle("DocCaption", parent=body, fontSize=body_size * 0.9,
                                   alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
                                   spaceBefore=2, spaceAfter=body_size)
    aligns = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}

    rtl_notes: set[str] = set()

    def make_paragraph(text: str, style, width: float, markup: bool, label: str,
                       rtl: bool | None = None, keep_alignment: bool = False) -> Paragraph:
        """Build a Paragraph; right-to-left text is wrapped and reversed by the fallback.

        width is the space the text will be laid out in (used to wrap before reversing).
        Left-aligned styles switch to right alignment for RTL text unless keep_alignment.
        """
        if rtl is None:
            rtl = looks_rtl(text)
        if not rtl:
            return Paragraph(text if markup else escape(text), style)
        style = ParagraphStyle(f"{style.name}-rtl-{label}", parent=style)
        if style.alignment == TA_LEFT and not keep_alignment:
            style.alignment = TA_RIGHT
        if rtlSupport:
            style.wordWrap = "RTL"
            return Paragraph(text if markup else escape(text), style)
        if markup:
            warnings.append(f'{label}: right-to-left text with "markup": true is drawn in '
                            "logical order and reads reversed; drop the markup for that block")
            return Paragraph(text, style)
        rtl_notes.add("fallback")
        lines = visual_rtl_lines(text, style.fontName, style.fontSize, width)
        return Paragraph("<br/>".join(escape(line) for line in lines), style)

    story = []
    if spec.get("title") and spec.get("show_title", True):
        story.append(make_paragraph(str(spec["title"]), title_style, avail_width, False, "title"))

    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("spec needs a 'blocks' list")

    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or "type" not in block:
            raise ValueError(f"block {index} must be an object with a 'type'")
        kind = str(block["type"]).lower()

        if kind == "heading":
            level = max(1, min(4, int(block.get("level", 1))))
            story.append(make_paragraph(str(block.get("text", "")), heading_styles[level], avail_width,
                                        bool(block.get("markup")), f"block {index} (heading)"))

        elif kind == "paragraph":
            raw = str(block.get("text", ""))
            rtl_flag = block.get("rtl", "auto")
            rtl = looks_rtl(raw) if rtl_flag == "auto" else bool(rtl_flag)
            align = block.get("align")
            if align is not None:
                alignment = aligns.get(str(align).lower(), TA_LEFT)
            else:
                alignment = TA_RIGHT if rtl else TA_LEFT
            style = ParagraphStyle(f"DocPara{index}", parent=body, alignment=alignment)
            story.append(make_paragraph(raw, style, avail_width, bool(block.get("markup")),
                                        f"block {index} (paragraph)", rtl=rtl, keep_alignment=True))

        elif kind in ("bullets", "numbered"):
            items = block.get("items") or []
            if not isinstance(items, list):
                raise ValueError(f"block {index}: 'items' must be a list")
            item_width = avail_width - 36  # list indent plus the bullet gutter
            flow_items = [ListItem(make_paragraph(str(item), body, item_width, bool(block.get("markup")),
                                                  f"block {index} (item {n})"), leftIndent=12)
                          for n, item in enumerate(items, start=1)]
            story.append(ListFlowable(
                flow_items,
                bulletType="bullet" if kind == "bullets" else "1",
                start=None if kind == "bullets" else int(block.get("start", 1)),
                bulletFontName=font_name, bulletFontSize=body_size, leftIndent=18))
            story.append(Spacer(1, body_size * 0.4))

        elif kind == "table":
            rows = block.get("rows") or []
            if not rows or not all(isinstance(r, list) for r in rows):
                raise ValueError(f"block {index}: 'rows' must be a non-empty list of lists")
            has_header = bool(block.get("header", True))
            ncols = max(len(r) for r in rows)
            widths_mm = block.get("col_widths_mm")
            if widths_mm:
                if len(widths_mm) != ncols:
                    raise ValueError(f"block {index}: col_widths_mm needs {ncols} entries")
                col_widths = [float(w) * MM for w in widths_mm]
                if any(w <= 0 for w in col_widths):
                    raise ValueError(f"block {index}: col_widths_mm entries must be positive")
                total_width = sum(col_widths)
                if total_width > avail_width + 0.01:
                    # reportlab draws an over-wide table past the page edge without complaint
                    col_widths = [w * avail_width / total_width for w in col_widths]
                    warnings.append(f"block {index}: table columns add up to {total_width / MM:.0f} mm "
                                    f"but only {avail_width / MM:.0f} mm fit between the margins; "
                                    "the widths were scaled down to fit")
            else:
                col_widths = [avail_width / ncols] * ncols
            data = []
            for r_index, row in enumerate(rows):
                row = list(row) + [""] * (ncols - len(row))
                style = cell_head if (has_header and r_index == 0) else cell_style
                data.append([make_paragraph("" if c is None else str(c), style,
                                            max(col_widths[c_index] - 12, 10), False,
                                            f"block {index} (cell {r_index + 1},{c_index + 1})")
                             for c_index, c in enumerate(row)])
            table = Table(data, colWidths=col_widths, repeatRows=1 if has_header else 0, hAlign="LEFT")
            commands = [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
            if has_header:
                commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")))
            table.setStyle(TableStyle(commands))
            story.append(table)
            story.append(Spacer(1, body_size * 0.8))

        elif kind == "image":
            raw_path = block.get("path")
            if not raw_path:
                raise ValueError(f"block {index}: image needs a 'path'")
            path = Path(raw_path)
            if not path.is_absolute():
                path = spec_dir / path
            if not path.is_file():
                raise FileNotFoundError(f"block {index}: image not found: {path}")
            width = min(float(block.get("width_mm", 100)) * MM, avail_width)
            iw, ih = ImageReader(str(path)).getSize()
            height = width * ih / iw
            image = Image(str(path), width=width, height=height)
            image.hAlign = str(block.get("align", "center")).upper()
            story.append(image)
            if block.get("caption"):
                story.append(Paragraph(escape(str(block["caption"])), caption_style))
            else:
                story.append(Spacer(1, body_size * 0.8))

        elif kind == "spacer":
            story.append(Spacer(1, float(block.get("height_mm", 5)) * MM))

        elif kind == "page_break":
            story.append(PageBreak())

        else:
            raise ValueError(f"block {index}: unknown type '{kind}'")

    header_text = spec.get("header", spec.get("title", "")) or ""
    footer_text = spec.get("footer", "") or ""
    page_numbers = bool(spec.get("page_numbers", True))
    small = max(7.0, body_size * 0.8)

    def furniture_text(text: str) -> str:
        """Header and footer are single canvas strings; reverse RTL text the same way."""
        if text and looks_rtl(text) and not rtlSupport:
            rtl_notes.add("fallback")
            return " ".join(visual_rtl_lines(text, font_name, small, page_size[0]))
        return text

    header_draw = furniture_text(str(header_text))
    footer_draw = furniture_text(str(footer_text))

    class NumberedCanvas(rl_canvas.Canvas):
        """Two-pass canvas: draws 'Page x of y' once the total is known."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_states = []

        def showPage(self):
            self._saved_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_states)
            for state in self._saved_states:
                self.__dict__.update(state)
                self._draw_furniture(total)
                super().showPage()
            super().save()

        def _draw_furniture(self, total: int):
            width, height = page_size
            self.setFont(font_name, small)
            self.setFillColor(colors.HexColor("#666666"))
            title_on_first_page = (self._pageNumber == 1 and bool(spec.get("show_title", True))
                                   and str(header_text) == str(spec.get("title", "")))
            if header_text and not title_on_first_page:
                self.drawString(margin, height - margin * 0.6, header_draw)
                self.setLineWidth(0.3)
                self.line(margin, height - margin * 0.6 - 4, width - margin, height - margin * 0.6 - 4)
            if footer_text:
                self.drawString(margin, margin * 0.5, footer_draw)
            if page_numbers:
                self.drawRightString(width - margin, margin * 0.5, f"Page {self._pageNumber} of {total}")

    doc = SimpleDocTemplate(
        str(output), pagesize=page_size,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
        title=str(spec.get("title", "")), author=str(spec.get("author", "")),
        subject=str(spec.get("subject", "")), creator="pdf_build.py")
    doc.build(story, canvasmaker=NumberedCanvas)

    if "fallback" in rtl_notes:
        warnings.append("right-to-left text was wrapped and reversed by the built-in fallback "
                        "(no rlbidi module); Hebrew is fine, Arabic letters are not joined, "
                        "list bullets stay on the left")

    return {"font": font_name, "font_path": font_path, "blocks": len(blocks), "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a PDF from a JSON spec (reportlab platypus).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=help_epilog("Spec format"))
    parser.add_argument("spec", help="JSON spec file (see --help for the format)")
    parser.add_argument("-o", "--output", required=True, help="PDF to write")
    parser.add_argument("--font", help="TrueType font file to use instead of the automatic search")
    parser.add_argument("--page-size", choices=["A4", "Letter"], help="override the spec page size")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_file():
        print(f"error: spec file not found: {spec_path}", file=sys.stderr)
        return 1
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: spec is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(spec, dict):
        print("error: spec must be a JSON object", file=sys.stderr)
        return 1
    if args.page_size:
        spec["page_size"] = args.page_size

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = build(spec, spec_path.parent.resolve(), output, args.font)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {str(exc).strip()}", file=sys.stderr)  # reportlab messages start with a newline
        return 1
    except Exception as exc:
        print(f"error: build failed: {exc.__class__.__name__}: {str(exc).strip()}", file=sys.stderr)
        return 1

    try:
        from pypdf import PdfReader
        pages = len(PdfReader(str(output)).pages)
    except Exception:
        pages = None

    for warning in result["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)
    font_note = f"{result['font']} ({result['font_path']})" if result["font_path"] else result["font"]
    print(f"wrote {output} ({pages if pages is not None else '?'} pages, {result['blocks']} blocks, font: {font_note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
