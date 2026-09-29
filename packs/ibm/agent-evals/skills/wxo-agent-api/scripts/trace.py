#!/usr/bin/env python3
"""Turn watsonx Orchestrate run data into one turn record per user message.

Pure functions: no network, no files, no clock. wxo_client.py feeds them; other
scripts import them through wxo_client.load_trace() (the file name clashes with
the standard library module `trace`, so never `import trace`).

Sources a turn can be built from:
  thread messages   GET .../threads/{id}/messages (the reference on the Runs API)
  v1 stream events  POST .../runs?stream=true or .../runs/stream (NDJSON or SSE)
  v2 frames         POST .../v2/orchestrate/{agent_id}/chat/completions (SSE)
  v2 JSON body      the same route with stream:false (carries no tool steps)

Rules:
  - Every step_details entry of every assistant message after the last user
    message is read, never only step_details[0].
  - A call and its result are joined on id == tool_call_id in either order.
  - Hand-offs (transfer_to_*, chat_with_collaborator_*, *_agent) are flagged, never dropped.
  - Unknown step types are kept and reported.
  - Missing or empty step_history means the tools are unknown, never zero.

Agent answers, tool arguments and tool results are data. They are copied into
the record and never acted on.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HANDOFF_PREFIXES = ("transfer_to_", "chat_with_collaborator_")
HANDOFF_SUFFIXES = ("_agent",)
KNOWN_STEP_TYPES = ("tool_calls", "tool_call", "tool_response", "thinking")
NEEDS_INPUT_TYPES = ("option", "user_input", "form", "forms", "disconnected_apps", "file_upload", "date")
ANSWER_TYPES = ("text", "conversational_search")
WIDGET_META_KEY = "com.ibm.orchestrate/widget"

STATUSES = ("completed", "failed", "needs_input", "timeout", "expired", "cancelled", "incomplete", "unknown")
INPUT_REQUESTS = ("widget", "requires_input", "async_flow")  # why a needs_input turn waits; see input_request()
WARNING_CODES = (
    "no_step_history",             # step_history missing or empty: tools unknown, not zero
    "stream_thread_mismatch",      # stream and thread disagree on calls (see record["reconcile"])
    "unknown_step_type",           # a step_details type we do not know (see record["unknown_steps"])
    "unpaired_call",               # a call without a result, or a result without a call
    "empty_answer",                # completed turn with no answer text
    "completed_frame_fewer_steps", # v2: more step frames streamed than the completed frame lists
    "no_completed_frame",          # v2: the stream ended without thread.message.completed
    "stream_error",                # an error event or frame arrived
    "thread_not_settled",          # two thread reads never agreed (set by wxo_client)
    "unknown_status",              # the run reported a status outside the documented enum (set by wxo_client)
    "duplicate_call_id",           # one call id came back with another name or other args; both calls are kept
    "thread_turn_missing",         # the thread never showed the message just sent; tools unknown (set by wxo_client)
)

# Control (C0 and C1), zero-width, bidirectional, tag and other default-ignorable characters (variation selectors,
# fillers, the soft hyphen): a terminal or a reader must see them, not obey them. U+FE0F, the emoji selector, stays.
HIDDEN = re.compile("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5"
                    "\u180b-\u180f\u200b-\u200f\u202a-\u202e\u2028\u2029\u2060-\u206f\u3164\ufe00-\ufe0e\ufeff\uffa0"
                    "\ufff9-\ufffb\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0000-\U000e0fff]")

AGENTOPS_MESSAGE_FIELDS = (
    "role", "content", "type", "interaction", "event", "conversational_search_metadata",
    "tool_calls", "tool_call_id", "response_time", "thread_id", "message_id", "trace_id", "run_id",
)

_TERMINAL_V1 = {
    "run.completed": "completed", "done": "completed",
    "run.failed": "failed", "error": "failed",
    "run.cancelled": "cancelled", "run.expired": "expired",
}
_SEVERITY = {"completed": 0, "expired": 1, "cancelled": 2, "failed": 3}


# --------------------------------------------------------------------------- helpers
def visible(text: Any) -> str:
    """The text with control, zero-width, bidirectional and other invisible characters (HIDDEN) shown as <U+XXXX>.

    Newline, tab and carriage return are kept; callers that print one line collapse them.
    """
    return HIDDEN.sub(lambda m: f"<U+{ord(m.group(0)):04X}>", "" if text is None else str(text))


def visible_line(text: Any) -> str:
    """visible() on one line: whitespace runs, line breaks and carriage returns become one space.

    For tenant values inside a plan or dry-run line, where a CR or LF would move the cursor.
    """
    return " ".join(visible(text).split())


def _json_escape(match: Any) -> str:
    code = ord(match.group(0))
    if code > 0xFFFF:
        code -= 0x10000
        return "\\u%04x\\u%04x" % (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF))
    return "\\u%04x" % code


def visible_json(text: str) -> str:
    """JSON text with every hidden character written as a \\uXXXX escape.

    The JSON value stays the same (those characters only occur inside strings), but a
    terminal shows the escape instead of obeying it. For JSON printed to a console.
    """
    return HIDDEN.sub(_json_escape, text)


def is_handoff(name: Any, extra_names: Iterable[str] = ()) -> bool:
    """True when a tool name looks like a hand-off to another agent.

    Heuristic by name: transfer_to_*, chat_with_collaborator_*, *_agent, or a name in extra_names.
    """
    if not isinstance(name, str) or not name:
        return False
    if name in set(extra_names or ()):
        return True
    return name.startswith(HANDOFF_PREFIXES) or name.endswith(HANDOFF_SUFFIXES)


def handoff_target(name: Any) -> Optional[str]:
    """The collaborator a prefixed hand-off name points at, else None.

    chat_with_collaborator_payroll_agent and transfer_to_payroll_agent both give payroll_agent:
    the prefix depends on the agent style and the route, not on the collaborator.
    """
    if isinstance(name, str):
        for prefix in HANDOFF_PREFIXES:
            if name.startswith(prefix) and len(name) > len(prefix):
                return name[len(prefix):]
    return None


def same_tool(expected: Any, observed: Any) -> bool:
    """True when an observed call name satisfies an expected tool name: equal, or both prefixed hand-offs to one collaborator."""
    if expected == observed:
        return True
    target = handoff_target(expected)
    return target is not None and target == handoff_target(observed)


def json_or_value(value: Any) -> Any:
    """A string holding a JSON object or array becomes that object; anything else is returned as is."""
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("{", "["):
            try:
                return json.loads(text)
            except ValueError:
                return value
    return value


def canonical_args(args: Any) -> str:
    """Stable text form of tool arguments for comparison: JSON with sorted keys after json_or_value."""
    return json.dumps(json_or_value(args), sort_keys=True, ensure_ascii=False, default=str)


def unwrap_messages(doc: Any) -> Tuple[List[dict], str]:
    """Thread messages come as a list or wrapped: {"data": [...]}. Returns (messages, shape).

    shape is "list", "data", "messages" or "unknown" (then messages is []).
    """
    if isinstance(doc, list):
        return [m for m in doc if isinstance(m, dict)], "list"
    if isinstance(doc, dict):
        for key in ("data", "messages"):
            if isinstance(doc.get(key), list):
                return [m for m in doc[key] if isinstance(m, dict)], key
    return [], "unknown"


def text_of(content: Any) -> str:
    """Plain text of a message content: a string, or a list of items with text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        content = [content]
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                rtype = item.get("response_type") or item.get("type") or "text"
                if rtype in ANSWER_TYPES and isinstance(item.get("text"), str):
                    texts.append(item["text"])
        return "\n\n".join(t for t in texts if t)
    return str(content)


