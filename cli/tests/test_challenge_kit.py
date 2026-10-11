"""The challenge-kit pack's blueprint renderer: checks, layout, totals and escaping.

The page is parsed with the standard HTML parser and the diagrams are tested on the
geometry the layout returns, so nothing here depends on how the markup is spelled.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "packs" / "ibm" / "challenge-kit" / "skills" / "solution-blueprint"


def load(name: str):
    sys.path.insert(0, str(SKILL / "scripts"))
    spec = importlib.util.spec_from_file_location(f"challenge_{name}", SKILL / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


blueprint = load("blueprint")
diagrams = blueprint.diagrams


def example(name: str = "blueprint-example") -> dict:
    return json.loads((SKILL / "assets" / f"{name}.json").read_text(encoding="utf-8"))


class Page(HTMLParser):
    """Collects the tags, the visible text and any script source of a rendered page."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.text: list[str] = []
        self.scripts: list[str] = []
        self._in = ""

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        self._in = tag

    def handle_endtag(self, tag):
        self._in = ""

    def handle_data(self, data):
        (self.scripts if self._in == "script" else self.text).append(data)


def parse(html: str) -> Page:
    page = Page()
    page.feed(html)
    return page


# ------------------------------------------------------------------- examples
@pytest.mark.parametrize("name", ["blueprint-example", "ideas-example"])
def test_bundled_examples_pass_the_check(name: str) -> None:
    errors, warnings = blueprint.check(example(name))
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("theme", sorted(blueprint.THEMES))
@pytest.mark.parametrize("mode", ["page", "present"])
def test_example_renders_in_every_theme_and_mode(theme: str, mode: str) -> None:
    html, layout = blueprint.render(example(), blueprint.THEMES[theme], mode)
    page = parse(html)
    sections = [attrs["id"] for tag, attrs in page.tags if tag == "section"]
    assert sections == ["problem", "process", "architecture", "impact", "alternatives", "demo", "adoption", "roadmap", "criteria", "risks"]
    assert layout == []
    assert len(page.scripts) == 1  # the presenter keys; nothing from the spec
    assert not [attrs for tag, attrs in page.tags if tag in ("link", "img", "iframe") or attrs.get("src")]  # self-contained


def test_no_external_address_in_the_page() -> None:
    html, _ = blueprint.render(example(), blueprint.THEMES["carbon"])
    page = parse(html)
    for tag, attrs in page.tags:
        for key, value in attrs.items():
            if key in ("href", "src", "action") and value:
                assert value.startswith("#"), (tag, key, value)


# --------------------------------------------------------------------- layout
def crossings(arch: dict, rtl: bool = False) -> list[str]:
    _, warnings, _ = diagrams.architecture(arch, rtl)
    return [w for w in warnings if "crosses" in w]


def test_example_connectors_miss_every_node() -> None:
    assert crossings(example()["architecture"]) == []
    assert crossings(example()["architecture"], rtl=True) == []


def test_dense_diagram_connectors_miss_every_node() -> None:
    layers = [{"title": f"Layer {r}", "nodes": [{"id": f"n{r}{c}", "title": f"Node {r}{c}"} for c in range(5)]} for r in range(5)]
    edges = []
    for r in range(5):
        for c in range(5):
            for r2, c2 in ((r + 1, (c + 2) % 5), (r + 2, (c + 3) % 5), (r, (c + 2) % 5), (r - 3, c)):
                if 0 <= r2 < 5:
                    edges.append({"from": f"n{r}{c}", "to": f"n{r2}{c2}", "label": "x"})
    arch = {"layers": layers, "edges": edges}
    assert crossings(arch) == []
    assert crossings(arch, rtl=True) == []


def test_single_layer_and_self_edges_do_not_break_the_layout() -> None:
    arch = {"layers": [{"title": "Only", "nodes": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}]}],
            "edges": [{"from": "a", "to": "c"}, {"from": "a", "to": "b"}, {"from": "b", "to": "b"}, {"from": "a", "to": "missing"}]}
    svg, warnings, _ = diagrams.architecture(arch)
    assert svg.startswith("<svg") and not [w for w in warnings if "crosses" in w]


