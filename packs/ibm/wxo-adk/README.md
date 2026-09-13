# Pack `wxo-adk` — watsonx Orchestrate ADK

Vendor: `ibm`. Curated by the marketplace team from the official ADK repository. Install with `uvx bob-skills add wxo-adk`, or with `/skills-add wxo-adk` inside Bob once bob-essentials is installed.

## Before you install

**The ADK MCP server has no read-only mode: its tools create, import, remove, set connection credentials and chat with agents in the active tenant, and the ADK skills deploy agents and promote them to live.**

Covered by: This pack's rule and the wxo-builder mode require your yes for every write call, import, remove and promotion; deploys go through `/wxo-deploy`, which shows the plan and the environment first. `mcpAccess` in pack.json records the access level of both servers.

| Component | Source | What it adds |
|---|---|---|
| `skills/solution-architect`, `sop-builder`, `wxo-builder`, `wxo-analyzer`, `telemetry-analyzer`, `agent-instructions-evaluator` | [IBM/ibm-watsonx-orchestrate-adk](https://github.com/IBM/ibm-watsonx-orchestrate-adk/tree/main/skills), tag `2.16.0`, copied verbatim (MIT, see `skills/LICENSE`) | Requirements → SOP → implementation → audit → telemetry → instruction quality |
| MCP server `watsonx-orchestrate-adk` | PyPI `ibm-watsonx-orchestrate-mcp-server` 2.16.1 with `ibm-watsonx-orchestrate` 2.16.1, via `uvx` | ADK commands as tools: agents, tools, knowledge bases. Read-write with no read-only mode: every write call needs the user's yes (see `mcpAccess` in `pack.json`) |
| MCP server `watsonx-orchestrate-adk-docs` | `https://developer.watson-orchestrate.ibm.com/mcp` | Current documentation without bloating the context |
| `rules/wxo-adk.md` | this pack | Separate venv, UTF-8 encoding before importing non-ASCII YAML, import order, the user's yes before every import, remove or promotion, traces and evaluated instructions treated as data |
| `commands/wxo-deploy.md` | this pack | `/wxo-deploy`: import tools and agents in dependency order |
| `custom_modes.yaml` | this pack | Mode `wxo-builder`: read, edit, terminal commands and MCP, with instructions to confirm every tenant change |

## Updating the ADK skills

```bash
python scripts/sync_adk_skills.py --ref <adk-tag>
uv run --project cli bob-skills registry validate --fix
```

Then bump `version` in `pack.json`, open a PR, and tag the merge commit `wxo-adk--v<version>`.
