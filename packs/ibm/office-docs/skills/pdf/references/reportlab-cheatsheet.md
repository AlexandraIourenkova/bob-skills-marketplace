# reportlab cheatsheet

reportlab creates PDFs. The low-level `canvas` draws at coordinates; the high-level
`platypus` layer lays out flowables (paragraphs, tables, images) across pages.
Units are points (72 per inch); `from reportlab.lib.units import mm, cm, inch`.
The origin of the canvas is the bottom-left corner of the page.

## Canvas basics

```python
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, LETTER, landscape

c = canvas.Canvas("out.pdf", pagesize=A4)
width, height = A4
c.setTitle("Title"); c.setAuthor("Me"); c.setSubject("Subject")
c.setFont("Helvetica", 12)
c.drawString(72, height - 72, "Hello")             # x, y from bottom-left
c.drawRightString(width - 72, 40, "Page 1")
c.drawCentredString(width / 2, 40, "centered")
c.line(72, 100, width - 72, 100)
c.rect(72, 200, 100, 50, stroke=1, fill=0)
c.drawImage("logo.png", 72, 600, width=120, height=60, preserveAspectRatio=True, mask="auto")
c.setFillColor(colors.red, alpha=0.3)              # transparency for stamps
c.saveState(); c.translate(300, 400); c.rotate(45); c.drawCentredString(0, 0, "DRAFT"); c.restoreState()
c.showPage()                                       # finish the page
c.save()
```

## Platypus document

```python
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table,
                                TableStyle, Image, ListFlowable, ListItem, KeepTogether,
                                CondPageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

styles = getSampleStyleSheet()                     # Normal, BodyText, Title, Heading1..6, Bullet, Code
body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=10.5,
                      leading=14, spaceAfter=6, alignment=TA_JUSTIFY)

story = [
    Paragraph("Title", styles["Title"]),
    Paragraph("Heading", styles["Heading1"]),
    Paragraph("Body with <b>bold</b>, <i>italic</i>, <font color='red'>color</font>, "
              "<super>2</super> and a <a href='https://example.org'>link</a>.", body),
    Spacer(1, 12),
    ListFlowable([ListItem(Paragraph("one", body)), ListItem(Paragraph("two", body))],
                 bulletType="bullet"),               # "1", "a", "A", "i" for numbering
    KeepTogether([Paragraph("heading", styles["Heading2"]), Paragraph("text", body)]),
    CondPageBreak(100),                            # break unless 100pt remain
    PageBreak(),
]
doc = SimpleDocTemplate("out.pdf", pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=20 * mm, bottomMargin=20 * mm,
                        title="Title", author="Me", subject="Subject")
doc.build(story)
```

Paragraph text is XML-like: escape `&`, `<`, `>` with `xml.sax.saxutils.escape` unless
you write the markup yourself. `<br/>` forces a line break. Bold and italic tags only
work when the font family has those faces registered (see fonts below).

## Tables

```python
data = [["Item", "Qty", "Price"], ["Bolt", "12", "0.30"]]
table = Table(data, colWidths=[80 * mm, 30 * mm, 30 * mm], repeatRows=1, hAlign="LEFT")
table.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),      # (col,row) from top-left; -1 = last
    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("SPAN", (0, 2), (1, 2)),                          # merge cells
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
]))
```

Wrap long cell text in `Paragraph` objects, otherwise cells never wrap and the table
overflows the page. Give `colWidths` explicitly when cells are Paragraphs.
`repeatRows=1` repeats the header on every page.

## Images

```python
from reportlab.lib.utils import ImageReader
iw, ih = ImageReader("chart.png").getSize()
image = Image("chart.png", width=120 * mm, height=120 * mm * ih / iw)   # keep aspect ratio
image.hAlign = "CENTER"
```

PNG, JPEG, GIF work through Pillow (installed with reportlab). SVG is not supported
directly; convert it first or draw with `reportlab.graphics`.

## Fonts and Unicode

The built-in fonts (Helvetica, Times-Roman, Courier and their variants) cover
Latin-1 only. Anything else (Cyrillic, Hebrew, Arabic, Greek, CJK) needs a TrueType
font registered before use:

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                              italic="DejaVu", boldItalic="DejaVu-Bold")
style = ParagraphStyle("u", fontName="DejaVu", fontSize=11)
```

Typical locations: `/usr/share/fonts` (Linux, DejaVu, Liberation, Noto),
`/Library/Fonts` and `/System/Library/Fonts/Supplemental` (macOS, Arial Unicode),
`C:\Windows\Fonts` (Windows, arial.ttf). The font is subset-embedded, so the PDF
stays small. Missing glyphs render as black boxes or nothing, never as an error.

Right-to-left text: reportlab reorders bidi text only when the optional `rlbidi`
module is installed (`ParagraphStyle(wordWrap="RTL", alignment=TA_RIGHT)`). Without
it, reverse Hebrew strings per line yourself; Arabic also needs glyph shaping, which
reportlab does not do.

## Page templates, headers and footers

```python
def on_page(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 8)
    canv.drawString(doc.leftMargin, doc.pagesize[1] - 30, "Header text")
    canv.drawRightString(doc.pagesize[0] - doc.rightMargin, 20, f"Page {doc.page}")
    canv.restoreState()

doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
```

"Page x of y" needs two passes: subclass `canvas.Canvas`, collect page states in
`showPage`, and draw the numbers in `save()` when the total is known; pass the class
as `doc.build(story, canvasmaker=NumberedCanvas)`.

Different layouts per page (cover page, two columns):

```python
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, NextPageTemplate
doc = BaseDocTemplate("out.pdf", pagesize=A4)
full = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="full")
left = Frame(doc.leftMargin, doc.bottomMargin, doc.width / 2 - 6, doc.height, id="left")
right = Frame(doc.leftMargin + doc.width / 2 + 6, doc.bottomMargin, doc.width / 2 - 6, doc.height, id="right")
doc.addPageTemplates([PageTemplate(id="one", frames=[full], onPage=on_page),
                      PageTemplate(id="two", frames=[left, right])])
story = [Paragraph("cover", styles["Title"]), NextPageTemplate("two"), PageBreak(), ...]
doc.build(story)
```

## Interactive form fields (AcroForm)

```python
form = c.acroForm                                  # on a canvas
form.textfield(name="full_name", value="", x=150, y=700, width=250, height=22, borderWidth=1)
form.checkbox(name="agree", checked=False, x=150, y=660, size=18)
form.radio(name="size", value="Small", selected=True, x=150, y=620, size=16)
form.radio(name="size", value="Large", selected=False, x=230, y=620, size=16)
form.choice(name="country", value="Israel", options=["Israel", "Japan"], x=150, y=580, width=150, height=22)
form.listbox(name="langs", value=["en"], options=["en", "he", "ru"], x=150, y=480, width=150, height=60,
             fieldFlags="multiSelect")
```

Checkbox states are `/Yes` and `/Off`; radio states are the `value` strings.
Set `forceBorder=True` to draw a visible border.

## Charts and drawings

`reportlab.graphics` has `Drawing`, shapes and `charts` (bar, line, pie) that can be
appended to a story as flowables; `renderPM` rasterises them when Pillow is present.
