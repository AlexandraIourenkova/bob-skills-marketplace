---
description: Install a skill pack from the Bob Skills Marketplace (skills, MCP servers, rules, commands, mode) after verifying vendor and checksums, and record it in .bob/skills.lock
argument-hint: <pack>[@version] [--global]
---

Install the marketplace pack `$ARGUMENTS`.

1. Run the installer and show its complete output:

   ```bash
   uvx bob-skills add $ARGUMENTS
   ```

2. If it refuses the pack (vendor not in the list, checksum mismatch, revoked version, unmanaged folder in the way), report the message verbatim. Do not retry with `--force` unless the user asks for it after reading the message.
3. On success, list the installed skills, MCP servers, rules, commands and modes from the report. Tell the user to reload the Bob window if a new MCP server does not appear in the MCP panel.
