#!/usr/bin/env python3
"""Convert an Excel workbook (or CSV) into a SQLite database plus a schema report.

The SQLite file is meant to be bundled inside a watsonx Orchestrate Python tool
(imported with `orchestrate tools import -k python -f tool.py -p <package_dir>`),
so the database must be self-contained and read-only friendly.

The schema report (schema.md) is meant to be pasted into the agent's
instructions so the LLM knows the exact tables, columns and value domains
without needing discovery queries.

Usage:
    python excel_to_sqlite.py INPUT.xlsx -o data.db [--sheet NAME ...]
        [--table NAME] [--schema-out schema.md] [--max-list-values 25]

Requires: pandas, openpyxl (both preinstalled in most environments).
"""
import argparse
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import pandas as pd


def sanitize_identifier(name: str, used: set) -> str:
    """Make a string safe to use as an unquoted-ish SQL identifier.

    Keeps unicode letters (Hebrew, Cyrillic, etc.) because SQLite and LLMs
    handle them fine when quoted; strips control/format chars (e.g. RTL marks
    that Excel headers often carry), collapses whitespace/punctuation to '_'.
    """
    name = str(name).strip()
    # Remove invisible format characters (RTL/LTR marks etc.)
    name = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cf", "Cc"))
    name = re.sub(r"[^\w]+", "_", name, flags=re.UNICODE).strip("_")
    if not name:
        name = "col"
    if name[0].isdigit():
        name = "c_" + name
    base, i = name, 2
    while name.lower() in used:
        name = f"{base}_{i}"
        i += 1
    used.add(name.lower())
    return name


def _clean_str_cell(v):
    if not isinstance(v, str):
        return v
    return "".join(ch for ch in v if unicodedata.category(ch) not in ("Cf", "Cc")).strip()


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize column names, drop empty rows/columns, convert datetimes to ISO text."""
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    used = set()
    df.columns = [sanitize_identifier(c, used) for c in df.columns]
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            # SQLite has no date type; ISO-8601 text works with date() functions
            if (s.dropna().dt.normalize() == s.dropna()).all():
                df[col] = s.dt.strftime("%Y-%m-%d")
            else:
                df[col] = s.dt.strftime("%Y-%m-%d %H:%M:%S")
        elif s.dtype == object:
            # Strip whitespace AND invisible format chars (RTL marks etc.) from
            # string cells — an LLM cannot type U+200F when filtering by value
            df[col] = s.map(_clean_str_cell)
    return df


def describe_column(conn: sqlite3.Connection, table: str, col: str, col_type: str,
                    n_rows: int, max_list_values: int) -> str:
    """One markdown bullet describing a column: type, nulls, domain."""
    q = lambda ident: '"' + ident.replace('"', '""') + '"'
    cur = conn.execute(
        f"SELECT COUNT({q(col)}), COUNT(DISTINCT {q(col)}) FROM {q(table)}")
    non_null, distinct = cur.fetchone()
    parts = [f"`{col}` {col_type}"]
    if n_rows:
        null_pct = round(100 * (n_rows - non_null) / n_rows)
        if null_pct:
            parts.append(f"{null_pct}% NULL")
    if distinct and distinct <= max_list_values:
        vals = [r[0] for r in conn.execute(
            f"SELECT DISTINCT {q(col)} FROM {q(table)} WHERE {q(col)} IS NOT NULL "
            f"ORDER BY 1 LIMIT {max_list_values}")]
        rendered = ", ".join(repr(v) if isinstance(v, str) else str(v) for v in vals)
        parts.append(f"values: {rendered}")
    elif col_type in ("INTEGER", "REAL") or "date" in col.lower():
        lo, hi = conn.execute(
            f"SELECT MIN({q(col)}), MAX({q(col)}) FROM {q(table)}").fetchone()
        parts.append(f"range: {lo} .. {hi}")
    else:
        parts.append(f"{distinct} distinct values")
        sample = [r[0] for r in conn.execute(
            f"SELECT DISTINCT {q(col)} FROM {q(table)} WHERE {q(col)} IS NOT NULL LIMIT 3")]
        if sample:
            parts.append("e.g. " + ", ".join(repr(str(v)) for v in sample))
    return "- " + " — ".join(parts)


def build_schema_report(db_path: Path, max_list_values: int) -> str:
    conn = sqlite3.connect(db_path)
    lines = ["# Database schema", ""]
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        n_rows = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        lines.append(f"## Table `{table}` ({n_rows:,} rows)")
        lines.append("")
        for _, col, col_type, *_ in conn.execute(f'PRAGMA table_info("{table}")'):
            lines.append(describe_column(conn, table, col, col_type, n_rows, max_list_values))
        lines.append("")
    conn.close()
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", help="Path to .xlsx/.xlsm/.csv file")
    ap.add_argument("-o", "--output", default="data.db", help="SQLite file to create")
    ap.add_argument("--sheet", action="append",
                    help="Sheet name to load (repeatable). Default: all non-empty sheets")
    ap.add_argument("--table", help="Table name override (only valid with a single sheet/CSV)")
    ap.add_argument("--schema-out", default=None,
                    help="Write markdown schema report here (default: <output>.schema.md)")
    ap.add_argument("--max-list-values", type=int, default=25,
                    help="List full value domain for columns with up to N distinct values")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"ERROR: {src} not found", file=sys.stderr)
        return 1
    out = Path(args.output)
    if out.exists():
        out.unlink()  # rebuild from scratch — the DB is a derived artifact

    if src.suffix.lower() == ".csv":
        frames = {args.table or sanitize_identifier(src.stem, set()): pd.read_csv(src)}
    else:
        sheets = pd.read_excel(src, sheet_name=args.sheet if args.sheet else None)
        if isinstance(sheets, pd.DataFrame):
            sheets = {args.sheet[0]: sheets}
        used_tables = set()
        frames = {}
        for sheet_name, df in sheets.items():
            df = normalize_dataframe(df)
            if df.empty:
                print(f"skip empty sheet: {sheet_name}")
                continue
            tname = args.table if (args.table and len(sheets) == 1) \
                else sanitize_identifier(sheet_name, used_tables)
            frames[tname] = df

    if not frames:
        print("ERROR: no non-empty sheets found", file=sys.stderr)
        return 1

    conn = sqlite3.connect(out)
    for tname, df in frames.items():
        df.to_sql(tname, conn, index=False, if_exists="fail", chunksize=5000)
        print(f"table {tname}: {len(df):,} rows, {len(df.columns)} columns")
    conn.execute("ANALYZE")
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    report = build_schema_report(out, args.max_list_values)
    schema_path = Path(args.schema_out) if args.schema_out else out.with_suffix(".schema.md")
    schema_path.write_text(report, encoding="utf-8")

    size_mb = out.stat().st_size / 1e6
    print(f"\nwrote {out} ({size_mb:.1f} MB) and {schema_path}")
    if size_mb > 50:
        print("WARNING: DB is large for a bundled tool artifact. Consider dropping unused "
              "columns/sheets or pre-aggregating before deploying to watsonx Orchestrate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
