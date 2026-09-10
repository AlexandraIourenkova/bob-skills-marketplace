#!/usr/bin/env python3
"""Keep roadmap.json in sync with the pack-request issues that collect votes.

Usage: refresh_roadmap.py [--create-issues]
For every planned pack: with --create-issues, open a "Request pack: <name>" issue
(label pack-request) when the entry has no issue yet and record its URL; always
refresh `votes` with the thumbs-up reaction count of the issue. Then run
`bob-skills registry build-index` so index.json, the catalog and the site pick
the numbers up. Needs the gh CLI logged in to the registry's GitHub host.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def repo() -> tuple[str, str]:
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    host, path = url.replace("https://", "").replace("git@", "").replace(":", "/").split("/", 1)
    return host, path.removesuffix(".git")


def gh(host: str, *args: str) -> str:
    result = subprocess.run(["gh", *args], env={**os.environ, "GH_HOST": host}, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {result.stderr.strip()[:200]}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-issues", action="store_true")
    args = parser.parse_args()
    path = ROOT / "roadmap.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    host, slug = repo()
    vendors = {v["id"]: v for v in json.loads((ROOT / "vendors.json").read_text(encoding="utf-8"))["vendors"]}
    for entry in data["planned"]:
        if not entry.get("issue") and args.create_issues:
            vendor = vendors.get(entry["vendor"], {}).get("displayName", entry.get("vendorDisplayName", entry["vendor"]))
            body = (f"**Pack** `{entry['name']}` from {vendor} ({entry['status']}).\n\n{entry['description']}\n\n"
                    f"**Source:** {entry.get('source', '-')}\n" + (f"**Blocked by:** {entry['blockedBy']}\n" if entry.get("blockedBy") else "") +
                    "\n**Vote** with a thumbs-up reaction on this issue; the count shows in the marketplace catalog. Comment with what you would use it for.")
            out = gh(host, "issue", "create", "-R", slug, "--title", f"Request pack: {entry['name']}", "--label", "pack-request", "--body", body)
            entry["issue"] = out.strip().splitlines()[-1]
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"created {entry['issue']}")
        if entry.get("issue"):
            number = entry["issue"].rstrip("/").split("/")[-1]
            issue = json.loads(gh(host, "api", f"repos/{slug}/issues/{number}"))
            entry["votes"] = int((issue.get("reactions") or {}).get("+1", 0))
        else:
            entry.setdefault("votes", 0)
    data["updated"] = date.today().isoformat()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("roadmap.json refreshed; run `bob-skills registry build-index`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
