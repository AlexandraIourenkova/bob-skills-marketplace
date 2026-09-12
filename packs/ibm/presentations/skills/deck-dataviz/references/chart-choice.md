# Chart choice: pick the chart from the message

This file is the decision guide for putting a chart on a slide. Read it after the finding for the slide is written and before writing a fenced `chart` block or a `chart_render.py` spec, and read it again when the user hands over a table and says "chart this". It answers one question: which form shows this message, and whether that form is a native PowerPoint chart or a rendered picture. Polishing the chosen chart is covered in chart-makeover.md. The spec keys for rendered charts are in chart-spec.md.

## The one rule

Write the finding as a sentence first. Then pick the chart that shows exactly that sentence and nothing else. The data shape (three columns, twelve rows) tells you what is possible. The sentence tells you what to draw. If you cannot write the sentence, you are not ready to chart. Go back to the data and find the point.

Six findings and the chart each one needs:

| Finding, written as the headline | Chart |
|---|---|
| Enterprise is the only tier that grew in every quarter | Line, Enterprise in the theme's accent, the other tiers muted. Small multiples above four tiers. |
| Two products cause 80 percent of support tickets | Horizontal bars sorted by count, the top two highlighted, the rest muted. Not a pie. |
| Churn fell from 6.1 to 3.4 percent after the onboarding change in March | Rendered annotated line with the March change marked. |
| Margin dropped 7 points: pricing gave 2, freight took 9 | Rendered waterfall from 31 to 24 percent. |
| Germany overtook France in 2025 | Rendered slope chart, 2024 to 2025, both countries labelled at both ends. |
| Enterprise customers doubled to 104 | Big-number layout. No chart. |

The test is the same as for a headline: cover the headline, look at the chart, and say the sentence back. If the chart supports a different sentence, or several, it is the wrong chart.

## Master table

Native types are the fenced `chart` block: `bar` (columns), `barh`, `stacked`, `barh-stacked`, `line`, `area`, `pie`, `doughnut`. Rendered types come from `chart_render.py` as a PNG placed with `![alt](charts/name.png)`: waterfall, slope, lollipop (dot), bullet, small multiples, scatter, annotated line, heatmap, ranked bar with highlight.

| Message | First choice | Second choice | Native or rendered | Notes |
|---|---|---|---|---|
| Compare a few values (2 to 7) | `bar`, or `barh` when the names are long | Lollipop | Native; lollipop rendered | Sort by value. Data labels on. Highlight the one the headline is about. |
| Compare many values, a ranking (8 to 12) | `barh` sorted, the top items highlighted | Ranked bar with highlight | Native; ranked bar rendered | Above 12: the top 10 plus "Other", the full list in the appendix. |
| Change over time, few periods (up to 8) | `bar` in time order | `line` | Native | Never sort a time axis. Label every column. |
| Change over time, many periods (more than 8) | `line` | `area`, one series only | Native | Up to 4 series. Beyond that, one in the accent and the rest muted, or small multiples. |
| Two periods only | Slope | `bar` with two series (paired columns) | Rendered; paired bars native | Name and value at both ends of every line. |
| Part of a whole, few parts (up to 5) | `barh` of shares, sorted | `pie` or `doughnut`, sorted by size | Native | Percent labels. Name the base in the footnote. Shares sum to 100. |
| Part of a whole, many parts | `barh` sorted, top 5 plus "Other" | `stacked` at 100 percent, up to 4 segments | Native | Never a pie. "Other" goes last, in the muted colour. |
| Composition of a change | Waterfall | `stacked` bars of the start and end states | Rendered; stacked native | Totals in the text colour, gains in the accent, losses in the muted colour. |
| Distribution | `bar` of bins (a histogram) | Dot strip (rendered scatter on one axis) | Native; dot strip rendered | There is no box plot type. Put the median and the range in the headline. |
| Relationship between two measures | Scatter | Connected scatter (points joined in time order) | Rendered | Annotate the outliers. If chart-spec.md has no connected option, draw two lines on a shared time axis. |
| Progress against a target | Bullet | Bar with a target line | Rendered | State the gap and the date in the headline: "72 percent of the Q4 target, six weeks left". |
| A single metric | Big-number layout | Statement slide | Neither | Not a chart. See "Big numbers" below. |
| Many series of the same shape | Small multiples, same axes | `line`, one series in the accent, the rest muted | Rendered; line native | Up to 9 panels. The same y axis on every panel, or the comparison is false. |
| A matrix of categories | Heatmap | `table` with the strong cells in bold | Rendered; table native | Up to 10 by 10 cells. Print the value in each cell when it fits. |
| Flows and processes | A diagram, not a chart: the `timeline` layout for steps in time, a drawn figure from deck-images for the rest | A numbered list | Neither | Sankey and flow charts are not chart types here. |
| Location | A map, only when the place itself is the message (a drawn figure) | `barh` by region, sorted | Rendered; bars native | "The North grew fastest" is a ranking. Draw bars. |
| Exact values people will look up | `table` layout | None | Native | 9 rows by 6 columns on the slide, the full table in the appendix. |

