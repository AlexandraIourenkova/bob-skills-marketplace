# Metrics

`score.py` computes every number from parsed JSON: the turn records in `<case>.trace.json` and the case file that ran. No network, no clock, no model, and no regular expression over answer text. The same run folder always gives the same `scores.json`.

A unit is one run of a case. With `--repeat N` a case has N units: `<case>`, `<case>.r2`, ... `<case>.rN`.

## Where each number comes from

| Metric | Source of truth | Per unit | Suite |
|---|---|---|---|
| Turn and case status | parser: `GET /runs/{id}` status and the poll loop | status of the last turn sent | counts, completion rate |
| Tool-call recall | parser | matched work goals / work goals | micro-average |
| Tool-call precision | parser | matched work goals / observed non-hand-off calls | micro-average |
| Name accuracy | parser | work goals whose tool was called / work goals | micro-average |
| Argument accuracy | parser | equal strict keys / strict keys, for goals whose tool was called | micro-average |
| Order respected | parser | no matched goal ran before a DAG predecessor | runs with a violation |
| Routing | parser, hand-off names are a heuristic | matched hand-off goals / hand-off goals | micro-average |
| Forbidden tools | parser, after the fact; a call only the stream showed counts too | `called`, `none`, `unknown` or `n/a` | runs with a call |
| Trace completeness | parser | turns with step history; turns with every call paired; stream turns that agree with a thread that had step history | shares of turns |
| Keyword assertions | author assertion | pass or fail per keyword | passed / total |
| Knowledge-base answer | parser | a `conversational_search` part with citations | in the verdict |
| Timing | client clock and run record | client wall time, server time, tool latency (stream only) | p50, p95, budget breaches |
| Usage | run record | token sums as given | sums; turns without usage |
| Stability | parser | - | pass rate per case, share of runs with the most common tool sequence |
| Answer, fuzzy args, groundedness, judge notes | judge (Bob, `judge-rubric.md`) | pass, fail, unsure or unjudged per item | counts |
| Journey success, parameter F1, KB faithfulness, red-teaming | IBM, through export only | - | - |

## Unknown, n/a and zero

Each ratio in `scores.json` is `{"num", "den", "value", "state"}`.

- `state: "ok"`: a real value, 0 included. Zero means the agent called no expected tool while its steps were visible.
- `state: "unknown"`: the unit's tools are not fully visible: a turn has no step history (`no_step_history`), or one of the cases below. `value` is null. The unit is left out of the suite averages and counted in `tools_unknown_units`.
- `state: "n/a"`: nothing to divide by, for example precision when no tool was called, or routing when the case expects no hand-off.

Tools are unknown for the whole unit when any sent turn lacks step history, because a missing goal could sit in that turn. Causes: `hide_reasoning` on the agent, a route that carries no steps, or step history written late. The probe of `wxo-agent-api` tells which.

These make facts unknown too, never failed:

