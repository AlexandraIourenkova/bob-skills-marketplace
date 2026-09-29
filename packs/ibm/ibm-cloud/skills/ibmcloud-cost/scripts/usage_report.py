#!/usr/bin/env python3
"""Where the IBM Cloud money goes this month: by service, resource group and instance.

Run:  python3 scripts/usage_report.py [--month 2026-09] [--compare] [--group NAME]
                                      [--out ibmcloud-reports/cost] [--json]

Reads three usage reports, whichever the user's role allows:
  account-usage              cost per service for the whole account (account billing access)
  resource-group-usage       cost per service for one group (--group; that group's admin)
  resource-instances-usage   cost per instance, the basis for the group and top-10 views
A report the role does not allow is listed with the role it needs instead of failing.

--compare adds the previous month and the change per service and per instance. The
current month is month-to-date. Instances that bill while every usage quantity is zero
are listed as candidates to review, never switched off.

Writes into --out: cost-<month>.csv (one row per instance), cost-<month>.json (the
summary) and raw/*.json (the CLI output). Read-only towards the account: the script
runs `ibmcloud billing ...` with --output json and nothing else.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

DENIED = ("not authorized", "unauthorized", "forbidden", "403", "access denied", "permission", "does not have access", "account admin")
NEEDS = {
    "account": "Viewer or higher on the Billing service for the account (the CLI help calls it account admin)",
    "group": "administrator of that resource group, or Billing access for the account",
    "instances": "Viewer or higher on the Billing service for the account",
}
FIELDS = ["month", "instance", "service", "plan", "resource_group", "region", "cost", "currency", "zero_usage"]


class CliError(RuntimeError):
    pass


def refuse_tracing() -> None:
    """With IBMCLOUD_TRACE on, the CLI prints API traffic into the output; stop instead."""
    trace = os.environ.get("IBMCLOUD_TRACE", "")
    if trace and trace.lower() != "false":
        raise CliError("IBMCLOUD_TRACE is on, so the CLI would print API traffic; unset it in the shell and run again")


def run_cli(args: list[str], timeout: int = 180):
    refuse_tracing()
    proc = subprocess.run(["ibmcloud", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        text = (proc.stderr or proc.stdout).strip().splitlines()
        raise CliError(" ".join(line.strip() for line in text if line.strip() and line.strip() != "FAILED")[:300])
    out = proc.stdout
    start = min((i for i in (out.find("{"), out.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise CliError("the CLI returned no JSON")
    return json.JSONDecoder().raw_decode(out[start:])[0]


def previous_month(month: str) -> str:
    first = dt.date.fromisoformat(f"{month}-01")
    return (first - dt.timedelta(days=1)).strftime("%Y-%m")


def is_denied(message: str) -> bool:
    return any(word in message.lower() for word in DENIED)


def money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def service_costs(doc) -> dict[str, float]:
    """account-usage or resource-group-usage -> {service: billable cost}."""
    out: dict[str, float] = defaultdict(float)
    for r in (doc or {}).get("resources") or []:
        out[r.get("resource_name") or r.get("resource_id") or "unknown"] += money(r.get("billable_cost"))
    return dict(out)


def instance_rows(doc, month: str) -> list[dict]:
    """resource-instances-usage -> one row per instance; the list may be wrapped in "resources"."""
    items = doc if isinstance(doc, list) else (doc or {}).get("resources") or []
    rows = []
    for i in items:
        usage = i.get("usage") or []
        cost = money(sum(money(u.get("cost")) for u in usage))
        rows.append({
            "month": i.get("month") or month,
            "instance": i.get("resource_instance_name") or i.get("resource_instance_id", ""),
            "service": i.get("resource_name") or i.get("resource_id", ""),
            "plan": i.get("plan_name") or i.get("plan_id", ""),
            "resource_group": i.get("resource_group_name") or i.get("resource_group_id", ""),
            "region": i.get("region") or i.get("pricing_region", ""),
            "cost": cost,
            "currency": i.get("currency_code", ""),
            "zero_usage": bool(usage) and cost > 0 and all(money(u.get("quantity")) == 0 for u in usage),
        })
    return sorted(rows, key=lambda r: -r["cost"])


def by_group(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        out[r["resource_group"] or "(unknown)"] += r["cost"]
    return {k: round(v, 2) for k, v in sorted(out.items(), key=lambda kv: -kv[1])}


def changes(current: dict[str, float], previous: dict[str, float], top: int = 10) -> list[tuple[str, float, float, float]]:
    keys = set(current) | set(previous)
    rows = [(k, previous.get(k, 0.0), current.get(k, 0.0), round(current.get(k, 0.0) - previous.get(k, 0.0), 2)) for k in keys]
    return sorted(rows, key=lambda r: -abs(r[3]))[:top]


def fetch(month: str, group: str | None, notes: list[str], raw: dict) -> dict:
    """Every report the role allows for one month; refusals become notes, not failures."""
    got: dict = {"services": None, "rows": None, "currency": ""}
    def attempt(kind: str, args: list[str]):
        try:
            doc = run_cli(args)
            raw[f"{kind}-{month}"] = doc
            return doc
        except CliError as exc:
            why = f"needs {NEEDS[kind]}" if is_denied(str(exc)) else str(exc)
            notes.append(f"{kind} usage for {month} not available: {why}")
        except subprocess.TimeoutExpired:
            notes.append(f"{kind} usage for {month}: the CLI timed out")
        return None
    account = attempt("account", ["billing", "account-usage", "-d", month, "--output", "json"])
    if account is not None:
        got["services"], got["currency"] = service_costs(account), account.get("currency_code", "")
    elif group:
        grp = attempt("group", ["billing", "resource-group-usage", group, "-d", month, "--output", "json"])
        if grp is not None:
            got["services"], got["currency"] = service_costs(grp), grp.get("currency_code", "")
    instances = attempt("instances", ["billing", "resource-instances-usage", *(["-g", group] if group else []), "-d", month, "--output", "json"])
    if instances is not None:
        got["rows"] = instance_rows(instances, month)
        got["currency"] = got["currency"] or next((r["currency"] for r in got["rows"] if r["currency"]), "")
    return got


def summarise(month: str, cur: dict, prev: dict | None) -> dict:
    rows = cur["rows"] or []
    services = cur["services"] if cur["services"] is not None else ({} if not rows else _from_rows(rows))
    summary = {
        "month": month, "month_to_date": month == dt.date.today().strftime("%Y-%m"), "currency": cur["currency"],
        "total": round(sum(services.values()), 2),
        "by_service": sorted(((k, round(v, 2)) for k, v in services.items()), key=lambda kv: -kv[1]),
        "by_resource_group": by_group(rows),
        "top_instances": [{k: r[k] for k in ("instance", "service", "resource_group", "cost")} for r in rows[:10]],
        "zero_usage": [{k: r[k] for k in ("instance", "service", "plan", "cost")} for r in rows if r["zero_usage"]],
    }
    if prev is not None:
        prev_services = prev["services"] if prev["services"] is not None else _from_rows(prev["rows"] or [])
        summary["previous_total"] = round(sum(prev_services.values()), 2)
        summary["service_changes"] = changes(dict(summary["by_service"]), prev_services)
        summary["instance_changes"] = changes({r["instance"]: r["cost"] for r in rows},
                                              {r["instance"]: r["cost"] for r in prev["rows"] or []})
    return summary


def _from_rows(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        out[r["service"] or "unknown"] += r["cost"]
    return dict(out)


def render(s: dict, notes: list[str], out: Path) -> str:
    c = s["currency"] or ""
    lines = [f"# IBM Cloud cost, {s['month']}{' (month to date)' if s['month_to_date'] else ''}", "",
             f"- Total: {s['total']:,.2f} {c}"]
    if "previous_total" in s:
        lines.append(f"- Previous month: {s['previous_total']:,.2f} {c} (change {s['total'] - s['previous_total']:+,.2f})")
    if s["by_service"]:
        lines += ["", "| Service | Cost |", "|---|---:|", *(f"| {k} | {v:,.2f} |" for k, v in s["by_service"][:12])]
    if s["by_resource_group"]:
        lines += ["", "| Resource group | Cost |", "|---|---:|", *(f"| {k} | {v:,.2f} |" for k, v in list(s["by_resource_group"].items())[:10])]
    if s["top_instances"]:
        lines += ["", "| Top instance | Service | Group | Cost |", "|---|---|---|---:|",
                  *(f"| {r['instance']} | {r['service']} | {r['resource_group']} | {r['cost']:,.2f} |" for r in s["top_instances"])]
    if s.get("service_changes"):
        lines += ["", "| Service | Before | Now | Change |", "|---|---:|---:|---:|",
                  *(f"| {k} | {a:,.2f} | {b:,.2f} | {d:+,.2f} |" for k, a, b, d in s["service_changes"] if d)]
    if s["zero_usage"]:
        lines += ["", "Billed with zero usage (review with the owner; nothing was changed):",
                  *(f"- {r['instance']} ({r['service']}, {r['plan']}): {r['cost']:,.2f} {c}" for r in s["zero_usage"])]
    if notes:
        lines += ["", "Not available with this role:", *(f"- {n}" for n in notes)]
    lines += ["", f"Files: {out}/cost-{s['month']}.csv, {out}/cost-{s['month']}.json, {out}/raw/"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--month", default=dt.date.today().strftime("%Y-%m"), help="YYYY-MM (default: this month)")
    parser.add_argument("--compare", action="store_true", help="add the previous month and the changes")
    parser.add_argument("--group", help="resource group, for users without account-level billing access")
    parser.add_argument("--out", default="ibmcloud-reports/cost")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        dt.date.fromisoformat(f"{args.month}-01")
    except ValueError:
        parser.error("--month must look like 2026-09")

    notes: list[str] = []
    raw: dict = {}
    cur = fetch(args.month, args.group, notes, raw)
    prev = fetch(previous_month(args.month), args.group, notes, raw) if args.compare else None
    if cur["services"] is None and cur["rows"] is None:
        sys.stderr.write("No usage report is available with this role:\n" + "\n".join(f"- {n}" for n in notes) + "\n")
        return 1
    summary = summarise(args.month, cur, prev)
    out = Path(args.out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    for name, doc in raw.items():
        (out / "raw" / f"{name}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    with (out / f"cost-{args.month}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(cur["rows"] or [])
    (out / f"cost-{args.month}.json").write_text(json.dumps({**summary, "notes": notes}, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "notes": notes}, indent=2) if args.json else render(summary, notes, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
