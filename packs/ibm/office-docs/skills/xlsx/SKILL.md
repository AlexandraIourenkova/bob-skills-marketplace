---
name: xlsx
description: Create, edit, analyse or analyze Excel workbooks (.xlsx/.xlsm) and convert CSV or TSV files with openpyxl. Builds sheets from a JSON spec with a styled frozen header, number formats (currency, percent, date), live formulas, a totals row, autofilter, native bar/line/pie charts and dropdown validation; converts CSV/TSV exports into typed sheets; reports what an existing workbook contains (sheets, header, formulas, charts, names, merged cells); and checks formulas for errors through a LibreOffice recalculation or a static scan. Use it whenever the input or the deliverable is a spreadsheet file, for requests such as "create an Excel file", "build a spreadsheet", "add formulas to the workbook", "convert this CSV to xlsx", "what is in this Excel file", "add a chart to the sheet" or "fix the broken formulas"; not for Word, PowerPoint or PDF files.
---

# xlsx: Excel workbooks with openpyxl

Paths below are relative to this skill folder. Scripts write only to the output path
they are given, never touch the network and only start LibreOffice (`soffice`) when it
is installed. Long API material lives in `references/openpyxl-cheatsheet.md`; failure
modes in `references/gotchas.md`. Read the relevant section before writing code.

## 1. Decide which workflow applies

1. **Create** a new workbook from data you have or compute (tables, formulas, totals,
   charts, dropdowns): write a JSON spec and run `scripts/xlsx_build.py` (workflow A).
2. **Convert** CSV/TSV exports into a clean workbook: `scripts/csv_to_xlsx.py` (workflow B).
3. **Edit** an existing workbook (add columns, formulas, a sheet, restyle): inspect it
   first, then write a short openpyxl script that loads, changes and saves to a NEW path
   (workflow C). Never overwrite the user's original.
4. **Fill** a template (a workbook with headers and styles already in place): treat it as
   an edit; write values into the existing cells and extend validations and tables.
