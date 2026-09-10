<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# Customer environment supplement: <customer / tenant name>

> **Filled in by the customer's platform team, once per tenant.** This file
> records the environment-specific facts the WxO skill cannot know on its own:
> which models are approved, where internal endpoints and mirrors live, and any
> naming or policy constraints the coding agent must honor.
>
> Drop a completed copy of this file into the project the coding agent is
> working in (alongside the agent YAML and tool code). The skill looks for it
> and applies these constraints during build, deploy, and the Phase 5
> diagnostic checks. If it is absent, the skill falls back to live `orchestrate`
> CLI lookups and will ask the platform team for anything it cannot determine.
>
> Delete the guidance blockquotes and replace every `<...>` placeholder. Leave
> a section empty (or write `none`) if it does not apply to this tenant.

---

**Tenant / environment:** `<tenant name, e.g. "acme-prod">`
**Maintained by:** `<platform team contact or distribution>`
**Last updated:** `<YYYY-MM-DD>`
**Topology:** `<Cloud SaaS | self-managed | airgapped | Developer Edition>`

---

## 1. Approved models

> The curated list of models an agent's `llm:` field is allowed to use on this
> tenant. The model gateway rejects anything not on this list at runtime — the
> deployment succeeds but the agent fails at first invocation. List the exact
> model IDs as they appear in `orchestrate models list`.

| Model ID | Approved for | Notes |
|----------|-------------|-------|
| `<provider/model-id>` | `orchestrator \| tool-calling \| RAG \| formatter \| vision \| any` | `<e.g. "default for new agents", "tool-use only">` |

- **Models explicitly disallowed (if any):** `<list, or "none">`
- **Who to ask for an exception:** `<contact>`

## 2. Internal endpoints and mirrors

> Required for self-managed and airgapped tenants. The coding agent uses these
> to confirm nothing reaches out to the public internet. Leave blank for Cloud
> SaaS.

- **`WO_INSTANCE` base URL (pattern or value):** `<https://wxo.internal.example.com/...>`
- **IAM / token endpoint (internal mirror):** `<https://iam.internal.example.com/identity/token or "uses public iam.cloud.ibm.com">`
- **PyPI mirror for `requirements.txt` deps:** `<https://artifactory.internal.example.com/.../simple or "public PyPI reachable">`
- **Other mirrored services the tools may call:** `<list internal service base URLs, or "none">`

## 3. Naming conventions

> Any internal naming rules beyond the WxO hard constraints (agent names must
> match `[a-zA-Z][a-zA-Z0-9_]*`, etc.). Leave blank if the WxO defaults are fine.

- **Agent name prefix / pattern:** `<e.g. "team prefix `acme_`", or "none">`
- **Toolkit name convention:** `<e.g. "kebab-case, domain prefix", or "none">`
- **Connection `app_id` convention:** `<e.g. "`acme-<system>-<env>`", or "none">`

## 4. Connection / secret policy

> How credentials are provisioned and scoped on this tenant.

- **Who creates connections:** `<platform team | innovator with scoped key | ...>`
- **Shared connections available for reuse:** `<list app_ids, or "none — create per project">`
- **Secret-rotation expectations:** `<e.g. "90-day rotation; use key_value with versioned keys">`

## 5. Data residency and DLP constraints

> Tenant-level controls the architecture plan (Phase 1) must respect. These
> usually mirror what the platform team checks during review.

- **Region / residency requirements:** `<e.g. "EU-only; no data egress outside region">`
- **DLP controls in force:** `<e.g. "PII redaction on egress channels">`
- **Channels disallowed on this tenant:** `<e.g. "no public web chat embed", or "none">`

## 6. Other tenant-specific guidance

> Anything else the coding agent should honor that does not fit above.

`<free text, or "none">`
