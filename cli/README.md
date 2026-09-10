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
bob-skills registry validate|build-index   # registry maintenance
```

Install once, straight from the registry repository (needs git access to github.ibm.com):

```bash
uv tool install "git+https://github.ibm.com/Maria-Startseva/bob-skills-marketplace.git#subdirectory=cli"
```

Or run from a checkout without installing: `uv run --project cli bob-skills --help`. `uvx bob-skills` will work once the package is published to an index; the name is free on PyPI.

Set `BOB_SKILLS_REGISTRY` to a local checkout or another git URL to use a different registry.
