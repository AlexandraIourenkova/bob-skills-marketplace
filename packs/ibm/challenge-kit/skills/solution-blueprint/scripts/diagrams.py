"""SVG diagrams for the solution blueprint.

A layered architecture with orthogonal connectors, process lanes, a time bar,
a waterfall and the hero backdrop. Standard library only. Every colour is a CSS
variable of the page, so one theme styles the text and the diagrams alike.

Each function returns the SVG markup and a list of warnings; nothing is written.
"""

from __future__ import annotations

from html import escape

WIDTH = 1120

KINDS = {
    "user": ("People", "var(--muted)"),
    "ui": ("Interface", "var(--c0)"),
    "agent": ("Agent", "var(--c1)"),
    "model": ("Model", "var(--c4)"),
    "tool": ("Tool or API", "var(--c2)"),
    "data": ("Data", "var(--c3)"),
    "external": ("Existing system", "var(--muted)"),
    "service": ("Service", "var(--c5)"),
}

# 24 x 24 line glyphs drawn for this pack.
ICONS = {
    "user": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 20c.8-3.6 3.8-5.5 7.5-5.5s6.700 1.900 7.500 5.500",
    "ui": "M3.5 5.500h17v11h-17z M9 20h6 M12 16.500v3.500",
    "agent": "M6 8.500h12v9.500h-12z M12 8.500v-3.500 M12 4.200a.8.8 0 1 0 0 .01 M9.500 12.500v1.500 M14.500 12.500v1.500 M3.500 12v3 M20.500 12v3",
    "model": "M7 7h10v10h-10z M10 10h4v4h-4z M9.500 7v-3 M14.500 7v-3 M9.500 20v-3 M14.500 20v-3 M7 9.500h-3 M7 14.500h-3 M20 9.500h-3 M20 14.500h-3",
    "tool": "M14.500 5.500a4 4 0 0 0-5 5l-5.500 5.500 2.500 2.500 5.500-5.500a4 4 0 0 0 5-5l-2.500 2.500-2-2z",
    "data": "M5 6.500c0-1.400 3.100-2.500 7-2.500s7 1.100 7 2.500-3.100 2.500-7 2.500-7-1.100-7-2.500z M5 6.500v11c0 1.400 3.100 2.500 7 2.500s7-1.100 7-2.500v-11 M5 12c0 1.400 3.100 2.500 7 2.500s7-1.100 7-2.500",
    "external": "M4 20v-12l5-3v15 M9 20v-9h11v9z M12.500 14h1.500 M16 14h1.500 M12.500 17h1.500 M16 17h1.500 M3 20h18",
    "service": "M7.500 18.500a4.500 4.500 0 0 1-.6-8.960 5.500 5.500 0 0 1 10.600 1.460 3.800 3.800 0 0 1-.5 7.500z",
}

NARROW = set("iljtfrI.,:;|!'()[]/ ")
WIDE = set("mwMW@%")


def text_width(text: str, size: float) -> float:
    """Estimated width of a line of text in a sans-serif face."""
    total = 0.0
    for ch in text:
        code = ord(ch)
        if ch in NARROW:
            total += 0.31
        elif ch in WIDE:
            total += 0.86
        elif code > 0x2E7F:
            total += 1.0
        elif code > 0x036F:
            total += 0.6
        elif ch.isupper() or ch.isdigit():
            total += 0.63
        else:
            total += 0.53
    return total * size


def wrap(text: str, size: float, width: float, max_lines: int) -> tuple[list[str], bool]:
    """Break text into lines that fit the width. The flag says that text was cut."""
    lines: list[str] = []
    current = ""
    for word in str(text).split():
        trial = f"{current} {word}".strip()
        if current and text_width(trial, size) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    cut = len(lines) > max_lines
    lines = lines[:max_lines]
    for i, line in enumerate(lines):
        mark = "…" if cut and i == len(lines) - 1 else ""
        shortened = line
        while len(shortened) > 1 and text_width(shortened + mark, size) > width:
            shortened = shortened[:-1]
            mark = "…"
            cut = True
        lines[i] = shortened.rstrip() + mark if mark else shortened
    return lines, cut


