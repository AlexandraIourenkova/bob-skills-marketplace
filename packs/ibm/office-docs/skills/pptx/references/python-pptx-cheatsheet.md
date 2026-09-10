# python-pptx cheat sheet

Everything below is for python-pptx 1.0 and Python 3.11+. Run scripts with
`uv run --with python-pptx python script.py`. The library reads and writes the
file format only; it does not render slides (use LibreOffice for that).

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Cm, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE, PP_PLACEHOLDER, MSO_CONNECTOR
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.chart.data import CategoryChartData, XyChartData, BubbleChartData
```

## 1. Units

All positions and sizes are integers in English Metric Units (EMU).

| Unit | EMU | Helper |
|---|---|---|
| 1 inch | 914,400 | `Inches(1)` |
| 1 cm | 360,000 | `Cm(1)` |
| 1 point | 12,700 | `Pt(1)` |
| 1 pixel at 96 dpi | 9,525 | `Emu(9525)` |

Helpers return a `Length` (an `int` subclass) with `.inches`, `.cm`, `.pt`, `.emu`
properties, so `shape.width.inches` works and `shape.width = Inches(4)` works.
Font sizes take `Pt(...)`.

## 2. Presentation and slide size

```python
prs = Presentation()                 # built-in template, 4:3, 10 x 7.5 in
prs = Presentation("template.pptx")  # a .pptx only; .potx/.ppsx raise ValueError (see below)
prs.slide_width, prs.slide_height    # EMU
prs.slide_width = Emu(12192000)      # 16:9 widescreen, exactly 13.333 x 7.5 in
prs.slide_height = Emu(6858000)      # (Inches(13.333) gives 12,191,695, 0.0003 in short)
prs.save("out.pptx")                 # also accepts a file-like object
```

`Presentation()` checks the content type of the main part and refuses a
template (`.potx`) or slideshow (`.ppsx`) package: "file 'brand.potx' is not a
PowerPoint file, content type is '...presentationml.template.main+xml'". Save
the template as `.pptx` in PowerPoint, or rewrite that one content type in
`[Content_Types].xml` to `...presentationml.presentation.main+xml` with the
standard-library `zipfile` module and open the result from a `BytesIO` (this is
what `open_presentation` in `scripts/pptx_build.py` does).

Common sizes: 16:9 widescreen 13.333 x 7.5 in; 4:3 standard 10 x 7.5 in;
16:10 10 x 6.25 in; A4 landscape 11.69 x 8.27 in.

Changing the size does not move the placeholders defined by the layouts: with the
built-in template on a 16:9 slide, the title and body stay 9 in wide and leave a
gap on the right. Either start from a 16:9 template or set `left/top/width/height`
on each placeholder after adding the slide.

Opening a template that already contains slides keeps those slides; delete them
first if you only want the layouts (section 10).

## 3. Layouts and placeholders

```python
for index, layout in enumerate(prs.slide_layouts):
    print(index, layout.name, [(ph.placeholder_format.idx, ph.placeholder_format.type) for ph in layout.placeholders])
slide = prs.slides.add_slide(prs.slide_layouts[1])
```

Built-in template layouts: 0 Title Slide, 1 Title and Content, 2 Section Header,
3 Two Content, 4 Comparison, 5 Title Only, 6 Blank, 7 Content with Caption,
8 Picture with Caption, 9 Title and Vertical Text, 10 Vertical Title and Text.
Corporate templates use their own names and order: always look them up by name.

```python
slide.shapes.title                 # title placeholder or None
slide.placeholders[1]              # by idx (the placeholder id), NOT by position
for ph in slide.placeholders:
    ph.placeholder_format.idx      # 0 title, 1 body on most layouts, 10+ for others
    ph.placeholder_format.type     # PP_PLACEHOLDER.TITLE, CENTER_TITLE, SUBTITLE, BODY, OBJECT, PICTURE, CHART, TABLE, ...
