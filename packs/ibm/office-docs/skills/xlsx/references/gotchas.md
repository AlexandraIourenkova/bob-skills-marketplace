# openpyxl and Excel gotchas

Things that regularly produce a workbook that "looks wrong" in Excel although the
Python code ran without an error. Read this before promising a result to a user.

## 1. Formula results are empty until something recalculates

* openpyxl stores formula text and nothing else. `load_workbook(path, data_only=True)`
  returns `None` for every formula cell of a file that was written by openpyxl and never
  opened by a spreadsheet application. This is not a bug in the file: Excel computes the
  values when it opens it.
* Consequences: a pipeline that writes formulas with openpyxl and then reads the numbers
  back with pandas or `data_only=True` gets `NaN`/`None`. Either compute the numbers in
  Python and write values, or recalculate first.
* Ways to obtain cached values: open and save the file in Excel; run
  `scripts/xlsx_recalc_check.py book.xlsx --save-recalculated book_calc.xlsx` when
  LibreOffice is installed; or `soffice --headless --convert-to xlsx --outdir out book.xlsx`.
* A workbook opened with `data_only=True` and saved again loses all formulas. Keep two
  handles: one for reading values, one (without `data_only`) for editing.
* Files saved by Excel keep stale cached values if the workbook was in manual
  calculation mode. Do not trust cached values blindly; check `wb.calculation.calcMode`.
  `scripts/xlsx_recalc_check.py` runs LibreOffice with its default profile, which
  computes formulas that have no cached value but leaves existing cached values as they
  are; to refresh stale ones, clear the cached values first (rewrite the formula cells
  with openpyxl) or recalculate in Excel.

## 2. Dates are numbers

* Excel stores a date as the number of days since 1899-12-30 (the 1900 date system;
  some Mac files use 1904). What makes it look like a date is the number format.
* Writing the string "2026-01-31" creates a TEXT cell. Excel shows it left-aligned,
  `=A1+1` gives #VALUE!, sorting and filtering treat it as text. Convert with
  `datetime.date.fromisoformat()` or `datetime.strptime()` before writing.
* Writing `datetime.date` or `datetime.datetime` makes openpyxl set a default date
  format only when the cell format is still `General`. If you apply a numeric format
  (for example `0.00`) to a date cell, Excel shows 46053 and openpyxl reads back a number.
* Reading returns `datetime.datetime` for whole days as well (midnight); compare with
  `.date()` when you need calendar dates. Times without a date come back as
  `datetime.time`; durations larger than 24 hours come back as `datetime.timedelta`
  only when the format is `[h]:mm`.
* Excel cannot represent dates before 1900-01-01 and treats 1900 as a leap year.
* Timezones are dropped. Convert to the timezone you want before writing.

## 3. Merged cells

* Only the top-left cell of a merged range holds a value and a style. The other
  cells are `MergedCell` objects; assigning to their `.value` raises an
  `AttributeError` ("object attribute 'value' is read-only").
* Merged ranges are stored separately from cells: `insert_rows`, `delete_rows` and
  `move_range` do not move them. After structural edits, re-create the merges.
* Borders around a merged range have to be set on every cell of the range, not only
  on the top-left cell.
* Autofilter, sorting and tables do not work over merged cells. Prefer
  "center across selection" (Alignment(horizontal="centerContinuous")) for titles.
* `ws.max_row` and `ws.iter_rows` include the placeholder cells; skip cells with
  `type(cell).__name__ == "MergedCell"` when reading.

## 4. Column widths are character units, not pixels

* `ws.column_dimensions["A"].width` counts characters of the default font's digit
  width (Calibri 11: about 7 pixels per unit plus 5 pixels of padding). The default is
  8.43, the maximum 255. Row heights are in points.
* openpyxl has no auto-fit: Excel calculates "AutoFit" at render time and never stores
  it. Estimate the width as the longest displayed string plus two characters, using the
  formatted length for numbers (thousand separators, currency symbol, two decimals) and
  10 characters for dates. Clamp to a range such as 8 to 60.
* Add about 2 units for a column that carries an autofilter button, otherwise the
  header text hides behind the arrow.
* Setting a width on a column dimension that also has `hidden=True` keeps it hidden.

## 5. Formulas: English names, commas, prefixes

* The file format always uses English function names, a comma as argument separator
  and a dot as decimal separator, regardless of the user's Excel language. Localized
  names (SUMME, SOMME, SUMA) or semicolons produce #NAME? or a repair prompt.
* Functions introduced after Excel 2007 need the `_xlfn.` prefix in the stored text:
  `=_xlfn.XLOOKUP(...)`, `=_xlfn.IFS(...)`, `=_xlfn.TEXTJOIN(...)`, `=_xlfn.STDEV.S(...)`.
  Without it Excel shows #NAME? until the user re-enters the formula. Dynamic array
  functions (FILTER, UNIQUE, SORT, SEQUENCE) additionally need array formula metadata
  to spill; written as plain formulas by openpyxl they behave as legacy single-cell
  formulas (implicit intersection) instead of filling a range.
* Sheet names with spaces or punctuation are quoted with single quotes: `='Q1 Sales'!B2`.
  A quote inside the name is doubled: `='Bob''s sheet'!A1`.
