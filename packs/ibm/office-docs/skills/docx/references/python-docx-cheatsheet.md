# python-docx cheatsheet

Tested against python-docx 1.2. Run snippets with
`uv run --with python-docx python script.py`. Lengths are `docx.shared` units:
`Inches`, `Cm`, `Mm`, `Pt`, `Emu` (914400 EMU = 1 inch; all lengths are stored as EMU).

## Open, create, save

```python
from docx import Document

doc = Document()                     # new file from the built-in default template
doc = Document("/abs/input.docx")    # existing file (.docx, .docm, .dotx)
doc.save("/abs/output.docx")         # always save to a new path while iterating
```

Walk body content in document order (paragraphs and tables interleaved):

```python
from docx.text.paragraph import Paragraph
for item in doc.iter_inner_content():          # python-docx >= 1.0
    if isinstance(item, Paragraph):
        print("P", item.style.name, item.text)
    else:
        print("TABLE", len(item.rows), "rows")
```

`doc.paragraphs` and `doc.tables` list only top-level items; cells have their own
`.paragraphs` and `.tables`. `paragraph.text` includes hyperlink text (1.0+).

## Document properties

```python
cp = doc.core_properties
cp.title = "Quarterly report"; cp.author = "Ops team"; cp.subject = "Q3"
cp.keywords = "status, q3"; cp.comments = "Generated"; cp.last_modified_by = "Ops team"
import datetime as dt
cp.created = cp.modified = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
```

Always set `author`, `created` and `modified`: the default template carries the
library's own author name and an old creation date. Custom properties (the
"Custom" tab) have no API; edit `docProps/custom.xml` by hand if required.

## Styles

```python
from docx.enum.style import WD_STYLE_TYPE
names = [s.name for s in doc.styles]                     # what the file really has
normal = doc.styles["Normal"]                            # KeyError if absent
normal.font.name = "Calibri"; normal.font.size = Pt(11)
style = doc.styles.add_style("Brand Body", WD_STYLE_TYPE.PARAGRAPH)
style.base_style = normal
style.next_paragraph_style = normal
style.paragraph_format.space_after = Pt(6)
style.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
char_style = doc.styles.add_style("Code Inline", WD_STYLE_TYPE.CHARACTER)
char_style.font.name = "Consolas"
```

Apply with `doc.add_paragraph(text, style="Brand Body")`, `paragraph.style = "Heading 2"`,
`paragraph.add_run(text, style="Code Inline")`, `table.style = "Table Grid"`.
Built-in styles exist in a document only after Word (or the default template) has
written them; a customer template may lack `List Bullet`, `Heading 4` or `Table Grid`.
Check with `name in names` before using a style, and prefer styles over direct
formatting so the customer can restyle the file later.

## Paragraphs and runs

```python
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
p = doc.add_paragraph("Lead text ", style="Normal")
r = p.add_run("bold and red")
r.bold = True; r.italic = None; r.underline = True     # None = inherit from style
r.font.size = Pt(12); r.font.color.rgb = RGBColor(0xAA, 0x00, 0x00)
r.add_break(WD_BREAK.LINE)                              # soft line break inside the paragraph
r.add_break(WD_BREAK.PAGE)                              # page break inside a run
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
pf = p.paragraph_format
pf.space_before = Pt(0); pf.space_after = Pt(6)
pf.line_spacing = 1.15                                  # multiple; or Pt(14) exact
pf.left_indent = Inches(0.5); pf.first_line_indent = Inches(-0.25)
pf.keep_with_next = True; pf.page_break_before = False; pf.widow_control = True
doc.add_heading("Section title", level=1)               # level 0 = "Title" style
doc.add_page_break()
before = p.insert_paragraph_before("Inserted above p", style="Normal")
```

Delete a paragraph or table by removing its element: `p._p.getparent().remove(p._p)`.
Move a table after a paragraph: `p._p.addnext(table._tbl)`.
Setting `p.text = "..."` or `cell.text = "..."` replaces all runs with one unformatted
run: edit `run.text` when formatting must survive.

Tab stops (for example right-aligned prices):

```python
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
p.paragraph_format.tab_stops.add_tab_stop(Inches(6), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
p.add_run("Item\t12.50")
```

## Tables and cell merging

```python
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE
table = doc.add_table(rows=1, cols=3)
table.style = "Table Grid"                     # borders; absent style = no borders
table.alignment = WD_TABLE_ALIGNMENT.CENTER
hdr = table.rows[0].cells
for cell, text in zip(hdr, ["Item", "Qty", "Price"]):
    cell.paragraphs[0].add_run(text).bold = True
row = table.add_row().cells
row[0].text = "Apples"; row[1].text = "3"; row[2].text = "1.50"
row[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
row[1].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
cell = table.cell(1, 0)                        # row, column (0-based)
```

