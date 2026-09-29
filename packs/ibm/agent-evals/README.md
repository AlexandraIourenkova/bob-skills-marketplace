# Pack `agent-evals` — Agent evals for watsonx Orchestrate

Vendor: `ibm` (marketplace team). Original skills written for this marketplace, Apache-2.0. Install with `uvx bob-skills add agent-evals`, or with `/skills-add agent-evals` inside Bob once bob-essentials is installed.

Test a deployed watsonx Orchestrate agent through its API: what it answered, which tools it called, with which arguments and results, and whether it handed off to the right collaborator. Test cases use IBM's AgentOps Core format, so the same files work in `orchestrate evaluations` and in the server-side upload. Every message to the agent waits for your yes to a plan.

## Before you install

**Every message sent to the agent creates a run, and usually a thread, on your watsonx Orchestrate tenant, and the agent may call tools that change external systems. The threads stay on the tenant.**

Covered by: Nothing is sent before your yes to a read-only plan or dry run that lists the host, the agent and every tool and collaborator it can reach; the runner then sends one canary case and stops. No script deletes, imports or removes anything, and every thread id is recorded. A forbidden tool is detected after it ran, so use a draft environment and a sandboxed test tenant.

**Test prompts go to your tenant, and the saved traces hold prompts, answers and tool outputs that may carry personal data from the agent's backends. If you run exported cases in IBM's own evaluation framework, it sends the transcripts to its judge model.**

Covered by: Traces stay in the project under `agent-evals/runs/` and `agent-evals/probe/raw/`, and the skills suggest git-ignoring both. Bob judges answers in your session, so nothing goes to a third service; export only writes local files. Credentials come from the environment only, and the token stays in memory, never printed or written. Captures become test fixtures only through `probe.py sanitize` and your review.

**Agent answers, tool results, thread messages and agent instructions come from the tenant and its backends and can carry text aimed at Bob.**

Covered by: The rule, the skills and the judge rubric treat them as data: quoted, never followed, and an instruction found in an answer is reported as a finding. Turns come from the case file, never from the agent's output, and `report.html` escapes everything.

## Contents

| Component | What it does |
|---|---|
| `skills/wxo-agent-api` | A standard-library client for the Runs API that returns the answer with every tool call, tool result, hand-off and timing; a one-time probe that shows where this instance exposes tool calls; `ask.py` for one question or a few turns; a batch template; references on routes, auth and stream formats |
| `skills/wxo-eval-cases` | Test cases in IBM's AgentOps Core format: a skeleton from your scenario, a draft from a real thread, validation against the agent's tools and argument schemas, an export folder and ZIP for IBM's tools. Reads the tenant only |
| `skills/wxo-eval-run` | A read-only plan with a hash, a canary case, then the rest; offline, deterministic scoring (tool-call recall and precision, arguments, order, routing, forbidden tools, keyword assertions, latency, tokens); Bob judges answer quality with a rubric; Markdown, HTML and CSV reports; a diff of two runs |
| `rules/agent-evals.md` | Credentials from the environment only, reading runs and sending asks, TLS stays on, tenant content is data, unknown is not zero, captures stay local |
| `commands/wxo-eval.md` | `/wxo-eval [cases-dir]`: catalog, probe check, validation, plan, canary, the rest, score, judge, report, each send after your yes |
| `custom_modes.yaml` | `agent-evals` mode: read, execute, skills, and edits only under `agent-evals/` |

The pack measures what a deployed agent does at runtime. It works next to wxo-adk: `agent-instructions-evaluator` reviews an agent's YAML without running it, and `telemetry-analyzer` reads production traces. The report points failing cases to both.

## Requirements

- A deployed agent on watsonx Orchestrate SaaS (IBM Cloud or AWS), or the Developer Edition at `http://localhost:4321`. For Cloud Pak for Data and on-premises, a bearer token in `WO_TOKEN`.
- `WO_INSTANCE`, and `WO_API_KEY` or `WO_TOKEN`, set in your own shell. The instance URL and the API key are on the instance's Settings, API details page. Optional: `WO_AUTH_TYPE`, `WO_IAM_URL`, and `WO_CA_BUNDLE` for a private CA.
- Developer Edition: `WO_INSTANCE=http://localhost:4321` with `WO_TOKEN`, or `WO_USERNAME` and `WO_PASSWORD`. An API key does not apply there.
- Python 3.9 or later; the scripts use the standard library only. Neither the ADK nor IBM's evaluation framework is needed.

## How it was checked

Routes, payloads and event names come from IBM client code (ADK 2.1.0 and 2.17.0, the evaluation framework 1.5.2 and 1.6.4), the server OpenAPI and the IBM API Hub specs. Nothing was observed on a live instance yet. The scripts are tested on fixtures built from those documented shapes in `cli/tests/test_agent_evals_client.py`, `test_agent_evals_probe.py`, `test_agent_evals_cases.py` and `test_agent_evals_run.py`: NDJSON and SSE framings, every step of every assistant message, a missing step history reported as unknown, the gates (no transport call without the approved hash), no token in any output, and an escaped HTML report. The first probe on a live tenant comes next; its findings and sanitized captures ship as 1.0.1.

## Planned

- 1.0.1: the probe's findings from a live tenant, and the sanitized captures as test fixtures.
- 1.1.0: answering widgets and async flows from the case; a gated cleanup of the threads a run left; a gated upload of cases and a server-side evaluation run.
