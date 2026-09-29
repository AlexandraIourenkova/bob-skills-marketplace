"""Marketplace policy linter: layer 3 of the poisoning gate.

Deterministic rules, no network, no model. The scanners (NVIDIA SkillSpector,
Cisco skill-scanner) and the LLM judge cover what these rules cannot. Every
finding carries a stable fingerprint so a finding that reviewers accepted can
be recorded in the pack's ``.policy-baseline.json`` and stop failing the gate.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .hashing import DigestError, iter_files

BLOCK = "block"
WARN = "warn"
INFO = "info"  # informational: shown in reports, never baselined by default

BASELINE_NAME = ".policy-baseline.json"

RULES: dict[str, str] = {
    "P001": "SKILL.md frontmatter must have a non-empty name and description",
    "P002": "Skill folder name must equal the frontmatter name",
    "P003": "Hidden Unicode: zero-width, bidirectional or tag characters",
    "P004": "Download piped into a shell",
    "P005": "Base64 blob",
    "P006": "Instruction that changes the agent's goal or hides actions from the user",
    "P007": "Hard-coded secret",
    "P008": "Network host outside the vendor allow-list",
    "P009": "Access to a protected path outside the project",
    "P010": "Symlink or unexpected binary file inside a skill",
    "P011": "TLS certificate verification disabled",
    "P012": "Listener on all network interfaces or a debug server",
    "P013": "Script deletes, overwrites or deploys in an external system",
}

CODE_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".ts", ".ps1"}
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".woff", ".woff2", ".ttf", ".ico"}

ALWAYS_ALLOWED_HOSTS = [
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "example.com", "*.example.com", "example.org", "*.example.org",
    "json-schema.org", "json.schemastore.org", "www.w3.org", "schema.org",
]

HIDDEN_UNICODE = re.compile(
    "[\u200b-\u200f\u2028-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]"
)
CURL_PIPE = re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da|k|)sh\b")
BASE64_BLOB = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{200,}={0,2}(?![A-Za-z0-9+/])")
URL_HOST = re.compile(r"\b(?:https?|wss?|ftp)://([A-Za-z0-9.-]+)", re.I)

FORBIDDEN_PHRASES = [
    r"\b(disable|remove|delete|turn off|bypass|skip)\s+(the\s+|all\s+|any\s+)?(hooks?|guard|safety checks?|permission checks?)\b",
    r"\bauto[- ]?approv(e|al)\b",
    r"\bwithout\s+(asking|confirmation|confirming|user consent)\b",
    r"\b(do not|don't|never)\s+(ask|tell|inform|notify|warn)\s+(the\s+)?user\b",
    r"\bignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+instructions\b",
    r"\bskip\s+(the\s+)?(confirmation|approval|permission)s?\b",
    r"\b(hide|conceal)\s+(this|these|the)?\s*(action|change|command|step)s?\b",
    r"отключи(те)?\s+хуки",
    r"без\s+подтверждени[яй]",
    r"не\s+спрашива[йя]",
    r"не\s+сообща[йя]\s+пользовател",
    r"игнорируй\s+(предыдущие|все)\s+инструкции",
]
FORBIDDEN = [re.compile(p, re.I) for p in FORBIDDEN_PHRASES]

SECRETS = [
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"), "API key"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{16,}['\"]"), "hard-coded credential"),
]

PROTECTED_PATHS_BLOCK = [
    re.compile(p) for p in (
        r"~/\.ssh\b", r"\$HOME/\.ssh\b", r"~/\.aws\b", r"~/\.gnupg\b", r"~/\.kube\b",
        r"\.bob/settings\.json", r"~/\.bob/settings", r"\.bob/settings/",
        r"/etc/(passwd|shadow|sudoers|hosts)\b", r"\.npmrc\b", r"\.pypirc\b", r"\.netrc\b",
    )
]
PROTECTED_PATHS_WARN = [
    re.compile(r"(^|[\s\"'(/])\.env\b(?!\.example|\.sample|\.template)"),
]

# P011: the three holes we found in real MCP servers (TLS off, a listener on every
# interface, admin writes by default) must never ship inside a skill. TLS and
# listener patterns apply to instructions too, because the agent executes them.
TLS_OFF = [re.compile(p) for p in (
    r"\bverify\s*=\s*False\b",
    r"(?i)\b(verify[_-]?ssl|ssl[_-]?verify|tls[_-]?verify|verify[_-]?certs?)\b['\"]?\s*[=:]\s*['\"]?(false|0|no|off)\b",
    r"(?i)\b(insecure[_-]?skip[_-]?verify|InsecureSkipVerify)\b['\"]?\s*[=:]\s*['\"]?true\b",
    r"_create_unverified_context\b", r"\bCERT_NONE\b", r"\bcheck_hostname\s*=\s*False\b",
    r"\bcurl\b[^\n|;]*\s(-k|--insecure)(?=\s|$)", r"--no-check-certificate\b", r"--insecure-skip-tls-verify\b",
    r"\bNODE_TLS_REJECT_UNAUTHORIZED\b['\"]?\s*[=:]\s*['\"]?0\b", r"\bPYTHONHTTPSVERIFY\b['\"]?\s*[=:]\s*['\"]?0\b",
    r"\bGIT_SSL_NO_VERIFY\b", r"\brejectUnauthorized\s*:\s*false\b",
    r"--skip-ssl-validation\b",  # ibmcloud api
    r"\b(TrustAllCerts|trustAllCerts|NoopHostnameVerifier|ALLOW_ALL_HOSTNAME_VERIFIER)\b",
    r"\bssl\.endpoint\.identification\.algorithm\s*=\s*(\"\"|'')?\s*$",
)]
OPEN_LISTENER = [re.compile(p) for p in (
    r"\bhost\s*=\s*['\"](0\.0\.0\.0|::)['\"]",
    r"--(host|bind|listen)(=|\s+)['\"]?(0\.0\.0\.0|::)(?![\w.:])",
    r"\bbind\(\(\s*['\"](0\.0\.0\.0)?['\"]\s*,",
    r"\b(HTTPServer|ThreadingHTTPServer|TCPServer)\(\(\s*['\"]['\"]\s*,",
    r"-m\s+http\.server\b(?![^\n]*(--bind|-b)\s+['\"]?(127\.0\.0\.1|localhost|::1)\b)",
    r"\.run\([^)\n]*\bdebug\s*=\s*True",
    r"\.listen\(\s*(\d+|PORT|port)\s*(\)|,\s*(\(|function\b|async\b))",
)]
DESTRUCTIVE = [re.compile(p, re.I) for p in (
    r"\brequests\.(delete|put|patch)\(", r"\baxios\.(delete|put|patch)\(", r"\bmethod\s*[=:]\s*['\"](DELETE|PUT|PATCH)['\"]",
    r"\bcurl\b[^\n]*\s-X\s*['\"]?(DELETE|PUT|PATCH)\b",
    r"\b(kubectl|oc)\s+(delete|drain|replace|scale)\b", r"\bhelm\s+(uninstall|delete)\b",
    r"\bterraform\s+destroy\b", r"\bterraform\s+apply\b[^\n]*-auto-approve",
    r"\baws\s+[\w-]+\s+(delete|terminate|remove|deregister)-", r"\baz\s+[^\n]*\s(delete|purge)\b", r"\bgcloud\s+[^\n]*\s(delete|remove)\b",
    r"\bconfluent\s+[^\n]*\sdelete\b", r"\bkafka-(topics|configs|acls)(\.sh)?\b[^\n]*--(delete|alter)\b",
    r"\bgit\s+push\b[^\n]*(--force|\s-f\b|--mirror|--delete)", r"\bgit\s+reset\s+--hard\b", r"\bgit\s+clean\s+-[a-z]*f",
    r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)\b", r"\bDELETE\s+FROM\s+\w+\s*(;|['\"]|$)",
    r"\brm\s+-[a-z]*r[a-z]*\s+[^\n]*\$\{?\w",
    r"\borchestrate\s+[\w-]+\s+(remove|delete|import)\b",
    # ibmcloud verbs are whole words or hyphen suffixes: instance-delete, image-rm, worker reload; shell or list form
    r"\bibmcloud\b[^\n]*?(?<!\w)(?:\w+-)*(delete|rm|remove|purge|reload|replace|destroy)(?![\w-])",
)]

# A forbidden phrase preceded by a negation in the same sentence is protective
# ("never delete an agent without confirming"), not an attack.
NEGATED_OK = {1, 2, 6}  # indexes into FORBIDDEN_PHRASES that accept a negation
NEGATION = re.compile(r"\b(never|do not|don't|must not|not|no|avoid|refuse to)\b", re.I)


def _negated(line: str, start: int) -> bool:
    sentence = re.split(r"[.;:!?]\s", line[:start])[-1]
    return bool(NEGATION.search(sentence))


def _negated_near(line: str, start: int, words: int = 4) -> bool:
    """Negation among the few words right before the match: "never set verify=False"."""
    before = re.split(r"[.;:!?(\u2014]\s*", line[:start])[-1].split()[-words:]
    return bool(NEGATION.search(" ".join(before)))


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    line: int
    message: str
    source: str = ""
    key: str = ""  # path relative to the pack (skills/<name>/...), stable between registry and install

    @property
    def fingerprint(self) -> str:
        raw = f"{self.rule}|{self.key or self.path}|{self.source.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict:
        return {
            "rule": self.rule, "severity": self.severity, "path": self.path,
            "line": self.line, "message": self.message, "fingerprint": self.fingerprint,
        }


def read_frontmatter(path: Path) -> tuple[dict | None, str]:
    """Return (frontmatter dict or None, full text) for a markdown file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not match:
        return None, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, text
    return (data if isinstance(data, dict) else None), text


