"""zos-app-insight, skill zos-app-map: zscan_rexx.py, the REXX language module of the map.

The fixtures under fixtures/zos-app-insight-lang/rexx are original synthetic execs written
for these tests (see their README). The module is called directly; zscan.scan does not
dispatch to it yet (that is the integration step).
"""

from __future__ import annotations

import ast
import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "packs" / "ibm" / "zos-app-insight" / "skills" / "zos-app-map" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures" / "zos-app-insight-lang" / "rexx"
COBOL_FIXTURES = Path(__file__).parent / "fixtures" / "zos-app-insight"

if str(SCRIPTS) not in sys.path:  # the language modules import zscan from their own folder
    sys.path.insert(0, str(SCRIPTS))
zscan = importlib.import_module("zscan")
zr = importlib.import_module("zscan_rexx")


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("proj")
    shutil.copytree(FIXTURES, root / "src" / "rexx")
    return root


def scan(project: Path, name: str) -> dict:
    return zr.scan_program(Path("src/rexx") / name, ["src/rexx"], root=project)


@pytest.fixture(scope="module")
def load(project) -> dict:
    return scan(project, "ORDLOAD.rexx")


@pytest.fixture(scope="module")
def menu(project) -> dict:
    return scan(project, "ORDMENU.rexx")


def stmt(p: dict, verb: str, line: int) -> dict:
    return next(s for s in p["statements"] if s["verb"] == verb and s["line"] == line and not s.get("copybook"))


def write(tmp_path: Path, name: str, text: str) -> dict:
    (tmp_path / name).write_text(text)
    return zr.scan_program(tmp_path / name, [], root=tmp_path)


def loop(line: int, kind: str, file: str = "src/rexx/ORDLOAD.rexx") -> dict:
    return {"via": line, "kind": kind, "file": file}


# --------------------------------------------------------------------------- module contract
def test_module_interface_and_no_import_side_effects():
    assert zr.LANGUAGE == "rexx"
    assert callable(zr.classify) and callable(zr.scan_program)
    tree = ast.parse((SCRIPTS / "zscan_rexx.py").read_text())
    stdlib = set(sys.stdlib_module_names)
    for node in tree.body:
        assert isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign,
                                 ast.FunctionDef, ast.ClassDef)), ast.dump(node)[:80]
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant)  # the docstring only
        if isinstance(node, ast.Import):
            assert all(a.name.split(".")[0] in stdlib | {"zscan"} for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] in stdlib | {"__future__"}


def test_classify(project):
    rexx = project / "src" / "rexx"
    kinds = {p.name: zr.classify(p, p.read_text()) for p in sorted(rexx.iterdir()) if p.suffix != ".md"}
    assert kinds == {"ORDCLEAN.clist": "skip", "ORDLOAD.rexx": "program", "ORDMENU.rexx": "program",
                     "ORDUTIL.rexx": "include"}
    assert zr.classify("X.rexx", "say 'no marker, but a .rexx file'\n") == "program"
    assert zr.classify("X.clist", "/* REXX */\nsay 'a REXX exec kept in a CLIST library'\n") == "program"
    assert zr.classify("X.txt", "PROC 1 NAME\nWRITE &NAME\n") == "skip"
    assert zr.classify("X.rexx", "/*%INCLUDE PARTA */\n/*%INCLUDE PARTB */\n") == "include"
    assert zr.classify("X.rexx", "/* REXX */\nmain:\n  call setup\n  exit\nsetup: return\n") == "program"


def test_record_has_the_shape_of_a_cobol_record(load):
    cobol = zscan.scan([COBOL_FIXTURES / "cobol"], [COBOL_FIXTURES / "copy"], root=COBOL_FIXTURES)
    ref = cobol["programs"][0]
    assert set(ref) - {"partial", "run_by"} <= set(load)  # scan adds those two to every program
    assert load["language"] == "rexx"

    def required(key: str) -> set:
        sets = [set(r) for p in cobol["programs"] for r in p[key]]
        return set.intersection(*sets) if sets else set()

    for key in ("copybooks", "paragraphs", "performs", "calls", "gotos", "sql", "conditions", "statements"):
        assert load[key], key
        need = required(key)
        for rec in load[key]:
            assert need <= set(rec), (key, need - set(rec))
    for f in load["files"]:
        assert required("files") - {"datasets"} <= set(f)  # scan adds datasets from the job steps
    assert load["data_items"] == [] and load["sections"] == [] and load["cics"] == [] and load["sql_includes"] == []


