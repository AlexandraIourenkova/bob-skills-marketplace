# Analyst canvas: charts, tables and notes next to the wxo chat

The third demo-page type (`assets/chart_canvas_template.html`): agent chat on
the left, a Grafana-style canvas on the right. Mermaid code blocks in the
agent's answers become chart blocks automatically; tables get an
"add to canvas" button; notes are added by hand. Blocks drag, resize,
auto-compact and close. The agent itself is untouched — chart code is
requested inside the user's message.

Everything below was established empirically against a live wxo instance
(eu-de, widget build of 2026-09) and is already implemented in the template.
Read this when adapting or debugging it.

## How interception works (and why not the documented way)

The ADK docs describe `pre:receive`/`receive` events. **They do not fire in
the current widget build**: `wxoLoader.init()` resolves without an instance,
and the visible `window.wxoEventBus` emits nothing (verified by wrapping its
`emit`). The widget renders into the parent DOM (not an iframe), so the
working interception point is a **MutationObserver on the chat container**:

- a ```` ```mermaid ```` fence renders as `<pre class="WxOChat__SyntaxHighlight--…">`
  whose **first line is the language label** (`mermaid`);
- read code via `innerText` (preserves newlines; `textContent` glues lines);
- streaming builds the block progressively — **debounce ~900 ms** until the
  text stabilizes before processing;
- after rendering, the `<pre>` is replaced with a small badge ("chart rendered
  on the canvas →") so the chat stays clean;
- markdown tables render as plain `<table>` — same observer, same debounce.
  Two buttons are injected after each table (in an `ltr` row — agent messages
  can be RTL and would flip the order): **"create a chart"** sends a follow-up
  prompt into the widget programmatically ("Show the last table as a chart,
  using exactly the numbers from that table — do not run a new query"; the
  no-new-query clause matters — without it the agent re-queries and can chart
  the wrong numbers), and **"add table to canvas"** transfers the table as a
  block. Programmatic send: the input is TipTap/ProseMirror — focus it,
  `document.execCommand('insertText', ...)`, then click
  `button.chat-bar__send-button`.

Widget quirks: Enter does NOT send a message (only the send button); the
first answer after a quiet period takes 15–30 s (draft cold start).

## The mermaid normalizer (LLM output repair)

LLMs produce broken mermaid constantly. The template repairs every observed
failure deterministically before rendering — keep this catalog growing:

| LLM output | Repair |
|---|---|
| `barChart` / `line` / `bar` as a top-level type (no such diagrams) with `xAxis`/`x-axis` keywords and pie-style `"label" : value` pairs | parse and rebuild as `xychart-beta` with `bar [...]` or `line [...]` |
| `pie` with negative values (parser rejects them; a pie cannot show polarity) | rebuild as `xychart-beta` bar chart with a negative-capable range |
| scientific notation (`6.65e7`, `9.4e-9`) anywhere | expand to plain decimals; NB: JS `String(9.4e-9)` re-emits `"9.4e-9"`, so serialization goes through a `toFixed`-based `toPlain()` |
| axis range split onto its own line (`y-axis "USD M"` ␊ `0 --> 100`) | merge number/arrow-only lines into the preceding axis line |
| `y-axis "label" 0 100` (missing `-->`) | insert the arrow |
| `bar ["Name"] [...]` (series name in brackets) | drop the bracketed name |
| values list broken across lines inside `[...]` | join to one line |
| nested double quotes in titles (`title ... (section = "מכירות")`) | inner `"` → `'` |
| `%%{init: ...}%%` directives on fake types | dropped during conversion |
| single-quoted strings (`title 'Revenue…'`) — models over-apply "avoid nested double quotes" | convert to double quotes on title/axis lines and list items |
| `title` line BEFORE the type keyword ("No diagram type detected") | detection tolerates a leading title line; the converter reassembles in valid order |
| colon-less pairs (`2024-01 -1453962.36`) in fake-type dialects | fallback pair parser: label = everything before the trailing number |
| negative values in a fake-type conversion | axis range min·1.1 --> max·1.1 instead of the 0-anchored range (which would clip) |
| pie pairs jammed onto ONE line (`pie title X "A" : 1 "B" : 2 …` — parser needs one pair per line, block shows as raw text) | rebuild: extract all pairs globally, emit type/title/one pair per line |
| two+ `bar`/`line` series in ONE xychart (mermaid has no grouped bars and no legend — the second series draws over the first) | split into one chart per series, titles suffixed "— series N/M"; prompt-side, the agent rules demand one series per chart and separate charts for A-vs-B comparisons |

