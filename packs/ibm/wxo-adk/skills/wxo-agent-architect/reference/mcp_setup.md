<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# MCP server setup & troubleshooting

Load this when the two MCP servers (`watsonx-orchestrate-adk-docs` and
`watsonx-orchestrate-adk`) are not both showing as connected — i.e. `/mcp`
doesn't list them, or the stdio server fails to start. If both are already
`✔ Connected`, you don't need anything here.

## Where the MCP config lives (and where it does NOT)

**MCP servers are NOT configured in `settings.json`.** Pasting an `mcpServers`
block into any `settings.json` is silently ignored — a common cause of "I added
the servers but none register," not even the HTTP one that needs no credentials.
Diagnostic tell: a server that never *appears* in `claude mcp list` means the
file wasn't read as MCP config; a server that appears but is **red** is a
connectivity problem instead.

Three `settings.json` files get confused here, and none holds MCP servers:
`.vscode/settings.json` (VS Code), `.claude/settings.json` (Claude Code
project), `.claude/settings.local.json` (local overrides).

MCP servers live in:

| Scope | File | Hand-edit? |
|-------|------|-----------|
| **Project** (shared, committed) | `<project-root>/.mcp.json` | ✅ yes — this is the hand-edit target |
| **User** (global) | `~/.claude.json` (a *file* in home, top-level `mcpServers`) | ⚠️ avoid — large machine-managed file; use the CLI |
| **Local** (this dir, private) | `~/.claude.json`, under `projects["<path>"].mcpServers` | ⚠️ nested/fragile — use the CLI |

Dot-vs-slash trap: the global config is the **file** `~/.claude.json`, NOT
`~/.claude/mcp.json` (that path is never read), and the `.claude/` *directory*
holds `settings.json`, never MCP servers.

**Rule of thumb: hand-edit project scope (`.mcp.json` at the repo root); use
`claude mcp add -s user` for global.** The CLI edits `~/.claude.json` correctly;
a stray comma in a hand edit can corrupt the whole file.

### Project `.mcp.json` — exact form

A standalone file at the project root (sibling of `.git/`, `.claude/`), nothing
merged into it. Filename is literally `.mcp.json` — leading dot, no `.claude/`
prefix, not `mcp.json`:

```json
{
  "mcpServers": {
    "watsonx-orchestrate-adk-docs": { "type": "http", "url": "https://developer.watson-orchestrate.ibm.com/mcp" },
    "watsonx-orchestrate-adk": { "type": "stdio", "command": "uvx", "args": ["ibm-watsonx-orchestrate-mcp-server"], "env": {} }
  }
}
```

After saving, restart Claude and **approve the one-time trust prompt** — project
servers stay inactive until approved (or set `enableAllProjectMcpServers: true`
in `.claude/settings.json`, a valid settings.json key that *references*
`.mcp.json` rather than defining servers). If a hand edit doesn't take, validate
the JSON — one trailing comma, a duplicate key, or a UTF-8 BOM makes Claude drop
the whole file:
`python -c "import json; json.load(open('.mcp.json')); print('valid')"`.
Never pin real secrets in `.mcp.json` — it's committed.

## Adding the MCP servers (if `/mcp` doesn't list them)

If the user says the servers are "installed" but `/mcp` doesn't show them,
they likely need to be (re)added. The two servers use different transports:

```bash
# 1. Docs server (HTTP) — documentation/syntax reference
claude mcp add --transport http watsonx-orchestrate-adk-docs \
  https://developer.watson-orchestrate.ibm.com/mcp

# 2. Platform-ops server (stdio, runs via uvx) — list/import/publish
claude mcp add watsonx-orchestrate-adk \
  -- uvx ibm-watsonx-orchestrate-mcp-server
```

Then restart Claude Code (or `/mcp` → reconnect) and confirm with
`claude mcp list` — both should report `✔ Connected`.

### Local vs. global (user) install — the most common gotcha

`claude mcp add` defaults to **local** scope: the server is bound to the
directory it was added from. `/mcp` only surfaces servers in scope for the
current working directory (plus user scope), so a server added locally in
one folder is invisible from every other project — it looks "installed but
missing." To make both servers available in **every** project, add them at
**user (global)** scope with `-s user`:

