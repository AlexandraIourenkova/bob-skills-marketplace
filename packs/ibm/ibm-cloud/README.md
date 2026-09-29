# Pack `ibm-cloud` — IBM Cloud

Vendor: `ibm` (marketplace team). Original skills written for this marketplace, Apache-2.0. Install with `uvx bob-skills add ibm-cloud`, or with `/skills-add ibm-cloud` inside Bob once bob-essentials is installed.

What an IBM Cloud account holds, what it costs, and why a VPC server, a cluster or a Code Engine app does not work. Version 1.0.0 only reads: every fix is shown as a command and runs after you say yes.

## Before you install

**The skills run the ibmcloud CLI in the session you opened, which carries every right your account gives you. A command outside the pack's read-only set could change or delete resources.**

Covered by: The pack's scripts only list and read. The `ibm-cloud` rule makes every changing command wait for your yes to that exact command, and `cloud-ops` mode writes only under `ibmcloud-reports/`. For the strictest setup, log in with an access group or service ID that has Viewer roles only.

**Resource names, tags, event messages and application logs come from the account and can carry text aimed at the agent.**

Covered by: The rule and every skill treat them as data: they are quoted to you, never followed.

## Contents

| Component | What it does |
|---|---|
| `skills/ibmcloud-setup` | CLI version, plug-ins, session and target; federated login with `--sso` typed by you, or an API key from `IBMCLOUD_API_KEY` |
| `skills/ibmcloud-inventory` | Every resource instance with service, group, region, state and tags; CSV and JSON; untagged, inactive, default-group and invisible-group findings |
| `skills/ibmcloud-diagnose` | VPC reachability through floating IPs, gateways, security groups and stateless ACLs; cluster health for Kubernetes Service and OpenShift; Code Engine readiness with events, hints and the log tail; permission errors |
| `skills/ibmcloud-cost` | Cost per service, group and instance, month against month, top spenders, instances billed with zero usage; falls back to the reports your role allows |
| `rules/ibm-cloud.md` | The session is yours, reading runs and changing asks, TLS and tracing stay safe, account content is data |
| `commands/ibmcloud-report.md` | `/ibmcloud-report [group]`: setup, inventory and cost in one read-only pass |
| `custom_modes.yaml` | `cloud-ops` mode: read, execute, skills, and edits only under `ibmcloud-reports/` |

## Requirements

- IBM Cloud CLI 2.x (built and checked with 2.43.0) and, for the diagnose checks, the plug-ins `vpc-infrastructure`, `container-service` and `code-engine`. `ibmcloud-setup` names what is missing.
- Python 3.9 or later; the scripts use the standard library only.
- A session you open yourself: `ibmcloud login --sso` for a federated account, or `ibmcloud login` with the key in `IBMCLOUD_API_KEY`.

## How it was checked

The scripts run against the real CLI for everything that works without a session (version, plug-ins, target). Their parsing and every check are tested on recorded responses in `cli/tests/test_ibm_cloud_pack.py`: the plug-in list and the logged-out target are real CLI output, the rest follow the documented API shapes of Resource Controller, Global Search, VPC, Kubernetes Service (v1 and v2), Code Engine (Knative and v2) and Usage Reports. A run against a live federated account comes next; whatever it finds ships as 1.0.1.

## Planned

- 1.1.0: `ibmcloud-access-review` (access groups, policies, service IDs, key age; findings as facts) and `ibmcloud-code-engine` (build and deploy with a yes for every change).
- 1.2.0: `ibmcloud-roks` (cluster inventory, versions and upgrade plan) and `ibmcloud-terraform` on the Terraform IBM Modules MCP server and the HashiCorp Terraform MCP server, both read-only.
- The MCP server built into the CLI (`ibmcloud --mcp-transport stdio`, experimental in 2.43) is read-only by default and takes an allow-list of commands; it is a candidate once it leaves the experimental stage. The client's checks already refuse it with `--mcp-allow-write` or without `--mcp-tools`.
