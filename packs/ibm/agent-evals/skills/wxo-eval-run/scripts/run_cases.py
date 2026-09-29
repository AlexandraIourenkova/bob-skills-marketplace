#!/usr/bin/env python3
"""Run a case set against a watsonx Orchestrate agent, behind a plan and a confirmed hash.

Run from the project root (script paths relative to the wxo-eval-run skill folder):
  python3 scripts/run_cases.py plan --cases agent-evals/cases [--agent NAME]
          [--capture thread|stream|stream-alt|v2] [--probe agent-evals/probe/probe.json]
          [--repeat N] [--max-cases N] [--environment-id ID [--v2-live]] [--turn-timeout 300]
          [--out agent-evals/runs]
  python3 scripts/run_cases.py run --plan agent-evals/runs/<ts>/plan.json --confirm <hash8>
  python3 scripts/run_cases.py resume --plan agent-evals/runs/<ts>/plan.json --confirm <hash8>

plan reads only: it mints the token and calls GET agents and GET tools. It writes
<out>/<ts>/plan.json and prints the target, every tool and collaborator the agent
can call, what will be sent and the plan hash. Nothing reaches the agent. Each plan
carries a random nonce inside its hash, so planning the same inputs again never gives
a hash the user already approved. The v1 routes send --environment-id in the body; the
v2 route would send it as X-IBM-ENVIRONMENT-ID, which IBM says runs against the live
(published) environment, so v2 with --environment-id needs --v2-live.

run checks the hash, the case bytes and the target, sends the first case only (the
canary) and stops; when the canary failed with an error, run sends it again. resume
sends the other runs after the user's next yes. Both refuse, before any message, when
--confirm is missing or wrong, a case file or plan.json changed after the plan,
WO_INSTANCE points elsewhere, or the agent's id, name, tools or the agents it can
hand off to (collaborators of collaborators too) no longer match the plan (a read of
GET agents and GET tools). Turns are scripted: the runner never picks a message from
the agent's output. Runs are sequential. A run that calls a tool the case forbids,
also a call only the stream showed, stops the whole run (exit 3) so the user can look
first. A run interrupted (Ctrl-C) leaves a trace marked stopped_early interrupted.
A case stops before its next turn when an async flow is still running (async_wait or
flow.slot.listen), when a v2 deployment keeps no threads (it echoes the thread header
back, or answers 503 to it; then the case stops before turn 0), or when an answer names
no thread to continue in (no_thread_id).

The run folder receives:
  cases/<case>.json       the case bytes that were run
  <unit>.trace.json       the turn records of one run of a case
  <unit>.messages.json    the same turns as agentops Message dicts
  raw/<unit>/turn-<n>.*   responses as received (stream bytes when streamed)
  threads.txt             thread ids that now persist on the tenant (stateless v2 ids are not listed)
  progress.json           which runs are done
A unit is one run of a case: <case>, or <case>.r<k> for repetition k >= 2.

Credentials come from WO_* environment variables only (see the wxo-agent-api skill).
The script sends GET and POST only; threads stay on the tenant for the user to clean.
Exit codes: 0 done, 1 API or runtime error, 2 refused or bad input, 3 stopped because
a forbidden tool was called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shlex
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parent.parent
API_SCRIPTS = SKILLS_ROOT / "wxo-agent-api" / "scripts"


def _load_client():
    """wxo_client from the wxo-agent-api skill of the same pack, found by path."""
    if not (API_SCRIPTS / "wxo_client.py").is_file() or not (API_SCRIPTS / "trace.py").is_file():
        raise SystemExit(f"error: {API_SCRIPTS} is missing. wxo-eval-run needs the wxo-agent-api skill of the "
                         "agent-evals pack next to it; install the whole pack.")
    if str(API_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(API_SCRIPTS))
    import wxo_client  # noqa: E402  (found through the path above)
    return wxo_client


wc = _load_client()
tr = wc.load_trace()

PLAN_VERSION = 1
DEFAULT_OUT = "agent-evals/runs"
DEFAULT_PROBE = "agent-evals/probe/probe.json"
DEFAULT_TURN_TIMEOUT = 300.0
MAX_REPEAT = 20
CONTINUE_STATUSES = ("completed", "needs_input")  # needs_input continues for widgets, never for async flows
SERVER_DEFAULT_ENV = "server default; IBM docs say draft"
TODO = "<TODO>"  # the placeholder wxo-eval-cases new and from-thread leave for the author
THREADS_HEADER = "# watsonx Orchestrate threads created by this run. They persist on the tenant.\n"


class Refused(Exception):
    """The gate said no, or the input is unusable. Nothing was sent."""


class ForbiddenCalled(Exception):
    """A run called a tool its case forbids."""


# --------------------------------------------------------------------------- small helpers
def iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, doc: Any, redact: Optional[Callable[[str], str]] = None) -> None:
    """JSON with indent 2; with redact, every known secret and bearer value is removed from the text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, ensure_ascii=False, default=str)
    path.write_text((redact(text) if redact else text) + "\n", encoding="utf-8")


