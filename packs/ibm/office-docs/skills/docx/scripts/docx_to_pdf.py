#!/usr/bin/env python3
"""Convert a .docx to PDF with LibreOffice in headless mode.

Run with:
    uv run python docx_to_pdf.py report.docx
    uv run python docx_to_pdf.py report.docx --out /path/to/report.pdf

Requires LibreOffice (the soffice binary) on PATH or in its standard install
location. When it cannot be found the script prints a message and exits with
code 2 so callers can distinguish "not installed" from a conversion failure.
No other converter is attempted and nothing is downloaded.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Standard vendor install locations that are often not on PATH.
EXTRA_DIRS = [
    "/Applications/LibreOffice.app/Contents/MacOS",
    "/opt/libreoffice/program",
    "/usr/lib/libreoffice/program",
    r"C:\Program Files\LibreOffice\program",
    r"C:\Program Files (x86)\LibreOffice\program",
]


def find_soffice() -> str | None:
    search_path = os.pathsep.join([os.environ.get("PATH", ""), *EXTRA_DIRS])
    for name in ("soffice", "libreoffice", "soffice.exe"):
        found = shutil.which(name, path=search_path)
        if found:
            return found
    return None


def convert(soffice: str, source: Path, out: Path, timeout: int) -> Path:
    outdir = out.parent
    produced = outdir / (source.stem + ".pdf")
    if produced != out and produced.exists():
        raise RuntimeError(
            f"LibreOffice would write {produced} before renaming to {out}, but that file already exists; "
            "choose --out in another directory or with the same stem as the input"
        )
    command = [
        soffice,
        "--headless",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        str(outdir),
        str(source),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"LibreOffice timed out after {timeout} s") from exc
    if result.returncode != 0 or not produced.is_file():
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"LibreOffice conversion failed (exit {result.returncode}) {details}".rstrip())
    if produced != out:
        produced.replace(out)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a .docx to PDF using LibreOffice headless.")
    parser.add_argument("docx", help="input .docx file")
    parser.add_argument("--out", help="output .pdf path (default: next to the input, same stem)")
    parser.add_argument("--timeout", type=int, default=300, help="seconds to wait for LibreOffice (default 300)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = Path(args.docx)
    if not source.is_file():
        print(f"error: file not found: {source}", file=sys.stderr)
        return 1
    if source.suffix.lower() not in (".docx", ".docm", ".dotx"):
        print(f"error: expected a .docx input, got {source.suffix or 'no extension'}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else source.with_suffix(".pdf")
    if out.suffix.lower() != ".pdf":
        print("error: --out must end with .pdf", file=sys.stderr)
        return 1
    if not out.parent.is_dir():
        print(f"error: output directory does not exist: {out.parent}", file=sys.stderr)
        return 1

    soffice = find_soffice()
    if soffice is None:
        print(
            "LibreOffice (soffice) is not installed or not on PATH; cannot convert to PDF.\n"
            "Install LibreOffice from its official download page or run the conversion "
            "on a machine that has it, then retry.",
            file=sys.stderr,
        )
        return 2
    try:
        result = convert(soffice, source.resolve(), out.resolve(), args.timeout)
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(str(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
