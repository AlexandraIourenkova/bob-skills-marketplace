# The blueprint spec

One JSON file, read by `scripts/blueprint.py`. Every section is optional: the page shows the sections the spec has, in the order below, and numbers them. `assets/blueprint-example.json` is a complete document and `assets/ideas-example.json` an idea board; `blueprint.py init <path>` copies one to a new file.

Text fields are plain text. `**two asterisks**` make words bold; nothing else is markup, and everything is escaped.

## Headlines

Most sections take `headline` and `lead`. The headline is the claim of the section, a sentence a reader could repeat: "Nine steps and four hand-offs become four steps and two", not "Process". Leave it out and the page falls back to a neutral title.

## meta

| Field | Meaning |
|---|---|
| `title` | Required. The result in a few words. |
| `tagline` | One or two sentences under the title. |
| `team`, `challenge`, `date` | The line under the tagline. |
| `status` | `plan` (nothing is built yet), `as-built` (drawn from the working proof of concept) or `ideas` (an idea board). Shown as a chip on the first screen. |
| `language` | Language code for the page, default `en`. |
| `direction` | `rtl` for Hebrew and Arabic: the page, the lanes and the architecture mirror. |
| `partial` | `true` for a page that is one part on purpose, such as the process alone: the check then stays quiet about the sections a whole blueprint needs. |

## labels

The page has fixed labels ("Before", "steps", "Recommended", the section names). For a document in another language, run `blueprint.py labels`, translate the values, and put the object into `labels`. Keys that are missing stay English.

## hero

The one number that matters, on the first screen: `value` ("3 days → 20 min"), `label` (what it measures), `basis`, `source`, and an optional `note`.

## Marks: basis and source

Every number carries `"basis"`: `measured`, `estimate` or `assumption`. `source` says how it was measured or worked out; it is the tooltip of the mark and, in places, printed next to it. The render stops when a number has no basis.

## problem

`headline`, `lead`, then `who` (who lives with it), `today` (what happens today), `cost`, `why_now`; `facts` is a list of `{value, label, basis, source}` tiles; `quote` and `quote_by` for one sentence in a user's own words.

## ideas

`headline`, `lead`, `items`. Each item: `title`, `direction` (`new-app`, `modernise`, `mcp`, `agent`, `other`), `pitch`, `who`, `demo`, `why`, `risk`, `scores` with `completeness`, `creativity`, `usability` and `effectiveness` from 1 to 5, and on one item `recommended: true` with a `verdict`. The total out of 20 is computed.

## process

| Field | Meaning |
|---|---|
| `headline`, `lead` | The claim about the change. |
| `basis`, `source` | One mark for the step times of both diagrams: take the weakest. |
| `before`, `after` | Each `{title, steps}`. Either may be left out. |

A step is `{actor, title, minutes, kind}`.

- `actor`: the lane. A role, a team, a system or an outside party. Lanes appear in the order actors first occur.
- `title`: a few words; three short lines fit.
- `minutes`: elapsed minutes of the step, a number. Waiting counts: two days in a queue is 2880.
- `kind`: `manual` (default), `wait`, `decision`, `auto` (a system does it) or `ai` (the agent does it).

Computed and shown: steps, hand-offs (changes of actor), roles, end-to-end time, the share of waiting, hands-on time (manual and decision steps), and the change in each from before to after. Under each diagram a bar shows where the time goes; both bars share one scale. Keep each side to ten steps or fewer.

## architecture

| Field | Meaning |
|---|---|
| `headline`, `lead`, `caption` | The claim, the context, and a line under the diagram. |
| `layers` | Top to bottom. Each `{title, nodes}`. Four or five layers read well: people, experience, agents or logic, tools, systems and data. |
| `edges` | Connectors, each `{from, to, label, style, both}`. |
| `decisions` | Up to four `{title, why}`: the design choices worth defending. |

A node is `{id, title, tech, kind, ibm, role, status, evidence}`.

- `id`: unique, used by the edges. `title`: the name. `tech`: one line under it.
- `kind`: `user`, `ui`, `agent`, `model`, `tool`, `data`, `external` (an existing company system) or `service`. It sets the icon and the colour.
- `ibm: true` marks IBM technology: a stronger outline, an IBM tag, and a line in the list under the diagram, where `role` says what it does in this solution.
- `status`: leave out for built, or `planned` or `mock`. Both are drawn dashed and tagged.
- `evidence`: for a built node in an `as-built` document, the file or resource that proves it exists. It is not printed; the check asks for it.

Connectors run at right angles and never cross a node. `label` is one or two words. `style: "dashed"` for a secondary or asynchronous flow; `both: true` for an arrow at each end. A connector between neighbouring layers is the clean case; one that skips a layer runs down the side of the diagram, so use few of them. At most five nodes in a layer.

## impact

`headline`, `lead`; `metrics` is a list of `{label, before, after, unit, better, basis, source}` with `better` being `lower` (default) or `higher`; each metric is drawn as a pair of bars with the change computed. `waterfall` is `{title, unit, total_label, items}` with items `{label, value, basis, source}`: contributions that add up, negative for costs; the total bar is computed. `scale` is a list of sentences on where the solution goes next.

## alternatives

`headline`, `lead`, `criteria` (the column names), `options` (the rows) and `difference` (one paragraph on what is different here). An option is `{name, note, values, ours, status_quo}` with one value per criterion: `yes`, `partial`, `no`, or a short text. Mark the team's solution with `ours: true` and include the option of doing nothing with `status_quo: true`.

## demo and adoption

Both are a strip of numbered cards: `headline`, `lead`, `items` of `{title, detail, time}`, and optional `facts` tiles. `demo` is the storyboard of the demonstration; `adoption` is the path of a real user from the first click to daily use, which is what the usability criterion asks about.

## roadmap

`headline`, `lead`, `items` of `{phase, duration, items, gate, done}`. `gate` is the test that lets the work move to the next phase.

## criteria

`headline`, `lead`, `items` of `{name, evidence, gap}`: for each judging criterion, what in the entry answers it and what is still open.

## risks, assumptions, sources

`risks` is `{headline, lead, items}` with items `{risk, level, mitigation}`; `level` is `low`, `medium` or `high`. `assumptions` is a list of `{text, check}`: every number marked `assumption` belongs here with the way to check it. `sources` is a list of `{label, detail}`.

## Themes

`--theme carbon` (white, IBM blue), `midnight` (dark navy) or `editorial` (warm paper, serif headlines), or the path of a `theme.json`. The file format is the one the presentations pack writes: `colors` (`bg`, `surface`, `text`, `muted`, `accent`, `accent2`, `line`, `on_accent`, `chart`), `fonts` (`css_heading`, `css_body`, `css_mono`) and `dark`. `blueprint.py theme <name> -o challenge/theme.json` writes a built-in theme in that format, so a deck can take the document's look.
