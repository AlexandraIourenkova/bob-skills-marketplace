"""zos-app-insight, skill cobol-perf-review: perf.py (COBOL performance checks on the map).

The fixtures under fixtures/zos-app-insight/perf are original synthetic COBOL written for
these tests (see its README): PERFPOS has one positive case per check, PERFNEG the tuned
or loop-free twin of each, PERFPART a missing copybook, PERFCALC a subroutine called from
a loop.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "packs" / "ibm" / "zos-app-insight" / "skills" / "cobol-perf-review" / "scripts" / "perf.py"
FIXTURES = Path(__file__).parent / "fixtures" / "zos-app-insight" / "perf"


def load():
    spec = importlib.util.spec_from_file_location("zos_perf", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


perf = load()
zscan = perf.zscan


def line_of(program: str, text: str) -> int:
    lines = (FIXTURES / "cobol" / f"{program}.cbl").read_text().splitlines()
    hits = [n for n, line in enumerate(lines, 1) if text in line]
    assert len(hits) == 1, (program, text, hits)
    return hits[0]


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("perfproj")
    shutil.copytree(FIXTURES, root / "src")
    zscan.write_map(zscan.scan(["src/cobol"], ["src/copy"], root=root), root=root)
    return root


@pytest.fixture(scope="module")
def app(project) -> dict:
    return zscan.load_map(root=project)


@pytest.fixture(scope="module")
def low(app, project) -> dict:
    return perf.scan(app, min_confidence="low", root=project)


def found(result: dict, check: str, program: str = "PERFPOS") -> list:
    return [f for f in result["findings"] if f["check"] == check and f["program"] == program]


def at(result: dict, check: str, line: int, program: str = "PERFPOS") -> dict:
    hits = [f for f in found(result, check, program) if f["line"] == line]
    assert len(hits) == 1, (check, line, [f["line"] for f in found(result, check, program)])
    return hits[0]


# --------------------------------------------------------------------------- shape
def test_every_finding_is_a_fact_with_lines_loop_evidence_and_fix(low) -> None:
    assert low["version"] == 1 and low["tool"] == "perf.py 1.0"
    checks = {f["check"] for f in low["findings"]}
    assert checks == set(perf.CHECKS), set(perf.CHECKS) - checks
    for f in low["findings"]:
        for key in ("id", "check", "confidence", "program", "file", "line", "loop", "fact", "evidence", "fix"):
            assert key in f, key
        assert f["confidence"] in ("high", "medium", "low")
        assert f["fix"] == f"references/checks.md#{f['check']}"
        assert f["id"].startswith(f["check"] + ":" + f["program"] + ":")
        assert any(e["role"] == "statement" and e["line"] == f["line"] for e in f["evidence"]), f["id"]
        for e in f["evidence"]:  # quoted exactly as the source has it
            source = (FIXTURES / Path(e["file"]).relative_to("src")).read_text().splitlines()
            assert e["text"] == source[e["line"] - 1].rstrip()
        if f["check"] not in ("serial-search-keyed", "serial-search-large"):
            assert f["loop"]["line"] and f["loop"]["kind"] in ("until", "varying", "times")
    assert len({f["id"] for f in low["findings"]}) == len(low["findings"])

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    assert not [k for k in keys(low) if "score" in k.lower()]  # facts, never a numeric quality score


def test_every_fix_pointer_has_its_section_in_checks_md() -> None:
    text = (SCRIPT.parents[1] / "references" / "checks.md").read_text()
    for check in perf.CHECKS:
        assert f"\n## {check}\n" in text, check
        section = text.split(f"\n## {check}\n", 1)[1].split("\n## ", 1)[0]
        for part in ("**Why it costs time.**", "**Fix.**", "**Known false positives.**", "**Measure.**"):
            assert part in section, (check, part)
        assert section.count("```cobol") >= 1, check


def test_ids_are_stable_between_runs(app, project, low) -> None:
    again = perf.scan(app, min_confidence="low", root=project)
    assert [f["id"] for f in again["findings"]] == [f["id"] for f in low["findings"]]


# --------------------------------------------------------------------------- each check, positive and negative
def test_open_close_in_loop(low) -> None:
    opened = at(low, "io-open-close-in-loop", line_of("PERFPOS", "OPEN EXTEND AUDIT-FILE"))
    assert opened["confidence"] == "high" and opened["detail"]["files"] == ["AUDIT-FILE"]
    assert opened["loop"]["line"] == line_of("PERFPOS", "PERFORM PRICE-MOVE UNTIL")
    assert opened["loop"]["kind"] == "until" and "PRICE-MOVE" in opened["loop"]["text"]
    assert at(low, "io-open-close-in-loop", line_of("PERFPOS", "CLOSE AUDIT-FILE"))["confidence"] == "high"
    guarded = at(low, "io-open-close-in-loop", line_of("PERFPOS", "OPEN EXTEND ERR-FILE"))
    assert guarded["confidence"] == "medium"
    assert guarded["detail"]["guards"][0]["line"] == line_of("PERFPOS", "IF MV-QTY = ZERO")
    assert any(e["role"] == "guard" for e in guarded["evidence"])
    # the OPEN before the loop in PERFPOS and every OPEN and CLOSE of PERFNEG stay quiet
    assert line_of("PERFPOS", "OPEN INPUT MOVE-FILE") not in [f["line"] for f in found(low, "io-open-close-in-loop")]
    assert found(low, "io-open-close-in-loop", "PERFNEG") == []


def test_sql_in_loop(low, app) -> None:
    for text, verb in (("SELECT RATE INTO", "SELECT"), ("INSERT INTO STOCK.MOVES_LOG", "INSERT"),
                       ("UPDATE STOCK.ITEMS SET ON_HAND", "UPDATE"), ("DELETE FROM STOCK.HOLDS", "DELETE")):
        f = at(low, "sql-in-loop", line_of("PERFPOS", text) - 1)
        assert f["confidence"] == "high" and f["detail"]["verb"] == verb, text
        assert any("END-EXEC" in e["text"] for e in f["evidence"])
    nested = at(low, "sql-in-loop", line_of("PERFPOS", "EXEC SQL OPEN SITECUR"))
    assert nested["confidence"] == "medium" and nested["detail"]["cursor"] == "SITECUR"
    lines = [f["line"] for f in found(low, "sql-in-loop")]
    assert line_of("PERFPOS", "EXEC SQL FETCH SITECUR") not in lines
    assert line_of("PERFPOS", "EXEC SQL CLOSE SITECUR") not in lines
    # PERFNEG: FETCH and UPDATE ... WHERE CURRENT OF inside the loop, a singleton SELECT outside it
    neg = zscan.find_program(app, "PERFNEG")
    in_loop = {(q["verb"], bool(q["cursor"])) for q in neg["sql"] if q["in_loop"]}
    assert in_loop == {("FETCH", True), ("UPDATE", True)}
    assert any(q["verb"] == "SELECT" and not q["in_loop"] for q in neg["sql"])
    assert found(low, "sql-in-loop", "PERFNEG") == []


def test_static_and_dynamic_calls_in_loop(low) -> None:
    static = at(low, "static-call-in-loop", line_of("PERFPOS", "CALL 'PERFCALC'"))
    assert static["confidence"] == "medium" and static["detail"]["target"] == "PERFCALC"
    dynamic = at(low, "dynamic-call-in-loop", line_of("PERFPOS", "CALL WS-PRICER"))
    assert dynamic["confidence"] == "high"
    assert dynamic["detail"]["candidates"] == ["PERFRATE"]
    assert dynamic["detail"]["cancel_lines"] == [line_of("PERFPOS", "CANCEL WS-PRICER")]
    assert "CANCEL" in dynamic["fact"]
    assert found(low, "static-call-in-loop", "PERFNEG") == []  # the same CALL, before the loop


def test_called_from_a_loop_is_a_note(low) -> None:
    calc = next(p for p in low["programs"] if p["program"] == "PERFCALC")
    assert calc["findings"] == 0
    assert calc["called_in_loop_by"] == [{"program": "PERFPOS", "file": "src/cobol/PERFPOS.cbl",
                                          "line": line_of("PERFPOS", "CALL 'PERFCALC'"),
                                          "loop": line_of("PERFPOS", "PERFORM PRICE-MOVE UNTIL"), "how": "CALL"}]


def test_serial_search(low, app) -> None:
    keyed = at(low, "serial-search-keyed", line_of("PERFPOS", "SEARCH PRICE-ENTRY"))
    assert keyed["confidence"] == "high"
    assert keyed["detail"]["keys"] == [{"name": "PR-ITEM", "order": "ascending"}]
    assert keyed["detail"]["when"][0]["line"] == line_of("PERFPOS", "WHEN PR-ITEM (PR-IX) = MV-ITEM")
    large = at(low, "serial-search-large", line_of("PERFPOS", "SEARCH SITE-ENTRY"))
    assert large["confidence"] == "medium" and large["detail"]["entries"] == 400
    # PERFNEG: SEARCH ALL on the keyed table, serial SEARCH on a 20-entry table
    neg = zscan.find_program(app, "PERFNEG")
    searches = [s for s in neg["statements"] if s["verb"] == "SEARCH"]
    assert [s["operands"] for s in searches] == [["ALL", "PRICE-ENTRY"], ["SMALL-ENTRY"]]
    assert all(s["in_loop"] for s in searches)
    assert found(low, "serial-search-keyed", "PERFNEG") == found(low, "serial-search-large", "PERFNEG") == []


def test_display_arithmetic(low) -> None:
    count = next(f for f in found(low, "display-arithmetic-in-loop") if f["detail"]["item"] == "WS-MOVE-COUNT")
    assert count["confidence"] == "high" and count["id"] == "display-arithmetic-in-loop:PERFPOS:WS-MOVE-COUNT"
    assert count["line"] == line_of("PERFPOS", "ADD 1 TO WS-MOVE-COUNT") and "COMP-5" in count["suggestion"]
    total = next(f for f in found(low, "display-arithmetic-in-loop") if f["detail"]["item"] == "WS-VALUE-TOTAL")
    assert total["confidence"] == "high" and "COMP-3" in total["suggestion"]
    assert any(e["role"] == "definition" and "WS-VALUE-TOTAL" in e["text"] for e in total["evidence"])
    record = {f["detail"]["item"]: f for f in found(low, "display-arithmetic-in-loop")
              if f["detail"]["section"] == "FILE"}
    assert set(record) == {"MV-QTY", "MV-PRICE"}
    assert {f["confidence"] for f in record.values()} == {"medium"}
    items = {f["detail"]["item"] for f in found(low, "display-arithmetic-in-loop")}
    assert "WS-RATE" not in items and "BIN-AMT" not in items  # COMP-3 operands
    # PERFNEG: group USAGE COMP-3 counters and a COMP-3 record field in the loop, a DISPLAY counter outside it
    assert found(low, "display-arithmetic-in-loop", "PERFNEG") == []
    # PERFPART: TB-AMT and TB-TOTAL inherit COMP-3 from their group in a copybook; PART-CNT is defined
    # twice, and only the qualified use of the DISPLAY one is reported, with the line in its id
    part = found(low, "display-arithmetic-in-loop", "PERFPART")
    assert [(f["id"], f["line"]) for f in part] == [
        (f"display-arithmetic-in-loop:PERFPART:PART-CNT@{line_of('PERFPART', 'PART-CNT            PIC 9(5)')}",
         line_of("PERFPART", "ADD 1 TO PART-CNT OF GRP-A"))]


def test_display_subscripts(low) -> None:
    sub = next(f for f in found(low, "display-subscript-in-loop") if f["detail"]["item"] == "WS-BIN")
    assert sub["confidence"] == "high" and sub["line"] == line_of("PERFPOS", "ADD WS-RATE TO BIN-AMT (WS-BIN)")
    assert sub["loop"] == {"line": line_of("PERFPOS", "PERFORM VARYING WS-BIN"), "kind": "varying",
                           "file": "src/cobol/PERFPOS.cbl", "paragraph": "PRICE-MOVE",
                           "text": "PERFORM VARYING WS-BIN FROM 1 BY 1 UNTIL WS-BIN > 20",
                           "outer": [{"line": line_of("PERFPOS", "PERFORM PRICE-MOVE UNTIL"), "kind": "until"}]}
    assert "VARYING variable" in sub["fact"] and "INDEXED BY" in sub["suggestion"]
    # the VARYING increment is folded into the subscript finding, not reported twice
    assert not [f for f in found(low, "display-arithmetic-in-loop") if f["detail"]["item"] == "WS-BIN"]
    part = found(low, "display-subscript-in-loop", "PERFPART")
    assert [f["detail"]["item"] for f in part] == ["WS-I"]
    # an EVALUATE WHEN inside the loop counts, and the out-of-line PERFORM VARYING is the loop itself
    assert [(u["line"], u["verb"]) for u in part[0]["detail"]["uses"]] == [
        (line_of("PERFPART", "WHEN TB-AMT (WS-I)"), "WHEN"), (line_of("PERFPART", "ADD TB-AMT (WS-I)"), "ADD"),
        (line_of("PERFPART", "PERFORM SUM-ONE"), "PERFORM VARYING")]
    assert part[0]["loop"]["line"] == line_of("PERFPART", "PERFORM SUM-ONE")
    # PERFNEG: a COMP-5 subscript and INDEXED BY indexes; reference modification is not a subscript
    assert found(low, "display-subscript-in-loop", "PERFNEG") == []


def test_initialize_group(low) -> None:
    f = at(low, "initialize-group-in-loop", line_of("PERFPOS", "INITIALIZE WS-SLIP"))
    assert f["confidence"] == "high"
    assert f["detail"] == {"group": "WS-SLIP", "elementary_fields": 17, "has_table": True}
    assert found(low, "initialize-group-in-loop", "PERFNEG") == []  # elementary in the loop, group before it


def test_string_ops_are_low_and_listed_only_on_request(app, project, low) -> None:
    ops = found(low, "string-op-in-loop")
    assert sorted(f["statement"] for f in ops) == ["INSPECT", "STRING", "UNSTRING"]
    assert {f["confidence"] for f in ops} == {"low"}
    assert found(low, "string-op-in-loop", "PERFNEG") == []  # STRING before the loop
    medium = perf.scan(app, root=project)
    assert medium["min_confidence"] == "medium"
    assert not [f for f in medium["findings"] if f["confidence"] == "low"]
    assert medium["hidden"] == {"low": 4}


def test_small_literal_times_loop_makes_a_finding_low(low) -> None:
    f = next(f for f in found(low, "display-arithmetic-in-loop") if f["detail"]["item"] == "WS-PASS")
    assert f["confidence"] == "low" and f["detail"]["confidence_before_loop_count"] == "high"
    assert f["loop"]["kind"] == "times" and f["loop"]["count"] == 3 and "runs 3 times" in f["fact"]


def test_min_confidence_high(app, project, low) -> None:
    high = perf.scan(app, min_confidence="high", root=project)
    assert {f["confidence"] for f in high["findings"]} == {"high"}
    n_medium = sum(1 for f in low["findings"] if f["confidence"] == "medium")
    assert high["hidden"] == {"medium": n_medium, "low": 4}
    assert [f["id"] for f in high["findings"]] == [f["id"] for f in low["findings"] if f["confidence"] == "high"]
    with pytest.raises(perf.PerfError):
        perf.scan(app, min_confidence="none", root=project)


# --------------------------------------------------------------------------- what could not be checked
def test_unknown_items_and_partial_programs_are_reported(low) -> None:
    part = next(p for p in low["programs"] if p["program"] == "PERFPART")
    assert part["partial"] is True
    nc = [n for n in low["not_checked"] if n["program"] == "PERFPART"]
    whole = [n for n in nc if n["check"] == "all"]
    assert len(whole) == 1 and "PERFGONE" in whole[0]["reason"]
    items = {(n["check"], n["item"]): n for n in nc if n["item"]}
    assert set(items) == {("display-arithmetic-in-loop", "GONE-AMT"), ("display-arithmetic-in-loop", "GONE-TOTAL"),
                          ("display-subscript-in-loop", "GONE-TAB")}
    corr = [n for n in nc if n["check"] == "display-arithmetic-in-loop" and not n["item"]]
    assert len(corr) == 1 and "CORRESPONDING" in corr[0]["reason"]
    assert corr[0]["line"] == line_of("PERFPART", "ADD CORRESPONDING")
    gone = items[("display-arithmetic-in-loop", "GONE-AMT")]
    assert gone["line"] == line_of("PERFPART", "ADD GONE-AMT TO GONE-TOTAL") and "PERFGONE" in gone["reason"]
    assert part["not_checked"] == len(nc)
    assert not [n for n in low["not_checked"] if n["program"] in ("PERFPOS", "PERFNEG", "PERFCALC")]


def test_changed_source_and_missing_source_are_notes(tmp_path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "src")
    app_map = zscan.scan(["src/cobol"], ["src/copy"], root=tmp_path)
    path = tmp_path / "src" / "cobol" / "PERFCALC.cbl"
    path.write_text(path.read_text() + "      * changed after the map\n")
    (tmp_path / "src" / "cobol" / "PERFNEG.cbl").unlink()
    result = perf.scan(app_map, root=tmp_path)
    notes = {(n["program"], n["message"].split(":")[0]) for n in result["notes"]}
    assert ("PERFCALC", "the source changed after the map was made; line numbers may be off") in notes
    assert ("PERFNEG", "the source file is not readable here") in notes


def test_duplicate_program_ids_get_distinct_labels(tmp_path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "src")
    shutil.copy(tmp_path / "src" / "cobol" / "PERFPOS.cbl", tmp_path / "src" / "cobol" / "PERFPOS2.cbl")
    app_map = zscan.scan(["src/cobol"], ["src/copy"], root=tmp_path)
    result = perf.scan(app_map, program="perfpos", root=tmp_path)
    assert [(p["program"], p["file"]) for p in result["programs"]] == [
        ("PERFPOS", "src/cobol/PERFPOS.cbl"), ("PERFPOS#2", "src/cobol/PERFPOS2.cbl")]
    first = {f["id"] for f in result["findings"] if f["program"] == "PERFPOS"}
    second = {f["id"] for f in result["findings"] if f["program"] == "PERFPOS#2"}
    assert first and {i.replace(":PERFPOS#2:", ":PERFPOS:") for i in second} == first


LOOPCPY = """IDENTIFICATION DIVISION.
PROGRAM-ID. LOOPCPY.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 WS-I     PIC 9(4) COMP.
01 WS-CNT   PIC 9(5).
01 SQLCODE  PIC S9(9).
PROCEDURE DIVISION.
MAIN-PARA.
    PERFORM WORK-PARA.
    COPY LOOPBODY.
    GOBACK.
