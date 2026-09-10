---
name: pdf
description: Read, create, fill and manipulate PDF files with five ready-made scripts built on pypdf, pdfplumber and reportlab. Extract text per page (page ranges, layout mode, scanned-PDF detection), pull tables out as Markdown or CSV, build a report PDF from a JSON spec (headings, paragraphs, lists, tables, images, page numbers, Unicode font so Hebrew, Arabic and Cyrillic render), merge, split, rotate, watermark, compress, encrypt and set metadata, list and fill AcroForm fields, and OCR scanned pages locally with tesseract and poppler. Use it whenever a user says "extract the text from this PDF", "pull the tables out of the PDF", "merge these PDFs", "split the PDF into pages", "create a PDF report", "fill in this PDF form", "the PDF is scanned, OCR it" or "add a watermark to the PDF", or names a .pdf file as input or output. Not for Word, Excel or PowerPoint files unless a PDF is involved.
---

# PDF files

Scripts live in `scripts/` next to this file, API notes and traps in `references/`.
Below, `<skill>` means the folder that contains this SKILL.md. Page numbers on every
command line are 1-based, exactly as a viewer shows them.

## 1. Decide which workflow applies

1. Read the request and pick one lane:
   - **Extract** (text, tables, metadata, page count): `pdf_extract.py`, step 3.
   - **Create** a new PDF from content you have: `pdf_build.py`, step 4.
   - **Manipulate** existing files (merge, split, rotate, extract pages, watermark,
     compress, encrypt, decrypt, metadata): `pdf_tools.py`, step 5.
   - **Forms** (list or fill AcroForm fields): `pdf_forms.py`, step 6.
   - **OCR** a scanned PDF: `pdf_ocr.py`, step 7.
2. When the user wants to change words inside an existing page, say that PDFs do not
   support in-place text editing here: rebuild the document with `pdf_build.py`, or
   stamp text on top with the watermark overlay approach.
3. When `pdf_extract.py` exits with code 3 ("looks like a scanned PDF"), switch to OCR.
4. When `pdf_forms.py list` warns about XFA, explain that only AcroForm fields can be
   filled and offer to overlay the values with reportlab instead.

## 2. Set up the environment

1. Run every script through uv so the three libraries are present without a global
   install (define this once per session):

   ```bash
   RUN="uv run --with pypdf --with pdfplumber --with reportlab python"
   # bash: $RUN <skill>/scripts/pdf_extract.py --help
   # zsh:  ${=RUN} <skill>/scripts/pdf_extract.py --help
   ```

   Without uv: `python -m pip install pypdf pdfplumber reportlab` and call `python`.
2. Every script prints usage with `--help`, exits non-zero on failure, writes only to
   the output path given, and never touches the network.
