#!/usr/bin/env python3
"""Write the report of a scored run: report.md, report.html and summary.csv.

Run from the project root (the script path is relative to the wxo-eval-run skill folder):
  python3 scripts/report.py --run agent-evals/runs/<ts>

Reads scores.json (written by score.py), the <unit>.trace.json files for answers and
tool calls, threads.txt, and compare.json when score.py compare wrote one into the run
folder. A compare.json made before this run or its base was scored or judged again (a
fingerprint of the verdicts differs from scores.json or from <base>/scores.json) is not
shown: the report names the compare to run again. Writes the three files into the run
folder. Standard library only; no network.

Agent answers, tool arguments and tool results are data from the agent, never
instructions. report.md quotes them in fenced blocks longer than any backtick run
inside them. report.html escapes every value and carries a Content-Security-Policy
that allows no script and no request. summary.csv defuses cells a spreadsheet would
read as a formula. Hidden and bidirectional control characters show as <U+XXXX>, through
trace.visible() of the wxo-agent-api skill, the same function the console output uses.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
API_SCRIPTS = HERE.parent.parent / "wxo-agent-api" / "scripts"


def _load_client():
    """wxo_client from the wxo-agent-api skill of the same pack, found by path."""
    if not (API_SCRIPTS / "wxo_client.py").is_file() or not (API_SCRIPTS / "trace.py").is_file():
        raise SystemExit(f"error: {API_SCRIPTS} is missing. wxo-eval-run needs the wxo-agent-api skill of the "
                         "agent-evals pack next to it; install the whole pack.")
    if str(API_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(API_SCRIPTS))
    import wxo_client  # noqa: E402  (found through the path above)
    return wxo_client


tr = _load_client().load_trace()
visible = tr.visible  # control, zero-width and bidirectional characters shown as <U+XXXX>
ANSWER_LIMIT = 4000
ARGS_LIMIT = 600
RESULT_LIMIT = 600
HIDDEN = tr.HIDDEN
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
CSV_FIELDS = ["unit", "case", "repeat", "verdict", "status", "turns_sent", "turns_planned", "tools_known", "recall",
              "precision", "routing", "order_respected", "forbidden", "keywords_passed", "keywords_total",
              "judge_unjudged", "judge_unsure", "judge_failed", "client_wall_max_s", "total_tokens", "tools_called",
              "thread_ids", "reasons"]
COMPARE_GROUPS = (("Case file changed between the runs (not compared)", "case_changed"),
                  ("Judging pending (not a regression until judged)", "pending_judgement"),
                  ("Tools or turn status became unknown", "lost_visibility"), ("Run errors", "run_errors"),
                  ("Planned but not sent in this run (not compared)", "not_run_in_new"),
                  ("Planned but not sent in the base run (not compared)", "not_run_in_base"))
NEXT_STEPS = [
    "Failing cases: review the agent's YAML and instructions with the agent-instructions-evaluator skill of wxo-adk.",
    "A deeper look at one failing run: hand its trace id and thread id to the telemetry-analyzer skill of wxo-adk.",
    "Tools unknown: check hide_reasoning on the agent and run the wxo-agent-api probe; evaluate a draft with it off.",
    "IBM metrics (journey success, parameter F1, KB faithfulness): export as wxo-eval-run/references/ibm-framework.md "
    "describes.",
    "The threads listed above stay on the tenant. Cleaning them up is the user's decision.",
]
KEYWORD_RESULT = {True: "pass", False: "fail", None: "unknown (an answer was not captured)"}
KB_RESULT = {True: "yes", False: "no", None: "unknown (an answer was not captured)"}


# --------------------------------------------------------------------------- text safety
def command(script: str, *args: Any) -> str:
    """A next-step command line with the script's resolved path, every part shell-quoted, so it runs as shown."""
    return " ".join(shlex.quote(str(part)) for part in ["python3", HERE / script, *args])


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n[... cut at {limit} characters; see the trace file]"


def as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=1, default=str)