## Bars

- When: a few values compared, a ranking, or a short run of periods (up to 8).
- Axis: starts at zero, always. A bar's length is the value; a truncated axis lies.
- Sorting: by value, largest first. Time order for periods. Natural order for scales (small, medium, large). For `barh` the builder draws the first category at the top, so list them in the order you want them read.
- Labels: `"data_labels": true` with one decimal at most, up to 12 categories. Long names: `barh`, so the names read horizontally and stay on one line.
- Limit: about 12 categories. Beyond that, the top 10 plus "Other", or a table in the appendix.
- Series: up to 3 grouped series. Beyond that the groups blur; use a line or small multiples.
- Emphasis: `"highlight": ["Billing"]` paints the named categories in the accent and the rest grey. Single series only.

## Lines

- When: change over more than a handful of periods, or several series compared over time.
- Axis: may start above zero when the movement is the message; then say so in the footnote. Time runs left to right at equal spacing. A missing period stays a gap; never squeeze the axis.
- Sorting: never. Time is the order.
- Labels: the series name at the end of the line (rendered) or the legend at the bottom (native, drawn by default when there is more than one series). Data labels only on a single series with few points.
- Limit: 4 series. Then one in the accent and the rest muted (rendered annotated line), or small multiples with the same axes.
- Markers: the builder draws circle markers on native lines. Fine up to about 12 points, noisy beyond that; render longer series.

## Pie and doughnut

- When: a share of one whole, the reader needs "about half" or "about a quarter", and there are at most 4 or 5 slices. The storyboard check warns above 5.
- Sorting: by size, largest first.
- Labels: `"data_labels": true` puts percentages on the slices; the base goes in the footnote ("of 1,240 tickets").
- Limit: 5 slices. More than that, or any comparison between two wholes: `barh` of shares.
- A doughnut with the number in the middle is right when that number is the share the headline states. Otherwise it is decoration; use a big number.

## Stacked bars

- When: composition per category, and the total matters as much as the parts.
- Segments: up to 4. Only the bottom segment sits on a common baseline, so put the segment the headline is about first in the series list.
- 100 percent stacks for a mix shift over time; absolute stacks when the totals are the message.
- Labels: `"data_labels": true` centres the values in the segments. Leave it off for thin segments and state the totals in the headline instead.
- Limit: 4 segments, about 8 categories. More segments: a line per segment, or small multiples.

## Slope, waterfall, bullet: the rendered specials

- Slope: two periods, up to about 8 entities, names and values at both ends. The line the headline is about in the accent, the rest muted.
- Waterfall: one starting total, up to about 7 steps, one closing total. Steps in the order the story tells them; largest first when the order is free.
- Bullet: one measure, one target, an optional range band. Several bullets stack vertically on the same scale.
- Spec format: chart-spec.md. Placement: `![alt text](charts/name.png)` under the headline.