- `thread_not_settled`: two thread reads never agreed before the settle cap, so a call may not have landed yet. The unit's tools count as not fully visible, as without step history. When such a turn has no answer text, its answer is unknown too.
- `thread_turn_missing`: the thread never showed the message just sent, so the turn has no answer and no steps. A keyword found in no other answer is `unknown` (the assertion's `pass` is null, counted under `assertions.unknown`), and so are a `response` with no answer text and a missing knowledge-base answer.
- A stream that ended before its turn did (status `incomplete`, or `no_completed_frame` on v2): the tools are not fully visible and the answer checks are unknown. A stream cut by a read error is a run error instead, which the runner sends again.
- An async flow still running when a turn ended (`input_request` `async_flow`), the last turn included: its calls and messages reach the thread later, so the tools are not fully visible and the answer checks are unknown.
- Turns never sent after a stop that is not the agent's failure (a harness stop, a turn that ended `incomplete` or `unknown`, a run error, or no stop recorded): the tools are not fully visible, and a keyword or response not found in the answers that were sent is unknown. After a turn that ended `failed`, `timeout`, `expired` or `cancelled`, or a forbidden call, the goals of the unsent turns count as missed.

A call that only the stream showed (a v2 step frame the completed frame leaves out, or a v1 stream call the thread does not show) is listed under `stream_only_calls`. It does not count for recall or precision, but a forbidden tool among them counts as called.

## Matching tool goals

Goals of type `tool_call` are matched against the observed calls of all turns of the unit, in order of appearance.

1. Goals are visited in the topological order of the `goals` DAG; ties keep the order of `goal_details`.
2. A candidate call has `name` equal to the goal's `tool_name`.
3. Arguments are compared per dotted key of the expected `args`: nested objects are walked, lists compare whole, keys the call adds are ignored. The mode of a key is the `arg_matching` entry of the longest path equal to the key or a parent of it; the default is `strict`.
   - `strict`: present and JSON-equal after parsing JSON strings. `1` equals `1.0`; `true` differs from `1`; `"2025"` differs from `2025`.
   - `optional`: equal when present; absent is fine.
   - `ignore`: skipped.
   - `fuzzy`: not compared by the parser. The key goes to the judge queue with the expected and observed values.
   - An unknown mode counts as `strict` and is listed under `unknown_modes`.
4. A goal matches the earliest unused candidate whose strict and optional keys pass and that comes after the calls matching its DAG predecessors. When none comes after, it takes the earliest passing candidate and the order check reports it. When the goal has fuzzy keys and more than one free call passes (a retried search, say), each fuzzy item lists every such call under `candidates`, and a judge pass on any one of them counts.
5. One call serves one goal. Repeated calls stay in the precision denominator.
6. Then calls move between goals while that lets one more goal match (a maximum matching). A goal with loose args that came first never keeps the only call a stricter goal of the same tool could use. The order check runs on the final matching.

Work goals are tool goals that are not hand-offs; hand-off goals feed routing. A hand-off goal named `chat_with_collaborator_<name>` or `transfer_to_<name>` takes a call with either prefix for the same collaborator: the prefix follows the agent style and the route, not the collaborator. A forbidden hand-off matches either prefix the same way. A goal is a hand-off when its `tool_name` matches a hand-off name (`transfer_to_*`, `chat_with_collaborator_*`, `*_agent`), names a collaborator of the planned agent (`handoff_names` in the trace), or any observed call of that name is flagged as a hand-off. Goals and calls follow the same rule, so precision never exceeds 1. Recall and precision use work goals and non-hand-off calls only.

Order: for each matched goal, every tool goal that directly precedes it in the DAG (text goals in between are looked through) and matched must have a call at an earlier position. An unmatched predecessor is not an order violation; recall already counts it.

A fuzzy key does not change recall. A judge `fail` on it fails the unit.

## Text and knowledge-base goals

- `keywords`: each keyword passes when it occurs literally, case-sensitive, in the answer of any turn. These are the author's assertions, reported as pass or fail. They say nothing about answer quality.
- `response`: goes to the judge as an `answer` item. When the agent gave no answer text at all, the goal fails without a judge.
- `conversational_search` goals also need a knowledge-base answer part with at least one citation.

## Verdict of a unit

In this order:

1. `error`: the run produced no turn (an API error before the first answer, or the case file is missing).
2. `fail`: any of: turns not sent because a turn ended `failed`, `timeout`, `expired` or `cancelled`, or a forbidden tool ran; the last turn ended `failed`, `timeout`, `expired` or `cancelled`; a goal not matched; an order violation; a forbidden call; a failing keyword; no knowledge-base answer with citations; a judge `fail`.
3. `unknown`: a run error after some turns (the harness stopped, not the agent); tools not fully visible while the case has tool goals or forbidden tools; a turn that ended while an async flow was still running, the last turn included; a keyword, response or knowledge-base answer that could not be checked because an answer was not seen; the last turn ended with a status outside `completed` and `needs_input`; a cycle in the goals DAG; the runner stopped the case before its next turn after a turn that ended `incomplete` or `unknown`, because an async flow was still running (`async_flow`), because the v2 route kept no thread (`no_thread_support`), because an answer named no thread to continue in (`no_thread_id`), or because the run was interrupted (`interrupted`); turns not sent with no stop recorded.
4. `pending_judgement`: every parser check passes and a judge item is `unjudged` or `unsure`.
5. `pass`: everything passes and every judge item is `pass`.

A latency budget breach (`max_latency_s`, compared with the client wall time of each turn) is reported but does not fail the unit.

Suite rates: `pass_rate` counts `pass` only; `pass_or_pending_rate` adds `pending_judgement`; `completion_rate` counts units whose last turn completed. They cover the units that ran: `units_planned` and `units_not_run` name what the plan made but never sent, when the plan stopped early.

## Judge queue

`judge-queue.json` lists what only a judge can decide. Each item has a stable `id`, a `kind`, a `question`, a `priority` and `material`:

| kind | id | material |
|---|---|---|
| `fuzzy_arg` | `<unit>:<goal>:arg:<key>` | tool name, key, expected and observed value, user turns, story |
| `answer` | `<unit>:<goal>:answer` | expected response, every turn's user text and answer, story |
| `groundedness` | `<unit>:groundedness` | every answer, every tool result with content |
| `judge_notes` | `<unit>:judge_notes` | the author's notes, story, answers, tool calls |

`priority: decides_case` marks items of units whose parser checks all pass: their verdict depends on the judge. `informational` items belong to units that already fail or are unknown.

Long texts are cut at 4000 characters with a note; the trace file has the full text.

## Timing and usage

- Client wall time per turn: from sending the message to the settled thread read.
- Server time per turn: `completed_at` minus `started_at` of the run record, when both exist.
- Tool latency (`t_result - t_call`) and `per_step` exist only with stream capture.
- p50 and p95 use the nearest-rank method.
- Usage is the run record's `usage`, summed as given. A missing record is counted, never estimated.

## Compare

`score.py compare` scores both folders the same way and groups units by case. It compares parser facts and judge verdicts only; a judgement that has not happened yet is never a regression. A case regresses when, in the new run:

- its share of `fail` runs rises (a pass, a pending judgement or an unknown that became a fail);
- a goal matched in every visible base run is unmatched in a visible new run;
- a forbidden tool is called that the base did not call;
- a keyword assertion fails that passed in the base;
- the base ended `completed` or `needs_input` everywhere and a new run ends `failed`, `timeout`, `expired` or `cancelled`, counting only runs that sent a turn (a base without such a run decides nothing here);
- recall drops while both are known.

A rise in the share of `pass` and `pending_judgement` runs, without a regression, is a fix. These go in their own lists, never under regressions:

- `pending_judgement`: more runs wait for the judge than in the base. Judge the new run, then compare again.
- `lost_visibility`: the tools became unknown (no step history in the new run), or a new run ends `incomplete` or `unknown` where the base ended `completed` or `needs_input`: the harness did not see the turn end.
- `run_errors`: more runs were stopped by an API or network error, before or after the first answer.

`--fail-on-regression` exits 1 for regressions only; bad input exits 2. Cases present in one run only are listed separately; a case the other run's plan held but never sent is listed as not sent (`not_run_in_new`, `not_run_in_base`) and not compared.

`case_changed` is set aside, never read as a change in the agent: the case file that ran differs between the runs (its `case_sha256`). A relaxed goal is not a fix and a stricter one is not a regression, so the case is not compared.

`not_comparable` names another host, capture route or environment. compare prints one line for each and the report shows them. The regressions are still listed and still count for `--fail-on-regression`: read them knowing that a difference can come from the target, not the agent.

compare.json keeps a fingerprint of both runs' verdicts. After `score` or `judgments` changes either run's (the base's as saved in its `scores.json`), `score.py` prints the compare to run again, and `report.py` leaves the old comparison out.