```

A slide placeholder inherits position, size and text style from the layout. Only
the placeholders that receive content are created on the slide; an empty
placeholder shows a prompt in edit mode but nothing in slide show or PDF. To
remove one: `ph._element.getparent().remove(ph._element)`.

Picture placeholders: `ph.insert_picture("img.png")` (crops to fill the frame).
Chart placeholders: `ph.insert_chart(XL_CHART_TYPE.PIE, chart_data)`.
Table placeholders: `ph.insert_table(rows, cols)`.

## 4. Text frames, paragraphs, runs

```python
box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
tf = box.text_frame
tf.text = "First paragraph\nSecond paragraph"   # "\n" starts a new paragraph, "\v" a line break
tf.word_wrap = True
tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE  # applied by PowerPoint when it opens the file
tf.vertical_anchor = MSO_ANCHOR.MIDDLE
tf.margin_left = tf.margin_right = Inches(0.1)

p = tf.paragraphs[0]           # every frame has at least one paragraph
p = tf.add_paragraph()
p.text = "Bullet text"
p.level = 1                    # 0..8, indentation and bullet style come from the layout
p.alignment = PP_ALIGN.LEFT    # LEFT, CENTER, RIGHT, JUSTIFY
p.space_before = Pt(6); p.space_after = Pt(0); p.line_spacing = 1.1
p.font.size = Pt(20)           # paragraph default, runs can override

run = p.add_run()
run.text = "bold part"
run.font.bold = True; run.font.italic = True; run.font.underline = True
run.font.size = Pt(24)
run.font.name = "Calibri"
run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
run.hyperlink.address = "https://example.com"
```

Assigning `tf.text`, `p.text` or `shape.text` replaces all runs, so formatting is
lost; to keep it, change `run.text` on the existing runs (see
`scripts/pptx_replace_text.py`). Bullets are decided by the layout, not by the
paragraph: a body placeholder shows bullets, a text box does not. To suppress a
bullet on one paragraph add `<a:buNone/>` to its `pPr`:

```python
from pptx.oxml.xmlchemy import OxmlElement
p_pr = p._p.get_or_add_pPr()
p_pr.insert_element_before(OxmlElement("a:buNone"), "a:tabLst", "a:defRPr", "a:extLst")
p_pr.set("marL", "0"); p_pr.set("indent", "0")
```

`tf.fit_text(max_size=24)` shrinks text to fit but needs the font file on disk;
prefer `MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` or shorter text.

## 5. Tables

```python
shape = slide.shapes.add_table(rows=4, cols=3, left=Inches(1), top=Inches(1.5), width=Inches(8), height=Inches(2))
table = shape.table
table.columns[0].width = Inches(3)
table.rows[0].height = Inches(0.5)
cell = table.cell(0, 0)
cell.text = "Header"                          # replaces formatting like tf.text
cell.text_frame.paragraphs[0].runs[0].font.bold = True
cell.fill.solid(); cell.fill.fore_color.rgb = RGBColor(0xD9, 0xE2, 0xF3)
cell.vertical_anchor = MSO_ANCHOR.MIDDLE
cell.margin_left = Inches(0.05)
table.cell(1, 0).merge(table.cell(1, 2))      # merge a range; merged cells report .is_merge_origin / .is_spanned
table.first_row = True                        # header row styling from the table style
for row in table.rows:
    for c in row.cells: print(c.text)
