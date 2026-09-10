---
name: guard
description: Explain and resolve a refusal from the bob-skills guard hook, which checks every skill against .bob/skills.lock before Bob activates it. Use when a skill activation was refused with a "bob-skills guard" message, or the user asks why a skill is blocked, mentions "unmanaged skill", "digest mismatch", "revoked version", "skill blocked", "guard", or wants to trust a local skill again.
---

# guard

The `PreToolUse` hook on `use_skill` runs `bob-skills guard`. It refuses the activation (exit code 2) in three cases:

| Case | Meaning |
|---|---|
| **unmanaged** | The skill is not in `.bob/skills.lock` or `~/.bob/skills.lock`. It was copied by hand, by another tool, or by the ADK MCP server. |
| **modified** | The digest of the skill folder differs from the lock. Someone edited it after installation. |
| **revoked** | The installed pack version was withdrawn by its vendor. |

## Steps

1. Quote the guard message to the user and name the case.
2. **Unmanaged.** Find the pack that ships the skill with `uvx bob-skills search <skill-name>` and install it with `/skills-add <pack>`; then delete the hand-copied folder. If it is the user's own project skill, register it: `uvx bob-skills trust <skill-name>`. Say that trusting records the current content only, and that an organisation policy may forbid local skills.
3. **Modified.** Show what changed with `uvx bob-skills verify`. If the change is unwanted, restore the pack: `uvx bob-skills add <pack> --force`. If the change is intended, the vendor releases a new version; local edits to a vendor skill are never trusted.
4. **Revoked.** Run `uvx bob-skills update`, which offers the fixed version or a rollback to the previous one.
5. Do not suggest editing the hook configuration or turning the check off, and do not work around the block by reading the skill file directly.
