#!/usr/bin/env python3
"""Invented data for a proof of concept: tables from a small JSON schema, with planted cases.

    synth.py init challenge/data/schema.json       write the example schema (never overwrites)
    synth.py check challenge/data/schema.json      validate the schema, write nothing
    synth.py make challenge/data/schema.json -o challenge/data [--format csv|json]

The same schema and seed always give the same rows. People and companies are built
from syllables, so no name comes from a list of real ones; e-mail addresses end in
example.com. Next to the tables the script writes manifest.json: the row ids of every
planted case, which is the answer key for testing the proof of concept.

Standard library only, no network. It writes only into the folder given with -o, and
replaces only files that an earlier run of this script wrote there.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

MARK = "challenge-kit synth"
TYPES = ("id", "int", "float", "date", "choice", "text", "person", "company", "email", "ref", "bool")
STARTS = ["ba", "ce", "do", "el", "fa", "gi", "ha", "il", "jo", "ka", "le", "mi", "no", "or", "pa", "ra", "sa", "te", "ul", "va", "we", "ya", "zo"]
MIDS = ["ra", "li", "no", "ve", "ta", "mi", "do", "ka", "ne", "so", "ri", "lu"]
ENDS = ["n", "r", "l", "s", "m", "la", "na", "ro", "vi", "ko", "den", "mar", "rin", "vale", "ston"]
TRADES = ["Logistics", "Foods", "Components", "Textiles", "Systems", "Packaging", "Freight", "Supply", "Works", "Trading"]
FORMS = ["Ltd", "Group", "Co", "Partners"]


def word(rng: random.Random, parts: int = 2) -> str:
    text = rng.choice(STARTS) + "".join(rng.choice(MIDS) for _ in range(parts - 2 if parts > 2 else 0)) + rng.choice(ENDS)
    return text.capitalize()


def check(schema: dict) -> list[str]:
    errors: list[str] = []
    tables = schema.get("tables")
    if not isinstance(tables, dict) or not tables:
        return ["tables must be an object with at least one table"]
    seen: dict[str, set] = {}
    for name, table in tables.items():
        fields = table.get("fields") if isinstance(table, dict) else None
        if not isinstance(fields, dict) or not fields:
            errors.append(f"{name}: fields must be an object with at least one field")
            continue
        rows = table.get("rows")
        if not isinstance(rows, int) or not 1 <= rows <= 100000:
            errors.append(f"{name}: rows must be a whole number from 1 to 100000")
        for field, spec in fields.items():
            kind = spec.get("type") if isinstance(spec, dict) else None
            where = f"{name}.{field}"
            if kind not in TYPES:
                errors.append(f"{where}: type must be one of {', '.join(TYPES)}")
                continue
            if kind in ("int", "float") and not (isinstance(spec.get("min"), (int, float)) and isinstance(spec.get("max"), (int, float)) and spec["min"] <= spec["max"]):
                errors.append(f"{where}: needs numbers min and max, min not above max")
            if kind == "date":
                try:
                    if date.fromisoformat(str(spec.get("from"))) > date.fromisoformat(str(spec.get("to"))):
                        errors.append(f"{where}: 'from' is after 'to'")
                except ValueError:
                    errors.append(f"{where}: needs 'from' and 'to' as YYYY-MM-DD")
            if kind in ("choice", "text"):
                values = spec.get("values")
                if not isinstance(values, list) or not values:
                    errors.append(f"{where}: needs a non-empty list 'values'")
                elif "weights" in spec and (not isinstance(spec["weights"], list) or len(spec["weights"]) != len(values)):
                    errors.append(f"{where}: weights must have one number per value")
            if kind == "ref":
                target, column = spec.get("table"), spec.get("field")
                if target not in seen:
                    errors.append(f"{where}: refers to table '{target}', which must be defined before '{name}'")
                elif column not in seen[target]:
                    errors.append(f"{where}: table '{target}' has no field '{column}'")
        planted = 0
        for i, case in enumerate(table.get("cases") or []):
            where = f"{name}.cases[{i}]"
            if not isinstance(case.get("count"), int) or case["count"] < 1:
                errors.append(f"{where}: count must be a whole number of at least 1")
            else:
                planted += case["count"]
            if not case.get("label"):
                errors.append(f"{where}: needs a label, the name of the case in the answer key")
            for field, value in (case.get("set") or {}).items():
                if field not in fields:
                    errors.append(f"{where}: sets '{field}', which is not a field of {name}")
                elif isinstance(value, dict) and value.get("from") not in fields:
                    errors.append(f"{where}: '{field}' is derived from '{value.get('from')}', which is not a field of {name}")
        if isinstance(rows, int) and planted > rows:
            errors.append(f"{name}: the cases plant {planted} rows, more than the {rows} rows of the table")
        seen[name] = set(fields)
    return errors


def value(rng: random.Random, spec: dict, index: int, row: dict, made: dict):
    kind = spec["type"]
    if kind == "id":
        return f"{spec.get('prefix', '')}{index + int(spec.get('start', 1)):0{int(spec.get('width', 4))}d}"
    if kind == "int":
        return rng.randint(int(spec["min"]), int(spec["max"]))
    if kind == "float":
        return round(rng.uniform(spec["min"], spec["max"]), int(spec.get("decimals", 2)))
    if kind == "date":
        first, last = date.fromisoformat(spec["from"]), date.fromisoformat(spec["to"])
        return (first + timedelta(days=rng.randint(0, (last - first).days))).isoformat()
    if kind in ("choice", "text"):
        return rng.choices(spec["values"], weights=spec.get("weights"))[0]
    if kind == "bool":
        return rng.random() < float(spec.get("share", 0.5))
    if kind == "person":
        return f"{word(rng)} {word(rng, 3)}"
    if kind == "company":
        return f"{word(rng, 3)} {rng.choice(TRADES)} {rng.choice(FORMS)}"
    if kind == "email":
        base = str(row.get(spec.get("from", ""), "") or word(rng)).lower()
        local = "".join(ch if ch.isalnum() else "." for ch in base).strip(".") or "user"
        return f"{local}@example.com"
    if kind == "ref":
        return rng.choice(made[spec["table"]])[spec["field"]]
    raise ValueError(kind)


def make(schema: dict) -> tuple[dict, dict]:
    rng = random.Random(schema.get("seed", 1))
    made: dict[str, list[dict]] = {}
    key: dict[str, list[dict]] = {}
    for name, table in schema["tables"].items():
        fields = table["fields"]
        rows = []
        for index in range(table["rows"]):
            row: dict = {}
            for field, spec in fields.items():
                row[field] = value(rng, spec, index, row, made)
            rows.append(row)
        free = list(range(len(rows)))
        rng.shuffle(free)
        first = next(iter(fields))
        for case in table.get("cases") or []:
            picked = sorted(free.pop() for _ in range(case["count"]))
            for at in picked:
                for field, change in (case.get("set") or {}).items():
                    if isinstance(change, dict):
                        base = rows[at][change["from"]]
                        result = base * change.get("times", 1) + change.get("plus", 0)
                        rows[at][field] = round(result, int(fields[field].get("decimals", 2))) if isinstance(result, float) else result
                    else:
                        rows[at][field] = change
            key.setdefault(name, []).append({"label": case["label"], "count": case["count"], "rows": [rows[at][first] for at in picked]})
        made[name] = rows
    return made, key


def write(made: dict, key: dict, schema: dict, out: Path, fmt: str) -> list[Path]:
    manifest_path = out / "manifest.json"
    ours: set[str] = set()
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if old.get("generator") == MARK:
                ours = set(old.get("files", [])) | {"manifest.json"}
        except (ValueError, OSError):
            pass
    names = [f"{name}.{fmt}" for name in made] + ["manifest.json"]
    blocked = [n for n in names if (out / n).exists() and n not in ours]
    if blocked:
        raise SystemExit(f"error: {', '.join(blocked)} in {out} was not written by this script; nothing was changed")
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, rows in made.items():
        path = out / f"{name}.{fmt}"
        if fmt == "json":
            path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        written.append(path)
    manifest = {"generator": MARK, "synthetic": True, "seed": schema.get("seed", 1), "files": names[:-1],
                "tables": {name: len(rows) for name, rows in made.items()}, "cases": key}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return written + [manifest_path]


def read(path: str) -> dict:
    try:
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"no such file: {path}")
    except json.JSONDecodeError as error:
        raise SystemExit(f"{path} is not valid JSON: line {error.lineno}, column {error.colno}: {error.msg}")
    if not isinstance(schema, dict):
        raise SystemExit(f"{path}: the schema must be a JSON object")
    return schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make invented tables with planted cases from a JSON schema.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="write the example schema to a new file")
    p.add_argument("path")
    p = sub.add_parser("check", help="validate a schema")
    p.add_argument("schema")
    p = sub.add_parser("make", help="write the tables and the answer key")
    p.add_argument("schema")
    p.add_argument("-o", "--output", required=True, help="folder for the tables and manifest.json")
    p.add_argument("--format", choices=("csv", "json"), default="csv")
    args = parser.parse_args(argv)

    if args.command == "init":
        target = Path(args.path)
        if target.exists():
            print(f"error: {target} exists; it is not overwritten", file=sys.stderr)
            return 1
        source = Path(__file__).resolve().parent.parent / "assets" / "schema-example.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {target}; change the tables and fields to the shape of your own data")
        return 0
    schema = read(args.schema)
    errors = check(schema)
    for line in errors:
        print(f"error: {line}", file=sys.stderr)
    if errors:
        return 1
    if args.command == "check":
        print("ok")
        return 0
    made, key = make(schema)
    for path in write(made, key, schema, Path(args.output), args.format):
        print(f"wrote {path}")
    for table, cases in key.items():
        for case in cases:
            print(f"planted in {table}: {case['count']} x {case['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
