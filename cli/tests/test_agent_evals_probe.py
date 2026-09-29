"""The wxo-agent-api skill's probe, ask.py and the batch_ask template against documented fixtures.

No test contacts a watsonx Orchestrate instance: every request goes to a fake transport that
fails on any call it does not expect. The gate tests prove that without the user's yes (the
plan hash for probe.py, --send for ask.py and batch_ask.py) no message reaches the agent.
"""

from __future__ import annotations

import base64
import copy
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "packs" / "ibm" / "agent-evals" / "skills" / "wxo-agent-api"
FIXTURES = Path(__file__).parent / "fixtures" / "agent-evals"
DOCUMENTED = FIXTURES / "documented"
PROBE_FX = FIXTURES / "probe"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = load(SKILL / "scripts" / "probe.py", "agent_evals_probe")
ask = load(SKILL / "scripts" / "ask.py", "agent_evals_ask")
batch = load(SKILL / "templates" / "batch_ask.py", "agent_evals_batch_ask")
wc = probe.wxo_client
tr = wc.load_trace()

CLOUD = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/tenant-0001"
OTHER = "https://api.eu-de.watson-orchestrate.cloud.ibm.com/instances/tenant-0002"
AGENT = "aaaaaaaa-0000-4000-8000-000000000001"
RUN = "22222222-2222-4222-8222-222222222222"
THREAD = "11111111-1111-4111-8111-111111111111"
MESSAGE = "What is my time off schedule for 2025?"


def fx(name: str, where: Path = DOCUMENTED):
    return json.loads((where / f"{name}.json").read_text(encoding="utf-8"))


def raw(name: str, where: Path = DOCUMENTED) -> bytes:
    return (where / name).read_bytes()


def chunked(data: bytes, size: int) -> list:
    return [data[i:i + size] for i in range(0, len(data), size)]


def b64url(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def make_jwt(exp: float) -> str:
    return f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url({'exp': int(exp), 'sub': 'planted-subject'})}.c2lnbmF0dXJlLXBsYW50ZWQ"


class FakeClock:
    def __init__(self, now: float = 1_790_000_000.0):
        self.now = now
        self.slept: list = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FakeTransport:
    """Answers (method, URL fragment) in order; the last answer of a repeat route is reused.

    Any request that matches no route fails the test, so an unexpected call is caught.
    """

    def __init__(self):
        self.routes: list = []
        self.calls: list = []

    def on(self, method: str, fragment: str, *answers, repeat: bool = False):
        self.routes.append({"method": method, "fragment": fragment, "answers": list(answers), "repeat": repeat})
        return self

    def __call__(self, method, url, headers, body, stream):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body, "stream": stream})
        for route in self.routes:
            if route["method"] != method or route["fragment"] not in url or not route["answers"]:
                continue
            if route["repeat"] and len(route["answers"]) == 1:
                answer = route["answers"][0]
            else:
                answer = route["answers"].pop(0)
            status, headers_out, payload = answer if isinstance(answer, tuple) else (200, {}, answer)
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            if stream:
                return status, headers_out, iter(chunked(data, 11))
            return status, headers_out, data
        raise AssertionError(f"unexpected call: {method} {url}")

    def count(self, method: str, fragment: str) -> int:
        return sum(1 for c in self.calls if c["method"] == method and fragment in c["url"])


def env(clock: FakeClock, instance: str = CLOUD) -> dict:
    return {"WO_INSTANCE": instance, "WO_TOKEN": make_jwt(clock.now + 36_000)}


def with_catalog(t: FakeTransport) -> FakeTransport:
    return t.on("GET", "/v1/orchestrate/agents", fx("agents"), repeat=True).on("GET", "/v1/orchestrate/tools",
                                                                               fx("tools"), repeat=True)


def no_cli() -> None:
    return None


def plan(tmp_path: Path, clock: FakeClock, *extra: str, agent: str = "hr_agent") -> tuple:
    out = tmp_path / "probe"
    t = with_catalog(FakeTransport())
    code = probe.main(["plan", "--agent", agent, "--message", MESSAGE, "--out", str(out), *extra],
                      transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    assert code == 0
    doc = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    return out, doc, t


def sends_nothing(t: FakeTransport) -> bool:
    return all(c["method"] == "GET" for c in t.calls) and not any(
        "/runs" in c["url"] or "chat/completions" in c["url"] for c in t.calls)


# --------------------------------------------------------------------------- plan
def test_plan_reads_only_and_saves_a_hash(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    out, doc, t = plan(tmp_path, clock)
    assert t.calls and sends_nothing(t)
    assert doc["plan_hash"] == probe.plan_hash(doc) and doc["agent_id"] == AGENT and doc["message"] == MESSAGE
    assert doc["routes"] == ["thread", "stream", "stream-alt"] and doc["auth_path"] == "wo_token"
    assert doc["sends"] == {"messages": 3, "new_threads": 3, "runs": 3, "v2_stateless_calls": 0, "reads_after": 0}
    text = capsys.readouterr().out
    assert "nothing has been sent" in text and doc["plan_hash"][:8] in text
    assert "delete_employee" in text and "collaborator  payroll_agent  tools: list_payslips" in text
    assert "hide_reasoning:  false" in text
    assert "catalog permission: read_write" in text and "may change external systems" in text

    _, five, t5 = plan(tmp_path, clock, "--v2", "--events")
    assert sends_nothing(t5) and five["sends"]["runs"] == 5 and five["sends"]["new_threads"] == 3
    assert five["plan_hash"] != doc["plan_hash"]

    bad = with_catalog(FakeTransport())
    code = probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--routes", "stream", "--events",
                       "--out", str(tmp_path / "x")], transport=bad, environ=env(clock), clock=clock, sleep=clock.sleep)
    assert code == 2 and bad.calls == []  # bad input, like a bad --routes value
    assert "keep thread in --routes" in capsys.readouterr().err
    code = probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--routes", "bogus",
                       "--out", str(tmp_path / "x")], transport=bad, environ=env(clock), clock=clock, sleep=clock.sleep)
    assert code == 2 and bad.calls == [] and "unknown route 'bogus'" in capsys.readouterr().err


