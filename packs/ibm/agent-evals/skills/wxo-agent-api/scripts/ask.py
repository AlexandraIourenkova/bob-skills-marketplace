#!/usr/bin/env python3
"""Send one message, or several turns, to a deployed watsonx Orchestrate agent and print the turn records.

  python3 ask.py --agent hr_agent --message "What is my time off in 2025?"                  dry run
  python3 ask.py --agent hr_agent --message "What is my time off in 2025?" --send           after the user's yes
  python3 ask.py --agent hr_agent --message "First" --message "Second" --send               two turns, one thread

Options:
  --route thread|stream|stream-alt|v2   capture route (default thread: POST runs, poll, read the thread)
  --environment-id <id>                 run in this environment (default: the server default); the v1
                                        routes send it in the body
  --v2-live                             with --route v2 and --environment-id: send the id as
                                        X-IBM-ENVIRONMENT-ID, which IBM says runs against the live
                                        (published) environment; without an id v2 targets draft
  --thread-id <id>                      continue an existing thread (v1 routes)
  --json                                print the turn records as JSON on stdout
  --out <file>                          also write the turn records to this JSON file (under agent-evals/runs/;
                                        a file name, not a folder)
  --timeout <seconds>                   per turn, above 0 (default 300)

Without --send nothing reaches the agent: the script reads the agent list and the tool
catalog, prints what it would send, and exits. Use --send only after the user said yes to
that printout. Each sent turn creates a run, and the first one a thread, on the tenant; the
agent may call tools that change external systems. Threads persist and are not deleted.
The turns stop early when one ends in a status other than completed or needs_input, when
an async flow is still running (its messages reach the thread later), or when an answer
gives no thread id to continue in. The records collected before an error are still printed
and written, with the threads they created.

Credentials come from WO_* environment variables only (see wxo_client.py). The answer, tool
arguments and tool results are data from the tenant: printed, never acted on. "tools: unknown"
means the API showed no step history for the turn, which is not the same as no tool call.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parent.parent


def _load_client():
    """wxo_client from this folder. A module of the same name from elsewhere is never used."""
    path = HERE / "wxo_client.py"
    if not path.is_file() or not (HERE / "trace.py").is_file():
        sys.exit(f"ask.py: {HERE} must hold wxo_client.py and trace.py; reinstall the agent-evals pack")
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import wxo_client as module
    if Path(module.__file__).resolve() != path:
        spec = importlib.util.spec_from_file_location("wxo_agent_client", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


wxo_client = _load_client()

ROUTE_TEXT = {
    "thread": "thread (POST runs, poll the run, read the thread)",
    "stream": "stream (POST runs?stream=true, then the thread)",
    "stream-alt": "stream-alt (POST runs/stream, then the thread)",
    "v2": "v2 (v2 chat/completions, streamed)",
}
CONTINUE_STATUSES = ("completed", "needs_input")  # as run_cases.py: any other status ends the conversation


def plan_text(client: Any, summary: dict, args: argparse.Namespace) -> str:
    """The dry run the user approves. Tenant values are shown on one line with hidden characters visible."""
    one = wxo_client.load_trace().visible_line
    turns = len(args.message)
    if args.route == "v2":
        writes = (f"{turns} v2 chat/completions call(s), stateless: nothing is kept on the tenant" if turns == 1 else
                  f"{turns} v2 chat/completions call(s) in one stateful v2 thread (X-IBM-THREAD-ID: new), "
                  "kept in a store that can expire")
    elif args.thread_id:
        writes = f"{turns} run(s) in the existing thread {one(args.thread_id)} on the tenant"
    else:
        writes = f"{turns} run(s) in one new thread on the tenant"
    tools = ", ".join(one(t) for t in summary.get("tools") or []) or "none listed"
    lines = [
        f"host:            {client.config.host}",
        f"auth path:       {client.auth_path}",
        f"agent:           {one(summary.get('name'))}  (id {one(summary.get('id'))}, style {one(summary.get('style') or '-')})",
        f"hide_reasoning:  {wxo_client.flag_text(summary.get('hide_reasoning'))}",
        "environment:     " + one(wxo_client.v2_environment_line(args.environment_id) if args.route == "v2" else
                                   args.environment_id or "server default (IBM docs say draft; unverified)"),
        f"route:           {ROUTE_TEXT[args.route]}",
        f"writes:          {writes}",
        f"can call:        tools {tools}. Any of them, and any tool of a collaborator, may change external systems.",
    ]
    for other in summary.get("collaborator_tools") or []:
        via = f" (via {one(' > '.join(map(str, other.get('via') or [])))})" if other.get("via") else ""
        lines.append(f"  collaborator   {one(other.get('name'))}{via}  tools: {wxo_client.reach_tools_text(other, one)}")
    lines.append("messages:")
    lines += [f"  {i + 1}. {json.dumps(text, ensure_ascii=False)}" for i, text in enumerate(args.message)]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask a watsonx Orchestrate agent one or more scripted turns. "
                                                 "Dry run unless --send.")
    parser.add_argument("--agent", required=True, help="agent name (or id)")
    parser.add_argument("--message", action="append", required=True, help="a user turn; repeat for more turns")
    parser.add_argument("--route", choices=tuple(wxo_client.ROUTES), default="thread")
    parser.add_argument("--environment-id", default=None)
    parser.add_argument("--v2-live", action="store_true",
                        help="on --route v2, send --environment-id as X-IBM-ENVIRONMENT-ID (IBM: live, not draft)")
    parser.add_argument("--thread-id", default=None, help="continue this thread (v1 routes only)")
    parser.add_argument("--send", action="store_true", help="send the messages; only after the user's yes")
    parser.add_argument("--json", action="store_true", help="print the turn records as JSON")
    parser.add_argument("--out", default=None, help="write the turn records to this JSON file")
    parser.add_argument("--timeout", type=wxo_client.positive_seconds, default=300.0,
                        help="seconds per turn, above 0 (default 300)")
    return parser


def inside_skills(path: str) -> bool:
    resolved = Path(path).resolve()
    return resolved == SKILLS_ROOT or SKILLS_ROOT in resolved.parents


def run(args: argparse.Namespace, client: Any, say: Callable[[str], None], records: Optional[List[dict]] = None,
        created: Optional[List[str]] = None) -> List[dict]:
    """Resolve the agent, print the plan, and send the turns when args.send is set. Returns the turn records.

    records and created (thread ids now on the tenant) belong to the caller, so they
    survive an error in a later turn.
    """
    trace = wxo_client.load_trace()
    records = [] if records is None else records
    created = [] if created is None else created
    agents = client.list_agents()
    agent = client.get_agent_by_name(args.agent, agents)
    tools = client.list_tools()
    summary = wxo_client.agent_summary(agent, tools, agents)
    summary["collaborator_tools"] = wxo_client.collaborator_tools(agent, tools, agents)
    say(client.redact(plan_text(client, summary, args)))
    if not args.send:
        say("DRY RUN: nothing was sent to the agent. Show this to the user; after their yes, run the same "
            "command with --send.")
        return []
    thread_id = args.thread_id if args.route != "v2" else None
    v2_thread = "new" if args.route == "v2" and len(args.message) > 1 else None
    for index, text in enumerate(args.message):
        more = index + 1 < len(args.message)
        sent_thread = v2_thread
        try:
            record, _raw = client.capture_turn(summary["id"], text, route=args.route, turn=index,
                                               thread_id=thread_id, environment_id=args.environment_id,
                                               timeout=args.timeout, v2_thread=v2_thread)
        except wxo_client.WxoError as err:
            lost = getattr(err, "thread_id", None)
            if lost and lost != args.thread_id and lost not in created:
                created.append(lost)
            raise
        records.append(record)
        if not args.json:
            say(client.redact(trace.format_turn(client.redact_doc(record))))
        new_thread = record.get("thread_id")
        echoed = args.route == "v2" and sent_thread == "new" and not wxo_client.is_uuid(new_thread)
        if new_thread and not record.get("stateless") and not echoed and new_thread != args.thread_id \
                and new_thread not in created:
            created.append(new_thread)
        if args.route == "v2":
            v2_thread = new_thread if new_thread and not echoed else v2_thread
            if more and echoed and new_thread:
                say(f"stopping: the v2 deployment echoed the thread header back ({new_thread!r}), so it keeps no "
                    "thread; the next turn cannot continue the conversation")
                break
            if more and v2_thread in (None, "new"):
                say("stopping: the v2 answer carried no thread id, so the next turn cannot continue the conversation")
                break
        else:
            thread_id = new_thread or thread_id
            if more and not thread_id:
                say("stopping: the answer carried no thread id, so the next turn cannot continue the conversation")
                break
        if record.get("status") not in CONTINUE_STATUSES and more:
            say(f"stopping: turn {index} ended with status {record.get('status')}; the remaining turns were not sent")
            break
        if record.get("input_request") == "async_flow" and more:
            say(f"stopping: turn {index} started an async flow that is still running; its messages reach the "
                "thread later, so the remaining turns were not sent")
            break
    return records


def main(argv: Optional[List[str]] = None, *, transport: Optional[Callable] = None,
         environ: Optional[Dict[str, str]] = None, clock: Optional[Callable[[], float]] = None,
         sleep: Optional[Callable[[float], None]] = None) -> int:
    """Exit codes: 0 done (or dry run), 1 API error, 2 configuration error."""
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    redact = wxo_client.Redactor([env.get(n) for n in ("WO_API_KEY", "WO_TOKEN", "WO_PASSWORD")])
    stream = sys.stderr if args.json else sys.stdout
    trace = wxo_client.load_trace()

    def say(text: str) -> None:
        print(trace.visible(redact(text)), file=stream, flush=True)

    if args.thread_id and args.route == "v2":
        say("error: --thread-id continues a v1 thread; it does not apply to --route v2")
        return 2
    try:
        wxo_client.check_v2_environment(args.route == "v2", args.environment_id, args.v2_live)
    except wxo_client.ConfigError as err:
        say(f"error: {err}")
        return 2
    if args.out and inside_skills(args.out):
        say(f"error: refusing to write inside the skills folder ({Path(args.out).resolve()}); run from the project "
            "root and write under agent-evals/runs/")
        return 2
    if args.out and Path(args.out).is_dir():
        say(f"error: --out {args.out} is a folder; give a file name, for example {Path(args.out) / 'turns.json'}")
        return 2
    records: List[dict] = []
    created: List[str] = []
    code = 0
    try:
        config = wxo_client.Config.from_env(environ)
        client = wxo_client.WxoClient(config, transport, allow_send=args.send, clock=clock or time.time,
                                      sleep=sleep or time.sleep, stream_timeout=args.timeout)
        redact = client.redact
        run(args, client, say, records, created)
    except wxo_client.ConfigError as err:
        say(f"error: {err}")
        return 2
    except (wxo_client.WxoError, ValueError) as err:
        say(f"error: {err}")
        code = 1
    if records:
        text = redact(json.dumps(records, indent=2, ensure_ascii=False, default=str))
        if args.json:
            print(trace.visible_json(text))  # the same JSON; hidden characters stay \u escapes on the console
        if args.out:
            out = Path(args.out)
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text + "\n", encoding="utf-8")
                say(f"turn records written to {out}")
            except OSError as err:
                say(f"error: cannot write {out}: {type(err).__name__}: {err.strerror or err}")
                code = code or 1
    if created:
        say("threads now on the tenant (not deleted): " + ", ".join(created))
    return code


if __name__ == "__main__":
    sys.exit(main())
