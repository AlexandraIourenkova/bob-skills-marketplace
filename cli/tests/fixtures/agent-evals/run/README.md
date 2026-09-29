# Runner fixtures

Inputs for `cli/tests/test_agent_evals_run.py`. They are written by hand; nothing here was captured from a live watsonx Orchestrate instance.

- `cases/timeoff.json`: one turn. Its goals match the calls in `../documented/thread-messages.json`: `fetch_assignment_id`, then `get_holiday_calendar`, then the hand-off to `payroll_agent` with a fuzzy `message`. A text goal carries two keyword assertions, an expected response and judge notes; `delete_employee` is forbidden.
- `cases/payslip.json`: two turns (`starting_sentence` and one `user_prompts` entry), used to check that the canary sends one case and `resume` sends the rest in one thread.
- `probe.json`: the two fields the runner reads from a probe result, `host` and `capture`.

The tests build run folders from these cases and the documented thread messages, then change single fields to cover each metric.
