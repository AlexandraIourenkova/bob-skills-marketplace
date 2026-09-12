---
description: Import a watsonx Orchestrate project (connections, tools, knowledge bases, agents) into the active ADK environment in dependency order
argument-hint: [project-dir] [--env <name>]
---

Deploy the watsonx Orchestrate project in `$ARGUMENTS` (default: the current directory) with the ADK CLI.

1. **Preflight.** Run `orchestrate --version` and `orchestrate env list`. If `--env <name>` was given, run `orchestrate env activate <name>`. If the active environment is not the one the user expects, stop and ask.
2. **Encoding.** If any YAML in the project contains non-ASCII text, run `orchestrate settings set-encoding utf-8` first.
3. **Discover.** List the project files: `connections/*.yaml`, `tools/**/*.py` with their `requirements.txt`, `knowledge_bases/*.yaml`, `agents/*.yaml`. Read each agent YAML to find `collaborators` and `tools` so the import order below is correct.
4. **Import in order.** Show the full plan first: each command, the active environment and the objects it creates or replaces (imports overwrite objects with the same name). Then show each command again and run it only after the user says yes to it:
   - connections: `orchestrate connections import -f <file>`
   - Python tools: `orchestrate tools import -k python -f <file> -r <requirements.txt>`
   - knowledge bases: `orchestrate knowledge-bases import -f <file>`
   - collaborator agents, then top-level agents: `orchestrate agents import -f <file>`
5. **Verify.** Run `orchestrate agents list` and `orchestrate tools list`. Report what was imported, what already existed, and any failure with the exact error text.

Never run `remove` or `delete` commands as part of this command. If an import fails on a name conflict, report it and let the user decide.
