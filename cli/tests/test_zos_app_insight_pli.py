"""zos-app-insight, skill zos-app-map: zscan_pli.py (PL/I programs in the map).

The fixtures under fixtures/zos-app-insight-lang/pli are original PL/I written for these
tests (see its README). The small programs the tests below write into tmp_path are
original too.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "packs" / "ibm" / "zos-app-insight" / "skills" / "zos-app-map" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures" / "zos-app-insight-lang" / "pli"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))  # zscan_pli imports zscan from its own folder, as zscan does for it
zscan_pli = importlib.import_module("zscan_pli")

V1_PROGRAM_KEYS = ("id", "file", "sha256", "format", "lines", "copybooks", "files", "data_items", "paragraphs",
                   "performs", "calls", "gotos", "sql", "cics", "conditions", "statements", "warnings")
MAIN = "src/src/BILLMAIN.pli"


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("proj")
    shutil.copytree(FIXTURES, root / "src")
    return root


@pytest.fixture(scope="module")
def main(project) -> dict:
    return zscan_pli.scan_program(MAIN, ["src/inc"], root=project)


@pytest.fixture(scope="module")
def sub(project) -> dict:
    return zscan_pli.scan_program("src/src/BILLSUB.pli", ["src/inc"], root=project)


def item(p: dict, name: str) -> dict:
    return next(i for i in p["data_items"] if i["name"] == name)


def stmt(p: dict, verb: str, line: int) -> dict:
    return next(s for s in p["statements"] if s["verb"] == verb and s["line"] == line)


def via(rec: dict):
    return (rec.get("in_loop") or {}).get("via")


def messages(p: dict) -> list:
    return [w["message"] for w in p["warnings"]]


def write(path: Path, lines: list, column: int = 2) -> Path:
    """Write PL/I lines starting in `column` (2 is the first column inside the default margins)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join((" " * (column - 1) + ln) if ln else "" for ln in lines) + "\n")
    return path


# --------------------------------------------------------------------------- interface
def test_interface_and_no_import_side_effects(tmp_path) -> None:
    assert zscan_pli.LANGUAGE == "pli"
    assert callable(zscan_pli.classify) and callable(zscan_pli.scan_program)
    code = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import zscan_pli"
    done = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout == "" and done.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_classify(project, tmp_path) -> None:
    src = project / "src"
    for name, kind in (("src/BILLMAIN.pli", "program"), ("src/BILLSUB.pli", "program"),
                       ("inc/BILLREC.inc", "include"), ("inc/BILLCNT.inc", "include"), ("inc/BILLWS.inc", "include")):
        path = src / name
        assert zscan_pli.classify(path, path.read_text()) == kind, name
    assert zscan_pli.classify(tmp_path / "X.pli", "") == "skip"
    assert zscan_pli.classify(tmp_path / "X.pli", "/* REXX */\nsay 'hello'\n") == "skip"
    assert zscan_pli.classify(tmp_path / "X.inc", "       01 CUST-REC.\n          05 CUST-ID PIC X(5).\n") == "skip"
    assert zscan_pli.classify(tmp_path / "X.pli", "   DCL A FIXED BIN(31);\n") == "include"
    assert zscan_pli.classify(tmp_path / "X.inc", " P: PROC;\n   A = 1;\n END P;\n") == "include"
    assert zscan_pli.classify(tmp_path / "X.inc", " P: PROC OPTIONS(MAIN);\n END P;\n") == "program"
    assert zscan_pli.classify(tmp_path / "X.txt", " P: PROCEDURE(A);\n END;\n") == "program"
    assert zscan_pli.classify(tmp_path / "X.pli", " %Q: PROC; RETURN('1'); %END Q;\n DCL B CHAR;\n") == "include"


