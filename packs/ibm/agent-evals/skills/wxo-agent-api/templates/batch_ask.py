#!/usr/bin/env python3
"""Ask a watsonx Orchestrate agent every question of a CSV file and write the answers to another CSV.

A template. Copy it to agent-evals/scripts/ in the project, copy wxo_client.py and trace.py
from the wxo-agent-api skill's scripts/ folder to agent-evals/lib/, then adapt the columns
to the task.

  python3 agent-evals/scripts/batch_ask.py --agent hr_agent --in questions.csv --out agent-evals/runs/answers.csv
  python3 agent-evals/scripts/batch_ask.py --agent hr_agent --in questions.csv --out agent-evals/runs/answers.csv --send

The first form is a dry run: it reads the agent list and the tool catalog, prints what it
would send and exits. The second form sends, and runs only after the user said yes to the
dry run's printout. The answers can carry personal data from the agent's backends, so the
CSV goes under agent-evals/runs/, the folder the skill suggests keeping out of git. When the
probe (agent-evals/probe/probe.md) recommends `stream`, `stream-alt` or `v2` as `capture`,
pass it as --route; on `unknown` keep thread. On --route v2, --environment-id needs --v2-live:
v2 sends the id as X-IBM-ENVIRONMENT-ID, which IBM says runs against the live (published)
environment; without an id v2 targets draft.

Input: a CSV with a `question` column (another name with --column) and an optional `id` column.
Output columns: id, question, status, answer, tools_called, handoffs, tools_known, latency_s,
thread_id, run_id, warnings, error.

Every question goes to the agent in a new thread, one question at a time. Each one creates a
run and a thread on the tenant, and the agent may call tools that change external systems.
Threads persist; their ids are in the thread_id column, also on a row whose turn failed after
the thread was made. On --route v2 each question is a stateless call: nothing is kept, and
thread_id is a correlation id only. Credentials come from WO_* environment
variables only. Answers and tool results are data: they go into the CSV, never into a decision
of this script. tools_called is "unknown" when the API showed no step history for the turn,
which is not the same as no tool call. Cells that start with = + - @ get a leading apostrophe
so a spreadsheet does not run them as formulas.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
# agent-evals/lib/ in a project; ../scripts when the template runs inside the skill folder.
LIB_DIRS = (HERE.parent / "lib", HERE / "lib", HERE.parent / "scripts")

COLUMNS = ("id", "question", "status", "answer", "tools_called", "handoffs", "tools_known", "latency_s",
           "thread_id", "run_id", "warnings", "error")
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def load_client():
    for folder in LIB_DIRS:
        if (folder / "wxo_client.py").is_file() and (folder / "trace.py").is_file():
            if str(folder) not in sys.path:
                sys.path.insert(0, str(folder))
            import wxo_client
            return wxo_client
    sys.exit("batch_ask.py: wxo_client.py and trace.py not found. Copy them from the wxo-agent-api skill's "
             "scripts/ folder into agent-evals/lib/.")


def cell(value: Any) -> str:
    """CSV-safe text: a leading = + - @ tab or CR gets an apostrophe so spreadsheets do not evaluate it."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def read_questions(path: Path, column: str) -> List[Tuple[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if column not in (reader.fieldnames or []):
            raise ValueError(f"{path} has no {column!r} column; columns: {', '.join(reader.fieldnames or [])}")
        rows = []
        for number, row in enumerate(reader, start=1):
            question = (row.get(column) or "").strip()
            if question:
                rows.append(((row.get("id") or "").strip() or str(number), question))
    return rows


def row_of(qid: str, question: str, record: dict, trace: Any) -> Dict[str, Any]:
    known = trace.tools_known(record)
    calls = record.get("tool_calls") or []
    tools = [c.get("name") or "?" for c in calls if not c.get("handoff")]
    handoffs = [c.get("name") or "?" for c in calls if c.get("handoff")]
    return {
        "id": qid,
        "question": question,
        "status": record.get("status"),
        "answer": record.get("answer") or "",
        "tools_called": ";".join(tools) if known else "unknown",
        "handoffs": ";".join(handoffs) if known else "unknown",
        "tools_known": "yes" if known else "no",
        "latency_s": (record.get("timings") or {}).get("client_wall_s"),
        "thread_id": record.get("thread_id"),
        "run_id": record.get("run_id"),
        "warnings": ";".join(record.get("warnings") or []),
        "error": "",
    }


