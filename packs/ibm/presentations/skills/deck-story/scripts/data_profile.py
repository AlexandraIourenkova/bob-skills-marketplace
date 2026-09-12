#!/usr/bin/env python3
"""Profile a CSV or Excel sheet before writing a data story.

Prints the shape; per column the dtype, non-null count, missing share, and
min, median, mean, max, sum for numbers or the distinct count and the top
categories for text; totals per period (year, quarter or month, chosen from
the span) with the change between the last two periods when a date column is
found or given with --date-column; and the top and bottom three rows per
numeric column when a text column looks like a row label. Reads only the input
file, writes to stdout or to the -o path, and never touches the network.

Run:  uv run --with pandas python data_profile.py data.csv
      uv run --with pandas --with openpyxl python data_profile.py book.xlsx --sheet Revenue --json -o profile.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # --help and the error message still work without pandas
    pd = None

DATE_HINTS = ("date", "time", "period", "month", "quarter", "week", "day", "year")


def load(path: Path, sheet: str | None, sep: str | None):
    if pd is None:
        raise ImportError("pandas is not installed; run with: uv run --with pandas python data_profile.py FILE")
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        try:
            return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
        except ImportError as exc:
            raise RuntimeError("reading Excel needs openpyxl: add --with openpyxl to the uv run command") from exc
    if sheet is not None:
        raise ValueError("--sheet applies to Excel files only")
    options = {"sep": None, "engine": "python"} if sep is None else {"sep": sep}
    return pd.read_csv(path, encoding_errors="replace", **options)


def coerce_numbers(df):
    """Read text such as '1,200', '12%' or '3 400' as numbers when nearly every value parses."""
    for col in df.columns:
        s = df[col]
        if s.dtype != object and not pd.api.types.is_string_dtype(s):
            continue
        text = s.astype("string").str.strip()
        nums = pd.to_numeric(text.str.replace(r"[,\s%$\u20ac\u00a3]", "", regex=True), errors="coerce")
        if nums.notna().sum() >= 0.95 * text.notna().sum() > 0 and text.dropna().str.contains(r"\d").all():
            df[col] = nums.astype(float)
    return df


def to_dates(s):
    """Return a datetime Series when the column reads as dates, periods or years, else None."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    if pd.api.types.is_numeric_dtype(s):  # a column of years such as 2024
        years = s.dropna()
        ok = len(years) > 0 and years.between(1900, 2100).all()
        return pd.to_datetime(years.astype(int).astype(str), format="%Y").reindex(s.index) if ok else None
    text = s.astype("string").str.strip().str.replace(r"^[Qq]([1-4])[-\s/]?(\d{4})$", r"\2Q\1", regex=True)
    if not text.dropna().str.contains(r"\d").all():
        return None
    parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    return parsed if parsed.notna().sum() >= 0.9 * text.notna().sum() > 0 else None


def find_date_column(df, name: str | None):
    if name is not None and name not in df.columns:
        raise ValueError(f"date column not found: {name}; columns are {', '.join(df.columns)}")
    candidates = [name] if name is not None else [
        c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c]) or any(h in c.lower() for h in DATE_HINTS)]
    for col in candidates:
        parsed = to_dates(df[col])
        if parsed is not None:
            return col, parsed
    if name is not None:
        raise ValueError(f"column {name} does not read as dates or periods")
    return None, None


def profile_columns(df, max_categories: int) -> list[dict]:
    out = []
    for col in df.columns:
        s = df[col]
        info = {"column": col, "dtype": str(s.dtype), "non_null": int(s.notna().sum()),
                "missing_pct": round(float(s.isna().mean() * 100), 1)}
        if pd.api.types.is_numeric_dtype(s):
            info["kind"] = "numeric"
            if info["non_null"]:
                info.update(min=float(s.min()), median=float(s.median()), mean=float(s.mean()),
                            max=float(s.max()), sum=float(s.sum()))
        elif pd.api.types.is_datetime64_any_dtype(s):
            info.update(kind="date", first=str(s.min())[:10], last=str(s.max())[:10])
        else:
            counts = s.astype("string").value_counts()
            info.update(kind="text", distinct=int(counts.size), top=[
                {"value": str(v), "count": int(c), "share_pct": round(c / info["non_null"] * 100, 1)}
                for v, c in counts.head(max_categories).items()])
        out.append(info)
    return out


def profile_periods(df, date_col: str, dates, numeric: list[str]) -> dict:
    span_days = int((dates.max() - dates.min()).days)
    code = "Y" if span_days > 3 * 366 else "Q" if span_days > 366 else "M"
    totals = df[numeric].groupby(dates.dt.to_period(code)).sum()
    report = {"date_column": date_col, "first": str(dates.min())[:10], "last": str(dates.max())[:10],
              "grain": {"Y": "year", "Q": "quarter", "M": "month"}[code], "periods": int(len(totals)), "last_two": {},
              "totals": [{"period": str(p), **{c: float(r[c]) for c in numeric}} for p, r in totals.iterrows()]}
    if len(totals) >= 2:
        prev, last = totals.iloc[-2], totals.iloc[-1]
        for c in numeric:
            diff = float(last[c] - prev[c])
            report["last_two"][c] = {"from": str(totals.index[-2]), "to": str(totals.index[-1]), "change": diff,
                                     "change_pct": round(diff / float(prev[c]) * 100, 1) if prev[c] else None}
    return report