# --------------------------------------------------------------------------- the record
def test_record_shape(main, project) -> None:
    for key in V1_PROGRAM_KEYS + ("sections", "procedure_using", "procedure_using_line", "sql_includes"):
        assert key in main, key
    json.dumps(main)  # serialisable as is
    assert main["id"] == "BILLMAIN" and main["language"] == "pli" and main["member"] == "BILLMAIN"
    assert main["file"] == MAIN and main["format"] == "fixed" and main["margins"] == [2, 72]
    assert main["lines"] == 120
    assert main["sha256"] == hashlib.sha256((project / MAIN).read_bytes()).hexdigest()
    assert main["entries"] == [{"name": "BILLMAIN", "line": 3, "kind": "procedure", "main": True}]
    assert main["procedure_using"] == [] and main["procedure_using_line"] is None
    assert main["sections"] == [] and main["cics"] == []
    for p in main["performs"]:
        assert set(p) >= {"from", "to", "thru", "loop", "inline", "line", "end_line", "in_loop"}
    for c in main["calls"]:
        assert set(c) >= {"target", "dynamic", "line", "paragraph", "using", "in_loop", "form"}
    for s in main["statements"]:
        assert set(s) >= {"verb", "line", "end_line", "paragraph", "operands", "in_loop"}
        assert not any(k.startswith("_") for k in s)


def test_margins(main, sub, tmp_path) -> None:
    operands = [o for s in main["statements"] for o in s["operands"]]
    assert not any(o.startswith("BM0") for o in operands)  # columns 73-80 hold sequence numbers
    assert not any("past column" in m or "left of column" in m for m in messages(main))
    # *PROCESS MARGINS(1,80): code starts in column 1 and runs past column 72
    assert sub["id"] == "BILLSUB" and sub["margins"] == [1, 80]
    assert item(sub, "CR_LIMIT")["parent"] == "CUST_REC" and item(sub, "CR_LIMIT")["type"] == "BIN(31)"
    assert sub["procedure_using"] == ["ORDER_ID", "ORDER_TOTAL"] and sub["procedure_using_line"] == 4
    assert sub["warnings"] == []
    # the same kind of text in the default margins: column 1 is outside them, and that is said
    path = write(tmp_path / "COL1.pli", ["COL1: PROC OPTIONS(MAIN);", "DCL A FIXED BIN(31);", "END COL1;"], column=1)
    rec = zscan_pli.scan_program(path, [], root=tmp_path)
    assert rec["id"] == "OL1"
    assert any("left of column 2" in m for m in messages(rec))


def test_includes(main) -> None:
    cbs = {c["name"]: c for c in main["copybooks"]}
    assert list(cbs) == ["BILLREC", "BILLCNT", "BILLWS", "AUDITPL"]
    assert cbs["BILLREC"] == {"name": "BILLREC", "library": None, "resolved": "src/inc/BILLREC.inc",
                              "replacing": False, "line": 5, "nested_in": None, "replacing_pairs": []}
    assert cbs["BILLCNT"]["library"] == "SYSLIB" and cbs["BILLCNT"]["resolved"] == "src/inc/BILLCNT.inc"
    assert cbs["BILLWS"]["nested_in"] == "BILLCNT" and cbs["BILLWS"]["line"] == 5
    assert cbs["AUDITPL"]["resolved"] is None and main["partial"] is True
    assert {"file": MAIN, "line": 7, "message": "%INCLUDE member AUDITPL not found; its declarations and code are "
                                               "missing from this map"} in main["warnings"]
    ws = item(main, "WS_ORD_AMT")
    assert (ws["copybook"], ws["file"], ws["line"]) == ("BILLWS", "src/inc/BILLWS.inc", 3)
    assert main["sql_includes"] == ["SQLCA"]


