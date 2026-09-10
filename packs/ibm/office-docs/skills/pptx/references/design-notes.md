# Slide design notes

Rules of thumb for decks that are read in a room or shared as a file. Apply them
when writing the outline; `scripts/pptx_build.py` enforces the measurable ones
(font sizes, bullet count, image fit) and warns about the rest.

## 1. One idea per slide

- A slide carries one point. If the heading needs "and", split the slide.
- Sequence: title, agenda or context, one slide per point, summary or ask, appendix.
- Ten to fifteen content slides fit a 20 minute talk; a reading deck can be longer but each slide still makes one point.

## 2. The headline states the point

- Write the heading as the conclusion, not the topic: "Revenue grew 18 percent on subscriptions", not "Revenue".
- Keep it under about 70 characters so it fits on one line at 36 pt; the build script warns above that.
- Someone reading only the headings should get the whole story.

## 3. At most six bullets

- Six bullets, each one line, is the ceiling; three or four is better.
- Bullets are fragments, not sentences; drop articles and filler; one level of nesting, two at most.
- Extra points go to the speaker notes ("Notes:" lines) or to a second slide.
- Tables: at most six rows and four columns on a slide; bigger data belongs in an appendix or a chart.

## 4. Sizes that read from the back of the room

- Headings 36 to 40 pt, body 24 pt, nested bullets no smaller than 18 pt, table and chart text 12 to 14 pt.
- 24 pt minimum for anything the audience must read on a screen in a room; 18 pt is the floor for decks read on a laptop.
- Do not rely on auto-shrink to fit text: shorten the text or split the slide.

## 5. Contrast and colour

- Dark text on a light background (or the reverse); aim for a contrast ratio of at least 4.5:1 for text, 3:1 for large headings.
- Use the template's theme colours; one accent colour for emphasis, one for the alternative or the negative case.
- Never encode meaning with colour alone: add labels, markers or patterns so the point survives grayscale printing and colour-blind viewers.
- Avoid pure red on green and light grey text on white.

## 6. Images and charts sized to the slide

- Scale pictures to fit the content area while keeping the aspect ratio; never stretch. On 16:9 the content area is roughly 12.3 x 5.25 in with 0.5 in margins.
- Raster images should be at least 1000 px on the long side when they fill the slide; screenshots should be cropped to the region that matters.
- One chart per slide, with a title that states the finding, axis labels with units, and data labels when there are fewer than about eight values.
- Prefer bar and line charts; use a pie only for a few parts of one whole, sorted by size, with percentages shown.
- Put the chart on the right and the two or three takeaways on the left, or give the chart the whole slide.

## 7. Consistent layout use

- Use the template's layouts: Title Slide for the opening, Title and Content for text, Title Only for visuals, Section Header for chapter breaks. Do not draw text boxes where a placeholder exists.
- Same margins, same title position and same font sizes on every slide; the audience notices jumps.
- Align edges: text box left edge, chart left edge and picture left edge share the same margin.
- Keep footers, logos and slide numbers on the master, not on each slide.

## 8. Speaker notes

- Notes hold the narrative: what to say, the source of each number, the anticipated question.
- Write them as short paragraphs, one per "Notes:" line; they are printed with the slide in notes view and read by screen readers.

## 9. Before sending

- Render to PDF and look at every page (`scripts/pptx_render.py`); check text overflow, overlapping shapes, unreadable labels.
- Run `scripts/pptx_extract.py` and read the outline as a story: headings alone, then bullets.
- Spell-check names and numbers; confirm every number on a slide is in the notes with its source.
- Remove empty placeholders and stray shapes outside the slide area.
