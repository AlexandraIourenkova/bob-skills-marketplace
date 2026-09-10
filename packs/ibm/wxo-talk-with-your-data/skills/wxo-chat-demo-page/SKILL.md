---
name: wxo-chat-demo-page
description: >-
  Build a polished demo web page with an embedded IBM watsonx Orchestrate (wxo)
  chat widget — a landing page for showing an agent to stakeholders. Fetches the
  official embed snippet, assembles a themed layout (hero, stat cards, example
  questions, mock chat preview, or full-page chat), serves it locally, and
  verifies the chat end-to-end in the browser. Use whenever the user wants a
  demo/landing page for a wxo agent, mentions embedding the wxo web chat into a
  site ("embed code", "вставить чат на страницу", "демо страница для агента",
  "лендинг с чатом"), wants charts or a dashboard built live from the agent's
  chat answers ("рендерить графики из ответов", "дашборд с чатом", mermaid
  charts from a wxo agent, analyst canvas), or reports the wxo chat widget
  loading forever.
---

# Demo page with embedded wxo chat

Goal: a page you'd be happy to screen-share with a customer, with the real
agent answering live, built in one pass. The layout is assembled from proven
blocks; the embed snippet comes from wxo itself; everything is verified in a
real browser before handing over.

## Step 1 — Ask the user what the demo should look like

These are taste decisions the user must make — ask (AskUserQuestion when
available) before writing code:

1. **Background / branding** — for the *landing* and *full-page chat* types
   only (the analyst canvas has its own look and skips this question) — four
   honest options, strongest illusion first:
   - *LIVE company page under the chat*: the real site in a full-viewport
     iframe, links and scrolling working, chat floating on top —
     `assets/livepage_iframe_template.html`. Check first that the site allows
     framing (`curl -sI <url> | grep -i 'x-frame-options\|frame-ancestors'`);
     if blocked, offer console injection instead (embed-issues.md #9). Use
     only for the customer being demoed to, never publish such a page.
   - *Screenshot of the company page as background*: static but unblockable —
     behind a full-page chat (fullpage template) or as a hero image.
   - *Blurred texture*: a screenshot or brand photo blurred into an abstract
     backdrop (`filter: blur(18px) saturate(1.4)` + dark gradient overlay) —
     looks premium, hides that the source image is a website screenshot.
   - *Neutral*: no image, dark gradient + radial accent glow. Always safe.

   **Getting the screenshot** (it is not assumed to exist — capture it):
   with a browser tool available, open the company URL at a generous viewport
   (~1600×2400) and screenshot it into the project next to the html. Without
   a browser tool, headless Chrome works:
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless
   --screenshot=company_bg.png --window-size=1600,2400 --hide-scrollbars
   <url>` (on Linux: `google-chrome`). If the page needs a login or a
   specific state, ask the user to provide the screenshot instead — they know
   which view sells the demo. For a blurred-texture hero any visually rich
   region is enough; for an as-is background capture the top of the page.
2. **Page type**:
   - *Landing + floating launcher* (default) — a marketing-style page, chat
     in the corner;
   - *Full-page chat* — the page IS the chat (header + widget filling the
     viewport), optionally over the company background;
   - *Analyst canvas* — chat on the left, a Grafana-style block canvas on the
     right: mermaid charts from the agent's answers render there
     automatically; every table in chat gets two buttons ("create a chart"
     sends a follow-up prompt, "add table to canvas" transfers it); text
     notes are added from the canvas toolbar. Blocks drag/resize/close, and
     the canvas state (blocks, content, positions) survives page reloads via
     localStorage keyed by agent. The impressive option for data agents —
     read `references/chart-canvas.md` before building it.
     **For this type, skip the background question and ask the THEME
     instead**: light or dark — the template ships both (`{{THEME}}` on the
     `<html>` tag picks the token set and the matching validated chart
     palette; the chat column stays light either way, that's the widget's own
     UI).
3. **Layout blocks** (multi-select; template contains all, delete unused):
   hero with CTA · stat cards band · example-question cards (copy to
   clipboard) · CSS mock-chat preview · "how it works" section · footer with
   disclaimer.
4. **Page language** (English default; welcome text and starter prompts of the
   *agent* stay whatever the agent has — the page should match them).

## Step 2 — Fetch the embed snippet from wxo

First resolve the instance, environment and agent — by asking, not guessing:

1. **Environment**: `orchestrate env list` shows the configured envs and marks
   the active one. If none is active (or the token is expired), do not pick
   one silently — the wrong env is a different tenant with different agents.
   For the key, **check the project's `.env` first** (`WXO_API_KEY` /
   `WXO_URL` usually live there — source it, never print the values), then
   activate: `orchestrate env activate <name> --api-key "$WXO_API_KEY"`. Ask
   the user only when `.env` has no key; never invent one. Same applies when
   a previously working env starts failing with "token missing or expired".
2. **Agent**: if the user named the agent, verify it exists in that env
   (`orchestrate agents list`). If they didn't, list the native agents and ask
   which one to embed; when exactly one exists, proceed with it and say so.
   An agent name that isn't found usually means the wrong env — go back to 1
   rather than assuming a typo.
3. **draft vs live**: draft is the norm for prototypes; use live only when the
   agent is actually deployed there.

Then generate the snippet:

```bash
orchestrate channels webchat embed --agent-name=<agent_name> --env=draft
```

If it errors with `Error retrieving CRN: 403` and prompts, pipe the CRN in:
`echo "<crn>" | orchestrate channels webchat embed ...`. **The CRN and
orchestrationID must belong to the SAME instance** — the authoritative source
is the API: `GET <instance-url>/v1/orchestrate/agents` returns `tenant_id`,
which IS the orchestrationID (`<account>_<instance>`), and the CRN's
`a/<account>` segment must match its first half. Never copy a CRN from
`~/.config/orchestrate` history or another page without checking the account
segment — a hash from a different env produces a page that fails with
"Authentication Error" (see embed-issues.md #4).

The snippet defines `window.wxOConfiguration` (orchestrationID = tenant id,
hostURL, rootElementID, showLauncher, crn, deploymentPlatform, and
`chatOptions: { agentId }`) and loads
`<hostURL>/wxochat/wxoLoader.js?embed=true`. **Use exactly this shape.** Do
not add `agentEnvironmentId` to chatOptions — it hangs the widget on skeleton
loaders (see references/embed-issues.md #1). If the CLI is unavailable, the
values can be assembled from the API (`GET <instance-url>/v1/orchestrate/agents`
gives `id` and `tenant_id`) plus the region host.

## Step 3 — Assemble the page

Start from the matching template and fill the `{{...}}` placeholders:

- `assets/landing_template.html` — landing + floating launcher; every optional
  block is fenced with `<!-- BLOCK:name -->…<!-- /BLOCK:name -->`, delete the
  ones the user didn't pick.
- `assets/fullpage_chat_template.html` — header + chat filling the viewport,
  optional page background image, transparent-widget CSS overrides.
- `assets/livepage_iframe_template.html` — the LIVE company site in an iframe
  with the chat floating above it; includes a visible demo ribbon and a
  fallback notice for sites that block framing.
- `assets/chart_canvas_template.html` — the analyst canvas: inline chat +
  gridstack block canvas with auto-rendered mermaid charts (validated light
  palette, an LLM-mermaid repair layer), table transfer and text notes. Its
  interception mechanism, the normalizer catalog and styling rules live in
  `references/chart-canvas.md` — required reading before touching it. Chart
  requests come from the agent's own starter prompts and instruction-level
  mermaid rules (see the excel-to-wxo-agent skill's visualization option).

All template content is SAMPLE data from a reference build — replace every
number, name, currency and category with the customer's real ones; nothing
from the sample company may survive into a new page.

Rules that make the page feel real rather than mocked:

- **Stat cards and mock-chat numbers must be true.** Compute them from the
  agent's actual data (row counts, date ranges, a real revenue figure) — a
  stakeholder will ask about the exact number on screen.
- Example-question cards must be questions the agent demonstrably answers
  well; ideally the same as its starter prompts. Test them.
- Keep the agent's own language in quoted values (Hebrew/Cyrillic categories
  etc.) — it shows the agent handles the customer's real vocabulary.

## Step 4 — Serve and verify end-to-end

`file://` will not work — serve over http (`python3 -m http.server 8765
--directory <dir>`, or the Claude Code browser preview). Then verify in the
browser, in this order:

1. Page renders, no horizontal scroll, background looks intentional.
2. Launcher bubble appears (widget script loaded).
3. Chat opens: agent display name + welcome message + starter prompts render
   (not "Custom Agent" with skeletons — if skeletons persist, go to
   references/embed-issues.md).
4. Click a starter prompt and wait for a real answer with data. First draft
   answer can take 15–30 s (cold start) — wait before concluding it's broken.

## Security — decide with the user, never silently

Embedded-chat security is an instance-level setting (wxo UI → profile →
**Settings → Embed Security**): JWT mode (RS256 keys, page must send signed
tokens — needs a backend) or Off (anonymous — anyone with the page URL can
query the agent and all data its tools reach). Lay out that tradeoff and let
the user flip the switch; it's their data exposure. Details, symptoms and the
JWT flow: references/embed-issues.md #2.

Every known failure mode (endless skeletons, CRN 403, blank widget on file://,
mojibake in welcome text, CSS bleed-through, slow first answer) with fixes:
**references/embed-issues.md** — read it whenever anything misbehaves.

<!-- IBM Bob copy. Primary copy: ~/.claude/skills/wxo-chat-demo-page — apply edits to both. -->
