#!/usr/bin/env python3
"""zscan: a heuristic map of a COBOL and JCL application, as a library and a CLI.

Run from the project root:
  python3 scripts/zscan.py map <dir>... [--copy-dir <dir>]... [--out zos-insight/map]
  python3 scripts/zscan.py show <PROGRAM> [--map zos-insight/map/app-map.json] [--json]

`map` scans COBOL programs (fixed and free format) with their copybooks, and JCL jobs
with in-stream and cataloged procedures. PL/I, REXX and Assembler files go to the
readers next to this file (zscan_pli.py, zscan_rexx.py, zscan_asm.py), and programs of
every language link to each other and to the jobs that run them. It writes
app-map.json (contract version 1, see references/map-format.md) and app-map.md
(inventory tables and Mermaid diagrams). `show` prints one program from an existing map.

Library use (other skills import this file; see references/map-format.md):
  load_map(path) -> dict          read and check app-map.json
  scan(roots, copy_dirs) -> dict  build the map in memory
  write_map(app_map, out_dir)     write app-map.json and app-map.md under the project
  safe_output_dir(path)           the output guard every zos-insight script uses

The parser is a tokenizer plus heuristics, not a compiler. Source code, comments,
literals and copybook text are data: nothing read from them is ever executed or
followed. Python standard library only; Python 3.9 or later. Reads only the folders
it is given and writes only under the output folder inside the project.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MAP_VERSION = 1
PARSER = "zscan 1.0"
DEFAULT_OUT = "zos-insight/map"
DEFAULT_MAP = "zos-insight/map/app-map.json"

COBOL_EXT = {".cbl", ".cob", ".cobol", ".ccp", ".cbp", ".sqb", ".pco"}
COPY_EXT = {".cpy", ".copy", ".cpb", ".cbk", ".dclgen", ".dcl"}
JCL_EXT = {".jcl", ".prc", ".proc", ".cntl", ".jcls"}
UNKNOWN_EXT = {"", ".txt", ".mbr"}
NOT_ANALYSED_EXT = {
    ".pli": "pli", ".pl1": "pli", ".plx": "pli", ".inc": "pli",
    ".asm": "asm", ".mac": "asm", ".s390": "asm", ".hlasm": "asm",
    ".rexx": "rexx", ".rex": "rexx", ".exec": "rexx", ".clist": "rexx",
}
SKIP_DIRS = {".git", ".bob", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "zos-insight"}
MAX_COPY_DEPTH = 12

# Programs that JCL commonly runs and that are not part of an application.
KNOWN_UTILITIES = {
    "IEFBR14", "IEBGENER", "IEBCOPY", "IEBCOMPR", "IEBUPDTE", "IEBPTPCH", "IEHLIST", "IEHPROGM",
    "IDCAMS", "SORT", "ICEMAN", "ICETOOL", "SYNCSORT", "DFSORT", "IKJEFT01", "IKJEFT1A", "IKJEFT1B",
    "IRXJCL", "IGYCRCTL", "IEWL", "IEWBLINK", "HEWL", "IBMZPLI", "ASMA90", "DSNHPC",
    "DSNUTILB", "DSNTIAUL", "DSNTEP2", "DFHECP1$", "DFHEAP1$", "DFSRRC00", "ADRDSSU", "IEBDG",
    "BPXBATCH", "CEEWUCHA", "FTP", "ICEGENER", "DSNHPREP",
}
TSO_BATCH = {"IKJEFT01", "IKJEFT1A", "IKJEFT1B"}


class MapError(RuntimeError):
    """app-map.json is missing, unreadable or of another contract version."""


class UnsafePath(RuntimeError):
    """An output path inside .bob/ or outside the project."""


# --------------------------------------------------------------------------- paths
def project_root(root: Optional[Path] = None) -> Path:
    return Path(root if root is not None else os.getcwd()).resolve()


OUTPUT_HOME = "zos-insight"


def safe_output_dir(path, root: Optional[Path] = None) -> Path:
    """Resolve an output folder; refuse one inside .bob/, outside the project or outside zos-insight/.

    Every zos-insight script calls this before it writes. Symbolic links are resolved
    first. Returns the absolute path; the folder is not created here.
    """
    base = project_root(root)
    target = Path(path)
    if not target.is_absolute():
        target = base / target
    target = Path(os.path.realpath(target))
    try:
        rel_parts = target.relative_to(base).parts
    except ValueError:
        raise UnsafePath(f"{path}: outside the project {base}; outputs go under {OUTPUT_HOME}/ in the project")
    if any(part.lower() == ".bob" for part in rel_parts):
        raise UnsafePath(f"{path}: inside .bob/, where skills and settings live; outputs go under {OUTPUT_HOME}/")
    home = Path(os.path.realpath(base / OUTPUT_HOME))
    try:
        target.relative_to(home)
    except ValueError:
        raise UnsafePath(f"{path}: outputs go under {OUTPUT_HOME}/ in the project, so no source file is overwritten")
    return target


def rel(path, root: Optional[Path] = None) -> str:
    """Posix path relative to the project root, or absolute when the file is outside it."""
    base = project_root(root)
    p = Path(os.path.realpath(path))
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.as_posix()


def short_paths(text: str, app_map: dict) -> str:
    """Show files outside the project relative to the scanned folder's parent, for reports.

    app-map.json keeps the full path, which the scripts need to read the source; a report
    names the folder that was scanned instead of the whole path on the user's machine.
    """
    folders = [r for r in list(app_map.get("roots") or []) + list(app_map.get("copy_dirs") or []) if os.path.isabs(r)]
    for folder in sorted(set(folders), key=len, reverse=True):
        base = folder.rstrip("/")
        text = text.replace(base + "/", Path(base).name + "/")
    return text


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_text(path: Path) -> str:
    data = Path(path).read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def member_name(path: Path) -> str:
    return Path(path).stem.upper()


_SOURCE_CACHE: Dict[str, Tuple[Tuple[int, int], List[str]]] = {}


def read_source(file: str, root: Optional[Path] = None) -> List[str]:
    """The lines of a file named in the map (relative to the project root, or absolute).

    Read once per process and kept while the file's size and modification time stay the
    same. Raises OSError when the file cannot be read. The list is shared: do not change it.
    """
    p = Path(file)
    if not p.is_absolute():
        p = project_root(root) / p
    key = os.path.realpath(p)
    st = os.stat(key)
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _SOURCE_CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    lines = read_text(Path(key)).splitlines()
    _SOURCE_CACHE[key] = (stamp, lines)
    return lines


def code_slice(file: str, start: int, end: int, root: Optional[Path] = None) -> List[Tuple[int, str]]:
    """Lines start..end (1-based, inclusive) of a file named in the map, as (number, text)."""
    lines = read_source(file, root)
    start = max(1, int(start))
    end = min(len(lines), int(end))
    return [(n, lines[n - 1]) for n in range(start, end + 1)]


# --------------------------------------------------------------------------- discovery
def iter_source_files(folders: Iterable[Path]) -> List[Path]:
    seen = set()
    out: List[Path] = []
    for folder in folders:
        folder = Path(folder)
        if folder.is_file():
            candidates = [folder]
        else:
            candidates = []
            for dirpath, dirnames, filenames in os.walk(folder):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
                for name in sorted(filenames):
                    if not name.startswith("."):
                        candidates.append(Path(dirpath) / name)
        for path in candidates:
            real = os.path.realpath(path)
            if real not in seen and not os.path.islink(path):
                seen.add(real)
                out.append(path)
    return out


# The language readers next to this file (zos-app-insight 1.1). Each has LANGUAGE,
# classify(path, text) -> "program" | "include" | "skip" and scan_program(path, include_dirs, root).
LANG_MODULES = {"pli": "zscan_pli", "rexx": "zscan_rexx", "asm": "zscan_asm"}
LANG_NAMES = {"cobol": "COBOL", "pli": "PL/I", "rexx": "REXX", "asm": "Assembler"}


def language_module(lang: str):
    """The reader module of a language, loaded once from this folder; None when it is not there.

    The modules `import zscan`; this module is registered under that name first, so they use
    the same helpers whichever name it was loaded under.
    """
    name = LANG_MODULES.get(lang)
    if name is None:
        return None
    module = sys.modules.get(name)
    if module is not None:
        return module
    path = Path(__file__).resolve().with_name(name + ".py")
    if not path.is_file():
        return None
    sys.modules.setdefault("zscan", sys.modules[__name__])
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _looks_like_asm(lines: Sequence[str]) -> bool:
    for ln in lines[:300]:
        if ln[:1] in ("*", ".") or not ln.strip():
            continue
        parts = ln.split()
        if len(parts) >= 2 and ln[0] != " " and parts[1].upper() in ("CSECT", "DSECT", "RSECT", "START"):
            return True
        if parts[0].upper() == "MACRO" and ln[0] == " ":
            return True
    return False


def sniff(path: Path) -> str:
    """Classify a file: cobol, copybook, jcl, pli, asm, rexx or other."""
    ext = path.suffix.lower()
    if ext in NOT_ANALYSED_EXT:
        return NOT_ANALYSED_EXT[ext]
    if ext not in COBOL_EXT | COPY_EXT | JCL_EXT | UNKNOWN_EXT:
        return "other"
    try:
        head = read_text(path)[:20000]
    except OSError:
        return "other"
    lines = [ln for ln in head.splitlines() if ln.strip()]
    if ext in JCL_EXT:
        return "jcl"
    if lines and lines[0].startswith("//"):
        return "jcl"
    upper = head.upper()
    if ext in UNKNOWN_EXT:
        if lines and "REXX" in lines[0].upper() and lines[0].lstrip().startswith("/*"):
            return "rexx"
        if "PROC OPTIONS" in upper.replace("  ", " ") or "%INCLUDE" in upper:
            return "pli"
        if "PROGRAM-ID" not in upper and _looks_like_asm(lines):
            return "asm"
    if "PROGRAM-ID" in upper:
        return "cobol"
    if ext in COBOL_EXT and ("PROCEDURE DIVISION" in upper or "IDENTIFICATION DIVISION" in upper):
        return "cobol"
    return "copybook"


# --------------------------------------------------------------------------- COBOL source lines
DIVISION_WORDS = {"IDENTIFICATION", "ID", "ENVIRONMENT", "DATA", "PROCEDURE"}
LISTING_DIRECTIVES = {"EJECT", "SKIP1", "SKIP2", "SKIP3"}


def detect_format(lines: Sequence[str], default: str = "fixed") -> str:
    """fixed or free: a >>SOURCE directive wins; otherwise where headers and levels start."""
    free = fixed = 0
    for raw in lines:
        upper = raw.upper()
        if ">>SOURCE" in upper:
            if "FREE" in upper:
                return "free"
            if "FIXED" in upper:
                return "fixed"
        line = raw.expandtabs(8)
        stripped = line.strip()
        if not stripped:
            continue
        if len(line) > 6 and line[6] in "*/" and line[:6].strip() == "":
            fixed += 1
            continue
        first = stripped.split()[0].upper().rstrip(".")
        start = len(line) - len(line.lstrip()) + 1
        significant = (first in DIVISION_WORDS or first in ("PROGRAM-ID", "COPY", "FD", "*>")
                       or (first.isdigit() and len(first) <= 2 and len(stripped.split()) > 1))
        if first.startswith("*>"):
            significant = True
        if significant:
            if start <= 6:
                free += 1
            else:
                fixed += 1
    if free > fixed:
        return "free"
    if fixed > free:
        return "fixed"
    return default


def _open_quote(text: str) -> Optional[str]:
    """The quote character of a literal left open at the end of text, or None."""
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif c in "'\"":
            quote = c
        elif text.startswith("*>", i):
            return None
        i += 1
    return quote


def _strip_floating_comment(text: str) -> str:
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif text.startswith("*>", i):
            return text[:i]
        i += 1
    return text


class CodeLine:
    __slots__ = ("n", "col0", "text", "breaks")

    def __init__(self, n: int, col0: int, text: str):
        self.n, self.col0, self.text = n, col0, text
        self.breaks: List[Tuple[int, int, int]] = []  # (offset in text, physical line, its column) of continuations

    def pos(self, i: int) -> Tuple[int, int]:
        """(physical line, column) of character i of the merged text."""
        n, col = self.n, self.col0 + i
        for offset, line, column in self.breaks:
            if i >= offset:
                n, col = line, column + (i - offset)
        return n, col


def code_lines(raw_lines: Sequence[str], fmt: str, stats: Optional[dict] = None) -> List[CodeLine]:
    """Comment-free code text per physical line, with continuations merged into the line they continue."""
    out: List[CodeLine] = []
    stats = stats if stats is not None else {}
    stats.setdefault("comment_lines", 0)
    stats.setdefault("debug_lines", 0)
    stats.setdefault("continuations", 0)
    for n, raw in enumerate(raw_lines, start=1):
        line = raw.expandtabs(8).rstrip("\r\n")
        if fmt == "fixed":
            if len(line) < 7:
                continue
            indicator = line[6]
            area = line[7:72]
            if indicator in "*/":
                stats["comment_lines"] += 1
                continue
            if indicator in "Dd":
                stats["debug_lines"] += 1
                continue
            if indicator == "-":
                stats["continuations"] += 1
                if out:
                    prev = out[-1]
                    quote = _open_quote(prev.text)
                    cont = area.lstrip()
                    start_col = 8 + len(area) - len(cont)
                    if quote and cont[:1] in ("'", '"'):
                        prev.text = prev.text.ljust(65)
                        prev.breaks.append((len(prev.text), n, start_col + 1))
                        prev.text += cont[1:]
                    else:
                        prev.text = prev.text.rstrip()
                        prev.breaks.append((len(prev.text), n, start_col))
                        prev.text += cont
                    prev.text = _strip_floating_comment(prev.text)
                continue
            if indicator not in " ":
                # $ and other vendor indicators: not code we can read
                stats["comment_lines"] += 1
                continue
            col0 = 8
        else:
            area = line
            stripped = area.lstrip()
            if stripped.startswith("*>") or stripped.startswith(">>"):
                stats["comment_lines"] += 1
                continue
            if out and stripped.startswith("-") and stripped[1:].lstrip()[:1] in ("'", '"') and _open_quote(out[-1].text):
                stats["continuations"] += 1
                cont = stripped[1:].lstrip()
                out[-1].breaks.append((len(out[-1].text), n, len(line) - len(cont) + 2))
                out[-1].text = out[-1].text + cont[1:]
                continue
            col0 = 1
        text = _strip_floating_comment(area)
        bare = text.strip().rstrip(".").upper()
        if not bare:
            continue
        if bare in LISTING_DIRECTIVES or bare.startswith("TITLE ") or bare.startswith(">>"):
            continue
        first = bare.split()[0]
        if first in ("CBL", "PROCESS") and not out:
            continue
        out.append(CodeLine(n, col0, text))
    return out


# --------------------------------------------------------------------------- tokenizer
WORD_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_#@$")
LITERAL_PREFIX = set("XxNnGgZzBbUu")
PSEUDO_WORD = re.compile(r":[A-Za-z0-9_-]+:[A-Za-z0-9_#@$:-]*")


class Tok:
    __slots__ = ("t", "u", "k", "line", "col", "src", "sub", "end", "o")

    def __init__(self, t: str, k: str, line: int, col: int, src: int, sub: str = "", end: Optional[int] = None):
        self.t = t
        self.u = t.upper()
        self.k = k  # w word, n number, s literal, p punctuation, . period, pic, exec, ==
        self.line = line
        self.col = col
        self.src = src
        self.sub = sub
        self.end = end if end is not None else line  # last line (EXEC blocks span lines)
        self.o: Optional[str] = None  # the text before COPY REPLACING when it differs; "" when unknown

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Tok({self.t!r},{self.k},{self.line})"


def lit_value(text: str) -> str:
    """'ABC' -> ABC; X'C1' -> C1; other text unchanged."""
    t = text
    if len(t) >= 2 and t[0] in LITERAL_PREFIX and t[1] in "'\"":
        t = t[1:]
    if len(t) >= 2 and t[0] in "'\"" and t[-1] == t[0]:
        return t[1:-1].replace(t[0] * 2, t[0])
    if len(t) >= 1 and t[0] in "'\"":
        return t[1:]
    return text


class Tokenizer:
    """Turns code lines into tokens. EXEC ... END-EXEC becomes one raw token."""

    def __init__(self, src: int):
        self.src = src
        self.exec_kind: Optional[str] = None
        self.exec_parts: List[str] = []
        self.exec_line = 0
        self.exec_col = 0
        self.pic = False
        self.exec_pending: Optional[Tuple[int, int]] = None
        self.out: List[Tok] = []

    def emit(self, t: str, k: str, line: int, col: int, sub: str = "") -> None:
        tok = Tok(t, k, line, col, self.src, sub)
        self.out.append(tok)
        if k == "w" and tok.u in ("PIC", "PICTURE"):
            self.pic = True

    def feed(self, lines: Sequence[CodeLine]) -> List[Tok]:
        for cl in lines:
            self._line(cl)
        if self.exec_kind:
            self._close_exec(" ".join(self.exec_parts), lines[-1].n if lines else None)
        return self.out

    def _close_exec(self, raw: str, end_line: Optional[int] = None) -> None:
        text = " ".join(part.strip() for part in self.exec_parts if part.strip()) if self.exec_parts else raw.strip()
        self.out.append(Tok(text, "exec", self.exec_line, self.exec_col, self.src, self.exec_kind or "",
                            end=end_line if end_line is not None else self.exec_line))
        self.exec_kind = None
        self.exec_parts = []

    def _scan_exec(self, s: str, i: int, cl: CodeLine) -> int:
        """Inside EXEC: collect raw text up to END-EXEC; return the index after it, or len(s)."""
        quote = None
        j = i
        while j < len(s):
            c = s[j]
            if quote:
                if c == quote:
                    quote = None
            elif c in "'\"":
                quote = c
            elif (c in "Ee" and s[j:j + 8].upper() == "END-EXEC"
                  and (j == 0 or s[j - 1] not in WORD_CHARS)
                  and (j + 8 >= len(s) or s[j + 8] not in WORD_CHARS)):
                self.exec_parts.append(s[i:j])
                self._close_exec(" ".join(self.exec_parts), cl.pos(j)[0])
                return j + 8
            j += 1
        self.exec_parts.append(s[i:])
        return len(s)

    def _line(self, cl: CodeLine) -> None:
        s = cl.text
        n = cl.n
        i = 0
        if self.exec_pending is not None:  # EXEC ended the previous line; SQL, CICS... starts this one
            m = re.match(r"\s*([A-Za-z]+)", s)
            if m and self.out and self.out[-1].u == "EXEC":
                self.exec_kind = m.group(1).upper()
                self.exec_line, self.exec_col = self.exec_pending
                self.exec_parts = []
                self.out.pop()
                i = m.end()
            self.exec_pending = None
        if self.exec_kind:
            i = self._scan_exec(s, i, cl)
        while i < len(s):
            c = s[i]
            if c in " \t,;":
                i += 1
                continue
            n, col = cl.pos(i)
            if self.pic:
                j = i
                while j < len(s) and s[j] not in " \t":
                    j += 1
                chunk = s[i:j]
                if chunk.upper() == "IS":
                    self.emit(chunk, "w", n, col)
                    i = j
                    continue
                self.pic = False
                tail = ""
                while chunk and chunk[-1] in ".,;" and len(chunk) > 1:
                    tail = chunk[-1] + tail
                    chunk = chunk[:-1]
                self.emit(chunk, "pic", n, col)
                if "." in tail:
                    self.emit(".", ".", n, col + len(chunk))
                i = j
                continue
            if c in "'\"" or (c in LITERAL_PREFIX and i + 1 < len(s) and s[i + 1] in "'\""
                              and (i == 0 or s[i - 1] not in WORD_CHARS)):
                start = i
                if c not in "'\"":
                    i += 1
                quote = s[i]
                j = i + 1
                while j < len(s):
                    if s[j] == quote:
                        if j + 1 < len(s) and s[j + 1] == quote:
                            j += 2
                            continue
                        break
                    j += 1
                self.emit(s[start:j + 1], "s", n, col)
                i = j + 1
                continue
            if s.startswith("==", i):
                self.emit("==", "==", n, col)
                i += 2
                continue
            if c == ":" and PSEUDO_WORD.match(s, i):
                m = PSEUDO_WORD.match(s, i)
                self.emit(m.group(0), "w", n, col)
                i = m.end()
                continue
            if c in WORD_CHARS and c != "-":
                j = i
                while j < len(s) and (s[j] in WORD_CHARS or (s[j] == ":" and PSEUDO_WORD.match(s, j))):
                    if s[j] == ":":
                        j = PSEUDO_WORD.match(s, j).end()
                        continue
                    j += 1
                word = s[i:j]
                if word.isdigit() and j + 1 < len(s) and s[j] == "." and s[j + 1].isdigit():
                    k = j + 1
                    while k < len(s) and s[k].isdigit():
                        k += 1
                    word, j = s[i:k], k
                kind = "n" if word.replace(".", "", 1).isdigit() else "w"
                self.emit(word, kind, n, col)
                i = j
                if kind == "w" and word.upper() == "EXEC":
                    m = re.match(r"\s+([A-Za-z]+)", s[i:])
                    if not m and not s[i:].strip():
                        self.exec_pending = (n, col)
                    if m:
                        self.exec_kind = m.group(1).upper()
                        self.exec_line, self.exec_col = n, col
                        self.exec_parts = []
                        self.out.pop()  # EXEC itself is folded into the raw token
                        i = self._scan_exec(s, i + m.end(), cl)
                continue
            if c in "+-" and i + 1 < len(s) and (s[i + 1].isdigit() or (s[i + 1] == "." and s[i + 2:i + 3].isdigit())):
                prev = self.out[-1] if self.out else None
                if prev is None or prev.k not in ("w", "n", "s") or prev.u in COBOL_KEYWORDS_BEFORE_NUMBER:
                    j = i + 1
                    while j < len(s) and (s[j].isdigit() or (s[j] == "." and j + 1 < len(s) and s[j + 1].isdigit())):
                        j += 1
                    self.emit(s[i:j], "n", n, col)
                    i = j
                    continue
            if c == "." and i + 1 < len(s) and s[i + 1].isdigit() and (i == 0 or s[i - 1] in " \t("):
                j = i + 1
                while j < len(s) and s[j].isdigit():
                    j += 1
                self.emit(s[i:j], "n", n, col)
                i = j
                continue
            if c == ".":
                if i + 1 >= len(s) or s[i + 1] in " \t":
                    self.emit(".", ".", n, col)
                else:
                    self.emit(".", "p", n, col)
                i += 1
                continue
            two = s[i:i + 2]
            if two in ("<=", ">=", "**", "<>"):
                self.emit(two, "p", n, col)
                i += 2
                continue
            self.emit(c, "p", n, col)
            i += 1


COBOL_KEYWORDS_BEFORE_NUMBER = {
    "VALUE", "VALUES", "TO", "BY", "FROM", "GIVING", "ADD", "SUBTRACT", "MOVE", "THRU", "THROUGH",
    "IS", "ARE", "INTO", "UNTIL", "OCCURS", "TIMES", "WHEN", "ALSO", "AND", "OR", "NOT", "=", "<", ">",
}


# --------------------------------------------------------------------------- copybooks
class Source:
    """One physical file that contributed tokens: the program itself or a copybook."""

    __slots__ = ("path", "file", "copybook", "lines", "replacing")

    def __init__(self, path: Path, file: str, copybook: Optional[str], lines: Dict[int, str], replacing: bool = False):
        self.path, self.file, self.copybook, self.lines = path, file, copybook, lines
        self.replacing = replacing  # copied with REPLACING: names may differ from the copybook text


class CopyIndex:
    """Copybook members by name, from --copy-dir folders first, then the scanned roots."""

    def __init__(self, files: Sequence[Tuple[Path, str]]):
        self.by_name: Dict[str, List[Tuple[Path, int]]] = {}
        for order, (path, kind) in enumerate(files):
            if kind in ("copybook", "cobol"):
                self.by_name.setdefault(member_name(path), []).append((path, order))

    def resolve(self, name: str, library: Optional[str], from_file: Path) -> Optional[Path]:
        key = name.upper()
        if "/" in name or "\\" in name or "." in name:
            direct = (from_file.parent / name)
            if direct.is_file():
                return direct
            key = Path(name.replace("\\", "/")).stem.upper()
        found = self.by_name.get(key)
        if not found:
            return None
        here = os.path.realpath(from_file.parent).split(os.sep)

        def score(item: Tuple[Path, int]):
            path, order = item
            parts = os.path.realpath(path.parent).split(os.sep)
            lib = 0 if library and any(p.upper() == library.upper() for p in parts) else 1
            ext = path.suffix.lower()
            ext_rank = 0 if ext in COPY_EXT else (1 if ext in UNKNOWN_EXT else 2)
            common = 0
            for a, b in zip(here, parts):
                if a != b:
                    break
                common += 1
            return (lib, ext_rank, -common, order)

        return sorted(found, key=score)[0][0]


def _segments(text: str) -> List[Tuple[bool, str]]:
    """Split a code line into (is_literal, text) runs."""
    out: List[Tuple[bool, str]] = []
    buf = ""
    quote = None
    for c in text:
        if quote:
            buf += c
            if c == quote:
                out.append((True, buf))
                buf, quote = "", None
        elif c in "'\"":
            if buf:
                out.append((False, buf))
            buf, quote = c, c
        else:
            buf += c
    if buf:
        out.append((quote is not None, buf))
    return out


def _word_pattern(words: List[str]) -> "re.Pattern[str]":
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(r"(?<![A-Za-z0-9_#@$-])" + body + r"(?![A-Za-z0-9_#@$-])", re.I)


def apply_replacing(text: str, pairs: Sequence[Tuple[str, str, str]]) -> str:
    """COPY REPLACING on one code line. pairs: (mode, from, to); mode is text, leading or trailing.

    A from-text with a non-word character at both ends (:TAG:, (PFX)) is replaced inside
    words as well, the way IBM compilers treat tagged copybooks. Literals are left alone
    unless the from-text is itself a literal.
    """
    out = []
    for is_lit, seg in _segments(text):
        for mode, old, new in pairs:
            old_s = old.strip()
            if not old_s:
                continue
            if mode == "text" and old_s[0] in "'\"":
                if is_lit and seg.upper() == old_s.upper():
                    seg = new
                continue
            if is_lit:
                continue
            if mode == "leading":
                seg = re.sub(r"(?<![A-Za-z0-9_#@$-])" + re.escape(old_s), lambda m: new, seg, flags=re.I)
            elif mode == "trailing":
                seg = re.sub(re.escape(old_s) + r"(?![A-Za-z0-9_#@$-])", lambda m: new, seg, flags=re.I)
            elif old_s[0] not in WORD_CHARS and old_s[-1] not in WORD_CHARS and " " not in old_s:
                seg = re.sub(re.escape(old_s), lambda m: new, seg, flags=re.I)
            else:
                seg = _word_pattern(old_s.split()).sub(lambda m: new, seg)
        out.append(seg)
    return "".join(out)


def _pseudo_text(toks: List[Tok], start: int, sources: List[Source]) -> Tuple[str, int]:
    """toks[start] is '=='; return the text up to the closing '==' and the index after it."""
    j = start + 1
    while j < len(toks) and toks[j].k != "==":
        j += 1
    inner = toks[start + 1:j]
    if not inner:
        return "", j + 1
    first, last = inner[0], inner[-1]
    if first.line == last.line and first.src == last.src:
        line = sources[first.src].lines.get(first.line)
        code_start = toks[start].col + 2
        code_end = toks[j].col if j < len(toks) and toks[j].line == first.line else None
        if line is not None and code_end is not None:
            return line[code_start - 1:code_end - 1].strip(), j + 1
    return " ".join(t.t for t in inner), j + 1


def parse_copy_statement(toks: List[Tok], i: int, sources: List[Source]) -> Tuple[dict, int]:
    """toks[i] is COPY. Return ({name, library, pairs}, index after the closing period)."""
    j = i + 1
    name = lit_value(toks[j].t) if j < len(toks) else ""
    j += 1
    library = None
    pairs: List[Tuple[str, str, str]] = []
    if j < len(toks) and toks[j].u in ("OF", "IN") and j + 1 < len(toks):
        library = lit_value(toks[j + 1].t)
        j += 2
    while j < len(toks) and toks[j].k != ".":
        tok = toks[j]
        if tok.u == "REPLACING":
            j += 1
            while j < len(toks) and toks[j].k != ".":
                mode = "text"
                if toks[j].u in ("LEADING", "TRAILING"):
                    mode = toks[j].u.lower()
                    j += 1
                if j >= len(toks) or toks[j].k == ".":
                    break
                if toks[j].k == "==":
                    old, j = _pseudo_text(toks, j, sources)
                else:
                    old, j = toks[j].t, j + 1
                if j < len(toks) and toks[j].u == "BY":
                    j += 1
                if j < len(toks) and toks[j].k == "==":
                    new, j = _pseudo_text(toks, j, sources)
                elif j < len(toks) and toks[j].k != ".":
                    new, j = toks[j].t, j + 1
                else:
                    new = ""
                pairs.append((mode, old, new))
            continue
        j += 1
    return {"name": name.upper() if "." not in name else name, "library": library.upper() if library else None,
            "pairs": pairs}, j + 1


def _mark_originals(before: List[Tok], after: List[Tok]) -> None:
    """Give each token changed by COPY REPLACING its text as written (`o`), line by line.

    On a line whose token count changed the tokens no longer pair up: they get "" (unknown).
    """
    by_line: Dict[int, List[Tok]] = {}
    for t in before:
        by_line.setdefault(t.line, []).append(t)
    after_by_line: Dict[int, List[Tok]] = {}
    for t in after:
        after_by_line.setdefault(t.line, []).append(t)
    for n, new in after_by_line.items():
        old = by_line.get(n, [])
        if len(old) != len(new):
            for b in new:
                b.o = ""
            continue
        for a, b in zip(old, new):
            if a.u != b.u:
                b.o = a.t


class Expander:
    """Tokenizes a program and splices in its copybooks, nested ones included."""

    SQL_SYSTEM_INCLUDES = {"SQLCA", "SQLDA"}

    def __init__(self, copy_index: CopyIndex, root: Path, default_format: str):
        self.copy_index = copy_index
        self.root = root
        self.default_format = default_format
        self.sources: List[Source] = []
        self.copybooks: List[dict] = []
        self.warnings: List[dict] = []
        self.used_files: Dict[str, Path] = {}
        self.stats: dict = {}

    def warn(self, file: Optional[str], line: Optional[int], message: str) -> None:
        self.warnings.append({"file": file, "line": line, "message": message})

    def load(self, path: Path, copybook: Optional[str], fmt: Optional[str],
             pairs: Sequence[Tuple[str, str, str]] = ()) -> Tuple[List[Tok], str]:
        raw = read_text(path).splitlines()
        use_fmt = fmt or detect_format(raw, self.default_format)
        if copybook is not None:
            use_fmt = detect_format(raw, use_fmt)
        lines = code_lines(raw, use_fmt, self.stats)
        before: List[Tok] = []
        if pairs:
            before = Tokenizer(-1).feed([CodeLine(cl.n, cl.col0, cl.text) for cl in lines])
            for cl in lines:
                cl.text = apply_replacing(cl.text, pairs)
        src = len(self.sources)
        self.sources.append(Source(path, rel(path, self.root), copybook,
                                   {n: ln.expandtabs(8) for n, ln in enumerate(raw, start=1)}, bool(pairs)))
        toks = Tokenizer(src).feed(lines)
        if pairs:
            _mark_originals(before, toks)
        return toks, use_fmt

    def expand(self, toks: List[Tok], stack: Tuple[str, ...], from_path: Path, fmt: str) -> List[Tok]:
        out: List[Tok] = []
        i = 0
        while i < len(toks):
            tok = toks[i]
            if tok.k == "w" and tok.u == "COPY" and i + 1 < len(toks) and toks[i + 1].k in ("w", "s", "n"):
                stmt, nxt = parse_copy_statement(toks, i, self.sources)
                self._include(stmt["name"], stmt["library"], stmt["pairs"], tok, stack, from_path, fmt, out)
                i = nxt
                continue
            if tok.k == "w" and tok.u == "REPLACE" and i + 1 < len(toks) and toks[i + 1].k in ("==", "w"):
                src = self.sources[tok.src]
                self.warn(src.file, tok.line, "REPLACE statement not applied; names after it may differ from the compiled program")
                while i < len(toks) and toks[i].k != ".":
                    i += 1
                i += 1
                continue
            out.append(tok)
            if tok.k == "exec" and tok.sub == "SQL":
                words = tok.u.split()
                if len(words) >= 2 and words[0] == "INCLUDE":
                    name = words[1].strip("'\"").rstrip(".")
                    if name not in self.SQL_SYSTEM_INCLUDES:
                        self._include(name, None, (), tok, stack, from_path, fmt, out, sql=True)
            i += 1
        return out

    def _include(self, name: str, library: Optional[str], pairs, tok: Tok, stack: Tuple[str, ...],
                 from_path: Path, fmt: str, out: List[Tok], sql: bool = False) -> None:
        src = self.sources[tok.src]
        path = self.copy_index.resolve(name, library, from_path)
        record = {
            "name": name, "library": library if not sql else "SQL INCLUDE",
            "resolved": rel(path, self.root) if path else None,
            "replacing": bool(pairs), "line": tok.line, "nested_in": src.copybook,
            "replacing_pairs": [[old, new] if mode == "text" else [old, new, mode] for mode, old, new in pairs],
        }
        self.copybooks.append(record)
        if path is None:
            return
        key = member_name(path)
        if key in stack or len(stack) >= MAX_COPY_DEPTH:
            chain = " -> ".join(stack + (key,))
            self.warn(src.file, tok.line, f"copybook {name} not expanded: nesting loop or depth over {MAX_COPY_DEPTH} ({chain})")
            return
        self.used_files[rel(path, self.root)] = path
        inner, inner_fmt = self.load(path, name, fmt, pairs)
        out.extend(self.expand(inner, stack + (key,), path, inner_fmt))


# --------------------------------------------------------------------------- statements and sentences
VERBS = {
    "ACCEPT", "ADD", "ALTER", "CALL", "CANCEL", "CLOSE", "COMPUTE", "CONTINUE", "DELETE", "DISPLAY",
    "DIVIDE", "ENTRY", "EVALUATE", "EXIT", "GENERATE", "GO", "GOBACK", "IF", "INITIALIZE", "INITIATE",
    "INSPECT", "INVOKE", "MERGE", "MOVE", "MULTIPLY", "OPEN", "PERFORM", "READ", "RELEASE", "RETURN",
    "REWRITE", "SEARCH", "SET", "SORT", "START", "STOP", "STRING", "SUBTRACT", "TERMINATE", "UNSTRING",
    "WRITE", "XML", "JSON", "ALLOCATE", "FREE", "RAISE", "RESUME", "USE", "NEXT",
}
SCOPE_ENDS = {"END-IF", "END-EVALUATE", "END-PERFORM", "END-SEARCH"}
# Every scope terminator. A data name may start with END- too (END-OF-FILE), so only these count.
END_WORDS = SCOPE_ENDS | {"END-" + v for v in (
    "READ", "WRITE", "REWRITE", "DELETE", "START", "RETURN", "CALL", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE",
    "COMPUTE", "STRING", "UNSTRING", "ACCEPT", "DISPLAY", "INVOKE", "XML", "JSON", "EXEC", "RECEIVE", "SEND",
    "WAIT", "CHAIN")}
# Conditional phrases, normalised, and the verbs each belongs to.
PHRASE_KINDS = {
    ("NOT", "AT", "END-OF-PAGE"): "NOT END-OF-PAGE", ("NOT", "AT", "EOP"): "NOT END-OF-PAGE",
    ("NOT", "AT", "END"): "NOT AT END", ("NOT", "INVALID", "KEY"): "NOT INVALID KEY",
    ("NOT", "INVALID"): "NOT INVALID KEY", ("NOT", "ON", "SIZE", "ERROR"): "NOT ON SIZE ERROR",
    ("NOT", "SIZE", "ERROR"): "NOT ON SIZE ERROR", ("NOT", "ON", "OVERFLOW"): "NOT ON OVERFLOW",
    ("NOT", "OVERFLOW"): "NOT ON OVERFLOW", ("NOT", "ON", "EXCEPTION"): "NOT ON EXCEPTION",
    ("NOT", "EXCEPTION"): "NOT ON EXCEPTION", ("AT", "END-OF-PAGE"): "END-OF-PAGE", ("AT", "EOP"): "END-OF-PAGE",
    ("END-OF-PAGE",): "END-OF-PAGE", ("EOP",): "END-OF-PAGE", ("AT", "END"): "AT END",
    ("INVALID", "KEY"): "INVALID KEY", ("INVALID",): "INVALID KEY", ("ON", "SIZE", "ERROR"): "ON SIZE ERROR",
    ("SIZE", "ERROR"): "ON SIZE ERROR", ("ON", "OVERFLOW"): "ON OVERFLOW", ("OVERFLOW",): "ON OVERFLOW",
    ("ON", "EXCEPTION"): "ON EXCEPTION", ("EXCEPTION",): "ON EXCEPTION",
}
_FILE_READ = {"READ", "RETURN", "SEARCH"}
_KEYED = {"READ", "WRITE", "REWRITE", "DELETE", "START"}
_ARITH = {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "COMPUTE"}
PHRASE_VERBS = {
    "AT END": _FILE_READ, "NOT AT END": _FILE_READ, "INVALID KEY": _KEYED, "NOT INVALID KEY": _KEYED,
    "ON SIZE ERROR": _ARITH, "NOT ON SIZE ERROR": _ARITH, "ON OVERFLOW": {"STRING", "UNSTRING", "CALL"},
    "NOT ON OVERFLOW": {"STRING", "UNSTRING", "CALL"},
    "ON EXCEPTION": {"CALL", "ACCEPT", "DISPLAY", "INVOKE", "XML", "JSON"},
    "NOT ON EXCEPTION": {"CALL", "ACCEPT", "DISPLAY", "INVOKE", "XML", "JSON"},
    "END-OF-PAGE": {"WRITE"}, "NOT END-OF-PAGE": {"WRITE"},
}
PHRASE_STARTS = {"AT", "NOT", "INVALID", "ON", "OVERFLOW", "EXCEPTION", "SIZE", "EOP", "END-OF-PAGE"}


# --------------------------------------------------------------------------- divisions
def _is_div(toks: List[Tok], i: int, word: str) -> bool:
    return (toks[i].u == word and i + 1 < len(toks) and toks[i + 1].u == "DIVISION")


def split_units(toks: List[Tok]) -> List[List[Tok]]:
    """One token list per program in the file (nested and batched programs split apart)."""
    starts = [i for i in range(len(toks)) if (_is_div(toks, i, "IDENTIFICATION") or _is_div(toks, i, "ID"))]
    if not starts:
        starts = [i for i, t in enumerate(toks) if t.u == "PROGRAM-ID"]
    if not starts:
        return [toks] if toks else []
    units = []
    if starts[0] > 0:
        starts[0] = 0
    for a, b in zip(starts, starts[1:] + [len(toks)]):
        unit = []
        j = a
        while j < b:
            t = toks[j]
            if t.u == "END" and j + 1 < b and toks[j + 1].u == "PROGRAM":
                j += 2
                while j < b and toks[j].k != ".":
                    j += 1
                j += 1
                continue
            unit.append(t)
            j += 1
        units.append(unit)
    return units


def division_ranges(toks: List[Tok]) -> Dict[str, Tuple[int, int]]:
    marks = []
    for i in range(len(toks) - 1):
        for word in ("IDENTIFICATION", "ID", "ENVIRONMENT", "DATA", "PROCEDURE"):
            if _is_div(toks, i, word):
                marks.append(("IDENTIFICATION" if word == "ID" else word, i))
    out: Dict[str, Tuple[int, int]] = {}
    for k, (name, start) in enumerate(marks):
        end = marks[k + 1][1] if k + 1 < len(marks) else len(toks)
        if name not in out:
            out[name] = (start, end)
    return out


def program_id(toks: List[Tok]) -> Optional[Tok]:
    for i, t in enumerate(toks):
        if t.u == "PROGRAM-ID":
            j = i + 1
            while j < len(toks) and toks[j].k in (".", "p"):
                j += 1
            if j < len(toks):
                return toks[j]
    return None


def sentences(toks: List[Tok]) -> List[List[Tok]]:
    out, cur = [], []
    for t in toks:
        cur.append(t)
        if t.k == ".":
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


# --------------------------------------------------------------------------- environment division
ASSIGN_PREFIXES = {"UT", "DA", "S", "D", "R", "I", "V", "AS", "SYS"}


def dd_of_assign(assign: str) -> str:
    """UT-S-CUSTIN -> CUSTIN; 'CUSTFILE' -> CUSTFILE."""
    name = lit_value(assign).strip()
    parts = name.split("-")
    while len(parts) > 1 and parts[0].upper() in ASSIGN_PREFIXES:
        parts = parts[1:]
    return "-".join(parts).upper()


def parse_selects(toks: List[Tok]) -> List[dict]:
    files = []
    for sent in sentences(toks):
        words = [t for t in sent if t.k != "."]
        idx = next((k for k, t in enumerate(words) if t.u == "SELECT"), None)
        if idx is None:
            continue
        w = words[idx + 1:]
        if w and w[0].u == "OPTIONAL":
            w = w[1:]
        if not w:
            continue
        rec = {"name": w[0].u, "assign": None, "organization": "SEQUENTIAL", "access": "SEQUENTIAL",
               "record": None, "io": [], "dd": None, "status": None, "keys": [], "line": w[0].line}
        k = 1
        while k < len(w):
            u = w[k].u
            nxt = lambda m: w[m].u if m < len(w) else ""
            if u == "ASSIGN":
                k += 1
                while k < len(w) and w[k].u in ("TO", "USING", "EXTERNAL", "DYNAMIC"):
                    k += 1
                if k < len(w):
                    rec["assign"] = lit_value(w[k].t) if w[k].k == "s" else w[k].u
                    rec["dd"] = dd_of_assign(w[k].t)
            elif u == "ORGANIZATION":
                k += 1
                while k < len(w) and w[k].u == "IS":
                    k += 1
                if k < len(w):
                    org = w[k].u
                    if org == "LINE" and nxt(k + 1) == "SEQUENTIAL":
                        org, k = "LINE SEQUENTIAL", k + 1
                    rec["organization"] = org
            elif u in ("INDEXED", "RELATIVE") and k > 0 and w[k - 1].u not in ("ACCESS", "IS", "MODE"):
                rec["organization"] = u
            elif u == "ACCESS":
                k += 1
                while k < len(w) and w[k].u in ("MODE", "IS"):
                    k += 1
                if k < len(w):
                    rec["access"] = w[k].u
            elif u == "KEY":
                k += 1
                while k < len(w) and w[k].u == "IS":
                    k += 1
                if k < len(w):
                    rec["keys"].append(w[k].u)
            elif u == "STATUS":
                k += 1
                while k < len(w) and w[k].u == "IS":
                    k += 1
                if k < len(w):
                    rec["status"] = w[k].u
            k += 1
        files.append(rec)
    return files


# --------------------------------------------------------------------------- data division
USAGE_WORDS = {
    "COMP", "COMP-1", "COMP-2", "COMP-3", "COMP-4", "COMP-5", "COMPUTATIONAL", "COMPUTATIONAL-1",
    "COMPUTATIONAL-2", "COMPUTATIONAL-3", "COMPUTATIONAL-4", "COMPUTATIONAL-5", "BINARY", "PACKED-DECIMAL",
    "DISPLAY", "DISPLAY-1", "INDEX", "POINTER", "POINTER-32", "NATIONAL", "FUNCTION-POINTER",
    "PROCEDURE-POINTER", "OBJECT", "FLOAT-SHORT", "FLOAT-LONG", "UTF-8",
}
CLAUSE_WORDS = USAGE_WORDS | {
    "REDEFINES", "PIC", "PICTURE", "USAGE", "OCCURS", "VALUE", "VALUES", "SIGN", "JUSTIFIED", "JUST",
    "SYNCHRONIZED", "SYNC", "BLANK", "GLOBAL", "EXTERNAL", "INDEXED", "ASCENDING", "DESCENDING",
    "DEPENDING", "RENAMES", "BASED", "GROUP-USAGE", "LEADING", "TRAILING", "DYNAMIC", "VOLATILE",
}
SECTION_NAMES = {"FILE", "WORKING-STORAGE", "LOCAL-STORAGE", "LINKAGE", "REPORT", "SCREEN", "COMMUNICATION"}


def _level(tok: Tok) -> Optional[int]:
    if tok.k != "n" or not tok.t.isdigit() or len(tok.t) > 2:
        return None
    value = int(tok.t)
    return value if (1 <= value <= 49 or value in (66, 77, 88)) else None


def parse_data_entry(words: List[Tok]) -> dict:
    level = _level(words[0])
    k = 1
    name = "FILLER"
    name_tok: Optional[Tok] = None
    if k < len(words) and words[k].k == "w" and words[k].u not in CLAUSE_WORDS:
        name = words[k].u
        name_tok = words[k]
        k += 1
    item: Dict[str, Any] = {"level": level, "name": name, "pic": None, "usage": None, "occurs": None,
                            "redefines": None, "value": None, "_name_tok": name_tok}
    while k < len(words):
        t = words[k]
        u = t.u
        if t.k == "pic":
            item["pic"] = t.t.upper()
        elif u == "REDEFINES" and k + 1 < len(words):
            item["redefines"] = words[k + 1].u
            k += 1
        elif u == "RENAMES" and k + 1 < len(words):
            item["redefines"] = None
            item["renames"] = " ".join(x.u for x in words[k + 1:])
            break
        elif u == "USAGE":
            k += 1
            while k < len(words) and words[k].u == "IS":
                k += 1
            if k < len(words):
                item["usage"] = words[k].u
        elif u in USAGE_WORDS:
            item["usage"] = u
        elif u == "OCCURS":
            occ = {"min": None, "max": None, "depending_on": None, "keys": [], "indexed_by": []}
            k += 1
            nums = []
            while k < len(words) and (words[k].k == "n" or words[k].u in ("TO", "UNBOUNDED")):
                if words[k].k == "n":
                    nums.append(int(float(words[k].t)))
                elif words[k].u == "UNBOUNDED":
                    nums.append(None)
                k += 1
            if nums:
                occ["min"], occ["max"] = nums[0], nums[-1]
            while k < len(words) and words[k].k != ".":
                w = words[k].u
                if w in ("TIMES",):
                    k += 1
                elif w == "DEPENDING":
                    k += 1
                    while k < len(words) and words[k].u == "ON":
                        k += 1
                    if k < len(words):
                        occ["depending_on"] = words[k].u
                    k += 1
                elif w in ("ASCENDING", "DESCENDING"):
                    order = w.lower()
                    k += 1
                    while k < len(words) and words[k].u in ("KEY", "IS"):
                        k += 1
                    while k < len(words) and words[k].k == "w" and words[k].u not in CLAUSE_WORDS:
                        occ["keys"].append({"name": words[k].u, "order": order})
                        k += 1
                elif w == "INDEXED":
                    k += 1
                    while k < len(words) and words[k].u == "BY":
                        k += 1
                    while k < len(words) and words[k].k == "w" and words[k].u not in CLAUSE_WORDS:
                        occ["indexed_by"].append(words[k].u)
                        k += 1
                else:
                    break
            item["occurs"] = occ
            continue
        elif u in ("VALUE", "VALUES"):
            k += 1
            while k < len(words) and words[k].u in ("IS", "ARE"):
                k += 1
            vals = []
            while k < len(words) and not (words[k].k == "w" and words[k].u in CLAUSE_WORDS - {"DISPLAY"}):
                vals.append(words[k].t)
                k += 1
            item["value"] = " ".join(vals) if vals else None
            continue
        k += 1
    return item


def parse_data_division(toks: List[Tok], sources: List[Source], files: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Data items and FD records. Returns (data_items, warnings)."""
    items: List[dict] = []
    warnings: List[dict] = []
    section = None
    fd = None
    stack: List[Tuple[int, str, int]] = []
    last_item: Optional[str] = None
    last_index: Optional[int] = None
    by_name = {f["name"]: f for f in files}
    for sent in sentences(toks):
        words = [t for t in sent if t.k not in (".", "exec")]
        if not words:
            continue
        first = words[0]
        if len(words) >= 2 and words[1].u == "SECTION" and first.u in SECTION_NAMES:
            section, fd, stack = first.u, None, []
            continue
        if first.u in ("FD", "SD", "RD", "CD") and len(words) > 1:
            fd = words[1].u
            stack = []
            if fd not in by_name:
                by_name[fd] = {"name": fd, "assign": None, "organization": None, "access": None, "record": None,
                               "io": [], "dd": None, "status": None, "keys": [], "line": words[1].line}
                files.append(by_name[fd])
                if first.u == "FD":
                    src = sources[words[1].src]
                    warnings.append({"file": src.file, "line": words[1].line,
                                     "message": f"FD {fd} has no SELECT in FILE-CONTROL"})
            by_name[fd]["kind"] = first.u
            continue
        level = _level(first)
        if level is None:
            continue
        item = parse_data_entry(words)
        name_tok = item.pop("_name_tok")
        if level in (1, 77):
            stack = []
            parent, parent_index = None, None
        elif level == 88:
            parent, parent_index = last_item, last_index
        elif level == 66:
            parent, parent_index = (stack[0][1], stack[0][2]) if stack else (None, None)
        else:
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent, parent_index = (stack[-1][1], stack[-1][2]) if stack else (None, None)
        index = len(items)
        if level not in (66, 88):
            stack.append((level, item["name"], index))
            last_item, last_index = item["name"], index
        src = sources[first.src]
        item.update({"section": section, "parent": parent, "parent_index": parent_index, "copybook": src.copybook,
                     "file": src.file, "line": first.line, "fd": fd if section == "FILE" else None})
        if src.replacing and not (name_tok is not None and name_tok.o == ""):
            written = name_tok.o if name_tok is not None and name_tok.o else None
            item["name_in_copybook"] = written.upper() if written else item["name"]
        if section == "FILE" and fd and level == 1 and fd in by_name:
            rec = by_name[fd]
            rec.setdefault("records", [])
            rec["records"].append(item["name"])
            if rec.get("record") is None:
                rec["record"] = item["name"]
        items.append(item)
    return items, warnings


