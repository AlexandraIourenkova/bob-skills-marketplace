#!/usr/bin/env python3
"""Read-only checks on a repository before it is submitted or made public.

    submission_check.py [repo] [--report <exported Bob session report>] [--no-history] [--json out.json]

It looks for credentials in the tracked files and in the git history, for files that
should not be tracked, and for the pieces a challenge entry needs (README, blueprint,
session report). It reports and never fixes: it changes no file, rewrites no history,
rotates no key and contacts no network. A credential is shown as its file, line and
name with the value masked.

Finding credentials by pattern is a net, not a proof: a clean result means none of the
known shapes was found. Standard library only; git is called with read-only commands.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 1_000_000
BIG_FILE = 20_000_000
KEY_NAME = r"[A-Za-z0-9_.-]*(?:api[_-]?key|apikey|secret|token|passw(?:or)?d|credential|private[_-]?key)[A-Za-z0-9_.-]*"
ASSIGNED = re.compile(rf"""(?ix) \b({KEY_NAME}) ["']? \s* [:=] \s* (["']?) ([A-Za-z0-9_\-/+=]{{20,}}) (?![A-Za-z0-9_.(\[]) """)
SHAPES = [
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |)PRIVATE KEY")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("API key with an sk- prefix", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b")),
    ("Slack token", re.compile(r"\bxox[abpsr]-[A-Za-z0-9-]{20,}\b")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\b")),
]
PLACEHOLDER = ("example", "changeme", "placeholder", "your", "xxxx", "dummy", "fake", "redacted", "<", ">", "${", "{{", "...", "process.env", "os.environ", "getenv")
UNWANTED = [
    (re.compile(r"(^|/)\.env(\.[A-Za-z0-9_-]+)?$"), "an environment file; keep it out of git and commit a .env.example without values"),
    (re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$"), "a key or certificate store"),
    (re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$"), "a private SSH key"),
    (re.compile(r"(^|/)(credentials|service-account|secrets?)\.(json|ya?ml)$"), "a credentials file"),
    (re.compile(r"(^|/)(node_modules|\.venv|venv|__pycache__|\.gradle|dist|build)/"), "installed or built output; it belongs in .gitignore"),
]
EXAMPLE_ENV = re.compile(r"\.env\.(example|sample|template)$")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace")
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout


def entropy(text: str) -> float:
    counts = {ch: text.count(ch) for ch in set(text)}
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def mask(value: str) -> str:
    return value[:4] + "…" + f" ({len(value)} characters)"


def scan_line(line: str) -> list[tuple[str, str]]:
    """Credentials on one line, as (what, masked value). The value itself never leaves this function."""
    found = []
    for label, pattern in SHAPES:
        match = pattern.search(line)
        if match:
            found.append((label, mask(match.group(0))))
    match = ASSIGNED.search(line)
    if match:
        name, quoted, value = match.group(1), match.group(2), match.group(3)
        low = line.lower()
        # A bare identifier is code that refers to a value; a name in one case with underscores is a constant.
        reference = (not quoted and value.isidentifier()) or ("_" in value and (value.isupper() or value.islower()) and value.replace("_", "").isalnum())
        looks_real = (entropy(value) >= 3.5 and any(ch.isdigit() for ch in value) and not reference
                      and not any(mark in low for mark in PLACEHOLDER))
        if looks_real and not any(masked == mask(value) for _, masked in found):
            found.append((f"a value assigned to '{name}'", mask(value)))
    return found


def tracked(repo: Path) -> list[str]:
    return [name for name in git(repo, "ls-files", "-z").split("\0") if name]


def check_files(repo: Path, files: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    secrets, unwanted, large = [], [], []
    for name in files:
        if not EXAMPLE_ENV.search(name):
            for pattern, why in UNWANTED:
                if pattern.search(name):
                    unwanted.append({"file": name, "why": why})
                    break
        path = repo / name
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > BIG_FILE:
            large.append({"file": name, "megabytes": round(size / 1_000_000, 1)})
        if size > MAX_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for what, masked in scan_line(line[:2000]):
                secrets.append({"file": name, "line": number, "what": what, "value": masked})
    return secrets, unwanted, large


def check_history(repo: Path, limit: int = 200) -> list[dict]:
    """Credentials in lines that any commit added, including lines deleted later."""
    found, commit, name = [], "", ""
    log = git(repo, "log", "--all", "-p", "-U0", "--no-color", "--no-ext-diff", "--format=commit %h %ad", "--date=short")
    for line in log.splitlines():
        if line.startswith("commit "):
            commit = line[7:]
        elif line.startswith("+++ "):
            name = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("+") and name and not EXAMPLE_ENV.search(name):
            for what, masked in scan_line(line[1:2000]):
                found.append({"commit": commit, "file": name, "what": what, "value": masked})
                if len(found) >= limit:
                    return found
    return found


def check_blueprint(repo: Path) -> dict | None:
    spec_path = repo / "challenge" / "blueprint.json"
    if not spec_path.is_file():
        return None
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except ValueError:
        return {"error": "challenge/blueprint.json is not valid JSON"}
    marks: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("basis") in ("measured", "estimate", "assumption"):
                marks.append(node["basis"])
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(spec)
    nodes = [n for layer in (spec.get("architecture") or {}).get("layers") or [] for n in layer.get("nodes") or []]
    page = repo / "challenge" / "blueprint.html"
    return {"status": (spec.get("meta") or {}).get("status", "plan"), "numbers": len(marks),
            "measured": marks.count("measured"), "estimate": marks.count("estimate"), "assumption": marks.count("assumption"),
            "planned_nodes": sum(1 for n in nodes if n.get("status") in ("planned", "mock")), "nodes": len(nodes),
            "page": page.is_file(), "page_older_than_spec": page.is_file() and page.stat().st_mtime < spec_path.stat().st_mtime}


def run(repo: Path, report: str | None, history: bool) -> dict:
    result: dict = {"repo": str(repo), "checks": []}

    def add(key: str, status: str, summary: str, items: list | None = None) -> None:
        result["checks"].append({"check": key, "status": status, "summary": summary, "items": items or []})

    try:
        files = tracked(repo)
    except (RuntimeError, FileNotFoundError) as error:
        add("repository", "fail", f"not a git repository, or git is missing: {error}")
        return result
    add("repository", "pass", f"{len(files)} tracked files")

    secrets, unwanted, large = check_files(repo, files)
    add("credentials in tracked files", "fail" if secrets else "pass",
        f"{len(secrets)} found; remove each from the file, then rotate it, because it is already in the history" if secrets else "none of the known shapes found", secrets)
    if history:
        try:
            old = check_history(repo)
            gone = [item for item in old if not any(s["file"] == item["file"] and s["value"] == item["value"] for s in secrets)]
            add("credentials in the git history", "fail" if gone else "pass",
                f"{len(gone)} found in earlier commits; deleting the line does not remove it from the history, so rotate the credential" if gone else "none of the known shapes found", gone)
        except RuntimeError as error:
            add("credentials in the git history", "warn", f"could not read the history: {error}")
    else:
        add("credentials in the git history", "skipped", "not checked (--no-history)")
    add("files that should not be tracked", "fail" if any("key" in u["why"] or "credentials" in u["why"] or "environment" in u["why"] for u in unwanted) else ("warn" if unwanted else "pass"),
        f"{len(unwanted)} found" if unwanted else "none", unwanted)
    add("large files", "warn" if large else "pass", f"{len(large)} above 20 MB" if large else "none", large)

    ignore = (repo / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines() if (repo / ".gitignore").is_file() else []
    covered = any(line.strip().lstrip("/") in (".env", ".env*", ".env.*", "*.env") for line in ignore)
    add(".gitignore covers .env", "pass" if covered else "warn",
        "yes" if covered else "no line for .env; add one before the first key is pasted into such a file")

    readmes = [name for name in files if name.lower() in ("readme.md", "readme.rst", "readme.txt", "readme")]
    if readmes:
        size = (repo / readmes[0]).stat().st_size
        add("README", "pass" if size > 400 else "warn", f"{readmes[0]}, {size} bytes" + ("" if size > 400 else "; too short to tell a stranger how to run the solution"))
    else:
        add("README", "fail", "no README at the top of the repository")

    blueprint = check_blueprint(repo)
    if blueprint is None:
        add("blueprint", "warn", "challenge/blueprint.json not found")
    elif "error" in blueprint:
        add("blueprint", "fail", blueprint["error"])
    else:
        notes = [f"status {blueprint['status']}", f"{blueprint['numbers']} marked numbers: {blueprint['measured']} measured, {blueprint['estimate']} estimate, {blueprint['assumption']} assumption",
                 f"{blueprint['planned_nodes']} of {blueprint['nodes']} architecture nodes planned or mocked"]
        status = "pass"
        if blueprint["status"] != "as-built":
            status, extra = "warn", "the document still says it is a plan; move it to as-built once the proof of concept runs"
            notes.append(extra)
        if not blueprint["page"]:
            status = "warn"
            notes.append("blueprint.html is missing; render it")
        elif blueprint["page_older_than_spec"]:
            status = "warn"
            notes.append("blueprint.html is older than the spec; render it again")
        add("blueprint", status, "; ".join(notes))

    if report:
        path = Path(report)
        ok = path.is_file() and path.stat().st_size > 0
        add("Bob session report", "pass" if ok else "fail", f"{path} ({path.stat().st_size} bytes)" if ok else f"{path} is missing or empty")
    else:
        add("Bob session report", "warn", "not checked: export the task session report from Bob IDE and pass its path with --report")

    dirty = [line for line in git(repo, "status", "--porcelain").splitlines() if line.strip()]
    add("uncommitted changes", "warn" if dirty else "pass", f"{len(dirty)} files differ from the last commit; what is not committed is not submitted" if dirty else "none")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only checks on a repository before submission.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--report", help="path of the exported Bob task session report")
    parser.add_argument("--no-history", action="store_true", help="do not read the git history")
    parser.add_argument("--json", dest="out", help="also write the result to this file")
    args = parser.parse_args(argv)
    result = run(Path(args.repo).resolve(), args.report, not args.no_history)
    marks = {"pass": "ok  ", "warn": "warn", "fail": "FAIL", "skipped": "skip"}
    for check in result["checks"]:
        print(f"[{marks[check['status']]}] {check['check']}: {check['summary']}")
        for item in check["items"][:25]:
            where = item.get("file", "")
            if "line" in item:
                where += f":{item['line']}"
            if "commit" in item:
                where = f"{item['commit']}  {where}"
            detail = item.get("what") or item.get("why") or f"{item.get('megabytes')} MB"
            print(f"       {where}  {detail}" + (f"  {item['value']}" if "value" in item else ""))
        if len(check["items"]) > 25:
            print(f"       ... and {len(check['items']) - 25} more")
    failed = sum(1 for c in result["checks"] if c["status"] == "fail")
    warned = sum(1 for c in result["checks"] if c["status"] == "warn")
    print(f"\n{failed} to fix, {warned} to look at. Nothing was changed.")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
