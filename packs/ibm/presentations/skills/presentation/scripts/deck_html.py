#!/usr/bin/env python3
"""Build an HTML presentation from the same storyboard and theme as the .pptx deck.

Two modes, one file, no network:

    deck_html.py storyboard.md --theme theme.json -o deck.html                 interactive
    deck_html.py storyboard.md --theme theme.json --mode static -o print.html  one page per slide, print to PDF

Interactive: arrow keys, space, click, swipe; O for the overview grid, N for
speaker notes, F for fullscreen, P for the print view, ? for help; the slide
number is in the address bar, so a link opens on that slide. Static: the slides
stacked as pages, `@page` set to the slide size, so the browser's Print to PDF
gives one slide per page.

Everything is inlined: CSS, the navigation script, charts as SVG, pictures as
data URIs (`--link-images` keeps them as relative links instead). Slides are a
fixed 1280 x 720 stage scaled to the window, so the layout matches the .pptx.

Also importable: `render_document(board, theme, ...)` returns the whole page and
`render_slides(board, theme)` the slide markup, which is how the style preview
shows concepts on the deck's own slides.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import mimetypes
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ inside an installed skill
sys.path.insert(0, str(Path(__file__).resolve().parent))
from storyboard import (Item, Slide, Storyboard, StoryboardError, appendix_label, bold_parts, inline_clean,  # noqa: E402
                        load_storyboard, numeric_columns, typographic)

IN = 96.0  # px per inch: 13.333 x 7.5 in = 1280 x 720 px
SLIDE_W, SLIDE_H = 1280, 720
PT = 4 / 3  # px per point

ICONS_DIR = Path(__file__).resolve().parents[2] / "deck-images" / "assets" / "icons"  # bundled Carbon icons
DEFAULT_THEME = {
    "id": "boardroom", "name": "Boardroom Blue", "dark": False,
    "colors": {"bg": "#FFFFFF", "surface": "#F2F4F8", "text": "#161616", "muted": "#525252", "accent": "#0F62FE",
               "accent2": "#002D9C", "line": "#C6C6C6", "on_accent": "#FFFFFF",
               "chart": ["#0F62FE", "#002D9C", "#8A3FFC", "#009D9A", "#FF832B", "#A8A8A8"]},
    "fonts": {"heading": "Arial", "body": "Arial", "mono": "Consolas",
              "css_heading": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif", "css_body": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"},
    "sizes": {"title": 40, "headline": 30, "body": 20, "small": 12, "number": 60},
    "layout": {"align": "left", "accent_bar": "top", "title_style": "split", "section_style": "accent",
               "corner": 0.06, "bullet": "▪", "cards": True, "ornament": "none"},
}


class HtmlError(Exception):
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
        raise HtmlError(f"theme not found: {file}")
    try:
        return deep_merge(DEFAULT_THEME, json.loads(file.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise HtmlError(f"theme {file} is not valid JSON: {error}") from None


def parse_hex(value: str) -> str:
    text = str(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        raise HtmlError(f"colour '{value}' is not a hex colour like #0F62FE")
    return "#" + text.upper()


def mix(color: str, other: str, amount: float) -> str:
    a, b = parse_hex(color)[1:], parse_hex(other)[1:]
    parts = [round(int(a[i:i + 2], 16) * (1 - amount) + int(b[i:i + 2], 16) * amount) for i in (0, 2, 4)]
    return "#" + "".join(f"{max(0, min(255, p)):02X}" for p in parts)


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


HYPHENATED = re.compile(r"(\w+(?:-\w+)+)")


def keep_hyphens(html_text: str) -> str:
    """Hyphenated words (self-serve, time-to-value) never break across lines."""
    return HYPHENATED.sub(r'<span class="nobr">\1</span>', html_text)


def rich(text: str) -> str:
    """Escape a text line, keeping paired **bold** markers as <b> and hyphenated words whole."""
    return "".join(f"<b>{keep_hyphens(esc(piece))}</b>" if bold else keep_hyphens(esc(piece))
                   for piece, bold in bold_parts(typographic(text))) or ""


def data_uri(path: Path) -> str:
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


# --------------------------------------------------------------------------- SVG charts
def fmt_number(spec: dict):
    pattern = spec.get("number_format") or ""
    unit = spec.get("unit", "") or ""

    def apply(value: float) -> str:
        if pattern and "{" in pattern:
            try:
                return pattern.format(value) + unit
            except (ValueError, TypeError):
                return f"{value:g}{unit}"
        decimals = 0
        percent = pattern.endswith("%")
        core = pattern.rstrip("%")
        if "." in core:
            decimals = len(core.split(".")[1])
        text = f"{value:,.{decimals}f}"
        return text + ("%" if percent else "") + unit
    return apply


def nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    if high == low:
        high = low + 1
    span = high - low
    raw = span / max(1, count)
    magnitude = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = min((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw), default=magnitude)
    start = math.floor(low / step) * step
    ticks = []
    value = start
    while value <= high + step * 0.5:
        ticks.append(round(value, 10))
        value += step
    return ticks


def svg_chart(spec: dict, colors: dict, fonts: dict, width: int, height: int) -> str:
    """One chart as inline SVG, drawn from the same spec as the native PowerPoint chart."""
    kind = spec["type"]
    categories = [str(c) for c in spec["categories"]]
    series = [(name, list(values)) for name, values in spec["series"]]
    palette = colors["chart"]
    labels = fmt_number(spec)
    text, muted, line, bg = colors["text"], colors["muted"], colors["line"], colors["bg"]
    font = fonts.get("css_body", fonts.get("body", "sans-serif"))
    parts = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
             f'style="font-family:{esc(font)}" aria-label="{esc(spec.get("title") or kind + " chart")}">']
    show_legend = spec.get("legend") if spec.get("legend") is not None else (kind in ("pie", "doughnut") or len(series) > 1)
    legend_h = 26 if show_legend else 0
    title_h = 26 if spec.get("title") else 0
    if spec.get("title"):
        parts.append(f'<text x="0" y="18" font-size="16" font-weight="700" fill="{text}">{esc(spec["title"])}</text>')

    if kind in ("pie", "doughnut"):
        values = series[0][1]
        total = sum(values) or 1
        radius = min(width * 0.42, (height - title_h - legend_h) * 0.46)
        cx, cy = width / 2, title_h + (height - title_h - legend_h) / 2
        angle = -math.pi / 2
        highlight = set(spec.get("highlight") or [])
        for index, (category, value) in enumerate(zip(categories, values)):
            sweep = 2 * math.pi * value / total
            x1, y1 = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
            x2, y2 = cx + radius * math.cos(angle + sweep), cy + radius * math.sin(angle + sweep)
            large = 1 if sweep > math.pi else 0
            fill = colors["accent"] if category in highlight else (palette[index % len(palette)] if not highlight else mix(muted, bg, 0.45))
            if kind == "doughnut":
                inner = radius * 0.6
                ix1, iy1 = cx + inner * math.cos(angle + sweep), cy + inner * math.sin(angle + sweep)
                ix2, iy2 = cx + inner * math.cos(angle), cy + inner * math.sin(angle)
                d = (f"M{x1:.1f},{y1:.1f} A{radius:.1f},{radius:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} "
                     f"L{ix1:.1f},{iy1:.1f} A{inner:.1f},{inner:.1f} 0 {large} 0 {ix2:.1f},{iy2:.1f} Z")
            else:
                d = f"M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} A{radius:.1f},{radius:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z"
            parts.append(f'<path d="{d}" fill="{fill}" stroke="{bg}" stroke-width="2"></path>')
            if spec.get("data_labels") and value / total > 0.04:
                mid = angle + sweep / 2
                lx, ly = cx + radius * 0.72 * math.cos(mid), cy + radius * 0.72 * math.sin(mid)
                parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="13" text-anchor="middle" dominant-baseline="middle" '
                             f'fill="{bg if kind == "pie" else text}">{value / total:.0%}</text>')
            angle += sweep
        if show_legend:
            parts.append(legend_svg(categories, [colors["accent"] if c in (spec.get("highlight") or []) else palette[i % len(palette)]
                                                 for i, c in enumerate(categories)], width, height - 8, muted))
        parts.append("</svg>")
        return "".join(parts)

    horizontal = kind in ("barh", "barh-stacked")
    stacked = kind in ("stacked", "barh-stacked")
    if stacked:
        totals = [sum(values[i] for _, values in series) for i in range(len(categories))]
        low, high = min(0, min(totals)), max(0, max(totals))
    else:
        flat = [v for _, values in series for v in values]
        low, high = min(0, min(flat)), max(0, max(flat))
    if kind in ("line", "area") and low == 0 and min(flat) > 0:
        low = min(flat) * 0.9
    ticks = nice_ticks(low, high)
    low, high = min(ticks[0], low), max(ticks[-1], high)
    if spec.get("data_labels", True) and kind not in ("stacked", "barh-stacked"):
        high += (high - low) * 0.07  # headroom so the label above the tallest column is not clipped
    pad_l = 88 if not horizontal else max(90, min(240, 9 * max(len(c) for c in categories) + 20))
    pad_r, pad_t = 26, title_h + 14
    pad_b = height - legend_h - 30
    plot_w, plot_h = width - pad_l - pad_r, pad_b - pad_t

    def vx(value: float) -> float:
        return pad_l + (value - low) / (high - low) * plot_w

    def vy(value: float) -> float:
        return pad_b - (value - low) / (high - low) * plot_h

    for tick in ticks:
        if horizontal:
            x = vx(tick)
            parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_b}" stroke="{line}" stroke-width="1"></line>')
            parts.append(f'<text x="{x:.1f}" y="{pad_b + 18}" font-size="12" text-anchor="middle" fill="{muted}">{esc(labels(tick))}</text>')
        else:
            y = vy(tick)
            parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="{line}" stroke-width="1"></line>')
            parts.append(f'<text x="{pad_l - 10}" y="{y + 4:.1f}" font-size="12" text-anchor="end" fill="{muted}">{esc(labels(tick))}</text>')

    slot = (plot_h if horizontal else plot_w) / max(1, len(categories))
    highlight = set(spec.get("highlight") or [])
    single = len(series) == 1

    if kind in ("line", "area"):
        for index, (name, values) in enumerate(series):
            color = palette[index % len(palette)]
            points = [(pad_l + slot * (i + 0.5), vy(v)) for i, v in enumerate(values)]
            path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points))
            if kind == "area":
                area = path + f" L{points[-1][0]:.1f},{vy(low):.1f} L{points[0][0]:.1f},{vy(low):.1f} Z"
                parts.append(f'<path d="{area}" fill="{color}" opacity="0.14"></path>')
            parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"></path>')
            for (x, y), value in zip(points, values):
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="{bg}" stroke-width="1.5"></circle>')
                if spec.get("data_labels"):
                    parts.append(f'<text x="{x:.1f}" y="{y - 12:.1f}" font-size="12" text-anchor="middle" fill="{text}">{esc(labels(value))}</text>')
    else:
        count = len(series)
        thickness = slot * (0.62 if stacked or single else 0.78 / count)
        offsets = [0.0] * len(categories)
        negatives = [0.0] * len(categories)
        for index, (name, values) in enumerate(series):
            base = palette[index % len(palette)]
            for position, value in enumerate(values):
                if single and highlight:
                    color = colors["accent"] if (categories[position] in highlight or str(position) in highlight) else mix(muted, bg, 0.5)
                else:
                    color = base
                centre = pad_l + slot * (position + 0.5) if not horizontal else pad_t + slot * (position + 0.5)
                shift = 0 if (stacked or single) else (index - (count - 1) / 2) * thickness
                start = (offsets if value >= 0 else negatives)[position] if stacked else 0.0
                if horizontal:
                    x0, x1 = vx(start + min(0, value)), vx(start + max(0, value))
                    y0 = centre + shift - thickness / 2
                    parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{max(1, x1 - x0):.1f}" height="{thickness:.1f}" fill="{color}"></rect>')
                    if spec.get("data_labels", True):
                        anchor, tx = ("start", x1 + 6) if value >= 0 else ("end", x0 - 6)
                        fill = bg if stacked else text
                        if stacked:
                            tx, anchor = (x0 + x1) / 2, "middle"
                        parts.append(f'<text x="{tx:.1f}" y="{y0 + thickness / 2 + 4:.1f}" font-size="12" text-anchor="{anchor}" fill="{fill}">{esc(labels(value))}</text>')
                else:
                    y0, y1 = vy(start + max(0, value)), vy(start + min(0, value))
                    x0 = centre + shift - thickness / 2
                    parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{thickness:.1f}" height="{max(1, y1 - y0):.1f}" fill="{color}"></rect>')
                    if spec.get("data_labels", True):
                        ty = y0 - 7 if value >= 0 else y1 + 16
                        fill = text
                        if stacked:
                            ty, fill = (y0 + y1) / 2 + 4, bg
                        parts.append(f'<text x="{x0 + thickness / 2:.1f}" y="{ty:.1f}" font-size="12" text-anchor="middle" fill="{fill}">{esc(labels(value))}</text>')
                if stacked:
                    if value >= 0:
                        offsets[position] += value
                    else:
                        negatives[position] += value

    # crowded or long category labels lean instead of overlapping
    longest = max((len(c) for c in categories), default=0)
    rotate = (not horizontal) and longest * 7.0 > slot - 6
    for position, category in enumerate(categories):
        if horizontal:
            y = pad_t + slot * (position + 0.5) + 4
            parts.append(f'<text x="{pad_l - 12}" y="{y:.1f}" font-size="12.5" text-anchor="end" fill="{text}">{esc(category)}</text>')
        elif rotate:
            x = pad_l + slot * (position + 0.5)
            parts.append(f'<text x="{x:.1f}" y="{pad_b + 16}" font-size="12" text-anchor="end" fill="{text}" '
                         f'transform="rotate(-30 {x:.1f} {pad_b + 16})">{esc(category)}</text>')
        else:
            x = pad_l + slot * (position + 0.5)
            parts.append(f'<text x="{x:.1f}" y="{pad_b + 20}" font-size="12.5" text-anchor="middle" fill="{text}">{esc(category)}</text>')
    axis = vy(0) if not horizontal else None
    if not horizontal and low < 0 < high:
        parts.append(f'<line x1="{pad_l}" y1="{axis:.1f}" x2="{width - pad_r}" y2="{axis:.1f}" stroke="{muted}" stroke-width="1.2"></line>')
    if horizontal:
        zero = vx(0)
        parts.append(f'<line x1="{zero:.1f}" y1="{pad_t}" x2="{zero:.1f}" y2="{pad_b}" stroke="{muted}" stroke-width="1.2"></line>')
    target = spec.get("target")
    if target is not None:  # a reference line: plan, budget, last year
        value = float(target["value"]) if isinstance(target, dict) else float(target)
        label = target.get("label", "Target") if isinstance(target, dict) else "Target"
        if horizontal:
            x = vx(value)
            parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_b}" stroke="{colors["accent2"]}" stroke-width="1.4" stroke-dasharray="6 4"></line>')
            parts.append(f'<text x="{x + 6:.1f}" y="{pad_t + 12}" font-size="12" fill="{colors["accent2"]}">{esc(label)} {esc(labels(value))}</text>')
        else:
            y = vy(value)
            parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="{colors["accent2"]}" stroke-width="1.4" stroke-dasharray="6 4"></line>')
            parts.append(f'<text x="{width - pad_r:.1f}" y="{y - 6:.1f}" font-size="12" text-anchor="end" fill="{colors["accent2"]}">{esc(label)} {esc(labels(value))}</text>')
    for note in spec.get("annotations") or []:  # a short note with a leader line, where the storyboard asks for one
        category = str(note.get("category", ""))
        if category not in categories:
            continue
        index = categories.index(category)
        name = note.get("series")
        values = next((v for n, v in series if n == name), series[0][1])
        value = values[index]
        if horizontal:
            x, y = vx(value), pad_t + slot * (index + 0.5)
            tx, ty, anchor = min(width - pad_r - 6, x + 34), max(pad_t + 12, y - 26), "start"
        else:
            x, y = pad_l + slot * (index + 0.5), vy(value)
            if y - pad_t > 46:  # room above the column
                tx, ty, anchor = x, y - 34, "middle"
            else:  # a tall column: the note goes beside it, into the empty space
                right = index < len(categories) - 1
                tx = x + slot * 0.55 + 8 if right else x - slot * 0.55 - 8
                ty, anchor = y + 26, "start" if right else "end"
        parts.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{tx:.1f}" y2="{ty - 4:.1f}" stroke="{muted}" stroke-width="1"></line>')
        parts.append(f'<text x="{tx + (4 if anchor == "start" else -4 if anchor == "end" else 0):.1f}" y="{ty:.1f}" font-size="12.5" '
                     f'text-anchor="{anchor}" fill="{text}">{esc(note.get("text", ""))}</text>')
    if show_legend and len(series) > 1:
        parts.append(legend_svg([name for name, _ in series], [palette[i % len(palette)] for i in range(len(series))], width, height - 8, muted))
    parts.append("</svg>")
    return "".join(parts)


def legend_svg(names: list[str], colors: list[str], width: float, y: float, muted: str) -> str:
    widths = [len(name) * 7.2 + 30 for name in names]
    total = sum(widths)
    x = max(0.0, (width - total) / 2)
    out = []
    for name, color, w in zip(names, colors, widths):
        out.append(f'<rect x="{x:.1f}" y="{y - 10:.1f}" width="11" height="11" rx="2" fill="{color}"></rect>')
        out.append(f'<text x="{x + 17:.1f}" y="{y:.1f}" font-size="12.5" fill="{muted}">{esc(name)}</text>')
        x += w
    return "".join(out)


# --------------------------------------------------------------------------- slide rendering
class Renderer:
    def __init__(self, board: Storyboard, theme: dict, base_dir: Path | None = None, link_images: bool = False):
        self.board = board
        self.theme = theme
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]
        self.sizes = theme["sizes"]
        self.layout = theme["layout"]
        self.base = Path(base_dir or (board.path.parent if board.path else "."))
        self.link_images = link_images
        self.rtl = board.rtl
        self.source_label = str(board.meta.get("source_label") or "Source:")
        self.scrim = str(board.meta.get("backdrop_scrim") or "dark").lower()  # dark, light or none
        self.text_side = str(board.meta.get("backdrop_text") or "left").lower()  # which half of the backdrop the title sits on
        labels = str(board.meta.get("chapter_label") or "auto").lower()
        self.chapters = labels != "off" and any(s.kind == "section" for s in board.slides)
        self.warnings: list[str] = []
        self.section_count = 0
        self.ornament = str(self.layout.get("ornament", "none"))
        bar = str(self.layout.get("accent_bar", "none"))
        self.left = 57.6 + (24 if bar == "left" else 0)
        self.right = 57.6
        self.content_w = SLIDE_W - self.left - self.right

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        sys.stderr.write(f"warning: {message}\n")

    # helpers ---------------------------------------------------------------
    def image_src(self, item: Item) -> str:
        path = item.path if item.path and item.path.is_absolute() else self.base / (item.text or "")
        if item.path and item.path.exists():
            path = item.path
        if not path.is_file():
            self.warn(f"picture not found: {path}")
            return ""
        if self.link_images:
            try:
                return esc(path.relative_to(self.base).as_posix())
            except ValueError:
                return esc(path.as_posix())
        return data_uri(path)

    def picture(self, item: Item, mode: str = "contain", extra: str = "") -> str:
        src = self.image_src(item)
        if not src:
            return f'<div class="missing">picture not found: {esc(item.text)}</div>'
        alt = esc(item.alt or "")
        return f'<img class="pic {mode}" src="{src}" alt="{alt}" {extra}>'

    def chart(self, item: Item, width: int, height: int) -> str:
        return f'<div class="chart">{svg_chart(item.chart, self.colors, self.fonts, width, height)}</div>'

    def visual(self, item: Item, width: int, height: int) -> str:
        return self.chart(item, width, height) if item.kind == "chart" else self.picture(item)

    def body_html(self, items: list[Item], size: float | None = None) -> str:
        size = size or self.sizes["body"]
        out = []
        for item in items:
            if item.kind in ("bullet", "number"):
                out.append(f'<li class="lv{min(item.level, 3)}{" num" if item.kind == "number" else ""}">{rich(item.text)}</li>')
            elif item.kind == "heading":
                out.append(f'<p class="sub-heading">{rich(item.text)}</p>')
            elif item.kind == "code":
                out.append(f'<pre>{esc(item.text)}</pre>')
            else:
                out.append(f'<p>{rich(item.text)}</p>')
        body = "".join(out)
        return f'<ul class="body-list" style="--fs:{size * PT:.1f}px">{body}</ul>' if body else ""

    def furniture(self, spec: Slide, number: int) -> str:
        footer = str(self.board.meta.get("footer") or self.board.title)
        mark = str(self.board.meta.get("confidentiality") or "")
        left = f'{esc(footer)}<span class="mark">{esc(mark)}</span>' if mark else esc(footer)
        page = appendix_label(spec) or str(number)
        parts = [f'<div class="foot"><span>{left}</span><span class="pageno">{page}</span></div>']
        bar = str(self.layout.get("accent_bar", "none"))
        if bar in ("top", "left"):
            parts.append(f'<div class="bar-{bar}"></div>')
        parts.append(self.ornament_html("content", number))
        return "".join(parts)

    def ornament_html(self, where: str, number: int = 0, over_picture: bool = False) -> str:
        """Decoration that gives the concept its character; mirrors deck_build.py.

        Over a picture only the HUD brackets stay: hatching, grids and shapes are textures for a plain canvas.
        """
        kind = self.ornament
        if over_picture and kind != "hud":
            return ""
        if kind == "grid":
            if where == "cover":
                return ""
            columns = "".join(f'<i style="left:{self.left + self.content_w * f:.0f}px"></i>' for f in (0.25, 0.5, 0.75))
            return f'<div class="orn grid">{columns}</div>'
        if kind == "hud":
            brackets = "".join(f'<i class="{c}"></i>' for c in ("tl", "tr", "bl", "br"))
            tag = f'<span class="hud-tag">{number:02d}</span>' if where == "content" and number else ""
            return f'<div class="orn hud">{brackets}{tag}</div>'
        if kind == "hatch":
            return '<div class="orn hatch"></div>'
        if kind == "shapes":
            if where == "cover":
                return ('<div class="orn shapes cover">'
                        '<i class="circle"></i><i class="tri"></i><i class="quarter"></i><i class="bar"></i></div>')
            return '<div class="orn shapes"><i class="dot"></i><i class="edge"></i></div>'
        return ""

    def source_takeaway(self, spec: Slide) -> tuple[str, float]:
        """Footnote and callout markup plus the height they take from the content area."""
        used = 0.0
        parts = []
        if spec.source:
            parts.append(f'<div class="src">{esc(self.source_label)} {rich(spec.source)}</div>')
            used += 38
        if spec.takeaway:
            parts.append(f'<div class="callout">{rich(spec.takeaway)}</div>')
            used += 91 + 29
        return "".join(parts), used

    # layouts ---------------------------------------------------------------
    def layouts(self) -> dict:
        """Layout name to the method that renders it. An explicit table, no dynamic lookup."""
        return {
            "title": self.l_title, "section": self.l_section, "bullets": self.l_bullets, "two-column": self.l_two_column,
            "big-number": self.l_big_number, "quote": self.l_quote, "statement": self.l_statement, "image": self.l_image,
            "chart": self.l_chart, "timeline": self.l_timeline, "table": self.l_table, "closing": self.l_closing,
            "split": self.l_split, "icons": self.l_icons,
        }

    def render(self, spec: Slide, number: int) -> str:
        layout = spec.effective_layout()
        inner = self.layouts()[layout](spec, number)
        classes = f"slide L-{layout} orn-{self.ornament}" + (" active" if number == 1 else "")
        notes = "\n".join(spec.notes)
        direction = ' dir="rtl"' if self.rtl else ""
        return (f'<section class="{classes}" data-slide="{number}" data-layout="{layout}"{direction} '
                f'aria-label="{esc(spec.title or layout)}">{inner}'
                f'<div class="notes" hidden>{esc(notes)}</div></section>')

    def own_backdrop(self, spec: Slide, default_key: str) -> str | None:
        """A picture line on the slide itself wins; otherwise the front matter default for this kind of slide."""
        own = next((i for i in spec.items if i.kind == "image"), None)
        if own is not None:
            return own.text
        value = self.board.meta.get(default_key)
        return str(value) if value else None

    def cover(self, spec: Slide, number: int, closing: bool = False) -> str:
        style = str(self.layout.get("title_style", "plain"))
        backdrop = self.own_backdrop(spec, "backdrop")
        if backdrop and style == "split":
            style = "plain"  # no accent panel to sit in when a picture fills the slide
        side = " text-right" if backdrop and self.text_side == "right" else ""
        parts = [f'<div class="cover t-{style}{" on-photo" if backdrop and self.scrim == "dark" else ""}{side}">']
        if backdrop:
            item = Item(kind="image", text=str(backdrop), path=self.base / str(backdrop))
            parts.append(self.picture(item, "cover", 'aria-hidden="true"'))
            if self.scrim != "none":
                parts.append(f'<div class="scrim {self.scrim}"></div>')
        elif style == "split":
            parts.append('<div class="tpanel"></div>')
        elif style == "band":
            parts.append('<div class="band"></div>')
        elif style == "full":
            parts.append('<div class="fullbg"></div>')
        else:
            parts.append('<div class="rule"></div>')
        parts.append(self.ornament_html("cover", over_picture=bool(backdrop)))
        lines = [rich(line) for line in spec.subtitle]
        if closing:
            lines += [rich(i.text) for i in spec.items if i.kind in ("bullet", "number", "para")]
        meta = [esc(self.board.meta[k]) for k in ("author", "date") if self.board.meta.get(k)] if not closing else []
        subtitle = "".join(f"<p>{line}</p>" for line in lines) + "".join(f'<p class="meta">{m}</p>' for m in meta)
        parts.append(f'<h1 class="title"><span>{rich(spec.title_markup or spec.title)}</span></h1>')
        if subtitle:
            parts.append(f'<div class="subtitle">{subtitle}</div>')
        parts.append("</div>")
        return "".join(parts)

    def l_title(self, spec: Slide, number: int) -> str:
        return self.cover(spec, number)

    def l_closing(self, spec: Slide, number: int) -> str:
        return self.cover(spec, number, closing=True)

    def l_section(self, spec: Slide, number: int) -> str:
        self.section_count += 1
        style = str(self.layout.get("section_style", "accent"))
        backdrop = self.own_backdrop(spec, "section_backdrop")
        # a picture keeps its colours: the text sits on a solid panel over the left third, not under a grey veil
        panel = bool(backdrop)
        side = " text-right" if backdrop and self.text_side == "right" and not panel else ""
        classes = f"section s-{style}{side}" + (" panelled" if panel else "")
        parts = [f'<div class="{classes}">']
        if backdrop:
            item = Item(kind="image", text=str(backdrop), path=self.base / str(backdrop))
            parts.append(self.picture(item, "cover", 'aria-hidden="true"'))
            parts.append('<div class="sec-panel"></div>')
        elif style == "band":
            parts.append('<div class="sideband"></div>')
        elif style == "plain":
            parts.append('<div class="rule"></div>')
        parts.append(self.ornament_html("cover", over_picture=bool(backdrop)))
        subtitle = "".join(f"<p>{rich(t)}</p>" for t in spec.subtitle + [i.text for i in spec.items if i.kind in ("bullet", "number", "para")])
        parts.append(f'<div class="label">{self.section_count:02d}</div><h2 class="title"><span>{rich(spec.title_markup or spec.title)}</span></h2>')
        if subtitle:
            parts.append(f'<div class="subtitle">{subtitle}</div>')
        parts.append("</div>")
        return "".join(parts)

    def eyebrow(self, spec: Slide, small: bool = False) -> str:
        """The chapter above the headline: where the audience is in the argument."""
        if small or not self.chapters or not spec.chapter or spec.kind != "content":
            return ""
        label = appendix_label(spec)
        number = f"{spec.chapter_number:02d}" if not label else "A"
        return f'<div class="eyebrow"><b>{number}</b>{esc(spec.chapter)}</div>'

    def headline(self, spec: Slide, number: int, small: bool = False) -> str:
        if spec.title and len(spec.title) > 70:
            self.warn(f"slide {number}: the headline has {len(spec.title)} characters; keep it under 70")
        cls = "hl kicker" if small else "hl"
        eyebrow = self.eyebrow(spec, small)
        cls += " under-eyebrow" if eyebrow else ""
        return eyebrow + f'<h2 class="{cls}"><span>{rich(spec.title_markup or spec.title)}</span></h2>'

    def l_bullets(self, spec: Slide, number: int) -> str:
        extras, used = self.source_takeaway(spec)
        text_items, visuals = spec.text_items, spec.visuals
        if len(spec.bullets) > 6:
            self.warn(f"slide {number} '{spec.title}': {len(spec.bullets)} bullets; six is the ceiling")
        body = self.body_html(text_items)
        height = int(SLIDE_H - 163 - 56 - used)
        if visuals:
            column = int(self.content_w * 0.58 - 29)
            rendered = "".join(self.visual(v, column, int(height / len(visuals)) - 12) for v in visuals)
            content = f'<div class="split"><div class="col-text">{body}</div><div class="col-vis">{rendered}</div></div>'
        else:
            content = body
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px">{content}</div>' + extras)

    def l_split(self, spec: Slide, number: int) -> str:
        """Picture on one half of the slide, headline and text on the other."""
        images = [i for i in spec.items if i.kind == "image"]
        if not images:
            self.warn(f"slide {number} '{spec.title}': split layout needs a picture; drawn as bullets")
            return self.l_bullets(spec, number)
        text_items = [i for i in spec.text_items]
        extras, used = self.source_takeaway(spec)
        height = int(SLIDE_H - 163 - 56 - used)
        body = self.body_html(text_items) if text_items else ""
        return (self.furniture(spec, number) +
                f'<div class="split-img">{self.picture(images[0], "cover")}</div>' +
                self.headline(spec, number).replace('class="hl"', 'class="hl half"') +
                f'<div class="content half" style="--content-h:{height}px">{body}</div>' +
                extras.replace('class="src"', 'class="src half"').replace('class="callout"', 'class="callout half"'))

    def icon_markup(self, name: str) -> str:
        path = ICONS_DIR / f"{name}.svg"
        if not path.is_file():
            self.warn(f"icon '{name}' is not in the bundled set (deck-images/assets/icons); a dot is drawn instead")
            return '<span class="icon-dot"></span>'
        body = path.read_text(encoding="utf-8").strip()
        inner = body[body.index(">") + 1:body.rindex("</svg>")]
        return f'<svg viewBox="0 0 32 32" class="icon" role="img" aria-label="{esc(name)}" fill="currentColor">{inner}</svg>'

    def l_icons(self, spec: Slide, number: int) -> str:
        """Three or four tiles, each an icon with a label and a line of detail."""
        tiles = [i for i in spec.items if i.kind in ("bullet", "number")]
        if not tiles:
            self.warn(f"slide {number} '{spec.title}': icons layout needs '- icon | label | detail' items")
            return self.l_bullets(spec, number)
        if len(tiles) > 4:
            self.warn(f"slide {number} '{spec.title}': {len(tiles)} icons; four fit")
            tiles = tiles[:4]
        extras, used = self.source_takeaway(spec)
        height = int(SLIDE_H - 163 - 56 - used)
        cards = "cards" if self.layout.get("cards", True) else "plain"
        blocks = []
        for tile in tiles:
            fields = tile.fields
            icon = fields[0]
            label = fields[1] if len(fields) > 1 else ""
            detail = fields[2] if len(fields) > 2 else ""
            blocks.append(f'<div class="tile icon-tile">{self.icon_markup(icon)}'
                          f'{f"<div class=label>{rich(label)}</div>" if label else ""}'
                          f'{f"<div class=detail>{rich(detail)}</div>" if detail else ""}</div>')
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px"><div class="tiles {cards} n{len(tiles)}">{"".join(blocks)}</div></div>' + extras)

    def l_two_column(self, spec: Slide, number: int) -> str:
        extras, used = self.source_takeaway(spec)
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
            self.warn(f"slide {number} '{spec.title}': two-column layout without '###' column titles")
            return self.l_bullets(spec, number)
        if len(columns) > 3:
            self.warn(f"slide {number} '{spec.title}': {len(columns)} columns; only three are drawn")
            columns = columns[:3]
        height = int(SLIDE_H - 163 - 56 - used)
        cards = "cards" if self.layout.get("cards", True) else "plain"
        cell = int((self.content_w - 29 * (len(columns) - 1)) / len(columns))
        blocks = []
        for index, (title, items) in enumerate(columns):
            visuals = [i for i in items if i.kind in ("image", "chart")]
            body = self.body_html([i for i in items if i.kind in ("bullet", "number", "para", "code")], self.sizes["body"] - 2)
            visual = "".join(self.visual(v, cell - 40, 200) for v in visuals)
            blocks.append(f'<div class="col c{index}">{visual}<p class="col-title">{rich(title)}</p>{body}</div>')
        lead_html = f'<div class="lead">{self.body_html(lead)}</div>' if lead else ""
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px">{lead_html}<div class="columns {cards}">{"".join(blocks)}</div></div>' + extras)

    def l_big_number(self, spec: Slide, number: int) -> str:
        extras, used = self.source_takeaway(spec)
        tiles = [i for i in spec.items if i.kind in ("bullet", "number")]
        lead = [i for i in spec.items if i.kind in ("para", "code")]
        if not tiles:
            self.warn(f"slide {number} '{spec.title}': big-number layout needs '- value | label | detail' items")
            return self.l_bullets(spec, number)
        if len(tiles) > 4:
            self.warn(f"slide {number} '{spec.title}': {len(tiles)} numbers; four fit")
            tiles = tiles[:4]
        scale = {1: 1.2, 2: 1.0, 3: 0.86, 4: 0.74}[len(tiles)]
        cards = "cards" if self.layout.get("cards", True) else "plain"
        blocks = []
        for tile in tiles:
            fields = tile.fields
            value = fields[0]
            label = fields[1] if len(fields) > 1 else ""
            detail = fields[2] if len(fields) > 2 else ""
            blocks.append(f'<div class="tile"><div class="value" style="--fs:{self.sizes["number"] * scale * PT:.0f}px">{rich(value)}</div>'
                          f'{f"<div class=label>{rich(label)}</div>" if label else ""}'
                          f'{f"<div class=detail>{rich(detail)}</div>" if detail else ""}</div>')
        height = int(SLIDE_H - 163 - 56 - used)
        lead_html = f'<div class="lead">{self.body_html(lead)}</div>' if lead else ""
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px">{lead_html}<div class="tiles {cards} n{len(tiles)}">{"".join(blocks)}</div></div>' + extras)

    def l_quote(self, spec: Slide, number: int) -> str:
        extras, used = self.source_takeaway(spec)
        quote = spec.quote or " ".join(i.text for i in spec.items if i.kind == "para")
        if not quote:
            self.warn(f"slide {number} '{spec.title}': quote layout without a '>' line")
        attribution = spec.attribution
        height = int(SLIDE_H - 163 - 56 - used)
        return (self.furniture(spec, number) + self.headline(spec, number, small=True) +
                f'<div class="content quote-wrap" style="--content-h:{height}px"><div class="mark">&ldquo;</div>'
                f'<div><blockquote>{rich(quote)}</blockquote>'
                f'{f"<p class=attrib>&mdash; {rich(attribution)}</p>" if attribution else ""}</div></div>' + extras)

    def l_statement(self, spec: Slide, number: int) -> str:
        extras, used = self.source_takeaway(spec)
        paras = [i.text for i in spec.items if i.kind in ("para", "bullet", "number")]
        body = "".join(f"<p>{rich(p)}</p>" for p in paras)
        return (self.furniture(spec, number) +
                f'<div class="statement"><div class="rule"></div><p class="big">{rich(spec.title_markup or spec.title)}</p>'
                f'{f"<div class=sub>{body}</div>" if body else ""}</div>' + extras)

    def l_image(self, spec: Slide, number: int) -> str:
        images = [i for i in spec.items if i.kind == "image"]
        captions = [i.text for i in spec.items if i.kind in ("para", "bullet", "number")]
        if not images:
            self.warn(f"slide {number} '{spec.title}': image layout without a picture")
            return self.l_bullets(spec, number)
        if len(images) == 1 and not captions:
            source = f'<div class="src on-image">{esc(self.source_label)} {rich(spec.source)}</div>' if spec.source else ""
            if spec.takeaway:
                self.warn(f"slide {number} '{spec.title}': takeaway is not drawn on a full-bleed image slide")
            return (f'<div class="bleed">{self.picture(images[0], "cover")}<div class="scrim bottom"></div>'
                    f'<h2 class="hl on-image"><span>{rich(spec.title_markup or spec.title)}</span></h2>{source}'
                    f'<div class="foot on-image"><span></span><span class="pageno">{number}</span></div></div>')
        extras, used = self.source_takeaway(spec)
        height = int(SLIDE_H - 163 - 56 - used - (46 if captions else 0))
        rows = 1 if len(images) <= 3 else 2
        grid = "".join(self.picture(i) for i in images)
        caption = f'<div class="caption">{"".join(f"<p>{rich(c)}</p>" for c in captions)}</div>' if captions else ""
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px"><div class="pic-grid r{rows} n{len(images)}">{grid}</div></div>'
                + caption + extras)

    def l_chart(self, spec: Slide, number: int) -> str:
        visuals = spec.visuals
        if not visuals:
            self.warn(f"slide {number} '{spec.title}': chart layout without a chart block or picture")
            return self.l_bullets(spec, number)
        if spec.text_items:
            return self.l_bullets(spec, number)
        extras, used = self.source_takeaway(spec)
        height = int(SLIDE_H - 163 - 56 - used)
        width = int((self.content_w - 29 * (len(visuals) - 1)) / len(visuals))
        rendered = "".join(self.visual(v, width, height - 8) for v in visuals)
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px"><div class="vis-row">{rendered}</div></div>' + extras)

    def l_timeline(self, spec: Slide, number: int) -> str:
        steps = [i for i in spec.items if i.kind in ("bullet", "number")]
        if not steps:
            self.warn(f"slide {number} '{spec.title}': timeline layout needs '- label | detail' items")
            return self.l_bullets(spec, number)
        if len(steps) > 6:
            self.warn(f"slide {number} '{spec.title}': {len(steps)} steps; six fit")
            steps = steps[:6]
        extras, used = self.source_takeaway(spec)
        height = int(SLIDE_H - 163 - 56 - used)
        blocks = []
        for index, step in enumerate(steps):
            fields = step.fields
            marker = fields[0] if len(fields) >= 3 else str(index + 1)
            label = fields[1] if len(fields) >= 3 else fields[0]
            detail = fields[2] if len(fields) >= 3 else (fields[1] if len(fields) == 2 else "")
            blocks.append(f'<div class="step"><div class="dot">{esc(marker)}</div><p class="label">{rich(label)}</p>'
                          f'{f"<p class=detail>{rich(detail)}</p>" if detail else ""}</div>')
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px"><div class="timeline n{len(steps)}"><div class="track"></div>{"".join(blocks)}</div></div>' + extras)

    def l_table(self, spec: Slide, number: int) -> str:
        rows = [r.cells for r in spec.rows]
        if not rows:
            self.warn(f"slide {number} '{spec.title}': table layout without '| a | b |' rows")
            return self.l_bullets(spec, number)
        columns = max(len(r) for r in rows)
        rows = [r + [""] * (columns - len(r)) for r in rows]
        if len(rows) > 9 or columns > 6:
            self.warn(f"slide {number} '{spec.title}': {len(rows)} rows x {columns} columns; keep tables under nine by six")
        size = 14 if len(rows) <= 5 else 13 if len(rows) <= 7 else 12  # table text sits below the body size; it is read, not declaimed
        num = numeric_columns(rows)
        head = "".join(f'<th class="{"num" if num[i] else ""}">{rich(c)}</th>' for i, c in enumerate(rows[0]))
        body = "".join("<tr>" + "".join(
            f'<td class="{"num" if num[i] else ""}">{rich(cell)}</td>' for i, cell in enumerate(row)) + "</tr>"
            for row in rows[1:])
        extras, used = self.source_takeaway(spec)
        height = int(SLIDE_H - 163 - 56 - used)
        return (self.furniture(spec, number) + self.headline(spec, number) +
                f'<div class="content" style="--content-h:{height}px"><table style="--fs:{size * PT:.0f}px">'
                f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>' + extras)


# --------------------------------------------------------------------------- CSS
def theme_vars(theme: dict) -> str:
    colors, fonts, sizes, layout = theme["colors"], theme["fonts"], theme["sizes"], theme["layout"]
    bar = str(layout.get("accent_bar", "none"))
    left = 57.6 + (24 if bar == "left" else 0)
    return "".join([
        f"--bg:{colors['bg']};--surface:{colors['surface']};--text:{colors['text']};--muted:{colors['muted']};",
        f"--accent:{colors['accent']};--accent2:{colors['accent2']};--line:{colors['line']};--on-accent:{colors['on_accent']};",
        "".join(f"--c{i + 1}:{c};" for i, c in enumerate(colors["chart"])),
        f"--f-head:{fonts.get('css_heading', fonts['heading'])};--f-body:{fonts.get('css_body', fonts['body'])};",
        f"--f-mono:{fonts.get('css_mono', fonts.get('mono', 'monospace'))};",
        f"--f-num:{fonts.get('css_number') or (fonts['number'] + ', ' + fonts.get('css_heading', 'sans-serif') if fonts.get('number') else fonts.get('css_heading', fonts['heading']))};",
        f"--s-title:{sizes['title'] * PT:.1f}px;--s-hl:{sizes['headline'] * PT:.1f}px;--s-body:{sizes['body'] * PT:.1f}px;",
        f"--s-small:{sizes['small'] * PT:.1f}px;--s-num:{sizes['number'] * PT:.1f}px;",
        f"--radius:{float(layout.get('corner', 0)) * 60:.0f}px;--bullet:'{layout.get('bullet', '•')}';",
        f"--left:{left:.0f}px;--right:57.6px;--tile-bg:{colors['surface'] if layout.get('cards', True) else 'transparent'};",
        f"--align:{'right' if str(layout.get('align')) == 'right' else ('center' if layout.get('align') == 'center' else 'left')};",
    ])


SLIDE_CSS = """
.slide{position:relative;width:1280px;height:720px;overflow:hidden;background:var(--bg);color:var(--text);
  font-family:var(--f-body);text-align:var(--align);box-sizing:border-box}