def test_long_text_is_cut_and_reported() -> None:
    arch = {"layers": [{"title": "L", "nodes": [{"id": "a", "title": "A very long node title that cannot fit into two lines of a small box at all, ever"}]}], "edges": []}
    _, warnings, _ = diagrams.architecture(arch)
    assert any("was cut" in w for w in warnings)


# --------------------------------------------------------------------- totals
def test_process_totals_are_computed_from_the_steps() -> None:
    steps = example()["process"]["before"]["steps"]
    stats = diagrams.process_stats(steps)
    assert stats["steps"] == 9 and stats["handoffs"] == 4 and stats["actors"] == 3
    assert stats["minutes"] == sum(s["minutes"] for s in steps)
    assert stats["waiting"] == 2880 + 1200
    assert stats["hands_on"] == 5 + 20 + 25 + 10 + 30 + 10 + 15


def test_waterfall_total_is_the_sum_of_its_items() -> None:
    spec = {"items": [{"label": "a", "value": 10}, {"label": "b", "value": 5.5}, {"label": "c", "value": -3}]}
    svg, _ = diagrams.waterfall(spec)
    assert ">12.5<" in svg


@pytest.mark.parametrize("before, after, shown", [(100, 28, "−72%"), (10, 60, "×6"), (4200, 20, "210× less"), (5, 5, ""), (0, 3, "")])
def test_change_labels(before, after, shown) -> None:
    assert blueprint.shift(before, after) == shown


def test_durations_read_naturally() -> None:
    assert [diagrams.duration(m) for m in (0, 0.5, 5, 45, 120, 2880, 4320)] == ["", "30 s", "5 min", "45 min", "2 h", "2 d", "3 d"]


# ---------------------------------------------------------------------- checks
def test_a_number_without_a_mark_stops_the_render(tmp_path: Path) -> None:
    spec = example()
    del spec["impact"]["metrics"][0]["basis"]
    errors, _ = blueprint.check(spec)
    assert any("basis" in e for e in errors)
    source = tmp_path / "spec.json"
    source.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out.html"
    assert blueprint.main(["render", str(source), "-o", str(out)]) == 1
    assert not out.exists()


def test_check_names_broken_references_and_bad_values() -> None:
    spec = example()
    spec["architecture"]["edges"].append({"from": "clerk", "to": "nowhere"})
    spec["architecture"]["layers"][0]["nodes"].append({"id": "clerk", "title": "Twice"})
    spec["process"]["before"]["steps"][0]["kind"] = "magic"
    spec["alternatives"]["options"][0]["values"] = ["yes"]
    spec["hero"].pop("basis")
    errors, _ = blueprint.check(spec)
    text = "\n".join(errors)
    for needle in ("nowhere", "used twice", "kind must be one of", "one value per criterion", "hero"):
        assert needle in text


def test_check_warns_about_what_the_judges_ask_for() -> None:
    spec = example()
    for layer in spec["architecture"]["layers"]:
        for node in layer["nodes"]:
            node.pop("ibm", None)
    del spec["adoption"]
    spec["alternatives"]["options"] = [o for o in spec["alternatives"]["options"] if not o.get("status_quo")]
    spec["assumptions"] = []
    _, warnings = blueprint.check(spec)
    text = "\n".join(warnings)
    for needle in ("IBM technology", "'adoption' is missing", "doing nothing", "assumptions section is empty"):
        assert needle in text


def test_as_built_asks_for_evidence() -> None:
    spec = example()
    spec["meta"]["status"] = "as-built"
    _, warnings = blueprint.check(spec)
    assert any("evidence" in w and "'inbox'" in w for w in warnings)
    assert not any("'erp'" in w and "evidence" in w for w in warnings)  # mocked, so nothing to prove


