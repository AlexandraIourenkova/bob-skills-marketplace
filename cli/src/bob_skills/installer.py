"""Install, remove, verify and guard packs in a Bob configuration folder.

A *scope* is either the project folder ``./.bob`` or the user folder
``~/.bob``. Installing a pack copies its skills, rules and commands, merges its
MCP servers and custom modes, and records everything in ``skills.lock``.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .hashing import IGNORED_NAMES, DigestError, tree_digest
from .lock import entry_for_skill, get_entry, read_lock, remove_entry, set_entry, write_lock
from .policy import BLOCK, lint_skill, load_baseline
from .registry import Pack, Registry, RegistryError, pack_tag, resolve_registry, semver_key

LOCAL_VENDOR = "local"


class InstallError(Exception):
    """Raised when a pack cannot be installed, removed or verified."""


class TrustRefused(InstallError):
    """The policy linter found blocking problems in a local skill the user wants to trust."""

    def __init__(self, message: str, findings: list) -> None:
        super().__init__(message)
        self.findings = findings


class VendorConfirmationRequired(InstallError):
    """First install from a vendor in this scope: the user must accept the vendor first."""

    def __init__(self, vendor: dict, pack: str):
        self.vendor = vendor
        self.pack = pack
        super().__init__(f"first install from vendor '{vendor.get('id')}' ({vendor.get('displayName', '')}); "
                         f"confirm with `uvx bob-skills add {pack} --accept-vendor`")


@dataclass
class Scope:
    bob_dir: Path
    is_global: bool

    @property
    def skills_dir(self) -> Path:
        return self.bob_dir / "skills"

    @property
    def rules_dir(self) -> Path:
        return self.bob_dir / "rules"

    @property
    def commands_dir(self) -> Path:
        return self.bob_dir / "commands"

    @property
    def mcp_path(self) -> Path:
        return self.bob_dir / "mcp.json"  # Bob: ~/.bob/mcp.json (global) and .bob/mcp.json (project)

    @property
    def modes_path(self) -> Path:
        # Bob reads global modes from ~/.bob/settings/custom_modes.yaml, project modes from .bob/custom_modes.yaml
        return self.bob_dir / ("settings/custom_modes.yaml" if self.is_global else "custom_modes.yaml")

    @property
    def label(self) -> str:
        return "~/.bob" if self.is_global else ".bob"


def project_scope(cwd: Path | None = None) -> Scope:
    return Scope(Path(cwd or Path.cwd()) / ".bob", False)


def global_scope(home: Path | None = None) -> Scope:
    return Scope(Path(home or Path.home()) / ".bob", True)


def parse_spec(spec: str) -> tuple[str, str | None]:
    name, _, version = spec.partition("@")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise InstallError(f"invalid pack name '{name}'")
    return name, (version or None)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORED_NAMES, "*.pyc"), symlinks=False)


# -- yaml helpers ------------------------------------------------------------

class _BlockDumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_BlockDumper.add_representer(str, _str_presenter)


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, Dumper=_BlockDumper, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8") or "{}")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# -- trust checks ------------------------------------------------------------

def check_trust(registry: Registry, pack: Pack) -> list[str]:
    """Everything that must hold before a pack is copied anywhere. Returns notes."""
    vendor = registry.vendors.get(pack.vendor)
    if vendor is None:
        raise InstallError(f"vendor '{pack.vendor}' is not in vendors.json: refusing pack '{pack.name}'")
    if vendor.get("status") == "suspended":
        raise InstallError(f"vendor '{pack.vendor}' is suspended: refusing pack '{pack.name}'")
    if pack.version in pack.manifest.get("revokedVersions", []):
        raise InstallError(f"{pack.name}@{pack.version} was revoked by its vendor; install another version")
    recorded = pack.manifest.get("checksums", {})
    expected = pack.compute_checksums()
    if not recorded:
        raise InstallError(f"{pack.name}@{pack.version} has no checksums in pack.json: refusing")
    bad = [c for c in expected if recorded.get(c) != expected[c]] + [c for c in recorded if c not in expected]
    if bad:
        raise InstallError(f"{pack.name}@{pack.version}: checksum mismatch for {bad}: refusing")
    notes = [f"checksums verified for {len(expected)} components"]
    if vendor.get("publicKey"):
        notes.append("signature: vendor key enrolled, cosign verification not implemented yet (planned)")
    else:
        notes.append("signature: none (vendor has no signing key enrolled yet)")
    return notes


# -- add / remove --------------------------------------------------------------

def trusted_vendors(scopes: list[Scope]) -> set[str]:
    """Vendors with at least one installed pack in any of the scopes."""
    out: set[str] = set()
    for scope in scopes:
        for entry in read_lock(scope.bob_dir).get("pack", []):
            if entry.get("vendor") and entry["vendor"] != LOCAL_VENDOR:
                out.add(entry["vendor"])
    return out


def add(spec: str, scope: Scope, registry_spec: str | None = None, force: bool = False, offline: bool = False,
        accept_vendor: bool = False, known_vendors: set[str] | None = None) -> dict:
    name, version = parse_spec(spec)
    ref = pack_tag(name, version) if version else None
    root, used_spec, commit = resolve_registry(registry_spec, ref=ref, offline=offline)
    registry = Registry(root)
    pack = registry.get(name)
    if version and pack.version != version:
        raise InstallError(f"tag {ref} contains {name}@{pack.version}, not {version}: refusing")
    notes = check_trust(registry, pack)
    known = set(known_vendors) if known_vendors is not None else trusted_vendors([scope])
    if pack.vendor not in known and not accept_vendor:
        raise VendorConfirmationRequired(registry.vendors[pack.vendor], name)

    lock = read_lock(scope.bob_dir)
    existing = get_entry(lock, name) or {}
    report = {"pack": name, "version": pack.version, "vendor": pack.vendor, "scope": scope.label,
              "notes": notes, "safety": pack.manifest.get("safety", []),
              "skills": [], "mcpServers": [], "rules": [], "commands": [], "modes": []}

    # Skills: refuse to overwrite anything this pack does not own.
    for skill in pack.skills:
        dst = scope.skills_dir / skill
        owner = entry_for_skill(lock, skill)
        if dst.exists() and not (owner and owner.get("name") == name) and not force:
            who = f"pack '{owner['name']}'" if owner else "no pack (unmanaged)"
            raise InstallError(f"{dst} already exists and belongs to {who}; remove it or use --force")
    for kind, folder in (("rules", scope.rules_dir), ("commands", scope.commands_dir)):
        for component in pack.manifest.get(kind, []):
            dst = folder / Path(component).name
            owned = Path(component).name in existing.get(kind, [])
            if dst.exists() and not owned and not force:
                raise InstallError(f"{dst} already exists and is not managed by {name}; remove it or use --force")

    skill_digests = {}
    for skill in pack.skills:
        dst = scope.skills_dir / skill
        if dst.exists():
            shutil.rmtree(dst)
        _copy_tree(pack.skill_dir(skill), dst)
        digest = tree_digest(dst)
        if digest != pack.manifest["checksums"].get(f"skills/{skill}"):
            shutil.rmtree(dst)
            raise InstallError(f"digest of installed {skill} does not match the registry checksum")
        skill_digests[skill] = digest
        report["skills"].append(skill)

    for kind, folder in (("rules", scope.rules_dir), ("commands", scope.commands_dir)):
        for component in pack.manifest.get(kind, []):
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pack.path / component, folder / Path(component).name)
            report[kind].append(Path(component).name)

    servers = pack.manifest.get("mcpServers", {})
    if servers:
        mcp = _read_json(scope.mcp_path)
        mcp.setdefault("mcpServers", {})
        for server, config in servers.items():
            current = mcp["mcpServers"].get(server)
            owned = server in existing.get("mcpServers", [])
            if current is not None and current != config and not owned and not force:
                raise InstallError(f"MCP server '{server}' already exists in {scope.mcp_path} with a different config; use --force")
            mcp["mcpServers"][server] = config
            report["mcpServers"].append(server)
        _write_json(scope.mcp_path, mcp)

    if pack.manifest.get("modes"):
        incoming = _read_yaml(pack.path / pack.manifest["modes"]).get("customModes", [])
        current = _read_yaml(scope.modes_path)
        modes = [m for m in current.get("customModes", []) if isinstance(m, dict)]
        for mode in incoming:
            modes = [m for m in modes if m.get("slug") != mode.get("slug")] + [mode]
            report["modes"].append(mode.get("slug"))
        current["customModes"] = modes
        _write_yaml(scope.modes_path, current)

    entry = {
        "name": name, "version": pack.version, "vendor": pack.vendor,
        "digest": tree_digest(pack.path), "installed": _now(),
        "registry": used_spec, "registryCommit": commit,
        "networkAllow": list(pack.manifest.get("networkAllow", [])),
        "skills": report["skills"], "mcpServers": report["mcpServers"],
        "rules": report["rules"], "commands": report["commands"], "modes": report["modes"],
        "policyAccepted": sorted(load_baseline(pack.path)),
        "skillDigests": skill_digests,
    }
    set_entry(lock, entry)
    write_lock(scope.bob_dir, lock)
    report["lock"] = str(scope.bob_dir / "skills.lock")
    return report


def remove(name: str, scope: Scope) -> dict:
    lock = read_lock(scope.bob_dir)
    entry = get_entry(lock, name)
    if entry is None:
        raise InstallError(f"pack '{name}' is not installed in {scope.label}")
    report = {"pack": name, "removed": []}
    for skill in entry.get("skills", []):
        path = scope.skills_dir / skill
        if path.exists():
            shutil.rmtree(path)
            report["removed"].append(f"skills/{skill}")
    for kind, folder in (("rules", scope.rules_dir), ("commands", scope.commands_dir)):
        for item in entry.get(kind, []):
            path = folder / item
            if path.exists():
                path.unlink()
                report["removed"].append(f"{kind}/{item}")
    if entry.get("mcpServers") and scope.mcp_path.is_file():
        mcp = _read_json(scope.mcp_path)
        for server in entry["mcpServers"]:
            if mcp.get("mcpServers", {}).pop(server, None) is not None:
                report["removed"].append(f"mcp:{server}")
        _write_json(scope.mcp_path, mcp)
    if entry.get("modes") and scope.modes_path.is_file():
        current = _read_yaml(scope.modes_path)
        before = len(current.get("customModes", []))
        current["customModes"] = [m for m in current.get("customModes", []) if not (isinstance(m, dict) and m.get("slug") in entry["modes"])]
        if len(current["customModes"]) != before:
            report["removed"].extend(f"mode:{slug}" for slug in entry["modes"])
        _write_yaml(scope.modes_path, current)
    remove_entry(lock, name)
    write_lock(scope.bob_dir, lock)
    return report


def trust(skill: str, scope: Scope, force: bool = False, allow: list[str] | None = None) -> dict:
    """Record a local, unsigned skill in the lock so the guard accepts it.

    The policy linter runs first. A blocking finding refuses the trust unless the
    user read the findings and passed ``force``; the forced findings are recorded
    as accepted so ``verify`` does not repeat them.
    """
    path = scope.skills_dir / skill
    if not (path / "SKILL.md").is_file():
        raise InstallError(f"{path} has no SKILL.md")
    blocking = [f for f in lint_skill(path, list(allow or []), scope.bob_dir.parent) if f.severity == BLOCK]
    if blocking and not force:
        lines = "\n".join(f"  {f.rule} {f.path}:{f.line}: {f.message}" for f in blocking[:12])
        more = f"\n  ... and {len(blocking) - 12} more" if len(blocking) > 12 else ""
        raise TrustRefused(f"refusing to trust '{skill}': {len(blocking)} blocking policy finding(s):\n{lines}{more}\n"
                           f"Audit it (`uvx bob-skills audit {scope.label}/skills/{skill}`), fix the skill, "
                           "or re-run with --force after reading every finding.", blocking)
    try:
        digest = tree_digest(path)
    except DigestError as error:
        raise InstallError(str(error)) from error
    lock = read_lock(scope.bob_dir)
    owner = entry_for_skill(lock, skill)
    if owner and owner.get("vendor") != LOCAL_VENDOR:
        raise InstallError(f"skill '{skill}' belongs to pack '{owner['name']}'; reinstall it with `uvx bob-skills add {owner['name']} --force` instead")
    entry = {
        "name": skill, "version": "0.0.0", "vendor": LOCAL_VENDOR, "digest": digest, "installed": _now(),
        "networkAllow": list(allow or []), "skills": [skill], "mcpServers": [], "rules": [], "commands": [], "modes": [],
        "skillDigests": {skill: digest},
    }
    if blocking:
        entry["policyAccepted"] = sorted({f.fingerprint for f in blocking})
    set_entry(lock, entry)
    write_lock(scope.bob_dir, lock)
    return {"skill": skill, "digest": digest, "lock": str(scope.bob_dir / "skills.lock"), "forced": len(blocking)}


# -- verify / guard ------------------------------------------------------------

def unmanaged_skills(scope: Scope) -> list[str]:
    lock = read_lock(scope.bob_dir)
    managed = {s for e in lock.get("pack", []) for s in e.get("skills", [])}
    if not scope.skills_dir.is_dir():
        return []
    return sorted(p.name for p in scope.skills_dir.iterdir() if p.is_dir() and p.name not in managed and not p.name.startswith("."))


def verify(scope: Scope, lint: bool = True) -> tuple[list[str], list[str]]:
    """Return (problems, warnings) for every installed pack in the scope."""
    problems: list[str] = []
    warnings: list[str] = []
    lock = read_lock(scope.bob_dir)
    for entry in lock.get("pack", []):
        for skill, expected in entry.get("skillDigests", {}).items():
            path = scope.skills_dir / skill
            if not path.is_dir():
                problems.append(f"{entry['name']}: skill '{skill}' is missing from {scope.label}/skills")
                continue
            try:
                actual = tree_digest(path)
            except DigestError as error:
                problems.append(f"{entry['name']}: {error}")
                continue
            if actual != expected:
                problems.append(f"{entry['name']}: skill '{skill}' was modified after install (digest mismatch)")
            if lint:
                accepted = set(entry.get("policyAccepted", []))
                findings = lint_skill(path, list(entry.get("networkAllow", [])), scope.bob_dir.parent)
                for finding in findings:
                    if finding.severity == BLOCK and finding.fingerprint not in accepted:
                        problems.append(f"{entry['name']}/{skill}: {finding.rule} {finding.path}:{finding.line} {finding.message}")
    for skill in unmanaged_skills(scope):
        warnings.append(f"unmanaged skill '{skill}' in {scope.label}/skills; the guard will refuse it (install its pack or `uvx bob-skills trust {skill}`)")
    return problems, warnings


def extract_tool(payload: dict) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or payload.get("toolName") or "")


def extract_skill_name(payload: dict) -> str | None:
    """Best-effort skill name from a PreToolUse payload (both documented shapes)."""
    data = payload.get("tool_input")
    if data is None:
        data = payload.get("input", payload.get("params", payload.get("args")))
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {"skill": data}
    if not isinstance(data, dict):
        return None
    for key in ("skill", "skill_name", "skillName", "name", "id", "path", "skill_path", "skillPath"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return _normalise_skill(value.strip())
    return None


def _normalise_skill(value: str) -> str:
    value = value.replace("\\", "/").rstrip("/")
    if value.endswith("SKILL.md"):
        value = value[: -len("SKILL.md")].rstrip("/")
    if "/" in value:
        parts = value.split("/")
        if "skills" in parts:
            index = len(parts) - 1 - parts[::-1].index("skills")
            if index + 1 < len(parts):
                return parts[index + 1]
        return parts[-1]
    return value


def guard(payload: dict, scopes: list[Scope], allow_local: bool = True, strict: bool = False) -> tuple[int, str]:
    """Decide whether Bob may activate the skill named in ``payload``.

    Returns (exit code, message). 0 allows, 2 refuses.
    """
    tool = extract_tool(payload)
    if tool and "skill" not in tool.lower():
        return 0, ""
    skill = extract_skill_name(payload)
    if not skill:
        if strict:
            return 2, "uvx bob-skills guard: cannot determine the skill name from the hook payload; refusing (strict mode)"
        return 0, "uvx bob-skills guard: no skill name in payload; allowed (use --strict to refuse)"
    for scope in scopes:
        path = scope.skills_dir / skill
        lock = read_lock(scope.bob_dir)
        entry = entry_for_skill(lock, skill)
        if not path.is_dir() and entry is None:
            continue
        if entry is None:
            return 2, (f"uvx bob-skills guard: skill '{skill}' in {scope.label}/skills is unmanaged (not in {scope.label}/skills.lock). "
                       f"Install it from the marketplace (`uvx bob-skills add <pack>`) or, for your own skill, `uvx bob-skills trust {skill}`.")
        if entry.get("vendor") == LOCAL_VENDOR and not allow_local:
            return 2, f"uvx bob-skills guard: skill '{skill}' is a local skill and the organisation policy allows marketplace packs only."
        if not path.is_dir():
            return 2, f"uvx bob-skills guard: skill '{skill}' is in the lock but missing from {scope.label}/skills; reinstall `{entry['name']}`."
        expected = entry.get("skillDigests", {}).get(skill)
        try:
            actual = tree_digest(path)
        except DigestError as error:
            return 2, f"uvx bob-skills guard: {error}"
        if expected != actual:
            return 2, (f"uvx bob-skills guard: skill '{skill}' was modified after install (pack {entry['name']}@{entry.get('version')}). "
                       f"Run `uvx bob-skills verify` to see what changed, or `uvx bob-skills add {entry['name']} --force` to restore it.")
        return 0, ""
    return 2, f"uvx bob-skills guard: skill '{skill}' is not installed in any managed scope."


def brief(scopes: list[Scope]) -> str:
    """One line for the SessionStart hook."""
    parts = []
    for scope in scopes:
        lock = read_lock(scope.bob_dir)
        if not lock.get("pack") and not scope.skills_dir.is_dir():
            continue
        problems, warnings = verify(scope, lint=False)
        packs = ", ".join(f"{e['name']}@{e.get('version')}" for e in lock.get("pack", [])) or "no packs"
        status = "OK" if not problems else f"{len(problems)} problem(s)"
        text = f"{scope.label}: {packs} {status}"
        if warnings:
            text += f", {len(warnings)} unmanaged skill(s): " + ", ".join(unmanaged_skills(scope))
        parts.append(text)
    return "bob-skills: " + ("; ".join(parts) if parts else "no packs installed")


# -- update --------------------------------------------------------------------

def check_updates(scope: Scope, registry_spec: str | None = None, offline: bool = False) -> list[dict]:
    """For every installed marketplace pack, what the registry offers now."""
    lock = read_lock(scope.bob_dir)
    out = []
    for entry in lock.get("pack", []):
        if entry.get("vendor") == LOCAL_VENDOR:
            continue
        spec = registry_spec or entry.get("registry")
        try:
            root, _, _ = resolve_registry(spec, offline=offline)
            pack = Registry(root).get(entry["name"])
        except RegistryError as error:
            out.append({"pack": entry["name"], "installed": entry.get("version"), "error": str(error)})
            continue
        installed = entry.get("version", "0.0.0")
        revoked = installed in pack.manifest.get("revokedVersions", [])
        newer = semver_key(pack.version) > semver_key(installed)
        diffs = {}
        if newer:
            for skill in pack.skills:
                new_md = pack.skill_dir(skill) / "SKILL.md"
                old_md = scope.skills_dir / skill / "SKILL.md"
                old = old_md.read_text(encoding="utf-8").splitlines() if old_md.is_file() else []
                new = new_md.read_text(encoding="utf-8").splitlines() if new_md.is_file() else []
                diff = list(difflib.unified_diff(old, new, f"installed/{skill}/SKILL.md", f"{pack.version}/{skill}/SKILL.md", lineterm=""))
                if diff:
                    diffs[skill] = "\n".join(diff)
        out.append({
            "pack": entry["name"], "installed": installed, "latest": pack.version, "newer": newer,
            "revoked": revoked, "major": semver_key(pack.version)[0] != semver_key(installed)[0],
            "diffs": diffs, "registry": spec,
        })
    return out