Widths: Word reads the width of each cell, not of the column object. Set
`table.autofit = False` and the same width on every cell of a column:

```python
table.autofit = False
for width, column in zip([Inches(3), Inches(1), Inches(1)], table.columns):
    for cell in column.cells:
        cell.width = width
```

Merging: `a.merge(b)` merges the rectangle spanning both cells and returns the merged
cell; the texts of merged cells are concatenated as paragraphs.

```python
title_cell = table.cell(0, 0).merge(table.cell(0, 2))    # whole first row
title_cell.text = "Fruit"
```

After a merge, `row.cells` returns the same cell object for each grid position it
covers; compare `cell._tc` to detect repeats when reading.

Row height, header row repeated on every page, cell shading (OOXML):

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
table.rows[0].height = Cm(0.8); table.rows[0].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
tr_pr = table.rows[0]._tr.get_or_add_trPr()
tr_pr.append(OxmlElement("w:tblHeader"))                  # repeat header row
shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "D9E2F3")
table.cell(0, 0)._tc.get_or_add_tcPr().append(shd)
```

A nested table: `inner = cell.add_table(rows=2, cols=2)`. Two tables directly after
each other merge in Word; add an empty paragraph between them.

## Images

```python
doc.add_picture("/abs/chart.png", width=Inches(5.5))   # own paragraph, keeps aspect ratio
pic_par = doc.paragraphs[-1]; pic_par.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = doc.add_paragraph().add_run(); run.add_picture("/abs/icon.png", height=Cm(1))  # inline in a run
shape = doc.inline_shapes[-1]; print(shape.width, shape.height)   # EMU
```

Formats: PNG, JPEG, GIF, BMP, TIFF. Give `width` or `height`, not both, to keep the
aspect ratio. Fit to the text area:

```python
s = doc.sections[-1]
max_w = s.page_width - s.left_margin - s.right_margin
shape = doc.inline_shapes[-1]
if shape.width > max_w:
    shape.height = int(shape.height * max_w / shape.width); shape.width = max_w
```

Replacing an existing picture means swapping the image part behind the relationship id
found in `shape._inline.graphic.graphicData.pic.blipFill.blip.embed`; simpler is to
delete the paragraph holding the picture and add a new one.

## Sections, page size, orientation, margins

```python
from docx.enum.section import WD_ORIENT, WD_SECTION
s = doc.sections[0]
s.page_width, s.page_height = Mm(210), Mm(297)          # A4 (default template is Letter)
s.left_margin = s.right_margin = Cm(2); s.top_margin = s.bottom_margin = Cm(2.5)
s.orientation = WD_ORIENT.LANDSCAPE
s.page_width, s.page_height = s.page_height, s.page_width   # orientation alone does not swap sizes
wide = doc.add_section(WD_SECTION.NEW_PAGE)             # content after this call lands in the new section
wide.orientation = WD_ORIENT.LANDSCAPE
wide.page_width, wide.page_height = wide.page_height, wide.page_width
```

`WD_SECTION.CONTINUOUS` starts a section without a page break (for column changes).

## Headers and footers

```python
s = doc.sections[0]
header = s.header                       # default header of the section
header.is_linked_to_previous = False    # give this section its own definition
header.paragraphs[0].text = "Left\tCentre\tRight"   # Header style has centre and right tabs
s.different_first_page_header_footer = True
s.first_page_header.paragraphs[0].text = "Cover page header"
doc.settings.odd_and_even_pages_header_footer = True
s.even_page_footer.paragraphs[0].text = "Even pages"
footer_table = s.footer.add_table(rows=1, cols=2, width=Inches(6))
```

Accessing `s.header.paragraphs` on a section whose header is linked to the previous
one creates an empty definition; check `is_linked_to_previous` first when only reading.
Header and footer images work through `header.paragraphs[0].add_run().add_picture(...)`.

## Page numbers (field codes)

python-docx has no field API; build the `PAGE` field from OOXML pieces inside a run:

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def add_field(run, instruction):
    """Append a field such as PAGE, NUMPAGES, DATE or TOC to a run."""
    begin = OxmlElement("w:fldChar"); begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = f" {instruction} "
    separate = OxmlElement("w:fldChar"); separate.set(qn("w:fldCharType"), "separate")
    cached = OxmlElement("w:t"); cached.text = "1"          # shown until fields are updated
    end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end")
    for element in (begin, instr, separate, cached, end):
        run._r.append(element)

footer_p = doc.sections[0].footer.paragraphs[0]
footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
footer_p.add_run("Page "); add_field(footer_p.add_run(), "PAGE")
footer_p.add_run(" of "); add_field(footer_p.add_run(), "NUMPAGES")
```