def host_allowed(host: str, allow: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for pattern in list(allow) + ALWAYS_ALLOWED_HOSTS:
        pattern = pattern.lower()
        if fnmatch.fnmatchcase(host, pattern):
            return True
        if pattern.startswith("*.") and host == pattern[2:]:
            return True
    return False


def _is_binary(path: Path) -> bool:
    with open(path, "rb") as handle:
        return b"\0" in handle.read(8192)


def _rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def lint_file(path: Path, allow: list[str], base: Path, key_root: Path | None = None, key_prefix: str = "") -> list[Finding]:
    """Content rules for one text file."""
    rel = _rel(path, base)
    key = key_prefix + (_rel(path, key_root) if key_root else rel)
    findings: list[Finding] = []
    if path.suffix.lower() in MEDIA_SUFFIXES:
        return findings
    if _is_binary(path):
        findings.append(Finding("P010", BLOCK, rel, 1, "binary file inside a skill; only text, scripts and media are allowed", key=key))
        return findings

    is_code = path.suffix.lower() in CODE_SUFFIXES
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        for match in HIDDEN_UNICODE.finditer(line):
            findings.append(Finding("P003", BLOCK, rel, number,
                                    f"hidden character U+{ord(match.group(0)):04X} at column {match.start() + 1}", line, key))
        if CURL_PIPE.search(line):
            findings.append(Finding("P004", BLOCK, rel, number, "download piped into a shell", line, key))
        if BASE64_BLOB.search(line):
            findings.append(Finding("P005", BLOCK, rel, number, "base64 blob of 200+ characters", line, key))
        for index, pattern in enumerate(FORBIDDEN):
            match = pattern.search(line)
            if match and not (index in NEGATED_OK and _negated(line, match.start())):
                findings.append(Finding("P006", BLOCK, rel, number, f"forbidden instruction: '{match.group(0)}'", line, key))
                break
        for pattern, label in SECRETS:
            if pattern.search(line):
                findings.append(Finding("P007", BLOCK, rel, number, f"looks like a {label}", line, key))
                break
        for host in {m.group(1) for m in URL_HOST.finditer(line)}:
            if not host_allowed(host, allow):
                severity = BLOCK if is_code else INFO
                where = "script" if is_code else "instructions"
                findings.append(Finding("P008", severity, rel, number,
                                        f"host '{host}' in {where} is not in the allow-list {sorted(allow)}", line, key))
        for rule, patterns, message in (("P011", TLS_OFF, "TLS certificate verification disabled"),
                                        ("P012", OPEN_LISTENER, "listener on all network interfaces or a debug server; bind to 127.0.0.1")):
            match = next((m for m in (p.search(line) for p in patterns) if m), None)
            if match and (is_code or not _negated_near(line, match.start())):
                findings.append(Finding(rule, BLOCK, rel, number, f"{message}: '{match.group(0).strip()}'", line, key))
        if is_code and not line.lstrip().startswith(("#", "//", "*", "/*")):
            match = next((m for m in (p.search(line) for p in DESTRUCTIVE) if m), None)
            if match:
                findings.append(Finding("P013", BLOCK, rel, number,
                                        f"deletes, overwrites or deploys in an external system: '{match.group(0).strip()}'; "
                                        "the skill must get the user's confirmation for this exact action first", line, key))
        for tier, patterns in ((BLOCK, PROTECTED_PATHS_BLOCK), (WARN, PROTECTED_PATHS_WARN)):
            match = next((m for m in (p.search(line) for p in patterns) if m), None)
            if match:
                severity = tier if is_code else WARN
                findings.append(Finding("P009", severity, rel, number,
                                        f"reference to protected path '{match.group(0).strip()}'", line, key))
                break
    return findings


def lint_skill(skill_dir: Path, allow: list[str], base: Path) -> list[Finding]:
    """Structural and content rules for one skill folder."""
    skill_dir = Path(skill_dir)
    rel = _rel(skill_dir, base)
    prefix = f"skills/{skill_dir.name}/"
    md_key = prefix + "SKILL.md"
    findings: list[Finding] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        findings.append(Finding("P001", BLOCK, f"{rel}/SKILL.md", 1, "SKILL.md is missing", key=md_key))
        return findings
    meta, _ = read_frontmatter(skill_md)
    md_rel = _rel(skill_md, base)
    if meta is None:
        findings.append(Finding("P001", BLOCK, md_rel, 1, "no YAML frontmatter; Bob needs name and description", key=md_key))
    else:
        name = meta.get("name")
        description = meta.get("description")
        if not isinstance(name, str) or not name.strip():
            findings.append(Finding("P001", BLOCK, md_rel, 1, "frontmatter 'name' is missing or empty", key=md_key))
        if not isinstance(description, str) or not description.strip():
            findings.append(Finding("P001", BLOCK, md_rel, 1, "frontmatter 'description' is missing or empty; Bob ignores the skill", key=md_key))
        elif len(description) > 1024:
            findings.append(Finding("P001", WARN, md_rel, 1, f"description is {len(description)} characters; keep it under 1024", key=md_key))
        if isinstance(name, str) and name.strip() and name.strip() != skill_dir.name:
            findings.append(Finding("P002", BLOCK, md_rel, 1, f"frontmatter name '{name}' differs from folder '{skill_dir.name}'", key=md_key))
    try:
        for path in iter_files(skill_dir):
            findings.extend(lint_file(path, allow, base, key_root=skill_dir, key_prefix=prefix))
    except DigestError as error:
        findings.append(Finding("P010", BLOCK, rel, 1, str(error), key=prefix))
    return findings


def lint_pack(pack_dir: Path, base: Path, allow: list[str] | None = None) -> list[Finding]:
    """Lint every shipped component of a pack."""
    pack_dir = Path(pack_dir)
    manifest = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
    allow = list(allow if allow is not None else manifest.get("networkAllow", []))
    findings: list[Finding] = []
    for skill in manifest.get("skills", []):
        findings.extend(lint_skill(pack_dir / "skills" / skill, allow, base))
    for component in list(manifest.get("rules", [])) + list(manifest.get("commands", [])):
        path = pack_dir / component
        if path.is_file():
            findings.extend(lint_file(path, allow, base, key_root=pack_dir))
    if manifest.get("modes"):
        path = pack_dir / manifest["modes"]
        if path.is_file():
            findings.extend(lint_file(path, allow, base, key_root=pack_dir))
    return findings


def find_pack_dirs(root: Path) -> list[Path]:
    root = Path(root)
    if (root / "pack.json").is_file():
        return [root]
    return sorted(p.parent for p in root.glob("*/*/pack.json")) or sorted(p.parent for p in root.rglob("pack.json"))


def load_baseline(where: Path) -> set[str]:
    path = Path(where) / BASELINE_NAME
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {entry["fingerprint"] for entry in data.get("accepted", []) if "fingerprint" in entry}


def write_baseline(where: Path, findings: list[Finding], reason: str, include_info: bool = False) -> Path:
    findings = [f for f in findings if include_info or f.severity != INFO]
    path = Path(where) / BASELINE_NAME
    existing: dict[str, dict] = {}
    if path.is_file():
        for entry in json.loads(path.read_text(encoding="utf-8")).get("accepted", []):
            existing[entry["fingerprint"]] = entry
    for finding in findings:
        existing.setdefault(finding.fingerprint, {
            "fingerprint": finding.fingerprint, "rule": finding.rule, "path": finding.key or finding.path,
            "line": finding.line, "message": finding.message, "reason": reason,
        })
    payload = {"accepted": sorted(existing.values(), key=lambda e: (e["path"], e["rule"], e["fingerprint"]))}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def lint_path(path: Path, base: Path, allow: list[str] | None = None, use_baseline: bool = True) -> tuple[list[Finding], list[Finding]]:
    """Lint a pack folder, a packs/ tree or a bare skill folder.

    Returns (active findings, suppressed findings).
    """
    path = Path(path)
    results: list[tuple[Finding, Path]] = []
    if (path / "SKILL.md").is_file():
        results += [(f, path) for f in lint_skill(path, list(allow or []), base)]
    else:
        pack_dirs = find_pack_dirs(path)
        if not pack_dirs:
            for file in iter_files(path):
                results += [(f, path) for f in lint_file(file, list(allow or []), base)]
        for pack_dir in pack_dirs:
            results += [(f, pack_dir) for f in lint_pack(pack_dir, base, allow)]
    active: list[Finding] = []
    suppressed: list[Finding] = []
    baselines: dict[Path, set[str]] = {}
    for finding, home in results:
        if use_baseline:
            accepted = baselines.setdefault(home, load_baseline(home))
            if finding.fingerprint in accepted:
                suppressed.append(finding)
                continue
        active.append(finding)
    return active, suppressed


def format_text(findings: list[Finding]) -> str:
    lines = []
    for finding in findings:
        lines.append(f"{finding.severity.upper():5} {finding.rule} {finding.path}:{finding.line}: {finding.message}  [{finding.fingerprint}]")
    return "\n".join(lines)


def to_sarif(findings: list[Finding], version: str) -> dict:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "bob-skills-policy",
                "version": version,
                "informationUri": "https://github.ibm.com/Maria-Startseva/bob-skills-marketplace",
                "rules": [{"id": rule, "shortDescription": {"text": text}} for rule, text in RULES.items()],
            }},
            "results": [{
                "ruleId": f.rule,
                "level": "error" if f.severity == BLOCK else "warning" if f.severity == WARN else "note",
                "message": {"text": f.message},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": f.path},
                    "region": {"startLine": max(f.line, 1)},
                }}],
                "partialFingerprints": {"bobSkillsPolicy/v1": f.fingerprint},
            } for f in findings],
        }],
    }
