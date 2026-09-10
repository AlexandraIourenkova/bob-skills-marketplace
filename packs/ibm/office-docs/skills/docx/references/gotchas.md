# Gotchas when working with .docx files

## Placeholders split across runs

Word stores a paragraph as a sequence of runs, and it starts a new run whenever the
formatting changes, whenever the spell checker marks a word, after certain edits, or
just because of editing-session ids. A placeholder typed as `{{client_name}}` may be
stored as three runs `{{`, `client_`, `name}}`, so `"{{client_name}}" in run.text` is
false for every run even though the paragraph reads correctly.

- Detect on paragraph text: `"".join(r.text for r in p.runs)` or `p.text`.
- Replace with `scripts/docx_fill.py`: it maps the match offsets back onto the
  underlying `w:t` text nodes, writes the value into the first node and empties the
  rest, so no formatting of untouched characters is changed.
- Prevention when you author templates: type the whole placeholder in one go, do not
  spell-check it (add it to the dictionary or disable proofing on the run), and avoid
  formatting changes inside the braces.
- Placeholders in text boxes, shapes, footnotes and comments are not reachable through
  `doc.paragraphs`; the fill script walks every `w:p` in the body, headers, footers,
  footnotes and endnotes instead.

## Styles missing in a template

`doc.styles["List Bullet"]` raises `KeyError: "no style with name 'List Bullet'"`
when the document was created from a template that never used that style. Word keeps
unused built-in styles latent (declared in `latentStyles` only), and python-docx
cannot instantiate a latent style.

- List what exists: `[s.name for s in doc.styles]`.
- Fall back explicitly (bold run instead of `Heading 3`, `Normal` plus indent instead
  of `List Bullet`), or copy the missing style definition from a document that has it
  (open both, append the `w:style` element to `doc.styles.element`).
- `Table Grid` missing means tables come without borders; add borders through
  `w:tblBorders` in `tblPr` or ask for a template that contains the style.
- Style names are case-sensitive and localized documents may rename built-in styles
  (`Heading 1` is stored with a `w:styleId` such as `Heading1`; look up by name via
  `doc.styles`, and fall back to matching `style.style_id`).

## Table widths

- Word honours the width of each cell (`w:tcW`), not the `Column.width` value, so set
  `cell.width` for every cell of a column and `table.autofit = False`; otherwise Word
  autosizes to content and LibreOffice lays the table out differently again.
- The sum of the column widths should not exceed the text area
  (`page_width - left_margin - right_margin`, 6 inches on Letter with 1.25 inch margins,
  about 6.3 inches on A4 with 2.5 cm margins); wider tables run into the margin.
- `doc.add_table` in headers and footers requires a `width` argument.
- Two tables that follow each other with no paragraph in between are shown as one
  table by Word; add an empty paragraph as a separator.
- A row taller than a page is not split; long cell text overflows to the next page only
  when `w:cantSplit` is absent (the default).

## Images larger than the page

- `doc.add_picture(path)` without `width` uses the pixel size at the image's stored
  DPI (72 dpi when the file has none), so a 2000 pixel screenshot becomes 27 inches
  wide and Word clips it or pushes it off the page.
- Pass `width=Inches(x)` at most equal to the text area width, or clamp afterwards
  with `doc.inline_shapes[-1]` (keep the aspect ratio by computing the height).
- Give `width` or `height`, never both, unless distortion is intended.
- Large images are stored uncompressed; downscale the file before insertion when the
  document must stay small. python-docx does not resample.

## Numbering and lists

- All paragraphs styled `List Number` reference one numbering instance, so a second
  list continues counting. Restart requires a new `w:num` with a `startOverride`
  (helper `new_num_instance` in `scripts/docx_build.py`).
- Nested levels come from `w:ilvl` in the paragraph's `numPr`; the built-in
  `List Bullet 2` and `List Number 2` styles reach the same effect with their own
  numbering instances. Documents written by Word use `List Paragraph` plus a
  paragraph-level `numPr` for nearly every list.
- A list paragraph with `numId` 0 is explicitly "not numbered".
- Bullets are glyphs from the Symbol font in the default template; when the target
  machine lacks that font, bullets render as boxes. Use a template from the customer
  when fidelity matters.
- The bullet or number glyph is not part of `paragraph.text`; extraction shows the
  list level and kind, not the rendered number.

## Document properties

- `doc.core_properties` covers title, subject, author, keywords, comments, category,
  last_modified_by, revision, created, modified, last_printed. The default template
  sets an author and dates from the library itself; overwrite them on every new file.
- Datetimes are naive and interpreted as UTC when written.
- Custom properties are not exposed; edit `docProps/custom.xml` inside the zip if
  they are required.
- Word shows "Title" from the core properties in the file dialog, not the first
  heading; set both when the user expects them to match.

## Reading .doc files (not supported)

python-docx opens Office Open XML only. A legacy binary `.doc` (Word 97-2003), `.rtf`
or `.odt` file raises `PackageNotFoundError` or "File is not a zip file". Tell the
user this and convert first:

```bash
soffice --headless --convert-to docx --outdir /abs/out /abs/legacy.doc
```

Then process the resulting `.docx`. `.docm` (macro-enabled) and `.dotx` (template)
files open, but saving them under a `.docx` name keeps their original content type in
`[Content_Types].xml`; Word may complain. Save `.dotx` input as `.dotx`, or create a
new `Document()` and copy the content across.

## Other traps

- `paragraph.text = "..."` and `cell.text = "..."` drop every run and its formatting;
  edit `run.text` instead.
- Text in text boxes, shapes, SmartArt, footnotes, comments and tracked insertions is
  not returned by `doc.paragraphs`; accept all tracked changes in Word before
  processing when the text must be complete.
- Accessing `section.header.paragraphs` on a linked header creates an empty header
  definition; check `is_linked_to_previous` before touching headers you only read.
- Fields (page numbers, dates, table of contents) hold a cached value until Word or
  LibreOffice recalculates them; a generated TOC is empty until the user updates
  fields unless `w:updateFields` is set in `settings.xml`.
- Element order inside `pPr`, `rPr`, `tblPr` and `tcPr` is fixed by the schema; Word
  reports a corrupt file when hand-built XML puts `w:jc` before `w:bidi` or `w:shd`
  after `w:vAlign`. Use python-docx `get_or_add_*` and `insert_element_before` helpers.
- A file that is open in Word on Windows is locked; save to a new name.
- Page count and line breaks are unknown to python-docx; only a renderer (Word,
  LibreOffice) knows where pages end. Convert to PDF to check pagination.
- Saving does not validate; open the result in Word or LibreOffice, or at least run
  `scripts/docx_extract.py` on it, before delivering.
