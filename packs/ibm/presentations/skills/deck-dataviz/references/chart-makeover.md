# Chart makeover: make one chart say one thing

This file is the procedure for turning a draft chart into a slide chart: one message, readable from the back of the room, in the deck's theme. Read it after chart-choice.md has settled the form and before writing the final fenced `chart` block or `chart_render.py` spec. Read it also when the user hands over an existing chart (a picture, a PowerPoint chart, an Excel sheet) and asks for it to be improved; the last sections cover that case. The rules assume the pack's builder: the slide headline is the chart's title, `Takeaway:` and `Source:` lines sit under the chart, and every colour comes from the chosen theme.json (`colors.chart` for series, `colors.accent` for the one thing, `colors.muted` for the rest).

## The procedure

1. State the message. One sentence with the number in it: "Churn fell from 6.1 to 3.4 percent after March". This is the slide headline. Everything in the chart serves it.
2. Choose the form with chart-choice.md. A draft that cannot show the sentence changes form; it does not get decorated.
3. Cut what does not serve the message: series the sentence does not mention (or fold them into "Other"), categories beyond the top 5 or top 10, borders, shadows, the legend when direct labels do the job, decimals beyond one. Native charts keep the builder's thin gridlines; on rendered charts keep at most light horizontal gridlines.
4. Order. Sort bars by value, largest first, unless the order carries meaning: time, a scale (small to large), the stages of a process. Time stays in time order even when a sorted version looks tidier.
5. Emphasise one thing. The series or point the headline is about gets the theme's accent; everything else goes to the muted colour. Bold its label. Native: `"highlight": ["Q4"]` on a single series. Rendered: the emphasis keys in chart-spec.md.
6. Label directly. Series names at the end of lines, data labels on bars when there are 8 or fewer, the value on the highlighted point at least. No legend when the labels carry the names: `"legend": false`.
7. Axis. Bars start at zero, always. Lines may start above zero when the movement is the message; say so in the footnote. Units and scale go in the headline or the axis title ("EUR M", "percent of tickets"). Round tick values (0, 5, 10, not 0, 4.7, 9.4). No dual axes: two charts, or both series indexed to 100.
8. Words. The title is the finding, which is the slide headline, so the chart's own title stays empty. The subtitle is what is measured and the period: on a rendered chart its subtitle line, on a native chart the `Source:` line or the headline itself. The footnote is the source and the caveats: the `Source:` line.
9. Annotate. A short note on the event, the target line or the outlier: "Onboarding flow changed", "Target 4.0". Rendered charts only; a native chart that needs a note becomes a rendered one.
10. Colour. The theme's chart palette in order; the accent for the one thing; the muted colour for the rest. Colour-blind safe pairs (blue and orange, not red and green). Meaning never by colour alone: a label or a marker carries it too.
11. Size and fonts. Nothing inside the chart below 12 pt; 14 pt is better for the labels that carry the message. The chart fills the slide width on a `chart` layout, or the 60 percent column when bullets share the slide. Category names short enough to stay on one line.
12. Check, then place. Squint test: blurred, does the accent element still stand out? Read the headline and the chart together: does the chart prove the sentence? Then put the block or picture in the storyboard under the headline with a `Takeaway:` line (the so-what) and a `Source:` line (where the numbers come from).

## What the builder already does

Know this before fighting it. For a native `chart` block, `deck_build.py`:

- Sets the chart font to the theme body font at 12 pt, with tick labels, data labels and the legend at 11 pt. Keep names short; there is no room to shrink.
- Draws thin gridlines on the value axis in the theme's line colour and none on the category axis; the value axis line itself is invisible.
- Colours series in `colors.chart` order. The first series gets the first palette colour, so list the important series first.
- Shows a legend at the bottom (right for pies) whenever there is more than one series, or the chart is a pie. `"legend": false` turns it off.
- Puts data labels outside the end of bars, above points on lines, centred in stacked segments, and as percentages on pie slices. `number_format` formats both labels and axis ticks.
- Draws `barh` categories top to bottom in storyboard order, and paints `highlight` categories in the accent with the rest faded, for a single series.
- Draws the `title` key at 14 pt bold above the plot when present. Leave it out; the headline is the title.

## Before and after

| Flaw | What it looks like | Fix |
|---|---|---|
| Topic title | "Revenue by quarter" above the chart | Headline states the finding: "Revenue grew 17 percent, all of it in Enterprise". Chart title empty. |
| Legend hunting | Six coloured lines, a legend in the corner, eyes bouncing between them | Names at the line ends, or one line in the accent and the rest muted, legend off. |
| Rainbow bars | Every bar a different colour with no meaning | All bars in one palette colour; the one that matters in the accent. |
| Truncated axis | Bars starting at 80 so a 3 percent gap fills the slide | Axis from zero; if the gap is the message, chart the differences instead. |
| Unsorted bars | Regions in alphabetical order, the reader ranking them by eye | Sorted by value, largest first, "Other" last. |
| Too many decimals | 12.437, 11.982, 13.051 | 12.4, 12.0, 13.1: one decimal, the same in every label. |
| Spaghetti lines | Eight series crossing each other | Small multiples with the same axes, or one series in the accent and seven in grey. |
| Pie with nine slices | Slices too thin to label, colours repeating | Sorted horizontal bars, top 5 plus "Other". |
| Dual axis | Revenue on the left, margin on the right, lines crossing where the scales put them | Two charts on a shared time axis, or both indexed to 100. |
| Chart junk | 3D bars, shadows, a bordered plot area, a background gradient | Flat bars, no border, no shadow, the slide background showing through. |

