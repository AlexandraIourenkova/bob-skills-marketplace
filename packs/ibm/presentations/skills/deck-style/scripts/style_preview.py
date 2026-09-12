#!/usr/bin/env python3
"""Show style concepts for a deck as one HTML page, then write the chosen one as theme.json.

Each card draws the same five slides of the user's own deck (title, bullets,
chart, big numbers, section) in that concept, through the same renderer that
builds the HTML deck, so the preview is the deck. The page is self-contained
(no scripts, no network, no external fonts) and opens from disk.

    style_preview.py --title "..." --headline "..." -o style-preview.html   five concepts
    style_preview.py --list                                                 every concept with its purpose
    style_preview.py --choose sketch -o theme.json                          the chosen one as theme.json
    style_preview.py --brand-accent "#0F62FE" ...                           adds a concept built on the brand colour

`--script cyrillic|hebrew|arabic` swaps fonts for ones that cover the script;
`--rtl` previews right-to-left slides. Overrides for --choose: --accent,
--accent2, --bg, --text, --heading-font, --body-font, --align, --name.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "presentation" / "scripts"
sys.dont_write_bytecode = True  # no __pycache__ inside an installed skill
sys.path.insert(0, str(ENGINE))
try:
    from deck_html import SLIDE_CSS, parse_hex, render_slides, theme_vars  # noqa: E402
    from storyboard import parse_storyboard  # noqa: E402
except ImportError:  # pragma: no cover - depends on the install
    sys.stderr.write(f"the presentation skill is missing next to this one: expected {ENGINE}/deck_html.py and storyboard.py\n")
    sys.exit(1)

CONCEPTS: dict[str, dict] = {
    "swiss": {
        "name": "Swiss Minimal", "tagline": "White space, black grotesk type, one bright signal colour",
        "best_for": "product and design audiences, keynotes, any deck that must look confident and calm",
        "mood": "calm, precise, confident", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F2F2F0", "text": "#111111", "muted": "#6B6B6B", "accent": "#F5200C",
                   "accent2": "#0038FF", "line": "#D6D6D3", "on_accent": "#111111",
                   "chart": ["#F5200C", "#111111", "#0038FF", "#8C8C8C", "#FF9F1C", "#C9C9C6"]},
        "fonts": {"heading": "Arial", "body": "Arial", "mono": "Courier New",
                  "css_heading": "'Helvetica Neue', Helvetica, Arial, sans-serif", "css_body": "'Helvetica Neue', Helvetica, Arial, sans-serif"},
        "sizes": {"title": 46, "headline": 32, "body": 20, "small": 12, "number": 68},
        "layout": {"align": "left", "accent_bar": "none", "title_style": "plain", "section_style": "plain", "corner": 0,
                   "bullet": "—", "cards": False, "ornament": "none"},
        "image": "editorial photography, desaturated or black and white, one subject, plenty of empty space",
    },
    "carbon": {
        "name": "IBM Carbon", "tagline": "Corporate grid, Plex type, IBM blue with bright Carbon accents",
        "best_for": "IBM and enterprise audiences, boards, status reviews, proposals that need approval",
        "mood": "strict, engineered, credible", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F4F4F4", "text": "#161616", "muted": "#525252", "accent": "#0F62FE",
                   "accent2": "#8A3FFC", "line": "#C6C6C6", "on_accent": "#FFFFFF",
                   "chart": ["#0F62FE", "#8A3FFC", "#007D79", "#EE5396", "#FA4D56", "#4589FF"]},
        "fonts": {"heading": "IBM Plex Sans", "body": "IBM Plex Sans", "mono": "IBM Plex Mono",
                  "css_heading": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif", "css_body": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif",
                  "css_mono": "'IBM Plex Mono', Consolas, ui-monospace, monospace"},
        "sizes": {"title": 42, "headline": 30, "body": 20, "small": 12, "number": 62},
        "layout": {"align": "left", "accent_bar": "none", "title_style": "split", "section_style": "band", "corner": 0,
                   "bullet": "—", "cards": True, "ornament": "grid"},
        "image": "clean product and workplace photography, blue duotone, or Carbon icons in one weight",
    },
    "cyber-steel": {
        "name": "Cyber Steel", "tagline": "Steel black, hazard amber and cyan, HUD brackets, mono headlines",
        "best_for": "developer conferences, security and platform demos, launches, anything that should feel technical",
        "mood": "tactical, futuristic, high contrast", "dark": True,
        "colors": {"bg": "#0F1216", "surface": "#1A1F26", "text": "#E9EEF4", "muted": "#93A0AE", "accent": "#FFC300",
                   "accent2": "#35D6FF", "line": "#2B333D", "on_accent": "#0F1216",
                   "chart": ["#FFC300", "#35D6FF", "#7CFF6B", "#FF6B6B", "#B79CFF", "#93A0AE"]},
        "fonts": {"heading": "Consolas", "body": "Arial", "mono": "Consolas", "number": "Consolas",
                  "css_heading": "ui-monospace, 'JetBrains Mono', Consolas, 'SF Mono', monospace",
                  "css_body": "'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
                  "css_mono": "ui-monospace, Consolas, monospace"},
        "sizes": {"title": 44, "headline": 30, "body": 20, "small": 12, "number": 66},
        "layout": {"align": "left", "accent_bar": "left", "title_style": "plain", "section_style": "band", "corner": 0,
                   "bullet": "›", "cards": True, "ornament": "hud"},
        "image": "night city and machine-room photography, wireframes, dark UI screenshots, amber and cyan glows",
    },
    "sketch": {
        "name": "Pencil Sketch", "tagline": "Paper white, pencil hatching, hand-drawn rules and ink accents",
        "best_for": "workshops, early concepts, design reviews, teaching, anything still being worked out",
        "mood": "light, human, unfinished on purpose", "dark": False,
        "colors": {"bg": "#FBFAF6", "surface": "#F0EDE4", "text": "#22201C", "muted": "#6E6A62", "accent": "#2E5AAC",
                   "accent2": "#C0392B", "line": "#C9C3B6", "on_accent": "#FBFAF6",
                   "chart": ["#2E5AAC", "#C0392B", "#7A8B5A", "#B98A2E", "#6E6A62", "#9BB0D6"]},
        "fonts": {"heading": "Trebuchet MS", "body": "Trebuchet MS", "mono": "Courier New",
                  "css_heading": "'Bradley Hand', 'Segoe Print', 'Ink Free', 'Trebuchet MS', cursive",
                  "css_body": "'Trebuchet MS', 'Segoe UI', Verdana, sans-serif"},
        "sizes": {"title": 44, "headline": 31, "body": 20, "small": 12, "number": 64},
        "layout": {"align": "left", "accent_bar": "underline", "title_style": "plain", "section_style": "plain", "corner": 0.1,
                   "bullet": "–", "cards": False, "ornament": "hatch"},
        "image": "pencil and ink drawings, whiteboard photographs, hand-drawn diagrams; no polished stock photos",
    },
    "geometric": {
        "name": "Geometric Poster", "tagline": "Bauhaus shapes, cobalt and vermilion blocks, geometric sans",
        "best_for": "keynotes, campaigns, launches, all-hands, anything meant to be remembered from the back row",
        "mood": "bold, graphic, optimistic", "dark": False,
        "colors": {"bg": "#F7F4EF", "surface": "#ECE6DC", "text": "#14110F", "muted": "#5F5850", "accent": "#D93518",
                   "accent2": "#1B4BD6", "line": "#D8D0C4", "on_accent": "#FFFFFF",
                   "chart": ["#D93518", "#1B4BD6", "#E8A700", "#14110F", "#5F5850", "#8FA6D8"]},
        "fonts": {"heading": "Century Gothic", "body": "Century Gothic", "mono": "Courier New",
                  "css_heading": "'Century Gothic', 'Futura', 'Avenir Next', 'Segoe UI', sans-serif",
                  "css_body": "'Century Gothic', 'Futura', 'Avenir Next', 'Segoe UI', sans-serif"},
        "sizes": {"title": 48, "headline": 32, "body": 20, "small": 12, "number": 72},
        "layout": {"align": "left", "accent_bar": "none", "title_style": "plain", "section_style": "accent", "corner": 0,
                   "bullet": "■", "cards": True, "ornament": "shapes"},
        "image": "flat cut-out shapes, high-contrast photography on colour blocks, isometric illustration",
    },
    "midnight": {
        "name": "Midnight Gold", "tagline": "Near-black canvas, warm gold, serif headlines, quiet luxury",
        "best_for": "boards and executives in a dark room, investor evenings, awards and launch events",
        "mood": "calm, expensive, confident", "dark": True,
        "colors": {"bg": "#14120F", "surface": "#1F1C17", "text": "#F2EDE4", "muted": "#A79E90", "accent": "#C9A227",
                   "accent2": "#6FA8A0", "line": "#332E27", "on_accent": "#14120F",
                   "chart": ["#C9A227", "#6FA8A0", "#D98E73", "#8E9BB5", "#A79E90", "#E4D7B8"]},
        "fonts": {"heading": "Georgia", "body": "Calibri", "mono": "Consolas",
                  "css_heading": "Georgia, 'Times New Roman', serif", "css_body": "Calibri, 'Segoe UI', Arial, sans-serif"},
        "sizes": {"title": 44, "headline": 31, "body": 20, "small": 12, "number": 66},
        "layout": {"align": "left", "accent_bar": "underline", "title_style": "plain", "section_style": "band", "corner": 0.04,
                   "bullet": "—", "cards": True, "ornament": "none"},
        "image": "low-key photography, dark product shots, gold or amber light; never bright white images",
    },
    "editorial": {
        "name": "Editorial Serif", "tagline": "Cream paper, serif headlines, magazine rhythm",
        "best_for": "thought leadership, strategy narratives, research and long-form arguments",
        "mood": "considered, literate, warm", "dark": False,
        "colors": {"bg": "#FBF7EF", "surface": "#F1EADB", "text": "#1F1B16", "muted": "#6E6558", "accent": "#7A1E2C",
                   "accent2": "#2F4A3E", "line": "#D9D0BF", "on_accent": "#FBF7EF",
                   "chart": ["#7A1E2C", "#2F4A3E", "#B8862B", "#8C7B6B", "#C9A0A6", "#4E4A44"]},
        "fonts": {"heading": "Georgia", "body": "Calibri", "mono": "Courier New",
                  "css_heading": "Georgia, 'Times New Roman', serif", "css_body": "Calibri, 'Segoe UI', Arial, sans-serif"},
        "sizes": {"title": 44, "headline": 32, "body": 20, "small": 12, "number": 64},
        "layout": {"align": "left", "accent_bar": "underline", "title_style": "band", "section_style": "band", "corner": 0,
                   "bullet": "•", "cards": False, "ornament": "none"},
        "image": "documentary photography with warm tones, or ink illustrations; no gradients",
    },
    "boardroom": {
        "name": "Boardroom Blue", "tagline": "Neutral corporate blue, cards, nothing to argue with",
        "best_for": "executives outside IBM, status reviews, proposals that need approval",
        "mood": "reliable, structured, formal", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F2F4F8", "text": "#161616", "muted": "#525252", "accent": "#0F62FE",
                   "accent2": "#002D9C", "line": "#C6C6C6", "on_accent": "#FFFFFF",
                   "chart": ["#0F62FE", "#002D9C", "#8A3FFC", "#009D9A", "#FF832B", "#A8A8A8"]},
        "fonts": {"heading": "Arial", "body": "Arial", "mono": "Consolas",
                  "css_heading": "'Segoe UI', Arial, sans-serif", "css_body": "'Segoe UI', Arial, sans-serif"},
        "sizes": {"title": 40, "headline": 30, "body": 20, "small": 12, "number": 60},
        "layout": {"align": "left", "accent_bar": "top", "title_style": "split", "section_style": "accent", "corner": 0.06,
                   "bullet": "▪", "cards": True, "ornament": "none"},
        "image": "clean business photography, blue tint, or flat icons in one weight",
    },
    "data-studio": {
        "name": "Data Studio", "tagline": "Dense but ordered, teal and orange, tabular numbers",
        "best_for": "analysts, finance reviews, dashboards, reading decks with many figures",
        "mood": "precise, analytical, quiet", "dark": False,
        "colors": {"bg": "#F7F8FA", "surface": "#FFFFFF", "text": "#1B1F24", "muted": "#5C6570", "accent": "#0E7C86",
                   "accent2": "#E8710A", "line": "#D5DAE0", "on_accent": "#FFFFFF",
                   "chart": ["#0E7C86", "#E8710A", "#3E5C76", "#9BB0C1", "#6FC2C9", "#B26B00"]},
        "fonts": {"heading": "Arial", "body": "Arial", "mono": "Consolas", "number": "Consolas",
                  "css_heading": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif", "css_body": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif",
                  "css_mono": "Consolas, ui-monospace, monospace"},
        "sizes": {"title": 38, "headline": 28, "body": 18, "small": 11, "number": 56},
        "layout": {"align": "left", "accent_bar": "underline", "title_style": "plain", "section_style": "plain", "corner": 0.04,
                   "bullet": "–", "cards": True, "ornament": "grid"},
        "image": "no photographs; charts, small multiples and schematic diagrams only",
    },
    "academic": {
        "name": "Academic Clean", "tagline": "Numbered sections, muted blue, serif and sans pairing",
        "best_for": "research results, lectures, technical reviews, training decks",
        "mood": "clear, credible, unhurried", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F3F5F7", "text": "#22303C", "muted": "#5F6E7A", "accent": "#2E5E8C",
                   "accent2": "#B25D2D", "line": "#D3DAE0", "on_accent": "#FFFFFF",
                   "chart": ["#2E5E8C", "#B25D2D", "#5E8C6A", "#8B7DB2", "#9FB3C4", "#4A4A4A"]},
        "fonts": {"heading": "Cambria", "body": "Calibri", "mono": "Consolas",
                  "css_heading": "Cambria, Georgia, serif", "css_body": "Calibri, 'Segoe UI', Arial, sans-serif"},
        "sizes": {"title": 40, "headline": 30, "body": 20, "small": 12, "number": 56},
        "layout": {"align": "left", "accent_bar": "top", "title_style": "plain", "section_style": "plain", "corner": 0,
                   "bullet": "•", "cards": False, "ornament": "none"},
        "image": "diagrams, figures with captions, archival photographs; no decorative stock images",
    },
    "warm-human": {
        "name": "Warm and Human", "tagline": "Terracotta and sand, rounded cards, people first",
        "best_for": "customer stories, HR and culture, community and non-profit decks",
        "mood": "friendly, warm, approachable", "dark": False,
        "colors": {"bg": "#FFF8F1", "surface": "#F6E7D8", "text": "#2B2118", "muted": "#7A6A5C", "accent": "#B84A32",
                   "accent2": "#5B7F5B", "line": "#E4D3C2", "on_accent": "#FFF8F1",
                   "chart": ["#B84A32", "#5B7F5B", "#E0A458", "#7A6A5C", "#EAA88E", "#3E5C3E"]},
        "fonts": {"heading": "Trebuchet MS", "body": "Trebuchet MS", "mono": "Courier New",
                  "css_heading": "'Avenir Next', 'Trebuchet MS', Verdana, sans-serif", "css_body": "'Avenir Next', 'Trebuchet MS', Verdana, sans-serif"},
        "sizes": {"title": 42, "headline": 30, "body": 20, "small": 12, "number": 60},
        "layout": {"align": "left", "accent_bar": "none", "title_style": "band", "section_style": "band", "corner": 0.16,
                   "bullet": "•", "cards": True, "ornament": "none"},
        "image": "natural-light photographs of real people at work, warm tint; hand-drawn illustrations",
    },
    "nature": {
        "name": "Earth and Nature", "tagline": "Deep green, sand and sky, organic shapes",
        "best_for": "sustainability, agriculture, wellbeing, ESG reporting",
        "mood": "grounded, calm, optimistic", "dark": False,
        "colors": {"bg": "#F6F3EA", "surface": "#E9E4D3", "text": "#1E2A22", "muted": "#5F6B60", "accent": "#1F5E3D",
                   "accent2": "#C99A3B", "line": "#D3CDB8", "on_accent": "#F6F3EA",
                   "chart": ["#1F5E3D", "#C99A3B", "#5A8FBF", "#8A9A5B", "#A0522D", "#7C8B84"]},
        "fonts": {"heading": "Gill Sans MT", "body": "Gill Sans MT", "mono": "Courier New",
                  "css_heading": "'Gill Sans', 'Gill Sans MT', Calibri, sans-serif", "css_body": "'Gill Sans', 'Gill Sans MT', Calibri, sans-serif"},
        "sizes": {"title": 42, "headline": 30, "body": 20, "small": 12, "number": 60},
        "layout": {"align": "left", "accent_bar": "none", "title_style": "split", "section_style": "accent", "corner": 0.2,
                   "bullet": "•", "cards": True, "ornament": "none"},
        "image": "landscape and macro nature photography, green and sand tones, soft light",
    },
    "startup-gradient": {
        "name": "Startup Gradient", "tagline": "White with violet and pink accents, rounded cards, big KPIs",
        "best_for": "investor pitches, product marketing, launch announcements",
        "mood": "ambitious, fresh, fast", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F5F1FF", "text": "#1A1033", "muted": "#6B5F87", "accent": "#6D3DF5",
                   "accent2": "#E0409A", "line": "#E2DAF7", "on_accent": "#FFFFFF",
                   "chart": ["#6D3DF5", "#E0409A", "#FF7A45", "#2BB0A6", "#B39DFF", "#5C5470"]},
        "fonts": {"heading": "Calibri", "body": "Calibri", "mono": "Consolas",
                  "css_heading": "'Segoe UI', Inter, Roboto, Arial, sans-serif", "css_body": "'Segoe UI', Inter, Roboto, Arial, sans-serif"},
        "sizes": {"title": 44, "headline": 32, "body": 20, "small": 12, "number": 68},
        "layout": {"align": "left", "accent_bar": "none", "title_style": "split", "section_style": "accent", "corner": 0.18,
                   "bullet": "•", "cards": True, "ornament": "none"},
        "image": "3D clay renders or gradient abstracts in violet and pink, product screenshots on light UI",
    },
    "mono-ink": {
        "name": "Monochrome Ink", "tagline": "Black on white, thin rules, typographic contrast",
        "best_for": "architecture, law, luxury, any deck that wants to feel printed",
        "mood": "serious, elegant, quiet", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F4F4F4", "text": "#0A0A0A", "muted": "#5A5A5A", "accent": "#0A0A0A",
                   "accent2": "#8A8A8A", "line": "#0A0A0A", "on_accent": "#FFFFFF",
                   "chart": ["#0A0A0A", "#8A8A8A", "#C4C4C4", "#5A5A5A", "#E0E0E0", "#3A3A3A"]},
        "fonts": {"heading": "Georgia", "body": "Arial", "mono": "Courier New",
                  "css_heading": "Georgia, 'Times New Roman', serif", "css_body": "Arial, Helvetica, sans-serif"},
        "sizes": {"title": 46, "headline": 32, "body": 20, "small": 12, "number": 64},
        "layout": {"align": "left", "accent_bar": "underline", "title_style": "plain", "section_style": "plain", "corner": 0,
                   "bullet": "—", "cards": False, "ornament": "none"},
        "image": "black and white photography with strong shapes, or line drawings; never colour photos",
    },
    "playful": {
        "name": "Playful Pastel", "tagline": "Pastel blocks, rounded type, sticker shapes",
        "best_for": "education, workshops, internal events, consumer products",
        "mood": "light, energetic, friendly", "dark": False,
        "colors": {"bg": "#FFFDF7", "surface": "#DFF3EA", "text": "#23283A", "muted": "#6A6F85", "accent": "#684AEE",
                   "accent2": "#FFB347", "line": "#E5E2F5", "on_accent": "#FFFFFF",
                   "chart": ["#684AEE", "#FFB347", "#3DC6A5", "#FF6F91", "#4FA3FF", "#B0B4C8"]},
        "fonts": {"heading": "Arial Rounded MT Bold", "body": "Verdana", "mono": "Courier New",
                  "css_heading": "'Arial Rounded MT Bold', Nunito, Verdana, sans-serif", "css_body": "Verdana, Geneva, sans-serif"},
        "sizes": {"title": 44, "headline": 30, "body": 19, "small": 12, "number": 64},
        "layout": {"align": "left", "accent_bar": "none", "title_style": "band", "section_style": "accent", "corner": 0.25,
                   "bullet": "●", "cards": True, "ornament": "shapes"},
        "image": "flat vector illustrations with pastel fills, simple shapes, no photographs",
    },
}

DEFAULT_FIVE = ["swiss", "carbon", "cyber-steel", "sketch", "geometric"]
AUDIENCE_FIVE = {
    "executives": ["carbon", "swiss", "midnight", "geometric", "editorial"],
    "investors": ["carbon", "geometric", "midnight", "swiss", "startup-gradient"],
    "customers": ["carbon", "swiss", "geometric", "midnight", "warm-human"],
    "technical": ["cyber-steel", "carbon", "swiss", "sketch", "data-studio"],
    "team": ["geometric", "sketch", "swiss", "cyber-steel", "warm-human"],
    "conference": ["geometric", "cyber-steel", "swiss", "midnight", "sketch"],
    "training": ["sketch", "swiss", "carbon", "cyber-steel", "playful"],
    "research": ["swiss", "sketch", "carbon", "midnight", "academic"],
}
DARK_FALLBACK = ["cyber-steel", "midnight"]

SERIF_FONTS = {"Georgia", "Cambria", "Book Antiqua", "Palatino Linotype", "Times New Roman", "Garamond", "Charter", "Baskerville"}
SCRIPT_SAFE = {
    "cyrillic": {"Arial", "Arial Black", "Verdana", "Georgia", "Times New Roman", "Calibri", "Cambria", "Trebuchet MS", "Tahoma",
                 "Courier New", "Consolas", "Segoe UI", "Palatino Linotype", "Century Gothic", "Impact", "IBM Plex Sans", "IBM Plex Mono"},
    "hebrew": {"Arial", "Tahoma", "Times New Roman", "Courier New", "Calibri", "Segoe UI"},
    "arabic": {"Arial", "Tahoma", "Times New Roman", "Courier New", "Calibri", "Segoe UI"},
}
SCRIPT_FALLBACK = {
    "cyrillic": {"serif": "Georgia", "sans": "Arial", "mono": "Courier New"},
    "hebrew": {"serif": "Times New Roman", "sans": "Arial", "mono": "Courier New"},
    "arabic": {"serif": "Times New Roman", "sans": "Arial", "mono": "Courier New"},
}
CSS_SCRIPT_STACK = {
    "cyrillic": "'PT Sans', 'Segoe UI', Arial, sans-serif",
    "hebrew": "'Arial Hebrew', Arial, 'Segoe UI', sans-serif",
    "arabic": "'Geeza Pro', 'Segoe UI', Tahoma, Arial, sans-serif",
}


# --------------------------------------------------------------------------- the picture library
LIBRARY = Path(__file__).resolve().parents[2] / "deck-images" / "assets" / "library"


def library_manifest() -> dict:
    path = LIBRARY / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"packs": {}, "space": {}}


def picture_packs_for(concept_id: str, manifest: dict, limit: int = 4) -> list[tuple[str, dict, Path]]:
    """Packs whose pictures exist and that suit the concept, with the cover picture for the title slide."""
    packs = []
    for pack, info in manifest.get("packs", {}).items():
        if concept_id not in info.get("suits", []):
            continue
        for name in info.get("covers", []):
            for suffix in (".jpg", ".jpeg", ".png"):
                path = LIBRARY / pack / f"{name}{suffix}"
                if path.is_file():
                    packs.append((pack, info, path))
                    break
            else:
                continue
            break
    return packs[:limit]


GENERATED_PATTERNS = ("grid", "bands", "contours", "waves", "mesh")  # strict structures first, soft ones last


def generated_backdrops(concept: dict, tmp: Path) -> list[tuple[str, Path]]:
    """One SVG backdrop per pattern, drawn in the concept's own colours by deck-images."""
    engine = Path(__file__).resolve().parents[2] / "deck-images" / "scripts"
    if str(engine) not in sys.path:
        sys.path.insert(0, str(engine))
    try:
        from visual_assets import load_colors, svg_backdrop  # noqa: PLC0415
    except ImportError:
        return []
    theme_file = tmp / f"theme-{concept.get('id', 'x')}.json"
    theme_file.write_text(json.dumps({"colors": concept["colors"]}), encoding="utf-8")
    colors = load_colors(str(theme_file))
    made = []
    for pattern in GENERATED_PATTERNS:
        target = tmp / f"gen-{concept.get('id', 'x')}-{pattern}.svg"
        try:
            target.write_text(svg_backdrop(colors, pattern, (1600, 900), 7, None, 1.0), encoding="utf-8")
        except Exception:
            continue
        made.append((pattern, target))
    return made


