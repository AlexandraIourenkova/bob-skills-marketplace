# openpyxl cheatsheet

openpyxl reads and writes the OOXML spreadsheet formats (.xlsx, .xlsm, .xltx, .xltm).
It does not open the legacy binary .xls format and it never evaluates formulas.
Install nothing globally: run scripts with `uv run --with openpyxl python script.py`.

## Workbooks and sheets

```python
from openpyxl import Workbook, load_workbook

wb = Workbook()                     # new workbook with one sheet called "Sheet"
ws = wb.active                      # the first sheet
ws.title = "Data"                   # 31 characters max, no [ ] : * ? / \
extra = wb.create_sheet("Notes")    # appended at the end
extra = wb.create_sheet("First", 0) # inserted at position 0
wb.remove(extra)                    # delete a sheet
copy = wb.copy_worksheet(ws)        # copies cells and styles inside the same workbook
ws.sheet_state = "hidden"           # or "visible"
ws.sheet_properties.tabColor = "1F4E78"
wb.sheetnames                       # ["Data", "Notes"]
wb["Data"]                          # sheet by name (KeyError when missing)
wb.save("out.xlsx")                 # always overwrites the target file

wb = load_workbook("in.xlsx")                     # formulas kept as text
wb = load_workbook("in.xlsx", data_only=True)     # cached results instead of formulas
wb = load_workbook("in.xlsm", keep_vba=True)      # keep macros; save as .xlsm
wb = load_workbook("big.xlsx", read_only=True)    # streaming reader for large files
```

## Cells and ranges

```python
ws["A1"] = "Region"                        # write by coordinate
ws["A1"].value                             # read
ws.cell(row=2, column=1, value="North")    # 1-based row and column, returns the Cell
ws.append(["South", 4, 9.5])               # adds a row after the last used row
ws["A1:C3"]                                # tuple of tuples of cells
ws["A"], ws[2]                             # a whole column / a whole row
ws.max_row, ws.max_column                  # used area (formatted empty cells count)
ws.dimensions                              # "A1:C3"

for row in ws.iter_rows(min_row=2, max_col=3, values_only=True):
    region, units, price = row             # plain values, no Cell objects

for col in ws.iter_cols(min_col=2, max_col=2):
    for cell in col:
        cell.number_format = "#,##0"

ws.insert_rows(2, amount=3)                # shifts cells only: formulas, merged
ws.delete_cols(4)                          #   ranges, charts and validations are NOT updated
ws.move_range("B2:D10", rows=1, cols=0, translate=True)   # translate adjusts formulas inside

from openpyxl.utils import get_column_letter, column_index_from_string
get_column_letter(28)                      # "AB"
column_index_from_string("AB")             # 28
```

`cell.data_type` is "n" (number), "s" (string), "f" (formula), "d" (date), "b" (bool),
"e" (error). `cell.coordinate` is "B2", `cell.row` and `cell.column` are integers.

## Styles

Style objects are immutable: build a new one and assign it, or `copy()` an existing one.

```python
from copy import copy
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, NamedStyle

cell.font = Font(name="Calibri", size=11, bold=True, italic=False, color="FFFFFF")
cell.fill = PatternFill("solid", fgColor="1F4E78")           # hex RGB, no "#"
cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
thin = Side(style="thin", color="999999")
cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
bold = copy(cell.font); bold.bold = True; cell.font = bold  # derive from an existing style

header = NamedStyle(name="header")          # reusable named style
header.font = Font(bold=True)
header.fill = PatternFill("solid", fgColor="D9E1F2")
wb.add_named_style(header)
ws["A1"].style = "header"

ws.column_dimensions["A"].width = 18        # character units, not pixels (default 8.43)
ws.row_dimensions[1].height = 24            # points
ws.column_dimensions["B"].hidden = True
```

openpyxl has no auto-fit. Estimate widths from the longest formatted value plus two
characters and clamp them (8 to 60 is a sensible range).

## Number formats

Excel stores numbers; the number format decides what is displayed.

| Purpose      | Code                          | Value to store        |
|--------------|-------------------------------|-----------------------|
| Integer      | `#,##0`                       | 1234                  |
| Decimal      | `#,##0.00`                    | 1234.5                |
| Currency     | `$#,##0.00;[Red]-$#,##0.00`   | 1234.5                |
| Euro suffix  | `#,##0.00 "EUR"`              | 1234.5                |
| Percent      | `0.0%`                        | 0.125 (shown 12.5%)   |
| Date         | `yyyy-mm-dd`                  | datetime.date         |
| Date + time  | `yyyy-mm-dd hh:mm`            | datetime.datetime     |
| Time only    | `hh:mm:ss`                    | datetime.time         |
| Text         | `@`                           | "00123"               |
| Thousands    | `#,##0,"K"`                   | 1234567 (shown 1,235K)|

```python
cell.number_format = "0.0%"
from openpyxl.styles.numbers import FORMAT_DATE_YYYYMMDD2, FORMAT_PERCENTAGE_00
```