def test_program_basics(project, load):
    path = project / "src" / "rexx" / "ORDLOAD.rexx"
    assert load["id"] == "ORDLOAD"
    assert load["file"] == "src/rexx/ORDLOAD.rexx"
    assert load["format"] == "free"
    assert load["lines"] == len(path.read_text().splitlines())
    assert load["sha256"] == zscan.sha256_file(path)
    text = json.dumps(load)  # serialisable, no private keys left

    def keys(x):
        if isinstance(x, dict):
            for k, v in x.items():
                yield k
                yield from keys(v)
        elif isinstance(x, list):
            for v in x:
                yield from keys(v)

    assert not [k for k in keys(json.loads(text)) if k.startswith("_")]


def test_scan_writes_nothing(project):
    before = {p: p.stat().st_mtime_ns for p in project.rglob("*")}
    scan(project, "ORDLOAD.rexx")
    assert {p: p.stat().st_mtime_ns for p in project.rglob("*")} == before


# --------------------------------------------------------------------------- lexical structure
def test_nested_comment_doubled_quotes_and_continuation(load):
    first = load["statements"][0]
    assert (first["verb"], first["line"]) == ("PARSE", 6)  # the nested comment did not end the header early
    assert stmt(load, "SAY", 9)["operands"][0] == "'ORDLOAD can''t run twice a day; run date'"
    assert stmt(load, "SAY", 10)["operands"] == ['"Mode ""TEST"" bills nothing"']
    alloc = stmt(load, "TSO", 14)
    assert alloc["end_line"] == 15
    assert alloc["text"] == ("ALLOC FI(ORDOUT) DA('BILL.ORDERS.PRICED') NEW CATALOG SPACE(5,5) TRACKS "
                             "RECFM(F B) LRECL(80)")
    assert alloc["options"]["space"] == "5,5" and alloc["options"]["new"] is True


def test_comma_continuation_inside_a_call_and_concatenation(tmp_path):
    rec = write(tmp_path, "CONT.rexx", "/* REXX */\ncall work a,,\n  b\nexit\nwork: return\n")
    pr = rec["performs"][0]
    assert (pr["to"], pr["line"], pr["end_line"], pr["using"]) == ("WORK", 2, 3, ["a", "b"])
    rec = write(tmp_path, "CAT.rexx", '/* REXX */\n"FREE" || " FI("ddn")"\n"FREE FI("ddn2 ||")"\nddn2 = "A"\n')
    texts = [s["text"] for s in rec["statements"] if s["verb"] == "TSO"]
    assert texts == ["FREE FI(DDN)", "FREE FI({ddn2})"]  # a symbol never assigned stands for its own name


# --------------------------------------------------------------------------- labels, CALL, functions
def test_labels_and_internal_calls(load):
    paras = {p["name"]: p for p in load["paragraphs"]}
    assert list(paras) == ["PRICE_LINE", "CHECK_CONTROL", "FAILED", "NOVALUE", "FMT_AMOUNT"]
    assert paras["PRICE_LINE"] == {"name": "PRICE_LINE", "section": None, "start_line": 75, "end_line": 80,
                                   "procedure": True, "expose": ["TOTAL", "LINETOTAL"]}
    assert paras["FMT_AMOUNT"]["copybook"] == "ORDUTIL" and paras["FMT_AMOUNT"]["start_line"] == 3
    performs = [(p["from"], p["to"], p["line"], p["via"]) for p in load["performs"]]
    assert performs == [(None, "PRICE_LINE", 21, "CALL"), (None, "CHECK_CONTROL", 30, "CALL"),
                        ("CHECK_CONTROL", "FMT_AMOUNT", 85, "function")]
    assert load["performs"][0]["using"] == ["custId", "qty", "price"]
    assert all(p["thru"] is None and p["loop"] is None and p["inline"] is False for p in load["performs"])


