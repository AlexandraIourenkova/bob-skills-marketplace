# Pack format

A pack is one installable unit. It lives at `packs/<vendor>/<name>/` and is described by `pack.json` ([schema](../schemas/pack.schema.json)).

```
packs/<vendor>/<name>/
├── pack.json               manifest
├── README.md               shown in the catalog, not installed
├── .policy-baseline.json   accepted linter findings, reviewed (optional)
├── skills/<skill>/SKILL.md one folder per skill, copied to .bob/skills/<skill>/
├── rules/*.md              copied to .bob/rules/
├── commands/*.md           copied to .bob/commands/ (Bob Shell slash commands)
└── custom_modes.yaml       customModes merged by slug into .bob/custom_modes.yaml
```

## pack.json

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Pack id, unique in the registry, equals the folder name. `uvx bob-skills add <name>`. |
| `displayName`, `description` | yes | Catalog text. |
| `version` | yes | Semver. Any change to a shipped file needs a new version. Release tag `<name>--v<version>`. |
| `vendor` | yes | Vendor id from `vendors.json`; must equal the parent folder. |
| `skills` | yes | Skill folder names under `skills/`. Each `SKILL.md` needs frontmatter `name` (equal to the folder) and a non-empty `description`; Bob ignores a skill without one. |
| `mcpServers` | no | Merged into `.bob/mcp.json` (project) or `~/.bob/mcp_settings.json` (`--global`). The installer refuses to overwrite a server it does not own unless `--force`. |
| `rules`, `commands`, `modes` | no | Relative paths of rule files, command files and the modes file. |
| `networkAllow` | no | Hosts the pack's scripts may contact. Must be a subset of the vendor's allow-list. Any other host in a script is a blocking linter finding. |
| `revokedVersions` | no | Versions the vendor withdrew. The installer refuses them, `update` offers a way out, the guard refuses their skills. |
| `checksums` | yes for release | Digest per component (`skills/<skill>`, `rules/<file>`, `commands/<file>`, `custom_modes.yaml`). Maintained by `bob-skills registry validate --fix`; CI fails when they do not match the tree. The installer refuses a pack whose checksums do not match. |
| `source`, `license`, `homepage`, `minBob`, `tags` | no | Provenance and catalog metadata. |

## Digest algorithm

The same function computes checksums in the registry, digests in the lock and the guard's comparison, so they always match.

- File digest: sha256 of the file bytes.
- Directory digest: sha256 over the lines `<relative posix path>\n<file sha256>\n` for every regular file, sorted by path. Ignored: `.DS_Store`, `Thumbs.db`, `__pycache__`, `.git`, `*.pyc`. Symlinks are refused.
- Rendered as `sha256:<hex>`.

Implementation: `cli/src/bob_skills/hashing.py`.

## Lock file

`.bob/skills.lock` (or `~/.bob/skills.lock` for `--global`) is TOML, written only by `uvx bob-skills add`, `remove` and `trust`:

```toml
version = 1

[[pack]]
name = "wxo-adk"
version = "1.0.0"
vendor = "ibm"
digest = "sha256:..."                     # whole pack folder in the registry
installed = "2026-09-30T10:12:00Z"
registry = "https://github.ibm.com/Maria-Startseva/bob-skills-marketplace.git"
registryCommit = "..."
networkAllow = ["*.ibm.com", "ibm.com", "pypi.org", "github.com"]
skills = ["solution-architect", "sop-builder", "wxo-builder", "wxo-analyzer", "telemetry-analyzer", "agent-instructions-evaluator"]
mcpServers = ["wxo-adk", "watsonx-orchestrate-adk-docs"]
rules = ["wxo-adk.md"]
commands = ["wxo-deploy.md"]
modes = ["wxo-builder"]
policyAccepted = ["..."]                  # baseline fingerprints, so verify does not re-flag reviewed findings

[pack.skillDigests]
"wxo-builder" = "sha256:..."              # what the guard compares against
```

A skill trusted with `uvx bob-skills trust <skill>` gets an entry with `vendor = "local"`. `uvx bob-skills guard --no-local` refuses those; organisations enforce that through the hook command in an EnforcedHooks policy.

## Versions, tags, rollback, revocation

- `uvx bob-skills add wxo-adk` installs the version on the registry's default branch.
- `uvx bob-skills add wxo-adk@1.0.0` exports the tag `wxo-adk--v1.0.0` with `git archive` and installs that. Rollback is the same command with an older version.
- `uvx bob-skills update` compares the lock with the registry, prints the unified diff of every `SKILL.md`, and installs with `--apply` (`--yes` for a major bump).
- To revoke, the vendor adds the version to `revokedVersions` in a PR. No tag is deleted; history stays auditable.

## Policy baseline

`.policy-baseline.json` in the pack folder lists linter findings a reviewer accepted, with the reason. Fingerprints are keyed by the path inside the pack (`skills/<skill>/...`) and the line text, so they stay valid after installation and stop matching as soon as the line changes. Write it with `uvx bob-skills lint <pack> --write-baseline --reason "..."` and edit the reasons; the file is reviewed like code.
