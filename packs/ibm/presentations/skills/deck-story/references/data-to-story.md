# From data to a story

This file turns a spreadsheet, CSV, database extract or written analysis into three to five findings and a storyline. Read it when the user's material is numbers rather than an argument: a sales export, a survey, an experiment log, a cost report. It runs in six steps: inventory the data, profile it with the script, look for findings through six lenses, rank them, write one slide per finding, arrange the slides into an arc. The output is a storyboard that the presentation skill builds.

## Step 1: inventory

Before any analysis, write down what the data is. Five facts, one line each:

| Fact | What to record | Example |
|---|---|---|
| What | The measure and the entity | Revenue in EUR by customer tier |
| Grain | What one row is | One row = one tier in one quarter |
| Period | First and last date, and the calendar (fiscal or civil) | Q1 2024 to Q4 2025, fiscal equals civil |
| Source | System, report, extract date, owner | Finance close extract, 8 January 2026, FP&A |
| Caveats | What is known to be wrong or partial | Q4 2025 is preliminary; refunds not deducted |

When any of these is unclear, ask the user, in one message:

1. What does one row represent?
2. Which column is the date, and is the last period complete?
3. Are the numbers gross or net, and in which currency or unit?
4. Where did the file come from, and may the deck name the source?
5. Is there a plan, budget or target to compare against?
6. What decision will the audience make with these numbers?

The last question decides which findings matter. A finding that does not touch the decision goes to the appendix.

## Step 2: profile

Run the profiler on the file. It reads the file, prints to stdout and touches nothing else.

```bash
uv run --with pandas python scripts/data_profile.py data.csv
uv run --with pandas --with openpyxl python scripts/data_profile.py book.xlsx --sheet Revenue
uv run --with pandas python scripts/data_profile.py data.csv --date-column period --max-categories 5 --json -o profile.json
```

It prints:

- The shape (rows and columns) and the file name.
- Per column: dtype, non-null count and missing percentage. Numeric columns get min, median, mean, max and sum. Text columns get the distinct count and the top categories with counts and shares (`--max-categories`, default 8). Text that is really numbers ("1,200", "12%") is read as numbers.
- When a date column is detected from its name (date, period, month, quarter, year) or given with `--date-column`: the period covered and, for every numeric column, totals per period. The grain is chosen from the span: months under a year, quarters up to three years, years beyond. The last two periods are compared with the absolute and the percentage change.
- When a text column looks like a row label (mostly distinct values, such as a customer or product name): the top 3 and bottom 3 rows for each numeric column.

Options: `--sep ";"` for semicolon CSVs (the default detects the delimiter), `--sheet NAME` for Excel (needs openpyxl), `--json` for machine-readable output, `-o path` to write the report to a file. Read the profile before writing anything: missing values, period boundaries and the top categories are where most findings, and most mistakes, live.

## Step 3: six lenses for findings

Run each lens over the profile and the data. Write every candidate finding as a one-line headline with its number. Expect ten to fifteen candidates; Step 4 cuts them.

### Lens 1: change over time

Ask: what moved between the first and the last period, and was the move steady or a step?

```python
by_q = df.groupby(["quarter", "tier"])["revenue"].sum().unstack()
growth = (by_q.iloc[-1] / by_q.iloc[0] - 1) * 100
```

Headline pattern: "X grew N percent over the period while Y fell M percent"; "SMB fell in six of seven quarters".

### Lens 2: comparison against a benchmark or plan

Ask: where is actual above or below plan, budget, last year or the market, and by how much?

```python
gap = df.assign(gap=df["actual"] - df["plan"], gap_pct=(df["actual"] / df["plan"] - 1) * 100)
gap.sort_values("gap_pct")
```

Headline pattern: "Region X beat plan by N percent; region Y missed by M"; "Costs came in 4 percent under budget for the third year".

### Lens 3: ranking

Ask: who is first, who is last, and how far apart are they?

```python
rank = df.groupby("customer")["revenue"].sum().sort_values(ascending=False)
rank.head(5), rank.tail(5)
```

Headline pattern: "X is the largest Y at N, three times the median"; "The bottom ten products together sell less than the top one".

### Lens 4: share, part of whole

Ask: what part of the total do the biggest pieces make, and has that share moved?

```python
share = rank / rank.sum() * 100
share.cumsum().head(3)
```

Headline pattern: "Three customers are 60 percent of revenue"; "Enterprise is now 53 percent of revenue, up from 44".

### Lens 5: distribution and outliers

Ask: what is typical, how wide is the spread, and which rows sit far outside it?

```python
q1, q3 = df["ticket_hours"].quantile([0.25, 0.75])
outliers = df[df["ticket_hours"] > q3 + 1.5 * (q3 - q1)]
df["ticket_hours"].describe(percentiles=[0.5, 0.9, 0.99])
```

Headline pattern: "Half of tickets close in 4 hours; 5 percent take over a week"; "Two sites account for 80 percent of the outliers".

