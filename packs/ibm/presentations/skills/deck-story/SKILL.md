---
name: deck-story
description: Build the story of a presentation. Choose a narrative structure, write one headline per slide, and check that the headlines alone tell the story. Works from scratch (an interview of eight questions), from the user's data (six lenses that turn a spreadsheet into three to five findings) or from a document. Use when the user asks how to structure a talk or a deck, says the deck has no story or "too many slides", wants an outline or a storyboard before slides exist, asks what to put on which slide, or says "структура презентации", "как рассказать эту историю", "сделай сторилайн". The presentation skill calls this as its story step.
---

# deck-story

Output: `deck/storyboard.md`, agreed with the user as a headline outline. Nothing is styled or built here.

## 1. Know the audience before choosing the structure

Read the brief (`deck/brief.md`) or ask for the five things that decide everything else: who is in the room, what they should decide or do, the format and time, the language, the one thing to remember. `references/audiences.md` maps audience, goal and format to depth, tone, order, evidence and slide count. Take the slide budget from there: a live talk runs one to two minutes per slide.

## 2. Choose the structure

`references/narratives.md` has the decision table and twelve structures with skeletons and worked examples: answer first for executives, situation-complication-question-answer for proposals, what-so-what-now-what for reviews, options and a recommendation for decisions, the data story arc for analytics, sparkline and transformation for keynotes and customer stories, and the rest. Name the structure in the brief and say why it fits.

## 3. From data, from a document, or from nothing

- **Data.** Profile it first, then work through `references/data-to-story.md`: six lenses (change over time, comparison to plan, ranking, share, distribution, relationship), rank the findings by the audience's decision, keep three to five.

  ```bash
  uv run --with pandas --with openpyxl python scripts/data_profile.py data.xlsx --sheet Revenue
  ```

  It prints the shape, per-column types and ranges, missing values, top categories, and per-period totals with the change between the last two periods.
- **A document.** Its headings are not headlines: read the argument, write the conclusion of each section as a headline, drop everything that does not serve the ask.
- **Nothing yet.** Run the eight-question interview at the end of `references/narratives.md` and write the storyboard from the answers.

## 4. Write the storyboard

Format: `../presentation/references/storyboard-format.md`. Headlines first, top to bottom, before any evidence: each is the point of its slide, states a conclusion, stays under 70 characters. Then fill each slide with the least evidence that carries the headline, add `Takeaway:` where there is a so-what, `Source:` for every number, and `Notes:` with what you will say and where the numbers come from. One idea per slide; if the headline needs "and", split it.

## 5. Check and agree

```bash
uv run python ../presentation/scripts/storyboard_check.py deck/storyboard.md --minutes 15
```

The output opens with the headline test: read the headlines alone and see whether the story holds. Then it warns about topic headlines, more than six bullets, bullets longer than a line, numbers without a source, slides without notes, a missing hook or ask, missing pictures and a slide count that does not fit the time. Add `--reading` for a deck that is read rather than presented, `--strict` to fail on warnings.

Fix what you agree with, then show the user the headline outline with one line on the structure and ask whether the storyline is right. Continue only with an answer; the style and the slides come after.

## 6. Hand over

Report the structure chosen, the headline outline, the slide count and estimated minutes, the open questions (missing numbers, claims without evidence), and what you moved to the appendix.
