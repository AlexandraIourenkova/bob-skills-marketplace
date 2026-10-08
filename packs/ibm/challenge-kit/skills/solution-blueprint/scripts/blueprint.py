#!/usr/bin/env python3
"""Solution blueprint: one JSON spec in, one self-contained HTML document out.

    blueprint.py init challenge/blueprint.json          write the example spec (never overwrites)
    blueprint.py check challenge/blueprint.json         problems and warnings, nothing written
    blueprint.py render challenge/blueprint.json -o challenge/blueprint.html [--theme carbon] [--mode present]
    blueprint.py themes                                 list the built-in themes
    blueprint.py labels                                 the fixed labels of the page, to translate
    blueprint.py theme midnight -o challenge/theme.json write a theme file other tools can read

Standard library only. The script never touches the network, reads the spec and an
optional theme file, and writes only the path given with -o. Every string from the
spec is escaped before it reaches the page.
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagrams  # noqa: E402

FIXED = [
    "Plan: nothing here is built yet",
    "As built: drawn from the working proof of concept",
    "Idea board",
    "Who lives with it",
    "What happens today",
    "What it costs",
    "Why now",
    "The problem",
    "Problem",
    "Who it helps",
    "The demo moment",
    "Why it can win",
    "Main risk",
    "Recommended",
    "Ideas worth three weeks",
    "Ideas",
    "Today",
    "With the solution",
    "steps",
    "hand-offs",
    "roles",
    "end to end",
    "waiting",
    "End-to-end time",
    "Hands-on time",
    "Steps",
    "Hand-offs",
    "Step times",
    "see the assumptions section",
    "The bar under each diagram is its elapsed time, both on one scale.",
    "The work before and after",
    "Process",
    "IBM technology",
    "Planned or mocked, not built yet",
    "IBM technology in this solution",
    "How it is built",
    "Architecture",
    "Before",
    "After",
    "How the value adds up",
    "Where it goes next",
    "What changes, in numbers",
    "Impact",
    "What is different here",
    "yes",
    "partly",
    "no",
    "What people would use instead",
    "Alternatives",
    "What the demo shows",
    "Demo",
    "From first click to daily use",
    "Adoption",
    "Gate",
    "From proof of concept to production",
    "Roadmap",
    "Open",
    "How this answers the judging criteria",
    "Criteria",
    "Risk",
    "Level",
    "What we do about it",
    "Assumption",
    "How to check it",
    "Sources",
    "What could go wrong, and what we assumed",
    "Risks",
    "Measured",
    "Estimate",
    "less",
    "Completeness and feasibility",
    "Creativity and innovation",
    "Design and usability",
    "Effectiveness and efficiency",
    "New application",
    "Modernisation",
    "Bob with MCP",
    "AI agent",
    "Other",
    "Manual work",
    "Waiting",
    "Decision",
    "Automated",
    "Done by the agent",
    "People",
    "Interface",
    "Agent",
    "Model",
    "Tool or API",
    "Data",
    "Existing system",
    "Service",
    "min",
    "h",
    "d",
    "s",
    "planned",
    "mock",
    "Total",
    "Numbers carry a mark: measured, estimate or assumption. Built with IBM Bob and the challenge-kit pack.",
    "Scores are the team's own estimate against the four judging criteria, five points each. They rank the ideas against each other and predict nothing about the judges.",
]

t = diagrams.t
FOOTER = "Numbers carry a mark: measured, estimate or assumption. Built with IBM Bob and the challenge-kit pack."
SCORE_NOTE = ("Scores are the team's own estimate against the four judging criteria, five points each. "
              "They rank the ideas against each other and predict nothing about the judges.")

BASES = {"measured": "Measured", "estimate": "Estimate", "assumption": "Assumption"}
CRITERIA = [
    ("completeness", "Completeness and feasibility"),
    ("creativity", "Creativity and innovation"),
    ("usability", "Design and usability"),
    ("effectiveness", "Effectiveness and efficiency"),
]
DIRECTIONS = {"new-app": "New application", "modernise": "Modernisation", "mcp": "Bob with MCP", "agent": "AI agent", "other": "Other"}

SANS = "'IBM Plex Sans', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, 'SF Mono', Consolas, monospace"
THEMES = {
    "carbon": {
        "name": "Carbon", "tagline": "White canvas, IBM blue, engineered and calm", "dark": False,
        "colors": {"bg": "#FFFFFF", "surface": "#F4F6F9", "text": "#161616", "muted": "#566070", "accent": "#0F62FE",
                   "accent2": "#8A3FFC", "line": "#D5DAE1", "on_accent": "#FFFFFF",
                   "chart": ["#0F62FE", "#8A3FFC", "#007D79", "#D12771", "#B28600", "#4589FF"]},
        "fonts": {"heading": "IBM Plex Sans", "body": "IBM Plex Sans", "mono": "IBM Plex Mono", "css_heading": SANS, "css_body": SANS, "css_mono": MONO},
    },
    "midnight": {
        "name": "Midnight", "tagline": "Deep navy, cyan and violet light, made for a screen", "dark": True,
        "colors": {"bg": "#0B1020", "surface": "#141B31", "text": "#EEF2FB", "muted": "#9AA6C1", "accent": "#4CC9F0",
                   "accent2": "#B197FC", "line": "#28324F", "on_accent": "#06101F",
                   "chart": ["#4CC9F0", "#B197FC", "#3DDBB4", "#FF7EB6", "#FFD166", "#82AAFF"]},
        "fonts": {"heading": "IBM Plex Sans", "body": "IBM Plex Sans", "mono": "IBM Plex Mono", "css_heading": SANS, "css_body": SANS, "css_mono": MONO},
    },
    "editorial": {
        "name": "Editorial", "tagline": "Warm paper, serif headlines, the look of a printed report", "dark": False,
        "colors": {"bg": "#FBF8F2", "surface": "#F2EDE2", "text": "#1E1B16", "muted": "#6A6257", "accent": "#0B5D4B",
                   "accent2": "#B4472B", "line": "#DDD4C3", "on_accent": "#FFFFFF",
                   "chart": ["#0B5D4B", "#B4472B", "#2F5D8A", "#8A5A00", "#6B4E9B", "#3E7C6B"]},
        "fonts": {"heading": "Georgia", "body": "Helvetica Neue", "mono": "Menlo",
                  "css_heading": "'Iowan Old Style', 'Palatino Linotype', Georgia, 'Times New Roman', serif",
                  "css_body": "'Helvetica Neue', 'Segoe UI', Arial, sans-serif", "css_mono": MONO},
    },
}


# ------------------------------------------------------------------ small helpers
def e(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def rich(value) -> str:
    """Escaped text in which **words** become bold. No other markup is honoured."""
    parts = e(value).split("**")
    if len(parts) % 2 == 0:
        return "**".join(parts)
    return "".join(f"<strong>{p}</strong>" if i % 2 else p for i, p in enumerate(parts))


def items_of(section) -> list:
    if isinstance(section, dict):
        return list(section.get("items") or [])
    return list(section or [])


def head_of(section, default: str) -> tuple[str, str]:
    if isinstance(section, dict):
        return section.get("headline") or t(default), section.get("lead") or ""
    return t(default), ""


def basis_tag(basis: str | None, source: str | None = None) -> str:
    if basis not in BASES:
        return ""
    tip = f' title="{e(source)}"' if source else ""
    return f'<span class="basis {basis}"{tip}><i></i>{e(t(BASES[basis]))}</span>'


def shift(before: float, after: float) -> str:
    """The change in words a reader takes in at a glance: a percentage, or a factor when it is large."""
    if not before or before == after:
        return ""
    ratio = after / before
    if ratio >= 2:
        return f"×{diagrams.n(round(ratio, 1))}"
    if 0 < ratio <= 0.2:
        return f"{round(1 / ratio)}× {t('less')}"
    return f"{round((after - before) / before * 100):+d}%".replace("-", "−")


def hex_ok(value) -> bool:
    if not isinstance(value, str) or len(value) not in (4, 7) or not value.startswith("#"):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in value[1:])


def load_theme(name: str) -> dict:
    if name in THEMES:
        return THEMES[name]
    path = Path(name)
    if not path.is_file():
        raise SystemExit(f"theme '{name}' is neither a built-in theme ({', '.join(THEMES)}) nor a file")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    base = json.loads(json.dumps(THEMES["midnight" if loaded.get("dark") else "carbon"]))
    for group in ("colors", "fonts"):
        for key, value in (loaded.get(group) or {}).items():
            if group == "colors" and key == "chart":
                if isinstance(value, list) and all(hex_ok(v) for v in value) and value:
                    base["colors"]["chart"] = (value * 6)[:6]
            elif group == "colors":
                if hex_ok(value):
                    base["colors"][key] = value
            elif isinstance(value, str) and not any(c in value for c in "<>{};"):
                base["fonts"][key] = value
    base["name"] = str(loaded.get("name") or path.stem)
    base["dark"] = bool(loaded.get("dark"))
    return base


# ------------------------------------------------------------------------- check
def check(spec: dict) -> tuple[list[str], list[str]]:
    """Errors stop the render; warnings are shown and the render goes on."""
    errors: list[str] = []
    warnings: list[str] = []
    meta = spec.get("meta") or {}
    if not meta.get("title"):
        errors.append("meta.title is missing")
    status = meta.get("status", "plan")
    if status not in ("plan", "as-built", "ideas"):
        errors.append("meta.status must be 'plan', 'as-built' or 'ideas'")

    def need_basis(where: str, item: dict) -> None:
        if item.get("basis") not in BASES:
            errors.append(f"{where}: every number needs \"basis\": measured, estimate or assumption")
        elif item["basis"] != "assumption" and not item.get("source"):
            warnings.append(f"{where}: say in \"source\" how the number was measured or estimated")

    hero = spec.get("hero")
    if hero:
        if not hero.get("value") or not hero.get("label"):
            errors.append("hero needs value and label")
        need_basis("hero", hero)
    elif status != "ideas" and not meta.get("partial"):
        warnings.append("hero is missing: the document opens best with the one number that matters")

    for i, fact in enumerate(items_of((spec.get("problem") or {}).get("facts"))):
        need_basis(f"problem.facts[{i}]", fact)

    for i, idea in enumerate(items_of(spec.get("ideas"))):
        scores = idea.get("scores") or {}
        for key, name in CRITERIA:
            value = scores.get(key)
            if not isinstance(value, (int, float)) or not 1 <= value <= 5:
                errors.append(f"ideas[{i}] '{idea.get('title', '?')}': scores.{key} must be a number from 1 to 5 ({name})")
        for key in ("who", "demo", "why", "risk"):
            if not idea.get(key):
                warnings.append(f"ideas[{i}] '{idea.get('title', '?')}': '{key}' is empty, so the card argues less than the others")
    ideas = items_of(spec.get("ideas"))
    if ideas and sum(1 for i in ideas if i.get("recommended")) != 1:
        warnings.append("ideas: mark exactly one idea as recommended and say why in its 'verdict'")
    if ideas and len({i.get("direction") for i in ideas}) < min(3, len(ideas)):
        warnings.append("ideas: the ideas cover fewer than three directions; a board of look-alikes is not a choice")

    process = spec.get("process") or {}
    for side in ("before", "after"):
        steps = (process.get(side) or {}).get("steps") or []
        for i, step in enumerate(steps):
            if not step.get("actor") or not step.get("title"):
                errors.append(f"process.{side}.steps[{i}] needs actor and title")
            if step.get("kind", "manual") not in diagrams.STEP_KINDS:
                errors.append(f"process.{side}.steps[{i}].kind must be one of {', '.join(diagrams.STEP_KINDS)}")
            if not isinstance(step.get("minutes", 0), (int, float)):
                errors.append(f"process.{side}.steps[{i}].minutes must be a number")
        if len(steps) > 10:
            warnings.append(f"process.{side} has {len(steps)} steps; merge steps until ten or fewer remain, the diagram reads as a wall otherwise")
        if steps and all(not s.get("minutes") for s in steps):
            warnings.append(f"process.{side} has no minutes, so the time bar and the totals are left out")
    if process and process.get("basis") not in BASES and (process.get("before") or process.get("after")):
        errors.append("process.basis is missing: say whether the step times are measured, estimate or assumption")

    arch = spec.get("architecture") or {}
    ids: dict[str, str] = {}
    layers = arch.get("layers") or []
    for li, layer in enumerate(layers):
        nodes = layer.get("nodes") or []
        if not nodes:
            errors.append(f"architecture.layers[{li}] '{layer.get('title', '?')}' has no nodes")
        if len(nodes) > 5:
            warnings.append(f"architecture layer '{layer.get('title', '?')}' has {len(nodes)} nodes; five is the limit for readable text, group the rest")
        for node in nodes:
            if not node.get("id") or not node.get("title"):
                errors.append(f"architecture layer '{layer.get('title', '?')}': every node needs id and title")
            elif node["id"] in ids:
                errors.append(f"architecture: node id '{node['id']}' is used twice")
            else:
                ids[node["id"]] = node.get("status", "built")
            if node.get("kind") and node["kind"] not in diagrams.KINDS:
                errors.append(f"architecture node '{node.get('id')}': kind must be one of {', '.join(diagrams.KINDS)}")
    if len(layers) > 6:
        warnings.append("architecture has more than six layers; a reader keeps four or five in mind")
    for i, edge in enumerate(arch.get("edges") or []):
        for end in ("from", "to"):
            if edge.get(end) not in ids:
                errors.append(f"architecture.edges[{i}].{end} names '{edge.get(end)}', which is not a node id")
    if layers and not any(node.get("ibm") for layer in layers for node in layer.get("nodes") or []):
        warnings.append("architecture: no node is marked \"ibm\": true; the judges ask how clear the use of IBM technology is")
    linked = {edge.get(end) for edge in arch.get("edges") or [] for end in ("from", "to")}
    for node_id in ids:
        if node_id not in linked and len(ids) > 1:
            warnings.append(f"architecture: node '{node_id}' has no connector; connect it or remove it")
    if status == "as-built":
        for layer in layers:
            for node in layer.get("nodes") or []:
                if node.get("status") not in ("planned", "mock") and node.get("kind") not in ("user", "external") and not node.get("evidence"):
                    warnings.append(f"architecture: node '{node.get('id')}' is drawn as built; name the file or resource that proves it in \"evidence\", or mark it planned")
    if status == "as-built" and any(state == "planned" for state in ids.values()):
        warnings.append("status is as-built, yet some nodes are planned; they are drawn dashed, check that this is what you mean")

    impact = spec.get("impact") or {}
    for i, metric in enumerate(impact.get("metrics") or []):
        for key in ("before", "after"):
            if not isinstance(metric.get(key), (int, float)):
                errors.append(f"impact.metrics[{i}].{key} must be a number")
        if metric.get("better", "lower") not in ("lower", "higher"):
            errors.append(f"impact.metrics[{i}].better must be 'lower' or 'higher'")
        need_basis(f"impact.metrics[{i}] '{metric.get('label', '?')}'", metric)
    waterfall = impact.get("waterfall") or {}
    for i, item in enumerate(waterfall.get("items") or []):
        if not isinstance(item.get("value"), (int, float)):
            errors.append(f"impact.waterfall.items[{i}].value must be a number")
        if item.get("basis") not in BASES:
            errors.append(f"impact.waterfall.items[{i}] '{item.get('label', '?')}' needs a basis")
    if len(waterfall.get("items") or []) > 7:
        warnings.append("impact.waterfall has more than seven items; merge the small ones")

    alternatives = spec.get("alternatives") or {}
    columns = alternatives.get("criteria") or []
    options = alternatives.get("options") or []
    for option in options:
        if len(option.get("values") or []) != len(columns):
            errors.append(f"alternatives: option '{option.get('name', '?')}' needs one value per criterion ({len(columns)})")
    if options and sum(1 for o in options if o.get("ours")) != 1:
        warnings.append("alternatives: mark exactly one option with \"ours\": true")
    if options and not any("nothing" in str(o.get("name", "")).lower() or o.get("status_quo") for o in options):
        warnings.append("alternatives: add the option of doing nothing (\"status_quo\": true); it is the competitor every proposal meets")

    for i, row in enumerate(items_of(spec.get("criteria"))):
        if not row.get("evidence"):
            warnings.append(f"criteria[{i}] '{row.get('name', '?')}' has no evidence")

    used = {m.get("basis") for m in impact.get("metrics") or []} | {(hero or {}).get("basis"), process.get("basis")}
    used |= {i.get("basis") for i in waterfall.get("items") or []}
    if "assumption" in used and not items_of(spec.get("assumptions")):
        warnings.append("some numbers are assumptions, yet the assumptions section is empty: list each one and how to check it")

    labels = spec.get("labels") or {}
    if not isinstance(labels, dict):
        errors.append("labels must be an object that maps a fixed English label to its translation")
    else:
        for key in labels:
            if key not in FIXED:
                warnings.append(f"labels: '{key}' is not a label of the page; run `blueprint.py labels` for the list")
        if meta.get("language", "en") not in ("en", "") and not labels:
            warnings.append(f"the language is '{meta.get('language')}', yet labels is empty: the fixed labels of the page stay English; run `blueprint.py labels`")
    if status != "ideas" and not meta.get("partial"):
        wanted = {"process": "the before and after of the work", "architecture": "feasibility and the IBM technology used",
                  "impact": "measurable impact (Effectiveness and efficiency)", "alternatives": "differentiation (Creativity and innovation)",
                  "adoption": "how fast people can start using it (Design and usability)", "roadmap": "the way from proof of concept to production"}
        for key, why in wanted.items():
            if not spec.get(key):
                warnings.append(f"section '{key}' is missing: it shows {why}")
    return errors, warnings


# ---------------------------------------------------------------------- sections
class Page:
    def __init__(self, spec: dict):
        self.spec = spec
        self.meta = spec.get("meta") or {}
        self.rtl = self.meta.get("direction") == "rtl"
        self.sections: list[tuple[str, str, str]] = []
        self.warnings: list[str] = []

    def add(self, key: str, label: str, headline: str, lead: str, body: str) -> None:
        number = f"{len(self.sections) + 1:02d}"
        label = t(label)
        lead_html = f'<p class="lead">{rich(lead)}</p>' if lead else ""
        self.sections.append((key, label, (
            f'<section id="{key}"><div class="wrap"><header class="sec-head"><div class="kicker"><b>{number}</b>{e(label)}</div>'
            f'<h2>{rich(headline)}</h2>{lead_html}</header>{body}</div></section>')))


def hero_html(page: Page) -> str:
    meta, hero = page.meta, page.spec.get("hero") or {}
    status = meta.get("status", "plan")
    chip = {"plan": "Plan: nothing here is built yet", "as-built": "As built: drawn from the working proof of concept", "ideas": "Idea board"}[status]
    chip = t(chip)
    facts = [meta.get("team"), meta.get("challenge"), meta.get("date")]
    line = "".join(f"<span>{e(f)}</span>" for f in facts if f)
    number = ""
    if hero:
        note = f'<p class="hero-note">{rich(hero.get("note"))}</p>' if hero.get("note") else ""
        number = (f'<div class="hero-number"><div class="hero-value">{e(hero.get("value"))}</div><div class="hero-label">{rich(hero.get("label"))}</div>'
                  f'{basis_tag(hero.get("basis"), hero.get("source"))}{note}</div>')
    tagline = f'<p class="tagline">{rich(meta.get("tagline"))}</p>' if meta.get("tagline") else ""
    return (f'<header class="hero" id="top">{diagrams.backdrop(str(meta.get("title", "")))}<div class="wrap hero-grid"><div>'
            f'<div class="chip {status}">{e(chip)}</div><h1>{rich(meta.get("title"))}</h1>{tagline}<div class="hero-meta">{line}</div></div>{number}</div></header>')


def problem(page: Page) -> None:
    data = page.spec.get("problem")
    if not data:
        return
    rows = []
    for key, label in (("who", "Who lives with it"), ("today", "What happens today"), ("cost", "What it costs"), ("why_now", "Why now")):
        if data.get(key):
            rows.append(f'<div class="fact-row"><dt>{e(t(label))}</dt><dd>{rich(data[key])}</dd></div>')
    tiles = []
    for fact in items_of(data.get("facts")):
        tiles.append(f'<div class="tile"><div class="tile-value">{e(fact.get("value"))}</div><div class="tile-label">{rich(fact.get("label"))}</div>'
                     f'{basis_tag(fact.get("basis"), fact.get("source"))}</div>')
    quote = f'<blockquote>{rich(data["quote"])}<cite>{e(data.get("quote_by", ""))}</cite></blockquote>' if data.get("quote") else ""
    body = f'<div class="split"><dl class="facts">{"".join(rows)}</dl><div><div class="tiles">{"".join(tiles)}</div>{quote}</div></div>'
    headline, lead = head_of(data, "The problem")
    page.add("problem", "Problem", headline, lead, body)


def pips(score) -> str:
    return "".join('<i class="on"></i>' if p < float(score or 0) else "<i></i>" for p in range(5))


def ideas(page: Page) -> None:
    section = page.spec.get("ideas")
    cards = []
    for idea in items_of(section):
        scores = idea.get("scores") or {}
        total = sum(float(scores.get(k) or 0) for k, _ in CRITERIA)
        bars = "".join(f'<div class="score"><span>{e(t(name))}</span><div class="pips">{pips(scores.get(key))}</div><b>{diagrams.n(float(scores.get(key) or 0))}</b></div>'
                       for key, name in CRITERIA)
        rows = "".join(f'<div class="fact-row"><dt>{e(t(label))}</dt><dd>{rich(idea[key])}</dd></div>' for key, label in
                       (("who", "Who it helps"), ("demo", "The demo moment"), ("why", "Why it can win"), ("risk", "Main risk")) if idea.get(key))
        ribbon = f'<div class="ribbon">{e(t("Recommended"))}</div>' if idea.get("recommended") else ""
        verdict = f'<p class="verdict">{rich(idea["verdict"])}</p>' if idea.get("verdict") else ""
        direction = t(DIRECTIONS[idea["direction"]]) if idea.get("direction") in DIRECTIONS else idea.get("direction") or ""
        cards.append(f'<article class="idea{" pick" if idea.get("recommended") else ""}">{ribbon}<div class="idea-top"><span class="pill">{e(direction)}</span>'
                     f'<span class="total"><b>{diagrams.n(total)}</b>/20</span></div><h3>{rich(idea.get("title"))}</h3><p class="pitch">{rich(idea.get("pitch"))}</p>'
                     f'<dl class="facts tight">{rows}</dl><div class="scores">{bars}</div>{verdict}</article>')
    if cards:
        headline, lead = head_of(section, "Ideas worth three weeks")
        note = f'<p class="fine">{e(t(SCORE_NOTE))}</p>'
        page.add("ideas", "Ideas", headline, lead, f'<div class="idea-grid">{"".join(cards)}</div>{note}')


def process(page: Page) -> None:
    data = page.spec.get("process")
    if not data:
        return
    before = (data.get("before") or {}).get("steps") or []
    after = (data.get("after") or {}).get("steps") or []
    order: list[str] = []
    for step in before + after:
        if step.get("actor") and step["actor"] not in order:
            order.append(step["actor"])
    stats_b, stats_a = diagrams.process_stats(before), diagrams.process_stats(after)
    scale = max(stats_b["minutes"], stats_a["minutes"])
    blocks = []
    for name, side, steps, stats in (("Today", "before", before, stats_b), ("With the solution", "after", after, stats_a)):
        if not steps:
            continue
        svg, warnings = diagrams.lanes(steps, order, page.rtl)
        page.warnings += warnings
        title = (data.get(side) or {}).get("title") or t(name)
        figures = [f"<b>{stats['steps']}</b> {e(t('steps'))}", f"<b>{stats['handoffs']}</b> {e(t('hand-offs'))}", f"<b>{stats['actors']}</b> {e(t('roles'))}"]
        if stats["minutes"]:
            figures.append(f"<b>{e(diagrams.duration(stats['minutes']))}</b> {e(t('end to end'))}")
            if stats["waiting"]:
                figures.append(f"<b>{round(stats['waiting'] / stats['minutes'] * 100)}%</b> {e(t('waiting'))}")
        blocks.append(f'<figure class="flow {side}"><figcaption><span class="flow-name">{e(title)}</span><span class="flow-stats">{" · ".join(figures)}</span></figcaption>'
                      f'<div class="scroll">{svg}</div>{diagrams.timebar(steps, scale)}</figure>')
    if scale and blocks:
        blocks.append(f'<p class="bar-note">{e(t("The bar under each diagram is its elapsed time, both on one scale."))}</p>')
    deltas = []
    if before and after:
        for label, key, show in (("End-to-end time", "minutes", diagrams.duration), ("Hands-on time", "hands_on", diagrams.duration),
                                 ("Steps", "steps", lambda v: str(int(v))), ("Hand-offs", "handoffs", lambda v: str(int(v)))):
            b, a = stats_b[key], stats_a[key]
            if not b and not a:
                continue
            change = shift(b, a)
            deltas.append(f'<div class="tile"><div class="tile-label">{e(t(label))}</div><div class="tile-pair"><s>{e(show(b) or "0")}</s><span class="to">→</span><b>{e(show(a) or "0")}</b></div>'
                          f'<div class="delta {"good" if a < b else "flat"}">{e(change)}</div></div>')
    kinds = {s.get("kind", "manual") for s in before + after}
    legend = "".join(f'<span class="key k-{k}"><i></i>{e(t(label))}</span>' for k, label in diagrams.STEP_KINDS.items() if k in kinds)
    note = f'<p class="fine">{basis_tag(data.get("basis"), data.get("source"))} {e(t("Step times"))}: {rich(data.get("source") or t("see the assumptions section"))}.</p>'
    body = f'{"".join(blocks)}<div class="legend">{legend}</div><div class="tiles four">{"".join(deltas)}</div>{note}'
    headline, lead = head_of(data, "The work before and after")
    page.add("process", "Process", headline, lead, body)


def architecture(page: Page) -> None:
    data = page.spec.get("architecture")
    if not data or not data.get("layers"):
        return
    svg, warnings, kinds = diagrams.architecture(data, page.rtl)
    page.warnings += warnings
    legend = "".join(f'<span class="key kind" style="--k:{color}"><i></i>{e(t(label))}</span>' for key, (label, color) in diagrams.KINDS.items() if key in kinds)
    nodes = [node for layer in data["layers"] for node in layer.get("nodes") or []]
    if any(node.get("ibm") for node in nodes):
        legend += f'<span class="key ibm"><i>IBM</i>{e(t("IBM technology"))}</span>'
    if any(node.get("status") in ("planned", "mock") for node in nodes):
        legend += f'<span class="key dashed"><i></i>{e(t("Planned or mocked, not built yet"))}</span>'
    ibm = [f"<li><b>{e(node.get('title'))}</b>{' — ' + rich(node['role']) if node.get('role') else ''}</li>" for node in nodes if node.get("ibm")]
    used = f'<div class="callout"><h4>{e(t("IBM technology in this solution"))}</h4><ul>{"".join(ibm)}</ul></div>' if ibm else ""
    decisions = "".join(f'<div class="decision"><h4>{rich(d.get("title"))}</h4><p>{rich(d.get("why"))}</p></div>' for d in data.get("decisions") or [])
    side = f'<div class="split wide">{used}<div class="decisions">{decisions}</div></div>' if used or decisions else ""
    caption = f'<p class="fine">{rich(data["caption"])}</p>' if data.get("caption") else ""
    body = f'<figure class="arch-fig"><div class="scroll">{svg}</div><div class="legend">{legend}</div></figure>{caption}{side}'
    headline, lead = head_of(data, "How it is built")
    page.add("architecture", "Architecture", headline, lead, body)


def impact(page: Page) -> None:
    data = page.spec.get("impact")
    if not data:
        return
    rows = []
    for metric in data.get("metrics") or []:
        before, after = float(metric["before"]), float(metric["after"])
        top = max(abs(before), abs(after)) or 1
        lower = metric.get("better", "lower") == "lower"
        good = after < before if lower else after > before
        change = shift(before, after)
        unit = f' <span class="unit">{e(metric.get("unit"))}</span>' if metric.get("unit") else ""
        rows.append(
            f'<div class="metric"><div class="metric-name">{rich(metric.get("label"))}{basis_tag(metric.get("basis"), metric.get("source"))}</div>'
            f'<div class="bars"><div class="bar-row"><span class="bar-tag">{e(t("Before"))}</span><div class="bar-track"><div class="bar before" style="width:{diagrams.n(abs(before) / top * 100)}%"></div></div><span class="bar-value">{diagrams.number(before)}{unit}</span></div>'
            f'<div class="bar-row"><span class="bar-tag">{e(t("After"))}</span><div class="bar-track"><div class="bar after" style="width:{diagrams.n(max(abs(after) / top * 100, 0.6))}%"></div></div><span class="bar-value"><b>{diagrams.number(after)}</b>{unit}</span></div></div>'
            f'<div class="delta big {"good" if good else "bad"}">{e(change)}</div></div>')
    chart = ""
    waterfall = data.get("waterfall")
    if waterfall and waterfall.get("items"):
        svg, warnings = diagrams.waterfall(waterfall)
        page.warnings += warnings
        basis = "".join(f'<li>{rich(item.get("label"))}: {basis_tag(item.get("basis"), item.get("source"))} {rich(item.get("source") or "")}</li>' for item in waterfall["items"])
        chart = (f'<figure class="card"><figcaption>{rich(waterfall.get("title") or t("How the value adds up"))}</figcaption>{svg}'
                 f'<ul class="fine basis-list">{basis}</ul></figure>')
    scale = "".join(f"<li>{rich(item)}</li>" for item in data.get("scale") or [])
    scale_html = f'<div class="callout"><h4>{e(t("Where it goes next"))}</h4><ul>{scale}</ul></div>' if scale else ""
    body = f'<div class="metrics">{"".join(rows)}</div>{chart}{scale_html}'
    headline, lead = head_of(data, "What changes, in numbers")
    page.add("impact", "Impact", headline, lead, body)


def alternatives(page: Page) -> None:
    data = page.spec.get("alternatives")
    if not data or not data.get("options"):
        return
    marks = {"yes": '<span class="mark yes" title="yes"></span>', "partial": '<span class="mark partial" title="partly"></span>', "no": '<span class="mark no" title="no"></span>'}
    head = "".join(f"<th>{rich(c)}</th>" for c in data.get("criteria") or [])
    rows = []
    for option in data["options"]:
        cells = "".join(f"<td>{marks.get(str(v).lower(), rich(v))}</td>" for v in option.get("values") or [])
        note = f'<small>{rich(option["note"])}</small>' if option.get("note") else ""
        rows.append(f'<tr class="{"ours" if option.get("ours") else ""}"><th scope="row">{rich(option.get("name"))}{note}</th>{cells}</tr>')
    edge = f'<div class="callout"><h4>{e(t("What is different here"))}</h4><p>{rich(data["difference"])}</p></div>' if data.get("difference") else ""
    body = (f'<div class="scroll"><table class="matrix"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="legend"><span class="key"><span class="mark yes"></span>{e(t("yes"))}</span><span class="key"><span class="mark partial"></span>{e(t("partly"))}</span><span class="key"><span class="mark no"></span>{e(t("no"))}</span></div>{edge}')
    headline, lead = head_of(data, "What people would use instead")
    page.add("alternatives", "Alternatives", headline, lead, body)


def strip(page: Page, key: str, label: str, default: str) -> None:
    section = page.spec.get(key)
    steps = items_of(section)
    if not steps:
        return
    cards = []
    for i, step in enumerate(steps, 1):
        time = f'<span class="secs">{e(step["time"])}</span>' if step.get("time") else ""
        cards.append(f'<li><div class="strip-num">{i}</div><h4>{rich(step.get("title"))}{time}</h4><p>{rich(step.get("detail"))}</p></li>')
    extra = ""
    if isinstance(section, dict) and section.get("facts"):
        extra = '<div class="tiles">' + "".join(
            f'<div class="tile"><div class="tile-value">{e(f.get("value"))}</div><div class="tile-label">{rich(f.get("label"))}</div>{basis_tag(f.get("basis"), f.get("source"))}</div>'
            for f in section["facts"]) + "</div>"
    headline, lead = head_of(section, default)
    page.add(key, label, headline, lead, f'<ol class="strip">{"".join(cards)}</ol>{extra}')


def roadmap(page: Page) -> None:
    section = page.spec.get("roadmap")
    phases = items_of(section)
    if not phases:
        return
    cards = []
    for i, phase in enumerate(phases):
        todo = "".join(f"<li>{rich(item)}</li>" for item in phase.get("items") or [])
        gate = f'<div class="gate"><span>{e(t("Gate"))}</span>{rich(phase["gate"])}</div>' if phase.get("gate") else ""
        state = " done" if phase.get("done") else ""
        cards.append(f'<div class="phase{state}"><div class="phase-dot"></div><div class="phase-when">{e(phase.get("duration", ""))}</div><h4>{rich(phase.get("phase"))}</h4><ul>{todo}</ul>{gate}</div>')
    headline, lead = head_of(section, "From proof of concept to production")
    page.add("roadmap", "Roadmap", headline, lead, f'<div class="phases" style="--n:{len(cards)}">{"".join(cards)}</div>')


def criteria(page: Page) -> None:
    section = page.spec.get("criteria")
    rows = items_of(section)
    if not rows:
        return
    cards = []
    for row in rows:
        proof = "".join(f"<li>{rich(item)}</li>" for item in row.get("evidence") or [])
        gap = f'<p class="gap"><span>{e(t("Open"))}</span>{rich(row["gap"])}</p>' if row.get("gap") else ""
        cards.append(f'<div class="card crit"><h4>{rich(row.get("name"))}</h4><ul>{proof}</ul>{gap}</div>')
    headline, lead = head_of(section, "How this answers the judging criteria")
    page.add("criteria", "Criteria", headline, lead, f'<div class="grid two">{"".join(cards)}</div>')


def risks(page: Page) -> None:
    risk_rows = items_of(page.spec.get("risks"))
    assumed = items_of(page.spec.get("assumptions"))
    sources = items_of(page.spec.get("sources"))
    if not (risk_rows or assumed or sources):
        return
    parts = []
    if risk_rows:
        rows = "".join(f'<tr><th scope="row">{rich(r.get("risk"))}</th><td><span class="level {e(str(r.get("level", "medium")).lower())}">{e(r.get("level", "medium"))}</span></td><td>{rich(r.get("mitigation"))}</td></tr>' for r in risk_rows)
        parts.append(f'<div class="scroll"><table class="plain"><thead><tr><th>{e(t("Risk"))}</th><th>{e(t("Level"))}</th><th>{e(t("What we do about it"))}</th></tr></thead><tbody>{rows}</tbody></table></div>')
    if assumed:
        rows = "".join(f'<tr><th scope="row">{rich(a.get("text"))}</th><td>{rich(a.get("check"))}</td></tr>' for a in assumed)
        parts.append(f'<div class="scroll"><table class="plain"><thead><tr><th>{e(t("Assumption"))}</th><th>{e(t("How to check it"))}</th></tr></thead><tbody>{rows}</tbody></table></div>')
    if sources:
        rows = "".join(f"<li><b>{rich(s.get('label'))}</b> {rich(s.get('detail'))}</li>" for s in sources)
        parts.append(f'<div class="callout"><h4>{e(t("Sources"))}</h4><ul>{rows}</ul></div>')
    headline, lead = head_of(page.spec.get("risks"), "What could go wrong, and what we assumed")
    page.add("risks", "Risks", headline, lead, "".join(parts))


# ------------------------------------------------------------------------ render
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def asset(name: str) -> str:
    """The page's stylesheet and presenter keys ship beside the script and are inlined into the page."""
    return (ASSETS / name).read_text(encoding="utf-8").strip()



