"""``bob-skills doctor``: one read-only report on the Bob setup of a project and the user scope.

It never changes a file. Each item says what is wrong, why it matters and how to
fix it; the bob-doctor skill explains the report and applies fixes only after
the user agrees.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .installer import Scope, verify
from .mcpcheck import PROBLEM, WARNING, check_servers
from .policy import read_frontmatter
from .registry import BOB_GROUPS


@dataclass
class Item:
    scope: str
    area: str
    severity: str
    message: str
    fix: str = ""

    def as_dict(self) -> dict:
        return {"scope": self.scope, "area": self.area, "severity": self.severity, "message": self.message, "fix": self.fix}


@dataclass
class Report:
    items: list[Item] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    def add(self, *args: str) -> None:
        self.items.append(Item(*args))

    @property
    def problems(self) -> list[Item]:
        return [i for i in self.items if i.severity == PROBLEM]

    @property
    def warnings(self) -> list[Item]:
        return [i for i in self.items if i.severity == WARNING]

    def as_dict(self) -> dict:
        return {"problems": len(self.problems), "warnings": len(self.warnings), "checked": self.checked,
                "items": [i.as_dict() for i in self.items]}


def _load_json(path: Path, report: Report, scope: str, area: str) -> dict | None:
    if not path.is_file():
        return None
    report.checked.append(str(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        report.add(scope, area, PROBLEM, f"{path} is not valid JSON ({error}); Bob cannot read it", "fix the syntax")
        return None
    return data if isinstance(data, dict) else None


def _has_hook(settings: dict | None, event: str, command_part: str, tool: str | None = None) -> bool:
    for entry in ((settings or {}).get("hooks", {}) or {}).get(event, []) or []:
        matcher = str(entry.get("matcher", "") or "")
        if tool is not None:
            try:
                if matcher and not re.search(matcher, tool):
                    continue
            except re.error:
                continue
        for hook in entry.get("hooks", []) or []:
            if command_part in str(hook.get("command", "")):
                return True
    return False


def check_hooks(project: Scope, user: Scope, report: Report) -> None:
    settings = [_load_json(scope.bob_dir / "settings.json", report, scope.label, "hooks") for scope in (project, user)]
    if not any(_has_hook(s, "PreToolUse", "bob-skills guard", "use_skill") for s in settings):
        report.add(project.label, "hooks", WARNING,
                   "the guard hook is not configured, so Bob activates skills without checking them against the lock",
                   "add the PreToolUse hook on use_skill that runs `uvx bob-skills guard` (docs/bob-integration.md)")
    if not any(_has_hook(s, "SessionStart", "bob-skills check") for s in settings):
        report.add(project.label, "hooks", WARNING, "no SessionStart status line: revoked or modified packs go unnoticed until use",
                   "add the SessionStart hook that runs `uvx bob-skills check --brief`")


def check_lock(scope: Scope, report: Report) -> None:
    if not scope.skills_dir.is_dir() and not (scope.bob_dir / "skills.lock").is_file():
        return
    problems, warnings = verify(scope, lint=True)
    for line in problems:
        report.add(scope.label, "lock", PROBLEM, line, "reinstall the pack (`uvx bob-skills add <pack> --force`) or run `uvx bob-skills update`")
    for line in warnings:
        report.add(scope.label, "lock", WARNING, line, "audit it with the skill-audit skill, then install its pack or trust it")


def check_skills(scope: Scope, report: Report) -> None:
    if not scope.skills_dir.is_dir():
        return
    report.checked.append(str(scope.skills_dir))
    for folder in sorted(p for p in scope.skills_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        skill_md = folder / "SKILL.md"
        if not skill_md.is_file():
            report.add(scope.label, "skills", WARNING, f"skill folder '{folder.name}' has no SKILL.md; Bob ignores it", "add SKILL.md or delete the folder")
            continue
        meta, _ = read_frontmatter(skill_md)
        if not meta or not str(meta.get("description", "")).strip():
            report.add(scope.label, "skills", WARNING, f"skill '{folder.name}' has no description; Bob never selects it",
                       "add a description to the frontmatter (the skill-creator skill helps)")
        elif str(meta.get("name", "")).strip() != folder.name:
            report.add(scope.label, "skills", WARNING, f"skill '{folder.name}': frontmatter name '{meta.get('name')}' differs from the folder",
                       "make them equal")


def check_mcp(scope: Scope, report: Report) -> None:
    data = _load_json(scope.mcp_path, report, scope.label, "mcp")
    if data is not None:
        for issue in check_servers(data.get("mcpServers", {}) or {}, strict=False):
            report.add(scope.label, "mcp", issue.severity, f"server '{issue.server}': {issue.code} {issue.message}", issue.fix)
    legacy = scope.bob_dir / "mcp_settings.json"
    if scope.is_global and legacy.is_file():
        report.add(scope.label, "mcp", WARNING, f"{legacy} exists, but Bob reads global MCP servers from {scope.mcp_path}; servers there are ignored",
                   f"move the servers you still need to {scope.mcp_path}, then delete {legacy.name}")


def check_modes(scope: Scope, report: Report) -> None:
    paths = [scope.modes_path]
    if scope.is_global:
        paths.append(scope.bob_dir / "custom_modes.yaml")
    for path in paths:
        if not path.is_file():
            continue
        report.checked.append(str(path))
        if scope.is_global and path != scope.modes_path:
            report.add(scope.label, "modes", WARNING, f"{path} exists, but Bob reads global modes from {scope.modes_path}; modes there are ignored",
                       f"move them to {scope.modes_path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            report.add(scope.label, "modes", PROBLEM, f"{path} is not valid YAML ({error})", "fix the syntax")
            continue
        for mode in data.get("customModes", []) or []:
            if not isinstance(mode, dict):
                continue
            slug = mode.get("slug", "?")
            names, edit_restricted = [], False
            for group in mode.get("groups", []) or []:
                if isinstance(group, list) and group:
                    names.append(str(group[0]))
                    edit_restricted = edit_restricted or (str(group[0]) == "edit" and any(isinstance(g, dict) and g.get("fileRegex") for g in group[1:]))
                else:
                    names.append(str(group))
            unknown = [n for n in names if n not in BOB_GROUPS]
            if unknown:
                report.add(scope.label, "modes", WARNING,
                           f"mode '{slug}' uses group(s) {', '.join(unknown)} that Bob's documentation does not list, and unknown groups grant nothing",
                           f"use the documented names ({', '.join(sorted(BOB_GROUPS))}); for terminal commands that is `execute`")
            if "edit" in names and not edit_restricted and ({"execute", "command"} & set(names)) and "mcp" in names:
                report.add(scope.label, "modes", WARNING,
                           f"mode '{slug}' can edit every file, run commands and call MCP tools",
                           "restrict edit with fileRegex, or drop the groups the mode does not need")


def check_security_rule(project: Scope, user: Scope, report: Report) -> None:
    if not any((scope.rules_dir / "security-defaults.md").is_file() for scope in (project, user)):
        report.add(project.label, "rules", WARNING,
                   "the security-defaults rule is not installed: skills from other vendors may write to external systems without asking first",
                   "install bob-essentials (`uvx bob-skills add bob-essentials`), which adds the rule to .bob/rules")


def run(project: Scope, user: Scope) -> Report:
    report = Report()
    check_hooks(project, user, report)
    check_security_rule(project, user, report)
    for scope in (project, user):
        check_lock(scope, report)
        check_skills(scope, report)
        check_mcp(scope, report)
        check_modes(scope, report)
    return report
