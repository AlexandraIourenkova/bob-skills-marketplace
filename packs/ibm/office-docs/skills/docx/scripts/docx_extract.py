#!/usr/bin/env python3
"""Dump the headings, paragraphs and tables of a .docx as Markdown or JSON.

Run with:
    uv run --with python-docx python docx_extract.py report.docx
    uv run --with python-docx python docx_extract.py report.docx --format json --out report.json
    uv run --with python-docx python docx_extract.py report.docx --tables-only

Body content is walked in document order, so tables appear where they sit
between paragraphs; paragraphs and tables wrapped in content controls
(w:sdt) are included. Header and footer text of every section is included.
In Markdown the Title style is rendered as a setext heading (underlined with
"="), Heading N as N hashes, so a title and a first-level heading stay apart.
Only .docx files are supported; legacy binary .doc files are rejected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:  # pragma: no cover
    sys.exit(
        "python-docx is not installed. Run this script with:\n"
        "  uv run --with python-docx python docx_extract.py FILE.docx"
    )


# ------------------------------------------------------------------ paragraph info


def heading_level(paragraph) -> int | None:
    """0 for Title, N for Heading N (following the base-style chain), else None."""
    style = paragraph.style
    seen: set[str] = set()
    while style is not None and style.name not in seen:
        seen.add(style.name)
        if style.name == "Title":
            return 0
        if style.name.startswith("Heading "):
            try:
                return int(style.name.split()[1])
            except ValueError:
                pass
        style = style.base_style
    ppr = paragraph._p.pPr
    if ppr is not None:
        outline = ppr.find(qn("w:outlineLvl"))
        if outline is not None:
            try:
                val = int(outline.get(qn("w:val")))
            except (TypeError, ValueError):
                return None
            if 0 <= val <= 8:  # 9 means "body text" in OOXML
                return val + 1
    return None


def numbering_props(paragraph) -> tuple[int, int] | None:
    """(numId, ilvl) from the paragraph or its style chain, or None."""
    candidates = []
    ppr = paragraph._p.pPr
    if ppr is not None:
        candidates.append(ppr)
    style = paragraph.style
    seen: set[str] = set()
    while style is not None and style.name not in seen:
        seen.add(style.name)
        if style.element.pPr is not None:
            candidates.append(style.element.pPr)
        style = style.base_style
    for ppr in candidates:
        numpr = ppr.find(qn("w:numPr"))
        if numpr is None:
            continue
        numid = numpr.find(qn("w:numId"))
        ilvl = numpr.find(qn("w:ilvl"))
        if numid is None:
            continue
        num_id = int(numid.get(qn("w:val")))
        level = int(ilvl.get(qn("w:val"))) if ilvl is not None else 0
        if num_id == 0:
            return None  # numId 0 switches numbering off
        return num_id, level
    return None


def number_format(doc, num_id: int, level: int) -> str | None:
    """numFmt value (bullet, decimal, ...) for a numbering instance and level."""
    try:
        numbering = doc.part.numbering_part.element
    except Exception:
        return None
    abstract_id = None
    for num in numbering.findall(qn("w:num")):
        if int(num.get(qn("w:numId"))) == num_id:
            abstract = num.find(qn("w:abstractNumId"))
            abstract_id = abstract.get(qn("w:val")) if abstract is not None else None
            break
    if abstract_id is None:
        return None
    for abstract in numbering.findall(qn("w:abstractNum")):
        if abstract.get(qn("w:abstractNumId")) == abstract_id:
            for lvl in abstract.findall(qn("w:lvl")):
                if int(lvl.get(qn("w:ilvl"))) == level:
                    fmt = lvl.find(qn("w:numFmt"))
                    return fmt.get(qn("w:val")) if fmt is not None else None
    return None


STYLE_LEVEL = re.compile(r"^List (?:Bullet|Number|Paragraph)(?: (\d))?$")


def list_info(doc, paragraph) -> tuple[str, int, int | None] | None:
    """("bullet" | "number", level, numId or None) when the paragraph is a list item."""
    style_name = paragraph.style.name if paragraph.style is not None else ""
    props = numbering_props(paragraph)
    if props is None:
        num_id = None
        if "List Bullet" in style_name:
            kind, level = "bullet", 0
        elif "List Number" in style_name:
            kind, level = "number", 0
        else:
            return None
    else:
        num_id, level = props
        fmt = number_format(doc, num_id, level)
        kind = "bullet" if fmt in (None, "bullet") else "number"
    # Built-in "List Bullet 2" / "List Number 3" styles encode depth in the name.
    match = STYLE_LEVEL.match(style_name)
    if level == 0 and match and match.group(1):
        level = int(match.group(1)) - 1
    return kind, level, num_id


# ------------------------------------------------------------------------- walking


W_P, W_TBL, W_SDT, W_SDT_CONTENT = qn("w:p"), qn("w:tbl"), qn("w:sdt"), qn("w:sdtContent")


def iter_block_items(element, parent):
    """Yield Paragraph and Table objects under `element` in document order.

    Content controls (w:sdt) are transparent: their w:sdtContent is walked as if
    its children sat directly in `element`.
    """
    for child in element.iterchildren():
        if child.tag == W_P:
            yield Paragraph(child, parent)
        elif child.tag == W_TBL:
            yield Table(child, parent)
        elif child.tag == W_SDT:
            content = child.find(W_SDT_CONTENT)
            if content is not None:
                yield from iter_block_items(content, parent)


def cell_text(cell) -> str:
    """Text of a cell; nested tables are flattened to "a | b" lines."""
    lines: list[str] = []
    for item in iter_block_items(cell._tc, cell):
        if isinstance(item, Paragraph):
            lines.append(item.text)
        else:
            for row in table_rows(item):
                lines.append(" | ".join(row))
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines)


def table_rows(table) -> list[list[str]]:
    """Cell text per row; a merged cell is printed once, its span reads as ""."""
    rows = []
    seen: list = []  # w:tc elements already emitted (kept alive so identity is stable)
    for row in table.rows:
        values = []
        for cell in row.cells:
            tc = cell._tc
            if any(tc is done for done in seen):
                values.append("")  # continuation of a horizontal or vertical merge
            else:
                seen.append(tc)
                values.append(cell_text(cell))
        rows.append(values)
    return rows


def paragraph_block(doc, paragraph, include_empty: bool) -> dict | None:
    text = paragraph.text
    if not text.strip() and not include_empty:
        return None
    level = heading_level(paragraph)
    if level is not None:
        return {"type": "heading", "level": level, "text": text}
    block = {"type": "paragraph", "style": paragraph.style.name if paragraph.style else None, "text": text}
    info = list_info(doc, paragraph)
    if info is not None:
        block["list"], block["list_level"], num_id = info
        if num_id is not None:
            block["list_id"] = num_id  # numbering instance; a new id means the list restarts
    return block


def body_blocks(doc, include_empty: bool) -> list[dict]:
    blocks: list[dict] = []
    table_index = 0
    for item in iter_block_items(doc.element.body, doc):
        if isinstance(item, Paragraph):
            block = paragraph_block(doc, item, include_empty)
            if block is not None:
                blocks.append(block)
        else:
            table_index += 1
            blocks.append({"type": "table", "index": table_index, "rows": table_rows(item)})
    return blocks


def header_footer_blocks(doc) -> list[dict]:
    """Text of every header/footer definition, labelled by section and kind."""
    out: list[dict] = []
    for index, section in enumerate(doc.sections, start=1):
        kinds = [
            ("header", section.header),
            ("footer", section.footer),
            ("first_page_header", section.first_page_header),
            ("first_page_footer", section.first_page_footer),
            ("even_page_header", section.even_page_header),
            ("even_page_footer", section.even_page_footer),
        ]
        for kind, part in kinds:
            if part.is_linked_to_previous:
                continue
            lines: list[str] = []
            for item in iter_block_items(part._element, part):
                if isinstance(item, Paragraph):
                    if item.text.strip():
                        lines.append(item.text)
                else:
                    for row in table_rows(item):
                        lines.append(" | ".join(row))
            if lines:
                out.append({"section": index, "kind": kind, "text": lines})
    return out


def properties(doc) -> dict:
    props = doc.core_properties
    return {
        "title": props.title or "",
        "author": props.author or "",
        "subject": props.subject or "",
        "created": props.created.isoformat() if props.created else None,
        "modified": props.modified.isoformat() if props.modified else None,
    }


# ------------------------------------------------------------------------ rendering


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def md_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    padded = [r + [""] * (ncols - len(r)) for r in rows]
    lines = ["| " + " | ".join(md_escape(c) for c in padded[0]) + " |"]
    lines.append("|" + "|".join([" --- "] * ncols) + "|")
    for row in padded[1:]:
        lines.append("| " + " | ".join(md_escape(c) for c in row) + " |")
    return "\n".join(lines)


def render_markdown(data: dict, tables_only: bool) -> str:
    chunks: list[str] = []
    if tables_only:
        for block in data["blocks"]:
            if block["type"] == "table":
                chunks.append(f"### Table {block['index']}\n\n{md_table(block['rows'])}")
        return "\n\n".join(chunks) + ("\n" if chunks else "")
    for hf in data["headers_footers"]:
        label = hf["kind"].replace("_", " ")
        chunks.append(f"> [{label}, section {hf['section']}] " + " / ".join(hf["text"]))
    list_lines: list[str] = []
    counters: dict[int, int] = {}
    current_list: list[int | None] = [None]  # numId of the list being rendered

    def flush_list() -> None:
        if list_lines:
            chunks.append("\n".join(list_lines))
            list_lines.clear()
        counters.clear()
        current_list[0] = None

    for block in data["blocks"]:
        if "list" in block:
            level = block["list_level"]
            list_id = block.get("list_id")
            if level == 0 and list_id is not None and current_list[0] is not None and list_id != current_list[0]:
                flush_list()  # a different numbering instance: the list restarts
            if level == 0 and list_id is not None:
                current_list[0] = list_id
            for deeper in [k for k in counters if k > level]:
                del counters[deeper]
            if block["list"] == "bullet":
                marker = "-"
            else:
                counters[level] = counters.get(level, 0) + 1
                marker = f"{counters[level]}."
            list_lines.append("  " * level + f"{marker} {block['text']}")
            continue
        flush_list()
        if block["type"] == "heading":
            if block["level"] == 0:  # Title style: setext heading, distinct from "# Heading 1"
                title = block["text"]
                chunks.append(f"{title}\n{'=' * max(3, len(title))}")
            else:
                hashes = "#" * max(1, min(6, block["level"]))
                chunks.append(f"{hashes} {block['text']}")
        elif block["type"] == "table":
            chunks.append(md_table(block["rows"]))
        else:
            chunks.append(block["text"])
    flush_list()
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def render_json(data: dict, tables_only: bool) -> str:
    if tables_only:
        payload = {"source": data["source"], "tables": [b for b in data["blocks"] if b["type"] == "table"]}
    else:
        payload = data
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ----------------------------------------------------------------------------- main


def extract(path: Path, include_empty: bool) -> dict:
    doc = Document(str(path))
    return {
        "source": str(path),
        "properties": properties(doc),
        "headers_footers": header_footer_blocks(doc),
        "blocks": body_blocks(doc, include_empty),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract headings, paragraphs and tables from a .docx.")
    parser.add_argument("docx", help="input .docx file")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="output format (default: md)")
    parser.add_argument("--out", help="write to this file instead of stdout")
    parser.add_argument("--tables-only", action="store_true", help="emit only the tables")
    parser.add_argument("--include-empty", action="store_true", help="keep empty paragraphs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = Path(args.docx)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    if path.suffix.lower() == ".doc":
        print(
            "error: legacy binary .doc files are not supported by python-docx; "
            "convert to .docx first (for example with LibreOffice: soffice --headless --convert-to docx FILE.doc)",
            file=sys.stderr,
        )
        return 1
    try:
        data = extract(path, args.include_empty)
    except Exception as exc:  # python-docx raises several types for bad packages
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    text = render_json(data, args.tables_only) if args.format == "json" else render_markdown(data, args.tables_only)
    if args.out:
        out = Path(args.out)
        if not out.parent.is_dir():
            print(f"error: output directory does not exist: {out.parent}", file=sys.stderr)
            return 1
        out.write_text(text, encoding="utf-8")
        print(str(out.resolve()))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
