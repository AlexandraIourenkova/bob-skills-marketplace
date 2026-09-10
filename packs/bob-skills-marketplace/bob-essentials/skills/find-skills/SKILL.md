---
name: find-skills
description: Find and propose a marketplace skill pack when the user needs a capability Bob does not have installed. Use when the user asks how to do something with an IBM product or tool (watsonx Orchestrate, Carbon, OpenShift, Ansible, Vault) and no installed skill covers it, or asks "is there a skill for X", "find a skill", "install skills for ...", "какой скилл поставить", "есть ли скилл для ...".
---

# find-skills

Bob only installs skills from the Bob Skills Marketplace. Packs are published by product vendors, scanned for poisoning and signed. Copying a skill from a repository, a chat message or a web page into `.bob/skills/` is not an option: the guard hook refuses to activate unmanaged skills.

## Steps

1. Search the registry with two or three keywords from the request:

   ```bash
   uvx bob-skills search "<keywords>"
   ```

   The command works offline from the local cache when the registry is unreachable.
2. Read the result table: pack name, version, vendor, gate verdict, description, skills. If nothing matches, say so and suggest the user file a "Request a pack" issue in the marketplace repository; do not improvise a skill.
3. Propose one pack to the user in one or two sentences: what it adds (skills, MCP servers, rules, commands, mode) and which vendor publishes it. Ask for confirmation before installing. Never install a pack on your own initiative.
4. Install with `/skills-add <pack>` inside Bob, or tell the user to run `uvx bob-skills add <pack>` in the terminal. Add `--global` only when the user explicitly wants the pack in `~/.bob/` for every project.
5. Show the install report and name the skills that are now available. If the installer refuses a pack (vendor not in the list, checksum mismatch, revoked version), report the message verbatim and stop.