Word recalculates fields when it opens the file or on F9; LibreOffice recalculates
them during PDF conversion. A table of contents is the same trick with
`TOC \o "1-3" \h \z \u`; ask Word to refresh it by setting `w:updateFields` in
`settings.xml` (`doc.settings.element.append(OxmlElement("w:updateFields"))` with
`w:val="true"`), which makes Word prompt the user to update fields on opening.

## Lists

```python
doc.add_paragraph("First point", style="List Bullet")
doc.add_paragraph("Sub point", style="List Bullet 2")    # deeper level styles: 2, 3
doc.add_paragraph("Step one", style="List Number")
doc.add_paragraph("Step two", style="List Number")
```

All `List Number` paragraphs share one numbering instance, so a second list continues
at the next number. To restart, clone the instance: add a `w:num` to
`doc.part.numbering_part.element` that points to the same `w:abstractNumId` and carries
`w:lvlOverride[w:ilvl=0]/w:startOverride[w:val=1]`, then set that `numId` on the
paragraphs (`p._p.get_or_add_pPr().get_or_add_numPr()` with `get_or_add_numId().val`
and `get_or_add_ilvl().val`). `scripts/docx_build.py` contains a working
`new_num_instance` helper. Word-authored lists usually use style `List Paragraph`
plus a paragraph-level `numPr`; `ilvl` is the nesting depth.

## Fonts

```python
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml.ns import qn
font = doc.styles["Normal"].font
font.name = "Arial"; font.size = Pt(11)
rfonts = doc.styles["Normal"].element.get_or_add_rPr().get_or_add_rFonts()
rfonts.set(qn("w:eastAsia"), "Yu Gothic")     # East Asian text uses its own slot
rfonts.set(qn("w:cs"), "Arial")               # complex-script slot (Hebrew, Arabic)
run.font.highlight_color = WD_COLOR_INDEX.YELLOW
run.font.superscript = True; run.font.small_caps = True; run.font.strike = True
```

`font.name` sets the ASCII and high-ANSI slots only. Theme fonts (`+Body`) in a
template override nothing here but a viewer without the font substitutes silently.

## Right-to-left paragraphs (Hebrew, Arabic)

A right-to-left paragraph needs `w:bidi` in the paragraph properties, right alignment,
and `w:rtl` on its runs; complex-script bold and size use `w:bCs` and `w:szCs`.
Element order inside `pPr` and `rPr` matters to Word, so insert before the known
successors instead of appending blindly:

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def set_rtl(paragraph, lang="he-IL"):
    ppr = paragraph._p.get_or_add_pPr()
    if ppr.find(qn("w:bidi")) is None:
        ppr.insert_element_before(OxmlElement("w:bidi"),
            "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
            "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
            "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for run in paragraph.runs:
        rpr = run._r.get_or_add_rPr()
        if rpr.find(qn("w:rtl")) is None:
            rpr.insert_element_before(OxmlElement("w:rtl"),
                "w:cs", "w:em", "w:lang", "w:eastAsianLayout", "w:specVanish", "w:oMath")
        lang_el = rpr.find(qn("w:lang"))
        if lang_el is None:
            lang_el = OxmlElement("w:lang"); rpr.insert_element_before(lang_el, "w:eastAsianLayout", "w:specVanish", "w:oMath")
        lang_el.set(qn("w:bidi"), lang)

p = doc.add_paragraph(hebrew_text)          # any Hebrew or Arabic string
set_rtl(p)                                  # use lang="ar-SA" for Arabic
```

Mixed-direction text (a Latin product name inside an Arabic sentence) is handled by
the renderer once the paragraph is marked `bidi`; keep the Latin part in its own run
without `w:rtl`. Tables in right-to-left documents: set `w:bidiVisual` in `tblPr` so
columns flow right to left. The `"rtl": true` key of a `paragraph` block in
`scripts/docx_build.py` applies the same paragraph and run markers.

## Hyperlinks and comments

```python
# External hyperlink (no high-level API; relationship + w:hyperlink element)
from docx.opc.constants import RELATIONSHIP_TYPE as RT
def add_hyperlink(paragraph, url, text):
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink"); link.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r"); rpr = OxmlElement("w:rPr")
    rstyle = OxmlElement("w:rStyle"); rstyle.set(qn("w:val"), "Hyperlink"); rpr.append(rstyle)
    t = OxmlElement("w:t"); t.text = text; new_run.append(rpr); new_run.append(t)
    link.append(new_run); paragraph._p.append(link)

# Comments (python-docx >= 1.2)
run = doc.paragraphs[0].runs[0]
doc.add_comment(runs=[run], text="Please confirm this figure", author="Reviewer", initials="RV")
```

Reading hyperlinks: `paragraph.hyperlinks` gives `.text`, `.address` and `.runs`.
