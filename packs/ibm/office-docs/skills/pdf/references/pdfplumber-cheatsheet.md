# pdfplumber cheatsheet

pdfplumber sits on pdfminer.six and gives access to every character, line, rectangle
and image on a page with coordinates, plus text and table extraction. It is the tool
for reading. It cannot write PDFs. Indexes are 0-based; coordinates use points with
the origin at the top-left of the page (`top` grows downwards; `y0`/`y1` are measured
from the bottom, pdfminer style).

## Opening

```python
import pdfplumber

with pdfplumber.open("in.pdf") as pdf:            # also accepts file objects
    pdf.metadata                                  # dict: Title, Author, CreationDate, ...
    len(pdf.pages)
    page = pdf.pages[0]
    page.width, page.height                       # points
    page.page_number                              # 1-based, matches what viewers show

pdfplumber.open("in.pdf", password="secret")      # encrypted files
pdfplumber.open("in.pdf", pages=[1, 2, 3])        # load only some pages (1-based)
```

## Text

```python
page.extract_text()                               # lines joined with newlines
page.extract_text(layout=True)                    # keeps horizontal positions with spaces
page.extract_text(x_tolerance=1, y_tolerance=3)   # tune word and line grouping
page.extract_text_lines()                         # list of dicts with text and bbox
page.extract_words()                              # [{"text", "x0", "x1", "top", "bottom", ...}]
page.extract_words(keep_blank_chars=True, use_text_flow=True)
page.chars                                        # every glyph with font name, size, position
page.dedupe_chars()                               # page copy without overprinted duplicates
```

`x_tolerance` (default 3) merges characters into words; raise it for widely spaced
fonts, lower it when words run together. `y_tolerance` (default 3) merges lines.
`use_text_flow=True` follows the content stream order instead of sorting by position,
which sometimes fixes multi-column pages.

## Cropping and filtering (columns, headers, footers)

```python
left = page.crop((0, 0, page.width / 2, page.height))          # bbox = (x0, top, x1, bottom)
right = page.crop((page.width / 2, 0, page.width, page.height))
text = left.extract_text() + "\n" + right.extract_text()

body = page.within_bbox((0, 60, page.width, page.height - 60))  # strip header and footer
big = page.filter(lambda obj: obj.get("size", 0) >= 12)         # keep large text only
```

## Tables

```python
page.extract_tables()                             # list of tables, each a list of rows (cells: str or None)
page.extract_table()                              # the largest table only
page.find_tables()                                # Table objects with .bbox, .rows, .cells

settings = {
    "vertical_strategy": "lines",                 # "lines", "lines_strict", "text", "explicit"
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_tolerance": 3,
    "text_x_tolerance": 2,
    "explicit_vertical_lines": [],                # x positions when strategy is "explicit"
}
page.extract_tables(settings)
```

- `lines`: use drawn ruling lines. Works for bordered tables.
- `text`: infer columns from word alignment. Use for borderless tables; expect noise.
- `explicit`: give the column x positions yourself for stubborn layouts.
- Cells with line breaks contain `\n`; merged cells come back as `None` in the covered positions.

## Graphics and images

```python
page.lines, page.rects, page.curves               # vector objects with coordinates
page.images                                       # [{"x0", "top", "width", "height", "srcsize", ...}]
page.annots                                       # annotations (links, comments)
page.hyperlinks                                   # link annotations with "uri"
```

`page.images` non-empty with `extract_text()` empty is the signature of a scanned page.

## Debug rendering

```python
img = page.to_image(resolution=100)               # needs Pillow (and pypdfium2 in recent versions)
img.draw_rects(page.extract_words())
img.debug_tablefinder(settings)
img.save("debug.png")
```

## Memory on large files

```python
with pdfplumber.open("big.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        page.flush_cache()                        # drop parsed objects of that page
```

Iterate page by page and avoid keeping `page.chars` of every page alive.

## Text order pitfalls

- Multi-column layouts come out interleaved; crop each column and extract separately.
- Right-to-left scripts are stored in visual order; Hebrew words appear reversed.
- Ligatures (fi, fl) and custom encodings can produce odd characters; check `page.chars`.
- Headers, footers and page numbers are part of the text; strip them with `within_bbox`.
