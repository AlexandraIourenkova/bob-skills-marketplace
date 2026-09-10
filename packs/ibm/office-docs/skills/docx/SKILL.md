---
name: docx
description: Create, edit, fill and extract Microsoft Word (.docx) files with python-docx through four ready-made scripts. Build a document from a JSON spec of headings, paragraphs, bullet and numbered lists, tables, images and page breaks (optionally on top of a template that keeps its styles, headers and footers), replace {{placeholders}} in a template even when Word split them across runs, dump the headings, text and tables of a .docx to Markdown or JSON, and convert to PDF with LibreOffice. Use it whenever a user asks to "create a Word document", "write a .docx report", "fill this Word template", "extract the text from this docx", "add a table to the document", "convert the docx to PDF" or "edit the Word file", or names a .docx file as input or output. Do not use for PDF, spreadsheet or presentation files unless a .docx is the input or the output.
---

# Word documents (.docx)

Scripts live in `scripts/` next to this file; `references/` holds the API cheatsheet
and the gotchas. Below, `<skill>` means the folder that contains this SKILL.md.

## 1. Decide which workflow applies

1. Read the request and pick exactly one starting point:

| The user wants to ... | Workflow | Tool |
| --- | --- | --- |
| produce a new document from content you have or write | Create (section 3) | `docx_build.py` |
| fill fields of an existing template (`{{name}}` markers) | Fill (section 4) | `docx_fill.py` |
| read, summarise, search or reuse the content of a .docx | Extract (section 5) | `docx_extract.py` |
| change wording, add a table or image, or restyle an existing file | Edit (section 6) | python-docx directly |
| get a PDF of a .docx | Convert (section 7) | `docx_to_pdf.py` |

2. If the input is a legacy `.doc`, stop: python-docx cannot open it. Ask for a `.docx`
   or convert with LibreOffice first (`soffice --headless --convert-to docx FILE.doc`).
3. Always write to a new output path. Never overwrite the user's source file.

## 2. Environment

1. Use `uv` so the dependency is resolved per run; no project setup is needed:

```bash
uv run --with python-docx python <skill>/scripts/docx_build.py --help
```

2. Every script prints `--help`, exits non-zero on failure and writes only to `--out`.
3. `docx_to_pdf.py` needs no Python package (`uv run python ...`) but needs LibreOffice.
4. Use absolute paths for inputs and outputs so the results are easy to find and report.

## 3. Create a document (docx_build.py)

1. Write the content as a JSON spec. Top level: `title`, `author`, `orientation`
   (`portrait` or `landscape`) and `blocks`. Supported blocks:

| type | keys |
| --- | --- |
| `heading` | `text`, `level` (0 = Title style, 1..9 = Heading N), `align` |
| `paragraph` | `text` or `runs` (each: `text`, `bold`, `italic`, `underline`, `size_pt`, `font`, `color`), `style`, `align`, `rtl` |
| `bullets` / `numbered` | `items` (strings or `{"text", "level"}`), `restart` (numbered, default true) |
| `table` | `header`, `rows`, `style` (default `Table Grid`), `col_widths_in`, `header_bold`, `align` |
| `image` | `path` (relative to the spec file), `width_in` (clamped to the page), `caption`, `align` |
| `page_break` | none |
| `section` | `orientation` (starts a new page with its own orientation) |

Minimal example:

```json
{
  "title": "Status report", "author": "Ops team",
  "blocks": [
    {"type": "heading", "text": "Status report", "level": 0},
    {"type": "heading", "text": "Summary", "level": 1},
    {"type": "paragraph", "runs": [{"text": "On track. ", "bold": true}, {"text": "Two risks open."}]},
    {"type": "bullets", "items": ["Budget approved", "Vendor contract signed"]},
    {"type": "table", "header": ["Item", "Owner", "Due"], "rows": [["Rollout", "Dana", "2026-10-01"]]},
    {"type": "image", "path": "burnup.png", "width_in": 5.5, "caption": "Figure 1: burn-up"},
    {"type": "page_break"},
    {"type": "heading", "text": "Appendix", "level": 1}
  ]
}
```

2. Build it:

```bash
uv run --with python-docx python <skill>/scripts/docx_build.py /abs/spec.json --out /abs/report.docx
```

3. To inherit corporate styles, headers and footers, pass the customer's document as a
   template. Its body is replaced (add `--keep-body` to append after the existing content);
   a multi-section template collapses to its last section, which keeps the headers and
   footers it showed in Word. Only `.docx`/`.docm`/`.dotx` templates open; `.doc` is rejected:

```bash
uv run --with python-docx python <skill>/scripts/docx_build.py /abs/spec.json \
  --template /abs/corporate.docx --out /abs/report.docx --orientation landscape
```

4. Read the warnings on stderr: a missing style (for example no `List Bullet` in the
   template) falls back to a plain paragraph with a text marker. Fix the spec or the
   template rather than shipping the fallback silently.
5. Run the verification in section 8.

## 4. Fill a template (docx_fill.py)

1. List the placeholders the template really contains (Word may have split them
   across runs; the script joins them):

