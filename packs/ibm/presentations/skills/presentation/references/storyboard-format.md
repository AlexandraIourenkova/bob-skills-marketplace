# Storyboard format

The storyboard is the single source for the deck: `deck_build.py` builds the PowerPoint file from it, `deck_html.py` the interactive and printable HTML, `storyboard_check.py` reviews it, and the talk kit (pitch, Q&A) is written from its headlines and notes. It is Markdown, one construct per line, UTF-8. The office-docs `pptx` outline syntax is a subset, so an outline written for that skill builds here unchanged.

## Front matter (optional)

```markdown
---
title: Subscriptions now carry the business
subtitle: FY2026 mid-year review
author: Maria Startseva
date: September 2026
footer: FY2026 mid-year review        # bottom-left of content slides; default: the title
language: en                          # he, ar, fa, ur switch the deck to right-to-left
backdrop: images/title.jpg            # picture behind the title slide only (the closing slide reuses it)
section_backdrop: images/section.jpg  # default picture behind every section slide; a section can bring its own
backdrop_scrim: none                  # dark (default), light or none: the veil drawn over those pictures
backdrop_text: left                   # left (default) or right: the half of the picture the title sits on; keep it left for library pictures
source_label: Source:                 # the word before a Source line, for decks in another language
confidentiality: Internal use         # a small mark in the footer; set it for internal decks, leave it out for customers
chapter_label: auto                   # auto (default) puts the chapter above every headline; 'off' hides it
---
```

A section slide with a picture keeps the picture's colours: the text sits on a solid panel in the accent colour over the left third, not under a grey veil, and `backdrop_scrim` does not apply to it. Titles over a picture sit on the left half: every picture in the library was generated with its subject on the right and room on the left, so `backdrop_text: right` is only for a picture of your own that is built the other way round. The title picture is used once: nothing else in the deck shows it. Sections take `section_backdrop` unless a `![alt](images/x.jpg)` line stands under the `# Chapter` heading, which gives that chapter its own picture; a closing slide with its own picture line works the same way. Repeat one neutral picture on every section or give each chapter its own, but never the title picture. A photograph usually needs `backdrop_scrim: dark` so the title stays readable, which is the default. A generated backdrop from `visual_assets.py` is already quiet, so `none` (or `light` on a busy one) keeps its colours. The .pptx cannot place an SVG: keep a PNG of the same name next to it and the builder picks it up.

## Slides

| Line | Meaning |
|---|---|
| `# Deck title` | The first `#` line is the title slide. Plain lines under it are subtitle lines. |
| `# Chapter name` | Every later `#` line is a section slide (numbered 01, 02, ...). Plain lines under it are the chapter subtitle; a `![alt](images/x.jpg)` line under it is that chapter's own backdrop. Its name then stands above the headline of every slide in the chapter. A chapter called `Appendix` (or Backup, Annex) turns the rest of the deck into the appendix: those slides are numbered A1, A2 and left out of the timing. |
| `## Headline` | A content slide. The headline states the point ("Revenue grew 18 percent on subscriptions"), under 70 characters. |
| `layout: name` | Optional, directly under the headline: forces a layout (see below). Without it the layout is chosen from the content. |
| `- text` / `* text` | Bullet. Indent by two spaces per level (three levels at most). `1.` or `1)` makes a numbered item. |
| `### Column title` | Starts a column on a two-column slide (two or three `###` lines); on a bullets slide it is a bold sub-heading. |
| plain text | A paragraph. A slide with only one or two short paragraphs becomes a statement slide. |
| `> quote text` | A quote. A following line starting with `--` or an em dash is the attribution. |
| `![alt text](images/pic.png)` | A picture, path relative to the storyboard. PNG, JPEG, GIF, BMP or TIFF. The alt text is stored for screen readers. |
| ```` ```chart ```` ... ```` ``` ```` | A native chart from JSON (below). |
| `\| a \| b \|` | A table row. Separator rows (`\|---\|`) are skipped; the first row is the header. |
| `- 42% \| Revenue growth \| year on year` | On a `big-number` slide: value, label, detail. On a `timeline` slide: marker, label, detail (two fields: label, detail). |
| `Takeaway: text` | A callout under the content: the so-what of the slide. |
| `Source: text` | A small footnote line above the footer. |
| `Notes: text` | One paragraph of speaker notes; repeat the line for more paragraphs. `Note:` (singular) is ordinary text. |
| numbers | A number keeps its unit on the same line (12 M, 61 %, 30 days) and a range between two numbers takes an en dash (2025-2026 becomes an en dash). Both renderers do this; write the text plainly. |
| `**bold**` | Bold span inside any text line. A lone `**` stays text. In a headline, a statement or a title the bold words take the accent colour: `## Revenue grew **35 percent** in two years`. |
| `<!-- ... -->`, `---` | Ignored (comments, horizontal rules). |