WORK-PARA.
    CONTINUE.
"""
LOOPBODY = "".join("*> original test copybook: a loop kept in a copybook\n" for _ in range(9)) + """\
    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 100
       ADD 1 TO WS-CNT
       ADD 1 TO SQLCODE
    END-PERFORM
"""


def test_a_loop_in_a_copybook_is_told_apart_and_sqlca_names_need_sql(tmp_path) -> None:
    (tmp_path / "src" / "cobol").mkdir(parents=True)
    (tmp_path / "src" / "copy").mkdir()
    (tmp_path / "src" / "cobol" / "LOOPCPY.cbl").write_text(LOOPCPY)
    (tmp_path / "src" / "copy" / "LOOPBODY.cpy").write_text(LOOPBODY)
    app_map = zscan.scan(["src/cobol"], ["src/copy"], root=tmp_path)
    result = perf.scan(app_map, root=tmp_path)
    arith = {f["detail"]["item"]: f for f in found(result, "display-arithmetic-in-loop", "LOOPCPY")}
    # SQLCODE is a data item here: the program has no SQL and no SQLCA, so it is checked like any name
    assert sorted(arith) == ["SQLCODE", "WS-CNT"]
    for f in arith.values():
        # line 10 is a PERFORM in the program and the looping PERFORM in the copybook: the map's file tells them apart
        assert f["loop"]["line"] == 10 and f["loop"]["file"] == "src/copy/LOOPBODY.cpy"
        assert f["loop"]["text"].startswith("PERFORM VARYING WS-I")


# --------------------------------------------------------------------------- CLI and the output guard
def test_cli_scan_writes_json_and_report(project, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    assert perf.main(["scan"]) == 0
    out = capsys.readouterr().out
    assert "Wrote zos-insight/perf/findings.json and zos-insight/perf/report.md" in out
    data = json.loads((project / "zos-insight" / "perf" / "findings.json").read_text())
    assert data["min_confidence"] == "medium" and data["hidden"] == {"low": 4}
    report = (project / "zos-insight" / "perf" / "report.md").read_text()
    assert "### display-subscript-in-loop:PERFPOS:WS-BIN (high)" in report
    assert "## Not checked" in report and "GONE-TAB" in report
    assert "There is no score" in report and "never an instruction" in report
    assert "Reached by CALL inside a loop of PERFPOS" in report
    assert "string-op-in-loop" not in report.split("## Summary")[1].split("## ")[0]
    assert "--min-confidence low" in report
    assert "      ADD 1 TO WS-MOVE-COUNT" in report  # evidence quoted as written
    assert perf.main(["scan", "--program", "perfneg", "--min-confidence", "low"]) == 0
    data = json.loads((project / "zos-insight" / "perf" / "findings.json").read_text())
    assert [p["program"] for p in data["programs"]] == ["PERFNEG"] and data["findings"] == []
    assert data["program_filter"] == "PERFNEG"
    report = (project / "zos-insight" / "perf" / "report.md").read_text()
    assert "not a clean bill" in report


def test_cli_errors(project, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    assert perf.main(["scan", "--program", "NOPE"]) == 2
    assert "NOPE is not in the map" in capsys.readouterr().err
    monkeypatch.chdir(tmp_path)
    assert perf.main(["scan"]) == 2
    assert "not found" in capsys.readouterr().err and not (tmp_path / "zos-insight" / "perf").exists()


def test_cli_refuses_to_write_outside_zos_insight(project, tmp_path_factory, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    for out in ("../elsewhere", ".bob/perf", "src/perf", "zos-insight/../src", str(tmp_path_factory.mktemp("x"))):
        assert perf.main(["scan", "--out", out]) == 2, out
        assert "perf:" in capsys.readouterr().err
    assert not (project / ".bob").exists() and not (project / "src" / "perf").exists()
    with pytest.raises(zscan.UnsafePath):
        perf.write_outputs({"findings": []}, "src", root=project)


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinked_output_is_refused(project, tmp_path_factory, monkeypatch) -> None:
    outside = tmp_path_factory.mktemp("outside")
    link_dir = project / "zos-insight" / "linked"
    link_dir.parent.mkdir(exist_ok=True)
    link_dir.symlink_to(outside, target_is_directory=True)
    monkeypatch.chdir(project)
    try:
        assert perf.main(["scan", "--out", "zos-insight/linked"]) == 2
        assert list(outside.iterdir()) == []
        real = project / "zos-insight" / "perf2"
        real.mkdir()
        (real / "findings.json").symlink_to(outside / "stolen.json")
        assert perf.main(["scan", "--out", "zos-insight/perf2"]) == 2
        assert not (outside / "stolen.json").exists()
    finally:
        link_dir.unlink()


# --------------------------------------------------------------------------- operand parsing
def test_references_split_subscripts_refmod_and_functions() -> None:
    refs = perf.references(["TAB", "OF", "GRP", "(", "WS-I", "WS-J", ")", "(", "1", ":", "LEN", ")", "=",
                            "FUNCTION", "MAX", "(", "A", "B", ")", "+", "(", "C", "*", "2", ")", "ZERO"])
    got = [(r["name"], r["quals"], r["role"], r["table"]) for r in refs]
    assert got == [("TAB", ["GRP"], "operand", None), ("WS-I", [], "subscript", "TAB"),
                   ("WS-J", [], "subscript", "TAB"), ("LEN", [], "refmod", "TAB"),
                   ("A", [], "operand", None), ("B", [], "operand", None), ("C", [], "operand", None)]
    assert perf.split_text("BIN-AMT(WS-BIN) = 'A B' AND X > -1.5") == [
        "BIN-AMT", "(", "WS-BIN", ")", "=", "'A B'", "AND", "X", ">", "-", "1.5"]


def test_pic_helpers() -> None:
    assert perf.pic_numeric("S9(7)V99") and perf.pic_numeric("V999") and perf.pic_numeric("9(16)")
    assert not perf.pic_numeric("X(5)") and not perf.pic_numeric("ZZZ,ZZ9") and not perf.pic_numeric(None)
    assert perf.pic_digits("S9(9)V99") == (9, 2) and perf.pic_digits("999") == (3, 0)