### Lens 6: relationship between two measures

Ask: when one measure moves, does the other move with it, and does that hold in every group?

```python
df[["discount_pct", "margin_pct"]].corr()
df.groupby("segment")[["discount_pct", "margin_pct"]].corr().unstack().iloc[:, 1]
```

Headline pattern: "Every 5 points of discount cost 3 points of margin"; "Onboarding time predicts churn only in the SMB tier". Write "is associated with", not "causes", unless the data comes from an experiment.

## Step 4: rank the findings

Score each candidate from 1 to 3 on four criteria and add the scores.

| Criterion | 1 | 2 | 3 |
|---|---|---|---|
| Relevance to the decision | Background | Informs the decision | Changes the decision |
| Surprise | The audience knows it already | Sharpens what they suspect | Contradicts what they believe |
| Size of effect | Under 5 percent, or noise | 5 to 20 percent | Over 20 percent, or a reversal |
| Confidence in the data | One source, partial period | Complete period, known caveats | Reconciled to finance, complete |

Keep the top three to five. A finding with confidence 1 needs a caveat in the notes or drops out. The rest go to an appendix section, one slide per finding, no notes. Never keep a high-surprise, low-confidence finding in the main story: it is the one they will remember and the one that turns out wrong.

## Step 5: one slide per finding

Every finding slide has the same five parts.

| Part | Rule | Storyboard line |
|---|---|---|
| Headline | The finding with its number, under 70 characters | `## Enterprise revenue grew 38 percent in 2025` |
| Evidence | One chart, or one small table; never both | a ```` ```chart ```` block, or `![...](charts/x.png)` |
| So-what | What it means for the decision | `Takeaway: Growth now depends on one tier` |
| Source | System, date, owner | `Source: Finance close extract, 8 January 2026` |
| Caveat | What the data cannot show, what is preliminary | `Notes: Q4 2025 is preliminary; refunds not deducted` |

Chart by finding type. Native chart blocks cover the first two rows; the rest are rendered with `deck-dataviz/scripts/chart_render.py spec.json --theme theme.json -o charts/name.png` and placed as pictures, where the spec's `"type"` key names the form (keys in deck-dataviz/references/chart-spec.md).

| Finding type | Chart | How |
|---|---|---|
| Comparison between categories | Sorted bar, the key bar highlighted | `{"type": "barh", "highlight": ["Enterprise"]}` |
| Change over time, many periods | Line, one series per group, four at most | `{"type": "line"}` |
| Composition of a change | Waterfall from the old total to the new | rendered, `{"type": "waterfall"}` |
| Two periods, several groups | Slope chart | rendered, `{"type": "slope"}` |
| Ranking of many items | Lollipop | rendered, `{"type": "lollipop"}` |
| Actual against a target | Bullet chart | rendered, `{"type": "bullet"}` |
| Same measure in several groups | Small multiples | rendered, `{"type": "small-multiples"}` |
| Relationship between two measures | Scatter with the outlier labelled | rendered, `{"type": "scatter"}` |

Use a pie only for one share against the rest, five slices at most. The headline states, the chart proves: number in the headline, chart under it.

## Step 6: arrange the arc

The data story arc has six slots. Map the ranked findings onto them.

| Slot | Content | Layout |
|---|---|---|
| Context | What was measured, the period, the total | `big-number` or `statement` |
| Hook | The most surprising finding, as a contrast or a question | `statement` or `chart` |
| Evidence 1 to 3 | The findings, in the order that builds the insight | `chart`, or `bullets` beside a chart |
| Insight | What the findings mean together; a sentence, not a chart | `statement` |
| Action | The decision, with a date | `closing` |
| Appendix | The full table, the method, the rejected findings | `table`, after the closing |

For an executive audience that wants the answer first, use SCQA instead: the context is the Situation, the hook is the Complication, the insight and the action are the Answer, and the evidence follows. Same slides, different order.

### Example: quarterly revenue by customer tier, two years

Data: 24 rows, one per tier per quarter, Q1 2024 to Q4 2025, EUR millions. Enterprise went from 13.9 to 19.2, Mid-market from 10.0 to 10.8, SMB from 7.4 to 6.2; the total from 31.3 to 36.2.

````markdown
# Growth now depends on one tier
Revenue review, FY2024 to FY2025, for the leadership team

## Revenue reached 36.2 M in 2025, up 16 percent
layout: big-number
- 36.2 M | Revenue 2025 | up from 31.3 M
- 16% | Growth | year on year
- 3 | Tiers | Enterprise, Mid-market, SMB
Source: Finance close extract, 8 January 2026
Notes: Set the base: 24 quarterly rows, two years, euros, net of discounts, before refunds.

## One tier did all the work
Enterprise added 5.3 M. Mid-market added 0.8 M. SMB lost 1.2 M.
Takeaway: Without Enterprise, revenue would have fallen.
Notes: This is the hook. Pause here before the evidence.

## Enterprise grew 38 percent with every quarter above the last
```chart
{"type": "line", "categories": ["Q1 24", "Q2 24", "Q3 24", "Q4 24", "Q1 25", "Q2 25", "Q3 25", "Q4 25"],
 "series": {"Enterprise": [3.1, 3.3, 3.6, 3.9, 4.2, 4.6, 5.0, 5.4],
            "Mid-market": [2.4, 2.5, 2.5, 2.6, 2.6, 2.7, 2.7, 2.8],
            "SMB": [2.0, 1.9, 1.8, 1.7, 1.7, 1.6, 1.5, 1.4]}, "unit": "M EUR"}