def short(text: Any, limit: int = 100) -> str:
    text = " ".join(tr.visible(text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def say(text: str = "", file=None) -> None:
    """Print a line; tenant text in it shows hidden and control characters as <U+XXXX>.

    Flushed at once, so a reader of stdout and stderr merged sees the lines in the order they were written.
    """
    print(tr.visible(text), file=file or sys.stdout, flush=True)


def one(value: Any) -> str:
    """A tenant value (a name, an id) on one line, hidden characters shown: a CR or LF cannot move the cursor."""
    return tr.visible_line(value)


def command(script: str, *args: Any) -> str:
    """A next-step command line with the script's resolved path, every part shell-quoted, so it runs as shown
    from the project root, also when a folder name holds a space."""
    return " ".join(shlex.quote(str(part)) for part in ["python3", HERE / script, *args])


def check_out(path: Path) -> Path:
    """Refuse an output folder inside the installed skills: run the script from the project root."""
    resolved = Path(path).resolve()
    if resolved == SKILLS_ROOT or SKILLS_ROOT in resolved.parents:
        raise Refused(f"refusing to write inside the skills folder ({resolved}); run the script from the "
                      "project root so the run lands under agent-evals/runs")
    return Path(path)


# --------------------------------------------------------------------------- cases
def find_case_files(paths: List[str]) -> List[Path]:
    """Case files from files and folders (*.json in a folder, not recursive, without the agentops
    *.messages.json files, as wxo-eval-cases validate skips them), in a stable order."""
    files: List[Path] = []
    for given in paths:
        path = Path(given)
        if path.is_dir():
            files.extend(sorted(p for p in path.glob("*.json") if p.is_file() and not p.name.endswith(".messages.json")))
        elif path.is_file():
            files.append(path)
        else:
            raise Refused(f"no such case file or folder: {given}")
    seen, unique = set(), []
    for path in files:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def case_turns(doc: dict) -> List[str]:
    """Turn 0 is starting_sentence, turns 1..n are user_prompts (the agentops semantics)."""
    return [doc["starting_sentence"]] + list(doc.get("user_prompts") or [])


def case_problems(doc: Any) -> List[str]:
    """The checks a run needs. The full check is wxo-eval-cases validate."""
    if not isinstance(doc, dict):
        return ["not a JSON object"]
    problems = []
    first = doc.get("starting_sentence")
    if not isinstance(first, str) or not first.strip():
        problems.append("starting_sentence must be a non-empty string")
    prompts = doc.get("user_prompts")
    if prompts is not None and (not isinstance(prompts, list)
                                or not all(isinstance(p, str) and p.strip() for p in prompts)):
        problems.append("user_prompts must be a list of non-empty strings")
    turns = [("starting_sentence", first)] + [(f"user_prompts[{i}]", p)
                                              for i, p in enumerate(prompts if isinstance(prompts, list) else [])]
    problems.extend(f"{where}: placeholder {TODO} left; fill it in" for where, text in turns
                    if isinstance(text, str) and TODO in text)
    if not isinstance(doc.get("goal_details", []), list):
        problems.append("goal_details must be a list")
    else:
        names = Counter(g.get("name") for g in doc.get("goal_details") or []
                        if isinstance(g, dict) and isinstance(g.get("name"), str) and g.get("name"))
        for name, count in sorted(names.items()):
            if count > 1:
                problems.append(f"goal_details name {name!r} is used {count} times; scoring needs unique names")
    extra = doc.get("x_agent_evals")
    if extra is not None and not isinstance(extra, dict):
        problems.append("x_agent_evals must be an object")
    repeat = (extra or {}).get("repeat") if isinstance(extra, dict) else None
    if repeat is not None and (isinstance(repeat, bool) or not isinstance(repeat, int) or not 1 <= repeat <= MAX_REPEAT):
        problems.append(f"x_agent_evals.repeat must be an integer from 1 to {MAX_REPEAT}")
    forbidden = (extra or {}).get("forbidden_tools") if isinstance(extra, dict) else None
    if forbidden is not None and (not isinstance(forbidden, list) or not all(isinstance(f, str) for f in forbidden)):
        problems.append("x_agent_evals.forbidden_tools must be a list of tool names")
    return problems


def forbidden_of(doc: dict) -> List[str]:
    extra = doc.get("x_agent_evals") if isinstance(doc.get("x_agent_evals"), dict) else {}
    return [f for f in extra.get("forbidden_tools") or [] if isinstance(f, str)]


def is_forbidden(name: Any, forbidden: Any) -> bool:
    """A call name matches a forbidden name: equal, or a hand-off to the same collaborator with either prefix."""
    return any(tr.same_tool(f, name) for f in forbidden)


def environment_notes(environment_id: Optional[str], resolved: Dict[str, dict]) -> List[str]:
    """A note for each planned agent whose record lists environments without --environment-id among their ids or
    names: one plan sends the same id to every agent, and an environment belongs to one agent."""
    notes = []
    for name, agent in resolved.items() if environment_id else ():
        envs = [e for e in agent.get("environments") or [] if e]
        keys = {str(v) for e in envs for v in ((e.get("id"), e.get("name")) if isinstance(e, dict) else (e,)) if v}
        if not envs or environment_id in keys:
            continue
        draft = next((e.get("id") for e in envs if isinstance(e, dict) and e.get("name") == "draft" and e.get("id")),
                     None)
        notes.append(f"--environment-id {environment_id} is not among the environments of {name}"
                     + (f" (its draft is {draft})" if draft else "") + "; every run of this plan sends the same id, "
                     "so plan each agent's cases apart, each with its own id")
    return notes


def repeat_of(doc: Any, override: Optional[int]) -> int:
    """--repeat, else x_agent_evals.repeat, else 1."""
    if override:
        return override
    extra = doc.get("x_agent_evals") if isinstance(doc, dict) and isinstance(doc.get("x_agent_evals"), dict) else {}
    value = extra.get("repeat")
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_REPEAT else 1


HASHED_PLAN_KEYS = ("plan_version", "nonce", "instance", "route", "environment_id", "v2_live", "turn_timeout_s",
                    "tool_catalog_readable", "settle_reads")


def plan_hash(plan: dict) -> str:
    """sha256 over the plan's nonce, instance, route, environment, v2_live, turn timeout, thread reads per turn
    and whether the tool catalog was readable; per case its bytes, agent id and name, turns and repeats; per agent its id, name,
    tools and every agent it can reach through hand-offs, with their tools and hand-off path. Everything
    the runner reads from plan.json at run time is in it, so an edit after the user's yes changes the
    hash, and the random nonce makes every plan's hash new."""
    material: Dict[str, Any] = {key: plan.get(key) for key in HASHED_PLAN_KEYS}
    material["cases"] = [dict({k: c[k] for k in ("name", "sha256", "agent_id", "turns", "repeat")}, agent=c.get("agent"))
                         for c in plan.get("cases") or []]
    material["agents"] = [{"id": a.get("id"), "name": a.get("name"), "tools": list(a.get("tools") or []),
                           "collaborators": [{"name": o.get("name"), "tools": list(o.get("tools") or []),
                                              "via": list(o.get("via") or [])}
                                             for o in a.get("collaborator_tools") or []]}
                          for a in plan.get("agents") or []]
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(blob.encode("utf-8"))


def plan_units(plan: dict) -> List[dict]:
    """Every run the plan makes, in order: each case, repetition 1..repeat."""
    units = []
    for case in plan["cases"]:
        for k in range(1, int(case["repeat"]) + 1):
            units.append({"unit": case["name"] if k == 1 else f"{case['name']}.r{k}", "case": case, "repeat_index": k})
    return units


def pick_route(capture: Optional[str], probe_path: str, host: str) -> Tuple[str, str, List[str]]:
    """The capture route: --capture, else probe.json's recommendation, else thread."""
    if capture:
        return capture, "--capture", []
    path = Path(probe_path)
    if not path.is_file():
        return "thread", "default", [f"no probe result at {probe_path}: run the wxo-agent-api probe once per "
                                     "instance to confirm where tool calls appear"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError, OSError):
        return "thread", "default", [f"{probe_path} is not readable JSON; using thread"]
    doc = doc if isinstance(doc, dict) else {}
    probe_host = doc.get("host") or (wc.host_of(doc["instance"]) if isinstance(doc.get("instance"), str) else None)
    if probe_host and str(probe_host).lower() != host:
        return "thread", "default", [f"{probe_path} was made for {probe_host}, not {host}; using thread"]
    recommended = doc.get("capture")
    if recommended in wc.ROUTES:
        return recommended, f"probe ({probe_path})", []
    return "thread", "default", [f"the probe was inconclusive (capture={recommended!r}); using thread"]


def settle_from_probe(probe_path: str, host: str) -> Tuple[int, List[str]]:
    """Thread reads per turn: enough to cover the step-history lag the probe measured on R1 for this host.

    The probe reads the thread at completion, +5 s and +15 s; lag.stable_from is the first read that
    already showed the final thread. Without a probe for this host, the client's default.
    """
    try:
        doc = json.loads(Path(probe_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return wc.SETTLE_READS, []
    doc = doc if isinstance(doc, dict) else {}
    probe_host = doc.get("host") or (wc.host_of(doc["instance"]) if isinstance(doc.get("instance"), str) else None)
    lag = (((doc.get("routes") or {}).get("thread") or {}).get("lag") or {}) if isinstance(doc.get("routes"), dict) else {}
    if not probe_host or str(probe_host).lower() != host or not isinstance(lag, dict) \
            or not lag.get("changed_after_completion"):
        return wc.SETTLE_READS, []
    seconds = lag.get("stable_from_s")
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        label = lag.get("stable_from")
        seconds = float(label[:-1]) if isinstance(label, str) and label[:-1].isdigit() and label.endswith("s") else None
    reads = wc.settle_reads_for(seconds)
    if reads == wc.SETTLE_READS:
        return reads, []
    return reads, [f"the probe saw the thread change up to {one(lag.get('stable_from'))} after a run completed: each "
                   f"turn reads the thread for up to {wc.settle_window_s(reads):g} s"]


# --------------------------------------------------------------------------- plan
def make_run_dir(out: Path, now: float) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now))
    candidate = out / stamp
    n = 2
    while candidate.exists():
        candidate = out / f"{stamp}-{n}"
        n += 1
    candidate.mkdir(parents=True)
    return candidate


def describe_agent(agent: dict, tools: List[dict], agents: List[dict]) -> dict:
    """agent_summary plus every agent it can reach through hand-offs (collaborators of collaborators too)
    with their own tools and hand-off path, and each tool's catalog permission."""
    summary = wc.agent_summary(agent, tools, agents)
    tool_by_name = {t.get("name"): t for t in tools}
    summary["collaborator_tools"] = wc.collaborator_tools(agent, tools, agents)
    summary["tool_permissions"] = {name: tool_by_name[name].get("permission")
                                   for name in summary["tools"] if name in tool_by_name
                                   and tool_by_name[name].get("permission") is not None}
    return summary


def cmd_plan(args, env, transport, clock, sleep) -> int:
    if args.repeat is not None and not 1 <= args.repeat <= MAX_REPEAT:
        raise Refused(f"--repeat must be from 1 to {MAX_REPEAT}")
    if args.max_cases is not None and args.max_cases < 1:
        raise Refused("--max-cases must be 1 or more")
    if args.v2_live and not args.environment_id:
        raise Refused("--v2-live needs --environment-id")
    check_out(Path(args.out))
    files = find_case_files(args.cases)
    if not files:
        raise Refused("no case files found")
    problems: List[str] = []
    loaded = []
    for path in files:
        data = path.read_bytes()
        try:
            doc = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            problems.append(f"{path}: not valid JSON ({err})")
            continue
        problems.extend(f"{path}: {p}" for p in case_problems(doc))
        agent_name = args.agent or (doc.get("agent") if isinstance(doc, dict) else None)
        if not isinstance(agent_name, str) or not agent_name.strip():
            problems.append(f"{path}: no agent name; set 'agent' in the case or pass --agent")
        loaded.append((path, data, doc, agent_name))
    if args.max_cases:
        loaded = loaded[: args.max_cases]
    units_seen: Dict[str, str] = {}
    for path, _, doc, _ in loaded:
        for k in range(1, repeat_of(doc, args.repeat) + 1):
            unit = path.stem if k == 1 else f"{path.stem}.r{k}"
            if unit in units_seen:
                problems.append(f"{path}: run name {unit} clashes with {units_seen[unit]}; rename one case file")
            else:
                units_seen[unit] = str(path)
    if problems:
        raise Refused("the cases cannot run:\n  " + "\n  ".join(problems)
                      + "\nFix them (wxo-eval-cases validate shows every problem) and plan again.")

    config = wc.Config.from_env(env)
    client = wc.WxoClient(config, transport, allow_send=False, clock=clock, sleep=sleep)
    auth_path = client.ensure_auth()
    agents = client.list_agents()
    notes: List[str] = []
    catalog_readable = True
    try:
        tools = client.list_tools()
    except wc.RateLimited:
        raise  # a wait, not a missing catalog: plan again later
    except wc.ApiError as err:
        tools = []
        catalog_readable = False
        notes.append(f"the tool catalog is not readable (HTTP {err.status}); tools are shown by id")

    resolved: Dict[str, dict] = {}
    for _, _, _, name in loaded:
        if name not in resolved:
            resolved[name] = client.get_agent_by_name(name, agents)
            if not isinstance(resolved[name].get("id"), str) or not resolved[name]["id"]:
                raise Refused(f"agent {name} has no id in GET agents")
    route, route_source, route_notes = pick_route(args.capture, args.probe, config.host)
    try:
        wc.check_v2_environment(route == "v2", args.environment_id, args.v2_live)
    except wc.ConfigError as err:
        raise Refused(f"the capture route is {route} ({route_source}): {err}"
                      + ("; or pick a v1 route, for example --capture thread" if route == "v2" else "")) from None
    notes.extend(route_notes)
    settle_reads, settle_notes = settle_from_probe(args.probe, config.host) if route != "v2" else (wc.SETTLE_READS, [])
    notes.extend(settle_notes)
    summaries = {name: describe_agent(agent, tools, agents) for name, agent in resolved.items()}
    notes.extend(environment_notes(args.environment_id, resolved))
    for name, summary in summaries.items():
        if summary["hide_reasoning"] is True:
            notes.append(f"{name} has hide_reasoning on: tool calls may be missing from the thread and tool "
                         "metrics may come back unknown; a draft with hide_reasoning off gives full traces")

    cases = []
    for path, data, doc, name in loaded:
        repeat = repeat_of(doc, args.repeat)
        cases.append({
            "name": path.stem,
            "path": str(path.resolve()),
            "sha256": sha256(data),
            "agent": name,
            "agent_id": resolved[name]["id"],
            "turns": len(case_turns(doc)),
            "repeat": int(repeat),
            "forbidden_tools": forbidden_of(doc),
            "first_turn": short(doc["starting_sentence"], 100),
        })
    units = sum(c["repeat"] for c in cases)
    turns = sum(c["turns"] * c["repeat"] for c in cases)
    # On v2 a single-turn run is stateless; only a multi-turn run opens a (stateful) thread.
    threads = sum(c["repeat"] for c in cases if c["turns"] > 1) if route == "v2" else units
    run_dir = make_run_dir(Path(args.out), clock())
    plan = {
        "plan_version": PLAN_VERSION,
        "nonce": secrets.token_hex(16),
        "created_at": iso(clock()),
        "instance": config.instance,
        "host": config.host,
        "auth_path": auth_path,
        "route": route,
        "route_source": route_source,
        "environment_id": args.environment_id,
        "v2_live": bool(route == "v2" and args.environment_id and args.v2_live),
        "turn_timeout_s": args.turn_timeout,
        "settle_reads": settle_reads,
        "tool_catalog_readable": catalog_readable,
        "agents": list(summaries.values()),
        "cases": cases,
        "totals": {"cases": len(cases), "units": units, "turns": turns, "runs": turns, "threads": threads,
                   "stateless_units": units - threads},
        "notes": notes,
    }
    full = plan_hash(plan)
    plan = dict({"plan_version": PLAN_VERSION, "hash": full, "hash8": full[:8]}, **plan)
    plan_path = run_dir / "plan.json"
    write_json(plan_path, plan, client.redact)
    print_plan(plan, plan_path, client.redact)
    return 0


def environment_line(plan: dict) -> str:
    """What the plan's messages target. On v2 the id is a header that IBM says selects live."""
    if plan["route"] == "v2":
        return wc.v2_environment_line(plan["environment_id"] if plan.get("v2_live") else None)
    if plan["environment_id"]:
        return plan["environment_id"] + " (--environment-id, sent as environment_id in the body)"
    return SERVER_DEFAULT_ENV


def sends_line(plan: dict) -> str:
    """What the plan writes on the tenant, by route: POST /runs and threads on v1; v2 chat/completions,
    stateless for a single-turn run, a stateful v2 thread for a multi-turn run."""
    totals = plan["totals"]
    head = f"  {totals['cases']} case(s), {totals['units']} run(s) of a case, {totals['turns']} message(s): "
    if plan["route"] != "v2":
        return head + f"{totals['turns']} POST /runs, up to {totals['threads']} new thread(s) that stay on the tenant"
    stateless = totals.get("stateless_units", totals["units"] - totals["threads"])
    return (head + f"{totals['turns']} POST v2 chat/completions; {stateless} single-turn run(s) are stateless and "
            f"keep nothing; up to {totals['threads']} multi-turn run(s) each open a stateful v2 thread, kept in a "
            "store that can expire")


def print_plan(plan: dict, plan_path: Path, redact: Callable[[str], str] = str) -> None:
    def out(text: str = "") -> None:
        say(redact(text))

    out(f"Plan {plan['hash8']}  ({plan_path})")
    out("Nothing has been sent to the agent.")
    out("")
    out("Target")
    out(f"  host         {one(plan['host'])}")
    out(f"  auth         {plan['auth_path']}")
    out(f"  environment  {one(environment_line(plan))}")
    for agent in plan["agents"]:
        out("")
        out(f"Agent {one(agent['name'])}  id={one(agent['id'])}  style={one(agent['style'])}  "
            f"hide_reasoning={wc.flag_text(agent['hide_reasoning'])}  "
            f"environments={', '.join(one(e) for e in agent['environments']) or '-'}")
        out("  Tools it can call. Any of them may change external systems:")
        for name in agent["tools"] or ["(none listed)"]:
            permission = agent["tool_permissions"].get(name)
            suffix = (f"  (catalog says permission={one(permission)}; the tool's code decides what it does)"
                      if permission else "")
            out(f"    {one(name)}{suffix}")
        if agent["collaborator_tools"]:
            out("  Agents it can hand off to (collaborators, and theirs), with their own tools:")
            for other in agent["collaborator_tools"]:
                via = f" (via {' > '.join(one(v) for v in other.get('via') or [])})" if other.get("via") else ""
                out(f"    {one(other['name'])}{via}  tools: {wc.reach_tools_text(other, one)}")
    out("")
    out("What will be sent")
    out(f"  capture route  {plan['route']} ({plan['route_source']})")
    out(sends_line(plan))
    for case in plan["cases"]:
        out(f"    {case['name']}: agent {one(case['agent'])}, {case['turns']} turn(s) x{case['repeat']}, "
            f"first turn \"{case['first_turn']}\"")
    forbidden = sorted({f for c in plan["cases"] for f in c["forbidden_tools"]})
    if forbidden:
        out(f"  Forbidden tools named by the cases: {', '.join(one(f) for f in forbidden)}. A call is detected "
            "after it ran, not prevented; the run stops at the first one.")
    for note in plan["notes"]:
        out(f"  note: {one(note)}")
    out("")
    out("Ask the user to approve this plan. After their yes, the canary sends the first case only:")
    out("  " + command("run_cases.py", "run", "--plan", plan_path, "--confirm", plan["hash8"]))


# --------------------------------------------------------------------------- gate
def load_plan(path: Path) -> dict:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as err:
        raise Refused(f"cannot read the plan {path}: {err}") from None
    if not isinstance(plan, dict) or plan.get("plan_version") != PLAN_VERSION or not isinstance(plan.get("hash"), str):
        raise Refused(f"{path} is not a plan made by this script")
    if plan.get("route") not in wc.ROUTES or not isinstance(plan.get("cases"), list) or not plan["cases"] \
            or not isinstance(plan.get("agents"), list) \
            or not all(isinstance(c, dict) for c in plan["cases"] + plan["agents"]):
        raise Refused(f"{path} is not a usable plan")
    return plan


def check_gate(plan: dict, confirm: Optional[str], env) -> Tuple[Any, Dict[str, bytes]]:
    """Local checks, before any request: the confirmed hash, the case bytes, the instance, the plan itself."""
    if not confirm:
        raise Refused("no --confirm. Show the plan to the user; after their yes, pass the hash the plan printed.")
    confirm = confirm.strip().lower()
    if len(confirm) < 8 or not plan["hash"].startswith(confirm):
        raise Refused("--confirm does not match this plan. Nothing was sent. Run plan again and show it to the user.")
    problems: List[str] = []
    datas: Dict[str, bytes] = {}
    for case in plan["cases"]:
        path = Path(case["path"])
        if not path.is_file():
            problems.append(f"{case['name']}: {path} is missing")
            continue
        data = path.read_bytes()
        if sha256(data) != case["sha256"]:
            problems.append(f"{case['name']}: the case file changed after the plan")
        datas[case["name"]] = data
    config = wc.Config.from_env(env)
    if config.instance != plan["instance"]:
        problems.append(f"WO_INSTANCE is {config.host}, the plan targets {plan.get('host')}")
    try:
        same = plan_hash(plan) == plan["hash"]
    except (KeyError, TypeError, AttributeError):
        same = False
    if not same:
        problems.append("plan.json was edited after the plan was made")
    if problems:
        raise Refused("the plan no longer matches: " + "; ".join(problems)
                      + ". Nothing was sent. Run plan again and show the new plan to the user.")
    return config, datas


def check_target(client, plan: dict) -> None:
    """Read-only (GET agents, GET tools): every agent the plan sends to still exists under the same id and
    name, and can call the same tools and reach the same agents through hand-offs (collaborators of
    collaborators too), with the same tools, as the plan the user approved.

    A tool catalog readable at plan time but not now (or the other way round) cannot be compared: the
    refusal says so instead of reporting every tool as changed. A 429 is raised as it is (exit 1)."""
    agents = client.list_agents()
    readable = plan.get("tool_catalog_readable", True) is not False
    try:
        tools = client.list_tools()
        now_readable = True
    except wc.RateLimited:
        raise
    except wc.ApiError as err:
        tools, now_readable = [], False  # the plan falls back the same way: tools shown by id
        if readable:
            raise Refused(f"cannot check the agent's tools: the tool catalog was readable when the plan was made "
                          f"but GET tools now answers HTTP {err.status}. Nothing was sent. Try the same command "
                          "again later; if the catalog stays unreadable, make a new plan") from None
    if now_readable and not readable:
        raise Refused("the tool catalog is readable now but was not when the plan was made, so the plan showed "
                      "tools by id and cannot be compared. Nothing was sent. Make a new plan, which shows the tool "
                      "names, and show it to the user")
    by_id = {a.get("id"): a for a in agents}
    targets = {c["agent_id"]: c.get("agent") for c in plan["cases"]}
    for agent in plan["agents"]:
        targets.setdefault(agent.get("id"), agent.get("name"))
    problems = []
    for agent_id, name in targets.items():
        live = by_id.get(agent_id)
        if live is None:
            problems.append(f"agent {one(name)} ({one(agent_id)}) is no longer on this instance")
        elif live.get("name") != name:
            problems.append(f"agent id {one(agent_id)} is now named {one(repr(live.get('name')))}, "
                            f"not {one(repr(name))}")
    for planned in plan["agents"]:
        live = by_id.get(planned.get("id"))
        if live is None or live.get("name") != planned.get("name"):
            continue
        problems.extend(wc.target_changes(planned, describe_agent(live, tools, agents)))
    if problems:
        raise Refused("the target changed: " + "; ".join(problems) + ". Nothing was sent. Run plan again and "
                      "show the new plan to the user.")


# --------------------------------------------------------------------------- run files
def load_progress(run_dir: Path, plan: dict) -> dict:
    path = run_dir / "progress.json"
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and doc.get("plan_hash") == plan["hash"] and isinstance(doc.get("units"), dict):
                return doc
        except ValueError:
            pass
        raise Refused(f"{path} does not belong to this plan")
    return {"plan_hash": plan["hash"], "units": {}}


def save_progress(run_dir: Path, progress: dict, redact: Optional[Callable[[str], str]] = None) -> None:
    write_json(run_dir / "progress.json", progress, redact)


def known_threads(run_dir: Path) -> set:
    path = run_dir / "threads.txt"
    if not path.is_file():
        return set()
    return {line.split("\t", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def note_thread(run_dir: Path, thread_id: Optional[str], unit: str) -> None:
    """Append a thread id to threads.txt once, the moment it is known."""
    if not thread_id or thread_id in known_threads(run_dir):
        return
    path = run_dir / "threads.txt"
    with path.open("a", encoding="utf-8") as handle:
        if path.stat().st_size == 0:
            handle.write(THREADS_HEADER)
        handle.write(f"{thread_id}\t{unit}\n")


def write_raw(raw_dir: Path, index: int, raw: dict, redact: Callable[[str], str]) -> None:
    """Responses as received, with every known secret removed (stream bytes otherwise untouched)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    data = dict(raw)
    stream = data.pop("stream", None)
    if isinstance(stream, (bytes, bytearray)):
        text = bytes(stream).decode("utf-8", errors="surrogateescape")
        (raw_dir / f"turn-{index}.stream").write_bytes(redact(text).encode("utf-8", errors="surrogateescape"))
        data["stream_file"] = f"turn-{index}.stream"
    write_json(raw_dir / f"turn-{index}.json", data, redact)


class ThreadWatch:
    """Wraps the transport to note the thread id of every POST /runs answer, even if the turn fails later."""

    def __init__(self, transport: Callable, run_dir: Path):
        self._transport = transport
        self.run_dir = run_dir
        self.unit = ""

    def __call__(self, method, url, headers, body, stream):
        status, response_headers, data = self._transport(method, url, headers, body, stream)
        path = url.split("?", 1)[0]
        if method == "POST" and path.endswith("/orchestrate/runs") and not stream \
                and isinstance(data, (bytes, bytearray)) and 200 <= int(status) < 300:
            try:
                doc = json.loads(bytes(data).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                doc = None
            if isinstance(doc, dict) and isinstance(doc.get("thread_id"), str):
                note_thread(self.run_dir, doc["thread_id"], self.unit)
        return status, response_headers, data


# --------------------------------------------------------------------------- run
def tools_line(turns: List[dict]) -> str:
    if not turns:
        return "tools: none sent"
    if not all(tr.tools_known(t) for t in turns):
        return "tools: unknown (no step history)"
    names = [f"{short(c.get('name'), 80)}{' [hand-off]' if c.get('handoff') else ''}"
             for t in turns for c in t["tool_calls"]]
    return "tools: " + (", ".join(names) or "none called")


def run_unit(client, plan: dict, unit: dict, case_doc: dict, run_dir: Path, clock, watch: ThreadWatch) -> dict:
    case = unit["case"]
    name = unit["unit"]
    watch.unit = name
    texts = case_turns(case_doc)
    route = plan["route"]
    agent = next((a for a in plan["agents"] if a["id"] == case["agent_id"]), {})
    handoff_names = [c["name"] for c in agent.get("collaborator_tools") or [] if isinstance(c.get("name"), str)]
    record: Dict[str, Any] = {
        "case": case["name"], "unit": name, "repeat_index": unit["repeat_index"], "repeats": case["repeat"],
        "case_sha256": case["sha256"], "agent": {"name": case["agent"], "id": case["agent_id"]},
        "host": plan["host"], "capture": route, "environment_id": plan.get("environment_id"),
        "started_at": iso(clock()), "finished_at": None, "turns_planned": len(texts), "turns_sent": 0,
        "stopped_early": None, "error": None, "thread_ids": [], "correlation_ids": [], "forbidden_called": [],
        "handoff_names": handoff_names, "turns": [],
    }
    thread_id: Optional[str] = None
    v2_thread: Optional[str] = ("new" if len(texts) > 1 else None) if route == "v2" else None
    forbidden = set(forbidden_of(case_doc))  # from the case bytes the hash covers, never from plan.json

    def persists(tid: Optional[str]) -> None:
        if tid:
            note_thread(run_dir, tid, name)
            if tid not in record["thread_ids"]:
                record["thread_ids"].append(tid)

    def stop(index: int, status: str) -> None:
        """Stop after turn `index`; -1 means before turn 0."""
        record["stopped_early"] = {"after_turn": index, "status": status, "turns_not_sent": len(texts) - index - 1}

    # On v2 the environment id is a header that IBM says selects live: sent only with --v2-live (hashed).
    environment_id = plan.get("environment_id") if route != "v2" or plan.get("v2_live") else None
    settle = plan.get("settle_reads")  # hashed with the plan
    settle_reads = settle if isinstance(settle, int) and not isinstance(settle, bool) and settle >= 1 else wc.SETTLE_READS
    try:
        for index, text in enumerate(texts):
            sent_thread = v2_thread
            try:
                turn, raw = client.capture_turn(
                    case["agent_id"], text, route=route, turn=index,
                    thread_id=thread_id if route != "v2" else None,
                    environment_id=environment_id,
                    timeout=float(plan.get("turn_timeout_s") or DEFAULT_TURN_TIMEOUT),
                    settle_reads=settle_reads, v2_thread=v2_thread, handoff_names=handoff_names)
            except wc.NoThreadSupport as err:
                if sent_thread != "new":
                    raise
                # 503 to X-IBM-THREAD-ID: new. The turn did not run and the deployment keeps no threads.
                stop(index - 1, "no_thread_support")
                record["stopped_early"]["detail"] = client.redact(str(err))
                break
            record["turns"].append(turn)
            record["turns_sent"] = index + 1
            write_raw(run_dir / "raw" / name, index, raw, client.redact)
            tid = turn.get("thread_id")
            no_thread_support = route == "v2" and sent_thread == "new" and not wc.is_uuid(tid)
            if turn.get("stateless") or no_thread_support:
                if tid and tid not in record["correlation_ids"]:
                    record["correlation_ids"].append(tid)  # nothing is stored under it on the tenant
            else:
                persists(tid)
            if tid and not no_thread_support:
                if route == "v2":
                    v2_thread = tid
                else:
                    thread_id = thread_id or tid
            # The source of truth decides recall and precision, but a forbidden call the stream showed
            # (a v2 step delta, or a v1 stream call the thread leaves out) ran all the same.
            hits = [{"turn": index, "name": c.get("name"), "id": c.get("id")}
                    for c in turn["tool_calls"] if is_forbidden(c.get("name"), forbidden)]
            hits += [{"turn": index, "name": c["name"], "id": c["id"], "seen": "stream only"}
                     for c in tr.wire_only_calls(turn) if is_forbidden(c["name"], forbidden)]
            record["forbidden_called"].extend(hits)
            last = index == len(texts) - 1
            if not last and hits:
                stop(index, "forbidden_tool_called")
                break
            if not last and turn["status"] not in CONTINUE_STATUSES:
                stop(index, turn["status"])
                break
            if not last and turn.get("input_request") == "async_flow":
                stop(index, "async_flow")  # the flow still runs and adds to the thread; a scripted turn would cut in
                break
            if not last and no_thread_support:
                stop(index, "no_thread_support")  # the deployment echoed X-IBM-THREAD-ID back: no thread to continue
                break
            if not last and not (tid if route == "v2" else thread_id):
                stop(index, "no_thread_id")  # the next turn would open another conversation
                break
    except wc.WxoError as err:
        record["error"] = client.redact(f"{type(err).__name__}: {err}")
        if route != "v2" or v2_thread not in (None, "new"):
            persists(getattr(err, "thread_id", None))
    except BaseException:  # Ctrl-C or a bug: the trace on disk must not look like a finished run
        if not record["stopped_early"] and record["turns_sent"] < len(texts):
            stop(record["turns_sent"] - 1, "interrupted")
        raise
    finally:
        record["finished_at"] = iso(clock())
        write_json(run_dir / f"{name}.trace.json", record, client.redact)
        write_json(run_dir / f"{name}.messages.json", tr.to_agentops_messages(record["turns"]), client.redact)
    return record


def forbidden_lines(record: dict, redact_doc: Callable[[Any], Any]) -> List[str]:
    """One line per forbidden call: its turn, name and arguments, redacted before they are cut."""
    lines = []
    for hit in record["forbidden_called"]:
        turn = next((t for t in record["turns"] if t.get("turn") == hit["turn"]), {})
        call = next((c for c in turn.get("tool_calls") or []
                     if c.get("name") == hit["name"] and c.get("id") == hit["id"]), None)
        args = ("arguments not captured: only the stream showed this call" if call is None
                else short(json.dumps(redact_doc(call.get("args")), ensure_ascii=False, default=str), 300))
        lines.append(f"turn {hit['turn']}: {short(hit['name'], 80)}({args})")
    return lines


def unit_line(position: int, total: int, record: dict) -> str:
    turns = record["turns"]
    if record["error"]:
        status = "error"
    else:
        status = turns[-1]["status"] if turns else "not sent"
    warnings = sorted({w for t in turns for w in t.get("warnings") or []})
    line = (f"[{position}/{total}] {record['unit']}: {status}  turns {record['turns_sent']}/{record['turns_planned']}  "
            f"{tools_line(turns)}  warnings: {', '.join(warnings) or '-'}")
    stopped = record["stopped_early"]
    if stopped:
        where = "before turn 0" if stopped["after_turn"] < 0 else f"after turn {stopped['after_turn']}"
        line += f"  stopped {where} ({stopped['status']})"
    return line


def cmd_run(args, env, transport, clock, sleep, resume: bool) -> int:
    plan_path = Path(args.plan)
    plan = load_plan(plan_path)
    run_dir = plan_path.parent
    config, datas = check_gate(plan, args.confirm, env)
    progress = load_progress(run_dir, plan)
    units = plan_units(plan)
    canary = units[0]["unit"]
    canary_done = progress["units"].get(canary, {}).get("state") == "done"
    if not resume and canary_done:
        raise Refused("the canary of this plan already ran. After the user's yes to its result, use resume "
                      "(not a new plan): " + command("run_cases.py", "resume", "--plan", plan_path, "--confirm",
                                                     plan["hash8"]))
    if resume and not canary_done:
        raise Refused("the canary has not completed yet. After the user's yes, send it again with run "
                      "(not a new plan): " + command("run_cases.py", "run", "--plan", plan_path, "--confirm",
                                                     plan["hash8"]))
    todo = [units[0]] if not resume else [u for u in units if progress["units"].get(u["unit"], {}).get("state") != "done"]
    if not todo:
        print("Every run of this plan is done. Next: " + command("score.py", "score", "--run", run_dir))
        return 0

    turn_timeout = float(plan.get("turn_timeout_s") or DEFAULT_TURN_TIMEOUT)
    watch = ThreadWatch(transport or wc.urllib_transport(config.ca_bundle, wc.DEFAULT_TIMEOUT_S,
                                                         stream_timeout=turn_timeout), run_dir)
    client = wc.WxoClient(config, watch, allow_send=False, clock=clock, sleep=sleep)
    client.ensure_auth()
    check_target(client, plan)
    for case in plan["cases"]:
        snapshot = run_dir / "cases" / f"{case['name']}.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(datas[case["name"]])
    client.allow_send = True  # the confirmed hash, the case bytes and the target all match the plan

    def out(text: str = "", file=None) -> None:
        """say() with every known secret removed: turns and errors carry tenant text."""
        say(client.redact(text), file=file)

    def threads_line() -> None:
        count = len(known_threads(run_dir))
        out(f"Threads created so far: {count}, listed in {run_dir / 'threads.txt'} (they stay on the tenant)."
            if count else "No thread was created on the tenant.")

    position = {u["unit"]: i + 1 for i, u in enumerate(units)}
    out(("Resuming" if resume else "Canary") + f": plan {plan['hash8']}, route {plan['route']}, host {plan['host']}")
    for unit in todo:
        case_doc = json.loads(datas[unit["case"]["name"]].decode("utf-8"))
        record = run_unit(client, plan, unit, case_doc, run_dir, clock, watch)
        entry = {"state": "error" if record["error"] else "done", "finished_at": record["finished_at"]}
        if record["error"]:
            entry["error"] = record["error"]
        progress["units"][unit["unit"]] = entry
        save_progress(run_dir, progress, client.redact)
        out(unit_line(position[unit["unit"]], len(units), record))
        if not resume:
            for turn in client.redact_doc(record["turns"]):  # redacted before format_turn cuts long values
                out(tr.format_turn(turn))
        if (record["stopped_early"] or {}).get("detail"):
            out(f"  {record['stopped_early']['detail']}")
        if record["error"]:
            threads_line()
            out(f"error: {record['error']}", file=sys.stderr)
            again = "resume" if resume else "run"
            out(f"Stopped. The partial trace is in {run_dir / (unit['unit'] + '.trace.json')}. Show the error to the "
                f"user; after their yes, this command sends the run again (no new plan needed):", file=sys.stderr)
            out("  " + command("run_cases.py", again, "--plan", plan_path, "--confirm", plan["hash8"]), file=sys.stderr)
            return 1
        if record["forbidden_called"]:
            threads_line()
            names = ", ".join(sorted({short(c["name"], 80) for c in record["forbidden_called"]}))
            out(f"STOPPED: {unit['unit']} called forbidden tool(s) {names}. The call already ran; check what it "
                "changed:", file=sys.stderr)
            for line in forbidden_lines(record, client.redact_doc):
                out(f"  {line}", file=sys.stderr)
            out(f"The trace is in {run_dir / (unit['unit'] + '.trace.json')}.", file=sys.stderr)
            left = [u for u in units if progress["units"].get(u["unit"], {}).get("state") != "done"]
            if left:
                out(f"Show this to the user. Only after their new yes, resume sends the {len(left)} run(s) left:",
                    file=sys.stderr)
                out("  " + command("run_cases.py", "resume", "--plan", plan_path, "--confirm", plan["hash8"]),
                    file=sys.stderr)
            else:
                out("No run of this plan is left to send. Next: " + command("score.py", "score", "--run", run_dir),
                    file=sys.stderr)
            return 3
    threads_line()
    if not resume and len(units) > 1:
        out("Stopped after the canary. Show this result to the user; after their yes, run the rest:")
        out("  " + command("run_cases.py", "resume", "--plan", plan_path, "--confirm", plan["hash8"]))
    elif not resume:
        out("The canary was the only run in this plan: the plan is done. Next: "
            + command("score.py", "score", "--run", run_dir))
    else:
        out(f"All {len(units)} run(s) are done. Next: " + command("score.py", "score", "--run", run_dir))
    return 0


# --------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run test cases against a watsonx Orchestrate agent behind a plan "
                                                 "and a confirmed hash.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="read-only: resolve the agent, list its tools, write plan.json and print the hash")
    p.add_argument("--cases", nargs="+", required=True, help="case files or folders of *.json cases")
    p.add_argument("--agent", help="agent name for every case (default: each case's 'agent')")
    p.add_argument("--capture", choices=wc.ROUTES, help="capture route (default: the probe's recommendation, else thread)")
    p.add_argument("--probe", default=DEFAULT_PROBE, help=f"probe result to read the route from (default {DEFAULT_PROBE})")
    p.add_argument("--repeat", type=int, help="runs per case for stability (default: x_agent_evals.repeat, else 1)")
    p.add_argument("--max-cases", type=int, help="run only the first N cases")
    p.add_argument("--environment-id", help="environment id to run against, sent as environment_id on the v1 routes "
                                             "(default: the server default)")
    p.add_argument("--v2-live", action="store_true",
                   help="on the v2 route, send --environment-id as X-IBM-ENVIRONMENT-ID, which IBM says runs against "
                        "the live (published) environment")
    p.add_argument("--turn-timeout", type=wc.positive_seconds, default=DEFAULT_TURN_TIMEOUT,
                   help="seconds per turn, a finite number above 0 (default 300)")
    p.add_argument("--out", default=DEFAULT_OUT, help=f"folder for run folders (default {DEFAULT_OUT})")
    for name, text in (("run", "send the first case only (the canary) and stop"),
                       ("resume", "send the remaining runs of a plan whose canary is done")):
        q = sub.add_parser(name, help=text)
        q.add_argument("--plan", required=True, help="the plan.json that plan wrote")
        q.add_argument("--confirm", help="the plan hash the user approved (8 characters or more)")
    return parser


def main(argv: Optional[List[str]] = None, *, transport: Optional[Callable] = None,
         environ: Optional[Dict[str, str]] = None, clock: Callable[[], float] = time.time,
         sleep: Callable[[float], None] = time.sleep) -> int:
    args = build_parser().parse_args(argv)
    redact = wc.Redactor()
    try:
        try:
            redact = wc.Redactor(wc.Config.from_env(environ).secrets())
        except wc.ConfigError:
            pass
        if args.command == "plan":
            return cmd_plan(args, environ, transport, clock, sleep)
        return cmd_run(args, environ, transport, clock, sleep, resume=args.command == "resume")
    except Refused as err:  # a refusal can name the tenant's tools and agents: say() shows hidden characters
        say(f"refused: {redact(err)}", file=sys.stderr)
        return 2
    except wc.ConfigError as err:
        say(f"error: {redact(err)}", file=sys.stderr)
        return 2
    except wc.WxoError as err:
        say(f"error: {redact(err)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