# --------------------------------------------------------------------------- EXEC SQL and EXEC CICS
SQL_TOKEN = re.compile(
    r"'(?:[^']|'')*'?|\"(?:[^\"]|\"\")*\"?"
    r"|:\s*[A-Za-z0-9_#@$][A-Za-z0-9_#@$-]*(?:\.[A-Za-z0-9_#@$-]+)*"
    r"|[A-Za-z0-9_#@$][A-Za-z0-9_#@$-]*(?:\.[A-Za-z0-9_#@$][A-Za-z0-9_#@$-]*)*"
    r"|\S")
SQL_TABLE_END = {
    "WHERE", "GROUP", "ORDER", "HAVING", "FETCH", "FOR", "UNION", "EXCEPT", "INTERSECT", "WITH", "OPTIMIZE",
    "QUERYNO", "SKIP", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "ON", "SET", "VALUES", "SELECT",
    "USING", "WHEN", "INTO", "OFFSET", "LIMIT", "AS", "FROM", "OUTER", "ISOLATION",
}
FETCH_SKIP = {"NEXT", "PRIOR", "FIRST", "LAST", "CURRENT", "BEFORE", "AFTER", "ABSOLUTE", "RELATIVE",
              "ROWSET", "STARTING", "AT", "FROM", "SENSITIVE", "INSENSITIVE", "WITH", "CONTINUE", "ROW", "ROWS"}


