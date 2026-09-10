#!/usr/bin/env python3
"""Render a .pptx deck to PDF with LibreOffice (headless) and to one PNG per slide.

The PDF is produced by LibreOffice (soffice). The PNGs are produced by pdftoppm
(poppler) when it is installed; otherwise only the PDF is written. Exit codes:
0 success, 1 conversion failure, 2 LibreOffice not found.

Files written into --outdir: <deck>.pdf and <deck>-<n>.png. Existing files with
those names are replaced, so give each deck its own output directory when names
could collide.

Run:  uv run python pptx_render.py deck.pptx --outdir renders/
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SOFFICE_CANDIDATES = (
    "soffice",
    "libreoffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "C:\\Program Files\\LibreOffice\\program\\soffice.exe",
)

MISSING_MESSAGE = """LibreOffice (soffice) was not found on PATH.
Install it, then run again:
  macOS:          brew install --cask libreoffice
  Debian/Ubuntu:  apt install libreoffice-impress
  Fedora:         dnf install libreoffice-impress
  Windows:        install LibreOffice and add its 'program' folder to PATH
Or pass the executable with --soffice /path/to/soffice.
"""


def find_soffice(explicit: str | None) -> str | None:
    """Return the LibreOffice executable to run, or None when there is none.

    An explicit path is resolved to an absolute path: a bare file name in the
    current directory would otherwise be looked up on PATH by the OS.
    """
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return str(path.resolve())
        return shutil.which(explicit)
    for candidate in SOFFICE_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
        if os.path.isabs(candidate) and Path(candidate).is_file():
            return candidate
    return None


def run(command: list[str], timeout: int, what: str) -> subprocess.CompletedProcess:
    """Run a command and turn every launch or timeout failure into a RuntimeError."""
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{what} did not finish within {timeout} seconds") from None
    except OSError as error:  # missing, not executable, not a program
        raise RuntimeError(f"cannot run {command[0]}: {error}") from None


def convert_to_pdf(soffice: str, deck: Path, outdir: Path, timeout: int) -> Path:
    pdf = outdir / (deck.stem + ".pdf")
    pdf.unlink(missing_ok=True)  # never report a stale PDF as this run's result
    profile = outdir / f".lo-profile-{os.getpid()}"
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        soffice,
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--headless",
        "--norestore",
        "--convert-to", "pdf",
        "--outdir", str(outdir),
        str(deck),
    ]
    try:
        result = run(command, timeout, "LibreOffice")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if result.returncode != 0 or not pdf.is_file():
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"LibreOffice conversion failed (exit {result.returncode}, no {pdf.name} written). {detail}")
    return pdf


def rasterise(pdf: Path, outdir: Path, dpi: int, timeout: int) -> list[Path]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return []
    prefix = outdir / pdf.stem
    for stale in outdir.glob(f"{pdf.stem}-*.png"):
        stale.unlink()
    result = run([pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)], timeout, "pdftoppm")
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed (exit {result.returncode}). {(result.stderr or '').strip()}")
    return sorted(outdir.glob(f"{pdf.stem}-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a .pptx deck to PDF (LibreOffice headless) and PNG per slide (pdftoppm).")
    parser.add_argument("deck", help="input .pptx file")
    parser.add_argument(
        "--outdir", required=True,
        help="existing directory that receives <deck>.pdf and <deck>-<n>.png; files with those names are replaced",
    )
    parser.add_argument("--dpi", type=int, default=110, help="PNG resolution (default 110)")
    parser.add_argument("--pdf-only", action="store_true", help="skip the PNG step even when pdftoppm is installed")
    parser.add_argument("--soffice", help="path to the LibreOffice executable when it is not on PATH")
    parser.add_argument("--timeout", type=int, default=180, help="seconds to wait for LibreOffice (default 180)")
    args = parser.parse_args(argv)

    deck = Path(args.deck)
    if not deck.is_file():
        sys.stderr.write(f"error: deck not found: {deck}\n")
        return 1
    outdir = Path(args.outdir)
    if not outdir.is_dir():
        sys.stderr.write(f"error: --outdir is not an existing directory: {outdir}\n")
        return 1
    soffice = find_soffice(args.soffice)
    if not soffice:
        sys.stderr.write(MISSING_MESSAGE)
        return 2

    try:
        pdf = convert_to_pdf(soffice, deck, outdir, args.timeout)
        print(f"PDF: {pdf}")
        if args.pdf_only:
            return 0
        pngs = rasterise(pdf, outdir, args.dpi, args.timeout)
    except RuntimeError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    if not pngs:
        print("pdftoppm not found: PDF only. Install poppler (brew install poppler / apt-get install poppler-utils) for PNGs.")
        return 0
    print(f"PNG: {len(pngs)} slides")
    for png in pngs:
        print(f"  {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
