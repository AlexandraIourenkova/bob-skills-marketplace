#!/usr/bin/env bash
# The security gate, runnable locally: the same steps as .github/workflows/gate.yml.
# Use it before every PR and as a pre-push check while GitHub Actions is unavailable
# on the registry's GitHub host. Exit code 0 = green.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
export PYTHONWARNINGS=ignore

step() { printf '\n== %s\n' "$1"; }

step "client tests (includes the red-team cases)"
uv run -q --project cli pytest -q

step "schemas, vendor list, checksums, release tags"
uv run -q --project cli bob-skills registry validate

step "index.json, marketplace.json and the offline catalog are up to date"
uv run -q --project cli bob-skills registry build-index --check

step "marketplace policy linter"
uv run -q --project cli bob-skills lint packs --format sarif --output policy.sarif
uv run -q --project cli bob-skills lint packs

step "NVIDIA SkillSpector and Cisco skill-scanner (thresholds: >= 30 blocks, CRITICAL/HIGH blocks)"
if ! command -v skillspector >/dev/null || ! command -v skill-scanner >/dev/null; then
  echo "installing scanners with uv tool install"
  uv tool install -q git+https://github.com/NVIDIA/skillspector.git
  uv tool install -q cisco-ai-skill-scanner
fi
uv run -q --project cli python scripts/run_scanners.py --check --reports reports

printf '\n== gate: green\n'
