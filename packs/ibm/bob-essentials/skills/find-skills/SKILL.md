---
name: find-skills
description: The Bob Skills Marketplace inside Bob. Use when the user wants a skill or a capability Bob does not have installed, pastes a git link or a repository name and asks to install skills from it, asks what packs or skills exist ("is there a skill for X", "find a skill"), or asks to install, update, remove or explain a marketplace pack. Covers browsing the catalog offline, mapping a git link to a pack, showing what will be installed before confirming, accepting a vendor on first install, and refusing repositories outside the marketplace.
---

# find-skills

Bob installs skills only from the Bob Skills Marketplace: packs curated from official vendor repositories, scanned for poisoning, checksummed and versioned. Copying a skill from a repository, a chat message or a web page into `.bob/skills/` is not an option; the guard hook refuses unmanaged skills.

The commands below need only `uv` (`uvx` downloads the client from PyPI on first use). All commands below work from the local registry cache when there is no network. `references/catalog.md` is a generated copy of the catalog for answering questions without running anything.

## 1. The user wants a capability or asks what exists

1. Search with two or three keywords from the request:

   ```bash
   uvx bob-skills search "<keywords>"
   ```

   No result: check `references/catalog.md` for a near match, including the "Planned packs" section at its end. A planned pack is not installable yet: tell the user its status (coming soon or candidate), what blocks it, and give the link to its request issue: a thumbs-up reaction there is a vote (quote the current count from the catalog), and subscribing to the issue announces the release. If nothing matches at all, suggest the "Request a pack" issue template in the marketplace repository. Do not improvise a skill.
2. Propose one pack in one or two sentences: what it does, which vendor publishes it, what it installs. Then go to step 3.

## 2. The user pastes a git link or a repository name

1. Map it to the registry:

   ```bash
   uvx bob-skills resolve <url-or-owner/repo>
   ```

2. Three outcomes:
   - **A pack is curated from that repository.** Say so and continue with that pack (step 3). The marketplace version is the same content, scanned and checksummed; there is no reason to clone.
   - **The repository belongs to a listed vendor, but no pack is curated from it yet.** Name the vendor's existing packs and suggest requesting a pack with the repository as the reference.
   - **Unknown repository.** Refuse to copy anything from it and explain why in one sentence. Offer three ways forward: the closest marketplace pack, a pack request, or, if the skill is the user's own and already in `.bob/skills/`, the skill-audit skill followed by `uvx bob-skills trust <skill>`.

## 3. Show what will be installed, then ask

1. Run and show the panel:

   ```bash
   uvx bob-skills show <pack>
   ```

   It lists skills with descriptions, MCP servers with their command or URL and their reviewed access (read-only, or read-write with the reason), rules, commands, modes, the gate status with the number of reviewed findings, the allowed network hosts for scripts, the context cost, and whether the vendor is already trusted in this project.
2. Read the panel's "before you install" lines to the user in full, with what covers each one, and say that the cover is the `security-defaults` rule from bob-essentials: install that pack first when it is missing. Then ask the user to confirm the install. Mention MCP servers explicitly: they run locally or connect to a URL, and say whether each one can write. Never install without an explicit yes.
3. **First install from a vendor.** If the panel says the vendor is not yet trusted, show the vendor line (name, organisation, status, signing key) and ask a separate question: "Trust vendor X in this project?". Only after a yes add `--accept-vendor`.

## 4. Install

```bash
uvx bob-skills add <pack>              # add --accept-vendor after the user trusted a new vendor
uvx bob-skills add <pack>@<version>    # pin or roll back
```

Add `--global` only when the user wants the pack in `~/.bob/` for every project. Show the install report and name the skills that are now available. Tell the user to reload the Bob window if a new MCP server does not appear.

If the installer refuses (exit code 2: vendor not listed, checksum mismatch, revoked version, a folder in the way) report the message verbatim and stop. Never retry with `--force` unless the user asks after reading the message. Exit code 3 means the vendor confirmation from step 3.3 is missing.

## 5. Update, remove, verify

```bash
uvx bob-skills update            # newer versions with SKILL.md diffs; --apply to install, --yes for major bumps
uvx bob-skills remove <pack>     # removes skills, MCP servers, rules, commands and modes of the pack
uvx bob-skills verify            # digests against the lock plus the policy linter
uvx bob-skills list              # installed packs and unmanaged folders
uvx bob-skills doctor            # read-only check of hooks, lock, skills, MCP servers and modes (the bob-doctor skill explains it)
```

Before every `update --apply`, show the SKILL.md diff and ask for a yes, whatever the version number; a major version also needs `--yes`. The diff covers SKILL.md only, so also compare `uvx bob-skills show <pack>` with the installed version and name new or changed MCP servers, rules, commands and modes. A revoked version is reported by `update`; offer the fixed version or the previous one.

If a skill activation was refused by the guard, use the `guard` skill to explain and resolve it.