## Emphasis techniques

Pick one, at most two, per chart:

- Highlight one category and grey the rest. Native: `"highlight": [...]`. Rendered: the ranked bar with highlight, or the emphasis keys in chart-spec.md.
- A reference line for the target or the average, labelled at its end: "Target 4.0", "Average 2.8". Rendered.
- A shaded band for a period: "Pilot, March to May". Rendered annotated line.
- A note on one point, six words or fewer, placed next to the point and not over the data. Rendered.
- Small multiples with the same axes, the panel the headline is about first or in the accent. Rendered.
- An "Other" bucket for the long tail: the top 5 in full colour, "Other" last in the muted colour, its contents listed in the `Source:` line.
- The headline repeats the highlighted value, so the chart and the sentence confirm each other.

## Number formatting on slides

| Rule | Do | Not |
|---|---|---|
| Two significant digits | 12 M, 1.2 M, 18 percent, 0.85 | 12.437 M, 18.27 percent |
| A third digit only when it is the message | 12.4 against 12.1 | 12.4 against 9 |
| Thousands separators | 1,240 and 12,400 | 1240, 12400 |
| Units once | "EUR M" in the headline or the axis title, plain numbers in the labels | "3.1 M", "3.4 M", "3.9 M" on every bar |
| Percent with the base named | "61 percent of revenue", "of 1,240 tickets" | "61 percent" alone |
| Negative numbers with a sign | -0.4, and a muted or second palette colour if colour helps | (0.4), or red alone |
| Consistent decimals within a chart | 1.9, 1.8, 1.6, 1.5 | 1.9, 1.75, 1.6, 1.5 |
| Round tick values | 0, 2, 4, 6 | 0, 1.7, 3.4, 5.1 |

Excel format strings for `number_format`, which the builder applies to labels and axis ticks:

- `"0"` whole numbers, `"0.0"` one decimal, `"#,##0"` thousands separators, `"0%"` percentages from fractions (0.51 shows as 51%).
- `"0.0\" M\""` attaches a unit to every value when the labels stand alone; use it sparingly, the unit usually belongs in the headline.
- `"+0.0;-0.0;0"` shows the sign on both gains and losses, for charts of changes.

## Accessibility

- Contrast: text and lines must stand out from the slide background. The theme's chart palette is checked against the theme background when the theme is built (deck-style). What you add on top is yours to check: annotation text, reference lines, any grey you choose for muted elements.
- Colour-blind safe pairings: blue and orange, blue and grey, dark and light of one hue. Not red and green, not green and brown. Two series that must be told apart get different markers or line styles as well as different colours.
- Print and greyscale: direct labels and markers carry the meaning, so the chart still reads when the colour is gone. Patterns on bars are a last resort; labels are better.
- Alt text for rendered charts: the message and the key numbers, in the image's alt text: `![Churn fell from 6.1 to 3.4 percent between January and June 2026](charts/churn.png)`. The builder stores it for screen readers. Native charts are read as data by screen readers, so the headline and the `Takeaway:` carry the message for them.
- Minimum sizes: 12 pt for any text in a chart, 2 pt for lines, 7 pt for markers, bars wide enough that a label fits on them. If a chart needs smaller text to fit, it has too much in it.

## Presentation rules

- One chart per slide. Two only when they share an axis and a message (before and after, two regions on the same scale); the `chart` layout places them side by side, and both get the same y scale.
- The chart's title is the slide headline. Leave the `title` key out of the block and the title empty in a rendered spec.
- The legend goes away when direct labels exist. It stays only for a multi-series native chart where end labels are not possible.
- Animate nothing. No builds, no transitions, no reveals. The whole chart is on screen from the start.
- The same measure keeps the same scale and colour across consecutive slides; the audience compares slide 5 with slide 4.
- The `Takeaway:` line says the so-what, not what the chart shows: "The growth plan rests on one tier", not "Enterprise grew the most".
- The chart must stand alone in the exported PDF. The speaker notes explain, they do not complete.
- Chart text is in the deck's language, including axis titles and "Other".

## A makeover, start to finish

The draft the user sent: a clustered column chart titled "Support tickets", twelve products on the x axis, three years as three series, a legend on the right, values to two decimals, a different colour for every year. The sentence the user wants on the slide: "Two products cause 80 percent of tickets".

What changes, step by step:

1. Message: "Payroll and Invoicing cause 80 percent of support tickets". That is the headline.
2. Form: a ranking with a share in it, so sorted horizontal bars with the top two highlighted (chart-choice.md, "compare many values").
3. Cut: three series become one, because the sentence is about 2025. Twelve products become the top 5 plus "Other". Two decimals become whole numbers with a separator. The legend goes; the bars are named.
4. Order: by ticket count, largest first, "Other" last.
5. Emphasis: Payroll and Invoicing in the accent, the rest faded.
6. Words: the chart title moves to the headline; the base and the contents of "Other" go to the `Source:` line.

The result in the storyboard:

```chart
{"type": "barh", "categories": ["Payroll", "Invoicing", "Ledger", "Expenses", "Payments", "Other (7 products)"],
 "series": [{"name": "Tickets, 2025", "values": [620, 372, 58, 41, 36, 113]}],
 "data_labels": true, "number_format": "#,##0", "highlight": ["Payroll", "Invoicing"], "legend": false}
```

Takeaway: Fixing the top issues in two products halves the queue; the other ten can wait.
Source: Support desk export, tickets closed in 2025, 1,240 in total. Other: Timesheets, Reports, Inventory, Mobile, Portal, Integrations, Admin.

The three-year trend the draft tried to show at the same time is a second sentence ("Payroll tickets doubled since 2023") and gets its own slide, as a line chart of one series, if the story needs it.

## Placing the chart on the slide

The builder offers three placements. Pick by how much the chart needs to say on its own.

| Placement | Storyboard | When | Consequence for the chart |
|---|---|---|---|
| Full width | The block or picture alone under the headline; the `chart` layout is chosen automatically | Most charts; anything with more than 6 categories or more than one series | The chart has the whole content area; labels fit; up to 12 categories. |
| Beside bullets | Two or three bullets plus the block or picture; bullets take the left 40 percent, the chart the right 60 percent | The chart needs a reading: three short lines that say what to see, not a repeat of the data | Narrower plot: about 8 categories at most, short names, `barh` rather than `bar` for long names. |
| Two side by side | Two blocks or two pictures under one headline on the `chart` layout | Before and after, or two regions on the same scale, under one sentence that covers both | Each chart gets half the width; same y scale, same colours, no more than 6 categories each. |

A chart beside bullets, in the storyboard:

````markdown
## Payroll and Invoicing cause 80 percent of support tickets
- 992 of 1,240 tickets closed in 2025
- Both products ship fixes for their top three issues in Q1
- The other ten products share 248 tickets
```chart
{"type": "barh", "categories": ["Payroll", "Invoicing", "Ledger", "Expenses", "Payments", "Other (7 products)"],
 "series": [{"name": "Tickets, 2025", "values": [620, 372, 58, 41, 36, 113]}],
 "data_labels": true, "number_format": "#,##0", "highlight": ["Payroll", "Invoicing"], "legend": false}
```
Takeaway: Two fixes halve the queue.
Source: Support desk export, tickets closed in 2025.
````

Bullets and chart must agree to the digit. If a bullet says 992 and the bars say 620 and 372, the audience adds them up; make sure they get 992.

## When the user hands you an existing chart

1. Read it. Write the sentence the chart currently supports, and the sentence the user wants it to support. Often they differ, and that gap is the whole makeover.
2. Get the numbers. A native chart inside a .pptx: `deck_inspect.py deck.pptx --json` prints categories and series per slide. An Excel or CSV source: read the range. A picture only: read the values off its labels, and ask for the data behind it when the labels are missing or the chart is too small to read.
3. Check the numbers. Shares that sum to 96, a total that does not match its parts, a period missing from the axis: say so before drawing anything, and ask which source is right.
4. List the problems, using the before and after table as the checklist: title, legend, colour, axis, order, decimals, junk. Three to six lines, each naming the flaw and the fix.
5. Propose the rebuild. Either a native `chart` block from the extracted data, written out in full with the headline, or a rendered chart when the message needs a target line, an annotation, a waterfall or a slope. Say which and why in one line.
6. Keep the original untouched. The rebuilt chart goes into the storyboard and the new deck (`deck_build.py -o new-deck.pptx`). The user's file is read, never written. If the user wants the chart back in their own deck, hand over the built slide and let them paste it.
7. Show the pair. Put the user's chart and the rebuilt one side by side once, in the reply or on a scratch slide, so the change is visible and the user can say which sentence they meant.

## Pre-flight checklist

Run on every chart before building the deck. Ten yes or no questions; any "no" is a fix, not a note.

1. Can I say the headline sentence by looking at the chart alone?
2. Is there exactly one accent element, and is it the one the headline names?
3. Do the bars start at zero, and does the line chart say so in the footnote when it does not?
4. Is the order meaningful: sorted by value, or in time or scale order?
5. Are the unit and the period stated once, in the headline, the axis title or the `Source:` line?
6. Is every label 12 pt or larger and on one line?
7. Is the legend off where direct labels exist, and on where they do not?
8. Do the decimals match across every label, at two significant digits?
9. Does the chart survive greyscale, with meaning carried by labels or markers rather than colour alone?
10. Does the slide have a `Source:` line, and a `Takeaway:` line that says the so-what?