.slide *{box-sizing:border-box}
.slide h1,.slide h2,.slide p,.slide ul,.slide li,.slide blockquote,.slide pre,.slide table{margin:0;padding:0;font-weight:400}
.slide b{font-weight:700}
.slide .hl,.slide .title,.statement .big,.quote-wrap blockquote,.callout,.tiles .label,.timeline .label{text-wrap:balance}
.body-list,.lead,.caption,.subtitle,td,.tiles .detail,.timeline .detail{text-wrap:pretty}
.nobr{white-space:nowrap}
.slide .hl{position:absolute;left:var(--left);right:var(--right);top:43px;min-height:66px;display:flex;align-items:center;
  font-family:var(--f-head);font-weight:700;font-size:var(--s-hl);line-height:1.12}
.slide .hl.under-eyebrow{top:66px;min-height:74px}
.slide .eyebrow{position:absolute;left:var(--left);right:var(--right);top:38px;font-size:calc(var(--s-small) + 1px);
  letter-spacing:1.6px;text-transform:uppercase;color:var(--muted);font-weight:600;display:flex;gap:10px;align-items:center}
.slide .eyebrow b{color:var(--accent);font-weight:700;letter-spacing:1px}
.slide .foot .mark{margin-left:14px;padding:1px 7px;border:1px solid var(--line);border-radius:3px;letter-spacing:.6px;text-transform:uppercase;font-size:.85em}
.slide .hl b,.t-plain .title b,.t-band .title b,.statement .big b{color:var(--accent)}
.slide .hl.kicker{font-size:calc(var(--s-small) + 2px);letter-spacing:1.4px;text-transform:uppercase;color:var(--muted);
  font-weight:600;top:46px;min-height:0}
