"""zos-app-insight, skill zos-app-map: zscan.py (COBOL and JCL map) and zowe_fetch.py.

The fixtures under fixtures/zos-app-insight are an original synthetic application written
for these tests (see its README). No test calls Zowe: subprocess is stubbed.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "packs" / "ibm" / "zos-app-insight" / "skills" / "zos-app-map" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures" / "zos-app-insight"


def load(script: str):
    path = SCRIPTS / f"{script}.py"
    spec = importlib.util.spec_from_file_location(f"zos_{script}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


zscan = load("zscan")
zowe_fetch = load("zowe_fetch")

ROOTS = ["src/cobol", "src/jcl", "src/proclib", "src/legacy"]
COPY = ["src/copy"]


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("proj")
    shutil.copytree(FIXTURES, root / "src")
    return root


@pytest.fixture(scope="module")
def app(project) -> dict:
    return zscan.scan(ROOTS, COPY, root=project)


def prog(app_map: dict, pid: str) -> dict:
    found = zscan.find_program(app_map, pid)
    assert found is not None, pid
    return found


def stmt(p: dict, verb: str, line: int) -> dict:
    return next(s for s in p["statements"] if s["verb"] == verb and s["line"] == line)


def item(p: dict, name: str) -> dict:
    return zscan.data_item_index(p)[name][0]


def loop(via: int, kind: str, file: str = "src/cobol/ORDMAIN.cbl") -> dict:
    return {"via": via, "kind": kind, "file": file}


# --------------------------------------------------------------------------- top level
def test_contract_top_level(app) -> None:
    for key in ("version", "generated", "parser", "roots", "programs", "copybooks", "jobs", "procs", "edges",
                "not_analysed", "unresolved", "warnings"):
        assert key in app
    assert app["version"] == 1 and app["parser"] == "zscan 1.0"
    assert app["roots"] == ROOTS and app["copy_dirs"] == COPY
    assert sorted(p["id"] for p in app["programs"]) == [
        "ASMUTIL", "CLEANUP", "CUSTUPD", "OLDRPT", "ORDCICS", "ORDDB2", "ORDMAIN", "PRICECAL"]
    json.dumps(app)  # serialisable as is
    for p in app["programs"]:
        for key in ("id", "language", "file", "sha256", "format", "lines", "copybooks", "files", "data_items",
                    "paragraphs", "performs", "calls", "gotos", "sql", "cics", "conditions", "statements", "warnings"):
            assert key in p, key
        assert len(p["sha256"]) == 64
    assert {c["language"] for c in app["copybooks"]} == {"cobol"}


def test_the_legacy_languages_are_analysed_since_1_1(app) -> None:
    assert app["not_analysed"] == {"pli": [], "asm": [], "rexx": []}
    langs = {p["id"]: (p["language"], p["file"]) for p in app["programs"]}
    assert langs["OLDRPT"] == ("pli", "src/legacy/OLDRPT.pli")
    assert langs["ASMUTIL"] == ("asm", "src/legacy/ASMUTIL.asm")
    assert langs["CLEANUP"] == ("rexx", "src/legacy/CLEANUP.rexx")
    assert all(langs[pid][0] == "cobol" for pid in ("CUSTUPD", "ORDCICS", "ORDDB2", "ORDMAIN", "PRICECAL"))


# --------------------------------------------------------------------------- source format
def test_fixed_format_columns_comments_debug_and_continuation(app) -> None:
    p = prog(app, "ORDMAIN")
    assert p["format"] == "fixed" and p["lines"] == 123
    words = {o for s in p["statements"] for o in s["operands"]}
    assert not any(w.startswith("ORD26A") for w in words)  # columns 73-80 are ignored
    assert not any(s["verb"] == "DISPLAY" for s in p["statements"])  # the D line is a debug line
    assert "PURGEALL" not in words  # comment text never becomes code
    move = stmt(p, "MOVE", 79)
    assert move["operands"][0] == "'NIGHTLY ORDER BILLING RUN FOR ALL REGIONS AND CUSTOMERS OF EVERY PRODUCT LINE'"
    assert move["operands"][1:] == ["TO", "WS-MSG"]
    assert prog(app, "PRICECAL")["format"] == "fixed"
    assert prog(app, "ORDCICS")["format"] == "fixed"


def test_free_format_detected(app) -> None:
    p = prog(app, "ORDDB2")
    assert p["format"] == "free"
    assert [x["name"] for x in p["paragraphs"]] == ["MAIN-PARA", "FETCH-ONE"]
    assert item(p, "NO-MORE-ROWS")["parent"] == "WS-DONE"


def test_detect_format_and_free_continuation() -> None:
    assert zscan.detect_format(["      >>SOURCE FORMAT IS FREE", "IDENTIFICATION DIVISION."]) == "free"
    assert zscan.detect_format(["000100 IDENTIFICATION DIVISION.", "000200 PROGRAM-ID. X."]) == "fixed"
    assert zscan.detect_format(["       IDENTIFICATION DIVISION."]) == "fixed"
    assert zscan.detect_format(["identification division.", "program-id. x."]) == "free"


# --------------------------------------------------------------------------- copybooks
def test_copy_replacing_library_nested_and_unresolved(app) -> None:
    p = prog(app, "ORDMAIN")
    books = {c["name"]: c for c in p["copybooks"]}
    assert books["ORDREC"]["resolved"] == "src/copy/ORDREC.cpy" and books["ORDREC"]["replacing"] is False
    assert books["CUSTREC"]["replacing"] is True and books["CUSTREC"]["line"] == 28
    assert books["WSCOMMON"]["library"] == "COMMLIB"
    assert books["WSCOMMON"]["resolved"] == "src/copy/COMMLIB/WSCOMMON.cpy"
    assert books["DATEWS"]["nested_in"] == "WSCOMMON" and books["DATEWS"]["resolved"] == "src/copy/DATEWS.cpy"
    assert books["AUDITREC"]["resolved"] is None
    # REPLACING ==:PFX:== BY ==CM== reaches the data names and the RECORD KEY
    cust = item(p, "CM-CUST-ID")
    assert (cust["copybook"], cust["file"], cust["line"]) == ("CUSTREC", "src/copy/CUSTREC.cpy", 3)
    assert item(p, "CM-ACTIVE")["level"] == 88 and item(p, "CM-ACTIVE")["parent"] == "CM-STATUS"
    assert not any(":PFX:" in d["name"] for d in p["data_items"])
    # nested copybook items hang under the includer's group
    yyyy = item(p, "WS-TODAY-YYYY")
    assert yyyy["copybook"] == "DATEWS" and yyyy["parent"] == "WS-TODAY"
    assert item(p, "WS-TODAY")["parent"] == "WS-COMMON"
    # the missing copybook is reported, never silently empty
    assert p["partial"] is True
    assert any("AUDITREC" in w["message"] for w in p["warnings"])
    assert app["unresolved"]["copybooks"] == [
        {"name": "AUDITREC", "library": None, "programs": [{"id": "ORDMAIN", "file": "src/cobol/ORDMAIN.cbl"}]}]
    cat = {c["name"]: c for c in app["copybooks"]}
    assert cat["WSCOMMON"]["includes"] == ["DATEWS"] and cat["DATEWS"]["used_by"] == ["ORDMAIN"]
    assert cat["CUSTREC"]["used_by"] == ["CUSTUPD", "ORDMAIN"] and cat["ORDREC"]["used_by"] == ["CUSTUPD", "ORDMAIN"]
    edges = {(e["from"], e["to"]) for e in app["edges"] if e["kind"] == "copy"}
    assert {("ORDMAIN", "WSCOMMON"), ("WSCOMMON", "DATEWS"), ("ORDMAIN", "AUDITREC")} <= edges


def test_apply_replacing_rules() -> None:
    pairs = [("text", ":TAG:", "CUST"), ("text", "OLD-NAME", "NEW-NAME")]
    out = zscan.apply_replacing("01 :TAG:-REC. 05 OLD-NAME PIC X VALUE 'OLD-NAME'.", pairs)
    assert out == "01 CUST-REC. 05 NEW-NAME PIC X VALUE 'OLD-NAME'."
    assert zscan.apply_replacing("05 OLD-NAMES PIC X.", pairs) == "05 OLD-NAMES PIC X."
    assert zscan.apply_replacing("05 WS-A PIC X.", [("leading", "WS", "LK")]) == "05 LK-A PIC X."


# --------------------------------------------------------------------------- data division
def test_select_assign_and_fd(app) -> None:
    files = {f["name"]: f for f in prog(app, "ORDMAIN")["files"]}
    cust = files["CUST-FILE"]
    assert (cust["assign"], cust["dd"], cust["organization"], cust["access"]) == ("UT-S-CUSTMAST", "CUSTMAST", "INDEXED", "DYNAMIC")
    assert cust["record"] == "CM-CUSTOMER" and cust["keys"] == ["CM-CUST-ID"] and cust["status"] == "WS-CUST-STATUS"
    order = files["ORDER-FILE"]
    assert (order["assign"], order["organization"], order["record"]) == ("ORDIN", "SEQUENTIAL", "ORDER-RECORD")
    io = [(x["verb"], x["line"], x.get("mode")) for x in order["io"]]
    assert io == [("OPEN", 72, "INPUT"), ("READ", 84, None), ("READ", 109, None), ("CLOSE", 123, None)]
    assert [x["verb"] for x in files["RPT-FILE"]["io"]] == ["OPEN", "WRITE", "CLOSE"]
    assert files["CUST-FILE"]["io"][0]["mode"] == "I-O"
    assert item(prog(app, "ORDMAIN"), "OR-ORDER-ID")["fd"] == "ORDER-FILE"


def test_data_items_occurs_redefines_odo_and_88(app) -> None:
    p = prog(app, "ORDMAIN")
    rate = item(p, "RATE-ENTRY")
    assert rate["occurs"] == {"min": 50, "max": 50, "depending_on": None,
                              "keys": [{"name": "RATE-CODE", "order": "ascending"}], "indexed_by": ["RATE-IX"]}
    line = item(p, "WS-LINE")
    assert line["occurs"]["min"] == 1 and line["occurs"]["max"] == 20
    assert line["occurs"]["depending_on"] == "WS-LINE-COUNT" and line["occurs"]["indexed_by"] == ["LINE-IX"]
    assert item(p, "WS-AMOUNT-X")["redefines"] == "WS-LINE-AMOUNT"
    eof = item(p, "ORD-EOF")
    assert (eof["level"], eof["value"], eof["parent"], eof["section"]) == (88, "'10'", "WS-ORD-STATUS", "WORKING-STORAGE")
    total = item(p, "WS-ORDER-TOTAL")
    assert (total["pic"], total["usage"], total["value"], total["copybook"]) == ("S9(9)V99", "COMP-3", "ZERO", None)
    assert item(p, "WS-LINE-COUNT")["usage"] == "COMP"
    assert item(p, "RATE-PCT")["parent"] == "RATE-ENTRY"
    assert item(prog(app, "PRICECAL"), "WS-DISCOUNT")["value"] == ".05"
    assert item(prog(app, "PRICECAL"), "LK-TOTAL")["section"] == "LINKAGE"
    assert prog(app, "PRICECAL")["procedure_using"] == ["LK-ORDER-ID", "LK-TOTAL"]


# --------------------------------------------------------------------------- procedure division
def test_sections_paragraphs_and_performs(app) -> None:
    p = prog(app, "ORDMAIN")
    paras = [(x["name"], x["section"], x["start_line"], x["end_line"]) for x in p["paragraphs"]]
    assert paras == [("0000-START", "0000-MAINLINE", 65, 70), ("1000-INIT", "0000-MAINLINE", 71, 86),
                     ("1000-EXIT", "0000-MAINLINE", 87, 88), ("2000-START", "2000-PROCESS-ORDER", 90, 111),
                     ("2100-PRICE-LINE", "2000-PROCESS-ORDER", 112, 119), ("9000-START", "9000-CLOSE", 121, 123)]
    assert [s["name"] for s in p["sections"]] == ["0000-MAINLINE", "2000-PROCESS-ORDER", "9000-CLOSE"]
    perf = {x["line"]: x for x in p["performs"]}
    assert (perf[66]["to"], perf[66]["thru"], perf[66]["loop"], perf[66]["inline"]) == ("1000-INIT", "1000-EXIT", None, False)
    assert (perf[67]["to"], perf[67]["loop"], perf[67]["from"]) == ("2000-PROCESS-ORDER", "until", "0000-START")
    assert (perf[81]["to"], perf[81]["loop"], perf[81]["inline"]) == (None, "times", True)
    assert (perf[92]["loop"], perf[92]["inline"]) == ("varying", True)
    assert (perf[95]["loop"], perf[95]["inline"]) == ("varying", True)
    assert perf[94]["to"] == "2100-PRICE-LINE" and perf[94]["loop"] is None
    edges = {(e["from"], e["to"]) for e in app["edges"] if e["kind"] == "perform"}
    assert ("ORDMAIN:0000-START", "ORDMAIN:2000-PROCESS-ORDER") in edges


def test_in_loop_inline_out_of_line_nested_and_thru(app) -> None:
    p = prog(app, "ORDMAIN")
    # out of line: the section performed UNTIL ORD-EOF
    assert stmt(p, "ADD", 91)["in_loop"] == loop(67, "until")
    assert stmt(p, "READ", 109)["in_loop"] == loop(67, "until")
    # inline, nested: the innermost loop wins
    assert stmt(p, "INITIALIZE", 96)["in_loop"] == loop(95, "varying")
    # a paragraph performed from inside an inline loop is in that loop
    assert stmt(p, "COMPUTE", 116)["in_loop"] == loop(92, "varying")
    assert stmt(p, "SEARCH", 113)["in_loop"] == loop(92, "varying")
    # TIMES
    assert stmt(p, "ADD", 82)["in_loop"] == loop(81, "times")
    # PERFORM THRU without a loop leaves its range outside any loop
    assert stmt(p, "OPEN", 72)["in_loop"] is None and stmt(p, "READ", 84)["in_loop"] is None
    assert stmt(p, "WRITE", 122)["in_loop"] is None
    # calls, SQL and file I/O carry the same field
    assert next(c for c in p["calls"] if c["line"] == 102)["in_loop"] == loop(67, "until")
    db2 = prog(app, "ORDDB2")
    fetch = next(s for s in db2["sql"] if s["verb"] == "FETCH")
    single = next(s for s in db2["sql"] if s["verb"] == "SELECT")
    assert fetch["in_loop"] == loop(21, "until", "src/cobol/ORDDB2.cbl")
    assert single["in_loop"] == loop(21, "until", "src/cobol/ORDDB2.cbl")
    assert next(s for s in db2["sql"] if s["verb"] == "OPEN")["in_loop"] is None
    assert len(zscan.statements_in_loop(p)) > 10


def test_calls_gotos_and_conditions(app) -> None:
    p = prog(app, "ORDMAIN")
    static = next(c for c in p["calls"] if c["line"] == 102)
    assert (static["target"], static["dynamic"], static["using"], static["paragraph"]) == (
        "PRICECAL", False, ["OR-ORDER-ID", "WS-ORDER-TOTAL"], "2000-START")
    dyn = next(c for c in p["calls"] if c["line"] == 104)
    assert (dyn["target"], dyn["dynamic"], dyn["candidates"]) == ("WS-PGM-NAME", True, ["TAXCALC"])
    calls = {(e["from"], e["to"], bool(e.get("dynamic"))) for e in app["edges"] if e["kind"] == "call"}
    assert calls == {("ORDMAIN", "PRICECAL", False), ("ORDMAIN", "TAXCALC", True)}
    assert zscan.callers(app, "PRICECAL") == ["ORDCICS", "ORDMAIN"]
    assert p["gotos"] == [{"to": ["1000-EXIT"], "line": 76, "paragraph": "1000-INIT", "depending_on": None}]
    cond = [(c["kind"], c["text"], c["start_line"], c["end_line"]) for c in p["conditions"]]
    assert ("IF", "NOT ORD-OK", 75, 77) in cond
    assert ("EVALUATE", "TRUE", 99, 108) in cond
    assert ("WHEN", "OR-PRIORITY = 'H'", 100, 105) in cond
    assert ("IF", "WS-ORDER-TOTAL > 1000", 101, 105) in cond  # nested in the WHEN
    assert ("WHEN", "OTHER", 106, 107) in cond
    assert ("UNTIL", "WS-SUB > WS-LINE-COUNT", 93, 93) in cond
    assert ("SEARCH-WHEN", "RATE-CODE (RATE-IX) = OR-RATE-CODE", 115, 117) in cond
    when = next(c for c in p["conditions"] if c["kind"] == "WHEN" and c["start_line"] == 100)
    assert when["subject"] == "TRUE" and when["data_items"] == ["OR-PRIORITY"] and when["paragraph"] == "2000-START"
    until = next(c for c in p["conditions"] if c["kind"] == "UNTIL" and c["start_line"] == 93)
    assert until["data_items"] == ["WS-SUB", "WS-LINE-COUNT"]
    assert not p["warnings"][1:]  # only the missing copybook


def test_exec_sql(app) -> None:
    db2 = prog(app, "ORDDB2")
    by_verb = {s["verb"]: s for s in db2["sql"]}
    assert by_verb["DECLARE CURSOR"]["cursor"] == "CUSTCUR" and by_verb["DECLARE CURSOR"]["paragraph"] is None
    assert by_verb["DECLARE CURSOR"]["tables"] == ["BILLING.CUSTOMER"]
    assert by_verb["FETCH"]["cursor"] == "CUSTCUR" and by_verb["FETCH"]["tables"] == ["BILLING.CUSTOMER"]
    assert by_verb["FETCH"]["host_vars"] == ["WS-CUST-ID", "WS-NAME"]
    assert by_verb["SELECT"]["tables"] == ["BILLING.ORDERS"] and by_verb["SELECT"]["cursor"] is None
    assert by_verb["INSERT"]["tables"] == ["BILLING.CUST_TOTALS"]
    assert by_verb["INCLUDE"]["tables"] == [] and db2["copybooks"] == []  # SQLCA is not a copybook to find
    assert [s["verb"] for s in db2["statements"] if s["verb"] == "EXEC SQL"] == ["EXEC SQL"] * 5
    tables = {e["to"]: e["verbs"] for e in app["edges"] if e["kind"] == "sql-table"}
    assert tables["BILLING.ORDERS"] == ["SELECT"] and "FETCH" in tables["BILLING.CUSTOMER"]
    assert zscan.parse_sql("UPDATE BILLING.T SET A = 1 WHERE CURRENT OF C1")["cursor"] == "C1"
    assert zscan.parse_sql("SELECT A INTO :X FROM T1 A JOIN T2 B ON A.K = B.K")["tables"] == ["T1", "T2"]


def test_exec_cics(app) -> None:
    c = prog(app, "ORDCICS")
    cmds = {x["command"]: x for x in c["cics"]}
    assert cmds["READ"]["options"] == {"file": "'CUSTFIL'", "into": "WS-CUST-REC", "ridfld": "WS-CUST-KEY"}
    assert cmds["LINK"]["options"]["program"] == "'PRICECAL'"
    assert cmds["XCTL"]["candidates"] == ["ORDMENU"]
    kinds = {(e["kind"], e["to"]) for e in app["edges"] if e["from"] == "ORDCICS"}
    assert ("cics-link", "PRICECAL") in kinds and ("cics-xctl", "ORDMENU") in kinds
    assert zscan.parse_cics("SEND MAP('M1') MAPSET('S1') ERASE")["command"] == "SEND MAP"
    assert zscan.parse_cics("READQ TS QUEUE(WS-Q) INTO(WS-A)")["options"]["queue"] == "WS-Q"


def test_recursion_and_unfollowed_flow_are_warnings(tmp_path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    lines = [
        " IDENTIFICATION DIVISION.", " PROGRAM-ID. RECUR.", " DATA DIVISION.", " WORKING-STORAGE SECTION.",
        " 01  WS-N  PIC 9 VALUE 0.", " PROCEDURE DIVISION.", " A-PARA.", "     PERFORM B-PARA UNTIL WS-N > 3.",
        "     GOBACK.", " B-PARA.", "     ADD 1 TO WS-N.", "     PERFORM C-PARA.", " C-PARA.",
        "     IF WS-N = 2", "        GO TO Z-PARA", "     END-IF.", "     PERFORM B-PARA.",
        "     GO TO A-PARA B-PARA DEPENDING ON WS-N.", " Z-PARA.", "     EXIT.",
    ]
    (src / "RECUR.cbl").write_text("".join(f"       {ln[1:]}\n" if ln[0] == " " else ln for ln in lines))
    m = zscan.scan(["src"], root=tmp_path)
    p = prog(m, "RECUR")
    text = " | ".join(w["message"] for w in p["warnings"])
    assert "recursive PERFORM among B-PARA, C-PARA" in text
    assert "DEPENDING ON WS-N" in text
    assert "GO TO Z-PARA at line 15 leaves the range of the loop PERFORM at line 8" in text
    assert stmt(p, "ADD", 11)["in_loop"] == loop(8, "until", "src/RECUR.cbl")


# --------------------------------------------------------------------------- JCL
def test_jcl_job_continuation_set_symbols_and_instream_data(app) -> None:
    job = next(j for j in app["jobs"] if j["name"] == "ORDNIGHT")
    assert job["file"] == "src/jcl/ORDNIGHT.jcl" and job["symbols"] == {"HLQ": "BILLING", "ENV": "PROD"}
    steps = {s["name"]: s for s in job["steps"]}
    assert list(steps) == ["STEP010", "STEP020", "STEP030", "STEP040"]
    s20 = steps["STEP020"]
    assert (s20["pgm"], s20["proc"], s20["cond"], s20["parm"], s20["line"]) == ("ORDMAIN", None, "(4,LT)", "'NIGHTLY,FULL'", 14)
    dds = {d["name"]: d for d in s20["dd"]}
    assert dds["ORDIN"]["dsn"] == "&HLQ..&ENV..ORDERS.DAILY"  # as written
    assert dds["ORDIN"]["dsn_resolved"] == "BILLING.PROD.ORDERS.DAILY"
    assert dds["CUSTMAST"]["disp"] == "OLD"  # from the continuation line
    assert dds["RPTOUT"]["sysout"] == "*" and dds["RPTOUT"]["dsn"] is None
    assert dds["CTLCARD"]["inline"] is True and dds["CTLCARD"]["inline_lines"] == 2
    assert steps["STEP040"]["runs"] == "ORDDB2"


def test_jcl_instream_and_cataloged_procs(app) -> None:
    procs = {p["name"]: p for p in app["procs"]}
    assert procs["ORDSORT"]["source"] == "in-stream" and procs["ORDSORT"]["kind"] == "proc"
    assert procs["ORDPROC"]["source"] == "cataloged" and procs["ORDPROC"]["file"] == "src/proclib/ORDPROC.jcl"
    assert procs["ORDPROC"]["defaults"] == {"HLQ": "TEST", "RPTCLS": "A"}
    job = next(j for j in app["jobs"] if j["name"] == "ORDNIGHT")
    steps = {s["name"]: s for s in job["steps"]}
    sort = steps["STEP010"]
    assert sort["proc"] == "ORDSORT" and sort["proc_source"] == "in-stream"
    sortin = sort["proc_steps"][0]["dd"][0]
    assert (sortin["dsn"], sortin["dsn_resolved"]) == ("&SORTIN", "BILLING.ORDERS.RAW")  # default built on a SET symbol
    assert sort["proc_steps"][0]["dd"][1]["dsn_resolved"] == "&&SORTED"  # temporary data set, not a symbol
    cat = steps["STEP030"]
    assert cat["proc"] == "ORDPROC" and cat["proc_source"] == "cataloged" and cat["overrides"] == {"RPTCLS": "B"}
    rpt = {d["name"]: d for d in cat["proc_steps"][0]["dd"]}
    assert rpt["ORDIN"]["dsn_resolved"] == "TEST.ORDERS.REPRINT"  # PROC default over the job's SET
    assert procs["ORDPROC"]["steps"][0]["dd"][0]["dsn_resolved"] == "TEST.ORDERS.REPRINT"
    edges = {(e["from"], e["to"], e["kind"]) for e in app["edges"]}
    assert ("ORDNIGHT", "ORDSORT", "exec-proc") in edges and ("ORDNIGHT", "ORDPROC", "exec-proc") in edges
    assert ("ORDPROC", "ORDMAIN", "exec-pgm") in edges and ("ORDNIGHT", "ORDMAIN", "exec-pgm") in edges
    assert ("ORDNIGHT:STEP020", "BILLING.PROD.ORDERS.DAILY", "dd-dataset") in edges
    assert ("ORDNIGHT:STEP030.RPT010", "TEST.CUSTOMER.MASTER", "dd-dataset") in edges


def test_program_to_job_links_and_unresolved(app) -> None:
    p = prog(app, "ORDMAIN")
    assert {(r["job"], r["step"]) for r in p["run_by"]} == {("ORDNIGHT", "STEP020"), ("ORDNIGHT", "STEP030.RPT010")}
    assert prog(app, "ORDDB2")["run_by"] == [{"job": "ORDNIGHT", "step": "STEP040", "file": "src/jcl/ORDNIGHT.jcl", "via": "IKJEFT01"}]
    files = {f["name"]: f for f in p["files"]}
    assert {d["dsn_resolved"] for d in files["CUST-FILE"]["datasets"]} == {"BILLING.PROD.CUSTOMER.MASTER", "TEST.CUSTOMER.MASTER"}
    assert ("ORDMAIN", "CUSTMAST", "file-assign") in {(e["from"], e["to"], e["kind"]) for e in app["edges"]}
    un = app["unresolved"]
    assert un["procs"] == [{"name": "MISSPROC", "jobs": ["ORDWEEK"]}]
    assert {x["name"] for x in un["programs"]} == {"ORDAUDIT", "ORDMENU", "TAXCALC"}
    assert {u["name"] for u in app["utilities"]} == {"IKJEFT01", "SORT"}
    assert any("&ARCHHLQ" in w["message"] for w in app["warnings"])
    week = next(j for j in app["jobs"] if j["name"] == "ORDWEEK")
    assert week["steps"][1]["dd"][0]["dsn_resolved"] is None


def test_resolve_symbols_and_operands() -> None:
    syms = {"HLQ": "PROD", "APP": "BILL"}
    assert zscan.resolve_symbols("&HLQ..&APP..DATA", syms) == ("PROD.BILL.DATA", [])
    assert zscan.resolve_symbols("&HLQ.X", syms) == ("PRODX", [])
    assert zscan.resolve_symbols("&&TEMP", syms) == ("&&TEMP", [])
    assert zscan.resolve_symbols("&NOPE..X", syms) == (None, ["NOPE"])
    ops = zscan.split_operands("PGM=X,PARM='A,B',COND=(4,LT),REGION=0M")
    assert ops == [("PGM", "X"), ("PARM", "'A,B'"), ("COND", "(4,LT)"), ("REGION", "0M")]


# --------------------------------------------------------------------------- outputs and safety
def test_output_guard_refuses_bob_and_outside(project) -> None:
    with pytest.raises(zscan.UnsafePath):
        zscan.safe_output_dir(".bob/zos", root=project)
    with pytest.raises(zscan.UnsafePath):
        zscan.safe_output_dir("../elsewhere", root=project)
    with pytest.raises(zscan.UnsafePath):
        zscan.safe_output_dir("/tmp", root=project)
    (project / ".bob").mkdir(exist_ok=True)
    (project / "sneaky").symlink_to(project / ".bob")
    with pytest.raises(zscan.UnsafePath):
        zscan.safe_output_dir("sneaky/map", root=project)
    with pytest.raises(zscan.UnsafePath):
        zscan.safe_output_dir("src/cobol", root=project)  # outputs never land among the sources
    assert zscan.safe_output_dir("zos-insight/map", root=project) == (project / "zos-insight" / "map").resolve()


def test_cli_map_show_and_load(project, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    assert zscan.main(["map", "src/cobol", "--out", ".bob/map"]) == 2
    assert "inside .bob/" in capsys.readouterr().err
    assert not (project / ".bob" / "map").exists()
    assert zscan.main(["map", *ROOTS, "--copy-dir", *COPY]) == 0
    out = capsys.readouterr().out
    assert "Programs: 8 (COBOL 5, PL/I 1, REXX 1, Assembler 1)" in out
    assert "Partial (a copybook or include member was not found): ORDMAIN" in out
    loaded = zscan.load_map()
    assert loaded["version"] == 1 and zscan.find_program(loaded, "ordmain")["id"] == "ORDMAIN"
    md = (project / "zos-insight" / "map" / "app-map.md").read_text()
    assert md.count("```mermaid") == 3 and "## Not found" in md and "AUDITREC" in md
    assert "PURGEALL" not in md
    assert zscan.main(["show", "ORDMAIN"]) == 0
    shown = capsys.readouterr().out
    assert "2100-PRICE-LINE" in shown and "NOT FOUND" in shown and "PRICECAL" in shown
    assert zscan.main(["show", "NOSUCH"]) == 2
    bad = project / "zos-insight" / "map" / "old.json"
    bad.write_text(json.dumps({"version": 99}))
    with pytest.raises(zscan.MapError):
        zscan.load_map(bad)
    assert zscan.code_slice("src/cobol/PRICECAL.cbl", 2, 2)[0][1].endswith("PROGRAM-ID. PRICECAL.")


def test_diagrams_are_capped_and_say_what_was_cut(app) -> None:
    graph = zscan.call_graph(app, limit=2)
    assert "Left out to keep the diagram readable" in graph
    assert graph.count('["') == 2
    flow = zscan.job_flow(app, limit=5)
    assert "ORDWEEK" in flow.split("Left out")[1]
    full = zscan.call_graph(app)
    assert "Left out" not in full and ":::missing" in full


# --------------------------------------------------------------------------- zowe_fetch
class FakeRun:
    def __init__(self, returncode: int = 0):
        self.calls = []
        self.returncode = returncode

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))

        class Proc:
            pass

        proc = Proc()
        proc.returncode, proc.stdout, proc.stderr = self.returncode, "ok", ""
        return proc


@pytest.fixture()
def zowe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = FakeRun()
    monkeypatch.setattr(zowe_fetch.subprocess, "run", fake)
    monkeypatch.setattr(zowe_fetch.shutil, "which", lambda name: "/usr/local/bin/zowe" if name == "zowe" else None)
    return fake


def test_zowe_plan_is_argument_lists_and_runs_nothing(zowe, tmp_path, capsys) -> None:
    plan = zowe_fetch.make_plan("hlq.app.cobol", ["ordmain", "PRICECAL"], profile="lpar1")
    assert plan["commands"] == [
        ["zowe", "zos-files", "download", "data-set", "HLQ.APP.COBOL(ORDMAIN)", "--file",
         "zos-insight/src/HLQ.APP.COBOL/ORDMAIN.cbl", "--zosmf-profile", "lpar1"],
        ["zowe", "zos-files", "download", "data-set", "HLQ.APP.COBOL(PRICECAL)", "--file",
         "zos-insight/src/HLQ.APP.COBOL/PRICECAL.cbl", "--zosmf-profile", "lpar1"],
    ]
    whole = zowe_fetch.make_plan("HLQ.APP.COPYLIB")
    assert whole["commands"] == [["zowe", "zos-files", "download", "all-members", "HLQ.APP.COPYLIB",
                                  "--directory", "zos-insight/src/HLQ.APP.COPYLIB", "--extension", ".cpy"]]
    assert zowe_fetch.make_plan("HLQ.PROD.CNTL", list_only=True)["commands"] == [
        ["zowe", "zos-files", "list", "all-members", "HLQ.PROD.CNTL"]]
    assert zowe_fetch.main(["plan", "--dataset", "HLQ.APP.JCL", "--member", "ORDNIGHT"]) == 0
    out = capsys.readouterr().out
    assert "zowe zos-files download data-set 'HLQ.APP.JCL(ORDNIGHT)' --file zos-insight/src/HLQ.APP.JCL/ORDNIGHT.jcl" in out
    assert (tmp_path / "zos-insight" / "src" / "fetch-plan-HLQ.APP.JCL.json").is_file()
    assert "run --plan zos-insight/src/fetch-plan-HLQ.APP.JCL.json --confirm" in out
    assert zowe.calls == []


def test_zowe_plan_refuses_bad_names_and_folders(zowe) -> None:
    for dsn in ("HLQ.APP;rm", "HLQ..APP", "TOOLONGQUAL.X", "HLQ.APP COBOL", "'HLQ.A'(X)"):
        with pytest.raises(zowe_fetch.Refused):
            zowe_fetch.make_plan(dsn)
    with pytest.raises(zowe_fetch.Refused):
        zowe_fetch.make_plan("HLQ.APP.COBOL", ["TOOLONGNAME"])
    with pytest.raises(zowe_fetch.Refused):
        zowe_fetch.make_plan("HLQ.APP.COBOL", to=".bob/src")
    with pytest.raises(zowe_fetch.Refused):
        zowe_fetch.make_plan("HLQ.APP.COBOL", to="../outside")
    with pytest.raises(zowe_fetch.Refused):
        zowe_fetch.make_plan("HLQ.APP.COBOL", to="cobol")  # never over the user's own sources
    with pytest.raises(zowe_fetch.Refused):
        zowe_fetch.make_plan("HLQ.APP.COBOL", profile="x --password y")
    assert zowe_fetch.main(["plan", "--dataset", "HLQ.APP.COBOL", "--to", ".bob/x"]) == 2


def test_zowe_run_needs_the_confirmed_hash_and_uses_no_shell(zowe, tmp_path) -> None:
    plan = zowe_fetch.make_plan("HLQ.APP.COBOL", ["ORDMAIN"])
    path = zowe_fetch.write_plan(plan)
    assert zowe_fetch.main(["run", "--plan", str(path)]) == 2
    assert zowe_fetch.main(["run", "--plan", str(path), "--confirm", "00000000"]) == 2
    assert zowe.calls == []
    assert zowe_fetch.main(["run", "--plan", str(path), "--confirm", plan["hash8"]]) == 0
    assert len(zowe.calls) == 1
    argv, kwargs = zowe.calls[0]
    assert argv == ["/usr/local/bin/zowe", "zos-files", "download", "data-set", "HLQ.APP.COBOL(ORDMAIN)",
                    "--file", "zos-insight/src/HLQ.APP.COBOL/ORDMAIN.cbl"]
    assert kwargs["shell"] is False
    assert (tmp_path / "zos-insight" / "src" / "HLQ.APP.COBOL").is_dir()


def rehash(plan: dict) -> dict:
    plan["hash"] = zowe_fetch.plan_hash(plan)
    plan["hash8"] = plan["hash"][:8]
    return plan


@pytest.mark.parametrize("tamper", [
    lambda c: c.__setitem__(2, "upload"),
    lambda c: c.__setitem__(2, "submit"),
    lambda c: c.__setitem__(1, "zos-jobs"),
    lambda c: c.__setitem__(6, "../../etc/profile"),
    lambda c: c.__setitem__(6, ".bob/settings.json"),
    lambda c: c.extend(["--password", "secret"]),
    lambda c: c.extend(["--host", "evil.example.com"]),
    lambda c: c.__setitem__(4, "HLQ.OTHER.COBOL(ORDMAIN)"),
])
def test_zowe_run_rechecks_a_tampered_plan(zowe, tamper) -> None:
    plan = zowe_fetch.make_plan("HLQ.APP.COBOL", ["ORDMAIN"])
    path = zowe_fetch.write_plan(plan)
    tamper(plan["commands"][0])
    path.write_text(json.dumps(plan))
    with pytest.raises(zowe_fetch.Refused):  # hash no longer matches
        zowe_fetch.load_and_check(path, plan["hash8"])
    rehash(plan)
    path.write_text(json.dumps(plan))
    with pytest.raises(zowe_fetch.Refused):  # a recomputed hash does not get past the allow-list
        zowe_fetch.load_and_check(path, plan["hash8"])
    assert zowe.calls == []


def test_zowe_allow_list(tmp_path) -> None:
    folder = tmp_path / "zos-insight" / "src" / "HLQ.A"
    ok = ["zowe", "zos-files", "list", "all-members", "HLQ.A"]
    zowe_fetch.check_command(ok, folder, tmp_path)
    for bad in (
        ["zowe", "zos-files", "upload", "file-to-data-set", "x", "HLQ.A"],
        ["zowe", "zos-jobs", "submit", "data-set", "HLQ.A(JOB)"],
        ["zowe", "zos-files", "delete", "data-set", "HLQ.A"],
        ["zowe", "zos-files", "create", "data-set-partitioned", "HLQ.A"],
        ["zowe", "zos-files", "download", "all-members", "HLQ.A"],
        ["sh", "-c", "zowe zos-files list all-members HLQ.A", "x", "y"],
        "zowe zos-files list all-members HLQ.A",
        ok + ["--user", "me"],
    ):
        with pytest.raises(zowe_fetch.Refused):
            zowe_fetch.check_command(bad, folder, tmp_path)
    assert zowe_fetch.guess_extension("HLQ.APP.PROCLIB") == ".jcl"
    assert zowe_fetch.guess_extension("HLQ.APP.DATA") == ".txt"


# --------------------------------------------------------------------------- fields added for the consumer skills
def test_phrases_end_lines_and_else_line(app) -> None:
    p = prog(app, "CUSTUPD")
    read_order = stmt(p, "READ", 38)
    assert read_order["phrases"] == [{"kind": "AT END", "line": 39}, {"kind": "NOT AT END", "line": 41}]
    assert read_order["end_line"] == 43  # END-READ
    read_cust = stmt(p, "READ", 45)
    assert read_cust["phrases"] == [{"kind": "INVALID KEY", "line": 46}, {"kind": "NOT INVALID KEY", "line": 48}]
    assert read_cust["end_line"] == 57
    compute = stmt(p, "COMPUTE", 49)
    assert compute["phrases"] == [{"kind": "ON SIZE ERROR", "line": 50}] and compute["end_line"] == 52
    assert stmt(p, "REWRITE", 54)["phrases"] == [{"kind": "INVALID KEY", "line": 55}]
    assert "phrases" not in stmt(p, "MOVE", 53)
    # the statements inside a phrase are their own records, in the same loop
    assert stmt(p, "ADD", 51)["in_loop"] == loop(34, "until", "src/cobol/CUSTUPD.cbl")
    cond = next(c for c in p["conditions"] if c["kind"] == "IF")
    assert (cond["start_line"], cond["else_line"], cond["end_line"]) == (44, 58, 60)
    assert stmt(p, "IF", 44)["end_line"] == 60
    # a data name that starts with END- is a name, not a terminator
    until = next(c for c in p["conditions"] if c["kind"] == "UNTIL")
    assert until["text"] == "END-OF-ORDERS" and until["tokens"] == ["END-OF-ORDERS"]
    # ORDMAIN: the continued literal ends on its continuation line; SEARCH AT END is a phrase
    m = prog(app, "ORDMAIN")
    assert stmt(m, "MOVE", 79)["end_line"] == 80
    assert stmt(m, "SEARCH", 113)["phrases"] == [{"kind": "AT END", "line": 114}]
    assert stmt(m, "SEARCH", 113)["end_line"] == 118 and stmt(m, "EVALUATE", 99)["end_line"] == 108
    inner_if = next(c for c in m["conditions"] if c["kind"] == "IF" and c["start_line"] == 101)
    assert inner_if["else_line"] == 103
    assert next(c for c in m["conditions"] if c["kind"] == "IF" and c["start_line"] == 75)["else_line"] is None


def test_conditions_carry_tokens_and_the_loop_of_their_statement(app) -> None:
    m = prog(app, "ORDMAIN")
    by = {(c["kind"], c["start_line"]): c for c in m["conditions"]}
    assert by[("SEARCH-WHEN", 115)]["tokens"] == ["RATE-CODE", "(", "RATE-IX", ")", "=", "OR-RATE-CODE"]
    assert by[("SEARCH-WHEN", 115)]["in_loop"] == loop(92, "varying")
    assert by[("WHEN", 100)]["in_loop"] == loop(67, "until")  # the loop of its EVALUATE
    assert by[("UNTIL", 68)]["in_loop"] is None  # the loop around the PERFORM, not its own
    assert by[("UNTIL", 95)]["in_loop"] == loop(92, "varying")
    assert by[("IF", 75)]["in_loop"] is None


def test_perform_end_lines(app) -> None:
    perf = {x["line"]: x for x in prog(app, "ORDMAIN")["performs"]}
    assert perf[81]["end_line"] == 83 and perf[92]["end_line"] == 98 and perf[95]["end_line"] == 97
    assert perf[67]["end_line"] == 68 and perf[66]["end_line"] == 66


def test_data_item_parents_and_names_before_replacing(app) -> None:
    for pid, prefix in (("ORDMAIN", "CM"), ("CUSTUPD", "CU")):
        p = prog(app, pid)
        items = p["data_items"]
        for k, it in enumerate(items):
            if it["parent"] is None:
                assert it["parent_index"] is None
            else:
                assert items[it["parent_index"]]["name"] == it["parent"] and it["parent_index"] < k
        cust = item(p, f"{prefix}-CUST-ID")
        assert cust["name_in_copybook"] == ":PFX:-CUST-ID"
        assert item(p, f"{prefix}-ACTIVE")["name_in_copybook"] == ":PFX:-ACTIVE"
        assert "name_in_copybook" not in item(p, "OR-CUST-ID")  # ORDREC is copied without REPLACING
        books = {c["name"]: c for c in p["copybooks"]}
        assert books["CUSTREC"]["replacing_pairs"] == [[":PFX:", prefix]] and books["ORDREC"]["replacing_pairs"] == []
    assert "name_in_copybook" not in item(prog(app, "ORDMAIN"), "WS-TODAY-YYYY")  # nested, no REPLACING of its own


def test_sql_text_multi_row_and_includes(app) -> None:
    db2 = prog(app, "ORDDB2")
    assert db2["sql_includes"] == ["SQLCA"]
    by_verb = {s["verb"]: s for s in db2["sql"]}
    assert by_verb["SELECT"]["text"] == "SELECT SUM(AMOUNT) INTO :WS-TOTAL FROM BILLING.ORDERS WHERE CUST_ID = :WS-CUST-ID"
    assert (by_verb["SELECT"]["line"], by_verb["SELECT"]["end_line"]) == (31, 35)
    assert not any(s["multi_row"] for s in db2["sql"])
    assert zscan.parse_sql("FETCH NEXT ROWSET FROM C1 FOR 10 ROWS INTO :A")["multi_row"] is True
    assert zscan.parse_sql("INSERT INTO T (A) VALUES (:A) FOR :N ROWS")["multi_row"] is True
    assert zscan.parse_sql("SELECT A INTO :A FROM T FOR UPDATE OF A")["multi_row"] is False
    assert prog(app, "ORDMAIN")["sql_includes"] == []
    assert prog(app, "PRICECAL")["procedure_using_line"] == 10 and prog(app, "ORDMAIN")["procedure_using_line"] is None
    cics = {c["command"]: c for c in prog(app, "ORDCICS")["cics"]}
    assert (cics["READ"]["line"], cics["READ"]["end_line"]) == (12, 14)


def test_read_source_caches_and_sees_changes(tmp_path) -> None:
    f = tmp_path / "zos-insight" / "x.cbl"
    f.parent.mkdir()
    f.write_text("A\nB\n")
    first = zscan.read_source("zos-insight/x.cbl", root=tmp_path)
    assert first == ["A", "B"] and zscan.read_source(str(f)) is first
    f.write_text("A\nB\nC\n")
    assert zscan.read_source("zos-insight/x.cbl", root=tmp_path) == ["A", "B", "C"]
    assert zscan.code_slice(str(f), 2, 9) == [(2, "B"), (3, "C")]
    with pytest.raises(OSError):
        zscan.read_source("zos-insight/none.cbl", root=tmp_path)


def test_reports_name_the_scanned_folder_not_the_whole_path(tmp_path):
    """Sources outside the project keep their full path in the JSON but not in the report."""
    import shutil
    outside = tmp_path / "elsewhere" / "mainframe-src"
    shutil.copytree(FIXTURES, outside)
    project = tmp_path / "project"
    project.mkdir()
    app_map = zscan.scan([outside / "cobol", outside / "jcl"], copy_dirs=[outside / "copy"], root=project)
    some_file = app_map["programs"][0]["file"]
    assert Path(some_file).is_absolute()
    text = zscan.render_markdown(app_map)
    assert str(outside / "cobol") + "/" not in text
    assert "cobol/" in text


# --------------------------------------------------------------------------- languages (1.1): links across languages
LANG = Path(__file__).parent / "fixtures" / "zos-app-insight-lang"
LANG_ROOTS = ["src/pli/src", "src/rexx", "src/asm/src", "src/xlang"]
LANG_COPY = ["src/pli/inc", "src/asm/copy", "src/asm/maclib"]


@pytest.fixture(scope="module")
def xproject(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("xlang")
    shutil.copytree(LANG, root / "src")
    return root


@pytest.fixture(scope="module")
def xapp(xproject) -> dict:
    return zscan.scan(LANG_ROOTS, LANG_COPY, root=xproject)


def test_every_language_is_a_program_of_the_map(xapp) -> None:
    langs = {p["id"]: p["language"] for p in xapp["programs"]}
    assert langs == {"BILLMAIN": "pli", "BILLSUB": "pli", "BILLCALC": "pli", "ORDLOAD": "rexx", "ORDMENU": "rexx",
                     "BILLRUN": "asm", "BILLSQL": "asm", "BILLDRV": "cobol"}
    includes = {(c["name"], c["language"]) for c in xapp["copybooks"]}
    assert {("BILLREC", "pli"), ("BILLREC", "asm"), ("ORDUTIL", "rexx"), ("BSAVE", "asm")} <= includes
    assert xapp["not_analysed"]["rexx"] == ["src/rexx/ORDCLEAN.clist"]  # a CLIST: listed, not analysed


def test_jcl_steps_run_pli_assembler_and_rexx(xapp) -> None:
    progs = {p["id"]: p for p in xapp["programs"]}
    runs = lambda pid: {(r["step"], r.get("via"), r.get("entry")) for r in progs[pid]["run_by"]}  # noqa: E731
    assert runs("BILLMAIN") == {("PRICE", None, None)}
    assert runs("BILLCALC") == {("RERATE", None, "RECALC")}  # EXEC PGM= of a PL/I secondary entry
    assert runs("BILLRUN") == {("USAGE", None, None)}
    assert runs("ORDLOAD") == {("LOAD", "IKJEFT01", None), ("BATCHRX", "IRXJCL", None)}
    assert runs("ORDMENU") == {("LOAD", "IKJEFT01", None)}  # EXEC 'BILL.EXEC(ORDMENU)'
    step = next(s for s in xapp["jobs"][0]["steps"] if s["name"] == "LOAD")
    assert step["execs"] == [{"name": "ORDLOAD", "how": "%", "line": 13}, {"name": "ORDMENU", "how": "EXEC", "line": 14}]
    edges = {(e["from"], e["to"], e.get("via"), e.get("entry")) for e in xapp["edges"] if e["kind"] == "exec-pgm"}
    assert {("BILLJOB", "BILLMAIN", None, None), ("BILLJOB", "BILLCALC", None, "RECALC"), ("BILLJOB", "BILLRUN", None, None),
            ("BILLJOB", "ORDLOAD", "IKJEFT01", None), ("BILLJOB", "ORDMENU", "IKJEFT01", None)} <= edges
    # edges are unique by (from, to, kind): the IRXJCL step shows in run_by above
    assert "LISTCAT" not in {u["name"] for u in xapp["unresolved"]["programs"]}  # a TSO command, not an exec
    assert {u["name"] for u in xapp["utilities"]} == {"IKJEFT01", "IRXJCL"}


def test_cobol_calls_reach_a_pli_entry_and_an_assembler_entry(xapp) -> None:
    calls = {(e["to"], e.get("entry")) for e in xapp["edges"] if e["kind"] == "call" and e["from"] == "BILLDRV"}
    assert calls == {("BILLCALC", "RECALC"), ("BILLRUN", "BILLALT")}
    assert zscan.callers(xapp, "BILLCALC") == ["BILLDRV"] and zscan.callers(xapp, "BILLRUN") == ["BILLDRV"]
    missing = {u["name"] for u in xapp["unresolved"]["programs"]}
    assert not {"RECALC", "BILLALT", "BILLCALC", "BILLRUN"} & missing
    # the languages' own calls: PL/I FETCH, REXX LINKMVS and TSO EXEC, Assembler LINK; system routines are neither
    vias = {(e["from"], e["to"], e.get("via")) for e in xapp["edges"] if e["kind"] == "call"}
    assert {("BILLMAIN", "BILLTX01", "FETCH"), ("ORDLOAD", "PRICECAL", "LINKMVS"), ("ORDMENU", "ORDLOAD", "TSO EXEC"),
            ("BILLRUN", "PRTFMT", "LINK"), ("BILLMAIN", "BILLSUB", None)} <= vias
    assert not {"BPXWDYN", "RXSUBCOM"} & missing and not any(e["to"] in ("BPXWDYN", "RXSUBCOM") for e in xapp["edges"])


def test_unresolved_includes_and_macros(xapp) -> None:
    un = xapp["unresolved"]
    assert {c["name"]: [p["id"] for p in c["programs"]] for c in un["copybooks"]} == {
        "AUDITDS": ["BILLRUN"], "AUDITPL": ["BILLMAIN"]}
    assert un["macros"] == [{"name": "TRACEPT", "programs": [{"id": "BILLRUN", "file": "src/asm/src/BILLRUN.asm",
                                                              "line": 34}]}]


def test_a_rexx_exec_pulled_in_by_another_is_an_include(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "MAINX.rexx").write_text("/* REXX - original test exec */\ncall helper\nexit 0\n"
                                                  "/*%INCLUDE HELPX*/\n")
    (tmp_path / "src" / "HELPX.rexx").write_text("/* REXX - original test exec, also included */\n"
                                                  "say 'help'\nexit 0\n")
    m = zscan.scan(["src"], root=tmp_path)
    assert [p["id"] for p in m["programs"]] == ["MAINX"]
    assert [(c["name"], c["language"], c["used_by"]) for c in m["copybooks"]] == [("HELPX", "rexx", ["MAINX"])]


def test_tso_batch_input() -> None:
    lines = ["  %ORDLOAD 2026", "  DSN SYSTEM(DB2P)", "  RUN PROGRAM(ORDDB2)", "  END",
             "  EX 'BILL.EXEC(ORDMENU)'", "  CALL 'BILL.LOAD(PRICER)'", "  LISTDS 'BILL.X'", "  ORDHELP", "/* end"]
    assert zscan.tso_commands(lines, 10) == [
        {"name": "ORDLOAD", "how": "%", "line": 10}, {"name": "ORDMENU", "how": "EXEC", "line": 14},
        {"name": "PRICER", "how": "CALL", "line": 15}, {"name": "ORDHELP", "how": "implicit", "line": 17}]


def test_markdown_and_show_speak_each_language(xapp, xproject, monkeypatch, capsys) -> None:
    md = zscan.render_markdown(xapp)
    assert "| Program | Language |" in md and "| BILLRUN | Assembler |" in md and "margins 2-72" in md
    assert "## Commands that change data" in md and "| ORDLOAD |" in md
    assert "Assembler macro TRACEPT" in md and "BILLCALC (PL/I)" in md
    monkeypatch.chdir(xproject)
    zscan.write_map(xapp)
    assert zscan.main(["show", "BILLRUN"]) == 0
    out = capsys.readouterr().out
    assert "BILLRUN  Assembler" in out and "BCT to READLOOP, count, confidence high" in out and "TRACEPT@34" in out
    assert zscan.main(["show", "ORDMENU"]) == 0
    out = capsys.readouterr().out
    assert "Host command environments: TSO" in out and "Commands that change data or submit jobs:" in out
    assert "BPXWDYN (function)  (supplied by z/OS)" in out
    assert zscan.main(["show", "BILLMAIN"]) == 0
    out = capsys.readouterr().out
    assert "Procedures, BEGIN blocks and ON-units:" in out and "[on-unit]" in out and "handlers: ON ENDFILE@45" in out
