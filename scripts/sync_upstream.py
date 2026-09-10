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
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


TEXT_SUFFIXES = {".md", ".txt", ".py", ".sh", ".ps1", ".yaml", ".yml", ".json", ".toml", ".js", ".ts", ".html", ".css", ".csv", ".cfg", ".ini", ".bicep", ".tf", ".hcl", ".xml"}


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
    overrides = manifest.get("sources", {})
    groups: dict[tuple, list[str]] = {}
    for skill in manifest["skills"]:
        src = overrides.get(skill) or manifest["source"]
        key = (src["repo"], args.ref or src["ref"], src.get("path", "").strip("/"))
        groups.setdefault(key, []).append(skill)
    resolved: dict[tuple, str] = {}
    for (repo, ref, subpath), skills in groups.items():
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "upstream"
            clone.mkdir()
            run("git", "init", "-q", cwd=clone)
            run("git", "remote", "add", "origin", repo, cwd=clone)
            fetch_ref = ref
            if re.fullmatch(r"[0-9a-f]{7,39}", ref):
                fetch_ref = "HEAD"  # an abbreviated commit cannot be fetched; take the default branch and verify below
            run("git", "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", fetch_ref, cwd=clone)
            if fetch_ref != ref and not run("git", "rev-parse", "FETCH_HEAD", cwd=clone).startswith(ref):
                raise SystemExit(f"{repo}: default branch moved past {ref}; pass --ref with a full 40-character commit or a branch")
            run("git", "sparse-checkout", "set", "--no-cone", f"/{subpath}/**" if subpath else "/**", "/LICENSE*", cwd=clone)
            run("git", "checkout", "-q", "FETCH_HEAD", cwd=clone)
            commit = run("git", "rev-parse", "FETCH_HEAD", cwd=clone)
            resolved[(repo, ref, subpath)] = commit
            for skill in skills:
                src_dir = clone / subpath / skill if subpath else clone / skill
                if not (src_dir / "SKILL.md").is_file():
                    raise SystemExit(f"{skill}: no SKILL.md at {repo}@{ref}:{subpath}/{skill}")
                dst = pack_dir / "skills" / skill
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src_dir, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "node_modules"))
                for f in dst.rglob("*"):
                    if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES and b"\r\n" in f.read_bytes():
                        f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))  # git normalises on commit; checksums must see the same bytes
                print(f"synced {skill} from {repo}@{commit[:12]} ({sum(1 for _ in dst.rglob('*') if _.is_file())} files)")
            licences = sorted(l for l in clone.glob("LICENSE*") if l.is_file())
            if licences:
                suffix = "" if (repo, ref, subpath) == (manifest["source"]["repo"], args.ref or manifest["source"]["ref"], manifest["source"].get("path", "").strip("/")) else "-" + re.sub(r"[^A-Za-z0-9]+", "-", repo.split("/")[-1])
                shutil.copyfile(licences[0], pack_dir / "skills" / f"LICENSE{suffix}")
    main_key = (manifest["source"]["repo"], args.ref or manifest["source"]["ref"], manifest["source"].get("path", "").strip("/"))
    if main_key in resolved:
        manifest["source"]["ref"] = resolved[main_key]
    for skill, src in overrides.items():
        key = (src["repo"], args.ref or src["ref"], src.get("path", "").strip("/"))
        if key in resolved:
            src["ref"] = resolved[key]
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{args.pack}: pinned {len(resolved)} source(s); now `bob-skills registry validate --fix` and `uvx bob-skills lint {pack_dir}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