Prompt-side prevention (cheap): the mermaid rules block from the
`excel-to-wxo-agent` skill (`assets/mermaid_chart_rules.md`) baked into the
AGENT's instructions — exact syntax samples, plain-decimals rule, chart-type
selection. The page has no prompt chips: the agent's own starter prompts
cover discovery, and the rules travel with the agent.

Error handling: mermaid fails two ways — a thrown parse error AND a
"successful" render of an error SVG ("Syntax error in text"). Detect the
latter by sniffing the returned SVG, and **remove the stray error element
mermaid leaves in `<body>`** on failure (`#<id>` / `#d<id>`). The card then
shows the message plus the source, so new LLM dialects are easy to spot and
add to the catalog.

## Chart styling (the dataviz pass)

Charts follow the data-viz reference method; values already validated:

- **Palette**: 8-slot categorical set in fixed order, starting
  `#2a78d6, #eb6834, #1baf7a, #eda100, #e87ba4, #008300, #4a3aa7, #e34948`,
  validated on the light surface `#fcfcfb` (CVD ΔE 9.1, normal-vision 19.6,
  ALL PASS; the sub-3:1 contrast WARN on slots 3–5 is relieved by the data
  table the agent sends alongside + on-chart labels).
- **Mermaid theming** via `theme: 'base'` + `themeVariables`: `pie1..pie8`
  from the palette, `pieOpacity 1` with a 2px surface-colored stroke (the
  "gap between fills" spec), `xyChart.plotColorPalette`, muted axis ink
  `#898781`, IBM Plex.
- **Post-render polish** (`polishChart`): bars get 4px rounded data-ends on
  the value side only; recessive hairline gridlines at tick heights behind
  the marks (tick label positions are mapped through the **inverse CTM of the
  bar group** — text lives in differently-transformed groups, so bbox math in
  mixed spaces silently breaks); native `<title>` tooltips on bars and
  slices.
- **Vertical x-labels when needed**: mermaid has no label-rotation option, so
  long category labels (Hebrew section names etc.) overlap. The polish step
  measures each label against its band width and, when they outgrow it,
  rotates them -90° — composing WITH mermaid's own positioning transform
  (replacing it flings labels away and explodes the viewBox) — then grows the
  viewBox bottom (capped +200) so nothing clips.
- **Honest bars**: mermaid xychart anchors bars at the axis MINIMUM — with a
  negative range, zeros render as full columns. The polish step rebuilds a
  value→pixel map from the ticks and re-anchors every bar to the zero line
  (positive up, negative down, zero = hairline stub). Converters also force
  `0 --> max·1.1` ranges so positive charts never start mid-axis.

## Canvas mechanics

- **GridStack** (CDN) with `float:false` (vertical auto-compaction), drag by
  the block header, resize handles, per-block close. Tables get a
  row-count-based initial height; notes are 4×3 contenteditable blocks.
- **Resilience**: the wxo embed lives in its **own `<script>` block, first in
  the document** — a CDN or canvas-library failure must never take the chat
  down. If GridStack is missing, blocks degrade to a static stacked column
  (drag/resize lost, nothing else).
- Numeric table columns are auto-detected (dashes `—` count as empty) and get
  right alignment + `font-variant-numeric: tabular-nums`.
- **Persistence**: the canvas survives page reloads. Every block stores its
  kind + payload (`el._meta`: mermaid code / table data / note text read live)
  and grid geometry; a debounced save writes the list to `localStorage` under
  `wxo_canvas_<agentId>` on add/close/move/resize/note edits (gridstack
  `change` event covers drags), and `restoreCanvas()` rebuilds blocks with
  their geometry on load. The chat itself starts a fresh thread on reload —
  the canvas is what carries the session's results. Clear wipes the stored
  state; all storage access is try/catch-guarded so blocked storage just
  turns persistence off.

## Adapting the template

**Theme**: `{{THEME}}` = `light` | `dark`, set on `<html data-theme>`. Both
token sets ship in the CSS, and the JS picks the matching validated palette
(light and dark are different steps of the same hues, both validated against
their surfaces) plus theme-correct mermaid variables and gridline color. Ask
the user which they want — for the canvas type this replaces the background
question. The chat column stays light in both themes (the widget's own UI).

Fill `{{PAGE_TITLE}} {{BRAND}} {{ORCHESTRATION_ID}} {{HOST_URL}} {{CRN}}
{{AGENT_ID}} {{THEME}}` (same sources as the other templates — `orchestrate channels
webchat embed` or the API), (no prompt chips to fill — the agent's starter prompts and its
instruction-level mermaid rules carry that job). Test
end-to-end in a browser: send a starter prompt asking for a chart, wait for the badge in chat and
the block on the canvas, and try one deliberately awkward request (top-N with
tiny/negative values) to see the normalizer working.