def top_bottom(df, label: str, numeric: list[str], date_col: str | None) -> dict:
    def row(r, c):
        return {"label": str(r[label]), "value": float(r[c]), **({"date": str(r[date_col])[:10]} if date_col else {})}
    out = {}
    for c in numeric:
        ordered = df.dropna(subset=[c]).sort_values(c, ascending=False)
        out[c] = {"top": [row(r, c) for _, r in ordered.head(3).iterrows()],
                  "bottom": [row(r, c) for _, r in ordered.tail(3).iloc[::-1].iterrows()]}
    return out


def build_report(args) -> dict:
    df = load(args.file, args.sheet, args.sep)
    df.columns = [str(c) for c in df.columns]
    if df.empty:
        raise ValueError("the file has no rows")
    df = coerce_numbers(df)
    date_col, dates = find_date_column(df, args.date_column)
    if date_col is not None:
        df[date_col] = dates
    columns = profile_columns(df, args.max_categories)
    numeric = [c["column"] for c in columns if c["kind"] == "numeric" and "min" in c]
    report = {"file": str(args.file), "rows": int(len(df)), "columns": int(df.shape[1]), "column_profiles": columns}
    if date_col is not None and numeric:
        report["periods"] = profile_periods(df, date_col, dates, numeric)
    labels = [(c["distinct"] / c["non_null"], c["column"]) for c in columns  # mostly distinct text = a row label
              if c["kind"] == "text" and c["column"] != date_col and c["non_null"] >= 4]
    ratio, label = max(labels, default=(0.0, None))
    if label is not None and ratio >= 0.5 and numeric:
        report["label_column"] = label
        report["top_bottom"] = top_bottom(df, label, numeric, date_col)
    return report


def fmt(x) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x:,.2f}" if isinstance(x, float) and not x.is_integer() else f"{int(x):,}"


def render_text(rep: dict) -> str:
    lines = [f"File: {rep['file']}", f"Shape: {rep['rows']:,} rows x {rep['columns']} columns", "", "Columns"]
    for c in rep["column_profiles"]:
        head = f"- {c['column']} ({c['kind']}, {c['dtype']}): {c['non_null']:,} non-null, {c['missing_pct']}% missing"
        if c["kind"] == "numeric" and "min" in c:
            head += "; " + ", ".join(f"{k} {fmt(c[k])}" for k in ("min", "median", "mean", "max", "sum"))
        elif c["kind"] == "text":
            head += f", {c['distinct']:,} distinct"
        elif c["kind"] == "date":
            head += f", {c['first']} to {c['last']}"
        lines.append(head)
        lines += [f"    {t['value']}: {t['count']:,} ({t['share_pct']}%)" for t in c.get("top", [])]
    per = rep.get("periods")
    if per:
        lines += ["", f"Periods by {per['date_column']}: {per['first']} to {per['last']}, {per['periods']} {per['grain']}s"]
        cols = [k for k in per["totals"][0] if k != "period"]
        lines.append("    " + "  ".join(["period".ljust(10)] + [k[:14].rjust(14) for k in cols]))
        lines += ["    " + "  ".join([r["period"].ljust(10)] + [fmt(r[k]).rjust(14) for k in cols]) for r in per["totals"]]
        for k, ch in per["last_two"].items():
            pct = "n/a" if ch["change_pct"] is None else f"{ch['change_pct']:+.1f}%"
            lines.append(f"    {k}: {ch['from']} to {ch['to']} {ch['change']:+,.2f} ({pct})")
    if rep.get("top_bottom"):
        lines += ["", f"Top and bottom rows by value (label: {rep['label_column']})"]
        for k, sides in rep["top_bottom"].items():
            for side in ("top", "bottom"):
                items = (f"{i['label']} {fmt(i['value'])}" + (f" ({i['date']})" if "date" in i else "") for i in sides[side])
                lines.append(f"    {k} {side}: " + ", ".join(items))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="CSV, TSV or Excel file to profile")
    parser.add_argument("--sheet", help="Excel sheet name (default: the first sheet)")
    parser.add_argument("--sep", help="CSV delimiter (default: detected)")
    parser.add_argument("--max-categories", type=int, default=8, help="top categories per text column (default 8)")
    parser.add_argument("--date-column", help="column with dates or periods (default: detected from the column name)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("-o", "--output", type=Path, help="write the report to this file instead of stdout")
    args = parser.parse_args(argv)
    try:
        report = build_report(args)
        text = json.dumps(report, indent=2, default=str) if args.json else render_text(report)
    except Exception as exc:  # any read or parse problem: one line on stderr, exit 1
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {args.output}" if args.output else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
