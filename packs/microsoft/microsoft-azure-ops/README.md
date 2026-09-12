# Pack `microsoft-azure-ops` — Microsoft Azure operations

Vendor: `microsoft`. Curated from [microsoft/skills](https://github.com/microsoft/skills) (MIT), plugin `azure-skills`. Install with `uvx bob-skills add microsoft-azure-ops`.

## Before you install

**The diagnostics and compute skills run commands inside virtual machines, reset passwords, exec into AKS pods and start privileged debug pods, and they apply fixes such as scaling a plan up.**

Covered by: The security-defaults rule makes the agent show each command and its target and wait for your yes; ask for read-only checks and `--dry-run` first, and delete debug pods when the investigation ends.

**Capacity reservations bill from the moment they exist, whether or not a virtual machine uses them, and several workflows create or enable billable resources.**

Covered by: The rule requires the monthly cost and the exact resource to be shown before creation, and your yes for that action.

| Skill | What it adds |
|---|---|
| `azure-resource-lookup` | Find Azure resources and their properties |
| `azure-storage` | Storage accounts, blobs, files and queues |
| `azure-cost` | Cost analysis and optimisation |
| `azure-compliance` | Compliance checks against policies |
| `azure-quotas` | Quota lookup and increase requests |

Refresh with `python3 scripts/sync_upstream.py microsoft-azure-ops`, then `bob-skills registry validate --fix`, lint, scanners, version bump, PR, tag.