* Percent cells store fractions (0.25 shows as 25%); `=B2*100` in a percent cell shows 2500%.
* Booleans are the bare words TRUE and FALSE, strings are double-quoted, and a double
  quote inside a string is doubled (`"say ""hi"""`).
* openpyxl performs no validation. A formula with unbalanced parentheses, a reference
  to a sheet that does not exist or a #REF! token is saved happily and fails in Excel.
  Run `scripts/xlsx_recalc_check.py` before delivering.
* A formula that references a cell in the totals row from inside the totals range
  (`=SUM(B2:B6)` in B6) is a circular reference; Excel warns on open.
* Absolute references (`$B$2`) matter when the user will copy cells. Prefer them for
  lookups, rates and configuration cells.

## 6. Sheet names

* At most 31 characters, none of `[ ] : * ? / \`, unique without regard to case, no
  leading or trailing apostrophe, never empty. openpyxl only warns on a long name and
  Excel refuses to open the file ("We found a problem with some content").
* Renaming a sheet does not update formulas that point to it; openpyxl does not rewrite
  references. Do the rename first, then write the formulas.
* Excel reserves the sheet name "History". Hidden helper sheets (for validation lists
  or configuration) are fine; set `ws.sheet_state = "hidden"` after filling them.

## 7. CSV encodings and locale formats

* "CSV UTF-8" saved by Excel starts with a byte order mark; decode with `utf-8-sig`
  (plain `utf-8` keeps the BOM inside the first header name).
* Plain "CSV (comma delimited)" on Windows uses the system code page: cp1252 for
  Western Europe, cp1251 for Cyrillic, cp1255 for Hebrew, cp1250 for Central Europe,
  cp1256 for Arabic. Decoding them as UTF-8 raises `UnicodeDecodeError` at byte 0xC4
  or similar; `latin-1` never fails but silently produces mojibake for anything but
  Western text, so do not use it as a blind fallback.
* In locales where the comma is the decimal separator Excel writes semicolon-delimited
  CSV with values like `1.500,75`. `scripts/csv_to_xlsx.py` switches to decimal-comma
  parsing when it detects the semicolon delimiter (override with `--decimal-comma`).
* "Unicode Text" exports are UTF-16 with a BOM and tab delimiters.
* Excel mangles CSV on open: leading zeros vanish (00123 becomes 123), 16+ digit IDs
  become 1.23457E+15 with the last digits replaced by zeros, `1/2` becomes a date,
  and `=cmd|...` strings are evaluated. Delivering an .xlsx with typed columns avoids
  all of these; keep identifiers as text.
* Dates in CSV are ambiguous: 03/04/2026 is 4 March in most of the world and 3 April in
  the United States. Ask, or pass `--dayfirst`; ISO dates (2026-03-04) are never ambiguous.

## 8. Editing existing workbooks

* Load with `keep_vba=True` for .xlsm files and save with the .xlsm extension, otherwise
  the macros are dropped silently. Never save an .xlsm as .xlsx and hope.
* openpyxl round-trips cells, styles, merged cells, comments, data validations,
  conditional formats, defined names, tables, charts and images (images need Pillow).
  It drops shapes, text boxes, form controls, slicers, sparklines, embedded objects and
  some printer settings. Warn the user and keep the original file untouched.
* Pivot tables are preserved but not refreshed; the user has to refresh in Excel.
* Inserting or deleting rows and columns shifts cell values only. Formulas, merged
  ranges, charts, validations, conditional formats, tables and defined names keep their
  old coordinates. Prefer appending rows, or rewrite the affected formulas afterwards.
* Styles are immutable objects; `cell.font.bold = True` fails. Use
  `cell.font = Font(bold=True)` or `copy(cell.font)`.
* Appended rows do not inherit data validation or conditional formatting from the row
  above. Extend the ranges (`dv.add(...)`) after appending.
* `ws.max_row` counts rows that only carry formatting. Use the inspect script or scan
  for the last row with a value when the sheet has "formatted emptiness" below the data.
* Named tables (`ws.tables`) need unique header strings and their `ref` must be updated
  when rows are appended, otherwise Excel repairs the file.

## 9. Charts and validation

* Charts reference ranges, so a totals row inside the range becomes a bar. Charts built
  from the header row need `titles_from_data=True` to turn the header into the series name.
* Recent Excel versions hide the axes of openpyxl charts unless
  `chart.x_axis.delete = False` and `chart.y_axis.delete = False` are set.
* Inline validation lists are limited to 255 characters including separators; store
  longer lists in a (hidden) sheet and reference the range.
* `DataValidation(showDropDown=True)` hides the dropdown arrow: the flag is inverted in
  the file format. Leave it unset.
* Validation stops nothing that a script writes; it only constrains typing in Excel.

## 10. Numbers stored as text

* Values such as "1,234" or "12%" read from CSV or copied from a web page are strings.
  Excel shows a green triangle ("number stored as text") and SUM ignores them. Convert
  to `int`/`float` before writing and apply a number format instead.
* Conversely, IDs, phone numbers and ZIP codes must stay strings; apply the `@` format
  to make Excel keep them as text when the user edits the cell.
* Floating point: 0.1 + 0.2 shows as 0.30000000000000004 with a `General` format.
  Round in Python or apply a fixed-decimal format.