```
Takeaway: Enterprise growth is steady, not one large deal.
Source: Finance close extract, 8 January 2026
Notes: Eight quarters of growth. The largest single customer is 6 percent of the tier, so it is not one deal.

## SMB fell 16 percent and has not grown in a single quarter
![Slope chart: 2024 to 2025 revenue by tier](charts/tier_slope.png)
Takeaway: A slow, steady decline points to churn, not to one event.
Source: Finance close extract, 8 January 2026
Notes: Rendered with chart_render.py from a slope spec. The data shows the decline, not its cause; the churn analysis is in the appendix.

## Enterprise is now 53 percent of revenue, up from 44
![Waterfall: 31.3 M in 2024 to 36.2 M in 2025 by tier](charts/change_by_tier.png)
Takeaway: One tier carries the growth and half the revenue: a concentration risk.
Source: Finance close extract, 8 January 2026
Notes: Waterfall from 31.3 to 36.2: Enterprise plus 5.3, Mid-market plus 0.8, SMB minus 1.2.

## The growth is real, and it is fragile
layout: statement
Two years of data show one tier growing, one flat, one shrinking. The plan assumed three growing.
Notes: The insight slide has no chart. Say what the three findings mean together.

## Fund Enterprise onboarding now; decide on SMB by 31 October
layout: closing
- Approve two enterprise onboarding hires, 240 K a year
- SMB: fix or harvest, decided at the October review with churn data
- Owners: VP Sales (Enterprise), VP Customer Success (SMB)
Notes: Both asks follow from the concentration finding. Ask for the decision date first.

# Appendix

## Revenue by quarter and tier, EUR millions
layout: table
| Quarter | Enterprise | Mid-market | SMB | Total |
|---|---|---|---|---|
| Q1 2024 | 3.1 | 2.4 | 2.0 | 7.5 |
| Q2 2024 | 3.3 | 2.5 | 1.9 | 7.7 |
| Q3 2024 | 3.6 | 2.5 | 1.8 | 7.9 |
| Q4 2024 | 3.9 | 2.6 | 1.7 | 8.2 |
| Q1 2025 | 4.2 | 2.6 | 1.7 | 8.5 |
| Q2 2025 | 4.6 | 2.7 | 1.6 | 8.9 |
| Q3 2025 | 5.0 | 2.7 | 1.5 | 9.2 |
| Q4 2025 | 5.4 | 2.8 | 1.4 | 9.6 |
Source: Finance close extract, 8 January 2026
Notes: Reference slide, not presented; it is here so every headline can be checked against the rows.
````

Run `storyboard_check.py` on the result. Every finding slide should pass the number-with-source check; the hook and the closing should satisfy the opening and ending checks.

## Honesty rules

1. Show the base. Every percentage has its denominator on the slide or in the `Source:` line: "up 16 percent, from 31.3 M".
2. Bar charts start at zero. A truncated axis is allowed only on a line chart, and the slide says so.
3. Say what the data cannot show. A decline is not a cause; a correlation is not an effect. Put the limit in `Notes:` and, when it matters for the decision, on the slide.
4. Mark estimates and preliminary periods on the slide, not only in the notes: "Q4 2025 preliminary".
5. Do not cherry-pick the period. Use the full period in the file, or state why a window is used, and show the same window for every group.
6. Keep the full table in the appendix so anyone can check the headline against the rows.
7. One unit everywhere. Gross and net, EUR and USD, calendar and fiscal quarters do not mix on one slide.
8. State the count. Below about 30 rows per group, show the rows rather than an average.
9. Round for reading, compute from the unrounded values: one decimal in millions, whole percentages.

## The number the audience will remember

They will keep one number. Choose it before writing the deck, or they choose it for you.

- Pick the number that best supports the action and survives scrutiny: a share ("53 percent of revenue"), a growth rate ("up 38 percent"), or a count ("seven quarters"). Prefer the one with the highest confidence score from Step 4.
- Put it in the title slide subtitle or in the first finding, then in the insight, then on the closing slide. Three appearances, same wording, same rounding each time.
- Give it a base the first time ("53 percent of 36.2 M") and only the number afterwards.
- Do not let a second number compete with it in the same size. Other numbers stay in bullets, charts and notes.

In the example above the number is 53 percent: it appears in the fourth finding, drives the insight, and justifies both asks.