.slide .content{position:absolute;left:var(--left);right:var(--right);top:163px;height:var(--content-h,470px)}
.slide .foot{position:absolute;left:var(--left);right:var(--right);bottom:14px;display:flex;justify-content:space-between;
  font-size:var(--s-small);color:var(--muted);letter-spacing:.2px}
.slide .src{position:absolute;left:var(--left);right:var(--right);bottom:44px;font-size:var(--s-small);color:var(--muted)}
.slide .callout{position:absolute;left:var(--left);right:var(--right);bottom:81px;min-height:66px;display:flex;align-items:center;
  padding:12px 20px;background:var(--surface);border-left:6px solid var(--accent);border-radius:var(--radius);
  font-family:var(--f-head);font-weight:700;font-size:var(--s-body)}
.slide[dir=rtl] .callout{border-left:0;border-right:6px solid var(--accent)}
.slide .bar-top{position:absolute;left:0;right:0;top:0;height:11px;background:var(--accent)}
.slide .bar-left{position:absolute;left:0;top:0;bottom:0;width:13px;background:var(--accent)}
.body-list{font-size:var(--fs,var(--s-body));line-height:1.42;list-style:none;height:100%}
.body-list li{position:relative;padding-left:1.7em;margin-bottom:.55em}
.body-list li.lv1{margin-left:1.5em;font-size:.9em}.body-list li.lv2{margin-left:3em;font-size:.82em}
.body-list li.lv3{margin-left:4.5em;font-size:.78em}
.body-list li::before{content:var(--bullet);position:absolute;left:0;top:0;width:1.2em;text-align:center;color:var(--accent);font-weight:700;font-size:.9em;line-height:inherit}
.slide[dir=rtl] .body-list li{padding-left:0;padding-right:1.7em}
.slide[dir=rtl] .body-list li::before{left:auto;right:0}
.body-list li.num{counter-increment:n}.body-list li.num::before{content:counter(n) "."}
.body-list{counter-reset:n}
.body-list p{margin-bottom:14px}
.body-list .sub-heading{font-family:var(--f-head);font-weight:700;color:var(--accent);margin-bottom:6px}
.body-list pre{font-family:var(--f-mono);font-size:.85em;white-space:pre-wrap;margin-bottom:10px}
.split{display:flex;gap:29px;height:100%}
.split .col-text{flex:0 0 40%}.split .col-vis{flex:1;display:flex;flex-direction:column;gap:12px;justify-content:center;min-width:0}
.vis-row{display:flex;gap:29px;height:100%;align-items:center;justify-content:center}
.chart{display:flex;align-items:center;justify-content:center;max-width:100%}
.chart svg{max-width:100%;height:auto}
img.pic{display:block;max-width:100%;max-height:100%;object-fit:contain;margin:auto}
img.pic.cover{width:100%;height:100%;object-fit:cover;margin:0}
.missing{border:2px dashed var(--line);color:var(--muted);padding:20px;font-size:14px;text-align:center;border-radius:var(--radius)}
.pic-grid{display:grid;gap:16px;height:100%;align-items:center}
.pic-grid.n2{grid-template-columns:1fr 1fr}.pic-grid.n3{grid-template-columns:repeat(3,1fr)}
.pic-grid.n4{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
.pic-grid img{max-height:100%;width:100%;object-fit:contain}
.caption{position:absolute;left:var(--left);right:var(--right);bottom:70px;font-size:calc(var(--s-body) - 4px);color:var(--muted)}
.columns{display:flex;gap:29px;height:100%}
.columns .col{flex:1;min-width:0;padding:0;overflow:hidden}
.columns .col img.pic{max-height:88px;width:auto;margin:0 0 14px}
.columns .col .chart{margin-bottom:12px}
.split .col-vis img.pic{max-height:100%}
.columns.cards .col{background:var(--surface);border-radius:var(--radius);padding:20px 22px;border-top:8px solid var(--c1)}
.columns.cards .col.c1{border-top-color:var(--c2)}.columns.cards .col.c2{border-top-color:var(--c3)}
.columns .col-title{font-family:var(--f-head);font-weight:700;font-size:calc(var(--s-body) + 2px);color:var(--accent);margin-bottom:12px}
.lead{margin-bottom:16px;font-size:var(--s-body)}
.tiles{display:flex;gap:24px;height:100%}
.tiles .tile{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:18px}
.tiles.cards .tile{background:var(--tile-bg);border-radius:var(--radius)}
.split-img{position:absolute;left:50%;top:0;right:0;bottom:0;overflow:hidden}
.split-img img.pic{width:100%;height:100%;object-fit:cover;margin:0}
.slide .hl.half,.slide .content.half,.slide .src.half,.slide .callout.half{right:calc(50% + 40px)}
.slide[dir=rtl] .split-img{left:0;right:50%}
.slide[dir=rtl] .hl.half,.slide[dir=rtl] .content.half,.slide[dir=rtl] .src.half,.slide[dir=rtl] .callout.half{right:var(--right);left:calc(50% + 40px)}
.tiles .icon-tile{justify-content:flex-start;padding-top:36px}
.tiles .icon{width:72px;height:72px;color:var(--accent);margin-bottom:22px}
.tiles .icon-dot{width:24px;height:24px;border-radius:50%;background:var(--accent);margin-bottom:26px}
.tiles .value{font-family:var(--f-num,var(--f-head));font-weight:700;font-size:var(--fs);color:var(--accent);line-height:1}
.tiles .label{font-weight:700;font-size:calc(var(--s-body) - 1px);margin-top:14px}
.tiles .detail{font-size:calc(var(--s-body) - 6px);color:var(--muted);margin-top:5px}
.quote-wrap{display:flex;gap:20px;align-items:center}
.quote-wrap .mark{font-family:var(--f-head);font-size:150px;line-height:.8;color:var(--accent);align-self:flex-start}
.quote-wrap blockquote{font-family:var(--f-head);font-size:var(--s-hl);line-height:1.3;font-style:italic}
.quote-wrap .attrib{margin-top:24px;color:var(--muted);font-size:var(--s-body)}
.statement{position:absolute;left:var(--left);right:var(--right);top:110px;bottom:70px;display:flex;flex-direction:column;justify-content:center}
.statement .rule{width:115px;height:9px;background:var(--accent);margin-bottom:26px;margin-right:auto}
.statement .big{font-family:var(--f-head);font-weight:700;font-size:var(--s-title);line-height:1.14}
.statement .sub{margin-top:22px;font-size:calc(var(--s-body) + 2px);color:var(--muted);line-height:1.45;max-width:80%}
.timeline{position:relative;height:100%;display:flex;gap:8px;padding-top:24px}
.timeline .track{position:absolute;left:8%;right:8%;top:55px;height:2px;background:var(--line)}
.timeline .step{flex:1;text-align:center;position:relative;z-index:1}
.timeline .dot{width:62px;height:62px;border-radius:50%;background:var(--accent);color:var(--on-accent);display:flex;
  align-items:center;justify-content:center;margin:0 auto 16px;font-family:var(--f-head);font-weight:700;font-size:15px}
.timeline .label{font-family:var(--f-head);font-weight:700;font-size:calc(var(--s-body) - 2px)}
.timeline .detail{font-size:calc(var(--s-body) - 6px);color:var(--muted);margin-top:5px}
table{width:100%;border-collapse:collapse;font-size:var(--fs,18px);line-height:1.3}
th{background:var(--accent);color:var(--on-accent);text-align:var(--align);padding:10px 16px;font-weight:700;vertical-align:bottom}
td{padding:9px 16px;border-bottom:1px solid var(--line);vertical-align:middle}
tbody tr:nth-child(even){background:var(--surface)}
th.num,td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums lining-nums;width:1%}
th:first-child,td:first-child{padding-left:12px}
th:last-child,td:last-child{padding-right:12px}
.slide[dir=rtl] th.num,.slide[dir=rtl] td.num{text-align:left}
.cover,.section{position:absolute;inset:0}
.cover .title,.section .title{position:absolute;left:var(--left);right:var(--right);font-family:var(--f-head);font-weight:700;
  font-size:var(--s-title);line-height:1.08}
