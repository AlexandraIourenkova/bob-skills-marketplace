#!/usr/bin/env python3
"""Verify that a release tag <pack>--v<version> matches the pack's pack.json.

Usage: check_release_tag.py <tag>
Prints the pack folder on success so the workflow can package it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main(tag: str) -> int:
    if "--v" not in tag:
        print(f"::error::tag '{tag}' is not of the form <pack>--v<version>")
        return 1
    name, version = tag.split("--v", 1)
    matches = list(Path("packs").glob(f"*/{name}/pack.json"))
    if len(matches) != 1:
        print(f"::error::expected exactly one pack named '{name}', found {len(matches)}")
        return 1
    # Read the manifest as it is at the tag, so older tags stay valid after later releases.
    shown = subprocess.run(["git", "show", f"{tag}:{matches[0].as_posix()}"], capture_output=True, text=True)
    manifest = json.loads(shown.stdout) if shown.returncode == 0 else json.loads(matches[0].read_text())
    if manifest.get("version") != version:
        print(f"::error::tag says {version} but {matches[0]} has version {manifest.get('version')}")
        return 1
    if version in manifest.get("revokedVersions", []):
        print(f"::error::{name}@{version} is listed in revokedVersions")
        return 1
    print(matches[0].parent.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
