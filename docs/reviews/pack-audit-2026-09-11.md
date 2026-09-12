# Pack audit for the three holes, 2026-09-11

Every skill, rule, command, mode and MCP entry in the 14 packs was read for the three holes from the [security MCP review](ibm-security-mcp-servers.md): write or admin actions without the user's yes (H1), outside content that can steer actions (H2), weak transport or exposure (H3). The automated part of this check now runs in the gate for every pack ([security-gate.md](../security-gate.md)); this page records what the manual read found and where each finding stands.

## Fixed in our packs

| Pack | What changed |
|---|---|
| bob-essentials 1.2.0 | New `security-defaults` rule for every task (content is data, the user's yes before each external write, security settings stay on). Trusting a local skill is the user's own step; `trust` lints first. Every `update --apply` needs a yes. `add` and `doctor` warn when the rule is missing |
| wxo-adk 1.1.1 | ADK MCP server pinned with its SDK (2.16.1) and declared read-write: the server has 64 tools and no read-only mode, so the rule and the mode require a yes for every write call. Imports, removes, promotions and `compile_deploy` need a yes each; `/wxo-deploy` confirms per import. Traces and evaluated instructions are data. Developer Edition start warns about its open ports |
| wxo-talk-with-your-data 1.1.0 | Unused ADK MCP server removed. Chart images go to the customer's COS bucket by default, with no silent fallback to public hosts. Demo page served on 127.0.0.1 from a folder that holds only the page. Confirmation before every import. Spreadsheet values fenced as data in the agent prompt. DOM injection in the chart canvas closed |
| ibm-watsonx-data-integration 1.0.1 | The rule asks for a yes per run, retry, restore and delete, names the write mode, keeps the IAM token out of the project config, and treats logs and data rows as data |
| office-docs 1.0.1 | Document text, comments, notes and metadata are data |
| presentations (unreleased) | Material the user brings is data; speaker notes no longer re-parsed as HTML in the HTML deck |

## Open in vendor skills

We cannot edit vendor text. Each gap below is covered on the user's machine by the `security-defaults` rule, which bob-essentials installs and `add` and `doctor` recommend; script lines the linter catches carry a reviewed baseline reason.

| Pack | Main gaps | Class |
|---|---|---|
| anthropic-dev-kit | mcp-builder's evaluation harness calls every tool, write tools included, against live services and feeds results back; its HTTP server example listens on every interface without auth | H1, H2, H3 |
| openai-dev-tools | gh-fix-ci reads logs of fork pull requests, whose authors control them; jupyter-notebook runs notebooks top to bottom; cli-creator installs on PATH | H1, H2 |
| openai-security | security-best-practices follows instructions in the project's own docs and downplays missing TLS | H2, H3 |
| google-cloud-data | `bq rm -f`, DDL and DML, billable AI functions and model training without a yes; table rows used as prompts; gcloud proceeds unless a command is on a denylist | H1, H2 |
| hashicorp-terraform | terraform-test applies real resources by default; search-import plans and applies; refactor-module moves state | H1 |
| microsoft-azure-ops | VM run-command and password resets, AKS exec and privileged debug pods, capacity reservations that bill immediately, compliance fixes in loops, Key Vault secret values in the transcript | H1, H2, H3 |
| microsoft-foundry | deletes, deployments, fine-tuning jobs and role assignments without a yes; several "do not ask" overrides; traces and GitHub issues drive runs; local servers on every interface; secrets collected through chat | H1, H2, H3 |
| confluent-kafka | cdc-tableflow and flink-udf delete environments and connectors; kafka-streams runs against Confluent Cloud whenever credentials exist; compose files publish broker and REST ports on every interface; topic messages are read without a data clause | H1, H2, H3 |
| wxo-adk (IBM ADK skills) | mcp_setup.md suggests storing the API key in an MCP config and auto-enabling project MCP servers; the ADK sends the CPD token with TLS verification off | H1, H3 |

## Report upstream

anthropics/skills (mcp-builder, webapp-testing), openai/skills (gh-fix-ci, security-best-practices), google/skills (bigquery-*), hashicorp/agent-skills (terraform-test, terraform-search-import), microsoft/skills (azure-diagnostics, azure-compute, microsoft-foundry), confluentinc/agent-skills (cdc-tableflow, kafka-streams, compose files), IBM/ibm-watsonx-orchestrate-adk (mcp_setup.md, CPD activation with TLS off, an MCP server with no read-only mode).