5. **Extract or analyse** ("what is in this file", "summarise the sheet", "list the
   formulas"): `scripts/xlsx_inspect.py` (workflow D). Use pandas only inside that
   script (`--stats`) or for read-only analysis; write workbooks with openpyxl.
6. **Fix broken formulas** (#REF!, #NAME?, #VALUE!, #DIV/0!, #N/A): `scripts/xlsx_recalc_check.py`
   then edit the offending cells (workflow E).
7. For .xls (binary) or .numbers files, ask the user to export .xlsx first; openpyxl
   cannot read them. For .xlsm keep macros with `keep_vba=True` and save as .xlsm.

## 2. Environment

1. Run every script through uv so openpyxl is available without a global install:
   `uv run --with openpyxl python scripts/<script>.py --help`
2. Add `--with pandas` only for `xlsx_inspect.py --stats`.
3. LibreOffice is optional. `scripts/xlsx_recalc_check.py` finds `soffice` on PATH with
   `shutil.which` (or takes `--soffice PATH` / the `SOFFICE` environment variable, which
   must point to an existing executable, otherwise exit 2; on macOS that is the `soffice`
   binary inside `LibreOffice.app/Contents/MacOS`) and falls back to a static check with a
   clear message when it is absent. `--require-libreoffice` exits 2 instead. It runs
   `soffice --headless --convert-to xlsx` with the default profile: formulas without a
   cached value are computed, stale cached values from Excel are not refreshed.
4. All scripts print usage with `--help`, exit non-zero on failure and print the output
   path on success (stdout); progress and summaries go to stderr.

## 3. Workflow A: build a workbook from a JSON spec

1. Write the spec (JSON). Minimal example with everything the builder supports:
   ```json
   {
     "sheets": [{
       "name": "Sales",
       "headers": ["Region", "Units", "Price", "Revenue", "Date", "Share"],
       "rows": [
         ["North", 10, 12.5, "=B2*C2", "2026-01-15", 0.25],
         {"Region": "South", "Units": 4, "Price": 9, "Revenue": "=B3*C3", "Date": "2026-02-01", "Share": 0.1}
       ],
       "formats": {"Price": "currency", "Revenue": "currency", "Date": "date", "Share": "percent"},
       "totals": {"label": "Total", "columns": {"Units": "SUM", "Revenue": "SUM", "Share": "AVERAGE"}},
       "widths": "auto",
       "autofilter": true,
       "freeze_header": true,
       "charts": [{"type": "bar", "title": "Revenue by region", "data": ["Revenue"],
                   "categories": "Region", "y_title": "USD"}],
       "validations": [{"range": "A2:A200", "list": ["North", "South", "East", "West"],
                        "error": "Choose a region"}]
     }, {
       "name": "Config",
       "headers": ["Setting", "Value"],
       "rows": [["Tax rate", 0.2]],
       "formats": {"Value": "percent"},
       "autofilter": false
     }],
     "defined_names": {"TaxRate": "Config!$B$2"}
   }
   ```
   Rules: strings starting with `=` are formulas; ISO date strings become real dates
   (except in columns formatted `text`); percent values are fractions (0.25); column keys
   are header names (case-insensitive), upper-case column letters inside the sheet, or
   1-based numbers, anything else is an error; totals take a function name (`SUM`,
   `AVERAGE`, `MIN`, `MAX`, `COUNT`, `COUNTA`, `MEDIAN`) or a formula with the
   placeholders `{range}`, `{col}`, `{first}`, `{last}` (double literal braces: `{{1,2}}`);
   format presets are `currency`, `percent`, `date`, `datetime`, `integer`, `number`,
   `text`, or any Excel format code such as `"0.0%"`; chart `data` and `categories`
   accept column names (header plus data rows, totals excluded) or explicit ranges
   (`"F1:F5"`, `"Other!$A$1:$B$9"`); `type` is `bar` (add `"horizontal": true` or
   `"stacked": true`), `line` or `pie`; validations take a `list`, a `source` range, or
   `type`/`operator`/`formula1`/`formula2`. Lists longer than 255 characters are moved to
   a hidden `_lists` sheet automatically. Every defined name must point at a sheet that
   exists in the spec, otherwise Excel shows #REF! for it.
2. Build: `uv run --with openpyxl python scripts/xlsx_build.py spec.json --output report.xlsx`
   (`-` reads the spec from stdin). The header row is bold, filled and frozen; the
   autofilter covers the data rows only, so sorting never moves the totals row.
3. Verify (section 8), then check formulas:
   `uv run --with openpyxl python scripts/xlsx_recalc_check.py report.xlsx`
4. Compute values in Python and write numbers instead of formulas when the user will
   read the file with a program rather than Excel: openpyxl never calculates formulas,
   so formula cells have no cached value until Excel or LibreOffice saves the file.

## 4. Workflow B: convert CSV files

1. Look at the first bytes and lines of the file (`head -c 300 data.csv | od -c | head`)
   to spot a BOM, the delimiter, the decimal separator and the date style.
2. Convert: `uv run --with openpyxl python scripts/csv_to_xlsx.py data.csv more.csv --output data.xlsx`
   Options: `--sheet-names "Orders,Returns"`, `--encoding cp1251` (or a comma-separated
   list to try in order; the default tries `utf-8-sig,utf-8` and refuses to guess),
   `--delimiter tab`, `--dayfirst` for 31/12/2026 style dates, `--decimal-comma yes`,
   `--float-format "#,##0.00"`, `--no-header`.
3. Read the type summary and the `note:` lines the script prints to stderr. Columns are
   typed only when every non-empty value agrees; leading-zero codes and 16+ digit
   identifiers stay text on purpose. Slashed dates use one convention per column
   (month-first by default, day-first with `--dayfirst`, or whichever the values prove;
   mixed conventions stay text), dotted thousands such as `1.500` in decimal-comma files
   are read as 1500, and skipped blank lines are counted. If a column that should be
   numeric came out as text, the source mixes formats: clean it or pass the right locale
   options and convert again.
4. Verify with `scripts/xlsx_inspect.py data.xlsx --rows 5` (section 8).

## 5. Workflow C: edit an existing workbook

1. Inspect first: `uv run --with openpyxl python scripts/xlsx_inspect.py in.xlsx --rows 5 --formulas`
   Note the header row, the last data row, formulas that must keep working, merged
   cells, tables, validations and charts (they do not move when rows are inserted).
2. Write a short script and run it with `uv run --with openpyxl python edit.py`:
   ```python
   from openpyxl import load_workbook
   from openpyxl.styles import Font
   wb = load_workbook("in.xlsx")                 # add keep_vba=True for .xlsm
   ws = wb["Sales"]
   last = ws.max_row                             # confirm against the inspect report
   ws.cell(row=1, column=8, value="Margin").font = Font(bold=True)
   for r in range(2, last + 1):
       ws.cell(row=r, column=8, value=f"=D{r}-C{r}*B{r}").number_format = "#,##0.00"
   ws.auto_filter.ref = f"A1:H{last}"
   wb.save("out.xlsx")                           # never the input path
   ```
3. Append rows with `ws.append([...])` rather than inserting in the middle; if you must
   insert, rewrite formulas, merged ranges, validations, table refs and chart ranges
   that pointed below the insertion point.
4. Copy the style of an existing cell with `copy(cell.font)` / `copy(cell.fill)`; style
   objects are immutable, so assign new objects instead of mutating attributes.
5. Never load with `data_only=True` for editing: saving such a workbook deletes every
   formula. Load a second copy with `data_only=True` when you need cached values.
6. Re-run the inspect script on the output and compare with step 1: same sheets, same
   or larger dimensions, formula count as expected, charts and validations still present.
7. Run `scripts/xlsx_recalc_check.py out.xlsx` before handing the file over.

## 6. Workflow D: inspect and answer questions

1. `uv run --with openpyxl python scripts/xlsx_inspect.py book.xlsx --rows 10`
   gives, per sheet: dimensions, header row, formula versus value counts, whether cached
   results exist, the first N rows as a Markdown table, merged cells, charts, tables,
   validations, conditional formats, freeze panes and the autofilter; plus defined names.
2. Add `--formulas` to list every formula with its cached value, `--sheet NAME` to
   focus, `--json` for machine-readable output, and `--stats` (with `--with pandas`) for
   numeric column statistics.
3. When the question is about computed numbers and the report says cached results are
   missing, say so: the file was produced by a library and never recalculated. Use
   `xlsx_recalc_check.py --save-recalculated calc.xlsx` when LibreOffice is available, or
   recompute the figures in Python from the input cells.
4. For deeper analysis read the data with `load_workbook(path, data_only=True)` and
   `ws.iter_rows(min_row=2, values_only=True)`, or `pandas.read_excel(path, sheet_name=...)`.

## 7. Workflow E: fix broken formulas

1. Run `uv run --with openpyxl python scripts/xlsx_recalc_check.py book.xlsx`. It always
   tokenizes every formula and reports: unbalanced parentheses, references to sheets or
   tables that do not exist, cells outside the grid, unknown names, `#REF!` tokens,
   semicolon separators, post-2007 functions missing the `_xlfn.` prefix, unknown
   function names (warning), defined names whose target sheet is missing, and error
   values already cached in the file. With
   LibreOffice it also recalculates a temporary copy and lists cells whose result is
   `#REF!`, `#DIV/0!`, `#NAME?`, `#VALUE!`, `#N/A`, `#NUM!` or `#NULL!`.
   Exit code 1 means errors were found; `--json` gives the findings as data;
   `--strict` also fails on warnings; `--static-only` skips LibreOffice.
2. Fix the causes, not the symptoms: restore the missing sheet name, replace `#REF!`
   with the intended range, add the `_xlfn.` prefix, wrap divisions in
   `IFERROR(..., 0)` only when a blank result is the correct business answer.
3. Write the corrected formulas with a script as in workflow C, save to a new file and
   re-run the check until it reports `Result: OK`.

## 8. Verify before delivering

1. Read the file back with openpyxl and assert what the user asked for:
   ```python
   from openpyxl import load_workbook
   wb = load_workbook("report.xlsx")
   ws = wb["Sales"]
   assert ws["D2"].value == "=B2*C2" and ws["D2"].data_type == "f"
   assert ws.freeze_panes == "A2" and ws.auto_filter.ref
   assert ws["A1"].font.bold and ws["C2"].number_format != "General"
   assert len(ws._charts) == 1 and len(ws.data_validations.dataValidation) == 1
   ```
2. Run `scripts/xlsx_inspect.py` on the output and read the report as the user would:
   header names, row count, formulas count, charts count, hidden sheets.
3. Run `scripts/xlsx_recalc_check.py` and require `Result: OK`. Mention in the answer
   whether LibreOffice recalculated the file or only the static check ran.
4. Tell the user which cells are formulas (values appear when the file is opened in
   Excel) and which numbers were computed in Python.

## 9. Gotchas (details in references/gotchas.md)

1. Formula cells have no cached value until Excel or LibreOffice saves the file; the
   recalc check fills missing values but never refreshes stale cached ones.
2. Dates are numbers plus a format: write `datetime` objects, not strings; they come
   back as `datetime.datetime` even for whole days.
3. Formulas use English function names, commas and `_xlfn.` prefixes for new functions.
4. Sheet names: at most 31 characters, no `[ ] : * ? / \`, unique case-insensitively.
5. Column widths are character units; there is no auto-fit, estimate from content.
6. Only the top-left cell of a merged range holds a value; inserting rows moves cells
   but not merges, charts, validations or formulas.
7. CSV from Excel is UTF-8 with BOM (`utf-8-sig`) or a Windows code page
   (cp1252, cp1251, cp1255); semicolon-delimited files use a decimal comma.
8. Percent cells store fractions; `showDropDown=True` hides a dropdown; inline
   validation lists are limited to 255 characters.
