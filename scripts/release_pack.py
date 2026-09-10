#!/usr/bin/env python3
"""Publish a pack version as a GitHub release with downloadable archives.

Usage: release_pack.py <tag> [<tag> ...]      e.g. release_pack.py wxo-adk--v1.1.0
       release_pack.py --all                   every <pack>--v<version> tag

For each tag: verifies it matches pack.json (scripts/check_release_tag.py),
exports the pack folder at that tag with `git archive`, writes <tag>.zip,
<tag>.tar.gz and <tag>.sha256, and creates the release with `gh release create`
(skipped when the release already exists). Runs where GitHub Actions cannot.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args: str, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, check=check, capture_output=True, text=True, **kw)


def repo_slug() -> str:
    url = run("git", "remote", "get-url", "origin").stdout.strip()
    host, path = url.replace("https://", "").replace("git@", "").replace(":", "/").split("/", 1)
    return host, path.removesuffix(".git")


def release(tag: str, host: str, repo: str) -> str:
    check = run("python3", "scripts/check_release_tag.py", tag, check=False)
    if check.returncode != 0:
        return f"{tag}: {check.stdout.strip() or check.stderr.strip()}"
    pack_dir = check.stdout.strip()
    env = {**os.environ, "GH_HOST": host}
    exists = subprocess.run(["gh", "release", "view", tag, "-R", repo], env=env, capture_output=True, text=True)
    if exists.returncode == 0:
        return f"{tag}: release already exists"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for fmt, name in (("zip", f"{tag}.zip"), ("tar.gz", f"{tag}.tar.gz")):
            with open(out / name, "wb") as handle:
                subprocess.run(["git", "archive", f"--format={fmt}", f"--prefix={tag}/", tag, "--", pack_dir], cwd=ROOT, check=True, stdout=handle)
        digests = []
        for name in (f"{tag}.zip", f"{tag}.tar.gz"):
            digests.append(f"{hashlib.sha256((out / name).read_bytes()).hexdigest()}  {name}")
        (out / f"{tag}.sha256").write_text("\n".join(digests) + "\n")
        name, version = tag.split("--v", 1)
        notes = (f"Pack `{name}` version {version}. Archives contain `{pack_dir}` as it is at this tag.\n\n"
                 f"Install with the marketplace client: `uvx bob-skills add {name}@{version}`\n"
                 f"Verify: `sha256sum -c {tag}.sha256`")
        create = subprocess.run(["gh", "release", "create", tag, str(out / f"{tag}.zip"), str(out / f"{tag}.tar.gz"), str(out / f"{tag}.sha256"),
                                 "-R", repo, "--title", tag, "--notes", notes], env=env, capture_output=True, text=True)
        if create.returncode != 0:
            return f"{tag}: gh release create failed: {create.stderr.strip()[:200]}"
    return f"{tag}: released"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tags", nargs="*")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    tags = args.tags
    if args.all:
        tags = [t for t in run("git", "tag", "--list", "*--v*").stdout.split() if "--v" in t]
    if not tags:
        parser.error("give tags or --all")
    host, repo = repo_slug()
    failed = False
    for tag in tags:
        line = release(tag, host, repo)
        failed |= "failed" in line or "error" in line.lower()
        print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