def test_a_partial_page_is_not_nagged_about_missing_sections() -> None:
    spec = {"meta": {"title": "Only the process", "partial": True}, "process": copy.deepcopy(example()["process"])}
    errors, warnings = blueprint.check(spec)
    assert errors == [] and warnings == []
    html, _ = blueprint.render(spec, blueprint.THEMES["carbon"])
    assert [attrs["id"] for tag, attrs in parse(html).tags if tag == "section"] == ["process"]


def test_idea_board_needs_scores_and_spread() -> None:
    spec = example("ideas-example")
    spec["ideas"]["items"][0]["scores"]["creativity"] = 9
    for idea in spec["ideas"]["items"]:
        idea["direction"] = "agent"
    errors, warnings = blueprint.check(spec)
    assert any("scores.creativity" in e for e in errors)
    assert any("fewer than three directions" in w for w in warnings)


# -------------------------------------------------------------------- escaping
HOSTILE = '"><script>alert(1)</script><img src=x onerror=alert(2)>'


def poison(value):
    if isinstance(value, dict):
        return {k: (v if k in ("basis", "kind", "status", "better", "direction", "style", "level", "id", "from", "to", "language") else poison(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [poison(v) for v in value]
    if isinstance(value, str):
        return value + HOSTILE
    return value


@pytest.mark.parametrize("name", ["blueprint-example", "ideas-example"])
def test_every_string_of_the_spec_is_escaped(name: str) -> None:
    spec = poison(example(name))
    spec["meta"]["status"] = example(name)["meta"]["status"]
    spec["labels"] = {label: label + HOSTILE for label in blueprint.FIXED}
    html, _ = blueprint.render(spec, blueprint.THEMES["carbon"])
    page = parse(html)
    assert len(page.scripts) == 1 and "alert" not in page.scripts[0]
    assert not [tag for tag, _ in page.tags if tag == "img"]
    assert not [attrs for _, attrs in page.tags if any(key.startswith("on") for key in attrs)]
    assert "alert(1)" in "".join(page.text)  # shown as text, which is the point


def test_a_theme_file_cannot_inject_css(tmp_path: Path) -> None:
    theme = tmp_path / "theme.json"
    theme.write_text(json.dumps({"name": "x", "colors": {"bg": "red;}</style><script>alert(1)</script>", "accent": "#123456", "chart": ["#fff", "url(x)"]},
                                 "fonts": {"css_body": "Arial;} body{display:none", "css_heading": "Georgia, serif"}}), encoding="utf-8")
    loaded = blueprint.load_theme(str(theme))
    assert loaded["colors"]["bg"] == blueprint.THEMES["carbon"]["colors"]["bg"]
    assert loaded["colors"]["accent"] == "#123456"
    assert loaded["colors"]["chart"] == blueprint.THEMES["carbon"]["colors"]["chart"]
    assert loaded["fonts"]["css_body"] == blueprint.THEMES["carbon"]["fonts"]["css_body"]
    assert loaded["fonts"]["css_heading"] == "Georgia, serif"
    html, _ = blueprint.render(example(), loaded)
    assert len(parse(html).scripts) == 1


def test_exported_theme_reads_back(tmp_path: Path) -> None:
    out = tmp_path / "theme.json"
    assert blueprint.main(["theme", "midnight", "-o", str(out)]) == 0
    assert blueprint.load_theme(str(out))["colors"] == blueprint.THEMES["midnight"]["colors"]


# ------------------------------------------------------------------------- cli
def test_init_never_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "challenge" / "blueprint.json"
    assert blueprint.main(["init", str(target)]) == 0
    target.write_text("mine", encoding="utf-8")
    assert blueprint.main(["init", str(target)]) == 1
    assert target.read_text(encoding="utf-8") == "mine"


def test_labels_translate_the_fixed_text() -> None:
    spec = example()
    spec["meta"]["language"] = "de"
    spec["labels"] = {"Before": "Vorher", "steps": "Schritte", "min": "Min.", "Process": "Prozess"}
    html, _ = blueprint.render(spec, blueprint.THEMES["carbon"])
    text = "".join(parse(html).text)
    assert "Vorher" in text and "Schritte" in text and "45 Min." not in text and "5 Min." in text
    _, warnings = blueprint.check({**spec, "labels": {"Nope": "x"}})
    assert any("'Nope' is not a label" in w for w in warnings)
    try:
        blueprint.render(example(), blueprint.THEMES["carbon"])
    finally:
        assert diagrams.LABELS == {}


def test_scripts_have_no_network_or_process_code() -> None:
    import ast
    banned = {"socket", "urllib", "http", "requests", "subprocess", "ftplib", "smtplib", "ssl", "webbrowser"}
    for script in (SKILL / "scripts").glob("*.py"):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        names |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert not names & banned, (script.name, names & banned)


# ================================================================ poc-scope: synth
PACK = REPO / "packs" / "ibm" / "challenge-kit" / "skills"


def load_script(skill: str, name: str):
    path = PACK / skill / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"challenge_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


synth = load_script("poc-scope", "synth")
subcheck = load_script("submission-check", "submission_check")


def schema() -> dict:
    return json.loads((PACK / "poc-scope" / "assets" / "schema-example.json").read_text(encoding="utf-8"))


def test_same_seed_same_rows_and_another_seed_differs() -> None:
    first, key = synth.make(schema())
    again, _ = synth.make(schema())
    other, _ = synth.make({**schema(), "seed": 8})
    assert first == again and first != other
    assert {name: len(rows) for name, rows in first.items()} == {"suppliers": 25, "invoices": 200}


def test_references_resolve_and_addresses_are_reserved() -> None:
    made, _ = synth.make(schema())
    suppliers = {row["supplier_id"] for row in made["suppliers"]}
    assert len(suppliers) == 25
    assert all(row["supplier_id"] in suppliers for row in made["invoices"])
    assert all(row["email"].endswith("@example.com") for row in made["suppliers"])


def test_planted_cases_match_the_answer_key() -> None:
    made, key = synth.make(schema())
    rows = {row["invoice_id"]: row for row in made["invoices"]}
    cases = {case["label"]: case for case in key["invoices"]}
    assert [cases[label]["count"] for label in ("matches the order", "price mismatch", "freight added")] == [166, 20, 14]
    assert sum(len(case["rows"]) for case in cases.values()) == len({i for case in cases.values() for i in case["rows"]}) == 200
    for invoice in cases["price mismatch"]["rows"]:
        row = rows[invoice]
        assert row["status"] == "blocked" and row["invoice_amount"] == round(row["order_amount"] * 1.07, 2)
    for invoice in cases["freight added"]["rows"]:
        assert rows[invoice]["invoice_amount"] == round(rows[invoice]["order_amount"] + 85.0, 2)
    for invoice in cases["matches the order"]["rows"]:
        assert rows[invoice]["invoice_amount"] == rows[invoice]["order_amount"]


def test_schema_errors_are_named() -> None:
    bad = schema()
    bad["tables"]["invoices"]["fields"]["supplier_id"]["table"] = "nowhere"
    bad["tables"]["invoices"]["fields"]["quantity"]["min"] = 99
    bad["tables"]["invoices"]["fields"]["issued"]["from"] = "June"
    bad["tables"]["invoices"]["cases"][0]["count"] = 500
    bad["tables"]["invoices"]["cases"][1]["set"]["ghost"] = 1
    bad["tables"]["suppliers"]["fields"]["country"]["type"] = "postcode"
    text = "\n".join(synth.check(bad))
    for needle in ("nowhere", "min not above max", "YYYY-MM-DD", "more than the 200 rows", "'ghost'", "type must be one of"):
        assert needle in text
    assert synth.check(schema()) == []


def test_generator_replaces_only_its_own_files(tmp_path: Path) -> None:
    source = tmp_path / "schema.json"
    source.write_text(json.dumps(schema()), encoding="utf-8")
    out = tmp_path / "data"
    assert synth.main(["make", str(source), "-o", str(out)]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True and manifest["files"] == ["suppliers.csv", "invoices.csv"]
    with (out / "invoices.csv").open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 200
    assert synth.main(["make", str(source), "-o", str(out)]) == 0  # its own files: replaced

    foreign = tmp_path / "real"
    foreign.mkdir()
    (foreign / "invoices.csv").write_text("the user's own export", encoding="utf-8")
    with pytest.raises(SystemExit):
        synth.main(["make", str(source), "-o", str(foreign)])
    assert (foreign / "invoices.csv").read_text(encoding="utf-8") == "the user's own export"
    assert not (foreign / "suppliers.csv").exists()

    target = tmp_path / "s" / "schema.json"
    assert synth.main(["init", str(target)]) == 0 and synth.main(["init", str(target)]) == 1


def test_generator_has_no_network_or_process_code() -> None:
    import ast
    tree = ast.parse((PACK / "poc-scope" / "scripts" / "synth.py").read_text(encoding="utf-8"))
    names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not names & {"socket", "urllib", "http", "requests", "subprocess", "ssl", "ftplib", "smtplib"}


# ====================================================== submission-check: the script
import csv  # noqa: E402
import hashlib  # noqa: E402
import subprocess  # noqa: E402

# Built at run time, so that no credential-shaped literal sits in this repository.
LIVE = "Zk9" + "qT2xLm7Rv" + "4BnW8sYc1" + "HdP6uJe3G" + "aK5tXo0NiF"
OLD = "Qw7" + "eR4tY1uI8" + "oP5aS2dF9" + "gH6jK3lZ0" + "xC7vB4nM1q"
AWS = "AKIA" + "ABCDEFGH" + "IJKLMNOP"


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True)


def snapshot(repo: Path) -> dict:
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(repo.rglob("*")) if p.is_file()}


@pytest.fixture()
def entry(tmp_path: Path) -> Path:
    """A small entry. What is committed is clean; the credential-shaped lines are staged only,
    so the fixture never asks git to commit one (machines often run a pre-commit secret hook)."""
    repo = tmp_path / "entry"
    (repo / "src").mkdir(parents=True)
    (repo / "challenge").mkdir()
    run_git(repo, "init", "-q")
    (repo / "README.md").write_text("# Entry\n\n" + "How to run it, step by step. " * 30, encoding="utf-8")
    (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repo / "src" / "old.py").write_text('import os\nWO_API_KEY = os.environ["WO_API_KEY"]\n', encoding="utf-8")
    (repo / "challenge" / "blueprint.json").write_text(json.dumps(example()), encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "first")
    (repo / "src" / "app.py").write_text(
        f'api_key = "{LIVE}"\n'                              # a real-looking key
        f"aws = '{AWS}'\n"                                   # a known shape
        'token = cred.get_token("scope").token_value_long\n'  # code, not a value
        'password = "<your-password-goes-here-please>"\n'    # a placeholder
        "api_key_name = DB2_USERNAME_PASSWORD_SECURITY_9\n",  # a constant
        encoding="utf-8")
    run_git(repo, "add", "-A")
    return repo


def with_history(monkeypatch) -> None:
    """The log of a repository in which an earlier commit carried a key that was later removed."""
    real = subcheck.git
    log = ("commit 1a2b3c4 2026-10-01\ndiff --git a/src/old.py b/src/old.py\n--- /dev/null\n+++ b/src/old.py\n@@ -0,0 +1 @@\n"
           f'+WO_API_KEY = "{OLD}"\n'
           "commit 5d6e7f8 2026-10-02\ndiff --git a/src/old.py b/src/old.py\n--- a/src/old.py\n+++ b/src/old.py\n@@ -1 +1,2 @@\n"
           f'-WO_API_KEY = "{OLD}"\n+import os\n+WO_API_KEY = os.environ["WO_API_KEY"]\n'
           "diff --git a/src/app.py b/src/app.py\n--- /dev/null\n+++ b/src/app.py\n@@ -0,0 +1 @@\n"
           f'+api_key = "{LIVE}"\n')
    monkeypatch.setattr(subcheck, "git", lambda repo, *args: log if args[0] == "log" else real(repo, *args))


def by_name(result: dict) -> dict:
    return {check["check"]: check for check in result["checks"]}


def test_finds_credentials_in_files_and_in_history(entry: Path, monkeypatch) -> None:
    with_history(monkeypatch)
    checks = by_name(subcheck.run(entry, None, True))
    files = checks["credentials in tracked files"]
    assert files["status"] == "fail"
    assert {(item["file"], item["line"]) for item in files["items"]} == {("src/app.py", 1), ("src/app.py", 2)}
    history = checks["credentials in the git history"]
    assert history["status"] == "fail"
    # deleted from the file yet still in a commit; the key that is also in a tracked file is reported once, above
    assert [(item["commit"], item["file"]) for item in history["items"]] == [("1a2b3c4 2026-10-01", "src/old.py")]


def test_values_never_reach_the_output(entry: Path, capsys, tmp_path: Path, monkeypatch) -> None:
    with_history(monkeypatch)
    out = tmp_path / "result.json"
    assert subcheck.main([str(entry), "--json", str(out)]) == 1
    printed = capsys.readouterr()
    everything = printed.out + printed.err + out.read_text(encoding="utf-8")
    for secret in (LIVE, OLD, AWS):
        assert secret not in everything
        assert secret[:4] in everything  # masked, so the user can tell which one it is
    assert "Nothing was changed." in printed.out


def test_the_repository_is_untouched(entry: Path) -> None:
    before = snapshot(entry)
    head = subprocess.run(["git", "-C", str(entry), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    subcheck.run(entry, None, True)
    assert snapshot(entry) == before
    assert subprocess.run(["git", "-C", str(entry), "rev-parse", "HEAD"], capture_output=True, text=True).stdout == head


def test_reports_what_an_entry_needs(entry: Path, tmp_path: Path) -> None:
    checks = by_name(subcheck.run(entry, None, False))
    assert checks["credentials in the git history"]["status"] == "skipped"
    assert checks["README"]["status"] == "pass" and checks[".gitignore covers .env"]["status"] == "pass"
    assert checks["Bob session report"]["status"] == "warn"
    blueprint = checks["blueprint"]
    assert blueprint["status"] == "warn" and "status plan" in blueprint["summary"] and "blueprint.html is missing" in blueprint["summary"]
    assert "2 of 13 architecture nodes planned or mocked" in blueprint["summary"]

    report = tmp_path / "session.md"
    report.write_text("exported", encoding="utf-8")
    assert by_name(subcheck.run(entry, str(report), False))["Bob session report"]["status"] == "pass"
    assert by_name(subcheck.run(entry, str(tmp_path / "missing.md"), False))["Bob session report"]["status"] == "fail"


def test_flags_tracked_files_that_should_not_be(entry: Path) -> None:
    (entry / ".env").write_text("X=1\n", encoding="utf-8")
    (entry / ".env.example").write_text("X=\n", encoding="utf-8")
    (entry / "node_modules").mkdir()
    (entry / "node_modules" / "a.js").write_text("1", encoding="utf-8")
    run_git(entry, "add", "-f", "-A")
    unwanted = by_name(subcheck.run(entry, None, False))["files that should not be tracked"]
    assert unwanted["status"] == "fail"
    assert {item["file"] for item in unwanted["items"]} == {".env", "node_modules/a.js"}


def test_a_folder_that_is_not_a_repository_is_said_so(tmp_path: Path) -> None:
    result = subcheck.run(tmp_path, None, True)
    assert result["checks"][0]["status"] == "fail" and len(result["checks"]) == 1


def test_git_is_called_with_read_only_commands() -> None:
    import ast
    tree = ast.parse((PACK / "submission-check" / "scripts" / "submission_check.py").read_text(encoding="utf-8"))
    verbs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "git":
            verbs.add(node.args[1].value)
    assert verbs == {"ls-files", "log", "status"}
    names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not names & {"socket", "urllib", "http", "requests", "ssl", "shutil", "os"}