def test_external_routines_and_built_ins(load):
    calls = {(c["target"], c["via"]): c for c in load["calls"]}
    assert set(calls) == {("ORDAUDIT", "CALL"), ("ORDSTAMP", "function"), ("ORDWAIT", "CALL"),
                          ("PRICECAL", "LINKMVS"), ("RXSUBCOM", "function")}
    assert calls[("ORDAUDIT", "CALL")]["using"] == ["'START'", "runDate"]
    assert calls[("RXSUBCOM", "function")]["system"] is True
    assert not any(c.get("system") for c in load["calls"] if c["target"] != "RXSUBCOM")
    targets = {c["target"] for c in load["calls"]}
    for builtin in ("WORDS", "LEFT", "RIGHT", "SYSDSN", "SUBSTR", "FORMAT"):
        assert builtin not in targets
    assert all(c["dynamic"] is False for c in load["calls"])


def test_parse_arg_and_variables(load):
    assert load["procedure_using"] == ["RUNDATE", "MODE"]
    assert load["procedure_using_line"] == 6
    v = {x["name"]: x for x in load["variables"]}
    assert v["ORD."]["kind"] == "stem" and v["ORD."]["set_by"] == [{"how": "EXECIO DISKR", "line": 17}]
    assert v["CTL."]["set_by"] == [{"how": "EXECIO DISKR", "line": 28}]
    assert v["CUSTID"] == {"name": "CUSTID", "kind": "simple", "line": 20,
                           "set_by": [{"how": "PARSE VAR", "line": 20}]}
    assert {"how": "PARSE ARG", "line": 76} in v["QTY"]["set_by"]
    assert v["CUSTNAME"]["set_by"] == [{"how": "EXECSQL FETCH", "line": 63}]
    assert v["AMOUNT"]["copybook"] == "ORDUTIL"
    assert "TOTAL" not in v  # plain assignments are not listed; REXX has no declarations
    assert load["data_items"] == []


def test_signal_and_traps(load):
    assert load["gotos"] == [{"to": ["FAILED"], "line": 16, "paragraph": None, "depending_on": None}]
    assert load["traps"] == [{"condition": "NOVALUE", "action": "SIGNAL", "on": True, "target": "NOVALUE",
                              "line": 7, "paragraph": None, "resolved": True}]


# --------------------------------------------------------------------------- files
def test_execio_alloc_and_free(load):
    files = {f["name"]: f for f in load["files"]}
    assert list(files) == ["ORDIN", "ORDOUT", "ORDCTL"]
    ordin = files["ORDIN"]
    assert (ordin["kind"], ordin["dd"], ordin["access"], ordin["dsns"]) == ("DD", "ORDIN", "SEQUENTIAL",
                                                                           ["'BILL.ORDERS.DAILY'"])
    assert [(i["verb"], i.get("mode"), i.get("disp"), i["line"]) for i in ordin["io"]] == [
        ("ALLOC", None, "SHR", 13), ("EXECIO", "DISKR", None, 17), ("FREE", None, None, 71)]
    assert ordin["io"][1]["stem"] == "ORD." and ordin["io"][1]["options"] == ["FINIS"]
    out = files["ORDOUT"]["io"]
    assert out[0]["verb"] == "ALLOC" and out[0]["disp"] == "NEW" and out[0]["changes"] is True
    assert out[1]["verb"] == "EXECIO" and out[1]["mode"] == "DISKW" and out[1]["changes"] is True
    assert out[1]["in_loop"] == loop(19, "iterative")
    ctl = files["ORDCTL"]
    assert ctl["dsns"] == []  # allocated outside the exec (by the JCL)
    assert [(i["count"], i.get("options"), i["in_loop"]) for i in ctl["io"]] == [
        ("0", ["OPEN"], None), ("1", None, loop(27, "while")), ("0", ["FINIS"], None)]
    assert not any(i.get("changes") for i in ordin["io"] + ctl["io"])


def test_variables_set_outside_assignments_stay_unknown(tmp_path):
    rec = write(tmp_path, "SETBY.rexx", "/* REXX */\npgm = 'ORDCALC'\n\"CALL 'BILL.LOADLIB(\"pgm\")'\"\n"
                                        "address dsnrexx \"EXECSQL FETCH C1 INTO :hv\"\n\"FREE FI(\"hv\")\"\n"
                                        "\"FREE FI(\"rc\")\"\n\"FREE FI(\"sysdsname\")\"\n\"FREE FI(\"plain\")\"\n")
    call = rec["calls"][0]
    assert (call["target"], call["dynamic"], call["candidates"], call["library"]) == (
        "PGM", True, ["ORDCALC"], "BILL.LOADLIB")
    frees = [s["text"] for s in rec["statements"] if s.get("command") == "FREE"]
    assert frees == ["FREE FI({hv})", "FREE FI({rc})", "FREE FI({sysdsname})", "FREE FI(PLAIN)"]


