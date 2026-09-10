#!/usr/bin/env python3
"""Copy the official skills from the watsonx Orchestrate ADK repository into the wxo pack.

Usage: sync_adk_skills.py --ref 2.16.0
Then: bump version in pack.json, run `bob-skills registry validate --fix`, lint, PR.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

PACK = Path("packs/ibm-watsonx-orchestrate/wxo")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True, help="ADK tag, e.g. 2.16.0")
    args = parser.parse_args()
    manifest = json.loads((PACK / "pack.json").read_text())
    repo = manifest["source"]["repo"]
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "adk"
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", args.ref, "--filter=blob:none", "--sparse", repo, str(clone)], check=True)
        subprocess.run(["git", "sparse-checkout", "set", manifest["source"].get("path", "skills")], cwd=clone, check=True)
        subprocess.run(["git", "checkout", "--quiet", "HEAD", "--", "LICENSE"], cwd=clone, check=True)
        for skill in manifest["skills"]:
            src = clone / manifest["source"].get("path", "skills") / skill
            dst = PACK / "skills" / skill
            if not src.is_dir():
                raise SystemExit(f"skill '{skill}' not found in {repo}@{args.ref}")
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
            print(f"synced {skill}")
        shutil.copyfile(clone / "LICENSE", PACK / "skills" / "LICENSE")
    manifest["source"]["ref"] = args.ref
    (PACK / "pack.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"pack.json source.ref = {args.ref}; now bump version and run `bob-skills registry validate --fix`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
