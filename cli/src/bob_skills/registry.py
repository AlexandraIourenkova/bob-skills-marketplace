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

from .hashing import path_digest, tree_digest
from .policy import host_allowed, read_frontmatter

DEFAULT_REGISTRY = "https://github.ibm.com/Maria-Startseva/bob-skills-marketplace.git"
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
        packs = []
        for manifest_path in sorted((self.root / "packs").glob("*/*/pack.json")):
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
        codeowners = (self.root / "CODEOWNERS").read_text(encoding="utf-8") if (self.root / "CODEOWNERS").is_file() else ""
        seen: dict[str, str] = {}
        for pack in self.packs():
            label = pack.path.relative_to(self.root).as_posix()
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
            expected = pack.compute_checksums()
            recorded = pack.manifest.get("checksums", {})
            if expected != recorded:
                if fix:
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
                "scan": {"riskScore": None, "policyFindings": 0, "verdict": "pending"},
            }
            for key in ("license", "homepage", "minBob", "tags"):
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
            "packs": packs,
        }

    def build_marketplace_manifest(self, index: dict) -> dict:
        """Compatibility manifest in the marketplace.json shape used by other agents."""
        return {
            "name": "bob-skills-marketplace",
            "owner": {"name": "Bob Skills Marketplace team", "url": "https://github.ibm.com/Maria-Startseva/bob-skills-marketplace"},
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
    def _stable(doc: dict) -> dict:
        copy = json.loads(json.dumps(doc))
        copy.pop("generated", None)
        copy.get("registry", {}).pop("commit", None)
        return copy

    def write_index(self, check: bool = False) -> bool:
        """Write index.json and marketplace.json. Returns True when they changed."""
        index = self.build_index()
        index_path = self.root / "index.json"
        current = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
        marketplace = self.build_marketplace_manifest(index)
        market_path = self.root / "marketplace.json"
        current_market = json.loads(market_path.read_text(encoding="utf-8")) if market_path.is_file() else {}
        changed = self._stable(current) != self._stable(index) or current_market != marketplace
        if changed and not check:
            index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            market_path.write_text(json.dumps(marketplace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return changed


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
