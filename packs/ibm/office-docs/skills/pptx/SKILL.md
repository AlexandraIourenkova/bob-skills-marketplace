---
name: pptx
description: Create, edit, fill, extract and render PowerPoint (.pptx) decks with python-pptx and tested helper scripts. Builds a 16:9 deck from a Markdown outline (title slide, nested bullets, images, native bar/line/pie charts, speaker notes, optional corporate .pptx or .potx template), finds and replaces text across slides and notes while keeping run formatting, dumps an existing deck to Markdown with slide numbers, and renders it to PDF and PNG with LibreOffice for review. Use it when the user says "create a PowerPoint", "make a slide deck", "build slides from this outline", "add a chart to the presentation", "update the text in this pptx", asks about "speaker notes", wants to "export the deck to PDF", or names a .pptx file or a .potx template. Not for PDF, Word or Excel files unless a slide deck is the input or output.
---

# pptx

Build and change PowerPoint decks with python-pptx. Four scripts cover the common
jobs; `references/python-pptx-cheatsheet.md` covers custom edits;
`references/design-notes.md` covers what makes a slide readable.

## 1. Decide which workflow applies

1. **Create** a new deck from content the user gives or that you write: section 3 (and 4 when a template is supplied).
2. **Edit** an existing deck: text changes go through section 5; anything else (new slide, chart, table, picture) is a short python-pptx script, section 6.
3. **Fill** a template deck that contains marker text such as `{{customer}}`: section 7.
4. **Extract** the content of a deck (summarise, review, reuse elsewhere): section 8.
5. **Render** or export to PDF/PNG: section 9. Always finish with section 10.

Never overwrite the user's original file: write to a new path, then let the user replace the original.

## 2. Environment

1. Run every script with uv, which fetches python-pptx on demand (paths are relative to this skill folder):

   ```bash
   uv run --with python-pptx python scripts/pptx_build.py --help
   ```

2. `pptx_render.py` needs LibreOffice (`soffice`) and optionally `pdftoppm` (poppler); it needs no Python package, so `uv run python scripts/pptx_render.py ...` is enough. Without LibreOffice it exits 2 with install hints; tell the user and continue with the python-pptx read-back check (section 10).
3. Requirements: Python 3.11+, python-pptx 1.0+. The scripts never use the network and only write to the output paths you pass.

## 3. Create a deck from an outline

1. Write the outline as Markdown, one construct per line. Keep one idea per slide, a headline that states the point, at most six bullets, no bullet longer than one line (see `references/design-notes.md`):

   ````markdown
   # Deck title
   Subtitle line

   ## Revenue grew 18 percent on subscriptions
   - Total revenue **12.4 M**, up 18 percent
   - Subscriptions now 61 percent of revenue
     - Enterprise tier doubled
   Notes: Open with the headline number, then the mix shift.

   ## Revenue by quarter
   ```chart
   {"type": "bar", "title": "USD millions", "categories": ["Q1", "Q2", "Q3", "Q4"],
    "series": [{"name": "2025", "values": [10.2, 11.0, 12.4, 13.1]}], "data_labels": true}
   ```

   ## Product screenshot
   ![Dashboard](images/dashboard.png)
   ````

   Rules: `#` makes the title slide (plain lines after it become the subtitle); `##` starts a slide; `-`, `*` or `1.` make bullets, indent 2 or 4 spaces to nest; `###` is a bold line without a bullet; plain text is a paragraph without a bullet; paired `**markers**` make a bold span (a lone `**`, as in `2 ** 3`, stays text); `![alt](path)` inserts a picture (path relative to the outline file; PNG, JPEG, GIF, BMP, TIFF); a fenced `chart` block holds JSON with `type` (bar, column, barh, stacked, barh-stacked, line, pie, doughnut, area), `categories`, `series` (list of `{"name", "values"}` or an object `{"name": [values]}`), optional `title`, `data_labels`, `number_format`, `legend`; each line starting with `Notes:` (plural; `Note:` is ordinary text) is one paragraph of speaker notes. Bullets and visuals on the same slide are laid out side by side; a slide with only visuals gets the full width. Save the outline as UTF-8.
