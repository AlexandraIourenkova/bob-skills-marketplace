# Bob Skills Marketplace

A curated, vendor-owned registry of skill packs for [IBM Bob](https://bob.ibm.com). One command installs a pack of skills, MCP servers, rules, slash commands and modes into `.bob/`, after the pack has been checked for poisoning, verified against the vendor list and recorded in a lock file. A hook then refuses any skill that is not in the lock or was changed after install.

Team entry for the IBM Bob Innovation Challenge, Israel 2026. First pack: **watsonx Orchestrate**.

```bash
uvx bob-skills search orchestrate   # what is there
uvx bob-skills add wxo              # install: vendor + checksums verified, lock written
uvx bob-skills verify               # digests and policy linter on what is installed
uvx bob-skills update               # newer versions with SKILL.md diffs, revocations
```

Inside Bob: `/skills-add wxo`.

## Why

Bob has native skills, hooks, MCP and a CLI, but no install, update or verification layer. Today a skill is installed with `git clone` and `cp -r ~/.bob/skills/` and updated by hand. Public catalogs show roughly a quarter of skills with security findings (NVIDIA SkillSpector data), and nobody checks what lands in `.bob/skills/`. The marketplace closes that gap with four properties:

| Property | How |
|---|---|
| **Checked for poisoning** | Every pack version passes static scanners, the marketplace policy linter, an LLM judge and two human approvals before it is released. Accepted false positives live in a reviewed per-pack baseline. |
| **Official vendors only** | A pack is published by the owner of the product it is about. `vendors.json` is the closed list; CODEOWNERS and CI reject PRs from anyone else; the installer and the guard refuse everything outside the list. |
| **Versioned** | Semver per pack, git tag `<pack>--v<version>`, `.bob/skills.lock` in the project, pinning, rollback and revocation. |
| **One command** | `bob-skills add` copies skills, merges MCP servers and custom modes, adds rules and commands, writes the lock. `remove` undoes all of it. |

## How a skill gets from a vendor into Bob

1. **Vendor opens a PR** with the pack folder: `pack.json`, `skills/<name>/SKILL.md`, optional MCP servers, rules, commands, modes. CI checks the author is a maintainer of that vendor.
2. **Gate runs**: JSON schema, checksums, policy linter (`bob-skills lint`), NVIDIA SkillSpector, Cisco skill-scanner, LLM judge. Findings go to the PR as SARIF; blocking findings fail it.
3. **Two people approve**: a vendor maintainer and a marketplace administrator read the SKILL.md diff.
4. **Release**: the merge commit is tagged `<pack>--v<version>`, `index.json` is rebuilt, the release is signed (cosign, planned) or covered by sha256 checksums in `pack.json`.
5. **Developer installs**: `bob-skills add <pack>` clones the registry, verifies the vendor and every checksum, copies the pack into `.bob/`, writes `.bob/skills.lock`.
6. **Bob activates a skill**: the `PreToolUse` hook on `use_skill` runs `bob-skills guard`, which compares the skill folder digest against the lock. Mismatch or unknown skill: exit code 2, the skill is not activated.

## Repository layout

```
vendors.json            closed vendor list: ids, GitHub orgs, maintainers, keys, network allow-lists
CODEOWNERS              vendor folders are owned by vendor maintainers
schemas/                JSON schemas for pack.json, vendors.json, index.json
packs/<vendor>/<pack>/  pack.json, skills/, rules/, commands/, custom_modes.yaml, .policy-baseline.json
index.json              generated search index (bob-skills registry build-index)
marketplace.json        generated compatibility manifest for other agents
cli/                    the bob-skills client (Python, typer); also the linter and registry tools
scripts/                sync_adk_skills.py, CI helpers
docs/                   pack format, security gate, vendor onboarding, Bob integration, team plan
.github/                gate and release workflows, pack request template
```

## Packs

| Pack | Vendor | Contents |
|---|---|---|
| [`wxo`](packs/ibm-watsonx-orchestrate/wxo) | IBM watsonx Orchestrate | 6 official ADK skills (solution-architect, sop-builder, wxo-builder, wxo-analyzer, telemetry-analyzer, agent-instructions-evaluator), MCP servers `wxo-adk` and `wxo-docs`, ADK rule, `/wxo-deploy`, mode `wxo-builder` |
| [`bob-essentials`](packs/bob-skills-marketplace/bob-essentials) | marketplace team | find-skills, skill-creator, guard, `/skills-add` |
| `carbon`, `building-blocks` | IBM Carbon, IBM Client Engineering | planned |

## Working on the registry

```bash
uv run --project cli pytest -q                          # client tests, including the red-team cases
uv run --project cli bob-skills registry validate --fix # schemas, vendors, checksums
uv run --project cli bob-skills registry build-index    # index.json + marketplace.json
uv run --project cli bob-skills lint packs              # policy linter, honours .policy-baseline.json
```

Try the client against this checkout without publishing anything:

```bash
cd /path/to/some/project
uv run --project /path/to/bob-skills-marketplace/cli bob-skills add wxo --registry /path/to/bob-skills-marketplace
```

## Docs

- [Pack format, checksums, lock file](docs/pack-format.md)
- [Security gate: layers, thresholds, baselines](docs/security-gate.md)
- [Vendor onboarding](docs/vendor-onboarding.md)
- [Bob integration: hooks, commands, what to verify on day one](docs/bob-integration.md)
- [Team plan for the challenge (Russian)](docs/marketplace-plan.md)

The vendored ADK skills are MIT-licensed by IBM (see `packs/ibm-watsonx-orchestrate/wxo/skills/LICENSE`). This repository is a hackathon team project and is not an IBM product.
