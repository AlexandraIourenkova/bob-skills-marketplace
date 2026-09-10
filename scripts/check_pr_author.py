#!/usr/bin/env python3
"""Fail when a PR touches a vendor folder or a protected file and the author is not allowed to.

Usage: check_pr_author.py --actor <login> --base <git ref>
Vendor folders are owned by the vendor's maintainers in vendors.json; shared
files (vendors.json, schemas, CODEOWNERS, CI, CLI) by the marketplace team's
maintainers (vendor id ``bob-skills-marketplace``).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROTECTED_PREFIXES = ("vendors.json", "schemas/", "CODEOWNERS", ".github/", "cli/", "scripts/", "index.json", "marketplace.json")
ADMIN_VENDOR = "bob-skills-marketplace"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor", required=True)
    parser.add_argument("--base", required=True, help="base ref, e.g. origin/main")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)
    vendors = {v["id"]: v for v in json.loads((root / "vendors.json").read_text())["vendors"]}
    admins = set(vendors.get(ADMIN_VENDOR, {}).get("maintainers", []))
    changed = subprocess.run(["git", "diff", "--name-only", f"{args.base}...HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
    failures = []
    for path in changed:
        if path.startswith("packs/"):
            vendor = path.split("/")[1]
            allowed = set(vendors.get(vendor, {}).get("maintainers", [])) | admins
            if vendor not in vendors:
                failures.append(f"{path}: vendor '{vendor}' is not in vendors.json")
            elif args.actor not in allowed:
                failures.append(f"{path}: {args.actor} is not a maintainer of vendor '{vendor}' (allowed: {sorted(allowed)})")
        elif path.startswith(PROTECTED_PREFIXES) and args.actor not in admins:
            failures.append(f"{path}: only marketplace administrators may change this file (allowed: {sorted(admins)})")
    for line in failures:
        print(f"::error::{line}")
    print(f"checked {len(changed)} changed file(s) for {args.actor}: {'refused' if failures else 'ok'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
