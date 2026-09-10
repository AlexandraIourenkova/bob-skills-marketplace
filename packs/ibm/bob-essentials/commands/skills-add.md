---
description: Install a skill pack from the Bob Skills Marketplace after showing what will be installed and confirming with the user; records it in .bob/skills.lock
argument-hint: <pack>[@version] [--global]
---

Install the marketplace pack `$ARGUMENTS`.

1. Show what will be installed and wait for the user's confirmation:

   ```bash
   uvx bob-skills show $ARGUMENTS
   ```

   If the panel says the vendor is not yet trusted in this project, ask a separate question whether to trust that vendor. Do not continue without a yes.
2. Install, adding `--accept-vendor` only after the user trusted a new vendor:

   ```bash
   uvx bob-skills add $ARGUMENTS
   ```

3. If the installer refuses (vendor not in the list, checksum mismatch, revoked version, a folder in the way), report the message verbatim. Do not retry with `--force` unless the user asks for it after reading the message.
4. On success, list the installed skills, MCP servers, rules, commands and modes from the report. Tell the user to reload the Bob window if a new MCP server does not appear in the MCP panel.
