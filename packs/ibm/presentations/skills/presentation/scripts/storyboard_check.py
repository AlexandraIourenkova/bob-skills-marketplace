#!/usr/bin/env python3
"""Review a storyboard before building: the headline test, slide budgets, structure, timing.

Prints the headline outline (what the audience gets from headlines alone), then
warnings: headlines over 70 characters or that only name a topic, more than six
bullets, bullets longer than one line, numbers on a slide with no source or note,
slides without notes, missing hook or ask, pictures that do not exist, a slide
count that does not fit the time budget. Exit 1 with --strict when there are
warnings, so the loop stops before a weak storyboard becomes a deck.

Run:  uv run python storyboard_check.py storyboard.md --minutes 20
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ inside an installed skill
sys.path.insert(0, str(Path(__file__).resolve().parent))
from storyboard import Slide, Storyboard, StoryboardError, inline_clean, load_storyboard  # noqa: E402

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,.]*\s?(%|percent|k|m|bn|million|billion|x)?(?![A-Za-z])", re.I)
TOPIC_WORDS = ("overview", "update", "agenda", "introduction", "background", "summary", "results", "status", "next steps", "q&a", "questions", "thank you")
ASK_WORDS = ("approve", "decide", "decision", "ask", "next step", "recommend", "we need", "commit", "sign off", "agree", "invest", "hire", "budget", "go / no-go", "go/no-go")
HOOK_WORDS = ("?", "why", "what if", "imagine", "problem", "risk", "cost", "lost", "losing", "opportunity", "surprise", "unexpected")


def check(board: Storyboard, minutes: float | None, reading: bool) -> list[str]:
    warnings: list[str] = []
    content = board.content_slides
    for number, slide in enumerate(board.slides, start=1):
        title = slide.title
        if slide.kind == "content":
            if len(title) > 70:
                warnings.append(f"slide {number}: headline has {len(title)} characters; keep it under 70")
            if len(title.split()) <= 2 and title.lower().rstrip(":") in TOPIC_WORDS:
                warnings.append(f"slide {number}: '{title}' names a topic, not a point; write the conclusion as the headline")
            elif len(title.split()) <= 3 and not NUMBER_RE.search(title) and slide.effective_layout() not in ("closing", "quote", "image", "chart", "table", "timeline"):
                warnings.append(f"slide {number}: '{title}' is short for a headline; does it state what the audience should take away?")
            if " and " in title.lower() and len(title) > 45 and "," in title:
                warnings.append(f"slide {number}: the headline joins two ideas; consider two slides")
        bullets = slide.bullets
        if len(bullets) > 6:
            warnings.append(f"slide {number}: {len(bullets)} bullets; six is the ceiling, three or four read better")
        for item in bullets:
            if len(inline_clean(item.text)) > 90 and slide.effective_layout() in ("bullets", "two-column"):
                warnings.append(f"slide {number}: bullet '{inline_clean(item.text)[:40]}...' is longer than one line; cut it or move the detail to the notes")
        texts = [title, slide.takeaway, *[inline_clean(i.text) for i in slide.items if i.kind in ("bullet", "number", "para")]]
        has_number = any(NUMBER_RE.search(t) for t in texts if t)
        has_chart = any(i.kind == "chart" for i in slide.items)
        if (has_number or has_chart) and not slide.source and not slide.notes and slide.kind == "content" and slide.effective_layout() not in ("timeline", "closing"):
            warnings.append(f"slide {number}: numbers without a 'Source:' line or a note that says where they come from")
        if slide.kind == "content" and not slide.notes and not reading and not slide.appendix:
            warnings.append(f"slide {number}: no speaker notes; write what you will say and where the numbers come from")
        for item in slide.items:
            if item.kind == "image" and item.path is not None and not item.path.is_file():
                warnings.append(f"slide {number}: picture not found: {item.path}")
            if item.kind == "chart" and item.chart and item.chart["type"] in ("pie", "doughnut") and len(item.chart["categories"]) > 5:
                warnings.append(f"slide {number}: {item.chart['type']} with {len(item.chart['categories'])} slices; use a sorted bar chart above five")
        layout = slide.effective_layout()
        if layout == "big-number" and not bullets:
            warnings.append(f"slide {number}: big-number layout without '- value | label | detail' items")
        if layout == "timeline" and len(bullets) > 6:
            warnings.append(f"slide {number}: timeline with {len(bullets)} steps; six fit, split the rest to a second slide")
        if layout == "table" and len(slide.rows) > 9:
            warnings.append(f"slide {number}: table with {len(slide.rows)} rows; nine fit on a slide, the rest belongs in the appendix")
    if content:
        first = content[0]
        opening = (first.title + " " + " ".join(i.text for i in first.items if i.kind in ("bullet", "para"))).lower()
        if not any(word in opening for word in HOOK_WORDS) and not NUMBER_RE.search(first.title) and first.title.lower().rstrip(":") in TOPIC_WORDS:
            warnings.append("opening: the first content slide is an agenda or overview; consider opening with the hook (a number, a question, the problem)")
        main = [s for s in content if not s.appendix] or content
        tail = " ".join((s.title + " " + " ".join(i.text for i in s.items if i.kind in ("bullet", "para", "number"))).lower() for s in main[-2:])
        if not any(word in tail for word in ASK_WORDS):
            warnings.append("ending: the last slides do not state an ask, a decision or next steps; end with what you want the audience to do")
    if len(board.slides) > 1 and not any(s.kind == "title" for s in board.slides):
        warnings.append("no title slide: start the storyboard with '# Deck title'")
    if minutes:
        talk = board.estimated_minutes()
        main = [s for s in content if not s.appendix]
        per_slide = minutes / max(1, len(main))
        if talk > minutes * 1.15:
            warnings.append(f"timing: notes take about {talk} minutes at 130 words per minute; the budget is {minutes}")
        if per_slide < 0.9 and not reading:
            warnings.append(f"timing: {len(main)} content slides in {minutes:g} minutes is {per_slide:.1f} minutes per slide; cut or merge slides, or move some to the appendix")
        if per_slide > 3.5 and not reading:
            warnings.append(f"timing: {per_slide:.1f} minutes per slide; the audience will wait for the next slide, split long slides or add visuals")
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("storyboard", help="storyboard Markdown file")
    parser.add_argument("--minutes", type=float, help="time budget of the talk, for the slide-count and notes checks")
    parser.add_argument("--reading", action="store_true", help="a reading deck sent by email: notes are optional and slides may be denser")
    parser.add_argument("--strict", action="store_true", help="exit 1 when there are warnings")
    parser.add_argument("--quiet", action="store_true", help="only the warnings, no outline")
    args = parser.parse_args(argv)
    try:
        board = load_storyboard(Path(args.storyboard))
    except (StoryboardError, FileNotFoundError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    warnings = check(board, args.minutes, args.reading)
    if not args.quiet:
        print("Headline test (what the audience gets from the headlines alone):")
        print("\n".join(board.headline_outline()))
        counts = {}
        for slide in board.slides:
            counts[slide.effective_layout()] = counts.get(slide.effective_layout(), 0) + 1
        print(f"\n{len(board.slides)} slides ({', '.join(f'{v} {k}' for k, v in counts.items())}); "
              f"about {board.estimated_minutes()} minutes of talk from the notes; {sum(s.words for s in board.slides)} words on slides")
        print()
    if warnings:
        print(f"{len(warnings)} warning(s):")
        print("\n".join(f"  - {w}" for w in warnings))
    else:
        print("Nothing to fix in the storyboard.")
    return 1 if (warnings and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
