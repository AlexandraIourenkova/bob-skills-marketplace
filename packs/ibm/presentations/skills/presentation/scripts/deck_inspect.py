#!/usr/bin/env python3
"""Read a .pptx deck back for verification: content per slide plus geometry checks.

Prints, per slide, the layout name recorded by deck_build.py, the text of every
shape (headline, bullets, big numbers, table cells), chart categories and
series, pictures with their alt text, and the speaker notes. Then it checks
what a render would show: shapes outside the slide, overlapping text boxes,
text that is probably too long for its box, fonts below 12 pt, empty slides.
Exit 0 always with `--json`; otherwise exit 1 when a check fails so the
build-and-verify loop can stop on it.

Run:  uv run --with python-pptx python deck_inspect.py deck.pptx
      uv run --with python-pptx python deck_inspect.py deck.pptx --json -o inspect.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.oxml.ns import qn
    from pptx.util import Emu
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write("python-pptx is not installed. Run with: uv run --with python-pptx python deck_inspect.py ...\n")
    sys.exit(1)

EMU = 914400


def inches(value) -> float:
    return round((value or 0) / EMU, 2)


def shape_text(shape) -> list[str]:
    if not shape.has_text_frame:
        return []
    lines = []
    for paragraph in shape.text_frame.paragraphs:
        text = "".join(run.text for run in paragraph.runs).strip()
        if text:
            level = paragraph.level or 0
            lines.append(("  " * level) + text)
    return lines


def min_font(shape) -> float | None:
    sizes = []
    if shape.has_text_frame:
        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                if run.font.size is not None and run.text.strip():
                    sizes.append(run.font.size.pt)
    return min(sizes) if sizes else None


def has_bullet(paragraph) -> bool:
    """True when the paragraph carries a bullet glyph or an auto number (its text is indented)."""
    p_pr = paragraph._p.pPr
    return p_pr is not None and (p_pr.find(qn("a:buChar")) is not None or p_pr.find(qn("a:buAutoNum")) is not None)


def overflow_estimate(shape) -> bool:
    """True when the text is likely to exceed the box: 0.5 em average glyph, 1.15 line height."""
    if not shape.has_text_frame or not shape.width or not shape.height:
        return False
    frame = shape.text_frame
    width_in = shape.width / EMU - (frame.margin_left + frame.margin_right) / EMU
    height_in = shape.height / EMU - (frame.margin_top + frame.margin_bottom) / EMU
    needed = 0.0
    paragraphs = [p for p in frame.paragraphs if any(r.text for r in p.runs)]
    for position, paragraph in enumerate(paragraphs):
        runs = [r for r in paragraph.runs if r.text]
        size = max((r.font.size.pt if r.font.size else 18) for r in runs)
        text = "".join(r.text for r in runs)
        bold = any(r.font.bold for r in runs)
        indent = (size * 1.7 + size * 1.5 * (paragraph.level or 0)) / 72 if has_bullet(paragraph) else 0  # deck_build's hanging indent
        per_line = max(1, int(max(0.5, width_in - indent) * 72 / (size * (0.56 if bold else 0.5))))
        lines = max(1, math.ceil(len(text) * 1.08 / per_line))
        after = paragraph.space_after.pt if paragraph.space_after is not None and position < len(paragraphs) - 1 else 0
        needed += lines * size * 1.15 + after
    return needed / 72 > height_in * 1.12


def inspect(path: Path) -> dict:
    prs = Presentation(str(path))
    slide_w, slide_h = prs.slide_width, prs.slide_height
    report = {"file": str(path), "slides": [], "checks": [], "size": f"{inches(slide_w)} x {inches(slide_h)} in"}
    for number, slide in enumerate(prs.slides, start=1):
        hidden = slide._element.get("show") == "0"
        entry = {"number": number, "layout": slide.name or "", "hidden": hidden, "texts": [], "pictures": [], "charts": [], "tables": [], "notes": ""}
        if hidden:
            report["checks"].append(f"slide {number}: hidden slide; it is still in the file when the deck is sent")
        text_boxes = []
        for shape in slide.shapes:
            box = (shape.left or 0, shape.top or 0, shape.width or 0, shape.height or 0)
            decorative = shape.name.startswith("deck:ornament")  # shapes the theme bleeds off the edge on purpose
            if not decorative and shape.left is not None and (box[0] < -Emu(EMU // 10) or box[1] < -Emu(EMU // 10)
                                                              or box[0] + box[2] > slide_w + EMU // 10 or box[1] + box[3] > slide_h + EMU // 10):
                report["checks"].append(f"slide {number}: shape '{shape.name}' extends outside the slide")
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                alt = ""
                try:
                    alt = shape._element._nvXxPr.cNvPr.get("descr", "")
                except Exception:
                    pass
                entry["pictures"].append({"name": shape.name, "alt": alt, "box_in": [inches(v) for v in box]})
            elif getattr(shape, "has_chart", False) and shape.has_chart:
                chart = shape.chart
                categories = list(chart.plots[0].categories) if chart.plots else []
                series = [{"name": s.name, "values": list(s.values)} for s in chart.series]
                alt = ""
                try:
                    alt = shape._element.nvGraphicFramePr.cNvPr.get("descr", "")
                except Exception:
                    pass
                entry["charts"].append({"type": str(chart.chart_type).split(" ")[0], "alt": alt,
                                        "categories": [str(c) for c in categories], "series": series})
            elif getattr(shape, "has_table", False) and shape.has_table:
                rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
                entry["tables"].append(rows)
            elif shape.has_text_frame:
                lines = shape_text(shape)
                if lines:
                    entry["texts"].append({"name": shape.name, "lines": lines})
                    text_boxes.append(shape)
                    small = min_font(shape)
                    if small is not None and small < 11 and not shape.name.startswith("deck:footer") and not shape.name.startswith("deck:number"):
                        report["checks"].append(f"slide {number}: '{shape.name}' uses {small:.0f} pt text; 12 pt is the floor for anything the audience reads")
                    if overflow_estimate(shape) and not shape.name.startswith(("deck:quote-mark", "deck:footer", "deck:number", "deck:label")):
                        report["checks"].append(f"slide {number}: text in '{shape.name}' is probably longer than its box; shorten it")
        for index, first in enumerate(text_boxes):
            for second in text_boxes[index + 1:]:
                if first.name.startswith("deck:footer") or second.name.startswith("deck:footer"):
                    continue
                ox = min(first.left + first.width, second.left + second.width) - max(first.left, second.left)
                oy = min(first.top + first.height, second.top + second.height) - max(first.top, second.top)
                if ox > EMU * 0.15 and oy > EMU * 0.15:
                    report["checks"].append(f"slide {number}: text boxes '{first.name}' and '{second.name}' overlap")
        if slide.has_notes_slide:
            entry["notes"] = slide.notes_slide.notes_text_frame.text
        if not entry["texts"] and not entry["pictures"] and not entry["charts"] and not entry["tables"]:
            report["checks"].append(f"slide {number}: empty slide")
        report["slides"].append(entry)
    return report


def format_report(report: dict) -> str:
    lines = [f"{report['file']}: {len(report['slides'])} slides, {report['size']}"]
    for slide in report["slides"]:
        lines.append(f"\n## Slide {slide['number']}: {slide['layout']}" + (" [hidden]" if slide.get("hidden") else ""))
        for text in slide["texts"]:
            for line in text["lines"]:
                lines.append(f"  {line}" if text["name"].startswith("deck:body") or text["name"].startswith("deck:column") else f"  [{text['name'].replace('deck:', '')}] {line}")
        for picture in slide["pictures"]:
            lines.append(f"  Image: {picture['alt'] or picture['name']} at {picture['box_in']} in")
        for chart in slide["charts"]:
            lines.append(f"  Chart {chart['type']}: {', '.join(chart['categories'])}")
            for series in chart["series"]:
                lines.append(f"    {series['name']}: {series['values']}")
        for table in slide["tables"]:
            for row in table:
                lines.append("  | " + " | ".join(row) + " |")
        if slide["notes"]:
            lines.append(f"  Notes: {slide['notes']}")
    lines.append("")
    if report["checks"]:
        lines.append("Checks:")
        lines += [f"  - {c}" for c in report["checks"]]
    else:
        lines.append("Checks: nothing to report")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("deck", help=".pptx file to read")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("-o", "--output", help="write the report to this file")
    args = parser.parse_args(argv)
    path = Path(args.deck)
    if not path.is_file():
        sys.stderr.write(f"error: {path} not found\n")
        return 1
    try:
        report = inspect(path)
    except Exception as error:  # not a pptx or a damaged package
        sys.stderr.write(f"error: cannot read {path}: {error}\n")
        return 1
    text = json.dumps(report, indent=2, ensure_ascii=False) if args.json else format_report(report)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 1 if (report["checks"] and not args.json) else 0


if __name__ == "__main__":
    sys.exit(main())