def parse_sql(raw: str) -> dict:
    """verb, tables, cursor, host variables, multi-row form and INCLUDE member of one EXEC SQL block."""
    toks = [m.group(0) for m in SQL_TOKEN.finditer(raw)]
    upper = [t.upper() for t in toks]
    words = [u for u in upper if u[:1].isalnum() or u[:1] in "_#@$"]
    verb = words[0] if words else ""
    cursor = None
    tables: List[str] = []
    host_vars: List[str] = []
    for t in toks:
        if t.startswith(":"):
            name = t[1:].strip().upper()
            if name and name not in host_vars:
                host_vars.append(name)
    if verb == "DECLARE" and len(words) > 2:
        if "CURSOR" in words[:6]:
            verb, cursor = "DECLARE CURSOR", words[1]
        elif words[1] == "TABLE" or words[2] == "TABLE":
            verb = "DECLARE TABLE"
            tables.append(words[2] if words[1] == "TABLE" else words[1])
        elif "STATEMENT" in words[:6]:
            verb = "DECLARE STATEMENT"
    elif verb in ("OPEN", "CLOSE") and len(words) > 1:
        cursor = words[1]
    elif verb == "FETCH":
        for w in words[1:]:
            if w in FETCH_SKIP or w[0].isdigit():
                continue
            cursor = w
            break
    if "CURRENT" in upper:
        k = upper.index("CURRENT")
        if k + 2 < len(upper) and upper[k + 1] == "OF":
            cursor = upper[k + 2]
    multi_row = "ROWSET" in upper or any(u == "FOR" and k + 2 < len(upper) and upper[k + 2] in ("ROW", "ROWS")
                                         for k, u in enumerate(upper))
    include = words[1].strip("'\"") if verb == "INCLUDE" and len(words) > 1 else None

    def take_tables(k: int) -> None:
        expect = True
        while k < len(upper):
            u = upper[k]
            if u == "(":
                depth = 1
                k += 1
                while k < len(upper) and depth:
                    depth += {"(": 1, ")": -1}.get(upper[k], 0)
                    k += 1
                expect = False
                continue
            if u in (")", ";") or u in SQL_TABLE_END and u != "AS":
                return
            if u == ",":
                expect = True
            elif expect and not u.startswith(":") and (u[:1].isalpha() or u[:1] in "_#@$"):
                if u not in tables:
                    tables.append(u)
                expect = False
            k += 1

    for k, u in enumerate(upper):
        nxt = upper[k + 1] if k + 1 < len(upper) else ""
        if u in ("FROM", "JOIN") and verb not in ("FETCH", "DECLARE TABLE"):
            take_tables(k + 1)
        elif u == "INTO" and verb in ("INSERT", "MERGE") and not nxt.startswith(":"):
            take_tables(k + 1)
        elif u == "UPDATE" and k == upper.index("UPDATE") and verb == "UPDATE":
            take_tables(k + 1)
        elif u == "TABLE" and verb in ("LOCK",):
            take_tables(k + 1)
    return {"verb": verb, "tables": tables, "cursor": cursor, "host_vars": host_vars, "multi_row": multi_row,
            "include": include}


CICS_TWO_WORD = {
    "SEND": {"MAP", "TEXT", "CONTROL", "PAGE", "PARTNSET"},
    "RECEIVE": {"MAP", "PARTN"},
    "READQ": {"TS", "TD"}, "WRITEQ": {"TS", "TD"}, "DELETEQ": {"TS", "TD"},
    "HANDLE": {"CONDITION", "AID", "ABEND"}, "IGNORE": {"CONDITION"}, "PUSH": {"HANDLE"}, "POP": {"HANDLE"},
}


