---
name: bob-doctor
description: Check the Bob setup of this project and of ~/.bob and fix problems together with the user - guard hook missing, skills modified after install or unmanaged, skills Bob ignores, MCP servers with secrets in the config, unpinned versions, plain HTTP, TLS verification off, listeners on all interfaces, write tools approved in advance or telemetry on, and custom modes with unknown tool groups. Use when the user says "check my Bob setup", "doctor", "why is my skill or MCP server not working", "is my mcp.json safe", "проверь настройки Bob", or after installing packs or adding MCP servers by hand.
---

# bob-doctor

## Steps

1. Run the check. It only reads files:

   ```bash
   uvx bob-skills doctor
   ```

   Add `--json` to read the items programmatically.
2. Explain the problems first, then the warnings, grouped by area (hooks, lock, skills, mcp, modes): what is wrong, why it matters, and the fix the report suggests.
3. Propose fixes one at a time and apply each only after the user agrees to it:
   - **MCP servers** (`.bob/mcp.json`, `~/.bob/mcp.json`): pin the version; replace a secret in the file with a reference to an environment variable, ask the user to set that variable and to rotate the secret, because it was stored in plain text (never print, copy or move the value yourself); switch `http://` to `https://`; remove flags that turn TLS verification or authentication off and bindings to every interface; take write tools out of `alwaysAllow`; add the telemetry opt-out the report names.
   - **Lock**: a skill modified after install goes back with `uvx bob-skills add <pack> --force`, after the user confirms that local edits may be lost; a revoked version with `uvx bob-skills update`.
   - **Unmanaged skills**: audit them with the skill-audit skill, then install the pack they come from or trust them.
   - **Skills Bob ignores**: add the missing description or align the name, with the skill-creator skill.
   - **Modes**: rename tool groups Bob does not know to the documented ones (terminal commands are `execute`), restrict `edit` with `fileRegex`.
4. Hooks are part of the user's own Bob settings. Show the hook snippet from the marketplace documentation (docs/bob-integration.md) and let the user add it; this skill does not edit Bob's settings files.
5. Run `uvx bob-skills doctor` again and report what is left.