def test_dynamic_dd_name(tmp_path):
    rec = write(tmp_path, "DYN.rexx", '/* REXX */\ndd = \'WORKDD\'\n"EXECIO * DISKR" dd "(STEM in."\n')
    f = rec["files"][0]
    assert (f["name"], f["dd"], f["dynamic"], f["candidates"]) == ("{DD}", None, True, ["WORKDD"])
    assert rec["statements"][1]["text"] == "EXECIO * DISKR {dd} (STEM in." and rec["statements"][1]["dynamic"]


# --------------------------------------------------------------------------- control flow
def test_loops_and_in_loop(load):
    loops = [(x["line"], x["end_line"], x["kind"], x["control"], x["leave_lines"]) for x in load["loops"]]
    assert loops == [(19, 24, "iterative", "I", []), (27, 31, "while", None, []), (42, 47, "forever", None, [44, 45]),
                     (67, 69, "times", None, [])]
    assert stmt(load, "DO", 19)["loop"] == "iterative" and stmt(load, "DO", 35)["loop"] is None
    assert stmt(load, "QUEUE", 22)["in_loop"] == loop(19, "iterative")
    assert stmt(load, "LEAVE", 44)["in_loop"] == loop(42, "forever")
    assert stmt(load, "QUEUE", 68)["in_loop"] == loop(67, "times")
    assert stmt(load, "SAY", 36)["in_loop"] is None  # a plain DO ... END group is not a loop
    # routines called from a loop: the loop reaches them through CALL and a function call
    assert stmt(load, "ASSIGN", 77)["in_loop"] == loop(19, "iterative")
    assert stmt(load, "SAY", 85)["in_loop"] == loop(27, "while")
    fmt = next(s for s in load["statements"] if s.get("copybook") == "ORDUTIL" and s["verb"] == "RETURN")
    assert fmt["in_loop"] == loop(27, "while")
    calls = {c["target"]: c for c in load["calls"]}
    assert calls["ORDWAIT"]["in_loop"] == loop(42, "forever") and calls["ORDAUDIT"]["in_loop"] is None
    assert stmt(load, "SAY", 89)["in_loop"] is None  # FAILED is reached by SIGNAL only


def test_conditions(load):
    conds = [(c["kind"], c["text"], c["start_line"], c["end_line"]) for c in load["conditions"]]
    assert conds[:5] == [("IF", "rc <> 0", 16, 16), ("WHILE", "more", 27, 27), ("IF", "rc = 2", 29, 30),
                         ("WHEN", "mode = 'TEST'", 34, 34), ("WHEN", "mode = 'RERUN'", 35, 38)]
    if_rc = load["conditions"][2]
    assert if_rc["else_line"] == 30 and if_rc["data_items"] == ["RC"] and if_rc["in_loop"] == loop(27, "while")
    when = load["conditions"][3]
    assert when["subject"] is None and when["select_line"] == 33 and when["tokens"] == ["mode", "=", "'TEST'"]
    assert stmt(load, "SELECT", 33)["end_line"] == 40 and stmt(load, "SELECT", 33)["otherwise_line"] == 39
    qty = next(c for c in load["conditions"] if c["text"] == "qty > 100")
    assert qty["paragraph"] == "PRICE_LINE" and qty["in_loop"] == loop(19, "iterative")


def test_else_pairs_with_the_nearest_if(tmp_path):
    rec = write(tmp_path, "IFS.rexx", "/* REXX */\nif a then\n  if b then say 1\n  else say 2\nelse say 3\n")
    ifs = [(c["text"], c["start_line"], c["end_line"], c["else_line"]) for c in rec["conditions"]]
    assert ifs == [("a", 2, 5, 5), ("b", 3, 4, 4)]


