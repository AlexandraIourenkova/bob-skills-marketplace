#!/usr/bin/env bash
# Deploy a bundled-SQLite text-to-SQL agent to watsonx Orchestrate.
# Prereqs: `pip install ibm-watsonx-orchestrate` in a clean venv, and an
# environment already added (orchestrate env add -n NAME -u URL).
#
# Usage: ./deploy.sh [package_dir] [agent_yaml]
set -euo pipefail

# Force UTF-8 end to end. Critical: the ADK auto-detects file encoding with
# charset_normalizer, and UTF-8 YAML dense with Hebrew/Cyrillic gets misdetected
# (as cp855) and imported as mojibake — on any OS. The settings override
# disables that detection; the env vars guard the rest of the toolchain.
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
orchestrate settings set-encoding utf-8 >/dev/null

PKG_DIR="${1:-tool_pkg}"
AGENT_YAML="${2:-agent.yaml}"
TOOL_FILE="$(ls "$PKG_DIR"/*.py | head -1)"

if ! orchestrate env list 2>/dev/null | grep -q '(active)'; then
    echo "No active orchestrate environment. Run:"
    echo "  orchestrate env add -n my_env -u <WXO_INSTANCE_URL>"
    echo "  orchestrate env activate my_env --api-key <WXO_API_KEY>"
    exit 1
fi

echo "== Importing tool package: $PKG_DIR (entry: $TOOL_FILE)"
orchestrate tools import -k python \
    -f "$TOOL_FILE" \
    -p "$PKG_DIR" \
    -r "$PKG_DIR/requirements.txt"

echo "== Importing agent: $AGENT_YAML"
orchestrate agents import -f "$AGENT_YAML"

echo "== Done. Verify with: orchestrate agents list"
