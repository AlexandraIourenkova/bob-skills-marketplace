# Pack `wxo-talk-with-your-data` — Talk with your data on watsonx Orchestrate

Vendor: `ibm`. Install with `uvx bob-skills add wxo-talk-with-your-data`, or with `/skills-add wxo-talk-with-your-data` inside Bob once bob-essentials is installed.

Start from a spreadsheet and end with an agent people can talk to.

## Before you install

**Importing a tool or an agent replaces objects with the same name in your Orchestrate tenant, and the chart tool uploads chart images built from your data.**

Covered by: The skill and the pack rule name the environment and the objects and ask before each import; charts go to your own COS bucket by default with no silent fallback, and the free public hosting option is described as demo-only, for made-up data.

| Component | Source | What it adds |
|---|---|---|
| `skills/excel-to-wxo-agent` | IBM tech garage, excel-to-wxo (an IBM-internal repository, published here with its owner's consent) | Excel or CSV to a SQLite database bundled inside a watsonx Orchestrate Python tool, agent YAML with the schema baked into the instructions, import through the ADK CLI |
| `skills/wxo-chat-demo-page` | same | Demo page with the embedded watsonx Orchestrate chat: hero, example questions, charts rendered from the agent's answers; served locally and verified end to end |
| MCP server `watsonx-orchestrate-adk` | PyPI `ibm-watsonx-orchestrate-mcp-server` via `uvx` | ADK commands as tools |
| MCP server `watsonx-orchestrate-adk-docs` | `https://developer.watson-orchestrate.ibm.com/mcp` | Current documentation on demand |
| `rules/wxo-data-agent.md` | this pack | ADK environment, encoding, data handling for prototypes |

Planned for 1.1: database sources (Db2, PostgreSQL through connections), an Orchestrate flow that refreshes the data on a schedule, a `/talk-with-data` command.

Installs alongside `wxo-adk`: the MCP servers are identical, so the second install reuses them.

## Differences from the upstream skills

- `scripts/excel_to_sqlite.py`: a literal right-to-left mark inside a comment is written as `U+200F`, so the file carries no hidden characters (policy rule P003). No behaviour change.
- `SKILL.md` descriptions: the Russian trigger phrases are dropped; the marketplace and its site are English-only. Bodies are unchanged.
- Everything else is byte-identical to the source commit in `pack.json`. The chart tool's demo-only upload to public image hosts is kept as upstream ships it and is recorded in `.policy-baseline.json` with the maintainer's reason; the skill itself tells the agent to state the risk and never use it with real data.
