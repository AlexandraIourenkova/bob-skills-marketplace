#!/usr/bin/env python3
"""Copy a pack's skills from its upstream repository, as recorded in pack.json `source`.

Usage: sync_upstream.py <pack-name> [--ref <branch, tag or commit>]
Copies <source.path>/<skill> for every skill in pack.json into the pack's
skills/ folder, copies the repository LICENSE next to them, and pins
`source.ref` to the exact commit that was copied. Then run
`bob-skills registry validate --fix`, lint, review, bump the version, PR, tag.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack")
    parser.add_argument("--ref", help="Branch, tag or commit to copy; default: source.ref from pack.json")
    args = parser.parse_args()
    matches = list(Path("packs").glob(f"*/{args.pack}/pack.json"))
    if len(matches) != 1:
        raise SystemExit(f"expected one pack named {args.pack}, found {len(matches)}")
    manifest_path = matches[0]
    pack_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["source"]
    ref = args.ref or source["ref"]
    subpath = source.get("path", "").strip("/")
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "upstream"
        clone.mkdir()
        run("git", "init", "-q", cwd=clone)
        run("git", "remote", "add", "origin", source["repo"], cwd=clone)
        run("git", "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", ref, cwd=clone)
        run("git", "sparse-checkout", "set", "--no-cone", f"/{subpath}/**" if subpath else "/**", "/LICENSE*", cwd=clone)
        run("git", "checkout", "-q", "FETCH_HEAD", cwd=clone)
        commit = run("git", "rev-parse", "FETCH_HEAD", cwd=clone)
        for skill in manifest["skills"]:
            src = clone / subpath / skill if subpath else clone / skill
            if not (src / "SKILL.md").is_file():
                raise SystemExit(f"{skill}: no SKILL.md at {source['repo']}@{ref}:{subpath}/{skill}")
            dst = pack_dir / "skills" / skill
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "node_modules"))
            print(f"synced {skill} ({sum(1 for _ in dst.rglob('*') if _.is_file())} files)")
        licences = sorted(p for p in clone.glob("LICENSE*") if p.is_file())
        if licences:
            shutil.copyfile(licences[0], pack_dir / "skills" / "LICENSE")
            print(f"copied {licences[0].name}")
    source["ref"] = commit[:12]
    manifest["source"] = source
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{args.pack}: source.ref = {commit[:12]}; now `bob-skills registry validate --fix` and `bob-skills lint {pack_dir}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
