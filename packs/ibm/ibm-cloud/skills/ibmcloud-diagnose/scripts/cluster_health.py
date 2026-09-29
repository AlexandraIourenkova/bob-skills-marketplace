#!/usr/bin/env python3
"""Health of an IBM Cloud Kubernetes Service or Red Hat OpenShift on IBM Cloud cluster.

Run:  python3 scripts/cluster_health.py --cluster NAME_OR_ID [--json]

Checks, each PASS, WARN or FAIL with its evidence: cluster state, master health and
status, Ingress, every worker's health and lifecycle, workers running a different version
than the master, pending updates, and how the workers spread across zones.

Read-only. The script runs `ibmcloud ks cluster get` and `ibmcloud ks worker ls` with
--output json and writes nothing. It never reloads, replaces or updates a worker: when a
fix needs one of those, the SKILL.md shows the command to the user first.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter


class CliError(RuntimeError):
    pass


def refuse_tracing() -> None:
    """With IBMCLOUD_TRACE on, the CLI prints API traffic into the output; stop instead."""
    trace = os.environ.get("IBMCLOUD_TRACE", "")
    if trace and trace.lower() != "false":
        raise CliError("IBMCLOUD_TRACE is on, so the CLI would print API traffic; unset it in the shell and run again")


def run_cli(args: list[str], timeout: int = 120):
    refuse_tracing()
    proc = subprocess.run(["ibmcloud", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        text = (proc.stderr or proc.stdout).strip().splitlines()
        raise CliError(" ".join(line.strip() for line in text if line.strip() and line.strip() != "FAILED")[:300])
    out = proc.stdout
    start = min((i for i in (out.find("{"), out.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise CliError("the CLI returned no JSON")
    return json.JSONDecoder().raw_decode(out[start:])[0]


def first(doc: dict, *paths: str, default=""):
    """First present value among dotted paths: the v2 API nests what v1 kept flat."""
    for path in paths:
        value = doc
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value not in (None, ""):
            return value
    return default


def worker_view(w: dict) -> dict:
    kube = w.get("kubeVersion")
    actual = first(kube, "actual") if isinstance(kube, dict) else (kube or "")
    target = (first(kube, "desired", "target") if isinstance(kube, dict) else first(w, "targetVersion")) or actual
    return {
        "id": w.get("id", ""),
        "zone": first(w, "location", "zone"),
        "pool": first(w, "poolName"),
        "health": str(first(w, "health.state", "state", default="unknown")).lower(),
        "lifecycle": str(first(w, "lifecycle.actualState", "status", default="")).lower(),
        "message": first(w, "health.message", "lifecycle.message", "status"),
        "version": actual,
        "target": target,
    }


def evaluate(cluster: dict, workers: list[dict]) -> tuple[list[dict], list[dict]]:
    checks = []
    def add(name: str, verdict: str, detail: str) -> None:
        checks.append({"check": name, "result": verdict, "detail": detail})

    state = str(first(cluster, "state", default="unknown")).lower()
    add("cluster state", "PASS" if state == "normal" else "WARN" if state in {"deploying", "pending", "updating", "warning"} else "FAIL",
        f"{state}; {first(cluster, 'status', default='no status text')}")

    health = str(first(cluster, "lifecycle.masterHealth", "masterHealth", default="unknown")).lower()
    status = first(cluster, "lifecycle.masterStatus", "masterStatus", default="unknown")
    add("master", "PASS" if health == "normal" and str(status).lower() == "ready" else "FAIL",
        f"health {health}, status {status}, state {first(cluster, 'lifecycle.masterState', 'masterState', default='unknown')}")

    ingress = str(first(cluster, "ingress.status", "ingressStatus", default="")).lower()
    if ingress:
        add("Ingress", "PASS" if ingress in {"healthy", "normal"} else "WARN",
            f"{ingress}: {first(cluster, 'ingress.message', 'ingressMessage', default='no message')}")

    views = [worker_view(w) for w in workers]
    bad = [v for v in views if v["health"] != "normal" or (v["lifecycle"] and v["lifecycle"] not in {"deployed", "ready"})]
    counts = Counter(v["health"] for v in views)
    add("workers", "PASS" if views and not bad else "FAIL" if bad else "WARN",
        f"{len(views)} workers: " + ", ".join(f"{k} {n}" for k, n in counts.most_common()) if views else "no workers returned")

    master_version = str(first(cluster, "masterKubeVersion", "masterVersion", default=""))
    behind = [v for v in views if v["version"] and master_version and v["version"].split("_")[0] != master_version.split("_")[0]]
    if behind:
        add("versions", "WARN", f"{len(behind)} workers run {sorted({v['version'] for v in behind})} while the master runs {master_version}")
    pending = [v for v in views if v["target"] and v["version"] and v["target"] != v["version"]]
    target = first(cluster, "targetVersion", default="")
    if pending or (target and master_version and target != master_version):
        add("updates", "WARN", f"master {master_version} -> {target or master_version}; {len(pending)} workers have an update pending")
    zones = Counter(v["zone"] for v in views if v["zone"])
    if views:
        add("zones", "PASS" if len(zones) > 1 else "WARN",
            ", ".join(f"{z} {n}" for z, n in sorted(zones.items())) + ("" if len(zones) > 1 else "; a zone outage takes the whole cluster down"))
    return checks, bad


def render(cluster: dict, checks: list[dict], bad: list[dict]) -> str:
    title = f"{first(cluster, 'name')} ({first(cluster, 'type', 'provider', default='cluster')}, {first(cluster, 'masterKubeVersion', default='?')})"
    lines = [f"# Cluster health: {title}", "", "| Check | Result | Evidence |", "|---|---|---|"]
    lines += [f"| {c['check']} | {c['result']} | {c['detail']} |" for c in checks]
    if bad:
        lines += ["", "| Worker | Zone | Pool | Health | Lifecycle | Message |", "|---|---|---|---|---|---|"]
        lines += [f"| {v['id']} | {v['zone']} | {v['pool']} | {v['health']} | {v['lifecycle']} | {v['message']} |" for v in bad]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cluster", required=True, help="cluster name or ID")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        cluster = run_cli(["ks", "cluster", "get", "--cluster", args.cluster, "--output", "json"])
        workers = run_cli(["ks", "worker", "ls", "--cluster", args.cluster, "--output", "json"])
    except (CliError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    workers = workers if isinstance(workers, list) else workers.get("workers", [])
    checks, bad = evaluate(cluster, workers)
    print(json.dumps({"checks": checks, "unhealthy_workers": bad}, indent=2) if args.json else render(cluster, checks, bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
