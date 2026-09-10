<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# Testing a deployed agent — REST/IAM request mechanics

Load this when running scripted or CI tests against a deployed agent via the
REST API (Phase 4). For Web UI or local-DE CLI testing, you don't need it —
SKILL.md's Phase 4 summary covers those paths.

## REST API (Cloud SaaS or self-managed)

1. **Exchange `WO_API_KEY` for an IAM token.** POST to
   `https://iam.cloud.ibm.com/identity/token` (or the customer's internal IAM
   mirror on airgapped installs — see `airgapped_preflight.md`):

   ```
   grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=<WO_API_KEY>
   ```

   with `Content-Type: application/x-www-form-urlencoded`. The response's
   `access_token` is your bearer token.

2. **POST the chat request** to
   `{WO_INSTANCE}/v1/orchestrate/{agent_id}/chat/completions` with:
   - `Authorization: Bearer <token>`
   - `X-IBM-THREAD-ID: <uuid>` — reuse the same UUID across turns for
     multi-turn continuity; use a fresh one to start a new conversation.

3. **Body schema is `ChatCompletion`** — NOT OpenAI-equivalent. Key
   differences:
   - no `model` field (the agent's own `llm:` governs the model);
   - `messages` is a list of `{role, content}` with role in
     `user | assistant | system`.

   ```json
   {
     "messages": [
       { "role": "user", "content": "<your test prompt>" }
     ]
   }
   ```

This path is best for scripted regression tests and CI.

## Why test against the deployed agent at all

Test the SAME prompts you intend production users to send. Routing,
delegation, memory, and tool-call behavior cannot be predicted reliably
from YAML inspection alone — that's the point of Phase 4.
