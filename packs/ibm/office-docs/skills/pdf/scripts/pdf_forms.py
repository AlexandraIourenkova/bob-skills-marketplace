#!/usr/bin/env python3
"""List and fill AcroForm fields in a PDF with pypdf.

Run with:
    uv run --with pypdf --with pdfplumber --with reportlab python pdf_forms.py list form.pdf [--json]
    uv run --with pypdf --with pdfplumber --with reportlab python pdf_forms.py fill form.pdf \
        -o filled.pdf --data values.json [--flatten] [--strict]

values.json maps field names (as printed by 'list') to values:
{
  "full_name": "Jane Doe",                 # text field
  "subscribe": true,                       # checkbox: true/false or a state name such as "Yes"
  "size": "Large",                         # radio group: the export value of one option
  "country": "Israel",                     # combo box or list box
  "languages": ["English", "Hebrew"]       # multi-select list box
}

Names that do not exist in the form are reported (and fail the run with --strict).
XFA forms are detected and reported: only classic AcroForm fields can be filled.
Fields that use a built-in Latin font (Helvetica etc.) cannot display Cyrillic, Hebrew or
other non-Latin-1 text; the script warns and suggests a reportlab overlay instead.
Exit codes: 0 ok, 1 error (missing file, no form, unknown field with --strict).
"""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import sys
from pathlib import Path

FLAG_RADIO = 1 << 15
FLAG_PUSHBUTTON = 1 << 16
FLAG_COMBO = 1 << 17
FLAG_MULTISELECT = 1 << 21


def classify(field) -> str:
    field_type = field.get("/FT")
    flags = int(field.get("/Ff", 0) or 0)
    if field_type == "/Tx":
        return "text"
    if field_type == "/Btn":
        if flags & FLAG_PUSHBUTTON:
            return "pushbutton"
        if flags & FLAG_RADIO:
            return "radio"
        return "checkbox"
    if field_type == "/Ch":
        return "combo" if flags & FLAG_COMBO else "listbox"
    if field_type == "/Sig":
        return "signature"
    return "unknown"


def help_epilog(marker: str) -> str | None:
    """Return the module docstring from the line that starts with marker (for --help)."""
    doc = __doc__ or ""
    start = doc.find("\n" + marker)
    return doc[start + 1:] if start >= 0 else None


def qualified_name(annotation) -> str:
    parts = []
    node = annotation
    depth = 0
    while node is not None and depth < 32:
        title = node.get("/T")
        if title is not None:
            parts.append(str(title))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
        depth += 1
    return ".".join(reversed(parts))


def inherited(node, key: str):
    """Read key from a field or widget dictionary, falling back to its /Parent chain."""
    depth = 0
    while node is not None and depth < 32:
        value = node.get(key)
        if value is not None:
            return value
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
        depth += 1
    return None


def collect_widgets(reader) -> dict:
    """Map field name -> {'pages': [...], 'states': [...], 'da': ...} from the page annotations."""
    widgets: dict[str, dict] = {}
    for number, page in enumerate(reader.pages, start=1):
        for ref in page.get("/Annots") or []:
            annotation = ref.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            name = qualified_name(annotation)
            entry = widgets.setdefault(name, {"pages": [], "states": [], "da": None})
            if number not in entry["pages"]:
                entry["pages"].append(number)
            if entry["da"] is None:
                entry["da"] = inherited(annotation, "/DA")
            appearance = annotation.get("/AP")
            if appearance is not None and "/N" in appearance:
                normal = appearance["/N"].get_object()
                if hasattr(normal, "keys"):
                    for state in normal.keys():
                        state = str(state)
                        if state != "/Off" and state not in entry["states"]:
                            entry["states"].append(state)
    return widgets


def plain_value(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [plain_value(v) for v in value]
    return str(value)


def choice_options(field) -> list:
    options = field.get("/Opt")
    if not options:
        return []
    result = []
    for option in options:
        option = option.get_object() if hasattr(option, "get_object") else option
        if isinstance(option, (list, tuple)):
            result.append({"export": str(option[0]), "label": str(option[-1])})
        else:
            result.append(str(option))
    return result


def open_form(path: str, password: str | None):
    from pypdf import PdfReader

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"input file not found: {source}")
    reader = PdfReader(str(source))
    if reader.is_encrypted:
        # files that only carry an owner password (print/copy restrictions) open with ""
        if reader.decrypt(password or "") == 0:
            if password:
                raise ValueError(f"{source}: wrong password")
            raise ValueError(f"{source} is encrypted; pass --password")
    root = reader.trailer["/Root"]
    acroform = root.get("/AcroForm")
    xfa = bool(acroform is not None and acroform.get("/XFA") is not None)
    fields = reader.get_fields() or {}
    return reader, fields, xfa


