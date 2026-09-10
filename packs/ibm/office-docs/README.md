# Pack `office-docs` — Office documents

Vendor: `ibm` (marketplace team). Original skills written for this marketplace, Apache-2.0. Install with `uvx bob-skills add office-docs` or `/skills-add office-docs` inside Bob.

| Skill | Library | Scripts |
|---|---|---|
| `docx` | python-docx | build a document from a JSON spec, extract to Markdown or JSON, fill `{{placeholders}}` (also across runs, headers and footers), convert to PDF with LibreOffice |
| `pptx` | python-pptx | build a 16:9 deck from a Markdown outline with images, native charts and notes, extract an outline, find and replace text, render to PDF and PNG |
| `xlsx` | openpyxl (pandas for inspection) | build a workbook from a JSON spec with formulas, formats, charts and validation, inspect, recalculate and check formulas with LibreOffice, CSV to xlsx |
| `pdf` | pypdf, pdfplumber, reportlab | extract text and tables, build a PDF report with Unicode fonts, merge, split, rotate, watermark, metadata, encrypt, fill forms, OCR scanned files with local tesseract |

Every script runs with `uv run --with <library> python <script>`, has `--help`, writes only to the path it is given and never touches the network. `rules/office-docs.md` fixes the environment and the verification step: read every produced file back before claiming it is right.
