"""zos-app-insight, skill zos-data-dictionary: dd.py (data dictionary from app-map.json).

The map comes from zscan.scan on the original synthetic fixtures under
fixtures/zos-app-insight, copied to a temporary project. One more small program,
written below, copies the same copybooks as ORDMAIN so that shared fields have two users.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "packs" / "ibm" / "zos-app-insight" / "skills" / "zos-data-dictionary" / "scripts" / "dd.py"
FIXTURES = Path(__file__).parent / "fixtures" / "zos-app-insight"


def _load():
    spec = importlib.util.spec_from_file_location("zos_dd", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dd = _load()
zscan = dd.zscan  # the copy dd.py imported, so that its exception classes match

ROOTS = ["src/cobol", "src/jcl", "src/proclib"]
COPY = ["src/copy"]

# A second user of ORDREC, CUSTREC (with another REPLACING prefix) and WSCOMMON.
BILLRPT = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BILLRPT.
      *  Test program: shares copybooks with ORDMAIN.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ORDER-FILE ASSIGN TO ORDIN.
       DATA DIVISION.
       FILE SECTION.
       FD  ORDER-FILE.
           COPY ORDREC.
       WORKING-STORAGE SECTION.
           COPY CUSTREC REPLACING ==:PFX:== BY ==BR==.
           COPY WSCOMMON OF COMMLIB.
       01  BR-TOTAL                PIC S9(9)V99 COMP-3 VALUE ZERO.
       01  WS-MSG                  PIC X(40).
       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT ORDER-FILE.
           READ ORDER-FILE
               AT END CONTINUE
           END-READ.
           MOVE OR-CUST-ID TO BR-CUST-ID.
           IF BR-ACTIVE
               ADD BR-BALANCE TO BR-TOTAL
           END-IF.
           MOVE WS-TODAY-YYYY OF WS-TODAY TO WS-RUN-DATE.
           MOVE 'BILLING DONE' TO WS-MSG.
           CLOSE ORDER-FILE.
           GOBACK.
"""


def make_project(root: Path) -> Path:
    shutil.copytree(FIXTURES, root / "src")
    (root / "src" / "cobol" / "BILLRPT.cbl").write_text(BILLRPT, encoding="utf-8")
    return root


def scan(root: Path) -> dict:
    return zscan.scan(ROOTS, COPY, root=root)


