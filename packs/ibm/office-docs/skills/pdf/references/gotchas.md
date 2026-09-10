# PDF gotchas

## Page numbers: 1-based in the CLI, 0-based in the libraries

Every script in this skill takes pages the way a viewer shows them: `--pages 1-3,7`
means the first three pages and the seventh. pypdf (`reader.pages[0]`) and
pdfplumber (`pdf.pages[0]`) are 0-based. Subtract 1 when you move from the command
line into code, and print `page.page_number` (pdfplumber, 1-based) when reporting.
PDFs can also carry display labels (`reader.page_labels`, e.g. "iv", "A-2") that
differ from the physical index; the scripts ignore labels.

## Text order and columns

A PDF stores glyphs with coordinates, not paragraphs. Extraction sorts by position, so:

- Two-column pages come out line-interleaved. Crop each column
  (`page.crop((0, 0, page.width / 2, page.height))`) and extract them separately, or
  try `--layout`, which keeps horizontal spacing so columns stay visually apart.
- Headers, footers and page numbers are mixed into the text. Cut them with
  `page.within_bbox(...)` or by dropping the first and last lines.
- Tables read as one line per row when the ruling lines are missing; use
  `--tables --table-strategy text` for borderless tables and expect to clean up.
- Words can be glued together or split when the font's spacing is unusual; tune
  `x_tolerance` in pdfplumber.
- Bold rendered as double-printed glyphs produces doubled characters; use `--dedupe`.
- Hyphenated line ends stay hyphenated.

## Scanned PDFs

A scanned PDF contains one image per page and no text layer. `pdf_extract.py` prints
`notice: ... looks like a scanned PDF` and exits with code 3 when every selected page
has images but no text. Run `pdf_ocr.py`, which needs `pdftoppm` (poppler) and
`tesseract` on PATH plus the language data (`tesseract --list-langs`). OCR quality
depends on resolution (300 dpi is the usual minimum), skew and the right language;
Hebrew needs `heb`, Russian `rus`, mixed pages `eng+heb`. Some PDFs are hybrids: a
scan with an invisible OCR layer already present, so extraction works but the text
has OCR errors. Everything runs locally; no page image leaves the machine.

## Encrypted PDFs

- A user password is required to open the file: every script accepts `--password`.
- An owner password only restricts printing or copying; the file opens with the empty
  user password (`reader.decrypt("")` returns 1, the user-password match; the owner
  password returns 2). The scripts try `""` first, so such files need no `--password`,
  and `pdf_tools.py decrypt in.pdf -o out.pdf` removes the restriction.
- AES encryption and decryption need the `cryptography` package in pypdf. The
  documented `uv run --with pypdf --with pdfplumber --with reportlab` line already
  installs it (pdfplumber depends on pdfminer.six, which depends on cryptography);
  add `--with cryptography` only when pypdf is installed alone and reports
  `DependencyError`, or choose `--algorithm RC4-128` (weak, only for compatibility).
- Passwords given on the command line end up in the shell history, and `pdf_ocr.py`
  hands the password to `pdftoppm -upw`, where other local users can read it from the
  process list while a page renders.

## Forms

- Only AcroForm fields can be listed and filled. XFA forms (Adobe LiveCycle, some
  government forms) keep their data in an XML layer that pypdf does not understand;
  `pdf_forms.py list` warns when `/XFA` is present. Ask for a non-XFA version or
  print the form to a static PDF and overlay text with reportlab.
- Checkbox and radio values are state names (`/Yes`, `/Large`), not booleans, inside
  the file; the fill script converts `true`/`false` and bare names for you. The on
  state is whatever the author chose (`/Yes`, `/On`, `/1`); read it from `list`.
- Text fields show their new value only when the viewer regenerates appearances
  (`NeedAppearances`) or when pypdf has generated an appearance stream; both are done
  by the script. Some viewers cache the old look until the file is reopened.
- `--flatten` paints the values into the page and removes the widgets. pypdf names
  the painted XObject after the field, so radio groups (several widgets, one name)
  can end up sharing one appearance; check flattened radios visually.
- Field appearances use the font named in the field's `/DA` string, usually Helvetica
  (`/Helv`), a single-byte font. Cyrillic, Hebrew and other non-Latin-1 values are
  stored correctly but render empty (or as `?` after `--flatten`); `pdf_forms.py fill`
  warns per field. Draw such text on top of the page with reportlab and a TrueType
  font instead.
- Field names can be hierarchical (`address.street`); use the full dotted name.
- Merging two PDFs that both contain a field called `name` produces one shared
  field; rename fields before merging if they must stay independent.

## Fonts and right-to-left text

- reportlab's built-in fonts only cover Latin-1. `pdf_build.py` looks for DejaVu Sans,
  Arial Unicode, Liberation Sans and Noto Sans in the usual system folders and warns
  when it finds none; then Hebrew, Arabic and Cyrillic characters are silently
  dropped or drawn as boxes. Install DejaVu (`fonts-dejavu` on Debian, `brew install
  --cask font-dejavu` on macOS) or pass `--font /path/to/font.ttf`.
- Bold in `<b>` tags needs a registered bold face; with a single-face font (Arial
  Unicode) bold renders as regular.
- PDFs store text in visual order. reportlab reorders bidi text only with the
  optional `rlbidi` module; without it `pdf_build.py` wraps and reverses Hebrew
  itself in the title, headings, paragraphs, list items, table cells, header and
  footer (correct for Hebrew, isolated letter forms for Arabic, which also needs
  shaping; list bullets stay on the left). Blocks with `"markup": true` cannot be
  reversed safely and stay in logical order; the script warns and names the block.
  Extracting that text back returns the visual (reversed) order; this is true of most
  PDFs produced by any tool, not only ours.
- Watermark text is Helvetica by default; pass `--font` for non-Latin stamps.

## Large files

- pypdf loads the object tree lazily but `writer.append(reader)` copies everything;
  merging hundreds of large files needs memory in proportion. Process in batches.
- pdfplumber keeps parsed characters per page; call `page.flush_cache()` in loops
  and never hold `page.chars` for a whole book.
- `compress` only recompresses content streams and drops duplicate objects; it does
  not resample images, which usually dominate size. Remove or downscale images
  before building, or use `--remove-images` when images are not needed.
- OCR at 300 dpi renders roughly 8 MB per A4 page as PNG; the script deletes the
  images after each page but a 500-page scan still takes minutes.

## Other traps

- Watermarks are drawn in unrotated page space; the script adds `/Rotate` to the
  stamp angle so it looks the same in the viewer, but pages with unusual `mediabox`
  origins may put the stamp off-centre.
- `pdf_tools.py rotate` only sets `/Rotate`; the content is not rewritten, which is
  what viewers and printers expect.
- Metadata dates are strings in `D:YYYYMMDDHHmmSS` form; write them that way.
- reportlab Paragraph text is parsed as XML: an unescaped `&` or `<` breaks the
  build. The build script escapes plain text and only trusts `"markup": true`.
- reportlab draws a table whose column widths exceed the frame past the right page
  edge without raising an error (`LayoutError` is only raised for flowables too tall
  to fit or split). `pdf_build.py` scales `col_widths_mm` down to the text width and
  warns; when you build tables yourself, keep the sum under the page width minus the
  margins.
- `reader.metadata` may be `None` on files without an Info dictionary; XMP metadata
  (`reader.xmp_metadata`) is separate and not touched by the scripts.
