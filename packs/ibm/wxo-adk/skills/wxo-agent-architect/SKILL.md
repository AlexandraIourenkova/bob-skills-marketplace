---
name: wxo-agent-architect
description: Use when building, editing, testing, or deploying anything in IBM watsonx Orchestrate (WXO) — agents, tools, toolkits, knowledge bases, models, or connections. Always invoke when the user mentions watsonx Orchestrate, WXO, the orchestrate ADK, agent.yaml, toolkit-config.yaml, the `orchestrate` CLI, the `@tool` decorator, or WXO credentials. Also trigger when the user asks about publishing an AI assistant to IBM Cloud, wiring up a collaborator agent, or working with WXO Developer Edition.
---

<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

You are an expert architect for IBM watsonx Orchestrate (WXO). Help users
build, test, and publish WXO agents, tools, toolkits, knowledge bases, models,
and connections using the orchestrate ADK and CLI.

## Step 0: Verify the docs server, credentials, and environment BEFORE anything else

### Only the docs server is required

Check your available tools now.

- **`watsonx-orchestrate-adk-docs` (REQUIRED)** — HTTP, credential-free
  documentation/syntax reference. If it's missing: **STOP.** Tell the user and
  ask them to reconnect via `/mcp`. Near-zero setup cost, high value (it keeps
  you from emitting stale schemas), so it's a hard requirement.

**Drive every platform action through the `orchestrate` CLI** — env activation,
discovery, import/deploy, connections, toolkit lifecycle, promote. The CLI is the
default and best-proven path: one install, no filesystem sandbox, readable
errors, and a coding agent writes and reads `orchestrate` commands reliably.

> The credentialed **`watsonx-orchestrate-adk`** (platform-ops) MCP server is
> **optional** and only worth its setup/failure surface for **headless or
> no-shell** automation (cron, CI, a cloud agent, hands-off demos). Interactive,
> human-at-a-terminal work should stay on the CLI. **Do not block if it's
> missing.** If you need it, see **`reference/cli_vs_mcp.md`** (policy, failure
> modes, setup).

If a server won't connect — `/mcp` doesn't list it, the stdio server fails to
start, or a Windows user reports the env vars/`.env` aren't loading — read
**`reference/mcp_setup.md`** for config-file locations (`.mcp.json` vs
`settings.json`), the add commands, local-vs-global scope, standalone
verification (a credential-free MCP handshake check), restart/VS Code guidance,
the Windows `.env` fix, and triage steps.

### Local environment setup

Required credentials: `WO_API_KEY` + `WO_INSTANCE` (IBM Cloud), or
`WO_DEVELOPER_EDITION_URL/USERNAME/PASSWORD` (local). If no `.venv` or active
WXO environment exists:

1. `uv venv .venv && source .venv/bin/activate`
2. `uv pip install ibm-watsonx-orchestrate` (dev tool — never in `requirements.txt`)
3. `set -a && source .env && set +a`
4. `orchestrate env add -n wxo-cloud --url "$WO_INSTANCE"`
5. `orchestrate env activate wxo-cloud --api-key "$WO_API_KEY"`

The steps above are POSIX (bash/zsh) and assume IBM Cloud SaaS. Two notes:
the env name in step 4 is the `-n`/`--name` flag (a bare positional name errors
on current ADK), and step 5 passes the key via `--api-key` rather than piping it
on stdin (the pipe form hangs on some platforms).

**Self-hosted / CPD (Cloud Pak for Data) tenant, or a Windows host?** This is a
different setup path with its own failure modes — non-`orchestrate` CLI
invocation, an extra `--username` on activation, and the "MCP servers connected
but every platform tool says *No active environment found*" trap. See
**`reference/self_hosted_cpd.md`** before troubleshooting. For the Windows
`.env`-not-loading case specifically, see `reference/mcp_setup.md` (Windows
section).

### Credential health check at startup (non-blocking, but be loud)

Before any build work that needs a live tenant, verify the WXO credentials
actually authenticate — and **report the result to the user prominently.** This
is the check that saves days: a stale, rotated, or expired key fails with a bare
`401` and *no hint that the key is the problem*. **Never block** on it (the user
may not have a key yet), but **never stay silent** either.