def field_font(da, acroform) -> tuple[str | None, str | None]:
    """Return (font label, /Subtype) of the font named in a /DA string such as '/Helv 12 Tf 0 g'."""
    if da is None and acroform is not None:
        da = acroform.get("/DA")
    if not da:
        return None, None
    tokens = str(da).split()
    if "Tf" not in tokens or tokens.index("Tf") < 2:
        return None, None
    resource_name = tokens[tokens.index("Tf") - 2]
    label, subtype = resource_name.lstrip("/"), None
    resources = acroform.get("/DR") if acroform is not None else None
    fonts = resources.get_object().get("/Font") if resources is not None else None
    if fonts is not None and resource_name in fonts:
        font = fonts[resource_name].get_object()
        subtype = str(font.get("/Subtype", "")) or None
        label = str(font.get("/BaseFont", resource_name)).lstrip("/")
    return label, subtype


def warn_unencodable(values: dict, widgets: dict, acroform) -> None:
    """Warn when a value needs characters that the field's single-byte font cannot show."""
    for name, value in values.items():
        text = value if isinstance(value, str) else " ".join(value) if isinstance(value, list) else ""
        outside = [ch for ch in text if ord(ch) > 255]
        if not outside:
            continue
        label, subtype = field_font(widgets.get(name, {}).get("da"), acroform)
        if subtype == "/Type0":
            continue  # a composite (CID) font can carry any Unicode text
        print(f"warning: {name}: the field's font {label or 'Helvetica'} is a single-byte font; "
              f"characters outside Latin-1 such as {outside[0]!r} are stored but will not display "
              "(and print as '?' when flattened). Overlay the text with reportlab and a TrueType "
              "font instead", file=sys.stderr)


def describe_fields(reader, fields) -> list[dict]:
    widgets = collect_widgets(reader)
    described = []
    for name, field in fields.items():
        kind = classify(field)
        widget = widgets.get(name, {"pages": [], "states": []})
        entry = {
            "name": name,
            "type": kind,
            "value": plain_value(field.get("/V")),
            "pages": widget["pages"],
        }
        if kind in ("checkbox", "radio"):
            states = field.get("/_States_") or widget["states"]
            entry["states"] = [str(s) for s in states]
        if kind in ("combo", "listbox"):
            entry["options"] = choice_options(field)
            entry["multi_select"] = bool(int(field.get("/Ff", 0) or 0) & FLAG_MULTISELECT)
        if field.get("/TU") is not None:
            entry["tooltip"] = str(field.get("/TU"))
        described.append(entry)
    return described


def cmd_list(args) -> int:
    reader, fields, xfa = open_form(args.input, args.password)
    described = describe_fields(reader, fields)
    if args.json:
        print(json.dumps({"file": args.input, "xfa": xfa, "field_count": len(described),
                          "fields": described}, indent=2, ensure_ascii=False))
    else:
        if xfa:
            print("warning: this document carries an XFA form; only its AcroForm fields "
                  "(if any) are listed and fillable", file=sys.stderr)
        if not described:
            print("no form fields found")
        for entry in described:
            extra = ""
            if entry.get("states"):
                extra = f" states={entry['states']}"
            if entry.get("options"):
                extra = f" options={entry['options']}"
            pages = ",".join(str(p) for p in entry["pages"]) or "?"
            print(f"{entry['name']}  [{entry['type']}]  page {pages}  value={entry['value']!r}{extra}")
        print(f"{len(described)} field(s)")
    return 0


def normalise_state(value, states: list[str]) -> str:
    """Turn true/false/'Yes'/'/Yes'/'Off' into the state name pypdf expects."""
    on_states = [s for s in states if s != "/Off"]
    if isinstance(value, bool):
        if not value:
            return "/Off"
        return on_states[0] if on_states else "/Yes"
    text = str(value).strip()
    if text.lower() in ("", "off", "/off", "false", "0", "no"):
        return "/Off"
    if not text.startswith("/"):
        text = "/" + text
    return text


def remove_flattened_fields(writer, names: set[str]) -> None:
    """pypdf paints flattened appearances into the page but keeps the widgets; drop them."""
    from pypdf.generic import ArrayObject, NameObject

    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        kept = ArrayObject()
        for ref in annots:
            annotation = ref.get_object()
            if annotation.get("/Subtype") == "/Widget" and qualified_name(annotation) in names:
                continue
            kept.append(ref)
        if kept:
            page[NameObject("/Annots")] = kept
        else:
            del page["/Annots"]

    root = writer._root_object
    acroform = root.get("/AcroForm")
    if acroform is None:
        return
    acroform = acroform.get_object()
    fields = acroform.get("/Fields")
    if fields is None:
        return
    kept = ArrayObject()
    for ref in fields:
        field = ref.get_object()
        if qualified_name(field) in names:
            continue
        kept.append(ref)
    acroform[NameObject("/Fields")] = kept