.cover .subtitle,.section .subtitle{position:absolute;left:var(--left);right:var(--right);font-size:calc(var(--s-body) + 2px);
  line-height:1.4;color:var(--muted)}
.cover .subtitle p,.section .subtitle p{margin-bottom:12px}
.cover .subtitle .meta{font-size:calc(var(--s-body) - 4px);opacity:.9}
.cover .rule{position:absolute;left:var(--left);top:150px;width:115px;height:9px;background:var(--accent)}
.t-plain .title{top:186px;height:132px;display:flex;align-items:flex-end}
.t-plain .subtitle{top:342px}
.t-split .tpanel{position:absolute;left:0;top:0;bottom:0;width:44%;background:var(--accent)}
.t-split .title{left:57.6px;right:auto;width:calc(44% - 115px);top:134px;height:400px;display:flex;align-items:center;color:var(--on-accent)}
.t-split .subtitle{left:calc(44% + 57.6px);right:57.6px;top:134px;height:400px;display:flex;flex-direction:column;justify-content:center}
.t-band .band{position:absolute;left:0;right:0;bottom:0;height:36%;background:var(--accent)}
.t-band .title{top:96px;height:230px;display:flex;align-items:flex-end}
.t-band .subtitle{top:490px;color:var(--on-accent)}
.t-full{background:var(--accent)}
.t-full .fullbg{position:absolute;inset:0;background:var(--accent)}
.t-full .title{top:186px;height:132px;display:flex;align-items:flex-end;color:var(--on-accent)}
.t-full .subtitle{top:342px;color:var(--on-accent);opacity:.92}
.cover:has(img.cover):not(.text-right) .title,.cover:has(img.cover):not(.text-right) .subtitle,
.section:has(img.cover):not(.text-right) .title,.section:has(img.cover):not(.text-right) .subtitle{right:50%}
.cover.text-right .title,.cover.text-right .subtitle,.section.text-right .title,.section.text-right .subtitle,.section.text-right .label{left:52%;right:var(--right);width:auto}
.cover.text-right .rule,.section.text-right .rule{left:52%}
.cover .scrim,.section .scrim{position:absolute;inset:0}
.cover .scrim.dark,.section .scrim.dark{background:rgba(0,0,0,.45)}
.cover .scrim.light,.section .scrim.light{background:rgba(255,255,255,.55)}
.cover:has(img.cover) .title,.section:has(img.cover) .title{color:var(--text)}
.cover:has(img.cover) .subtitle,.section:has(img.cover) .subtitle{color:var(--text)}
.slide .cover.on-photo .title,.slide .section.on-photo .title,.slide .cover.on-photo .label,.slide .section.on-photo .label{color:#fff}
.slide .cover.on-photo .subtitle,.slide .section.on-photo .subtitle,.slide .cover.on-photo .subtitle .meta{color:#EDEDED}
.section.panelled .sec-panel{position:absolute;left:0;top:0;bottom:0;width:34%;background:var(--accent)}
.slide[dir=rtl] .section.panelled .sec-panel{left:auto;right:0}
.slide .section.panelled .label{left:40px;top:96px;color:var(--on-accent)}
.slide .section.panelled .title{left:40px;right:auto;width:calc(34% - 80px);top:150px;height:auto;color:var(--on-accent);font-size:calc(var(--s-title) - 6px)}
.slide .section.panelled .subtitle{left:40px;right:auto;width:calc(34% - 80px);top:auto;bottom:70px;color:var(--on-accent);opacity:.92;font-size:var(--s-body)}
.slide[dir=rtl] .section.panelled .label,.slide[dir=rtl] .section.panelled .title,.slide[dir=rtl] .section.panelled .subtitle{left:auto;right:40px}
.section .label{position:absolute;left:var(--left);top:120px;font-family:var(--f-head);font-weight:700;font-size:36px;color:var(--accent)}
.section .title{top:276px;height:122px;display:flex;align-items:flex-start}
.section .subtitle{top:470px}
.s-accent{background:var(--accent)}
.s-accent .label,.s-accent .title{color:var(--on-accent)}.s-accent .subtitle{color:var(--on-accent);opacity:.9}
.s-band .sideband{position:absolute;left:0;top:0;bottom:0;width:210px;background:var(--accent)}
.s-band .label,.s-band .title,.s-band .subtitle{left:268px}
.slide[dir=rtl] .t-split .tpanel{left:auto;right:0}
.slide[dir=rtl] .t-split .title{left:auto;right:57.6px}
.slide[dir=rtl] .t-split .subtitle{left:57.6px;right:calc(44% + 57.6px)}
.slide[dir=rtl] .s-band .sideband{left:auto;right:0}
.slide[dir=rtl] .s-band .label,.slide[dir=rtl] .s-band .title,.slide[dir=rtl] .s-band .subtitle{left:57.6px;right:268px}
.slide[dir=rtl] .bar-left{left:auto;right:0}
.slide[dir=rtl] .cover .rule,.slide[dir=rtl] .s-plain .rule,.slide[dir=rtl] .statement .rule{left:auto;right:var(--left);margin-left:auto}
.slide[dir=rtl] .section .label{left:auto;right:var(--left)}
.slide[dir=rtl] .orn.hud .hud-tag{right:auto;left:26px}
.slide[dir=rtl] .orn.shapes .dot{right:auto;left:70px}
.slide[dir=rtl].orn-shapes .hl{right:var(--right);left:calc(var(--left) + 86px)}
.slide[dir=rtl] .cover:has(.orn.shapes) .title,.slide[dir=rtl] .cover:has(.orn.shapes) .subtitle{right:var(--right);left:42%}
.slide[dir=rtl] .section:has(.orn.shapes) .title,.slide[dir=rtl] .section:has(.orn.shapes) .subtitle,.slide[dir=rtl] .section:has(.orn.shapes) .label{right:var(--left);left:42%}
.slide[dir=rtl] .quote-wrap .mark{order:2}
.slide[dir=rtl] .statement .rule{margin-right:0;margin-left:auto}
.s-plain .rule{position:absolute;left:var(--left);top:250px;width:115px;height:9px;background:var(--accent)}
.bleed{position:absolute;inset:0}
.bleed .scrim.bottom{position:absolute;left:0;right:0;bottom:0;height:250px;background:linear-gradient(to top,rgba(0,0,0,.78),rgba(0,0,0,0))}
.bleed .hl.on-image{top:auto;bottom:96px;color:#fff}
.bleed .src.on-image{color:#DDD;bottom:60px}
.bleed .foot.on-image{color:#DDD}
/* ornaments */
.orn{position:absolute;inset:0;pointer-events:none}
.orn.grid i{position:absolute;top:0;bottom:0;width:1px;background:var(--line);opacity:.7}
.orn.hud{--hud:var(--accent)}
.orn.hud i{position:absolute;width:26px;height:26px;border:2px solid var(--hud);opacity:.85}
.orn.hud i.tl{left:16px;top:16px;border-right:0;border-bottom:0}
.orn.hud i.tr{right:16px;top:16px;border-left:0;border-bottom:0}
.orn.hud i.bl{left:16px;bottom:16px;border-right:0;border-top:0}
.orn.hud i.br{right:16px;bottom:16px;border-left:0;border-top:0}
.orn.hud .hud-tag{position:absolute;right:26px;top:22px;font-family:var(--f-mono);font-size:13px;letter-spacing:2px;color:var(--accent);opacity:.9}
.slide.orn-hud .hl{right:calc(var(--right) + 54px)}
.slide:has(.orn.hud){background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);
  background-size:64px 64px;background-position:-1px -1px}
.orn.hatch{background:repeating-linear-gradient(135deg,transparent 0 22px,color-mix(in srgb,var(--line) 55%,transparent) 22px 23px);opacity:.5}
.orn.shapes i{position:absolute}
.orn.shapes .dot{right:70px;top:52px;width:54px;height:54px;border-radius:50%;background:var(--accent2);opacity:.9}
.orn.shapes .edge{left:0;right:0;bottom:0;height:10px;background:var(--accent)}
.slide.orn-shapes .hl{right:calc(var(--right) + 86px)}
.slide.orn-shapes .foot{bottom:22px}
.slide.orn-shapes .src{bottom:52px}
.cover:has(.orn.shapes) .title,.cover:has(.orn.shapes) .subtitle{right:42%}
.section:has(.orn.shapes) .title,.section:has(.orn.shapes) .subtitle,.section:has(.orn.shapes) .label{right:42%}
.orn.shapes.cover .circle{right:96px;top:96px;width:300px;height:300px;border-radius:50%;background:var(--accent2);opacity:.92}
.orn.shapes.cover .tri{right:300px;bottom:110px;width:0;height:0;border-bottom:190px solid var(--c3,var(--accent));border-left:110px solid transparent;border-right:110px solid transparent;opacity:.95}
.orn.shapes.cover .quarter{left:0;bottom:0;width:190px;height:190px;background:var(--accent);border-top-right-radius:190px}
.orn.shapes.cover .bar{right:0;top:0;width:64px;height:100%;background:var(--c4,var(--muted));opacity:.35}
"""

APP_CSS = """
:root{color-scheme:light dark}
html,body{margin:0;padding:0;background:#0D0F12;font-family:'Segoe UI',-apple-system,Arial,sans-serif}
body.static{background:#8A8F98}
.stage{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;overflow:hidden}
.stage .slide{position:absolute;transform-origin:center center;box-shadow:0 12px 60px rgba(0,0,0,.45)}
.stage .slide{display:none}
.stage .slide.active{display:block}
body.static .stage{position:static;display:block}
body.static .slide{position:relative;display:block;margin:0 auto 18px;box-shadow:0 3px 14px rgba(0,0,0,.3)}
.bar{position:fixed;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,.14);z-index:5}
.bar i{display:block;height:100%;background:#fff;opacity:.85;transition:width .18s ease}
.hud-bar{position:fixed;right:16px;bottom:14px;color:rgba(255,255,255,.75);font-size:13px;z-index:6;
  font-variant-numeric:tabular-nums;display:flex;gap:14px;align-items:center}
.hud-bar button{background:rgba(255,255,255,.1);color:#fff;border:0;border-radius:6px;padding:5px 9px;font-size:12px;cursor:pointer}
.hud-bar button:hover{background:rgba(255,255,255,.2)}
.panel{position:fixed;left:0;right:0;bottom:0;max-height:38vh;overflow:auto;background:#15181D;color:#E6EAF0;
  border-top:1px solid #2A2F38;padding:16px 22px 22px;z-index:7;font-size:15px;line-height:1.5}
.panel h3{margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:1.2px;color:#8C95A3}
.overview{position:fixed;inset:0;background:#0D0F12;overflow:auto;z-index:8;padding:26px;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;align-content:start}
.overview .cell{position:relative;width:300px;height:169px;overflow:hidden;cursor:pointer;border:2px solid transparent;background:#fff}
.overview .cell.here{border-color:#fff}
.overview .cell .slide{display:block;transform:scale(.2344);transform-origin:top left;box-shadow:none}
.overview .cell span{position:absolute;left:6px;bottom:4px;background:rgba(0,0,0,.65);color:#fff;font-size:11px;padding:1px 6px;border-radius:4px}
.help{position:fixed;inset:0;background:rgba(8,10,13,.86);z-index:9;display:flex;align-items:center;justify-content:center}
.help div{background:#15181D;color:#E6EAF0;padding:26px 32px;border-radius:12px;font-size:15px;line-height:1.9;min-width:330px}
.help b{display:inline-block;min-width:96px;color:#fff;font-family:ui-monospace,Consolas,monospace}
[hidden]{display:none!important}
@media print{
  html,body{background:#fff}
  .bar,.hud-bar,.panel,.overview,.help{display:none!important}
  .stage{position:static;display:block}
  .slide{display:block!important;position:relative!important;margin:0!important;box-shadow:none!important;
    transform:none!important;page-break-after:always;break-after:page}
  .slide:last-child{page-break-after:auto;break-after:auto}
  @page{size:1280px 720px;margin:0}
}
"""

APP_JS = """
(function(){
  var slides=[].slice.call(document.querySelectorAll('.slide'));
  var stage=document.querySelector('.stage'), total=slides.length, current=0;
  var fill=document.querySelector('.bar i'), counter=document.getElementById('counter');
  var panel=document.getElementById('notes'), overview=document.getElementById('overview'), help=document.getElementById('help');
  var builds=document.body.dataset.builds==='1', step=0;
  function fit(){
    if(document.body.classList.contains('static'))return;
    var scale=Math.min(window.innerWidth/1280, window.innerHeight/720);
    slides.forEach(function(s){s.style.transform='scale('+scale+')';});
  }
  function steps(slide){return builds?[].slice.call(slide.querySelectorAll('.body-list > li, .tiles .tile, .timeline .step')):[];}
  function paint(){
    slides.forEach(function(s,i){s.classList.toggle('active', i===current);});
    var items=steps(slides[current]);
    items.forEach(function(el,i){el.style.visibility = (i<=step||!builds)?'visible':'hidden';});
    if(fill)fill.style.width=((current+1)/total*100)+'%';
    if(counter)counter.textContent=(current+1)+' / '+total;
    if(panel&&!panel.hidden)showNotes();
    if(overview&&!overview.hidden)markOverview();
    if(location.hash!=='#'+(current+1))history.replaceState(null,'','#'+(current+1));
  }
  function showNotes(){
    // Notes are text: build the panel with text nodes, never by re-parsing them as HTML.
    var n=slides[current].querySelector('.notes'), text=(n&&n.textContent.trim())?n.textContent:'';
    panel.textContent='';
    var h=document.createElement('h3');h.textContent='Speaker notes \\u2014 slide '+(current+1);panel.appendChild(h);
    if(!text){var i=document.createElement('i');i.textContent='no notes for this slide';panel.appendChild(i);return;}
    text.split('\\n').forEach(function(line,k){if(k)panel.appendChild(document.createElement('br'));panel.appendChild(document.createTextNode(line));});
  }
  function markOverview(){
    [].slice.call(overview.children).forEach(function(c,i){c.classList.toggle('here',i===current);});
  }
  function go(index,resetStep){
    current=Math.max(0,Math.min(total-1,index));
    step=(resetStep===false)?step:0;
    paint();
  }
  function next(){
    var items=steps(slides[current]);
    if(builds&&step<items.length-1){step++;paint();return;}
    if(current<total-1)go(current+1);
  }
  function prev(){
    if(builds&&step>0){step--;paint();return;}
    if(current>0){go(current-1);var items=steps(slides[current]);step=builds?Math.max(0,items.length-1):0;paint();}
  }
  function buildOverview(){
    if(overview.children.length)return;
    slides.forEach(function(s,i){
      var cell=document.createElement('div');cell.className='cell';
      var clone=s.cloneNode(true);clone.classList.add('active');clone.style.transform='scale(0.2344)';
      cell.appendChild(clone);
      var tag=document.createElement('span');tag.textContent=i+1;cell.appendChild(tag);
      cell.addEventListener('click',function(){overview.hidden=true;go(i);});
      overview.appendChild(cell);
    });
  }
  document.addEventListener('keydown',function(e){
    if(e.metaKey||e.ctrlKey||e.altKey)return;
    var k=e.key;
    if(k==='ArrowRight'||k==='PageDown'||k===' '||k==='Enter'){e.preventDefault();next();}
    else if(k==='ArrowLeft'||k==='PageUp'||k==='Backspace'){e.preventDefault();prev();}
    else if(k==='Home'){go(0);} else if(k==='End'){go(total-1);}
    else if(k==='n'||k==='N'){panel.hidden=!panel.hidden;if(!panel.hidden)showNotes();}
    else if(k==='o'||k==='O'){buildOverview();overview.hidden=!overview.hidden;markOverview();}
    else if(k==='f'||k==='F'){if(document.fullscreenElement){document.exitFullscreen();}else{document.documentElement.requestFullscreen();}}
    else if(k==='p'||k==='P'){
      var wasStatic=document.body.classList.toggle('static');fit();window.scrollTo(0,0);
      if(wasStatic){setTimeout(function(){window.print();},120);}
    }
    else if(k==='?'||k==='/'){help.hidden=!help.hidden;}
    else if(k==='Escape'){overview.hidden=true;help.hidden=true;panel.hidden=true;}
    else if(/^[0-9]$/.test(k)){go(parseInt(k,10)-1);}
  });
  stage.addEventListener('click',function(e){
    if(document.body.classList.contains('static'))return;
    if(e.clientX < window.innerWidth*0.25){prev();}else{next();}
  });
  var startX=null;
  stage.addEventListener('touchstart',function(e){startX=e.touches[0].clientX;},{passive:true});
  stage.addEventListener('touchend',function(e){
    if(startX===null)return;var dx=e.changedTouches[0].clientX-startX;startX=null;
    if(Math.abs(dx)>45){dx<0?next():prev();}
  },{passive:true});
  window.addEventListener('resize',fit);
  window.addEventListener('hashchange',function(){var n=parseInt(location.hash.slice(1),10);if(n)go(n-1);});
  [].slice.call(document.querySelectorAll('[data-action]')).forEach(function(b){
    b.addEventListener('click',function(){
      var a=b.dataset.action;
      if(a==='next')next();else if(a==='prev')prev();
      else if(a==='notes'){panel.hidden=!panel.hidden;if(!panel.hidden)showNotes();}
      else if(a==='overview'){buildOverview();overview.hidden=!overview.hidden;markOverview();}
      else if(a==='print'){document.body.classList.add('static');fit();window.print();}
      else if(a==='help'){help.hidden=!help.hidden;}
    });
  });
  fit();
  var start=parseInt(location.hash.slice(1),10);
  go(start?start-1:0);
})();
"""

FIT_JS = """
(function(){
  function shrink(el,floor){
    var size=parseFloat(getComputedStyle(el).fontSize);
    var guard=0;
    while(el.scrollHeight>el.clientHeight+1 && size>floor && guard++<40){
      size-=1; el.style.fontSize=size+'px';
    }
  }
  function run(){
    [].slice.call(document.querySelectorAll('.body-list')).forEach(function(el){shrink(el,15*1.333);});
    [].slice.call(document.querySelectorAll('.slide .hl')).forEach(function(el){
      var size=parseFloat(getComputedStyle(el).fontSize), guard=0;
      while(el.scrollHeight>el.clientHeight+1 && size>22*1.333 && guard++<30){size-=1;el.style.fontSize=size+'px';}
    });
  }
  if(document.readyState==='complete'){run();}else{window.addEventListener('load',run);}
})();
"""


# --------------------------------------------------------------------------- document
def render_slides(board: Storyboard, theme: dict, base_dir: Path | None = None, link_images: bool = False) -> tuple[list[str], Renderer]:
    renderer = Renderer(board, theme, base_dir, link_images)
    slides = [renderer.render(spec, number) for number, spec in enumerate(board.slides, start=1)]
    return slides, renderer


def render_document(board: Storyboard, theme: dict, mode: str = "interactive", base_dir: Path | None = None,
                    link_images: bool = False, builds: bool = False) -> tuple[str, Renderer]:
    slides, renderer = render_slides(board, theme, base_dir, link_images)
    rtl = ' dir="rtl"' if board.rtl else ""
    body_class = "static" if mode == "static" else ""
    chrome = ""
    scripts = f"<script>{FIT_JS}</script>"
    if mode != "static":
        chrome = (
            '<div class="bar"><i></i></div>'
            '<div class="hud-bar"><span id="counter"></span>'
            '<button data-action="prev">&larr;</button><button data-action="next">&rarr;</button>'
            '<button data-action="overview">Overview (O)</button><button data-action="notes">Notes (N)</button>'
            '<button data-action="print">PDF (P)</button><button data-action="help">?</button></div>'
            '<div class="panel" id="notes" hidden></div>'
            '<div class="overview" id="overview" hidden></div>'
            '<div class="help" id="help" hidden><div>'
            '<b>&rarr; space</b> next slide<br><b>&larr;</b> back<br><b>O</b> overview<br><b>N</b> speaker notes<br>'
            '<b>F</b> fullscreen<br><b>P</b> print view and print dialog<br><b>1-9</b> jump to a slide<br><b>Esc</b> close</div></div>')
        scripts += f"<script>{APP_JS}</script>"
    return (f"""<!DOCTYPE html>
<html lang="{esc(board.meta.get('language', 'en'))}"{rtl}><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(board.title)}</title>
<style>{APP_CSS}
.slide{{{theme_vars(theme)}}}
{SLIDE_CSS}</style></head>
<body class="{body_class}" data-builds="{1 if builds else 0}">
<div class="stage">
{chr(10).join(slides)}
</div>
{chrome}
{scripts}
</body></html>
""", renderer)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("storyboard", help="storyboard Markdown file")
    parser.add_argument("-o", "--output", required=True, help="output .html path")
    parser.add_argument("--theme", help="theme.json from deck-style (default: the built-in Boardroom Blue theme)")
    parser.add_argument("--mode", choices=["interactive", "static"], default="interactive",
                        help="interactive: one slide at a time with navigation; static: slides stacked as pages for printing to PDF")
    parser.add_argument("--builds", action="store_true", help="interactive only: reveal bullets, tiles and timeline steps one at a time")
    parser.add_argument("--link-images", action="store_true", help="keep pictures as relative links instead of embedding them (smaller file, needs the images folder)")
    parser.add_argument("--strict", action="store_true", help="exit 1 without writing when there are warnings")
    args = parser.parse_args(argv)
    try:
        board = load_storyboard(Path(args.storyboard))
        theme = load_theme(args.theme)
        page, renderer = render_document(board, theme, args.mode, Path(args.storyboard).parent, args.link_images, args.builds)
    except (StoryboardError, HtmlError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    if renderer.warnings and args.strict:
        sys.stderr.write(f"{len(renderer.warnings)} warning(s) and --strict: nothing written\n")
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    size = output.stat().st_size / 1024
    print(f"wrote {output}: {len(board.slides)} slides, {args.mode} mode, theme '{theme.get('name', theme.get('id'))}', "
          f"{size:.0f} KB, {len(renderer.warnings)} warning(s)")
    if args.mode == "interactive":
        print("open it in a browser: arrows or space to move, O overview, N notes, F fullscreen, P print view, ? help")
    else:
        print("open it in a browser and print to PDF: one slide per page, no margins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
