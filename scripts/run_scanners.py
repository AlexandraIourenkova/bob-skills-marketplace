#!/usr/bin/env python3
"""Run NVIDIA SkillSpector and Cisco skill-scanner on every skill of every pack.

Usage:
  run_scanners.py [pack ...] [--write] [--check] [--accept-skillspector REASON]

--write   records results in packs/<vendor>/<pack>/.scan.json (committed; shown by
          the site, `bob-skills show` and index.json via `registry build-index`).
--check   exits 1 when any pack's verdict is `block`: SkillSpector risk score >= 30
          after the pack's .skillspector-baseline.yaml, or a Cisco CRITICAL/HIGH finding.
--accept-skillspector REASON
          regenerates the pack's .skillspector-baseline.yaml accepting every current
          SkillSpector finding with REASON (reviewers only, after reading the findings).

Thresholds follow docs/security-gate.md: >= 30 block, 10 to 29 manual review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BLOCK, REVIEW = 30, 10
SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
SS_BASELINE = ".skillspector-baseline.yaml"
CISCO_BASELINE = ".cisco-baseline.json"


def tool(name: str) -> str:
    found = shutil.which(name) or shutil.which(name, path=str(Path.home() / ".local" / "bin"))
    if not found:
        raise SystemExit(f"{name} not found; install with `uv tool install` (see docs/security-gate.md)")
    return found


def run_json(cmd: list[str], out: Path, timeout: int = 600) -> dict:
    subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if not out.is_file():
        raise RuntimeError(f"no report written by {' '.join(cmd[:2])}")
    return json.loads(out.read_text(encoding="utf-8"))


def skillspector_scan(skill: Path, baseline: Path | None, tmp: Path, raw: bool = False) -> dict:
    out = tmp / f"ss-{skill.parent.parent.name}-{skill.name}.json"
    cmd = [tool("skillspector"), "scan", str(skill), "--no-llm", "--format", "json", "--output", str(out)]
    if baseline and baseline.is_file():
        cmd += ["--baseline", str(baseline)]
    report = run_json(cmd, out)
    if raw:
        return report
    risk = report.get("risk_assessment", {})
    issues = report.get("issues", [])
    return {
        "riskScore": int(risk.get("score", 0)),
        "recommendation": risk.get("recommendation"),
        "severity": risk.get("severity"),
        "issues": len(issues),
        "byRule": dict(Counter(i.get("id", "?") for i in issues)),
        "suppressed": int(report.get("suppressed_count", 0)),
        "version": report.get("metadata", {}).get("skillspector_version"),
        "complete": report.get("analysis_completeness", {}).get("is_complete"),
    }


def cisco_key(skill: Path, finding: dict) -> str:
    raw = "|".join(str(finding.get(k, "")) for k in ("category", "title", "file_path", "line_number"))
    return hashlib.sha256(f"{skill.name}|{raw}".encode()).hexdigest()[:16]


def cisco_scan(skill: Path, tmp: Path, accepted: dict[str, dict]) -> dict:
    out = tmp / f"cisco-{skill.parent.parent.name}-{skill.name}.json"
    report = run_json([tool("skill-scanner"), "scan", str(skill), "--format", "json", "--output-json", str(out)], out)
    findings = report.get("findings", [])
    active = [f for f in findings if cisco_key(skill, f) not in accepted]
    ranked = [f.get("severity") for f in active if f.get("severity") in SEVERITY_RANK]
    return {
        "isSafe": bool(report.get("is_safe", False)),
        "maxSeverity": max(ranked, key=lambda s: SEVERITY_RANK[s]) if ranked else ("INFO" if findings else None),
        "findings": len(findings),
        "accepted": len(findings) - len(active),
        "bySeverity": dict(Counter(f.get("severity", "?") for f in active)),
        "version": (report.get("scan_metadata") or {}).get("scanner_version"),
        "_raw": findings,
    }


def verdict(skills: dict) -> dict:
    scores = [s["skillspector"]["riskScore"] for s in skills.values()]
    cisco = [s["cisco"]["maxSeverity"] for s in skills.values() if s["cisco"]["maxSeverity"]]
    risk = max(scores) if scores else None
    cisco_max = max(cisco, key=lambda x: SEVERITY_RANK.get(x, 0)) if cisco else None
    if (risk is not None and risk >= BLOCK) or SEVERITY_RANK.get(cisco_max or "", 0) >= SEVERITY_RANK["HIGH"]:
        result = "block"
    elif (risk is not None and risk >= REVIEW) or SEVERITY_RANK.get(cisco_max or "", 0) >= SEVERITY_RANK["MEDIUM"]:
        result = "review"
    else:
        result = "pass"
    return {"riskScore": risk, "ciscoMaxSeverity": cisco_max, "verdict": result,
            "skillspectorSuppressed": sum(s["skillspector"]["suppressed"] for s in skills.values()),
            "ciscoAccepted": sum(s["cisco"].get("accepted", 0) for s in skills.values())}


def accept_skillspector(pack_dir: Path, skills: list[Path], reason: str, tmp: Path) -> Path:
    """Merge per-skill `skillspector baseline` outputs into one pack baseline."""
    import yaml
    merged = {"version": 2, "scanner_version": None, "rules": [], "fingerprints": []}
    seen = set()
    for skill in skills:
        out = tmp / f"baseline-{skill.name}.yaml"
        subprocess.run([tool("skillspector"), "baseline", str(skill), "-o", str(out), "--no-llm", "--reason", reason],
                       capture_output=True, text=True, timeout=600)
        if not out.is_file():
            continue
        data = yaml.safe_load(out.read_text(encoding="utf-8")) or {}
        merged["scanner_version"] = data.get("scanner_version") or merged["scanner_version"]
        for fp in data.get("fingerprints", []):
            if fp.get("hash") not in seen:
                seen.add(fp.get("hash"))
                merged["fingerprints"].append(fp)
    path = pack_dir / SS_BASELINE
    path.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True), encoding="utf-8")
    # Second pass: findings that fingerprints did not catch get a glob rule (rule id + file).
    rules = []
    seen_rules = set()
    for skill in skills:
        report = skillspector_scan(skill, path, tmp, raw=True)
        for issue in report.get("issues", []):
            loc = issue.get("location") or {}
            key = (issue.get("id"), loc.get("file"))
            if key in seen_rules or not issue.get("id"):
                continue
            seen_rules.add(key)
            rule = {"id": issue["id"], "reason": reason}
            if loc.get("file"):
                rule["path"] = f"*{loc['file']}"
            rules.append(rule)
    if rules:
        merged["rules"] = rules
        path.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packs", nargs="*", help="pack names; default: all")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--accept-skillspector", metavar="REASON")
    parser.add_argument("--accept-cisco", metavar="REASON", help="accept every current Cisco finding above INFO into .cisco-baseline.json")
    parser.add_argument("--reports", metavar="DIR", help="keep raw JSON reports in DIR")
    args = parser.parse_args()
    manifests = sorted(Path("packs").glob("*/*/pack.json"))
    if args.packs:
        manifests = [m for m in manifests if m.parent.name in args.packs]
    blocked = []
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(args.reports) if args.reports else Path(tmp_name)
        tmp.mkdir(parents=True, exist_ok=True)
        for manifest_path in manifests:
            pack_dir = manifest_path.parent
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            skills = [pack_dir / "skills" / s for s in manifest.get("skills", [])]
            if args.accept_skillspector:
                print(f"{pack_dir}: baseline -> {accept_skillspector(pack_dir, skills, args.accept_skillspector, tmp)}")
            baseline = pack_dir / SS_BASELINE
            cisco_path = pack_dir / CISCO_BASELINE
            accepted = {}
            if cisco_path.is_file():
                accepted = {e["key"]: e for e in json.loads(cisco_path.read_text(encoding="utf-8")).get("accepted", [])}
            results = {}
            for skill in skills:
                results[skill.name] = {"skillspector": skillspector_scan(skill, baseline, tmp), "cisco": cisco_scan(skill, tmp, accepted)}
                if args.accept_cisco:
                    for f in results[skill.name]["cisco"]["_raw"]:
                        if f.get("severity") in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                            key = cisco_key(skill, f)
                            accepted.setdefault(key, {"key": key, "skill": skill.name, "severity": f.get("severity"), "category": f.get("category"),
                                                      "title": f.get("title"), "file": f.get("file_path"), "line": f.get("line_number"), "reason": args.accept_cisco})
                results[skill.name]["cisco"].pop("_raw", None)
                ss, cs = results[skill.name]["skillspector"], results[skill.name]["cisco"]
                print(f"  {pack_dir.name}/{skill.name}: SkillSpector {ss['riskScore']}/100 {ss['recommendation']} "
                      f"({ss['issues']} issues {ss['byRule']}, {ss['suppressed']} suppressed) | Cisco {cs['maxSeverity']} ({cs['findings']} findings)")
            if args.accept_cisco:
                cisco_path.write_text(json.dumps({"_comment": "Accepted Cisco skill-scanner findings, each read by a reviewer. Remove an entry to re-evaluate it.",
                                                  "accepted": sorted(accepted.values(), key=lambda e: (e["skill"], e["file"] or "", e["key"]))}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                # re-evaluate with the new acceptance so the verdict reflects it
                for skill in skills:
                    results[skill.name]["cisco"] = cisco_scan(skill, tmp, accepted)
                    results[skill.name]["cisco"].pop("_raw", None)
            summary = verdict(results)
            versions = {"skillspector": next((r["skillspector"]["version"] for r in results.values()), None),
                        "ciscoSkillScanner": next((r["cisco"]["version"] for r in results.values()), None)}
            print(f"{pack_dir.name}: verdict {summary['verdict']} (risk {summary['riskScore']}, cisco {summary['ciscoMaxSeverity']})")
            if summary["verdict"] == "block":
                blocked.append(pack_dir.name)
            if args.write:
                data = {"scannedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                        "tools": versions, "thresholds": {"block": BLOCK, "review": REVIEW}, "skills": results, "summary": summary}
                (pack_dir / ".scan.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.check and blocked:
        print(f"::error::gate blocked: {', '.join(blocked)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