def css_for(theme: dict) -> str:
    colors, fonts = theme["colors"], theme["fonts"]
    dark = theme.get("dark")
    values = {"bg": colors["bg"], "surface": colors["surface"], "text": colors["text"], "muted": colors["muted"], "accent2": colors["accent2"],
              "accent": colors["accent"], "line": colors["line"], "on_accent": colors["on_accent"],
              "good": "#42D6A4" if dark else "#0E7C5B", "bad": "#FF8389" if dark else "#C2302E", "warn": "#F1C21B" if dark else "#9A6700",
              "css_heading": fonts["css_heading"], "css_body": fonts["css_body"], "css_mono": fonts["css_mono"]}
    values.update({f"c{i}": c for i, c in enumerate((colors["chart"] * 6)[:6])})
    css = asset("blueprint.css")
    for key in sorted(values, key=len, reverse=True):
        css = css.replace(f"@{key}", values[key])
    return css


def render(spec: dict, theme: dict, mode: str = "page") -> tuple[str, list[str]]:
    page = Page(spec)
    labels = spec.get("labels") if isinstance(spec.get("labels"), dict) else {}
    diagrams.LABELS = {k: str(v) for k, v in labels.items() if k in FIXED and isinstance(v, (str, int, float))}
    for build in (problem, ideas, process, architecture, impact, alternatives):
        build(page)
    strip(page, "demo", "Demo", "What the demo shows")
    strip(page, "adoption", "Adoption", "From first click to daily use")
    for build in (roadmap, criteria, risks):
        build(page)
    meta = page.meta
    links = "".join(f'<a href="#{key}">{e(label)}</a>' for key, label, _ in page.sections)
    made = " · ".join(e(x) for x in (meta.get("team"), meta.get("date")) if x)
    html = (
        f'<!doctype html><html lang="{e(meta.get("language", "en"))}" dir="{"rtl" if page.rtl else "ltr"}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(meta.get("title"))}</title><style>{css_for(theme)}</style></head>'
        f'<body class="{"present" if mode == "present" else "page"}"><nav class="top"><div class="wrap"><b>{e(meta.get("title"))}</b>{links}</div></nav>'
        f'{hero_html(page)}{"".join(html for _, _, html in page.sections)}'
        f'<footer><div class="wrap"><span>{made}</span><span>{e(t(FOOTER))}</span></div></footer>'
        f'<script>{asset('present.js')}</script></body></html>')
    return html, page.warnings


