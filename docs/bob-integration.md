# Bob integration

## Hooks

Add to `.bob/settings.json` (project) or the user settings. `uvx bob-skills guard` reads the hook payload from stdin and exits 2 to block; `check --brief` prints one status line at session start and never fails.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "^use_skill$",
        "hooks": [
          { "type": "command", "command": "uvx bob-skills guard", "timeout": 5 }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "uvx bob-skills check --brief" }
        ]
      }
    ]
  }
}
```

The `bob-skills` command comes from a one-time `uv tool install "git+https://github.ibm.com/Maria-Startseva/bob-skills-marketplace.git#subdirectory=cli"`; it puts `bob-skills` on the PATH that Bob's hooks use. From a checkout without installing: `uv run --project /path/to/bob-skills-marketplace/cli bob-skills guard`.

For an organisation-wide rule, put the same `PreToolUse` entry in an **EnforcedHooks** policy (Bob 2.1.0+) with `uvx bob-skills guard --no-local`, so users cannot switch the guard off and only marketplace packs are activated.

## Verify on day one

The hook payload shape differs between Bob 2.0.2 (`tool_name`, `tool_input`) and the documentation (`tool`, `input`). The guard reads both, and looks for the skill name under `skill`, `skill_name`, `name`, `id` or a `path` ending in `SKILL.md`. What must be confirmed against a real Bob: that the `use_skill` payload carries the skill name at all.

- If it does: nothing to change.
- If it does not: the guard allows and prints a warning (use `--strict` to refuse instead). Fallback: a `SessionStart` hook that quarantines folders in `.bob/skills/` which are not in the lock before Bob reads them, plus a rule in `.bob/rules/` that forbids using skills outside the lock.

Test the payload by pointing the hook at a script that dumps stdin to a file, then activating any skill.

## Slash command inside Bob

The `bob-essentials` pack ships `.bob/commands/skills-add.md`. Users type `/skills-add wxo-adk`; Bob runs the installer through `execute_command` and shows the report. The same command works non-interactively for CI:

```bash
bob run "/skills-add wxo-adk"
```

## What the installer touches

| Pack component | Project scope (`uvx bob-skills add`) | User scope (`--global`) |
|---|---|---|
| skills | `.bob/skills/<skill>/` | `~/.bob/skills/<skill>/` |
| MCP servers | `.bob/mcp.json` → `mcpServers` | `~/.bob/mcp.json` → `mcpServers` |
| rules | `.bob/rules/<file>` | `~/.bob/rules/<file>` |
| commands | `.bob/commands/<file>` | `~/.bob/commands/<file>` |
| modes | `.bob/custom_modes.yaml` → `customModes` by slug | `~/.bob/settings/custom_modes.yaml` (Settings → Modes → Edit Global Modes) |
| lock | `.bob/skills.lock` | `~/.bob/skills.lock` |

`uvx bob-skills remove <pack>` reverses all of it, including the MCP entries and modes, using the lock as the record of ownership.

## The ADK MCP server and unmanaged skills

The watsonx Orchestrate MCP server can copy skills into `.bob/skills/` on its own. The guard treats those as unmanaged and refuses them; the `guard` skill explains to the user how to install the `wxo-adk` pack instead, or `uvx bob-skills trust <skill>` for a genuinely local skill.

## Checking the setup

`uvx bob-skills doctor` reads `.bob/` and `~/.bob/` and reports, without changing a file: a missing guard or SessionStart hook, skills modified after install or not in the lock, skills Bob ignores, risky MCP server entries (the same M001–M007 checks the registry applies to packs) and custom modes with tool groups Bob does not document. Earlier clients wrote global MCP servers to `~/.bob/mcp_settings.json` and global modes to `~/.bob/custom_modes.yaml`, where Bob does not read them; `doctor` points out leftovers there. The bob-doctor skill in bob-essentials explains the report and applies fixes one at a time after the user agrees.