## Layouts

| Layout | Content it expects | Chosen automatically when |
|---|---|---|
| `title` | title, subtitle lines; author and date from the front matter | the first `#` |
| `section` | chapter title, optional subtitle | later `#` lines |
| `bullets` | up to six bullets, optional sub-headings, paragraphs; pictures or charts go side by side | text, or text with visuals |
| `two-column` | two or three `###` columns with bullets or paragraphs under each; a paragraph before the first column is the lead | two or more `###` lines |
| `big-number` | one to four `- value \| label \| detail` items, optional lead paragraph | `layout: big-number` |
| `quote` | a `>` quote and an attribution line; the headline becomes a small kicker | a `>` line |
| `statement` | the headline is the message, drawn large; one or two paragraphs under it | short paragraphs only, or an empty slide |
| `image` | one picture: full-bleed with the headline over a dark band; two to four pictures: a grid with an optional caption paragraph | pictures only, or pictures with a caption |
| `chart` | one or two chart blocks or rendered chart pictures, full width; with bullets it falls back to side by side | charts only |
| `timeline` | two to six `- marker \| label \| detail` steps on a line (marker: a month, a year, a phase) | `layout: timeline` |
| `table` | up to nine rows and six columns; the first row is the header. A column whose cells are all numbers, percentages or amounts is right-aligned together with its header and never wraps; text columns take the remaining width. Table text is 12 to 14 pt, below the body size | `\|` rows |
| `closing` | the ask or the summary as the headline; bullets become lines under it (contacts, next steps, decision date) | `layout: closing` |
| `split` | one picture cover-fitted on half the slide, headline and bullets on the other half; the designed look for a picture with a point | `layout: split` |
| `icons` | three or four `- icon \| label \| detail` tiles with an icon from the bundled Carbon set (`visual_assets.py icon --list` for the names); the .pptx gets the same icon as a recoloured PNG | `layout: icons` |

## Chart block

```chart
{"type": "bar", "categories": ["Q1", "Q2", "Q3", "Q4"],
 "series": [{"name": "2025", "values": [10.2, 11.0, 12.4, 13.1]}],
 "data_labels": true, "number_format": "0.0", "highlight": ["Q4"]}
```

- `type`: `bar` (columns), `barh` (horizontal), `stacked`, `barh-stacked`, `line`, `area`, `pie`, `doughnut` (one series, at most five slices).
- `series`: a list of `{"name", "values"}` or an object `{"2025": [...]}`; values are numbers, one per category.
- `highlight`: category names or zero-based indexes to draw in the accent colour while the rest go grey (single series only).
- `data_labels`, `number_format` (Excel format string), `legend` (true or false), `title` (usually empty: the slide headline is the title), `unit`.
- `annotations`: `[{"category": "Q3", "text": "Launch", "series": "2026"}]` draws a short note with a leader line at that column. One per chart, only when the note says something the headline does not. The .pptx puts it as a line above the plot instead of a leader.
- `target`: `12` or `{"value": 12, "label": "Plan"}` draws a dashed reference line. HTML only; the .pptx warns and keeps the bars alone.
- Category labels that would collide lean by 30 degrees on their own, in both formats.
- Charts that python-pptx cannot draw natively (waterfall, slope, lollipop, bullet, small multiples, scatter, annotated line) are rendered to PNG with `deck-dataviz/scripts/chart_render.py` and placed with `![...](charts/name.png)`.

## Example

```markdown
---
title: Subscriptions now carry the business
author: Maria Startseva
date: September 2026
---

# Subscriptions now carry the business
FY2026 mid-year review for the leadership team

# Where the growth came from

## Revenue grew 18 percent, and subscriptions did the work
- Total revenue **12.4 M**, up 18 percent year on year
- Subscriptions are now 61 percent of revenue
  - Enterprise tier doubled its customer count
Takeaway: The mix shift we planned for 2027 arrived a year early.
Source: Finance close, August 2026
Notes: Open with the headline number, then the mix shift.

## Three numbers to remember
layout: big-number
- 18% | Revenue growth | year on year
- 61% | Subscription share | of total revenue
- 2x | Enterprise customers | 52 to 104 in twelve months

## Approve two enterprise onboarding hires for Q4
layout: closing
- Cost: 240 K for the year
- Decision needed by 30 September
```
