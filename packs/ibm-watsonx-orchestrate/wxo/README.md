# Pack `wxo` — watsonx Orchestrate

Vendor: `ibm-watsonx-orchestrate`. Install with `uvx bob-skills add wxo` or `/skills-add wxo` inside Bob.

| Component | Source | What it adds |
|---|---|---|
| `skills/solution-architect`, `sop-builder`, `wxo-builder`, `wxo-analyzer`, `telemetry-analyzer`, `agent-instructions-evaluator` | [IBM/ibm-watsonx-orchestrate-adk](https://github.com/IBM/ibm-watsonx-orchestrate-adk/tree/main/skills), tag `2.16.0`, copied verbatim (MIT, see `skills/LICENSE`) | Requirements → SOP → implementation → audit → telemetry → instruction quality |
| MCP server `wxo-adk` | PyPI `ibm-watsonx-orchestrate-mcp-server` via `uvx` | ADK commands as tools: agents, tools, knowledge bases |
| MCP server `wxo-docs` | `https://developer.watson-orchestrate.ibm.com/mcp` | Current documentation without bloating the context |
| `rules/wxo-adk.md` | this pack | Separate venv, UTF-8 encoding before importing non-ASCII YAML, import order |
| `commands/wxo-deploy.md` | this pack | `/wxo-deploy`: import tools and agents in dependency order |
| `custom_modes.yaml` | this pack | Mode `wxo-builder` with a restricted tool set |

## Updating the ADK skills

```bash
python scripts/sync_adk_skills.py --ref <adk-tag>
uv run --project cli bob-skills registry validate --fix
```

Then bump `version` in `pack.json`, open a PR, and tag the merge commit `wxo--v<version>`.