## Tables

- When: exact values people will look up, or text next to numbers (owner, status, amount) that no chart holds.
- Limit: 9 rows and 6 columns on a slide; the builder warns beyond that. The full table is an appendix slide or an attached file.
- Formatting rules are in "Tables on slides" below.

## What to avoid and why

| Avoid | Why | Use instead |
|---|---|---|
| 3D charts | Perspective distorts lengths and angles; the front slice always looks bigger. | Flat bars or a flat pie. |
| A pie with more than 5 slices, or two pies to compare | Thin angles cannot be read; two pies cannot be compared slice by slice. | Sorted `barh` of shares; two periods as two series. |
| Dual axes | Two scales on one plot let any crossing point be manufactured by choosing the scales. | Two charts on a shared time axis, or both series indexed to 100. |
| Truncated bar axes | Bar length stops meaning value; a 2 percent gap looks like a collapse. | Start at zero, or chart the differences as their own bars. |
| Rainbow palettes | Nothing stands out because everything does; colour-blind readers lose categories. | The theme palette in order, or one accent and the muted colour. |
| Spaghetti lines (5 or more series) | Lines cross, colours run out, the legend takes over. | One series in the accent, or small multiples. |
| Stacked area for absolute comparison | Only the bottom series sits on a flat baseline; every other series is read against a moving one. | Lines, or small multiples. Stacked area only for the total with a sense of mix. |
| Radar charts | Area depends on the axis order; readers cannot compare shapes. | Sorted bars, or a table. |
| Doughnut with a number in the middle | Decoration when the share is not the message; the ring adds nothing to the number. | Big-number layout. Keep the doughnut only when the share itself is the headline. |
| Gauges | One number drawn as a speedometer: no comparison, no history, a lot of ink. | A big number with a comparison, or a bullet against the target. |
| Word clouds | Word size is unreadable as a value; long words look bigger. | Ranked bars of the top 10 terms. |
| Animated builds that reveal data step by step | The audience cannot compare what is not yet on screen; the file breaks in viewers and print. | Show the whole chart. Emphasise with colour, not with time. |

## Native or rendered

1. Native (a fenced `chart` block) for bar, barh, stacked, barh-stacked, line, area, pie and doughnut when the chart may be edited in PowerPoint later: the numbers, the colours, the fonts. Native charts also follow the theme through the builder, and `deck_inspect.py` reads their data back for review. In the HTML deck the same block is drawn as inline SVG, which stays sharp at any zoom and prints cleanly.
2. Rendered (`chart_render.py`, placed as a picture) for waterfall, slope, lollipop, bullet, small multiples, scatter, annotated line, heatmap and ranked bar with highlight.
3. Rendered also when a native type needs something the block cannot express: a target or average line, a shaded period, a note on a point, one line in the accent among muted lines.
4. Native `highlight` covers the common case: one series, the named categories in the accent, the rest grey. Reach for it before a rendered chart.
5. When both work, prefer native. A picture of a chart cannot be corrected by the user the evening before the meeting; a native chart can.
6. Mixing is fine. A native bar on slide 4 and a rendered waterfall on slide 5 look alike because both take colours and fonts from the same theme.json.

## Big numbers

A single number beats a chart when the message is the number itself: a total, a growth rate, a count, a date. A chart with one bar is a number wearing a costume.

Give the number context with the `big-number` layout's `- value | label | detail` items:

- Value: the number, two significant digits, unit attached ("12.4 M", "61%", "2x").
- Label: what it is ("Revenue growth").
- Detail: the comparison, the period and the direction ("up from 10.5 M, FY2025 against FY2024").

