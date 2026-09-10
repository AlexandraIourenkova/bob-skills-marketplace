## What

<!-- pack and version, or the registry change -->

## Checklist for pack changes

- [ ] `version` in `pack.json` bumped; checksums refreshed with `bob-skills registry validate --fix`
- [ ] `bob-skills lint packs/<vendor>/<pack>` is clean, or new baseline entries carry a real reason
- [ ] SKILL.md diff read in full by both reviewers (vendor maintainer + marketplace administrator)
- [ ] MCP servers, rules, commands and modes listed in `pack.json` and reviewed
- [ ] `revokedVersions` updated if this PR withdraws a version
