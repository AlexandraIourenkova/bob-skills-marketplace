"""zos-app-insight end to end: map, data dictionary, program and application docs, performance review.

Runs every skill's CLI in order on the original synthetic fixtures (fixtures/zos-app-insight,
see its README) in a temporary project, the way Bob runs them from the project root. It locks
the formats one skill writes and the next reads: app-map.json for all three, and DD.json
between dd.py and doc_context.py.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "packs" / "ibm" / "zos-app-insight" / "skills"
FIXTURES = Path(__file__).parent / "fixtures" / "zos-app-insight"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


zscan = load(SKILLS / "zos-app-map" / "scripts" / "zscan.py", "zos_flow_zscan")
dd = load(SKILLS / "zos-data-dictionary" / "scripts" / "dd.py", "zos_flow_dd")
doc = load(SKILLS / "zos-program-doc" / "scripts" / "doc_context.py", "zos_flow_doc")
perf = load(SKILLS / "cobol-perf-review" / "scripts" / "perf.py", "zos_flow_perf")

DESCRIBED = {
    "copy:CUSTREC::PFX:-CUSTOMER.:PFX:-BALANCE": "Amount the customer owes, in the account currency.",
    "prog:CUSTUPD:WS-FEE": "Fee charged on each order of the day.",
    "prog:CUSTUPD:WS-REJECTS": "Orders whose customer could not be read or updated.",
    "prog:CUSTUPD:WS-EOF": "End of the order file reached.",
}


def run(capsys, module, *argv) -> str:
    code = module.main(list(argv))
    out, err = capsys.readouterr()
    assert code == 0, (argv, out, err)
    return out


def files_outside_src(root: Path) -> list:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and not p.relative_to(root).as_posix().startswith("src/"))


def test_map_dictionary_docs_and_performance_in_order(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURES, root / "src")
    monkeypatch.chdir(root)

    # 1. map
    out = run(capsys, zscan, "map", "src/cobol", "src/jcl", "src/proclib", "src/legacy", "--copy-dir", "src/copy")
    assert "Programs: 5" in out

    # 2. data dictionary: build, describe from the queue, apply, approve three of four
    out = run(capsys, dd, "build")
    assert "Programs: 5 (unchanged 0, changed 0, new 5, removed 0)" in out
    run(capsys, dd, "queue", "--program", "CUSTUPD", "--limit", "100")
    queue = json.loads((root / "zos-insight" / "dd" / "queue.json").read_text(encoding="utf-8"))
    queued = {it["id"] for it in queue["items"]}
    assert set(DESCRIBED) <= queued, sorted(queued)
    descriptions = root / "zos-insight" / "dd" / "descriptions.json"
    descriptions.write_text(json.dumps({"source": "test-model", "descriptions": [
        {"id": key, "description": text} for key, text in DESCRIBED.items()]}), encoding="utf-8")
    out = run(capsys, dd, "apply", "zos-insight/dd/descriptions.json")
    assert "Proposed 4" in out
    approved = [k for k in DESCRIBED if k != "prog:CUSTUPD:WS-EOF"]
    out = run(capsys, dd, "approve", *approved, "--by", "analyst")
    assert "Approved 3" in out
    entries = json.loads((root / "zos-insight" / "dd" / "DD.json").read_text(encoding="utf-8"))["entries"]
    assert entries["copy:CUSTREC::PFX:-CUSTOMER.:PFX:-BALANCE"]["aliases"]["CUSTUPD"] == ["CU-BALANCE"]

    # 3. program context pack: the descriptions reach the items the program uses
    out = run(capsys, doc, "program", "CUSTUPD")
    assert "Wrote zos-insight/docs/context/CUSTUPD.json" in out
    pack = json.loads((root / "zos-insight" / "docs" / "context" / "CUSTUPD.json").read_text(encoding="utf-8"))
    items = {it["name"]: it for it in pack["data_items"]["items"]}
    assert items["CU-BALANCE"]["dd"] == {"description": DESCRIBED["copy:CUSTREC::PFX:-CUSTOMER.:PFX:-BALANCE"],
                                         "status": "approved"}
    assert items["WS-FEE"]["dd"] == {"description": DESCRIBED["prog:CUSTUPD:WS-FEE"], "status": "approved"}
    assert items["WS-REJECTS"]["dd"]["status"] == "approved"
    assert items["WS-EOF"]["dd"] == {"description": DESCRIBED["prog:CUSTUPD:WS-EOF"], "status": "proposed"}
    assert pack["data_dictionary"]["found"] is True and pack["data_dictionary"]["described"] == 4
    assert pack["data_dictionary"]["items_matched"] >= 4
    rule = next(c for c in pack["business_rule_candidates"] if isinstance(c, dict) and c["kind"] == "IF")
    assert rule["else_at"] == 58 and {d["name"] for d in rule["data_items"]} == {"END-OF-ORDERS"}
    assert [x["at"] for x in pack["error_handling"]["phrases"]] == [
        "CUSTUPD.cbl:38-43", "CUSTUPD.cbl:45-57", "CUSTUPD.cbl:49-52", "CUSTUPD.cbl:54-56"]
    # ORDMAIN copies CUSTREC with another prefix: the same copybook entry describes its CM-BALANCE
    run(capsys, doc, "program", "ORDMAIN")
    main_pack = json.loads((root / "zos-insight" / "docs" / "context" / "ORDMAIN.json").read_text(encoding="utf-8"))
    assert main_pack["data_dictionary"]["described"] == 4

    # 4. application context pack
    out = run(capsys, doc, "application")
    app_pack = json.loads((root / "zos-insight" / "docs" / "context" / "_application.json").read_text(encoding="utf-8"))
    assert app_pack["counts"]["programs"] == 5
    assert {c["name"] for c in app_pack["shared_copybooks"]} == {"CUSTREC", "ORDREC"}

    # 5. performance review
    out = run(capsys, perf, "scan", "--min-confidence", "low")
    assert "Wrote zos-insight/perf/findings.json and zos-insight/perf/report.md" in out
    findings = json.loads((root / "zos-insight" / "perf" / "findings.json").read_text(encoding="utf-8"))
    checks = {(f["program"], f["check"]) for f in findings["findings"]}
    assert ("ORDMAIN", "initialize-group-in-loop") in checks and ("ORDDB2", "sql-in-loop") in checks
    assert not any(f["program"] == "CUSTUPD" for f in findings["findings"])  # COMP-3 counters, no I/O open in the loop

    # every output is under zos-insight/, nothing beside the sources
    written = files_outside_src(root)
    assert written and all(p.startswith("zos-insight/") for p in written), written
    assert {"zos-insight/map/app-map.json", "zos-insight/dd/DD.json", "zos-insight/docs/context/CUSTUPD.json",
            "zos-insight/docs/context/_application.json", "zos-insight/perf/findings.json"} <= set(written)


def test_a_new_map_keeps_the_approved_descriptions(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURES, root / "src")
    monkeypatch.chdir(root)
    run(capsys, zscan, "map", "src/cobol", "--copy-dir", "src/copy")
    run(capsys, dd, "build")
    key = "copy:CUSTREC::PFX:-CUSTOMER.:PFX:-BALANCE"
    path = root / "zos-insight" / "dd" / "descriptions.json"
    path.write_text(json.dumps({"source": "test-model", "descriptions": [{"id": key, "description": DESCRIBED[key]}]}),
                    encoding="utf-8")
    run(capsys, dd, "apply", "zos-insight/dd/descriptions.json")
    run(capsys, dd, "approve", key)
    # the copybook gains a comment line: its fields move down one line
    cpy = root / "src" / "copy" / "CUSTREC.cpy"
    cpy.write_text("      * one more comment line\n" + cpy.read_text(encoding="utf-8"), encoding="utf-8")
    run(capsys, zscan, "map", "src/cobol", "--copy-dir", "src/copy")
    out = run(capsys, dd, "build")
    assert "changed" in out
    entry = json.loads((root / "zos-insight" / "dd" / "DD.json").read_text(encoding="utf-8"))["entries"][key]
    assert entry["status"] == "approved" and entry["line"] == 6 and not entry["stale"]
    run(capsys, doc, "program", "CUSTUPD")
    pack = json.loads((root / "zos-insight" / "docs" / "context" / "CUSTUPD.json").read_text(encoding="utf-8"))
    items = {it["name"]: it for it in pack["data_items"]["items"]}
    assert items["CU-BALANCE"]["dd"]["description"] == DESCRIBED[key]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