```bash
uv run --with python-docx python <skill>/scripts/docx_fill.py /abs/template.docx --list
```

2. Write a JSON object with one key per placeholder. Nested objects map to dotted
   names (`{"client": {"name": "ACME"}}` fills `{{client.name}}`); `null` becomes an
   empty string; `\n` in a value becomes a line break.
3. Fill and read the report. Use `--strict` when every field must be resolved:

```bash
uv run --with python-docx python <skill>/scripts/docx_fill.py /abs/template.docx \
  --data /abs/values.json --out /abs/filled.docx --strict
```

4. The report lists replacements per part (body, header, footer, footnotes), unused
   keys and unresolved placeholders. Unresolved ones stay in the text as `{{name}}`;
   resolve them or tell the user which are missing.
5. Formatting of untouched text is never changed; a value takes the formatting of the
   first character of its placeholder. For repeated rows (one row per item), build
   the table with python-docx instead (section 6) or generate the document (section 3).

## 5. Extract content (docx_extract.py)

1. Markdown to stdout is the default; it shows header/footer lines first, then headings
   (the Title style underlined with `=`, Heading N as N hashes), list items, paragraphs
   and pipe tables in document order:

```bash
uv run --with python-docx python <skill>/scripts/docx_extract.py /abs/input.docx
uv run --with python-docx python <skill>/scripts/docx_extract.py /abs/input.docx --format json --out /abs/input.json
uv run --with python-docx python <skill>/scripts/docx_extract.py /abs/input.docx --tables-only
```

2. JSON gives `properties`, `headers_footers` and `blocks` (`heading` with `level` where
   0 is the Title, `paragraph` with `style` and optional `list`/`list_level`/`list_id`,
   `table` with `rows`; a merged cell is printed once and its span reads as `""`).
   Use it when the content feeds another step (a summary, a spreadsheet, a new document).
3. Paragraphs and tables inside content controls are included. Text inside shapes and
   text boxes, footnotes, comments and tracked changes is not part of the body walk;
   say so if the document looks incomplete. Read `references/gotchas.md`.

## 6. Edit an existing document (python-docx directly)

1. Extract first (section 5) to locate the paragraph or table to change.
2. Write a short script; edit runs, never assign `paragraph.text` on formatted text:

```bash
uv run --with python-docx python - <<'EOF'
from docx import Document
from docx.shared import Inches
doc = Document("/abs/input.docx")
for p in doc.paragraphs:
    for r in p.runs:
        if "2025" in r.text:
            r.text = r.text.replace("2025", "2026")   # keeps the run's formatting
anchor = next(p for p in doc.paragraphs if p.text.startswith("Budget"))
table = doc.add_table(rows=1, cols=2)
table.style = "Table Grid"
table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Item", "Amount"
anchor._p.addnext(table._tbl)                       # move the table right after the anchor
doc.save("/abs/output.docx")
EOF
```

3. Look up the API you need in `references/python-docx-cheatsheet.md` (styles, runs,
   tables and merged cells, images, sections, headers/footers, page-number fields,
   lists, fonts, right-to-left text). Prefer style names over direct formatting.
4. Save to a new path and verify (section 8).

## 7. Convert to PDF (docx_to_pdf.py)

1. Run the converter; it uses LibreOffice headless only when `soffice` is installed:

```bash
uv run python <skill>/scripts/docx_to_pdf.py /abs/report.docx --out /abs/report.pdf
```

2. Exit code 2 means LibreOffice is absent. Tell the user to install it or to open the
   .docx in Word and export; do not try other converters or downloads.
3. LibreOffice rendering differs slightly from Word (fonts, table widths). Fields such
   as page numbers and tables of contents are recalculated during the conversion.

## 8. Verify the produced file

1. Read the output back and check that the expected content is present:

```bash
uv run --with python-docx python <skill>/scripts/docx_extract.py /abs/report.docx
```

2. Confirm headings in the right order, every table with its header row, placeholder
   markers gone (`grep -c '{{'` on the extract must be 0 after a fill), header/footer
   text kept when a template was used.
3. For images and sections check counts with python-docx:
   `len(doc.inline_shapes)`, `len(doc.sections)`, `doc.sections[-1].orientation`.
4. Report the absolute output path and any warning the scripts printed.

## 9. Gotchas (details in references/gotchas.md)

1. Placeholders get split across runs by Word; only `docx_fill.py` or a run-joining
   approach finds them. Do not search `run.text` for `{{`.
2. A template may lack built-in styles (`List Bullet`, `Heading 3`, `Table Grid`);
   python-docx raises `KeyError` and the build script falls back with a warning.
3. Column widths must be set on every cell of the column and `table.autofit = False`.
4. Images wider than the page are clamped by the build script; when using python-docx
   directly pass `width=` and never set both width and height.
5. Every `List Number` paragraph continues the same list; restart needs a new
   numbering instance (the build script does this per list).
6. Set `core_properties.title` and `author`; the default template's author is not you.
7. `.doc`, `.rtf` and `.odt` are not supported by python-docx; convert them first.