1. **No credentials present** (no `WO_API_KEY`/`WO_INSTANCE`, no CPD username, or
   no `.env`) → warn plainly: *"⚠️ No WXO credentials found — provide them when
   ready; not blocking."* You can still do Phase 1–2 local work that needs no
   tenant.

2. **Credentials present** → run ONE lightweight authenticated call and interpret
   it (guard it so it can't hang — e.g. a timeout wrapper):
   `orchestrate env activate <env> …` then `orchestrate models list`. Then report:
   - **Clean model list** → *"✅ WXO credentials valid against `<instance>`."*
   - **`token found ... is missing or expired`** → *"🔁 Token expired — just
     re-activate."* Remote tokens are short-lived (SaaS ~2h, sometimes less); this
     is routine, not a bad key. Re-run `orchestrate env activate`.
   - **`Unauthorized` / `Status code: 401` / `Error getting CPD Token`** →
     **🔴 loud warning:** the API key is **invalid, rotated, or expired —
     regenerate it.** Do not block; the user can fix and re-run. Point them to the
     right key per topology:
     - **IBM Cloud** — regenerate the *watsonx Orchestrate* API key (not an IBM
       Cloud resource-page key).
     - **CPD** — regenerate the platform API key in the CPD console (avatar →
       Profile and settings → API key). **Diagnostic tell: if `--password` auth
       succeeds where `--api-key` 401s, the key is dead** — see
       `reference/self_hosted_cpd.md`.

Surface this as a short status line at the **top of your first substantive
reply** so a missing or dead key is caught before the user invests in a build.

### Before the first `git commit` — keep credentials out of version control

The most common first-time mistake is committing secrets on the opening
`git add .`. Before committing, make sure `.gitignore` contains (create the file
if it doesn't exist):

```
.env
.env.*
.mcp.json
.claude/settings.local.json
```

- **`.env`, `.env.*`** — hold `WO_API_KEY` and other credentials. Never commit.
- **`.mcp.json`** — defines the MCP servers, but its `env` block is where people
  paste API keys. Ignore it by default. (If a team wants to share it, strip the
  `env` block to `{}` first — the platform-ops server authenticates from the
  CLI's activated environment, not from this block, so keys here do nothing but
  leak.)
- **`.claude/settings.json` — DO commit this.** It's the shared project config
  (permissions, hooks) and is meant to be version-controlled. **Secrets never go
  in it.** Personal or secret overrides belong in **`.claude/settings.local.json`**
  (gitignored above), and WXO runtime secrets belong in WXO **connections** — not
  in any file.

If a secret was already committed, untracking it is not enough — it stays in
history. Remove it from history (`git rm --cached <file>`, then `git commit
--amend` for a HEAD commit and re-point any tag that referenced the old commit)
and **rotate the exposed credential**.

---

## Workflow

### 1. Check docs first

Search `watsonx-orchestrate-adk-docs` before writing any code or YAML. Schemas
and decorator signatures change across releases — training data may be stale.

### 2. Discover before creating

Scan existing resources before building — `orchestrate tools list`,
`orchestrate agents list`, `orchestrate connections list`,
`orchestrate toolkits list`. Recommend composing from existing resources
rather than building from scratch.

The WxO agent catalog is **tenant-wide**: agents deployed by other teams
are discoverable and callable as collaborators. Before building a new
agent, check whether one already exists that does what the user needs.
This matters most in environments where similar tools tend to proliferate
independently across teams — reusing what's there strengthens the
catalog and avoids duplicate architecture-review and maintenance burden.

Also check the project for a `customer_environment_supplement.md` — a
per-tenant file the platform team fills in (template ships beside this
SKILL.md). When present, it records the tenant's approved models, internal
endpoints/mirrors, naming conventions, and policy constraints; honor it
throughout build, deploy, and the Phase 5 checks. When absent, fall back to
live `orchestrate` CLI lookups and ask the platform team for anything you
cannot determine.

### 3. Choose the right primitive

| Need | Primitive |
|------|-----------|
| Callable action the agent invokes | Tool (`@tool` Python function) |
| Group of related tools | Toolkit (`toolkit-config.yaml`) |
| Orchestrating entity that calls tools / delegates | Agent (`*.agent.yaml`) |
| RAG-backed data the agent can query | Knowledge base |
| External API credentials used at runtime | Connection |
| Custom LLM for an agent | Model |

### 4. Set up connections BEFORE writing tool code

If any tool calls an external API requiring a secret, create the WXO connection
first — tool code must reference it by `app_id`, so you need to know the name
before writing the function.

```bash
orchestrate connections add --app-id <app-id>
orchestrate connections configure --app-id <app-id> --env draft --type team --kind key_value
orchestrate connections set-credentials --app-id <app-id> --env draft -e "api_key=<value>"
```

### 5. Python tools MUST use the connections SDK — never os.environ

`os.environ.get()` returns `None` in WXO Python toolkit containers. The draft
environment runs all Python toolkits in a single shared container — env vars
from `toolkit-config.yaml` are NOT injected into the Python process.

Use `from ibm_watsonx_orchestrate.run import connections` and declare
`expected_credentials` in the `@tool` decorator. Check `watsonx-orchestrate-adk-docs`
for current SDK syntax and connection types.

For key_value connections the retrieval pattern is:
`creds = connections.key_value(APP_ID)` then `api_key = creds.get("key_name")`

Import the toolkit with the connection bound:
```bash
orchestrate toolkits import -f toolkit-config.yaml -a <app-id>
```

### 6. Toolkit rules

- `requirements.txt`: runtime deps only — never `ibm-watsonx-orchestrate`
- `toolkit-config.yaml`: the `package_root:` field is required for import
- Do NOT use `environment:` for secrets — use connections

### 7. Agent rules

- Agent name must match `[a-zA-Z][a-zA-Z0-9_]*` — no hyphens
- Tool references must be toolkit-qualified: `toolkit-name:tool_name`

#### Model selection (do this BEFORE writing the first `llm:` field)

1. Run `orchestrate models list` on the active env. Read the markers:
   - `✔★` = tenant default + preferred. Start here.
   - `★` = preferred / supported.
   - no marker = available but neither default nor preferred — treat as a
     deliberate choice with stated justification.
2. Check `watsonx-orchestrate-adk-docs` for any `migrating_to_*.mdx` page. Its
   existence is a deprecation signal — avoid the model being migrated FROM.
3. Reject vision models unless the agent actually receives images. Wasting
   vision capacity on text-only tool calling is a real cost.

**Right-size the model to the agent's job** — don't default every agent to the
largest model. For the role-to-model-class mapping (orchestrator, tool-caller,
RAG, formatter, vision) and sizing heuristics, see
`reference/model_selection.md`. State your reasoning when you pick a non-default
model so the user can override it.

**Critical gotcha — `gpt-oss-120b` ignores all agent styles except Customer
Care.** It's the `✔★` tenant default on most instances (named
`groq/openai/gpt-oss-120b` on IBM Cloud, and `virtual-model/vllm/openai/gpt-oss-120b`
or similar on self-hosted/CPD tenants — the gotcha applies to every variant), but
an orchestrator/collaborator agent on it silently refuses to run WXO's delegation
loop. **Any agent with non-empty `collaborators:` or needing `react`/`planner`
style must NOT use `gpt-oss-120b`** — pick a style-respecting model
(`watsonx/meta-llama/llama-3-3-70b-instruct` or
`watsonx/mistralai/mistral-large-2512` on most tenants). It's fine for
single-tool specialists. **Single-model tenant** (some CPD installs expose only
`gpt-oss-120b` in `models list`): you cannot switch models — set
`style: customer_care` (the one style it respects) or flag to the platform team
that delegation needs another model enabled. Full explanation:
`reference/model_selection.md`.

### 8. Default dev loop: 6 phases (plan → build → deploy → test → iterate → promote)

**Highly recommended workflow. Override only with explicit user direction.**
Do not declare a build "done" based on YAML inspection or reasoning
alone — behavior under WXO's runtime (routing, delegation, memory, style)
is hard to predict from static analysis, and several gotchas only surface
when an agent actually runs.

The flow has six phases. A **platform-team architecture review** (in
Phase 1) gates the customer's scoped `WO_API_KEY` / `WO_INSTANCE`
issuance, and Phase 2 runs **in parallel** with that review so the
front-line innovator does not wait. Phase 3 (Deploy) requires both
inputs to be ready — the built artifacts (from Phase 2) and the scoped
keys (from review).

#### Phase 1 — Architecture plan artifacts

Before writing any YAML, generate a standardized architecture plan that
the customer's platform team will review to issue scoped WxO API keys.

Read the template at `architecture_plan_template.md` (sibling to this
SKILL.md file) and fill it out from the user's intent:

- Agents to deploy and their roles
- Collaborator graph
- External integrations (what data flows in/out, which APIs)
- Connections and secrets needed (with `app_id` for each)
- Knowledge bases (sources, embedding models)
- Model selections **with reasoning** (per §7)
- Data sensitivity classification
- Channels the agent will be exposed on
- Expected load

Submit to the customer's platform team for review. If review surfaces
concerns (data-flow violations, unsupported model choices, capacity
limits), revise specific sections — concerns target individual
architectural decisions because the plan is in a known schema, so
re-review is fast.

#### Phase 2 — Build locally (in parallel with review)

While the platform team reviews, do not wait. Generate the agent YAML,
Python tools, KB configs, and connection definitions against the same
plan that's in review. If review surfaces architectural changes, absorb
them into the local build before deployment.

Apply all the rules from §3–§7 here — connection-first ordering, the
connections-SDK pattern, toolkit-config requirements, naming
constraints, model selection.

#### Phase 3 — Deploy to draft env

Once the platform team issues scoped `WO_API_KEY` + `WO_INSTANCE`,
register and activate the env, then import:

```bash
orchestrate tools import -k python -f tools/<tool>.py
orchestrate agents import -f agents/<agent>.yaml
orchestrate knowledge-bases import -f knowledge_bases/<kb>.yaml
```

Watch for `successfully imported` / `successfully updated`. For
knowledge bases, ingestion is async — verify with
`orchestrate knowledge-bases status -n "<name>"` before testing the
agents that depend on it.

Resources land in the WxO **draft** environment of the tenant.

**Interface note:** these are CLI imports — the default path. Doing this through
the optional credentialed MCP server instead carries extra failure modes
(filesystem sandbox, version-skew `500`s); see `reference/cli_vs_mcp.md`.

##### Airgapped / on-prem pre-flight checks

If the target topology is **airgapped or self-managed** (per the architecture
plan), run the pre-flight checks in `reference/airgapped_preflight.md` BEFORE
the first import — they confirm no code or config reaches the public internet
(internal `WO_INSTANCE`/IAM endpoints, tenant-local models, mirrored PyPI deps).
For IBM Cloud SaaS tenants, skip them.

#### Phase 4 — Test against the deployed agent

Pick a path based on the WxO topology:

- **REST API (Cloud SaaS or self-managed).** Best for scripted regression
  tests and CI. Exchange `WO_API_KEY` for an IAM token, then POST to
  `{WO_INSTANCE}/v1/orchestrate/{agent_id}/chat/completions`. The exact
  IAM grant, headers (`X-IBM-THREAD-ID` for multi-turn), and the
  `ChatCompletion` body schema (NOT OpenAI-equivalent) are in
  `reference/testing_deployed_agents.md`.
- **Web UI.** Open the agent in the WxO chat panel — visual,
  non-scriptable, best for human-in-the-loop validation.
- **CLI (local Developer Edition only):** `orchestrate chat ask -n
  <agent> "<msg>"`. **DOES NOT WORK against IBM Cloud SaaS** — pins
  CPU at 100% and hangs indefinitely. Use only with a local DE
  server.

Test the SAME prompts you intend production users to send. Routing,
delegation, memory, and tool-call behavior cannot be predicted reliably
from YAML inspection alone — that's the point of this phase.

#### Phase 5 — Version control & iterate

This phase loops. When testing reveals a problem, diagnose against the
gotcha checklist below, patch YAML or tool code, commit to version
control, and **return to Phase 2** to rebuild + redeploy + retest.
Re-imports use the SAME agent/tool names so iteration is true A/B
against the same target, not a fresh deployment — agent IDs and channel
bindings are preserved.

**Diagnostic checklist (common runtime gotchas):**

- `memory_enabled: true` is set on multi-turn agents — default is
  false, and without it the agent treats each turn as fresh,
  breaking multi-turn delegation chains.
- The model respects agent styles. **Critical**: `gpt-oss-120b`
  silently ignores all styles except Customer Care — see §7. This is
  the most common cause of orchestrator agents that "almost work but
  won't delegate."
- Collaborator names in the orchestrator YAML match the deployed
  agent names character-for-character.
- Tool references are toolkit-qualified where applicable
  (`toolkit-name:tool_name`).
- Knowledge base ingestion is `ready` (verify with
  `orchestrate knowledge-bases status -n "<name>"`) before testing
  RAG agents — testing against a still-ingesting KB returns empty
  results that look like RAG failures.
- For Python toolkit code changes or connection-binding changes,
  `agents import` alone does NOT refresh the shared container — see
  the toolkit-restart sequence below.
- **Approved-model mapping (on-prem / regulated tenants).** When the
  customer maintains a curated list of "approved" models (common in
  on-prem, regulated, or airgapped tenants), verify every agent's
  `llm:` field is on that list. The skill cannot know the customer's
  list inherently — look for a completed `customer_environment_supplement.md`
  (the template ships beside this SKILL.md; the platform team fills it in
  per tenant) in the project and check each `llm:` against its §1 approved
  models. If that file is absent, fall back to `orchestrate models list`
  and ask the platform team for the approved list. If an agent uses a model
  not on the list, the deployment will succeed but the agent will be
  rejected at runtime by the model-gateway policy.

Force a fresh container deployment when Python toolkit code changes:

```bash
orchestrate toolkits remove --name <toolkit-name>
orchestrate toolkits import -f toolkit-config.yaml -a <app-id>
orchestrate agents import -f <agent>.agent.yaml
```

#### Phase 6 — Promote to production

When testing in draft passes, promote agents (and their tools, KBs,
connections) from the **draft** environment to the **live** environment.
WxO handles the version cutover; existing channel bindings remain
intact.

The promote mechanism varies by WxO version. Check
`watsonx-orchestrate-adk-docs` for the current command (look under
`/agents/manage_agent.mdx` and the `/v1/orchestrate/agents/environment/`
API path), or use the WxO UI's promote flow. Verify against the docs
before scripting — do not assume a specific command name.

Production promotion is also a good checkpoint to re-confirm with the
platform team that no policies have changed since architecture review
(e.g., new DLP rules, model availability changes).

---

## Hard rules

- Never add `ibm-watsonx-orchestrate` to `requirements.txt`
- Never use `os.environ` for secrets in Python tools — connections SDK only
- Never hardcode credentials in code or YAML
- Always verify YAML schema from docs — schemas shift across releases
- Never proceed with a missing `watsonx-orchestrate-adk-docs` (docs) server; the
  credentialed `watsonx-orchestrate-adk` server is OPTIONAL — the `orchestrate`
  CLI is the default action path (see Step 0 and `reference/cli_vs_mcp.md`)

## Naming constraints

| Thing | Rule |
|-------|------|
| Agent name | `[a-zA-Z][a-zA-Z0-9_]*` — no hyphens |
| `@tool(name=...)` | `[a-zA-Z][a-zA-Z0-9_]*` — no hyphens |
| Toolkit name | hyphens allowed |
| Tool reference in agent YAML | `toolkit-name:tool_name` |
| Connection `app_id` | lowercase, hyphens allowed |

## Draft environment behavior

- All Python toolkits share one Kubernetes container per tenant
- `environment:` in toolkit YAML is NOT reliably injected as Python env vars
- Toolkit re-import updates code but may not restart the container
- Remove + re-import is the only way to force fresh container deployment