def thumbnail(path: Path, tmp: Path) -> Path:
    """A 640 px JPEG for the preview page when Pillow is around; the original otherwise."""
    try:
        from PIL import Image
    except ImportError:
        return path
    target = tmp / f"{path.parent.name}-{path.stem}.jpg"
    if not target.is_file():
        im = Image.open(path).convert("RGB")
        im.thumbnail((640, 360))
        im.save(target, quality=72, optimize=True)
    return target


# --------------------------------------------------------------------------- colour maths
def luminance(color: str) -> float:
    text = parse_hex(color)[1:]
    channels = []
    for i in (0, 2, 4):
        c = int(text[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    light, dark = max(la, lb), min(la, lb)
    return round((light + 0.05) / (dark + 0.05), 1)


def mix(color: str, other: str, amount: float) -> str:
    a, b = parse_hex(color)[1:], parse_hex(other)[1:]
    parts = [round(int(a[i:i + 2], 16) * (1 - amount) + int(b[i:i + 2], 16) * amount) for i in (0, 2, 4)]
    return "#" + "".join(f"{max(0, min(255, p)):02X}" for p in parts)


def brand_concept(accent: str) -> dict:
    accent = parse_hex(accent)
    on_accent = "#FFFFFF" if contrast(accent, "#FFFFFF") >= 3.5 else "#111111"
    accent2 = mix(accent, "#000000", 0.4)
    return {
        "name": "Brand", "tagline": f"Your brand colour {accent} on a clean white canvas",
        "best_for": "decks that must match the corporate identity; swap the fonts for the brand fonts when the company has them",
        "mood": "on brand, neutral, safe", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F4F4F4", "text": "#161616", "muted": "#525252", "accent": accent,
                   "accent2": accent2, "line": "#D0D0D0", "on_accent": on_accent,
                   "chart": [accent, accent2, mix(accent, "#FFFFFF", 0.45), "#8D8D8D", mix(accent, "#000000", 0.65), "#C6C6C6"]},
        "fonts": {"heading": "Arial", "body": "Arial", "mono": "Consolas",
                  "css_heading": "'Segoe UI', Arial, sans-serif", "css_body": "'Segoe UI', Arial, sans-serif"},
        "sizes": {"title": 42, "headline": 30, "body": 20, "small": 12, "number": 62},
        "layout": {"align": "left", "accent_bar": "top", "title_style": "split", "section_style": "accent", "corner": 0.06,
                   "bullet": "▪", "cards": True, "ornament": "grid"},
        "image": "the company's own photography and icon set from the brand portal",
    }


def contrast_report(colors: dict) -> list[tuple[str, float, bool]]:
    checks = [
        ("text on background", contrast(colors["text"], colors["bg"]), 4.5),
        ("muted text on background", contrast(colors["muted"], colors["bg"]), 4.5),
        ("accent on background (large text, bars)", contrast(colors["accent"], colors["bg"]), 3.0),
        ("text on accent (title panels)", contrast(colors["on_accent"], colors["accent"]), 4.5),
    ]
    return [(label, ratio, ratio >= floor) for label, ratio, floor in checks]


def apply_script(concept: dict, script: str | None) -> dict:
    if not script:
        return concept
    safe, fallback = SCRIPT_SAFE[script], SCRIPT_FALLBACK[script]
    result = json.loads(json.dumps(concept))
    fonts = result["fonts"]
    for role in ("heading", "body", "mono", "number"):
        font = fonts.get(role)
        if not font or font in safe:
            continue
        kind = "mono" if role == "mono" else "serif" if font in SERIF_FONTS else "sans"
        fonts.setdefault("replaced", {})[role] = font
        fonts[role] = fallback[kind]
    for role in ("css_heading", "css_body"):
        if fonts.get("replaced"):
            fonts[role] = CSS_SCRIPT_STACK[script]
    return result


# --------------------------------------------------------------------------- sample deck
def sample_board(text: dict, rtl: bool, backdrop: Path | None = None, scrim: str = "dark", side: str = "left"):
    """A five-slide storyboard from the user's own words: title, bullets, chart, numbers, section."""
    bullets = "\n".join(f"- {b}" for b in text["bullets"])
    numbers = "\n".join(f"- {' | '.join(part for part in item if part)}" for item in text["numbers"])
    meta = ["---", f"title: {text['title']}", f"footer: {text['footer']}"]
    if backdrop is not None:
        meta += [f"backdrop: {backdrop.resolve().as_posix()}", f"backdrop_scrim: {scrim}", f"backdrop_text: {side}"]
    if text["meta"][0]:
        meta.append(f"author: {text['meta'][0]}")
    if text["meta"][1]:
        meta.append(f"date: {text['meta'][1]}")
    if rtl:
        meta.append("language: he")
    meta.append("---")
    chart = json.dumps({"type": "bar", "categories": ["Q1", "Q2", "Q3", "Q4"],
                        "series": [{"name": "2025", "values": [10.2, 11.0, 12.4, 13.1]},
                                   {"name": "2026", "values": [11.9, 13.4, 14.6, 15.5]}],
                        "data_labels": True, "number_format": "0.0"})
    source = "\n".join(meta) + f"""

# {text['title']}
{text['subtitle']}

## {text['headline']}
{bullets}
Takeaway: {text['takeaway']}
Source: {text['source']}

## {text['chart_title']}
layout: chart
```chart
{chart}
```
Source: {text['source']}

## {text['numbers_title']}
layout: big-number
{numbers}

# {text['section']}
{text['section_sub']}
"""
    return parse_storyboard(source, base_dir=Path("."))


# --------------------------------------------------------------------------- page
PAGE_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#ECEEF1;color:#1A1A1A;font:15px/1.5 -apple-system,'Segoe UI',Arial,sans-serif;padding:30px 38px 60px}
h1{font-size:26px;margin:0 0 6px}
p.lead{max-width:980px;margin:0 0 26px;color:#444}
.card{background:#fff;border-radius:14px;padding:22px 24px 20px;margin:0 0 26px;box-shadow:0 1px 4px rgba(0,0,0,.09)}
.card h2{margin:0 0 2px;font-size:20px;display:flex;align-items:center;gap:10px}
.card .num{display:inline-flex;width:30px;height:30px;border-radius:15px;background:#1A1A1A;color:#fff;align-items:center;justify-content:center;font-weight:700;font-size:15px}
.card .tag{color:#666;margin:2px 0 16px}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
.frame{overflow:hidden;border:1px solid #CFD3D9;flex:none;background:#fff;position:relative}
.frame .slide{transform-origin:top left}
.hero{width:576px;height:324px}.hero .slide{transform:scale(.45)}
.grid{display:grid;grid-template-columns:repeat(2,282px);gap:9px;flex:none}
.thumb{width:282px;height:158.6px}.thumb .slide{transform:scale(.22)}
a.frame{text-decoration:none;color:inherit;display:block}
.info{flex:1 1 250px;min-width:230px;font-size:14px}
.info dt{font-weight:700;margin-top:9px}.info dd{margin:0}
.sw{display:inline-block;width:22px;height:22px;border-radius:4px;border:1px solid rgba(0,0,0,.15);vertical-align:middle;margin:2px 3px 2px 0}
.ok{color:#137333}.bad{color:#B3261E;font-weight:700}
code{background:#F1F1F1;padding:1px 5px;border-radius:4px;font-size:13px;font-family:ui-monospace,Consolas,'Courier New',monospace;font-variant-ligatures:none}
.lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:9;align-items:center;justify-content:center}
.lb:target{display:flex}
.lb .big{width:1024px;height:576px;overflow:hidden;box-shadow:0 14px 50px rgba(0,0,0,.55);background:#fff}
.lb .big .slide{transform:scale(.8);transform-origin:top left}
.lb a.close{position:absolute;top:18px;right:24px;color:#fff;font-size:15px;text-decoration:none;background:rgba(255,255,255,.16);padding:6px 12px;border-radius:6px}
footer{color:#555;font-size:13px;max-width:980px}
.pictures{margin-top:18px;border-top:1px solid #E4E6EA;padding-top:12px}
.pictures h3{margin:0 0 10px;font-size:13px;color:#525252;text-transform:uppercase;letter-spacing:1px}
.picrow{display:flex;gap:14px;flex-wrap:wrap}
figure.pic{margin:0;width:282px}
figure.pic figcaption{font-size:12px;color:#333;margin-top:5px;line-height:1.35}
figure.pic figcaption span{color:#666}
figure.pic figcaption b{display:inline-block;min-width:20px;height:20px;border-radius:10px;background:#1A1A1A;color:#fff;text-align:center;line-height:20px;font-size:11px;margin-right:4px}
.hint{font-size:13px;color:#555;margin:10px 0 0}
"""


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def picture_row(concept_id: str, concept: dict, text: dict, rtl: bool, manifest: dict, tmp: Path) -> str:
    """Mini title slides, one per picture pack that suits the concept, so style and pictures are chosen together."""
    packs = picture_packs_for(concept_id, manifest)
    if not packs:
        return ""
    variables = theme_vars(concept)
    scrims = {"pack-a": "none", "pack-b": "dark", "pack-c": "none", "pack-d": "dark", "pack-e": "none", "pack-f": "none"}  # the title sits on the calm side
    cells = []
    for number, (pack, info, cover) in enumerate(packs, start=1):
        key = f"{pack}/{cover.stem}"
        board = sample_board(text, rtl, backdrop=thumbnail(cover, tmp), scrim=scrims.get(pack, "dark"), side="left")  # pictures carry their subject on the right
        slides, _ = render_slides(board, concept, base_dir=Path("."))
        cells.append(f'<figure class="pic"><a class="frame thumb" href="#{concept_id}-p{number}"><div style="{variables}">{slides[0]}</div></a>'
                     f'<figcaption><b>{number}</b> {esc(info.get("name", pack))} <code>{pack}</code><br><span>{esc(info.get("look", ""))}</span></figcaption></figure>')
        cells.append(f'<div class="lb" id="{concept_id}-p{number}"><a class="close" href="#c-{concept_id}">close</a>'
                     f'<div class="big"><div style="{variables}">{slides[0]}</div></div></div>')
    generated = []
    for offset, (pattern, path) in enumerate(generated_backdrops(concept, tmp), start=len(packs) + 1):
        board = sample_board(text, rtl, backdrop=path, scrim="none", side="left")
        slides, _ = render_slides(board, concept, base_dir=Path("."))
        generated.append(f'<figure class="pic"><a class="frame thumb" href="#{concept_id}-p{offset}"><div style="{variables}">{slides[0]}</div></a>'
                         f'<figcaption><b>{offset}</b> Generated <code>{pattern}</code><br><span>drawn in this theme\u2019s colours, no photograph</span></figcaption></figure>')
        generated.append(f'<div class="lb" id="{concept_id}-p{offset}"><a class="close" href="#c-{concept_id}">close</a>'
                         f'<div class="big"><div style="{variables}">{slides[0]}</div></div></div>')
    heading = "With pictures from the library, or a generated backdrop" if generated else "With pictures from the library"
    return (f'<div class="pictures"><h3>{heading}</h3><div class="picrow">' + "".join(cells + generated) +
            '</div><p class="hint">Say the concept and the picture set together: "3 with pictures 2". "No pictures" keeps the plain title; '
            'a generated backdrop is drawn from the theme colours, so it never clashes and needs no licence.</p></div>')


def concept_card(index: int, concept_id: str, concept: dict, slides: list[str], pictures: str = "") -> tuple[str, str]:
    names = ["Title slide", "Headline and bullets", "Chart", "Big numbers", "Section divider"]
    variables = theme_vars(concept)
    def frame(cls: str, position: int) -> str:
        return (f'<a class="frame {cls}" href="#{concept_id}-{position}" title="{names[position]}">'
                f'<div style="{variables}">{slides[position]}</div></a>')
    thumbs = "".join(frame("thumb", i) for i in range(1, 5))
    lightboxes = "".join(
        f'<div class="lb" id="{concept_id}-{i}"><a class="close" href="#c-{concept_id}">close</a>'
        f'<div class="big"><div style="{variables}">{slides[i]}</div></div></div>' for i in range(5))
    colors = concept["colors"]
    swatches = "".join(f'<span class="sw" style="background:{c}" title="{c}"></span>' for c in
                       [colors["bg"], colors["text"], colors["accent"], colors["accent2"], colors["surface"]] + colors["chart"])
    checks = "".join(f'<div class="{"ok" if ok else "bad"}">{esc(label)}: {ratio}:1{"" if ok else " (below the floor)"}</div>'
                     for label, ratio, ok in contrast_report(colors))
    fonts = concept["fonts"]
    replaced = fonts.get("replaced", {})
    font_line = f"{esc(fonts['heading'])} for headlines, {esc(fonts['body'])} for text"
    if replaced:
        font_line += " (swapped for script coverage from " + ", ".join(esc(v) for v in replaced.values()) + ")"
    card = f"""
<section class="card" id="c-{concept_id}">
  <h2><span class="num">{index}</span>{esc(concept['name'])} <code>{concept_id}</code></h2>
  <p class="tag">{esc(concept['tagline'])}</p>
  <div class="row">
    {frame('hero', 0)}
    <div class="grid">{thumbs}</div>
    <dl class="info">
      <dt>Best for</dt><dd>{esc(concept['best_for'])}</dd>
      <dt>Mood</dt><dd>{esc(concept['mood'])}</dd>
      <dt>Fonts</dt><dd>{font_line}</dd>
      <dt>Palette</dt><dd>{swatches}</dd>
      <dt>Contrast</dt><dd>{checks}</dd>
      <dt>Images</dt><dd>{esc(concept['image'])}</dd>
      <dt>Choose it</dt><dd><code>--choose {concept_id}</code>, with pictures: <code>--choose {concept_id} --pictures pack-x</code></dd>
    </dl>
  </div>
  {pictures}
</section>"""
    return card, lightboxes


def build_page(chosen: list[tuple[str, dict]], text: dict, rtl: bool, with_pictures: bool = True) -> str:
    import tempfile
    board = sample_board(text, rtl)
    manifest = library_manifest() if with_pictures else {"packs": {}, "space": {}}
    tmp = Path(tempfile.mkdtemp(prefix="deck-preview-"))
    cards, boxes = [], []
    for index, (concept_id, concept) in enumerate(chosen, start=1):
        slides, _ = render_slides(board, concept, base_dir=Path("."))
        pictures = picture_row(concept_id, concept, text, rtl, manifest, tmp) if with_pictures else ""
        card, lightbox = concept_card(index, concept_id, concept, slides, pictures)
        cards.append(card)
        boxes.append(lightbox)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Style concepts: {esc(text['title'])}</title><style>{PAGE_CSS}
{SLIDE_CSS}</style></head>
<body>
<h1>Style concepts for &ldquo;{esc(text['title'])}&rdquo;</h1>
<p class="lead">{len(chosen)} concepts, deliberately different from each other. Every card shows the same five slides of your deck drawn in that style; click a slide to enlarge it. Under each card, the title slide again with the picture sets that suit that style. Reply with both: the concept and the picture set (&ldquo;2 with pictures 3&rdquo;), or &ldquo;2, no pictures&rdquo;. The deck is built only after you choose.</p>
{''.join(cards)}
<footer>These are the real slides: the same renderer builds the HTML deck, and the PowerPoint file uses the same colours, sizes and layouts. Fonts that are missing here are replaced by the browser, so the .pptx on a machine with Office may look slightly different. The chosen concept becomes <code>theme.json</code>; edit that file to tune a colour or a size before building.</footer>
{''.join(boxes)}
</body></html>
"""


# --------------------------------------------------------------------------- theme output
def theme_from(concept_id: str, concept: dict, args: argparse.Namespace) -> dict:
    theme = {"id": concept_id, **json.loads(json.dumps(concept))}
    for key, value in {"accent": args.accent, "accent2": args.accent2, "bg": args.bg, "text": args.text}.items():
        if value:
            theme["colors"][key] = parse_hex(value)
    if args.accent:
        theme["colors"]["on_accent"] = "#FFFFFF" if contrast(theme["colors"]["accent"], "#FFFFFF") >= 3.5 else "#111111"
        theme["colors"]["chart"][0] = theme["colors"]["accent"]
    if args.heading_font:
        theme["fonts"]["heading"] = args.heading_font
        theme["fonts"]["css_heading"] = f"'{args.heading_font}', " + theme["fonts"].get("css_heading", "sans-serif")
    if args.body_font:
        theme["fonts"]["body"] = args.body_font
        theme["fonts"]["css_body"] = f"'{args.body_font}', " + theme["fonts"].get("css_body", "sans-serif")
    if args.align:
        theme["layout"]["align"] = args.align
    if args.name:
        theme["name"] = args.name
    theme["contrast"] = {label: ratio for label, ratio, _ in contrast_report(theme["colors"])}
    return theme


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", help="style-preview.html (default) or theme.json with --choose")
    parser.add_argument("--list", action="store_true", help="print the built-in concepts and exit")
    parser.add_argument("--choose", metavar="ID", help="write theme.json for this concept ('brand' needs --brand-accent)")
    parser.add_argument("--pick", help="comma-separated concept ids to show (default: five for the audience)")
    parser.add_argument("--audience", choices=sorted(AUDIENCE_FIVE), help="pick the five concepts that suit this audience")
    parser.add_argument("--exclude", help="comma-separated ids to leave out of the automatic pick")
    parser.add_argument("--brand-accent", metavar="#HEX", help="add a 'brand' concept built around this colour (shown first)")
    parser.add_argument("--script", choices=sorted(SCRIPT_SAFE), help="swap fonts for ones that cover this script")
    parser.add_argument("--rtl", action="store_true", help="preview right-to-left slides")
    parser.add_argument("--title", default="Subscriptions now carry the business", help="deck title shown on the sample slides")
    parser.add_argument("--subtitle", default="FY2026 mid-year review for the leadership team")
    parser.add_argument("--author", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--footer", default="", help="footer text (default: the title)")
    parser.add_argument("--headline", default="Revenue grew 18 percent, and subscriptions did the work")
    parser.add_argument("--bullets", default="Total revenue **12.4 M**, up 18 percent year on year;Subscriptions are now 61 percent of revenue;Services revenue fell 9 percent as planned",
                        help="semicolon-separated bullets for the sample slide")
    parser.add_argument("--takeaway", default="The mix shift we planned for 2027 arrived a year early.")
    parser.add_argument("--source", default="Finance close, August 2026")
    parser.add_argument("--chart-title", default="Every quarter of 2026 beat the same quarter of 2025")
    parser.add_argument("--numbers", default="18%|Revenue growth|year on year;61%|Subscription share|of total revenue;2x|Enterprise customers|52 to 104",
                        help="semicolon-separated 'value|label|detail' items")
    parser.add_argument("--numbers-title", default="Three numbers to remember")
    parser.add_argument("--section", default="What it cost us")
    parser.add_argument("--section-subtitle", default="Hosting, support and the two hires we made")
    for flag in ("--accent", "--accent2", "--bg", "--text", "--heading-font", "--body-font", "--name"):
        parser.add_argument(flag, help=f"override for --choose ({flag[2:].replace('-', ' ')})")
    parser.add_argument("--align", choices=["left", "center"], help="override for --choose: text alignment")
    parser.add_argument("--pictures", metavar="SET", help="with --choose: what the user picked for pictures: a library pack (pack-a ... pack-g), "
                                                          "'generated:<pattern>' for a backdrop in the theme colours (grid, bands, contours, waves, mesh), or 'none'")
    parser.add_argument("--no-pictures", action="store_true", help="preview without the picture rows")
    args = parser.parse_args(argv)

    library = dict(CONCEPTS)
    if args.brand_accent:
        library = {"brand": brand_concept(args.brand_accent), **library}
    if args.list:
        for concept_id, concept in library.items():
            print(f"{concept_id:18} {concept['name']:20} {concept['best_for']}")
        return 0
    if args.choose:
        if args.choose not in library:
            sys.stderr.write(f"error: unknown concept '{args.choose}'; run --list (use --brand-accent for 'brand')\n")
            return 1
        theme = theme_from(args.choose, apply_script(library[args.choose], args.script), args)
        if args.pictures:
            theme["pictures"] = args.pictures
        output = Path(args.output or "theme.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(theme, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        low = [f"{label} {ratio}:1" for label, ratio, ok in contrast_report(theme["colors"]) if not ok]
        print(f"wrote {output}: {theme['name']} ({args.choose}); fonts {theme['fonts']['heading']} / {theme['fonts']['body']}"
              + (f"; contrast below the floor: {', '.join(low)}" if low else "; contrast checks pass")
              + (f"; pictures: {args.pictures}" if args.pictures else "; no picture set recorded, ask the user or pass --pictures"))
        return 0

    if args.pick:
        ids = [i.strip() for i in args.pick.split(",") if i.strip()]
    else:
        ids = list(AUDIENCE_FIVE.get(args.audience or "", DEFAULT_FIVE))
        if args.brand_accent:
            ids = ["brand"] + [i for i in ids if i != "carbon"][:4]
    excluded = {i.strip() for i in (args.exclude or "").split(",") if i.strip()}
    ids = [i for i in ids if i not in excluded]
    if not args.pick and not any(library.get(i, {}).get("dark") for i in ids):
        # a set with no dark concept hides a whole direction from the user
        dark = next((d for d in DARK_FALLBACK if d in library and d not in excluded and d not in ids), None)
        if dark:
            ids = ids[:4] + [dark]
    unknown = [i for i in ids if i not in library]
    if unknown:
        sys.stderr.write(f"error: unknown concept(s): {', '.join(unknown)}; run --list\n")
        return 1
    if not ids:
        sys.stderr.write("error: no concepts left to show\n")
        return 1
    text = {
        "title": args.title, "subtitle": args.subtitle, "meta": [args.author, args.date], "footer": args.footer or args.title,
        "headline": args.headline, "bullets": [b.strip() for b in args.bullets.split(";") if b.strip()], "takeaway": args.takeaway,
        "source": args.source, "chart_title": args.chart_title, "numbers_title": args.numbers_title,
        "section": args.section, "section_sub": args.section_subtitle,
        "numbers": [tuple(part.strip() for part in (item.split("|") + ["", ""])[:3]) for item in args.numbers.split(";") if item.strip()][:4],
    }
    chosen = [(i, apply_script(library[i], args.script)) for i in ids]
    page = build_page(chosen, text, args.rtl, with_pictures=not args.no_pictures)
    output = Path(args.output or "style-preview.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print(f"wrote {output}: {len(chosen)} concepts; open it in a browser and ask the user to choose.")
    print("Show the user these lines as they are; do not describe the concepts from memory:")
    manifest = library_manifest() if not args.no_pictures else {"packs": {}}
    for number, (concept_id, concept) in enumerate(chosen, start=1):
        dark = " (dark)" if concept.get("dark") else ""
        print(f"  {number} {concept['name']} [{concept_id}]{dark}: {concept['tagline']}")
        packs = picture_packs_for(concept_id, manifest)
        if packs:
            options = [f"{n} {info.get('name', pack)} [{pack}]" for n, (pack, info, _) in enumerate(packs, start=1)]
            options += [f"{len(packs) + i} generated {pattern}" for i, pattern in enumerate(GENERATED_PATTERNS, start=1)]
            print("      pictures: " + "; ".join(options) + "; or none")
    if manifest.get("packs"):
        print("Ask for both in one question: the concept and the picture set. Never pick the picture set yourself.")
    for concept_id, concept in chosen:
        low = [label for label, ratio, ok in contrast_report(concept["colors"]) if not ok]
        if low:
            print(f"  note: {concept_id} is below the contrast floor for {', '.join(low)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
