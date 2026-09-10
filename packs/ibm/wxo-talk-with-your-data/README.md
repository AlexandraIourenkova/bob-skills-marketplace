# Pack `wxo-talk-with-your-data` — Talk with your data on watsonx Orchestrate

Vendor: `ibm`. Install with `uvx bob-skills add wxo-talk-with-your-data` or `/skills-add wxo-talk-with-your-data` inside Bob.

Start from a spreadsheet and end with an agent people can talk to.

| Component | Source | What it adds |
|---|---|---|
| `skills/excel-to-wxo-agent` | IBM tech garage, [excel-to-wxo](https://github.ibm.com/tech-garage-spgi/excel-to-wxo) | Excel or CSV to a SQLite database bundled inside a watsonx Orchestrate Python tool, agent YAML with the schema baked into the instructions, import through the ADK CLI |
| `skills/wxo-chat-demo-page` | same | Demo page with the embedded watsonx Orchestrate chat: hero, example questions, charts rendered from the agent's answers; served locally and verified end to end |
| MCP server `wxo-adk` | PyPI `ibm-watsonx-orchestrate-mcp-server` via `uvx` | ADK commands as tools |
| MCP server `wxo-docs` | `https://developer.watson-orchestrate.ibm.com/mcp` | Current documentation on demand |
| `rules/wxo-data-agent.md` | this pack | ADK environment, encoding, data handling for prototypes |

Planned for 1.1: database sources (Db2, PostgreSQL through connections), an Orchestrate flow that refreshes the data on a schedule, a `/talk-with-data` command.

Installs alongside `wxo-adk`: the MCP servers are identical, so the second install reuses them.

## Differences from the upstream skills

The gate found three things in the upstream copy; the marketplace edition changes them and the changes are worth upstreaming:

- `assets/visualization_tool.py`: upload modes `free` and `cos_fallback` (litterbox.catbox.moe, freeimage.host, with an embedded API key) are removed; `UPLOAD_MODE` is fixed to `cos`. Chart images carry the customer's numbers and must not leave IBM-controlled storage. `SKILL.md` and `references/visualization.md` say so.
- `scripts/excel_to_sqlite.py`: a literal right-to-left mark in a comment is written as `U+200F`, so the file has no hidden characters.
- Everything else is byte-identical to the source commit in `pack.json`. Accepted findings (placeholder hostnames, a mention of `.env`, an instruction that tells the agent not to send users to external renderers) are listed in `.policy-baseline.json` with reasons.
