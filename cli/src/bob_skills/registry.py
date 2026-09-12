"""Registry access: vendors.json, packs/<vendor>/<name>/pack.json, index.json.

A registry is a git repository (or a local folder with the same layout). The
installer clones it into ``~/.cache/bob-skills`` and exports a version tag with
``git archive`` when a pinned version is requested.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .hashing import IGNORED_NAMES, path_digest, tree_digest
from .mcpcheck import PROBLEM as MCP_PROBLEM, check_server
from .policy import host_allowed, read_frontmatter

DEFAULT_REGISTRY = "https://github.ibm.com/Maria-Startseva/bob-skills-marketplace.git"
# The find-skills skill carries a generated catalog so Bob can answer offline.
CATALOG_PATH = Path("packs/ibm/bob-essentials/skills/find-skills/references/catalog.md")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$")


class RegistryError(Exception):
    """Raised when a registry is malformed or a pack cannot be trusted."""


def semver_key(version: str) -> tuple[int, int, int, int]:
    match = SEMVER.match(version)
    if not match:
        return (0, 0, 0, 0)
    major, minor, patch, pre = match.groups()
    return (int(major), int(minor), int(patch), 0 if pre else 1)


def pack_tag(name: str, version: str) -> str:
    return f"{name}--v{version}"


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RegistryError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def git_optional(*args: str, cwd: Path | None = None) -> str | None:
    try:
        return git(*args, cwd=cwd)
    except (RegistryError, FileNotFoundError):
        return None


@dataclass
class Pack:
    name: str
    vendor: str
    version: str
    path: Path
    manifest: dict

    @property
    def tag(self) -> str:
        return pack_tag(self.name, self.version)

    @property
    def skills(self) -> list[str]:
        return list(self.manifest.get("skills", []))

    def skill_dir(self, skill: str) -> Path:
        return self.path / "skills" / skill

    def components(self) -> list[str]:
        """Relative paths of everything the pack ships, in checksum order."""
        items = [f"skills/{skill}" for skill in self.skills]
        items += list(self.manifest.get("rules", []))
        items += list(self.manifest.get("commands", []))
        if self.manifest.get("modes"):
            items.append(self.manifest["modes"])
        return items

    def compute_checksums(self) -> dict[str, str]:
        checksums = {}
        for component in self.components():
            target = self.path / component
            if target.exists():
                checksums[component] = path_digest(target)
        return checksums

    def mode_slugs(self) -> list[str]:
        if not self.manifest.get("modes"):
            return []
        path = self.path / self.manifest["modes"]
        if not path.is_file():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return [m.get("slug") for m in data.get("customModes", []) if isinstance(m, dict) and m.get("slug")]

    def skill_descriptions(self) -> list[dict]:
        out = []
        for skill in self.skills:
            meta, _ = read_frontmatter(self.skill_dir(skill) / "SKILL.md") if (self.skill_dir(skill) / "SKILL.md").is_file() else (None, "")
            out.append({"name": skill, "description": (meta or {}).get("description", "") or ""})
        return out


class Registry:
    def __init__(self, root: Path):
        self.root = Path(root)
        vendors_path = self.root / "vendors.json"
        if not vendors_path.is_file():
            raise RegistryError(f"{self.root} is not a registry: vendors.json missing")
        self.vendors_doc = json.loads(vendors_path.read_text(encoding="utf-8"))
        self.vendors: dict[str, dict] = {v["id"]: v for v in self.vendors_doc.get("vendors", [])}

    # -- reading ---------------------------------------------------------

    def packs(self) -> list[Pack]:
        """Packs in vendors.json order (the registry's own vendor first), then by name."""
        order = {v["id"]: i for i, v in enumerate(self.vendors_doc.get("vendors", []))}
        packs = []
        for manifest_path in sorted((self.root / "packs").glob("*/*/pack.json"),
                                    key=lambda m: (order.get(m.parent.parent.name, 999), m.parent.name)):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            packs.append(Pack(
                name=str(manifest.get("name", manifest_path.parent.name)),
                vendor=manifest_path.parent.parent.name,
                version=str(manifest.get("version", "0.0.0")),
                path=manifest_path.parent,
                manifest=manifest,
            ))
        return packs

    def get(self, name: str) -> Pack:
        matches = [p for p in self.packs() if p.name == name]
        if not matches:
            raise RegistryError(f"pack '{name}' is not in the registry")
        if len(matches) > 1:
            raise RegistryError(f"pack '{name}' appears under several vendors: refusing")
        pack = matches[0]
        claimed = pack.manifest.get("vendor")
        if claimed != pack.vendor:
            raise RegistryError(f"pack '{name}' claims vendor '{claimed}' but lives under packs/{pack.vendor}/: refusing")
        if pack.vendor not in self.vendors:
            raise RegistryError(f"vendor '{pack.vendor}' of pack '{name}' is not in vendors.json: refusing")
        return pack

    # -- validation ------------------------------------------------------

    def _schema(self, name: str) -> dict | None:
        path = self.root / "schemas" / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def _schema_problems(self, schema_name: str, instance: dict, label: str) -> list[str]:
        schema = self._schema(schema_name)
        if schema is None:
            return [f"{label}: schema {schema_name} not found in registry (skipped)"]
        try:
            import jsonschema
        except ImportError:  # pragma: no cover
            return []
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        return [f"{label}: {'/'.join(str(p) for p in e.path) or '$'}: {e.message}" for e in validator.iter_errors(instance)]

    def validate(self, fix: bool = False) -> list[str]:
        problems: list[str] = []
        problems += self._schema_problems("vendors.schema.json", self.vendors_doc, "vendors.json")
        problems += self._schema_problems("index.schema.json", self.build_index(), "index.json (as built)")
        codeowners = (self.root / "CODEOWNERS").read_text(encoding="utf-8") if (self.root / "CODEOWNERS").is_file() else ""
        eol = git_optional("ls-files", "--eol", "packs", cwd=self.root) or ""
        crlf = [line.split()[-1] for line in eol.splitlines() if "w/crlf" in line and "i/lf" in line]
        if crlf:
            problems.append(f"line endings: {len(crlf)} file(s) are CRLF in the working copy but LF in git, so checksums would not match a fresh clone: normalise them (first: {crlf[0]})")
        seen: dict[str, str] = {}
        # Files git ignores (IDE and build output next to build files) would be hashed
        # here but never shipped, so a release would fail its own checksums on install.
        ignored = [line.rstrip("/") for line in (git_optional("ls-files", "--others", "--ignored", "--exclude-standard", "--directory",
                                                               "--", "packs", cwd=self.root) or "").splitlines()
                   if line and not any(part in IGNORED_NAMES for part in Path(line.rstrip("/")).parts) and not line.endswith(".pyc")]
        for pack in self.packs():
            label = pack.path.relative_to(self.root).as_posix()
            junk = [j for j in ignored if j.startswith(label + "/")]
            if junk:
                problems.append(f"{label}: files ignored by git would be hashed but never shipped ({', '.join(junk[:3])}"
                                f"{', ...' if len(junk) > 3 else ''}); delete them, they are usually IDE or build output")
            servers = pack.manifest.get("mcpServers", {}) or {}
            access = pack.manifest.get("mcpAccess", {}) or {}
            for server, spec in servers.items():
                for issue in check_server(server, spec, strict=True):
                    if issue.severity == MCP_PROBLEM:
                        problems.append(f"{label}: MCP server '{server}': {issue}")
                if server not in access:
                    problems.append(f"{label}: MCP server '{server}' has no mcpAccess entry; declare read-only, "
                                    "or read-write with the reason and the confirmation that guards each write")
            for server in access:
                if server not in servers:
                    problems.append(f"{label}: mcpAccess names '{server}', which is not in mcpServers")
            problems += self._schema_problems("pack.schema.json", pack.manifest, f"{label}/pack.json")
            if pack.name in seen:
                problems.append(f"{label}: pack name '{pack.name}' already used by {seen[pack.name]}")
            seen[pack.name] = label
            if pack.path.name != pack.name:
                problems.append(f"{label}: folder name must equal pack name '{pack.name}'")
            if pack.manifest.get("vendor") != pack.vendor:
                problems.append(f"{label}: vendor '{pack.manifest.get('vendor')}' does not match folder packs/{pack.vendor}/")
            vendor = self.vendors.get(pack.vendor)
            if vendor is None:
                problems.append(f"{label}: vendor '{pack.vendor}' is not in vendors.json")
            else:
                if vendor.get("status") == "suspended":
                    problems.append(f"{label}: vendor '{pack.vendor}' is suspended")
                for host in pack.manifest.get("networkAllow", []):
                    if host not in vendor.get("networkAllow", []) and not host_allowed(host.lstrip("*."), vendor.get("networkAllow", [])):
                        problems.append(f"{label}: networkAllow host '{host}' is not covered by the vendor allow-list")
                if vendor.get("maintainers") and f"/packs/{pack.vendor}/" not in codeowners:
                    problems.append(f"CODEOWNERS: missing an entry for /packs/{pack.vendor}/")
            if pack.version in pack.manifest.get("revokedVersions", []):
                problems.append(f"{label}: current version {pack.version} is listed in revokedVersions")
            for skill in pack.skills:
                skill_md = pack.skill_dir(skill) / "SKILL.md"
                if not skill_md.is_file():
                    problems.append(f"{label}: skill '{skill}' has no SKILL.md")
                    continue
                meta, _ = read_frontmatter(skill_md)
                if not meta or not str(meta.get("description", "")).strip():
                    problems.append(f"{label}: skill '{skill}' has no description; Bob would ignore it")
                if meta and meta.get("name") != skill:
                    problems.append(f"{label}: skill '{skill}' frontmatter name is '{meta.get('name')}'")
            for component in pack.components():
                if not (pack.path / component).exists():
                    problems.append(f"{label}: component '{component}' is missing")
            if pack.manifest.get("modes") and (pack.path / pack.manifest["modes"]).is_file() and not pack.mode_slugs():
                problems.append(f"{label}: {pack.manifest['modes']} has no customModes with a slug")
            if git_optional("rev-parse", "--verify", "--quiet", f"refs/tags/{pack.tag}", cwd=self.root):
                rel = pack.path.relative_to(self.root).as_posix()
                # Shipped components only: pack.json changes follow content changes, and
                # generated files (the offline catalog) may drift from the tag.
                pathspec = [f"{rel}/{c}" for c in pack.components()] + [f":(exclude){rel}/{g}" for g in pack.manifest.get("generated", [])]
                diff = subprocess.run(["git", "diff", "--quiet", pack.tag, "--", *pathspec], cwd=self.root, capture_output=True)
                if diff.returncode == 1:
                    problems.append(f"{label}: content differs from released tag {pack.tag}; bump version in pack.json")
            expected = pack.compute_checksums()
            recorded = pack.manifest.get("checksums", {})
            if expected != recorded:
                if fix and junk:
                    problems.append(f"{label}: checksums not rewritten while ignored files are present")
                elif fix:
                    pack.manifest["checksums"] = expected
                    (pack.path / "pack.json").write_text(json.dumps(pack.manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                else:
                    changed = sorted(set(expected) ^ set(recorded) | {k for k in expected if recorded.get(k) != expected[k]})
                    problems.append(f"{label}: checksums out of date for {changed}; run `bob-skills registry validate --fix`")
        return problems

    # -- index -----------------------------------------------------------

    def versions_from_tags(self, name: str) -> list[str]:
        out = git_optional("tag", "--list", f"{name}--v*", cwd=self.root)
        if not out:
            return []
        versions = [t.split("--v", 1)[1] for t in out.splitlines() if "--v" in t]
        return sorted(versions, key=semver_key, reverse=True)

    @staticmethod
    def baseline_count(pack_dir: Path) -> int:
        path = Path(pack_dir) / ".policy-baseline.json"
        if not path.is_file():
            return 0
        return len(json.loads(path.read_text(encoding="utf-8")).get("accepted", []))

    def scan_summary(self, pack_dir: Path) -> dict:
        """Gate results for the index: from .scan.json (scripts/run_scanners.py) plus the policy baseline."""
        summary = {"riskScore": None, "policyFindings": self.baseline_count(pack_dir), "verdict": "pending"}
        path = Path(pack_dir) / ".scan.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            s = data.get("summary", {})
            summary.update({
                "riskScore": s.get("riskScore"), "verdict": s.get("verdict", "pending"), "scannedAt": data.get("scannedAt"),
                "skillspectorVersion": data.get("tools", {}).get("skillspector"), "skillspectorSuppressed": s.get("skillspectorSuppressed", 0),
                "ciscoMaxSeverity": s.get("ciscoMaxSeverity"), "ciscoVersion": data.get("tools", {}).get("ciscoSkillScanner"),
            })
        return summary

    def build_index(self, registry_url: str | None = None) -> dict:
        packs = []
        for pack in self.packs():
            vendor = self.vendors.get(pack.vendor, {})
            entry = {
                "name": pack.name,
                "displayName": pack.manifest.get("displayName", pack.name),
                "vendor": pack.vendor,
                "vendorDisplayName": vendor.get("displayName", pack.vendor),
                "vendorStatus": vendor.get("status", "planned"),
                "version": pack.version,
                "description": pack.manifest.get("description", ""),
                "path": pack.path.relative_to(self.root).as_posix(),
                "tag": pack.tag,
                "skills": pack.skill_descriptions(),
                "mcpServers": sorted(pack.manifest.get("mcpServers", {}).keys()),
                "rules": [Path(r).name for r in pack.manifest.get("rules", [])],
                "commands": [Path(c).name for c in pack.manifest.get("commands", [])],
                "modes": pack.mode_slugs(),
                "digest": tree_digest(pack.path),
                "revokedVersions": list(pack.manifest.get("revokedVersions", [])),
                "versions": self.versions_from_tags(pack.name) or [pack.version],
                "baselineFindings": self.baseline_count(pack.path),
                "components": len(pack.manifest.get("checksums", {})),
                "readme": pack.path.relative_to(self.root).as_posix() + "/README.md" if (pack.path / "README.md").is_file() else "",
                "scan": self.scan_summary(pack.path),
            }
            for key in ("license", "homepage", "minBob", "tags", "source", "sources", "safety"):
                if key in pack.manifest:
                    entry[key] = pack.manifest[key]
            for skill_entry in entry["skills"]:
                skill_entry["digest"] = pack.manifest.get("checksums", {}).get(f"skills/{skill_entry['name']}", "")
            packs.append(entry)
        return {
            "$schema": "./schemas/index.schema.json",
            "schemaVersion": 1,
            "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "registry": {
                "url": registry_url or git_optional("remote", "get-url", "origin", cwd=self.root) or "",
                "commit": git_optional("rev-parse", "HEAD", cwd=self.root) or "",
            },
            "vendors": [{
                "id": v["id"], "displayName": v.get("displayName", v["id"]), "status": v.get("status", "planned"),
                "homepage": v.get("homepage", ""), "github": v.get("github", {}), "extraSources": v.get("extraSources", []),
                "notes": v.get("notes", ""), "packs": [p["name"] for p in packs if p["vendor"] == v["id"]],
            } for v in self.vendors_doc.get("vendors", [])],
            "packs": packs,
            "planned": self.planned(),
        }

    def planned(self) -> list[dict]:
        """Planned packs from roadmap.json, with their vendor names."""
        path = self.root / "roadmap.json"
        if not path.is_file():
            return []
        out = []
        for entry in json.loads(path.read_text(encoding="utf-8")).get("planned", []):
            vendor = self.vendors.get(entry.get("vendor"), {})
            out.append({
                "name": entry["name"], "displayName": entry.get("displayName", entry["name"]), "vendor": entry.get("vendor", ""),
                "vendorDisplayName": vendor.get("displayName", entry.get("vendorDisplayName", entry.get("vendor", ""))),
                "status": entry.get("status", "candidate"), "description": entry.get("description", ""),
                "source": entry.get("source", ""), "blockedBy": entry.get("blockedBy", ""), "issue": entry.get("issue", ""),
                "votes": int(entry.get("votes", 0) or 0),
            })
        return out

    # -- catalog for the find-skills skill -----------------------------------

    @staticmethod
    def build_catalog(index: dict) -> str:
        """Deterministic markdown catalog: what Bob reads when there is no network."""
        out = ["# Marketplace catalog", "",
               "Generated by `bob-skills registry build-index` from index.json. Do not edit by hand.",
               "Install: `uvx bob-skills add <pack>`; details: `uvx bob-skills show <pack>`; map a git link: `uvx bob-skills resolve <url>`.", ""]
        out += ["## Vendors", ""]
        for v in index.get("vendors", []):
            gh = v.get("github", {})
            sources = [f"{gh.get('host', 'github.com')}/{gh.get('org', '')}"] + list(v.get("extraSources", []))
            out.append(f"- **{v['displayName']}** (`{v['id']}`, {v['status']}): sources {', '.join(sources)}. Packs: {', '.join(v['packs']) or 'none yet'}.")
        out += ["", "## Packs", ""]
        for pack in index["packs"]:
            out.append(f"### {pack['name']} — {pack['displayName']}")
            out.append("")
            out.append(f"- Vendor: {pack['vendorDisplayName']} (`{pack['vendor']}`, {pack['vendorStatus']}). Version {pack['version']}.")
            out.append(f"- {pack['description']}")
            if pack.get("source"):
                src = pack["source"]
                out.append(f"- Source: {src.get('repo', '')} @ {src.get('ref', '')}" + (f" ({src['path']})" if src.get("path") else ""))
            if pack.get("homepage"):
                out.append(f"- Homepage: {pack['homepage']}")
            out.append(f"- Tags: {', '.join(pack.get('tags', [])) or '-'}")
            out.append(f"- Skills ({len(pack['skills'])}):")
            for skill in pack["skills"]:
                out.append(f"  - `{skill['name']}`: {skill['description']}")
            extras = []
            if pack.get("mcpServers"):
                extras.append("MCP servers: " + ", ".join(pack["mcpServers"]))
            if pack.get("rules"):
                extras.append("rules: " + ", ".join(pack["rules"]))
            if pack.get("commands"):
                extras.append("commands: " + ", ".join("/" + c.removesuffix(".md") for c in pack["commands"]))
            if pack.get("modes"):
                extras.append("modes: " + ", ".join(pack["modes"]))
            if extras:
                out.append("- Also installs: " + "; ".join(extras) + ".")
            for note in pack.get("safety", []):
                out.append(f"- Before you install: {note['warning']} Covered by: {note['covered']}")
            scan = pack.get("scan", {})
            risk = f", SkillSpector risk {scan['riskScore']}/100" if scan.get("riskScore") is not None else ""
            cisco = f", Cisco max severity {scan['ciscoMaxSeverity']}" if scan.get("ciscoMaxSeverity") else ""
            out.append(f"- Gate: {scan.get('verdict', 'pending')}{risk}{cisco}; {pack.get('baselineFindings', 0)} reviewed policy findings; {pack.get('components', 0)} checksummed components.")
            out.append(f"- Install: `uvx bob-skills add {pack['name']}`")
            out.append("")
        if index.get("planned"):
            out += ["## Planned packs (not installable yet)", ""]
            for item in index["planned"]:
                label = "coming soon" if item["status"] == "coming-soon" else "candidate"
                line = f"- **{item['displayName']}** (`{item['name']}`, {item['vendorDisplayName']}, {label}): {item['description']}"
                if item.get("source"):
                    line += f" Source: {item['source']}."
                if item.get("blockedBy"):
                    line += f" Blocked by: {item['blockedBy']}."
                if item.get("issue"):
                    line += f" Vote or subscribe: {item['issue']} ({item.get('votes', 0)} votes)."
                out.append(line)
            out.append("")
        return "\n".join(out).rstrip() + "\n"

    def build_marketplace_manifest(self, index: dict) -> dict:
        """Compatibility manifest in the marketplace.json shape used by other agents."""
        return {
            "name": "bob-skills-marketplace",
            "owner": {"name": "IBM Bob Skills Marketplace team", "url": "https://github.ibm.com/Maria-Startseva/bob-skills-marketplace"},
            "metadata": {
                "description": "Vendor-signed skill packs for IBM Bob. Install with `uvx bob-skills add <pack>`; other agents may read this manifest to discover packs.",
                "version": "1.0.0",
            },
            "plugins": [{
                "name": p["name"],
                "source": "./" + p["path"],
                "description": p["description"],
                "version": p["version"],
                "author": {"name": p["vendorDisplayName"]},
                **({"homepage": p["homepage"]} if p.get("homepage") else {}),
                **({"license": p["license"]} if p.get("license") else {}),
                "keywords": p.get("tags", []),
                "category": "ibm-bob",
            } for p in index["packs"]],
        }

    @staticmethod
    def _stable(doc: dict, soft: bool = False) -> dict:
        """Index without the fields that change on their own.

        ``generated`` and the registry commit always differ between builds. Pack
        ``versions`` come from release tags, which are created after the commit
        that carries the index, so ``--check`` ignores them too (soft=False);
        a plain build still rewrites the file when they change (soft=True).
        """
        copy = json.loads(json.dumps(doc))
        copy.pop("generated", None)
        copy.get("registry", {}).pop("commit", None)
        if not soft:
            for pack in copy.get("packs", []):
                pack.pop("versions", None)
        return copy

    def write_index(self, check: bool = False) -> bool:
        """Write index.json and marketplace.json. Returns True when they changed."""
        index = self.build_index()
        index_path = self.root / "index.json"
        current = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
        marketplace = self.build_marketplace_manifest(index)
        market_path = self.root / "marketplace.json"
        current_market = json.loads(market_path.read_text(encoding="utf-8")) if market_path.is_file() else {}
        catalog = self.build_catalog(index)
        catalog_path = self.root / CATALOG_PATH
        current_catalog = catalog_path.read_text(encoding="utf-8") if catalog_path.is_file() else ""
        catalog_changed = catalog_path.parent.is_dir() and current_catalog != catalog
        refreshed = False
        if not check:
            # The catalog lives inside a pack: write it when it changed, keep that
            # pack's checksums in sync, then rebuild so the index carries the digests.
            if catalog_changed:
                catalog_path.write_text(catalog, encoding="utf-8")
            for pack in self.packs():
                if catalog_path.parent.is_dir() and catalog_path.is_relative_to(pack.path):
                    fresh = pack.compute_checksums()
                    if fresh != pack.manifest.get("checksums"):
                        pack.manifest["checksums"] = fresh
                        (pack.path / "pack.json").write_text(json.dumps(pack.manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                        refreshed = True
            if catalog_changed or refreshed:
                index = self.build_index()
                marketplace = self.build_marketplace_manifest(index)
        stable_changed = self._stable(current) != self._stable(index) or current_market != marketplace or catalog_changed or refreshed
        full_changed = stable_changed or self._stable(current, soft=True) != self._stable(index, soft=True)
        if check:
            return stable_changed
        if full_changed:
            index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            market_path.write_text(json.dumps(marketplace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return full_changed


# -- resolving a registry spec to a local checkout ---------------------------

def cache_dir() -> Path:
    return Path(os.environ.get("BOB_SKILLS_CACHE") or Path.home() / ".cache" / "bob-skills").expanduser()


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40] + "-" + hashlib.sha1(text.encode()).hexdigest()[:8]


def resolve_registry(spec: str | None, ref: str | None = None, offline: bool = False) -> tuple[Path, str, str]:
    """Return (checkout root, registry spec used, commit) for a registry spec.

    ``spec`` is a local folder or a git URL. With ``ref`` (a version tag) the
    tagged tree is exported into the cache so the working copy stays on HEAD.
    """
    spec = spec or os.environ.get("BOB_SKILLS_REGISTRY") or DEFAULT_REGISTRY
    local = Path(spec).expanduser()
    if local.is_dir():
        root = local.resolve()
    else:
        root = cache_dir() / "registries" / _slug(spec)
        if (root / ".git").is_dir():
            if not offline:
                git("fetch", "--quiet", "--tags", "--force", "origin", cwd=root)
                git("reset", "--quiet", "--hard", "origin/HEAD", cwd=root)
        else:
            if offline:
                raise RegistryError(f"no cached copy of {spec}; drop --offline to clone it")
            root.parent.mkdir(parents=True, exist_ok=True)
            git("clone", "--quiet", spec, str(root))
    if not (root / "vendors.json").is_file():
        raise RegistryError(f"{spec} is not a registry: vendors.json missing")
    commit = git_optional("rev-parse", "HEAD", cwd=root) or ""
    if ref:
        commit = git_optional("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=root) or ""
        if not commit:
            raise RegistryError(f"version tag '{ref}' does not exist in {spec}")
        export = cache_dir() / "refs" / _slug(str(root)) / re.sub(r"[^A-Za-z0-9._-]+", "_", ref)
        if export.exists():
            shutil.rmtree(export)
        export.mkdir(parents=True)
        archive = subprocess.run(["git", "archive", "--format=tar", ref], cwd=root, capture_output=True)
        if archive.returncode != 0:
            raise RegistryError(f"git archive {ref} failed: {archive.stderr.decode(errors='replace').strip()}")
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            try:
                tar.extractall(export, filter="data")
            except TypeError:  # Python < 3.12
                tar.extractall(export)
        root = export
    return root, spec, commit


# -- resolving a git link or a name to packs ------------------------------------

def normalise_repo(text: str) -> tuple[str, str, str] | None:
    """Return (host, org, repo) for a git URL, ``host/org/repo`` or ``org/repo``; None if not repo-like."""
    text = text.strip().rstrip("/")
    match = re.match(r"^(?:git@|ssh://git@)([^:/]+)[:/](.+)$", text)
    if match:
        host, path = match.group(1), match.group(2)
    else:
        match = re.match(r"^(?:https?://)?([A-Za-z0-9.-]+\.[a-z]{2,})/(.+)$", text)
        if match:
            host, path = match.group(1), match.group(2)
        elif re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", text):
            host, path = "github.com", text
        else:
            return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    org = parts[0]
    repo = parts[1].removesuffix(".git") if len(parts) > 1 else ""
    return host.lower(), org.lower(), repo.lower()


def resolve_reference(index: dict, reference: str) -> dict:
    """Map a pasted git link (or a pack/skill name) to registry packs and vendors."""
    packs = index.get("packs", [])
    target = normalise_repo(reference)
    if target is None:
        name = reference.strip().lower()
        hits = [p for p in packs if p["name"] == name or any(s["name"] == name for s in p["skills"])]
        return {"input": reference, "kind": "name", "packs": hits, "vendors": []}
    host, org, repo = target

    def same_repo(url: str) -> bool:
        other = normalise_repo(url or "")
        return bool(other) and other[0] == host and other[1] == org and (other[2] == repo or not repo)

    hits = [p for p in packs if same_repo(p.get("source", {}).get("repo", "")) or same_repo(p.get("homepage", ""))
            or any(same_repo(s.get("repo", "")) for s in p.get("sources", {}).values())]
    vendors = []
    for v in index.get("vendors", []):
        gh = v.get("github", {})
        if gh.get("host", "github.com").lower() == host and gh.get("org", "").lower() == org:
            vendors.append(v)
            continue
        for src in v.get("extraSources", []):
            other = normalise_repo(src)
            if other and other[0] == host and other[1] == org and (not other[2] or other[2] == repo):
                vendors.append(v)
                break
    return {"input": reference, "kind": "repo", "host": host, "org": org, "repo": repo, "packs": hits, "vendors": vendors}


def describe_pack(registry: "Registry", pack: Pack, index_entry: dict) -> dict:
    """Everything the 'what will be installed' panel needs."""
    vendor = registry.vendors.get(pack.vendor, {})
    always_on = 0
    for skill in pack.skills:
        meta, _ = read_frontmatter(pack.skill_dir(skill) / "SKILL.md") if (pack.skill_dir(skill) / "SKILL.md").is_file() else (None, "")
        always_on += len(str((meta or {}).get("description", "")))
    for rule in pack.manifest.get("rules", []):
        if (pack.path / rule).is_file():
            always_on += len((pack.path / rule).read_text(encoding="utf-8", errors="replace"))
    on_use = 0
    for skill in pack.skills:
        for file in pack.skill_dir(skill).rglob("*.md"):
            on_use += file.stat().st_size
    return {
        "name": pack.name, "displayName": pack.manifest.get("displayName", pack.name), "version": pack.version,
        "description": pack.manifest.get("description", ""), "tag": pack.tag,
        "vendor": {"id": pack.vendor, "displayName": vendor.get("displayName", pack.vendor), "status": vendor.get("status", "unknown"),
                   "homepage": vendor.get("homepage", ""), "github": vendor.get("github", {}), "signingKey": bool(vendor.get("publicKey"))},
        "source": pack.manifest.get("source"), "sources": pack.manifest.get("sources", {}), "minBob": pack.manifest.get("minBob"),
        "skills": index_entry.get("skills", []),
        "mcpServers": {name: cfg for name, cfg in pack.manifest.get("mcpServers", {}).items()},
        "mcpAccess": pack.manifest.get("mcpAccess", {}),
        "safety": pack.manifest.get("safety", []),
        "rules": [Path(r).name for r in pack.manifest.get("rules", [])],
        "commands": ["/" + Path(c).stem for c in pack.manifest.get("commands", [])],
        "modes": pack.mode_slugs(),
        "networkAllow": pack.manifest.get("networkAllow", []),
        "gate": {"verdict": index_entry.get("scan", {}).get("verdict", "pending"), "baselineFindings": index_entry.get("baselineFindings", 0),
                 "riskScore": index_entry.get("scan", {}).get("riskScore"), "ciscoMaxSeverity": index_entry.get("scan", {}).get("ciscoMaxSeverity"),
                 "scannedAt": index_entry.get("scan", {}).get("scannedAt"),
                 "components": len(pack.manifest.get("checksums", {})), "revoked": pack.version in pack.manifest.get("revokedVersions", [])},
        "contextTokens": {"alwaysOn": always_on // 4, "onUse": on_use // 4},
    }
