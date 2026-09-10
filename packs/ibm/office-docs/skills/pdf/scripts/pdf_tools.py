#!/usr/bin/env python3
"""Manipulate PDF files with pypdf: merge, split, rotate, extract pages, metadata,
watermark, compress, encrypt and decrypt.

Run with:
    uv run --with pypdf --with pdfplumber --with reportlab python pdf_tools.py <command> ...

Commands and examples (page numbers are 1-based):
    merge a.pdf b.pdf c.pdf -o merged.pdf
    split in.pdf -o out_dir --every 1              # one file per page
    split in.pdf -o out_dir --pages 1-3,4-6,7-      # one file per comma-separated range
    rotate in.pdf -o out.pdf --degrees 90 --pages 2,4
    extract-pages in.pdf -o out.pdf --pages 1-3,7
    metadata in.pdf [--json]                        # print title, author, ...
    metadata in.pdf -o out.pdf --title "T" --author "A" --subject "S"
    watermark in.pdf -o out.pdf --text DRAFT [--opacity 0.25 --angle 45 --font-size 72]
    compress in.pdf -o out.pdf [--remove-images]
    encrypt in.pdf -o out.pdf --password secret [--owner-password admin --algorithm AES-256]
    decrypt in.pdf -o out.pdf --password secret
    decrypt in.pdf -o out.pdf                       # owner-password-only file (opens with "")

Every reading command accepts --password for an encrypted input; files that only carry an
owner password (print/copy restrictions) open without one.
Exit codes: 0 ok, 1 error (bad arguments, file problems, wrong password).
"""

from __future__ import annotations

import argparse
import inspect
import io
import json
import sys
from pathlib import Path


def parse_pages(spec: str, total: int, unique: bool = True) -> list[int]:
    """'1-3,7,10-' -> 1-based page numbers (order kept, duplicates dropped when unique)."""
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
            raise ValueError(f"page range '{part}' is outside 1-{total} or reversed")
        chosen.extend(range(start, end + 1))
    if not unique:
        return chosen
    seen: set[int] = set()
    return [n for n in chosen if not (n in seen or seen.add(n))]


def parse_ranges(spec: str, total: int) -> list[tuple[int, int]]:
    """'1-3,4-6,9' -> [(1,3),(4,6),(9,9)] for split."""
    ranges = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        pages = parse_pages(part, total)
        ranges.append((pages[0], pages[-1]))
    return ranges


def help_epilog(marker: str) -> str | None:
    """Return the module docstring from the line that starts with marker (for --help)."""
    doc = __doc__ or ""
    start = doc.find("\n" + marker)
    return doc[start + 1:] if start >= 0 else None


def open_reader(path: str, password: str | None):
    from pypdf import PdfReader
    from pypdf.errors import DependencyError, PdfReadError

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"input file not found: {source}")
    try:
        reader = PdfReader(str(source))
    except PdfReadError as exc:
        raise ValueError(f"cannot read {source}: {exc}") from exc
    if reader.is_encrypted:
        # files that only carry an owner password (print/copy restrictions) open with ""
        try:
            status = reader.decrypt(password or "")
        except DependencyError as exc:
            raise ValueError(f"{source}: {exc}. AES needs the 'cryptography' package: "
                             "add --with cryptography to the uv run command") from exc
        if status == 0:
            if password:
                raise ValueError(f"{source}: wrong password")
            raise ValueError(f"{source} is encrypted; pass --password")
    return reader


def ensure_output(path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_writer(writer, target: Path) -> None:
    with target.open("wb") as handle:
        writer.write(handle)


# ---------------------------------------------------------------- commands

def cmd_merge(args) -> int:
    from pypdf import PdfWriter

    if len(args.inputs) < 1:
        raise ValueError("merge needs at least one input")
    writer = PdfWriter()
    total = 0
    for path in args.inputs:
        reader = open_reader(path, args.password)
        writer.append(reader)
        total += len(reader.pages)
    target = ensure_output(args.output)
    write_writer(writer, target)
    print(f"wrote {target} ({total} pages from {len(args.inputs)} files)")
    return 0


def cmd_split(args) -> int:
    from pypdf import PdfWriter

    reader = open_reader(args.input, args.password)
    total = len(reader.pages)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.input).stem

    if args.pages:
        ranges = parse_ranges(args.pages, total)
    else:
        every = max(1, int(args.every))
        ranges = [(s, min(s + every - 1, total)) for s in range(1, total + 1, every)]

    written = []
    for index, (start, end) in enumerate(ranges, start=1):
        writer = PdfWriter()
        writer.append(reader, pages=list(range(start - 1, end)))
        label = f"p{start}" if start == end else f"p{start}-{end}"
        if args.pages:
            name = f"{stem}_part{index:02d}_{label}.pdf"
        else:
            name = f"{stem}_{label}.pdf"
        target = out_dir / name
        write_writer(writer, target)
        written.append(target)
    for target in written:
        print(f"wrote {target}")
    print(f"{len(written)} files written to {out_dir}")
    return 0


