#!/usr/bin/env python3
"""Why a VPC virtual server cannot be reached on a port, or cannot reach out.

Run:  python3 scripts/vpc_reachability.py --instance NAME_OR_ID --port 443 [--protocol tcp]
                                          [--source 203.0.113.7/32] [--outbound 0.0.0.0/0] [--json]

Inbound (default): can traffic from --source (default 0.0.0.0/0, the internet) reach the
instance's primary interface on --port? Outbound (--outbound DEST): can the instance open a
connection to DEST on --port?

The checks, each reported as PASS, FAIL or UNKNOWN with the rule that decided it:
  1. the instance is running
  2. a public path exists when the peer is public: a floating IP on the interface for
     inbound, a floating IP or a public gateway on the subnet for outbound
  3. a security group on the interface allows the traffic (security groups are stateful)
  4. the subnet's network ACL allows the traffic in and the reply out, or out and back in:
     ACLs are stateless and evaluated rule by rule, first match wins
Load balancers, VPN, Transit Gateway, custom routes and endpoint gateways are not checked.

Read-only. The script runs `ibmcloud is instance`, `instance-network-interface`,
`security-group`, `subnet` and `network-acl`, all with --output JSON, and writes nothing.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys

EPHEMERAL = (1024, 65535)
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "161.26.0.0/16", "166.8.0.0/14")]
ANY_PROTOCOL = {"all", "any"}


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


# --------------------------------------------------------------------------- matching
def net(value: str):
    return ipaddress.ip_network(value, strict=False)


def covers(rule_cidr: str | None, peer) -> bool:
    """True when the rule's CIDR contains the whole peer network."""
    if not rule_cidr:
        return False
    block = net(rule_cidr)
    return block.version == peer.version and peer.subnet_of(block)


def protocol_matches(rule_protocol: str | None, protocol: str) -> bool:
    p = (rule_protocol or "all").lower()
    return p in ANY_PROTOCOL or p == protocol or (p == "icmp_tcp_udp" and protocol in {"icmp", "tcp", "udp"})


def in_range(low, high, port: int) -> bool:
    return (low is None and high is None) or ((low or 1) <= port <= (high or 65535))


def spans(low, high, span: tuple[int, int]) -> bool:
    return (low is None and high is None) or ((low or 1) <= span[0] and span[1] <= (high or 65535))


def is_public(peer) -> bool:
    return not any(peer.version == p.version and peer.subnet_of(p) for p in PRIVATE)


# --------------------------------------------------------------------------- the checks
def sg_decision(groups: list[dict], direction: str, peer, protocol: str, port: int) -> tuple[str, str]:
    """Security groups allow when any rule of any group on the interface matches."""
    members_only = []
    for group in groups:
        for rule in group.get("rules") or []:
            if rule.get("direction") != direction or not protocol_matches(rule.get("protocol"), protocol):
                continue
            if protocol in {"tcp", "udp"} and not in_range(rule.get("port_min"), rule.get("port_max"), port):
                continue
            remote = rule.get("remote") or {}
            cidr = remote.get("cidr_block") or (remote.get("address") and f"{remote['address']}/32")
            if cidr and covers(cidr, peer):
                return "PASS", f"{group.get('name')}: {direction} {rule.get('protocol')} {describe_ports(rule)} from {cidr}"
            if not cidr and remote.get("name"):
                members_only.append(f"{group.get('name')} allows members of security group {remote['name']}")
    detail = f"no {direction} rule in {', '.join(g.get('name', '?') for g in groups) or 'any group'} covers {peer} {protocol}/{port}"
    if members_only:
        detail += "; " + "; ".join(members_only)
        if not is_public(peer):  # a private peer may be a member; the CLI output cannot tell
            return "UNKNOWN", detail + " (check whether the peer's interface is in that group)"
    return "FAIL", detail


def acl_decision(rules: list[dict], direction: str, peer_field: str, peer, local, protocol: str,
                 dest_port: int | tuple[int, int], src_port: int | tuple[int, int]) -> tuple[str, str]:
    """First matching rule decides; no match means the implicit deny. The rule's other side
    (destination for inbound, source for outbound) must cover the instance's own address."""
    local_field = "destination" if peer_field == "source" else "source"
    for rule in rules:
        if rule.get("direction") != direction or not protocol_matches(rule.get("protocol"), protocol):
            continue
        if not covers(rule.get(peer_field) or "0.0.0.0/0", peer):
            continue
        if local is not None and not covers(rule.get(local_field) or "0.0.0.0/0", local):
            continue
        if protocol in {"tcp", "udp"}:
            if not port_fits(rule.get("destination_port_min"), rule.get("destination_port_max"), dest_port):
                continue
            if not port_fits(rule.get("source_port_min"), rule.get("source_port_max"), src_port):
                continue
        verdict = "PASS" if rule.get("action") == "allow" else "FAIL"
        return verdict, f"rule {rule.get('name') or rule.get('id')}: {rule.get('action')} {direction} {rule.get('protocol')} {peer_field} {rule.get(peer_field)}"
    return "FAIL", f"no {direction} rule matches, so the ACL's implicit deny applies"


def port_fits(low, high, port) -> bool:
    return spans(low, high, port) if isinstance(port, tuple) else in_range(low, high, port)