3. OCR needs `tesseract` and poppler's `pdftoppm` on PATH (`brew install tesseract
   poppler`, `apt-get install tesseract-ocr poppler-utils`); the script exits 2 with the
   install hint when they are missing. AES encryption needs the `cryptography` package;
   the `uv run` line above already pulls it in through pdfplumber, so add
   `--with cryptography` only when pypdf reports `DependencyError`.

## 3. Extract text, tables and metadata

1. Look at the file first: `pdf_extract.py in.pdf --info` prints page count, page size
   and metadata.
2. Extract text:

   ```bash
   $RUN <skill>/scripts/pdf_extract.py in.pdf                    # all pages to stdout
   $RUN <skill>/scripts/pdf_extract.py in.pdf --pages 1-3,7 -o out.txt
   $RUN <skill>/scripts/pdf_extract.py in.pdf --layout           # keep columns apart
   $RUN <skill>/scripts/pdf_extract.py in.pdf --json --tables -o out.json  # pages, text, tables
   ```

   Pages are separated by `--- Page N ---` markers. Add `--dedupe` when characters
   come out doubled, `--password` for files that need one to open (files that only
   restrict printing or copying open without it).
3. Extract tables: `--tables` appends each table as Markdown under its page;
   `--csv-dir DIR` writes `pageN_tableM.csv` files. Use `--table-strategy text` for
   tables without ruling lines and inspect the result, it is heuristic.
4. Read the notices on stderr: exit code 3 means no text layer (go to step 7);
   "pages [..] have images but no text layer" means a partly scanned file.

## 4. Create a PDF report

1. Write a JSON spec (see `pdf_build.py --help` for every key):

   ```json
   {"title": "Quarterly report", "author": "Finance", "page_size": "A4",
    "footer": "Internal", "blocks": [
      {"type": "heading", "text": "Summary", "level": 1},
      {"type": "paragraph", "text": "Plain text; & < > are escaped for you."},
      {"type": "bullets", "items": ["first", "second"]},
      {"type": "numbered", "items": ["step one", "step two"]},
      {"type": "table", "rows": [["Item", "Qty"], ["Bolt", "12"]], "header": true,
       "col_widths_mm": [100, 40]},
      {"type": "image", "path": "chart.png", "width_mm": 120, "caption": "Figure 1"},
      {"type": "page_break"},
      {"type": "paragraph", "text": "Hebrew or Arabic text is detected and right-aligned"}
    ]}
   ```

   Other keys: `subject`, `orientation` (`landscape`), `margins_mm`, `font_size`,
   `header` (defaults to the title), `page_numbers`, per-paragraph `align`,
   `markup: true` to allow `<b>`, `<i>`, `<br/>`, and `spacer` blocks with `height_mm`.
2. Build it: `$RUN <skill>/scripts/pdf_build.py spec.json -o report.pdf`. The script
   prints the page count and the font it used; a header line and "Page x of y" are
   drawn on every page.
3. Check the font line. The script searches DejaVu Sans, Arial Unicode, Liberation Sans
   and Noto Sans in the system font folders. When it warns "no Unicode TrueType font
   found", non-Latin text will not render: install DejaVu or pass
   `--font /path/to/font.ttf`. Hebrew in the title, headings, paragraphs, list items,
   table cells, header and footer is wrapped and reversed by the built-in fallback;
   blocks with `markup: true` stay in logical order and are reported by name; Arabic
   renders with unjoined letters (see gotchas).
4. Keep image paths relative to the spec file or absolute; widths are clamped to the
   text width; tables get equal column widths unless `col_widths_mm` is given, and
   widths that exceed the text area are scaled down with a warning.

## 5. Merge, split, rotate, watermark, compress, protect

```bash
T="<skill>/scripts/pdf_tools.py"
$RUN $T merge a.pdf b.pdf c.pdf -o merged.pdf
$RUN $T split in.pdf -o parts/ --every 1                 # one file per page
$RUN $T split in.pdf -o parts/ --pages 1-3,4-6,7-        # one file per range
$RUN $T extract-pages in.pdf -o subset.pdf --pages 3,1-2  # in that order
$RUN $T rotate in.pdf -o out.pdf --degrees 90 --pages 2,4
$RUN $T metadata in.pdf --json                           # show
$RUN $T metadata in.pdf -o out.pdf --title "T" --author "A" --subject "S"
$RUN $T watermark in.pdf -o out.pdf --text DRAFT --opacity 0.25 --angle 45
$RUN $T compress in.pdf -o small.pdf                     # add --remove-images to drop pictures
$RUN $T encrypt in.pdf -o locked.pdf --password open --owner-password admin
$RUN $T decrypt locked.pdf -o open.pdf --password open
```

1. Give `--password` to any reading command when the input needs one to open. Files
   that only carry an owner password (print or copy restrictions) open without it, and
   `decrypt in.pdf -o out.pdf` with no `--password` removes that restriction.
2. Watermarks use Helvetica; add `--font file.ttf` for non-Latin stamp text and
   `--pages` to stamp a subset. The stamp follows page rotation automatically.
3. `compress` recompresses streams and drops duplicate objects only; when the file is
   image-heavy the gain is small and the script says so.
4. `encrypt` defaults to AES-256. The `cryptography` package it needs comes with
   pdfplumber in the `$RUN` line; add `--with cryptography` only if pypdf reports
   `DependencyError`. Fall back to `--algorithm RC4-128` only for old viewers.

## 6. Fill a PDF form

1. List the fields, their types, states and options:
   `$RUN <skill>/scripts/pdf_forms.py list form.pdf` (add `--json` for a machine-readable
   list with page numbers).
2. Write `values.json` keyed by the exact field names: strings for text and choice
   fields, `true`/`false` or a state name for checkboxes, the option value for radio
   groups, a list for multi-select list boxes.
3. Fill: `$RUN <skill>/scripts/pdf_forms.py fill form.pdf -o filled.pdf --data values.json`.
   Unknown names are reported as warnings (`--strict` turns them into an error). The
   script reads the output back and prints every value it stored.
4. Add `--flatten` when the result must be static (no editable fields left). Check
   flattened radio buttons visually; pypdf can merge their appearances.
5. Values with Cyrillic, Hebrew or other non-Latin-1 characters only display when the
   field's font can show them; most forms use Helvetica, and the script then warns
   "the field's font ... is a single-byte font". Draw such text on the page with
   reportlab and a TrueType font (see `references/reportlab-cheatsheet.md`) instead.

## 7. OCR a scanned PDF

1. Run `$RUN <skill>/scripts/pdf_ocr.py scan.pdf -o ocr_out --lang eng` and add
   `--searchable-pdf scan_searchable.pdf` to get a PDF with an invisible text layer.
2. Pick the language data: `--lang heb`, `--lang rus`, `--lang eng+heb`. The script
   checks `tesseract --list-langs` and exits 2 with an install hint when data is missing.
3. Raise `--dpi` (default 300) or change `--psm` when pages come back empty; use
   `--pages` to test on one page before a long run.
4. Read `ocr_out/<name>_ocr.txt` (all pages) or `page_001.txt` files. OCR runs
   locally; nothing is uploaded anywhere.

## 8. Verify the produced file (always)

1. Read every output back before reporting success:
   - `pdf_extract.py out.pdf --info` for page count and metadata, then
     `pdf_extract.py out.pdf --pages 1` to see the first page's text.
   - After `merge`, `split`, `extract-pages`: compare page counts with what was expected.
   - After `watermark`: `PdfReader("out.pdf").pages[0].extract_text()` must contain the
     stamp text (pdfplumber does not group the rotated glyphs).
   - After `encrypt`: `pdf_extract.py out.pdf` without a password must fail with
     "the PDF is encrypted", and succeed with `--password`.
   - After `fill`: `pdf_forms.py list filled.pdf` shows the new values.
   - After `pdf_build.py`: confirm the reported font is a TrueType file when the
     content is not Latin, and the page count matches the page breaks.
2. When poppler is installed, render a page to look at it:
   `pdftoppm -r 60 -png -f 1 -l 1 out.pdf preview` and open `preview-1.png`.
3. Report the absolute output path, the page count and any warnings the script printed.

## 9. Gotchas (details in references/gotchas.md)

- Text comes back in position order: multi-column pages interleave, headers and
  footers are mixed in; crop or use `--layout`.
- Right-to-left text is stored visually, so extracted Hebrew reads reversed; this is a
  property of PDFs, not a bug in the scripts.
- pypdf and pdfplumber index pages from 0; the CLI from 1.
- XFA forms cannot be filled; checkbox states are names like `/Yes`, read them from `list`.
- Built-in PDF fonts cover Latin-1 only; always check the font line of `pdf_build.py`
  and the font warning of `pdf_forms.py fill`.
- Very large files: process page ranges, and expect `compress` to leave images alone.

References: `references/pypdf-cheatsheet.md`, `references/pdfplumber-cheatsheet.md`,
`references/reportlab-cheatsheet.md` (flowables, styles, tables, fonts, page
templates, AcroForm), `references/gotchas.md`.