## Formulas

```python
ws["D2"] = "=B2*C2"                        # any string starting with "=" is a formula
ws["D6"] = "=SUM(D2:D5)"
ws["E2"] = "=IF(D2>100,\"high\",\"low\")"  # English function names, comma separators
ws["F2"] = "=VLOOKUP(A2,Prices!$A$2:$B$50,2,FALSE)"
ws["G2"] = "='Q1 Sales'!B2"                # sheet names with spaces are single-quoted
ws["H2"] = "=_xlfn.XLOOKUP(A2,Prices!A:A,Prices!B:B)"   # functions newer than Excel 2007
```

Facts that shape every formula task:

* openpyxl writes the formula text only. It never computes anything, so the cached
  value of a formula cell is empty until Excel or LibreOffice opens and saves the file.
  `load_workbook(path, data_only=True)` then returns `None` for such cells.
* Use English function names and commas even when the target Excel is localized.
  The file format is locale independent; Excel translates on display.
* Functions added after Excel 2007 (IFS, XLOOKUP, TEXTJOIN, CONCAT, MAXIFS, STDEV.S,
  FILTER, UNIQUE, LET, ...) must be stored with the `_xlfn.` prefix or Excel shows #NAME?.
* Array formulas: `from openpyxl.worksheet.formula import ArrayFormula` then
  `ws["E2"] = ArrayFormula("E2:E10", "=B2:B10*C2:C10")`.
* Percent cells hold fractions (0.25), currency cells hold plain numbers.
* Excel accepts at most 8192 characters per formula and 64 nesting levels.

Check formulas with `scripts/xlsx_recalc_check.py`; it tokenizes every formula and,
when LibreOffice is installed, recalculates the workbook and reports error cells.

## Reading values

```python
wb = load_workbook("report.xlsx", data_only=True)   # cached results, None if never calculated
ws = wb["Data"]
rows = list(ws.iter_rows(min_row=2, values_only=True))
```

Never save a workbook that was opened with `data_only=True`: the formulas are gone and
only the cached numbers remain. Load a second copy without `data_only` for editing.

## Charts

```python
from openpyxl.chart import BarChart, LineChart, PieChart, ScatterChart, Reference, Series

chart = BarChart()
chart.type = "col"                          # "col" vertical bars, "bar" horizontal
chart.grouping = "clustered"                # or "stacked" (also set chart.overlap = 100)
chart.title = "Revenue by region"
chart.x_axis.title = "Region"
chart.y_axis.title = "USD"
chart.x_axis.delete = False                 # newer Excel hides axes otherwise
chart.y_axis.delete = False
data = Reference(ws, min_col=4, min_row=1, max_col=4, max_row=5)   # include the header row
cats = Reference(ws, min_col=1, min_row=2, max_row=5)              # data rows only
chart.add_data(data, titles_from_data=True) # header becomes the series name
chart.set_categories(cats)
chart.width, chart.height = 18, 9           # centimetres
chart.style = 10                            # built-in colour scheme 1..48
ws.add_chart(chart, "H2")                   # top-left anchor cell

line = LineChart()                          # same API; one series per data column
pie = PieChart()                            # one series; categories become the slices
scatter = ScatterChart()                    # needs Series(y_values, x_values) objects
xs = Reference(ws, min_col=1, min_row=2, max_row=20)
ys = Reference(ws, min_col=2, min_row=1, max_row=20)
scatter.series.append(Series(ys, xs, title_from_data=True))
```

Keep the totals row out of chart ranges. Charts read from existing files are available
as `ws._charts` (count them for verification, but do not rely on editing them).

## Data validation

```python
from openpyxl.worksheet.datavalidation import DataValidation

dv = DataValidation(type="list", formula1='"North,South,East,West"', allow_blank=True)
dv.error = "Choose a region from the list"; dv.errorTitle = "Invalid region"
dv.prompt = "Pick a region"; dv.promptTitle = "Region"
ws.add_data_validation(dv)
dv.add("A2:A500")                           # ranges can be added after registration

long_list = DataValidation(type="list", formula1="=Lists!$A$1:$A$120")   # inline lists max 255 chars
number = DataValidation(type="whole", operator="between", formula1="0", formula2="100")
decimal = DataValidation(type="decimal", operator="greaterThan", formula1="0")
date = DataValidation(type="date", operator="greaterThanOrEqual", formula1="DATE(2026,1,1)")
custom = DataValidation(type="custom", formula1="=AND(LEN(B2)>0,ISNUMBER(C2))")
```

`showDropDown=True` hides the arrow (the attribute is inverted in the file format);
leave it unset to show the dropdown.

## Conditional formatting