```

Reading: `shape.has_table` then `shape.table`. Column widths must add up to the
shape width; row heights grow with content when opened in PowerPoint.

## 6. Pictures

```python
pic = slide.shapes.add_picture("photo.png", Inches(1), Inches(1))                 # native size (pixels at the image dpi)
pic = slide.shapes.add_picture("photo.png", Inches(1), Inches(1), width=Inches(5))  # one dimension keeps the aspect ratio
pic = slide.shapes.add_picture("photo.png", Inches(1), Inches(1), Inches(5), Inches(3))  # both dimensions stretch
pic.crop_left = 0.1            # fraction of the width cropped away
pic.image.blob, pic.image.ext, pic.image.size, pic.image.dpi   # read an embedded image
pic._element._nvXxPr.cNvPr.set("descr", "Alt text for screen readers")
```

Supported formats: PNG, JPEG, GIF, BMP, TIFF (Pillow decodes the header). SVG,
WebP and PDF are not supported: convert them to PNG first. To fit an image inside
a box without distortion, add it at native size, compute
`scale = min(box_w / pic.width, box_h / pic.height)`, then set width and height.
A file-like object (`io.BytesIO`) works instead of a path.

## 7. Native charts

```python
data = CategoryChartData()
data.categories = ["Q1", "Q2", "Q3", "Q4"]           # strings, numbers or dates
data.add_series("2025", (10.2, 11.0, 12.4, 13.1))     # numbers or None for a gap
data.add_series("2024", (8.1, 9.2, 9.8, 10.5), number_format="0.0")
frame = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.5), Inches(8), Inches(5), data)
chart = frame.chart
```

Chart types (all `XL_CHART_TYPE.*`): `COLUMN_CLUSTERED`, `COLUMN_STACKED`,
`COLUMN_STACKED_100`, `BAR_CLUSTERED`, `BAR_STACKED`, `LINE`, `LINE_MARKERS`,
`PIE`, `PIE_EXPLODED`, `DOUGHNUT`, `AREA`, `AREA_STACKED`, `RADAR`,
`XY_SCATTER` (use `XyChartData`), `BUBBLE` (use `BubbleChartData`).
Pie and doughnut charts take exactly one series.

```python
chart.has_title = True
chart.chart_title.text_frame.text = "Revenue by quarter"
chart.has_legend = True
chart.legend.position = XL_LEGEND_POSITION.BOTTOM     # RIGHT, LEFT, TOP, CORNER
chart.legend.include_in_layout = False
chart.font.size = Pt(14)                              # default for all chart text

plot = chart.plots[0]
plot.vary_by_categories = False     # one colour per series (True gives one colour per bar)
plot.gap_width = 80; plot.overlap = 0
plot.has_data_labels = True
labels = plot.data_labels
labels.number_format = "#,##0.0"; labels.number_format_is_linked = False
labels.position = XL_LABEL_POSITION.OUTSIDE_END        # INSIDE_END, CENTER, ABOVE, BEST_FIT (pie)
labels.show_value = True; labels.show_percentage = True; labels.show_category_name = False
labels.font.size = Pt(12)

series = plot.series[0]
series.format.fill.solid(); series.format.fill.fore_color.rgb = RGBColor(0x0F, 0x62, 0xFE)
series.format.line.color.rgb = RGBColor(0x0F, 0x62, 0xFE); series.format.line.width = Pt(2.5)
series.smooth = False                # line charts
series.marker.style                  # XL_MARKER_STYLE for line/scatter
point = series.points[2]             # one bar or one pie slice
point.format.fill.solid(); point.format.fill.fore_color.rgb = RGBColor(0xDA, 0x1E, 0x28)

