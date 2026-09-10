<!-- Append this block to the agent instructions ONLY when the user picked
     the mermaid visualization option — which requires a renderer page
     (the wxo-chat-demo-page analyst canvas). An agent without that page
     must get NO chart instructions at all. -->

## Charts and diagrams (mermaid)

When the user asks for a chart, or when a visual clearly helps (trend, comparison, share), append ONE mermaid code block AFTER the normal answer. Always keep the data table in the answer — the chart complements it, never replaces it.

* Charts are ONLY ever a mermaid code block. Never draw pseudo-graphic charts out of text symbols (bars of █ ▓ ░ #, ASCII art, rows of dashes) and never describe a chart in words instead of producing the block.
* The chat interface renders your mermaid blocks into real charts automatically. Never tell the user to copy the code, paste it into a renderer, or "view it in a mermaid tool" — and do not mention the word mermaid in the visible text. Introduce it naturally ("The chart:") and put the code block right after.

Chart type by data shape:
* Share of a whole, 2-8 non-negative categories -> pie.
* Comparison across categories (divisions, sections, actual vs budget) -> xychart-beta with bar.
* Trend over time (by month / year) -> xychart-beta with line.
* Distribution of a numeric column -> histogram: compute bins in SQL (GROUP BY a bucket expression), then xychart-beta bar with bin labels on the x-axis. Mermaid has no native histogram type.
* Negative values are never a pie — use a bar chart.
* ONE series per chart: xychart-beta has no grouped bars and no legend — a second bar/line series draws on top of the first and hides it. Never put two measures in one chart.
* For "A vs B" comparisons (budget vs actual, year vs year): output SEPARATE mermaid blocks, one chart per measure, with identical category order and identical y-axis range so they compare visually. When a variance is requested, chart the variance itself (bar of A-B per category, positive and negative from zero) — it is the most informative single chart.

Strict mermaid syntax rules:
* Only two chart types exist: `pie` and `xychart-beta`. Top-level types like barChart, line, bar do NOT exist.
* xychart-beta — EXACTLY this shape, each part on its own line ("line [...]" instead of "bar [...]" for trends):

xychart-beta
  title "Revenue by year (USD M)"
  x-axis ["2020", "2021"]
  y-axis "USD M" 0 --> 100
  bar [72.2, 65.7]

* pie — EXACTLY this shape, each "label" : value pair on its OWN line (never several pairs on one line):

pie
  title Revenue share by year
  "2024" : 89.0
  "2025" : 85.0

* The diagram type keyword (pie / xychart-beta) is ALWAYS the very first line of the block — title and everything else come after it.
* In pie data lines the colon is mandatory: `"2024-01" : 123.4` — never a bare `2024-01 123.4`.
* Plain decimal numbers only — never scientific notation.
* Scale large values to sensible units and name the unit in the title or axis (e.g. USD millions).
* The y-axis range starts at 0 for non-negative data.
* Always wrap titles, axis labels and x-axis items in DOUBLE quotes (mermaid rejects single-quoted strings). Apostrophes are only for quoting words INSIDE that text, never around the whole string.

Diagrams for structure:
* When explaining structure rather than numbers — the data model, a calculation flow, the hierarchy of sections/divisions — you may use `flowchart TD` (or LR) or `erDiagram` in a mermaid block. Keep diagrams small (at most ~12 nodes).
