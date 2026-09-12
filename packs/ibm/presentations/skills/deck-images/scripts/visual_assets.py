#!/usr/bin/env python3
"""Pictures a deck needs but nobody has to search for: backdrops, treated photos, placeholders.

    visual_assets.py backdrop --theme theme.json --pattern mesh -o images/backdrop.png
    visual_assets.py treat photo.jpg --theme theme.json --crop 16:9 --duotone -o images/04-team.jpg
    visual_assets.py placeholder --theme theme.json --text "Photo: the onboarding team at work" -o images/06-team.png

backdrop   an abstract on-theme background for title and section slides
           (patterns: gradient, mesh, bands, dots, grid, waves, contours, noise)
treat      one consistent treatment for the user's own photo: crop to a ratio,
           resize, duotone or tint in the theme colours, grayscale, a dark
           scrim at the bottom for a headline, rounded corners
placeholder a labelled stand-in with the intended picture's description and
           size, so the deck can be reviewed before the real image arrives
icon       one of 92 bundled Carbon icons (Apache-2.0, assets/icons) as SVG in a
           theme colour; `--list` and `--find <word>` search the set
pattern    one of 12 bundled tileable patterns (assets/patterns) tiled across a
           slide-sized SVG in a theme colour, for textures behind sections
library    the 26 bundled pictures (assets/library: abstract vector, black and
           white photo art, dark technology) plus the user's own folder; `--find`
           by keyword, `--for-theme` picks the pack for a theme, `--pick` gives
           the path for treat

Pillow only, no network, writes only the output path.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write("Pillow is not installed. Run with: uv run --with pillow python visual_assets.py ...\n")
    sys.exit(1)

DEFAULT_COLORS = {"bg": "#FFFFFF", "surface": "#F2F4F8", "text": "#161616", "muted": "#525252", "accent": "#0F62FE", "accent2": "#002D9C", "line": "#C6C6C6"}
PATTERNS = ("gradient", "mesh", "bands", "dots", "grid", "waves", "contours", "noise", "shapes", "arcs")
FONT_CANDIDATES = (
    "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
    "C:\\Windows\\Fonts\\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


class AssetError(Exception):
    pass


# --------------------------------------------------------------------------- colours and fonts
def parse_hex(value: str) -> tuple[int, int, int]:
    text = str(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        raise AssetError(f"colour '{value}' is not a hex colour like #0F62FE")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def mix(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(x * (1 - amount) + y * amount))) for x, y in zip(a, b))


def load_colors(path: str | None) -> dict[str, tuple[int, int, int]]:
    colors = dict(DEFAULT_COLORS)
    if path:
        file = Path(path)
        if not file.is_file():
            raise AssetError(f"theme not found: {file}")
        theme = json.loads(file.read_text(encoding="utf-8"))
        colors.update({k: v for k, v in theme.get("colors", {}).items() if k in colors})
    return {k: parse_hex(v) for k, v in colors.items()}


def load_font(size: int):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow before 10.1
        return ImageFont.load_default()


def parse_size(text: str) -> tuple[int, int]:
    try:
        width, height = text.lower().split("x")
        return int(width), int(height)
    except ValueError:
        raise AssetError(f"size '{text}' must look like 1920x1080") from None


def parse_ratio(text: str) -> float:
    try:
        if ":" in text:
            a, b = text.split(":")
            return float(a) / float(b)
        return float(text)
    except (ValueError, ZeroDivisionError):
        raise AssetError(f"ratio '{text}' must look like 16:9 or 1.5") from None


# --------------------------------------------------------------------------- backdrops
def gradient_image(size: tuple[int, int], start: tuple[int, int, int], end: tuple[int, int, int], angle: float = 35.0) -> Image.Image:
    width, height = size
    base = Image.new("RGB", (width, height))
    pixels = base.load()
    rad = math.radians(angle)
    dx, dy = math.cos(rad), math.sin(rad)
    span = abs(width * dx) + abs(height * dy)
    for y in range(height):
        for x in range(width):
            t = ((x * dx + y * dy) + (width * max(0.0, -dx)) + (height * max(0.0, -dy))) / span
            pixels[x, y] = mix(start, end, max(0.0, min(1.0, t)))
    return base


def backdrop(colors: dict, pattern: str, size: tuple[int, int], seed: int, dark: bool | None) -> Image.Image:
    rng = random.Random(seed)
    bg, accent, accent2, surface = colors["bg"], colors["accent"], colors["accent2"], colors["surface"]
    is_dark = dark if dark is not None else sum(bg) < 3 * 110
    small = (size[0] // 4, size[1] // 4)  # draw at quarter size, upscale with smoothing: fast and soft
    if pattern == "gradient":
        image = gradient_image(small, mix(bg, accent, 0.3 if is_dark else 0.12), mix(bg, accent2, 0.55 if is_dark else 0.35))
    elif pattern == "mesh":
        image = Image.new("RGB", small, mix(bg, accent, 0.06) if not is_dark else mix(bg, accent, 0.12))
        blobs = Image.new("RGB", small, image.getpixel((0, 0)))
        draw = ImageDraw.Draw(blobs)
        for index in range(7):
            color = [accent, accent2, mix(accent, accent2, 0.5)][index % 3]
            radius = rng.randint(small[0] // 6, small[0] // 3)
            cx, cy = rng.randint(int(small[0] * 0.4), int(small[0] * 1.1)), rng.randint(0, small[1])
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=mix(image.getpixel((0, 0)), color, 0.55 if is_dark else 0.4))
        image = blobs.filter(ImageFilter.GaussianBlur(radius=small[0] // 9))
    elif pattern == "bands":
        image = Image.new("RGB", small, bg if not is_dark else mix(bg, accent, 0.08))
        draw = ImageDraw.Draw(image)
        x = -small[1]
        step = small[0] // 9
        band = 0
        while x < small[0] + small[1]:
            width = step * rng.choice((1, 1, 2))
            color = [accent, accent2, mix(bg, accent, 0.25), surface][band % 4]
            draw.polygon([(x, 0), (x + width, 0), (x + width - small[1] * 0.6, small[1]), (x - small[1] * 0.6, small[1])], fill=mix(image.getpixel((0, 0)), color, 0.85))
            x += width + step
            band += 1
    elif pattern == "dots":
        image = Image.new("RGB", small, bg if not is_dark else mix(bg, accent, 0.05))
        draw = ImageDraw.Draw(image)
        gap = max(6, small[0] // 40)
        for y in range(gap, small[1], gap):
            for x in range(gap, small[0], gap):
                t = (x / small[0]) * 0.8 + (y / small[1]) * 0.2
                radius = max(1, int(gap * 0.36 * (0.2 + t)))
                draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=mix(image.getpixel((0, 0)), accent, 0.25 + 0.55 * t))
    elif pattern == "grid":
        image = Image.new("RGB", small, bg if not is_dark else mix(bg, accent, 0.05))
        draw = ImageDraw.Draw(image)
        gap = max(8, small[0] // 24)
        line = mix(image.getpixel((0, 0)), accent, 0.35 if is_dark else 0.18)
        for x in range(0, small[0], gap):
            draw.line([(x, 0), (x, small[1])], fill=line, width=1)
        for y in range(0, small[1], gap):
            draw.line([(0, y), (small[0], y)], fill=line, width=1)
        for _ in range(9):
            x = rng.randrange(int(small[0] * 0.45), small[0], gap)
            y = rng.randrange(0, small[1], gap)
            draw.rectangle([x, y, x + gap, y + gap], fill=mix(image.getpixel((0, 0)), rng.choice((accent, accent2)), 0.7))
    elif pattern == "waves":
        image = Image.new("RGB", small, bg if not is_dark else mix(bg, accent2, 0.15))
        draw = ImageDraw.Draw(image)
        for index in range(6):
            points = []
            base_y = small[1] * (0.45 + index * 0.1)
            for x in range(0, small[0] + 1, 4):
                y = base_y + math.sin(x / small[0] * math.pi * 2 + index * 0.9) * small[1] * 0.06 + math.sin(x / small[0] * math.pi * 5 + index) * small[1] * 0.02
                points.append((x, y))
            points += [(small[0], small[1]), (0, small[1])]
            draw.polygon(points, fill=mix(image.getpixel((0, 0)), [accent, accent2][index % 2], 0.18 + index * 0.13))
    elif pattern == "contours":
        image = Image.new("RGB", small, bg if not is_dark else mix(bg, accent, 0.06))
        draw = ImageDraw.Draw(image)
        cx, cy = small[0] * rng.uniform(0.3, 0.7), small[1] * rng.uniform(0.3, 0.7)
        for radius in range(small[0] // 14, int(small[0] * 1.1), max(4, small[0] // 24)):
            wobble = [(cx + math.cos(a / 40 * math.pi * 2) * radius * (1 + 0.08 * math.sin(a / 40 * math.pi * 6 + radius / 30)),
                       cy + math.sin(a / 40 * math.pi * 2) * radius * (0.72 + 0.06 * math.cos(a / 40 * math.pi * 4))) for a in range(40)]
            draw.polygon(wobble, outline=mix(image.getpixel((0, 0)), accent, 0.55 if is_dark else 0.3))
    elif pattern == "noise":
        image = Image.new("RGB", small, mix(bg, accent, 0.18 if is_dark else 0.08))
        pixels = image.load()
        base = image.getpixel((0, 0))
        for y in range(small[1]):
            for x in range(small[0]):
                pixels[x, y] = mix(base, accent2, rng.random() * 0.12)
        image = image.filter(ImageFilter.GaussianBlur(radius=1))
    elif pattern in ("shapes", "arcs"):
        image = Image.new("RGB", small, bg if not is_dark else mix(bg, accent, 0.05))
        draw = ImageDraw.Draw(image)
        if pattern == "shapes":
            r = int(small[1] * 0.24)
            draw.ellipse([int(small[0] * 0.74) - r, int(small[1] * 0.34) - r, int(small[0] * 0.74) + r, int(small[1] * 0.34) + r], fill=accent2)
            draw.polygon([(small[0] * 0.52, small[1] * 0.86), (small[0] * 0.64, small[1] * 0.58), (small[0] * 0.76, small[1] * 0.86)], fill=accent)
            q = int(small[1] * 0.56)
            draw.pieslice([-q, small[1] - q, q, small[1] + q], 270, 360, fill=accent)
        else:
            for index in range(7):
                radius = int(small[1] * (0.25 + index * 0.13))
                cx, cy = int(small[0] * 0.86), int(small[1] * 0.12)
                draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=accent if index % 2 == 0 else accent2, width=max(1, index // 2 + 1))
    else:
        raise AssetError(f"unknown pattern '{pattern}'; use one of {', '.join(PATTERNS)}")
    return image.resize(size, Image.LANCZOS)


# --------------------------------------------------------------------------- bundled assets
ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICONS = ASSETS / "icons"
TILES = ASSETS / "patterns"
COLOUR_ROLES = ("accent", "accent2", "text", "muted", "line", "bg")


def load_manifest() -> dict:
    path = ICONS / "manifest.json"
    if not path.is_file():
        raise AssetError(f"icon manifest not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def find_icons(query: str, manifest: dict) -> list[tuple[str, str]]:
    query = query.strip().lower()
    hits = []
    for name, info in manifest["icons"].items():
        haystack = f"{name} {info['carbon']} {info['keywords']}".lower()
        if not query or query in haystack:
            hits.append((name, info["keywords"]))
    return hits


def icon_svg(name: str, colour: str, size: int) -> str:
    path = ICONS / f"{name}.svg"
    if not path.is_file():
        raise AssetError(f"icon '{name}' is not in the set; run `visual_assets.py icon --list` or search with `--find <word>`")
    body = path.read_text(encoding="utf-8").strip()
    inner = body[body.index(">") + 1:body.rindex("</svg>")]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" height="{size}" '
            f'role="img" aria-label="{esc_attr(name.replace("-", " "))}" fill="{colour}">{inner}</svg>\n')


def esc_attr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def pattern_svg(name: str, colour: str, size: tuple[int, int], strength: float, scale: float, bg: str | None) -> str:
    path = TILES / f"{name}.svg"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in TILES.glob("*.svg")))
        raise AssetError(f"pattern tile '{name}' not found; available: {available}")
    tile = path.read_text(encoding="utf-8").strip()
    view = tile.split('viewBox="0 0 ', 1)[1].split('"', 1)[0]
    unit = float(view.split()[0]) * max(0.2, scale)
    inner = tile[tile.index(">") + 1:tile.rindex("</svg>")]
    width, height = size
    ground = f'<rect width="{width}" height="{height}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="presentation" aria-hidden="true"><defs>'
            f'<pattern id="t" width="{unit:g}" height="{unit:g}" patternUnits="userSpaceOnUse">'
            f'<g transform="scale({max(0.2, scale):g})" color="{colour}" opacity="{max(0.02, min(1.0, strength)):g}">{inner}</g>'
            f'</pattern></defs>{ground}<rect width="{width}" height="{height}" fill="url(#t)"/></svg>\n')


# --------------------------------------------------------------------------- the picture library
BUNDLED_LIBRARY = ASSETS / "library"  # ships with the pack: 26 pictures in three packs, see manifest.json
PERSONAL_LIBRARY = Path.home() / "Pictures" / "deck-library"  # the user's own additions, same layout
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def library_roots(extra: str | None) -> list[Path]:
    roots = [BUNDLED_LIBRARY, Path(extra).expanduser() if extra else PERSONAL_LIBRARY]
    return [r for r in roots if r.is_dir()]


def library_manifest() -> dict:
    path = BUNDLED_LIBRARY / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"packs": {}, "pictures": {}}


def library_pictures(extra: str | None) -> list[tuple[str, str, Path, str]]:
    """(pack, name, path, keywords) for every picture, bundled first, then the personal folder."""
    manifest = library_manifest()
    found = []
    for root in library_roots(extra):
        for pack in sorted(p for p in root.iterdir() if p.is_dir()):
            for f in sorted(x for x in pack.iterdir() if x.suffix.lower() in IMAGE_SUFFIXES):
                keywords = manifest["pictures"].get(f"{pack.name}/{f.stem}", "")
                found.append((pack.name, f.stem, f, keywords))
    return found


def library_listing(extra: str | None, query: str | None) -> list[str]:
    pictures = library_pictures(extra)
    if not pictures:
        return ["no pictures found: the bundled library is missing from assets/library and there is no personal folder"]
    query = (query or "").lower()
    words = [w for w in query.replace(",", " ").split() if w]
    lines = []
    manifest = library_manifest()
    current = None
    shown = 0
    for pack, name, path, keywords in pictures:
        haystack = f"{pack} {name} {keywords}".lower()
        if words and not any(w in haystack for w in words):
            continue
        if pack != current:
            info = manifest["packs"].get(pack, {})
            suits = ", ".join(info.get("suits", [])) or "any theme"
            lines.append(f"{pack}: {info.get('name', '')} ({info.get('look', 'personal folder')}); suits {suits}")
            current = pack
        lines.append(f"  {name:12} {keywords or '-':50}  {path}")
        shown += 1
    if not shown:
        lines.append(f"nothing matches '{query}'; run without --find to see everything")
    return lines


def library_for_theme(theme_path: str | None, colors: dict) -> list[str]:
    """Which pack fits the theme, and which pictures to use for the title and the sections."""
    manifest = library_manifest()
    theme_id = ""
    if theme_path and Path(theme_path).is_file():
        theme_id = str(json.loads(Path(theme_path).read_text(encoding="utf-8")).get("id", ""))
    is_dark = sum(colors["bg"]) < 3 * 110
    present = {p.name for root in library_roots(None) for p in root.iterdir() if p.is_dir()}  # a pack counts once its pictures exist
    matches = [pack for pack, info in manifest["packs"].items() if theme_id and theme_id in info.get("suits", []) and pack in present]
    planned = [pack for pack, info in manifest["packs"].items() if theme_id and theme_id in info.get("suits", []) and pack not in present]
    if is_dark:
        matches.sort(key=lambda pack: 0 if "dark" in manifest["packs"][pack].get("look", "") else 1)
    wanted = ""
    if theme_path and Path(theme_path).is_file():
        wanted = str(json.loads(Path(theme_path).read_text(encoding="utf-8")).get("pictures", "") or "")
    if wanted == "none":
        return [f"theme {theme_id}: the user chose no pictures; keep the title and sections plain"]
    if wanted.startswith("generated"):
        pattern = wanted.partition(":")[2] or "mesh"
        if pattern not in PATTERNS:
            return [f"theme {theme_id}: '{pattern}' is not a pattern; choose one of {', '.join(PATTERNS)}"]
        return [f"theme {theme_id}: the user chose a generated backdrop, pattern '{pattern}', drawn from the theme colours",
                f"  title:    visual_assets.py backdrop --theme deck/theme.json --pattern {pattern} --seed 7 -o deck/images/title.svg  (and the same with -o deck/images/title.png for the .pptx)",
                f"  sections: visual_assets.py backdrop --theme deck/theme.json --pattern {pattern} --seed 21 --intensity 0.55 -o deck/images/section.svg  (quieter, a different seed, so it is not the title again)",
                "  front matter: backdrop: images/title.svg    section_backdrop: images/section.svg    backdrop_scrim: none    backdrop_text: left",
                "  no licence, no credit, and the colours cannot clash with the theme"]
    if wanted and wanted in manifest["packs"] and wanted in present:
        chosen = wanted
    elif wanted:
        return [f"theme {theme_id}: theme.json asks for pictures '{wanted}', which is not a pack with pictures on disk; ask the user again "
                f"(available: {', '.join(sorted(present))})"]
    elif len(matches) > 1:
        options = "; ".join(f"{pack} {manifest['packs'][pack].get('name', '')} ({manifest['packs'][pack].get('look', '')})" for pack in matches)
        return [f"theme {theme_id or '(default)'}: {len(matches)} picture sets suit it and theme.json does not say which the user wants.",
                f"  ask the user to choose, or run style_preview.py so they see them: {options}; or none, or generated",
                f"  then record it: style_preview.py --choose {theme_id} --pictures <pack> -o deck/theme.json, and run this command again"]
    else:
        chosen = matches[0] if matches else ("pack-c" if is_dark else "pack-a")
    info = manifest["packs"].get(chosen, {})
    covers = info.get("covers", [])
    scrim = {"pack-a": "none", "pack-b": "dark", "pack-c": "none", "pack-d": "dark", "pack-e": "none", "pack-f": "none", "pack-g": "none", "pack-h": "none"}.get(chosen, "dark")
    title_pick = f"{chosen}/{covers[0]}" if covers else "?"
    side = "left"  # every pack is generated with its subject on the right, so the title sits on the left
    title_name = covers[0] if covers else ""
    neutral = [n for n in manifest.get("neutral", {}).get(chosen, []) if n != title_name]  # the title picture is never repeated
    others = [c for c in covers[1:]] + [n for n in neutral if n not in covers]
    lines = [f"theme {theme_id or '(default)'}: use {chosen}, {info.get('name', '')} ({info.get('look', '')})",
             f"  title (used once, nowhere else): {title_pick}",
             f"  sections, one per chapter, in this order: {', '.join(f'{chosen}/{c}' for c in others) or 'none left'}",
             f"  or one neutral picture repeated on every section: {', '.join(f'{chosen}/{n}' for n in neutral) or 'none marked'}",
             f"  content slides: any other picture from the pack, each used once (library --find <words>)",
             f"  front matter: backdrop: images/title.jpg    section_backdrop: images/section.jpg    backdrop_scrim: {scrim}    backdrop_text: {side}",
             f"  a picture line under a '# Chapter' heading gives that section its own backdrop instead of section_backdrop",
             f"  other packs that also suit this theme: {', '.join(matches[1:]) or 'none'}"]
    if planned:
        lines.append(f"  not generated yet but would suit it: {', '.join(planned)} (prompts in references/library.md)")
    return lines


def library_pick(name: str, extra: str | None) -> Path:
    """Resolve 'growth' or 'pack-a/growth' to a file, bundled first."""
    pack, _, stem = name.replace("\\", "/").rpartition("/")
    for p, n, path, _ in library_pictures(extra):
        if n == stem and (not pack or p == pack):
            return path
    raise AssetError(f"no picture named '{name}' in the library; run `visual_assets.py library` to see the names")


# --------------------------------------------------------------------------- svg backdrops
def hexstr(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{c:02X}" for c in rgb)


def svg_backdrop(colors: dict, pattern: str, size: tuple[int, int], seed: int, dark: bool | None, intensity: float) -> str:
    """The same patterns as vector art: a few kilobytes, crisp at any zoom, ideal for the HTML deck."""
    rng = random.Random(seed)
    width, height = size
    bg, accent, accent2, surface = colors["bg"], colors["accent"], colors["accent2"], colors["surface"]
    is_dark = dark if dark is not None else sum(bg) < 3 * 110
    strength = max(0.15, min(1.6, intensity))
    ink = lambda amount: hexstr(mix(bg, accent, min(0.95, amount * strength)))  # noqa: E731
    ink2 = lambda amount: hexstr(mix(bg, accent2, min(0.95, amount * strength)))  # noqa: E731
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
             f'role="presentation" aria-hidden="true">', f'<rect width="{width}" height="{height}" fill="{hexstr(bg)}"/>']

    if pattern == "gradient":
        parts.append(f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                     f'<stop offset="0" stop-color="{ink(0.35 if is_dark else 0.14)}"/>'
                     f'<stop offset="1" stop-color="{ink2(0.6 if is_dark else 0.4)}"/></linearGradient></defs>'
                     f'<rect width="{width}" height="{height}" fill="url(#g)"/>')
    elif pattern == "mesh":
        parts.append('<defs><filter id="soft" x="-30%" y="-30%" width="160%" height="160%">'
                     f'<feGaussianBlur stdDeviation="{width // 9}"/></filter></defs><g filter="url(#soft)">')
        for index in range(7):  # the colour gathers on the right, the left stays quiet for the title
            colour = [ink(0.55), ink2(0.6), hexstr(mix(bg, mix(accent, accent2, 0.5), 0.5 * strength))][index % 3]
            radius = rng.randint(width // 6, width // 3)
            parts.append(f'<circle cx="{rng.randint(int(width * 0.4), int(width * 1.1))}" cy="{rng.randint(0, height)}" r="{radius}" fill="{colour}"/>')
        parts.append("</g>")
    elif pattern == "bands":
        x, step, band = -height, width // 9, 0
        while x < width + height:
            band_w = step * rng.choice((1, 1, 2))
            colour = [ink(0.85), ink2(0.85), ink(0.3), hexstr(mix(bg, surface, 0.9))][band % 4]
            parts.append(f'<polygon points="{x},0 {x + band_w},0 {x + band_w - height * 0.6},{height} {x - height * 0.6},{height}" fill="{colour}"/>')
            x += band_w + step
            band += 1
    elif pattern == "dots":
        gap = max(10, width // 40)
        for y in range(gap, height, gap):
            for x in range(gap, width, gap):
                t = (x / width) * 0.8 + (y / height) * 0.2
                parts.append(f'<circle cx="{x}" cy="{y}" r="{gap * 0.36 * (0.25 + t):.1f}" fill="{ink(0.25 + 0.55 * t)}"/>')
    elif pattern == "grid":
        gap = max(24, width // 24)
        line = ink(0.35 if is_dark else 0.2)
        for x in range(0, width + 1, gap):
            parts.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}" stroke="{line}" stroke-width="1"/>')
        for y in range(0, height + 1, gap):
            parts.append(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" stroke="{line}" stroke-width="1"/>')
        for _ in range(9):  # accent cells stay out of the left third, where the title sits
            x = rng.randrange(int(width * 0.45), width, gap)
            y = rng.randrange(0, height, gap)
            parts.append(f'<rect x="{x}" y="{y}" width="{gap}" height="{gap}" fill="{rng.choice([ink(0.8), ink2(0.8)])}"/>')
    elif pattern == "waves":
        for index in range(6):
            base = height * (0.45 + index * 0.1)
            points = []
            for x in range(0, width + 1, max(4, width // 160)):
                y = base + math.sin(x / width * math.pi * 2 + index * 0.9) * height * 0.06 + math.sin(x / width * math.pi * 5 + index) * height * 0.02
                points.append(f"{x},{y:.1f}")
            parts.append(f'<polygon points="{" ".join(points)} {width},{height} 0,{height}" fill="{[ink(0.2 + index * 0.13), ink2(0.2 + index * 0.13)][index % 2]}"/>')
    elif pattern == "contours":
        cx, cy = width * rng.uniform(0.3, 0.7), height * rng.uniform(0.3, 0.7)
        stroke = ink(0.5 if is_dark else 0.32)
        for radius in range(width // 14, int(width * 1.1), max(16, width // 24)):
            points = []
            for step in range(41):
                angle = step / 40 * math.pi * 2
                rx = radius * (1 + 0.08 * math.sin(angle * 3 + radius / 30))
                ry = radius * (0.72 + 0.06 * math.cos(angle * 2))
                points.append(f"{cx + math.cos(angle) * rx:.1f},{cy + math.sin(angle) * ry:.1f}")
            parts.append(f'<polygon points="{" ".join(points)}" fill="none" stroke="{stroke}" stroke-width="1.4"/>')
    elif pattern == "noise":
        parts.append(f'<defs><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="{seed}"/>'
                     f'<feColorMatrix type="saturate" values="0"/></filter></defs>'
                     f'<rect width="{width}" height="{height}" fill="{ink(0.12)}"/>'
                     f'<rect width="{width}" height="{height}" filter="url(#n)" opacity="{0.10 * strength:.2f}"/>')
    elif pattern == "shapes":
        parts.append(f'<circle cx="{width * 0.74:.0f}" cy="{height * 0.34:.0f}" r="{height * 0.24:.0f}" fill="{ink2(0.9)}"/>')
        parts.append(f'<polygon points="{width * 0.52:.0f},{height * 0.86:.0f} {width * 0.64:.0f},{height * 0.58:.0f} {width * 0.76:.0f},{height * 0.86:.0f}" fill="{ink(0.75)}"/>')
        parts.append(f'<path d="M0,{height} L0,{height * 0.72:.0f} A{height * 0.28:.0f},{height * 0.28:.0f} 0 0 1 {height * 0.28:.0f},{height} Z" fill="{ink(0.9)}"/>')
    elif pattern == "arcs":
        stroke = ink(0.55)
        for index in range(7):
            radius = height * (0.25 + index * 0.13)
            parts.append(f'<circle cx="{width * 0.86:.0f}" cy="{height * 0.12:.0f}" r="{radius:.0f}" fill="none" '
                         f'stroke="{stroke if index % 2 == 0 else ink2(0.55)}" stroke-width="{2 + index * 0.6:.1f}" opacity="0.85"/>')
    else:
        raise AssetError(f"unknown pattern '{pattern}'; use one of {', '.join(PATTERNS)}")
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- treatments
def crop_to_ratio(image: Image.Image, ratio: float, focus: str) -> Image.Image:
    width, height = image.size
    current = width / height
    if abs(current - ratio) < 0.005:
        return image
    if current > ratio:  # too wide
        new_w = int(height * ratio)
        offsets = {"left": 0, "center": (width - new_w) // 2, "right": width - new_w}
        left = offsets.get(focus, offsets["center"])
        return image.crop((left, 0, left + new_w, height))
    new_h = int(width / ratio)
    offsets = {"top": 0, "center": (height - new_h) // 2, "bottom": height - new_h}
    top = offsets.get(focus, offsets["center"])
    return image.crop((0, top, width, top + new_h))


def duotone(image: Image.Image, dark: tuple[int, int, int], light: tuple[int, int, int]) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return ImageOps.colorize(gray, black=dark, white=light)


def tint(image: Image.Image, color: tuple[int, int, int], amount: float) -> Image.Image:
    layer = Image.new("RGB", image.size, color)
    return Image.blend(image.convert("RGB"), layer, max(0.0, min(1.0, amount)))


def scrim(image: Image.Image, position: str, strength: float) -> Image.Image:
    image = image.convert("RGBA")
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pixels = overlay.load()
    span = int(height * 0.55) if position in ("bottom", "top") else height
    for y in range(height):
        if position == "bottom":
            t = max(0.0, (y - (height - span)) / span)
        elif position == "top":
            t = max(0.0, (span - y) / span)
        else:
            t = 1.0
        alpha = int(255 * strength * (t ** 1.5 if position != "full" else 1))
        for x in range(width):
            pixels[x, y] = (0, 0, 0, alpha)
    return Image.alpha_composite(image, overlay).convert("RGB")


def rounded(image: Image.Image, radius: int) -> Image.Image:
    image = image.convert("RGBA")
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.width - 1, image.height - 1], radius=radius, fill=255)
    image.putalpha(mask)
    return image


def treat(args: argparse.Namespace, colors: dict) -> str:
    source = Path(args.input)
    if not source.is_file():
        raise AssetError(f"input not found: {source}")
    try:
        image = Image.open(source)
        image.load()
    except Exception as error:
        raise AssetError(f"cannot open {source}: {error}") from None
    image = ImageOps.exif_transpose(image).convert("RGB")
    steps = []
    if args.crop:
        image = crop_to_ratio(image, parse_ratio(args.crop), args.focus)
        steps.append(f"crop {args.crop} ({args.focus})")
    if args.width and image.width != args.width:
        image = image.resize((args.width, int(image.height * args.width / image.width)), Image.LANCZOS)
        steps.append(f"resize to {args.width} px wide")
    if args.grayscale:
        image = ImageOps.grayscale(image).convert("RGB")
        steps.append("grayscale")
    if args.duotone:
        image = duotone(image, colors["accent2"] if sum(colors["accent2"]) < sum(colors["accent"]) else colors["accent"], mix(colors["bg"], colors["accent"], 0.08))
        steps.append("duotone in the theme accent")
    if args.tint:
        image = tint(image, colors["accent"], args.tint)
        steps.append(f"tint {args.tint:g}")
    if args.scrim:
        image = scrim(image, args.scrim, args.scrim_strength)
        steps.append(f"scrim {args.scrim} {args.scrim_strength:g}")
    output = Path(args.output)
    if args.rounded:
        image = rounded(image, args.rounded)
        if output.suffix.lower() not in (".png", ".webp"):
            output = output.with_suffix(".png")
        steps.append(f"rounded corners {args.rounded} px")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() in (".jpg", ".jpeg"):
        image.convert("RGB").save(output, quality=args.quality, optimize=True)
    else:
        image.save(output)
    return f"wrote {output}: {image.width} x {image.height} px, {', '.join(steps) or 'no changes'}"


# --------------------------------------------------------------------------- placeholder
def placeholder(args: argparse.Namespace, colors: dict) -> str:
    size = parse_size(args.size)
    image = Image.new("RGB", size, mix(colors["bg"], colors["muted"], 0.12))
    draw = ImageDraw.Draw(image)
    line = mix(colors["bg"], colors["muted"], 0.4)
    draw.rectangle([0, 0, size[0] - 1, size[1] - 1], outline=line, width=max(2, size[0] // 300))
    draw.line([(0, 0), size], fill=line, width=max(1, size[0] // 600))
    draw.line([(0, size[1]), (size[0], 0)], fill=line, width=max(1, size[0] // 600))
    big = load_font(max(18, size[0] // 28))
    small = load_font(max(12, size[0] // 48))
    words = args.text.split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textlength(trial, font=big) > size[0] * 0.8 and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    total_h = len(lines) * (big.size + 8)
    y = (size[1] - total_h) // 2 - big.size
    box = [size[0] * 0.08, y - 24, size[0] * 0.92, y + total_h + big.size + 40]
    draw.rectangle(box, fill=colors["bg"])
    for text in lines:
        draw.text(((size[0] - draw.textlength(text, font=big)) / 2, y), text, fill=colors["text"], font=big)
        y += big.size + 8
    footer = f"placeholder {size[0]} x {size[1]} px"
    draw.text(((size[0] - draw.textlength(footer, font=small)) / 2, y + 14), footer, fill=colors["muted"], font=small)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return f"wrote {output}: placeholder {size[0]} x {size[1]} px"


# --------------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    back = sub.add_parser("backdrop", help="abstract on-theme background")
    back.add_argument("-o", "--output", required=True)
    back.add_argument("--theme", help="theme.json from deck-style")
    back.add_argument("--pattern", choices=PATTERNS, default="mesh")
    back.add_argument("--size", default="1920x1080", help="pixels, WIDTHxHEIGHT (default 1920x1080)")
    back.add_argument("--seed", type=int, default=7, help="change for another variation")
    back.add_argument("--format", choices=["png", "svg"], help="png for the .pptx, svg for the HTML deck (default: from the output suffix)")
    back.add_argument("--intensity", type=float, default=1.0, help="svg only: 0.4 for a quiet section backdrop, 1.4 for a loud title (default 1.0)")
    back.add_argument("--dark", action="store_true", help="force the dark variant")
    back.add_argument("--light", action="store_true", help="force the light variant")

    tr = sub.add_parser("treat", help="apply one consistent treatment to a photo")
    tr.add_argument("input")
    tr.add_argument("-o", "--output", required=True)
    tr.add_argument("--theme", help="theme.json from deck-style")
    tr.add_argument("--crop", help="ratio to crop to, e.g. 16:9, 4:3, 1:1, or 1.5")
    tr.add_argument("--focus", choices=["center", "left", "right", "top", "bottom"], default="center", help="which side to keep when cropping")
    tr.add_argument("--width", type=int, help="resize to this width in pixels (keeps the ratio)")
    tr.add_argument("--grayscale", action="store_true")
    tr.add_argument("--duotone", action="store_true", help="two-colour version in the theme accent")
    tr.add_argument("--tint", type=float, help="blend the theme accent over the photo, 0.1 to 0.5")
    tr.add_argument("--scrim", choices=["bottom", "top", "full"], help="dark gradient so a headline stays readable")
    tr.add_argument("--scrim-strength", type=float, default=0.65)
    tr.add_argument("--rounded", type=int, help="corner radius in pixels (output becomes PNG)")
    tr.add_argument("--quality", type=int, default=84, help="JPEG quality (default 84)")

    ic = sub.add_parser("icon", help="one icon from the bundled Carbon set, in a theme colour")
    ic.add_argument("name", nargs="?", help="icon name, e.g. rocket, chart-line, security")
    ic.add_argument("-o", "--output", help="output .svg path (default: print the SVG)")
    ic.add_argument("--theme", help="theme.json from deck-style")
    ic.add_argument("--color", default="accent", help=f"theme role ({', '.join(COLOUR_ROLES)}) or a hex colour (default accent)")
    ic.add_argument("--size", type=int, default=64, help="pixel size written into the SVG (default 64)")
    ic.add_argument("--list", action="store_true", help="list the icons by group and exit")
    ic.add_argument("--find", metavar="WORD", help="search icons by name or keyword")

    pat = sub.add_parser("pattern", help="tile one of the bundled pattern tiles across a slide-sized SVG")
    pat.add_argument("name", nargs="?", help="tile name, e.g. dots, grid, diagonal, circuit")
    pat.add_argument("-o", "--output", help="output .svg path (default: print the SVG)")
    pat.add_argument("--theme", help="theme.json from deck-style")
    pat.add_argument("--color", default="accent", help=f"theme role ({', '.join(COLOUR_ROLES)}) or a hex colour (default accent)")
    pat.add_argument("--strength", type=float, default=0.1, help="opacity of the pattern, 0.06 to 0.12 behind text (default 0.1)")
    pat.add_argument("--scale", type=float, default=1.0, help="tile size multiplier (default 1.0)")
    pat.add_argument("--size", default="1600x900", help="pixels, WIDTHxHEIGHT (default 1600x900)")
    pat.add_argument("--ground", action="store_true", help="fill the background with the theme background colour instead of leaving it transparent")
    pat.add_argument("--list", action="store_true", help="list the tiles and exit")

    lib = sub.add_parser("library", help="the bundled picture library (assets/library) plus the user's own folder")
    lib.add_argument("--dir", help=f"personal folder searched after the bundled set (default {PERSONAL_LIBRARY})")
    lib.add_argument("--find", metavar="WORDS", help="pictures whose name or keywords contain any of these words")
    lib.add_argument("--for-theme", metavar="THEME_JSON", help="which pack and which title and section pictures fit this theme")
    lib.add_argument("--pick", metavar="NAME", help="print the path of one picture, e.g. growth or pack-b/road, for treat")

    ph = sub.add_parser("placeholder", help="labelled stand-in for a pending picture")
    ph.add_argument("-o", "--output", required=True)
    ph.add_argument("--theme", help="theme.json from deck-style")
    ph.add_argument("--text", required=True, help="what the picture will show, e.g. 'Photo: the support team at work'")
    ph.add_argument("--size", default="1600x900")

    args = parser.parse_args(argv)
    try:
        colors = load_colors(getattr(args, "theme", None))
        if args.command == "backdrop":
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            fmt = args.format or ("svg" if output.suffix.lower() == ".svg" else "png")
            dark = True if args.dark else False if args.light else None
            size = parse_size(args.size)
            if fmt == "svg":
                markup = svg_backdrop(colors, args.pattern, size, args.seed, dark, args.intensity)
                output.write_text(markup, encoding="utf-8")
                message = f"wrote {output}: {args.pattern} backdrop, svg {size[0]} x {size[1]}, {len(markup) / 1024:.1f} KB"
            else:
                image = backdrop(colors, args.pattern, size, args.seed, dark)
                image.save(output)
                message = f"wrote {output}: {args.pattern} backdrop, png {image.width} x {image.height} px"
        elif args.command == "library":
            if args.pick:
                print(library_pick(args.pick, args.dir))
            elif args.for_theme:
                print("\n".join(library_for_theme(args.for_theme, load_colors(args.for_theme))))
            else:
                print("\n".join(library_listing(args.dir, args.find)))
            return 0
        elif args.command == "icon":
            manifest = load_manifest()
            if args.list or (not args.name and not args.find):
                print(f"{manifest['set']} ({manifest['package']} {manifest['version']}, {manifest['license']}), {len(manifest['icons'])} icons")
                for group, names in manifest["groups"].items():
                    print(f"  {group:12} {' '.join(names)}")
                return 0
            if args.find:
                hits = find_icons(args.find, manifest)
                if not hits:
                    print(f"nothing matches '{args.find}'")
                for name, keywords in hits:
                    print(f"  {name:18} {keywords}")
                return 0
            colour = hexstr(colors[args.color]) if args.color in COLOUR_ROLES else hexstr(parse_hex(args.color))
            markup = icon_svg(args.name, colour, args.size)
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(markup, encoding="utf-8")
                message = f"wrote {output}: icon {args.name} in {colour} at {args.size} px"
            else:
                sys.stdout.write(markup)
                return 0
        elif args.command == "pattern":
            if args.list or not args.name:
                print("pattern tiles (assets/patterns, Apache-2.0, written for this pack):")
                for tile in sorted(TILES.glob("*.svg")):
                    note = tile.read_text(encoding="utf-8").split('data-note="', 1)[-1].split('"', 1)[0]
                    print(f"  {tile.stem:12} {note}")
                return 0
            colour = hexstr(colors[args.color]) if args.color in COLOUR_ROLES else hexstr(parse_hex(args.color))
            ground = hexstr(colors["bg"]) if args.ground else None
            markup = pattern_svg(args.name, colour, parse_size(args.size), args.strength, args.scale, ground)
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(markup, encoding="utf-8")
                message = f"wrote {output}: pattern {args.name} in {colour} at {args.strength:g} strength"
            else:
                sys.stdout.write(markup)
                return 0
        elif args.command == "treat":
            message = treat(args, colors)
        else:
            message = placeholder(args, colors)
    except AssetError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
