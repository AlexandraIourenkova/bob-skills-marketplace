# bob-skills

Client for the Bob Skills Marketplace: installs vendor-signed skill packs into IBM Bob, keeps a lock file, and guards `use_skill` activations.

```bash
uvx bob-skills search orchestrate      # find packs
uvx bob-skills add wxo-adk             # install into ./.bob (add --global for ~/.bob)
uvx bob-skills add wxo-adk@1.0.0       # pin or roll back
uvx bob-skills list                    # what is installed
uvx bob-skills verify                  # digests + policy linter on installed skills
uvx bob-skills update [--apply]        # newer versions, SKILL.md diffs, revocations
uvx bob-skills remove wxo-adk          # cleans MCP entries, rules, commands, modes too
uvx bob-skills trust my-local-skill    # accept a project-local skill as it is now
uvx bob-skills guard                   # PreToolUse hook: JSON on stdin, exit 2 blocks
uvx bob-skills check --brief           # SessionStart hook: one status line
uvx bob-skills lint <pack-or-skill>    # marketplace policy linter (text or --format sarif)
uvx bob-skills registry validate|build-index   # registry maintenance
```

Until the package is on an index reachable from your machine, run it from the checkout:

```bash
uv run --project cli bob-skills --help
```

Set `BOB_SKILLS_REGISTRY` to a local checkout or another git URL to use a different registry.