```python
from openpyxl.formatting.rule import CellIsRule, FormulaRule, ColorScaleRule, DataBarRule, IconSetRule

red = PatternFill("solid", fgColor="FFC7CE")
ws.conditional_formatting.add("D2:D100", CellIsRule(operator="lessThan", formula=["0"], fill=red))
ws.conditional_formatting.add("A2:F100", FormulaRule(formula=["$F2=\"late\""], fill=red))
ws.conditional_formatting.add("E2:E100", ColorScaleRule(start_type="min", start_color="F8696B",
                                                        end_type="max", end_color="63BE7B"))
ws.conditional_formatting.add("B2:B100", DataBarRule(start_type="min", end_type="max", color="638EC6"))
ws.conditional_formatting.add("C2:C100", IconSetRule("3TrafficLights1", "percent", [0, 33, 67]))
```

Formula rules are written relative to the top-left cell of the range.

## Freeze panes, filters, tables, printing

```python
ws.freeze_panes = "A2"                      # freeze the header row ("B2" freezes row 1 and column A)
ws.auto_filter.ref = "A1:F200"              # filter buttons; exclude the totals row

from openpyxl.worksheet.table import Table, TableStyleInfo
table = Table(displayName="Sales", ref="A1:F200")            # unique name, no spaces
table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
ws.add_table(table)                         # header cells must be unique non-empty strings

ws.print_title_rows = "1:1"                 # repeat the header on every printed page
ws.page_setup.orientation = "landscape"
ws.page_setup.fitToWidth = 1
ws.sheet_properties.pageSetUpPr.fitToPage = True
```

## Defined names

```python
from openpyxl.workbook.defined_name import DefinedName

wb.defined_names["TaxRate"] = DefinedName("TaxRate", attr_text="Config!$B$2")      # openpyxl >= 3.1
ws.defined_names["LocalRange"] = DefinedName("LocalRange", attr_text="Data!$A$2:$A$50")  # sheet scope
for name, definition in wb.defined_names.items():
    print(name, definition.attr_text)
```

Names may be used in formulas (`=D2*TaxRate`). openpyxl 3.0 used
`wb.defined_names.append(DefinedName(...))` and `wb.defined_names.definedName` instead.

## Dates and times

```python
import datetime as dt
ws["A2"] = dt.date(2026, 1, 31)             # openpyxl applies "yyyy-mm-dd" if the format is General
ws["B2"] = dt.datetime(2026, 1, 31, 9, 30)  # "yyyy-mm-dd h:mm:ss"
ws["C2"] = dt.time(9, 30)
ws["D2"] = "2026-01-31"                     # stays TEXT; convert with dt.date.fromisoformat first
ws["E2"] = "=TODAY()"                       # computed by Excel, cached value empty until then
```

Reading back returns `datetime.datetime` for any cell whose number format is a date
format, even for whole days (midnight). Cells with a date value but a numeric format
come back as the raw serial number (days since 1899-12-30). `wb.epoch` reports the
1900 or 1904 date system.

## Merged cells

```python
ws.merge_cells("A1:D1")                     # only A1 keeps its value; B1..D1 become MergedCell
ws["A1"].alignment = Alignment(horizontal="center")
ws.unmerge_cells("A1:D1")
[str(r) for r in ws.merged_cells.ranges]    # ["A1:D1"]
```

Write the value and style to the top-left cell before or after merging; writing to any
other cell of the range raises `AttributeError: 'MergedCell' object attribute 'value' is read-only`.

## Comments, hyperlinks, images

```python
from openpyxl.comments import Comment
ws["A1"].comment = Comment("Source: finance export", "Bob")
ws["A2"].hyperlink = "https://example.org/report"; ws["A2"].style = "Hyperlink"

from openpyxl.drawing.image import Image  # needs Pillow: uv run --with openpyxl --with pillow
ws.add_image(Image("logo.png"), "H1")
```

## Large files

```python
wb = Workbook(write_only=True)              # streaming writer: low memory, append only
ws = wb.create_sheet("Data")                # write_only workbooks start with no sheet
ws.freeze_panes = "A2"                      # panes and column widths: BEFORE the first append,
ws.column_dimensions["A"].width = 12        #   they are streamed out with the first row
ws.append(["id", "value"])                  # rows must be appended in order
from openpyxl.cell import WriteOnlyCell
cell = WriteOnlyCell(ws, value="Total"); cell.font = Font(bold=True)
ws.append([cell, "=SUM(B2:B1000000)"])      # styled cells go through WriteOnlyCell
ws.auto_filter.ref = "A1:B1000"             # any time before saving
wb.save("big.xlsx")                         # save once; the workbook cannot be reopened for writing

wb = load_workbook("big.xlsx", read_only=True)             # streaming reader
ws = wb["Data"]
for row in ws.iter_rows(min_row=2, values_only=True): ...
wb.close()                                  # read_only workbooks keep the file handle open
```

In write-only mode `ws["A1"]`, `ws.cell()`, merged cells and `insert_rows` are not
available; charts and validations can still be added before saving. In read-only mode
`ws.max_row` may be `None` for files without a stored dimension; iterate to count.