def cmd_fill(args) -> int:
    from pypdf import PdfWriter

    reader, fields, xfa = open_form(args.input, args.password)
    if not fields:
        raise ValueError("the PDF has no AcroForm fields to fill"
                         + (" (it is an XFA form, which is not supported)" if xfa else ""))
    if xfa:
        print("warning: XFA form detected; only AcroForm fields are filled and viewers that "
              "prefer the XFA layer may not show the values", file=sys.stderr)

    data_path = Path(args.data)
    if not data_path.is_file():
        raise FileNotFoundError(f"data file not found: {data_path}")
    mapping = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict):
        raise ValueError("the data file must be a JSON object of field name -> value")

    widgets = collect_widgets(reader)
    unknown = [name for name in mapping if name not in fields]
    if unknown:
        print(f"warning: {len(unknown)} unknown field(s) ignored: {unknown}", file=sys.stderr)
        if args.strict:
            raise ValueError("unknown fields present and --strict given")

    values: dict = {}
    problems = []
    for name, value in mapping.items():
        if name not in fields:
            continue
        field = fields[name]
        kind = classify(field)
        states = [str(s) for s in (field.get("/_States_") or widgets.get(name, {}).get("states", []))]
        if kind in ("checkbox", "radio"):
            state = normalise_state(value, states)
            if state != "/Off" and states and state not in states:
                problems.append(f"{name}: '{value}' is not one of {states}")
                continue
            values[name] = state
        elif kind == "listbox" and isinstance(value, list):
            values[name] = [str(v) for v in value]
        elif kind in ("pushbutton", "signature"):
            problems.append(f"{name}: {kind} fields cannot be filled")
        else:
            values[name] = "" if value is None else str(value)
    if problems:
        for problem in problems:
            print(f"warning: {problem}", file=sys.stderr)
        if args.strict:
            raise ValueError("invalid values present and --strict given")
    if not values:
        raise ValueError("nothing to fill: no value matched an existing field")

    acroform = reader.trailer["/Root"].get("/AcroForm")
    warn_unencodable(values, widgets, acroform.get_object() if acroform is not None else None)

    writer = PdfWriter(clone_from=reader)
    supports_flatten = "flatten" in inspect.signature(writer.update_page_form_field_values).parameters
    if args.flatten and not supports_flatten:
        print("warning: this pypdf version cannot flatten fields; the form stays editable",
              file=sys.stderr)
    flatten = bool(args.flatten and supports_flatten)

    # pypdf logs raw notices here ("characters not supported by font encoding", "XObject
    # already added"); the warnings printed by this script cover both, so keep them quiet
    pypdf_log = logging.getLogger("pypdf")
    saved_level = pypdf_log.level
    pypdf_log.setLevel(logging.ERROR)
    try:
        for page in writer.pages:
            page_names = {qualified_name(ref.get_object()) for ref in (page.get("/Annots") or [])
                          if ref.get_object().get("/Subtype") == "/Widget"}
            page_values = {k: v for k, v in values.items() if k in page_names}
            if not page_values:
                continue
            kwargs = {"auto_regenerate": not flatten}
            if flatten:
                kwargs["flatten"] = True
            writer.update_page_form_field_values(page, page_values, **kwargs)
    finally:
        pypdf_log.setLevel(saved_level)
    if flatten:
        radios = [name for name in values if classify(fields[name]) == "radio"]
        if radios:
            print(f"warning: flattened radio group(s) {radios}: pypdf names the painted appearance "
                  "after the field, so the options can share one look; check them visually",
                  file=sys.stderr)
        remove_flattened_fields(writer, set(values))
    else:
        writer.set_need_appearances_writer(True)

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        writer.write(handle)

    # read back for verification
    from pypdf import PdfReader
    check = PdfReader(str(target))
    after = check.get_fields() or {}
    print(f"wrote {target} ({len(values)} field(s) filled{', flattened' if flatten else ''})")
    for name in values:
        if name in after:
            print(f"  {name} = {plain_value(after[name].get('/V'))!r}")
        elif flatten:
            print(f"  {name} flattened into the page content")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List and fill PDF form fields (pypdf).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=help_epilog("values.json maps"))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show fields, types, states and current values")
    p.add_argument("input")
    p.add_argument("--json", action="store_true")
    p.add_argument("--password")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("fill", help="fill fields from a JSON mapping")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--data", required=True, help="JSON file: field name -> value")
    p.add_argument("--flatten", action="store_true",
                   help="burn the filled fields into the page (pypdf >= 4 with flatten support)")
    p.add_argument("--strict", action="store_true", help="fail on unknown fields or bad values")
    p.add_argument("--password")
    p.set_defaults(func=cmd_fill)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
