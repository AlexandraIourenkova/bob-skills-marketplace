# SQLite text-to-SQL tool for watsonx Orchestrate.
# The database file (data.db) is bundled INSIDE the tool package and read locally —
# no external database, no connections/app-id needed.
#
# Placeholders to replace before import:
#   {{TOOL_NAME}}   -> unique tool name, e.g. query_sales_data (function name = tool name in wxo)
#
# Import with:
#   orchestrate tools import -k python -f <pkg>/{{TOOL_NAME}}.py -p <pkg> -r <pkg>/requirements.txt
import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool

DB_PATH = Path(__file__).parent / "data.db"

_UNSAFE_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
                    "CREATE", "REPLACE", "GRANT", "REVOKE", "ATTACH", "VACUUM", "PRAGMA")


def _connect() -> sqlite3.Connection:
    # The wxo tool runtime filesystem is read-only: open the DB read-only and
    # immutable so SQLite never attempts to create journal/WAL files.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _is_read_only(sql_query: str) -> bool:
    normalized = sql_query.upper()
    return not any(
        normalized.startswith(kw) or f" {kw} " in normalized
        or f";{kw}" in normalized or f"\n{kw}" in normalized
        for kw in _UNSAFE_KEYWORDS
    )


def _escape_cell(value) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _rows_to_markdown(rows: List[Dict], limit: Optional[int] = 30) -> str:
    if not rows:
        return "No rows returned."
    display = rows[:limit] if limit else rows
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(_escape_cell(h) for h in headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in display:
        lines.append("| " + " | ".join(_escape_cell(row.get(h)) for h in headers) + " |")
    table = "\n".join(lines)
    if limit and len(rows) > limit:
        table += f"\n\n_Showing first {limit} of {len(rows)} rows._"
    return table


def _rows_to_json(rows: List[Dict], limit: Optional[int]) -> str:
    return json.dumps(rows[:limit] if limit else rows, indent=2, default=str, ensure_ascii=False)


def _rows_to_csv(rows: List[Dict], limit: Optional[int]) -> str:
    if not rows:
        return ""
    display = rows[:limit] if limit else rows
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=display[0].keys())
    writer.writeheader()
    writer.writerows(display)
    return out.getvalue()


def sql_query_execute(sql_query: str, output_format: str = "markdown",
                      limit: Optional[int] = 30) -> str:
    try:
        if not _is_read_only(sql_query):
            return ("**Error:** unsafe query detected. Only read-only SELECT queries "
                    "are allowed against this bundled database.")
        conn = _connect()
        try:
            cursor = conn.execute(sql_query)
            rows = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        if output_format == "json":
            return _rows_to_json(rows, limit)
        if output_format == "csv":
            return _rows_to_csv(rows, limit)
        return _rows_to_markdown(rows, limit)
    except Exception as e:
        return f"**Error:** {e}"


@tool
def {{TOOL_NAME}}(sql_query: str) -> str:
    """
    Execute a read-only SQL query against the bundled SQLite database and return
    the result as a Markdown table.

    Args:
        sql_query (str): SQLite SELECT query to execute.

    Returns:
        str: Query result formatted as a Markdown table, or an error message.
    """
    return sql_query_execute(sql_query, output_format="markdown", limit=30)


@tool
def {{TOOL_NAME}}_schema() -> str:
    """
    Return the schema of the bundled SQLite database: tables, columns, types and
    row counts. Use when unsure about exact table or column names.

    Returns:
        str: Markdown description of all tables and their columns.
    """
    try:
        conn = _connect()
        try:
            lines = []
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                n = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                lines.append(f"### {table} ({n:,} rows)")
                for _, col, col_type, *_ in conn.execute(f'PRAGMA table_info("{table}")'):
                    lines.append(f"- {col} ({col_type})")
                lines.append("")
            return "\n".join(lines) or "No tables found."
        finally:
            conn.close()
    except Exception as e:
        return f"**Error:** {e}"
