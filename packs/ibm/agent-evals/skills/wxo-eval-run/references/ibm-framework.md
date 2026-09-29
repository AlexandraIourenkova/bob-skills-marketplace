# IBM's evaluation framework and this skill

IBM ships its own evaluation framework: the Python package `agentops` (ibm-watsonx-orchestrate-evaluation-framework), installed with `pip install "ibm-watsonx-orchestrate[agentops]"` and driven by the ADK command `orchestrate evaluations` (evaluate, record, generate, analyze, quick-eval, red-teaming). This pack never imports or calls it. It speaks the same file formats, so the user can take this pack's cases and captured runs to IBM's tools, and IBM's to this pack.

Nothing below was checked against a live instance. It comes from the framework's code (1.5.2 and 1.6.4), the ADK's code (2.1.0 and 2.17) and IBM's documentation.

## What stays with IBM

Reach these through export; this pack's scripts do not compute them:

- A simulated user played by an LLM, instead of scripted turns.
- Journey success, parameter F1, knowledge-base faithfulness and answer relevancy.
- Red-teaming.
- The server-side evaluation API (below).

## Shared formats

| This pack's file | IBM's name | Notes |
|---|---|---|
| `agent-evals/cases/<case>.json` | AgentOps Core TestCase | `x_agent_evals` is the pack's only addition; the framework ignores unknown keys and `wxo-eval-cases export` strips it |
| `runs/<ts>/<case>.messages.json` | the framework's Message list | role, content, type, tool_call_id, thread_id, run_id, trace_id, response_time; tool calls and results as JSON strings of type `tool_call` and `tool_response` |

The messages file pairs with its case by file name, which is how the framework's paired loader (`load_paired_test_cases_and_messages`) finds them. Put the exported case and the messages file of the same name in one folder. Which `orchestrate evaluations` subcommand scores a paired folder offline changes between ADK versions. Ask the user to run `orchestrate evaluations --help` in their own terminal; never run the CLI yourself.

Scripted turns mean the same in both tools: turn 0 is `starting_sentence`, then `user_prompts` in order.

## Export

1. `wxo-eval-cases` `export` writes a clean case folder and a ZIP.
2. Copy `<case>.messages.json` from the run folder next to the exported cases when IBM should score the captured runs. A later `export --force` keeps them.
3. The user runs IBM's tooling in their own terminal. The pack's scripts upload nothing.

## Server-side evaluation API

IBM's Agent Testing and Evaluation API (spec 1.0.4) documents, under the instance URL:

- `POST /v1/orchestrate/agent/{agent_id}/test_case/v2`: upload test cases in AgentOps Core format, as JSON or ZIP.
- `POST /v1/orchestrate/agent/{agent_id}/test_case/v2/from_thread`: draft a test case from a thread.
- `POST /v1/orchestrate/agent/{agent_id}/evaluate/v2`: run an evaluation (routing accuracy, journey success, tool quality, answer quality, transaction completion); results through the evaluation list, get and status routes.
- Custom metrics.

These are known from the spec only. Every one of them writes to the tenant. This pack does not call them in 1.0; a later version may, behind the same plan and confirm gate.

## Side effects when the user runs `orchestrate evaluations`

Tell the user before they run IBM's framework themselves:

- **It rewrites two ADK files.** On every run the framework's tenant setup rewrites `~/.config/orchestrate/config.yaml` (it switches `active_environment`) and `~/.cache/orchestrate/credentials.yaml`. Another active environment afterwards is expected; the user can check it with `orchestrate env list`.
- **TLS verification.** The framework's client turns certificate checks off unless the environment was added with verification or `WO_SSL_VERIFY=true` is set. Ask the user to export `WO_SSL_VERIFY=true` first.
- **It prompts.** When the token has expired it asks for the API key interactively, which blocks a headless run.
- **It talks to the live agent.** `evaluate` and `generate` send messages to the agent and create threads, with an LLM-simulated user choosing the turns. The pack's plan, canary and forbidden-tool stop do not apply there. IBM's docs limit evaluation to draft environments.
- **Transcripts go to a judge model.** Answers and tool data are sent to IBM's judge model (the ADK 2.17 default is `watsonx/openai/gpt-oss-120b`, through the tenant's gateway or watsonx). Outside the Dallas region the docs require `MODEL_OVERRIDE`.
- **SaaS path.** The framework builds the SaaS streaming URL with a double slash, which IBM's own code marks as not validated.

The runner avoids all of these: it reads credentials from `WO_*` variables only, keeps TLS verification on, writes only under `agent-evals/`, sends only the scripted turns the user approved, and keeps judging in the session.
