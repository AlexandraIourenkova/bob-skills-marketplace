#!/usr/bin/env python3
"""Extract text, tables and metadata from a PDF with pdfplumber.

Run with:
    uv run --with pypdf --with pdfplumber --with reportlab python pdf_extract.py INPUT.pdf [options]

Examples:
    pdf_extract.py report.pdf                      # text of every page to stdout
    pdf_extract.py report.pdf --pages 1-3,7        # only those pages (1-based)
    pdf_extract.py report.pdf --layout             # keep horizontal spacing (columns)
    pdf_extract.py report.pdf --tables             # text plus tables as Markdown
    pdf_extract.py report.pdf --tables --csv-dir out/tables   # one CSV per table
    pdf_extract.py report.pdf --info               # metadata and page count only
    pdf_extract.py report.pdf --json -o report.json

Exit codes: 0 ok, 1 usage or file error, 3 no text layer found (scanned PDF, run pdf_ocr.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


def parse_pages(spec: str, total: int) -> list[int]:
    """Turn '1-3,7,10-' into a sorted list of unique 1-based page numbers."""
    chosen: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                first, last = part.split("-", 1)
                start = int(first) if first.strip() else 1
                end = int(last) if last.strip() else total
            else:
                start = end = int(part)
        except ValueError:
            raise ValueError(f"page spec '{part}' is not a page number or a range "
                             "like 1-3,7,10-") from None
        if start < 1 or end > total or start > end:
            raise ValueError(
                f"page range '{part}' is outside 1-{total} or reversed"
            )
        chosen.extend(range(start, end + 1))
    seen: set[int] = set()
    ordered = []
    for number in chosen:
        if number not in seen:
            seen.add(number)
            ordered.append(number)
    return ordered


def help_epilog(marker: str) -> str | None:
    """Return the module docstring from the line that starts with marker (for --help)."""
    doc = __doc__ or ""
    start = doc.find("\n" + marker)
    return doc[start + 1:] if start >= 0 else None


def clean_cell(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def table_to_markdown(rows: list[list]) -> str:
    cleaned = [[clean_cell(c).replace("|", "\\|") for c in row] for row in rows]
    if not cleaned:
        return ""
    width = max(len(r) for r in cleaned)
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]
    lines = ["| " + " | ".join(cleaned[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def metadata_to_plain(meta: dict | None) -> dict:
    result = {}
    for key, value in (meta or {}).items():
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        result[str(key)] = value if isinstance(value, (int, float, bool)) else str(value)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract text, tables and metadata from a PDF (pdfplumber).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=help_epilog("Examples:"),
    )
    parser.add_argument("input", help="PDF file to read")
    parser.add_argument("--pages", help="1-based pages, e.g. 1-3,7 (default: all)")
    parser.add_argument("--layout", action="store_true",
                        help="preserve horizontal layout with spaces (good for columns)")
    parser.add_argument("--dedupe", action="store_true",
                        help="drop duplicated characters (fake-bold overprint)")
    parser.add_argument("--tables", action="store_true", help="also extract tables")
    parser.add_argument("--table-strategy", choices=["lines", "text"], default="lines",
                        help="table detection: ruling lines (default) or text alignment")
    parser.add_argument("--csv-dir", help="write every table as CSV into this directory")
    parser.add_argument("--info", action="store_true",
                        help="print only metadata, page count and page size")
    parser.add_argument("--json", action="store_true", help="emit a JSON document")
    parser.add_argument("-o", "--output", help="write the result here instead of stdout")
    parser.add_argument("--password", help="password for an encrypted PDF")
    args = parser.parse_args()

    source = Path(args.input)
    if not source.is_file():
        print(f"error: input file not found: {source}", file=sys.stderr)
        return 1

    try:
        import pdfplumber
    except ImportError:
        print("error: pdfplumber is not installed; run with "
              "'uv run --with pypdf --with pdfplumber --with reportlab python ...'",
              file=sys.stderr)
        return 1

    # probe encryption with pypdf first: pdfminer's error for a missing password is opaque.
    # Files that only carry an owner password (print/copy restrictions) open with "".
    try:
        from pypdf import PdfReader
        probe = PdfReader(str(source))
        if probe.is_encrypted and probe.decrypt(args.password or "") == 0:
            if args.password:
                print("error: wrong password", file=sys.stderr)
            else:
                print("error: the PDF is encrypted; pass --password", file=sys.stderr)
            return 1
    except ImportError:
        pass
    except Exception as exc:
        if exc.__class__.__name__ == "DependencyError":
            print(f"error: {exc}; add --with cryptography to the uv run command", file=sys.stderr)
            return 1
        # any other problem: let pdfplumber report it below

    try:
        pdf = pdfplumber.open(str(source), password=args.password or "")
    except Exception as exc:  # pdfminer raises several exception types
        chain = [exc.__class__.__name__]
        cause = exc.__cause__ or exc.__context__
        if cause is not None:
            chain.append(f"{cause.__class__.__name__}: {cause}")
        print(f"error: cannot open {source}: {'; '.join(chain)}", file=sys.stderr)
        return 1

    with pdf:
        total = len(pdf.pages)
        info = {
            "file": str(source),
            "page_count": total,
            "metadata": metadata_to_plain(pdf.metadata),
        }
        if total:
            first = pdf.pages[0]
            info["page_size_pt"] = [round(float(first.width), 2), round(float(first.height), 2)]

        if args.info:
            if args.json:
                payload = json.dumps(info, indent=2, ensure_ascii=False)
            else:
                lines = [f"file: {info['file']}", f"pages: {total}",
                         f"page size (pt): {info.get('page_size_pt')}", "metadata:"]
                lines += [f"  {k}: {v}" for k, v in info["metadata"].items()] or ["  (none)"]
                payload = "\n".join(lines)
            return write_out(payload, args.output)

        try:
            numbers = parse_pages(args.pages, total) if args.pages else list(range(1, total + 1))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        table_settings = None
        if args.table_strategy == "text":
            table_settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}

        csv_dir = Path(args.csv_dir) if args.csv_dir else None
        if csv_dir:
            csv_dir.mkdir(parents=True, exist_ok=True)

        pages_out = []
        empty_with_images = []
        total_chars = 0
        csv_files = []
        for number in numbers:
            page = pdf.pages[number - 1]
            if args.dedupe:
                page = page.dedupe_chars()
            try:
                text = page.extract_text(layout=args.layout) or ""
            except Exception as exc:
                print(f"warning: page {number}: text extraction failed: {exc}", file=sys.stderr)
                text = ""
            stripped = text.strip()
            total_chars += len(stripped)
            image_count = len(page.images)
            if not stripped and image_count:
                empty_with_images.append(number)

            tables = []
            if args.tables or csv_dir:
                try:
                    tables = page.extract_tables(table_settings) or []
                except Exception as exc:
                    print(f"warning: page {number}: table extraction failed: {exc}", file=sys.stderr)
            if csv_dir:
                for index, rows in enumerate(tables, start=1):
                    target = csv_dir / f"page{number}_table{index}.csv"
                    with target.open("w", newline="", encoding="utf-8") as handle:
                        writer = csv.writer(handle)
                        for row in rows:
                            writer.writerow([clean_cell(c) for c in row])
                    csv_files.append(str(target))

            pages_out.append({
                "number": number,
                "text": text,
                "image_count": image_count,
                "tables": [[[clean_cell(c) for c in row] for row in t] for t in tables],
            })

    scanned = total_chars == 0 and bool(empty_with_images)
    no_text = total_chars == 0

    if args.json:
        info["scanned"] = scanned
        info["pages_without_text_layer"] = empty_with_images
        info["pages"] = pages_out
        if csv_files:
            info["csv_files"] = csv_files
        payload = json.dumps(info, indent=2, ensure_ascii=False)
    else:
        chunks = []
        for entry in pages_out:
            chunks.append(f"--- Page {entry['number']} ---")
            chunks.append(entry["text"].rstrip() if entry["text"].strip() else "(no text layer on this page)")
            if args.tables:
                for index, rows in enumerate(entry["tables"], start=1):
                    chunks.append(f"\n[Table {index} on page {entry['number']}]")
                    chunks.append(table_to_markdown(rows))
            chunks.append("")
        if csv_files:
            chunks.append("CSV files written:")
            chunks.extend(f"  {f}" for f in csv_files)
        payload = "\n".join(chunks)

    code = write_out(payload, args.output)
    if scanned:
        print(f"notice: no text layer found on {len(empty_with_images)} page(s) that contain images; "
              "this looks like a scanned PDF. Run scripts/pdf_ocr.py to OCR it.", file=sys.stderr)
        return 3
    if no_text:
        print("notice: no text found on the selected pages (blank pages or vector-only content). "
              "If the pages are scans, run scripts/pdf_ocr.py.", file=sys.stderr)
        return 3
    if empty_with_images:
        print(f"notice: pages {empty_with_images} have images but no text layer; they may be scans "
              "(scripts/pdf_ocr.py --pages ...).", file=sys.stderr)
    return code


def write_out(payload: str, output: str | None) -> int:
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + ("\n" if not payload.endswith("\n") else ""), encoding="utf-8")
        print(f"wrote {target}", file=sys.stderr)
    else:
        sys.stdout.write(payload + ("\n" if not payload.endswith("\n") else ""))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
