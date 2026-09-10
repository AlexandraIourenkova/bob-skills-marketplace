#!/usr/bin/env python3
"""Find and replace text across all slides and speaker notes of a .pptx deck.

The mapping is a JSON file, either an object {"old": "new", ...} or a list of
{"find": "old", "replace": "new"} entries. Replacements keep run formatting:
a match inside one run only changes that run's text; a match that spans several
runs (PowerPoint splits text at every formatting or spell-check boundary) is
written into the first run of the span and removed from the others. A match
never spans a line break (<a:br>) inside a paragraph.

Run:  uv run --with python-pptx python pptx_replace_text.py deck.pptx mapping.json -o out.pptx
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

try:
    from pptx import Presentation
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write("python-pptx is not installed. Run with: uv run --with python-pptx python pptx_replace_text.py ...\n")
    sys.exit(1)

PRESENTATION_MAIN = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
RETYPE_MAIN_RE = re.compile(r"application/vnd\.openxmlformats-officedocument\.presentationml\.(?:template|slideshow)\.main\+xml")
RETYPE_SUFFIXES = (".potx", ".ppsx")


def open_presentation(path: Path):
    """Open a deck; .potx/.ppsx packages are retyped in memory so python-pptx accepts them."""
    if path.suffix.lower() not in RETYPE_SUFFIXES:
        return Presentation(str(path))
    buffer = io.BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info)
            if info.filename == "[Content_Types].xml":
                data = RETYPE_MAIN_RE.sub(PRESENTATION_MAIN, data.decode("utf-8")).encode("utf-8")
            target.writestr(info, data)
    buffer.seek(0)
    return Presentation(buffer)


def load_mapping(path: Path) -> list[tuple[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read mapping {path}: {error}") from None
    pairs: list[tuple[str, str]] = []
    if isinstance(data, dict):
        pairs = [(str(k), str(v)) for k, v in data.items()]
    elif isinstance(data, list):
        for index, entry in enumerate(data):
            if not isinstance(entry, dict) or "find" not in entry or "replace" not in entry:
                raise ValueError(f"mapping entry {index + 1} must be an object with 'find' and 'replace'")
            pairs.append((str(entry["find"]), str(entry["replace"])))
    else:
        raise ValueError("mapping must be a JSON object or a list of {find, replace} objects")
    if not pairs:
        raise ValueError("mapping is empty")
    for old, _ in pairs:
        if old == "":
            raise ValueError("an empty search string is not allowed")
    return pairs


def iter_text_frames(shapes):
    for shape in shapes:
        try:
            is_group = shape.shape_type is not None and shape.shape_type.name == "GROUP"
        except Exception:
            is_group = False
        if is_group:
            yield from iter_text_frames(shape.shapes)
            continue
        if shape.has_text_frame:
            yield shape.text_frame
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    yield cell.text_frame


def run_segments(paragraph) -> list[list]:
    """Runs of a paragraph grouped between <a:br> line breaks.

    paragraph.runs lists the <a:r> children in order but skips the breaks, so
    the children of <a:p> are walked to find where a new line starts; a match
    is then searched inside one segment only.
    """
    runs = iter(paragraph.runs)
    segments: list[list] = [[]]
    for child in paragraph._p:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "r":
            segments[-1].append(next(runs))
        elif tag == "br":
            segments.append([])
    return [segment for segment in segments if segment]


def replace_in_runs(runs: list, texts: list[str], start: int, end: int, new: str) -> None:
    """Write `new` over the characters start..end of the joined run texts."""
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for text in texts:
        offsets.append((cursor, cursor + len(text)))
        cursor += len(text)
    first = next(i for i, (a, b) in enumerate(offsets) if a <= start < b)
    last = next(i for i, (a, b) in enumerate(offsets) if a < end <= b)
    if first == last:
        a, _ = offsets[first]
        runs[first].text = texts[first][: start - a] + new + texts[first][end - a:]
        return
    a_first, _ = offsets[first]
    a_last, _ = offsets[last]
    runs[first].text = texts[first][: start - a_first] + new
    runs[last].text = texts[last][end - a_last:]
    for index in range(first + 1, last):
        runs[index]._r.getparent().remove(runs[index]._r)
    if runs[last].text == "":
        runs[last]._r.getparent().remove(runs[last]._r)


def replace_in_paragraph(paragraph, old: str, new: str, ignore_case: bool) -> int:
    count = 0
    segment_index = 0
    position = 0
    needle = old.lower() if ignore_case else old
    while True:
        segments = run_segments(paragraph)  # recomputed: replacements may remove runs
        if segment_index >= len(segments):
            return count
        runs = segments[segment_index]
        texts = [run.text for run in runs]
        full = "".join(texts)
        haystack = full.lower() if ignore_case else full
        start = haystack.find(needle, position)
        if start < 0:
            segment_index += 1
            position = 0
            continue
        replace_in_runs(runs, texts, start, start + len(old), new)
        count += 1
        position = start + len(new)


def replace_in_frames(frames, pairs: list[tuple[str, str]], ignore_case: bool, per_key: dict[str, int]) -> int:
    total = 0
    for frame in frames:
        for paragraph in frame.paragraphs:
            for old, new in pairs:
                hits = replace_in_paragraph(paragraph, old, new, ignore_case)
                per_key[old] += hits
                total += hits
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find and replace text across all slides and notes of a .pptx deck, keeping run formatting.")
    parser.add_argument("deck", help="input .pptx file (.potx and .ppsx are read too)")
    parser.add_argument("mapping", help="JSON file: {\"old\": \"new\"} or [{\"find\": ..., \"replace\": ...}]")
    parser.add_argument("-o", "--output", help="output .pptx path (required unless --dry-run)")
    parser.add_argument("--ignore-case", action="store_true", help="match case-insensitively")
    parser.add_argument("--dry-run", action="store_true", help="only count matches, write nothing")
    parser.add_argument("--require-match", action="store_true", help="exit 1 without writing the deck when any search string has no match")
    parser.add_argument("--json-report", help="also write the per-slide counts as JSON to this path")
    args = parser.parse_args(argv)

    deck = Path(args.deck)
    if not deck.is_file():
        sys.stderr.write(f"error: deck not found: {deck}\n")
        return 1
    if not args.dry_run and not args.output:
        parser.error("-o/--output is required unless --dry-run")
    output = Path(args.output) if args.output else None
    if output is not None:
        if output.suffix.lower() != ".pptx":
            sys.stderr.write("error: the output path must end with .pptx\n")
            return 1
        if not output.parent.exists():
            sys.stderr.write(f"error: output directory does not exist: {output.parent}\n")
            return 1
    try:
        pairs = load_mapping(Path(args.mapping))
    except ValueError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    try:
        prs = open_presentation(deck)
    except Exception as error:
        sys.stderr.write(f"error: cannot open {deck}: {error}\n")
        return 1

    per_key: dict[str, int] = {old: 0 for old, _ in pairs}
    report: list[dict] = []
    total = 0
    for slide_no, slide in enumerate(prs.slides, start=1):
        on_slide = replace_in_frames(iter_text_frames(slide.shapes), pairs, args.ignore_case, per_key)
        in_notes = 0
        if slide.has_notes_slide:
            in_notes = replace_in_frames(iter_text_frames(slide.notes_slide.shapes), pairs, args.ignore_case, per_key)
        total += on_slide + in_notes
        report.append({"slide": slide_no, "slide_text": on_slide, "notes": in_notes})
        if on_slide or in_notes:
            print(f"slide {slide_no}: {on_slide} in slide text, {in_notes} in notes")

    print(f"total: {total} replacements in {len(prs.slides)} slides")
    missing = [old for old, hits in per_key.items() if hits == 0]
    for old in missing:
        sys.stderr.write(f"warning: no match for {old!r}\n")
    if args.json_report:
        Path(args.json_report).write_text(
            json.dumps({"deck": deck.name, "total": total, "per_slide": report, "per_key": per_key}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.require_match and missing:
        sys.stderr.write("error: --require-match and some search strings had no match; nothing was written\n")
        return 1
    if output is not None and not args.dry_run:
        try:
            prs.save(str(output))
        except OSError as error:
            sys.stderr.write(f"error: cannot write {output}: {error}\n")
            return 1
        print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
