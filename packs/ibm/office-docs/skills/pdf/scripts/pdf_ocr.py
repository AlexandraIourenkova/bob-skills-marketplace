#!/usr/bin/env python3
"""OCR a scanned PDF with poppler (pdftoppm) and tesseract. Everything runs locally.

Run with:
    uv run --with pypdf --with pdfplumber --with reportlab python pdf_ocr.py scan.pdf -o ocr_out \
        [--lang eng] [--pages 1-3] [--dpi 300] [--searchable-pdf scan_searchable.pdf]

Outputs inside the -o directory:
    page_001.txt, page_002.txt ...   text of every processed page
    <stem>_ocr.txt                   all pages joined with '--- Page N ---' markers
With --searchable-pdf, the page images plus an invisible text layer are merged into that PDF.

Languages: tesseract codes joined with '+', e.g. eng, heb, rus, eng+heb. The language data
must be installed (tesseract --list-langs).

Exit codes: 0 ok, 1 error, 2 tesseract, pdftoppm or language data missing.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def install_hint(tool: str) -> str:
    system = platform.system()
    package = {"tesseract": "tesseract", "pdftoppm": "poppler"}[tool]
    if system == "Darwin":
        return f"brew install {package}"
    if system == "Windows":
        return ("install tesseract (UB Mannheim build) and poppler for Windows, "
                "then add both bin folders to PATH")
    return f"apt install {'tesseract-ocr' if tool == 'tesseract' else 'poppler-utils'}"


def language_hint(missing: list[str]) -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install tesseract-lang (installs all languages)"
    if system == "Windows":
        return "copy <lang>.traineddata into the tessdata folder of the tesseract install"
    return "apt install " + " ".join(f"tesseract-ocr-{code}" for code in missing)


def parse_pages(spec: str, total: int) -> list[int]:
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
    seen: set[int] = set()
    return [n for n in chosen if not (n in seen or seen.add(n))]


def help_epilog(marker: str) -> str | None:
    """Return the module docstring from the line that starts with marker (for --help)."""
    doc = __doc__ or ""
    start = doc.find("\n" + marker)
    return doc[start + 1:] if start >= 0 else None


def run(command: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def installed_languages(tesseract: str) -> list[str]:
    result = run([tesseract, "--list-langs"])
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    codes = []
    for line in lines:
        line = line.strip()
        if not line or line.lower().startswith("list of") or " " in line:
            continue
        codes.append(line)
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OCR a scanned PDF with pdftoppm + tesseract (local tools only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=help_epilog("Outputs inside"))
    parser.add_argument("input", help="scanned PDF")
    parser.add_argument("-o", "--output", required=True, help="output directory for the text files")
    parser.add_argument("--lang", default="eng", help="tesseract language(s), e.g. eng, heb, rus, eng+heb")
    parser.add_argument("--pages", help="1-based pages, e.g. 1-3,7 (default all)")
    parser.add_argument("--dpi", type=int, default=300, help="render resolution (default 300)")
    parser.add_argument("--psm", type=int, default=3, help="tesseract page segmentation mode (default 3)")
    parser.add_argument("--searchable-pdf", help="also write a PDF with an invisible text layer here")
    parser.add_argument("--json", action="store_true", help="print a JSON summary instead of text")
    parser.add_argument("--password", help="password for an encrypted input")
    args = parser.parse_args()

    tesseract = shutil.which("tesseract")
    pdftoppm = shutil.which("pdftoppm")
    missing = [name for name, path in (("tesseract", tesseract), ("pdftoppm", pdftoppm)) if not path]
    if missing:
        for name in missing:
            print(f"error: '{name}' was not found on PATH. Install it with: {install_hint(name)}",
                  file=sys.stderr)
        print("OCR needs both tesseract (recognition) and poppler's pdftoppm (page rendering).",
              file=sys.stderr)
        return 2

    wanted = [code for code in args.lang.split("+") if code]
    available = installed_languages(tesseract)
    absent = [code for code in wanted if available and code not in available]
    if absent:
        print(f"error: tesseract language data missing for {absent}; installed: {available}. "
              f"Install with: {language_hint(absent)}", file=sys.stderr)
        return 2

    source = Path(args.input)
    if not source.is_file():
        print(f"error: input file not found: {source}", file=sys.stderr)
        return 1

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(source))
        # files that only carry an owner password (print/copy restrictions) open with ""
        if reader.is_encrypted and reader.decrypt(args.password or "") == 0:
            if args.password:
                print("error: wrong password", file=sys.stderr)
            else:
                print("error: the PDF is encrypted; pass --password", file=sys.stderr)
            return 1
        total = len(reader.pages)
    except Exception as exc:
        print(f"error: cannot read {source}: {exc}", file=sys.stderr)
        return 1

    try:
        numbers = parse_pages(args.pages, total) if args.pages else list(range(1, total + 1))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.password:
        print("note: pdftoppm receives the password through -upw, so it is visible in the "
              "process list while each page renders", file=sys.stderr)

    page_results = []
    pdf_parts: list[Path] = []
    pdf_layer_failed = False
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".ocr_work_") as work:
        work_dir = Path(work)
        for number in numbers:
            prefix = work_dir / f"page_{number:03d}"
            command = [pdftoppm, "-r", str(args.dpi), "-png", "-f", str(number), "-l", str(number),
                       "-singlefile"]
            if args.password:
                command += ["-upw", args.password]
            command += [str(source), str(prefix)]
            render = run(command)
            image = prefix.with_suffix(".png")
            if render.returncode != 0 or not image.is_file():
                print(f"error: pdftoppm failed on page {number}: {render.stderr.strip()}", file=sys.stderr)
                return 1

            base = work_dir / f"ocr_{number:03d}"
            command = [tesseract, str(image), str(base), "-l", args.lang, "--psm", str(args.psm), "txt"]
            if args.searchable_pdf and not pdf_layer_failed:
                command.append("pdf")
            recognised = run(command)
            text_file = base.with_suffix(".txt")
            if recognised.returncode != 0 or not text_file.is_file():
                print(f"error: tesseract failed on page {number}: {recognised.stderr.strip()}",
                      file=sys.stderr)
                return 1
            text = text_file.read_text(encoding="utf-8", errors="replace")
            (out_dir / f"page_{number:03d}.txt").write_text(text, encoding="utf-8")
            page_results.append({"page": number, "characters": len(text.strip()), "text": text})

            if args.searchable_pdf and not pdf_layer_failed:
                part = base.with_suffix(".pdf")
                if part.is_file():
                    keep = out_dir / f".ocr_part_{number:03d}.pdf"
                    shutil.move(str(part), str(keep))
                    pdf_parts.append(keep)
                else:
                    pdf_layer_failed = True
                    print("warning: this tesseract build did not produce a PDF (pdf.ttf missing in "
                          "tessdata?); continuing with text only", file=sys.stderr)

    combined = out_dir / f"{source.stem}_ocr.txt"
    with combined.open("w", encoding="utf-8") as handle:
        for entry in page_results:
            handle.write(f"--- Page {entry['page']} ---\n{entry['text'].rstrip()}\n\n")

    searchable = None
    if args.searchable_pdf and pdf_parts:
        from pypdf import PdfWriter
        writer = PdfWriter()
        for part in pdf_parts:
            writer.append(PdfReader(str(part)))
        target = Path(args.searchable_pdf)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            writer.write(handle)
        for part in pdf_parts:
            part.unlink(missing_ok=True)
        searchable = str(target)

    empty = [e["page"] for e in page_results if e["characters"] == 0]
    summary = {
        "file": str(source),
        "pages_processed": [e["page"] for e in page_results],
        "language": args.lang,
        "dpi": args.dpi,
        "text_file": str(combined),
        "page_files": [str(out_dir / f"page_{e['page']:03d}.txt") for e in page_results],
        "searchable_pdf": searchable,
        "pages_without_text": empty,
        "characters": sum(e["characters"] for e in page_results),
    }
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"OCR done: {len(page_results)} page(s), {summary['characters']} characters, lang={args.lang}")
        print(f"text: {combined}")
        if searchable:
            print(f"searchable PDF: {searchable}")
        if empty:
            print(f"warning: no text recognised on pages {empty}; try a higher --dpi or another --psm",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