# --------------------------------------------------------------------------- host commands
def test_host_command_environments(load):
    assert load["environments"] == ["TSO", "ISPEXEC", "LINKMVS", "DSNREXX"]
    vget = stmt(load, "ISPEXEC", 49)
    assert (vget["command"], vget["address_line"], vget["text"]) == ("VGET", 48, "VGET (ZUSER) SHARED")
    assert stmt(load, "ISPEXEC", 50)["options"] == {"panel": "ORDPAN1"}
    assert stmt(load, "ADDRESS", 48)["environment"] == "ISPEXEC"
    assert stmt(load, "TSO", 13)["address_line"] is None  # the TSO default before any ADDRESS
    assert stmt(load, "TSO", 70)["address_line"] == 66
    run = stmt(load, "LINKMVS", 53)
    assert (run["command"], run["address_line"]) == ("PRICECAL", 53)
    pricecal = next(c for c in load["calls"] if c["target"] == "PRICECAL")
    assert pricecal["using"] == ["PARMAREA"] and pricecal["line"] == 53


def test_dsnrexx_execsql(load):
    sql = {s["line"]: s for s in load["sql"]}
    assert [(s["verb"], s["cursor"]) for s in load["sql"]] == [
        ("DECLARE CURSOR", "C1"), ("PREPARE", None), ("OPEN", "C1"), ("FETCH", "C1"), ("CLOSE", "C1")]
    prep = sql[61]
    assert prep["sql_from"] == "SQLTEXT" and prep["statement"] == "S1"
    assert prep["candidates"] == [{"line": 58, "text": "SELECT CUST_NAME FROM BILL.CUSTOMER WHERE CUST_ID = ?",
                                   "verb": "SELECT", "tables": ["BILL.CUSTOMER"]}]
    for line in (60, 61, 62, 63, 64):
        assert sql[line]["tables"] == ["BILL.CUSTOMER"] and sql[line]["dynamic"] is True
    assert sql[63]["host_vars"] == ["CUSTNAME"] and sql[63]["text"] == "FETCH C1 INTO :custName"
    assert stmt(load, "DSNREXX", 57)["command"] == "CONNECT"  # a DSNREXX command, not SQL
    assert len(load["sql"]) == 5


def test_changes_are_marked(load, menu):
    changed = [(s["verb"], s["command"] if "command" in s else None, s["line"]) for s in load["statements"]
               if s.get("changes")]
    assert changed == [("TSO", "ALLOC", 14), ("TSO", "EXECIO", 23), ("TSO", "DELETE", 37), ("TSO", "SUBMIT", 70)]
    assert stmt(load, "TSO", 37)["datasets"] == ["'BILL.ORDERS.PRICED.OLD'"]
    assert stmt(load, "TSO", 70)["datasets"] == ["'BILL.JCL(ORDNIGHT)'"]
    assert "changes" not in stmt(load, "TSO", 13)  # ALLOC SHR
    menu_changed = [(s["verb"], s.get("command"), s["line"]) for s in menu["statements"] if s.get("changes")]
    assert menu_changed == [("ASSIGN", None, 19), ("SYSCALL", "WRITEFILE", 20), ("MVS", "EXECIO", 21),
                            ("ISREDIT", "SAVE", 22)]


def test_menu_program_runs_and_warnings(menu):
    calls = {(c["target"], c["via"]): c for c in menu["calls"]}
    assert set(calls) == {("PROG", "LINKMVS"), ("ORDARCH", "ATTCHMVS"), ("ORDPURGE", "TSO CALL"),
                          ("ORDRPT", "TSO %"), ("ORDLOAD", "TSO EXEC"), ("ORDHELP", "ISPEXEC SELECT CMD"),
                          ("ORDBROW", "ISPEXEC SELECT PGM"), ("BPXWDYN", "function")}
    dyn = calls[("PROG", "LINKMVS")]
    assert dyn["dynamic"] is True and dyn["candidates"] == ["ORDSTAT", "ORDSUMM"] and dyn["using"] == ["CHOICE"]
    assert calls[("ORDPURGE", "TSO CALL")]["library"] == "BILL.LOADLIB"
    assert calls[("ORDLOAD", "TSO EXEC")]["library"] == "BILL.EXEC"
    assert calls[("ORDLOAD", "TSO EXEC")]["using"] == ["'TEST'"]
    assert calls[("ORDBROW", "ISPEXEC SELECT PGM")]["using"] == ["DAILY"]
    assert calls[("BPXWDYN", "function")]["system"] is True
    assert stmt(menu, "TSO", 4)["command"] == "NEWSTACK"  # unquoted and never assigned: its own name
    tmp = menu["files"][0]
    assert tmp["name"] == "ORDTMP" and [(i["verb"], i.get("via"), i.get("changes")) for i in tmp["io"]] == [
        ("ALLOC", "BPXWDYN", True), ("EXECIO", None, True)]
    v = {x["name"]: x for x in menu["variables"]}
    assert v["LST."]["set_by"] == [{"how": "OUTTRAP", "line": 6}] and "OFF" not in v
    assert menu["traps"][0]["action"] == "CALL" and menu["traps"][0]["target"] == "CMD_ERROR"
    messages = [w["message"] for w in menu["warnings"]]
    assert any("ALTLIB" in m for m in messages) and any("LIBDEF" in m for m in messages)
    assert menu["procedure_using"] == ["CHOICE"]


