<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# Architecture plan: <project name>

> **Phase 1 artifact** of the WxO agent deployment flow. The front-line
> innovator (with their coding agent) fills this out and submits to the
> customer's platform team. The platform team reviews and, on approval,
> issues scoped `WO_API_KEY` + `WO_INSTANCE` for the target tenant
> environment.
>
> If review surfaces concerns, the front-line innovator revises specific
> sections — the structure is standardized so re-review targets individual
> decisions rather than the whole plan.

---

**Submitted to:** `<platform team contact or distribution>`
**Submitted by:** `<front-line innovator name / team>`
**Date:** `<YYYY-MM-DD>`
**Target WxO topology:** `<Cloud SaaS | self-managed | airgapped | Developer Edition>`
**Target environment:** `<draft | named env, e.g. "team-prototype">`

---

## 1. One-sentence purpose

What does this system do for users? Avoid technical jargon — describe the
business outcome.

> Example: *"Lets network engineers analyze PCAP files and generate
> Jira-ready incident tickets without leaving a chat interface."*

`<your one sentence here>`

## 2. Agents to deploy

| Name | Role (1 line) | Model | Style | memory_enabled | Collaborators | Tools | Knowledge bases |
|------|--------------|-------|-------|----------------|---------------|-------|-----------------|
| `<name>` | `<role>` | `<model id from orchestrate models list>` | `default \| react \| planner` | `true \| false` | `<names or –>` | `<names or –>` | `<names or –>` |

**Model selection rationale.** For each non-default model choice, justify
the pick using the right-sizing rule from the WxO skill (orchestrator →
strong reasoning that respects styles; tool-calling specialist →
tool-use-tuned; RAG agent → medium; formatter → small; vision-required →
vision-only). Note: `gpt-oss-120b` must NOT be used for orchestrator agents
or any agent depending on `react` / `planner` style — it silently ignores
those styles.

`<rationale per agent>`

## 3. Collaborator graph

If multiple agents collaborate, show the delegation structure. Prose, ASCII
diagram, or Mermaid all fine.

> Example:
> ```
> triage_agent → analysis_agent
>              → retrieval_agent
>              → ticket_agent
> ```
> The triage agent routes by user-utterance keywords; specialist agents do
> not delegate to each other.

`<your graph here>`

## 4. External integrations

For each external system the agents will call (databases, APIs, internal
services):

| System | Direction | Data sent | Data received | Auth model |
|--------|-----------|-----------|---------------|------------|
| `<name>` | `inbound \| outbound \| both` | `<fields>` | `<fields>` | `key_value \| basic \| oauth2 \| bearer \| ...` |

## 5. Connections and secrets

For each `app_id` the agents need (one WxO connection per external system
that requires credentials):

| app_id | Connection kind | Keys/fields to set | Scope of access |
|--------|----------------|--------------------|-----------------|
| `<id>` | `key_value \| basic \| oauth2 \| ...` | `<list of keys>` | `<what the credential can do, scope/permissions>` |

## 6. Knowledge bases

For each KB the agents will query:

| Name | Source documents (count, type, classification) | Embedding model | Expected query patterns |
|------|------------------------------------------------|-----------------|------------------------|
| `<name>` | `<e.g. "9 PDFs, ~5MB total, public standards docs">` | `<model id>` | `<example queries>` |

## 7. Data sensitivity

- **Data classes flowing through this system:** `<PII | regulated financial | regulated health | internal-only | public | mixed>`
- **Where does sensitive data originate?** `<source systems>`
- **Where can sensitive data egress?** `<approved destinations>`
- **DLP (Data Loss Prevention) considerations:** `<known controls that should apply, e.g. PII redaction on egress, region pinning>`

## 8. Channels

Which surfaces will this be exposed on?

- [ ] Web chat embed (WxO-hosted)
- [ ] Slack
- [ ] Microsoft Teams
- [ ] Twilio (SMS / WhatsApp)
- [ ] Phone (voice)
- [ ] Direct REST API access (e.g. for CI tests or programmatic clients)
- [ ] Enterprise UI host — `<name the host application if known>`
      *(UI hosting is out of scope for this skill — see the adjacent
      "WxO agent → enterprise UI" skill if applicable)*

## 9. Load estimate

- **Expected steady-state load:** `<requests/day>`
- **Concurrent sessions at peak:** `<number>`
- **Burst expectations:** `<peak/steady ratio, e.g. "5x for 30 min during incidents">`

## 10. Token & cost estimate

For each model used, estimate the per-request token footprint and project
the resulting monthly cost at the load estimated above. The platform team
needs this to confirm fit within tenant token budgets and model-gateway
quotas.

| Model | Input tokens/req (avg) | Output tokens/req (avg) | Tool-call cost (additional req/turn) | Est. $/month at steady load |
|-------|-----------------------|------------------------|--------------------------------------|----------------------------|
| `<model id>` | `<n>` | `<n>` | `<n requests × tokens each>` | `$<value>` |

- **Pricing source / model card referenced:** `<URL or "tenant model-policy lookup">`
- **Assumed retention:** how many conversation turns kept in memory per session? `<n>`
- **Headroom factor:** what multiplier did you apply to estimates for safety? `<e.g. 1.5x>`
- **Notes on cost-sensitive paths:** `<which agent / model / tool is the biggest cost driver and why>`

## 11. Open questions for the platform team

Anything the front-line innovator is unsure about and wants confirmed
before review.

- `<e.g. "Is model X available on this tenant?">`
- `<e.g. "Can we use the team-shared Jira connection or do we need a new app_id?">`

---

## Platform team review (filled by reviewer)

**Reviewer:** `<name>`
**Review date:** `<YYYY-MM-DD>`

Checklist:

- [ ] Data flows meet residency and DLP policy
- [ ] All external integrations are approved (or noted as new)
- [ ] Model choices are licensed and available on the target tenant
- [ ] Channel exposures match intent and policy
- [ ] Required connections are creatable with appropriate scoping
- [ ] Load estimate fits available tenant capacity
- [ ] Naming follows internal conventions (if any)

**Outcome:**

- [ ] **Approved.** Scoped keys issued: `WO_API_KEY` delivered to `<recipient via secure channel>`; `WO_INSTANCE` = `<URL>`
- [ ] **Requires revision.** See comments below — re-submit specific sections only.
- [ ] **Rejected.** See comments below.

**Reviewer comments:**

`<...>`
