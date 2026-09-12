# wxo embedded chat: known issues and fixes

Field-tested on watsonx Orchestrate SaaS (eu-de, ADK 2.x, 2026). Ordered by
how often each one actually bites.

## 1. Endless skeleton loaders, title "Custom Agent", no console errors

The widget opens but never initializes: gray placeholder bars, spinner in the
input, agent name shows as "Custom Agent".

- **Cause A (most common): `agentEnvironmentId` present in `chatOptions`.**
  Verified empirically: adding it hangs the widget; removing it fixes it
  instantly. The official generator (`orchestrate channels webchat embed`)
  never emits it, even with `--env=draft`. chatOptions must contain
  `agentId` only.
- **Cause B: Embed Security enabled but unconfigured.** Per IBM docs, security
  is enabled by default at instance level and the chat "does not work until"
  it is configured; the widget gets 403s silently. See #2 for both fixes.
  Quick differential: if another page with the same orchestrationID/agentId
  works in the same instance, security is fine and you're in Cause A.

## 2. Embed Security: anonymous vs JWT

Instance-level switch: wxo UI → profile icon → **Settings → Embed Security**.

- **Off (anonymous)**: chat works from any page with no code changes. Anyone
  who obtains the page (or just the IDs inside it — they're visible in
  view-source) can query the agent and everything its tools expose. Fine for
  live demos and low-risk data; wrong for real financials on a public URL.
  This is a decision for the user, not for you.
- **On (JWT)**: generate RS256 keys (`openssl genpkey -algorithm RSA -pkeyopt
  rsa_keygen_bits:4096` → extract public key), upload the public key in the
  Embed Security tab; the page must then attach a JWT signed with the private
  key to every widget request — which requires a small backend to mint tokens
  (max expiry 7100 s; refresh in-session via `updateAuthToken()`). A static
  demo page cannot do JWT mode on its own.

Docs: ibm.com/docs → watsonx Orchestrate → "Securing the embedded chat" and
"Configuring security for embedded chat".

## 3. Widget does nothing on `file://`

Opening the html directly from disk gives a dead widget (script/CORS). Always
serve over http on the loopback address: `python3 -m http.server 8765 --bind 127.0.0.1 --directory <dir>`.

## 4. `channels webchat embed` fails with CRN 403

The ADK tries to resolve the CRN via the IBM Cloud resource controller; an
instance (MCSP) token gets 403 there, and the command falls back to an
interactive prompt. Pipe the CRN in:

```bash
echo "crn:v1:bluemix:public:watsonx-orchestrate:<region>:a/<account>:<instance>::" \
  | orchestrate channels webchat embed --agent-name=<name> --env=draft
```

Find the CRN in IBM Cloud → resource list → the instance — and make sure it
belongs to THE instance you're embedding.

**"Authentication Error — This content couldn't be loaded" on page load** is
the symptom of getting this wrong (seen in the field): an orchestrationID or
CRN assembled with the account hash of a DIFFERENT environment (e.g. copied
from `~/.config/orchestrate` history, which holds CRNs of every env ever
added). The widget authenticates against a tenant that doesn't own the
instance and fails. The authoritative pairing: `GET
<instance-url>/v1/orchestrate/agents` returns `tenant_id` =
`<account>_<instance>` — that exact string is the orchestrationID, and the
CRN's `a/<account>` segment must equal its first half. Verify both before
shipping the page.

## 5. Mojibake (`Рђћ`, `ОћОЋ…`) in the widget's welcome text / prompts

Not a page problem — the agent itself was imported with mangled instructions
(the ADK guesses file encoding and misreads Hebrew/Cyrillic-heavy UTF-8 yaml
as cp855). Fix on the agent side: `orchestrate settings set-encoding utf-8`,
regenerate/repair agent.yaml, re-import. (If the excel-to-wxo-agent skill is
installed, its wxo-notes.md has the full recovery procedure, including
reversing the damage via `text.encode('cp855').decode('utf-8')`.)

## 6. First answer is slow (15–30 s)

Draft-environment cold start: the first message after a quiet period spins up
the tool runtime. Wait it out before debugging; warn the audience or send a
warm-up question before the demo.

## 7. Widget styling bleeds / wrong background

The widget injects its own styles into your page. For full-page embeds on a
custom background, force transparency on its containers:

```css
#root > div, [class*="wxo-"], [class*="chat-container"] {
  background: transparent !important;
}
```

For the floating launcher, avoid `z-index` wars: keep your own fixed elements
below ~10000 and leave the bottom-right corner (roughly 100×100 px) free on
every breakpoint.

## 8. "Open chat" CTA button on the page

There is no documented JS API to open the launcher. A best-effort selector
click works today but may break with widget updates:

```js
document.querySelector('[class*="launcher" i] button, button[class*="launcher" i]')?.click()
```

Always keep a visible fallback hint ("use the chat bubble in the corner ↘").

## 9. Demo over the LIVE company site

Three ways to show the chat "on" the customer's real website, strongest first:

1. **iframe wrapper** (`assets/livepage_iframe_template.html`): the live site
   in a full-viewport `<iframe>`, chat floating above it in the parent page.
   Links, scrolling and navigation inside the frame all work. Precondition —
   the site must allow framing; check the response headers:

   ```bash
   curl -sI https://company.com | grep -i 'x-frame-options\|content-security-policy'
   ```

   `X-Frame-Options: DENY|SAMEORIGIN` or a CSP `frame-ancestors` directive →
   the frame renders blank; fall back to option 2 or a screenshot background.
   Keep the wrapper's demo ribbon visible — the page must not pass for the
   real site.

2. **Console injection on the real site** (live demo trick, nothing saved):
   open the actual company page in a browser, open DevTools Console, paste the
   full embed snippet (the `window.wxOConfiguration = {...}` object plus the
   loader `<script>` body as plain JS — create the script element and call
   `wxoLoader.init()` on load). The launcher appears on the genuine page.
   Caveats: a strict site CSP (`script-src`) can block the wxo loader; the
   widget disappears on any navigation/refresh, so inject right before
   showing; demo-only — never leave injected code in a customer session
   unattended, and get their OK before doing it on their machine.

3. **Real integration**: hand the customer's web team the generated snippet
   for their page `<head>` — the production path, out of demo scope.

## 10. Verifying beyond the happy path

Before showing the demo: ask one starter prompt (data answer), one follow-up
("and by division?" — tests conversation context), and one off-topic question
(checks the agent declines gracefully). Screenshot the answers — if a number
on your stat cards disagrees with the agent's answer, fix the cards.
