<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# CLI vs. credentialed MCP server — which interface for what

There are two ways to make watsonx Orchestrate *do things*: the `orchestrate`
**CLI**, and the credentialed **`watsonx-orchestrate-adk`** (platform-ops) MCP
server. They are NOT equivalent, and mixing them silently is how failures hide.
This file is the opinionated policy; `SKILL.md` Step 0 is the short version.

> The credential-free **`watsonx-orchestrate-adk-docs`** server is a separate
> thing and is always worth it — it's pure reference with no setup cost. Keep it.
> This page is only about the **credentialed** platform-ops server.

## Policy

**Default lane: `orchestrate` CLI for every action; docs MCP for reference.**
Use the credentialed `watsonx-orchestrate-adk` MCP server only when a specific
scenario below calls for it — it is **optional**, never a hard requirement.

| Task | Default | Notes |
|------|---------|-------|
| Env activation | **CLI** | `orchestrate env activate` — the MCP server *reads* this; it can't replace it |
| Discovery / list | **CLI** | `orchestrate agents/tools/connections/toolkits list` |
| Import / deploy agents, tools, KBs | **CLI** | `orchestrate ... import -f ...` |
| Connections & toolkit lifecycle | **CLI** | remove/re-import to force a fresh container |
| Promote to production | **CLI / UI** | per current docs |
| Reference / schema lookups | **docs MCP** | `watsonx-orchestrate-adk-docs` |
| Hands-off autonomy (no shell) | credentialed MCP | see "When it earns its keep" |

## Why the CLI is the default

The single most important fact: **the credentialed MCP server authenticates from
the CLI's activated environment on disk.** It does not hold its own credentials
(anything in `.mcp.json`'s `env` block is ignored for auth and only leaks). So
you must get the CLI working *first* — which means the MCP server can never be
*simpler* than the CLI. It is, structurally, **the CLI plus a second process, a
second install, and a second bundled `ibm_watsonx_orchestrate_clients` version to
keep in sync.**

Against that overhead, its unique benefit — structured, no-shell tool calls — is
marginal here: a capable coding agent writes and parses `orchestrate` commands
reliably. In an interactive, human-at-a-terminal setting the trade rarely pays.

## The two failure modes the CLI does not have

Observed on a real CPD + Windows customer engagement (July 2026):

1. **Filesystem sandbox.** The MCP file tools (`import_agent(path:)`,
   `import_tool(path:)`) refuse to read a file unless `WXO_MCP_WORKING_DIRECTORY`
   is set on the server — otherwise: *"No working directory defined. Access to
   file system is blocked."* The CLI reads from the shell's cwd freely.
   - Fix if you insist on MCP file import:
     `claude mcp add -s user watsonx-orchestrate-adk -e WXO_MCP_WORKING_DIRECTORY=<project-dir> -- uvx ibm-watsonx-orchestrate-mcp-server`
   - Or just use `orchestrate ... import -f ...` and skip it entirely.

2. **Separate-install version skew → opaque `500`s.** The MCP server ships as its
   own package (`ibm-watsonx-orchestrate-mcp-server`, run via `uvx`) with its own
   bundled client library. When that drifts from the CLI's version, its requests
   malform and the platform returns a generic
   `ClientAPIException(status_code=500, {"detail":"An Unexpected Error Occurred."})`
   — while the **same operation on the CLI returns 200.** The early tell is a
   `ModuleNotFoundError: No module named 'ibm_watsonx_orchestrate_clients.cpd'`
   from the uvx tool's Python.
   - Diagnose: run the same op on the CLI. **CLI 200 + MCP 500 = version skew,
     not a platform outage** (do not escalate to the vendor for this).
   - Fix: `uv tool upgrade ibm-watsonx-orchestrate` and the `-mcp-server` package
     so the MCP server's client library matches the CLI, then fully restart the
     editor and reconnect MCP (the running server holds old code until restarted).

## When the credentialed MCP server *does* earn its keep

All three are hands-off / no-human cases:

- **Headless automation** — cron, CI, a cloud agent with no interactive shell.
- **Locked-down hosts** where the agent genuinely has no usable shell but can
  speak MCP. (Note: on the CPD/Windows engagement the *shell* was the reliable
  surface and the MCP server was the broken one — verify the assumption before
  betting on it.)
- **Hands-off demos** where the agent drives WXO end-to-end in front of an
  audience with no terminal in view.

If you adopt it for one of these, **pin the MCP server's version to the CLI** and
**set `WXO_MCP_WORKING_DIRECTORY`** up front, and expect the version-skew `500`
otherwise.

## The rule that prevents repeat pain

**Never silently pivot from MCP to CLI.** When a platform op fails through the MCP
server and you fall back to the CLI, that's correct — but *record the MCP failure*
(server version, exact error). A silent pivot makes the build succeed while the
MCP bug drops into the ether, where it waits to ambush the next user who leans on
the MCP path. The July 2026 engagement was, in part, a bug an earlier project had
quietly stepped around this way.