def test_data_items(main) -> None:
    assert [(i["name"], i["level"], i["parent"]) for i in main["data_items"] if i["line"] in range(12, 19)
            and i["file"] == MAIN] == [
        ("BILL_LINE", 1, None), ("BL_ORDER", 2, "BILL_LINE"), ("BL_AMOUNT", 2, "BILL_LINE"), ("BL_TAX", 2, "BILL_LINE"),
        ("BL_ITEMS", 2, "BILL_LINE"), ("BL_SKU", 3, "BL_ITEMS"), ("BL_QTY", 3, "BL_ITEMS")]
    items = main["data_items"]
    assert items[item(main, "BL_SKU")["parent_index"]]["name"] == "BL_ITEMS"
    assert item(main, "BL_ITEMS")["occurs"] == {"min": 5, "max": 5, "depending_on": None, "keys": [], "indexed_by": []}
    assert item(main, "BL_ITEMS")["dimensions"] == [{"lower": 1, "upper": 5}]
    assert item(main, "BL_AMOUNT")["pic"] == "(7)9V99" and item(main, "BL_AMOUNT")["usage"] is None
    tax = item(main, "BL_TAX")
    assert (tax["type"], tax["usage"], tax["value"]) == ("FIXED DEC(9,2)", "PACKED-DECIMAL", "0")
    assert (item(main, "BL_QTY")["type"], item(main, "BL_QTY")["usage"]) == ("FIXED BIN(31)", "BINARY")
    text = item(main, "BILL_TEXT")
    assert (text["redefines"], text["defined"], text["section"]) == ("BILL_LINE", "BILL_LINE", "DEFINED")
    view = item(main, "TAX_VIEW")
    assert (view["section"], view["based"], view["redefines"]) == ("BASED", "TAX_PTR", None)
    assert item(main, "TV_RATE")["section"] == "BASED"
    assert item(main, "TAX_PTR")["usage"] == "POINTER"
    assert item(main, "CUST_NAME")["type"] == "CHAR(40) VARYING"
    rates = item(main, "RATES")
    assert (rates["section"], rates["value"], rates["occurs"]["max"]) == ("STATIC", "(12)0", 12)
    assert item(main, "EOF_ORD")["value"] == "'0'B" and item(main, "EOF_ORD")["usage"] == "BIT"
    assert item(main, "I")["type"] == item(main, "J")["type"] == "FIXED BIN(15)"  # factored attributes
    assert item(main, "CNT_LINES")["section"] == "STATIC" and item(main, "CNT_LINES")["copybook"] == "BILLCNT"
    amt = item(main, "AMT")
    assert (amt["section"], amt["block"]) == ("PARAMETER", "FMT_AMOUNT")
    assert item(main, "LINE_AMT")["block"] == "PRICE_ORDER" and item(main, "BILL_LINE")["block"] is None
    assert item(main, "TRACE_ON")["line"] == 42  # inside %IF: every branch is mapped
    names = {i["name"] for i in items}
    assert not names & {"ORDFILE", "BILLOUT", "PRICECAL", "BILLTAX", "BILLSUB", "ADDR", "SUBSTR"}
    for i in items:
        assert {"type", "dimensions", "based", "defined", "like", "external", "block", "fd"} <= set(i)


def test_files_and_handlers(main, sub) -> None:
    files = {f["name"]: f for f in main["files"]}
    assert list(files) == ["ORDFILE", "BILLOUT"]
    ordf = files["ORDFILE"]
    assert (ordf["dd"], ordf["access"], ordf["transmission"], ordf["line"]) == ("ORDFILE", "SEQUENTIAL", "RECORD", 9)
    assert ordf["attributes"] == ["RECORD", "INPUT", "SEQUENTIAL"] and ordf["env"] == "FB RECSIZE(80)"
    assert [(x["verb"], x["line"], x.get("mode"), via(x)) for x in ordf["io"]] == [
        ("OPEN", 51, "INPUT", None), ("READ", 53, None, None), ("READ", 66, None, 54), ("CLOSE", 84, None, None)]
    assert ordf["record"] == "ORDER_REC" and ordf["records"] == ["ORDER_REC"]
    assert ordf["handlers"] == [{"condition": "ENDFILE", "line": 45, "end_line": 45, "unit": "ON-ENDFILE-45",
                                 "paragraph": None}]
    assert stmt(main, "READ", 66)["phrases"] == [{"kind": "ON ENDFILE", "line": 45}]
    out = files["BILLOUT"]
    assert (out["dd"], out["assign"], out["title"]) == ("BILLDD", "'BILLDD'", "'BILLDD'")
    assert [(x["verb"], x["line"], x.get("mode"), via(x)) for x in out["io"]] == [
        ("OPEN", 51, "OUTPUT", None), ("WRITE", 64, None, 54), ("CLOSE", 84, None, None)]
    assert "phrases" not in stmt(main, "WRITE", 64)
    vsam = sub["files"][0]
    assert (vsam["name"], vsam["organization"], vsam["access"]) == ("CUSTMAS", "VSAM", "DIRECT")
    assert vsam["keys"] == ["SUBSTR(ORDER_ID, 1, 8)", "CR_KEY"]
    assert [(x["verb"], x.get("mode")) for x in vsam["io"]] == [("OPEN", "UPDATE"), ("READ", None), ("REWRITE", None),
                                                                ("CLOSE", None)]
    assert stmt(sub, "READ", 12)["phrases"] == stmt(sub, "REWRITE", 15)["phrases"] == [{"kind": "ON KEY", "line": 10}]