axis = chart.value_axis              # not available on pie/doughnut
axis.minimum_scale = 0; axis.maximum_scale = 20; axis.major_unit = 5
axis.has_major_gridlines = True
axis.tick_labels.number_format = "0"; axis.tick_labels.number_format_is_linked = False
axis.tick_labels.font.size = Pt(12)
axis.axis_title.text_frame.text = "USD millions"; axis.has_title = True
chart.category_axis.tick_labels.font.size = Pt(12)
chart.category_axis.visible = True
```

Update data in place: `chart.replace_data(new_chart_data)`.
Read a chart: `shape.has_chart`, `chart.chart_type`, `list(plot.categories)`,
`[(s.name, list(s.values)) for s in plot.series]`. Chart text (title, labels)
lives in the chart part, not in slide shapes, so slide-level text searches do
not see it.

## 8. Speaker notes

```python
slide.has_notes_slide                       # False until notes exist; do not create notes just to check
notes = slide.notes_slide                   # created on first access
notes.notes_text_frame.text = "Say this.\nThen this."
notes.notes_text_frame.text                # read back
```

## 9. Shapes, lines, colours

```python
shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(1), Inches(3), Inches(1))
shape.text = "Label"                        # centred text inside the shape
shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor(0xF4, 0xF4, 0xF4)
shape.fill.background()                     # no fill
shape.line.color.rgb = RGBColor(0x16, 0x16, 0x16); shape.line.width = Pt(1)
shape.line.fill.background()                # no outline
shape.shadow.inherit = False                # remove the theme shadow
shape.rotation = 15.0
shape.name = "Callout 1"
shape.adjustments[0] = 0.1                  # corner radius of a rounded rectangle
conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(3), Inches(6), Inches(3))
conn.line.width = Pt(2)
group = slide.shapes.add_group_shape([shape, conn])     # or add_group_shape() then group.shapes.add_*
shape.click_action.hyperlink.address = "https://example.com"
```

Theme colours: `shape.fill.fore_color.theme_color = MSO_THEME_COLOR.ACCENT_1`
(`from pptx.enum.dml import MSO_THEME_COLOR`), optionally
`fore_color.brightness = 0.25` (lighter) or `-0.25` (darker). RGB values are
`RGBColor(r, g, b)` or `RGBColor.from_string("0F62FE")`.

Shape order in `slide.shapes` is z-order (first is at the back). To send a shape
to the back: `spTree = slide.shapes._spTree; spTree.remove(el); spTree.insert(2, el)`
with `el = shape._element` (indexes 0 and 1 are `nvGrpSpPr` and `grpSpPr`).

## 10. Reading and managing slides

```python
prs = Presentation("deck.pptx")
for number, slide in enumerate(prs.slides, start=1):
    print(number, slide.slide_layout.name, slide.slide_id)
    for shape in slide.shapes:
        shape.shape_type                # MSO_SHAPE_TYPE.PICTURE, TABLE, CHART, GROUP, TEXT_BOX, PLACEHOLDER, AUTO_SHAPE, LINE
        shape.has_text_frame, shape.has_table, shape.has_chart
        shape.is_placeholder, shape.left, shape.top, shape.width, shape.height, shape.name
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for inner in shape.shapes: ...        # recurse, groups nest
```

Delete a slide (there is no public API):

```python
sld_id_lst = prs.slides._sldIdLst
sld_id = sld_id_lst[index]
prs.part.drop_rel(sld_id.rId)
sld_id_lst.remove(sld_id)
```

Reorder: move the `sldId` element inside `sld_id_lst`
(`sld_id_lst.remove(el); sld_id_lst.insert(new_index, el)`).
Duplicating a slide or copying slides between decks is not supported by the API;
rebuild the slide from its content instead (pictures and charts carry
relationships that a plain element copy does not bring along).

Slide masters and layouts: `prs.slide_master`, `prs.slide_masters`,
`layout.slide_master`, `layout.placeholders`; text on masters and layouts (footers,
logos) is edited the same way as slide shapes.

## 11. Gotchas

- Sizes are EMU integers: pass `Inches()`/`Pt()` or you get microscopic shapes.
- `placeholders[1]` means idx 1, not the second placeholder; iterate and check `placeholder_format.type` in templates.
- The built-in template is 4:3; set 16:9 explicitly and reposition placeholders, or build on a 16:9 template.
- `text = ...` on a frame, paragraph, cell or shape drops run formatting.
- Fonts are not embedded; a font missing on the viewer's machine is substituted.
- `MSO_AUTO_SIZE` flags are honoured by PowerPoint when it opens the file; python-pptx does not compute the shrunken size, and LibreOffice may render the original size.
- Chart values must be numbers (or None); category labels are strings, numbers or dates.
- Accessing `slide.notes_slide` creates an empty notes slide; test `has_notes_slide` when reading.
- Pictures in unsupported formats (SVG, WebP) raise on `add_picture`; convert to PNG first.
- Saving over the input path is allowed but keep the original: write to a new file and compare.
