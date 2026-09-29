"""The ibm-cloud pack's scripts against recorded CLI responses.

The plug-in list and the logged-out target are real CLI 2.43.0 output; the rest follow the
documented API shapes (Resource Controller, Global Search, VPC, Kubernetes Service v1 and
v2, Code Engine Knative and v2, Usage Reports). No test calls the real CLI.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "packs" / "ibm" / "ibm-cloud" / "skills"
FIXTURES = Path(__file__).parent / "fixtures" / "ibm-cloud"


def load(skill: str, script: str):
    path = SKILLS / skill / "scripts" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(f"ibmcloud_{script}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fx(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def fake_cli(responses: dict, module):
    """A run_cli stand-in: the first key that the command line starts with answers."""
    def run(args, timeout=0):
        line = " ".join(args)
        for prefix, answer in responses.items():
            if line.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise module.CliError(f"unexpected command: {line}")
    return run


# --------------------------------------------------------------------------- setup
def test_setup_reads_plugins_and_session() -> None:
    setup = load("ibmcloud-setup", "check_setup")
    plugins = setup.installed_plugins(fx("plugin-list"))
    assert plugins["vpc-infrastructure"] == "16.5.0" and plugins["code-engine"] == "1.54.2"
    assert setup.session(fx("target-logged-out"))["logged_in"] is False
    s = setup.session(fx("target-logged-in"))
    assert (s["logged_in"], s["account"], s["region"], s["resource_group"]) == (True, "Demo federated account", "us-south", "prod")
    assert setup.parse_version("ibmcloud 2.43.0+1da71311e-2026-04-21") == (2, 43, 0)


def test_setup_advice_never_asks_for_the_passcode(monkeypatch) -> None:
    setup = load("ibmcloud-setup", "check_setup")
    base = {"cli": True, "missing_plugins": ["code-engine"], "session": setup.session(fx("target-logged-out")),
            "env": {"api_key_in_env": False, "trace_on": True}}
    notes = " ".join(setup.advice(base))
    assert "ibmcloud plugin install code-engine" in notes and "login --sso" in notes and "own terminal" in notes
    assert "IBMCLOUD_TRACE" in notes
    with_key = {**base, "missing_plugins": [], "env": {"api_key_in_env": True, "trace_on": False}}
    assert "reads the key from the environment" in " ".join(setup.advice(with_key))


def test_scripts_stop_while_api_tracing_is_on(monkeypatch) -> None:
    """With IBMCLOUD_TRACE on the CLI would print API traffic into the output: no call is made."""
    monkeypatch.setenv("IBMCLOUD_TRACE", "true")
    for skill, script in (("ibmcloud-inventory", "inventory"), ("ibmcloud-diagnose", "vpc_reachability"), ("ibmcloud-cost", "usage_report")):
        module = load(skill, script)
        monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("the CLI ran with tracing on"))
        with pytest.raises(module.CliError, match="IBMCLOUD_TRACE"):
            module.run_cli(["resource", "groups", "--output", "json"])
    monkeypatch.setenv("IBMCLOUD_TRACE", "false")
    assert load("ibmcloud-setup", "check_setup").environment()["trace_on"] is False


# --------------------------------------------------------------------------- inventory
def test_inventory_normalises_and_flags() -> None:
    inv = load("ibmcloud-inventory", "inventory")
    assert inv.parse_crn("crn:v1:bluemix:public:codeengine:us-south:a/x:guid::") == {"service": "codeengine", "location": "us-south"}
    rows = inv.normalise(fx("service-instances"), inv.group_names(fx("resource-groups")), inv.tag_map(fx("search")))
    by_name = {r["name"]: r for r in rows}
    assert by_name["analytics-cos"]["findings"] == [] and by_name["analytics-cos"]["tags"] == ["env:prod", "owner:data"]
    assert by_name["orders-db"]["findings"] == ["untagged", "default resource group"]
    assert by_name["old-logs"]["findings"] == ["untagged", "state inactive", "resource group not visible"]
    summary = inv.summarise(rows)
    assert summary["instances"] == 4 and summary["findings"] == {"untagged": 2, "default resource group": 1, "state": 1, "resource group not visible": 1}


def test_inventory_run_writes_files_and_survives_search_refusal(tmp_path: Path, monkeypatch, capsys) -> None:
    inv = load("ibmcloud-inventory", "inventory")
    monkeypatch.setattr(inv, "run_cli", fake_cli({
        "resource groups": fx("resource-groups"),
        "resource service-instances": fx("service-instances"),
        "resource search": inv.CliError("Global Search is not available for this account"),
    }, inv))
    assert inv.main(["--out", str(tmp_path / "inv")]) == 0
    rows = list(csv.DictReader((tmp_path / "inv" / "inventory.csv").open()))
    assert len(rows) == 4 and all(r["tags"] == "" for r in rows)
    assert (tmp_path / "inv" / "raw" / "service-instances.json").is_file()
    assert "tags unknown" in capsys.readouterr().out


# --------------------------------------------------------------------------- VPC
def vpc(**override):
    docs = {"instance": fx("vpc-instance"), "nic": fx("vpc-nic"), "groups": [fx("vpc-sg")], "subnet": fx("vpc-subnet"), "acl": fx("vpc-acl")}
    docs.update(override)
    return docs


def verdicts(checks):
    return {c["check"]: c["result"] for c in checks}


def test_vpc_https_from_internet_passes() -> None:
    reach = load("ibmcloud-diagnose", "vpc_reachability")
    d = vpc()
    checks = reach.evaluate(d["instance"], d["nic"], d["groups"], d["subnet"], d["acl"], reach.net("0.0.0.0/0"), "tcp", 443, False)
    assert set(verdicts(checks).values()) == {"PASS"}


def test_vpc_ssh_from_internet_is_blocked_by_group_and_acl() -> None:
    reach = load("ibmcloud-diagnose", "vpc_reachability")
    d = vpc()
    checks = verdicts(reach.evaluate(d["instance"], d["nic"], d["groups"], d["subnet"], d["acl"], reach.net("203.0.113.7/32"), "tcp", 22, False))
    assert checks["security group inbound"] == "FAIL" and checks["network ACL in"] == "FAIL"
    private = verdicts(reach.evaluate(d["instance"], d["nic"], d["groups"], d["subnet"], d["acl"], reach.net("10.240.9.5/32"), "tcp", 22, False))
    assert private["security group inbound"] == "UNKNOWN"  # allowed for members of bastion-sg


def test_vpc_stateless_acl_drops_replies_and_missing_floating_ip() -> None:
    reach = load("ibmcloud-diagnose", "vpc_reachability")
    d = vpc(acl=fx("vpc-acl-tight-out"), nic={**fx("vpc-nic"), "floating_ips": []})
    checks = verdicts(reach.evaluate(d["instance"], d["nic"], d["groups"], d["subnet"], d["acl"], reach.net("0.0.0.0/0"), "tcp", 443, False))
    assert checks["network ACL in"] == "PASS" and checks["network ACL reply out"] == "FAIL"
    assert checks["public path"] == "FAIL"


def test_vpc_outbound_needs_a_public_gateway_or_floating_ip() -> None:
    reach = load("ibmcloud-diagnose", "vpc_reachability")
    d = vpc(nic={**fx("vpc-nic"), "floating_ips": []})
    no_path = verdicts(reach.evaluate(d["instance"], d["nic"], d["groups"], d["subnet"], d["acl"], reach.net("0.0.0.0/0"), "tcp", 443, True))
    assert no_path["public path"] == "FAIL" and no_path["security group outbound"] == "PASS"
    with_gateway = {**fx("vpc-subnet"), "public_gateway": {"id": "r006-pgw", "name": "pgw-1"}}
    ok = verdicts(reach.evaluate(d["instance"], d["nic"], d["groups"], with_gateway, d["acl"], reach.net("0.0.0.0/0"), "tcp", 443, True))
    assert ok["public path"] == "PASS"
    assert ok["network ACL reply in"] == "FAIL"  # deny-in drops replies to ephemeral ports


# --------------------------------------------------------------------------- clusters
def test_cluster_health_v2_finds_the_sick_worker_and_skew() -> None:
    health = load("ibmcloud-diagnose", "cluster_health")
    checks, bad = health.evaluate(fx("ks-cluster"), fx("ks-workers"))
    got = verdicts(checks)
    assert got["master"] == "PASS" and got["workers"] == "FAIL" and got["Ingress"] == "WARN"
    assert got["versions"] == "WARN" and got["updates"] == "WARN" and got["zones"] == "PASS"
    assert [w["id"] for w in bad] == ["kube-c0ffee1-w2"]


def test_cluster_health_reads_the_v1_shape() -> None:
    health = load("ibmcloud-diagnose", "cluster_health")
    checks, bad = health.evaluate(fx("ks-cluster-v1"), fx("ks-workers-v1"))
    got = verdicts(checks)
    assert got["cluster state"] == "PASS" and got["master"] == "PASS" and got["workers"] == "PASS" and not bad
    assert got["zones"] == "WARN"


# --------------------------------------------------------------------------- Code Engine
def test_code_engine_failed_revision_and_image_pull() -> None:
    ce = load("ibmcloud-diagnose", "code_engine_app")
    knative = ce.evaluate(fx("ce-app-knative"), fx("ce-events"))
    assert verdicts(knative["checks"]) == {"ready": "FAIL", "newest revision": "FAIL"}
    assert any("starts and exits" in h for h in knative["hints"])
    v2 = ce.evaluate(fx("ce-app-v2"), [])
    assert v2["app"]["state"] == "failed" and any("cannot be pulled" in h for h in v2["hints"])
    ready = ce.evaluate(fx("ce-app-ready"), [])
    assert verdicts(ready["checks"]) == {"ready": "PASS", "newest revision": "PASS"} and ready["hints"] == []


# --------------------------------------------------------------------------- cost
def test_cost_summary_changes_and_zero_usage() -> None:
    cost = load("ibmcloud-cost", "usage_report")
    cur = {"services": cost.service_costs(fx("billing-account")), "rows": cost.instance_rows(fx("billing-instances"), "2026-09"), "currency": "USD"}
    prev = {"services": None, "rows": cost.instance_rows(fx("billing-instances-prev"), "2026-08"), "currency": "USD"}
    s = cost.summarise("2026-09", cur, prev)
    assert s["total"] == 522.0 and s["by_service"][0] == ("Databases for PostgreSQL", 412.5)
    assert s["by_resource_group"] == {"Default": 412.5, "prod": 124.2}
    assert [z["instance"] for z in s["zero_usage"]] == ["reserved-vpn"]
    assert s["previous_total"] == 380.0
    assert s["instance_changes"][0] == ("orders-db", 300.0, 412.5, 112.5)
    assert cost.previous_month("2026-01") == "2025-12"


def test_cost_falls_back_when_the_account_report_is_refused(monkeypatch) -> None:
    cost = load("ibmcloud-cost", "usage_report")
    monkeypatch.setattr(cost, "run_cli", fake_cli({
        "billing account-usage": cost.CliError("You are not authorized to view the usage of this account. (account admin only)"),
        "billing resource-group-usage prod": {"currency_code": "USD", "resources": [
            {"resource_name": "Cloud Object Storage", "billable_cost": 88.2}]},
        "billing resource-instances-usage": fx("billing-instances"),
    }, cost))
    notes, raw = [], {}
    got = cost.fetch("2026-09", "prod", notes, raw)
    assert got["services"] == {"Cloud Object Storage": 88.2} and len(got["rows"]) == 3
    assert notes == ["account usage for 2026-09 not available: needs " + cost.NEEDS["account"]]
    assert set(raw) == {"group-2026-09", "instances-2026-09"}


def test_scripts_never_carry_write_verbs() -> None:
    """The pack is read-only in 1.0.0: no script invokes a command that changes the account."""
    from bob_skills import policy
    for script in SKILLS.glob("*/scripts/*.py"):
        text = script.read_text(encoding="utf-8")
        for pattern in policy.DESTRUCTIVE:
            assert not pattern.search(text), f"{script.name}: {pattern.pattern}"
        assert "--apikey" not in text and "--skip-ssl-validation" not in text