def test_paragraphs(main) -> None:
    assert [(p["name"], p["kind"], p["start_line"], p["end_line"]) for p in main["paragraphs"]] == [
        ("ON-ENDFILE-45", "on-unit", 45, 45), ("ON-ERROR-46", "on-unit", 46, 49),
        ("PRICE_ORDER", "procedure", 91, 102), ("ADD_LINES", "procedure", 104, 111),
        ("FMT_AMOUNT", "procedure", 113, 118)]
    fmt = next(p for p in main["paragraphs"] if p["name"] == "FMT_AMOUNT")
    assert fmt["params"] == ["AMT"] and fmt["external"] is False and fmt["parent"] is None and fmt["section"] is None
    assert stmt(main, "PUT", 47)["paragraph"] == "ON-ERROR-46"
    assert stmt(main, "ASSIGN", 95)["paragraph"] == "PRICE_ORDER"
    assert stmt(main, "WRITE", 64)["paragraph"] is None  # the main procedure is the program, not a paragraph
    assert [(x["name"], x["line"]) for x in main["labels"]] == [("NEXT_ORDER", 65), ("SQL_ERROR", 87)]


def test_performs_and_loops(main) -> None:
    inline = [(p["line"], p["loop"], p["end_line"], via(p)) for p in main["performs"] if p["inline"]]
    assert inline == [(54, "while", 67, None), (71, "until", 80, None), (93, "iterative", 98, 54),
                      (94, "iterative", 96, 93), (106, "iterative", 109, 54)]
    calls = [(p["from"], p["to"], p["line"], via(p), p.get("function", False)) for p in main["performs"]
             if not p["inline"]]
    assert calls == [(None, "PRICE_ORDER", 55, 54, False), (None, "ADD_LINES", 57, 54, False),
                     ("ADD_LINES", "FMT_AMOUNT", 110, 54, True)]
    # the innermost inline loop wins; a procedure called from a loop is in that loop
    assert via(stmt(main, "ASSIGN", 95)) == 94
    assert via(stmt(main, "CALL", 97)) == 93
    assert via(stmt(main, "EXEC SQL", 99)) == 54
    assert via(stmt(main, "PUT", 116)) == 54  # two calls away from the loop at line 54
    assert via(stmt(main, "ASSIGN", 69)) is None
    assert stmt(main, "PUT", 47)["in_loop"] is None  # an ON-unit runs when its condition is raised
    assert stmt(main, "DO", 54)["end_line"] == 67 and stmt(main, "DO", 54)["operands"] == ["WHILE", "(", "^", "EOF_ORD", ")"]


def test_calls(main) -> None:
    calls = [(c["target"], c["form"], c["dynamic"], c["line"], c["paragraph"], via(c), c.get("candidates"))
             for c in main["calls"]]
    assert calls == [("BILLTAX", "FETCH", True, 52, None, None, ["BILLTX01"]),
                     ("BILLSUB", "CALL", False, 83, None, None, None),
                     ("PRICECAL", "CALL", False, 97, "PRICE_ORDER", 93, None),
                     ("BILLTAX", "FUNCTION", True, 101, "PRICE_ORDER", 54, ["BILLTX01"])]
    assert next(c for c in main["calls"] if c["target"] == "PRICECAL")["using"] == ["BL_SKU(I)", "LINE_AMT"]
    assert next(c for c in main["calls"] if c["target"] == "BILLSUB")["using"] == ["BL_ORDER", "WS_TOTAL"]
    assert stmt(main, "CALL", 48)["operands"][0] == "PLIDUMP"  # a built-in subroutine: a statement, not a call


