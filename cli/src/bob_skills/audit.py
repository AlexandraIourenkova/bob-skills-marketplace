"""``bob-skills audit``: check a skill before anyone trusts it.

The same layers as the registry gate, run on any folder: the policy linter
(always), NVIDIA SkillSpector and Cisco skill-scanner when they are installed.
Verdicts follow docs/security-gate.md: block on a blocking policy finding, a
SkillSpector risk of 30 or more, or a CRITICAL/HIGH Cisco finding.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .policy import BLOCK, WARN, Finding, lint_skill

SS_BLOCK, SS_REVIEW = 30, 10
CISCO_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


def _tool(name: str) -> str | None:
    return shutil.which(name) or shutil.which(name, path=str(Path.home() / ".local" / "bin"))


def skill_dirs(path: Path) -> list[Path]:
    path = Path(path)
    if (path / "SKILL.md").is_file():
        return [path]
    manifest = path / "pack.json"
    if manifest.is_file():
        names = json.loads(manifest.read_text(encoding="utf-8")).get("skills", [])
        return [path / "skills" / name for name in names]
    if (path / "skills").is_dir():
        path = path / "skills"
    return sorted(p for p in path.iterdir() if (p / "SKILL.md").is_file()) if path.is_dir() else []


def _skillspector(skill: Path, timeout: int) -> dict:
    exe = _tool("skillspector")
    if not exe:
        return {"available": False}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ss.json"
        subprocess.run([exe, "scan", str(skill), "--no-llm", "--format", "json", "--output", str(out)],
                       capture_output=True, text=True, timeout=timeout)
        if not out.is_file():
            return {"available": True, "error": "SkillSpector produced no report"}
        report = json.loads(out.read_text(encoding="utf-8"))
    issues = report.get("issues", [])
    return {
        "available": True,
        "riskScore": int(report.get("risk_assessment", {}).get("score", 0)),
        "issues": [{"id": i.get("id"), "severity": i.get("severity"), "category": i.get("category"),
                    "file": (i.get("location") or {}).get("file"), "line": (i.get("location") or {}).get("start_line"),
                    "finding": str(i.get("finding") or "")[:160]} for i in issues],
    }


def _cisco(skill: Path, timeout: int) -> dict:
    exe = _tool("skill-scanner")
    if not exe:
        return {"available": False}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cisco.json"
        subprocess.run([exe, "scan", str(skill), "--format", "json", "--output-json", str(out)],
                       capture_output=True, text=True, timeout=timeout)
        if not out.is_file():
            return {"available": True, "error": "skill-scanner produced no report"}
        report = json.loads(out.read_text(encoding="utf-8"))
    findings = report.get("findings", [])
    return {
        "available": True,
        "maxSeverity": report.get("max_severity", "INFO"),
        "findings": [{"severity": f.get("severity"), "rule": f.get("rule_id"), "file": f.get("file_path"),
                      "line": f.get("line_number"), "title": f.get("title")} for f in findings],
    }


def verdict(findings: list[Finding], ss: dict, cisco: dict) -> str:
    risk = ss.get("riskScore") or 0
    cisco_rank = CISCO_RANK.get(str(cisco.get("maxSeverity", "INFO")).upper(), 0)
    if any(f.severity == BLOCK for f in findings) or risk >= SS_BLOCK or cisco_rank >= CISCO_RANK["HIGH"]:
        return "block"
    if any(f.severity == WARN for f in findings) or risk >= SS_REVIEW or cisco_rank == CISCO_RANK["MEDIUM"]:
        return "review"
    return "pass"


def audit(path: Path, allow: list[str] | None = None, scanners: bool = True, timeout: int = 600) -> dict:
    """Audit a skill folder, a pack folder or a folder of skills."""
    results = []
    for skill in skill_dirs(Path(path)):
        findings = lint_skill(skill, list(allow or []), skill.parent)
        ss = _skillspector(skill, timeout) if scanners else {"available": False, "skipped": True}
        cisco = _cisco(skill, timeout) if scanners else {"available": False, "skipped": True}
        results.append({
            "skill": skill.name, "path": str(skill),
            "policy": [f.as_dict() for f in findings],
            "blocking": sum(f.severity == BLOCK for f in findings),
            "warnings": sum(f.severity == WARN for f in findings),
            "skillspector": ss, "cisco": cisco,
            "verdict": verdict(findings, ss, cisco),
        })
    order = {"pass": 0, "review": 1, "block": 2}
    overall = max((r["verdict"] for r in results), key=order.__getitem__, default="none")
    return {"path": str(path), "skills": results, "verdict": overall}
