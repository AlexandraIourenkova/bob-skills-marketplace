# watsonx Orchestrate ADK rules

These rules apply whenever you work with the watsonx Orchestrate ADK: the `orchestrate` CLI, agent or tool YAML, Python tools, knowledge bases, flows.

## Environment

- Install the ADK in a dedicated virtual environment: `uv venv .venv-wxo && uv pip install --python .venv-wxo ibm-watsonx-orchestrate`. Never add `ibm-watsonx-orchestrate` to a tool's `requirements.txt`; the platform provides it.
- Before importing any YAML that contains non-ASCII text (Hebrew, Cyrillic, accented characters), run `orchestrate settings set-encoding utf-8` once. Without it the ADK corrupts the text on import.
- Run `orchestrate env list` before any import and confirm the active environment with the user when it is not obvious. Never import into an environment the user did not name.

## Documentation first

- Before solving an ADK task, search the documentation with the `wxo-docs` MCP server. ADK YAML fields change between releases; prefer the docs over memory.
- Use the `wxo-adk` MCP server to list existing agents and tools before creating new ones, and to reuse collaborator agents where they exist.

## Deploy order and safety

- Import in dependency order: connections, tools, knowledge bases, collaborator agents, then the top-level agent. `/wxo-deploy` does this.
- Confirm the exact name with the user before removing or overwriting an agent, tool or knowledge base.
- Keep credentials in `.env` and connections; never write API keys into YAML or Python files.