```bash
claude mcp add -s user --transport http watsonx-orchestrate-adk-docs \
  https://developer.watson-orchestrate.ibm.com/mcp
claude mcp add -s user watsonx-orchestrate-adk \
  -- uvx ibm-watsonx-orchestrate-mcp-server
```

| Scope | Flag | Visible from | Use when |
|-------|------|-------------|----------|
| Local (default) | _(none)_ | only the directory it was added in | one-off, project-specific |
| User / global | `-s user` | every project for this user | normal case — recommended |
| Project | `-s project` | anyone using the repo (`.mcp.json`, requires trust prompt) | shared team config |

### Triage when they still don't appear (`claude mcp list` from the project dir)

- **Not listed at all** → wrong scope/directory. Re-add with `-s user` (above).
- **Listed but failing/timeout on the stdio server** → `uvx` not on PATH.
  It ships with `uv`; check `which uvx` and install if missing
  (`curl -LsSf https://astral.sh/uv/install.sh | sh`). The HTTP docs server
  has no such dependency — it only needs network reachability to
  `developer.watson-orchestrate.ibm.com` (check proxy/firewall).
- **Edited `.claude.json` by hand** → restart Claude Code; config is read at
  startup.
- **Added at project scope** → approve the one-time trust prompt before it
  activates.
- **Connected, but every platform tool returns `No active environment found`** →
  the stdio server reads the CLI's *activated* environment, not the `WO_*` vars
  in `.mcp.json`'s `env` block. Run a successful `orchestrate env activate`
  first. On self-hosted/CPD this needs extra flags (`--username`,
  `--skip-version-check`) — see `reference/self_hosted_cpd.md`.

## Verify the servers work standalone (outside Claude)

Run these on the user's machine to separate "the server itself is broken" from
"Claude's config/env is wrong."

**Prereq:** `uv --version` and `command -v uvx` (`where uvx` on Windows). No
`uvx` → install `uv` (`winget install astral-sh.uv`, or
`curl -LsSf https://astral.sh/uv/install.sh | sh`) and retry.

**Credential-free stdio smoke test** — confirms the server installs and speaks
MCP without any `WO_*` credentials. The MCP `initialize` handshake needs no
credentials, so a healthy server completes it on its own.

Have your coding agent perform this check (it can write a throwaway stdio MCP
client to do so — no script ships with this skill): launch the server command
over stdio and run the JSON-RPC handshake — send `initialize`, then the
`initialized` notification, then `tools/list` — against:
```
uvx ibm-watsonx-orchestrate-mcp-server
```
A healthy server returns an `initialize` result and a non-empty `tools/list`. If
the handshake succeeds here while Claude still fails, the problem is Claude's
config/env, not the server. (Running `uvx ibm-watsonx-orchestrate-mcp-server`
bare will appear to **hang** — that's correct; a stdio server waits silently on
stdin. An immediate traceback is the real failure.)

**HTTP docs server reachability** — no file needed; use `curl.exe` on Windows so
PowerShell doesn't hijack `curl`:
```
curl -sS -m 20 -X POST https://developer.watson-orchestrate.ibm.com/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0.0.1"}}}'
```
Expected: `200` and an `event: message` / `data: {...}` line. Any JSON-RPC
response = reachable; a hang or TLS error = proxy/firewall blocking the IBM
endpoint.

**GUI alternative — official MCP Inspector:**
`npx @modelcontextprotocol/inspector uvx ibm-watsonx-orchestrate-mcp-server`
opens a browser UI to watch the handshake, list tools, and call one.

| Result | Means |
|--------|-------|
| smoke test PASS but Claude fails | server is fine — fix Claude config/env (`.mcp.json` location, scope, or the Windows `.env` issue) |
| smoke test FAIL / traceback | install problem — retry with `uvx ... --refresh`, check `uv` |
| curl to docs server hangs / TLS error | proxy/firewall to `developer.watson-orchestrate.ibm.com` |

## Restarting to apply changes (including VS Code)

Env-var and config changes are read at process start, so a `/mcp` reload is not
always enough — match the action to what changed:

- **New conversation** (`/clear` or New chat) — does NOT reconnect MCP or
  re-read env.
- **Reconnect MCP** (picks up `.mcp.json`/config edits) — `/mcp` → reconnect,
  or toggle the panel.