def test_two_plans_of_the_same_inputs_have_different_hashes(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    out, first, _ = plan(tmp_path, clock)
    first_plan = (out / "plan.json").read_text(encoding="utf-8")
    clock.now += 3600
    _, second, _ = plan(tmp_path, clock)
    assert first["nonce"] != second["nonce"] and first["plan_hash"] != second["plan_hash"]
    assert probe.plan_hash(dict(second, nonce=first["nonce"], created_at=first["created_at"])) == first["plan_hash"]
    t = FakeTransport()
    assert probe.main(["run", "--confirm", first["plan_hash"][:8], "--out", str(out)], transport=t,
                      environ=env(clock), clock=clock, sleep=clock.sleep, adk=no_cli) == 2
    assert t.calls == [] and "does not match the saved plan" in capsys.readouterr().err
    assert json.loads(first_plan)["plan_hash"] == first["plan_hash"]


def test_run_refuses_without_the_right_hash(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock)
    t = FakeTransport()  # no routes: any request would fail the test

    def run(confirm: str, environ=None) -> int:
        return probe.main(["run", "--confirm", confirm, "--out", str(out)], transport=t,
                          environ=environ or env(clock), clock=clock, sleep=clock.sleep, adk=no_cli)

    for confirm in ("", "deadbeef", doc["plan_hash"][:7], "0" * 64):
        assert run(confirm) == 2
    with pytest.raises(SystemExit):
        probe.main(["run", "--out", str(out)], transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    edited = dict(doc, message="Delete every employee record")
    (out / "plan.json").write_text(json.dumps(edited), encoding="utf-8")
    assert run(doc["plan_hash"][:8]) == 2
    (out / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    assert run(doc["plan_hash"][:8], env(clock, OTHER)) == 2
    (out / "plan.json").write_text(json.dumps(dict(doc, run_started_at="2026-09-29T10:00:00Z")), encoding="utf-8")
    assert run(doc["plan_hash"]) == 2
    (out / "plan.json").unlink()
    assert run(doc["plan_hash"]) == 2
    assert t.calls == []
    err = capsys.readouterr().err
    assert err.count("Nothing was sent") == 8 and "changed after the plan step" in err and "already ran" in err


# --------------------------------------------------------------------------- run
def full_transport() -> FakeTransport:
    return with_catalog(FakeTransport()
            .on("POST", "/v1/orchestrate/runs?stream=true", raw("stream-runs.ndjson"))
            .on("POST", "/v1/orchestrate/runs/stream", raw("stream-runs.sse"))
            .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
            .on("GET", f"/v1/orchestrate/runs/{RUN}/events", fx("run-events", PROBE_FX))
            .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-running"))
            .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
            .on("GET", f"/v1/orchestrate/threads/{THREAD}/messages", fx("thread-messages"), repeat=True)
            .on("POST", f"/v2/orchestrate/{AGENT}/chat/completions", raw("stream-v2.sse"),
                fx("chat-completions-nonstream")))


def test_run_probes_every_route_and_recommends_thread(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--v2", "--events")
    capsys.readouterr()
    t = full_transport()
    environ = env(clock)
    token = environ["WO_TOKEN"]
    code = probe.main(["run", "--confirm", doc["plan_hash"][:8], "--out", str(out)], transport=t,
                      environ=environ, clock=clock, sleep=clock.sleep, adk=lambda: "2.17.0")
    assert code == 0
    result = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    assert (result["capture"], result["capture_kind"], result["verdict"]) == ("thread", "thread", "conclusive")
    assert result["adk_version"] == "2.17.0" and result["hide_reasoning"] is False
    routes = result["routes"]
    assert list(routes) == ["thread", "stream", "stream-alt", "v2", "v2_body", "events"]

    r1 = routes["thread"]
    assert (r1["tool_calls"], r1["tool_results"], r1["handoffs"], r1["ids_join"]) == (3, 3, 1, "yes")
    assert r1["statuses"] == ["running", "completed"] and r1["container_shape"] == "list"
    assert r1["run_result_keys"] == ["message", "output"] and r1["run_result_step_history"] is False
    assert r1["step_types"]["tool_call"] == ["args", "name", "tool_call_id", "type"]
    assert r1["step_types"]["thinking"] == ["content", "type"] and r1["call_keys"] == ["args", "id", "name"]
    assert [r["label"] for r in r1["thread_reads"]] == ["0s", "5s", "15s"] and r1["lag"]["stable_from"] == "0s"

    r2, r3 = routes["stream"], routes["stream-alt"]
    assert (r2["wire_format"], r3["wire_format"]) == ("ndjson", "sse") and r3["ended_by"] == "terminal"
    assert r2["events"]["order"][-2:] == ["run.completed", "done"] and r2["stop_event"] == "run.completed"
    assert r2["events_after_stop"] == 1 and r3["done_marker"] and r3["events_after_stop"] >= 1  # read past the stop
    assert r2["events"]["carry_step_details"] == ["run.step.delta"] and r2["events"]["without_thread_id"] == 1
    assert "run.step.intermediate" in r2["events"]["counts"]
    for stream in (r2, r3):
        compare = stream["thread_compare"]
        assert compare["compared"] and compare["names_match"] and compare["ids_match"] and compare["args_match"]
        assert stream["tool_calls"] == 3 and stream["ids_join"] == "yes"

    v2, body, events = routes["v2"], routes["v2_body"], routes["events"]
    assert v2["enabled"] and v2["step_delta_frames"] == 4 and v2["completed_step_details"] == 4 and v2["tool_calls"] == 2
    assert body["step_details_paths"] == [] and body["tools_known"] is False and body["tool_calls"] is None
    assert events["shape"] == "array" and events["tool_steps_replay"] and events["tool_calls"] == 1

    written = {p.name for p in (out / "raw").iterdir()}
    assert {"runs-create-r1.json", "thread-messages-r1-0s.json", "thread-messages-r1-15s.json", "stream-runs-r2.ndjson",
            "stream-runs-r3.sse", "stream-v2-r4.sse", "chat-completions-nonstream-r4.json",
            "run-events-r5.json"} <= written
    assert raw("stream-runs.sse").startswith((out / "raw" / "stream-runs-r3.sse").read_bytes())
    assert THREAD in (out / "threads.txt").read_text(encoding="utf-8")
    assert 5.0 in clock.slept and 10.0 in clock.slept  # thread reads at +5 s and +15 s

    report = (out / "probe.md").read_text(encoding="utf-8")
    assert "capture: **thread**" in report and "| R1 thread" in report and "| R5 GET runs/{id}/events" in report
    text = (out / "probe.json").read_text(encoding="utf-8")
    assert "nwaters" not in text and "15338303" not in text and "Payroll confirmed" not in text  # keys, never values

    stdout = capsys.readouterr().out
    everything = stdout + "".join(p.read_text(errors="replace") for p in out.rglob("*") if p.is_file())
    assert token not in everything and token.split(".")[1] not in everything
    assert all(c["headers"]["Authorization"] == "Bearer " + token for c in t.calls)

    again = FakeTransport()
    assert probe.main(["run", "--confirm", doc["plan_hash"][:8], "--out", str(out)], transport=again,
                      environ=env(clock), clock=clock, sleep=clock.sleep, adk=no_cli) == 2
    assert again.calls == []  # one yes covers one run


@pytest.mark.parametrize("agent, thread_doc, cause", [
    ("hr_agent", ("thread-messages-thinking-only", PROBE_FX), "no_tool_called"),
    ("payroll_agent", ("thread-messages-no-steps", DOCUMENTED), "hide_reasoning"),
    ("hr_agent", ("thread-messages-no-steps", DOCUMENTED), "empty_step_history"),
])
def test_run_without_visible_calls_is_inconclusive(tmp_path: Path, capsys, agent, thread_doc, cause) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--routes", "thread", agent=agent)
    t = with_catalog(FakeTransport()
         .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
         .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
         .on("GET", f"/threads/{THREAD}/messages", fx(*thread_doc), repeat=True))
    assert probe.main(["run", "--confirm", doc["plan_hash"], "--out", str(out)], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep, adk=no_cli) == 0
    result = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    assert (result["capture"], result["verdict"], result["recommendation"]["cause"]) == ("unknown", "inconclusive", cause)
    assert "inconclusive" in (out / "probe.md").read_text(encoding="utf-8")
    assert "read-only tool" in result["recommendation"]["next_step"]  # asks for another message, never "no tool metadata"
    if cause == "no_tool_called":
        assert result["routes"]["thread"]["tool_calls"] == 0 and "read-only tool" in capsys.readouterr().out
    else:
        assert result["routes"]["thread"]["tool_calls"] is None  # unknown, not zero
        assert "| unknown | unknown |" in (out / "probe.md").read_text(encoding="utf-8")


def test_v2_not_enabled_is_recorded_not_fatal(tmp_path: Path) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--routes", "thread", "--v2")
    t = with_catalog(FakeTransport()
         .on("POST", "/chat/completions", (404, {}, b'{"detail": "Not Found"}'))
         .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
         .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
         .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    assert probe.main(["run", "--confirm", doc["plan_hash"], "--out", str(out)], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep, adk=no_cli) == 0
    result = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    assert result["routes"]["v2"]["enabled"] is False and result["routes"]["v2"]["http_status"] == 404
    assert not result["routes"]["v2_body"]["works"] and t.count("POST", "/chat/completions") == 1
    assert result["capture"] == "thread"


# --------------------------------------------------------------------------- recommendation
def facts(works: bool = True, known: bool = True, calls: int = 0) -> dict:
    return {"works": works, "tools_known": known, "tool_calls": calls if known else None, "label": "x"}


@pytest.mark.parametrize("routes, hide, expected", [
    ({"thread": facts(calls=2), "stream": facts(calls=2), "v2": facts(calls=2)}, False, ("thread", "thread", None)),
    ({"thread": facts(calls=1)}, True, ("thread", "thread", None)),  # hide_reasoning, yet the steps showed
    ({"thread": facts(calls=0), "stream": facts(calls=1), "stream-alt": facts(calls=1)}, False, ("stream", "stream", None)),
    ({"thread": facts(known=False), "stream": facts(known=False), "stream-alt": facts(calls=1)}, True,
     ("stream-alt", "stream", None)),
    ({"thread": facts(works=False), "v2": facts(calls=1)}, None, ("v2", "v2", None)),
    ({"thread": facts(calls=0), "stream": facts(known=False)}, True, ("unknown", "unknown", "no_tool_called")),
    ({"thread": facts(known=False), "stream": facts(known=False), "v2": facts(known=False)}, True,
     ("unknown", "unknown", "hide_reasoning")),
    ({"thread": facts(known=False)}, False, ("unknown", "unknown", "empty_step_history")),
    ({"thread": facts(known=False)}, None, ("unknown", "unknown", "empty_step_history")),
    ({"thread": facts(works=False), "stream": facts(works=False)}, True, ("unknown", "unknown", "no_route_worked")),
    ({"thread": facts(known=False), "events": facts(calls=3), "v2_body": facts(calls=3)}, False,
     ("unknown", "unknown", "empty_step_history")),
])
def test_recommendation_is_deterministic(routes, hide, expected) -> None:
    rec = probe.recommend(routes, hide)
    assert (rec["capture"], rec["capture_kind"], rec["cause"]) == expected
    assert rec["capture"] in (*wc.ROUTES, "unknown")  # run_cases.py uses it as the client route
    assert rec["verdict"] == ("conclusive" if expected[0] != "unknown" else "inconclusive")
    assert rec == probe.recommend(copy.deepcopy(routes), hide)


def test_join_state_and_shapes() -> None:
    call = {"kind": "call", "id": "c1"}
    result = {"kind": "result", "tool_call_id": "c1"}
    assert probe.join_state([result, call]) == "yes"
    assert probe.join_state([call, {"kind": "result", "tool_call_id": "c2"}]) == "no"
    assert probe.join_state([call, {"kind": "call", "id": "c2"}, result]) == "partial"
    assert probe.join_state([{"kind": "call", "id": None}, result]) == "no"
    assert probe.join_state([{"kind": "thinking"}]) == "no calls"
    shapes = probe.step_shapes([{"type": "tool_calls", "tool_calls": [{"id": "x", "name": "y", "args": {"secret": 1}}]}])
    assert shapes == {"step_types": {"tool_calls": ["tool_calls", "type"]}, "call_keys": ["args", "id", "name"]}


# --------------------------------------------------------------------------- sanitize
LINE_END = re.compile(r"(\r\n|\r|\n)")


def line_kind(line: str) -> str:
    if not line.strip():
        return "blank"
    for name in ("data", "event", "id", "retry"):
        if line.startswith(name + ":"):
            return name
    return "comment" if line.startswith(":") else "other"


def all_keys(obj, path: str = "") -> set:
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(f"{path}.{k}")
            keys |= all_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for item in obj:
            keys |= all_keys(item, path + "[]")
    return keys


def test_sanitize_keeps_framing_and_keys_but_replaces_ids_and_values(tmp_path: Path) -> None:
    raw_dir = tmp_path / "probe" / "raw"
    raw_dir.mkdir(parents=True)
    jwt = make_jwt(1_790_000_000)
    host_line = b": served by api.us-south.watson-orchestrate.cloud.ibm.com for " + jwt.encode() + b"\n\n"
    sse = raw("stream-runs.sse")
    files = {
        "stream-runs-r2.ndjson": raw("stream-runs.ndjson"),
        "stream-runs-r3.sse": host_line + sse,
        "stream-runs-crlf.sse": sse.replace(b"\n", b"\r\n"),
        "stream-v2-r4.sse": raw("stream-v2.sse"),
        "thread-messages-r1-15s.json": (json.dumps(fx("thread-messages"), indent=2) + "\n").encode(),
        "run-status-r1.json": (json.dumps(fx("run-status-completed-with-step-history"), indent=2) + "\n").encode(),
    }
    for name, data in files.items():
        (raw_dir / name).write_bytes(data)
    (tmp_path / "probe" / "probe.json").write_text(json.dumps({"host": "api.us-south.watson-orchestrate.cloud.ibm.com"}))
    out = tmp_path / "captured" / "ibm-cloud-2026-09-29"
    clock = FakeClock()
    assert probe.main(["sanitize", "--in", str(raw_dir), "--out", str(out)], environ={}, clock=clock) == 0
    assert (out / "README.md").is_file()

    for name, original in files.items():
        new = (out / name).read_bytes()
        text = new.decode("utf-8")
        for secret in ("nwaters", "15338303", THREAD, RUN, "Payroll confirmed", "2025-04-11", "api.us-south", "eyJ"):
            assert secret not in text, (name, secret)
        if name.endswith(".json"):
            assert all_keys(json.loads(original)) == all_keys(json.loads(new)), name
            continue
        a, b = LINE_END.split(original.decode()), LINE_END.split(text)
        assert a[1::2] == b[1::2], name  # identical line ends
        assert [line_kind(x) for x in a[0::2]] == [line_kind(x) for x in b[0::2]], name
        assert [x for x in a[0::2] if x.startswith("event:")] == [x for x in b[0::2] if x.startswith("event:")]
        before, after = wc.parse_stream(original), wc.parse_stream(new)
        assert before["line_classes"] == after["line_classes"] and before["framing"] == after["framing"], name
        assert before["done_marker"] == after["done_marker"] and after["malformed"] == 0
        assert [e["event"] for e in before["events"]] == [e["event"] for e in after["events"]], name

    assert "tenant.example.com" in (out / "stream-runs-r3.sse").read_text() and "[REDACTED-JWT]" in (out / "stream-runs-r3.sse").read_text()
    assert b"data: [DONE]\r\n" in (out / "stream-runs-crlf.sse").read_bytes()

    stream_turn = tr.turn_from_stream(wc.parse_stream((out / "stream-runs-r3.sse").read_bytes())["events"])
    thread_turn = tr.turn_from_thread(json.loads((out / "thread-messages-r1-15s.json").read_text()))
    original_turn = tr.turn_from_stream(wc.parse_stream(sse)["events"])
    assert [c["name"] for c in stream_turn["tool_calls"]] == [c["name"] for c in original_turn["tool_calls"]]
    assert stream_turn["warnings"] == original_turn["warnings"] and all(c["result"] for c in stream_turn["tool_calls"])
    assert [c["id"] for c in stream_turn["tool_calls"]] == [c["id"] for c in thread_turn["tool_calls"]]  # stable fakes
    assert stream_turn["thread_id"] == thread_turn["thread_id"] != THREAD
    first = thread_turn["tool_calls"][0]
    assert first["name"] == "fetch_assignment_id" and set(first["args"]) == {"username"}
    assert re.fullmatch(r"<text-\d+>", first["args"]["username"])
    assert re.fullmatch(r"<number-\d+>", first["result"]["content_json"]["assignment_id"])  # JSON inside a string
    assert thread_turn["tool_calls"][2]["handoff"] and thread_turn["answer"].startswith("<text-")

    assert probe.main(["sanitize", "--in", str(raw_dir), "--out", str(raw_dir / "inside")], environ={}, clock=clock) == 2


# --------------------------------------------------------------------------- ask.py
def test_ask_dry_run_sends_nothing(capsys) -> None:
    clock = FakeClock()
    t = with_catalog(FakeTransport())
    code = ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--message", "And in 2026?"], transport=t,
                    environ=env(clock), clock=clock, sleep=clock.sleep)
    assert code == 0 and t.calls and sends_nothing(t)
    out = capsys.readouterr().out
    assert "DRY RUN: nothing was sent" in out and "2 run(s) in one new thread" in out
    assert "delete_employee" in out and "collaborator   payroll_agent  tools: list_payslips" in out
    assert json.dumps(MESSAGE) in out


def test_ask_send_keeps_one_thread_across_turns(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    t = with_catalog(FakeTransport()
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"), repeat=True)
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
                     .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    target = tmp_path / "turns.json"
    environ = env(clock)
    code = ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--message", "And in 2026?", "--send",
                     "--out", str(target)], transport=t, environ=environ, clock=clock, sleep=clock.sleep)
    assert code == 0
    bodies = [json.loads(c["body"]) for c in t.calls if c["method"] == "POST"]
    assert len(bodies) == 2 and "thread_id" not in bodies[0] and bodies[1]["thread_id"] == THREAD
    assert all(b["agent_id"] == AGENT for b in bodies)
    records = json.loads(target.read_text(encoding="utf-8"))
    assert [r["turn"] for r in records] == [0, 1] and all(len(r["tool_calls"]) == 3 for r in records)
    out = capsys.readouterr().out
    assert "[hand-off]" in out and f"threads now on the tenant (not deleted): {THREAD}" in out
    assert environ["WO_TOKEN"] not in out + target.read_text(encoding="utf-8")

    code = ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--send", "--json"], transport=t,
                    environ=env(clock), clock=clock, sleep=clock.sleep)
    assert code == 0 and json.loads(capsys.readouterr().out)[0]["status"] == "completed"


# --------------------------------------------------------------------------- batch_ask template
def test_batch_ask_dry_run_then_send(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    questions = tmp_path / "questions.csv"
    questions.write_text('id,question\nq1,What is my time off in 2025?\nq2,"=HYPERLINK(""x"",""y"")"\n,\n',
                         encoding="utf-8")
    answers = tmp_path / "agent-evals" / "runs" / "answers.csv"
    args = ["--agent", "hr_agent", "--in", str(questions), "--out", str(answers)]

    dry = with_catalog(FakeTransport())
    assert batch.main(args, transport=dry, environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    assert sends_nothing(dry) and not answers.exists()
    dry_out = capsys.readouterr().out
    assert "DRY RUN: nothing was sent" in dry_out and "collaborator payroll_agent  tools: list_payslips" in dry_out

    t = with_catalog(FakeTransport()
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"), repeat=True)
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
                     .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), fx("thread-messages"),
                         fx("thread-messages-no-steps"), repeat=True))  # without steps, reads go on to the cap
    assert batch.main(args + ["--send"], transport=t, environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    rows = list(csv.DictReader(answers.open(encoding="utf-8")))
    assert [r["id"] for r in rows] == ["q1", "q2"] and all("thread_id" not in json.loads(c["body"])
                                                          for c in t.calls if c["method"] == "POST")
    assert rows[0]["tools_called"] == "fetch_assignment_id;get_holiday_calendar"
    assert rows[0]["handoffs"] == "chat_with_collaborator_payroll_agent" and rows[0]["tools_known"] == "yes"
    assert rows[1]["question"].startswith("'=") and rows[1]["tools_called"] == "unknown" and rows[1]["tools_known"] == "no"
    assert rows[0]["status"] == "completed" and rows[0]["thread_id"] == THREAD


def test_ask_keeps_what_it_collected_when_a_later_turn_fails(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    t = with_catalog(FakeTransport()
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"), (500, {}, b"upstream error"))
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
                     .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    target = tmp_path / "agent-evals" / "runs" / "turns.json"
    code = ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--message", "And in 2026?", "--send", "--json",
                     "--out", str(target)], transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    out, err = capsys.readouterr()
    assert code == 1 and "HTTP 500" in err
    assert [r["turn"] for r in json.loads(out)] == [0] and len(json.loads(target.read_text())) == 1
    assert f"threads now on the tenant (not deleted): {THREAD}" in err


def test_ask_stops_after_an_async_flow_and_shows_escapes(capsys) -> None:
    clock = FakeClock()
    thread = fx("thread-messages")
    thread[2]["content"][0]["text"] = "Started.\x1b[2K\x1b[1A"
    t = with_catalog(FakeTransport()
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"), repeat=True)
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", {**fx("run-status-completed"), "status": "async_wait"},
                         repeat=True)
                     .on("GET", f"/threads/{THREAD}/messages", thread, repeat=True))
    code = ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--message", "And in 2026?", "--send"],
                    transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    out = capsys.readouterr().out
    assert code == 0 and t.count("POST", "/runs") == 1 and "async flow that is still running" in out
    assert "\x1b" not in out and "<U+001B>[2K" in out


@pytest.mark.parametrize("script", ["ask", "probe", "batch"])
def test_timeouts_must_be_above_zero(script: str, tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    t = FakeTransport()
    argv = {"ask": ["--agent", "hr_agent", "--message", MESSAGE, "--send", "--timeout", "0"],
            "probe": ["run", "--confirm", "deadbeef", "--out", str(tmp_path), "--timeout", "-5"],
            "batch": ["--agent", "hr_agent", "--in", str(tmp_path / "q.csv"), "--out", str(tmp_path / "a.csv"),
                      "--send", "--timeout", "0"]}[script]
    main = {"ask": ask.main, "probe": probe.main, "batch": batch.main}[script]
    with pytest.raises(SystemExit) as info:
        main(argv, transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    assert info.value.code == 2 and t.calls == [] and "above 0" in capsys.readouterr().err


def test_ask_refuses_an_output_inside_the_skills_folder(capsys) -> None:
    clock = FakeClock()
    t = FakeTransport()
    code = ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--send", "--out", str(SKILL / "turns.json")],
                    transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    assert code == 2 and t.calls == [] and "inside the skills folder" in capsys.readouterr().out
    assert not (SKILL / "turns.json").exists()


def test_batch_error_rows_keep_the_thread_that_persists(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    questions = tmp_path / "questions.csv"
    questions.write_text("id,question\nq1,What is my time off in 2025?\n", encoding="utf-8")
    answers = tmp_path / "agent-evals" / "runs" / "answers.csv"
    t = with_catalog(FakeTransport()
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", (503, {}, b"unavailable"), repeat=True))
    code = batch.main(["--agent", "hr_agent", "--in", str(questions), "--out", str(answers), "--send"],
                      transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    rows = list(csv.DictReader(answers.open(encoding="utf-8")))
    assert code == 1 and rows[0]["status"] == "error" and (rows[0]["thread_id"], rows[0]["run_id"]) == (THREAD, RUN)


# --------------------------------------------------------------------------- review round 3
def test_the_plan_shows_hidden_characters_instead_of_obeying_them(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    agents, tools = fx("agents"), fx("tools")
    for tool in tools:
        tool["description"] = "reads data\x1b[2K\x1b[1A\x1b[2K‮HIDDEN"
    agents[1]["name"] = "payroll_agent\x1b[31m"
    t = FakeTransport().on("GET", "/v1/orchestrate/agents", agents, repeat=True).on("GET", "/v1/orchestrate/tools",
                                                                                    tools, repeat=True)
    out = tmp_path / "probe"
    assert probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--out", str(out)], transport=t,
                      environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    text = capsys.readouterr().out
    assert "\x1b" not in text and "‮" not in text
    assert "reads data<U+001B>[2K" in text and "<U+202E>HIDDEN" in text and "payroll_agent<U+001B>[31m" in text


def test_a_default_probe_run_never_starts_a_process(tmp_path: Path, monkeypatch) -> None:
    import os
    import subprocess

    def refuse(*args, **kwargs):
        raise AssertionError(f"the probe started a process: {args!r}")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)
    monkeypatch.setattr(os, "system", refuse)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--routes", "thread")
    t = with_catalog(FakeTransport()
         .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
         .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
         .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    assert probe.main(["run", "--confirm", doc["plan_hash"], "--out", str(out)], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep) == 0
    result = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    assert "adk_version" in result and "orchestrate_version" not in result
    assert not (tmp_path / "home" / ".config").exists()  # the ADK's config file is never created
    source = (SKILL / "scripts" / "probe.py").read_text(encoding="utf-8")
    assert "subprocess" not in source and "shutil.which" not in source


@pytest.mark.parametrize("extra, body, enabled", [
    ((), b'{"detail": "Not Found"}', False),
    ((), b'{"error": {"message": "agent not found", "code": 404}}', None),
    (("--environment-id", "env-live-0001", "--v2-live"), b'{"detail": "Not Found"}', None),
])
def test_a_v2_404_is_not_enabled_only_when_nothing_else_explains_it(tmp_path: Path, capsys, extra, body,
                                                                     enabled) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--routes", "thread", "--v2", *extra)
    t = with_catalog(FakeTransport()
         .on("POST", "/chat/completions", (404, {}, body))
         .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
         .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
         .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    assert probe.main(["run", "--confirm", doc["plan_hash"], "--out", str(out)], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep, adk=no_cli) == 0
    assert json.loads((out / "probe.json").read_text(encoding="utf-8"))["routes"]["v2"]["enabled"] is enabled
    text = capsys.readouterr().out
    assert ("not enabled on this tenant" in text) is (enabled is False)
    v2_call = next(c for c in t.calls if "chat/completions" in c["url"])
    assert ("X-IBM-ENVIRONMENT-ID" in v2_call["headers"]) is bool(extra)
    runs_call = next(c for c in t.calls if c["method"] == "POST" and c["url"].endswith("/v1/orchestrate/runs"))
    assert json.loads(runs_call["body"]).get("environment_id") == (extra[1] if extra else None)


def test_v2_with_an_environment_id_needs_an_explicit_live(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    t = with_catalog(FakeTransport())
    code = probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--v2", "--environment-id",
                       "env-draft-0001", "--out", str(tmp_path / "p")], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep)
    err = capsys.readouterr().err
    assert code == 2 and t.calls == [] and "X-IBM-ENVIRONMENT-ID" in err and "live" in err and "--v2-live" in err
    _, doc, _ = plan(tmp_path, clock, "--v2", "--environment-id", "env-live-0001", "--v2-live")
    text = capsys.readouterr().out
    assert doc["v2_live"] is True and "sent as X-IBM-ENVIRONMENT-ID" in text and "live (published)" in text
    _, draft, _ = plan(tmp_path, clock, "--v2")
    assert draft["v2_live"] is False and "no X-IBM-ENVIRONMENT-ID" in capsys.readouterr().out

    for argv in (["--route", "v2", "--environment-id", "env-draft-0001"], ["--environment-id", "env-1", "--v2-live"]):
        asked = FakeTransport()
        assert ask.main(["--agent", "hr_agent", "--message", MESSAGE, *argv], transport=asked, environ=env(clock),
                        clock=clock, sleep=clock.sleep) == 2
        assert asked.calls == []
    capsys.readouterr()
    live = with_catalog(FakeTransport())
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--route", "v2", "--environment-id", "env-live-0001",
                     "--v2-live"], transport=live, environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    assert "live (published)" in capsys.readouterr().out and sends_nothing(live)
    batch_t = FakeTransport()
    assert batch.main(["--agent", "hr_agent", "--in", str(tmp_path / "q.csv"), "--out", str(tmp_path / "a.csv"),
                       "--route", "v2", "--environment-id", "env-draft-0001"], transport=batch_t, environ=env(clock),
                      clock=clock, sleep=clock.sleep) == 2
    assert batch_t.calls == []


# --------------------------------------------------------------------------- review round 4
def test_the_probe_never_writes_inside_the_skills_folder(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    inside = SKILL / "agent-evals" / "probe"
    t = with_catalog(FakeTransport())
    assert probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--out", str(inside)], transport=t,
                      environ=env(clock), clock=clock, sleep=clock.sleep) == 2
    assert probe.main(["run", "--confirm", "deadbeef", "--out", str(inside)], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep, adk=no_cli) == 2
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    assert probe.main(["sanitize", "--in", str(raw_dir), "--out", str(inside)], environ={}, clock=clock) == 2
    assert t.calls == [] and not (SKILL / "agent-evals").exists()
    assert capsys.readouterr().err.count("inside the skills folder") == 3


@pytest.mark.parametrize("change", ["tool", "nested collaborator"])
def test_run_refuses_when_the_agent_changed_after_the_plan(tmp_path: Path, capsys, change: str) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--routes", "thread")
    agents, tools = fx("agents"), fx("tools")
    tools.append({"id": "bbbbbbbb-0000-4000-8000-0000000000ff", "name": "wire_funds_out"})
    if change == "tool":
        agents[0]["tools"].append("bbbbbbbb-0000-4000-8000-0000000000ff")
    else:
        agents.append({"id": "aaaaaaaa-0000-4000-8000-000000000003", "name": "offboarding_agent",
                       "tools": ["bbbbbbbb-0000-4000-8000-0000000000ff"], "collaborators": []})
        agents[1]["collaborators"] = ["aaaaaaaa-0000-4000-8000-000000000003"]
    t = (FakeTransport()
         .on("GET", "/v1/orchestrate/agents", agents, repeat=True)
         .on("GET", "/v1/orchestrate/tools", tools, repeat=True)
         .on("POST", "/v1/orchestrate/runs", fx("runs-create")))
    assert probe.main(["run", "--confirm", doc["plan_hash"], "--out", str(out)], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep, adk=no_cli) == 2
    err = capsys.readouterr().err
    assert t.count("POST", "/runs") == 0 and "the target changed" in err and "Nothing was sent" in err
    assert ("wire_funds_out" if change == "tool" else "offboarding_agent") in err
    assert "run_started_at" not in json.loads((out / "plan.json").read_text(encoding="utf-8"))  # the yes is unused


def test_the_stream_thread_comparison_counts_repeated_calls() -> None:
    thread_turn = tr.turn_from_thread(fx("thread-messages"))
    stream_turn = copy.deepcopy(thread_turn)
    stream_turn["tool_calls"].append(copy.deepcopy(stream_turn["tool_calls"][0]))  # the stream shows it twice
    compare = probe.diff_calls(stream_turn, thread_turn)
    assert (compare["stream_calls"], compare["thread_calls"]) == (4, 3) and not probe.calls_agree(compare)
    assert [c["name"] for c in compare["only_in_stream"]] == ["fetch_assignment_id"] and not compare["only_in_thread"]
    facts = {"route": "stream", "works": True, "events": {"total": 5}, "thread_compare": compare}
    assert "thread disagrees" in probe.route_notes(facts)
    rec = probe.recommend({"thread": {"works": True, "tools_known": True, "tool_calls": 3, "label": "R1"},
                           "stream": facts}, False)
    assert rec["capture"] == "thread" and any("disagree" in note for note in rec["notes"])
    same = probe.diff_calls(thread_turn, copy.deepcopy(thread_turn))
    assert probe.calls_agree(same) and "thread agrees" in probe.route_notes(dict(facts, thread_compare=same))


def test_ask_refuses_a_folder_as_out_and_survives_a_failed_write(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    t = FakeTransport()
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--send", "--out", str(tmp_path)], transport=t,
                    environ=env(clock), clock=clock, sleep=clock.sleep) == 2
    assert t.calls == [] and "is a folder" in capsys.readouterr().out
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a folder should be", encoding="utf-8")
    t = with_catalog(FakeTransport()
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"), repeat=True)
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
                     .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    code = ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--send", "--out", str(blocker / "turns.json")],
                    transport=t, environ=env(clock), clock=clock, sleep=clock.sleep)
    out = capsys.readouterr().out
    assert code == 1 and "error: cannot write" in out and f"threads now on the tenant (not deleted): {THREAD}" in out


def test_dry_runs_keep_each_tenant_name_on_its_line(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    agents, tools = fx("agents"), fx("tools")
    tools[3]["name"] = "delete_employee\rlist_holidays  "  # a CR would let the name overwrite its own line
    tools[2]["name"] = "get_holiday_cal\x9b8m_hidden\x9b0m"
    t = FakeTransport().on("GET", "/v1/orchestrate/agents", agents, repeat=True).on("GET", "/v1/orchestrate/tools",
                                                                                    tools, repeat=True)
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE], transport=t, environ=env(clock), clock=clock,
                    sleep=clock.sleep) == 0
    questions = tmp_path / "q.csv"
    questions.write_text("id,question\nq1,hi\n", encoding="utf-8")
    batch_args = ["--agent", "hr_agent", "--in", str(questions), "--out", str(tmp_path / "a.csv")]
    assert batch.main(batch_args, transport=t, environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    out = tmp_path / "probe"
    assert probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--out", str(out)], transport=t,
                      environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    text = capsys.readouterr().out
    assert "\r" not in text and "\x9b" not in text and text.count("delete_employee list_holidays") == 3
    assert text.count("get_holiday_cal<U+009B>8m_hidden<U+009B>0m") == 3


def test_batch_on_v2_says_it_keeps_nothing_and_needs_a_real_limit(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    questions = tmp_path / "q.csv"
    questions.write_text("id,question\nq1,hi\nq2,again\n", encoding="utf-8")
    args = ["--agent", "hr_agent", "--in", str(questions), "--out", str(tmp_path / "a.csv"), "--route", "v2"]
    assert batch.main(args, transport=with_catalog(FakeTransport()), environ=env(clock), clock=clock,
                      sleep=clock.sleep) == 0
    out = capsys.readouterr().out
    assert "2 stateless v2 chat/completions call(s)" in out and "new thread" not in out
    for bad in ("0", "-1", "two"):
        with pytest.raises(SystemExit) as info:
            batch.main(args + ["--limit", bad], transport=FakeTransport(), environ=env(clock), clock=clock,
                       sleep=clock.sleep)
        assert info.value.code == 2


# --------------------------------------------------------------------------- review round 5
def thread_route() -> FakeTransport:
    return with_catalog(FakeTransport()
                        .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
                        .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
                        .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))


def test_a_second_probe_run_moves_the_first_runs_captures_aside(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    out, first, _ = plan(tmp_path, clock, "--v2", "--events")
    assert probe.main(["run", "--confirm", first["plan_hash"][:8], "--out", str(out)], transport=full_transport(),
                      environ=env(clock), clock=clock, sleep=clock.sleep, adk=no_cli) == 0
    clock.now += 3600
    _, second, _ = plan(tmp_path, clock, "--routes", "thread")
    capsys.readouterr()
    assert probe.main(["run", "--confirm", second["plan_hash"][:8], "--out", str(out)], transport=thread_route(),
                      environ=env(clock), clock=clock, sleep=clock.sleep, adk=no_cli) == 0
    raw_dir = out / "raw"
    latest = {p.name for p in raw_dir.iterdir() if p.is_file()}
    assert latest == {"runs-create-r1.json", "run-status-r1.json", "thread-messages-r1-0s.json",
                      "thread-messages-r1-5s.json", "thread-messages-r1-15s.json"}
    earlier = [p for p in raw_dir.iterdir() if p.is_dir()]
    assert len(earlier) == 1 and earlier[0].name.startswith("previous-20") and (earlier[0] / "stream-v2-r4.sse").is_file()
    assert f"moved to {earlier[0]}/" in capsys.readouterr().out
    fixtures = tmp_path / "fixtures"
    assert probe.main(["sanitize", "--in", str(raw_dir), "--out", str(fixtures)], environ={}, clock=clock) == 0
    assert {p.name for p in fixtures.rglob("*") if p.is_file()} == latest | {"README.md"}  # one run only


def test_every_route_that_fails_gets_its_console_line(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--routes", "thread", "--v2", "--events")
    capsys.readouterr()
    t = with_catalog(FakeTransport()
                     .on("POST", "/chat/completions", (404, {}, b'{"detail": "Not Found"}'))
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
                     .on("GET", f"/v1/orchestrate/runs/{RUN}/events", (404, {}, b'{"detail": "Not Found"}'))
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
                     .on("GET", f"/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    assert probe.main(["run", "--confirm", doc["plan_hash"], "--out", str(out)], transport=t, environ=env(clock),
                      clock=clock, sleep=clock.sleep, adk=no_cli) == 0
    printed = capsys.readouterr().out
    assert "R4 v2: failed (v2 is not enabled on this tenant): " in printed
    assert "R4 v2_body: failed: skipped: the stream:true call answered HTTP 404" in printed
    assert re.search(r"R5 events: failed: .*HTTP 404", printed)


def test_tool_descriptions_are_redacted_before_they_are_cut(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    environ = {"WO_INSTANCE": CLOUD, "WO_TOKEN": make_jwt(4_102_444_800)}  # wxo_client.main uses the real clock
    token = environ["WO_TOKEN"]
    tools = fx("tools")
    tools[0]["description"] = "reads data " * 12 + f"token {token}"  # the 160-character cut falls inside the token
    tools[1]["description"] = "reads data " * 8 + token  # and the CLI's 100-character one
    t = FakeTransport().on("GET", "/v1/orchestrate/agents", fx("agents"), repeat=True).on(
        "GET", "/v1/orchestrate/tools", tools, repeat=True)
    out = tmp_path / "probe"
    assert probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--out", str(out)], transport=t,
                      environ=environ, clock=clock, sleep=clock.sleep) == 0
    assert wc.main(["tools"], transport=t, environ=environ) == 0
    everything = capsys.readouterr().out + (out / "plan.json").read_text(encoding="utf-8")
    assert token[:12] not in everything and everything.count("[REDACTED") >= 3


def hidden_catalog():
    """GET agents leaves the hidden payroll_agent out unless the URL asks for hidden agents, as the server does."""
    agents = fx("agents")
    agents[1]["hidden"] = True

    def transport(method, url, headers, body, stream):
        if method == "GET" and "/v1/orchestrate/agents" in url:
            return 200, {}, json.dumps(agents if "include_hidden=true" in url else agents[:1]).encode()
        if method == "GET" and "/v1/orchestrate/tools" in url:
            return 200, {}, json.dumps(fx("tools")).encode()
        raise AssertionError(f"unexpected call: {method} {url}")
    return transport


def test_a_hidden_collaborator_and_its_tools_are_in_every_plan(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    plan_out = tmp_path / "probe"
    assert probe.main(["plan", "--agent", "hr_agent", "--message", MESSAGE, "--out", str(plan_out)],
                      transport=hidden_catalog(), environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    assert "collaborator  payroll_agent  tools: list_payslips" in capsys.readouterr().out
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE], transport=hidden_catalog(), environ=env(clock),
                    clock=clock, sleep=clock.sleep) == 0
    assert "collaborator   payroll_agent  tools: list_payslips" in capsys.readouterr().out
    assert ask.main(["--agent", "payroll_agent", "--message", MESSAGE], transport=hidden_catalog(),
                    environ=env(clock), clock=clock, sleep=clock.sleep) == 0  # a hidden target resolves too
    assert "payroll_agent  (id aaaaaaaa-0000-4000-8000-000000000002" in capsys.readouterr().out


def test_a_hide_reasoning_value_cannot_forge_a_plan_line(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    agents = fx("agents")
    agents[0]["hide_reasoning"] = "true\nwrites:          nothing: this agent is read-only"
    t = FakeTransport().on("GET", "/v1/orchestrate/agents", agents, repeat=True).on("GET", "/v1/orchestrate/tools",
                                                                                    fx("tools"), repeat=True)
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE], transport=t, environ=env(clock), clock=clock,
                    sleep=clock.sleep) == 0
    questions = tmp_path / "q.csv"
    questions.write_text("id,question\nq1,hi\n", encoding="utf-8")
    assert batch.main(["--agent", "hr_agent", "--in", str(questions), "--out", str(tmp_path / "a.csv")], transport=t,
                      environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    text = capsys.readouterr().out
    assert not any(line.lstrip().startswith("writes:          nothing") for line in text.splitlines())
    assert text.count("'true\\nwrites:") == 2


def test_ask_stops_after_a_turn_that_did_not_complete_or_named_no_thread(capsys) -> None:
    clock = FakeClock()
    steps_only = b"\n\n".join(raw("stream-v2.sse").split(b"\n\n")[:4]) + b"\n\n"  # the stream ends without its end
    t = with_catalog(FakeTransport().on("POST", "/chat/completions", steps_only, repeat=True))
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--message", "And in 2026?", "--route", "v2",
                     "--send"], transport=t, environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    assert t.count("POST", "/chat/completions") == 1 and "turn 0 ended with status incomplete" in capsys.readouterr().out

    no_ids = (raw("stream-runs.ndjson").replace(f'"thread_id":"{THREAD}",'.encode(), b"")
              .replace(f'"run_id":"{RUN}",'.encode(), b"").replace(f'"run_id":"{RUN}"'.encode(), b""))
    t = with_catalog(FakeTransport().on("POST", "/v1/orchestrate/runs?stream=true", no_ids, repeat=True))
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--message", "And in 2026?", "--route", "stream",
                     "--send"], transport=t, environ=env(clock), clock=clock, sleep=clock.sleep) == 0
    assert t.count("POST", "/runs") == 1 and "carried no thread id" in capsys.readouterr().out


def test_a_password_with_a_quote_never_reaches_asks_output(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    password = 'Sup3r"Secret!pwé'
    thread = fx("thread-messages")
    thread[2]["content"][0]["text"] = f"The login used {password}."
    t = (FakeTransport()
         .on("POST", "/api/v1/auth/token?tenant_id=t-1", {"access_token": "tenant-token-local"}, repeat=True)
         .on("POST", "/api/v1/auth/token", {"access_token": "global-token-local"}, repeat=True)
         .on("GET", "/api/v1/tenants", [{"id": "t-1", "name": "wxo-dev"}], repeat=True)
         .on("GET", "/v1/orchestrate/agents", fx("agents"), repeat=True)
         .on("GET", "/v1/tools", fx("tools"), repeat=True)
         .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
         .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
         .on("GET", f"/v1/threads/{THREAD}/messages", thread, repeat=True))
    target = tmp_path / "turns.json"
    environ = {"WO_INSTANCE": "http://localhost:4321", "WO_USERNAME": "dev", "WO_PASSWORD": password}
    assert ask.main(["--agent", "hr_agent", "--message", MESSAGE, "--send", "--json", "--out", str(target)],
                    transport=t, environ=environ, clock=clock, sleep=clock.sleep) == 0
    everything = capsys.readouterr().out + target.read_text(encoding="utf-8")
    assert "Secret!pw" not in everything and "[REDACTED]" in everything


def test_the_skeleton_lists_the_thread_a_failed_turn_left(tmp_path: Path, monkeypatch, capsys) -> None:
    guide = (SKILL / "references" / "writing-scripts.md").read_text(encoding="utf-8")
    code = guide.split("## Skeleton", 1)[1].split("```python\n", 1)[1].split("```", 1)[0]
    script = tmp_path / "agent-evals" / "scripts" / "task.py"
    script.parent.mkdir(parents=True)
    script.write_text(code, encoding="utf-8")
    clock = FakeClock()
    v2_thread = "66666666-6666-4666-8666-666666666666"
    t = with_catalog(FakeTransport().on("POST", "/chat/completions", raw("stream-v2.sse"),
                                        (500, {}, b"upstream error")))
    task = load(script, "agent_evals_skeleton_task")
    monkeypatch.setattr(task.wxo_client, "urllib_transport", lambda *args, **kwargs: t)
    monkeypatch.setenv("WO_INSTANCE", CLOUD)
    monkeypatch.setenv("WO_TOKEN", make_jwt(4_102_444_800))  # the skeleton's client uses the real clock
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["task.py", "--agent", "hr_agent", "--message", MESSAGE,
                                      "--message", "And in 2026?", "--route", "v2", "--send"])
    assert task.main() == 1
    out, err = capsys.readouterr()
    assert "HTTP 500" in err and f"thread(s) on the tenant: {v2_thread}" in err
    assert t.calls[-1]["headers"]["X-IBM-THREAD-ID"] == v2_thread and "hide_reasoning false" in out


# --------------------------------------------------------------------------- review round 6
def test_the_recommendation_names_the_probe_file_and_a_lag_longer_than_the_settle_reads() -> None:
    lag = {"stable_from": "15s", "stable_from_s": 15.0, "changed_after_completion": True, "steps_at_completion": 0,
           "steps_final": 7}
    rec = probe.recommend({"thread": dict(facts(calls=7), lag=lag)}, False, "my probe/probe.json")
    assert "--probe 'my probe/probe.json'" in rec["next_step"] and "capture thread" in rec["next_step"]
    note = next(n for n in rec["notes"] if "stable only from 15s" in n)
    assert "18 s" in note and "settle_reads=10" in note and not any("keep the settle reads" in n for n in rec["notes"])
    short = dict(lag, stable_from="5s", stable_from_s=5.0)
    rec = probe.recommend({"thread": dict(facts(calls=7), lag=short)}, False)
    assert "within the default settle window (8 s)" in rec["notes"][0]
    assert rec["next_step"].startswith("run_cases.py uses capture thread")


def test_probe_md_keeps_an_error_body_as_text_and_every_probe_thread_is_counted(tmp_path: Path, capsys) -> None:
    clock = FakeClock()
    out, doc, _ = plan(tmp_path, clock, "--routes", "thread,stream")
    (out / "threads.txt").write_text("old-1\tprobe thread x\nold-2\tprobe stream x\n", encoding="utf-8")
    capsys.readouterr()
    body = b"![status](https://attacker.example/pixel.png?r=1) <img src=https://attacker.example/i.png>"
    t = with_catalog(FakeTransport()
                     .on("POST", "/v1/orchestrate/runs?stream=true", (500, {}, body))
                     .on("POST", "/v1/orchestrate/runs", fx("runs-create"))
                     .on("GET", f"/v1/orchestrate/runs/{RUN}", fx("run-status-completed"), repeat=True)
                     .on("GET", f"/v1/orchestrate/threads/{THREAD}/messages", fx("thread-messages"), repeat=True))
    assert probe.main(["run", "--confirm", doc["plan_hash"][:8], "--out", str(out)], transport=t,
                      environ=env(clock), clock=clock, sleep=clock.sleep, adk=no_cli) == 0
    md = (out / "probe.md").read_text(encoding="utf-8")
    assert "attacker.example" in md and "![status](" not in md and "<img" not in md
    stdout = capsys.readouterr().out
    assert "This run created 1 thread(s)" in stdout and "(3 in all)" in stdout
    assert f"--probe {out / 'probe.json'}" in stdout  # a probe outside the default folder must be named


def test_sanitize_keeps_the_structure_of_type_shaped_content(tmp_path: Path) -> None:
    doc = [{"role": "user", "content": [{"type": "text", "text": "Where is my order 12345?"}]},
           {"role": "assistant", "content": [{"type": "text", "text": "Your order #12345 is being processed."}],
            "step_history": [{"role": "assistant", "step_details": [
                {"type": "tool_calls", "tool_calls": [{"id": "c1", "name": "get_order", "args": {"order": "12345"}}]},
                {"type": "tool_response", "name": "get_order", "tool_call_id": "c1",
                 "content": "{\"status\": \"processing\"}"}]}]}]
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "thread-messages-r1-15s.json").write_text(json.dumps(doc), encoding="utf-8")
    out = tmp_path / "fixtures"
    assert probe.main(["sanitize", "--in", str(raw_dir), "--out", str(out)], environ={}, clock=FakeClock()) == 0
    clean = json.loads((out / "thread-messages-r1-15s.json").read_text(encoding="utf-8"))
    before, after = tr.turn_from_thread(doc), tr.turn_from_thread(clean)
    assert after["status"] == before["status"] == "completed" and "empty_answer" not in after["warnings"]
    assert clean[1]["content"][0]["type"] == "text" and re.fullmatch(r"<text-\d+>", after["answer"])
    assert [c["name"] for c in after["tool_calls"]] == [c["name"] for c in before["tool_calls"]] == ["get_order"]
    assert "12345" not in json.dumps(clean) and "processing" not in json.dumps(clean)