# --------------------------------------------------------------------------- %INCLUDE
def test_include_directive(load, tmp_path):
    assert load["copybooks"] == [{"name": "ORDUTIL", "library": None, "resolved": "src/rexx/ORDUTIL.rexx",
                                  "replacing": False, "line": 95, "nested_in": None, "replacing_pairs": []}]
    assert any("compiler directive" in w["message"] for w in load["warnings"])
    assert not any(c["target"] == "FMT_AMOUNT" for c in load["calls"])  # internal once the member is expanded
    rec = write(tmp_path, "MISS.rexx", "/* REXX */\nsay fmt(1)\nexit\n/*%INCLUDE NOSUCH */\n")
    assert rec["copybooks"][0]["resolved"] is None
    assert [c["target"] for c in rec["calls"]] == ["FMT"]
    assert any("NOSUCH not found" in w["message"] for w in rec["warnings"])


def test_include_by_library_name(tmp_path):
    for lib in ("LIBA", "LIBB"):
        (tmp_path / lib).mkdir()
        (tmp_path / lib / "PART.rexx").write_text(f"part_{lib.lower()}: return\n")
    (tmp_path / "MAIN.rexx").write_text("/* REXX */\ncall part_libb\nexit\n/*%INCLUDE LIBB(PART) */\n")
    rec = zr.scan_program("MAIN.rexx", ["LIBA", "LIBB"], root=tmp_path)
    assert rec["copybooks"][0]["resolved"] == "LIBB/PART.rexx" and rec["copybooks"][0]["library"] == "LIBB"
    assert rec["performs"][0]["to"] == "PART_LIBB"


# --------------------------------------------------------------------------- honest about the unknown
def test_run_time_choices_are_warnings(tmp_path):
    rec = write(tmp_path, "RUNTIME.rexx", "/* REXX */\ninterpret 'say' x\naddress value envName\n'LISTCAT'\n"
                                          "signal value 'L'n\ncall ON halt\nend\n")
    messages = " | ".join(w["message"] for w in rec["warnings"])
    for part in ("INTERPRET", "ADDRESS VALUE", "SIGNAL VALUE", "label HALT is not in this exec", "END without DO"):
        assert part in messages
    assert rec["gotos"][0]["to"] == [] and rec["gotos"][0]["depending_on"] == "'L'n"
    assert next(s for s in rec["statements"] if s["line"] == 4)["verb"] == "UNKNOWN"


def test_unclosed_do_and_recursion(tmp_path):
    rec = write(tmp_path, "OPEN.rexx", "/* REXX */\ndo forever\n  say 'x'\nlbl:\n  say 'y'\n")
    assert rec["loops"][0]["end_line"] == 3
    assert any("inside the open DO of line 2" in w["message"] for w in rec["warnings"])
    rec = write(tmp_path, "REC.rexx", "/* REXX */\ndo 3\n  call ping\nend\nexit\nping: call pong\n  return\n"
                                      "pong: call ping\n  return\n")
    assert any("recursive routine calls among PING, PONG" in w["message"] for w in rec["warnings"])
    assert all(s["in_loop"] == {"via": 2, "kind": "times", "file": "REC.rexx"}
               for s in rec["statements"] if s["paragraph"] in ("PING", "PONG"))


def test_routine_without_return_runs_into_the_next_label(tmp_path):
    rec = write(tmp_path, "FALL.rexx", "/* REXX */\ndo 2\n  call first\nend\nexit\nfirst:\n  x = 1\n"
                                       "second:\n  y = 2\n  return\nthird:\n  z = 3\n  return\n")
    in_loop = {s["paragraph"]: s["in_loop"] for s in rec["statements"] if s["paragraph"]}
    assert in_loop["FIRST"] and in_loop["SECOND"] and in_loop["THIRD"] is None
