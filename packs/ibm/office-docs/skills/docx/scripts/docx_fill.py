#!/usr/bin/env python3
"""Fill {{placeholders}} in a .docx template from a JSON mapping.

Run with:
    uv run --with python-docx python docx_fill.py template.docx --data values.json --out filled.docx
    uv run --with python-docx python docx_fill.py template.docx --list

Placeholders look like {{name}} or {{ client.address }} and may appear in body
paragraphs, tables (nested ones too), text boxes, headers, footers, footnotes
and endnotes. Word often splits a placeholder over several runs (for example
after spell-checking or editing); this script joins the text of the paragraph,
finds the placeholder, writes the value into the first text node it touches
and blanks the remainder, so the formatting of every untouched character stays
exactly as it was. The value takes the formatting of the placeholder's first
character. Newlines in a value become line breaks.

The JSON mapping may be nested; nested keys are addressed with dots
({"client": {"name": "ACME"}} fills {{client.name}}). Values that are null
become an empty string.

Unresolved placeholders (present in the document, absent in the mapping) are
reported on stderr. With --strict nothing is written and the exit code is 1
when any placeholder is unresolved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.oxml import serialize_part_xml
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import qn
except ImportError:  # pragma: no cover
    sys.exit(
        "python-docx is not installed. Run this script with:\n"
        "  uv run --with python-docx python docx_fill.py TEMPLATE.docx --data VALUES.json --out OUT.docx"
    )

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*\}\}")
W_P = qn("w:p")
W_T = qn("w:t")
W_DEL = qn("w:del")
XML_SPACE = qn("xml:space")

PART_TYPES = {
    RT.HEADER: "header",
    RT.FOOTER: "footer",
    RT.FOOTNOTES: "footnotes",
    RT.ENDNOTES: "endnotes",
}


# ----------------------------------------------------------------------- mapping


def flatten(data, prefix: str = "") -> dict[str, str]:
    """Flatten nested dicts into dotted keys; stringify values."""
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        raise ValueError("mapping JSON must be an object")
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten(value, full))
        elif value is None:
            out[full] = ""
        elif isinstance(value, bool):
            out[full] = "true" if value else "false"
        elif isinstance(value, list):
            out[full] = "\n".join("" if v is None else str(v) for v in value)
        else:
            out[full] = str(value)
    return out


# ---------------------------------------------------------------------- traversal


def iter_parts(doc):
    """Yield (label, root element, generic part or None) for the body and every
    header, footer, footnotes and endnotes part.

    Header and footer parts are XML parts whose element is saved automatically.
    Footnotes and endnotes are loaded by python-docx as generic parts that only
    hold bytes, so their XML is parsed here and written back by `store_generic`.
    """
    yield "body", doc.element.body, None
    for rel in doc.part.rels.values():
        label = PART_TYPES.get(rel.reltype)
        if label is None or rel.is_external:
            continue
        part = rel.target_part
        element = getattr(part, "element", None)
        if element is not None:
            yield label, element, None
        elif getattr(part, "blob", None):
            yield label, parse_xml(part.blob), part


def store_generic(part, element) -> None:
    """Write a modified XML tree back into a generic (bytes-only) part.

    `Part.blob` is read-only in python-docx, so the bytes go into the private
    `_blob` attribute that `blob` returns; a future release may rename it.
    """
    part._blob = serialize_part_xml(element)


def paragraph_text_nodes(paragraph):
    """w:t elements that belong directly to this paragraph, in document order.

    Text nodes of nested paragraphs (text boxes) and of tracked deletions are
    skipped; nested paragraphs are visited on their own.
    """
    nodes = []
    for t in paragraph.iter(W_T):
        parent = t.getparent()
        deleted = False
        while parent is not None and parent.tag != W_P:
            if parent.tag == W_DEL:
                deleted = True
            parent = parent.getparent()
        if parent is paragraph and not deleted:
            nodes.append(t)
    return nodes


def set_text(node, text: str) -> None:
    """Write text into a w:t node; embedded newlines become w:br siblings."""
    parts = text.split("\n")
    node.text = parts[0]
    node.set(XML_SPACE, "preserve")
    anchor = node
    for segment in parts[1:]:
        br = OxmlElement("w:br")
        anchor.addnext(br)
        extra = OxmlElement("w:t")
        extra.text = segment
        extra.set(XML_SPACE, "preserve")
        br.addnext(extra)
        anchor = extra


def replace_in_paragraph(paragraph, mapping: dict[str, str] | None, found: Counter, unresolved: Counter) -> int:
    """Replace placeholders in one paragraph. With mapping=None only scan."""
    nodes = paragraph_text_nodes(paragraph)
    if not nodes:
        return 0
    text = "".join(n.text or "" for n in nodes)
    if "{{" not in text:
        return 0
    matches = list(PLACEHOLDER.finditer(text))
    replaced = 0
    # Walk from the last match to the first so earlier offsets stay valid.
    for match in reversed(matches):
        key = match.group(1)
        found[key] += 1
        if mapping is None:
            continue
        if key not in mapping:
            unresolved[key] += 1
            continue
        value = mapping[key]
        start, end = match.span()
        position = 0
        spans = []
        for node in nodes:
            length = len(node.text or "")
            spans.append((position, position + length))
            position += length
        first = next(i for i, (s, e) in enumerate(spans) if e > start)
        s, e = spans[first]
        node_text = nodes[first].text or ""
        suffix = node_text[end - s:] if end <= e else ""
        set_text(nodes[first], node_text[: start - s] + value + suffix)
        for j in range(first + 1, len(nodes)):
            s, e = spans[j]
            if s >= end:
                break
            remaining = (nodes[j].text or "")[max(0, end - s):]
            nodes[j].text = remaining
            if remaining:
                nodes[j].set(XML_SPACE, "preserve")
        replaced += 1
    return replaced


def process(doc, mapping: dict[str, str] | None):
    found: Counter = Counter()
    unresolved: Counter = Counter()
    per_part: Counter = Counter()
    for label, root, generic_part in iter_parts(doc):
        changed = 0
        for paragraph in list(root.iter(W_P)):
            changed += replace_in_paragraph(paragraph, mapping, found, unresolved)
        if changed:
            per_part[label] += changed
            if generic_part is not None:
                store_generic(generic_part, root)
    return found, unresolved, per_part


# ----------------------------------------------------------------------------- main


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace {{placeholders}} in a .docx from a JSON mapping.")
    parser.add_argument("template", help="input .docx with {{placeholders}}")
    parser.add_argument("--data", help="JSON file with the values (object, may be nested)")
    parser.add_argument("--out", help="output .docx path (required unless --list)")
    parser.add_argument("--list", action="store_true", help="only list the placeholders found and exit")
    parser.add_argument("--strict", action="store_true", help="fail (exit 1) if any placeholder is unresolved")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    template = Path(args.template)
    if not template.is_file():
        print(f"error: template not found: {template}", file=sys.stderr)
        return 1
    try:
        doc = Document(str(template))
    except Exception as exc:
        print(f"error: cannot open {template}: {exc}", file=sys.stderr)
        return 1

    if args.list:
        found, _, _ = process(doc, None)
        if not found:
            print("no placeholders found")
        for key in sorted(found):
            print(f"{key}\t{found[key]}")
        return 0

    if not args.data or not args.out:
        print("error: --data and --out are required (or use --list)", file=sys.stderr)
        return 1
    out = Path(args.out)
    if out.suffix.lower() != ".docx":
        print("error: --out must end with .docx", file=sys.stderr)
        return 1
    if out.resolve() == template.resolve():
        print("error: --out must differ from the template", file=sys.stderr)
        return 1
    if not out.parent.is_dir():
        print(f"error: output directory does not exist: {out.parent}", file=sys.stderr)
        return 1
    try:
        mapping = flatten(json.loads(Path(args.data).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"error: cannot load --data: {exc}", file=sys.stderr)
        return 1

    if args.strict:
        found, _, _ = process(doc, None)
        missing = sorted(k for k in found if k not in mapping)
        if missing:
            print("error: unresolved placeholders: " + ", ".join(missing), file=sys.stderr)
            return 1

    found, unresolved, per_part = process(doc, mapping)
    doc.save(str(out))

    total = sum(per_part.values())
    print(f"replaced {total} placeholder(s) in {out.resolve()}")
    for label in sorted(per_part):
        print(f"  {label}: {per_part[label]}")
    unused = sorted(k for k in mapping if k not in found)
    if unused:
        print("unused keys: " + ", ".join(unused))
    if unresolved:
        print("unresolved placeholders: " + ", ".join(sorted(unresolved)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