- **Full restart** (required for env-var changes) — **VS Code:** fully quit the
  app (`File → Exit`, all windows), not just the Claude panel or a window
  reload; the extension host can otherwise keep a stale environment. If new
  `WO_*` vars still don't appear after a clean relaunch, sign out / reboot — or
  sidestep restarts entirely with `claude mcp add -e ...` (next section).

## Windows: `.env` does NOT auto-load (common MCP startup failure)

**Symptom:** on Windows the `watsonx-orchestrate-adk` (stdio) server fails to
connect even though `.env` exists and the same setup works on a colleague's
Mac.

**Why.** `.env` is just a text file — nothing reads it automatically. An MCP
server is a child process Claude Code spawns; it inherits (a) Claude Code's own
OS process environment and (b) the server's `env` block in config. It does
**not** read your project `.env`. On Mac/Linux the skill's
`set -a && source .env && set +a` step exports the vars into the launching
shell, and the MCP child inherits them — so it "just works" only because you
sourced them into the shell Claude was started from. On Windows:

- there is no `source .env` equivalent in cmd/PowerShell, so the POSIX step
  in SKILL.md's Local environment setup never runs;
- Claude Code is often launched from a **GUI shortcut**, so there is no
  launching shell to inherit from at all;
- the native way to give a GUI app env vars is to set them **persistently**,
  and those only apply to processes started afterward — so a `/mcp` reload is
  not enough; a **full close-and-reopen** is mandatory.

(The `watsonx-orchestrate-adk-docs` HTTP server needs none of this — it has no
env dependency. If *it* fails, the cause is network/proxy, not env vars.)

### Fix — three options, most robust first

1. **Pin the vars in the MCP server config (recommended — fully portable).**
   Bypasses `.env`, `setx`, shell inheritance, and restart timing; behaves
   identically on every OS. You can pin **globally** (every project) or just
   for the **project you're working in** — your choice via the `-s` scope flag:

   ```
   # Global — available in every project for this user
   claude mcp add -s user watsonx-orchestrate-adk ^
     -e WO_API_KEY=<key> -e WO_INSTANCE=<url> ^
     -- uvx ibm-watsonx-orchestrate-mcp-server

   # Per-project — only when Claude is launched from this directory
   # (-s local is the default, so the flag can be omitted entirely)
   claude mcp add watsonx-orchestrate-adk ^
     -e WO_API_KEY=<key> -e WO_INSTANCE=<url> ^
     -- uvx ibm-watsonx-orchestrate-mcp-server
   ```

   Pick **global** for a single tenant you use everywhere; pick **per-project**
   when different project directories target different WXO tenants — each gets
   its own pinned `WO_API_KEY`/`WO_INSTANCE` with no global var to swap.

   | Scope flag | Stored in | Visible from |
   |-----------|-----------|-------------|
   | `-s user` | `.claude.json` (top-level) | every project |
   | `-s local` *(default)* | `.claude.json` (keyed to project path) | only that directory |
   | `-s project` | `.mcp.json` **in the repo** | anyone who trusts the repo |

   Trade-off: with `-s user`/`-s local` the key is stored in plaintext in the
   user's `.claude.json` — acceptable for most dev setups; flag it if the
   customer's policy forbids secrets at rest in config. **Do NOT use `-s project`
   with `-e <secret>`:** that writes the credential into `.mcp.json`, which is
   committed to the repo and leaks the secret to everyone with access.

2. **Persistent Windows user env vars + full restart.** Keeps secrets out of
   `.claude.json`. Run in a terminal (NOT inside Claude):
   ```
   setx WO_API_KEY "<key>"
   setx WO_INSTANCE "<url>"
   ```
   Caveats: `setx` silently **truncates values over 1024 chars**; the current
   terminal does **not** see the new value (only newly launched processes do);
   you must fully close and reopen Claude Code, not `/mcp` reload. The
   GUI equivalent is System Properties → Environment Variables (easier to edit
   or delete later).

3. **Per-session (PowerShell), then launch Claude from that shell:**
   ```
   $env:WO_API_KEY = "<key>"; $env:WO_INSTANCE = "<url>"; claude
   ```
   No persistence — applies only to that session and only if Claude is started
   from it.

**Also on Windows:** install `uv`/`uvx` (needed by the stdio server) with
`winget install astral-sh.uv`, then verify with `uv --version`. A missing
`uvx` looks identical to an env problem — the server simply never starts.
