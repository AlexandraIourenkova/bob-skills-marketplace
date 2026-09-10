---
name: skill-creator
description: Create or improve an IBM Bob skill (SKILL.md plus optional scripts, references and assets) that Bob picks up and the marketplace policy linter accepts. Use when the user wants to write a new skill, package a repeated workflow as a skill, fix a skill Bob ignores, or prepare a skill for a marketplace pack. Triggers include "create a skill", "write a SKILL.md", "package this as a skill", "the skill is not picked up".
---

# skill-creator

## What Bob requires

- The folder name equals `name` in the frontmatter: lowercase letters, digits and hyphens.
- `description` is mandatory. Bob ignores a skill without it, and it is the text Bob matches against the user's request. Say what the skill does and when to use it, and list the phrases users say, in every language the team uses. One paragraph, under 1024 characters.
- The body of SKILL.md is short and imperative: numbered steps, exact commands, what to report back. Long reference material goes to `references/`, helpers to `scripts/`, templates to `assets/`. Keep SKILL.md under about 300 lines.

## What the marketplace policy blocks

- Network access in scripts to hosts outside the vendor's allow-list, `curl` or `wget` piped into a shell, writes outside the project folder, any change to Bob's settings or hook configuration.
- Instructions that change Bob's goal or keep the user in the dark: skipping confirmations, turning off safety checks, staying silent about what was done.
- Hidden Unicode (zero-width or bidirectional characters), base64 blobs, hard-coded secrets.

## Steps

1. Ask for the workflow the skill captures and the two or three phrases a user would say to trigger it. Draft the frontmatter first, then the steps.
2. Put every command the skill runs in a fenced block and every external file it reads in `references/`.
3. Lint the folder and fix every finding:

   ```bash
   uvx bob-skills lint <skill-dir>
   ```

4. Test with one request that should trigger the skill and one that should not. Adjust the description until both behave.
5. To publish, the skill goes into the vendor's pack folder in the marketplace repository (`packs/<vendor>/<pack>/skills/`), see `docs/vendor-onboarding.md`. Only the product's vendor publishes it; a user request goes through the "Request a pack" issue template.