2. Build:

   ```bash
   uv run --with python-pptx python scripts/pptx_build.py outline.md -o deck.pptx
   ```

   Defaults: 16:9 (13.333 x 7.5 in), headings 36 pt (title slide 4 pt larger, capped at 40), bullets 24 pt stepping down to 18 pt for nested levels. Options: `--title-size 36..40`, `--body-size 18..24`, `--max-bullets 6`, `--strict` (warnings become exit 1 and no file is written).
3. Read the warnings on stderr: more than six bullets, headline longer than 70 characters, empty slide. Fix the outline and rebuild rather than shipping a crowded slide.
4. Verify (section 10).

## 4. Use a corporate template

1. List the layouts and placeholders of the template so you can name them:

   ```bash
   uv run --with python-pptx python scripts/pptx_build.py --list-layouts --template brand.pptx outline.md
   ```

2. Build on the template (`.pptx`, or a `.potx`/`.ppsx` that the script retypes in memory); its slide size, theme, fonts and layouts are kept and its existing slides are removed (`--keep-template-slides` keeps them in front of the new ones and the summary counts them):

   ```bash
   uv run --with python-pptx python scripts/pptx_build.py outline.md -o deck.pptx --template brand.pptx \
     --title-layout "Title Slide" --content-layout "Title and Content" --title-only-layout "Title Only"
   ```

   The layout flags are only needed when the template names its layouts differently; matching is case-insensitive.
3. Placeholder positions come from the template. If the template's layouts do not fill its slide (a 4:3 layout on a 16:9 slide), fix the template or use a script (section 6) to reposition.

## 5. Edit text in an existing deck

1. Put the changes in a JSON mapping, longest keys first when one key contains another:

   ```json
   {"FY2025 Q3": "FY2025 Q4", "Northwind Traders": "Contoso"}
   ```

2. Count first, then write:

   ```bash
   uv run --with python-pptx python scripts/pptx_replace_text.py deck.pptx changes.json --dry-run
   uv run --with python-pptx python scripts/pptx_replace_text.py deck.pptx changes.json -o deck-v2.pptx
   ```

   The script reports counts per slide and per key, covers slide text, tables, grouped shapes and speaker notes, keeps run formatting (a match spanning several runs takes the formatting of the first run; a match never spans a line break), and warns for keys with no match. `--ignore-case` matches loosely; `--require-match` exits 1 without writing when a key is not found; `--json-report counts.json` saves the counts.
3. Text inside charts (titles, labels) and on masters or layouts is not touched; edit it with a script (section 6).

## 6. Other edits with a python-pptx script

1. Open the cheat sheet for the exact API: `references/python-pptx-cheatsheet.md` (units, placeholders, text, tables, pictures, charts, notes, shapes, deleting and reordering slides).
2. Write a short script in the working directory that opens the deck, changes it and saves to a new path, then run it with `uv run --with python-pptx python edit.py`. Pattern:

   ```python
   from pptx import Presentation
   from pptx.util import Inches, Pt
   prs = Presentation("deck.pptx")
   slide = prs.slides[2]                       # zero-based
   slide.shapes.title.text = "New headline"
   slide.notes_slide.notes_text_frame.text = "Speaker notes for this slide."
   prs.save("deck-v2.pptx")
   ```

3. To add a slide with a chart or picture, build it from an outline snippet with `pptx_build.py --template deck.pptx --keep-template-slides` when the new slide can go at the end; otherwise use `add_chart` / `add_picture` from the cheat sheet.
4. Prefer placeholders of the slide's layout over free text boxes so fonts and positions stay consistent.

## 7. Fill a template deck

1. Extract the deck (section 8) to see the marker text (`{{name}}`, `[DATE]`, `XXX`) and where it sits.
2. Build a mapping from marker to value and run `pptx_replace_text.py` with `--require-match` so a misspelt marker fails loudly.
3. For pictures or charts that must change per customer, use a script (section 6): `picture.image` to inspect, `add_picture` into the same box, or `chart.replace_data(new_data)`.