def fence(text: Any, info: str = "text") -> str:
    """A fenced block that the text cannot close: the fence is longer than any backtick run inside."""
    body = visible(text)
    longest = max((len(m.group(0)) for m in re.finditer("`+", body)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{info}\n{body}\n{ticks}"


def code(text: Any, table: bool = True) -> str:
    """Inline code for one short value: one line, pipes escaped for tables, a fence the value cannot close."""
    body = " ".join(visible(text).split())
    body = body.replace("|", "\\|") if table else body
    longest = max((len(m.group(0)) for m in re.finditer("`+", body)), default=0)
    ticks = "`" * (longest + 1)
    pad = " " if body.startswith("`") or body.endswith("`") or not body else ""
    return f"{ticks}{pad}{body}{pad}{ticks}"


def e(text: Any) -> str:
    return html.escape(visible(text), quote=True)


def csv_cell(value: Any) -> str:
    text = " ".join(visible(value).split()) if not isinstance(value, (int, float)) or isinstance(value, bool) else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def fmt_ratio(metric: Optional[dict]) -> str:
    if not metric:
        return "-"
    if metric["state"] == "unknown":
        return "unknown"
    if metric["state"] == "n/a":
        return "n/a"
    return f"{metric['value']:.2f} ({metric['num']}/{metric['den']})"


def fmt_s(value: Any) -> str:
    return f"{value:.1f} s" if isinstance(value, (int, float)) else "-"


# --------------------------------------------------------------------------- data
def read_json(path: Path, kind: type = dict) -> Any:
    """Parsed JSON of a file that must hold a `kind`; ValueError names the file otherwise."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:  # UnicodeDecodeError is a ValueError too
        raise ValueError(f"{path} is not valid JSON: {err}") from None
    if not isinstance(doc, kind):
        raise ValueError(f"{path} holds a JSON {type(doc).__name__}, not an object")
    return doc


def load(run_dir: Path) -> Tuple[dict, Dict[str, dict], Optional[dict], List[str]]:
    scores = read_json(run_dir / "scores.json")
    if not isinstance(scores.get("units"), list) or not isinstance(scores.get("suite"), dict):
        raise ValueError(f"{run_dir / 'scores.json'} is not a score.py result; run score.py score again")
    traces: Dict[str, dict] = {}
    for path in sorted(run_dir.glob("*.trace.json")):
        doc = read_json(path)
        traces[doc.get("unit") or path.name[: -len(".trace.json")]] = doc
    compare_path = run_dir / "compare.json"
    compare = read_json(compare_path) if compare_path.is_file() else None
    if compare is not None:
        base = Path(compare.get("base_path") or run_dir.parent / str(compare.get("base") or "<base run>"))
        base_now = saved_fingerprint(base)
        if compare.get("new_fingerprint") != scores.get("fingerprint") or compare.get("new") != scores.get("run") \
                or (compare.get("base_fingerprint") and base_now and base_now != compare["base_fingerprint"]):
            # Scored or judged again after the compare, this run or the base: the verdicts compared are gone.
            compare = {"stale": True, "base": compare.get("base"),
                       "command": command("score.py", "compare", "--base", base, "--new", run_dir)}
    threads: List[str] = []  # threads.txt lists what persists; without it, none was recorded
    threads_path = run_dir / "threads.txt"
    if threads_path.is_file():
        threads = [line.split("\t", 1)[0].strip() for line in threads_path.read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.startswith("#")]
    return scores, traces, compare, list(dict.fromkeys(threads))


def saved_fingerprint(run_dir: Path) -> Optional[str]:
    """The verdict fingerprint in <run>/scores.json, or None when there is none to read."""
    try:
        doc = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc.get("fingerprint") if isinstance(doc, dict) and isinstance(doc.get("fingerprint"), str) else None


def summary_rows(scores: dict) -> List[Tuple[str, str]]:
    s = scores["suite"]
    v = s["verdicts"]
    t = s["timing"]
    usage = s["usage"]
    tokens = usage["sums"].get("total_tokens")
    judge = s["judge"]
    rows = [("Runs (cases)", f"{s['units']} ({s['cases']})")]
    if s.get("units_not_run"):
        rows.append(("Planned runs not sent", f"{len(s['units_not_run'])} of {s['units_planned']}: "
                     f"{', '.join(s['units_not_run'])}; every count and rate here covers the runs that were sent"))
    rows += [
        ("Verdicts", f"pass {v['pass']}, fail {v['fail']}, pending judgement {v['pending_judgement']}, "
                     f"unknown {v['unknown']}, error {v['error']}"),
        ("Pass rate", fmt_ratio(s["pass_rate"])),
        ("Pass or pending judgement", fmt_ratio(s["pass_or_pending_rate"])),
        ("Completed runs", fmt_ratio(s["completion_rate"])),
        ("Tool-call recall", fmt_ratio(s["recall"])),
        ("Tool-call precision", fmt_ratio(s["precision"])),
        ("Routing: expected hand-offs (by name, heuristic)", fmt_ratio(s["routing"])),
        ("Argument accuracy (strict keys)", fmt_ratio(s["arg_accuracy"])),
        ("Runs with tools unknown (not zero)", str(s["tools_unknown_units"])),
        ("Runs with an order violation", str(s["order_violation_units"])),
        ("Runs that called a forbidden tool (found after the call ran)", str(s["forbidden_units"])),
        ("Keyword assertions (author assertions, not a quality score)",
         f"{s['assertions']['passed']}/{s['assertions']['total']} passed"
         + (f", {s['assertions']['unknown']} unknown (an answer was not captured)"
            if s["assertions"].get("unknown") else "")),
        ("Turns with step history", fmt_ratio(s["trace_completeness"]["with_history"])),
        ("Turns with every call paired", fmt_ratio(s["trace_completeness"]["fully_paired"])),
        ("Stream and thread agree", fmt_ratio(s["trace_completeness"]["stream_agreement"])),
        ("Client time per turn p50 / p95", f"{fmt_s(t['client_wall_p50_s'])} / {fmt_s(t['client_wall_p95_s'])}"),
        ("Server time per turn p50 / p95", f"{fmt_s(t['server_p50_s'])} / {fmt_s(t['server_p95_s'])}"),
        ("Latency budget breaches", str(t["budget_breaches"])),
        ("Tokens (as the run records give them)",
         f"{tokens if tokens is not None else 'not reported'}; turns without usage: {usage['turns_without_usage']}"),
        ("Judge items", f"pass {judge['pass']}, fail {judge['fail']}, unsure {judge['unsure']}, "
                        f"unjudged {judge['unjudged']}"),
    ]
    if "stability" in s:
        for entry in s["stability"]:
            rows.append((f"Stability of {entry['case']}",
                         f"pass {fmt_ratio(entry['pass_rate'])}, same tool sequence "
                         f"{fmt_ratio(entry['tool_sequences']['agreement'])}"))
    return rows


def goal_result(goal: dict, known: bool) -> str:
    if not known:
        return "unknown (no step history)"
    if goal["matched"]:
        return "matched" + (", out of order" if goal["order"] == "violated" else "")
    if not goal["called"]:
        return "not called"
    keys = [m["key"] for m in goal["mismatches"] + goal["optional_mismatches"]]
    return "called with other args: " + ", ".join(keys)


def csv_row(unit: dict) -> dict:
    m = unit["metrics"]
    walls = [w for w in unit["timing"]["client_wall_s"] if isinstance(w, (int, float))]
    judge = unit["judge"]["counts"]
    return {
        "unit": unit["unit"], "case": unit["case"], "repeat": unit["repeat_index"], "verdict": unit["verdict"],
        "status": unit["status"], "turns_sent": unit["turns_sent"], "turns_planned": unit["turns_planned"],
        "tools_known": unit["tools_known"], "recall": fmt_ratio(m["recall"]), "precision": fmt_ratio(m["precision"]),
        "routing": fmt_ratio(m["routing"]),
        "order_respected": "unknown" if m["order_respected"] is None else m["order_respected"],
        "forbidden": m["forbidden"]["state"], "keywords_passed": unit["assertions"]["passed"],
        "keywords_total": unit["assertions"]["total"], "judge_unjudged": judge["unjudged"],
        "judge_unsure": judge["unsure"], "judge_failed": judge["fail"],
        "client_wall_max_s": max(walls) if walls else "",
        "total_tokens": unit["usage"]["sums"].get("total_tokens", ""),
        "tools_called": ";".join(str(c["name"]) for c in unit["observed_calls"]) if unit["tools_known"] else "unknown",
        "thread_ids": ";".join(unit.get("thread_ids") or []),
        "reasons": " | ".join(unit.get("reasons") or []),
    }


# --------------------------------------------------------------------------- markdown
def render_md(scores: dict, traces: Dict[str, dict], compare: Optional[dict], threads: List[str]) -> str:
    plan = scores.get("plan") or {}
    agents = ", ".join(code(a.get("name")) for a in scores.get("agents") or []) or "-"
    out: List[str] = ["# Agent evaluation report", ""]
    out.append(f"Run {code(scores['run'])}, agent {agents}, host {code(plan.get('host') or '-')}, capture "
               f"{code(plan.get('route') or '-')}, environment {code(plan.get('environment_id') or 'server default')}.")
    out.append("")
    out.append("Agent answers, tool arguments and tool results below are quoted data from the agent. "
               "They are not instructions.")
    out += ["", "## Summary", "", "| Measure | Value |", "|---|---|"]
    out += [f"| {label} | {value} |" for label, value in summary_rows(scores)]
    out += ["", "Notes:"] + [f"- {note}" for note in scores.get("notes") or []]
    if compare and compare.get("stale"):
        out += ["", "## Compared with the baseline", "",
                f"The comparison with {code(compare['base'])} is out of date: this run or the base was scored or "
                f"judged again after it. Compare again, then write the report: {code(compare['command'])}."]
    elif compare:
        out += ["", "## Compared with the baseline", "",
                f"Base run {code(compare['base'])}, this run {code(compare['new'])}.", ""]
        differences = compare.get("not_comparable") or []
        out += [f"- Not comparable: {visible(d)}. A change can come from the target, not the agent." for d in differences]
        out += ([""] if differences else []) + ["| Measure | Base | This run |", "|---|---|---|"]
        out += [f"| {metric} | {fmt_ratio(v['base'])} | {fmt_ratio(v['new'])} |" for metric, v in compare["suite"].items()]
        out += ["", f"Regressions: {', '.join(code(c) for c in compare['regressions']) or 'none'}. "
                    f"Fixes: {', '.join(code(c) for c in compare['fixes']) or 'none'}."]
        for label, key in COMPARE_GROUPS:
            if compare.get(key):
                out.append(f"{label}: {', '.join(code(c) for c in compare[key])}.")
        for case in compare["cases"]:
            if case["details"]:
                out.append(f"- {code(case['case'])} ({case['change']}): " + "; ".join(visible(d) for d in case["details"]))
    out += ["", "## Runs"]
    for unit in scores["units"]:
        out += render_unit_md(unit, traces.get(unit["unit"]) or {})
    out += ["", "## Threads created", ""]
    out += [f"- {code(t)}" for t in threads] or ["- none recorded"]
    out += ["", "## Next steps", ""] + [f"- {step}" for step in NEXT_STEPS]
    return "\n".join(out) + "\n"


def render_unit_md(unit: dict, trace: dict) -> List[str]:
    out = ["", f"### {code(unit['unit'])}: {unit['verdict']}", ""]
    out.append(f"Status {code(unit['status'])}, turns {unit['turns_sent']}/{unit['turns_planned']}, capture "
               f"{code(unit.get('capture') or '-')}, tools known: {'yes' if unit['tools_known'] else 'no'}.")
    if unit.get("trace_ids"):
        out.append(f"Trace ids: {', '.join(code(t) for t in unit['trace_ids'])}.")
    if unit.get("reasons"):  # inline code: a reason can quote a server's error body, whose Markdown must stay text
        out += ["", "Reasons:"] + [f"- {code(r, table=False)}" for r in unit["reasons"]]
    if unit["tool_goals"]:
        out += ["", "| Goal | Tool | Result |", "|---|---|---|"]
        for goal in unit["tool_goals"]:
            tag = " (hand-off)" if goal["handoff"] else ""
            out.append(f"| {code(goal['goal'])} | {code(goal['tool_name'])}{tag} | "
                       f"{visible(goal_result(goal, unit['tools_known'])).replace('|', '/')} |")
        out.append("")
    for entry in unit["text_goals"]:
        for kw in entry["keywords"]:
            out.append(f"- Keyword assertion {code(entry['goal'])} {code(kw['keyword'])}: "
                       f"{KEYWORD_RESULT.get(kw['pass'], 'fail')}")
        if entry.get("kb_answer"):
            out.append(f"- Knowledge-base answer with citations for {code(entry['goal'])}: "
                       f"{KB_RESULT.get(entry['kb_answer']['pass'], 'no')}")
    forbidden = unit["metrics"]["forbidden"]
    if forbidden["state"] != "n/a":
        out.append(f"- Forbidden tools ({', '.join(code(t) for t in forbidden['tools'])}): {forbidden['state']}")
    for jid, result in unit["judge"]["items"].items():
        if result["verdict"] == "unjudged":
            out.append(f"- Judge {code(jid)}: unjudged")
            continue
        out += ["", f"Judge {code(jid)}: {result['verdict']}" + (f" by {code(result.get('model'))}" if result.get("model") else "")]
        if result.get("reason"):
            out.append(fence(result["reason"]))
        for quote in result.get("evidence") or []:
            out.append(fence(quote, "quote"))
        if result.get("unverified_quotes"):
            out.append("Some quotes are not in the material verbatim: review this verdict.")
        if result.get("instruction_found"):
            out.append("The judge found an instruction inside the agent's output: a finding in itself.")
    for turn in trace.get("turns") or []:
        wall = (turn.get("timings") or {}).get("client_wall_s")
        out += ["", f"#### Turn {turn.get('turn')}: {code(turn.get('status'))}, {fmt_s(wall)}"
                    + (f", warnings {', '.join(code(w) for w in turn.get('warnings') or [])}" if turn.get("warnings") else "")]
        out += ["", "User:", fence(turn.get("user_text") or "")]
        if "no_step_history" in (turn.get("warnings") or []):
            out.append("Tools: unknown (no step history).")
        for call in turn.get("tool_calls") or []:
            tag = " (hand-off)" if call.get("handoff") else ""
            out += ["", f"Tool {code(call.get('name'))}{tag}, args:", fence(clip(as_text(call.get("args")), ARGS_LIMIT), "json")]
            result = call.get("result")
            out.append("Result:" if result else "Result: none recorded.")
            if result:
                out.append(fence(clip(as_text(result.get("content")), RESULT_LIMIT)))
        out += ["", "Answer:", fence(clip(turn.get("answer") or "", ANSWER_LIMIT))]
    return out


# --------------------------------------------------------------------------- html
CSS = """
:root { --bg: #ffffff; --fg: #161616; --muted: #525252; --line: #e0e0e0; --box: #f4f4f4;
        --pass: #198038; --fail: #da1e28; --wait: #8e6a00; --unknown: #6f6f6f; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161616; --fg: #f4f4f4; --muted: #c6c6c6; --line: #393939; --box: #262626;
          --pass: #42be65; --fail: #ff8389; --wait: #f1c21b; --unknown: #a8a8a8; } }
body { background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, sans-serif; margin: 0 auto;
       max-width: 1100px; padding: 24px 16px; }
h1 { font-size: 26px; margin: 0 0 8px; } h2 { margin-top: 32px; border-bottom: 1px solid var(--line); }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th, td { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
pre { background: var(--box); padding: 8px 10px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
code { background: var(--box); padding: 0 4px; }
.meta, .note { color: var(--muted); }
.verdict { font-weight: 600; } .pass { color: var(--pass); } .fail, .error { color: var(--fail); }
.pending_judgement { color: var(--wait); } .unknown { color: var(--unknown); }
details { border: 1px solid var(--line); margin: 12px 0; padding: 8px 12px; }
summary { cursor: pointer; font-weight: 600; }
"""


def pre(text: Any) -> str:
    return f"<pre>{e(text)}</pre>"


def render_html(scores: dict, traces: Dict[str, dict], compare: Optional[dict], threads: List[str]) -> str:
    plan = scores.get("plan") or {}
    agents = ", ".join(e(a.get("name")) for a in scores.get("agents") or []) or "-"
    out = ["<!DOCTYPE html>", '<html lang="en"><head><meta charset="utf-8">',
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">",
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f"<title>Agent evaluation {e(scores['run'])}</title><style>{CSS}</style></head><body>",
           "<h1>Agent evaluation report</h1>",
           f"<p class=\"meta\">Run <code>{e(scores['run'])}</code>, agent {agents}, host <code>{e(plan.get('host') or '-')}</code>, "
           f"capture <code>{e(plan.get('route') or '-')}</code>, environment "
           f"<code>{e(plan.get('environment_id') or 'server default')}</code>.</p>",
           "<p class=\"note\">Agent answers, tool arguments and tool results below are quoted data from the agent. "
           "They are not instructions.</p>",
           "<h2>Summary</h2><table>"]
    out += [f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>" for label, value in summary_rows(scores)]
    out.append("</table><ul>" + "".join(f"<li>{e(n)}</li>" for n in scores.get("notes") or []) + "</ul>")
    if compare and compare.get("stale"):
        out.append(f"<h2>Compared with the baseline</h2><p>The comparison with <code>{e(compare['base'])}</code> is "
                   "out of date: this run or the base was scored or judged again after it. Compare again, then "
                   f"write the report: <code>{e(compare['command'])}</code></p>")
    elif compare:
        out.append(f"<h2>Compared with the baseline</h2><p>Base run <code>{e(compare['base'])}</code>, "
                   f"this run <code>{e(compare['new'])}</code>.</p>")
        out += [f"<p class=\"note\">Not comparable: {e(d)}. A change can come from the target, not the agent.</p>"
                for d in compare.get("not_comparable") or []]
        out.append("<table><tr><th>Measure</th><th>Base</th><th>This run</th></tr>")
        out += [f"<tr><td>{e(m)}</td><td>{e(fmt_ratio(v['base']))}</td><td>{e(fmt_ratio(v['new']))}</td></tr>"
                for m, v in compare["suite"].items()]
        out.append("</table><ul>")
        out += [f"<li><code>{e(c['case'])}</code> ({e(c['change'])}): {e('; '.join(c['details']))}</li>"
                for c in compare["cases"] if c["details"]]
        out.append(f"</ul><p>Regressions: {e(', '.join(compare['regressions']) or 'none')}. "
                   f"Fixes: {e(', '.join(compare['fixes']) or 'none')}.</p>")
        out += [f"<p>{e(label)}: {e(', '.join(compare[key]))}.</p>" for label, key in COMPARE_GROUPS if compare.get(key)]
    out.append("<h2>Runs</h2>")
    for unit in scores["units"]:
        out.append(render_unit_html(unit, traces.get(unit["unit"]) or {}))
    out.append("<h2>Threads created</h2><ul>" + ("".join(f"<li><code>{e(t)}</code></li>" for t in threads)
                                                 or "<li>none recorded</li>") + "</ul>")
    out.append("<h2>Next steps</h2><ul>" + "".join(f"<li>{e(s)}</li>" for s in NEXT_STEPS) + "</ul>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def render_unit_html(unit: dict, trace: dict) -> str:
    verdict = unit["verdict"] if unit["verdict"] in ("pass", "fail", "error", "pending_judgement", "unknown") else "unknown"
    out = [f"<details{' open' if verdict != 'pass' else ''}><summary><code>{e(unit['unit'])}</code> "
           f"<span class=\"verdict {verdict}\">{e(unit['verdict'])}</span></summary>",
           f"<p>Status <code>{e(unit['status'])}</code>, turns {e(unit['turns_sent'])}/{e(unit['turns_planned'])}, "
           f"capture <code>{e(unit.get('capture') or '-')}</code>, tools known: {'yes' if unit['tools_known'] else 'no'}"
           + (f", trace ids {e(', '.join(unit['trace_ids']))}" if unit.get("trace_ids") else "") + ".</p>"]
    if unit.get("reasons"):
        out.append("<ul>" + "".join(f"<li>{e(r)}</li>" for r in unit["reasons"]) + "</ul>")
    if unit["tool_goals"]:
        out.append("<table><tr><th>Goal</th><th>Tool</th><th>Result</th></tr>")
        out += [f"<tr><td><code>{e(g['goal'])}</code></td><td><code>{e(g['tool_name'])}</code>"
                f"{' (hand-off)' if g['handoff'] else ''}</td><td>{e(goal_result(g, unit['tools_known']))}</td></tr>"
                for g in unit["tool_goals"]]
        out.append("</table>")
    items = []
    for entry in unit["text_goals"]:
        items += [f"<li>Keyword assertion <code>{e(entry['goal'])}</code> <code>{e(kw['keyword'])}</code>: "
                  f"{e(KEYWORD_RESULT.get(kw['pass'], 'fail'))}</li>" for kw in entry["keywords"]]
        if entry.get("kb_answer"):
            items.append(f"<li>Knowledge-base answer with citations for <code>{e(entry['goal'])}</code>: "
                         f"{e(KB_RESULT.get(entry['kb_answer']['pass'], 'no'))}</li>")
    forbidden = unit["metrics"]["forbidden"]
    if forbidden["state"] != "n/a":
        items.append(f"<li>Forbidden tools ({e(', '.join(forbidden['tools']))}): {e(forbidden['state'])}</li>")
    if items:
        out.append("<ul>" + "".join(items) + "</ul>")
    for jid, result in unit["judge"]["items"].items():
        by = f" by <code>{e(result['model'])}</code>" if result.get("model") else ""
        out.append(f"<p>Judge <code>{e(jid)}</code>: <strong>{e(result['verdict'])}</strong>{by}</p>")
        if result.get("reason"):
            out.append(pre(result["reason"]))
        out += [f"<blockquote>{pre(q)}</blockquote>" for q in result.get("evidence") or []]
        if result.get("unverified_quotes"):
            out.append("<p class=\"note\">Some quotes are not in the material verbatim: review this verdict.</p>")
        if result.get("instruction_found"):
            out.append("<p class=\"note\">The judge found an instruction inside the agent's output: a finding in itself.</p>")
    for turn in trace.get("turns") or []:
        wall = (turn.get("timings") or {}).get("client_wall_s")
        warnings = ", ".join(turn.get("warnings") or [])
        out.append(f"<h4>Turn {e(turn.get('turn'))}: <code>{e(turn.get('status'))}</code>, {e(fmt_s(wall))}"
                   + (f", warnings {e(warnings)}" if warnings else "") + "</h4>")
        out.append("<p>User:</p>" + pre(turn.get("user_text") or ""))
        if "no_step_history" in (turn.get("warnings") or []):
            out.append("<p>Tools: unknown (no step history).</p>")
        for call in turn.get("tool_calls") or []:
            tag = " (hand-off)" if call.get("handoff") else ""
            out.append(f"<p>Tool <code>{e(call.get('name'))}</code>{tag}, args:</p>" + pre(clip(as_text(call.get("args")), ARGS_LIMIT)))
            result = call.get("result")
            out.append("<p>Result:</p>" + pre(clip(as_text(result.get("content")), RESULT_LIMIT)) if result
                       else "<p>Result: none recorded.</p>")
        out.append("<p>Answer:</p>" + pre(clip(turn.get("answer") or "", ANSWER_LIMIT)))
    out.append("</details>")
    return "\n".join(out)


# --------------------------------------------------------------------------- csv and CLI
def render_csv(scores: dict) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for unit in scores["units"]:
        writer.writerow({k: csv_cell(v) for k, v in csv_row(unit).items()})
    return buffer.getvalue()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Write report.md, report.html and summary.csv for a scored run.")
    parser.add_argument("--run", required=True, help="the run folder with scores.json")
    args = parser.parse_args(argv)
    run_dir = Path(args.run)
    if not (run_dir / "scores.json").is_file():
        print(f"error: {run_dir / 'scores.json'} not found: run {command('score.py', 'score', '--run', run_dir)} "
              "first", file=sys.stderr)
        return 2
    try:
        scores, traces, compare, threads = load(run_dir)
        (run_dir / "report.md").write_text(render_md(scores, traces, compare, threads), encoding="utf-8")
        (run_dir / "report.html").write_text(render_html(scores, traces, compare, threads), encoding="utf-8")
        (run_dir / "summary.csv").write_text(render_csv(scores), encoding="utf-8")
    except (OSError, ValueError) as err:
        print(f"error: {visible(err)}", file=sys.stderr)
        return 2
    print(f"Wrote {run_dir / 'report.md'}, {run_dir / 'report.html'} and {run_dir / 'summary.csv'}.")
    if compare and compare.get("stale"):
        print(f"note: compare.json is older than the verdicts of this run or its base, so the report leaves it out. "
              f"Compare again, then write the report: {compare['command']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
