<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# Model selection — right-sizing & the gpt-oss-120b style gotcha

Load this when choosing an agent's `llm:` model. SKILL.md keeps the 3-step
selection procedure and the one-line gpt-oss-120b warning; this file holds the
role-to-model mapping and the full explanation of the style gotcha.

## Right-size the model to the agent's job

Don't default every agent to the largest available model. Map the role:

| Agent role | What it does | Model class to pick from `list_models` |
|------------|-------------|-------------|
| Orchestrator / triage | Routes requests, maintains multi-turn context, delegates to collaborators | Strong reasoning model **that respects agent styles** (see gpt-oss-120b gotcha below) — never the tenant default if that default is `gpt-oss-120b` |
| Tool-calling specialist | Picks the right tool, builds structured args, formats results | Tool-use-tuned `★` model |
| RAG / citation agent | Retrieves from KB, composes cited prose | Medium reasoning is usually enough |
| Formatter / classifier / extractor | Transforms structured input → fixed output shape | Small fast model |
| Vision-required | Reads screenshots, diagrams, scanned PDFs | Vision model — only here |

Two heuristics:
- If the agent's instructions fit in one screen and it produces structured
  output, a small model is probably enough.
- If the agent has multiple collaborators or routes among >3 tools, lean to a
  stronger reasoning model — routing errors propagate.

State your reasoning when you pick a non-default model so the user can
override it.

## Critical: gpt-oss-120b ignores agent styles

`groq/openai/gpt-oss-120b` is the `✔★` tenant default on most WXO instances,
but the WXO docs explicitly warn:

> If you use `groq/openai/gpt-oss-120b` as your agent's model, the agent
> ignores all styles, except for the Customer Care style.

**Concrete impact:** an orchestrator agent on `gpt-oss-120b` with
`style: default` will NOT run WXO's collaborator-delegation reasoning loop.
It works for simple single-tool calls but silently refuses to delegate
to collaborator agents on multi-turn flows — the agent tries to answer
itself or asks the user for data that should come from a collaborator.

This contradicts the "pick the `✔★` default" rule for one specific
case: **orchestrator agents (any agent with non-empty `collaborators:`) or
any agent that needs `react` / `planner` style must NOT use
`gpt-oss-120b`.** Pick a style-respecting model — on most tenants
`watsonx/meta-llama/llama-3-3-70b-instruct` or
`watsonx/mistralai/mistral-large-2512` are the practical options.
`gpt-oss-120b` remains fine for single-tool specialist agents where style
behavior doesn't matter.