## 8. Extract content from a deck

1. Dump titles, bullets (nested by level), plain text boxes, tables, chart data and notes, one section per slide with slide numbers:

   ```bash
   uv run --with python-pptx python scripts/pptx_extract.py deck.pptx -o outline.md
   mkdir -p img
   uv run --with python-pptx python scripts/pptx_extract.py deck.pptx --images-dir img/ --layouts
   ```

   Without `-o` the Markdown goes to standard output. `--images-dir` saves embedded pictures and links them; `--layouts` adds the layout name under each heading. Bold runs come back as `**text**`, bold lines without a bullet as `###`, and a chart that the build script cannot rebuild (scatter, bubble) carries a `note`.
2. To edit and rebuild, extract with `--plain`: the file header becomes a comment, headings lose the `Slide N:` prefix, the title slide becomes `# title` and unsaved pictures become comments, so `pptx_build.py outline.md -o deck-v2.pptx` reproduces the deck (use `--images-dir` to carry the pictures over).
3. Use the extract for summaries and reviews; do not paste raw XML or shape dumps to the user.

## 9. Render to PDF and PNG

1. Convert with LibreOffice headless; PNGs are added when `pdftoppm` is installed:

   ```bash
   mkdir -p renders
   uv run python scripts/pptx_render.py deck.pptx --outdir renders --dpi 110
   ```

   Exit 2 means LibreOffice is missing (the message shows how to install it or pass `--soffice`); `--pdf-only` skips the PNG step. The script replaces `renders/deck.pdf` and `renders/deck-<n>.png` from an earlier run, so give each deck its own directory when names collide.
2. Look at every PNG for overflowing text, overlapping shapes and unreadable chart labels. LibreOffice substitutes fonts, so small differences from PowerPoint are expected; layout problems are real.
3. When the user asked for a PDF, hand over `renders/deck.pdf`.

## 10. Verify before handing over

1. Read the produced file back and check it against the request:

   ```bash
   uv run --with python-pptx python scripts/pptx_extract.py deck.pptx
   ```

   Confirm the slide count, every heading, the bullets, chart categories and series, the `Image:` lines and the `Notes:` lines. For replacements, confirm the reported counts match the expected occurrences and that the extract shows the new text.
2. Render (section 9) when LibreOffice is available and inspect the PNGs; otherwise say that visual review was skipped.
3. Report the output path, slide count, warnings you accepted, and anything you could not do (unsupported image format, chart text not replaced).

## 11. Gotchas

- The built-in python-pptx template is 4:3; `pptx_build.py` sets 16:9 and repositions the title, subtitle and body placeholders itself. Custom templates keep their own size and positions.
- `Presentation()` opens `.pptx` only; a `.potx` template or `.ppsx` show raises `ValueError ... content type is ...template.main+xml`. The three python-pptx scripts retype such files in memory; in your own script save the template as `.pptx` in PowerPoint first, or copy `open_presentation` from `scripts/pptx_build.py`.
- `slide.placeholders[1]` is the placeholder with idx 1, not the second shape; iterate and check `placeholder_format.type` in templates.
- Setting `.text` on a shape, paragraph or cell drops run formatting; use `pptx_replace_text.py` or edit `run.text`.
- Pie and doughnut charts take exactly one series; values must be numbers; category counts must match value counts (the build script reports the line).
- SVG and WebP pictures are not supported by python-pptx; convert to PNG first.
- Accessing `slide.notes_slide` creates an empty notes slide; check `slide.has_notes_slide` when reading.
- Auto-shrink (`TEXT_TO_FIT_SHAPE`) is applied by PowerPoint on open and may not show in LibreOffice renders; shorten text instead of relying on it.
- Fonts are not embedded in .pptx; stick to the template's theme fonts.
- Deleting or reordering slides has no public API; the cheat sheet shows the two-line element edit.