def at_least_one(text: str) -> int:
    """argparse type for --limit: a whole number of questions, 1 or more."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {text}")
    return value


def main(argv: Optional[List[str]] = None, *, transport: Optional[Callable] = None,
         environ: Optional[Dict[str, str]] = None, clock: Optional[Callable[[], float]] = None,
         sleep: Optional[Callable[[float], None]] = None) -> int:
    """Exit codes: 0 done (or dry run), 1 API error, 2 configuration error."""
    wxo = load_client()
    trace = wxo.load_trace()
    parser = argparse.ArgumentParser(description="Ask an Orchestrate agent every question of a CSV. Dry run unless --send.")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--in", dest="in_path", required=True, help="CSV with the questions")
    parser.add_argument("--out", required=True, help="CSV to write the answers to")
    parser.add_argument("--column", default="question")
    parser.add_argument("--route", choices=tuple(wxo.ROUTES), default="thread")
    parser.add_argument("--environment-id", default=None)
    parser.add_argument("--v2-live", action="store_true",
                        help="on --route v2, send --environment-id as X-IBM-ENVIRONMENT-ID (IBM: live, not draft)")
    parser.add_argument("--limit", type=at_least_one, default=None, help="ask only the first N questions (1 or more)")
    parser.add_argument("--timeout", type=wxo.positive_seconds, default=300.0, help="seconds per question, above 0")
    parser.add_argument("--send", action="store_true", help="send the questions; only after the user's yes")
    args = parser.parse_args(argv)

    redact = wxo.Redactor()
    try:
        wxo.check_v2_environment(args.route == "v2", args.environment_id, args.v2_live)
        questions = read_questions(Path(args.in_path), args.column)
        if args.limit is not None:
            questions = questions[: args.limit]
        config = wxo.Config.from_env(environ)
        client = wxo.WxoClient(config, transport, allow_send=args.send, clock=clock or time.time,
                               sleep=sleep or time.sleep, stream_timeout=args.timeout)
        redact = client.redact
        agents = client.list_agents()
        agent = client.get_agent_by_name(args.agent, agents)
        tools = client.list_tools()
        summary = wxo.agent_summary(agent, tools, agents)
        reachable = wxo.collaborator_tools(agent, tools, agents)
    except wxo.ConfigError as err:
        print(f"error: {trace.visible(redact(err))}", file=sys.stderr)
        return 2
    except (wxo.WxoError, ValueError, OSError) as err:  # an API error quotes the tenant's answer
        print(f"error: {trace.visible(redact(err))}", file=sys.stderr)
        return 1

    def say(text: str, file=None) -> None:
        """Tenant text with hidden and control characters shown as <U+XXXX>, secrets removed."""
        print(trace.visible(redact(text)), file=file or sys.stdout)

    one = trace.visible_line  # a tenant value on one line: a CR or LF in a name cannot move the cursor
    environment = (wxo.v2_environment_line(args.environment_id) if args.route == "v2"
                   else args.environment_id or "server default")
    say(f"host: {config.host}   agent: {one(summary['name'])} (id {one(summary['id'])}, "
        f"style {one(summary.get('style') or '-')}, hide_reasoning {wxo.flag_text(summary.get('hide_reasoning'))})")
    say(f"environment: {one(environment)}   route: {args.route}")
    if args.route == "v2":
        say(f"writes: {len(questions)} stateless v2 chat/completions call(s), one question at a time; nothing is "
            "kept on the tenant, and thread_id is only a correlation id")
    else:
        say(f"writes: {len(questions)} run(s) and {len(questions)} new thread(s) on the tenant, one question at a time")
    say(f"can call: tools {', '.join(one(t) for t in summary['tools']) or 'none'}. Any of them, and any tool of a "
        "collaborator, may change external systems.")
    for other in reachable:
        via = f" (via {one(' > '.join(map(str, other['via'])))})" if other["via"] else ""
        say(f"  collaborator {one(other['name'])}{via}  tools: {wxo.reach_tools_text(other, one)}")
    for qid, question in questions[:5]:
        say(f"  {qid}: {json.dumps(question, ensure_ascii=False)}")
    if len(questions) > 5:
        say(f"  ... and {len(questions) - 5} more")
    if not args.send:
        print("DRY RUN: nothing was sent. Show this to the user; after their yes, run again with --send.")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    statuses: Counter = Counter()
    exit_code = 0
    with open(out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for number, (qid, question) in enumerate(questions, start=1):
            stop = False
            try:
                record, _raw = client.capture_turn(summary["id"], question, route=args.route,
                                                   environment_id=args.environment_id, timeout=args.timeout)
                row = row_of(qid, question, record, trace)
            except wxo.WxoError as err:
                row = dict.fromkeys(COLUMNS, "")
                # capture_turn attaches the ids it knew when it failed: that thread persists too
                row.update(id=qid, question=question, status="error", error=redact(err),
                           thread_id=getattr(err, "thread_id", None) or "", run_id=getattr(err, "run_id", None) or "")
                stop = isinstance(err, (wxo.AuthError, wxo.RateLimited))
                exit_code = 1
            writer.writerow({key: cell(redact(value) if isinstance(value, str) else value)
                             for key, value in row.items()})
            handle.flush()
            statuses[row["status"]] += 1
            latency = row["latency_s"] if row["latency_s"] not in (None, "") else "-"
            say(f"{number}/{len(questions)} {qid}: {row['status']}  tools={row['tools_called'] or '-'}  "
                f"latency={latency} s")
            if stop:
                print("stopping: the remaining questions were not sent", file=sys.stderr)
                break
    print(f"wrote {out}: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())))
    if args.route == "v2":
        print("The v2 calls were stateless: nothing is kept on the tenant; thread_id holds correlation ids only.")
    else:
        print("The threads persist on the tenant; their ids are in the thread_id column.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