@pytest.fixture()
def project(tmp_path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = make_project(tmp_path_factory.mktemp("dd") / "proj")
    app_map = scan(root)
    doc, report = dd.build(app_map, None, root=root)
    return root, app_map, doc, report


def entry(doc: dict, key: str) -> dict:
    assert key in doc["entries"], sorted(doc["entries"])
    return doc["entries"][key]


def uses(e: dict, program: str = None) -> list:
    return [(u["program"], u["line"], u["verb"]) for u in e["used_in"] if program is None or u["program"] == program]


def describe(doc: dict, key: str, text: str = "Customer number the order belongs to.", source: str = "test-model"):
    return dd.apply_descriptions(doc, {"source": source, "descriptions": [{"id": key, "description": text}]})


# --------------------------------------------------------------------------- build
def test_shared_copybook_field_is_one_entry_with_every_user(built) -> None:
    _, _, doc, report = built
    assert sorted(report["new"]) == ["BILLRPT", "CUSTUPD", "ORDCICS", "ORDDB2", "ORDMAIN", "PRICECAL"]
    e = entry(doc, "copy:ORDREC:ORDER-RECORD.OR-CUST-ID")
    assert e["scope"] == "copybook" and e["copybook"] == "ORDREC" and e["owner"] == "ORDREC"
    assert e["programs"] == ["BILLRPT", "CUSTUPD", "ORDMAIN"]
    assert e["file"] == "src/copy/ORDREC.cpy" and e["line"] == 4
    assert e["parents"] == ["ORDER-RECORD"] and e["parent_id"] == "copy:ORDREC:ORDER-RECORD"
    assert e["pic"] == "X(8)" and e["section"] == "FILE"
    assert set(e["built_from"]) == {"BILLRPT", "CUSTUPD", "ORDMAIN"} and all(len(v) == 64 for v in e["built_from"].values())
    assert ("BILLRPT", 23, "MOVE") in uses(e)
    assert sum(1 for k in doc["entries"] if k.endswith(":ORDER-RECORD.OR-CUST-ID")) == 1
    # the record is the FD record of both programs
    roles = {(r["program"], r["role"]) for r in entry(doc, "copy:ORDREC:ORDER-RECORD")["roles"]}
    assert ("ORDMAIN", "record of file ORDER-FILE (DD ORDIN)") in roles and ("BILLRPT", "record of file ORDER-FILE (DD ORDIN)") in roles


def test_replacing_copies_share_the_copybook_spelling(built) -> None:
    _, _, doc, _ = built
    e = entry(doc, "copy:CUSTREC::PFX:-CUSTOMER.:PFX:-STATUS")
    assert e["name"] == ":PFX:-STATUS"
    assert e["aliases"] == {"BILLRPT": ["BR-STATUS"], "CUSTUPD": ["CU-STATUS"], "ORDMAIN": ["CM-STATUS"]}
    assert e["programs"] == ["BILLRPT", "CUSTUPD", "ORDMAIN"]
    assert e["conditions"] == [{"name": ":PFX:-ACTIVE", "value": "'A'", "line": 7}]
    used = [u for u in e["used_in"] if u["program"] == "BILLRPT"]
    assert used and used[0]["verb"] == "IF" and used[0]["via"] == "BR-ACTIVE" and used[0]["as"] == "BR-STATUS"
    key = entry(doc, "copy:CUSTREC::PFX:-CUSTOMER.:PFX:-CUST-ID")
    assert {(r["program"], r["role"]) for r in key["roles"]} == {("ORDMAIN", "RECORD KEY of CUST-FILE"),
                                                                ("CUSTUPD", "RECORD KEY of CUST-FILE")}
    assert ("BILLRPT", 23, "MOVE") in uses(key)
    assert not any(k.startswith("copy:CUSTREC:CM-") or k.startswith("copy:CUSTREC:BR-") for k in doc["entries"])


def test_program_local_fields_88_levels_occurs_and_redefines(built) -> None:
    _, _, doc, _ = built
    st = entry(doc, "prog:ORDMAIN:WS-STATUS-FIELDS.WS-ORD-STATUS")
    assert st["scope"] == "program" and st["programs"] == ["ORDMAIN"] and st["copybook"] is None
    assert [(c["name"], c["value"]) for c in st["conditions"]] == [("ORD-OK", "'00'"), ("ORD-EOF", "'10'")]
    vias = {(u["line"], u["verb"], u.get("via")) for u in st["used_in"]}
    assert {(67, "PERFORM", "ORD-EOF"), (75, "IF", "ORD-OK"), (85, "SET", "ORD-EOF")} <= vias
    assert not any(k.endswith("ORD-EOF") or k.endswith("ORD-OK") for k in doc["entries"])  # 88s are not entries
    assert {r["role"] for r in st["roles"]} == {"FILE STATUS of ORDER-FILE"}

    rate = entry(doc, "prog:ORDMAIN:WS-RATE-TABLE.RATE-ENTRY")
    assert rate["occurs"] == {"min": 50, "max": 50, "depending_on": None,
                              "keys": [{"name": "RATE-CODE", "order": "ascending"}], "indexed_by": ["RATE-IX"]}
    assert rate["children"] == ["RATE-CODE", "RATE-PCT"]
    assert {r["role"] for r in entry(doc, "prog:ORDMAIN:WS-RATE-TABLE.RATE-ENTRY.RATE-CODE")["roles"]} == {
        "ASCENDING KEY of table RATE-ENTRY"}
    line = entry(doc, "prog:ORDMAIN:WS-ORDER-LINES.WS-LINE")
    assert line["occurs"]["min"] == 1 and line["occurs"]["max"] == 20 and line["occurs"]["depending_on"] == "WS-LINE-COUNT"
    assert "OCCURS DEPENDING ON of WS-LINE" in {r["role"] for r in entry(doc, "prog:ORDMAIN:WS-COUNTERS.WS-LINE-COUNT")["roles"]}
    red = entry(doc, "prog:ORDMAIN:WS-AMOUNTS.WS-AMOUNT-X")
    assert red["redefines"] == "WS-LINE-AMOUNT" and red["pic"] == "X(9)"
    amount = entry(doc, "prog:ORDMAIN:WS-AMOUNTS.WS-LINE-AMOUNT")
    assert [(u["line"], u["verb"]) for u in amount["used_in"]] == [(114, "MOVE"), (116, "COMPUTE"), (119, "ADD")]
    # the same name in two programs gives two entries
    assert entry(doc, "prog:PRICECAL:LK-TOTAL")["programs"] == ["PRICECAL"]
    assert {r["role"] for r in entry(doc, "prog:PRICECAL:LK-TOTAL")["roles"]} == {
        "PROCEDURE DIVISION USING: passed in by the caller"}
    for e in doc["entries"].values():
        assert e["status"] == "none" and e["description"] is None and e["stale"] is False


def test_where_used_covers_when_sql_cics_and_qualification(built) -> None:
    _, _, doc, _ = built
    assert ("ORDMAIN", 100, "WHEN") in uses(entry(doc, "copy:ORDREC:ORDER-RECORD.OR-PRIORITY"))
    assert ("ORDMAIN", 115, "SEARCH-WHEN") in uses(entry(doc, "copy:ORDREC:ORDER-RECORD.OR-RATE-CODE"))
    assert uses(entry(doc, "prog:ORDDB2:WS-CUST-ID")) == [
        ("ORDDB2", 25, "EXEC SQL FETCH"), ("ORDDB2", 31, "EXEC SQL SELECT"), ("ORDDB2", 36, "EXEC SQL INSERT")]
    cics = entry(doc, "prog:ORDCICS:WS-CUST-KEY")["used_in"]
    assert [(u["verb"], u["option"]) for u in cics] == [("EXEC CICS READ", "RIDFLD")]
    yyyy = entry(doc, "copy:DATEWS:WS-TODAY.WS-TODAY-YYYY")
    assert ("BILLRPT", 27, "MOVE") in uses(yyyy)
    assert not uses(entry(doc, "copy:DATEWS:WS-TODAY"), "BILLRPT")  # a qualifier is not a use
    assert entry(doc, "copy:DATEWS:WS-TODAY")["parent_id"] is None  # the group around it is WSCOMMON's
    assert [d["parents"] for d in entry(doc, "copy:DATEWS:WS-TODAY")["declared_in"]] == [["WS-COMMON"], ["WS-COMMON"]]


def test_unresolved_copybooks_are_named(built) -> None:
    _, _, doc, _ = built
    assert doc["unresolved_copybooks"] == [{"name": "AUDITREC", "programs": ["ORDMAIN"]}]
    assert doc["programs"]["ORDMAIN"]["partial"] is True
    lines = dd.status_lines(doc, dd.summary(doc))
    assert any("AUDITREC" in x and "unknown, not absent" in x for x in lines)


def test_copybook_spelling_comes_from_the_map_not_the_copybook_file(tmp_path) -> None:
    root = make_project(tmp_path / "proj")
    app_map = scan(root)
    (root / "src" / "copy" / "CUSTREC.cpy").unlink()  # dd.py no longer reads copybook lines for names
    doc, _ = dd.build(app_map, None, root=root)
    e = entry(doc, "copy:CUSTREC::PFX:-CUSTOMER.:PFX:-STATUS")
    assert e["aliases"]["ORDMAIN"] == ["CM-STATUS"] and e["aliases"]["CUSTUPD"] == ["CU-STATUS"]


# --------------------------------------------------------------------------- incremental build
def test_incremental_rebuild_keeps_unchanged_and_approved_and_marks_stale(project) -> None:
    first, _ = dd.build(scan(project), None, root=project)
    describe(first, "prog:PRICECAL:WS-DISCOUNT", "Volume discount rate taken off large order totals.")
    describe(first, "prog:PRICECAL:LK-TOTAL", "Order total passed in by the caller and reduced by the discount.")
    describe(first, "copy:ORDREC:ORDER-RECORD.OR-CUST-ID")
    dd.approve(first, ["prog:PRICECAL:WS-DISCOUNT", "prog:PRICECAL:LK-TOTAL"], by="analyst")
    before = json.loads(json.dumps(first))

    src = project / "src" / "cobol" / "PRICECAL.cbl"
    text = src.read_text(encoding="utf-8")
    text = text.replace("000060 01  WS-DISCOUNT             PIC V99 VALUE .05.\n",
                        "000060 01  WS-RATE                 PIC V99 VALUE .05.\n")
    text = text.replace("(1 - WS-DISCOUNT)", "(1 - WS-RATE)")
    text = text.replace("01  LK-TOTAL                PIC S9(9)V99 COMP-3.", "01  LK-TOTAL                PIC S9(11)V99 COMP-3.")
    src.write_text(text, encoding="utf-8")
    (project / "src" / "cobol" / "ORDCICS.cbl").unlink()

    second, report = dd.build(scan(project), first, root=project)
    assert report["changed"] == ["PRICECAL"] and report["removed"] == ["ORDCICS"]
    assert sorted(report["unchanged"]) == ["BILLRPT", "CUSTUPD", "ORDDB2", "ORDMAIN"]
    for pid in ("ORDMAIN", "ORDDB2", "BILLRPT", "CUSTUPD"):
        assert second["programs"][pid] == before["programs"][pid]
        for key, e in before["entries"].items():
            if pid in e["programs"]:
                assert second["entries"][key] == e, key

    gone = second["entries"]["prog:PRICECAL:WS-DISCOUNT"]
    assert gone["stale"] is True and gone["stale_since"]
    assert gone["status"] == "approved" and gone["description"] == "Volume discount rate taken off large order totals."
    total = second["entries"]["prog:PRICECAL:LK-TOTAL"]
    assert total["pic"] == "S9(11)V99" and total["status"] == "approved"
    assert total["description"] == "Order total passed in by the caller and reduced by the discount."
    assert total["review"]["fields"] == ["pic"]
    new = second["entries"]["prog:PRICECAL:WS-RATE"]
    assert new["status"] == "none" and new["stale"] is False
    for key in before["entries"]:
        if key.startswith("prog:ORDCICS:"):
            assert second["entries"][key]["stale"] is True
    assert second["entries"]["copy:ORDREC:ORDER-RECORD.OR-CUST-ID"]["status"] == "proposed"
    assert report["entries"]["newly_stale"] == 1 + sum(1 for k in before["entries"] if k.startswith("prog:ORDCICS:"))

    third, report3 = dd.build(scan(project), second, root=project)
    assert sorted(report3["unchanged"]) == ["BILLRPT", "CUSTUPD", "ORDDB2", "ORDMAIN", "PRICECAL"]
    assert third["entries"] == second["entries"]
    assert report3["entries"]["newly_stale"] == 0

    full, report_full = dd.build(scan(project), third, root=project, full=True)
    assert report_full["unchanged"] == [] and full["entries"] == third["entries"]


def test_build_never_overwrites_an_approved_description(project) -> None:
    doc, _ = dd.build(scan(project), None, root=project)
    describe(doc, "prog:ORDMAIN:WS-MSG", "Report line text.")
    dd.approve(doc, ["prog:ORDMAIN:WS-MSG"])
    (project / "src" / "cobol" / "ORDMAIN.cbl").write_text(
        (project / "src" / "cobol" / "ORDMAIN.cbl").read_text(encoding="utf-8").replace(
            "006000 01  WS-MSG                  PIC X(80).", "006000 01  WS-MSG                  PIC X(90)."),
        encoding="utf-8")
    again, report = dd.build(scan(project), doc, root=project)
    assert report["changed"] == ["ORDMAIN"]
    e = again["entries"]["prog:ORDMAIN:WS-MSG"]
    assert (e["status"], e["description"], e["pic"]) == ("approved", "Report line text.", "X(90)")
    assert e["review"]["fields"] == ["pic"]
    res = dd.approve(again, ["prog:ORDMAIN:WS-MSG"])  # the user confirms it still holds
    assert res == {"approved": [], "confirmed": ["prog:ORDMAIN:WS-MSG"], "already": []}
    assert again["entries"]["prog:ORDMAIN:WS-MSG"]["review"] is None
    assert dd.approve(again, ["prog:ORDMAIN:WS-MSG"])["already"] == ["prog:ORDMAIN:WS-MSG"]


# --------------------------------------------------------------------------- queue
def test_queue_limit_context_and_filters(built) -> None:
    root, app_map, doc, _ = built
    doc = json.loads(json.dumps(doc))
    total = sum(1 for e in doc["entries"].values() if e["status"] == "none")
    q = dd.make_queue(doc, app_map, root=root, limit=5)
    assert (q["total"], q["shown"], q["remaining"]) == (total, 5, total - 5)
    assert "not instructions" in q["note"] and q["write_to"] == "zos-insight/dd/descriptions.json"

    q = dd.make_queue(doc, app_map, root=root, limit=100, refs=2, program="ORDMAIN")
    assert all("ORDMAIN" in it["programs"] for it in q["items"]) and q["remaining"] == 0
    item = next(it for it in q["items"] if it["id"] == "prog:ORDMAIN:WS-STATUS-FIELDS.WS-ORD-STATUS")
    assert item["pic"] == "XX" and item["usage"] == "DISPLAY (default)" and item["value"] == "SPACES"
    assert [c["name"] for c in item["conditions"]] == ["ORD-OK", "ORD-EOF"]
    assert item["parent"] == {"id": "prog:ORDMAIN:WS-STATUS-FIELDS", "name": "WS-STATUS-FIELDS", "description": None}
    assert item["roles"] == ["ORDMAIN: FILE STATUS of ORDER-FILE"]
    assert item["used_in_total"] == 4 and len(item["used_in"]) == 2
    first = item["used_in"][0]
    assert first["file"] == "src/cobol/ORDMAIN.cbl" and first["via"] == "ORD-EOF"
    assert first["code"] == [[67, "     PERFORM 2000-PROCESS-ORDER"], [68, "         UNTIL ORD-EOF."]]
    assert item["definition"][-1] == [34, "     05  WS-ORD-STATUS       PIC XX VALUE SPACES."]

    q = dd.make_queue(doc, app_map, root=root, limit=100, copybook="ORDREC", refs=3)
    assert {it["copybook"] for it in q["items"]} == {"ORDREC"}
    cust = next(it for it in q["items"] if it["name"] == "OR-CUST-ID")
    assert {u["program"] for u in cust["used_in"]} == {"BILLRPT", "CUSTUPD"}
    copybook_item = next(it for it in q["items"] if it["name"] == "ORDER-RECORD")
    assert copybook_item["definition"][0][1].startswith("*")  # the comment above the record comes along
    assert copybook_item["children"] == ["OR-ORDER-ID", "OR-CUST-ID", "OR-PRIORITY", "OR-RATE-CODE", "OR-LINE-DATA"]

    describe(doc, "prog:ORDMAIN:WS-MSG")
    dd.approve(doc, ["prog:ORDMAIN:WS-MSG"])
    describe(doc, "prog:ORDMAIN:WS-COUNTERS.WS-SUB")
    ids = {it["id"] for it in dd.make_queue(doc, app_map, root=root, limit=1000)["items"]}
    assert "prog:ORDMAIN:WS-MSG" not in ids and "prog:ORDMAIN:WS-COUNTERS.WS-SUB" not in ids
    ids = {it["id"] for it in dd.make_queue(doc, app_map, root=root, limit=1000, include_proposed=True)["items"]}
    assert "prog:ORDMAIN:WS-COUNTERS.WS-SUB" in ids and "prog:ORDMAIN:WS-MSG" not in ids


# --------------------------------------------------------------------------- apply and approve
def test_apply_validates_and_refuses_to_overwrite_approved(built) -> None:
    _, _, doc, _ = built
    doc = json.loads(json.dumps(doc))
    key = "prog:ORDMAIN:WS-MSG"
    snapshot = json.dumps(doc, sort_keys=True)
    bad = [
        ({"descriptions": [{"id": key, "description": "x"}]}, "'source' is missing"),
        ({"source": "m", "descriptions": [{"id": "prog:ORDMAIN:NOPE", "description": "x"}]}, "no such entry"),
        ({"source": "m", "descriptions": [{"id": key, "description": "   "}]}, "empty description"),
        ({"source": "m", "descriptions": [{"id": key, "description": "a"}, {"id": key, "description": "b"}]}, "given twice"),
        ({"source": "m", "descriptions": [{"id": key, "description": dd.PLACEHOLDER}]}, "placeholder"),
        ({"source": "m", "descriptions": [{"id": key, "description": "x" * 1001}]}, "longer than"),
        ({"source": "m", "descriptions": []}, "non-empty list"),
        ("text", "JSON object"),
    ]
    for payload, message in bad:
        with pytest.raises(dd.DDError, match=message):
            dd.apply_descriptions(doc, payload)
    # one bad item and nothing at all is applied
    with pytest.raises(dd.DDError, match="nothing applied"):
        dd.apply_descriptions(doc, {"source": "m", "descriptions": [
            {"id": key, "description": "Report line."}, {"id": "prog:ORDMAIN:NOPE", "description": "x"}]})
    assert json.dumps(doc, sort_keys=True) == snapshot

    res = dd.apply_descriptions(doc, {"source": "granite-3", "descriptions": {key: "  Text of the\nreport line. "}})
    assert res["applied"] == [key] and res["replaced"] == 0
    e = doc["entries"][key]
    assert (e["status"], e["description"], e["source"]) == ("proposed", "Text of the report line.", "granite-3")
    res = dd.apply_descriptions(doc, {"source": "x", "descriptions": [{"id": key, "description": "Unclear."}]}, source="maria")
    assert res["replaced"] == 1 and doc["entries"][key]["source"] == "maria"

    dd.approve(doc, [key])
    with pytest.raises(dd.DDError, match="already approved"):
        dd.apply_descriptions(doc, {"source": "m", "descriptions": [{"id": key, "description": "Something else."}]})
    assert doc["entries"][key]["description"] == "Unclear." and doc["entries"][key]["status"] == "approved"

    stale_key = "prog:ORDMAIN:WS-RETRY-OLD"
    doc["entries"][stale_key] = dict(doc["entries"]["prog:ORDMAIN:WS-COUNTERS.WS-RETRY"], stale=True)
    with pytest.raises(dd.DDError, match="stale"):
        dd.apply_descriptions(doc, {"source": "m", "descriptions": [{"id": stale_key, "description": "x"}]})


def test_approve_by_id_name_alias_and_all(built) -> None:
    _, _, doc, _ = built
    doc = json.loads(json.dumps(doc))
    with pytest.raises(dd.DDError, match="no description yet"):
        dd.approve(doc, ["prog:ORDMAIN:WS-MSG"])
    with pytest.raises(dd.DDError, match="name the entries"):
        dd.approve(doc)
    dd.apply_descriptions(doc, {"source": "m", "descriptions": [
        {"id": "prog:ORDMAIN:WS-MSG", "description": "Report line text."},
        {"id": "copy:CUSTREC::PFX:-CUSTOMER.:PFX:-BALANCE", "description": "Account balance of the customer."},
        {"id": "prog:ORDDB2:WS-TOTAL", "description": "Sum of the customer's orders."},
        {"id": "prog:PRICECAL:WS-DISCOUNT", "description": "Discount rate."},
    ]})
    with pytest.raises(dd.DDError, match="give the id"):
        dd.approve(doc, ["WS-MSG"])  # ORDMAIN and BILLRPT both declare one
    assert dd.approve(doc, ["prog:ORDMAIN:WS-MSG"], by="maria")["approved"] == ["prog:ORDMAIN:WS-MSG"]
    assert doc["entries"]["prog:ORDMAIN:WS-MSG"]["approved_by"] == "maria"
    assert dd.approve(doc, ["br-balance"])["approved"] == ["copy:CUSTREC::PFX:-CUSTOMER.:PFX:-BALANCE"]  # an alias
    with pytest.raises(dd.DDError, match="no description yet"):
        dd.approve(doc, ["LK-ORDER-ID", "WS-CUST-ID"])
    assert doc["entries"]["prog:PRICECAL:LK-ORDER-ID"]["status"] == "none"
    with pytest.raises(dd.DDError, match="no entry"):
        dd.approve(doc, ["NO-SUCH-FIELD"])
    with pytest.raises(dd.DDError, match="narrow --all"):
        dd.approve(doc, ["WS-MSG"], program="ORDMAIN")
    assert dd.approve(doc, all_=True, program="ORDDB2")["approved"] == ["prog:ORDDB2:WS-TOTAL"]
    assert dd.approve(doc, all_=True)["approved"] == ["prog:PRICECAL:WS-DISCOUNT"]
    assert dd.reopen(doc, ["prog:PRICECAL:WS-DISCOUNT"]) == ["prog:PRICECAL:WS-DISCOUNT"]
    assert doc["entries"]["prog:PRICECAL:WS-DISCOUNT"]["status"] == "proposed"
    dd.apply_descriptions(doc, {"source": "m", "descriptions": [{"id": "prog:PRICECAL:WS-DISCOUNT", "description": "Five per cent volume discount."}]})
    with pytest.raises(dd.DDError, match="not approved"):
        dd.reopen(doc, ["prog:PRICECAL:WS-DISCOUNT"])
    counts = dd.summary(doc)["status"]
    assert counts["approved"] == 3 and counts["proposed"] == 1


# --------------------------------------------------------------------------- CLI, CSV and the output guard
def test_cli_round_trip_and_csv_export(project, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    zscan.write_map(scan(project), root=project)
    assert dd.main(["queue"]) == 2 and "run `python3 scripts/dd.py build` first" in capsys.readouterr().err
    assert dd.main(["build"]) == 0
    out = capsys.readouterr().out
    assert "Programs: 6 (unchanged 0, changed 0, new 6, removed 0)" in out and "AUDITREC" in out
    assert dd.main(["build"]) == 0 and "unchanged 6" in capsys.readouterr().out

    assert dd.main(["queue", "--limit", "3", "--copybook", "CUSTREC"]) == 0
    out = capsys.readouterr().out
    q = json.loads((project / "zos-insight" / "dd" / "queue.json").read_text(encoding="utf-8"))
    assert q["shown"] == 3 and f"{q['remaining']} remain" in out

    desc = {"source": "test-model", "descriptions": [
        {"id": it["id"], "description": "=HYPERLINK(\"http://example.invalid\")" if i == 0 else "Unclear."}
        for i, it in enumerate(q["items"])]}
    path = project / "zos-insight" / "dd" / "descriptions.json"
    path.write_text(json.dumps(desc), encoding="utf-8")
    assert dd.main(["apply", str(path)]) == 0 and "Proposed 3" in capsys.readouterr().out
    assert dd.main(["status", "--list", "proposed"]) == 0
    listed = capsys.readouterr().out
    assert "proposed: 3" in listed and "(test-model)" in listed
    assert dd.main(["approve", "--all"]) == 0 and "Approved 3" in capsys.readouterr().out
    assert dd.main(["apply", str(path)]) == 2 and "already approved" in capsys.readouterr().err
    assert dd.main(["status", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["status"]["approved"] == 3 and info["map_drift"] == {"changed": [], "new": [], "removed": []}

    assert dd.main(["export", "--csv"]) == 0
    raw = (project / "zos-insight" / "dd" / "DD.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM, so a spreadsheet reads UTF-8
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    assert list(rows[0]) == list(dd.CSV_COLUMNS) and len(rows) == len(json.loads(
        (project / "zos-insight" / "dd" / "DD.json").read_text(encoding="utf-8"))["entries"])
    by_id = {r["id"]: r for r in rows}
    status = by_id["prog:ORDMAIN:WS-STATUS-FIELDS.WS-ORD-STATUS"]
    assert status["conditions_88"] == "ORD-OK = '00'; ORD-EOF = '10'" and status["qualified"] == "WS-STATUS-FIELDS.WS-ORD-STATUS"
    assert by_id["prog:ORDMAIN:WS-RATE-TABLE.RATE-ENTRY"]["occurs"] == "50 ASCENDING KEY RATE-CODE INDEXED BY RATE-IX"
    approved = [r for r in rows if r["status"] == "approved"]
    assert len(approved) == 3 and any(r["description"].startswith("'=HYPERLINK") for r in approved)
    assert dd._cell("-1") == "-1" and dd._cell("+X") == "'+X" and dd._cell("@SUM(A1)") == "'@SUM(A1)"

    src = project / "src" / "cobol" / "PRICECAL.cbl"
    src.write_text(src.read_text(encoding="utf-8").replace("VALUE .05", "VALUE .07"), encoding="utf-8")
    zscan.write_map(scan(project), root=project)
    assert dd.main(["status"]) == 0 and "changed PRICECAL" in capsys.readouterr().out


def test_writes_only_under_zos_insight(project, monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(project)
    zscan.write_map(scan(project), root=project)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    for argv, message in (
        (["build", "--dir", "src/dd"], "outputs go under zos-insight/"),
        (["build", "--dir", ".bob/dd"], "inside .bob/"),
        (["build", "--dir", str(outside)], "outside the project"),
        (["build", "--dir", "zos-insight/../src"], "outputs go under zos-insight/"),
    ):
        assert dd.main(argv) == 2, argv
        assert message in capsys.readouterr().err
    assert not (project / "src" / "dd").exists() and not (project / ".bob").exists() and not list(outside.iterdir())

    assert dd.main(["build"]) == 0
    capsys.readouterr()
    for argv in (["export", "--csv", "--out", "DD.csv"], ["export", "--csv", "--out", "src/DD.csv"],
                 ["export", "--csv", "--out", str(outside / "DD.csv")], ["queue", "--dir", ".bob/dd"]):
        assert dd.main(argv) == 2, argv
    assert not (project / "DD.csv").exists() and not (project / "src" / "DD.csv").exists()
    assert not (outside / "DD.csv").exists()

    (project / "zos-insight" / "link").symlink_to(outside, target_is_directory=True)
    assert dd.main(["export", "--csv", "--out", "zos-insight/link/DD.csv"]) == 2
    assert "outside the project" in capsys.readouterr().err and not (outside / "DD.csv").exists()

    # a file-level link inside the folder is replaced by the new file, never written through
    target = outside / "victim.txt"
    target.write_text("keep", encoding="utf-8")
    (project / "zos-insight" / "dd" / "DD.csv").symlink_to(target)
    assert dd.main(["export", "--csv"]) == 0
    assert target.read_text(encoding="utf-8") == "keep"
    assert not (project / "zos-insight" / "dd" / "DD.csv").is_symlink()