Up to four numbers on one slide; three read best. Put related numbers together (growth, share, count), not four unrelated facts. A number with no comparison is a fact without a meaning: "18 percent" says nothing until "against 11 percent last year" sits next to it.

```markdown
## Three numbers to remember
layout: big-number
- 18% | Revenue growth | year on year, FY2025
- 61% | Subscription share | of total revenue, up from 52
- 2x | Enterprise customers | 52 to 104 in twelve months
Source: Finance close, August 2026
```

## Tables on slides

A table is right when people will read individual values, compare two dimensions at once, or need text next to numbers. It is wrong when the message is a pattern; a pattern needs a chart.

1. Header row: names with the unit, "Revenue (EUR M)", so the cells hold plain numbers.
2. Numbers: one decimal, thousands separators, the same decimals down a column so the digits line up. Numbers belong right-aligned; the builder aligns every cell the way the theme aligns text, so keep units out of the cells and decimals consistent to get the same effect.
3. The row that matters: wrap its cells in `**` so it is bold. One row, not three.
4. Sort the rows by the column the headline is about, unless the order carries meaning.
5. Size: 9 rows by 6 columns at most, header included. The builder uses 16 pt up to 5 rows, 14 pt up to 7 and 12 pt beyond; fewer rows read better from the back of the room.
6. Totals last, bold. Percent columns name the base in the header ("Share of tickets, %").
7. The full table (the 40 rows, the 12 columns) goes to an appendix slide or an attached file. The slide gets the rows that carry the point.

## Three messages, one dataset

Quarterly revenue by tier, FY2025, EUR M:

| Tier | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| Enterprise | 3.1 | 3.4 | 3.9 | 4.6 |
| Business | 2.8 | 2.9 | 2.9 | 3.0 |
| Starter | 1.9 | 1.8 | 1.6 | 1.5 |
| Total | 7.8 | 8.1 | 8.4 | 9.1 |

### Message 1: Enterprise supplied all of the growth

Headline: "Revenue grew 17 percent in 2025, and Enterprise supplied all of it". This is the composition of a change, so a rendered waterfall from the Q1 total to the Q4 total: start bar 7.8, steps Enterprise +1.5, Business +0.2, Starter -0.4, end bar 9.1. The Enterprise step in the accent, the other steps muted, both totals in the text colour. Placed with `![Waterfall from 7.8 to 9.1 M: Enterprise +1.5, Business +0.2, Starter -0.4](charts/growth-bridge.png)`.

Takeaway: Business is flat and Starter is shrinking; the growth plan rests on one tier.

### Message 2: Enterprise is now half of revenue

Headline: "Enterprise passed half of revenue in Q4". A share of one whole with three parts: sorted horizontal bars of the Q4 shares with Enterprise highlighted. A three-slice pie is acceptable; the bars make the 50 percent mark easier to judge.

```chart
{"type": "barh", "categories": ["Enterprise", "Business", "Starter"],
 "series": [{"name": "Share of Q4 revenue", "values": [0.51, 0.33, 0.16]}],
 "data_labels": true, "number_format": "0%", "highlight": ["Enterprise"], "legend": false}
```

Source: Finance close, January 2026. Shares of 9.1 M Q4 revenue.

### Message 3: Starter is shrinking every quarter

Headline: "Starter revenue has fallen for three straight quarters". Change over time, four periods, one series: columns in time order, every column labelled, nothing sorted. The other tiers are left out because the sentence is about one.

```chart
{"type": "bar", "categories": ["Q1", "Q2", "Q3", "Q4"],
 "series": [{"name": "Starter revenue, EUR M", "values": [1.9, 1.8, 1.6, 1.5]}],
 "data_labels": true, "number_format": "0.0", "legend": false}
```

Takeaway: At this rate Starter drops below 1.2 M by mid-2026; decide whether to fix it or fold it.

Same numbers, three charts, because three different sentences. The 4 by 5 table itself belongs on an appendix slide for anyone who wants to check the arithmetic.
