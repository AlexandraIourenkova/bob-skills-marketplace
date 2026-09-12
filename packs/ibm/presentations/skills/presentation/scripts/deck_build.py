#!/usr/bin/env python3
"""Build a styled 16:9 PowerPoint deck from a storyboard (Markdown) and a theme (JSON).

Every slide is drawn on a blank layout from the theme's colours, fonts and
layout traits, so the same storyboard renders in any of the style concepts
from deck-style (`style_preview.py --choose <id> -o theme.json`). Layouts:
title, section, bullets (with side-by-side pictures or charts), two-column,
big-number, quote, statement, image, chart, timeline, table, closing.
Speaker notes come from `Notes:` lines, a `Source:` line becomes a footnote,
a `Takeaway:` line a callout. Warnings (long headlines, too many bullets,
text that may overflow) go to stderr; `--strict` turns them into exit 1.

Run:  uv run --with python-pptx python deck_build.py storyboard.md --theme theme.json -o deck.pptx
      uv run --with python-pptx python deck_build.py storyboard.md -o deck.pptx   (built-in theme)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ inside an installed skill
sys.path.insert(0, str(Path(__file__).resolve().parent))
from storyboard import (Item, Slide, Storyboard, StoryboardError, appendix_label, bold_parts, inline_clean,  # noqa: E402
                        load_storyboard, numeric_columns, typographic)

try:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_AXIS_CROSSES, XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Emu, Inches, Pt
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write("python-pptx is not installed. Run with: uv run --with python-pptx python deck_build.py ...\n")
    sys.exit(1)

EMU = 914400
SLIDE_W, SLIDE_H = 13.333, 7.5  # inches, the 16:9 size PowerPoint uses
BUNDLED_ICONS_PNG = Path(__file__).resolve().parents[2] / "deck-images" / "assets" / "icons" / "png"  # Carbon glyphs, black on transparent

DEFAULT_THEME = {
    "id": "boardroom",
    "name": "Boardroom Blue",
    "dark": False,
    "colors": {
        "bg": "#FFFFFF", "surface": "#F2F4F8", "text": "#161616", "muted": "#525252",
        "accent": "#0F62FE", "accent2": "#002D9C", "line": "#C6C6C6", "on_accent": "#FFFFFF",
        "chart": ["#0F62FE", "#002D9C", "#8A3FFC", "#009D9A", "#FF832B", "#A8A8A8"],
    },
    "fonts": {"heading": "Arial", "body": "Arial", "mono": "Consolas"},
    "sizes": {"title": 40, "headline": 30, "body": 20, "small": 12, "number": 60},
    "layout": {"align": "left", "accent_bar": "top", "title_style": "split", "section_style": "accent",
               "corner": 0.06, "bullet": "▪", "cards": True, "ornament": "none"},
}

CHART_TYPES = {
    "bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "barh": XL_CHART_TYPE.BAR_CLUSTERED, "stacked": XL_CHART_TYPE.COLUMN_STACKED,
    "barh-stacked": XL_CHART_TYPE.BAR_STACKED, "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE, "doughnut": XL_CHART_TYPE.DOUGHNUT, "area": XL_CHART_TYPE.AREA,
}
ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
NUMERIC_CELL = re.compile(r"^[-+(]?[$€£]?\s?\d[\d,.\s]*%?\s?[A-Za-z%]{0,3}\)?$")
ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}


class BuildError(Exception):
    pass


# --------------------------------------------------------------------------- theme
def deep_merge(base: dict, extra: dict) -> dict:
    result = json.loads(json.dumps(base))
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_theme(path: str | None) -> dict:
    if not path:
        return json.loads(json.dumps(DEFAULT_THEME))
    file = Path(path)
    if not file.is_file():
        raise BuildError(f"theme not found: {file}")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BuildError(f"theme {file} is not valid JSON: {error}") from None
    theme = deep_merge(DEFAULT_THEME, data)
    for key in ("bg", "text", "accent"):
        parse_hex(theme["colors"][key])
    return theme


def parse_hex(value: str) -> str:
    text = str(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        raise BuildError(f"colour '{value}' is not a hex colour like #0F62FE")
    return text.upper()


def rgb(value: str) -> RGBColor:
    return RGBColor.from_string(parse_hex(value))


def mix(color: str, other: str, amount: float) -> str:
    """Blend two hex colours; amount 0 keeps the first, 1 gives the second."""
    a, b = parse_hex(color), parse_hex(other)
    parts = [round(int(a[i:i + 2], 16) * (1 - amount) + int(b[i:i + 2], 16) * amount) for i in (0, 2, 4)]
    return "#" + "".join(f"{max(0, min(255, p)):02X}" for p in parts)


# --------------------------------------------------------------------------- text fitting
def fit_size(blocks: list[dict], start: float, floor: float, width_in: float, height_in: float,
             spacing: float, gap_pt: float) -> tuple[float, bool]:
    """Largest size (from start down to floor) at which the blocks should fit the box.

    Estimation only: average glyph width 0.5 em (0.56 for bold), 8 percent wrap waste.
    Returns (size, overflow) where overflow is True when even the floor does not fit.
    """
    size = float(start)
    while True:
        needed = 0.0
        last = len(blocks) - 1
        for index, block in enumerate(blocks):
            scale = block.get("scale", 1.0)
            point = size * scale
            indent = (point * 1.7 + point * 1.5 * block.get("level", 0)) / 72 if block.get("bullet") else 0.0  # matches set_bullet
            factor = 0.56 if (block.get("bold") or block.get("mono")) else 0.5
            usable = max(0.5, width_in - indent)
            per_line = max(1, int(usable * 72 / (point * factor)))
            text = inline_clean(block.get("text", ""))
            lines = max(1, math.ceil(len(text) * 1.08 / per_line)) if text else 1
            needed += lines * point * spacing + (gap_pt * block.get("gap_scale", 1.0) if index < last else 0)
        if needed / 72 <= height_in:
            return size, False
        if size <= floor:
            return size, True
        size -= 1


# --------------------------------------------------------------------------- XML helpers
def no_bullet(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    for child in list(p_pr):
        if child.tag in (qn("a:buNone"), qn("a:buChar"), qn("a:buAutoNum"), qn("a:buClr"), qn("a:buSzPct"), qn("a:buFont")):
            p_pr.remove(child)
    p_pr.insert_element_before(OxmlElement("a:buNone"), "a:tabLst", "a:defRPr", "a:extLst")
    p_pr.set("marL", "0")
    p_pr.set("indent", "0")


def set_bullet(paragraph, level: int, char: str, color_hex: str, numbered: bool = False, size_pt: float = 20.0) -> None:
    """A hanging bullet whose gap scales with the text: 1.7 em of indent, the glyph at 90 percent of the text."""
    p_pr = paragraph._p.get_or_add_pPr()
    for child in list(p_pr):
        if child.tag in (qn("a:buNone"), qn("a:buChar"), qn("a:buAutoNum"), qn("a:buClr"), qn("a:buSzPct"), qn("a:buFont")):
            p_pr.remove(child)
    step = int(Pt(max(16.0, size_pt) * 1.7))  # wide glyphs such as an em dash need most of that
    nest = int(Pt(max(16.0, size_pt) * 1.5))
    p_pr.set("marL", str(step + nest * level))
    p_pr.set("indent", str(-step))
    bu_clr = OxmlElement("a:buClr")
    srgb = OxmlElement("a:srgbClr")
    srgb.set("val", parse_hex(color_hex))
    bu_clr.append(srgb)
    bu_sz = OxmlElement("a:buSzPct")
    bu_sz.set("val", "90000")
    if numbered:
        marker = OxmlElement("a:buAutoNum")
        marker.set("type", "arabicPeriod")
    else:
        marker = OxmlElement("a:buChar")
        marker.set("char", char)
    for element in (bu_clr, bu_sz, marker):
        p_pr.insert_element_before(element, "a:tabLst", "a:defRPr", "a:extLst")


def set_rtl(paragraph) -> None:
    paragraph._p.get_or_add_pPr().set("rtl", "1")


def set_alpha(shape, percent: int) -> None:
    """Make a solid-filled shape translucent (percent = opacity, 0..100)."""
    sp_pr = shape._element.spPr
    solid = sp_pr.find(qn("a:solidFill"))
    if solid is None or len(solid) == 0:
        return
    alpha = OxmlElement("a:alpha")
    alpha.set("val", str(int(max(0, min(100, percent)) * 1000)))
    solid[0].append(alpha)


def rotate_tick_labels(axis, degrees: float) -> None:
    """Lean the axis labels; python-pptx has no property for it, so the text body is set directly."""
    tx_pr = axis._element.find(qn("c:txPr"))
    if tx_pr is None:
        tx_pr = OxmlElement("c:txPr")
        body = OxmlElement("a:bodyPr")
        tx_pr.append(body)
        tx_pr.append(OxmlElement("a:lstStyle"))
        paragraph = OxmlElement("a:p")
        paragraph.append(OxmlElement("a:pPr"))
        tx_pr.append(paragraph)
        axis._element.append(tx_pr)
    body = tx_pr.find(qn("a:bodyPr"))
    body.set("rot", str(int(degrees * 60000)))
    body.set("vert", "horz")


def cell_border_bottom(cell, color_hex: str, width_pt: float) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    line = OxmlElement("a:lnB")
    line.set("w", str(int(Pt(width_pt))))
    solid = OxmlElement("a:solidFill")
    srgb = OxmlElement("a:srgbClr")
    srgb.set("val", parse_hex(color_hex))
    solid.append(srgb)
    line.append(solid)
    fills = (qn("a:noFill"), qn("a:solidFill"), qn("a:gradFill"), qn("a:blipFill"), qn("a:pattFill"), qn("a:grpFill"))
    for index, child in enumerate(list(tc_pr)):
        if child.tag in fills:
            tc_pr.insert(index, line)
            return
    tc_pr.append(line)


# --------------------------------------------------------------------------- builder
class Deck:
    def __init__(self, board: Storyboard, theme: dict, args: argparse.Namespace):
        self.board = board
        self.theme = theme
        self.args = args
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]
        self.sizes = theme["sizes"]
        self.layout = theme["layout"]
        self.warnings: list[str] = []
        self.summary: list[str] = []
        self.rtl = board.rtl
        self.source_label = str(board.meta.get("source_label") or "Source:")
        self.scrim = str(board.meta.get("backdrop_scrim") or "dark").lower()
        self.text_side = str(board.meta.get("backdrop_text") or "left").lower()
        self.chapters = str(board.meta.get("chapter_label") or "auto").lower() != "off" and any(x.kind == "section" for x in board.slides)
        self.confidentiality = str(board.meta.get("confidentiality") or "")
        self.align = "right" if self.rtl else str(self.layout.get("align", "left"))
        self.prs = Presentation()
        self.prs.slide_width = Inches(SLIDE_W)
        self.prs.slide_height = Inches(SLIDE_H)
        self.blank = self.prs.slide_layouts[6]
        self.margin = 0.6
        self.gap = 0.3
        bar = str(self.layout.get("accent_bar", "none"))
        self.ornament = str(self.layout.get("ornament", "none"))
        self.left_margin = self.margin + (0.25 if bar == "left" and not self.rtl else 0.0)
        self.right_margin = self.margin + (0.25 if bar == "left" and self.rtl else 0.0)
        self.content_top = 1.85 if self.chapters else 1.7  # the chapter label above the headline takes the difference
        self.footer_top = SLIDE_H - 0.55
        self.section_count = 0
        self.logo = Path(args.logo) if args.logo else None
        if self.logo and not self.logo.is_file():
            raise BuildError(f"logo not found: {self.logo}")
        self.backdrop_override = args.backdrop  # --backdrop replaces the front matter title backdrop
        self.backdrop: Path | None = None  # set per slide by choose_backdrop()

    # backdrops --------------------------------------------------------------
    def resolve_backdrop(self, value: str | None) -> Path | None:
        """A backdrop path from the storyboard, with the PNG twin for an SVG; None when there is none."""
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute() and self.board.path:
            path = self.board.path.parent / path
        if path.suffix.lower() == ".svg":  # PowerPoint cannot place SVG; take the PNG next to it
            png = path.with_suffix(".png")
            if not png.is_file():
                self.warn(f"backdrop {path.name} is SVG, which the .pptx cannot use; generate a .png with the same name")
                return None
            path = png
        if not path.is_file():
            raise BuildError(f"backdrop image not found: {path}")
        return path

    def choose_backdrop(self, spec: Slide, default_key: str) -> None:
        """A picture line on the slide wins; otherwise the front matter default for this kind of slide."""
        own = next((i for i in spec.items if i.kind == "image"), None)
        if own is not None:
            self.backdrop = self.resolve_backdrop(own.text)
        elif default_key == "backdrop" and self.backdrop_override:
            self.backdrop = self.resolve_backdrop(self.backdrop_override)
        else:
            value = self.board.meta.get(default_key)
            self.backdrop = self.resolve_backdrop(str(value)) if value else None

    # utilities --------------------------------------------------------------
    def warn(self, message: str) -> None:
        self.warnings.append(message)
        sys.stderr.write(f"warning: {message}\n")

    @property
    def content_width(self) -> float:
        return SLIDE_W - self.left_margin - self.right_margin

    def box(self, left: float, top: float, width: float, height: float) -> tuple[int, int, int, int]:
        return (int(Inches(left)), int(Inches(top)), int(Inches(width)), int(Inches(height)))

    def mirror(self, left: float, width: float) -> float:
        """Horizontal position mirrored for right-to-left decks."""
        return SLIDE_W - left - width if self.rtl else left

    def new_slide(self, spec: Slide, layout: str):
        slide = self.prs.slides.add_slide(self.blank)
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = rgb(self.colors["bg"])
        try:
            slide.name = f"{layout}: {spec.title[:40]}"
        except Exception:
            pass
        return slide

    def rect(self, slide, box: tuple[int, int, int, int], color: str, shape=MSO_SHAPE.RECTANGLE, corner: float | None = None, name: str = ""):
        shape = slide.shapes.add_shape(shape, *box)
        if name:
            shape.name = name
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(color)
        shape.line.fill.background()
        shape.shadow.inherit = False
        if corner is not None and shape.shape_type is not None and shape.adjustments:
            try:
                shape.adjustments[0] = corner
            except Exception:
                pass
        return shape

    def text(self, slide, box: tuple[int, int, int, int], blocks: list[dict], *, size: float, floor: float | None = None,
             font: str | None = None, color: str | None = None, align: str | None = None, anchor: str = "top",
             spacing: float = 1.12, gap: float = 6.0, fit: bool = True, margin: float = 0.05, name: str = "", bold_color: str | None = None):
        """Add a text box. blocks: dicts with text and optional level, bullet, bold, italic, scale, color, font, mono, gap_scale."""
        box_shape = slide.shapes.add_textbox(*box)
        if name:
            box_shape.name = name
        frame = box_shape.text_frame
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.margin_left = frame.margin_right = Inches(margin)
        frame.margin_top = frame.margin_bottom = Inches(margin)
        frame.vertical_anchor = ANCHOR[anchor]
        width_in = box[2] / EMU - 2 * margin
        height_in = box[3] / EMU - 2 * margin
        floor = floor if floor is not None else max(10.0, size * 0.7)
        overflow = False
        if fit:
            size, overflow = fit_size(blocks, size, floor, width_in, height_in, spacing, gap)
        align = align or self.align
        font = font or self.fonts["body"]
        color = color or self.colors["text"]
        for index, block in enumerate(blocks):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.alignment = ALIGN[block.get("align", align)]
            paragraph.line_spacing = spacing
            paragraph.space_after = Pt(gap * block.get("gap_scale", 1.0))
            level = int(block.get("level", 0))
            bullet = block.get("bullet")
            point_for_indent = size * block.get("scale", 1.0) * (0.9 ** level if bullet else 1.0)
            if bullet:
                set_bullet(paragraph, level, str(self.layout.get("bullet", "•")), self.colors["accent"], numbered=(bullet == "number"),
                           size_pt=point_for_indent)
            else:
                no_bullet(paragraph)
            if self.rtl:
                set_rtl(paragraph)
            point = size * block.get("scale", 1.0) * (0.9 ** level if bullet else 1.0)
            parts = bold_parts(typographic(block.get("text", ""))) or [("", False)]
            for piece, bold in parts:
                run = paragraph.add_run()
                run.text = piece
                run.font.size = Pt(point)
                run.font.name = self.fonts["mono"] if block.get("mono") else (block.get("font") or font)
                run.font.bold = bool(bold or block.get("bold"))
                if bold and bold_color:
                    run.font.color.rgb = rgb(bold_color)
                    run.font.italic = bool(block.get("italic"))
                    continue
                run.font.italic = bool(block.get("italic"))
                run.font.color.rgb = rgb(bold_color if (bold and bold_color) else (block.get("color") or color))
        return box_shape, size, overflow

    def picture(self, slide, path: Path, box: tuple[int, int, int, int], mode: str = "contain", alt: str = ""):
        if path.suffix.lower() == ".svg":  # PowerPoint reads SVG, python-pptx does not: take the PNG twin
            png = path.with_suffix(".png")
            if not png.is_file():
                self.warn(f"{path.name} is SVG, which the .pptx cannot place; write a .png of the same name (the HTML deck uses the SVG)")
                return None
            path = png
        if not path.is_file():
            raise BuildError(f"image not found: {path}")
        left, top, width, height = box
        try:
            picture = slide.shapes.add_picture(str(path), left, top)
        except Exception as error:
            raise BuildError(f"cannot insert image {path}: {error}") from None
        img_w, img_h = picture.width, picture.height
        if mode == "cover":
            scale = max(width / img_w, height / img_h)
            shown_w, shown_h = img_w * scale, img_h * scale
            crop_w = max(0.0, (shown_w - width) / shown_w)
            crop_h = max(0.0, (shown_h - height) / shown_h)
            picture.crop_left = picture.crop_right = crop_w / 2
            picture.crop_top = picture.crop_bottom = crop_h / 2
            picture.left, picture.top, picture.width, picture.height = left, top, width, height
        else:
            scale = min(width / img_w, height / img_h)
            picture.width = int(img_w * scale)
            picture.height = int(img_h * scale)
            picture.left = left + (width - picture.width) // 2
            picture.top = top + (height - picture.height) // 2
        if alt:
            try:
                picture._element._nvXxPr.cNvPr.set("descr", alt)
            except Exception:
                pass
        return picture

    # slide furniture --------------------------------------------------------
    def draw_ornament(self, slide, where: str, number: int = 0) -> None:
        """Draw the concept's decoration: a column grid, HUD brackets, hatching or geometric shapes.

        Over a backdrop picture only the HUD brackets stay; the other ornaments are textures for a plain canvas.
        """
        kind = self.ornament
        if kind == "none" or (where == "cover" and self.backdrop is not None and kind != "hud"):
            return
        if kind == "grid" and where == "content":
            for fraction in (0.25, 0.5, 0.75):
                x = self.left_margin + self.content_width * fraction
                self.rect(slide, self.box(x, 0, 0.012, SLIDE_H), self.colors["line"], name="deck:ornament")
        elif kind == "hud":
            arm, thick, pad = 0.28, 0.035, 0.17
            for x, y, dx, dy in ((pad, pad, 1, 1), (SLIDE_W - pad, pad, -1, 1), (pad, SLIDE_H - pad, 1, -1), (SLIDE_W - pad, SLIDE_H - pad, -1, -1)):
                left = x if dx > 0 else x - arm
                top = y if dy > 0 else y - thick
                self.rect(slide, self.box(left, top, arm, thick), self.colors["accent"], name="deck:ornament")
                self.rect(slide, self.box(x if dx > 0 else x - thick, y if dy > 0 else y - arm, thick, arm), self.colors["accent"], name="deck:ornament")
            if where == "content" and number:
                box = self.box(self.mirror(SLIDE_W - self.margin - 0.9, 0.9), 0.28, 0.9, 0.3)
                self.text(slide, box, [{"text": f"{number:02d}", "font": self.fonts.get("mono", "Consolas")}], size=self.sizes["small"],
                          floor=self.sizes["small"], color=self.colors["accent"], fit=False, gap=0, align="right", name="deck:hud-tag")
        elif kind == "hatch":
            step, width = 0.62, 0.012
            x = -SLIDE_H
            while x < SLIDE_W + SLIDE_H:
                line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(Inches(max(0.0, x))), int(Inches(0 if x >= 0 else -x)),
                                                  int(Inches(min(SLIDE_W, x + SLIDE_H))), int(Inches(min(SLIDE_H, SLIDE_W - x))))
                line.line.color.rgb = rgb(mix(self.colors["line"], self.colors["bg"], 0.45))
                line.line.width = Pt(width * 72)
                x += step
        elif kind == "shapes":
            if where == "cover":
                self.rect(slide, self.box(self.mirror(SLIDE_W - 3.6, 3.1), 1.0, 3.1, 3.1), self.colors["accent2"], MSO_SHAPE.OVAL, name="deck:ornament")
                self.rect(slide, self.box(self.mirror(SLIDE_W - 4.6, 2.0), 4.6, 2.0, 1.9), self.colors["chart"][2], MSO_SHAPE.ISOSCELES_TRIANGLE, name="deck:ornament")
                self.rect(slide, self.box(self.mirror(-1.0, 2.0), SLIDE_H - 1.0, 2.0, 2.0), self.colors["accent"], MSO_SHAPE.OVAL, name="deck:ornament")
            else:
                self.rect(slide, self.box(self.mirror(SLIDE_W - self.margin - 0.55, 0.55), 0.5, 0.55, 0.55), self.colors["accent2"], MSO_SHAPE.OVAL, name="deck:ornament")
                self.rect(slide, self.box(0, SLIDE_H - 0.1, SLIDE_W, 0.1), self.colors["accent"], name="deck:ornament")

    def furniture(self, slide, number: int, spec: Slide) -> None:
        self.draw_ornament(slide, "content", number)
        bar = str(self.layout.get("accent_bar", "none"))
        if bar == "left":
            self.rect(slide, self.box(self.mirror(0, 0.14), 0, 0.14, SLIDE_H), self.colors["accent"])
        elif bar == "top":
            self.rect(slide, self.box(0, 0, SLIDE_W, 0.12), self.colors["accent"])
        if self.logo:
            box = self.box(self.mirror(SLIDE_W - self.margin - 1.6, 1.6), 0.3, 1.6, 0.45)
            self.picture(slide, self.logo, box, "contain", "logo")
        footer = str(self.board.meta.get("footer") or self.board.title)
        if self.confidentiality:
            footer = f"{footer}   ·   {self.confidentiality.upper()}"
        small = self.sizes["small"]
        left_box = self.box(self.left_margin, self.footer_top, self.content_width * 0.7, 0.36)
        right_box = self.box(self.left_margin + self.content_width * 0.7, self.footer_top, self.content_width * 0.3, 0.36)
        if self.rtl:
            left_box, right_box = right_box, left_box
        self.text(slide, left_box, [{"text": footer}], size=small, floor=small, color=self.colors["muted"], fit=False,
                  align="right" if self.rtl else "left", name="deck:footer")
        page = appendix_label(spec) or str(number)
        self.text(slide, right_box, [{"text": page}], size=small, floor=small, color=self.colors["muted"], fit=False,
                  align="left" if self.rtl else "right", name="deck:number")

    def eyebrow(self, slide, spec: Slide) -> bool:
        """The chapter above the headline; returns True when it was drawn, so the headline moves down."""
        if not self.chapters or not spec.chapter or spec.kind != "content":
            return False
        label = appendix_label(spec)
        number = "A" if label else f"{spec.chapter_number:02d}"
        width = self.content_width - (1.8 if self.logo else 0)
        box = self.box(self.mirror(self.left_margin, width), 0.4, width, 0.3)
        self.text(slide, box, [{"text": f"{number}   {spec.chapter.upper()}", "bold": True}], size=self.sizes["small"] + 1,
                  floor=self.sizes["small"], color=self.colors["muted"], fit=False, gap=0, name="deck:eyebrow",
                  bold_color=None, font=self.fonts["heading"])
        return True

    def headline(self, slide, text: str, number: int, small: bool = False, width_scale: float = 1.0, shifted: bool = False) -> None:
        plain = inline_clean(text)
        if not plain:
            self.warn(f"slide {number}: the headline is empty")
        elif len(plain) > 70:
            self.warn(f"slide {number}: the headline has {len(plain)} characters; keep it under 70")
        size = self.sizes["small"] + 2 if small else self.sizes["headline"]
        reserved = 1.8 if self.logo else (0.9 if self.ornament == "shapes" else 0.6 if self.ornament == "hud" else 0.0)
        width = (self.content_width - reserved) * width_scale
        top = (0.72 if shifted else 0.45) if not small else 0.5
        height = (1.0 if shifted else 1.1) if not small else 0.4
        box = self.box(self.mirror(self.left_margin, width) if width_scale < 1 else self.left_margin, top, width, height)
        blocks = [{"text": inline_clean(text).upper() if small else text, "bold": not small}]
        color = self.colors["muted"] if small else self.colors["text"]
        _, used, overflow = self.text(slide, box, blocks, size=size, floor=22 if not small else size, font=self.fonts["heading"],
                                      color=color, anchor="middle" if not small else "top", gap=0, name="deck:headline",
                                      bold_color=None if small else self.colors["accent"])
        if overflow:
            self.warn(f"slide {number}: the headline does not fit even at {used:.0f} pt; shorten it")
        if not small and str(self.layout.get("accent_bar")) == "underline":
            self.rect(slide, self.box(self.mirror(self.left_margin, 1.0), 1.5, 1.0, 0.06), self.colors["accent"])

    def notes(self, slide, spec: Slide) -> None:
        if spec.notes:
            slide.notes_slide.notes_text_frame.text = "\n".join(spec.notes)

    def source_line(self, slide, spec: Slide) -> float:
        """Draw the source footnote; return the bottom limit for content."""
        if not spec.source:
            return self.footer_top - 0.15
        top = self.footer_top - 0.4
        self.text(slide, self.box(self.left_margin, top, self.content_width, 0.35), [{"text": f"{self.source_label} {spec.source}"}],
                  size=self.sizes["small"], floor=self.sizes["small"] - 2, color=self.colors["muted"], fit=True, gap=0, name="deck:source")
        return top - 0.05

    def takeaway(self, slide, spec: Slide, bottom: float) -> float:
        """Draw the takeaway callout above `bottom`; return the new bottom limit."""
        if not spec.takeaway:
            return bottom
        height = 0.95
        top = bottom - height
        box = self.box(self.left_margin, top, self.content_width, height)
        self.rect(slide, box, self.colors["surface"], MSO_SHAPE.ROUNDED_RECTANGLE if self.layout.get("corner") else MSO_SHAPE.RECTANGLE,
                  float(self.layout.get("corner") or 0))
        self.rect(slide, self.box(self.mirror(self.left_margin, 0.1), top, 0.1, height), self.colors["accent"])
        inner = self.box(self.left_margin + 0.25, top, self.content_width - 0.5, height)
        self.text(slide, inner, [{"text": spec.takeaway, "bold": True}], size=self.sizes["body"], floor=14,
                  font=self.fonts["heading"], anchor="middle", gap=0, name="deck:takeaway")
        return top - self.gap

    def content_area(self, slide, spec: Slide) -> tuple[float, float, float, float]:
        """(left, top, width, height) in inches left for the main content after footnote and callout."""
        bottom = self.source_line(slide, spec)
        bottom = self.takeaway(slide, spec, bottom)
        return self.left_margin, self.content_top, self.content_width, max(1.0, bottom - self.content_top)

    # blocks from items ------------------------------------------------------
    def blocks_for(self, items: list[Item]) -> list[dict]:
        blocks = []
        for item in items:
            if item.kind in ("bullet", "number"):
                blocks.append({"text": item.text, "level": item.level, "bullet": "number" if item.kind == "number" else True})
            elif item.kind == "heading":
                blocks.append({"text": item.text, "bold": True, "color": self.colors["accent"], "gap_scale": 0.6, "font": self.fonts["heading"]})
            elif item.kind == "code":
                blocks.append({"text": item.text, "mono": True, "scale": 0.85, "gap_scale": 0.2})
            elif item.kind == "para":
                blocks.append({"text": item.text, "gap_scale": 1.2})
        return blocks

    # layouts ----------------------------------------------------------------
    def layouts(self) -> dict:
        """Layout name to the method that draws it. An explicit table, no dynamic lookup."""
        return {
            "title": self.slide_title, "section": self.slide_section, "bullets": self.slide_bullets,
            "two-column": self.slide_two_column, "big-number": self.slide_big_number, "quote": self.slide_quote,
            "statement": self.slide_statement, "image": self.slide_image, "chart": self.slide_chart,
            "timeline": self.slide_timeline, "table": self.slide_table, "closing": self.slide_closing,
            "split": self.slide_split, "icons": self.slide_icons,
        }

    def build(self) -> None:
        handlers = self.layouts()
        for number, spec in enumerate(self.board.slides, start=1):
            layout = spec.effective_layout()
            handler = handlers[layout]
            slide = self.new_slide(spec, layout)
            handler(slide, spec, number)
            self.notes(slide, spec)
            self.summary.append(f"{number:>2}. [{layout}] {spec.title}")

    def cover(self, slide, spec: Slide, number: int, style: str, title_size: float, closing: bool = False) -> None:
        """Title and closing slides: four styles plus an optional backdrop picture."""
        self.choose_backdrop(spec, "backdrop")
        title_color, sub_color = self.colors["text"], self.colors["muted"]
        left, width = self.left_margin, self.content_width
        if self.backdrop:
            self.picture(slide, self.backdrop, self.box(0, 0, SLIDE_W, SLIDE_H), "cover", "backdrop")
            if self.scrim == "dark":
                set_alpha(self.rect(slide, self.box(0, 0, SLIDE_W, SLIDE_H), "#000000"), 45)
                title_color = sub_color = "#FFFFFF"
            else:
                if self.scrim == "light":
                    set_alpha(self.rect(slide, self.box(0, 0, SLIDE_W, SLIDE_H), "#FFFFFF"), 55)
                sub_color = self.colors["text"]  # muted grey disappears into a photograph
        elif style == "full":
            slide.background.fill.fore_color.rgb = rgb(self.colors["accent"])
            title_color = sub_color = self.colors["on_accent"]
        elif style == "split":
            panel_w = SLIDE_W * 0.44
            self.rect(slide, self.box(self.mirror(0, panel_w), 0, panel_w, SLIDE_H), self.colors["accent"])
            title_color = self.colors["on_accent"]
            left, width = self.margin, panel_w - 2 * self.margin
        elif style == "band":
            band_h = SLIDE_H * 0.36
            self.rect(slide, self.box(0, SLIDE_H - band_h, SLIDE_W, band_h), self.colors["accent"])
            sub_color = self.colors["on_accent"]
        else:  # plain
            self.rect(slide, self.box(self.mirror(self.left_margin, 1.2), 2.05, 1.2, 0.09), self.colors["accent"])
        self.draw_ornament(slide, "cover")
        lines = spec.subtitle or ([] if not closing else [])
        extra = [i.text for i in spec.items if i.kind in ("bullet", "number", "para")] if closing else []
        meta_lines = [str(self.board.meta[k]) for k in ("author", "date") if self.board.meta.get(k)] if not closing else []
        if self.ornament == "shapes" and style not in ("split", "band"):
            width = width * 0.58  # the circle and triangle sit in the right third
        if self.backdrop and self.text_side == "right":  # the picture's empty side
            left = SLIDE_W * 0.52
            width = SLIDE_W - left - self.right_margin
        elif self.backdrop:
            width = SLIDE_W * 0.5 - left
        if style == "split" and not self.backdrop:
            title_box = self.box(self.mirror(left, width), 1.4, width, 4.2)
            self.text(slide, title_box, [{"text": spec.title_markup or spec.title, "bold": True}], size=title_size, floor=26, font=self.fonts["heading"],
                      color=title_color, anchor="middle", gap=0, name="deck:title")
            side_left = SLIDE_W * 0.44 + self.margin
            side_w = SLIDE_W - side_left - self.margin
            blocks = [{"text": t, "gap_scale": 1.5} for t in lines + extra] + [{"text": t, "scale": 0.8, "color": self.colors["muted"]} for t in meta_lines]
            if blocks:
                self.text(slide, self.box(self.mirror(side_left, side_w), 1.4, side_w, 4.2), blocks, size=self.sizes["body"] + 2, floor=16,
                          color=sub_color, anchor="middle", name="deck:subtitle")
        elif style == "band" and not self.backdrop:
            self.text(slide, self.box(self.mirror(left, width), 1.0, width, 3.4), [{"text": spec.title_markup or spec.title, "bold": True}], size=title_size,
                      floor=26, font=self.fonts["heading"], color=title_color, anchor="bottom", gap=0, name="deck:title", bold_color=self.colors["accent"] if title_color == self.colors["text"] else None)
            blocks = [{"text": t, "gap_scale": 1.5} for t in lines + extra] + [{"text": t, "scale": 0.8} for t in meta_lines]
            if blocks:
                self.text(slide, self.box(self.mirror(left, width), SLIDE_H * 0.64 + 0.3, width, SLIDE_H * 0.36 - 0.6), blocks,
                          size=self.sizes["body"] + 2, floor=16, color=sub_color, anchor="top", name="deck:subtitle")
        else:
            self.text(slide, self.box(self.mirror(left, width), 2.2, width, 2.2), [{"text": spec.title_markup or spec.title, "bold": True}], size=title_size,
                      floor=26, font=self.fonts["heading"], color=title_color, anchor="bottom", gap=0, name="deck:title", bold_color=self.colors["accent"] if title_color == self.colors["text"] else None)
            blocks = [{"text": t, "gap_scale": 1.5} for t in lines + extra] + [{"text": t, "scale": 0.8} for t in meta_lines]
            if blocks:
                self.text(slide, self.box(self.mirror(left, width), 4.55, width, 2.2), blocks, size=self.sizes["body"] + 2, floor=16,
                          color=sub_color, anchor="top", name="deck:subtitle")
        if self.logo and not self.backdrop and style != "full":
            self.picture(slide, self.logo, self.box(self.mirror(SLIDE_W - self.margin - 1.8, 1.8), SLIDE_H - 1.0, 1.8, 0.5), "contain", "logo")
        for item in spec.items:
            if item.kind == "chart" or (not closing and item.kind in ("bullet", "number", "para")):
                self.warn(f"line {item.line}: {item.kind} on a title slide is ignored")

    def slide_title(self, slide, spec: Slide, number: int) -> None:
        self.cover(slide, spec, number, str(self.layout.get("title_style", "plain")), self.sizes["title"])

    def slide_closing(self, slide, spec: Slide, number: int) -> None:
        self.cover(slide, spec, number, str(self.layout.get("title_style", "plain")), self.sizes["title"] - 4, closing=True)

    def slide_section(self, slide, spec: Slide, number: int) -> None:
        self.section_count += 1
        self.choose_backdrop(spec, "section_backdrop")
        style = str(self.layout.get("section_style", "accent"))
        label = f"{self.section_count:02d}"
        self.draw_ornament(slide, "cover")
        title_color, sub_color, label_color = self.colors["text"], self.colors["muted"], self.colors["accent"]
        panel_width = SLIDE_W * 0.34
        if self.backdrop:  # the picture keeps its colours; the text sits on a solid panel over the left third
            self.picture(slide, self.backdrop, self.box(0, 0, SLIDE_W, SLIDE_H), "cover", "backdrop")
            self.rect(slide, self.box(self.mirror(0, panel_width), 0, panel_width, SLIDE_H), self.colors["accent"], name="deck:section-panel")
            title_color = sub_color = label_color = self.colors["on_accent"]
        elif style == "accent":
            slide.background.fill.fore_color.rgb = rgb(self.colors["accent"])
            title_color = sub_color = label_color = self.colors["on_accent"]
        elif style == "band":
            self.rect(slide, self.box(self.mirror(0, 2.2), 0, 2.2, SLIDE_H), self.colors["accent"])
        else:
            self.rect(slide, self.box(self.mirror(self.left_margin, 1.2), 3.05, 1.2, 0.09), self.colors["accent"])
        left = self.left_margin + (2.2 if style == "band" and not self.backdrop else 0)
        width = (SLIDE_W - left - self.right_margin) * (0.58 if self.ornament == "shapes" else 1.0)
        if self.backdrop:  # inside the panel, with a smaller indent
            left = 0.42
            width = panel_width - 0.84
        # the label box is bottom-anchored, so it must end where the title begins
        label_top, title_top, title_size, sub_top = (0.35, 1.7, self.sizes["title"] - 8, 5.6) if self.backdrop else (1.4, 3.2, self.sizes["title"] - 2, 5.1)
        self.text(slide, self.box(self.mirror(left, width), label_top, width, 1.2), [{"text": label, "bold": True}], size=self.sizes["number"] * 0.6,
                  floor=24, font=self.fonts["heading"], color=label_color, anchor="bottom", gap=0, name="deck:label")
        self.text(slide, self.box(self.mirror(left, width), title_top, width, 3.4 if self.backdrop else 1.8),
                  [{"text": spec.title_markup or spec.title, "bold": True}], size=title_size,
                  floor=22, font=self.fonts["heading"], color=title_color, anchor="top", gap=0, name="deck:title",
                  bold_color=self.colors["accent"] if title_color == self.colors["text"] else None)
        blocks = [{"text": t} for t in spec.subtitle] + [{"text": i.text} for i in spec.items if i.kind in ("bullet", "para", "number")]
        if blocks:
            self.text(slide, self.box(self.mirror(left, width), sub_top, width, 1.6), blocks, size=self.sizes["body"] - (2 if self.backdrop else 0),
                      floor=14, color=sub_color, name="deck:subtitle")

    def slide_bullets(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        text_items, visuals = spec.text_items, spec.visuals
        if len(spec.bullets) > self.args.max_bullets:
            self.warn(f"slide {number} '{spec.title}': {len(spec.bullets)} bullets, more than {self.args.max_bullets}; split the slide")
        if not text_items and not visuals:
            self.warn(f"slide {number} '{spec.title}': no content")
        if visuals:
            text_w = width * 0.42
            vis_left, vis_w = left + text_w + self.gap, width - text_w - self.gap
            self.place_visuals(slide, visuals, (self.mirror(vis_left, vis_w), top, vis_w, height), columns=False)
            width = text_w
        if text_items:
            _, used, overflow = self.text(slide, self.box(self.mirror(left, width), top, width, height), self.blocks_for(text_items),
                                          size=self.sizes["body"], floor=15, name="deck:body")
            if overflow:
                self.warn(f"slide {number} '{spec.title}': text may overflow at {used:.0f} pt; cut words or split the slide")

    def place_visuals(self, slide, visuals: list[Item], area: tuple[float, float, float, float], columns: bool = True) -> None:
        left, top, width, height = area
        count = len(visuals)
        if columns:
            cell = (width - self.gap * (count - 1)) / count
            boxes = [self.box(left + i * (cell + self.gap), top, cell, height) for i in range(count)]
        else:
            cell = (height - self.gap * (count - 1)) / count
            boxes = [self.box(left, top + i * (cell + self.gap), width, cell) for i in range(count)]
        for item, box in zip(visuals, boxes):
            if item.kind == "image":
                self.picture(slide, item.path, box, "contain", item.alt)
            else:
                self.chart(slide, item, box)

    def slide_split(self, slide, spec: Slide, number: int) -> None:
        """Picture cover-fitted on one half, headline and text on the other."""
        images = [i for i in spec.items if i.kind == "image"]
        if not images:
            self.warn(f"slide {number} '{spec.title}': split layout needs a picture; drawn as bullets")
            self.slide_bullets(slide, spec, number)
            return
        half = SLIDE_W / 2
        self.picture(slide, images[0].path, self.box(self.mirror(half, half), 0, half, SLIDE_H), "cover", images[0].alt)
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, width_scale=(half - self.left_margin - 0.4) / self.content_width)
        left, top, width, height = self.content_area(slide, spec)
        width = half - self.left_margin - 0.4
        text_items = spec.text_items
        if text_items:
            _, used, overflow = self.text(slide, self.box(self.mirror(left, width), top, width, height), self.blocks_for(text_items),
                                          size=self.sizes["body"], floor=15, name="deck:body")
            if overflow:
                self.warn(f"slide {number} '{spec.title}': text may overflow at {used:.0f} pt on a half-width slide")

    def bundled_icon(self, name: str, out_dir: Path) -> Path | None:
        """Recolour the bundled Carbon glyph (deck-images/assets/icons/png) in the accent and save it next to the deck."""
        source = BUNDLED_ICONS_PNG / f"{name}.png"
        if not source.is_file():
            return None
        try:
            from PIL import Image  # python-pptx depends on Pillow, so it is present
        except ImportError:
            return None
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{name}.png"
        glyph = Image.open(source).convert("RGBA")
        r, g, b = (int(parse_hex(self.colors["accent"])[i:i + 2], 16) for i in (0, 2, 4))
        tinted = Image.new("RGBA", glyph.size, (r, g, b, 0))
        tinted.putalpha(glyph.getchannel("A"))
        tinted.save(target)
        return target

    def slide_icons(self, slide, spec: Slide, number: int) -> None:
        """Three or four tiles with an icon, a label and a line of detail."""
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        tiles = [i for i in spec.items if i.kind in ("bullet", "number")]
        if not tiles:
            self.warn(f"slide {number} '{spec.title}': icons layout needs '- icon | label | detail' items")
            return
        if len(tiles) > 4:
            self.warn(f"slide {number} '{spec.title}': {len(tiles)} icons; four fit, the rest are dropped")
            tiles = tiles[:4]
        count = len(tiles)
        cell = (width - self.gap * (count - 1)) / count
        cards = bool(self.layout.get("cards", True))
        icon_dir = (self.board.path.parent if self.board.path else Path(".")) / "images" / "icons"
        for index, tile in enumerate(tiles):
            fields = tile.fields
            icon, label = fields[0], fields[1] if len(fields) > 1 else ""
            detail = fields[2] if len(fields) > 2 else ""
            tile_left = left + index * (cell + self.gap)
            if cards:
                self.rect(slide, self.box(self.mirror(tile_left, cell), top, cell, height), self.colors["surface"],
                          MSO_SHAPE.ROUNDED_RECTANGLE if self.layout.get("corner") else MSO_SHAPE.RECTANGLE, float(self.layout.get("corner") or 0))
            pad = 0.3
            icon_size = 0.9
            icon_box = self.box(self.mirror(tile_left + (cell - icon_size) / 2, icon_size), top + pad + 0.1, icon_size, icon_size)
            png = icon_dir / f"{icon}.png"
            if not png.is_file():
                png = self.bundled_icon(icon, icon_dir)
            if png is not None and png.is_file():
                self.picture(slide, png, icon_box, "contain", icon)
            else:  # no such icon anywhere: a coloured disc with the label's initial
                disc = self.rect(slide, icon_box, self.colors["accent"], MSO_SHAPE.OVAL)
                frame = disc.text_frame
                frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
                frame.vertical_anchor = MSO_ANCHOR.MIDDLE
                paragraph = frame.paragraphs[0]
                paragraph.alignment = PP_ALIGN.CENTER
                run = paragraph.add_run()
                run.text = (label or icon)[:1].upper()
                run.font.size = Pt(26)
                run.font.bold = True
                run.font.name = self.fonts["heading"]
                run.font.color.rgb = rgb(self.colors["on_accent"])
                self.warn(f"slide {number}: icon '{icon}' is not in the bundled set; a disc with the initial is drawn instead")
            blocks = []
            if label:
                blocks.append({"text": label, "bold": True, "gap_scale": 0.5, "font": self.fonts["heading"]})
            if detail:
                blocks.append({"text": detail, "scale": 0.78, "color": self.colors["muted"]})
            if blocks:
                self.text(slide, self.box(self.mirror(tile_left + pad, cell - 2 * pad), top + pad + icon_size + 0.35, cell - 2 * pad, height - icon_size - 2 * pad - 0.35),
                          blocks, size=self.sizes["body"], floor=14, align="center", name="deck:icon-label")

    def slide_two_column(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        columns: list[tuple[str, list[Item]]] = []
        lead: list[Item] = []
        for item in spec.items:
            if item.kind == "heading":
                columns.append((item.text, []))
            elif columns:
                columns[-1][1].append(item)
            elif item.kind in ("bullet", "number", "para", "code"):
                lead.append(item)
        if not columns:
            self.warn(f"slide {number} '{spec.title}': two-column layout without '###' column titles; falling back to bullets")
            columns = [("", spec.text_items)]
        if len(columns) > 3:
            self.warn(f"slide {number} '{spec.title}': {len(columns)} columns; only the first three are drawn")
            columns = columns[:3]
        if lead:
            self.text(slide, self.box(self.mirror(left, width), top, width, 0.9), self.blocks_for(lead), size=self.sizes["body"], floor=14, name="deck:lead")
            top += 1.0
            height -= 1.0
        count = len(columns)
        cell = (width - self.gap * (count - 1)) / count
        cards = bool(self.layout.get("cards", True))
        for index, (title, items) in enumerate(columns):
            col_left = left + index * (cell + self.gap)
            if cards:
                self.rect(slide, self.box(self.mirror(col_left, cell), top, cell, height), self.colors["surface"],
                          MSO_SHAPE.ROUNDED_RECTANGLE if self.layout.get("corner") else MSO_SHAPE.RECTANGLE, float(self.layout.get("corner") or 0))
                self.rect(slide, self.box(self.mirror(col_left, cell), top, cell, 0.08), self.colors["chart"][index % len(self.colors["chart"])])
            pad = 0.2 if cards else 0.0
            inner_left, inner_w = col_left + pad, cell - 2 * pad
            y = top + pad + (0.05 if cards else 0)
            if title:
                self.text(slide, self.box(self.mirror(inner_left, inner_w), y, inner_w, 0.7), [{"text": title, "bold": True}], size=self.sizes["body"] + 2,
                          floor=16, font=self.fonts["heading"], color=self.colors["accent"], anchor="middle", gap=0, name="deck:column-title")
                y += 0.75
            blocks = self.blocks_for([i for i in items if i.kind in ("bullet", "number", "para", "code")])
            visuals = [i for i in items if i.kind in ("image", "chart")]
            body_h = top + height - y - pad
            if visuals:
                vis_h = body_h * (0.55 if blocks else 1.0)
                self.place_visuals(slide, visuals, (self.mirror(inner_left, inner_w), top + height - pad - vis_h, inner_w, vis_h))
                body_h -= vis_h + self.gap
            if blocks:
                _, used, overflow = self.text(slide, self.box(self.mirror(inner_left, inner_w), y, inner_w, body_h), blocks,
                                              size=self.sizes["body"] - 2, floor=14, name="deck:column")
                if overflow:
                    self.warn(f"slide {number} '{spec.title}': column '{title}' may overflow at {used:.0f} pt")

    def slide_big_number(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        tiles = [i for i in spec.items if i.kind in ("bullet", "number")]
        lead = [i for i in spec.items if i.kind in ("para", "code")]
        if not tiles:
            self.warn(f"slide {number} '{spec.title}': big-number layout needs '- value | label | detail' items")
            return
        if len(tiles) > 4:
            self.warn(f"slide {number} '{spec.title}': {len(tiles)} numbers; only four fit, the rest are dropped")
            tiles = tiles[:4]
        if lead:
            self.text(slide, self.box(self.mirror(left, width), top, width, 0.8), self.blocks_for(lead), size=self.sizes["body"], floor=14, name="deck:lead")
            top += 0.9
            height -= 0.9
        count = len(tiles)
        cell = (width - self.gap * (count - 1)) / count
        number_size = {1: self.sizes["number"] + 12, 2: self.sizes["number"], 3: self.sizes["number"] - 8, 4: self.sizes["number"] - 14}[count]
        cards = bool(self.layout.get("cards", True))
        for index, tile in enumerate(tiles):
            fields = tile.fields
            value = fields[0]
            label = fields[1] if len(fields) > 1 else ""
            detail = fields[2] if len(fields) > 2 else ""
            tile_left = left + index * (cell + self.gap)
            if cards:
                self.rect(slide, self.box(self.mirror(tile_left, cell), top, cell, height), self.colors["surface"],
                          MSO_SHAPE.ROUNDED_RECTANGLE if self.layout.get("corner") else MSO_SHAPE.RECTANGLE, float(self.layout.get("corner") or 0))
            pad = 0.25
            inner = (self.mirror(tile_left + pad, cell - 2 * pad), cell - 2 * pad)
            self.text(slide, self.box(inner[0], top + pad, inner[1], height * 0.5), [{"text": value, "bold": True}], size=number_size, floor=28,
                      font=self.fonts.get("number") or self.fonts["heading"], color=self.colors["accent"], anchor="bottom", gap=0,
                      align="center" if count > 1 else self.align, name="deck:number")
            blocks = []
            if label:
                blocks.append({"text": label, "bold": True, "gap_scale": 0.5})
            if detail:
                blocks.append({"text": detail, "scale": 0.75, "color": self.colors["muted"]})
            if blocks:
                self.text(slide, self.box(inner[0], top + pad + height * 0.5, inner[1], height * 0.5 - pad), blocks, size=self.sizes["body"], floor=14,
                          align="center" if count > 1 else self.align, name="deck:number-label")

    def slide_quote(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, small=True)
        left, top, width, height = self.content_area(slide, spec)
        quote = spec.quote or " ".join(i.text for i in spec.items if i.kind == "para")
        if not quote:
            self.warn(f"slide {number} '{spec.title}': quote layout without a '>' quote line")
        mark_w = 1.1
        self.text(slide, self.box(self.mirror(left, mark_w), top - 0.3, mark_w, 1.6), [{"text": "“", "bold": True}], size=120, floor=120,
                  font=self.fonts["heading"], color=self.colors["accent"], fit=False, gap=0, align="left", name="deck:quote-mark")
        text_left, text_w = left + mark_w, width - mark_w
        self.text(slide, self.box(self.mirror(text_left, text_w), top, text_w, height * 0.72), [{"text": quote, "italic": True}], size=self.sizes["headline"],
                  floor=20, font=self.fonts["heading"], anchor="middle", gap=0, name="deck:quote")
        attribution = spec.attribution
        if attribution:
            self.text(slide, self.box(self.mirror(text_left, text_w), top + height * 0.72, text_w, height * 0.28), [{"text": "— " + attribution}],
                      size=self.sizes["body"], floor=14, color=self.colors["muted"], anchor="top", name="deck:attribution")

    def slide_statement(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        left, top, width, height = self.content_area(slide, spec)
        top, height = 0.9, height + (self.content_top - 0.9)
        paras = [i.text for i in spec.items if i.kind in ("para", "bullet", "number")]
        stmt_h = height * (0.62 if paras else 0.9)
        self.rect(slide, self.box(self.mirror(left, 1.2), top + 0.3, 1.2, 0.09), self.colors["accent"])
        self.text(slide, self.box(self.mirror(left, width), top + 0.5, width, stmt_h), [{"text": spec.title_markup or spec.title, "bold": True}], size=self.sizes["title"],
                  floor=28, font=self.fonts["heading"], anchor="top", gap=0, name="deck:statement", bold_color=self.colors["accent"])
        if paras:
            self.text(slide, self.box(self.mirror(left, width), top + 0.5 + stmt_h, width, height - stmt_h - 0.5), [{"text": p, "gap_scale": 1.3} for p in paras],
                      size=self.sizes["body"] + 2, floor=16, color=self.colors["muted"], name="deck:body")

    def slide_image(self, slide, spec: Slide, number: int) -> None:
        images = [i for i in spec.items if i.kind == "image"]
        captions = [i.text for i in spec.items if i.kind in ("para", "bullet", "number")]
        if not images:
            self.warn(f"slide {number} '{spec.title}': image layout without a picture")
            self.slide_bullets(slide, spec, number)
            return
        if len(images) == 1 and not captions:
            self.picture(slide, images[0].path, self.box(0, 0, SLIDE_W, SLIDE_H), "cover", images[0].alt)
            scrim_h = 2.6
            scrim = self.rect(slide, self.box(0, SLIDE_H - scrim_h, SLIDE_W, scrim_h), "#000000")
            set_alpha(scrim, 62)
            self.text(slide, self.box(self.mirror(self.left_margin, self.content_width), SLIDE_H - scrim_h + 0.3, self.content_width, 1.5),
                      [{"text": spec.title, "bold": True}], size=self.sizes["headline"], floor=22, font=self.fonts["heading"], color="#FFFFFF",
                      anchor="middle", gap=0, name="deck:headline")
            if spec.source:  # narrower than the content area so the slide number keeps its corner
                self.text(slide, self.box(self.mirror(self.left_margin, self.content_width - 1.0), SLIDE_H - 0.65, self.content_width - 1.0, 0.4),
                          [{"text": f"{self.source_label} {spec.source}"}], size=self.sizes["small"], floor=10, color="#DDDDDD", fit=True, gap=0, name="deck:source")
            if spec.takeaway:
                self.warn(f"slide {number} '{spec.title}': takeaway is not drawn on a full-bleed image slide; move it to the notes")
            self.text(slide, self.box(self.mirror(SLIDE_W - self.margin - 0.8, 0.8), self.footer_top, 0.8, 0.3), [{"text": str(number)}],
                      size=self.sizes["small"], floor=10, color="#DDDDDD", fit=False, align="right", name="deck:number")
            return
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        caption_h = 0.8 if captions else 0.0
        rows = 1 if len(images) <= 3 else 2
        per_row = math.ceil(len(images) / rows)
        cell_w = (width - self.gap * (per_row - 1)) / per_row
        cell_h = (height - caption_h - self.gap * (rows - 1)) / rows
        for index, image in enumerate(images):
            row, col = divmod(index, per_row)
            box = self.box(self.mirror(left + col * (cell_w + self.gap), cell_w), top + row * (cell_h + self.gap), cell_w, cell_h)
            self.picture(slide, image.path, box, "contain", image.alt)
        if captions:
            self.text(slide, self.box(self.mirror(left, width), top + height - caption_h, width, caption_h), [{"text": c} for c in captions],
                      size=self.sizes["body"] - 2, floor=12, color=self.colors["muted"], anchor="bottom", name="deck:caption")

    def slide_chart(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        visuals = spec.visuals
        if not visuals:
            self.warn(f"slide {number} '{spec.title}': chart layout without a chart block or picture")
            return
        if spec.text_items:
            self.slide_bullets_body(slide, spec, number, (left, top, width, height))
            return
        self.place_visuals(slide, visuals, (self.mirror(left, width), top, width, height), columns=True)

    def slide_bullets_body(self, slide, spec: Slide, number: int, area: tuple[float, float, float, float]) -> None:
        left, top, width, height = area
        text_w = width * 0.4
        vis_left, vis_w = left + text_w + self.gap, width - text_w - self.gap
        self.place_visuals(slide, spec.visuals, (self.mirror(vis_left, vis_w), top, vis_w, height), columns=False)
        self.text(slide, self.box(self.mirror(left, text_w), top, text_w, height), self.blocks_for(spec.text_items), size=self.sizes["body"], floor=15,
                  name="deck:body")

    def slide_timeline(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        steps = [i for i in spec.items if i.kind in ("bullet", "number")]
        if not steps:
            self.warn(f"slide {number} '{spec.title}': timeline layout needs '- label | detail' items")
            return
        if len(steps) > 6:
            self.warn(f"slide {number} '{spec.title}': {len(steps)} steps; six fit on one slide, the rest are dropped")
            steps = steps[:6]
        count = len(steps)
        cell = width / count
        radius = 0.32
        line_y = top + 0.9
        connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(Inches(left + cell / 2)), int(Inches(line_y)),
                                               int(Inches(left + width - cell / 2)), int(Inches(line_y)))
        connector.line.color.rgb = rgb(self.colors["line"])
        connector.line.width = Pt(2.25)
        for index, step in enumerate(steps):
            fields = step.fields
            marker = fields[0] if len(fields) >= 3 else str(index + 1)
            label = fields[1] if len(fields) >= 3 else fields[0]
            detail = fields[2] if len(fields) >= 3 else (fields[1] if len(fields) == 2 else "")
            center_x = left + cell * index + cell / 2
            if self.rtl:
                center_x = SLIDE_W - center_x
            circle_d = radius * 2 if len(marker) <= 2 else radius * 2 + 0.35
            circle = self.rect(slide, self.box(center_x - circle_d / 2, line_y - circle_d / 2, circle_d, circle_d), self.colors["accent"], MSO_SHAPE.OVAL)
            frame = circle.text_frame
            frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
            frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            paragraph = frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER
            run = paragraph.add_run()
            run.text = marker
            run.font.size = Pt(14 if len(marker) <= 2 else 12)
            run.font.bold = True
            run.font.name = self.fonts["heading"]
            run.font.color.rgb = rgb(self.colors["on_accent"])
            text_left = center_x - cell / 2 + 0.1
            blocks = [{"text": label, "bold": True, "gap_scale": 0.6, "font": self.fonts["heading"]}]
            if detail:
                blocks.append({"text": detail, "scale": 0.8, "color": self.colors["muted"]})
            self.text(slide, self.box(text_left, line_y + radius + 0.25, cell - 0.2, height - 1.5), blocks, size=self.sizes["body"] - 2, floor=12,
                      align="center", name="deck:step")

    def slide_table(self, slide, spec: Slide, number: int) -> None:
        self.furniture(slide, number, spec)
        self.headline(slide, spec.title_markup or spec.title, number, shifted=self.eyebrow(slide, spec))
        left, top, width, height = self.content_area(slide, spec)
        rows = [r.cells for r in spec.rows]
        if not rows:
            self.warn(f"slide {number} '{spec.title}': table layout without '| a | b |' rows")
            return
        cols = max(len(r) for r in rows)
        rows = [r + [""] * (cols - len(r)) for r in rows]
        num_cols = numeric_columns(rows)
        if len(rows) > 9 or cols > 6:
            self.warn(f"slide {number} '{spec.title}': {len(rows)} rows x {cols} columns; keep tables under nine rows and six columns")
        row_h = min(0.6, height / len(rows))
        shape = slide.shapes.add_table(len(rows), cols, *self.box(left, top, width, row_h * len(rows)))
        table = shape.table
        tbl_pr = table._tbl.tblPr
        tbl_pr.set("bandRow", "0")
        tbl_pr.set("firstRow", "1")
        style_id = tbl_pr.find(qn("a:tableStyleId"))
        if style_id is not None:
            style_id.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # No Style, No Grid
        weights = [max(4, max(len(inline_clean(r[c])) for r in rows)) * (0.9 if num_cols[c] else 1.25) for c in range(cols)]
        total = sum(weights)
        for index, column in enumerate(table.columns):
            column.width = int(Inches(width * weights[index] / total))
        font_size = 14 if len(rows) <= 5 else 13 if len(rows) <= 7 else 12
        order = list(range(cols))[::-1] if self.rtl else list(range(cols))
        for r, row in enumerate(rows):
            table.rows[r].height = int(Inches(row_h))
            for c_pos, c in enumerate(order):
                cell = table.cell(r, c_pos)
                cell.fill.solid()
                if r == 0:
                    cell.fill.fore_color.rgb = rgb(self.colors["accent"])
                else:
                    cell.fill.fore_color.rgb = rgb(self.colors["surface"] if r % 2 == 0 else self.colors["bg"])
                    cell_border_bottom(cell, self.colors["line"], 0.75)
                cell.margin_left = cell.margin_right = Inches(0.1)
                cell.margin_top = cell.margin_bottom = Inches(0.04)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                paragraph = cell.text_frame.paragraphs[0]
                numeric = num_cols[c]  # the header follows its column, so labels and values line up
                if numeric:
                    cell.text_frame.word_wrap = False
                paragraph.alignment = (PP_ALIGN.LEFT if self.rtl else PP_ALIGN.RIGHT) if numeric else ALIGN[self.align]
                if self.rtl:
                    set_rtl(paragraph)
                for piece, bold in bold_parts(typographic(row[c])) or [("", False)]:
                    run = paragraph.add_run()
                    run.text = piece
                    run.font.size = Pt(font_size)
                    run.font.name = self.fonts["body"]
                    run.font.bold = bool(bold or r == 0)
                    run.font.color.rgb = rgb(self.colors["on_accent"] if r == 0 else self.colors["text"])

    # charts -----------------------------------------------------------------
    def chart_notes(self, slide, spec: dict, box: tuple[int, int, int, int]) -> None:
        """Annotations as a line above the chart: the .pptx cannot carry a leader line to a bar."""
        notes = [f"{n.get('category', '')}: {n.get('text', '')}".strip(" :") for n in (spec.get("annotations") or [])]
        if not notes:
            return
        left, top, width = box[0] / EMU, box[1] / EMU, box[2] / EMU
        self.text(slide, self.box(left, top + 0.04, width, 0.3), [{"text": "  ·  ".join(notes), "bold": True}],
                  size=self.sizes["small"] + 1, floor=self.sizes["small"], color=self.colors["accent"],
                  fit=False, gap=0, align="right" if not self.rtl else "left", name="deck:chart-note")

    def chart(self, slide, item: Item, box: tuple[int, int, int, int]) -> None:
        spec = item.chart or {}
        if spec.get("annotations"):  # the note sits in a strip above the plot
            box = (box[0], box[1] + int(Inches(0.34)), box[2], box[3] - int(Inches(0.34)))
        data = CategoryChartData()
        data.categories = spec["categories"]
        for name, values in spec["series"]:
            data.add_series(name, values)
        graphic = slide.shapes.add_chart(CHART_TYPES[spec["type"]], *box, data)
        alt = item.alt or spec.get("title") or f"{spec['type']} chart of {', '.join(spec['categories'][:6])}"
        try:  # alt text for screen readers; the shape tree differs between python-pptx versions
            graphic._element.nvGraphicFramePr.cNvPr.set("descr", alt)
        except Exception:
            pass
        chart = graphic.chart
        palette = self.colors["chart"]
        text, muted, line = self.colors["text"], self.colors["muted"], self.colors["line"]
        chart.font.size = Pt(12)
        chart.font.name = self.fonts["body"]
        chart.font.color.rgb = rgb(text)
        is_pie = spec["type"] in ("pie", "doughnut")
        is_line = spec["type"] in ("line",)
        plot = chart.plots[0]
        if spec["type"] in ("bar", "column", "barh", "stacked", "barh-stacked"):
            plot.gap_width = 70
            if spec["type"] in ("stacked", "barh-stacked"):
                plot.overlap = 100
        highlight = set(spec.get("highlight") or [])
        single = len(spec["series"]) == 1
        for index, series in enumerate(plot.series):
            color = palette[index % len(palette)]
            if is_pie:
                plot.vary_by_categories = True
                for point_index, point in enumerate(series.points):
                    point.format.fill.solid()
                    point.format.fill.fore_color.rgb = rgb(palette[point_index % len(palette)])
                    point.format.line.color.rgb = rgb(self.colors["bg"])
            elif is_line:
                series.smooth = False
                series.format.line.color.rgb = rgb(color)
                series.format.line.width = Pt(2.75)
                series.marker.style = XL_MARKER_STYLE.CIRCLE
                series.marker.size = 7
                series.marker.format.fill.solid()
                series.marker.format.fill.fore_color.rgb = rgb(color)
                series.marker.format.line.color.rgb = rgb(color)
            else:
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = rgb(color)
                series.format.line.fill.background()
                if highlight and single:
                    faded = mix(self.colors["muted"], self.colors["bg"], 0.55)
                    for point_index, category in enumerate(spec["categories"]):
                        point = series.points[point_index]
                        point.format.fill.solid()
                        chosen = category in highlight or str(point_index) in highlight
                        point.format.fill.fore_color.rgb = rgb(self.colors["accent"] if chosen else faded)
        if not is_pie:
            value_axis = chart.value_axis
            value_axis.has_major_gridlines = True
            value_axis.major_gridlines.format.line.color.rgb = rgb(line)
            value_axis.major_gridlines.format.line.width = Pt(0.75)
            value_axis.format.line.fill.background()
            value_axis.tick_labels.font.size = Pt(12)
            value_axis.tick_labels.font.color.rgb = rgb(muted)
            if spec.get("number_format"):
                value_axis.tick_labels.number_format = str(spec["number_format"])
                value_axis.tick_labels.number_format_is_linked = False
            category_axis = chart.category_axis
            category_axis.format.line.color.rgb = rgb(line)
            category_axis.tick_labels.font.size = Pt(12)
            category_axis.tick_labels.font.color.rgb = rgb(muted)
            category_axis.has_major_gridlines = False
            category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW  # labels stay at the edge when values go negative
            if spec["type"] not in ("barh", "barh-stacked"):
                slot = (box[2] / EMU) / max(1, len(spec["categories"]))  # inches per category
                longest = max((len(str(c)) for c in spec["categories"]), default=0)
                if longest * 0.075 > slot - 0.06:  # about 0.075 in per character at 12 pt
                    rotate_tick_labels(category_axis, -30)
            if spec["type"] in ("barh", "barh-stacked"):
                category_axis.reverse_order = True  # first category at the top, as in the storyboard
                category_axis.crosses = XL_AXIS_CROSSES.MAXIMUM  # keeps the value axis at the bottom
        legend = spec["legend"] if spec.get("legend") is not None else (is_pie or len(spec["series"]) > 1)
        chart.has_legend = bool(legend)
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.RIGHT if is_pie else XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(12)
            chart.legend.font.color.rgb = rgb(muted)
        if spec.get("title"):
            chart.has_title = True
            chart.chart_title.text_frame.text = spec["title"]
            for paragraph in chart.chart_title.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(14)
                    run.font.bold = True
                    run.font.color.rgb = rgb(text)
        else:
            chart.has_title = False
        self.chart_notes(slide, spec, (box[0], box[1] - int(Inches(0.34)), box[2], box[3]))
        if spec.get("target") is not None and not is_pie:
            value = float(spec["target"]["value"]) if isinstance(spec["target"], dict) else float(spec["target"])
            self.warn(f"chart target {value:g} is drawn only in the HTML deck; the .pptx keeps the bars alone")
        if spec.get("data_labels"):
            plot.has_data_labels = True
            labels = plot.data_labels
            labels.font.size = Pt(12)
            labels.font.color.rgb = rgb(text)
            if is_pie:
                labels.show_percentage = True
                labels.show_value = False
                labels.number_format = "0%"
                labels.number_format_is_linked = False
            else:
                if spec["type"] in ("stacked", "barh-stacked"):
                    labels.position = XL_LABEL_POSITION.CENTER
                elif is_line:
                    labels.position = XL_LABEL_POSITION.ABOVE
                else:
                    labels.position = XL_LABEL_POSITION.OUTSIDE_END
                if spec.get("number_format"):
                    labels.number_format = str(spec["number_format"])
                    labels.number_format_is_linked = False


# --------------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("storyboard", help="storyboard Markdown file")
    parser.add_argument("-o", "--output", required=True, help="output .pptx path (never the user's original file)")
    parser.add_argument("--theme", help="theme.json from deck-style (default: the built-in Boardroom Blue theme)")
    parser.add_argument("--logo", help="PNG or JPEG logo drawn in the top corner of content slides")
    parser.add_argument("--backdrop", help="picture behind the title slide (overrides 'backdrop:' in the front matter; sections use 'section_backdrop:' or their own picture line)")
    parser.add_argument("--max-bullets", type=int, default=6, help="warn when a slide has more bullets than this (default 6)")
    parser.add_argument("--strict", action="store_true", help="exit 1 without writing the deck when there are warnings")
    args = parser.parse_args(argv)
    try:
        board = load_storyboard(Path(args.storyboard))
        theme = load_theme(args.theme)
        deck = Deck(board, theme, args)
        deck.build()
    except (StoryboardError, BuildError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    except FileNotFoundError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    if deck.warnings and args.strict:
        sys.stderr.write(f"{len(deck.warnings)} warning(s) and --strict: nothing written\n")
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    deck.prs.save(str(output))
    print(f"wrote {output}: {len(board.slides)} slides, theme '{theme.get('name', theme.get('id'))}', {len(deck.warnings)} warning(s)")
    print("\n".join(deck.summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
