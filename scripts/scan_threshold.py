#!/usr/bin/env python3
"""Apply the marketplace thresholds to SkillSpector JSON reports.

Usage: scan_threshold.py report1.json [report2.json ...]
Exit 1 when any report scores >= BLOCK (30). Scores in [REVIEW, BLOCK) are
printed as warnings for manual review. The JSON field name is read defensively
(risk_score / riskScore / score, top level or under summary) until the week-0
spike pins the exact report shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REVIEW = 10
BLOCK = 30


def score_of(report: dict) -> int | None:
    for container in (report, report.get("summary", {}), report.get("result", {})):
        if not isinstance(container, dict):
            continue
        for key in ("risk_score", "riskScore", "score"):
            value = container.get(key)
            if isinstance(value, (int, float)):
                return int(value)
    return None


def main(paths: list[str]) -> int:
    blocked = False
    for path in paths:
        report = json.loads(Path(path).read_text())
        score = score_of(report)
        if score is None:
            print(f"::warning::{path}: no risk score found in report; check the SkillSpector JSON shape")
            continue
        if score >= BLOCK:
            print(f"::error::{path}: risk score {score} >= {BLOCK}: blocked")
            blocked = True
        elif score >= REVIEW:
            print(f"::warning::{path}: risk score {score}: manual review required")
        else:
            print(f"{path}: risk score {score}: ok")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