LABELS: dict[str, str] = {}


def t(text: str) -> str:
    """A fixed label of the page, in the document's language when the spec translates it."""
    return LABELS.get(text, text)


def n(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def path_d(points: list[tuple[float, float]], radius: float = 7) -> str:
    """An orthogonal polyline with rounded corners."""
    pts = [points[0]]
    for p in points[1:]:
        if abs(p[0] - pts[-1][0]) > 0.01 or abs(p[1] - pts[-1][1]) > 0.01:
            pts.append(p)
    d = f"M{n(pts[0][0])} {n(pts[0][1])}"
    for a, p, b in zip(pts, pts[1:], pts[2:]):
        la = abs(p[0] - a[0]) + abs(p[1] - a[1])
        lb = abs(b[0] - p[0]) + abs(b[1] - p[1])
        r = min(radius, la / 2, lb / 2)
        p1 = (p[0] + (a[0] - p[0]) / la * r, p[1] + (a[1] - p[1]) / la * r)
        p2 = (p[0] + (b[0] - p[0]) / lb * r, p[1] + (b[1] - p[1]) / lb * r)
        d += f" L{n(p1[0])} {n(p1[1])} Q{n(p[0])} {n(p[1])} {n(p2[0])} {n(p2[1])}"
    d += f" L{n(pts[-1][0])} {n(pts[-1][1])}"
    return d


def arrow(points: list[tuple[float, float]], cls: str = "edge") -> str:
    """A connector that ends in an arrowhead at the last point."""
    (ax, ay), (bx, by) = points[-2], points[-1]
    length = abs(bx - ax) + abs(by - ay) or 1
    ux, uy = (bx - ax) / length, (by - ay) / length
    base = (bx - ux * 7, by - uy * 7)
    left = (base[0] - uy * 4, base[1] + ux * 4)
    right = (base[0] + uy * 4, base[1] - ux * 4)
    body = points[:-1] + [(bx - ux * 5, by - uy * 5)]
    head = f"{n(bx)},{n(by)} {n(left[0])},{n(left[1])} {n(right[0])},{n(right[1])}"
    return f'<path class="{cls}" d="{path_d(body)}"/><polygon class="{cls}-head" points="{head}"/>'


def text_block(lines: list[str], x: float, y: float, size: float, cls: str, anchor: str = "start", leading: float = 1.25) -> str:
    out = []
    for i, line in enumerate(lines):
        out.append(f'<text class="{cls}" x="{n(x)}" y="{n(y + i * size * leading)}" font-size="{n(size)}" text-anchor="{anchor}">{escape(line)}</text>')
    return "".join(out)


# ---------------------------------------------------------------- architecture
def _assign_tracks(segments: list[dict]) -> int:
    """Give overlapping horizontal segments of one channel different tracks."""
    ends: list[float] = []
    for seg in sorted(segments, key=lambda s: (s["x1"], s["x2"])):
        for t, end in enumerate(ends):
            if end + 16 < seg["x1"]:
                ends[t] = seg["x2"]
                seg["track"] = t
                break
        else:
            seg["track"] = len(ends)
            ends.append(seg["x2"])
    return len(ends)


def architecture(arch: dict, rtl: bool = False) -> tuple[str, list[str], set[str]]:
    """Layers top to bottom, nodes in a row, orthogonal connectors that avoid nodes."""
    warnings: list[str] = []
    layers = arch.get("layers", [])
    label_w, node_h, pad, gap = 150, 78, 20, 26
    # Connectors that skip a layer run down the sides, so the sides are sized for them first.
    place = {item.get("id"): (li, (pos + 0.5) / max(len(layer.get("nodes", [])), 1))
             for li, layer in enumerate(layers) for pos, item in enumerate(layer.get("nodes", []))}

    def right_side(a_id, b_id) -> bool:
        return place[a_id][1] + place[b_id][1] >= 1

    skips = [right_side(r.get("from"), r.get("to")) for r in arch.get("edges", [])
             if r.get("from") in place and r.get("to") in place and abs(place[r["from"]][0] - place[r["to"]][0]) > 1]
    left_edge, right_edge = (8, WIDTH - label_w - 2) if rtl else (label_w + 2, WIDTH - 8)
    x0 = left_edge + 18 + 10 * skips.count(False)
    x1 = right_edge - 18 - 10 * skips.count(True)
    region = x1 - x0

    nodes: dict[str, dict] = {}
    for li, layer in enumerate(layers):
        items = layer.get("nodes", [])
        count = max(len(items), 1)
        width = min(236, (region - (count - 1) * gap) / count)
        start = x0 + (region - (count * width + (count - 1) * gap)) / 2
        for pos, item in enumerate(items):
            nodes[item["id"]] = {"layer": li, "pos": pos, "x": start + pos * (width + gap), "w": width,
                                 "spec": item, "top": [], "bottom": []}

    def gutter_x(right: bool, used: list[tuple[bool, float]]) -> float:
        taken = sum(1 for side, _ in used if side == right)
        return x1 + 12 + 10 * taken if right else x0 - 12 - 10 * taken

    edges: list[dict] = []
    corridors: list[tuple[bool, float]] = []
    for raw in arch.get("edges", []):
        a, b = nodes.get(raw.get("from")), nodes.get(raw.get("to"))
        if not a or not b or a is b:
            continue
        edge = {"raw": raw, "a": a, "b": b, "kind": "", "segs": []}
        ac, bc = a["x"] + a["w"] / 2, b["x"] + b["w"] / 2
        if a["layer"] == b["layer"]:
            if abs(a["pos"] - b["pos"]) == 1:
                edge["kind"] = "side"
            else:
                edge["kind"] = "arc"
                edge["above"] = a["layer"] > 0
                side = "top" if edge["above"] else "bottom"
                a[side].append((edge, "a", bc))
                b[side].append((edge, "b", ac))
        else:
            up, low = (a, b) if a["layer"] < b["layer"] else (b, a)
            edge["up"], edge["low"] = up, low
            edge["kind"] = "adjacent" if low["layer"] - up["layer"] == 1 else "skip"
            uc, lc = up["x"] + up["w"] / 2, low["x"] + low["w"] / 2
            if edge["kind"] == "skip":
                side = right_side(raw["from"], raw["to"])
                edge["cx"] = gutter_x(side, corridors)
                corridors.append((side, edge["cx"]))
                up["bottom"].append((edge, "up", edge["cx"]))
                low["top"].append((edge, "low", edge["cx"]))
            else:
                up["bottom"].append((edge, "up", lc))
                low["top"].append((edge, "low", uc))
        edges.append(edge)

    for node in nodes.values():
        for side in ("top", "bottom"):
            ports = sorted(node[side], key=lambda p: p[2])
            step = min(24, node["w"] * 0.62 / max(len(ports) - 1, 1))
            for i, (edge, role, _) in enumerate(ports):
                edge[f"x_{role}"] = node["x"] + node["w"] / 2 + (i - (len(ports) - 1) / 2) * step

    channels: list[list[dict]] = [[] for _ in range(max(len(layers) - 1, 1))]

    def seg(channel: int, xa: float, xb: float, edge: dict, name: str) -> None:
        item = {"x1": min(xa, xb), "x2": max(xa, xb), "track": 0}
        edge[name] = item
        channels[channel].append(item)

    for edge in edges:
        if edge["kind"] == "adjacent":
            if abs(edge["x_up"] - edge["x_low"]) < 4:
                edge["x_low"] = edge["x_up"]
                edge["straight"] = True
            else:
                seg(edge["up"]["layer"], edge["x_up"], edge["x_low"], edge, "h1")
        elif edge["kind"] == "skip":
            seg(edge["up"]["layer"], edge["x_up"], edge["cx"], edge, "h1")
            seg(edge["low"]["layer"] - 1, edge["cx"], edge["x_low"], edge, "h2")
        elif edge["kind"] == "arc":
            layer = edge["a"]["layer"]
            seg(layer - 1 if edge["above"] else min(layer, len(channels) - 1), edge["x_a"], edge["x_b"], edge, "h1")
    tracks = [_assign_tracks(ch) for ch in channels]
    heights = [max(46, 30 + 16 * t) for t in tracks]

    band_h = node_h + 2 * pad
    tops: list[float] = []
    y = 6.0
    for li in range(len(layers)):
        tops.append(y)
        y += band_h + (heights[li] if li < len(layers) - 1 else 0)
    # an arc under the only layer needs room below it
    extra = 46 if any(e["kind"] == "arc" and not e["above"] and e["a"]["layer"] == len(layers) - 1 for e in edges) else 0
    total_h = y + 6 + extra

    def track_y(channel: int, item: dict) -> float:
        if channel >= len(layers) - 1:
            return tops[-1] + band_h + 24
        top = tops[channel] + band_h
        return top + (heights[channel] - 16 * (tracks[channel] - 1)) / 2 + 16 * item["track"]

    for node in nodes.values():
        node["y"] = tops[node["layer"]] + pad

    out = [f'<svg class="diagram arch" viewBox="0 0 {WIDTH} {n(total_h)}" role="img" aria-label="Architecture diagram" direction="ltr" xmlns="http://www.w3.org/2000/svg">']
    for li, layer in enumerate(layers):
        out.append(f'<rect class="band" x="0.5" y="{n(tops[li])}" width="{WIDTH - 1}" height="{band_h}" rx="12"/>')
        lines, cut = wrap(layer.get("title", ""), 11.5, label_w - 34, 4)
        if cut:
            warnings.append(f"architecture: layer title '{layer.get('title')}' was cut; shorten it")
        tx = WIDTH - 20 if rtl else 20
        ty = tops[li] + band_h / 2 - (len(lines) - 1) * 7.5 + 4
        out.append(text_block([s.upper() for s in lines], tx, ty, 11.5, "band-title", "end" if rtl else "start", 1.3))

    used_kinds: set[str] = set()
    labels: list[str] = []
    heads: list[str] = []
    for edge in edges:
        a, b, raw = edge["a"], edge["b"], edge["raw"]
        if edge["kind"] == "side":
            left, right = (a, b) if a["x"] < b["x"] else (b, a)
            my = left["y"] + node_h / 2
            pts = [(left["x"] + left["w"], my), (right["x"], my)]
            if a is right:
                pts.reverse()
            label_at = ((pts[0][0] + pts[1][0]) / 2, left["y"] + node_h + pad / 2, "band")
        elif edge["kind"] == "arc":
            ty = track_y(a["layer"] - 1 if edge["above"] else a["layer"], edge["h1"])
            ya = a["y"] if edge["above"] else a["y"] + node_h
            pts = [(edge["x_a"], ya), (edge["x_a"], ty), (edge["x_b"], ty), (edge["x_b"], ya)]
            label_at = ((edge["x_a"] + edge["x_b"]) / 2, ty, "bg")
        else:
            up, low = edge["up"], edge["low"]
            y_up, y_low = up["y"] + node_h, low["y"]
            if edge.get("straight"):
                pts = [(edge["x_up"], y_up), (edge["x_low"], y_low)]
                label_at = (edge["x_up"], (y_up + y_low) / 2, "bg")
            elif edge["kind"] == "adjacent":
                ty = track_y(up["layer"], edge["h1"])
                pts = [(edge["x_up"], y_up), (edge["x_up"], ty), (edge["x_low"], ty), (edge["x_low"], y_low)]
                label_at = ((edge["x_up"] + edge["x_low"]) / 2, ty, "bg")
            else:
                t1, t2 = track_y(up["layer"], edge["h1"]), track_y(low["layer"] - 1, edge["h2"])
                pts = [(edge["x_up"], y_up), (edge["x_up"], t1), (edge["cx"], t1), (edge["cx"], t2), (edge["x_low"], t2), (edge["x_low"], y_low)]
                label_at = ((edge["x_up"] + edge["cx"]) / 2, t1, "bg")
            if a is low:
                pts.reverse()
        edge["points"] = pts
        cls = "edge dashed" if raw.get("style") == "dashed" else "edge"
        drawn = arrow(pts, "edge")
        if raw.get("style") == "dashed":
            drawn = drawn.replace('class="edge"', f'class="{cls}"', 1)
        if raw.get("both"):
            back = arrow(list(reversed(pts)), "edge")
            drawn += back[back.index("<polygon"):]
        heads.append(drawn)
        if raw.get("label"):
            text = str(raw["label"])[:26]
            lines = [text]
            w = len(text) * 6.35 + 14
            lx, ly, bg = label_at
            labels.append(f'<rect class="edge-label-{bg}" x="{n(lx - w / 2)}" y="{n(ly - 8)}" width="{n(w)}" height="16" rx="8"/>'
                          f'<text class="edge-label" x="{n(lx)}" y="{n(ly + 3.6)}" font-size="10.5" text-anchor="middle">{escape(lines[0])}</text>')

    for edge in edges:
        own = (edge["a"], edge["b"])
        pts = edge["points"]
        for (px, py), (qx, qy) in zip(pts, pts[1:]):
            for node in nodes.values():
                if node in own:
                    continue
                if min(px, qx) < node["x"] + node["w"] - 1 and max(px, qx) > node["x"] + 1 and min(py, qy) < node["y"] + node_h - 1 and max(py, qy) > node["y"] + 1:
                    warnings.append(f"architecture: the connector {edge['raw']['from']} -> {edge['raw']['to']} crosses the node '{node['spec'].get('title')}'; reorder the nodes of that layer")

    out.extend(heads)
    out.extend(labels)
    for node in nodes.values():
        spec = node["spec"]
        kind = spec.get("kind", "service") if spec.get("kind") in KINDS else "service"
        used_kinds.add(kind)
        x, y, w = node["x"], node["y"], node["w"]
        classes = "node" + (" ibm" if spec.get("ibm") else "") + (f" {spec['status']}" if spec.get("status") in ("planned", "mock") else "")
        out.append(f'<g class="{classes}" style="--k:{KINDS[kind][1]}">')
        out.append(f'<rect class="node-box" x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{node_h}" rx="10"/>')
        compact = w < 150
        icon = 0 if compact else 34
        ix = x + w - 12 - 26 if rtl else x + 12
        if not compact:
            out.append(f'<rect class="node-icon-bg" x="{n(ix)}" y="{n(y + node_h / 2 - 13)}" width="26" height="26" rx="7"/>'
                       f'<path class="node-icon" transform="translate({n(ix + 4)} {n(y + node_h / 2 - 9)}) scale(0.75)" d="{ICONS[kind]}"/>')
        else:
            out.append(f'<rect class="node-strip" x="{n(x)}" y="{n(y + 14)}" width="3" height="{node_h - 28}" rx="1.5"/>')
        text_w = w - 24 - icon - (6 if not compact else 0)
        title, cut_t = wrap(spec.get("title", ""), 13, text_w, 2)
        tech, cut_s = wrap(spec.get("tech", ""), 11, text_w, 2 if len(title) == 1 else 1)
        if cut_t or cut_s:
            warnings.append(f"architecture: the text of node '{spec.get('title')}' was cut; shorten it or use fewer nodes in the layer")
        block = len(title) * 16 + (len(tech) * 14 + 3 if tech else 0)
        ty = y + (node_h - block) / 2 + 12.5
        if rtl:
            tx, anchor = x + w - 12 - icon - (6 if icon else 0), "end"
        else:
            tx, anchor = x + 12 + icon + (6 if icon else 0), "start"
        out.append(text_block(title, tx, ty, 13, "node-title", anchor, 16 / 13))
        if tech:
            out.append(text_block(tech, tx, ty + len(title) * 16 + 1, 11, "node-tech", anchor, 14 / 11))
        tag = "IBM" if spec.get("ibm") else ""
        state = t({"planned": "planned", "mock": "mock"}.get(spec.get("status"), ""))
        bx = x + 10 if rtl else x + w - 10
        for text, cls in ((tag, "tag-ibm"), (state, "tag-state")):
            if not text:
                continue
            tw = text_width(text, 8.5) + 10
            rx = bx if rtl else bx - tw
            out.append(f'<rect class="{cls}" x="{n(rx)}" y="{n(y - 7)}" width="{n(tw)}" height="14" rx="7"/>'
                       f'<text class="{cls}-text" x="{n(rx + tw / 2)}" y="{n(y + 3.2)}" font-size="8.5" text-anchor="middle">{escape(text.upper())}</text>')
            bx = bx + tw + 4 if rtl else bx - tw - 4
        out.append("</g>")
    out.append("</svg>")
    return "".join(out), warnings, used_kinds


# --------------------------------------------------------------------- process
STEP_KINDS = {
    "manual": "Manual work",
    "wait": "Waiting",
    "decision": "Decision",
    "auto": "Automated",
    "ai": "Done by the agent",
}


def process_stats(steps: list[dict]) -> dict:
    total = sum(float(s.get("minutes") or 0) for s in steps)
    waiting = sum(float(s.get("minutes") or 0) for s in steps if s.get("kind") == "wait")
    hands = sum(1 for a, b in zip(steps, steps[1:]) if a.get("actor") != b.get("actor"))
    people = sum(float(s.get("minutes") or 0) for s in steps if s.get("kind", "manual") in ("manual", "decision"))
    return {"steps": len(steps), "handoffs": hands, "minutes": total, "waiting": waiting, "hands_on": people,
            "actors": len({s.get("actor") for s in steps})}


def duration(minutes: float) -> str:
    minutes = float(minutes or 0)
    if minutes <= 0:
        return ""
    if minutes < 1:
        return f"{round(minutes * 60)} {t('s')}"
    if minutes < 90:
        return f"{n(round(minutes, 1) if minutes < 10 else round(minutes))} {t('min')}"
    if minutes < 48 * 60:
        return f"{n(round(minutes / 60, 1))} {t('h')}"
    return f"{n(round(minutes / 1440, 1))} {t('d')}"


def lanes(steps: list[dict], lane_order: list[str], rtl: bool = False) -> tuple[str, list[str]]:
    """One lane per actor, one column per step, connectors in the gaps between columns."""
    warnings: list[str] = []
    actors = [a for a in lane_order if any(s.get("actor") == a for s in steps)]
    label_w, lane_h, box_h, gutter = 132, 104, 76, 22
    count = max(len(steps), 1)
    col = min(176, max(112, (WIDTH - label_w - 12) / count))
    width = max(WIDTH, label_w + 12 + col * count)
    height = lane_h * len(actors) + 2
    out = [f'<svg class="diagram lanes" viewBox="0 0 {n(width)} {n(height)}" role="img" aria-label="Process diagram" direction="ltr" xmlns="http://www.w3.org/2000/svg">']
    for i, actor in enumerate(actors):
        y = 1 + i * lane_h
        out.append(f'<rect class="lane{" alt" if i % 2 else ""}" x="0.5" y="{n(y)}" width="{n(width - 1)}" height="{lane_h}"/>')
        lines, cut = wrap(actor, 12, label_w - 28, 3)
        if cut:
            warnings.append(f"process: the actor name '{actor}' was cut; shorten it")
        tx = width - 16 if rtl else 16
        out.append(text_block(lines, tx, y + lane_h / 2 - (len(lines) - 1) * 7.5 + 4, 12, "lane-title", "end" if rtl else "start"))
    out.append(f'<rect class="lane-frame" x="0.5" y="1" width="{n(width - 1)}" height="{n(lane_h * len(actors))}" rx="12"/>')

    boxes = []
    for i, step in enumerate(steps):
        column = count - 1 - i if rtl else i
        base = 6 if rtl else label_w + 6
        x = base + column * col + gutter / 2
        y = 1 + actors.index(step.get("actor")) * lane_h + (lane_h - box_h) / 2
        boxes.append((x, y, col - gutter))
    connectors = []
    for (ax, ay, aw), (bx, by, bw) in zip(boxes, boxes[1:]):
        start = (ax, ay + box_h / 2) if rtl else (ax + aw, ay + box_h / 2)
        end = (bx + bw, by + box_h / 2) if rtl else (bx, by + box_h / 2)
        mid = (start[0] + end[0]) / 2
        pts = [start, end] if abs(ay - by) < 1 else [start, (mid, start[1]), (mid, end[1]), end]
        connectors.append(arrow(pts, "flow"))
    out.extend(connectors)
    for i, (step, (x, y, w)) in enumerate(zip(steps, boxes)):
        kind = step.get("kind", "manual") if step.get("kind") in STEP_KINDS else "manual"
        out.append(f'<g class="step {kind}"><rect class="step-box" x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{box_h}" rx="9"/>')
        time = duration(step.get("minutes", 0))
        title, cut = wrap(step.get("title", ""), 11.5, w - 14, 3)
        if cut:
            warnings.append(f"process: step {i + 1} '{step.get('title')}' was cut; keep step names to a few words")
        block = len(title) * 14 + (15 if time else 0)
        ty = y + (box_h - block) / 2 + 10.5
        out.append(text_block(title, x + w / 2, ty, 11.5, "step-title", "middle", 14 / 11.5))
        if time:
            out.append(f'<text class="step-time" x="{n(x + w / 2)}" y="{n(ty + len(title) * 14 + 1.5)}" font-size="10.5" text-anchor="middle">{escape(time)}</text>')
        cx = x + w - 2 if rtl else x + 2
        out.append(f'<circle class="step-num-bg" cx="{n(cx)}" cy="{n(y + 2)}" r="9"/><text class="step-num" x="{n(cx)}" y="{n(y + 5.5)}" font-size="9.5" text-anchor="middle">{i + 1}</text></g>')
    out.append("</svg>")
    return "".join(out), warnings


def timebar(steps: list[dict], scale: float) -> str:
    """Where the time goes: one stacked bar, a segment per step, on a shared scale."""
    total = sum(float(s.get("minutes") or 0) for s in steps)
    if total <= 0 or scale <= 0:
        return ""
    parts = []
    for i, step in enumerate(steps):
        minutes = float(step.get("minutes") or 0)
        if minutes <= 0:
            continue
        kind = step.get("kind", "manual") if step.get("kind") in STEP_KINDS else "manual"
        tip = escape(f"{i + 1}. {step.get('title', '')}: {duration(minutes)}", quote=True)
        parts.append(f'<span class="seg {kind}" style="flex:{n(minutes)} 1 0" title="{tip}"></span>')
    share = max(total / scale * 100, 1.5)
    return f'<div class="timebar"><div class="timebar-fill" style="width:{n(share)}%">{"".join(parts)}</div></div>'


# ------------------------------------------------------------------- waterfall
def number(value: float) -> str:
    value = float(value)
    if abs(value) >= 1000 or value == int(value):
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def waterfall(spec: dict) -> tuple[str, list[str]]:
    """Contributions that add up to a total; the total bar is computed, never given."""
    warnings: list[str] = []
    items = list(spec.get("items", []))
    unit = spec.get("unit", "")
    w, h, top, bottom, left = 720, 310, 34, 50, 8
    running, spans = 0.0, []
    for item in items:
        value = float(item.get("value") or 0)
        spans.append((running, running + value, item))
        running += value
    low = min([0.0] + [min(a, b) for a, b, _ in spans])
    high = max([0.0] + [max(a, b) for a, b, _ in spans]) or 1.0
    plot = h - top - bottom

    def y_of(value: float) -> float:
        return top + (high - value) / (high - low) * plot

    count = len(spans) + 1
    slot = (w - 2 * left) / count
    bar = min(84, slot * 0.62)
    out = [f'<svg class="diagram waterfall" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(spec.get("title", "Value build-up"), quote=True)}" direction="ltr" xmlns="http://www.w3.org/2000/svg">']
    out.append(f'<line class="axis" x1="{left}" x2="{w - left}" y1="{n(y_of(0))}" y2="{n(y_of(0))}"/>')
    for i, (a, b, item) in enumerate(spans + [(0.0, running, {"label": spec.get("total_label") or t("Total"), "total": True})]):
        x = left + i * slot + (slot - bar) / 2
        y1, y2 = y_of(max(a, b)), y_of(min(a, b))
        cls = "total" if item.get("total") else ("neg" if b < a else "pos")
        out.append(f'<rect class="wf {cls}" x="{n(x)}" y="{n(y1)}" width="{n(bar)}" height="{n(max(y2 - y1, 1.5))}" rx="3"/>')
        if i < len(spans):
            out.append(f'<line class="wf-link" x1="{n(x + bar)}" x2="{n(x + slot)}" y1="{n(y_of(b))}" y2="{n(y_of(b))}"/>')
        value = b - a
        sign = "" if item.get("total") or value < 0 else "+"
        label = f"{sign}{number(value)}".replace("-", "−")
        out.append(f'<text class="wf-value {cls}" x="{n(x + bar / 2)}" y="{n(y1 - 7)}" font-size="13" text-anchor="middle">{escape(label)}</text>')
        lines, cut = wrap(item.get("label", ""), 11, slot - 8, 3)
        if cut:
            warnings.append(f"impact: the waterfall label '{item.get('label')}' was cut; shorten it")
        out.append(text_block(lines, x + bar / 2, h - bottom + 18, 11, "wf-label", "middle"))
    if unit:
        out.append(f'<text class="wf-unit" x="{left}" y="14" font-size="11">{escape(unit)}</text>')
    out.append("</svg>")
    return "".join(out), warnings


# ------------------------------------------------------------------------ hero
def backdrop(seed: str) -> str:
    """A quiet backdrop for the hero: a grid that fades out and two soft lights."""
    shift = sum(ord(c) for c in seed) % 160
    lines = "".join(f'<line x1="{x}" y1="0" x2="{x}" y2="520"/>' for x in range(0, 1441, 48))
    lines += "".join(f'<line x1="0" y1="{y}" x2="1440" y2="{y}"/>' for y in range(0, 521, 48))
    return (
        '<svg class="backdrop" viewBox="0 0 1440 520" preserveAspectRatio="xMidYMid slice" aria-hidden="true" direction="ltr" xmlns="http://www.w3.org/2000/svg">'
        '<defs><radialGradient id="glow-a" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="var(--accent)" stop-opacity=".34"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="glow-b" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="var(--accent2)" stop-opacity=".26"/><stop offset="1" stop-color="var(--accent2)" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="fade" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".55" stop-color="#fff" stop-opacity=".5"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>'
        '<mask id="grid-mask"><rect width="1440" height="520" fill="url(#fade)"/></mask></defs>'
        f'<circle cx="{1040 + shift}" cy="120" r="420" fill="url(#glow-a)"/><circle cx="{1280 - shift}" cy="470" r="340" fill="url(#glow-b)"/>'
        f'<g class="backdrop-grid" mask="url(#grid-mask)">{lines}</g></svg>'
    )