# --------------------------------------------------------------------------- cli
def read_spec(path: str) -> dict:
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"no such file: {path}")
    except json.JSONDecodeError as error:
        raise SystemExit(f"{path} is not valid JSON: line {error.lineno}, column {error.colno}: {error.msg}")
    if not isinstance(spec, dict):
        raise SystemExit(f"{path}: the spec must be a JSON object")
    return spec


def report(errors: list[str], warnings: list[str]) -> None:
    for line in errors:
        print(f"error: {line}", file=sys.stderr)
    for line in warnings:
        print(f"warning: {line}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a solution blueprint from a JSON spec into one HTML file.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="write the example spec to a new file")
    p.add_argument("path")
    p.add_argument("--ideas", action="store_true", help="write the idea board example instead")
    p = sub.add_parser("check", help="validate a spec and lay out its diagrams without writing anything")
    p.add_argument("spec")
    p = sub.add_parser("render", help="write the HTML document")
    p.add_argument("spec")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--theme", default="carbon", help="carbon, midnight, editorial, or a theme.json file")
    p.add_argument("--mode", choices=("page", "present"), default="page", help="present: one section per screen, arrow keys move")
    sub.add_parser("themes", help="list the built-in themes")
    sub.add_parser("labels", help="print the fixed labels of the page as JSON, ready to translate into the spec's \"labels\"")
    p = sub.add_parser("theme", help="write a built-in theme as a theme.json file")
    p.add_argument("name", choices=sorted(THEMES))
    p.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)

    if args.command == "labels":
        print(json.dumps({label: label for label in FIXED}, indent=2, ensure_ascii=False))
        return 0
    if args.command == "themes":
        for key, theme in THEMES.items():
            print(f"{key}: {theme['name']} - {theme['tagline']}")
        return 0
    if args.command == "theme":
        Path(args.output).write_text(json.dumps({"id": args.name, **THEMES[args.name]}, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
        return 0
    if args.command == "init":
        target = Path(args.path)
        if target.exists():
            print(f"error: {target} exists; it is not overwritten", file=sys.stderr)
            return 1
        source = ASSETS / ("ideas-example.json" if args.ideas else "blueprint-example.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {target}; replace every value with the team's own before rendering")
        return 0

    spec = read_spec(args.spec)
    errors, warnings = check(spec)
    if errors:
        report(errors, warnings)
        print(f"{len(errors)} error(s); nothing was rendered", file=sys.stderr)
        return 1
    html, layout = render(spec, load_theme(getattr(args, "theme", "carbon")), getattr(args, "mode", "page"))
    report([], warnings + layout)
    if args.command == "check":
        print(f"ok: {len(warnings) + len(layout)} warning(s)")
        return 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