def describe_ports(rule: dict) -> str:
    low, high = rule.get("port_min"), rule.get("port_max")
    return "all ports" if low is None and high is None else (str(low) if low == high else f"{low}-{high}")


def evaluate(instance: dict, nic: dict, groups: list[dict], subnet: dict, acl: dict,
             peer, protocol: str, port: int, outbound: bool) -> list[dict]:
    checks = []
    def add(name: str, verdict: str, detail: str) -> None:
        checks.append({"check": name, "result": verdict, "detail": detail})

    status = instance.get("status", "unknown")
    reasons = "; ".join(r.get("message", "") for r in instance.get("status_reasons") or [])
    add("instance running", "PASS" if status == "running" else "FAIL", f"status {status}" + (f" ({reasons})" if reasons else ""))

    fips = [f.get("address") for f in nic.get("floating_ips") or []]
    gateway = (subnet.get("public_gateway") or {}).get("name")
    if not is_public(peer):
        add("public path", "PASS", f"{peer} is a private range; no floating IP needed")
    elif outbound:
        ok = bool(fips or gateway)
        add("public path", "PASS" if ok else "FAIL",
            f"floating IP {', '.join(fips)}" if fips else f"public gateway {gateway} on subnet {subnet.get('name')}" if gateway
            else f"no floating IP on {nic.get('name')} and no public gateway on subnet {subnet.get('name')}")
    else:
        add("public path", "PASS" if fips else "FAIL",
            f"floating IP {', '.join(fips)}" if fips else
            f"no floating IP on {nic.get('name')}; a public gateway only carries outbound traffic")

    direction = "outbound" if outbound else "inbound"
    add(f"security group {direction}", *sg_decision(groups, direction, peer, protocol, port))

    rules = acl.get("rules") or []
    address = (nic.get("primary_ip") or {}).get("address")
    local = net(f"{address}/32") if address else None
    if protocol == "icmp":
        dest_first, src_first, dest_back, src_back = port, port, port, port
    else:
        dest_first, src_first, dest_back, src_back = port, EPHEMERAL, EPHEMERAL, port
    if outbound:
        add("network ACL out", *acl_decision(rules, "outbound", "destination", peer, local, protocol, dest_first, src_first))
        add("network ACL reply in", *acl_decision(rules, "inbound", "source", peer, local, protocol, dest_back, src_back))
    else:
        add("network ACL in", *acl_decision(rules, "inbound", "source", peer, local, protocol, dest_first, src_first))
        add("network ACL reply out", *acl_decision(rules, "outbound", "destination", peer, local, protocol, dest_back, src_back))
    return checks


# --------------------------------------------------------------------------- CLI
def collect(instance_ref: str) -> dict:
    instance = run_cli(["is", "instance", instance_ref, "--output", "JSON"])
    primary = instance.get("primary_network_interface")
    if not primary:
        raise CliError("the instance uses network attachments (virtual network interfaces); this check covers "
                       "network interfaces only. Inspect it with `ibmcloud is instance-network-attachments`.")
    nic = run_cli(["is", "instance-network-interface", instance["id"], primary["id"], "--output", "JSON"])
    groups = [run_cli(["is", "security-group", g["id"], "--output", "JSON"]) for g in nic.get("security_groups") or []]
    subnet = run_cli(["is", "subnet", (nic.get("subnet") or primary.get("subnet"))["id"], "--output", "JSON"])
    acl = run_cli(["is", "network-acl", subnet["network_acl"]["id"], "--output", "JSON"])
    return {"instance": instance, "nic": nic, "groups": groups, "subnet": subnet, "acl": acl}


def render(docs: dict, checks: list[dict], peer, protocol: str, port: int, outbound: bool) -> str:
    inst, nic = docs["instance"], docs["nic"]
    ip = (nic.get("primary_ip") or {}).get("address", "?")
    where = f"{inst.get('name')} ({ip}) -> {peer} {protocol}/{port}" if outbound else f"{peer} -> {inst.get('name')} ({ip}) {protocol}/{port}"
    lines = [f"# VPC reachability: {where}", "", "| Check | Result | Evidence |", "|---|---|---|"]
    lines += [f"| {c['check']} | {c['result']} | {c['detail']} |" for c in checks]
    failed = [c["check"] for c in checks if c["result"] == "FAIL"]
    lines += ["", f"Blocked by: {', '.join(failed)}." if failed else "Nothing in these layers blocks the traffic; look at the application, the OS firewall, or a load balancer in front."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instance", required=True, help="virtual server instance name or ID")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--protocol", default="tcp", choices=["tcp", "udp", "icmp"])
    parser.add_argument("--source", default="0.0.0.0/0", help="who connects, for the inbound check (default: the internet)")
    parser.add_argument("--outbound", metavar="DEST", help="check the instance reaching DEST instead")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        peer = net(args.outbound or args.source)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        docs = collect(args.instance)
    except (CliError, subprocess.TimeoutExpired, KeyError, TypeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    checks = evaluate(docs["instance"], docs["nic"], docs["groups"], docs["subnet"], docs["acl"],
                      peer, args.protocol, args.port, bool(args.outbound))
    print(json.dumps(checks, indent=2) if args.json else render(docs, checks, peer, args.protocol, args.port, bool(args.outbound)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