def walk_find(obj: Any, key: str, path: str = "$") -> List[str]:
    """JSON paths of every occurrence of `key` in a parsed document (used to look for step_details)."""
    found: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}"
            if k == key:
                found.append(here)
            found.extend(walk_find(v, key, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(walk_find(v, key, f"{path}[{i}]"))
    return found


def turn_status(run_status: Optional[str], widgets: Sequence[dict] = (), flow_listen: bool = False) -> str:
    """Map a server run status plus what the turn showed to one of STATUSES.

    failed, cancelled, expired and timeout win; then widgets, flow.slot.listen,
    requires_input and async_wait give needs_input; completed stays completed;
    pending, running and async_completed give incomplete; anything else is unknown.
    """
    status = (run_status or "").strip().lower()
    if status in ("failed", "cancelled", "expired", "timeout"):
        return status
    if widgets or flow_listen or status in ("requires_input", "async_wait", "needs_input"):
        return "needs_input"
    if status == "completed":
        return "completed"
    if status in ("pending", "running", "async_completed", "incomplete"):
        return "incomplete"
    return "unknown"


def input_request(run_status: Optional[str], widgets: Sequence[dict] = (), flow_listen: bool = False) -> Optional[str]:
    """Why a turn waits for the user, or None.

    async_flow: the run is in async_wait, the stream sent flow.slot.listen, or (flow_listen from
    _turn_from_group) a completed run's last assistant message is an async flow's holding message.
    The flow keeps running on the server and adds its messages to the thread later, so a scripted
    next message must not be sent. requires_input: the run asked for input. widget: the answer
    holds an option, form or other widget; a scripted next message may answer it.
    """
    status = (run_status or "").strip().lower()
    if flow_listen or status == "async_wait":
        return "async_flow"
    if status == "requires_input":
        return "requires_input"
    if widgets:
        return "widget"
    return None


def tools_known(turn: dict) -> bool:
    """False when the turn carried no step history: its tool metrics are 'unknown', never zero."""
    return "no_step_history" not in (turn.get("warnings") or [])


def wire_only_calls(turn: dict) -> List[dict]:
    """Calls the stream showed that the turn's source of truth left out: [{id, name}].

    From record["reconcile"]["only_in_stream"] (a v1 stream read against the thread, or v2
    step deltas against the completed frame), minus calls tool_calls already holds. They do
    not count for recall or precision, but a forbidden tool among them did run.
    """
    wire = ((turn.get("reconcile") or {}).get("only_in_stream") or []) if isinstance(turn, dict) else []
    budget = Counter((c.get("id"), c.get("name")) for c in turn.get("tool_calls") or [] if isinstance(c, dict))
    out = []
    for call in wire:
        if not isinstance(call, dict):
            continue
        key = (call.get("id"), call.get("name"))
        if budget[key] > 0:
            budget[key] -= 1
        else:
            out.append({"id": call.get("id"), "name": call.get("name")})
    return out


def new_turn(turn: int = 0, user_text: Optional[str] = None, capture: str = "thread",
             source_of_truth: str = "thread") -> dict:
    """An empty turn record with every field present."""
    return {
        "turn": turn,
        "user_text": user_text,
        "run_id": None,
        "thread_id": None,
        "trace_id": None,
        "status": "unknown",
        "run_status": None,
        "input_request": None,
        "stateless": False,
        "capture": capture,
        "source_of_truth": source_of_truth,
        "answer": "",
        "answer_parts": [],
        "tool_calls": [],
        "thinking_count": 0,
        "widgets": [],
        "timings": {"client_wall_s": None, "server_started_at": None, "server_completed_at": None, "per_step": None},
        "usage": None,
        "warnings": [],
        "unknown_steps": [],
    }


def _warn(turn: dict, code: str) -> None:
    if code not in turn["warnings"]:
        turn["warnings"].append(code)


# --------------------------------------------------------------------------- steps
def normalise_detail(detail: Any) -> List[dict]:
    """One step_details entry -> a list of normalised steps.

    {"kind": "call", "id", "name", "args", "agent_display_name"}   from tool_calls (one per call) or tool_call
    {"kind": "result", "tool_call_id", "name", "content"}           from tool_response
    {"kind": "thinking", "content"}                                   from thinking
    {"kind": "unknown", "type", "keys"}                               anything else (kept, never dropped)
    """
    if not isinstance(detail, dict):
        return [{"kind": "unknown", "type": None, "keys": []}]
    dtype = detail.get("type")
    display = detail.get("agent_display_name")
    if dtype == "tool_calls":
        out = []
        for call in detail.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            out.append({
                "kind": "call",
                "id": call.get("id") or call.get("tool_call_id") or None,
                "name": call.get("name"),
                "args": call.get("args", call.get("arguments")),
                "agent_display_name": call.get("agent_display_name") or display,
            })
        return out
    if dtype == "tool_call":
        return [{
            "kind": "call",
            "id": detail.get("tool_call_id") or detail.get("id") or None,
            "name": detail.get("name"),
            "args": detail.get("args", detail.get("arguments")),
            "agent_display_name": display,
        }]
    if dtype == "tool_response":
        return [{
            "kind": "result",
            "tool_call_id": detail.get("tool_call_id") or None,
            "name": detail.get("name"),
            "content": detail.get("content"),
        }]
    if dtype == "thinking":
        return [{"kind": "thinking", "content": detail.get("content")}]
    return [{"kind": "unknown", "type": dtype, "keys": sorted(str(k) for k in detail)}]


def _details_of(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def steps_from_messages(messages: Sequence[dict]) -> Tuple[List[dict], bool]:
    """Every step of every step_history entry of the given assistant messages, in order.

    Returns (steps, has_history). has_history is False when no message had a
    non-empty step_history list: the tools of the turn are then unknown.
    """
    steps: List[dict] = []
    has_history = False
    for message in messages:
        history = message.get("step_history")
        if not isinstance(history, list) or not history:
            continue
        has_history = True
        for step in history:
            if not isinstance(step, dict):
                continue
            for detail in _details_of(step.get("step_details")):
                steps.extend(normalise_detail(detail))
    return steps, has_history


def _result_of(step: dict) -> dict:
    content = step.get("content")
    result = {"content": content, "tool_call_id": step.get("tool_call_id")}
    parsed = content if isinstance(content, (dict, list)) else json_or_value(content)
    if isinstance(parsed, (dict, list)):
        result["content_json"] = parsed
    return result


def pair_steps(steps: Sequence[dict], handoff_names: Iterable[str] = ()) -> dict:
    """Join calls and results into tool_call records.

    Returns {"tool_calls", "thinking_count", "unknown_steps", "warnings"}. Each
    tool_call is {id, name, args, result, handoff, agent_display_name?, t_call?, t_result?}.
    A call's position is where its call or its result first appeared, so a
    hand-off that arrives as [tool_response, tool_call] keeps one record.
    A call whose id was seen before joins that record only when the record holds
    a result alone, or the same name and arguments. Another name or other
    arguments under a known id make a new record and the warning duplicate_call_id.
    When only one side carries an id, a call and a result of the same name still
    join: a result takes the earliest call of its name that has no result (and no id,
    when the result carries one), so parallel calls of one tool get their results in
    order; a call without an id takes the latest result of its name that has no call yet.
    Steps may carry "t" (seconds from the request); it becomes t_call / t_result.
    """
    handoff_names = tuple(handoff_names or ())
    records: List[dict] = []
    by_id: Dict[str, dict] = {}
    thinking = 0
    unknown: List[dict] = []
    warnings: List[str] = []

    def new_record(call_id, name):
        rec = {"id": call_id, "name": name, "args": None, "result": None,
               "handoff": is_handoff(name, handoff_names), "_call": False}
        records.append(rec)
        if call_id:
            by_id[call_id] = rec
        return rec

    def set_result(rec, step):
        res = _result_of(step)
        if rec["result"] is None or rec["result"].get("content") != res.get("content"):
            rec["result"] = res
        if step.get("t") is not None and "t_result" not in rec:
            rec["t_result"] = step["t"]
        if not rec["name"] and step.get("name"):
            rec["name"] = step["name"]
            rec["handoff"] = is_handoff(rec["name"], handoff_names)

    def same_call(rec, step):
        if step.get("name") and rec["name"] and step["name"] != rec["name"]:
            return False
        return step.get("args") is None or rec["args"] is None or \
            canonical_args(step.get("args")) == canonical_args(rec["args"])

    def claim(rec, call_id):
        if call_id and not rec["id"]:
            rec["id"] = call_id
            by_id[call_id] = rec
        return rec

    for step in steps:
        kind = step.get("kind")
        if kind == "call":
            call_id = step.get("id")
            rec = by_id.get(call_id) if call_id else None
            if rec is not None and rec["_call"] and not same_call(rec, step):
                if "duplicate_call_id" not in warnings:
                    warnings.append("duplicate_call_id")
                rec = None
            elif rec is None:  # a result that came first, when only one side carries an id
                rec = next((r for r in reversed(records) if not r["_call"] and r["result"] is not None
                            and r["name"] == step.get("name") and (not call_id or not r["id"])), None)
                rec = claim(rec, call_id) if rec is not None else None
            if rec is None:
                rec = new_record(call_id, step.get("name"))
            if step.get("name"):
                rec["name"] = step["name"]
                rec["handoff"] = is_handoff(step["name"], handoff_names)
            if rec["args"] is None or not rec["_call"]:
                rec["args"] = json_or_value(step.get("args"))
            rec["_call"] = True
            if step.get("agent_display_name"):
                rec["agent_display_name"] = step["agent_display_name"]
            if step.get("t") is not None and "t_call" not in rec:
                rec["t_call"] = step["t"]
        elif kind == "result":
            call_id = step.get("tool_call_id")
            rec = by_id.get(call_id) if call_id else None
            if rec is None:  # the earliest open call of this name; with an id here, only a call that had none
                rec = next((r for r in records if r["result"] is None and r["_call"]
                            and r["name"] == step.get("name") and (not call_id or not r["id"])), None)
                rec = claim(rec, call_id) if rec is not None else None
            if rec is None:
                rec = new_record(call_id, step.get("name"))
            set_result(rec, step)
        elif kind == "thinking":
            thinking += 1
        else:
            unknown.append({"type": step.get("type"), "keys": step.get("keys", [])})
            if "unknown_step_type" not in warnings:
                warnings.append("unknown_step_type")

    calls = []
    for rec in records:
        if not rec["_call"] or rec["result"] is None:
            if "unpaired_call" not in warnings:
                warnings.append("unpaired_call")
        rec.pop("_call")
        calls.append(rec)
    return {"tool_calls": calls, "thinking_count": thinking, "unknown_steps": unknown, "warnings": warnings}


# --------------------------------------------------------------------------- content
def _item_text(item: dict) -> str:
    for key in ("text", "title", "description", "label"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _widget(item: dict, message: dict) -> dict:
    meta = item.get("_meta") if isinstance(item.get("_meta"), dict) else {}
    spec = meta.get(WIDGET_META_KEY)
    if spec is None and isinstance(message.get("_meta"), dict):
        spec = message["_meta"].get(WIDGET_META_KEY)
    options = []
    for opt in item.get("options") or (spec or {}).get("options") or []:
        if isinstance(opt, dict):
            options.append(opt.get("label") or opt.get("value") or "")
        else:
            options.append(opt)
    return {"type": item.get("response_type") or item.get("type"), "text": _item_text(item),
            "options": options, "widget": spec}


def display_flags(message: dict) -> Dict[str, bool]:
    """additional_properties.display_properties of a message: {"is_async", "skip_render"} (False when absent)."""
    props = message.get("additional_properties")
    display = props.get("display_properties") if isinstance(props, dict) else None
    display = display if isinstance(display, dict) else {}
    return {"is_async": display.get("is_async") is True, "skip_render": display.get("skip_render") is True}


def content_parts(messages: Sequence[dict]) -> dict:
    """Answer text, answer_parts and widgets from assistant message content.

    Returns {"answer", "answer_parts", "widgets"}. answer joins the text of
    text and conversational_search parts. A message marked
    additional_properties.display_properties.is_async (an async flow's holding
    message) is left out of the answer when another message gives answer text,
    as the ADK chat does; its parts stay in answer_parts with "is_async": true
    and "in_answer": false. skip_render is only flagged on the part, since its
    meaning is not documented. Items whose response_type needs the user
    (option, user_input, form, forms, disconnected_apps, file_upload, date) become
    widgets; so does a message-level _meta widget spec.
    """
    parts: List[dict] = []
    widgets: List[dict] = []
    for message in messages:
        flags = {k: True for k, v in display_flags(message).items() if v}
        first_part = len(parts)
        items = message.get("content")
        if isinstance(items, str):
            items = [{"response_type": "text", "text": items}]
        elif isinstance(items, dict):
            items = [items]
        has_item_widget = False
        for item in items or []:
            if not isinstance(item, dict):
                continue
            rtype = item.get("response_type") or item.get("type") or "text"
            if rtype == "text":
                parts.append({"type": "text", "text": item.get("text") or ""})
            elif rtype == "conversational_search":
                parts.append({"type": "conversational_search", "text": item.get("text") or "",
                              "citations": list(item.get("citations") or [])})
            elif rtype in NEEDS_INPUT_TYPES:
                widgets.append(_widget(item, message))
                has_item_widget = True
                parts.append({"type": rtype, "text": _item_text(item)})
            else:
                parts.append({"type": rtype, "text": _item_text(item)})
        for part in parts[first_part:]:
            part.update(flags)
        meta = message.get("_meta")
        if not has_item_widget and isinstance(meta, dict) and meta.get(WIDGET_META_KEY):
            spec = meta[WIDGET_META_KEY]
            widgets.append({"type": spec.get("type") if isinstance(spec, dict) else None,
                            "text": _item_text(spec) if isinstance(spec, dict) else "",
                            "options": [o.get("label") if isinstance(o, dict) else o
                                        for o in ((spec or {}).get("options") or [])] if isinstance(spec, dict) else [],
                            "widget": spec})
    answering = [p for p in parts if p["type"] in ANSWER_TYPES and p["text"]]
    chosen = [p for p in answering if not p.get("is_async")] or answering
    for part in answering:
        if not any(part is c for c in chosen):
            part["in_answer"] = False
    answer = "\n\n".join(p["text"] for p in chosen)
    return {"answer": answer, "answer_parts": parts, "widgets": widgets}


def _attach_search(turn: dict) -> None:
    """A conversational_search answer has no tool_call_id: attach it to the last tool step."""
    call_id = None
    for call in reversed(turn["tool_calls"]):
        if call.get("result") and call["result"].get("tool_call_id"):
            call_id = call["result"]["tool_call_id"]
            break
    if call_id is None:
        for call in reversed(turn["tool_calls"]):
            if call.get("id"):
                call_id = call["id"]
                break
    for part in turn["answer_parts"]:
        if part["type"] == "conversational_search":
            part["tool_call_id"] = call_id


def _fill(turn: dict, paired: dict, content: dict) -> None:
    turn["tool_calls"] = paired["tool_calls"]
    turn["thinking_count"] = paired["thinking_count"]
    turn["unknown_steps"] = paired["unknown_steps"]
    for code in paired["warnings"]:
        _warn(turn, code)
    turn["answer"] = content["answer"]
    turn["answer_parts"] = content["answer_parts"]
    turn["widgets"] = content["widgets"]
    _attach_search(turn)


def _finish(turn: dict) -> dict:
    if turn["status"] == "completed" and not turn["answer"]:
        _warn(turn, "empty_answer")
    return turn


# --------------------------------------------------------------------------- thread
def split_turns(messages: Any) -> List[Tuple[Optional[dict], List[dict]]]:
    """Group thread messages into (user message, assistant messages after it) pairs.

    Assistant messages before the first user message are ignored. Messages
    with other roles (tool messages are excluded by the API anyway) are skipped.
    """
    msgs, _ = unwrap_messages(messages)
    groups: List[Tuple[Optional[dict], List[dict]]] = []
    for message in msgs:
        role = message.get("role")
        if role == "user":
            groups.append((message, []))
        elif role == "assistant" and groups:
            groups[-1][1].append(message)
    return groups


def last_turn_messages(messages: Any) -> Tuple[Optional[dict], List[dict]]:
    """(last user message, every assistant message after it). With no user message: (None, all assistant messages)."""
    msgs, _ = unwrap_messages(messages)
    last_user = None
    for index, message in enumerate(msgs):
        if message.get("role") == "user":
            last_user = index
    if last_user is None:
        return None, [m for m in msgs if m.get("role") == "assistant"]
    return msgs[last_user], [m for m in msgs[last_user + 1:] if m.get("role") == "assistant"]


def _first(messages: Sequence[dict], key: str) -> Optional[str]:
    for message in messages:
        value = message.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _turn_from_group(user: Optional[dict], assistants: List[dict], *, turn: int, user_text: Optional[str],
                     run: Optional[dict], status: Optional[str], run_id: Optional[str], thread_id: Optional[str],
                     client_wall_s: Optional[float], handoff_names: Iterable[str]) -> dict:
    record = new_turn(turn, user_text if user_text is not None else (text_of(user.get("content")) if user else None))
    run = run if isinstance(run, dict) else {}
    steps, has_history = steps_from_messages(assistants)
    _fill(record, pair_steps(steps, handoff_names), content_parts(assistants))
    if not has_history:
        _warn(record, "no_step_history")
    server_status = run.get("status")
    record["run_status"] = server_status if server_status is not None else status
    effective = status if status is not None else server_status
    if effective is None:
        effective = "completed" if assistants else None
    # A run completes while an async flow goes on; its last message is the flow's holding message, marked
    # is_async. The ADK chat reads the flow from that flag; the thread takes no new message until the flow ends.
    flow = bool(assistants) and display_flags(assistants[-1])["is_async"]
    record["status"] = turn_status(effective, record["widgets"], flow)
    if record["status"] == "needs_input":
        record["input_request"] = input_request(effective, record["widgets"], flow)
    record["run_id"] = run_id or run.get("id") or run.get("run_id") or _first(assistants, "run_id")
    record["thread_id"] = (thread_id or run.get("thread_id") or _first(assistants, "thread_id")
                           or (user or {}).get("thread_id"))
    record["trace_id"] = run.get("trace_id") or _first(assistants, "trace_id")
    record["usage"] = run.get("usage")
    record["timings"]["client_wall_s"] = client_wall_s
    record["timings"]["server_started_at"] = run.get("started_at")
    record["timings"]["server_completed_at"] = run.get("completed_at")
    return _finish(record)


def turn_from_thread(messages: Any, *, turn: int = 0, user_text: Optional[str] = None, run: Optional[dict] = None,
                     status: Optional[str] = None, run_id: Optional[str] = None, thread_id: Optional[str] = None,
                     client_wall_s: Optional[float] = None, handoff_names: Iterable[str] = ()) -> dict:
    """The turn after the last user message of a thread, as one turn record.

    messages: the GET thread messages document (list or {"data": [...]}).
    run: the GET /runs/{id} record; gives run_status, trace_id, usage and server times.
    status: overrides the run's status (wxo_client passes "timeout" when polling ran out).
    Without run and status, a turn with assistant messages counts as completed. When the last
    assistant message is marked additional_properties.display_properties.is_async, an async
    flow still runs: status needs_input, input_request async_flow.
    """
    user, assistants = last_turn_messages(messages)
    return _turn_from_group(user, assistants, turn=turn, user_text=user_text, run=run, status=status,
                            run_id=run_id, thread_id=thread_id, client_wall_s=client_wall_s,
                            handoff_names=handoff_names)


def turns_from_thread(messages: Any, handoff_names: Iterable[str] = ()) -> List[dict]:
    """Every turn of a thread (one per user message), numbered from 0. No run data, so status comes from content."""
    return [
        _turn_from_group(user, assistants, turn=index, user_text=None, run=None, status=None, run_id=None,
                         thread_id=None, client_wall_s=None, handoff_names=handoff_names)
        for index, (user, assistants) in enumerate(split_turns(messages))
    ]


# --------------------------------------------------------------------------- v1 stream
def _event_parts(event: dict) -> Tuple[Optional[str], dict]:
    name = event.get("event")
    data = event.get("data")
    return (name if isinstance(name, str) else None), (data if isinstance(data, dict) else {})


def turn_from_stream(events: Sequence[dict], *, turn: int = 0, user_text: Optional[str] = None,
                     handoff_names: Iterable[str] = ()) -> dict:
    """A v1 Runs stream (events from wxo_client.parse_stream) as one turn record.

    Steps come from data.delta.step_details of any event (run.step.delta in
    practice), with the event's arrival time "t". The answer comes from
    message.created events whose data.message carries a role; role-less ones
    are skipped. When data.message has no role and no content (the Hub RunEvent
    types it {key, text}), a content list directly under data is read instead.
    Text in message.delta, or a plain string delta.content in run.step.delta
    (a Hub example), is the fallback answer. flow.slot.listen gives needs_input
    with input_request async_flow. Unknown event names are ignored. capture and
    source_of_truth are "stream".
    """
    record = new_turn(turn, user_text, capture="stream", source_of_truth="stream")
    steps: List[dict] = []
    messages: List[dict] = []
    delta_text: List[str] = []
    flow_listen = False
    saw_steps = False
    terminal: Optional[str] = None
    for event in events:
        name, data = _event_parts(event)
        t = event.get("t")
        record["thread_id"] = record["thread_id"] or data.get("thread_id")
        record["run_id"] = record["run_id"] or data.get("run_id")
        delta = data.get("delta")
        if isinstance(delta, dict):
            details = delta.get("step_details")
            if details is not None:
                saw_steps = True
                for detail in _details_of(details):
                    for step in normalise_detail(detail):
                        step["t"] = t
                        steps.append(step)
            elif delta.get("role") == "tool" and delta.get("tool_call_id"):
                saw_steps = True
                steps.append({"kind": "result", "tool_call_id": delta.get("tool_call_id"),
                              "name": delta.get("name"), "content": delta.get("content"), "t": t})
            elif name == "message.delta":
                chunk = delta.get("content")
                if isinstance(chunk, str):
                    delta_text.append(chunk)
                elif isinstance(chunk, list):
                    delta_text.extend(i.get("text", "") for i in chunk if isinstance(i, dict))
            elif name == "run.step.delta" and isinstance(delta.get("content"), str):
                delta_text.append(delta["content"])
        if name == "message.created":
            message = data.get("message")
            if isinstance(message, dict) and message.get("role"):
                messages.append(message)
            elif (not isinstance(message, dict) or not message.get("content")) \
                    and isinstance(data.get("content"), list) and data.get("role", "assistant") == "assistant":
                messages.append({k: data[k] for k in ("role", "content", "_meta", "additional_properties") if k in data})
        elif name == "flow.slot.listen":
            flow_listen = True
        if name in _TERMINAL_V1:
            mapped = _TERMINAL_V1[name]
            if terminal is None or _SEVERITY[mapped] > _SEVERITY[terminal]:
                terminal = mapped
        if name == "error":
            _warn(record, "stream_error")
    _fill(record, pair_steps(steps, handoff_names), content_parts(messages))
    if not record["answer"] and delta_text:
        record["answer"] = "".join(delta_text)
        record["answer_parts"].append({"type": "text", "text": record["answer"]})
    if not saw_steps:
        _warn(record, "no_step_history")
    record["run_status"] = terminal
    record["status"] = turn_status(terminal or "incomplete", record["widgets"], flow_listen)
    if record["status"] == "needs_input":
        record["input_request"] = input_request(terminal, record["widgets"], flow_listen)
    record["timings"]["per_step"] = [
        {"kind": s["kind"], "id": s.get("id") or s.get("tool_call_id"), "name": s.get("name"), "t": s.get("t")}
        for s in steps if s["kind"] in ("call", "result", "thinking")
    ]
    return _finish(record)


def _call_key(call: dict) -> Tuple[Any, Any, str]:
    return (call.get("id"), call.get("name"), canonical_args(call.get("args")))


def _surplus(calls: Sequence[dict], others: Sequence[dict]) -> List[dict]:
    """Calls of `calls` left over after each is matched once against `others` (a multiset difference)."""
    budget = Counter(_call_key(c) for c in others)
    out = []
    for call in calls:
        key = _call_key(call)
        if budget[key] > 0:
            budget[key] -= 1
        else:
            out.append(call)
    return out


def reconcile(stream_turn: dict, thread_turn: dict) -> dict:
    """Merge a stream-captured turn with the thread read of the same run.

    The thread is the source of truth: its calls, results and answer are kept,
    and stream timings (t_call, t_result, per_step) are copied onto matching
    calls (by id, else by name and order). Calls are compared as a multiset, so
    a call repeated on one side only counts. When the calls differ, the record
    gets stream_thread_mismatch and record["reconcile"] =
    {"only_in_stream": [{id, name}], "only_in_thread": [{id, name}]}.
    When the thread has no step history but the stream has steps, the stream's
    calls are used and source_of_truth becomes "stream"; stream_thread_mismatch then
    lists the stream's calls, and is left out when the stream showed none.
    capture is "stream" in the result.
    """
    merged = copy.deepcopy(thread_turn)
    merged["capture"] = "stream"
    merged["source_of_truth"] = "thread"
    merged["timings"]["per_step"] = copy.deepcopy(stream_turn["timings"].get("per_step"))
    for key in ("thread_id", "run_id", "trace_id"):
        merged[key] = merged.get(key) or stream_turn.get(key)
    if not tools_known(thread_turn) and tools_known(stream_turn):
        merged["tool_calls"] = copy.deepcopy(stream_turn["tool_calls"])
        merged["warnings"] = [w for w in merged["warnings"] if w != "no_step_history"]
        merged["source_of_truth"] = "stream"
        if stream_turn["tool_calls"]:  # the thread side is unknown, not empty: say what only the stream showed
            _warn(merged, "stream_thread_mismatch")
            merged["reconcile"] = {"only_in_stream": [{"id": c.get("id"), "name": c.get("name")}
                                                      for c in stream_turn["tool_calls"]], "only_in_thread": []}
        for code in stream_turn["warnings"]:
            if code in ("unpaired_call", "unknown_step_type"):
                _warn(merged, code)
    elif tools_known(thread_turn) and tools_known(stream_turn):
        only_stream = _surplus(stream_turn["tool_calls"], thread_turn["tool_calls"])
        only_thread = _surplus(thread_turn["tool_calls"], stream_turn["tool_calls"])
        if only_stream or only_thread:
            _warn(merged, "stream_thread_mismatch")
            merged["reconcile"] = {
                "only_in_stream": [{"id": c.get("id"), "name": c.get("name")} for c in only_stream],
                "only_in_thread": [{"id": c.get("id"), "name": c.get("name")} for c in only_thread],
            }
        by_id = {c["id"]: c for c in stream_turn["tool_calls"] if c.get("id")}
        used = set()
        for call in merged["tool_calls"]:
            match = by_id.get(call.get("id")) if call.get("id") else None
            if match is None:
                match = next((c for c in stream_turn["tool_calls"]
                              if id(c) not in used and c.get("name") == call.get("name") and not c.get("id")), None)
            if match is not None:
                used.add(id(match))
                for key in ("t_call", "t_result"):
                    if key in match:
                        call[key] = match[key]
    if not merged["answer"] and stream_turn.get("answer"):
        merged["answer"] = stream_turn["answer"]
        merged["answer_parts"] = copy.deepcopy(stream_turn["answer_parts"])
        merged["warnings"] = [w for w in merged["warnings"] if w != "empty_answer"]
    if stream_turn["status"] == "needs_input" and merged["status"] in ("completed", "unknown", "incomplete",
                                                                       "needs_input"):
        merged["status"] = "needs_input"
        if stream_turn.get("input_request") == "async_flow" or not merged.get("input_request"):
            merged["input_request"] = stream_turn.get("input_request")
    return merged


# --------------------------------------------------------------------------- v2
def _frame_of(event: dict) -> dict:
    frame = event.get("frame")
    if isinstance(frame, dict):
        return frame
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _choice(frame: dict) -> dict:
    choices = frame.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0]
    return {}


def turn_from_v2(events: Sequence[dict], *, turn: int = 0, user_text: Optional[str] = None,
                 handoff_names: Iterable[str] = ()) -> dict:
    """A v2 chat/completions SSE stream as one turn record.

    The thread.message.completed frame is the source of truth
    (data.message.step_details, data.message.content, choices[0].message.content).
    thread.run.step.delta frames only add timing; when they outnumber the
    completed frame's steps, completed_frame_fewer_steps is set and calls seen
    only in deltas are listed in record["reconcile"]["only_in_stream"].
    Missing data.message.step_details means tools unknown (no_step_history).
    Without a completed frame the turn is rebuilt from the deltas,
    source_of_truth "v2_deltas", warning no_completed_frame.
    """
    record = new_turn(turn, user_text, capture="v2", source_of_truth="v2_completed")
    delta_steps: List[dict] = []
    step_frames = 0
    text_chunks: List[str] = []
    completed: Optional[dict] = None
    error_text: Optional[str] = None
    run_ids: List[str] = []
    trace_ids: List[str] = []
    for event in events:
        frame = _frame_of(event)
        name = event.get("event") or frame.get("object")
        for value, sink in ((frame.get("run_id"), run_ids), (frame.get("trace_id"), trace_ids)):
            if isinstance(value, str) and value and value not in sink:
                sink.append(value)
        record["thread_id"] = record["thread_id"] or frame.get("thread_id")
        delta = _choice(frame).get("delta")
        delta = delta if isinstance(delta, dict) else {}
        if name == "thread.run.step.delta":
            step_frames += 1
            for detail in _details_of(delta.get("step_details")):
                for step in normalise_detail(detail):
                    step["t"] = event.get("t")
                    delta_steps.append(step)
        elif name == "thread.message.delta":
            if isinstance(delta.get("content"), str):
                text_chunks.append(delta["content"])
        elif name == "thread.message.completed":
            completed = frame
        elif name == "error":
            error_text = delta.get("content") if isinstance(delta.get("content"), str) else "error frame"
            _warn(record, "stream_error")
    record["run_id"] = run_ids[-1] if run_ids else None
    record["trace_id"] = trace_ids[-1] if trace_ids else None
    if completed is None:
        record["source_of_truth"] = "v2_deltas"
        _warn(record, "no_completed_frame")
        _fill(record, pair_steps(delta_steps, handoff_names), {"answer": "", "answer_parts": [], "widgets": []})
        if not delta_steps:
            _warn(record, "no_step_history")
        record["answer"] = "".join(text_chunks)
        if record["answer"]:
            record["answer_parts"] = [{"type": "text", "text": record["answer"]}]
        record["status"] = "failed" if error_text is not None else "incomplete"
        record["run_status"] = record["status"]
        return _finish(record)

    record["thread_id"] = completed.get("thread_id") or record["thread_id"]
    data = completed.get("data") if isinstance(completed.get("data"), dict) else {}
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    raw_steps = message.get("step_details")
    steps: List[dict] = []
    for detail in _details_of(raw_steps):
        steps.extend(normalise_detail(detail))
    times: Dict[Tuple[str, Any], Any] = {}
    for step in delta_steps:
        key = (step["kind"], step.get("id") or step.get("tool_call_id"))
        if key[1] and key not in times:
            times[key] = step.get("t")
    for step in steps:
        key = (step["kind"], step.get("id") or step.get("tool_call_id"))
        if key in times:
            step["t"] = times[key]
    content = content_parts([message]) if message else {"answer": "", "answer_parts": [], "widgets": []}
    _fill(record, pair_steps(steps, handoff_names), content)
    flat = _choice(completed).get("message")
    flat = flat if isinstance(flat, dict) else {}
    if not record["answer"] and isinstance(flat.get("content"), str) and flat["content"]:
        record["answer"] = flat["content"]
        record["answer_parts"].append({"type": "text", "text": flat["content"]})
    if isinstance(flat.get("_meta"), dict) and flat["_meta"].get(WIDGET_META_KEY) and not record["widgets"]:
        record["widgets"].extend(content_parts([{"content": [], "_meta": flat["_meta"]}])["widgets"])
    if not isinstance(raw_steps, list):
        _warn(record, "no_step_history")
    completed_count = len(raw_steps) if isinstance(raw_steps, list) else 0
    if step_frames > completed_count:
        _warn(record, "completed_frame_fewer_steps")
        known = {_call_key(c) for c in record["tool_calls"]}
        extra = pair_steps(delta_steps, handoff_names)["tool_calls"]
        only = [{"id": c.get("id"), "name": c.get("name")} for c in extra if _call_key(c) not in known]
        if only:
            record["reconcile"] = {"only_in_stream": only, "only_in_thread": []}
    record["timings"]["per_step"] = [
        {"kind": s["kind"], "id": s.get("id") or s.get("tool_call_id"), "name": s.get("name"), "t": s.get("t")}
        for s in delta_steps if s["kind"] in ("call", "result", "thinking")
    ]
    record["run_status"] = "failed" if error_text is not None else "completed"
    record["status"] = turn_status(record["run_status"], record["widgets"])
    if record["status"] == "needs_input":
        record["input_request"] = input_request(record["run_status"], record["widgets"])
    return _finish(record)


def turn_from_v2_body(body: Any, *, turn: int = 0, user_text: Optional[str] = None,
                      handoff_names: Iterable[str] = ()) -> dict:
    """A v2 chat/completions stream:false JSON body as one turn record.

    The documented body has no step_details, so tool calls are reported as
    unavailable: tool_calls [] with warning no_step_history. If a server ever
    adds data.message.step_details, they are read. source_of_truth "v2_body".
    """
    record = new_turn(turn, user_text, capture="v2", source_of_truth="v2_body")
    body = body if isinstance(body, dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    raw_steps = message.get("step_details")
    steps: List[dict] = []
    for detail in _details_of(raw_steps):
        steps.extend(normalise_detail(detail))
    _fill(record, pair_steps(steps, handoff_names), content_parts([message]) if message else
          {"answer": "", "answer_parts": [], "widgets": []})
    flat = _choice(body).get("message")
    flat = flat if isinstance(flat, dict) else {}
    if not record["answer"] and isinstance(flat.get("content"), str) and flat["content"]:
        record["answer"] = flat["content"]
        record["answer_parts"].append({"type": "text", "text": flat["content"]})
    if isinstance(flat.get("_meta"), dict) and flat["_meta"].get(WIDGET_META_KEY) and not record["widgets"]:
        record["widgets"].extend(content_parts([{"content": [], "_meta": flat["_meta"]}])["widgets"])
    if not isinstance(raw_steps, list):
        _warn(record, "no_step_history")
    record["thread_id"] = body.get("thread_id")
    record["run_id"] = body.get("run_id")
    record["trace_id"] = body.get("trace_id")
    record["run_status"] = "completed"
    record["status"] = turn_status("completed", record["widgets"])
    if record["status"] == "needs_input":
        record["input_request"] = input_request("completed", record["widgets"])
    return _finish(record)


# --------------------------------------------------------------------------- export and display
def _clean(message: dict) -> dict:
    return {k: v for k, v in message.items() if k in AGENTOPS_MESSAGE_FIELDS and v is not None}


def to_agentops_messages(turns: Sequence[dict]) -> List[dict]:
    """Turn records -> a list of agentops Message dicts (the <case>.messages.json content).

    Per turn: the user message (type text), then each tool call (type tool_call,
    content = JSON {"type": "tool_call", "id", "name", "args"}, plus tool_calls
    [{id, type: "function", function: {name, arguments}}]) followed by its result
    (type tool_response, content = JSON {"type": "tool_response", "name",
    "content", "tool_call_id"}), then the answer parts (type text;
    conversational_search parts carry conversational_search_metadata.tool_call_id).
    Every message carries thread_id, run_id and trace_id when known. Keys are
    limited to AGENTOPS_MESSAGE_FIELDS and None values are left out.
    """
    out: List[dict] = []
    for turn in turns:
        ids = {"thread_id": turn.get("thread_id"), "run_id": turn.get("run_id"), "trace_id": turn.get("trace_id")}
        if turn.get("user_text") is not None:
            out.append(_clean({"role": "user", "content": turn["user_text"], "type": "text", **ids}))
        for call in turn.get("tool_calls") or []:
            args = call.get("args")
            call_json = {"type": "tool_call", "id": call.get("id") or "", "name": call.get("name") or "",
                         "args": args if args is not None else {}}
            out.append(_clean({
                "role": "assistant",
                "content": json.dumps(call_json, ensure_ascii=False),
                "type": "tool_call",
                "tool_calls": [{"id": call.get("id") or "", "type": "function",
                                "function": {"name": call.get("name") or "",
                                             "arguments": json.dumps(json_or_value(call_json["args"]),
                                                                     ensure_ascii=False)}}],
                "tool_call_id": call.get("id") or "",
                "response_time": call.get("t_call"),
                **ids,
            }))
            result = call.get("result")
            if result is not None:
                content = result.get("content")
                out.append(_clean({
                    "role": "assistant",
                    "content": json.dumps({"type": "tool_response", "name": call.get("name") or "",
                                           "content": content, "tool_call_id": result.get("tool_call_id") or call.get("id") or ""},
                                          ensure_ascii=False, default=str),
                    "type": "tool_response",
                    "tool_call_id": result.get("tool_call_id") or call.get("id") or "",
                    "response_time": call.get("t_result"),
                    **ids,
                }))
        wall = (turn.get("timings") or {}).get("client_wall_s")
        for part in turn.get("answer_parts") or []:
            if part.get("type") not in ANSWER_TYPES or not part.get("text"):
                continue
            message = {"role": "assistant", "content": part["text"], "type": "text", "response_time": wall, **ids}
            if part["type"] == "conversational_search" and part.get("tool_call_id"):
                message["conversational_search_metadata"] = {"tool_call_id": part["tool_call_id"]}
            out.append(_clean(message))
    return out


def _short(value: Any, limit: int = 160) -> str:
    """One printable line: hidden characters shown as <U+XXXX>, whitespace collapsed, cut at limit."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(visible(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_turn(turn: dict) -> str:
    """A short human-readable summary of one turn record (several lines, no trailing newline).

    Every value from the tenant passes through visible(): an escape sequence in an
    answer or a tool name cannot move the cursor or hide a line.
    """
    def field(key: str, limit: int = 80) -> str:
        return _short(str(turn.get(key)), limit)

    lines = [f"turn {field('turn', 20)} [{field('status', 40)}] capture={field('capture', 20)} "
             f"thread={field('thread_id')} run={field('run_id')}"]
    if turn.get("stateless"):
        lines[0] += " (stateless: the thread id is for correlation only, nothing is kept)"
    if turn.get("user_text") is not None:
        lines.append(f"  user: {_short(turn['user_text'])}")
    if not tools_known(turn):
        lines.append("  tools: unknown (no step history)")
    for call in turn.get("tool_calls") or []:
        tag = " [hand-off]" if call.get("handoff") else ""
        result = call.get("result")
        shown = _short(result.get("content"), 120) if result else "(no result)"
        lines.append(f"  tool: {_short(str(call.get('name')), 80)}({_short(call.get('args'), 120)}){tag} -> {shown}")
    for widget in turn.get("widgets") or []:
        options = _short(widget.get("options"), 100) if widget.get("options") else ""
        lines.append(f"  needs input: {_short(str(widget.get('type')), 40)} {_short(widget.get('text'), 100)} {options}".rstrip())
    if turn.get("input_request") == "async_flow":
        lines.append("  needs input: an async flow is still running; its messages reach the thread later")
    lines.append(f"  answer: {_short(turn.get('answer') or '', 400)}")
    if turn.get("warnings"):
        lines.append(f"  warnings: {_short(', '.join(map(str, turn['warnings'])), 400)}")
    return "\n".join(lines)
