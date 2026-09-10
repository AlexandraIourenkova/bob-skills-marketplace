"""Command-line entry point: ``bob-skills``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from . import installer
from .installer import InstallError, Scope, VendorConfirmationRequired, global_scope, project_scope
from .policy import BLOCK, format_text, lint_path, to_sarif, write_baseline
from .registry import Registry, RegistryError, describe_pack, resolve_reference, resolve_registry

app = typer.Typer(
    help="Install, verify and guard skill packs for IBM Bob from the Bob Skills Marketplace.",
    no_args_is_help=True, add_completion=False, rich_markup_mode=None,
)
registry_app = typer.Typer(help="Registry maintenance. Run from a registry checkout.", no_args_is_help=True)
app.add_typer(registry_app, name="registry")

RegistryOpt = typer.Option(None, "--registry", "-r", envvar="BOB_SKILLS_REGISTRY",
                           help="Registry: local folder or git URL. Default: the marketplace repository.")
GlobalOpt = typer.Option(False, "--global", "-g", help="Use ~/.bob instead of ./.bob.")
OfflineOpt = typer.Option(False, "--offline", help="Use the cached registry without fetching.")
JsonOpt = typer.Option(False, "--json", help="Machine-readable output.")


def _scope(is_global: bool) -> Scope:
    return global_scope() if is_global else project_scope()


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bob-skills {__version__}")
        raise typer.Exit()


@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show the version.")) -> None:
    """Bob Skills Marketplace client."""


# -- search / list -------------------------------------------------------------

@app.command()
def search(query: list[str] = typer.Argument(None, help="Keywords; empty lists every pack."),
           registry: Optional[str] = RegistryOpt, offline: bool = OfflineOpt, json_out: bool = JsonOpt) -> None:
    """Search packs by name, description, tags, vendor and skill names."""
    try:
        root, _, _ = resolve_registry(registry, offline=offline)
        index = Registry(root).build_index()
    except RegistryError as error:
        _fail(str(error))
    terms = [t.lower() for t in (query or [])]

    def haystack(pack: dict) -> str:
        return " ".join([pack["name"], pack["displayName"], pack["description"], pack["vendor"], pack["vendorDisplayName"],
                         " ".join(pack.get("tags", [])), " ".join(s["name"] + " " + s["description"] for s in pack["skills"])]).lower()

    hits = [p for p in index["packs"] if all(t in haystack(p) for t in terms)]
    if json_out:
        typer.echo(json.dumps(hits, indent=2, ensure_ascii=False))
        return
    if not hits:
        typer.echo("no packs match; request one with the 'Request a pack' issue template in the marketplace repository")
        raise typer.Exit(code=1)
    for pack in hits:
        verdict = pack.get("scan", {}).get("verdict", "pending")
        risk = pack.get("scan", {}).get("riskScore")
        typer.echo(f"{pack['name']}@{pack['version']}  vendor={pack['vendor']} ({pack['vendorStatus']})  gate={verdict}{'' if risk is None else f' risk={risk}'}")
        typer.echo(f"    {pack['description']}")
        typer.echo(f"    skills: {', '.join(s['name'] for s in pack['skills'])}"
                   + (f"  mcp: {', '.join(pack['mcpServers'])}" if pack.get("mcpServers") else "")
                   + (f"  modes: {', '.join(pack['modes'])}" if pack.get("modes") else ""))


@app.command()
def resolve(reference: str = typer.Argument(..., help="A git URL, owner/repo, pack name or skill name."),
            registry: Optional[str] = RegistryOpt, offline: bool = OfflineOpt, json_out: bool = JsonOpt) -> None:
    """Map a pasted git link (or a name) to registry packs. Exit 1 when nothing matches."""
    try:
        root, _, _ = resolve_registry(registry, offline=offline)
        index = Registry(root).build_index()
    except RegistryError as error:
        _fail(str(error))
    result = resolve_reference(index, reference)
    if json_out:
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if result["packs"] else 1)
    if result["packs"]:
        for pack in result["packs"]:
            typer.echo(f"{pack['name']}@{pack['version']}  vendor={pack['vendor']} ({pack['vendorStatus']})  {pack['displayName']}")
            typer.echo(f"    this pack is curated from {reference}; install it with `uvx bob-skills add {pack['name']}`")
        return
    if result["kind"] == "repo" and result["vendors"]:
        for vendor in result["vendors"]:
            typer.echo(f"{reference} belongs to vendor {vendor['displayName']} ({vendor['id']}, {vendor['status']}) but no pack is curated from it yet.")
            typer.echo(f"    packs from this vendor: {', '.join(vendor['packs']) or 'none'}; request one with the 'Request a pack' issue template")
        raise typer.Exit(code=1)
    typer.echo(f"{reference} is not in the marketplace and its owner is not a listed vendor. Do not copy skills from it; request a pack or, for your own skill, `bob-skills trust <skill>`.")
    raise typer.Exit(code=1)


@app.command()
def show(pack: str, registry: Optional[str] = RegistryOpt, offline: bool = OfflineOpt,
         is_global: bool = GlobalOpt, json_out: bool = JsonOpt) -> None:
    """What will be installed: skills, MCP servers, rules, commands, modes, gate status, context cost, vendor trust."""
    try:
        root, _, _ = resolve_registry(registry, offline=offline)
        reg = Registry(root)
        target = reg.get(pack)
        entry = next((p for p in reg.build_index()["packs"] if p["name"] == pack), {})
    except RegistryError as error:
        _fail(str(error), code=2)
    info = describe_pack(reg, target, entry)
    info["vendorTrusted"] = target.vendor in installer.trusted_vendors([project_scope(), global_scope()])
    if json_out:
        typer.echo(json.dumps(info, indent=2, ensure_ascii=False))
        return
    v = info["vendor"]
    typer.echo(f"{info['displayName']}  ({info['name']}@{info['version']}, tag {info['tag']})")
    typer.echo(f"  {info['description']}")
    typer.echo(f"  vendor: {v['displayName']} ({v['id']}, {v['status']}){'' if info['vendorTrusted'] else '  NOT YET TRUSTED in this project: first install needs --accept-vendor'}")
    if info.get("source"):
        typer.echo(f"  source: {info['source'].get('repo')} @ {info['source'].get('ref')}")
    typer.echo(f"  skills ({len(info['skills'])}):")
    for skill in info["skills"]:
        typer.echo(f"    - {skill['name']}: {skill['description'][:160]}{'...' if len(skill['description']) > 160 else ''}")
    for name, cfg in info["mcpServers"].items():
        how = cfg.get("url") or " ".join([cfg.get("command", "")] + list(cfg.get("args", [])))
        typer.echo(f"  mcp server {name}: {how}")
    for kind in ("rules", "commands", "modes"):
        if info[kind]:
            typer.echo(f"  {kind}: {', '.join(info[kind])}")
    g = info["gate"]
    typer.echo(f"  gate: {g['verdict']}; {g['baselineFindings']} reviewed findings in the baseline; {g['components']} checksummed components"
               + ("; REVOKED" if g["revoked"] else ""))
    typer.echo(f"  network allowed in scripts: {', '.join(info['networkAllow']) or '-'}")
    c = info["contextTokens"]
    typer.echo(f"  context cost: ~{c['alwaysOn']} tokens always on (skill descriptions + rules), ~{c['onUse']} tokens when a skill is used")
    typer.echo(f"  install: uvx bob-skills add {info['name']}" + ("" if info["vendorTrusted"] else " --accept-vendor"))


@app.command("list")
def list_(is_global: bool = GlobalOpt, json_out: bool = JsonOpt) -> None:
    """Show installed packs and their versions."""
    scope = _scope(is_global)
    lock = installer.read_lock(scope.bob_dir)
    if json_out:
        typer.echo(json.dumps(lock, indent=2, ensure_ascii=False))
        return
    if not lock.get("pack"):
        typer.echo(f"no packs installed in {scope.label}")
        return
    for entry in sorted(lock["pack"], key=lambda e: e["name"]):
        typer.echo(f"{entry['name']}@{entry.get('version')}  vendor={entry.get('vendor')}  installed={entry.get('installed', '?')}")
        typer.echo(f"    skills: {', '.join(entry.get('skills', [])) or '-'}"
                   + (f"  mcp: {', '.join(entry['mcpServers'])}" if entry.get("mcpServers") else ""))
    unmanaged = installer.unmanaged_skills(scope)
    if unmanaged:
        typer.echo(f"unmanaged (guard refuses them): {', '.join(unmanaged)}")


# -- add / remove / update -----------------------------------------------------

def _print_report(report: dict) -> None:
    typer.echo(f"installed {report['pack']}@{report['version']} from vendor {report['vendor']} into {report['scope']}")
    for note in report.get("notes", []):
        typer.echo(f"  {note}")
    for kind in ("skills", "mcpServers", "rules", "commands", "modes"):
        if report.get(kind):
            typer.echo(f"  {kind}: {', '.join(report[kind])}")
    typer.echo(f"  lock: {report['lock']}")


@app.command()
def add(pack: str = typer.Argument(..., help="<name> or <name>@<version>"),
        registry: Optional[str] = RegistryOpt, is_global: bool = GlobalOpt,
        force: bool = typer.Option(False, "--force", help="Overwrite files this pack does not own."),
        accept_vendor: bool = typer.Option(False, "--accept-vendor", help="Accept the vendor on its first install in this scope."),
        offline: bool = OfflineOpt) -> None:
    """Install a pack: verify vendor and checksums, copy skills, merge MCP servers, rules, commands and modes, write the lock."""
    known = installer.trusted_vendors([project_scope(), global_scope()])
    try:
        _print_report(installer.add(pack, _scope(is_global), registry, force=force, offline=offline,
                                    accept_vendor=accept_vendor, known_vendors=known))
    except VendorConfirmationRequired as error:
        v = error.vendor
        typer.echo(f"first install from vendor {v.get('displayName')} ({v.get('id')}, {v.get('status')}) in this scope.", err=True)
        typer.echo(f"  homepage: {v.get('homepage', '-')}; organisation: {v.get('github', {}).get('host', '')}/{v.get('github', {}).get('org', '')}; "
                   f"signing key: {'enrolled' if v.get('publicKey') else 'none yet'}", err=True)
        typer.echo(f"  {v.get('notes', '')}", err=True)
        typer.echo(f"  if you trust this vendor: uvx bob-skills add {pack} --accept-vendor", err=True)
        raise typer.Exit(code=3)
    except (InstallError, RegistryError) as error:
        _fail(str(error), code=2)


@app.command()
def remove(pack: str, is_global: bool = GlobalOpt) -> None:
    """Remove a pack and everything it installed, including its MCP servers."""
    try:
        report = installer.remove(pack, _scope(is_global))
    except InstallError as error:
        _fail(str(error), code=2)
    typer.echo(f"removed {report['pack']}: " + (", ".join(report["removed"]) or "nothing on disk"))


@app.command()
def update(registry: Optional[str] = RegistryOpt, is_global: bool = GlobalOpt,
           apply: bool = typer.Option(False, "--apply", help="Install the newer versions."),
           yes: bool = typer.Option(False, "--yes", "-y", help="Accept major version updates."),
           offline: bool = OfflineOpt) -> None:
    """Compare the lock with the registry, show SKILL.md diffs, and install updates with --apply."""
    scope = _scope(is_global)
    results = installer.check_updates(scope, registry, offline=offline)
    if not results:
        typer.echo("no marketplace packs installed")
        return
    pending = []
    for item in results:
        if item.get("error"):
            typer.echo(f"{item['pack']}@{item['installed']}: {item['error']}")
            continue
        if item["revoked"]:
            typer.echo(f"{item['pack']}@{item['installed']}: REVOKED by the vendor; latest is {item['latest']}")
        if not item["newer"]:
            typer.echo(f"{item['pack']}@{item['installed']}: up to date")
            continue
        kind = "major" if item["major"] else "minor"
        typer.echo(f"{item['pack']}@{item['installed']} -> {item['latest']} ({kind} update)")
        for skill, diff in item["diffs"].items():
            typer.echo(diff)
        pending.append(item)
    if not apply:
        if pending:
            typer.echo("run with --apply to install (add --yes for major updates)")
        return
    for item in pending:
        if item["major"] and not yes:
            typer.echo(f"skipping {item['pack']}: major update needs --yes")
            continue
        try:
            _print_report(installer.add(item["pack"], scope, item.get("registry") or registry, force=True, offline=offline, accept_vendor=True))
        except (InstallError, RegistryError) as error:
            _fail(str(error), code=2)


# -- verify / trust / guard / check --------------------------------------------

@app.command()
def verify(is_global: bool = GlobalOpt,
           no_lint: bool = typer.Option(False, "--no-lint", help="Only compare digests, skip the policy linter.")) -> None:
    """Recompute digests of installed skills against the lock and run the policy linter on them."""
    scope = _scope(is_global)
    problems, warnings = installer.verify(scope, lint=not no_lint)
    for warning in warnings:
        typer.echo(f"warning: {warning}")
    for problem in problems:
        typer.echo(f"problem: {problem}")
    if problems:
        raise typer.Exit(code=1)
    typer.echo(f"{scope.label}: all managed skills match the lock")


@app.command()
def trust(skill: str, is_global: bool = GlobalOpt) -> None:
    """Record a local, unsigned skill in the lock so the guard accepts it as it is now."""
    try:
        report = installer.trust(skill, _scope(is_global))
    except InstallError as error:
        _fail(str(error), code=2)
    typer.echo(f"trusted local skill {report['skill']} ({report['digest'][:19]}...) in {report['lock']}")


@app.command()
def guard(strict: bool = typer.Option(False, "--strict", help="Refuse when the payload has no skill name."),
          no_local: bool = typer.Option(False, "--no-local", help="Refuse skills trusted locally; marketplace packs only.")) -> None:
    """PreToolUse hook for use_skill: read the hook JSON from stdin, exit 2 to block."""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    code, message = installer.guard(payload, [project_scope(), global_scope()], allow_local=not no_local, strict=strict)
    if message:
        typer.echo(message, err=True)
    if code:
        typer.echo(json.dumps({"decision": "block", "reason": message}))
    raise typer.Exit(code=code)


@app.command()
def check(brief: bool = typer.Option(False, "--brief", help="One line, for the SessionStart hook.")) -> None:
    """Status of the project and user scopes. Never fails; meant for SessionStart."""
    scopes = [project_scope(), global_scope()]
    if brief:
        typer.echo(installer.brief(scopes))
        return
    for scope in scopes:
        problems, warnings = installer.verify(scope, lint=False)
        lock = installer.read_lock(scope.bob_dir)
        typer.echo(f"{scope.label}: {len(lock.get('pack', []))} pack(s)")
        for line in warnings:
            typer.echo(f"  warning: {line}")
        for line in problems:
            typer.echo(f"  problem: {line}")


# -- lint ----------------------------------------------------------------------

@app.command()
def lint(paths: list[Path] = typer.Argument(..., help="Pack folder, packs/ tree or a bare skill folder."),
         fmt: str = typer.Option("text", "--format", help="text or sarif"),
         output: Optional[Path] = typer.Option(None, "--output", "-o"),
         allow: list[str] = typer.Option([], "--allow", help="Extra allowed hosts for bare skill folders."),
         no_baseline: bool = typer.Option(False, "--no-baseline", help="Ignore .policy-baseline.json"),
         write_baseline_flag: bool = typer.Option(False, "--write-baseline", help="Accept every current finding into the baseline (reviewers only)."),
         reason: str = typer.Option("accepted by reviewer", "--reason")) -> None:
    """Run the marketplace policy linter. Exit 1 when a blocking finding remains."""
    base = Path.cwd()
    active, suppressed = [], []
    for path in paths:
        if not path.exists():
            _fail(f"{path} does not exist")
        found, hidden = lint_path(path, base, allow=list(allow) or None, use_baseline=not no_baseline)
        if write_baseline_flag:
            home = path if (path / "pack.json").is_file() or (path / "SKILL.md").is_file() else None
            if home is None:
                _fail("--write-baseline needs a single pack or skill folder")
            write_baseline(home, found, reason)
            typer.echo(f"accepted {len(found)} finding(s) into {home / '.policy-baseline.json'}")
            found = []
        active += found
        suppressed += hidden
    if fmt == "sarif":
        text = json.dumps(to_sarif(active, __version__), indent=2)
    else:
        text = format_text(active)
    if output:
        output.write_text(text + ("\n" if text else ""), encoding="utf-8")
    elif text:
        typer.echo(text)
    blocking = [f for f in active if f.severity == BLOCK]
    typer.echo(f"{len(blocking)} blocking, {len(active) - len(blocking)} warning, {len(suppressed)} suppressed by baseline", err=True)
    if blocking:
        raise typer.Exit(code=1)


# -- registry ------------------------------------------------------------------

@registry_app.command("validate")
def registry_validate(root: Path = typer.Option(Path("."), "--root", help="Registry checkout."),
                      fix: bool = typer.Option(False, "--fix", help="Rewrite pack.json checksums.")) -> None:
    """Validate vendors.json and every pack against the schemas, the vendor list and their checksums."""
    try:
        problems = Registry(root).validate(fix=fix)
    except RegistryError as error:
        _fail(str(error))
    for problem in problems:
        typer.echo(problem)
    if problems:
        raise typer.Exit(code=1)
    typer.echo("registry OK")


@registry_app.command("build-index")
def registry_build_index(root: Path = typer.Option(Path("."), "--root"),
                         check: bool = typer.Option(False, "--check", help="Fail if index.json is out of date instead of writing it.")) -> None:
    """Generate index.json and marketplace.json from vendors.json and the packs."""
    try:
        changed = Registry(root).write_index(check=check)
    except RegistryError as error:
        _fail(str(error))
    if check and changed:
        typer.echo("index.json is out of date; run `bob-skills registry build-index`")
        raise typer.Exit(code=1)
    typer.echo("index.json up to date" if not changed else "index.json and marketplace.json written")


if __name__ == "__main__":  # pragma: no cover
    app()
