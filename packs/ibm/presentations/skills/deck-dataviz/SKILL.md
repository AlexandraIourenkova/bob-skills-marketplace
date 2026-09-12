---
name: deck-dataviz
description: Make the charts of a presentation say one thing and look like part of the deck. Chooses the chart from the message rather than the data shape, writes native PowerPoint chart blocks for bar, line, area and pie, and renders waterfall, slope, lollipop, bullet, small multiples, scatter and heatmap charts to PNG in the deck's theme colours with matplotlib, offline. Use when a slide needs a chart or a graph, when a chart is unreadable or cluttered, when the user asks which chart to use, how to visualise numbers, wants to highlight one bar or add a target line, or says "как показать эти данные", "сделай график", "перерисуй диаграмму".
---

# deck-dataviz

One chart, one message, and the slide headline states it. Charts live in a storyboard slide either as a native chart block (editable in PowerPoint) or as a rendered PNG.

## 1. Write the finding first

Before choosing a form, write the sentence the chart must prove: "Every quarter of 2026 beat the same quarter of 2025", not "revenue by quarter". That sentence becomes the slide headline. `references/chart-choice.md` maps message types to charts, says how many categories or series each form takes, and lists what to avoid and why.

## 2. Native or rendered

**Native** (`bar`, `barh`, `stacked`, `barh-stacked`, `line`, `area`, `pie`, `doughnut`) goes straight into the storyboard and stays editable in PowerPoint:

````markdown
## Every quarter of 2026 beat the same quarter of 2025
```chart
{"type": "bar", "categories": ["Q1", "Q2", "Q3", "Q4"],
 "series": [{"name": "2025", "values": [10.2, 11.0, 12.4, 13.1]}, {"name": "2026", "values": [11.9, 13.4, 14.6, 15.5]}],
 "data_labels": true, "number_format": "0.0"}
```
Source: Finance close, August 2026
````

`"highlight": ["Q4"]` draws one category in the accent colour and greys the rest (single series). `"annotations": [{"category": "Q3", "text": "Launch"}]` adds one short note with a leader line, and `"target": {"value": 12, "label": "Plan"}` a dashed reference line; both are for the chart that carries the argument, not for every chart. Crowded category labels lean on their own. The builder applies the theme palette, 12 pt chart text, no chart title (the headline is the title) and a legend only when there is more than one series.

**Rendered** for waterfall, slope, lollipop, bullet, small multiples, scatter, heatmap, donut with a centre number, and for any chart that needs annotations or a target line:

```bash
uv run --with matplotlib python scripts/chart_render.py deck/charts/bridge.json --theme deck/theme.json -o deck/charts/bridge.png
```

Then `![Revenue bridge FY2025 to FY2026](charts/bridge.png)` in the storyboard. Full content width is 11.5 x 5.2 in (the default); next to bullets use `"size": [7, 5.2]`. Every key is in `references/chart-spec.md`; keep the spec file next to the PNG so the chart can be changed and re-rendered.

## 3. Make it readable

`references/chart-makeover.md` is the procedure: cut what does not serve the message, sort unless the order carries meaning, emphasise one thing in the accent colour and grey the rest, label directly instead of a legend, start bars at zero, put units in the subtitle, annotate the event, and keep 12 pt as the floor for anything the audience reads. It also has the before-and-after table for a chart the user already has, and the ten-item pre-flight checklist.

## 4. When a chart is the wrong answer

One number with context belongs on a `big-number` slide, not in a chart. Exact values people will look up belong in a `table` slide (nine rows and six columns at most; the full table goes to the appendix). A process belongs in a `timeline` slide. `references/chart-choice.md` says when each applies.

## 5. Check before building

Read the finding and the chart together: does the picture prove the headline in five seconds? Then confirm the numbers against the source, name that source in `Source:`, and put the caveat in `Notes:`. After the deck is built, `deck_inspect.py` prints every chart's categories and series so you can compare them with the data.
