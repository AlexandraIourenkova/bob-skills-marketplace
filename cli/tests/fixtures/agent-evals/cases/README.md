# Case fixtures for wxo-eval-cases

Hand-written AgentOps Core test cases for `cases.py validate` and `export`, checked against the documented catalog in `../documented/` (`tools.json`, `agents.json`). They are not captured from a live instance. All names, ids and values are fake.

| File | What it proves |
|---|---|
| `valid.json` | One turn, two tool goals, fuzzy dates, a summarize goal with keywords, every `x_agent_evals` key. No errors, no warnings. |
| `valid-multi-turn.json` | Three `user_prompts`, a goals DAG with a branch, `optional` and `fuzzy` matching, a hand-off goal (`chat_with_collaborator_payroll_agent`), a `conversational_search` goal. No errors, no warnings. |
| `bad-dag.json` | A name in `goals` that is not in `goal_details`, and the reverse. |
| `bad-cycle.json` | `goals` with a cycle. |
| `unknown-tool.json` | A `tool_name` that is not in the tool catalog. |
| `bad-args.json` | An integer where the input_schema wants a string, an argument the tool does not have, a required argument left out (a warning). |
| `bad-arg_matching.json` | An `arg_matching` path that is not in `args`, and a strategy that does not exist. |
| `bad-x_agent_evals.json` | An unknown key, a duplicate forbidden tool, `max_latency_s` 0, `repeat` 0, `judge_notes` not a string, and a forbidden tool that is also an expected goal. |
| `bad-structure.json` | No `story`, a non-string user prompt, a `goals` value that is not a list, an unknown goal type, a `tool_call` goal without `tool_name`, an `interaction` goal without `identifier`. |

`../documented/cases/` holds the library's own copies of the valid and bad cases; the tests check that `validate` gives them the same verdicts.