def test_sql(main) -> None:
    rows = [(s["line"], s["verb"], s["tables"], s["cursor"], via(s), s["paragraph"]) for s in main["sql"]]
    assert rows == [(36, "INCLUDE", [], None, None, None), (37, "DECLARE CURSOR", ["ORDERS"], "CUR_ORD", None, None),
                    (70, "OPEN", ["ORDERS"], "CUR_ORD", None, None), (72, "FETCH", ["ORDERS"], "CUR_ORD", 71, None),
                    (81, "CLOSE", ["ORDERS"], "CUR_ORD", None, None),
                    (99, "SELECT", ["TAXTAB"], None, 54, "PRICE_ORDER")]
    fetch = next(s for s in main["sql"] if s["verb"] == "FETCH")
    assert fetch["host_vars"] == ["WS_ORD_ID", "WS_ORD_AMT"]
    assert fetch["text"] == "FETCH CUR_ORD INTO :WS_ORD_ID, :WS_ORD_AMT"
    assert next(s for s in main["sql"] if s["verb"] == "SELECT")["end_line"] == 100
    assert stmt(main, "EXEC SQL", 72)["operands"] == ["FETCH"]


def test_conditions(main) -> None:
    rows = [(c["kind"], c["text"], c["start_line"], c["end_line"], via(c)) for c in main["conditions"]]
    assert rows == [("WHILE", "^EOF_ORD", 54, 54, None), ("SELECT", "ORD_TYPE", 56, 63, 54),
                    ("WHEN", "'R', 'S'", 57, 57, 54), ("WHEN", "'X'", 58, 61, 54), ("OTHERWISE", "", 62, 62, 54),
                    ("UNTIL", "SQLCODE ^= 0", 71, 71, None), ("IF", "SQLCODE < 0", 73, 73, 71),
                    ("IF", "SQLCODE = 0", 74, 79, 71), ("IF", "SQLCODE = 100", 76, 79, 71),
                    ("WHILE", "K <= 5", 106, 106, 54)]
    ifs = [c for c in main["conditions"] if c["kind"] == "IF"]
    assert [c["else_line"] for c in ifs] == [None, 76, 78]
    when = next(c for c in main["conditions"] if c["kind"] == "WHEN")
    assert when["subject"] == "ORD_TYPE" and when["data_items"] == ["ORD_TYPE"] and when["tokens"] == ["'R'", ",", "'S'"]
    assert main["conditions"][0]["data_items"] == ["EOF_ORD"]


def test_gotos_and_warnings(main) -> None:
    assert [(g["to"], g["line"], g["paragraph"]) for g in main["gotos"]] == [(["NEXT_ORDER"], 60, None),
                                                                            (["SQL_ERROR"], 73, None)]
    msgs = messages(main)
    assert "GO TO SQL_ERROR at line 73 leaves the DO loop at line 71; in_loop does not follow GO TO" in msgs
    assert not any("NEXT_ORDER" in m for m in msgs)  # its label is inside the loop
    assert {"file": MAIN, "line": 41,
            "message": "preprocessor %IF not evaluated: the text of every branch is mapped"} in main["warnings"]
    assert len(msgs) == 3


