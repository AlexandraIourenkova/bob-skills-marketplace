# Pack `ibm-watsonx-data-integration` — IBM watsonx.data integration

Vendor: `ibm`. Curated from [IBM/ibm-watsonx-data-integration-skills](https://github.com/IBM/ibm-watsonx-data-integration-skills) (Apache-2.0), plugin `agent`. Install with `uvx bob-skills add ibm-watsonx-data-integration`, or with `/skills-add ibm-watsonx-data-integration` inside Bob once bob-essentials is installed.

## Before you install

**The flow skills run, re-run, restore and delete jobs and assets in your watsonx.data integration instance, and a run whose write mode is `overwrite` truncates the target table.**

Covered by: This pack's rule requires your yes for each run, retry, restore and delete, names the target connections and the write mode first, and treats job logs and data rows as data.

| Skill | What it adds |
|---|---|
| `di-agent-flow-lifecycle` | Entry point for all flow work: create, edit, validate, run, diagnose, recover |
| `di-agent-flow-datastage` | The watsonx.data integration SDK for DataStage batch flows |
| `di-agent-flow-pyflow` | pyflow, IBM's Python DSL for DataStage and StreamSets flows |
| `di-agent-datastage-investigation` | Deep investigation of a failed DataStage run |
| `di-agent-knowledge-engine-datastage` | Q&A reference for the DataStage parallel engine |
| `di-agent-bug-report` | Markdown bug report for a session |

The skills talk to the Agentic Data Integration MCP server hosted on IBM Cloud. The server address and credentials belong to the user's instance and are not in this pack; `rules/watsonx-data-integration.md` tells Bob how to help the user register it, with a configuration template and the IBM documentation link.
