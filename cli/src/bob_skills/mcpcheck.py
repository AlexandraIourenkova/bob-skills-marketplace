"""Checks for MCP server configurations.

One set of rules for two places: the registry gate (a pack may not ship a risky
server entry in ``mcpServers``) and ``bob-skills doctor`` (servers a user or
another tool added to ``.bob/mcp.json`` by hand). The rules target the holes we
found in real MCP servers: write tools approved in advance, secrets in the
config, TLS verification switched off, a listener on every interface or with
authentication disabled, unpinned package versions, telemetry on by default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath

PROBLEM = "problem"
WARNING = "warning"

CODES: dict[str, str] = {
    "M001": "Package runner without a pinned version",
    "M002": "Remote server over plain HTTP",
    "M003": "Secret written into the configuration",
    "M004": "TLS certificate verification disabled",
    "M005": "Listener on all interfaces or authentication disabled",
    "M006": "Tools approved in advance",
    "M007": "Known server with telemetry on or write tools unrestricted",
}

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

SECRET_KEY = re.compile(
    r"(token|secret|password|passwd|pwd|api[_-]?key|apikey|credential|private[_-]?key|access[_-]?key|"
    r"authorization|^auth$|^sec$|cookie|session)", re.I)
PLACEHOLDER = re.compile(
    r"^\s*$|\$\{[^}]+\}|^\$[A-Za-z_][A-Za-z0-9_]*$|^<[^>]*>$|\{\{[^}]+\}\}|"
    r"^(your|my)[-_ ]|^YOUR_|changeme|^x{3,}$|^\*+$|replace|placeholder|^todo$", re.I)
SECRET_VALUE = re.compile(
    r"\bAKIA[0-9A-Z]{16}\b|\bghp_[A-Za-z0-9]{36}\b|\bgh[ousr]_[A-Za-z0-9]{36}\b|\bsk-[A-Za-z0-9_-]{32,}\b|"
    r"\bxox[abpr]-[A-Za-z0-9-]{10,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----")
SECRET_ARG = re.compile(r"^--?(api[-_]?key|token|secret|password|passwd|access[-_]?key|auth[-_]?token)(=(?P<value>.+))?$", re.I)

TLS_OFF_ENV = {
    "NODE_TLS_REJECT_UNAUTHORIZED": {"0", "false"},
    "PYTHONHTTPSVERIFY": {"0", "false"},
    "GIT_SSL_NO_VERIFY": {"1", "true", "yes"},
}
TLS_OFF_KEY = re.compile(r"(verify[_-]?ssl|ssl[_-]?verify|tls[_-]?verify|verify[_-]?certs?)$", re.I)
TLS_OFF_ARGS = {"--insecure", "--no-verify", "--no-verify-ssl", "--skip-tls-verify", "--insecure-skip-tls-verify",
                "--tls-skip-verify", "--disable-ssl-verification", "--no-check-certificate", "--ssl-no-verify"}
AUTH_OFF_ARGS = {"--disable-auth", "--no-auth", "--auth=none", "--allow-anonymous", "--unauthenticated"}
LISTEN_FLAGS = {"--host", "--bind", "--listen", "--address", "--addr"}
ALL_INTERFACES = {"0.0.0.0", "::", "[::]", "*"}
LISTEN_ENV = re.compile(r"^(host|bind|listen|.*_host|.*_bind|.*_listen)$", re.I)

WRITE_TOOL = re.compile(
    r"(^|[-_.:/])(create|delete|remove|rm|update|write|put|post|patch|set|alter|drop|truncate|insert|upsert|import|"
    r"deploy|apply|execute|exec|run|kill|stop|restart|send|publish|push|close|assign|reset|move|rename|grant|revoke|"
    r"produce|upload|install|uninstall|enable|disable|modify|edit|approve)([-_.:/]|s?$)", re.I)

SEMVER = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"
NPM_PINNED = re.compile(rf"^(@[^/@\s]+/)?[^@/\s]+@{SEMVER}$")
PY_PINNED = re.compile(rf"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]+\])?(==|@){SEMVER}$")
GIT_PINNED = re.compile(r"^git\+[^@\s]+@[0-9a-f]{40}(#.*)?$")
IMAGE_PINNED = re.compile(r"@sha256:[0-9a-f]{64}$|:(?!latest$)[\w][\w.-]*$")

NPM_RUNNERS = {"npx", "bunx", "pnpx"}
DLX_RUNNERS = {"pnpm", "yarn"}
PY_RUNNERS = {"uvx", "pipx", "uv"}
NPM_VALUED_FLAGS = {"-p", "--package", "-c", "--call", "--registry", "--cache", "--userconfig"}
UV_VALUED_FLAGS = {"--with", "--python", "-p", "--index", "--index-url", "--extra-index-url", "--from", "--spec"}
DOCKER_VALUED_FLAGS = {"-e", "--env", "--env-file", "-v", "--volume", "-p", "--publish", "--name", "--network", "-w",
                       "--workdir", "--entrypoint", "-u", "--user", "--platform", "--mount", "--label", "-l", "--add-host",
                       "--cpus", "--memory", "-m", "--pull", "--restart", "--hostname", "-h", "--cap-add", "--cap-drop"}

# Servers whose risky defaults we know. `package` matches the runner's package
# name; `telemetry` names the variable that switches telemetry off; `restrict`
# lists the flags that limit which tools the agent gets.
KNOWN_SERVERS = [
    {"package": "@confluentinc/mcp-confluent", "telemetry": ("DO_NOT_TRACK", "true"),
     "restrict": ("--allow-tools", "--block-tools", "--allow-tools-file", "--block-tools-file"),
     "note": "write tools such as delete-topics, delete-connector and alter-topic-config are on by default"},
]


@dataclass
class McpIssue:
    code: str
    severity: str
    server: str
    message: str
    fix: str

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "server": self.server, "message": self.message, "fix": self.fix}

    def __str__(self) -> str:
        return f"{self.code} {self.message}; fix: {self.fix}"


def _base(command: str) -> str:
    return PurePath(command.replace("\\", "/")).name.lower().removesuffix(".cmd").removesuffix(".exe")


def _first_positional(args: list[str], valued: set[str]) -> tuple[int, str] | tuple[None, None]:
    skip = False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg.startswith("-"):
            if "=" not in arg and arg in valued:
                skip = True
            continue
        return index, arg
    return None, None


def package_spec(command: str, args: list[str]) -> tuple[str, str] | None:
    """Return (ecosystem, package spec) for commands that fetch and run a package."""
    base = _base(command)
    args = list(args)
    if base in NPM_RUNNERS or (base in DLX_RUNNERS and args[:1] == ["dlx"]) or (base == "npm" and args[:1] == ["exec"]):
        if base in DLX_RUNNERS or base == "npm":
            args = args[1:]
        for index, arg in enumerate(args):
            if arg in ("-p", "--package") and index + 1 < len(args):
                return "npm", args[index + 1]
            if arg.startswith("--package="):
                return "npm", arg.split("=", 1)[1]
        _, spec = _first_positional(args, NPM_VALUED_FLAGS)
        return ("npm", spec) if spec else None
    if base in PY_RUNNERS:
        if base == "uv":
            if args[:2] != ["tool", "run"]:
                return None
            args = args[2:]
        if base == "pipx":
            if args[:1] != ["run"]:
                return None
            args = args[1:]
        for index, arg in enumerate(args):
            if arg in ("--from", "--spec") and index + 1 < len(args):
                return "python", args[index + 1]
            if arg.startswith(("--from=", "--spec=")):
                return "python", arg.split("=", 1)[1]
        _, spec = _first_positional(args, UV_VALUED_FLAGS)
        return ("python", spec) if spec else None
    if base in ("docker", "podman") and "run" in args:
        rest = args[args.index("run") + 1:]
        _, image = _first_positional(rest, DOCKER_VALUED_FLAGS)
        return ("image", image) if image else None
    return None


def _pinned(ecosystem: str, spec: str) -> bool:
    if spec.startswith(("./", "../", "/", "~")) or spec.endswith((".js", ".mjs", ".py")):
        return True  # a local path, not a package download
    if ecosystem == "npm":
        return bool(NPM_PINNED.match(spec)) or bool(GIT_PINNED.match(spec))
    if ecosystem == "python":
        return bool(PY_PINNED.match(spec)) or bool(GIT_PINNED.match(spec))
    if ecosystem == "image":
        return bool(IMAGE_PINNED.search(spec))
    return True


def _package_name(ecosystem: str, spec: str) -> str:
    if ecosystem == "npm":
        head, _, _ = spec.rpartition("@") if spec.count("@") > (1 if spec.startswith("@") else 0) else (spec, "", "")
        return head or spec
    if ecosystem == "python":
        return re.split(r"==|@|\[", spec, maxsplit=1)[0]
    return spec


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER.search(value))


def check_server(name: str, spec: dict, strict: bool = False) -> list[McpIssue]:
    """Issues for one server entry. ``strict`` is the registry gate: stricter than doctor."""
    issues: list[McpIssue] = []
    def add(code: str, severity: str, message: str, fix: str) -> None:
        issues.append(McpIssue(code, severity, name, message, fix))

    command = str(spec.get("command", "") or "")
    args = [str(a) for a in spec.get("args", []) or []]
    env = {str(k): str(v) for k, v in (spec.get("env") or {}).items()}
    headers = {str(k): str(v) for k, v in (spec.get("headers") or {}).items()}
    url = str(spec.get("url", "") or "")

    # M001: the runner downloads whatever the registry serves today.
    found = package_spec(command, args) if command else None
    package = ""
    if found:
        ecosystem, pkg = found
        package = _package_name(ecosystem, pkg)
        if not _pinned(ecosystem, pkg):
            add("M001", PROBLEM if strict else WARNING,
                f"`{command}` runs '{pkg}' without a pinned version, so every start may fetch different code",
                "pin an exact version (npm: name@1.2.3, uvx: name==1.2.3, git: @<40-character commit>, image: a tag or digest)")

    # M002: remote servers must use TLS.
    match = re.match(r"^(https?|wss?)://([^/:?#]+|\[[^\]]+\])", url, re.I)
    if match and match.group(1).lower() in ("http", "ws") and match.group(2).lower() not in LOCAL_HOSTS:
        add("M002", PROBLEM, f"remote server at {url} is plain {match.group(1).upper()}; tokens and results travel unencrypted",
            "use the https:// endpoint")
    if re.match(r"^[a-z]+://[^/@\s]+:[^/@\s]+@", url, re.I):
        add("M003", PROBLEM, "the URL carries a user name and password", "move credentials to an environment variable or header placeholder")

    # M003: secrets belong in the environment of the user, not in a file that gets copied and committed.
    for where, mapping in (("env", env), ("headers", headers)):
        for key, value in mapping.items():
            literal = value.split(None, 1)[-1] if value.lower().startswith(("bearer ", "basic ", "token ")) else value
            named_secret = (SECRET_KEY.search(key) and not re.search(r"(_file|_path|_dir|_url|_endpoint|_host|_timeout|_ttl)$", key, re.I)
                            and not _is_placeholder(literal) and len(literal) >= 8 and not literal.isdigit()
                            and literal.lower() not in ("true", "false", "none", "null"))
            if named_secret or SECRET_VALUE.search(value):
                add("M003", PROBLEM, f"{where}.{key} holds a literal secret",
                    "reference the user's environment (for example ${env:NAME}) or a secret store; rotate the exposed value")
    for index, arg in enumerate(args):
        m = SECRET_ARG.match(arg)
        if m:
            value = m.group("value") if m.group("value") is not None else (args[index + 1] if index + 1 < len(args) else "")
            if value and not _is_placeholder(value):
                add("M003", PROBLEM, f"argument {arg.split('=')[0]} carries a literal secret", "pass it through the environment")
        elif SECRET_VALUE.search(arg):
            add("M003", PROBLEM, "an argument contains a token", "pass it through the environment")

    # M004: TLS verification off.
    for key, value in env.items():
        if TLS_OFF_ENV.get(key.upper()) and value.strip().lower() in TLS_OFF_ENV[key.upper()]:
            add("M004", PROBLEM, f"env {key}={value} disables TLS certificate verification", "remove it; trust an internal CA with its bundle instead")
        elif TLS_OFF_KEY.search(key) and value.strip().lower() in ("0", "false", "no", "off"):
            add("M004", PROBLEM, f"env {key}={value} disables TLS certificate verification", "remove it; trust an internal CA with its bundle instead")
    for arg in args:
        if arg.split("=")[0].lower() in TLS_OFF_ARGS:
            add("M004", PROBLEM, f"argument {arg} disables TLS certificate verification", "remove it")

    # M005: reachable from the network, or reachable without credentials.
    for index, arg in enumerate(args):
        flag, _, inline = arg.partition("=")
        value = inline or (args[index + 1] if index + 1 < len(args) and not inline else "")
        if flag.lower() in LISTEN_FLAGS and value.strip("'\"") in ALL_INTERFACES:
            add("M005", PROBLEM, f"{flag} {value} exposes the server to every network the machine is on",
                "bind to 127.0.0.1 or use stdio")
        if arg.lower() in AUTH_OFF_ARGS:
            add("M005", PROBLEM, f"argument {arg} turns authentication off", "remove it")
    for key, value in env.items():
        if LISTEN_ENV.match(key) and value.strip() in ALL_INTERFACES:
            add("M005", PROBLEM, f"env {key}={value} exposes the server to every network the machine is on", "bind to 127.0.0.1")

    # M006: tools approved in advance run without the user seeing the call.
    approved = [str(t) for t in spec.get("alwaysAllow", []) or []]
    writes = [t for t in approved if t == "*" or WRITE_TOOL.search(t)]
    if writes:
        add("M006", PROBLEM, f"write or admin tools approved in advance: {', '.join(writes)}",
            "remove them from alwaysAllow; each call must reach the user for confirmation")
    elif approved:
        add("M006", PROBLEM if strict else WARNING, f"tools approved in advance: {', '.join(approved)}",
            "packs never pre-approve tools; keep alwaysAllow empty" if strict else "keep only read-only tools there")

    # M007: servers whose risky defaults we know.
    for known in KNOWN_SERVERS:
        if package != known["package"]:
            continue
        var, wanted = known["telemetry"]
        if env.get(var, "").lower() != wanted:
            add("M007", PROBLEM if strict else WARNING, f"{package} sends telemetry unless {var}={wanted} is set",
                f"add env {var}={wanted}")
        if not any(a.split("=")[0] in known["restrict"] for a in args):
            add("M007", PROBLEM if strict else WARNING, f"{package}: {known['note']}",
                f"limit the tools with {' or '.join(known['restrict'][:2])}")
    return issues


def check_servers(servers: dict, strict: bool = False) -> list[McpIssue]:
    issues: list[McpIssue] = []
    for name, spec in (servers or {}).items():
        if isinstance(spec, dict):
            issues.extend(check_server(str(name), spec, strict=strict))
    return issues