# --------------------------------------------------------------------------- small programs
def test_preprocessor(tmp_path) -> None:
    write(tmp_path / "inc" / "MEMB.inc", ["DCL FROM_MEMB FIXED BIN(31);"])
    write(tmp_path / "src" / "sub" / "LOCAL.inc", ["DCL FROM_LOCAL CHAR(1);"])
    path = write(tmp_path / "src" / "PRE.pli", [
        "%DCL SWITCH CHAR;",
        "%SWITCH = 'ON';",
        "%MACRO: PROC(X) RETURNS(CHAR);",
        "  DCL X CHAR;",
        "  IF X = '' THEN RETURN('0'); ELSE RETURN(X);",
        "%END MACRO;",
        "%ACTIVATE MACRO;",
        "PRE: PROC OPTIONS(MAIN);",
        "%XINCLUDE MEMB;",
        "%XINCLUDE MEMB;",
        "%INCLUDE 'sub/LOCAL.inc';",
        "%DO SKIP;",
        "DCL NEVER_SEEN FIXED;",
        "%END;",
        "%PAGE;",
        "DCL A CHAR(1);",
        "A = MACRO('1');",
        "MACRO('2');",
        "END PRE;",
    ])
    rec = zscan_pli.scan_program(path, ["inc"], root=tmp_path)
    names = [i["name"] for i in rec["data_items"]]
    assert names == ["FROM_MEMB", "FROM_LOCAL", "A"]
    assert [(c["name"], c["resolved"]) for c in rec["copybooks"]] == [("MEMB", "inc/MEMB.inc"),
                                                                      ("sub/LOCAL.inc", "src/sub/LOCAL.inc")]
    assert [s["verb"] for s in rec["statements"]] == ["ASSIGN", "UNKNOWN"]
    msgs = messages(rec)
    assert "preprocessor %DECLARE not evaluated: macro variables in the code are left as written" in msgs
    assert "preprocessor assignment not evaluated" in msgs
    assert "preprocessor procedure MACRO not evaluated: its invocations are left as written" in msgs
    assert any(m.startswith("MACRO invokes preprocessor procedure MACRO") for m in msgs)
    assert any(m.startswith("MACRO is a preprocessor procedure") for m in msgs)
    assert not any("NEVER_SEEN" in m or "%PAGE" in m for m in msgs)


def test_blocks_entries_and_dynamic_calls(tmp_path) -> None:
    path = write(tmp_path / "BLK.pli", [
        "BLK: PROC OPTIONS(MAIN);",
        "DCL EV ENTRY VARIABLE;",
        "DCL PROGA ENTRY;",
        "DCL TARGET CHAR(8) INIT('CUSTINQ');",
        "DCL TAB(10) FIXED BIN(31);",
        "DCL 1 SHAPE, 2 SH_A CHAR(2);",
        "DCL COPY_OF LIKE SHAPE;",
        "DCL BUF CHAR(N REFER(LEN)) BASED;",
        "DCL 1 VREC BASED, 2 LEN FIXED BIN(15), 2 ROWS(100 REFER(LEN)) CHAR(4);",
        "DCL (I, N) FIXED BIN(31);",
        "DEFAULT RANGE(*) FIXED BIN;",
        "EV = PROGA;",
        "OUTER: DO I = 1 TO 10;",
        "   (SUBRG): TAB(I) = 0;",
        "   DO WHILE (I < 5);",
        "      CALL EV;",
        "END OUTER;",
        "EXEC CICS LINK PROGRAM('CUSTUPD') COMMAREA(TAB);",
        "EXEC CICS XCTL PROGRAM(TARGET);",
        "CALL LOOPY;",
        "CALL ALT2;",
        "GO TO NOWHERE;",
        "LOOPY: PROC RECURSIVE;",
        "   CALL LOOPY;",
        "ALT2: ENTRY;",
        "END LOOPY;",
        "ELSE;",
        "END BLK;",
        "LEFT: PROC;",
        "   DO;",
    ])
    rec = zscan_pli.scan_program(path, [], root=tmp_path)
    msgs = messages(rec)
    assert "END OUTER also closes the DO group at line 15 (multiple closure)" in msgs
    assert "ELSE without an IF" in msgs
    assert "GO TO target NOWHERE is not a label in this program" in msgs
    assert any(m.startswith("recursive calls among LOOPY") for m in msgs)
    assert "COPY_OF takes its members from SHAPE through the LIKE attribute; they are not repeated in the map" in msgs
    assert any(m.startswith("DEFAULT statement") for m in msgs)
    assert "DO group at line 30 has no END; closed at the end of the file" in msgs
    assert "procedure LEFT at line 29 has no END; closed at the end of the file" in msgs
    assert "2 external procedures in one file; mapped as one program with id BLK, the others are paragraphs " \
           "with external: true" in msgs
    assert [e["name"] for e in rec["entries"]] == ["BLK", "LEFT"]
    call = next(c for c in rec["calls"] if c["line"] == 16)
    assert (call["target"], call["dynamic"], call["candidates"], via(call)) == ("EV", True, ["PROGA"], 15)
    assert stmt(rec, "ASSIGN", 14)["in_loop"]["via"] == 13
    assert [(p["to"], p.get("entry")) for p in rec["performs"] if not p["inline"]] == [
        ("LOOPY", None), ("LOOPY", "ALT2"), ("LOOPY", None)]
    cics = [(c["command"], c["options"].get("program"), c.get("candidates")) for c in rec["cics"]]
    assert cics == [("LINK", "'CUSTUPD'", None), ("XCTL", "TARGET", ["CUSTINQ"])]
    assert stmt(rec, "EXEC CICS", 18)["operands"] == ["LINK"]
    assert item(rec, "TAB")["occurs"]["max"] == 10
    assert item(rec, "BUF")["type"] == "CHAR(N REFER(LEN))" and item(rec, "BUF")["based"] is None
    assert item(rec, "ROWS")["occurs"] == {"min": None, "max": 100, "depending_on": "LEN", "keys": [],
                                           "indexed_by": []}
    left = next(p for p in rec["paragraphs"] if p["name"] == "LEFT")
    assert left["external"] is True and left["kind"] == "procedure"


