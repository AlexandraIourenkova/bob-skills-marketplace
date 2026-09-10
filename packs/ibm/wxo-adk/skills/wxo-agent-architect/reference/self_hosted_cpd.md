<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# Self-hosted / CPD (Cloud Pak for Data) + Windows setup & troubleshooting

The happy-path Step 0 in `SKILL.md` assumes **IBM Cloud SaaS on a POSIX shell**.
A **self-hosted WXO on CPD** tenant — especially driven from a **Windows** host —
hits a different set of failure modes. Everything below was observed on a real
CPD tenant (`WO_INSTANCE` of the form
`https://cpd-cpd.apps.<cluster>/orchestrate/cpd/instances/<id>`), ADK 2.11.0,
Windows + VS Code. If you are on IBM Cloud SaaS and a Mac/Linux shell, you will
likely hit none of this — don't pre-apply these workarounds.

## The root-cause trap: "MCP servers connected but every platform tool fails"

**Symptom:** `/mcp` shows both servers connected, but every
`watsonx-orchestrate-adk` tool returns:

```
Error calling tool 'list_agents': No active environment found.
Please run `orchestrate env activate` to activate an environment
```

**Cause:** the `watsonx-orchestrate-adk` (stdio) MCP server does **not**
authenticate from the `WO_API_KEY` / `WO_INSTANCE` you put in the `.mcp.json`
`env` block. It reads the **active environment that the `orchestrate` CLI
persisted to disk**. If no `orchestrate env activate` has succeeded, the server
is up but has nothing to talk to.

**Fix:** run a successful `orchestrate env activate` from the CLI (see below),
*then* the MCP tools work. "MCP connected" and "WXO reachable" are two separate
states — connecting the server is necessary but not sufficient.

Corollary: putting `WO_API_KEY` in the `.mcp.json` `env` block is **both
useless and a leak risk** (it has been seen committed to git). Leave it `{}` and
authenticate via the CLI.

## Invoking the CLI when there's no activated venv on PATH

On a uvx-driven Windows box, bare `orchestrate` is often `command not found`,
and `uvx ibm-watsonx-orchestrate` fails — the package's executable is
`orchestrate.exe`, not `ibm-watsonx-orchestrate`:

```
An executable named `ibm-watsonx-orchestrate` is not provided by package
`ibm-watsonx-orchestrate`. The following executables are available:
- orchestrate.exe
```

Use the `--from` form for every CLI call:

```
uvx --from ibm-watsonx-orchestrate orchestrate.exe --version
uvx --from ibm-watsonx-orchestrate orchestrate.exe env list
```

(Inside an activated venv, plain `orchestrate ...` is fine — this only applies
when running ad-hoc via uvx.)

## Activating a CPD environment (the flags that actually matter)

CPD is a **third credential topology** beyond the two named in `SKILL.md`
(IBM Cloud `WO_API_KEY`+`WO_INSTANCE`; local DE `WO_DEVELOPER_EDITION_*`). CPD
activation needs the instance URL **plus a username plus the API key**:

```
# add the env — name is the -n / --name flag, NOT a bare positional arg
uvx --from ibm-watsonx-orchestrate orchestrate.exe env add -n <env-name> --url "<CPD_INSTANCE_URL>"

# activate — CPD requires --username; --skip-version-check avoids a hang on some installs
uvx --from ibm-watsonx-orchestrate orchestrate.exe env activate <env-name> \
  --username <cpd-username> --api-key "<WO_API_KEY>" --skip-version-check
```

Observed gotchas during activation:

- **`env add` without `-n` errors** — `Missing option '--name' / '-n'`. The bare
  positional form in older docs/snippets does not work on ADK 2.11.
- **Activation without `--username` silently hangs** — it backgrounds and never
  activates, and a later `env list` still shows *No active environment set*.
  Adding `--username` activates instantly. CPD prints
  `Support for CPD clusters is currently an early access preview` on success —
  that warning is expected, not an error.
- **Do not pipe the key on stdin** (`printf '%s\n' "$KEY" | ... env activate`).
  It hangs here; use `--api-key`.

Confirm with `env list` — the active env is marked; no marker + the
*No active environment* warning means activation didn't take.

## Smoke test: use `models list`, not `agents list`

On this CPD tenant, immediately after a successful activation:

- `list_models` / `orchestrate models list` returns cleanly ✅ — use this as the
  connectivity smoke test.
- `list_agents` returned `ClientAPIException(status_code=500, "An Unexpected
  Error Occurred.")` — a 500 here is **not** proof the connection is broken; it
  can be a tenant-side issue with an empty/initializing agent catalog.

So: a clean `models list` confirms creds + endpoint + token exchange all work,
even if `agents list` 500s.

## Single-model tenants and the gpt-oss-120b style trap

Some CPD installs expose only one model in `models list` (observed:
`virtual-model/vllm/openai/gpt-oss-120b`, `is_default: true`, sole entry). The
`gpt-oss-120b` style-ignoring gotcha (see `SKILL.md` §7 /
`reference/model_selection.md`) applies to this `vllm/` variant too. With only
one model you cannot switch to a style-respecting model — your options are:

- set `style: customer_care` (the one style `gpt-oss-120b` honors), or
- ask the platform team to enable a style-respecting model
  (`watsonx/meta-llama/llama-3-3-70b-instruct`,
  `watsonx/mistralai/mistral-large-2512`) if the agent needs real delegation.

## Don't commit secrets to the repo

CPD makes this sharper: `.mcp.json` here carries the WO API key plus any MCP
gateway tokens, and it's **not** in most default `.gitignore` files — so it has
been seen committed (even when a failed push left it local-only). The full rule,
the `.gitignore` block, and the history-removal + rotation steps live in
`SKILL.md` → *"Before the first `git commit`"*. Apply it before the first
`git add .`.
