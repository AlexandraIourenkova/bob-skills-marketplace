# Pack `bob-essentials`

Vendor: `ibm`. The marketplace's own skills, installed with `uvx bob-skills add bob-essentials`.

| Component | What it adds |
|---|---|
| `skills/find-skills` | When Bob lacks a capability, search the registry and propose a pack instead of copying skills by hand |
| `skills/skill-creator` | Write a SKILL.md that Bob picks up and the policy linter accepts |
| `skills/guard` | Explain a block from the guard hook and how to resolve it |
| `commands/skills-add.md` | `/skills-add <pack>` runs the installer from inside Bob |

The guard hook itself is not a skill; it is configured in `.bob/settings.json` (see `docs/bob-integration.md`).
