# pypdf cheatsheet

pypdf reads and writes the PDF object structure: pages, metadata, forms, annotations,
encryption. It does not render pages and its text extraction is basic; use pdfplumber
for text and tables. Page indexes in the library are 0-based (`pages[0]` is page 1).

## Reading

```python
from pypdf import PdfReader

reader = PdfReader("in.pdf")             # path, file object or BytesIO
len(reader.pages)                        # page count
page = reader.pages[0]                   # first page (0-based)
page.mediabox.width, page.mediabox.height   # points (1/72 inch), Decimal-like
page.rotation                            # /Rotate value: 0, 90, 180, 270
page.extract_text()                      # plain text, reading order is best effort
page.extract_text(extraction_mode="layout")   # keeps horizontal spacing
reader.metadata                          # DocumentInformation or None
reader.metadata.title, .author, .subject, .creator, .producer, .creation_date
reader.is_encrypted                      # True when a password is needed
reader.decrypt("secret")                 # returns 0 on failure, 1 user pw, 2 owner pw
reader.outline                           # bookmarks (nested lists of Destination)
reader.page_labels                       # display labels such as "i", "ii", "1"
reader.get_fields()                      # AcroForm fields, name -> Field (None when no form)
reader.attachments                       # embedded files, name -> list[bytes]
```

### Images on a page

```python
for image in page.images:                # ImageFile objects (needs Pillow)
    image.name, image.data                # e.g. "Im0.png", raw bytes
    with open(image.name, "wb") as f:
        f.write(image.data)
```

## Writing

```python
from pypdf import PdfReader, PdfWriter

writer = PdfWriter()
writer.add_page(reader.pages[0])          # copy a single page
writer.append(reader)                     # all pages, keeps outlines and form fields
writer.append(reader, pages=[2, 0, 1])    # chosen pages, 0-based, in this order
writer.append(reader, pages=(0, 3))       # pages 0,1,2 as a range
writer.insert_page(page, index=0)
writer.add_blank_page(width=595, height=842)
writer.add_metadata({"/Title": "Report", "/Author": "Team"})
writer.add_outline_item("Chapter 1", page_number=0)
with open("out.pdf", "wb") as handle:
    writer.write(handle)
```

`PdfWriter(clone_from=reader)` starts the writer as a full copy of the input (pages,
metadata, forms, outlines). Prefer it when you only change something in place
(rotate, metadata, watermark, encrypt) so nothing is lost.

## Page operations

```python
page.rotate(90)                           # clockwise, multiples of 90, changes /Rotate only
page.scale_by(0.5)                        # scale content and boxes
page.scale_to(width=595, height=842)
page.merge_page(other_page)               # draw other_page over this one (watermark, stamp)
page.merge_page(other_page, over=False)   # draw it underneath (background)
from pypdf import Transformation
page.merge_transformed_page(other, Transformation().rotate(45).translate(200, 300))
page.cropbox.lower_left = (50, 50)        # crop without deleting content
page.compress_content_streams()           # zlib-compress the content stream
```

A watermark overlay is just a one-page PDF made with reportlab and merged on top;
the overlay should match the target page size (`page.mediabox`).

## Metadata

```python
writer = PdfWriter(clone_from=reader)
writer.add_metadata({"/Title": "T", "/Author": "A", "/Subject": "S", "/Keywords": "k1, k2"})
```

Dates use the PDF format `D:YYYYMMDDHHmmSS+HH'mm'`. `reader.metadata.creation_date`
parses it into a datetime when possible. Keys carry a leading slash in the raw dict.

## Encryption

```python
writer.encrypt(user_password="open", owner_password="admin", algorithm="AES-256")
# algorithms: "RC4-40", "RC4-128", "AES-128", "AES-256", "AES-256-R5"
```

AES needs the optional `cryptography` package (already present with the documented
`uv run` line through pdfplumber; add `--with cryptography` when pypdf runs alone);
RC4 works with pypdf alone but is weak. To remove a password: open, `decrypt(pw)`,
then `PdfWriter(clone_from=reader)` and write.

## Forms (AcroForm)

```python
fields = reader.get_fields()              # name -> Field; Field behaves like a dict
field["/FT"]                              # /Tx text, /Btn button, /Ch choice, /Sig
field["/V"]                               # current value
field["/Ff"]                              # flag bits: radio 1<<15, pushbutton 1<<16, combo 1<<17
field.get("/_States_")                    # pypdf adds the checkbox/radio states, e.g. ['/Off', '/Yes']
field.get("/Opt")                         # choice options

writer = PdfWriter(clone_from=reader)
for page in writer.pages:
    writer.update_page_form_field_values(
        page, {"name": "Jane", "agree": "/Yes", "size": "/Large", "langs": ["en", "he"]},
        auto_regenerate=True,             # set NeedAppearances so viewers redraw the fields
        flatten=False)                    # True paints the appearance into the page
writer.set_need_appearances_writer(True)
```

Checkbox and radio values are state names with a leading slash. `flatten=True` draws
the appearance streams into the page but leaves the widgets in place; remove the
annotations and the `/AcroForm /Fields` entries yourself for a truly static page.
XFA forms (`/AcroForm /XFA` present) are not supported.

## Compression and cleanup

```python
writer = PdfWriter(clone_from=reader)
for page in writer.pages:
    page.compress_content_streams(level=9)
writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
writer.remove_images()                    # drops all images
writer.remove_annotations(subtypes=None)  # drops links, comments, widgets
```

Gains are modest: fonts and images dominate file size and pypdf does not resample images.

## Annotations and links

```python
from pypdf.annotations import Link, FreeText, Highlight
writer.add_annotation(page_number=0, annotation=Link(rect=(50, 50, 200, 80), url="https://example.org"))
page.annotations                          # existing annotations of a page
```

## Errors to expect

- `pypdf.errors.PdfReadError`: damaged file; try `PdfReader(path, strict=False)` (default).
- `pypdf.errors.DependencyError`: AES without `cryptography`.
- `FileNotDecryptedError`: encrypted file used before `decrypt()`.
- Empty `extract_text()` on a page with images: scanned page, OCR is needed.
