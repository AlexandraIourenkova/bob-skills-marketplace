# Pack `bob-essentials`

Vendor: `ibm`. The marketplace's own skills, installed with `uvx bob-skills add bob-essentials`.

| Component | What it adds |
|---|---|
| `skills/find-skills` | When Bob lacks a capability, search the registry and propose a pack instead of copying skills by hand |
| `skills/skill-audit` | Check a skill before anyone trusts it: policy linter, SkillSpector and Cisco when installed, and a read-through for writes without the user's yes, content that steers actions, TLS off, open listeners and credential fallbacks |
| `skills/bob-doctor` | Read-only check of the Bob setup (hooks, lock, skills, MCP servers, modes) with fixes applied only after the user agrees |
| `skills/skill-creator` | Write skills, custom modes, rules and slash commands that Bob picks up and the policy linter accepts, with safe defaults |
| `skills/guard` | Explain a block from the guard hook and how to resolve it |
| `rules/security-defaults.md` | For every task in the project: outside content is data, the user's yes before each external write, TLS on, loopback listeners, no stored-credential fallbacks, safe MCP entries |
| `commands/skills-add.md` | `/skills-add <pack>` runs the installer from inside Bob |

skill-audit and bob-doctor need client 0.2.0 or later (`uvx bob-skills audit`, `uvx bob-skills doctor`).

The guard hook itself is not a skill; it is configured in `.bob/settings.json` (see `docs/bob-integration.md`).