def cmd_rotate(args) -> int:
    from pypdf import PdfWriter

    if args.degrees % 90 != 0:
        raise ValueError("--degrees must be a multiple of 90")
    reader = open_reader(args.input, args.password)
    total = len(reader.pages)
    numbers = parse_pages(args.pages, total) if args.pages else list(range(1, total + 1))
    writer = PdfWriter(clone_from=reader)
    for number in numbers:
        writer.pages[number - 1].rotate(int(args.degrees))
    target = ensure_output(args.output)
    write_writer(writer, target)
    print(f"wrote {target} (rotated {len(numbers)} page(s) by {args.degrees} degrees)")
    return 0


def cmd_extract_pages(args) -> int:
    from pypdf import PdfWriter

    reader = open_reader(args.input, args.password)
    numbers = parse_pages(args.pages, len(reader.pages), unique=False)
    writer = PdfWriter()
    writer.append(reader, pages=[n - 1 for n in numbers])
    target = ensure_output(args.output)
    write_writer(writer, target)
    print(f"wrote {target} ({len(numbers)} pages: {args.pages})")
    return 0


def metadata_dict(reader) -> dict:
    result = {}
    for key, value in (reader.metadata or {}).items():
        result[str(key).lstrip("/")] = str(value)
    return result


def cmd_metadata(args) -> int:
    from pypdf import PdfWriter

    reader = open_reader(args.input, args.password)
    updates = {}
    for key in ("title", "author", "subject", "keywords", "creator"):
        value = getattr(args, key)
        if value is not None:
            updates["/" + key.capitalize()] = value

    if not updates:
        info = metadata_dict(reader)
        first = reader.pages[0] if reader.pages else None
        summary = {
            "file": args.input,
            "page_count": len(reader.pages),
            "encrypted": bool(reader.is_encrypted),
            "page_size_pt": [round(float(first.mediabox.width), 2), round(float(first.mediabox.height), 2)] if first else None,
            "metadata": info,
        }
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"file: {summary['file']}")
            print(f"pages: {summary['page_count']}")
            print(f"encrypted: {summary['encrypted']}")
            print(f"page size (pt): {summary['page_size_pt']}")
            print("metadata:")
            for key, value in info.items():
                print(f"  {key}: {value}")
            if not info:
                print("  (none)")
        return 0

    if not args.output:
        raise ValueError("setting metadata needs -o OUTPUT")
    writer = PdfWriter(clone_from=reader)
    writer.add_metadata(updates)
    target = ensure_output(args.output)
    write_writer(writer, target)
    print(f"wrote {target} (set {', '.join(k.lstrip('/') for k in updates)})")
    return 0


def make_overlay(width: float, height: float, text: str, font_name: str, font_size: float,
                 opacity: float, angle: float, color: str):
    """Return a one-page pypdf PageObject with the stamp drawn in the middle."""
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    stamp = canvas.Canvas(buffer, pagesize=(width, height))
    stamp.setFont(font_name, font_size)
    stamp.setFillColor(colors.HexColor(color), alpha=opacity)
    stamp.saveState()
    stamp.translate(width / 2.0, height / 2.0)
    stamp.rotate(angle)
    stamp.drawCentredString(0, -font_size / 3.0, text)
    stamp.restoreState()
    stamp.showPage()
    stamp.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def cmd_watermark(args) -> int:
    from pypdf import PdfWriter

    if not args.text.strip():
        raise ValueError("--text must not be empty")
    if not (0.0 < args.opacity <= 1.0):
        raise ValueError("--opacity must be between 0 and 1")
    font_name = "Helvetica-Bold"
    if args.font:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        if not Path(args.font).is_file():
            raise FileNotFoundError(f"font file not found: {args.font}")
        pdfmetrics.registerFont(TTFont("StampFont", args.font))
        font_name = "StampFont"

    reader = open_reader(args.input, args.password)
    total = len(reader.pages)
    numbers = parse_pages(args.pages, total) if args.pages else list(range(1, total + 1))
    writer = PdfWriter(clone_from=reader)
    cache = {}
    for number in numbers:
        page = writer.pages[number - 1]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rotation = int(page.rotation or 0) % 360
        key = (round(width, 2), round(height, 2), rotation)
        if key not in cache:
            # content is drawn in unrotated page space; add the page rotation so the
            # stamp keeps the requested angle in the viewer
            cache[key] = make_overlay(width, height, args.text, font_name, args.font_size,
                                      args.opacity, args.angle + rotation, args.color)
        page.merge_page(cache[key], over=True)
    target = ensure_output(args.output)
    write_writer(writer, target)
    print(f"wrote {target} (stamped '{args.text}' on {len(numbers)} page(s))")
    return 0