def test_unknown_and_condition_prefix(tmp_path) -> None:
    path = write(tmp_path / "ODD.pli", [
        "ODD: PROC OPTIONS(MAIN);",
        "DCL X FIXED BIN(31);",
        "(SIZE, NOFOFL): X = X + 1;",
        "L1: L2: X = 2;",
        "123;",
        "END ODD;",
        "END;",
    ])
    rec = zscan_pli.scan_program(path, [], root=tmp_path)
    assert [s["verb"] for s in rec["statements"]] == ["ASSIGN", "ASSIGN", "UNKNOWN"]
    assert [lab["name"] for lab in rec["labels"]] == ["L1", "L2"]
    msgs = messages(rec)
    assert "statement not understood (it starts with '123'); recorded as UNKNOWN" in msgs
    assert "END without an open procedure, DO, SELECT or BEGIN" in msgs


def test_include_index_refresh_and_reuse(tmp_path) -> None:
    path = write(tmp_path / "src" / "LATE.pli", ["LATE: PROC OPTIONS(MAIN);", "%INCLUDE LATEMEM;", "END LATE;"])
    (tmp_path / "inc").mkdir()
    first = zscan_pli.scan_program(path, ["inc"], root=tmp_path)
    assert first["copybooks"][0]["resolved"] is None and first["partial"] is True
    write(tmp_path / "inc" / "LATEMEM.inc", ["DCL LATE_ITEM CHAR(1);"])
    again = zscan_pli.scan_program(path, ["inc"], root=tmp_path)
    assert again["copybooks"][0]["resolved"] == "inc/LATEMEM.inc" and again["partial"] is False
    index = zscan_pli.IncludeIndex(["inc"], tmp_path)
    reused = zscan_pli.scan_program(path, index, root=tmp_path)
    assert [i["name"] for i in reused["data_items"]] == ["LATE_ITEM"]


def test_scan_writes_nothing(project) -> None:
    before = sorted((str(p), p.stat().st_mtime_ns) for p in project.rglob("*"))
    zscan_pli.scan_program(MAIN, ["src/inc"], root=project)
    after = sorted((str(p), p.stat().st_mtime_ns) for p in project.rglob("*"))
    assert before == after
    assert not (project / "zos-insight").exists() and os.path.isdir(project / "src")
