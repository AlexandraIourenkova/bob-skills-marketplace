#!/usr/bin/env python3
"""Render a chart spec (JSON) to a PNG for a slide, in the deck's theme colours, with matplotlib.

For the charts PowerPoint's native engine cannot draw well: waterfall, slope,
lollipop, bullet, small multiples, scatter with labels, heatmap, and bar or
line charts that need annotations, a target line or one highlighted element.
The picture is sized for the slide (default 11.5 x 5.2 in, the full content
area of a 16:9 deck; use 7 x 5.2 for the chart column next to bullets) and
placed in the storyboard with `![alt](charts/name.png)`. Spec reference:
references/chart-spec.md. No network, writes only the output path.

Run:  uv run --with matplotlib python chart_render.py spec.json --theme theme.json -o charts/revenue.png
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.ticker import FuncFormatter
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write("matplotlib is not installed. Run with: uv run --with matplotlib python chart_render.py ...\n")
    sys.exit(1)

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

TYPES = ("bar", "barh", "stacked", "line", "area", "slope", "waterfall", "lollipop", "bullet", "small-multiples", "scatter", "heatmap", "donut")
DEFAULT_COLORS = {"bg": "#FFFFFF", "surface": "#F2F4F8", "text": "#161616", "muted": "#525252", "accent": "#0F62FE", "accent2": "#002D9C",
                  "line": "#C6C6C6", "chart": ["#0F62FE", "#002D9C", "#8A3FFC", "#009D9A", "#FF832B", "#A8A8A8"]}


class SpecError(Exception):
    pass


# --------------------------------------------------------------------------- helpers
def parse_hex(value: str) -> str:
    text = str(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        raise SpecError(f"colour '{value}' is not a hex colour")
    return "#" + text.upper()


def mix(color: str, other: str, amount: float) -> str:
    a, b = parse_hex(color)[1:], parse_hex(other)[1:]
    parts = [round(int(a[i:i + 2], 16) * (1 - amount) + int(b[i:i + 2], 16) * amount) for i in (0, 2, 4)]
    return "#" + "".join(f"{max(0, min(255, p)):02X}" for p in parts)


def load_theme(path: str | None) -> tuple[dict, str]:
    colors = dict(DEFAULT_COLORS)
    font = "Arial"
    if path:
        file = Path(path)
        if not file.is_file():
            raise SpecError(f"theme not found: {file}")
        theme = json.loads(file.read_text(encoding="utf-8"))
        colors.update({k: v for k, v in theme.get("colors", {}).items() if k in colors})
        font = theme.get("fonts", {}).get("body", font)
    return colors, font


def pick_font(preferred: str) -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in (preferred, "Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"):
        if name in available:
            return name
    return "DejaVu Sans"


def series_list(spec: dict, categories: list[str]) -> list[tuple[str, list[float]]]:
    raw = spec.get("series")
    if isinstance(raw, dict):
        raw = [{"name": k, "values": v} for k, v in raw.items()]
    if not isinstance(raw, list) or not raw:
        raise SpecError("spec needs 'series': a list of {name, values} or an object {name: [values]}")
    result = []
    for entry in raw:
        values = entry.get("values") if isinstance(entry, dict) else None
        if not isinstance(values, list) or len(values) != len(categories):
            raise SpecError(f"series '{entry.get('name', '') if isinstance(entry, dict) else entry}' needs {len(categories)} values")
        try:
            result.append((str(entry.get("name", f"Series {len(result) + 1}")), [float(v) if v is not None else float('nan') for v in values]))
        except (TypeError, ValueError):
            raise SpecError(f"series '{entry.get('name', '')}' has a non-numeric value") from None
    return result


def fmt(spec: dict):
    pattern = spec.get("number_format") or "{:,.0f}"
    unit = spec.get("unit", "")
    if "{" not in pattern:  # Excel-style hints: 0, 0.0, 0.00, 0%
        decimals = len(pattern.split(".")[1].rstrip("%")) if "." in pattern else 0
        pattern = "{:,." + str(decimals) + "f}" + ("%" if pattern.endswith("%") else "")
    def apply(value, *_):
        try:
            return pattern.format(value) + unit
        except (ValueError, TypeError):
            return str(value)
    return apply


def style_axes(ax, colors: dict, muted_axis: bool = True):
    ax.set_facecolor("none")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(colors["line"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=colors["muted"], labelsize=11, length=0)
    ax.yaxis.grid(True, color=colors["line"], linewidth=0.7)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    if muted_axis:
        ax.spines["left"].set_visible(False)


def highlighted(spec: dict, categories: list[str]) -> set[int]:
    chosen = spec.get("highlight") or []
    if not isinstance(chosen, list):
        chosen = [chosen]
    result = set()
    for item in chosen:
        if isinstance(item, int) and 0 <= item < len(categories):
            result.add(item)
        elif str(item) in categories:
            result.add(categories.index(str(item)))
        elif str(item).isdigit() and int(item) < len(categories):
            result.add(int(item))
    return result


def finish(fig, ax_for_notes, spec: dict, colors: dict, output: Path, args) -> None:
    if spec.get("title"):
        fig.suptitle(spec["title"], x=0.01, ha="left", fontsize=15, fontweight="bold", color=colors["text"])
    if spec.get("subtitle"):
        fig.text(0.01, 0.905 if spec.get("title") else 0.96, spec["subtitle"], ha="left", fontsize=11, color=colors["muted"])
    if spec.get("source"):
        fig.text(0.01, 0.012, f"Source: {spec['source']}", ha="left", fontsize=9, color=colors["muted"])
    top = 0.84 if spec.get("title") and spec.get("subtitle") else 0.9 if spec.get("title") or spec.get("subtitle") else 0.97
    chart_type = str(spec.get("type", "bar")).lower()
    right = 0.86 if chart_type in ("line", "area") else 0.8 if chart_type == "slope" else 0.98
    left = 0.2 if chart_type in ("barh", "lollipop", "bullet", "heatmap") else 0.2 if chart_type == "slope" else 0.07
    fig.subplots_adjust(top=top, bottom=0.14 if spec.get("source") else 0.1, left=left, right=right)
    face = "none" if spec.get("transparent", args.transparent) else colors["bg"]
    # bbox_inches='tight' keeps long category labels and end-of-line labels inside the picture
    fig.savefig(output, dpi=int(spec.get("dpi", args.dpi)), facecolor=face, bbox_inches="tight", pad_inches=0.15)
    if args.svg:
        fig.savefig(output.with_suffix(".svg"), facecolor=face, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def add_target(ax, spec: dict, colors: dict, horizontal: bool = True) -> None:
    target = spec.get("target")
    if target is None:
        return
    value = target["value"] if isinstance(target, dict) else float(target)
    label = target.get("label", "Target") if isinstance(target, dict) else "Target"
    if horizontal:
        ax.axhline(value, color=colors["accent2"], linewidth=1.4, linestyle=(0, (5, 4)))
        ax.annotate(f"{label} {fmt(spec)(value)}", xy=(1.0, value), xycoords=("axes fraction", "data"), xytext=(-4, 4), textcoords="offset points",
                    ha="right", va="bottom", fontsize=10, color=colors["accent2"])
    else:
        ax.axvline(value, color=colors["accent2"], linewidth=1.4, linestyle=(0, (5, 4)))
        ax.annotate(f"{label} {fmt(spec)(value)}", xy=(value, 1.0), xycoords=("data", "axes fraction"), xytext=(4, -4), textcoords="offset points",
                    ha="left", va="top", fontsize=10, color=colors["accent2"])


def add_annotations(ax, spec: dict, categories: list[str], series: list[tuple[str, list[float]]], colors: dict, horizontal: bool = False) -> None:
    for note in spec.get("annotations") or []:
        category = str(note.get("category", ""))
        if category not in categories:
            continue
        index = categories.index(category)
        name = note.get("series")
        values = next((v for n, v in series if n == name), series[0][1])
        y = values[index]
        if horizontal:
            ax.annotate(note.get("text", ""), xy=(y, index), xytext=(12, 14), textcoords="offset points", fontsize=10, color=colors["text"],
                        arrowprops={"arrowstyle": "-", "color": colors["muted"], "linewidth": 0.8})
        else:
            ax.annotate(note.get("text", ""), xy=(index, y), xytext=(0, 22), textcoords="offset points", ha="center", fontsize=10, color=colors["text"],
                        arrowprops={"arrowstyle": "-", "color": colors["muted"], "linewidth": 0.8})


# --------------------------------------------------------------------------- chart types
def draw_bar(ax, spec: dict, colors: dict, horizontal: bool, stacked: bool = False) -> None:
    categories = [str(c) for c in spec["categories"]]
    series = series_list(spec, categories)
    order = list(range(len(categories)))
    if spec.get("sort") in ("asc", "desc") and len(series) == 1:
        order.sort(key=lambda i: series[0][1][i], reverse=spec["sort"] == "desc")
    categories = [categories[i] for i in order]
    series = [(n, [v[i] for i in order]) for n, v in series]
    chosen = highlighted(spec, categories)
    palette = colors["chart"]
    faded = mix(colors["muted"], colors["bg"], 0.55)
    labels = fmt(spec)
    positions = list(range(len(categories)))
    if horizontal:
        positions = positions[::-1]
    count = len(series)
    width = 0.72 if stacked or count == 1 else 0.8 / count
    bottoms = [0.0] * len(categories)
    for index, (name, values) in enumerate(series):
        base = palette[index % len(palette)]
        bar_colors = [colors["accent"] if i in chosen else (faded if chosen else base) for i in range(len(categories))] if count == 1 else [base] * len(categories)
        offset = 0 if stacked or count == 1 else (index - (count - 1) / 2) * width
        if horizontal:
            bars = ax.barh([p + offset for p in positions], values, height=width, left=bottoms if stacked else None, color=bar_colors, label=name)
        else:
            bars = ax.bar([p + offset for p in positions], values, width=width, bottom=bottoms if stacked else None, color=bar_colors, label=name)
        if spec.get("labels", True) and (count == 1 or stacked or len(categories) <= 6):
            for bar, value in zip(bars, values):
                if stacked:
                    x = bar.get_x() + bar.get_width() / 2 if not horizontal else bar.get_x() + bar.get_width() / 2
                    y = bar.get_y() + bar.get_height() / 2
                    if abs(value) > 0:
                        ax.text(x, y, labels(value), ha="center", va="center", fontsize=10, color=colors["bg"] if index < 3 else colors["text"])
                elif horizontal:
                    ax.text(bar.get_width() + (0.01 * max(1e-9, max(abs(v) for _, s in series for v in s))) * (1 if value >= 0 else -1), bar.get_y() + bar.get_height() / 2,
                            labels(value), ha="left" if value >= 0 else "right", va="center", fontsize=10, color=colors["text"])
                else:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (0.01 * max(1e-9, max(abs(v) for _, s in series for v in s))) * (1 if value >= 0 else -1),
                            labels(value), ha="center", va="bottom" if value >= 0 else "top", fontsize=10, color=colors["text"])
        if stacked:
            bottoms = [b + v for b, v in zip(bottoms, values)]
    if horizontal:
        ax.set_yticks(positions)
        ax.set_yticklabels(categories, color=colors["text"], fontsize=11)
        ax.xaxis.set_major_formatter(FuncFormatter(labels))
        ax.xaxis.grid(True, color=colors["line"], linewidth=0.7)
        ax.yaxis.grid(False)
        ax.spines["left"].set_visible(True)
        ax.spines["bottom"].set_visible(False)
        ax.axvline(0, color=colors["line"], linewidth=0.8)
    else:
        ax.set_xticks(range(len(categories)))
        lean = max((len(c) for c in categories), default=0) * len(categories) > 52  # long labels would overlap
        ax.set_xticklabels(categories, color=colors["text"], fontsize=11,
                           rotation=-30 if lean else 0, ha="left" if lean else "center",
                           rotation_mode="anchor" if lean else None)
        ax.yaxis.set_major_formatter(FuncFormatter(labels))
        ax.axhline(0, color=colors["line"], linewidth=0.8)
    if count > 1:
        ax.legend(frameon=False, fontsize=10, labelcolor=colors["text"], loc="upper left", ncol=min(count, 4), bbox_to_anchor=(0, 1.02))
    add_target(ax, spec, colors, horizontal=not horizontal)
    add_annotations(ax, spec, categories, series, colors, horizontal=horizontal)


def draw_line(ax, spec: dict, colors: dict, area: bool = False) -> None:
    categories = [str(c) for c in spec["categories"]]
    series = series_list(spec, categories)
    palette = colors["chart"]
    focus = spec.get("highlight_series")
    labels = fmt(spec)
    x = list(range(len(categories)))
    for index, (name, values) in enumerate(series):
        color = palette[index % len(palette)]
        if focus:
            color = colors["accent"] if name == focus else mix(colors["muted"], colors["bg"], 0.45)
        width = 3.0 if (not focus or name == focus) else 1.6
        ax.plot(x, values, color=color, linewidth=width, marker="o", markersize=5 if len(categories) <= 12 else 0, zorder=3 if name == focus else 2)
        if area:
            ax.fill_between(x, values, color=color, alpha=0.15)
        ax.annotate(name if len(series) > 1 else labels(values[-1]), xy=(x[-1], values[-1]), xytext=(10, 0), textcoords="offset points", va="center",
                    fontsize=10, color=color if (not focus or name == focus) else colors["muted"], fontweight="bold" if name == focus else "normal")
        if spec.get("labels") and len(categories) <= 12 and (not focus or name == focus):
            for xi, value in zip(x, values):
                ax.annotate(labels(value), xy=(xi, value), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9, color=colors["text"])
    ax.set_xticks(x)
    lean = max((len(c) for c in categories), default=0) * len(categories) > 52
    ax.set_xticklabels(categories, color=colors["text"], fontsize=11,
                       rotation=-30 if lean else 0, ha="left" if lean else "center",
                       rotation_mode="anchor" if lean else None)
    ax.yaxis.set_major_formatter(FuncFormatter(labels))
    ax.margins(x=0.04)
    if spec.get("average"):
        avg = sum(series[0][1]) / len(series[0][1])
        ax.axhline(avg, color=colors["muted"], linewidth=1, linestyle=(0, (2, 3)))
        ax.annotate(f"Average {labels(avg)}", xy=(0, avg), xytext=(2, 4), textcoords="offset points", fontsize=9, color=colors["muted"])
    add_target(ax, spec, colors, horizontal=True)
    add_annotations(ax, spec, categories, series, colors)


def draw_slope(ax, spec: dict, colors: dict) -> None:
    categories = [str(c) for c in spec["categories"]]
    if len(categories) != 2:
        raise SpecError("a slope chart needs exactly two categories (the two periods)")
    series = series_list(spec, categories)
    focus = spec.get("highlight") or []
    if not isinstance(focus, list):
        focus = [focus]
    labels = fmt(spec)
    for index, (name, values) in enumerate(series):
        chosen = (name in focus) or (not focus)
        color = colors["accent"] if name in focus else (colors["chart"][index % len(colors["chart"])] if not focus else mix(colors["muted"], colors["bg"], 0.35))
        ax.plot([0, 1], values, color=color, linewidth=3 if chosen else 1.5, marker="o", markersize=6, zorder=3 if name in focus else 2)
        ax.annotate(f"{name}  {labels(values[0])}", xy=(0, values[0]), xytext=(-8, 0), textcoords="offset points", ha="right", va="center", fontsize=10,
                    color=color if chosen else colors["muted"], fontweight="bold" if name in focus else "normal")
        ax.annotate(f"{labels(values[1])}  {name}", xy=(1, values[1]), xytext=(8, 0), textcoords="offset points", ha="left", va="center", fontsize=10,
                    color=color if chosen else colors["muted"], fontweight="bold" if name in focus else "normal")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(categories, color=colors["text"], fontsize=12)
    ax.set_xlim(-0.6, 1.6)
    ax.yaxis.set_visible(False)
    ax.yaxis.grid(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)


def draw_waterfall(ax, spec: dict, colors: dict) -> None:
    categories = [str(c) for c in spec["categories"]]
    series = series_list(spec, categories)
    values = series[0][1]
    totals = {str(t) for t in (spec.get("totals") or [])}
    labels = fmt(spec)
    running = 0.0
    up, down = colors["chart"][0], colors["accent2"] if colors["accent2"] != colors["chart"][0] else colors["chart"][1]
    for index, (category, value) in enumerate(zip(categories, values)):
        if category in totals or index == 0 and spec.get("first_is_total", True):
            ax.bar(index, value, color=colors["muted"], width=0.66)
            running = value
            ax.text(index, value + (0.012 * max(abs(v) for v in values)) * (1 if value >= 0 else -1), labels(value), ha="center",
                    va="bottom" if value >= 0 else "top", fontsize=10, color=colors["text"], fontweight="bold")
            continue
        bottom = running if value >= 0 else running + value
        ax.bar(index, abs(value), bottom=bottom, color=up if value >= 0 else down, width=0.66)
        ax.text(index, running + value + (0.012 * max(abs(v) for v in values)) * (1 if value >= 0 else -1), ("+" if value > 0 else "") + labels(value),
                ha="center", va="bottom" if value >= 0 else "top", fontsize=10, color=colors["text"])
        if index > 0:
            ax.plot([index - 1 + 0.33, index - 0.33], [running, running], color=colors["line"], linewidth=0.9)
        running += value
    ax.set_xticks(range(len(categories)))
    lean = max((len(c) for c in categories), default=0) * len(categories) > 52
    ax.set_xticklabels(categories, color=colors["text"], fontsize=11,
                       rotation=-30 if lean else 0, ha="left" if lean else "center",
                       rotation_mode="anchor" if lean else None)
    ax.yaxis.set_major_formatter(FuncFormatter(labels))
    ax.axhline(0, color=colors["line"], linewidth=0.8)


def draw_lollipop(ax, spec: dict, colors: dict) -> None:
    categories = [str(c) for c in spec["categories"]]
    series = series_list(spec, categories)
    values = series[0][1]
    order = list(range(len(categories)))
    if spec.get("sort", "desc") in ("asc", "desc"):
        order.sort(key=lambda i: values[i], reverse=spec.get("sort", "desc") == "desc")
    categories = [categories[i] for i in order]
    values = [values[i] for i in order]
    chosen = highlighted(spec, categories)
    labels = fmt(spec)
    positions = list(range(len(categories)))[::-1]
    for pos, category, value in zip(positions, categories, values):
        color = colors["accent"] if (pos in [positions[i] for i in chosen]) else (colors["chart"][0] if not chosen else mix(colors["muted"], colors["bg"], 0.4))
        ax.plot([0, value], [pos, pos], color=color, linewidth=2.2, zorder=2)
        ax.plot(value, pos, "o", color=color, markersize=11, zorder=3)
        ax.text(value + 0.02 * max(abs(v) for v in values), pos, labels(value), va="center", ha="left", fontsize=10, color=colors["text"])
    ax.set_yticks(positions)
    ax.set_yticklabels(categories, color=colors["text"], fontsize=11)
    ax.xaxis.set_major_formatter(FuncFormatter(labels))
    ax.xaxis.grid(True, color=colors["line"], linewidth=0.7)
    ax.yaxis.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(left=min(0, min(values) * 1.1), right=max(values) * 1.18)
    add_target(ax, spec, colors, horizontal=False)


def draw_bullet(ax, spec: dict, colors: dict) -> None:
    items = spec.get("bullets") or []
    if not items:
        raise SpecError("a bullet chart needs 'bullets': [{label, value, target, max}]")
    labels = fmt(spec)
    positions = list(range(len(items)))[::-1]
    for pos, item in zip(positions, items):
        maximum = float(item.get("max", max(item["value"], item.get("target", 0)) * 1.2))
        ranges = item.get("ranges") or [maximum * 0.5, maximum * 0.75, maximum]
        shade = [mix(colors["muted"], colors["bg"], a) for a in (0.55, 0.7, 0.85)]
        left = 0.0
        for bound, color in zip(ranges, shade):
            ax.barh(pos, bound - left, left=left, height=0.62, color=color)
            left = bound
        ax.barh(pos, float(item["value"]), height=0.26, color=colors["accent"])
        if item.get("target") is not None:
            ax.plot([item["target"], item["target"]], [pos - 0.31, pos + 0.31], color=colors["text"], linewidth=2.5)
        ax.text(maximum * 1.02, pos, labels(item["value"]) + (f" of {labels(item['target'])}" if item.get("target") is not None else ""), va="center",
                fontsize=10, color=colors["text"])
    ax.set_yticks(positions)
    ax.set_yticklabels([i["label"] for i in items], color=colors["text"], fontsize=11)
    ax.xaxis.set_major_formatter(FuncFormatter(labels))
    ax.yaxis.grid(False)
    ax.xaxis.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(0, max(float(i.get("max", 100)) for i in items) * 1.3)


def draw_small_multiples(fig, spec: dict, colors: dict) -> None:
    categories = [str(c) for c in spec["categories"]]
    series = series_list(spec, categories)
    kind = spec.get("kind", "line")
    count = len(series)
    cols = min(4, count) if count > 3 else count
    rows = -(-count // cols)
    axes = fig.subplots(rows, cols, sharex=True, sharey=True, squeeze=False)
    labels = fmt(spec)
    focus = spec.get("highlight_series")
    top = max(v for _, s in series for v in s if v == v)
    for index, ((name, values), ax) in enumerate(zip(series, axes.flat)):
        color = colors["accent"] if (focus is None or name == focus) else colors["muted"]
        style_axes(ax, colors)
        x = list(range(len(categories)))
        if kind == "bar":
            ax.bar(x, values, color=color, width=0.7)
        else:
            ax.plot(x, values, color=color, linewidth=2.2)
            ax.fill_between(x, values, color=color, alpha=0.12)
        ax.set_title(name, loc="left", fontsize=11, color=colors["text"], fontweight="bold" if name == focus else "normal")
        ax.annotate(labels(values[-1]), xy=(x[-1], values[-1]), xytext=(4, 2), textcoords="offset points", fontsize=9, color=colors["text"])
        ax.set_xticks([x[0], x[-1]])
        ax.set_xticklabels([categories[0], categories[-1]], fontsize=9, color=colors["muted"])
        ax.tick_params(axis="y", labelsize=9)
        ax.set_ylim(top=top * 1.15)
    for ax in list(axes.flat)[count:]:
        ax.set_visible(False)


def draw_scatter(ax, spec: dict, colors: dict) -> None:
    points = spec.get("points") or []
    if not points:
        raise SpecError("a scatter chart needs 'points': [{x, y, label, size, group}]")
    groups = sorted({str(p.get("group", "")) for p in points})
    palette = {g: colors["chart"][i % len(colors["chart"])] for i, g in enumerate(groups)}
    focus = {str(h) for h in (spec.get("highlight") or [])}
    sizes = [float(p.get("size", 1.0)) for p in points]
    scale = 220 / max(sizes) if max(sizes) > 0 else 1
    for point in points:
        label = str(point.get("label", ""))
        color = colors["accent"] if label in focus else (palette[str(point.get("group", ""))] if not focus else mix(colors["muted"], colors["bg"], 0.35))
        ax.scatter(point["x"], point["y"], s=max(30, float(point.get("size", 1.0)) * scale), color=color, alpha=0.85, edgecolors=colors["bg"], linewidths=0.8, zorder=3)
        if label and (label in focus or len(points) <= 15):
            ax.annotate(label, xy=(point["x"], point["y"]), xytext=(6, 4), textcoords="offset points", fontsize=9,
                        color=colors["text"] if (not focus or label in focus) else colors["muted"], fontweight="bold" if label in focus else "normal")
    ax.set_xlabel(spec.get("x_label", ""), fontsize=10, color=colors["muted"])
    ax.set_ylabel(spec.get("y_label", ""), fontsize=10, color=colors["muted"])
    ax.xaxis.grid(True, color=colors["line"], linewidth=0.6)
    if len(groups) > 1 and not focus:
        for group in groups:
            ax.scatter([], [], color=palette[group], label=group or "other")
        ax.legend(frameon=False, fontsize=9, labelcolor=colors["text"])
    for key, axis in (("x_target", "v"), ("y_target", "h")):
        if spec.get(key) is not None:
            (ax.axvline if axis == "v" else ax.axhline)(spec[key], color=colors["accent2"], linewidth=1.2, linestyle=(0, (5, 4)))


def draw_heatmap(fig, ax, spec: dict, colors: dict) -> None:
    rows = [str(r) for r in spec.get("rows") or []]
    columns = [str(c) for c in spec.get("columns") or []]
    values = spec.get("values") or []
    if not rows or not columns or len(values) != len(rows) or any(len(r) != len(columns) for r in values):
        raise SpecError("a heatmap needs 'rows', 'columns' and a 'values' matrix of matching shape")
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("theme", [mix(colors["accent"], colors["bg"], 0.92), colors["accent"]])
    image = ax.imshow(values, cmap=cmap, aspect="auto")
    labels = fmt(spec)
    flat = [v for row in values for v in row]
    mid = (max(flat) + min(flat)) / 2
    for r in range(len(rows)):
        for c in range(len(columns)):
            value = values[r][c]
            ax.text(c, r, labels(value), ha="center", va="center", fontsize=10, color=colors["bg"] if value > mid else colors["text"])
    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels(columns, fontsize=10, color=colors["text"])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=10, color=colors["text"])
    ax.xaxis.tick_top()
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    ax.yaxis.grid(False)
    del image


def draw_donut(ax, spec: dict, colors: dict) -> None:
    categories = [str(c) for c in spec["categories"]]
    series = series_list(spec, categories)
    values = series[0][1]
    if len(categories) > 5:
        raise SpecError("a donut takes at most five parts; use a sorted bar chart for more")
    chosen = highlighted(spec, categories)
    palette = [colors["accent"] if i in chosen else (colors["chart"][i % len(colors["chart"])] if not chosen else mix(colors["muted"], colors["bg"], 0.35 + 0.1 * i))
               for i in range(len(categories))]
    total = sum(values)
    wedges, _ = ax.pie(values, colors=palette, startangle=90, counterclock=False, wedgeprops={"width": 0.38, "edgecolor": colors["bg"], "linewidth": 2})
    for wedge, category, value in zip(wedges, categories, values):
        import math

        angle = math.radians((wedge.theta2 + wedge.theta1) / 2)
        x, y = math.cos(angle), math.sin(angle)
        ax.annotate(f"{category}  {value / total:.0%}", xy=(x * 0.82, y * 0.82), xytext=(x * 1.22, y * 1.22), ha="left" if x >= 0 else "right", va="center",
                    fontsize=10, color=colors["text"], arrowprops={"arrowstyle": "-", "color": colors["line"]})
    center = spec.get("center")
    if center:
        ax.text(0, 0, str(center), ha="center", va="center", fontsize=26, fontweight="bold", color=colors["text"])
    ax.set_aspect("equal")


# --------------------------------------------------------------------------- cli
def render(spec: dict, colors: dict, font: str, output: Path, args: argparse.Namespace) -> str:
    chart_type = str(spec.get("type", "bar")).lower()
    if chart_type not in TYPES:
        raise SpecError(f"unknown chart type '{chart_type}'; use one of {', '.join(TYPES)}")
    width, height = spec.get("size") or [args.width, args.height]
    plt.rcParams.update({"font.family": pick_font(font), "text.color": colors["text"], "axes.labelcolor": colors["text"]})
    fig = plt.figure(figsize=(float(width), float(height)))
    fig.patch.set_facecolor(colors["bg"])
    if chart_type == "small-multiples":
        draw_small_multiples(fig, spec, colors)
        finish(fig, None, spec, colors, output, args)
        return chart_type
    ax = fig.add_subplot(111)
    style_axes(ax, colors)
    if chart_type in ("bar", "barh", "stacked"):
        draw_bar(ax, spec, colors, horizontal=chart_type == "barh", stacked=chart_type == "stacked")
    elif chart_type in ("line", "area"):
        draw_line(ax, spec, colors, area=chart_type == "area")
    elif chart_type == "slope":
        draw_slope(ax, spec, colors)
    elif chart_type == "waterfall":
        draw_waterfall(ax, spec, colors)
    elif chart_type == "lollipop":
        draw_lollipop(ax, spec, colors)
    elif chart_type == "bullet":
        draw_bullet(ax, spec, colors)
    elif chart_type == "scatter":
        draw_scatter(ax, spec, colors)
    elif chart_type == "heatmap":
        draw_heatmap(fig, ax, spec, colors)
    elif chart_type == "donut":
        draw_donut(ax, spec, colors)
    finish(fig, ax, spec, colors, output, args)
    return chart_type


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", help="chart spec JSON file (see references/chart-spec.md)")
    parser.add_argument("-o", "--output", required=True, help="output PNG path")
    parser.add_argument("--theme", help="theme.json from deck-style; colours and the body font come from it")
    parser.add_argument("--width", type=float, default=11.5, help="inches (default 11.5, the full content width; 7 for the chart column)")
    parser.add_argument("--height", type=float, default=5.2, help="inches (default 5.2)")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--transparent", action="store_true", help="transparent background instead of the theme background")
    parser.add_argument("--svg", action="store_true", help="also write an .svg next to the PNG")
    args = parser.parse_args(argv)
    try:
        spec_path = Path(args.spec)
        if not spec_path.is_file():
            raise SpecError(f"spec not found: {spec_path}")
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SpecError(f"{spec_path} is not valid JSON: {error}") from None
        colors, font = load_theme(args.theme)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        chart_type = render(spec, colors, font, output, args)
    except SpecError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    print(f"wrote {output}: {chart_type} chart, {args.width:g} x {args.height:g} in at {args.dpi} dpi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
