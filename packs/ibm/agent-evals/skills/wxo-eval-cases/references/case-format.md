# Case format

One case is one JSON file in IBM's AgentOps Core TestCase format, the format of the evaluation framework (package `agentops`) behind `orchestrate evaluations`. The same file works in three places:

- this pack's runner (wxo-eval-run);
- `orchestrate evaluations evaluate --test-paths <folder> --output-dir <dir>`;
- the server-side test-case upload, `POST /v1/orchestrate/agent/{agent_id}/test_case/v2`, which takes JSON or a ZIP.

This pack adds one optional key, `x_agent_evals`. The framework ignores unknown keys, and `cases.py export` removes it anyway.

## Example

```json
{
  "agent": "hr_agent",
  "story": "An employee with the username nwaters wants to know their booked time off for 2025.",
  "starting_sentence": "What is my time off schedule for 2025? My username is nwaters.",
  "user_prompts": ["And which public holidays are there?"],
  "goals": {
    "fetch_id-1": ["get_timeoff-1"],
    "get_timeoff-1": ["summarize"]
  },
  "goal_details": [
    {"type": "tool_call", "name": "fetch_id-1", "tool_name": "fetch_assignment_id",
     "args": {"username": "nwaters"}},
    {"type": "tool_call", "name": "get_timeoff-1", "tool_name": "retrieve_timeoff_schedule",
     "args": {"assignment_id": "15338303", "start_date": "2025-01-01", "end_date": "2025-12-31"},
     "arg_matching": {"start_date": "fuzzy", "end_date": "fuzzy"}},
    {"type": "text", "name": "summarize",
     "response": "Your time off in 2025: 2025-04-11 and 2025-12-24.", "keywords": ["2025-04-11"]}
  ],
  "x_agent_evals": {
    "forbidden_tools": ["delete_employee"],
    "max_latency_s": 30,
    "judge_notes": "must list both dates",
    "repeat": 1
  }
}
```

## Fields

| Field | Required | Meaning |
|---|---|---|
| `agent` | yes | The agent name as `GET /v1/orchestrate/agents` lists it. The runner resolves it to the id. Optional in agentops, required here. |
| `story` | yes | Who the user is and what they want. Feeds the judge and IBM's simulated user. The runner never sends it. |
| `starting_sentence` | yes | Turn 0, sent as written. Optional in agentops, required here. |
| `user_prompts` | no | Turns 1..n, sent as written, in order. A list of non-empty strings. |
| `goals` | yes | The goals DAG: goal name -> list of goals that come after it. |
| `goal_details` | yes | The goals, one object each. |
| `x_agent_evals` | no | This pack's extension. |
| `dataset_name` | no | agentops uses it when set, otherwise the file name. Leave it out, or keep it equal to the file name. |
| `max_user_turns`, `runtime_context`, `file_upload`, `attack_data`, `agents_list_or_path` | no | agentops fields. Accepted; the runner in 1.0 does not use them. |

Any other top-level key gives a warning: agentops ignores it, so it is usually a typo.

## Turns

- Turn 0 is `starting_sentence`. Turn *i* is `user_prompts[i-1]`. This is the agentops order for scripted turns.
- The runner sends exactly these turns on one thread, one after another. It never chooses a message from the agent's answer.
- There is no simulated user in this pack. IBM's framework simulates one from `story` when `user_prompts` runs out; with `user_prompts` set, both tools send the same turns.

## Goals DAG

- Every name in `goals`, key or value, is a `goal_details` name, and every `goal_details` name appears in `goals`. agentops refuses a case otherwise.
- A goal with nothing after it maps to `[]`, or appears only as a value.
- `goals` must not have a cycle. The runner checks order: each goal's predecessors must have matched earlier calls.
- Goal names are unique. The drafts use `<tool>-<n>`, `kb_answer-<n>` and `summarize`.
- A branch is allowed: `{"fetch_id-1": ["timeoff-1", "holidays-1"], "timeoff-1": ["summarize"], "holidays-1": ["summarize"]}`.

## Goal types

| Type | Fields | How the runner scores it |
|---|---|---|
| `tool_call` | `tool_name` (required), `args`, `arg_matching` | An observed call with the same `tool_name` and matching args, across all turns. See `arg-matching.md`. |
| `text` | `response`, `keywords` | `keywords`: literal strings the answer must contain, reported as assertion pass or fail. `response`: the expected answer, judged. |
| `conversational_search` | `response`, `keywords` | A knowledge-base answer with citations; `response` is judged. |
| `interaction`, `tool_response` | agentops fields | Accepted, with a warning: this pack does not score them in 1.0. `interaction` needs `identifier` {key, value}. |

- Name the final answer goal `summarize` and make it a `text` goal. agentops reads the goal named `summarize` as the final summary.
- A `text` goal without `response` and `keywords` gives a warning: nothing to judge or assert.
- Keywords are author-written assertions, not a quality score. Answer quality is judged against `response`.

## Hand-offs and routing

- A collaborator hand-off is a tool call named `chat_with_collaborator_<agent>` (the default style) or `transfer_to_<agent>` (react styles). Names ending in `_agent` also count as hand-offs; `validate` treats such a name as a tool when the tool catalog has it.
- To test routing, list the hand-off as a `tool_call` goal. The runner matches it like a tool, and a goal with either prefix matches a call with either prefix for the same collaborator: `transfer_to_payroll_agent` matches `chat_with_collaborator_payroll_agent`. The prefix follows the agent style and the route (v2 names hand-offs `transfer_to_*`), so one case works on every route. `catalog` prints the name the agent's style gives. Hand-off detection is by name, so it is a heuristic.
- The message the agent passes on is free text: give the hand-off goal `args: {}`, or keep the message with `arg_matching` `fuzzy`.
- `validate` checks a hand-off's target against `agents.json` and the case agent's collaborators, and warns on a mismatch.
- `from-thread` leaves hand-offs out unless given `--handoffs`.

## x_agent_evals

| Key | Type | Meaning |
|---|---|---|
| `forbidden_tools` | list of unique tool names | The case fails when the agent calls one; a hand-off name matches either prefix for the same collaborator. Detected after the run; the call already happened. Must not also be an expected `tool_call` goal. |
| `max_latency_s` | number > 0 | Budget for the client wall time of each turn. |
| `judge_notes` | string | What the judge checks besides `response`. |
| `repeat` | integer from 1 to 20 | How many times the runner sends the case. Every repeat creates new threads and runs on the tenant. |

Any other key inside `x_agent_evals` is an error.

## File names

- One case per file in `agent-evals/cases/`. The file name without `.json` is the case name, and the run files use it.
- Use letters, digits, `.`, `-` and `_`.
- A name ending in `agent` is refused: agentops discovery skips files whose name ends in `agent.json`.
- `*.messages.json` is the agentops name for message exports; `validate` skips such files.
- Two case files with the same name in different folders are an error: agentops keys cases by file name.

## Placeholders

`new` and `from-thread` write `<TODO>` where a value is unknown. `validate` reports each one as an error until it is replaced. `<TODO>` is not an agentops value; `<IGNORE>` is, and `arg-matching.md` explains it.

## Export

`cases.py export` validates, then writes `agent-evals/export/<name>/<case>.json` and `<name>.zip`:

- `x_agent_evals` is removed; every other key and its order stay as written.
- The ZIP holds the same files at its root, with fixed timestamps, so the same cases give the same bytes.
- The export only writes local files. Uploading the ZIP writes to the tenant and is the user's step. Whether the upload wants the files at the ZIP root is not verified.
