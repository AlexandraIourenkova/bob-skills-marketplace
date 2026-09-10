# Pack `microsoft-azure-ops` — Microsoft Azure operations

Vendor: `microsoft`. Curated from [microsoft/skills](https://github.com/microsoft/skills) (MIT), plugin `azure-skills`. Install with `uvx bob-skills add microsoft-azure-ops`.

| Skill | What it adds |
|---|---|
| `azure-resource-lookup` | Find Azure resources and their properties |
| `azure-storage` | Storage accounts, blobs, files and queues |
| `azure-cost` | Cost analysis and optimisation |
| `azure-compliance` | Compliance checks against policies |
| `azure-quotas` | Quota lookup and increase requests |

Refresh with `python3 scripts/sync_upstream.py microsoft-azure-ops`, then `bob-skills registry validate --fix`, lint, scanners, version bump, PR, tag.