def parse_cics(raw: str) -> dict:
    """command and options of one EXEC CICS block; option values as written."""
    toks = [m.group(0) for m in SQL_TOKEN.finditer(raw)]
    options: Dict[str, Any] = {}
    command = ""
    k = 0
    words_seen = 0
    while k < len(toks):
        t = toks[k]
        u = t.upper()
        if t == "(" or t == ")" or not (u[:1].isalnum() or u[:1] in "_#@$"):
            k += 1
            continue
        has_value = k + 1 < len(toks) and toks[k + 1] == "("
        if has_value:
            depth, j, parts = 1, k + 2, []
            while j < len(toks) and depth:
                if toks[j] == "(":
                    depth += 1
                elif toks[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                parts.append(toks[j])
                j += 1
            value = " ".join(parts)
            if words_seen == 0:
                command = u
            elif words_seen == 1 and u in CICS_TWO_WORD.get(command, ()):
                command = f"{command} {u}"
            options[u.lower()] = value
            words_seen += 1
            k = j + 1
            continue
        if words_seen == 0:
            command = u
        elif words_seen == 1 and u in CICS_TWO_WORD.get(command, ()):
            command = f"{command} {u}"
        else:
            options[u.lower()] = True
        words_seen += 1
        k += 1
    return {"command": command, "options": options}


def join_tokens(toks: Sequence[Tok]) -> str:
    """Tokens back to text, with a single space where the source had any."""
    out = ""
    prev = None
    for t in toks:
        if prev is not None:
            adjacent = (t.src == prev.src and t.line == prev.line and t.col == prev.col + len(prev.t))
            if not adjacent:
                out += " "
        out += t.t
        prev = t
    return out


# --------------------------------------------------------------------------- procedure division
class Block:
    __slots__ = ("name", "kind", "section", "start", "end", "start_line", "end_line", "src")

    def __init__(self, name, kind, section, start, start_line, src):
        self.name, self.kind, self.section = name, kind, section
        self.start, self.end = start, start
        self.start_line, self.end_line, self.src = start_line, start_line, src


class ProcParser:
    """Statements, paragraphs, PERFORM ranges and conditions of one PROCEDURE DIVISION."""

    def __init__(self, toks: List[Tok], sources: List[Source], data_names: set, file_records: Dict[str, str]):
        self.toks = toks
        self.sources = sources
        self.data_names = data_names
        self.file_records = file_records  # record or file name -> file name
        self.blocks: List[Block] = []
        self.statements: List[dict] = []
        self.performs: List[dict] = []
        self.calls: List[dict] = []
        self.gotos: List[dict] = []
        self.sql: List[dict] = []
        self.cics: List[dict] = []
        self.conditions: List[dict] = []
        self.warnings: List[dict] = []
        self.using: List[str] = []
        self.block_at: Dict[int, Block] = {}
        self.block_no: Dict[int, int] = {}
        self._names: Dict[str, List[int]] = {}

    # ---- helpers
    def where(self, tok: Tok) -> dict:
        src = self.sources[tok.src]
        return {"copybook": src.copybook} if src.copybook else {}

    def warn(self, tok: Optional[Tok], message: str) -> None:
        if tok is None:
            self.warnings.append({"file": self.sources[0].file, "line": None, "message": message})
        else:
            self.warnings.append({"file": self.sources[tok.src].file, "line": tok.line, "message": message})

    def is_verb(self, i: int) -> bool:
        t = self.toks[i]
        if t.k != "w" or t.u not in VERBS:
            return False
        nxt = self.toks[i + 1].u if i + 1 < len(self.toks) else ""
        if t.u == "NEXT":
            return nxt == "SENTENCE"
        if t.u == "ENTRY":
            return self.toks[i + 1].k == "s" if i + 1 < len(self.toks) else False
        if t.u == "USE":
            return nxt in ("AFTER", "FOR", "BEFORE", "GLOBAL")
        if t.u in ("XML", "JSON"):
            return nxt in ("GENERATE", "PARSE")
        if t.u == "SET" and i > 0 and self.toks[i - 1].u in ("ROWSET",):
            return False
        return True

    def data_items_in(self, toks: Sequence[Tok]) -> List[str]:
        seen: List[str] = []
        for t in toks:
            if t.k == "w" and t.u in self.data_names and t.u not in seen:
                seen.append(t.u)
        return seen

    # ---- pass 1: headers
    def find_blocks(self, start: int) -> None:
        toks = self.toks
        i = start
        section = None
        at_start = True
        current: Optional[Block] = None
        while i < len(toks):
            t = toks[i]
            if at_start and t.u == "DECLARATIVES" and i + 1 < len(toks) and toks[i + 1].k == ".":
                i += 2
                continue
            if at_start and t.u == "END" and i + 2 < len(toks) and toks[i + 1].u == "DECLARATIVES":
                i += 3
                continue
            header = None
            if at_start and t.k in ("w", "n") and t.u not in VERBS and t.u not in END_WORDS:
                if i + 1 < len(toks) and toks[i + 1].k == ".":
                    header = ("paragraph", i + 2)
                elif (i + 2 < len(toks) and toks[i + 1].u == "SECTION"
                      and (toks[i + 2].k == "." or (toks[i + 2].k == "n" and i + 3 < len(toks) and toks[i + 3].k == "."))):
                    header = ("section", i + (3 if toks[i + 2].k == "." else 4))
            if header:
                kind, nxt = header
                if kind == "section":
                    section = t.u
                block = Block(t.u, kind, section if kind == "paragraph" else t.u, nxt, t.line, t.src)
                if current is not None:
                    current.end = i
                self.blocks.append(block)
                current = block
                i = nxt
                at_start = True
                continue
            if current is None:
                current = Block(None, "entry", None, i, t.line, t.src)
                self.blocks.append(current)
            at_start = t.k == "."
            i += 1
        if current is not None:
            current.end = len(toks)
        self.block_no = {id(b): k for k, b in enumerate(self.blocks)}
        for b in self.blocks:
            lines = [toks[k].line for k in range(b.start, b.end) if toks[k].src == b.src]
            b.end_line = max(lines) if lines else b.start_line
            for k in range(b.start, b.end):
                self.block_at[k] = b

    def names(self) -> Dict[str, List[int]]:
        out: Dict[str, List[int]] = {}
        for k, b in enumerate(self.blocks):
            if b.name:
                out.setdefault(b.name, []).append(k)
        return out

    def find_block(self, name: str, qualifier: Optional[str], section: Optional[str]) -> Optional[int]:
        cands = self._names.get(name, [])
        if not cands:
            return None
        if qualifier:
            for k in cands:
                if self.blocks[k].section == qualifier:
                    return k
        for k in cands:
            if self.blocks[k].section == section:
                return k
        return cands[0]

    def block_range(self, target: str, qualifier: Optional[str], thru: Optional[str], section: Optional[str]) -> List[int]:
        a = self.find_block(target, qualifier, section)
        if a is None:
            return []
        if thru:
            b = self.find_block(thru, None, self.blocks[a].section)
            if b is None or b < a:
                b = a
        else:
            b = a
        last = self.blocks[b]
        if last.kind == "section":
            while b + 1 < len(self.blocks) and self.blocks[b + 1].kind == "paragraph" and self.blocks[b + 1].section == last.name:
                b += 1
        return list(range(a, b + 1))

    # ---- pass 2: statements
    PHRASES = [  # longest first
        ("NOT", "AT", "END-OF-PAGE"), ("NOT", "AT", "EOP"), ("NOT", "AT", "END"), ("NOT", "INVALID", "KEY"),
        ("NOT", "ON", "SIZE", "ERROR"), ("NOT", "SIZE", "ERROR"), ("NOT", "ON", "OVERFLOW"), ("NOT", "ON", "EXCEPTION"),
        ("NOT", "OVERFLOW"), ("NOT", "EXCEPTION"), ("NOT", "INVALID"),
        ("AT", "END-OF-PAGE"), ("AT", "EOP"), ("AT", "END"), ("INVALID", "KEY"), ("INVALID",),
        ("ON", "SIZE", "ERROR"), ("SIZE", "ERROR"), ("ON", "OVERFLOW"), ("ON", "EXCEPTION"),
        ("OVERFLOW",), ("EXCEPTION",), ("END-OF-PAGE",), ("EOP",),
    ]

    def phrase_match(self, i: int) -> Optional[Tuple[int, str]]:
        """(index after the phrase, normalised kind) when a conditional phrase starts at i."""
        for phrase in self.PHRASES:
            if all(i + k < len(self.toks) and self.toks[i + k].u == w for k, w in enumerate(phrase)):
                return i + len(phrase), PHRASE_KINDS[phrase]
        return None

    def phrase_end(self, i: int) -> Optional[int]:
        m = self.phrase_match(i)
        return m[0] if m else None

    @staticmethod
    def phrase_owner(cur: Optional[dict], stack: List[dict], kind: str) -> Optional[dict]:
        """The statement a phrase belongs to: the current one when the phrase fits its verb,
        else the innermost open statement it fits, else the current one."""
        fits = PHRASE_VERBS.get(kind, set())
        if cur is not None and cur["verb"] in fits:
            return cur
        for e in reversed(stack):
            if e["type"] in ("STMT", "SEARCH") and e["rec"]["verb"] in fits:
                return e["rec"]
        return cur

    def span_end(self, rec: dict, a: int, b: int) -> None:
        """Extend rec's end_line over tokens a..b-1 that sit in the same file as its first line."""
        src = rec.get("_src")
        for k in range(min(b, len(self.toks)) - 1, a - 1, -1):
            if self.toks[k].src == src:
                rec["end_line"] = max(rec.get("end_line") or 0, self.toks[k].end)
                return

    def stmt_end(self, j: int, stops: Iterable[str] = ()) -> int:
        """First index at or after j where the current statement's own tokens stop."""
        stops = set(stops)
        while j < len(self.toks):
            t = self.toks[j]
            if t.k in (".", "exec") or self.is_verb(j) or t.u in ("ELSE", "WHEN", "THEN") or t.u in stops:
                return j
            if t.k == "w" and t.u in END_WORDS:
                return j
            if t.u in PHRASE_STARTS and self.phrase_end(j) is not None:
                return j
            j += 1
        return j

    def cond_end(self, j: int) -> int:
        while j < len(self.toks):
            t = self.toks[j]
            if t.k in (".", "exec") or self.is_verb(j) or t.u in ("THEN", "ELSE", "WHEN") or t.u in SCOPE_ENDS:
                return j
            j += 1
        return j

    def cond_record(self, kind: str, toks: Sequence[Tok], start: Tok, block: Optional[Block],
                    owner: Optional[dict] = None) -> dict:
        rec = {"kind": kind, "text": join_tokens(toks), "tokens": [x.t for x in toks], "start_line": start.line,
               "end_line": toks[-1].line if toks else start.line,
               "paragraph": block.name if block else None, "data_items": self.data_items_in(toks)}
        if kind == "IF":
            rec["else_line"] = None
        rec.update(self.where(start))
        rec["_owner"] = owner
        self.conditions.append(rec)
        return rec

    def prev_line(self, i: int) -> int:
        return self.toks[i - 1].line if i > 0 else self.toks[i].line

    def close(self, entry: dict, i: int, by_period: bool = False) -> None:
        """Close a scope at token i: the closing word (END-x, a period), or the last token inside it."""
        i = max(0, min(i, len(self.toks) - 1))
        end_line = self.toks[i].line
        if entry.get("cond") is not None:
            entry["cond"]["end_line"] = end_line
        if entry.get("when") is not None:
            entry["when"]["end_line"] = self.prev_line(i) if self.toks[i].k == "." or self.toks[i].u in END_WORDS else end_line
        rec = entry.get("rec")
        if rec is not None and self.toks[i].src == rec.get("_src"):
            rec["end_line"] = max(rec.get("end_line") or 0, end_line)
        if entry.get("pr") is not None and self.toks[i].src == entry["pr"].get("_src"):
            entry["pr"]["end_line"] = max(entry["pr"].get("end_line") or 0, end_line)
        if entry["type"] == "PERFORM" and by_period:
            self.warn(self.toks[i], f"period ends the inline PERFORM of line {entry['line']} before END-PERFORM")

    def parse(self, start: int) -> None:
        self._names = self.names()
        toks = self.toks
        stack: List[dict] = []
        cur: Optional[dict] = None
        block: Optional[Block] = None
        i = start
        while i < len(toks):
            t = toks[i]
            b = self.block_at.get(i)
            if b is None:
                i += 1
                continue
            if b is not block:
                if stack:
                    self.warn(t, f"paragraph {b.name} starts while {stack[-1]['type']} of an earlier paragraph is open")
                    while stack:
                        self.close(stack.pop(), i - 1 if i > 0 else i)
                block, cur = b, None
            loop = self.inline_loop(stack)
            if t.k == ".":
                while stack:
                    self.close(stack.pop(), i, by_period=True)
                cur = None
                i += 1
                continue
            if t.k == "exec":
                self.exec_record(t, block, loop)
                cur = None
                i += 1
                continue
            u = t.u
            if u == "ELSE":
                while stack and not (stack[-1]["type"] == "IF" and not stack[-1]["else"]):
                    self.close(stack.pop(), i - 1)
                if stack:
                    stack[-1]["else"] = True
                    stack[-1]["cond"]["else_line"] = t.line
                else:
                    self.warn(t, "ELSE without an open IF")
                cur = None
                i += 1
                continue
            if u == "WHEN" and any(e["type"] in ("EVALUATE", "SEARCH") for e in stack):
                while stack[-1]["type"] not in ("EVALUATE", "SEARCH"):
                    self.close(stack.pop(), i - 1)
                e = stack[-1]
                if e["when"] is not None:
                    e["when"]["end_line"] = self.prev_line(i)
                j = self.cond_end(i + 1)
                if e["type"] == "EVALUATE":
                    rec = self.cond_record("WHEN", toks[i + 1:j], t, block, e["rec"])
                    rec["subject"] = e["subject"]
                    rec["data_items"] = self.data_items_in(list(e["subject_toks"]) + list(toks[i + 1:j]))
                else:
                    rec = self.cond_record("SEARCH-WHEN", toks[i + 1:j], t, block, e["rec"])
                e["when"] = rec
                cur = None
                i = j
                continue
            if u in PHRASE_STARTS:
                m = self.phrase_match(i)
                if m is not None:
                    end, kind = m
                    owner = self.phrase_owner(cur, stack, kind)
                    if owner is not None:
                        owner.setdefault("phrases", []).append({"kind": kind, "line": t.line})
                        open_here = any(e.get("rec") is owner for e in stack)
                        if not open_here:  # what follows the phrase belongs to the statement until it closes
                            stack.append({"type": "STMT", "rec": owner, "cond": None})
                    cur = None
                    i = end
                    continue
            if u in SCOPE_ENDS:
                want = {"END-IF": "IF", "END-EVALUATE": "EVALUATE", "END-PERFORM": "PERFORM", "END-SEARCH": "SEARCH"}[u]
                if any(e["type"] == want for e in stack):
                    while stack:
                        e = stack.pop()
                        if e["type"] == want:
                            self.close(e, i)
                            break
                        self.close(e, i - 1)
                cur = None
                i += 1
                continue
            if t.k == "w" and u in END_WORDS:
                verb = u[4:]
                if any(e["type"] == "STMT" and e["rec"]["verb"] == verb for e in stack):
                    while stack:
                        e = stack.pop()
                        if e["type"] == "STMT" and e["rec"]["verb"] == verb:
                            self.close(e, i)
                            break
                        self.close(e, i - 1)
                elif cur is not None and cur["verb"] == verb and t.src == cur.get("_src"):
                    cur["end_line"] = max(cur.get("end_line") or 0, t.line)
                cur = None
                i += 1
                continue
            if u == "THEN":
                i += 1
                continue
            if self.is_verb(i):
                nxt, cur = self.statement(i, block, stack, loop)
                self.span_end(self.statements[-1], i, nxt)
                i = nxt
                continue
            if cur is not None:
                cur["operands"].append(t.t)
                if t.src == cur.get("_src"):
                    cur["end_line"] = max(cur.get("end_line") or 0, t.end)
            i += 1
        while stack:
            self.close(stack.pop(), len(toks) - 1)

    @staticmethod
    def inline_loop(stack: List[dict]) -> Optional[dict]:
        for e in reversed(stack):
            if e["type"] == "PERFORM" and e["loop"]:
                return {"via": e["line"], "kind": e["loop"], "file": e["file"]}
        return None

    def statement(self, i: int, block: Block, stack: List[dict], loop: Optional[dict]) -> Tuple[int, Optional[dict]]:
        toks = self.toks
        t = toks[i]
        verb = t.u
        j = i + 1
        if verb == "GO":
            verb = "GO TO"
            if j < len(toks) and toks[j].u == "TO":
                j += 1
        elif verb == "NEXT":
            verb, j = "NEXT SENTENCE", j + 1
        rec = {"verb": verb, "line": t.line, "end_line": t.line, "paragraph": block.name, "operands": [],
               "in_loop": loop}
        rec.update(self.where(t))
        rec["_b"] = self.block_no[id(block)]
        rec["_src"] = t.src
        self.statements.append(rec)
        if verb == "IF":
            end = self.cond_end(j)
            rec["operands"] = [x.t for x in toks[j:end]]
            cond = self.cond_record("IF", toks[j:end], t, block, rec)
            stack.append({"type": "IF", "cond": cond, "else": False, "rec": rec})
            if end < len(toks) and toks[end].u == "NEXT" and end + 1 < len(toks) and toks[end + 1].u == "SENTENCE":
                return end, None
            return end, None
        if verb == "EVALUATE":
            end = j
            while end < len(toks) and toks[end].u != "WHEN" and toks[end].k != ".":
                end += 1
            rec["operands"] = [x.t for x in toks[j:end]]
            cond = self.cond_record("EVALUATE", toks[j:end], t, block, rec)
            stack.append({"type": "EVALUATE", "cond": cond, "when": None, "subject": cond["text"],
                          "subject_toks": toks[j:end], "rec": rec})
            return end, None
        if verb == "SEARCH":
            end = self.stmt_end(j)
            rec["operands"] = [x.t for x in toks[j:end]]
            stack.append({"type": "SEARCH", "cond": None, "when": None, "rec": rec})
            return end, None
        if verb == "PERFORM":
            return self.perform(i, rec, block, stack, loop)
        if verb == "CALL":
            return self.call(i, rec, block, loop)
        if verb == "GO TO":
            end = self.stmt_end(j, stops=("DEPENDING",))
            targets = [x.u for x in toks[j:end] if x.k in ("w", "n")]
            depending = None
            k = end
            if k < len(toks) and toks[k].u == "DEPENDING":
                k += 1
                if k < len(toks) and toks[k].u == "ON":
                    k += 1
                if k < len(toks):
                    depending = toks[k].u
                    k += 1
                self.warn(t, f"GO TO ... DEPENDING ON {depending}: the target is chosen at run time; flow not followed")
            if not targets:
                self.warn(t, "GO TO without a target (set by ALTER); flow not followed")
            rec["operands"] = [x.t for x in toks[j:k]]
            g = {"to": targets, "line": t.line, "paragraph": block.name, "depending_on": depending, "_b": rec["_b"]}
            g.update(self.where(t))
            self.gotos.append(g)
            return k, None
        if verb == "ALTER":
            self.warn(t, "ALTER changes GO TO targets at run time; flow not followed")
        if verb == "NEXT SENTENCE":
            return j, None
        return j, rec

    def perform(self, i: int, rec: dict, block: Block, stack: List[dict], loop: Optional[dict]) -> Tuple[int, None]:
        toks = self.toks
        t = toks[i]
        j = i + 1
        u = (lambda k: toks[k].u if k < len(toks) else "")
        if j >= len(toks):
            return j, None
        first = toks[j]
        if u(j) in ("WITH", "TEST", "VARYING", "UNTIL"):
            inline = True
        elif first.k in ("w", "n") and u(j + 1) == "TIMES" and first.u not in self._names:
            inline = True
        elif first.k in ("w", "n") and first.u in self._names:
            inline = False
        elif first.k in (".", "exec") or self.is_verb(j) or first.u in SCOPE_ENDS:
            inline = True
        else:
            inline = first.k != "w"
        target = thru = qualifier = None
        if not inline:
            target = first.u
            j += 1
            if u(j) in ("OF", "IN"):
                qualifier, j = u(j + 1), j + 2
            if u(j) in ("THRU", "THROUGH"):
                thru, j = u(j + 1), j + 2
                if u(j) in ("OF", "IN"):
                    j += 2
            end = self.stmt_end(j)
        else:
            end = j
            while end < len(toks):
                x = toks[end]
                if x.k in (".", "exec") or self.is_verb(end) or x.u == "END-PERFORM":
                    break
                end += 1
        clause = toks[j:end]
        words = [x.u for x in clause]
        kind = "varying" if "VARYING" in words else ("until" if "UNTIL" in words else ("times" if "TIMES" in words else None))
        rec["operands"] = [x.t for x in toks[i + 1:end]]
        k = 0
        while k < len(clause):
            if clause[k].u == "UNTIL":
                m = k + 1
                while m < len(clause) and clause[m].u not in ("AFTER", "UNTIL", "VARYING"):
                    m += 1
                self.cond_record("UNTIL", clause[k + 1:m], clause[k], block, rec)
                k = m
                continue
            k += 1
        pr = {"from": block.name, "to": target, "thru": thru, "loop": kind, "inline": inline, "line": t.line,
              "end_line": t.line, "in_loop": loop}
        pr.update(self.where(t))
        pr.update({"_b": rec["_b"], "_q": qualifier, "_ctx": loop, "_src": t.src,
                   "_file": self.sources[t.src].file})
        self.span_end(pr, i, end)
        self.performs.append(pr)
        if inline:
            stack.append({"type": "PERFORM", "loop": kind, "line": t.line, "cond": None, "rec": rec, "pr": pr,
                          "file": self.sources[t.src].file})
        elif target not in self._names:
            self.warn(t, f"PERFORM target {target} is not a paragraph or section of this program")
        return end, None

    def call(self, i: int, rec: dict, block: Block, loop: Optional[dict]) -> Tuple[int, None]:
        toks = self.toks
        t = toks[i]
        j = i + 1
        if j >= len(toks):
            return j, None
        tt = toks[j]
        dynamic = tt.k != "s"
        target = lit_value(tt.t).strip().upper() if not dynamic else tt.u
        end = self.stmt_end(j + 1)
        using: List[str] = []
        returning = None
        mode = None
        depth = 0
        for x in toks[j + 1:end]:
            if x.t == "(":
                depth += 1
                continue
            if x.t == ")":
                depth -= 1
                continue
            if depth:
                continue
            if x.u == "USING":
                mode = "using"
            elif x.u == "RETURNING":
                mode = "returning"
            elif x.u in ("BY", "REFERENCE", "CONTENT", "VALUE", "ADDRESS", "OF", "LENGTH"):
                continue
            elif mode == "using" and x.k in ("w", "s", "n"):
                using.append(x.u if x.k == "w" else x.t)
            elif mode == "returning" and x.k == "w":
                returning = x.u
        rec["operands"] = [x.t for x in toks[j:end]]
        c = {"target": target, "dynamic": dynamic, "line": t.line, "paragraph": block.name, "using": using,
             "in_loop": loop}
        if returning:
            c["returning"] = returning
        c.update(self.where(t))
        c["_b"] = rec["_b"]
        self.calls.append(c)
        return end, rec

    def exec_record(self, t: Tok, block: Block, loop: Optional[dict]) -> None:
        kind = t.sub or "?"
        rec = {"verb": f"EXEC {kind}", "line": t.line, "end_line": t.end, "paragraph": block.name, "operands": [],
               "in_loop": loop}
        rec.update(self.where(t))
        rec["_b"] = self.block_no[id(block)]
        rec["_src"] = t.src
        if kind == "SQL":
            s = parse_sql(t.t)
            rec["operands"] = [s["verb"]]
            r = {"line": t.line, "end_line": t.end, "paragraph": block.name, "verb": s["verb"], "tables": s["tables"],
                 "cursor": s["cursor"], "host_vars": s["host_vars"], "multi_row": s["multi_row"], "text": t.t,
                 "in_loop": loop}
            r.update(self.where(t))
            r["_b"] = rec["_b"]
            self.sql.append(r)
        elif kind == "CICS":
            c = parse_cics(t.t)
            rec["operands"] = [c["command"]]
            r = {"line": t.line, "end_line": t.end, "paragraph": block.name, "command": c["command"],
                 "options": c["options"], "in_loop": loop}
            r.update(self.where(t))
            r["_b"] = rec["_b"]
            self.cics.append(r)
        else:
            rec["operands"] = t.u.split()[:1]
        self.statements.append(rec)

    # ---- pass 3: loops reached through PERFORM
    def sort_procedures(self) -> None:
        for rec in self.statements:
            if rec["verb"] not in ("SORT", "MERGE"):
                continue
            ops = [o.upper() for o in rec["operands"]]
            for k, o in enumerate(ops):
                if o == "PROCEDURE" and k > 0 and ops[k - 1] in ("INPUT", "OUTPUT"):
                    m = k + 1
                    if m < len(ops) and ops[m] == "IS":
                        m += 1
                    if m >= len(ops):
                        continue
                    target, thru = ops[m], None
                    if m + 2 < len(ops) and ops[m + 1] in ("THRU", "THROUGH"):
                        thru = ops[m + 2]
                    pr = {"from": rec["paragraph"], "to": target, "thru": thru, "loop": None, "inline": False,
                          "line": rec["line"], "sort": ops[k - 1].lower(), "in_loop": rec["in_loop"]}
                    if rec.get("copybook"):
                        pr["copybook"] = rec["copybook"]
                    pr.update({"_b": rec["_b"], "_q": None, "_ctx": rec["in_loop"]})
                    self.performs.append(pr)

    def compute_loops(self) -> None:
        graph: Dict[int, List[int]] = {k: [] for k in range(len(self.blocks))}
        sources = []
        for pr in self.performs:
            if pr["inline"]:
                continue
            section = self.blocks[pr["_b"]].section
            rng = self.block_range(pr["to"], pr["_q"], pr["thru"], section)
            pr["_range"] = rng
            for b in rng:
                if b not in graph[pr["_b"]]:
                    graph[pr["_b"]].append(b)
            if rng and pr["loop"]:
                sources.append((rng, pr["line"], pr["loop"], pr["_file"]))
            elif rng and pr["_ctx"]:
                sources.append((rng, pr["_ctx"]["via"], pr["_ctx"]["kind"], pr["_ctx"]["file"]))
        # recursion: strongly connected components of the PERFORM graph
        for comp in _sccs(graph):
            if len(comp) > 1 or comp[0] in graph[comp[0]]:
                ordered = [self.blocks[b].name or "(entry)" for b in sorted(comp)]
                names = ", ".join(ordered[:20]) + (f" and {len(ordered) - 20} more" if len(ordered) > 20 else "")
                self.warn(None, f"recursive PERFORM among {names}: COBOL does not support it; in_loop not followed there")
        best: Dict[int, Tuple[int, int, int, str, str]] = {}
        for rng, via, kind, file in sources:
            dist = {b: 0 for b in rng}
            queue = list(rng)
            while queue:
                b = queue.pop(0)
                for nb in graph[b]:
                    if nb not in dist:
                        dist[nb] = dist[b] + 1
                        queue.append(nb)
            for b, d in dist.items():
                cand = (d, len(rng), -via, kind, file)
                if b not in best or cand[:3] < best[b][:3]:
                    best[b] = cand
            for g in self.gotos:
                if g["_b"] in dist:
                    outside = [x for x in g["to"] if self.find_block(x, None, self.blocks[g["_b"]].section) not in dist]
                    if outside:
                        self.warn(None, f"GO TO {', '.join(outside)} at line {g['line']} leaves the range of the loop "
                                        f"PERFORM at line {via}; in_loop does not follow GO TO")
        for group in (self.statements, self.calls, self.sql, self.cics, self.performs):
            for rec in group:
                if rec.get("in_loop") is None and "_b" in rec and rec["_b"] in best:
                    _, _, via, kind, file = best[rec["_b"]]
                    rec["in_loop"] = {"via": -via, "kind": kind, "file": file}
        for c in self.conditions:  # a condition is in the loop of the statement it belongs to
            owner = c.pop("_owner", None)
            c["in_loop"] = owner.get("in_loop") if owner else None

    def paragraph_records(self) -> Tuple[List[dict], List[dict]]:
        paragraphs, sections = [], []
        for k, b in enumerate(self.blocks):
            if b.kind == "paragraph":
                paragraphs.append({"name": b.name, "section": b.section, "start_line": b.start_line, "end_line": b.end_line})
            elif b.kind == "section":
                last = k
                while last + 1 < len(self.blocks) and self.blocks[last + 1].kind == "paragraph" and self.blocks[last + 1].section == b.name:
                    last += 1
                sections.append({"name": b.name, "start_line": b.start_line,
                                 "end_line": max(self.blocks[m].end_line for m in range(k, last + 1))})
        return paragraphs, sections


def _sccs(graph: Dict[int, List[int]]) -> List[List[int]]:
    """Tarjan's strongly connected components, iterative."""
    index: Dict[int, int] = {}
    low: Dict[int, int] = {}
    on_stack = set()
    stack: List[int] = []
    out: List[List[int]] = []
    counter = [0]
    for root in graph:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, pos = work.pop()
            if pos == 0:
                index[node] = low[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            recurse = False
            nbrs = graph.get(node, [])
            for k in range(pos, len(nbrs)):
                nb = nbrs[k]
                if nb not in index:
                    work.append((node, k + 1))
                    work.append((nb, 0))
                    recurse = True
                    break
                if nb in on_stack:
                    low[node] = min(low[node], index[nb])
            if recurse:
                continue
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                out.append(comp)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return out


# --------------------------------------------------------------------------- one program file
PRIVATE_KEYS = ("_b", "_q", "_ctx", "_range", "_src", "_file", "_owner")


def _strip_private(records: Iterable[dict]) -> None:
    for rec in records:
        for key in PRIVATE_KEYS:
            rec.pop(key, None)


def _file_io(statements: List[dict], files: List[dict]) -> None:
    names = {f["name"] for f in files}
    by_record = {r: f["name"] for f in files for r in f.get("records", [])}
    by_name = {f["name"]: f for f in files}
    for s in statements:
        verb = s["verb"]
        ops = [o.upper() for o in s["operands"]]
        hits: List[Tuple[str, Optional[str]]] = []
        if verb == "OPEN":
            mode = None
            for o in ops:
                if o in ("INPUT", "OUTPUT", "I-O", "EXTEND"):
                    mode = o
                elif o in names:
                    hits.append((o, mode))
        elif verb == "CLOSE":
            hits = [(o, None) for o in ops if o in names]
        elif verb in ("READ", "DELETE", "START", "RETURN") and ops:
            if ops[0] in names:
                hits.append((ops[0], None))
        elif verb in ("WRITE", "REWRITE", "RELEASE") and ops:
            if ops[0] in by_record:
                hits.append((by_record[ops[0]], None))
            elif ops[0] in names:
                hits.append((ops[0], None))
        elif verb in ("SORT", "MERGE") and ops:
            if ops[0] in names:
                hits.append((ops[0], None))
            mode = None
            for o in ops[1:]:
                if o in ("USING", "GIVING"):
                    mode = o
                elif o in ("INPUT", "OUTPUT", "ON", "ASCENDING", "DESCENDING", "COLLATING", "WITH"):
                    mode = None
                elif mode and o in names:
                    hits.append((o, mode))
        for name, mode in hits:
            io = {"verb": verb, "line": s["line"], "paragraph": s["paragraph"], "in_loop": s["in_loop"]}
            if mode:
                io["mode"] = mode
            if s.get("copybook"):
                io["copybook"] = s["copybook"]
            by_name[name]["io"].append(io)


def _literal_values(items: List[dict], statements: List[dict]) -> Dict[str, List[str]]:
    """Literal values an identifier can hold: VALUE clauses and MOVE 'literal' TO identifier."""
    out: Dict[str, List[str]] = {}
    for item in items:
        v = item.get("value")
        if v and v[:1] in ("'", '"') and item["level"] != 88:
            out.setdefault(item["name"], []).append(lit_value(v).strip().upper())
    for s in statements:
        ops = s["operands"]
        if s["verb"] == "MOVE" and len(ops) >= 3 and ops[0][:1] in ("'", '"') and ops[1].upper() == "TO":
            for target in ops[2:]:
                if target[:1].isalpha():
                    vals = out.setdefault(target.upper(), [])
                    value = lit_value(ops[0]).strip().upper()
                    if value not in vals:
                        vals.append(value)
    return out


def parse_program_file(path: Path, copy_index: CopyIndex, root: Path, default_format: str = "fixed") -> Tuple[List[dict], List[dict], Dict[str, Path]]:
    """Parse one COBOL file. Returns (program records, file-level warnings, copybook files used)."""
    exp = Expander(copy_index, root, default_format)
    raw_toks, fmt = exp.load(path, None, None)
    toks = exp.expand(raw_toks, (member_name(path),), path, fmt)
    file_rel = rel(path, root)
    text = read_text(path)
    nlines = len(text.splitlines())
    digest = sha256_file(path)
    units = [u for u in split_units(toks) if u]
    programs: List[dict] = []
    file_warnings: List[dict] = []
    unit_ranges = []
    for unit in units:
        own = [t.line for t in unit if t.src == 0]
        unit_ranges.append((min(own) if own else 0, max(own) if own else 0))
    owner: Dict[int, int] = {}
    last_direct = 0
    for k, cb in enumerate(exp.copybooks):
        if cb["nested_in"] is None:
            for u, (a, b) in enumerate(unit_ranges):
                if cb["line"] >= a:
                    last_direct = u
        owner[k] = last_direct
    for u_index, unit in enumerate(units):
        pid_tok = program_id(unit)
        if pid_tok is None:
            file_warnings.append({"file": file_rel, "line": unit[0].line, "message": "no PROGRAM-ID found; text not analysed as a program"})
            continue
        pid = lit_value(pid_tok.t).strip().upper()
        warnings: List[dict] = []
        divs = division_ranges(unit)
        env = unit[slice(*divs["ENVIRONMENT"])] if "ENVIRONMENT" in divs else []
        data = unit[slice(*divs["DATA"])] if "DATA" in divs else []
        files = parse_selects(env)
        items, data_warnings = parse_data_division(data, exp.sources, files)
        warnings.extend(data_warnings)
        data_names = {i["name"] for i in items if i["name"] != "FILLER"}
        for i in items:
            if i["occurs"]:
                data_names.update(i["occurs"]["indexed_by"])
        file_records = {r: f["name"] for f in files for r in f.get("records", [])}
        parser = ProcParser(unit, exp.sources, data_names, file_records)
        using: List[str] = []
        using_line: Optional[int] = None
        if "PROCEDURE" in divs:
            start = divs["PROCEDURE"][0] + 2
            j = start
            mode = None
            while j < len(unit) and unit[j].k != ".":
                if unit[j].u == "USING" and using_line is None:
                    using_line = unit[j].line
                if unit[j].u in ("USING", "RETURNING"):
                    mode = unit[j].u
                elif mode == "USING" and unit[j].k == "w" and unit[j].u not in ("BY", "REFERENCE", "VALUE", "CONTENT"):
                    using.append(unit[j].u)
                j += 1
            body = j + 1
            parser.find_blocks(body)
            parser.parse(body)
            parser.sort_procedures()
            parser.compute_loops()
        else:
            warnings.append({"file": file_rel, "line": None, "message": "no PROCEDURE DIVISION found"})
        data_sql = []
        for t in data:
            if t.k == "exec" and t.sub == "SQL":
                s = parse_sql(t.t)
                rec = {"line": t.line, "end_line": t.end, "paragraph": None, "verb": s["verb"], "tables": s["tables"],
                       "cursor": s["cursor"], "host_vars": s["host_vars"], "multi_row": s["multi_row"],
                       "text": t.t, "in_loop": None}
                src = exp.sources[t.src]
                if src.copybook:
                    rec["copybook"] = src.copybook
                data_sql.append(rec)
        parser.sql[:0] = data_sql
        sql_includes: List[str] = []
        for t in unit:
            if t.k == "exec" and t.sub == "SQL":
                member = parse_sql(t.t)["include"]
                if member and member.upper() not in sql_includes:
                    sql_includes.append(member.upper())
        cursor_tables = {s["cursor"]: s["tables"] for s in parser.sql if s["verb"] == "DECLARE CURSOR" and s["cursor"]}
        for s in parser.sql:
            if s["cursor"] and not s["tables"] and s["cursor"] in cursor_tables:
                s["tables"] = list(cursor_tables[s["cursor"]])
        _file_io(parser.statements, files)
        values = _literal_values(items, parser.statements)
        for c in parser.calls:
            if c["dynamic"]:
                c["candidates"] = values.get(c["target"], [])
        for c in parser.cics:
            prog = c["options"].get("program")
            if isinstance(prog, str) and prog[:1] not in ("'", '"'):
                c["candidates"] = values.get(prog.upper(), [])
        paragraphs, sections = parser.paragraph_records()
        for group in (parser.statements, parser.performs, parser.calls, parser.gotos, parser.sql, parser.cics,
                      parser.conditions):
            _strip_private(group)
        copybooks = [dict(cb) for k, cb in enumerate(exp.copybooks) if owner.get(k, 0) == u_index]
        for cb in copybooks:
            if cb["resolved"] is None:
                warnings.append({"file": file_rel if cb["nested_in"] is None else None, "line": cb["line"],
                                 "message": f"copybook {cb['name']} not found"
                                            + (f" (COPY in {cb['nested_in']})" if cb["nested_in"] else "")
                                            + "; its data items and code are missing from this map"})
        warnings.extend(w for w in exp.warnings if w not in warnings)
        warnings.extend(parser.warnings)
        for f in files:
            f.setdefault("records", [])
        programs.append({
            "id": pid, "language": "cobol", "file": file_rel, "sha256": digest, "format": fmt, "lines": nlines,
            "copybooks": copybooks, "files": files, "data_items": items, "paragraphs": paragraphs,
            "sections": sections, "performs": parser.performs, "calls": parser.calls, "gotos": parser.gotos,
            "sql": parser.sql, "cics": parser.cics, "conditions": parser.conditions,
            "statements": parser.statements, "procedure_using": using, "procedure_using_line": using_line,
            "sql_includes": sql_includes, "warnings": warnings,
        })
    if len(programs) > 1:
        file_warnings.append({"file": file_rel, "line": None,
                              "message": f"{len(programs)} programs in one file (nested or batched); each is mapped on its own"})
    return programs, file_warnings, exp.used_files


# --------------------------------------------------------------------------- JCL
JCL_SYMBOL = re.compile(r"(?<!&)&(?!&)([A-Za-z@#$][A-Za-z0-9@#$]{0,7})(\.?)")
SYSTEM_SYMBOLS = {"SYSUID", "SYSNAME", "SYSCLONE", "SYSPLEX", "LYYMMDD", "LHHMMSS", "YYMMDD", "HHMMSS",
                  "JOBNAME", "SYSALVL", "SYSSMFID", "SYSR1", "LDAY", "LMON", "LYR4", "SEQ"}


def _split_operand_field(text: str) -> str:
    """The operand field: up to the first blank outside apostrophes."""
    quote = False
    for k, c in enumerate(text):
        if c == "'":
            quote = not quote
        elif c == " " and not quote:
            return text[:k]
    return text


def split_operands(text: str) -> List[Tuple[Optional[str], str]]:
    """'PGM=X,PARM='A,B',COND=(4,LT)' -> [('PGM','X'), ('PARM',"'A,B'"), ('COND','(4,LT)')]."""
    parts, depth, quote, cur = [], 0, False, ""
    for c in text:
        if c == "'":
            quote = not quote
        elif not quote and c == "(":
            depth += 1
        elif not quote and c == ")":
            depth -= 1
        if c == "," and depth == 0 and not quote:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    if cur:
        parts.append(cur)
    out: List[Tuple[Optional[str], str]] = []
    for p in parts:
        k = p.find("=")
        if k > 0 and "'" not in p[:k] and "(" not in p[:k]:
            out.append((p[:k].upper(), p[k + 1:]))
        else:
            out.append((None, p))
    return out


def unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def resolve_symbols(text: Optional[str], symbols: Dict[str, str]) -> Tuple[Optional[str], List[str]]:
    """Substitute &NAME and &NAME. from symbols. Returns (text or None when any symbol is missing, missing)."""
    if text is None:
        return None, []
    missing: List[str] = []

    def sub(m: "re.Match[str]") -> str:
        name = m.group(1).upper()
        if name in symbols:
            return symbols[name]
        missing.append(name)
        return m.group(0)

    out = text
    for _ in range(5):  # symbols whose values hold symbols
        new = JCL_SYMBOL.sub(sub, out)
        if new == out:
            break
        out = new
    return (None if missing else out), sorted(set(missing))


def jcl_statements(raw_lines: Sequence[str]) -> List[dict]:
    """Logical JCL statements with continuations joined and in-stream data attached."""
    stmts: List[dict] = []
    i = 0
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i].rstrip("\r\n").expandtabs(8)
        lineno = i + 1
        i += 1
        if line.startswith("//*") or not line.startswith("//"):
            continue
        body = line[2:71]
        if not body.strip():
            continue
        if body[0] != " ":
            parts = body.split(None, 1)
            name, rest = parts[0], (parts[1] if len(parts) > 1 else "")
        else:
            name, rest = "", body.strip()
        bits = rest.split(None, 1)
        op = bits[0].upper() if bits else ""
        field = _split_operand_field(bits[1].lstrip()) if len(bits) > 1 else ""
        if op == "IF" and len(bits) > 1:  # the condition holds blanks: keep the whole rest, without THEN
            field = bits[1].strip()
            if field.upper().endswith("THEN"):
                field = field[:-4].rstrip()
        while (field.endswith(",") or field.count("'") % 2 == 1) and i < n:
            nxt = raw_lines[i].rstrip("\r\n").expandtabs(8)
            if not nxt.startswith("//") or nxt.startswith("//*"):
                if nxt.startswith("//*"):
                    i += 1
                    continue
                break
            i += 1
            if field.count("'") % 2 == 1:
                field += nxt[15:71].rstrip()
            else:
                field += _split_operand_field(nxt[2:71].strip())
        stmt = {"name": name.upper(), "op": op, "operands": field, "line": lineno, "data": None}
        if op == "DD":
            ops = split_operands(field)
            positional = [v.upper() for k, v in ops if k is None]
            dlm = next((unquote(v) for k, v in ops if k == "DLM"), None)
            if positional and positional[0] in ("*", "DATA"):
                data = []
                stmt["data_line"] = i + 1
                is_data = positional[0] == "DATA"
                while i < n:
                    d = raw_lines[i].rstrip("\r\n")
                    if dlm and d.startswith(dlm):
                        i += 1
                        break
                    if not dlm and d.startswith("/*"):
                        i += 1
                        break
                    if not dlm and not is_data and d.startswith("//"):
                        break
                    data.append(d)
                    i += 1
                stmt["data"] = data
        stmts.append(stmt)
    return stmts


def _dd_record(stmt: dict, prev_name: Optional[str]) -> dict:
    ops = split_operands(stmt["operands"])
    kv = {k: v for k, v in ops if k}
    positional = [v.upper() for k, v in ops if k is None]
    name = stmt["name"]
    concat = False
    if not name:
        name, concat = (prev_name or ""), True
    dsn = kv.get("DSN", kv.get("DSNAME"))
    dd = {"name": name, "dsn": dsn.upper() if dsn else None, "disp": kv.get("DISP"),
          "inline": bool(positional and positional[0] in ("*", "DATA")),
          "sysout": kv.get("SYSOUT"), "line": stmt["line"]}
    if concat:
        dd["concat"] = True
    if positional and positional[0] == "DUMMY":
        dd["dummy"] = True
    if kv.get("PATH"):
        dd["path"] = unquote(kv["PATH"])
    if stmt.get("data") is not None:
        dd["inline_lines"] = len(stmt["data"])
    return dd


TSO_COMMANDS = {
    "ALLOC", "ALLOCATE", "ATTRIB", "CANCEL", "DELETE", "DEL", "EDIT", "END", "FREE", "HELP", "LINK", "LISTALC",
    "LISTBC", "LISTCAT", "LISTC", "LISTDS", "LOGOFF", "OUTPUT", "PRINTDS", "PROFILE", "PROTECT", "RECEIVE",
    "RENAME", "RUN", "SEND", "STATUS", "SUBMIT", "SUB", "TERMINAL", "TIME", "TRANSMIT", "XMIT", "WHEN", "DSN",
    "ISPSTART", "ALTLIB", "EXECUTIL", "SMCOPY", "TEST", "OPUT", "OGET", "OSHELL", "BPXBATCH", "SE",
}
_MEMBER = re.compile(r"[A-Za-z@#$][A-Za-z0-9@#$]{0,7}$")


def tso_commands(lines: Sequence[str], first_line: Optional[int] = None) -> List[dict]:
    """Execs and programs a TSO batch input (SYSTSIN, or an IKJEFT01 PARM) runs: {name, how, line}.

    how is "%" (%NAME), "EXEC" (EXEC 'lib(NAME)' or EXEC NAME), "CALL" (CALL 'lib(NAME)'), or
    "implicit" for a bare word that is not a TSO command (an exec only when the map has one by
    that name). Lines between DSN and END are DSN subcommands and are left out. Data, read for
    names only.
    """
    out: List[dict] = []
    in_dsn = False
    for k, raw in enumerate(lines):
        text = raw[:72].strip()
        if not text or text.startswith("/*") or text.startswith("*"):
            continue
        words = text.split()
        head = words[0].upper()
        line = first_line + k if first_line is not None else None
        if head == "DSN":
            in_dsn = True
            continue
        if in_dsn:
            if head == "END":
                in_dsn = False
            continue
        name, how = None, None
        if head.startswith("%") and len(head) > 1:
            name, how = head[1:], "%"
        elif head in ("EXEC", "EX", "CALL") and len(words) > 1:
            arg = words[1].strip("'\"")
            m = re.search(r"\(([A-Za-z@#$][A-Za-z0-9@#$]{0,7})\)", arg)
            name = m.group(1) if m else arg
            how = "CALL" if head == "CALL" else "EXEC"
        elif head not in TSO_COMMANDS:
            name, how = head, "implicit"
        if name and _MEMBER.match(name):
            rec = {"name": name.upper(), "how": how}
            if line is not None:
                rec["line"] = line
            out.append(rec)
    return out


def _tso_run_program(lines: Sequence[str]) -> Optional[str]:
    """DSN RUN PROGRAM(X) in a SYSTSIN in-stream deck (data, read only for the program name)."""
    text = " ".join(lines).upper()
    for key in ("PROGRAM(", "PROG("):
        k = text.find(key)
        if k >= 0 and "RUN" in text[:k]:
            end = text.find(")", k)
            if end > k:
                return text[k + len(key):end].strip().strip("'") or None
    return None


def parse_jcl_file(path: Path, root: Path, jcl_index: Dict[str, Path]) -> Tuple[List[dict], List[dict], List[dict]]:
    """Jobs, procs (in-stream, or the file itself as a cataloged proc) and warnings of one JCL file."""
    file_rel = rel(path, root)
    stmts = jcl_statements(read_text(path).splitlines())
    jobs: List[dict] = []
    procs: List[dict] = []
    warnings: List[dict] = []
    job: Optional[dict] = None
    proc: Optional[dict] = None
    step: Optional[dict] = None
    symbols: Dict[str, str] = {}
    if_stack: List[str] = []
    prev_dd: Optional[str] = None
    has_job = any(s["op"] == "JOB" for s in stmts)
    if not has_job and not any(s["op"] == "PROC" for s in stmts) and any(s["op"] == "EXEC" for s in stmts):
        proc = {"name": member_name(path), "file": file_rel, "kind": "proc", "source": "cataloged",
                "line": 1, "defaults": {}, "steps": []}
        procs.append(proc)

    def container() -> Optional[dict]:
        return proc if proc is not None else job

    for st in stmts:
        op = st["op"]
        ops = split_operands(st["operands"])
        if op == "JOB":
            job = {"name": st["name"], "file": file_rel, "line": st["line"], "steps": [], "symbols": {},
                   "includes": [], "jcllib": [], "dd": []}
            jobs.append(job)
            symbols, step, proc, prev_dd, if_stack = {}, None, None, None, []
        elif op == "PROC":
            in_stream = job is not None
            name = st["name"] or member_name(path)
            proc = {"name": name if in_stream else member_name(path), "file": file_rel, "kind": "proc",
                    "source": "in-stream" if in_stream else "cataloged", "line": st["line"],
                    "defaults": {k: unquote(v) for k, v in ops if k}, "steps": []}
            if not in_stream and st["name"] and st["name"] != proc["name"]:
                proc["statement_name"] = st["name"]
            if in_stream:
                proc["job"] = job["name"]
            procs.append(proc)
            step, prev_dd = None, None
        elif op == "PEND":
            proc, step, prev_dd = None, None, None
        elif op == "SET":
            for k, v in ops:
                if k:
                    value, _ = resolve_symbols(unquote(v), symbols)
                    if value is not None:
                        symbols[k] = value
                    else:
                        symbols.pop(k, None)  # its value rests on a symbol we do not know
            if job is not None and proc is None:
                job["symbols"] = dict(symbols)
        elif op == "INCLUDE":
            member = next((unquote(v).upper() for k, v in ops if k == "MEMBER"), None)
            target = jcl_index.get(member) if member else None
            if job is not None:
                job["includes"].append({"member": member, "resolved": rel(target, root) if target else None,
                                        "line": st["line"]})
            if target is not None:
                for inc in jcl_statements(read_text(target).splitlines()):
                    if inc["op"] == "SET":
                        for k, v in split_operands(inc["operands"]):
                            if k:
                                symbols[k] = unquote(v)
                if job is not None:
                    job["symbols"] = dict(symbols)
        elif op == "JCLLIB" and job is not None:
            order = next((v for k, v in ops if k == "ORDER"), "")
            job["jcllib"] = [unquote(x) for x in order.strip("()").split(",") if x.strip()]
        elif op == "IF":
            if_stack.append(st["operands"].rstrip())
        elif op == "ELSE" and if_stack:
            if_stack[-1] = f"NOT ({if_stack[-1]})"
        elif op == "ENDIF" and if_stack:
            if_stack.pop()
        elif op == "EXEC":
            kv = {k: v for k, v in ops if k}
            positional = [v for k, v in ops if k is None]
            pgm = kv.get("PGM")
            proc_name = kv.get("PROC") or (positional[0] if positional else None)
            step = {"name": st["name"], "pgm": unquote(pgm).upper() if pgm else None,
                    "proc": proc_name.upper() if proc_name and not pgm else None, "line": st["line"],
                    "cond": kv.get("COND"), "parm": kv.get("PARM"), "dd": []}
            if if_stack:
                step["if"] = " AND ".join(if_stack)
            parm_text = unquote(kv["PARM"]).strip() if kv.get("PARM") else ""
            if step["pgm"] == "IRXJCL" and parm_text:  # IRXJCL runs the exec named first in PARM
                first = parm_text.split()[0].lstrip("%").upper()
                if _MEMBER.match(first):
                    step["execs"] = [{"name": first, "how": "PARM", "line": st["line"]}]
            elif step["pgm"] in TSO_BATCH and parm_text:
                found_execs = tso_commands([parm_text], st["line"])
                if found_execs:
                    step["execs"] = [dict(e, how="PARM" if e["how"] == "implicit" else e["how"]) for e in found_execs]
            if step["proc"]:
                exec_keys = {"PARM", "COND", "REGION", "TIME", "ACCT", "ADDRSPC", "DPRTY", "DYNAMNBR",
                             "PERFORM", "RD", "MEMLIMIT", "CCSID", "PROC", "PGM", "TVSMSG", "TVSAMCOM"}
                step["overrides"] = {k: v for k, v in kv.items() if k.split(".")[0] not in exec_keys}
            if job is not None and proc is None:
                step["_symbols"] = dict(symbols)
            holder = container()
            if holder is None:
                warnings.append({"file": file_rel, "line": st["line"], "message": "EXEC before any JOB or PROC statement"})
            else:
                holder["steps"].append(step)
            prev_dd = None
        elif op == "DD":
            dd = _dd_record(st, prev_dd)
            prev_dd = dd["name"].split(".")[-1] if dd["name"] else prev_dd
            if step is not None:
                step["dd"].append(dd)
                if st.get("data") is not None and dd["name"] in ("SYSTSIN",) and step.get("pgm") in TSO_BATCH:
                    runs = _tso_run_program(st["data"])
                    if runs:
                        step["runs"] = runs
                    found_execs = tso_commands(st["data"], st.get("data_line"))
                    if found_execs:
                        step.setdefault("execs", []).extend(found_execs)
            elif job is not None:
                job["dd"].append(dd)
            if job is not None and proc is None:
                dd["_symbols"] = dict(symbols)
    if not jobs and not procs:
        warnings.append({"file": file_rel, "line": None,
                         "message": "no JOB, PROC or EXEC statement found (an INCLUDE member, or not JCL)"})
    return jobs, procs, warnings


def _resolve_dds(dds: List[dict], ctx: Dict[str, str], where: str, warnings: List[dict], file: str) -> None:
    for dd in dds:
        own = dd.pop("_symbols", None)
        symbols = dict(own) if own is not None else {}
        symbols.update(ctx)
        if dd["dsn"] is None:
            dd["dsn_resolved"] = None
            continue
        value, missing = resolve_symbols(dd["dsn"], symbols)
        dd["dsn_resolved"] = value
        unknown = [m for m in missing if m not in SYSTEM_SYMBOLS]
        if unknown:
            warnings.append({"file": file, "line": dd["line"],
                             "message": f"{where}: DSN {dd['dsn']} uses {', '.join('&' + m for m in unknown)} with no value from SET or PROC defaults"})


def expand_proc_steps(proc: dict, ctx: Dict[str, str], dd_overrides: List[dict], procs: Dict[str, dict],
                      depth: int, warnings: List[dict], where: str) -> List[dict]:
    """A copy of a proc's steps with symbols resolved in the caller's context."""
    out = []
    for pstep in proc["steps"]:
        s = json.loads(json.dumps({k: v for k, v in pstep.items() if k != "proc_steps"}))
        for dd in s["dd"]:
            dd.pop("_symbols", None)
        prefix = f"{pstep['name']}."
        for ov in dd_overrides:
            if ov["name"].startswith(prefix):
                name = ov["name"][len(prefix):]
                repl = dict(ov, name=name, override=True)
                idx = next((k for k, d in enumerate(s["dd"]) if d["name"] == name), None)
                if idx is None:
                    s["dd"].append(repl)
                else:
                    s["dd"][idx] = repl
        _resolve_dds(s["dd"], ctx, f"{where}.{pstep['name']}", warnings, proc["file"])
        if s.get("proc") and depth < 5:
            inner = procs.get(s["proc"])
            if inner is not None:
                inner_ctx = dict(ctx)
                inner_ctx.update(inner.get("defaults", {}))
                for k, v in (s.get("overrides") or {}).items():
                    val, _ = resolve_symbols(unquote(v), ctx)
                    if val is not None:
                        inner_ctx[k] = val
                    else:
                        inner_ctx.pop(k, None)
                s["proc_steps"] = expand_proc_steps(inner, inner_ctx, s["dd"], procs, depth + 1, warnings,
                                                    f"{where}.{pstep['name']}")
        out.append(s)
    return out


# --------------------------------------------------------------------------- the whole map
def _abs(path, base: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else base / p


def _walk_steps(steps: List[dict], prefix: str = ""):
    """(step path, step) for steps and the proc steps expanded under them."""
    for s in steps:
        path = f"{prefix}{s['name']}"
        yield path, s
        if s.get("proc_steps"):
            yield from _walk_steps(s["proc_steps"], path + ".")


class _Edges:
    def __init__(self):
        self.items: List[dict] = []
        self.seen: Dict[Tuple[str, str, str], dict] = {}

    def add(self, src: str, dst: str, kind: str, **extra) -> dict:
        key = (src, dst, kind)
        if key in self.seen:
            return self.seen[key]
        edge = {"from": src, "to": dst, "kind": kind}
        edge.update({k: v for k, v in extra.items() if v is not None})
        self.seen[key] = edge
        self.items.append(edge)
        return edge


def scan(roots: Sequence, copy_dirs: Sequence = (), root: Optional[Path] = None,
         default_format: str = "fixed") -> dict:
    """Scan folders and return the app-map dict (contract version 1). Writes nothing."""
    base = project_root(root)
    root_paths = [_abs(r, base) for r in roots]
    copy_paths = [_abs(c, base) for c in copy_dirs]
    for given, p in list(zip(roots, root_paths)) + list(zip(copy_dirs, copy_paths)):
        if not p.exists():
            raise MapError(f"{given}: no such folder or file")
    in_roots = {os.path.realpath(p) for p in iter_source_files(root_paths)}
    classified = [(p, sniff(p)) for p in iter_source_files(copy_paths + root_paths)]
    copy_index = CopyIndex(classified)
    jcl_index: Dict[str, Path] = {}
    for p, kind in classified:
        if kind == "jcl":
            jcl_index.setdefault(member_name(p), p)
    programs: List[dict] = []
    warnings: List[dict] = []
    not_analysed: Dict[str, List[str]] = {"pli": [], "asm": [], "rexx": []}
    jcl_files: List[Path] = []
    lang_includes: List[Tuple[Path, str]] = []
    include_dirs = [rel(p, base) for p in copy_paths + root_paths]
    lang_include_arg: Dict[str, Any] = {}
    for p, kind in classified:
        in_root = os.path.realpath(p) in in_roots
        if kind == "cobol" and in_root:
            try:
                progs, fw, _used = parse_program_file(p, copy_index, base, default_format)
            except Exception as error:  # one odd file must not stop the map of the rest
                warnings.append({"file": rel(p, base), "line": None,
                                 "message": f"not analysed: the parser failed ({type(error).__name__}: {error})"})
                continue
            programs.extend(progs)
            warnings.extend(fw)
        elif kind in LANG_MODULES:
            module = language_module(kind)
            if module is None:
                if in_root:
                    not_analysed[kind].append(rel(p, base))
                continue
            try:
                role = module.classify(p, read_text(p))
                if role == "program" and in_root:
                    if kind not in lang_include_arg:
                        index = getattr(module, "IncludeIndex", None)
                        lang_include_arg[kind] = index(include_dirs, base) if index else include_dirs
                    record = module.scan_program(p, lang_include_arg[kind], base)
                    record.setdefault("language", kind)
                    programs.append(record)
                elif role in ("include", "program"):
                    lang_includes.append((p, kind))
                elif in_root:
                    not_analysed[kind].append(rel(p, base))
            except Exception as error:  # one odd file must not stop the map of the rest
                warnings.append({"file": rel(p, base), "line": None,
                                 "message": f"not analysed: the {LANG_NAMES[kind]} reader failed "
                                            f"({type(error).__name__}: {error})"})
                if in_root:
                    not_analysed[kind].append(rel(p, base))
        elif kind == "jcl" and in_root:
            jcl_files.append(p)

    # a REXX exec that another exec pulls in with /*%INCLUDE*/ is an include member, not a program
    rexx_included = {cb["resolved"] for prog in programs if prog.get("language") == "rexx"
                     for cb in prog["copybooks"] if cb.get("resolved")}
    if rexx_included:
        kept = []
        for prog in programs:
            if prog.get("language") == "rexx" and prog["file"] in rexx_included:
                lang_includes.append((_abs(prog["file"], base), "rexx"))
            else:
                kept.append(prog)
        programs = kept

    prog_by_id: Dict[str, dict] = {}
    for prog in programs:
        prog.setdefault("language", "cobol")
        prog["partial"] = any(cb["resolved"] is None for cb in prog["copybooks"])
        prog["run_by"] = []
        if prog["id"] in prog_by_id:
            first = prog_by_id[prog["id"]]
            label = "PROGRAM-ID" if prog.get("language") == "cobol" else "program id"
            warnings.append({"file": prog["file"], "line": None,
                             "message": f"{label} {prog['id']} also in {first['file']}; links use that first one"})
        else:
            prog_by_id[prog["id"]] = prog
    entry_index: Dict[str, dict] = {}  # secondary entry points (PL/I entries, Assembler ENTRY)
    for prog in programs:
        for e in prog.get("entries") or []:
            name = str(e.get("name") or "").upper()
            if name and name not in prog_by_id:
                entry_index.setdefault(name, prog)

    def find(name: Optional[str]) -> Optional[dict]:
        """The program a name runs or calls: a program id first, then a secondary entry point."""
        if not name:
            return None
        key = str(name).upper()
        return prog_by_id.get(key) or entry_index.get(key)

    # copybooks, include members and macro definitions
    catalog: Dict[str, dict] = {}
    for prog in programs:
        resolved_by_name = {}
        for cb in prog["copybooks"]:
            if cb["resolved"] is None:
                continue
            resolved_by_name.setdefault(cb["name"], cb["resolved"])
            entry = catalog.setdefault(cb["resolved"], {"name": member_name(Path(cb["resolved"])), "file": cb["resolved"],
                                                       "used_by": set(), "includes": set(),
                                                       "language": prog.get("language", "cobol")})
            entry["used_by"].add(prog["id"])
            if cb["nested_in"] and cb["nested_in"] in resolved_by_name:
                catalog[resolved_by_name[cb["nested_in"]]]["includes"].add(cb["name"])
    for p, kind in classified:
        if kind == "copybook" and p.suffix.lower() in COPY_EXT | COBOL_EXT:
            catalog.setdefault(rel(p, base), {"name": member_name(p), "file": rel(p, base), "used_by": set(),
                                              "includes": set(), "language": "cobol"})
    for p, kind in lang_includes:
        catalog.setdefault(rel(p, base), {"name": member_name(p), "file": rel(p, base), "used_by": set(),
                                          "includes": set(), "language": kind})
    copybooks = []
    for file, entry in sorted(catalog.items(), key=lambda kv: (kv[1]["name"], kv[0])):
        path = _abs(file, base)
        copybooks.append({"name": entry["name"], "file": file, "language": entry["language"],
                          "lines": len(read_text(path).splitlines()), "sha256": sha256_file(path),
                          "used_by": sorted(entry["used_by"]), "includes": sorted(entry["includes"])})

    # JCL
    jobs: List[dict] = []
    procs: List[dict] = []
    for p in jcl_files:
        try:
            j, pr, w = parse_jcl_file(p, base, jcl_index)
        except Exception as error:  # one odd file must not stop the map of the rest
            warnings.append({"file": rel(p, base), "line": None,
                             "message": f"not analysed: the JCL reader failed ({type(error).__name__}: {error})"})
            continue
        jobs.extend(j)
        procs.extend(pr)
        warnings.extend(w)
    cataloged: Dict[str, dict] = {}
    for pr in procs:
        if pr["source"] == "cataloged":
            if pr["name"] in cataloged:
                warnings.append({"file": pr["file"], "line": pr["line"],
                                 "message": f"cataloged PROC {pr['name']} also in {cataloged[pr['name']]['file']}; jobs use that first one"})
            else:
                cataloged[pr["name"]] = pr
    unresolved_procs: Dict[str, set] = {}
    used_procs = set()
    for job in jobs:
        lookup = dict(cataloged)
        lookup.update({pr["name"]: pr for pr in procs if pr.get("job") == job["name"] and pr["file"] == job["file"]})
        _resolve_dds(job["dd"], {}, job["name"], warnings, job["file"])
        for st in job["steps"]:
            st_symbols = st.pop("_symbols", {})
            _resolve_dds(st["dd"], {}, f"{job['name']}.{st['name']}", warnings, job["file"])
            if not st["proc"]:
                continue
            pr = lookup.get(st["proc"])
            if pr is None:
                unresolved_procs.setdefault(st["proc"], set()).add(job["name"])
                continue
            used_procs.add(id(pr))
            st["proc_source"] = pr["source"]
            ctx = dict(st_symbols)
            ctx.update(pr.get("defaults", {}))
            for k, v in (st.get("overrides") or {}).items():
                val, _ = resolve_symbols(unquote(v), st_symbols)
                if val is not None:
                    ctx[k] = val
                else:
                    ctx.pop(k, None)  # the override rests on a symbol we do not know
            st["proc_steps"] = expand_proc_steps(pr, ctx, st["dd"], lookup, 1, warnings, f"{job['name']}.{st['name']}")
    for pr in procs:
        for st in pr["steps"]:
            st.pop("_symbols", None)
            _resolve_dds(st["dd"], pr.get("defaults", {}), pr["name"], [], pr["file"])

    # program to job links and the datasets behind each file
    utilities: Dict[str, set] = {}
    unresolved_programs: Dict[str, dict] = {}

    def missing_program(name: str, kind: str, by: str) -> None:
        entry = unresolved_programs.setdefault(name, {"name": name, "kinds": set(), "referenced_by": set()})
        entry["kinds"].add(kind)
        entry["referenced_by"].add(by)

    for job in jobs:
        for path, st in _walk_steps(job["steps"]):
            targets = [(st.get("pgm"), None, True), (st.get("runs"), st.get("pgm"), True)]
            for ex in st.get("execs") or []:  # TSO batch: %NAME, EXEC 'lib(NAME)', CALL, a bare NAME
                found = find(ex["name"])
                if ex["how"] == "implicit" and (found is None or found.get("language") != "rexx"):
                    continue  # a bare word is a TSO command unless an exec of the map has that name
                targets.append((ex["name"], st.get("pgm"), ex["how"] != "implicit"))
            for target, via, report in targets:
                if not target:
                    continue
                prog = find(target)
                if prog is not None:
                    link = {"job": job["name"], "step": path, "file": job["file"]}
                    if via:
                        link["via"] = via
                    if target.upper() != prog["id"]:
                        link["entry"] = target.upper()
                    if link not in prog["run_by"]:
                        prog["run_by"].append(link)
                    for f in prog["files"]:
                        if not f.get("dd"):
                            continue
                        for dd in st["dd"]:
                            if dd["name"] == f["dd"]:
                                f.setdefault("datasets", []).append({
                                    "job": job["name"], "step": path, "dsn": dd["dsn"],
                                    "dsn_resolved": dd.get("dsn_resolved"), "disp": dd["disp"],
                                    "sysout": dd["sysout"], "inline": dd["inline"]})
                elif target in KNOWN_UTILITIES:
                    utilities.setdefault(target, set()).add(job["name"])
                elif report:
                    missing_program(target, "exec-pgm" if via is None or st.get("runs") == target else "tso-exec",
                                    job["name"])
    for prog in programs:
        for f in prog["files"]:
            f.setdefault("datasets", [])

    # edges
    edges = _Edges()
    for prog in programs:
        pid = prog["id"]
        for c in prog["calls"]:
            if c.get("system"):
                continue  # a routine z/OS supplies (BPXWDYN, SYSCALLS...): neither a link nor missing
            how = c.get("via") or c.get("kind") or c.get("form")  # REXX, Assembler, PL/I wording
            how = None if how in (None, "CALL") else how
            names = [c["target"]] if not c["dynamic"] else list(c.get("candidates") or [])
            for name in names:
                target = find(name)
                to = target["id"] if target is not None else str(name).upper()
                e = edges.add(pid, to, "call", line=c["line"], dynamic=True if c["dynamic"] else None, via=how)
                if target is not None and str(name).upper() != to:
                    e.setdefault("entry", str(name).upper())
                if target is None:
                    missing_program(str(name).upper(), "call", pid)
        for pr in prog["performs"]:
            if pr["to"]:
                edges.add(f"{pid}:{pr['from'] or '(entry)'}", f"{pid}:{pr['to']}", "perform", line=pr["line"],
                          thru=pr["thru"], loop=pr["loop"])
        for cb in prog["copybooks"]:
            edges.add(cb["nested_in"] or pid, cb["name"], "copy")
        for s in prog["sql"]:
            if s["verb"] in ("DECLARE TABLE", "INCLUDE"):
                continue
            for table in s["tables"]:
                e = edges.add(pid, table, "sql-table", verbs=[])
                if s["verb"] not in e["verbs"]:
                    e["verbs"].append(s["verb"])
        for c in prog["cics"]:
            cmd = c["command"]
            if cmd not in ("LINK", "XCTL"):
                continue
            prog_opt = c["options"].get("program")
            kind = "cics-link" if cmd == "LINK" else "cics-xctl"
            if isinstance(prog_opt, str) and prog_opt[:1] in ("'", '"'):
                target = lit_value(prog_opt).strip().upper()
                found = find(target)
                edges.add(pid, found["id"] if found else target, kind, line=c["line"])
                if found is None:
                    missing_program(target, kind, pid)
            else:
                for cand in c.get("candidates", []):
                    found = find(cand)
                    edges.add(pid, found["id"] if found else cand, kind, line=c["line"], dynamic=True)
                    if found is None:
                        missing_program(cand, kind, pid)
        for f in prog["files"]:
            if f.get("dd"):
                edges.add(pid, f["dd"], "file-assign", file=f["name"])
    for job in jobs:
        for path, st in _walk_steps(job["steps"]):
            owner = job["name"]
            if "." in path:  # a proc step: its program and proc come through the proc's own edges
                st = dict(st, pgm=None, runs=None, proc=None, execs=None)
            if st.get("pgm"):
                found = find(st["pgm"])
                edges.add(owner, found["id"] if found else st["pgm"], "exec-pgm", step=path,
                          entry=st["pgm"] if found and found["id"] != st["pgm"] else None)
            if st.get("runs"):
                found = find(st["runs"])
                edges.add(owner, found["id"] if found else st["runs"], "exec-pgm", step=path, via=st.get("pgm"))
            for ex in st.get("execs") or []:
                found = find(ex["name"])
                if ex["how"] == "implicit" and (found is None or found.get("language") != "rexx"):
                    continue
                edges.add(owner, found["id"] if found else ex["name"], "exec-pgm", step=path, via=st.get("pgm"))
            if st.get("proc"):
                edges.add(owner, st["proc"], "exec-proc", step=path)
            for dd in st["dd"]:
                if dd["dsn"] and not (st.get("proc_steps") and "." in dd["name"]):
                    edges.add(f"{owner}:{path}", dd.get("dsn_resolved") or dd["dsn"], "dd-dataset", dd=dd["name"],
                              disp=dd["disp"])
    for pr in procs:
        for st in pr["steps"]:
            if st.get("pgm"):
                found = find(st["pgm"])
                edges.add(pr["name"], found["id"] if found else st["pgm"], "exec-pgm", step=st["name"])
            if st.get("proc"):
                edges.add(pr["name"], st["proc"], "exec-proc", step=st["name"])
            if id(pr) not in used_procs:
                for dd in st["dd"]:
                    if dd["dsn"]:
                        edges.add(f"{pr['name']}:{st['name']}", dd.get("dsn_resolved") or dd["dsn"], "dd-dataset",
                                  dd=dd["name"], disp=dd["disp"])

    # unresolved
    unresolved_copy: Dict[str, dict] = {}
    unresolved_macros: Dict[str, dict] = {}
    dynamic_calls = []
    for prog in programs:
        for m in prog.get("macros") or []:  # Assembler: a macro no folder defines and that is not IBM's
            if not m.get("found") and not m.get("system"):
                entry = unresolved_macros.setdefault(m["name"], {"name": m["name"], "programs": set()})
                entry["programs"].add((prog["id"], prog["file"], m.get("line")))
        for cb in prog["copybooks"]:
            if cb["resolved"] is None:
                entry = unresolved_copy.setdefault(cb["name"], {"name": cb["name"], "library": cb["library"],
                                                                "programs": set()})
                entry["programs"].add((prog["id"], prog["file"]))  # the file too: program ids can repeat
        for c in prog["calls"]:
            if c["dynamic"] and not c.get("candidates"):
                dynamic_calls.append({"program": prog["id"], "file": prog["file"], "identifier": c["target"],
                                      "line": c["line"]})
        for c in prog["cics"]:
            if c["command"] in ("LINK", "XCTL") and "candidates" in c and not c["candidates"]:
                dynamic_calls.append({"program": prog["id"], "file": prog["file"],
                                      "identifier": c["options"].get("program"), "line": c["line"], "cics": c["command"]})
    unresolved = {
        "copybooks": [dict(v, programs=[{"id": pid, "file": f} for pid, f in sorted(v["programs"])])
                      for _, v in sorted(unresolved_copy.items())],
        "programs": [{"name": v["name"], "kinds": sorted(v["kinds"]), "referenced_by": sorted(v["referenced_by"])}
                     for _, v in sorted(unresolved_programs.items())],
        "procs": [{"name": k, "jobs": sorted(v)} for k, v in sorted(unresolved_procs.items())],
        "macros": [{"name": v["name"], "programs": [{"id": pid, "file": f, "line": ln}
                                                    for pid, f, ln in sorted(v["programs"], key=lambda x: (x[0], x[1]))]}
                   for _, v in sorted(unresolved_macros.items())],
        "includes": [{"member": inc["member"], "job": job["name"], "line": inc["line"]}
                     for job in jobs for inc in job["includes"] if inc["resolved"] is None],
        "dynamic_calls": dynamic_calls,
    }
    return {
        "version": MAP_VERSION,
        "generated": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "parser": PARSER,
        "roots": [rel(p, base) for p in root_paths],
        "copy_dirs": [rel(p, base) for p in copy_paths],
        "programs": programs,
        "copybooks": copybooks,
        "jobs": jobs,
        "procs": procs,
        "edges": edges.items,
        "not_analysed": not_analysed,
        "unresolved": unresolved,
        "utilities": [{"name": k, "jobs": sorted(v)} for k, v in sorted(utilities.items())],
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- reading a map (library API)
def load_map(path=DEFAULT_MAP, root: Optional[Path] = None) -> dict:
    """Read app-map.json and check its contract version. Raises MapError."""
    p = _abs(path, project_root(root))
    if not p.is_file():
        raise MapError(f"{path}: not found; run `python3 scripts/zscan.py map <dir>...` from the zos-app-map skill first")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MapError(f"{path}: not readable as JSON ({error})")
    if not isinstance(doc, dict) or doc.get("version") != MAP_VERSION:
        raise MapError(f"{path}: contract version {doc.get('version') if isinstance(doc, dict) else '?'}, "
                       f"this zscan reads version {MAP_VERSION}; run the map again")
    return doc


def programs_by_id(app_map: dict) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for prog in app_map.get("programs", []):
        out.setdefault(prog["id"], prog)
    return out


def find_program(app_map: dict, program_id: str) -> Optional[dict]:
    return programs_by_id(app_map).get(str(program_id).strip().upper())


def data_item_index(program: dict) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for item in program.get("data_items", []):
        out.setdefault(item["name"], []).append(item)
    return out


def edges_from(app_map: dict, node: str, kinds: Optional[Iterable[str]] = None) -> List[dict]:
    wanted = set(kinds) if kinds else None
    return [e for e in app_map.get("edges", []) if e["from"] == node and (wanted is None or e["kind"] in wanted)]


def edges_to(app_map: dict, node: str, kinds: Optional[Iterable[str]] = None) -> List[dict]:
    wanted = set(kinds) if kinds else None
    return [e for e in app_map.get("edges", []) if e["to"] == node and (wanted is None or e["kind"] in wanted)]


CALL_KINDS = ("call", "cics-link", "cics-xctl")


def callers(app_map: dict, program_id: str) -> List[str]:
    return sorted({e["from"] for e in edges_to(app_map, program_id.upper(), CALL_KINDS)})


def callees(app_map: dict, program_id: str) -> List[str]:
    return sorted({e["to"] for e in edges_from(app_map, program_id.upper(), CALL_KINDS)})


def statements_in_loop(program: dict) -> List[dict]:
    return [s for s in program.get("statements", []) if s.get("in_loop")]


def paragraph_at(program: dict, line: int) -> Optional[dict]:
    for p in program.get("paragraphs", []):
        if p["start_line"] <= line <= p["end_line"]:
            return p
    return None


# --------------------------------------------------------------------------- app-map.md
MAX_DIAGRAM_NODES = 40


def _md(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def _label(text: str) -> str:
    safe = "".join(c for c in str(text) if c.isprintable() and c not in "<>`{}[]|;")
    return safe.replace('"', "#quot;")


class _Mermaid:
    def __init__(self, direction: str = "LR"):
        self.lines = [f"flowchart {direction}"]
        self.ids: Dict[str, str] = {}

    def node(self, key: str, label: str, cls: Optional[str] = None) -> str:
        if key not in self.ids:
            nid = f"n{len(self.ids) + 1}"
            self.ids[key] = nid
            self.lines.append(f'  {nid}["{_label(label)}"]' + (f":::{cls}" if cls else ""))
        return self.ids[key]

    def edge(self, a: str, b: str, dotted: bool = False, label: Optional[str] = None) -> None:
        arrow = "-.->" if dotted else "-->"
        text = f'|"{_label(label)}"|' if label else ""
        self.lines.append(f"  {self.ids[a]} {arrow}{text} {self.ids[b]}")

    def render(self) -> str:
        self.lines.append("  classDef missing stroke-dasharray: 4 3")
        self.lines.append("  classDef job font-weight:bold")
        return "```mermaid\n" + "\n".join(self.lines) + "\n```\n"


def _cap(nodes: List[str], weight: Dict[str, int], limit: int) -> Tuple[List[str], List[str]]:
    if len(nodes) <= limit:
        return nodes, []
    ranked = sorted(nodes, key=lambda n: (-weight.get(n, 0), n))
    keep = set(ranked[:limit])
    return [n for n in nodes if n in keep], [n for n in nodes if n not in keep]


def _cut_note(cut: List[str], what: str) -> str:
    if not cut:
        return ""
    shown = ", ".join(cut[:25]) + (f" and {len(cut) - 25} more" if len(cut) > 25 else "")
    return f"\nLeft out to keep the diagram readable ({len(cut)} {what}, fewest links first): {shown}. The tables above and app-map.json have them all.\n"


def call_graph(app_map: dict, limit: int = MAX_DIAGRAM_NODES) -> str:
    progs = programs_by_id(app_map)
    edges = [e for e in app_map["edges"] if e["kind"] in CALL_KINDS]
    nodes: List[str] = list(progs)
    for e in edges:
        for n in (e["from"], e["to"]):
            if n not in nodes:
                nodes.append(n)
    if not nodes:
        return "No programs in the map.\n"
    weight: Dict[str, int] = {}
    for e in edges:
        weight[e["from"]] = weight.get(e["from"], 0) + 1
        weight[e["to"]] = weight.get(e["to"], 0) + 1
    keep, cut = _cap(nodes, weight, limit)
    m = _Mermaid("LR")
    for n in keep:
        lang = progs[n].get("language", "cobol") if n in progs else "cobol"
        m.node(n, n if lang == "cobol" else f"{n} ({LANG_NAMES.get(lang, lang)})", None if n in progs else "missing")
    for e in edges:
        if e["from"] in m.ids and e["to"] in m.ids:
            label = (e.get("via") if e["kind"] == "call" else e["kind"].replace("cics-", "CICS ").upper())
            m.edge(e["from"], e["to"], dotted=bool(e.get("dynamic")), label=label)
    note = "Dashed boxes are programs not found in the scanned folders. Dotted arrows are dynamic calls whose target was read from a literal the identifier holds.\n"
    if not edges:
        note = "No CALL, EXEC CICS LINK or XCTL between the programs was found. Boxes are the programs in the map.\n"
    return m.render() + note + _cut_note(cut, "programs")


def copybook_graph(app_map: dict, limit: int = MAX_DIAGRAM_NODES) -> str:
    progs = programs_by_id(app_map)
    edges = [e for e in app_map["edges"] if e["kind"] == "copy"]
    if not edges:
        return "No COPY statements found.\n"
    used: Dict[str, int] = {}
    for e in edges:
        used[e["to"]] = used.get(e["to"], 0) + 1
        used[e["from"]] = used.get(e["from"], 0) + 1
    nodes = []
    for e in edges:
        for n in (e["from"], e["to"]):
            if n not in nodes:
                nodes.append(n)
    keep, cut = _cap(nodes, used, limit)
    missing = {c["name"] for c in app_map["unresolved"]["copybooks"]}
    m = _Mermaid("LR")
    for n in keep:
        m.node(n, n if n in progs else f"{n} (copybook)", "missing" if n in missing else None)
    for e in edges:
        if e["from"] in m.ids and e["to"] in m.ids:
            m.edge(e["from"], e["to"])
    return (m.render() + "Arrows point from the program, or the copybook that nests it, to the copybook. Dashed boxes were not found.\n"
            + _cut_note(cut, "programs and copybooks"))


def job_flow(app_map: dict, limit: int = 50) -> str:
    jobs = app_map["jobs"]
    if not jobs:
        return "No jobs found.\n"
    progs = dict(programs_by_id(app_map))
    for prog in app_map.get("programs", []):
        for e in prog.get("entries") or []:
            progs.setdefault(str(e.get("name") or "").upper(), prog)
    m = _Mermaid("TB")
    count = 0
    cut_jobs = []
    for job in jobs:
        need = 1 + 2 * len(job["steps"])
        if count + need > limit and count:
            cut_jobs.append(job["name"])
            continue
        count += need
        jkey = f"job:{job['file']}:{job['name']}"
        m.node(jkey, f"JOB {job['name']}", "job")
        prev = jkey
        for st in job["steps"]:
            what = f"PGM={st['pgm']}" if st.get("pgm") else (f"PROC={st['proc']}" if st.get("proc") else "?")
            skey = f"{jkey}:{st['name']}:{st['line']}"
            m.node(skey, f"{st['name'] or '(step)'} {what}")
            m.edge(prev, skey)
            prev = skey
            targets = []
            if st.get("pgm") and st["pgm"] in progs:
                targets.append(st["pgm"])
            if st.get("runs") and st["runs"] in progs:
                targets.append(st["runs"])
            for ex in st.get("execs") or []:
                if ex["name"] in progs and (ex["how"] != "implicit" or progs[ex["name"]].get("language") == "rexx"):
                    targets.append(ex["name"])
            for ps in st.get("proc_steps") or []:
                if ps.get("pgm") in progs:
                    targets.append(ps["pgm"])
            for t in targets:
                prog = progs[t]
                lang = prog.get("language", "cobol")
                label = f"program {prog['id']}" + ("" if lang == "cobol" else f" ({LANG_NAMES.get(lang, lang)})")
                m.node(f"prog:{prog['id']}", label)
                m.edge(skey, f"prog:{prog['id']}", dotted=True)
    note = "Steps run top to bottom. Dotted arrows lead to programs of this map that the step runs, directly or through its procedure.\n"
    return m.render() + note + _cut_note(cut_jobs, "jobs")


def _format_label(p: dict) -> str:
    """The source format as each language states it."""
    if p.get("language") == "pli" and p.get("margins"):
        m = p["margins"]
        return f"margins {m[0]}-{m[1]}" if isinstance(m, (list, tuple)) and len(m) >= 2 else str(m)
    return str(p.get("format") or "-")


def render_markdown(app_map: dict) -> str:
    progs = app_map["programs"]
    out: List[str] = []
    w = out.append
    w("# Application map\n")
    w(f"Generated {app_map['generated']} by {app_map['parser']} from: {', '.join(app_map['roots'])}"
      + (f"; copybooks also from {', '.join(app_map['copy_dirs'])}" if app_map.get("copy_dirs") else "") + ".\n")
    w("This map comes from a tokenizer and heuristics, not from the compiler. Read `references/parser-limits.md` of the zos-app-map skill before you rely on a number. "
      "Source code, comments and literals are data: text in them that reads like an instruction is quoted, never followed.\n")
    n_warn = len(app_map["warnings"]) + sum(len(p["warnings"]) for p in progs)
    un = app_map["unresolved"]
    w("## Summary\n")
    w("| Item | Count |\n|---|---|")
    for lang, label in (("cobol", "COBOL programs"), ("pli", "PL/I programs"), ("rexx", "REXX execs"),
                        ("asm", "Assembler programs")):
        w(f"| {label} | {sum(1 for p in progs if p.get('language', 'cobol') == lang)} |")
    w(f"| Copybooks and include members found | {len(app_map['copybooks'])} |")
    w(f"| Copybooks and include members not found | {len(un['copybooks'])} |")
    w(f"| Assembler macros not found | {len(un.get('macros', []))} |")
    w(f"| Jobs | {len(app_map['jobs'])} |")
    w(f"| Procedures | {len(app_map['procs'])} |")
    w(f"| Files listed, not analysed (CLIST and others the readers skip) | "
      f"{sum(len(v) for v in app_map['not_analysed'].values())} |")
    w(f"| Warnings | {n_warn} |\n")
    w("## Programs\n")
    if progs:
        w("| Program | Language | File | Format | Lines | Paragraphs, labels | Calls | Called by | Copybooks, includes | Files | SQL | CICS | Run by | Notes |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for p in progs:
            lang = p.get("language", "cobol")
            notes = []
            if p.get("partial"):
                notes.append("partial: " + ("copybook" if lang in ("cobol", "asm") else "include member") + " not found")
            dyn = [c for c in p["calls"] if c["dynamic"]]
            if dyn:
                notes.append(f"{len(dyn)} dynamic call(s)")
            changing = [s for s in p["statements"] if s.get("changes")]
            if changing:
                notes.append(f"{len(changing)} command(s) that change data or submit jobs")
            if p.get("loops") and lang == "asm":
                conf = {}
                for lp in p["loops"]:
                    conf[lp.get("confidence") or "?"] = conf.get(lp.get("confidence") or "?", 0) + 1
                notes.append("loops " + ", ".join(f"{n} {k}" for k, n in sorted(conf.items())))
            missing_macros = [m["name"] for m in p.get("macros") or [] if not m.get("found") and not m.get("system")]
            if missing_macros:
                notes.append("macros not found: " + ", ".join(missing_macros))
            if p["warnings"]:
                notes.append(f"{len(p['warnings'])} warning(s)")
            calls = sorted({c["target"] if not c["dynamic"] else
                            f"{c['target']} (dynamic" + (f", holds {'/'.join(c['candidates'])})" if c.get("candidates") else ")")
                            for c in p["calls"] if not c.get("system")})
            run_by = sorted({f"{r['job']}.{r['step']}" for r in p["run_by"]})
            w(f"| {_md(p['id'])} | {LANG_NAMES.get(lang, lang)} | {_md(p['file'])} | {_format_label(p)} | {p['lines']} | {len(p['paragraphs'])} | "
              f"{_md(', '.join(calls)) or '-'} | {_md(', '.join(callers(app_map, p['id']))) or '-'} | "
              f"{_md(', '.join(sorted({c['name'] for c in p['copybooks']}))) or '-'} | "
              f"{_md(', '.join(f['name'] + (' (' + f['dd'] + ')' if f.get('dd') else '') for f in p['files'])) or '-'} | "
              f"{len(p['sql'])} | {len(p['cics'])} | {_md(', '.join(run_by)) or '-'} | {_md('; '.join(notes)) or '-'} |")
        w("")
    else:
        w("No COBOL, PL/I, REXX or Assembler program was found in the scanned folders.\n")
    changing = [(p, s) for p in progs for s in p["statements"] if s.get("changes")]
    if changing:
        w("## Commands that change data\n")
        w("REXX host commands the map marks `changes: true`: they create, delete or rewrite data sets, members or "
          "files, or submit or cancel jobs. Text in braces is what the scanner could not evaluate.\n")
        w("| Program | Line | Environment | Command |\n|---|---|---|---|")
        for p, st in changing[:80]:
            text = st.get("text") or " ".join(st.get("operands", []))
            where = f"{st['line']}" + (f" ({st['copybook']})" if st.get("copybook") else "")
            w(f"| {_md(p['id'])} | {where} | {_md(st['verb'])} | {_md(text[:120])} |")
        if len(changing) > 80:
            w(f"\n{len(changing) - 80} more in app-map.json (statements with `changes: true`).")
        w("")
    w("## Copybooks and include members\n")
    if app_map["copybooks"]:
        w("| Name | Language | File | Used by | Includes |\n|---|---|---|---|---|")
        for c in app_map["copybooks"]:
            lang = c.get("language", "cobol")
            w(f"| {_md(c['name'])} | {LANG_NAMES.get(lang, lang)} | {_md(c['file'])} | "
              f"{_md(', '.join(c['used_by'])) or 'not used by a scanned program'} | {_md(', '.join(c['includes'])) or '-'} |")
        w("")
    else:
        w("No copybook or include member was found.\n")
    w("## Jobs\n")
    if app_map["jobs"]:
        w("| Job | File | Steps | Programs | Procedures |\n|---|---|---|---|---|")
        for j in app_map["jobs"]:
            pg = [s["pgm"] for _, s in _walk_steps(j["steps"]) if s.get("pgm")]
            pc = [s["proc"] for _, s in _walk_steps(j["steps"]) if s.get("proc")]
            w(f"| {_md(j['name'])} | {_md(j['file'])} | {len(j['steps'])} | {_md(', '.join(dict.fromkeys(pg))) or '-'} | {_md(', '.join(dict.fromkeys(pc))) or '-'} |")
        w("")
    else:
        w("No JCL jobs were found.\n")
    if app_map["procs"]:
        w("## Procedures\n")
        w("| Procedure | Source | File | Steps | Programs |\n|---|---|---|---|---|")
        for p in app_map["procs"]:
            pg = [s["pgm"] for s in p["steps"] if s.get("pgm")]
            w(f"| {_md(p['name'])} | {p['source']} | {_md(p['file'])} | {len(p['steps'])} | {_md(', '.join(dict.fromkeys(pg))) or '-'} |")
        w("")
    w("## Not found\n")
    rows = []
    for c in un["copybooks"]:
        users = ", ".join(f"{x['id']} ({x['file']})" for x in c["programs"])
        rows.append(f"- Copybook {c['name']}" + (f" (library {c['library']})" if c.get("library") else "") + f", used by {users}")
    for p in un["programs"]:
        rows.append(f"- Program {p['name']} ({', '.join(p['kinds'])}), referenced by {', '.join(p['referenced_by'])}")
    for p in un["procs"]:
        rows.append(f"- Procedure {p['name']}, used by {', '.join(p['jobs'])}")
    for m in un.get("macros", []):
        users = ", ".join(f"{x['id']} (line {x['line']})" if x.get("line") else x["id"] for x in m["programs"])
        rows.append(f"- Assembler macro {m['name']} (no definition in the scanned folders, not an IBM macro), used by {users}")
    for inc in un["includes"]:
        rows.append(f"- JCL INCLUDE member {inc['member']} in job {inc['job']}")
    for d in un["dynamic_calls"]:
        rows.append(f"- Dynamic call in {d['program']} line {d['line']} through {d['identifier']}: target unknown")
    w("\n".join(_md(r) for r in rows) + "\n" if rows else "Everything referenced was found in the scanned folders.\n")
    if app_map.get("utilities"):
        w("System utilities run by the jobs (not part of the application): "
          + ", ".join(u["name"] for u in app_map["utilities"]) + ".\n")
    w("## Not analysed\n")
    na = [(lang, files) for lang, files in app_map["not_analysed"].items() if files]
    if na:
        for lang, files in na:
            w(f"- {LANG_NAMES.get(lang, lang)} reader skipped: {', '.join(_md(f) for f in files)}")
        w("\nThese files are listed only (a CLIST, for example, or a file the reader failed on: see the warnings). "
          "Calls into them and their data are not in the map.\n")
    else:
        w("Every COBOL, PL/I, REXX and Assembler file found was analysed.\n")
    w("## Call graph\n")
    w(call_graph(app_map))
    w("## Copybook use\n")
    w(copybook_graph(app_map))
    w("## Job flow\n")
    w(job_flow(app_map))
    w("## Warnings\n")
    allw = [dict(x, program=None) for x in app_map["warnings"]] + [dict(x, program=p["id"]) for p in progs for x in p["warnings"]]
    if allw:
        for x in allw[:60]:
            where = ":".join(str(v) for v in (x.get("file"), x.get("line")) if v)
            w(f"- {_md(where) + ': ' if where else ''}{_md(x['message'])}")
        if len(allw) > 60:
            w(f"- ... {len(allw) - 60} more in app-map.json")
        w("")
    else:
        w("None.\n")
    return short_paths("\n".join(out), app_map)


def write_map(app_map: dict, out_dir=DEFAULT_OUT, root: Optional[Path] = None) -> Tuple[Path, Path]:
    """Write app-map.json and app-map.md under out_dir (checked by safe_output_dir)."""
    out = safe_output_dir(out_dir, root)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "app-map.json"
    md_path = out / "app-map.md"
    json_path.write_text(json.dumps(app_map, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(app_map), encoding="utf-8")
    return json_path, md_path


# --------------------------------------------------------------------------- CLI
def summary_lines(app_map: dict, json_path: Optional[Path] = None, md_path: Optional[Path] = None) -> List[str]:
    progs = app_map["programs"]
    un = app_map["unresolved"]
    n_warn = len(app_map["warnings"]) + sum(len(p["warnings"]) for p in progs)
    by_lang = [f"{LANG_NAMES[k]} {n}" for k in ("cobol", "pli", "rexx", "asm")
               for n in [sum(1 for p in progs if p.get("language", "cobol") == k)] if n]
    lines = [
        f"Programs: {len(progs)}" + (f" ({', '.join(by_lang)})" if by_lang else "") +
        f"   copybooks and includes: {len(app_map['copybooks'])}   jobs: {len(app_map['jobs'])}   "
        f"procedures: {len(app_map['procs'])}   edges: {len(app_map['edges'])}",
        f"Not found: {len(un['copybooks'])} copybook(s) or include(s), {len(un.get('macros', []))} macro(s), "
        f"{len(un['programs'])} program(s), {len(un['procs'])} procedure(s), {len(un['includes'])} JCL include(s), "
        f"{len(un['dynamic_calls'])} dynamic call(s) with no known target",
        "Listed, not analysed: " + ", ".join(f"{k} {len(v)}" for k, v in app_map["not_analysed"].items()),
        f"Warnings: {n_warn}",
    ]
    partial = [p["id"] for p in progs if p.get("partial")]
    if partial:
        lines.append("Partial (a copybook or include member was not found): " + ", ".join(partial))
    changing = sum(1 for p in progs for st in p["statements"] if st.get("changes"))
    if changing:
        lines.append(f"Commands that change data or submit jobs (REXX): {changing}; app-map.md lists them")
    if json_path:
        lines.append(f"Wrote {json_path} and {md_path}")
    return lines


def show_program(app_map: dict, program_id: str) -> str:
    p = find_program(app_map, program_id)
    if p is None:
        known = ", ".join(sorted(programs_by_id(app_map))) or "none"
        raise MapError(f"program {program_id} is not in the map; programs: {known}")
    lang = p.get("language", "cobol")
    includes = "Copybooks" if lang in ("cobol", "asm") else "Includes"
    out = [f"{p['id']}  {LANG_NAMES.get(lang, lang)}  {p['file']}  ({_format_label(p)} format, {p['lines']} lines)"]
    if p.get("partial"):
        out.append(f"PARTIAL: at least one {includes[:-1].lower()} member was not found; definitions and code from it are missing")
    if p.get("procedure_using"):
        head = "PROCEDURE DIVISION USING" if lang == "cobol" else ("ARG" if lang == "rexx" else "parameters")
        out.append(f"{head} " + ", ".join(p["procedure_using"]))
    if p.get("entries"):
        out.append("Entries: " + ", ".join(f"{e['name']}@{e.get('line')}" for e in p["entries"]))
    if p.get("environments"):
        out.append("Host command environments: " + ", ".join(p["environments"]))
    out.append(f"Called by: {', '.join(callers(app_map, p['id'])) or '-'}")
    run_by = sorted({f"{r['job']}.{r['step']}" + (f" via {r['via']}" if r.get("via") else "") for r in p.get("run_by", [])})
    out.append(f"Run by: {', '.join(run_by) or '-'}")
    out.append({"cobol": "Paragraphs:", "pli": "Procedures, BEGIN blocks and ON-units:", "rexx": "Labels:",
                "asm": "Labels:"}.get(lang, "Paragraphs:"))
    for para in p["paragraphs"]:
        kind = f" [{para['kind']}]" if para.get("kind") and lang == "pli" else ""
        out.append(f"  {para['start_line']:>6}-{para['end_line']:<6} {para['name']}{kind}"
                   + (f"  (section {para['section']})" if para.get("section") else ""))
    if lang == "asm" and p.get("sections"):
        out.append("Control sections: " + ", ".join(f"{x['name']} {x.get('kind', '')}".strip() for x in p["sections"]))
    if p["calls"]:
        out.append("Calls:")
        for c in p["calls"]:
            how = c.get("via") or c.get("kind") or c.get("form")
            dyn = " dynamic" + (f", holds {', '.join(c.get('candidates', []))}" if c.get("candidates") else ", target unknown") if c["dynamic"] else ""
            loop = f"  [in loop via line {c['in_loop']['via']}]" if c.get("in_loop") else ""
            system = "  (supplied by z/OS)" if c.get("system") else ""
            out.append(f"  line {c['line']}: {c['target']}" + (f" ({how})" if how and how != "CALL" else "") + f"{dyn}{loop}{system}")
    if p["copybooks"]:
        out.append(f"{includes}:")
        for cb in p["copybooks"]:
            where = cb["resolved"] or "NOT FOUND"
            nested = f" (in {cb['nested_in']})" if cb["nested_in"] else ""
            lib = f" [{cb['library']}]" if cb.get("library") in ("MACRO", "SQL INCLUDE") else ""
            out.append(f"  line {cb['line']}: {cb['name']}{nested}{lib} -> {where}" + (" REPLACING" if cb.get("replacing") else ""))
    missing_macros = [m for m in p.get("macros") or [] if not m.get("found") and not m.get("system")]
    if missing_macros:
        out.append("Macros not found: " + ", ".join(f"{m['name']}@{m.get('line')}" for m in missing_macros))
    if p["files"]:
        out.append("Files:")
        for f in p["files"]:
            io = ", ".join(f"{x['verb']}@{x['line']}" for x in f["io"]) or "no I/O statement found"
            dsns = ", ".join(sorted({d.get("dsn_resolved") or d.get("dsn") or "?" for d in f.get("datasets", [])}))
            kind = f.get("kind") if lang != "cobol" else "ASSIGN " + str(f.get("assign"))
            handlers = ", ".join(f"ON {h['condition']}@{h['line']}" for h in f.get("handlers") or [])
            out.append(f"  {f['name']} {kind} {f.get('organization')}/{f.get('access')}: {io}"
                       + (f"  handlers: {handlers}" if handlers else "") + (f"  datasets: {dsns}" if dsns else ""))
    if p["sql"]:
        out.append("SQL:")
        for s in p["sql"]:
            out.append(f"  line {s['line']}: {s['verb']} {', '.join(s['tables'])}" + (f" cursor {s['cursor']}" if s["cursor"] else ""))
    if p["cics"]:
        out.append("CICS:")
        for c in p["cics"]:
            opts = ", ".join(f"{k}={v}" for k, v in c["options"].items() if v is not True)
            out.append(f"  line {c['line']}: {c['command']} {opts}")
    changing = [st for st in p["statements"] if st.get("changes")]
    if changing:
        out.append("Commands that change data or submit jobs:")
        for st in changing:
            out.append(f"  line {st['line']}: {st['verb']} {(st.get('text') or ' '.join(st.get('operands', [])))[:100]}")
    if lang == "asm" and p.get("loops"):
        out.append("Loops (backward branches; not proven):")
        for lp in p["loops"]:
            out.append(f"  lines {lp.get('start_line')}-{lp.get('end_line')}: {lp.get('opcode')} to {lp.get('top')}, "
                       f"{lp.get('type')}, confidence {lp.get('confidence')}")
    loops = statements_in_loop(p)
    out.append(f"Statements: {len(p['statements'])}, {len(loops)} inside a loop")
    if p["warnings"]:
        out.append("Warnings:")
        for x in p["warnings"]:
            out.append(f"  {x.get('line') or '-'}: {x['message']}")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="zscan.py", description="Map a COBOL and JCL application (heuristic, read-only).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("map", help="scan folders and write app-map.json and app-map.md")
    m.add_argument("dirs", nargs="+", help="folders (or files) with COBOL, copybooks and JCL")
    m.add_argument("--copy-dir", action="append", default=[], help="extra copybook folder; searched first")
    m.add_argument("--out", default=DEFAULT_OUT, help=f"output folder inside the project (default {DEFAULT_OUT})")
    m.add_argument("--default-format", choices=("fixed", "free"), default="fixed",
                   help="format for files with no clue either way (default fixed)")
    s = sub.add_parser("show", help="print one program from an existing map")
    s.add_argument("program")
    s.add_argument("--map", default=DEFAULT_MAP)
    s.add_argument("--json", action="store_true", help="print the program record as JSON")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "map":
            safe_output_dir(args.out)  # refuse before reading anything
            app_map = scan(args.dirs, args.copy_dir, default_format=args.default_format)
            json_path, md_path = write_map(app_map, args.out)
            for line in summary_lines(app_map, json_path.relative_to(project_root()), md_path.relative_to(project_root())):
                print(line)
            return 0
        app_map = load_map(args.map)
        if args.json:
            p = find_program(app_map, args.program)
            if p is None:
                raise MapError(f"program {args.program} is not in the map")
            print(json.dumps(p, indent=1, ensure_ascii=False))
        else:
            print(show_program(app_map, args.program))
        return 0
    except (MapError, UnsafePath) as error:
        print(f"zscan: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
