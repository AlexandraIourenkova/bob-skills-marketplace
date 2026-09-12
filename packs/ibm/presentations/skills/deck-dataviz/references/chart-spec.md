# Chart spec for chart_render.py

`scripts/chart_render.py spec.json --theme theme.json -o charts/name.png` renders one chart from a JSON spec in the deck's colours and fonts. Use it for the types PowerPoint cannot draw natively (waterfall, slope, lollipop, bullet, small multiples, scatter, heatmap) and for bar or line charts that need annotations, a target line or a highlighted element. Native charts (bar, line, area, pie, doughnut) go into the storyboard as ```` ```chart ```` blocks instead; their keys are the first table below, minus the rendering ones.

## Keys shared by all types

| Key | Type | Meaning |
|---|---|---|
| `type` | string | `bar`, `barh`, `stacked`, `line`, `area`, `slope`, `waterfall`, `lollipop`, `bullet`, `small-multiples`, `scatter`, `heatmap`, `donut` |
| `title` | string | drawn above the chart; leave empty when the slide headline is the finding (the usual case) |
| `subtitle` | string | what is measured, unit, period: "Revenue, USD M" |
| `categories` | list | the x categories (or y for horizontal types) |
| `series` | list or object | `[{"name": "2025", "values": [..]}]` or `{"2025": [..]}`; one value per category |
| `number_format` | string | Python format such as `"{:,.0f}"`, `"{:.1f}"`, `"{:.0f}%"`, or Excel-style `"0"`, `"0.0"`, `"0%"` |
| `unit` | string | appended to every number label: `" M"`, `" K"` |
| `labels` | bool | value labels on bars and points (default true for bars, false for lines) |
| `highlight` | list | categories (names or zero-based indexes) drawn in the accent colour while the rest go grey; for `slope` and `scatter`: series or point names |
| `highlight_series` | string | `line`, `area`, `small-multiples`: this series in the accent, the others grey |
| `sort` | string | `asc`, `desc` or `none` (single series bars and lollipops; default `desc` for lollipop) |
| `target` | number or object | reference line: `12` or `{"value": 12, "label": "Plan"}` |
| `average` | bool | `line`: a dotted average line of the first series |
| `annotations` | list | `[{"category": "Q3", "text": "Launch", "series": "2026"}]`: a note with a leader line at that point |
| `source` | string | footnote "Source: ..." under the chart |
| `size` | list | `[width, height]` in inches; default 11.5 x 5.2 (full content width), use 7 x 5.2 next to bullets |
| `dpi` | int | default 200 |
| `transparent` | bool | no background fill, for placing over a coloured slide |

Colours never go into the spec: they come from `theme.json` (`colors.chart` for series in order, `colors.accent` for highlights, `colors.accent2` for targets and the negative case, `colors.muted` for de-emphasis). Font: `fonts.body` when installed, otherwise Helvetica, Arial or DejaVu Sans.

## Per type

**bar, barh, stacked.** Categories and one or more series. `highlight` works with one series. Stacked draws values inside the segments. Bars start at zero; the axis is never truncated.

```json
{"type": "barh", "subtitle": "Growth by tier, percent", "categories": ["Enterprise", "Team", "Self-serve", "Services"],
 "series": [{"name": "Growth", "values": [104, 31, 2, -9]}], "highlight": ["Enterprise"], "number_format": "{:.0f}%",
 "sort": "desc", "target": {"value": 40, "label": "Plan"}}
```

**line, area.** Up to four series before it becomes spaghetti; then `highlight_series` one and grey the rest, or use small multiples. Series names are written at the line ends, so no legend. `labels: true` puts values on the points of the highlighted (or only) series.

```json
{"type": "line", "subtitle": "Monthly active users, thousands", "categories": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
 "series": {"Enterprise": [20, 22, 25, 29, 33, 38], "Team": [30, 31, 31, 33, 34, 34]}, "highlight_series": "Enterprise", "labels": true}
```

**slope.** Exactly two categories (the two periods) and one series per entity; `highlight` names the entities to emphasise. Best for "who moved up and who moved down between two years".

```json
{"type": "slope", "subtitle": "Retention at month 12", "categories": ["2025", "2026"],
 "series": {"Enterprise": [91, 94], "Team": [80, 78], "Partners": [60, 72]}, "highlight": ["Partners"], "number_format": "{:.0f}%"}
```

**waterfall.** One series; the first category is the starting total, `totals` names the other total bars (usually the last). Positive steps in the first chart colour, negative in the second accent, totals grey.

```json
{"type": "waterfall", "subtitle": "Revenue bridge FY2025 to FY2026, USD M", "categories": ["FY2025", "Enterprise", "Team", "Services", "FY2026"],
 "series": [{"name": "", "values": [46.7, 7.9, 1.2, -0.5, 55.3]}], "totals": ["FY2025", "FY2026"], "number_format": "{:.1f}"}
```

**lollipop.** A ranked comparison with less ink than bars; one series, sorted by default, `highlight` for the one that matters, `target` for a vertical reference line.

**bullet.** Progress against a target with qualitative bands. No categories or series; instead `bullets`, one per row: `label`, `value`, `target` (optional), `max`, `ranges` (three upper bounds for the bands, optional).

```json
{"type": "bullet", "subtitle": "Q3 targets", "bullets": [
  {"label": "Time to value, days", "value": 34, "target": 30, "max": 60, "ranges": [30, 45, 60]},
  {"label": "Enterprise logos", "value": 12, "target": 15, "max": 20}]}
```

**small-multiples.** Many series with the same shape, one small panel each with shared axes; `kind` is `line` (default) or `bar`; `highlight_series` colours one panel. Up to twelve panels.

**scatter.** No categories; `points`: `[{"x": 2, "y": 120, "label": "Acme", "size": 3, "group": "Retail"}]`, plus `x_label`, `y_label`, optional `x_target` and `y_target` reference lines, `highlight` by point label. Labels are drawn for up to fifteen points, or only the highlighted ones.

**heatmap.** `rows`, `columns` and a `values` matrix; cells shaded from the background to the accent, values printed in each cell. Good for cohorts and matrices up to about 8 x 8.

**donut.** One series, at most five parts, `highlight` for the part the headline is about, `center` for the number in the middle. Above five parts use a sorted bar.

## Placing the picture

Write the PNG to `deck/charts/` and reference it from the storyboard: `![Revenue bridge FY2025 to FY2026](charts/bridge.png)`, alone on a `chart` slide (full width) or under bullets (side by side, use `size: [7, 5.2]`). Put the finding in the slide headline, the so-what in `Takeaway:`, the source in `Source:` (or in the spec, not both). Rendered charts are pictures: keep the spec file next to the PNG so the chart can be changed and re-rendered.
