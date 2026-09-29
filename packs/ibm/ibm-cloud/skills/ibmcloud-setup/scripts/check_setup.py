#!/usr/bin/env python3
"""Check that the IBM Cloud CLI is ready for the ibm-cloud pack.

Run:  python3 scripts/check_setup.py [--json]

Reports the CLI version, the plug-ins the pack uses, whether a session is open and what
it targets (account, region, resource group), and two environment settings that matter
for safety: whether an API key is available for login and whether API tracing is on.

Read-only. The script runs `ibmcloud version`, `ibmcloud plugin list` and `ibmcloud
target`, reads environment variables by name only, never logs in, never installs
anything and never prints the value of a key. Commands it suggests are for the user to
run after reading them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# plug-in name -> what needs it; container-registry is optional context for Code Engine
PLUGINS = {
    "vpc-infrastructure": "VPC reachability checks in ibmcloud-diagnose",
    "container-service": "cluster health checks in ibmcloud-diagnose",
    "code-engine": "Code Engine checks in ibmcloud-diagnose",
}
INSTALL_DOCS = "https://cloud.ibm.com/docs/cli?topic=cli-install-ibmcloud-cli"


class CliError(RuntimeError):
    pass


def refuse_tracing() -> None:
    """With IBMCLOUD_TRACE on, the CLI prints API traffic into the output; stop instead."""
    trace = os.environ.get("IBMCLOUD_TRACE", "")
    if trace and trace.lower() != "false":
        raise CliError("IBMCLOUD_TRACE is on, so the CLI would print API traffic; unset it in the shell and run again")


def run_cli(args: list[str], timeout: int = 60) -> str:
    refuse_tracing()
    proc = subprocess.run(["ibmcloud", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        text = (proc.stderr or proc.stdout).strip().splitlines()
        raise CliError(" ".join(line.strip() for line in text if line.strip() and line.strip() != "FAILED")[:300])
    return proc.stdout


def load_json(text: str):
    """The CLI can print a blank line or a status line before the JSON document."""
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise CliError("the CLI returned no JSON")
    return json.JSONDecoder().raw_decode(text[start:])[0]


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in m.groups()) if m else None


def installed_plugins(listing: list) -> dict[str, str]:
    """`ibmcloud plugin list --output json` -> {name: "1.54.2"}."""
    out = {}
    for item in listing or []:
        version = item.get("Version") or {}
        out[str(item.get("Name", ""))] = f"{version.get('Major', 0)}.{version.get('Minor', 0)}.{version.get('Build', 0)}"
    return out


def session(target: dict) -> dict:
    """`ibmcloud target --output json`; without a login the document has no account."""
    account = target.get("account") or {}
    group = target.get("resource_group") or {}
    return {
        "logged_in": bool(account.get("guid") or account.get("name")),
        "api_endpoint": target.get("api_endpoint", ""),
        "account": account.get("name", ""),
        "account_id": account.get("guid", ""),
        "region": (target.get("region") or {}).get("name", ""),
        "resource_group": group.get("name", ""),
    }


def environment() -> dict:
    trace = os.environ.get("IBMCLOUD_TRACE", "")
    return {
        "api_key_in_env": bool(os.environ.get("IBMCLOUD_API_KEY")),
        "trace_on": bool(trace) and trace.lower() != "false",
    }


def advice(state: dict) -> list[str]:
    """What the user should do next, in order. Commands are shown, never run."""
    notes = []
    if not state["cli"]:
        return [f"Install the IBM Cloud CLI from {INSTALL_DOCS}, then run this check again."]
    for name in state["missing_plugins"]:
        notes.append(f"Plug-in {name} is missing ({PLUGINS[name]}). The user can add it with: ibmcloud plugin install {name}")
    s = state["session"]
    if not s["logged_in"]:
        if state["env"]["api_key_in_env"]:
            notes.append("No session yet. IBMCLOUD_API_KEY is set, so the user can run `ibmcloud login` and the CLI reads the key from the environment.")
        else:
            notes.append("No session yet. On a federated (SSO) account the user runs `ibmcloud login --sso` in their own terminal and types the one-time passcode; the agent never handles it.")
    elif not s["resource_group"]:
        notes.append("No resource group is targeted; commands will cover only what the account-level view shows. Pick one with `ibmcloud target -g <group>` if the user works in a single group.")
    if s["api_endpoint"] and not s["api_endpoint"].startswith("https://"):
        notes.append(f"The API endpoint {s['api_endpoint']} is not HTTPS; stop and ask the user before any further command.")
    if state["env"]["trace_on"]:
        notes.append("IBMCLOUD_TRACE is on: the CLI prints API traffic, which can land in logs. The pack's scripts stop while it is on; the user unsets it in the shell.")
    return notes


def collect() -> dict:
    state: dict = {"cli": bool(shutil.which("ibmcloud")), "version": None, "plugins": {}, "missing_plugins": [],
                   "session": session({}), "env": environment(), "errors": []}
    if not state["cli"]:
        state["advice"] = advice(state)
        return state
    try:
        v = parse_version(run_cli(["version"]))
        state["version"] = ".".join(map(str, v)) if v else None
    except (CliError, subprocess.TimeoutExpired) as exc:
        state["errors"].append(f"ibmcloud version: {exc}")
    try:
        state["plugins"] = installed_plugins(load_json(run_cli(["plugin", "list", "--output", "json"])))
    except (CliError, subprocess.TimeoutExpired, ValueError) as exc:
        state["errors"].append(f"ibmcloud plugin list: {exc}")
    state["missing_plugins"] = [name for name in PLUGINS if name not in state["plugins"]]
    try:
        state["session"] = session(load_json(run_cli(["target", "--output", "json"])))
    except (CliError, subprocess.TimeoutExpired, ValueError) as exc:
        state["errors"].append(f"ibmcloud target: {exc}")
    state["advice"] = advice(state)
    return state


def render(state: dict) -> str:
    s = state["session"]
    lines = ["# IBM Cloud CLI check", ""]
    lines.append(f"- CLI: {'ibmcloud ' + (state['version'] or 'version unknown') if state['cli'] else 'not installed'}")
    if state["cli"]:
        have = ", ".join(f"{k} {v}" for k, v in sorted(state["plugins"].items())) or "none"
        lines.append(f"- Plug-ins: {have}")
    if s["logged_in"]:
        lines.append(f"- Session: account {s['account']} ({s['account_id']}), region {s['region'] or 'not set'}, "
                     f"resource group {s['resource_group'] or 'not set'}, endpoint {s['api_endpoint']}")
    else:
        lines.append("- Session: not logged in")
    lines.append(f"- API key in the environment: {'yes' if state['env']['api_key_in_env'] else 'no'}")
    lines.append(f"- API tracing: {'on' if state['env']['trace_on'] else 'off'}")
    if state["errors"]:
        lines += ["", "## Errors", *(f"- {e}" for e in state["errors"])]
    if state["advice"]:
        lines += ["", "## Next steps", *(f"{i}. {a}" for i, a in enumerate(state["advice"], 1))]
    else:
        lines += ["", "Ready: the CLI, the plug-ins and the session are in place."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="print the state as JSON")
    args = parser.parse_args(argv)
    state = collect()
    print(json.dumps(state, indent=2) if args.json else render(state))
    return 0 if state["cli"] and state["session"]["logged_in"] and not state["missing_plugins"] else 1


if __name__ == "__main__":
    sys.exit(main())