def cmd_compress(args) -> int:
    from pypdf import PdfWriter

    source = Path(args.input)
    reader = open_reader(args.input, args.password)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        page.compress_content_streams(level=9)
    if args.remove_images:
        writer.remove_images()
    if hasattr(writer, "compress_identical_objects"):
        params = inspect.signature(writer.compress_identical_objects).parameters
        if "remove_duplicates" in params:
            writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        else:
            writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    target = ensure_output(args.output)
    write_writer(writer, target)
    before = source.stat().st_size
    after = target.stat().st_size
    ratio = (1 - after / before) * 100 if before else 0
    print(f"wrote {target} ({before:,} -> {after:,} bytes, {ratio:.1f}% smaller)")
    if after >= before:
        print("note: no gain; the content streams were already compressed. Large embedded images "
              "dominate most PDFs and are left untouched (see --remove-images).", file=sys.stderr)
    return 0


def cmd_encrypt(args) -> int:
    from pypdf import PdfWriter
    from pypdf.errors import DependencyError

    reader = open_reader(args.input, args.password)
    writer = PdfWriter(clone_from=reader)
    try:
        writer.encrypt(user_password=args.user_password,
                       owner_password=args.owner_password or args.user_password,
                       algorithm=args.algorithm)
    except DependencyError as exc:
        raise ValueError(f"{exc}. AES needs the 'cryptography' package: add --with cryptography "
                         "to the uv run command, or use --algorithm RC4-128") from exc
    target = ensure_output(args.output)
    write_writer(writer, target)
    print(f"wrote {target} (encrypted with {args.algorithm})")
    return 0


def cmd_decrypt(args) -> int:
    from pypdf import PdfWriter

    reader = open_reader(args.input, args.user_password)
    if not reader.is_encrypted:
        print("note: the input was not encrypted; copying it unchanged", file=sys.stderr)
    writer = PdfWriter(clone_from=reader)
    target = ensure_output(args.output)
    write_writer(writer, target)
    print(f"wrote {target} (decrypted)")
    return 0


# ---------------------------------------------------------------- argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge, split, rotate, stamp, compress and protect PDFs (pypdf).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=help_epilog("Commands and examples"))
    sub = parser.add_subparsers(dest="command", required=True)

    def add_password(p):
        p.add_argument("--password", help="password to open an encrypted input")

    p = sub.add_parser("merge", help="concatenate PDFs")
    p.add_argument("inputs", nargs="+", help="input PDFs in order")
    p.add_argument("-o", "--output", required=True)
    add_password(p)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("split", help="split into several files")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True, help="output directory")
    p.add_argument("--pages", help="comma-separated ranges, one file each, e.g. 1-3,4-6")
    p.add_argument("--every", type=int, default=1, help="pages per file (default 1)")
    add_password(p)
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("rotate", help="rotate pages")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--degrees", type=int, required=True, help="90, 180, 270 or -90")
    p.add_argument("--pages", help="pages to rotate (default all)")
    add_password(p)
    p.set_defaults(func=cmd_rotate)

    p = sub.add_parser("extract-pages", help="copy selected pages to a new PDF")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--pages", required=True, help="pages in the order wanted, e.g. 3,1-2")
    add_password(p)
    p.set_defaults(func=cmd_extract_pages)

    p = sub.add_parser("metadata", help="show or set document metadata")
    p.add_argument("input")
    p.add_argument("-o", "--output", help="output PDF when setting values")
    p.add_argument("--title")
    p.add_argument("--author")
    p.add_argument("--subject")
    p.add_argument("--keywords")
    p.add_argument("--creator")
    p.add_argument("--json", action="store_true", help="print metadata as JSON")
    add_password(p)
    p.set_defaults(func=cmd_metadata)

    p = sub.add_parser("watermark", help="stamp text on pages")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--text", required=True, help="stamp text, e.g. DRAFT")
    p.add_argument("--font-size", type=float, default=64)
    p.add_argument("--opacity", type=float, default=0.25)
    p.add_argument("--angle", type=float, default=45, help="counter-clockwise degrees")
    p.add_argument("--color", default="#B00020", help="hex color, default #B00020")
    p.add_argument("--font", help="TrueType font file for non-Latin stamp text")
    p.add_argument("--pages", help="pages to stamp (default all)")
    add_password(p)
    p.set_defaults(func=cmd_watermark)

    p = sub.add_parser("compress", help="recompress content streams and drop duplicates")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--remove-images", action="store_true", help="strip all images")
    add_password(p)
    p.set_defaults(func=cmd_compress)

    p = sub.add_parser("encrypt", help="password-protect a PDF")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--password", dest="user_password", required=True, help="password to open the PDF")
    p.add_argument("--owner-password", help="owner password (default: same as --password)")
    p.add_argument("--algorithm", default="AES-256", choices=["AES-256", "AES-128", "RC4-128", "RC4-40"])
    p.add_argument("--input-password", dest="password", help="password of the input if it is already encrypted")
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("decrypt", help="remove the password from a PDF")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--password", dest="user_password",
                   help="password to open the input (omit for files that only carry an owner password)")
    p.set_defaults(func=cmd_decrypt)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # last resort: still give a readable message and non-zero exit
        print(f"error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
