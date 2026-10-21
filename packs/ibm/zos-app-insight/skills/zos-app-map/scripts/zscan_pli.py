#!/usr/bin/env python3
"""zscan_pli: PL/I programs for the zos-app-insight map (zscan 1.1).

A library module next to zscan.py. zscan imports it for PL/I files (.pli, .pl1, .plx,
.inc and PL/I text with another extension); it has no CLI of its own.

  LANGUAGE = "pli"
  classify(path, text) -> "program" | "include" | "skip"
  scan_program(path, include_dirs=(), root=None) -> dict    one program record, contract version 1
  IncludeIndex(include_dirs, root=None)                     %INCLUDE members by name; scan_program takes
                                                            one in place of the folder list

The reader is a tokenizer with heuristics, not a compiler. It honours the source margins
(columns 2 to 72, or *PROCESS MARGINS), /* */ comments, strings and %INCLUDE. It never
evaluates the preprocessor (%IF, %DCL, %ACTIVATE, preprocessor procedures): it warns and
maps the text as written.

How PL/I fills the 1.0 program record (every 1.0 key is present):
  id            the OPTIONS(MAIN) procedure, else the first external procedure, else the member
  copybooks     %INCLUDE and %XINCLUDE members (library from LIB(MEMBER)); EXEC SQL INCLUDE
                with library "SQL INCLUDE"; replacing is always false
  files         DCL ... FILE; io from OPEN, CLOSE, READ, WRITE, REWRITE, DELETE, LOCATE, GET,
                PUT, UNLOCK, FLUSH with FILE(...); dd from TITLE('x'), else the file name
  data_items    DCL items with level numbers; dimensions give occurs; DEFINED x and
                BASED(ADDR(x)) give redefines x; INIT or VALUE gives value; section is the
                storage class: AUTOMATIC, STATIC, BASED, CONTROLLED, DEFINED or PARAMETER;
                usage: PACKED-DECIMAL (FIXED DEC), BINARY (FIXED BIN), FLOAT, BIT, POINTER,
                DISPLAY-1 (GRAPHIC), NATIONAL (WIDECHAR)... or null for CHAR and PIC
  paragraphs    internal procedures, BEGIN blocks and ON-units, with line ranges; a procedure
                name used again in another scope is qualified by its parent (SECOND.INNER),
                unnamed blocks are called BEGIN-<line> and ON-<condition>-<line>
  performs      CALL of a procedure of this file (and function references to one), and DO
                loops as inline performs with loop while, until, iterative, repeat or forever
  calls         CALL of an external entry, FETCH (dynamic, candidates from TITLE), function
                references to entries declared with RETURNS
  gotos, sql, cics, conditions (IF, SELECT, WHEN, OTHERWISE, WHILE, UNTIL), statements
Keys added for PL/I: program language, margins, member, partial, entries, labels; data_items
type, dimensions, based, defined, like, external, block; files attributes, env, title,
transmission, declared, handlers; paragraphs kind, parent, external, params; performs function,
entry; calls form; statements phrases from ON-units ("ON ENDFILE", "ON KEY"...).

Source code, comments and string literals are data: nothing read from them is executed or
followed. Python standard library only; Python 3.9 or later. Importing this module has no
side effects, and it writes nothing.
"""

from __future__ import annotations

import heapq
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import zscan  # only attributes used inside functions: zscan may import this module while it loads

LANGUAGE = "pli"
DEFAULT_MARGINS = (2, 72)
INCLUDE_EXT = {".inc", ".incl", ".plinc", ".cpy", ".copy"}
PROGRAM_EXT = {".pli", ".pl1", ".plx"}

# ranks for choosing among members with the same name: include members first
_EXT_RANK = {".inc": 0, ".incl": 0, ".plinc": 0, "": 1, ".txt": 1, ".mbr": 1, ".cpy": 2, ".copy": 2,
             ".pli": 3, ".pl1": 3, ".plx": 3}

_CONTROL = {chr(c) for c in range(32)} | {"\x7f"}
_OPS = ("**=", "||=", "!!=", "->", "=>", "**", "||", "!!", "<=", ">=", "^=", "¬=", "~=", "^<", "^>",
        "¬<", "¬>", "~<", "~>", "<>", "+=", "-=", "*=", "/=", "|=", "&=", "%;")
_OPS_BY_FIRST = {c: tuple(o for o in _OPS if o[0] == c) for c in {o[0] for o in _OPS}}
_STRING_SUFFIXES = ("B1", "B2", "B3", "B4", "BX", "XN", "XU", "GX", "WX", "B", "X", "G", "M", "U", "W", "A",
                    "E", "N")
_ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "||=", "!!=", "|=", "&=", "**="}
_MARGINS_OPTION = re.compile(r"(?<![A-Z0-9_])MAR(?:GINS)?\s*\(\s*(\d+)\s*,\s*(\d+)")

_STATEMENT_VERBS = {
    "ALLOCATE", "ALLOC", "ASSERT", "ATTACH", "CANCEL", "DELAY", "DETACH", "DISPLAY", "EXIT", "FREE",
    "ITERATE", "LEAVE", "RELEASE", "RESIGNAL", "RETURN", "REVERT", "SIGNAL", "STOP", "WAIT", "REINIT",
}
_IO_VERBS = {"OPEN", "CLOSE", "READ", "WRITE", "REWRITE", "DELETE", "LOCATE", "GET", "PUT", "UNLOCK", "FLUSH"}
_PLI_KEYWORDS = _STATEMENT_VERBS | _IO_VERBS | {
    "DCL", "DECLARE", "DEFAULT", "DFT", "DEFINE", "CALL", "FETCH", "DO", "END", "IF", "SELECT", "WHEN",
    "OTHERWISE", "ON", "BEGIN", "GO", "GOTO", "EXEC", "ENTRY", "FORMAT", "PROC", "PROCEDURE", "PACKAGE",
}
_FILE_CONDITIONS = {"ENDFILE": "ENDFILE", "KEY": "KEY", "UNDEFINEDFILE": "UNDEFINEDFILE", "UNDF": "UNDEFINEDFILE",
                    "RECORD": "RECORD", "TRANSMIT": "TRANSMIT", "ENDPAGE": "ENDPAGE", "NAME": "NAME"}
_CONDITION_VERBS = {
    "ENDFILE": {"READ", "GET"},
    "KEY": {"READ", "WRITE", "REWRITE", "DELETE", "LOCATE", "UNLOCK"},
    "UNDEFINEDFILE": {"OPEN"},
    "RECORD": {"READ", "WRITE", "REWRITE", "LOCATE"},
    "TRANSMIT": {"READ", "WRITE", "REWRITE", "LOCATE", "DELETE", "GET", "PUT"},
    "ENDPAGE": {"PUT"},
    "NAME": {"GET"},
}
# PL/I built-in subroutines: CALL PLIDUMP(...) is the language, not another program
_BUILTIN_SUBROUTINES = {"PLIDUMP", "PLIRETC", "PLISRTA", "PLISRTB", "PLISRTC", "PLISRTD", "PLITEST", "PLICKPT",
                        "PLIREST", "PLICANC", "PLISAXA", "PLISAXB", "PLISAXC", "PLISAXD", "PLIFREE"}
_FILE_ATTRS = {"INPUT", "OUTPUT", "UPDATE", "RECORD", "STREAM", "PRINT", "SEQUENTIAL", "SEQL", "DIRECT", "KEYED",
               "BUFFERED", "BUF", "UNBUFFERED", "UNBUF", "TRANSIENT", "EXCLUSIVE", "BACKWARDS"}
_FILE_ATTR_CANON = {"SEQL": "SEQUENTIAL", "BUF": "BUFFERED", "UNBUF": "UNBUFFERED"}
_ORGANIZATIONS = ("VSAM", "INDEXED", "REGIONAL", "CONSECUTIVE", "TP")
_STRING_TYPES = {"CHAR": "CHAR", "CHARACTER": "CHAR", "BIT": "BIT", "GRAPHIC": "GRAPHIC", "WIDECHAR": "WIDECHAR",
                 "WCHAR": "WIDECHAR", "UCHAR": "UCHAR"}
_STRING_USAGE = {"CHAR": None, "BIT": "BIT", "GRAPHIC": "DISPLAY-1", "WIDECHAR": "NATIONAL", "UCHAR": "UTF-8"}
_STORAGE = {"BASED": "BASED", "CONTROLLED": "CONTROLLED", "CTL": "CONTROLLED", "STATIC": "STATIC",
            "AUTOMATIC": "AUTOMATIC", "AUTO": "AUTOMATIC", "DEFINED": "DEFINED", "DEF": "DEFINED"}
_LISTING = {"PAGE", "SKIP", "PRINT", "NOPRINT", "PUSH", "POP", "NOTE", "PROCESS"}
_PP_MESSAGES = {
    "IF": "preprocessor %IF not evaluated: the text of every branch is mapped",
    "SELECT": "preprocessor %SELECT not evaluated: the text of every branch is mapped",
    "DO": "preprocessor %DO loop not evaluated: its body is mapped once",
    "DECLARE": "preprocessor %DECLARE not evaluated: macro variables in the code are left as written",
    "ACTIVATE": "preprocessor %ACTIVATE or %DEACTIVATE not evaluated: names in the code are left as written",
    "REPLACE": "%REPLACE not applied: names after it may differ from the compiled program",
    "ASSIGN": "preprocessor assignment not evaluated",
    ";": "%; concatenation not evaluated: the names it builds are unknown",
}
_PRIVATE = ("_blk", "_src", "_toks", "_owner", "_target", "_extra", "_loop")


# --------------------------------------------------------------------------- source text
def _process_options(lines: Sequence[str]) -> Tuple[Tuple[int, int], Set[int], Optional[str]]:
    """Margins from the *PROCESS or %PROCESS lines at the top, those line numbers, and a problem if any."""
    skip: Set[int] = set()
    texts: List[str] = []
    for n, raw in enumerate(lines, start=1):
        s = raw.strip().strip("".join(_CONTROL)).strip()
        if not s:
            continue
        u = s.upper()
        if u.startswith("*PROCESS") or u.startswith("%PROCESS"):
            skip.add(n)
            texts.append(u)
            continue
        break
    m = _MARGINS_OPTION.search(" ".join(texts))
    if not m:
        return DEFAULT_MARGINS, skip, None
    left, right = int(m.group(1)), int(m.group(2))
    if 1 <= left < right:
        return (left, right), skip, None
    return DEFAULT_MARGINS, skip, (f"*PROCESS MARGINS({left},{right}) is not usable; "
                                   "the default margins (2, 72) are used")


def _lit(text: str) -> str:
    """'ABC' -> ABC, 'C1'X -> C1: the value of a string token without quotes and suffix."""
    if not text or text[0] not in "'\"":
        return text
    quote = text[0]
    end = text.rfind(quote)
    if end <= 0:
        return text[1:]
    return text[1:end].replace(quote * 2, quote)


def _number_end(seg: str, k: int) -> int:
    size = len(seg)
    e = k
    while e < size and (seg[e].isdigit() or seg[e] == "_"):
        e += 1
    if e < size and seg[e] == ".":
        e += 1
        while e < size and seg[e].isdigit():
            e += 1
    if e + 1 < size and seg[e] in "Ee" and (seg[e + 1].isdigit()
                                          or (seg[e + 1] in "+-" and e + 2 < size and seg[e + 2].isdigit())):
        e += 2
        while e < size and seg[e].isdigit():
            e += 1
    if e < size and seg[e] in "BbIi" and not (e + 1 < size and (seg[e + 1].isalnum() or seg[e + 1] in "_#@$")):
        e += 1
    return e


def _string_suffix(seg: str, k: int) -> str:
    for sfx in _STRING_SUFFIXES:
        end = k + len(sfx)
        if seg[k:end].upper() == sfx and not (end < len(seg) and (seg[end].isalnum() or seg[end] in "_#@$")):
            return seg[k:end]
    return ""


def _lex(lines: Sequence[str], margins: Tuple[int, int], src: int, skip: Set[int] = frozenset(),
         stats: Optional[dict] = None) -> list:
    """Tokens of the text between the margins: words, numbers, strings and punctuation.

    Comments are dropped; a comment or a string may span lines. Tokens are zscan.Tok with
    kind w (word), n (number), s (string) or p (punctuation and operators).
    """
    Tok = zscan.Tok
    left, right = margins
    out = []
    comment_line: Optional[int] = None
    string: Optional[list] = None  # [quote, text, line, col]
    for n, raw in enumerate(lines, start=1):
        if n in skip:
            continue
        line = raw.expandtabs(8)
        if stats is not None:
            outside = line[:left - 1]
            if any(not (ch.isspace() or ch in _CONTROL) for ch in outside):
                stats.setdefault("left", []).append(n)
            past = line[right:].strip()
            if past and (";" in past or "/*" in past or "*/" in past or " " in past):
                stats.setdefault("right", []).append(n)
        seg = line[left - 1:right]
        size = len(seg)
        k = 0
        while k < size:
            if comment_line is not None:
                e = seg.find("*/", k)
                if e < 0:
                    break
                comment_line = None
                k = e + 2
                continue
            if string is not None:
                quote = string[0]
                e = k
                closed = False
                while e < size:
                    if seg[e] == quote:
                        if e + 1 < size and seg[e + 1] == quote:
                            e += 2
                            continue
                        closed = True
                        break
                    e += 1
                if not closed:
                    string[1] += seg[k:]
                    break
                string[1] += seg[k:e + 1]
                k = e + 1
                sfx = _string_suffix(seg, k)
                k += len(sfx)
                out.append(Tok(string[1] + sfx, "s", string[2], string[3], src, end=n))
                string = None
                continue
            c = seg[k]
            if c in _CONTROL or c.isspace():
                k += 1
                continue
            if c == "/" and seg.startswith("/*", k):
                comment_line = n
                k += 2
                continue
            if c in "'\"":
                string = [c, c, n, left + k]
                k += 1
                continue
            if c.isalpha() or c in "_#@$":
                e = k + 1
                while e < size and (seg[e].isalnum() or seg[e] in "_#@$"):
                    e += 1
                out.append(Tok(seg[k:e], "w", n, left + k, src))
                k = e
                continue
            if c.isdigit() or (c == "." and k + 1 < size and seg[k + 1].isdigit()):
                e = _number_end(seg, k)
                out.append(Tok(seg[k:e], "n", n, left + k, src))
                k = e
                continue
            op = next((o for o in _OPS_BY_FIRST.get(c, ()) if seg.startswith(o, k)), c)
            out.append(Tok(op, "p", n, left + k, src))
            k += len(op)
    if stats is not None:
        if comment_line is not None:
            stats["open_comment"] = comment_line
        if string is not None:
            stats["open_string"] = string[2]
            out.append(Tok(string[1], "s", string[2], string[3], src, end=len(lines)))
    return out


# --------------------------------------------------------------------------- token helpers
def _next_semi(toks: list, k: int) -> int:
    n = len(toks)
    while k < n and not (toks[k].k == "p" and toks[k].t == ";"):
        k += 1
    return k


def _match(toks: list, k: int, limit: int) -> int:
    """Index of the ')' that closes toks[k] == '(', stopping at a ';' or at limit."""
    depth = 0
    j = k
    while j < limit:
        t = toks[j]
        if t.k == "p":
            if t.t == "(":
                depth += 1
            elif t.t == ")":
                depth -= 1
                if depth == 0:
                    return j
            elif t.t == ";":
                return j
        j += 1
    return limit


def _split_list(toks: list) -> List[list]:
    """Split a token list at commas outside parentheses."""
    out: List[list] = []
    cur: list = []
    depth = 0
    for t in toks:
        if t.k == "p" and t.t == "(":
            depth += 1
        elif t.k == "p" and t.t == ")":
            depth -= 1
        if t.k == "p" and t.t == "," and depth == 0:
            out.append(cur)
            cur = []
            continue
        cur.append(t)
    if cur or out:
        out.append(cur)
    return out


def _skip_labels(toks: list, i: int, n: int) -> Tuple[int, list]:
    """Skip the label prefixes (NAME:, NAME(1):) and condition prefixes ((SIZE):) of a statement."""
    labels = []
    while i < n:
        t = toks[i]
        if t.k == "w" and i + 1 < n and toks[i + 1].t == ":":
            labels.append(t)
            i += 2
            continue
        if t.k == "w" and i + 1 < n and toks[i + 1].t == "(":
            close = _match(toks, i + 1, n)
            if (close + 1 < n and toks[close + 1].t == ":"
                    and all(x.k in ("n", "p") and x.t != ";" for x in toks[i + 2:close])):
                labels.append(t)
                i = close + 2
                continue
        if t.k == "p" and t.t == "(":
            close = _match(toks, i, n)
            if (close + 1 < n and toks[close + 1].t == ":"
                    and all(x.k == "w" or x.t == "," for x in toks[i + 1:close])):
                i = close + 2
                continue
        break
    return i, labels


def _is_assignment(toks: list, j: int, semi: int) -> bool:
    """True when the statement at j is `reference[, reference] = expression` (PL/I has no reserved words)."""
    k = j
    while k < semi:
        if toks[k].k != "w":
            return False
        k += 1
        while k < semi:
            if toks[k].t == "(":
                k = _match(toks, k, semi) + 1
            elif toks[k].t in (".", "->", "=>") and k + 1 < semi and toks[k + 1].k == "w":
                k += 2
            else:
                break
        if k < semi and toks[k].k == "p" and toks[k].t in _ASSIGN_OPS:
            return True
        if k < semi and toks[k].t == ",":
            k += 1
            continue
        return False
    return False


def _ref_end(toks: list, k: int) -> int:
    """Index after the reference that starts at toks[k] (NAME, NAME(1), A.B, P->X)."""
    size = len(toks)
    if k >= size or toks[k].k != "w":
        return k
    k += 1
    while k < size:
        if toks[k].t == "(":
            k = _match(toks, k, size) + 1
        elif toks[k].t in (".", "->", "=>") and k + 1 < size and toks[k + 1].k == "w":
            k += 2
        else:
            break
    return k


def _text(toks: list) -> str:
    return zscan.join_tokens(toks) if toks else ""


def _ref_name(toks: list) -> Optional[str]:
    """NAME for a reference (A.B gives B, A(1) gives A); the text as written for an expression."""
    if not toks:
        return None
    words = []
    k = 0
    while k < len(toks):
        t = toks[k]
        if t.t == "(":
            k = _match(toks, k, len(toks)) + 1
            continue
        if t.k == "w":
            words.append(t.u)
        elif t.t not in (".", "->", "=>"):
            return _text(toks)
        k += 1
    return words[-1] if words else _text(toks)


def _key_text(toks: list) -> Optional[str]:
    """A KEY, KEYFROM or KEYTO value: the name of a plain reference, else the expression as written."""
    if toks and all(t.k == "w" or t.t in (".", "->", "=>") for t in toks):
        return _ref_name(toks)
    return _text(toks) or None


def _options(toks: list) -> Dict[str, Optional[list]]:
    """WORD or WORD(arg) items of a statement, first occurrence of each word."""
    out: Dict[str, Optional[list]] = {}
    k = 0
    while k < len(toks):
        t = toks[k]
        if t.k == "w":
            arg = None
            nk = k + 1
            if nk < len(toks) and toks[nk].t == "(":
                close = _match(toks, nk, len(toks))
                arg = toks[nk + 1:close]
                nk = close + 1
            out.setdefault(t.u, arg)
            k = nk
            continue
        k += 1
    return out


def _int(text: str) -> Any:
    s = text.strip()
    try:
        return int(s)
    except ValueError:
        return s


# --------------------------------------------------------------------------- %INCLUDE members
_INDEX_CACHE: Dict[Tuple[str, ...], "IncludeIndex"] = {}
_INDEX_CACHE_SIZE = 16


class IncludeIndex:
    """%INCLUDE members by name (file name without extension, upper case) in some folders.

    Folders are searched in the order given; files can be named too. A member is chosen by
    the library named in %INCLUDE LIB(MEMBER) when a folder on its path has that name, then
    by extension (.inc first), then by the folder closest to the including file, then by order.
    """

    def __init__(self, include_dirs: Sequence = (), root: Optional[Path] = None):
        base = zscan.project_root(root)
        self.folders = [Path(d) if Path(d).is_absolute() else base / d for d in include_dirs]
        self.by_name: Dict[str, List[Tuple[Path, int]]] = {}
        self._stamps: Dict[str, int] = {}
        seen: Set[str] = set()
        order = 0
        for folder in self.folders:
            candidates: List[Path] = []
            if folder.is_file():
                candidates.append(folder)
                self._stamp(str(folder))
            elif folder.is_dir():
                for dirpath, dirnames, filenames in os.walk(folder):
                    dirnames[:] = sorted(d for d in dirnames if d not in zscan.SKIP_DIRS and not d.startswith("."))
                    self._stamp(dirpath)
                    for name in sorted(filenames):
                        if not name.startswith("."):
                            candidates.append(Path(dirpath) / name)
            for path in candidates:
                real = os.path.realpath(path)
                if real in seen or os.path.islink(path):
                    continue
                seen.add(real)
                self.by_name.setdefault(zscan.member_name(path), []).append((path, order))
                order += 1

    def _stamp(self, where: str) -> None:
        try:
            self._stamps[where] = os.stat(where).st_mtime_ns
        except OSError:
            self._stamps[where] = -1

    def fresh(self) -> bool:
        """False when a folder was changed (a file added, removed or renamed) since the index was built."""
        for where, stamp in self._stamps.items():
            try:
                if os.stat(where).st_mtime_ns != stamp:
                    return False
            except OSError:
                return False
        return True

    @classmethod
    def cached(cls, include_dirs: Sequence = (), root: Optional[Path] = None) -> "IncludeIndex":
        """An index for these folders, reused while none of their directories changed."""
        base = zscan.project_root(root)
        key = (str(base),) + tuple(os.path.realpath(Path(d) if Path(d).is_absolute() else base / d)
                                   for d in include_dirs)
        hit = _INDEX_CACHE.get(key)
        if hit is not None and hit.fresh():
            return hit
        index = cls(include_dirs, base)
        _INDEX_CACHE.pop(key, None)
        _INDEX_CACHE[key] = index
        while len(_INDEX_CACHE) > _INDEX_CACHE_SIZE:
            _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
        return index

    def resolve(self, name: str, library: Optional[str], from_file: Path) -> Optional[Path]:
        key = name.upper()
        if "/" in name or "\\" in name or "." in name:
            direct = Path(from_file).parent / name
            if direct.is_file():
                return direct
            key = Path(name.replace("\\", "/")).stem.upper()
        found = self.by_name.get(key)
        if not found:
            return None
        here = os.path.realpath(Path(from_file).parent).split(os.sep)

        def score(item: Tuple[Path, int]):
            path, order = item
            parts = os.path.realpath(path.parent).split(os.sep)
            lib = 0 if library and any(p.upper() == library.upper() for p in parts) else 1
            common = 0
            for a, b in zip(here, parts):
                if a != b:
                    break
                common += 1
            return (lib, _EXT_RANK.get(path.suffix.lower(), 4), -common, order)

        return min(found, key=score)[0]


def _include_items(toks: list) -> List[Tuple[str, Optional[str], Any]]:
    """(member, library, token) for each item of %INCLUDE a, LIB(b), 'file.inc'."""
    items = []
    for group in _split_list(toks):
        if not group:
            continue
        first = group[0]
        if first.k == "s":
            items.append((_lit(first.t), None, first))
        elif first.k == "w":
            if len(group) >= 4 and group[1].t == "(":
                inner = group[2]
                items.append((_lit(inner.t) if inner.k == "s" else inner.u, first.u, first))
            else:
                items.append((first.u, None, first))
    return items


class _Source:
    __slots__ = ("path", "file", "copybook")

    def __init__(self, path: Path, file: str, copybook: Optional[str]):
        self.path, self.file, self.copybook = path, file, copybook


class _Loader:
    """Tokenizes a program, splices in its %INCLUDE members and steps over preprocessor statements."""

    def __init__(self, index: Optional[IncludeIndex], root: Path, margins: Tuple[int, int]):
        self.index = index
        self.root = root
        self.margins = margins
        self.sources: List[_Source] = []
        self.copybooks: List[dict] = []
        self.warnings: List[dict] = []
        self.sql_includes: List[str] = []
        self.macro_procs: List[str] = []
        self.pp: Dict[str, List[Tuple[str, int]]] = {}
        self.once: Set[str] = set()

    def warn(self, file: Optional[str], line: Optional[int], message: str) -> None:
        self.warnings.append({"file": file, "line": line, "message": message})

    def load(self, path: Path, copybook: Optional[str], skip: Set[int] = frozenset()) -> list:
        raw = zscan.read_text(path).splitlines()
        src = len(self.sources)
        file = zscan.rel(path, self.root)
        self.sources.append(_Source(path, file, copybook))
        stats: dict = {}
        toks = _lex(raw, self.margins, src, skip, stats)
        left, right = self.margins
        if stats.get("left"):
            lines = stats["left"]
            self.warn(file, lines[0], f"{len(lines)} line(s) have text left of column {left}, outside the margins "
                                      f"({left}, {right}); it is ignored as the compiler would. If the code starts in "
                                      "column 1, the source was written for other margins (*PROCESS MARGINS)")
        if stats.get("right"):
            lines = stats["right"]
            self.warn(file, lines[0], f"{len(lines)} line(s) have text past column {right} that looks like code or a "
                                      f"comment; it is ignored as the compiler would with margins ({left}, {right})")
        if stats.get("open_comment"):
            self.warn(file, stats["open_comment"], "comment not closed: the rest of the file is read as a comment")
        if stats.get("open_string"):
            self.warn(file, stats["open_string"], "string not closed before the end of the file")
        return toks

    def note(self, kind: str, tok, extra: Optional[str] = None) -> None:
        self.pp.setdefault(kind, []).append((self.sources[tok.src].file, tok.line))
        if extra and extra not in self.macro_procs:
            self.macro_procs.append(extra)

    def pp_warnings(self) -> List[dict]:
        out = []
        for kind, where in self.pp.items():
            if kind == "PROCEDURE":
                message = (f"preprocessor procedure {', '.join(self.macro_procs)} not evaluated: "
                           "its invocations are left as written")
            else:
                message = _PP_MESSAGES.get(kind, f"preprocessor statement %{kind} not evaluated")
            if len(where) > 1:
                message += f" ({len(where)} times)"
            out.append({"file": where[0][0], "line": where[0][1], "message": message})
        return out

    def expand(self, toks: list, stack: Tuple[str, ...], from_path: Path) -> list:
        out: list = []
        i, n = 0, len(toks)
        while i < n:
            t = toks[i]
            if t.k == "p" and t.t == "%;":
                self.note(";", t)
                i += 1
                continue
            if t.k == "p" and t.t == "%":
                i = self.preprocessor(toks, i, stack, from_path, out)
                continue
            if (t.k == "w" and t.u == "EXEC" and i + 3 < n and toks[i + 1].u == "SQL"
                    and toks[i + 2].u == "INCLUDE"):
                semi = _next_semi(toks, i)
                out.extend(toks[i:semi + 1])
                member = toks[i + 3]
                name = (_lit(member.t) if member.k == "s" else member.u).upper()
                if name not in self.sql_includes:
                    self.sql_includes.append(name)
                if name not in ("SQLCA", "SQLDA"):
                    self.include(name, None, t, stack, from_path, out, sql=True)
                i = semi + 1
                continue
            out.append(t)
            i += 1
        return out

    def preprocessor(self, toks: list, i: int, stack: Tuple[str, ...], from_path: Path, out: list) -> int:
        """toks[i] is '%': handle one preprocessor statement and return the index after it."""
        n = len(toks)
        t = toks[i]
        j = i + 1
        labels = []
        while j + 1 < n and toks[j].k == "w" and toks[j + 1].t == ":":
            labels.append(toks[j].u)
            j += 2
        kw = toks[j].u if j < n and toks[j].k == "w" else ""
        semi = _next_semi(toks, j)
        if kw in ("PROC", "PROCEDURE"):
            k = j
            while k < n and not (toks[k].t == "%" and k + 1 < n and toks[k + 1].u == "END"):
                k += 1
            self.note("PROCEDURE", t, labels[0] if labels else "(unnamed)")
            return _next_semi(toks, k) + 1
        if kw in ("INCLUDE", "XINCLUDE"):
            for name, library, tok in _include_items(toks[j + 1:semi]):
                self.include(name, library, toks[j], stack, from_path, out, once=(kw == "XINCLUDE"))
            return semi + 1
        if kw in _LISTING:
            return semi + 1
        if kw == "IF":
            self.note("IF", t)
            k = j + 1
            while k < n and toks[k].t != ";" and not (toks[k].t == "%" and k + 1 < n and toks[k + 1].u == "THEN"):
                k += 1
            return k + 2 if k < n and toks[k].t == "%" else k + 1
        if kw in ("THEN", "ELSE", "OTHERWISE", "OTHER"):
            return j + 1
        if kw == "WHEN":
            k = j + 1
            if k < n and toks[k].t == "(":
                return _match(toks, k, n) + 1
            return k
        if kw == "DO":
            spec = toks[j + 1:semi]
            if spec and spec[0].u == "SKIP":  # %DO SKIP: the body is never part of the program
                depth, k = 1, semi + 1
                while k < n and depth:
                    if toks[k].t == "%" and k + 1 < n and toks[k + 1].u == "DO":
                        depth += 1
                    elif toks[k].t == "%" and k + 1 < n and toks[k + 1].u == "END":
                        depth -= 1
                        if depth == 0:
                            return _next_semi(toks, k) + 1
                    k += 1
                return n
            if spec:
                self.note("DO", t)
            return semi + 1
        if kw == "END":
            return semi + 1
        if kw == "SELECT":
            self.note("SELECT", t)
        elif kw in ("DECLARE", "DCL"):
            self.note("DECLARE", t)
        elif kw in ("ACTIVATE", "ACT", "DEACTIVATE", "DEACT"):
            self.note("ACTIVATE", t)
        elif kw == "REPLACE":
            self.note("REPLACE", t)
        elif kw and j + 1 < n and (toks[j + 1].t == "=" or toks[j + 1].t == "("):
            self.note("ASSIGN", t)
        else:
            self.note(kw or "?", t)
        return semi + 1

    def include(self, name: str, library: Optional[str], tok, stack: Tuple[str, ...], from_path: Path, out: list,
                sql: bool = False, once: bool = False) -> None:
        src = self.sources[tok.src]
        path = self.index.resolve(name, library, from_path) if self.index is not None else None
        shown = name.upper() if not any(c in name for c in "./\\") else name
        ident = os.path.realpath(path) if path is not None else shown
        if once and ident in self.once:
            return
        self.once.add(ident)
        self.copybooks.append({
            "name": shown, "library": "SQL INCLUDE" if sql else library,
            "resolved": zscan.rel(path, self.root) if path is not None else None,
            "replacing": False, "line": tok.line, "nested_in": src.copybook, "replacing_pairs": [],
        })
        if self.index is None:
            return
        what = "EXEC SQL INCLUDE" if sql else "%INCLUDE"
        if path is None:
            self.warn(src.file, tok.line, f"{what} member {shown} not found"
                      + (f" (included from {src.copybook})" if src.copybook else "")
                      + "; its declarations and code are missing from this map")
            return
        member = zscan.member_name(path)
        if member in stack or len(stack) >= zscan.MAX_COPY_DEPTH:
            chain = " -> ".join(stack + (member,))
            self.warn(src.file, tok.line, f"{what} {shown} not expanded: nesting loop or depth over "
                                          f"{zscan.MAX_COPY_DEPTH} ({chain})")
            return
        inner = self.load(path, shown)
        out.extend(self.expand(inner, stack + (member,), path))


# --------------------------------------------------------------------------- statements and blocks
class _Blk:
    """A procedure, BEGIN block, ON-unit or package."""

    __slots__ = ("name", "kind", "parent", "line", "end_line", "src", "external", "main", "params", "params_line",
                 "returns", "procs", "aliases")

    def __init__(self, name: str, kind: str, parent: Optional["_Blk"], tok):
        self.name, self.kind, self.parent = name, kind, parent
        self.line = self.end_line = tok.line
        self.src = tok.src
        self.external = False
        self.main = False
        self.params: List[str] = []
        self.params_line: Optional[int] = None
        self.returns = False
        self.procs: Dict[str, "_Blk"] = {}
        self.aliases: List[str] = []

    def runs_in(self) -> "_Blk":
        """The procedure or ON-unit whose flow this block is part of (BEGIN blocks run inline)."""
        b = self
        while b.kind == "begin" and b.parent is not None:
            b = b.parent
        return b


class _Ctx:
    __slots__ = ("blk", "loop")

    def __init__(self, blk: Optional[_Blk], loop: Optional[dict]):
        self.blk, self.loop = blk, loop


class _Parser:
    """Statements, blocks, declarations, loops and conditions of one expanded PL/I program."""

    def __init__(self, toks: list, loader: _Loader):
        self.toks = toks
        self.n = len(toks)
        self.i = 0
        self.loader = loader
        self.sources = loader.sources
        self.blocks: List[_Blk] = []
        self.top_procs: Dict[str, _Blk] = {}
        self.entry_map: Dict[str, _Blk] = {}
        self.entry_stmts: List[Tuple[str, Any, Optional[_Blk]]] = []
        self.statements: List[dict] = []
        self.performs: List[dict] = []
        self.calls: List[dict] = []
        self.gotos: List[dict] = []
        self.sql: List[dict] = []
        self.cics: List[dict] = []
        self.conditions: List[dict] = []
        self.labels: List[dict] = []
        self.warnings: List[dict] = []
        self.items: List[dict] = []
        self.files: Dict[str, dict] = {}
        self.entries_decl: Dict[str, dict] = {}
        self.entry_vars: Set[str] = set()
        self.label_vars: Set[str] = set()
        self.raw_calls: List[dict] = []
        self.raw_io: List[dict] = []
        self.handlers: List[dict] = []
        self.expr_spans: List[Tuple[int, int, _Ctx, dict]] = []
        self.assign_lits: Dict[str, List[str]] = {}
        self.assign_words: Dict[str, List[str]] = {}
        self.loop_ranges: Dict[Tuple[str, int], Tuple[int, int, int]] = {}
        self.open_groups: List[Set[str]] = []
        self.pending: Optional[str] = None
        self.pending_tok = None
        self.warned_once: Set[str] = set()
        self.idb: Optional[_Blk] = None
        self.display: Dict[_Blk, str] = {}

    # ---- helpers
    def where(self, tok) -> dict:
        cb = self.sources[tok.src].copybook
        return {"copybook": cb} if cb else {}

    def file_of(self, tok) -> str:
        return self.sources[tok.src].file

    def warn(self, tok, message: str) -> None:
        if tok is None:
            self.warnings.append({"file": self.sources[0].file, "line": None, "message": message})
        else:
            self.warnings.append({"file": self.file_of(tok), "line": tok.line, "message": message})

    def next_semi(self, k: int) -> int:
        return _next_semi(self.toks, k)

    def match(self, k: int, limit: Optional[int] = None) -> int:
        return _match(self.toks, k, self.n if limit is None else limit)

    def last_line(self, src: int, a: int, b: int) -> Optional[int]:
        for k in range(min(b, self.n) - 1, a - 1, -1):
            if self.toks[k].src == src:
                return self.toks[k].end
        return None

    def span_end(self, rec: dict, a: int, b: int) -> None:
        last = self.last_line(rec["_src"], a, b)
        if last is not None:
            rec["end_line"] = max(rec.get("end_line") or 0, last)

    def new_stmt(self, verb: str, tok, ops: list, ctx: _Ctx, a: int, b: int) -> dict:
        rec = {"verb": verb, "line": tok.line, "end_line": tok.line, "paragraph": None,
               "operands": [x.t for x in ops], "in_loop": ctx.loop}
        rec.update(self.where(tok))
        rec["_blk"] = ctx.blk
        rec["_src"] = tok.src
        self.span_end(rec, a, b)
        self.statements.append(rec)
        return rec

    def new_cond(self, kind: str, toks: list, start, ctx: _Ctx, owner: dict) -> dict:
        rec = {"kind": kind, "text": _text(toks), "tokens": [x.t for x in toks], "start_line": start.line,
               "end_line": toks[-1].end if toks and toks[-1].src == start.src else start.line,
               "paragraph": None, "data_items": [], "in_loop": None}
        rec.update(self.where(start))
        rec.update({"_blk": ctx.blk, "_owner": owner, "_toks": list(toks), "_src": start.src})
        self.conditions.append(rec)
        return rec

    def add_labels(self, labels: list, tok, ctx: _Ctx) -> None:
        for lab in labels:
            rec = {"name": lab.u, "line": lab.line, "paragraph": None}
            rec.update(self.where(lab))
            rec.update({"_blk": ctx.blk, "_src": lab.src})
            self.labels.append(rec)

    def find_then(self, a: int, semi: int) -> Optional[int]:
        depth = 0
        for k in range(a, semi):
            t = self.toks[k]
            if t.t == "(":
                depth += 1
            elif t.t == ")":
                depth -= 1
            elif depth <= 0 and t.k == "w" and t.u == "THEN":
                return k
        return None

    # ---- the program
    def parse(self) -> None:
        ctx = _Ctx(None, None)
        while self.i < self.n:
            before = self.i
            self.unit(ctx)
            self.pending = None
            if self.i <= before:  # an END with nothing open
                self.i = before + 1

    def unit(self, ctx: _Ctx) -> None:
        """Parse one statement, with what it contains (a DO group, an IF with its THEN and ELSE...)."""
        toks, n = self.toks, self.n
        j, labels = _skip_labels(toks, self.i, n)
        if j >= n:
            self.add_labels(labels, labels[-1] if labels else None, ctx)
            self.i = n
            return
        t = toks[j]
        semi = self.next_semi(j)
        if t.k == "p" and t.t == ";":
            self.add_labels(labels, t, ctx)
            self.i = j + 1
            return
        if t.k != "w":
            self.add_labels(labels, t, ctx)
            self.unknown(j, semi, ctx)
            return
        u = t.u
        if u == "IF":
            then = self.find_then(j + 1, semi)
            if then is not None:
                self.add_labels(labels, t, ctx)
                self.if_stmt(j, then, ctx)
                return
        if _is_assignment(toks, j, semi):
            self.add_labels(labels, t, ctx)
            self.assignment(j, semi, ctx)
            return
        if u == "END":
            if self.open_groups:
                self.warn(t, "a statement was expected before this END")
                self.i = j
            else:
                self.warn(t, "END without an open procedure, DO, SELECT or BEGIN")
                self.i = semi + 1
            return
        if u in ("PROC", "PROCEDURE", "PACKAGE"):
            self.proc_block(labels, j, semi, ctx, "package" if u == "PACKAGE" else "procedure")
            return
        if u in ("DCL", "DECLARE"):
            self.declare(j, semi, ctx)
            self.i = semi + 1
            return
        if u in ("DEFAULT", "DFT"):
            if "DEFAULT" not in self.warned_once:
                self.warned_once.add("DEFAULT")
                self.warn(t, "DEFAULT statement: the defaults it sets are not applied to the type and usage of items")
            self.i = semi + 1
            return
        if u in ("DEFINE", "FORMAT"):
            self.i = semi + 1
            return
        if u == "ENTRY":
            self.entry_stmt(labels, j, semi, ctx)
            return
        self.add_labels(labels, t, ctx)
        if u == "BEGIN":
            self.begin_block(labels, j, semi, ctx)
        elif u == "DO":
            self.do_group(labels, j, semi, ctx)
        elif u == "SELECT":
            self.select_group(labels, j, semi, ctx)
        elif u == "ON":
            self.on_stmt(j, ctx)
        elif u == "EXEC":
            self.exec_stmt(j, semi, ctx)
        elif u == "CALL":
            self.call_stmt(j, semi, ctx)
        elif u == "FETCH":
            self.fetch_stmt(j, semi, ctx)
        elif u == "GOTO" or (u == "GO" and j + 1 < semi and toks[j + 1].u == "TO"):
            self.goto_stmt(j, semi, ctx)
        elif u in _IO_VERBS:
            self.io_stmt(j, semi, ctx)
        elif u == "ELSE":
            self.warn(t, "ELSE without an IF")
            self.i = j + 1
        elif u in ("WHEN", "OTHERWISE", "OTHER"):
            self.warn(t, f"{u} outside a SELECT")
            k = j + 1
            if u == "WHEN" and k < n and toks[k].t == "(":
                k = self.match(k) + 1
            self.i = k
        elif u in _STATEMENT_VERBS:
            self.generic(j, semi, ctx)
        else:
            self.unknown(j, semi, ctx)

    def close_end(self, k: int, semi: int, labels: list, names: Set[str], ctx: _Ctx, opener, what: str):
        """toks[k] is the END of a group or block: consume it and return its last token."""
        toks = self.toks
        self.add_labels(labels, toks[k], ctx)
        name = toks[k + 1].u if k + 1 < semi and toks[k + 1].k == "w" else None
        self.i = semi + 1
        end_tok = toks[min(semi, self.n - 1)]
        if name and name not in names:
            if any(name in g for g in self.open_groups[:-1]):
                self.pending, self.pending_tok = name, end_tok
                self.warn(toks[k], f"END {name} also closes the {what} at line {opener.line} (multiple closure)")
            else:
                self.warn(toks[k], f"END {name} does not name the {what} at line {opener.line}; taken as its END")
        return end_tok

    def body(self, labels: list, ctx: _Ctx, opener, what: str) -> None:
        """Statements up to the END that closes a DO group, BEGIN block, procedure or package."""
        names = {x.u for x in labels}
        self.open_groups.append(names)
        try:
            while True:
                if self.pending is not None:
                    if self.pending in names:
                        self.pending = None
                    return
                if self.i >= self.n:
                    self.warn(opener, f"{what} at line {opener.line} has no END; closed at the end of the file")
                    return
                k, lbls = _skip_labels(self.toks, self.i, self.n)
                if k < self.n and self.toks[k].k == "w" and self.toks[k].u == "END":
                    semi = self.next_semi(k)
                    if not _is_assignment(self.toks, k, semi):
                        self.close_end(k, semi, lbls, names, ctx, opener, what)
                        return
                self.unit(ctx)
        finally:
            self.open_groups.pop()

    def if_stmt(self, j: int, then: int, ctx: _Ctx) -> None:
        toks = self.toks
        chain = []
        while True:
            t = toks[j]
            cond_toks = toks[j + 1:then]
            rec = self.new_stmt("IF", t, cond_toks, ctx, j, then + 1)
            cond = self.new_cond("IF", cond_toks, t, ctx, rec)
            cond["else_line"] = None
            self.expr_spans.append((j + 1, then, ctx, rec))
            chain.append((rec, cond, j))
            self.i = then + 1
            self.unit(ctx)
            if (self.pending is None and self.i < self.n and toks[self.i].k == "w" and toks[self.i].u == "ELSE"):
                cond["else_line"] = toks[self.i].line
                self.i += 1
                k = self.i
                if k < self.n and toks[k].k == "w" and toks[k].u == "IF":  # ELSE IF: a chain, not a recursion
                    nthen = self.find_then(k + 1, self.next_semi(k))
                    if nthen is not None:
                        j, then = k, nthen
                        continue
                self.unit(ctx)
            break
        for rec, cond, start in chain:
            self.span_end(rec, start, self.i)
            cond["end_line"] = rec["end_line"]

    def do_kind(self, spec: list) -> Optional[str]:
        if not spec:
            return None
        first = spec[0].u
        if first == "WHILE":
            return "while"
        if first == "UNTIL":
            return "until"
        if first in ("FOREVER", "LOOP") and len(spec) == 1:
            return "forever"
        top: List[str] = []
        k = 0
        while k < len(spec):
            if spec[k].t == "(":
                k = _match(spec, k, len(spec)) + 1
                continue
            top.append(spec[k].u if spec[k].k == "w" else spec[k].t)
            k += 1
        if "=" not in top:
            return None
        if "REPEAT" in top:
            return "repeat"
        if set(top) & {"TO", "BY", "UPTHRU", "DOWNTHRU", "WHILE", "UNTIL", ","}:
            return "iterative"
        return None

    def do_group(self, labels: list, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        spec = toks[j + 1:semi]
        kind = self.do_kind(spec)
        rec = self.new_stmt("DO", t, spec, ctx, j, semi + 1)
        self.expr_spans.append((j + 1, semi, ctx, rec))
        inner = ctx
        pr = None
        if kind:
            pr = {"from": None, "to": None, "thru": None, "loop": kind, "inline": True, "line": t.line,
                  "end_line": t.line, "in_loop": ctx.loop}
            pr.update(self.where(t))
            pr.update({"_blk": ctx.blk, "_src": t.src})
            self.performs.append(pr)
            k = 0
            while k < len(spec):
                if spec[k].k == "w" and spec[k].u in ("WHILE", "UNTIL") and k + 1 < len(spec) and spec[k + 1].t == "(":
                    close = _match(spec, k + 1, len(spec))
                    self.new_cond(spec[k].u, spec[k + 2:close], spec[k], ctx, rec)
                    k = close + 1
                    continue
                if spec[k].t == "(":
                    k = _match(spec, k, len(spec)) + 1
                    continue
                k += 1
            inner = _Ctx(ctx.blk, {"via": t.line, "kind": kind, "file": self.file_of(t)})
        self.i = semi + 1
        self.body(labels, inner, t, "DO group")
        self.span_end(rec, j, self.i)
        if pr is not None:
            pr["end_line"] = rec["end_line"]
            self.loop_ranges[(self.file_of(t), t.line)] = (t.src, t.line, rec["end_line"])

    def select_group(self, labels: list, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        head = toks[j + 1:semi]
        subj = head[1:-1] if len(head) >= 2 and head[0].t == "(" and head[-1].t == ")" else head
        rec = self.new_stmt("SELECT", t, head, ctx, j, semi + 1)
        scond = self.new_cond("SELECT", subj, t, ctx, rec)
        subject = scond["text"] if subj else None
        self.expr_spans.append((j + 1, semi, ctx, rec))
        self.i = semi + 1
        names = {x.u for x in labels}
        self.open_groups.append(names)
        try:
            while True:
                if self.i >= self.n:
                    self.warn(t, f"SELECT at line {t.line} has no END; closed at the end of the file")
                    break
                if self.pending is not None:
                    if self.pending in names:
                        self.pending = None
                    break
                k, lbls = _skip_labels(toks, self.i, self.n)
                if k >= self.n:
                    self.i = self.n
                    continue
                w = toks[k]
                ksemi = self.next_semi(k)
                if w.k == "w" and w.u == "END" and not _is_assignment(toks, k, ksemi):
                    self.close_end(k, ksemi, lbls, names, ctx, t, "SELECT")
                    break
                if w.k == "w" and w.u == "WHEN" and not _is_assignment(toks, k, ksemi):
                    m = k + 1
                    if m + 1 < self.n and toks[m].u in ("ANY", "ALL") and toks[m + 1].t == "(":
                        m += 1
                    if m < self.n and toks[m].t == "(":
                        close = self.match(m)
                        vals, after = toks[m + 1:close], close + 1
                    else:
                        vals, after = [], m
                    wc = self.new_cond("WHEN", vals, w, ctx, rec)
                    wc["subject"] = subject
                    wc["_extra"] = list(subj)
                    self.expr_spans.append((m, after, ctx, rec))
                    self.i = after
                    self.unit(ctx)
                    last = self.last_line(w.src, k, self.i)
                    wc["end_line"] = max(wc["end_line"], last or 0)
                    continue
                if w.k == "w" and w.u in ("OTHERWISE", "OTHER") and not _is_assignment(toks, k, ksemi):
                    oc = self.new_cond("OTHERWISE", [], w, ctx, rec)
                    oc["subject"] = subject
                    oc["_extra"] = list(subj)
                    self.i = k + 1
                    self.unit(ctx)
                    last = self.last_line(w.src, k, self.i)
                    oc["end_line"] = max(oc["end_line"], last or 0)
                    continue
                self.warn(w, f"statement in the SELECT at line {t.line} is outside WHEN and OTHERWISE")
                before = self.i
                self.unit(ctx)
                if self.i <= before:
                    self.i = before + 1
        finally:
            self.open_groups.pop()
        self.span_end(rec, j, self.i)
        scond["end_line"] = rec["end_line"]

    def on_stmt(self, j: int, ctx: _Ctx) -> None:
        toks, n = self.toks, self.n
        t = toks[j]
        k = j + 1
        conds = []
        while k < n and toks[k].k == "w":
            name, ctok = toks[k].u, toks[k]
            k += 1
            arg: list = []
            if k < n and toks[k].t == "(":
                close = self.match(k)
                arg = toks[k + 1:close]
                k = close + 1
            conds.append((name, arg, ctok))
            if k < n and toks[k].t == ",":
                k += 1
                continue
            break
        if k < n and toks[k].u == "SNAP":
            k += 1
        rec = self.new_stmt("ON", t, toks[j + 1:k], ctx, j, k)
        unit_name = None
        if k + 1 < n and toks[k].u == "SYSTEM" and toks[k + 1].t == ";":
            self.i = k + 2
        else:
            first = conds[0][0] if conds else "CONDITION"
            unit_name = f"ON-{first}-{t.line}"
            blk = _Blk(unit_name, "on-unit", ctx.blk, t)
            self.blocks.append(blk)
            self.i = k
            ksemi = self.next_semi(k)
            if k < n and toks[k].u == "BEGIN" and not _is_assignment(toks, k, ksemi):
                self.begin_block([], k, ksemi, ctx, blk)
            else:
                self.unit(_Ctx(blk, None))
            last = self.last_line(blk.src, j, self.i)
            blk.end_line = max(blk.line, last or blk.line)
        self.span_end(rec, j, self.i)
        for name, arg, ctok in conds:
            cond = _FILE_CONDITIONS.get(name)
            file_ref = _ref_name(arg) if arg else None
            if cond and file_ref:
                h = {"condition": cond, "file": file_ref, "line": t.line, "end_line": rec["end_line"],
                     "unit": unit_name}
                h.update(self.where(t))
                h.update({"_blk": ctx.blk, "_src": t.src})
                self.handlers.append(h)

    def begin_block(self, labels: list, j: int, semi: int, ctx: _Ctx, blk: Optional[_Blk] = None) -> None:
        t = self.toks[j]
        if blk is None:
            name = labels[0].u if labels else f"BEGIN-{t.line}"
            blk = _Blk(name, "begin", ctx.blk, labels[0] if labels else t)
            self.blocks.append(blk)
            inner = _Ctx(blk, ctx.loop)
        else:
            inner = _Ctx(blk, None)
        self.i = semi + 1
        self.body(labels, inner, t, "BEGIN block")
        last = self.last_line(blk.src, j, self.i)
        blk.end_line = max(blk.end_line, last or blk.end_line)

    def proc_block(self, labels: list, j: int, semi: int, ctx: _Ctx, kind: str) -> None:
        toks = self.toks
        t = toks[j]
        k = j + 1
        params: List[str] = []
        params_line = None
        if k < semi and toks[k].t == "(":
            close = self.match(k, semi)
            params = [x.u for x in toks[k + 1:close] if x.k == "w"]
            params_line = toks[k + 1].line if k + 1 < close else None
            k = close + 1
        opts = _options(toks[k:semi])
        if labels:
            name = labels[0].u
        else:
            name = f"{kind.upper()}-{t.line}"
            self.warn(t, f"{kind} without a name; called {name} in this map")
        blk = _Blk(name, kind, ctx.blk, labels[0] if labels else t)
        blk.external = kind == "procedure" and (ctx.blk is None or ctx.blk.kind == "package")
        blk.main = any(x.u == "MAIN" for x in (opts.get("OPTIONS") or []))
        blk.returns = "RETURNS" in opts
        blk.params, blk.params_line = params, params_line
        blk.aliases = [x.u for x in labels[1:]]
        self.blocks.append(blk)
        if kind == "procedure":
            scope = self.top_procs if blk.external or ctx.blk is None else ctx.blk.procs
            for alias in [name] + blk.aliases:
                if alias in scope:
                    self.warn(t, f"procedure {alias} is declared twice in the same block; calls go to the first")
                else:
                    scope[alias] = blk
        self.i = semi + 1
        self.body(labels, _Ctx(blk, None), t, f"{kind} {name}")
        last = self.last_line(blk.src, j, self.i)
        blk.end_line = max(blk.end_line, last or blk.end_line)

    def entry_stmt(self, labels: list, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        proc = ctx.blk
        while proc is not None and proc.kind != "procedure":
            proc = proc.parent
        if j + 1 < semi and toks[j + 1].t == "(" and proc is not None:
            close = self.match(j + 1, semi)
            for x in toks[j + 2:close]:
                if x.k == "w" and x.u not in proc.params:
                    proc.params.append(x.u)
        for lab in labels:
            self.entry_stmts.append((lab.u, lab, proc))
            if proc is not None:
                self.entry_map.setdefault(lab.u, proc)
        self.i = semi + 1

    def exec_stmt(self, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        sub = toks[j + 1].u if j + 1 < semi and toks[j + 1].k == "w" else "?"
        body = toks[j + 2:semi]
        text = _text(body)
        rec = self.new_stmt(f"EXEC {sub}", t, [], ctx, j, semi + 1)
        if sub == "SQL":
            s = zscan.parse_sql(text)
            rec["operands"] = [s["verb"]]
            r = {"line": t.line, "end_line": rec["end_line"], "paragraph": None, "verb": s["verb"],
                 "tables": s["tables"], "cursor": s["cursor"], "host_vars": s["host_vars"],
                 "multi_row": s["multi_row"], "text": text, "in_loop": ctx.loop}
            r.update(self.where(t))
            r["_blk"] = ctx.blk
            self.sql.append(r)
        elif sub == "CICS":
            c = zscan.parse_cics(text)
            rec["operands"] = [c["command"]]
            r = {"line": t.line, "end_line": rec["end_line"], "paragraph": None, "command": c["command"],
                 "options": c["options"], "in_loop": ctx.loop}
            r.update(self.where(t))
            r["_blk"] = ctx.blk
            self.cics.append(r)
        elif body:
            rec["operands"] = [body[0].t.upper()]
        self.i = semi + 1

    def args_of(self, a: int, close: int) -> List[str]:
        out = []
        for group in _split_list(self.toks[a:close]):
            if len(group) == 1 and group[0].k == "w":
                out.append(group[0].u)
            elif group:
                out.append(_text(group))
        return out

    def call_stmt(self, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        rec = self.new_stmt("CALL", t, toks[j + 1:semi], ctx, j, semi + 1)
        self.i = semi + 1
        k = j + 1
        if k >= semi or toks[k].k != "w":
            self.warn(t, "CALL without an entry name")
            return
        name = toks[k].u
        k += 1
        qualified = False
        while k + 1 < semi and toks[k].t in (".", "->", "=>") and toks[k + 1].k == "w":
            qualified = True
            k += 2
        ref = _text(toks[j + 1:k])
        args: List[str] = []
        if k < semi and toks[k].t == "(":
            close = self.match(k, semi)
            args = self.args_of(k + 1, close)
        self.expr_spans.append((k, semi, ctx, rec))
        self.raw_calls.append({"form": "CALL", "name": name, "ref": ref.upper(), "qualified": qualified,
                               "args": args, "tok": t, "ctx": ctx, "rec": rec})

    def fetch_stmt(self, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        rec = self.new_stmt("FETCH", t, toks[j + 1:semi], ctx, j, semi + 1)
        for group in _split_list(toks[j + 1:semi]):
            if group and group[0].k == "w":
                opts = _options(group[1:])
                self.raw_calls.append({"form": "FETCH", "name": group[0].u, "title": opts.get("TITLE"), "args": [],
                                       "tok": t, "ctx": ctx, "rec": rec, "qualified": False})
        self.i = semi + 1

    def goto_stmt(self, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        k = j + 2 if t.u == "GO" else j + 1
        self.new_stmt("GO TO", t, toks[k:semi], ctx, j, semi + 1)
        target = toks[k].u if k < semi and toks[k].k == "w" else None
        g = {"to": [target] if target else [], "line": t.line, "paragraph": None, "depending_on": None}
        g.update(self.where(t))
        g.update({"_blk": ctx.blk, "_src": t.src, "_loop": ctx.loop})
        self.gotos.append(g)
        if target is None:
            self.warn(t, "GO TO without a label name; flow not followed")
        self.i = semi + 1

    def io_stmt(self, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        verb = t.u
        rec = self.new_stmt(verb, t, toks[j + 1:semi], ctx, j, semi + 1)
        self.expr_spans.append((j + 1, semi, ctx, rec))
        operands = toks[j + 1:semi]
        groups = _split_list(operands) if verb in ("OPEN", "CLOSE") else [operands]
        for group in groups:
            opts = _options(group)
            fname = _ref_name(opts["FILE"]) if opts.get("FILE") else None
            if not fname or fname == "*":  # CLOSE FILE(*) closes every open file
                continue
            mode = next((m for m in ("INPUT", "OUTPUT", "UPDATE") if m in opts), None) if verb == "OPEN" else None
            io = {"verb": verb, "file": fname, "rec": rec, "tok": t, "ctx": ctx, "mode": mode,
                  "title": opts.get("TITLE"), "records": [], "keys": [], "attrs": [w for w in opts if w in _FILE_ATTRS]}
            for key in ("INTO", "FROM"):
                if opts.get(key):
                    io["records"].append(_ref_name(opts[key]))
            if verb == "LOCATE" and group and group[0].k == "w":
                io["records"].append(group[0].u)
            for key in ("KEY", "KEYFROM", "KEYTO"):
                if opts.get(key):
                    io["keys"].append(_key_text(opts[key]))
            self.raw_io.append(io)
        self.i = semi + 1

    def generic(self, j: int, semi: int, ctx: _Ctx) -> None:
        t = self.toks[j]
        rec = self.new_stmt(t.u, t, self.toks[j + 1:semi], ctx, j, semi + 1)
        self.expr_spans.append((j + 1, semi, ctx, rec))
        self.i = semi + 1

    def assignment(self, j: int, semi: int, ctx: _Ctx) -> None:
        toks = self.toks
        t = toks[j]
        rec = self.new_stmt("ASSIGN", t, toks[j:semi], ctx, j, semi + 1)
        if semi - j == 3 and toks[j + 1].t == "=":
            value = toks[j + 2]
            if value.k == "s":
                self.assign_lits.setdefault(t.u, []).append(_lit(value.t).strip().upper())
            elif value.k == "w":
                self.assign_words.setdefault(t.u, []).append(value.u)
        eq = j
        while eq < semi and not (toks[eq].k == "p" and toks[eq].t in _ASSIGN_OPS):
            if toks[eq].t == "(":
                eq = self.match(eq, semi)
            eq += 1
        self.expr_spans.append((eq + 1, semi, ctx, rec))
        self.i = semi + 1

    def unknown(self, j: int, semi: int, ctx: _Ctx) -> None:
        t = self.toks[j]
        self.new_stmt("UNKNOWN", t, self.toks[j:semi], ctx, j, semi + 1)
        if t.k == "w" and t.u in self.loader.macro_procs:
            self.warn(t, f"{t.u} invokes preprocessor procedure {t.u}, which is not evaluated; recorded as UNKNOWN")
        else:
            self.warn(t, f"statement not understood (it starts with {t.t!r}); recorded as UNKNOWN")
        self.i = max(semi + 1, j + 1)

    # ---- declarations
    def declare(self, j: int, semi: int, ctx: _Ctx) -> None:
        stack: List[Tuple[int, str, int, str]] = []
        for part in _split_list(self.toks[j + 1:semi]):
            self.decl_part(part, ctx.blk, stack, [], None)

    def decl_part(self, part: list, blk: Optional[_Blk], stack: list, outer: list, level: Optional[int]) -> None:
        if not part:
            return
        k = 0
        if part[0].k == "n" and part[0].t.isdigit():
            level = int(part[0].t)
            k = 1
        if k < len(part) and part[k].t == "(":
            close = _match(part, k, len(part))
            attrs = part[close + 1:] + outer
            for sub in _split_list(part[k + 1:close]):
                self.decl_part(sub, blk, stack, attrs, level)
            return
        if k >= len(part):
            return
        name_tok = part[k]
        if name_tok.t == "*":
            name = "FILLER"
        elif name_tok.k == "w":
            name = name_tok.u
        else:
            return
        k += 1
        dims = None
        if k < len(part) and part[k].t == "(":
            close = _match(part, k, len(part))
            dims = part[k + 1:close]
            k = close + 1
        self.make_item(name, name_tok, level or 1, dims, part[k:] + outer, blk, stack)

    @staticmethod
    def parse_attrs(attrs: list) -> dict:
        info: Dict[str, Any] = {"pic": None, "init": None, "based": None, "defined": None, "like": None,
                                "external": False, "ext_name": None, "storage": None, "file": False, "entry": False,
                                "variable": False, "label": False, "returns": False, "skip": False,
                                "builtin": False, "dim": None, "file_attrs": [], "env": None, "options": None,
                                "parameter": False}
        scale = base = prec = strtype = strlen = varying = other = None
        extra: List[str] = []
        k = 0
        size = len(attrs)
        while k < size:
            t = attrs[k]
            if t.k != "w":
                k += 1
                continue
            w = t.u
            arg = None
            nk = k + 1
            if nk < size and attrs[nk].t == "(":
                close = _match(attrs, nk, size)
                arg = attrs[nk + 1:close]
                nk = close + 1
            if w in ("PIC", "PICTURE"):
                if nk < size and attrs[nk].k == "s":
                    info["pic"] = _lit(attrs[nk].t).upper()
                    nk += 1
            elif w in _STRING_TYPES:
                strtype, strlen = _STRING_TYPES[w], (_text(arg) if arg else None)
            elif w in ("VARYING", "VAR", "VARYINGZ", "VARZ"):
                varying = "VARYINGZ" if w.endswith("Z") else "VARYING"
            elif w in ("FIXED", "FLOAT"):
                scale = w
                prec = prec or (_text(arg) if arg else None)
            elif w in ("DEC", "DECIMAL", "BIN", "BINARY"):
                base = "DEC" if w.startswith("DEC") else "BIN"
                prec = prec or (_text(arg) if arg else None)
            elif w in ("PREC", "PRECISION"):
                prec = _text(arg) if arg else prec
            elif w in ("SIGNED", "UNSIGNED", "COMPLEX", "CPLX"):
                extra.append("COMPLEX" if w == "CPLX" else w)
            elif w in ("POINTER", "PTR"):
                other = "POINTER"
            elif w in ("OFFSET", "HANDLE", "AREA"):
                other = w + (f"({_text(arg)})" if arg else "")
            elif w in ("TASK", "EVENT"):
                other = w
            elif w == "LABEL":
                other, info["label"] = "LABEL", True
            elif w == "FORMAT" and not arg:
                other = "FORMAT"
            elif w == "ENTRY":
                other, info["entry"] = "ENTRY", True
            elif w == "FILE":
                other, info["file"] = "FILE", True
            elif w == "VARIABLE":
                info["variable"] = True
            elif w == "RETURNS":
                info["returns"] = True
            elif w == "OPTIONS":
                info["options"] = _text(arg) if arg else None
            elif w == "BUILTIN":
                info["skip"] = info["builtin"] = True
            elif w in ("CONDITION", "COND", "GENERIC"):
                info["skip"] = True
            elif w in ("DIM", "DIMENSION"):
                info["dim"] = arg
            elif w in ("INIT", "INITIAL"):
                if arg is not None:
                    info["init"] = _text(arg)
                elif nk < size and attrs[nk].u == "CALL":
                    stop = _ref_end(attrs, nk + 1)
                    info["init"] = _text(attrs[nk:stop])
                    nk = stop
                elif nk < size and attrs[nk].u == "TO":
                    stop = nk + 1
                    while stop < size and attrs[stop].t == "(":
                        stop = _match(attrs, stop, size) + 1
                    info["init"] = _text(attrs[nk:stop])
                    nk = stop
            elif w == "VALUE":
                if arg is not None:
                    info["init"] = _text(arg)
            elif w == "BASED":
                info["storage"] = "BASED"
                info["based"] = _text(arg) if arg else None
            elif w in ("DEFINED", "DEF"):
                info["storage"] = "DEFINED"
                if arg is not None:
                    info["defined"] = _text(arg)
                else:
                    stop = _ref_end(attrs, nk)
                    info["defined"] = _text(attrs[nk:stop]) or None
                    nk = stop
            elif w in _STORAGE:
                info["storage"] = _STORAGE[w]
            elif w in ("PARAMETER", "PARM"):
                info["parameter"] = True
            elif w in ("EXTERNAL", "EXT"):
                info["external"] = True
                if arg and arg[0].k == "s":
                    info["ext_name"] = _lit(arg[0].t).strip().upper()
            elif w == "LIKE":
                stop = _ref_end(attrs, nk)
                info["like"] = _ref_name(attrs[nk:stop])
                nk = stop
            elif w == "TYPE":
                if arg:
                    other = f"TYPE {_text(arg)}"
                elif nk < size and attrs[nk].k == "w":
                    other = f"TYPE {attrs[nk].u}"
                    nk += 1
            elif w == "ORDINAL":
                other = f"ORDINAL {_text(arg)}" if arg else "ORDINAL"
            elif w in _FILE_ATTRS:
                info["file_attrs"].append(_FILE_ATTR_CANON.get(w, w))
            elif w in ("ENV", "ENVIRONMENT"):
                info["env"] = _text(arg) if arg else ""
            k = nk
        typ = usage = None
        if info["pic"] is not None:
            typ = f"PIC '{info['pic']}'"
        elif strtype:
            typ = strtype + (f"({strlen})" if strlen else "") + (f" {varying}" if varying else "")
            usage = _STRING_USAGE[strtype]
        elif scale or base or prec:
            words = " ".join(x for x in (scale, base) if x) or "PRECISION"
            typ = words + (f"({prec})" if prec else "") + "".join(" " + x for x in extra)
            if scale == "FLOAT":
                usage = "FLOAT"
            elif scale == "FIXED" or (base and prec and "," in prec):  # a scale factor exists only for FIXED
                usage = "BINARY" if base == "BIN" else "PACKED-DECIMAL"
        elif other:
            typ = other
            if not other.startswith("TYPE"):
                usage = other.split("(")[0].split()[0]
        info["type"], info["usage"] = typ, usage
        return info

    def make_item(self, name: str, tok, level: int, dims: Optional[list], attrs: list, blk: Optional[_Blk],
                  stack: list) -> None:
        info = self.parse_attrs(attrs)
        if info["skip"]:
            return
        if info["file"] and not info["variable"]:
            self.declare_file(name, tok, info)
            return
        if info["entry"] and not info["variable"]:
            self.entries_decl.setdefault(name, {"ext": info["ext_name"] or name, "returns": info["returns"],
                                                "options": info["options"], "line": tok.line})
            return
        if info["entry"]:
            self.entry_vars.add(name)
        if info["label"]:
            self.label_vars.add(name)
        if dims is None and info["dim"] is not None:
            dims = info["dim"]
        dimensions, occurs = self.dimensions(dims) if dims is not None else (None, None)
        if level <= 1:
            stack.clear()
            parent = parent_index = None
            if (blk is not None and blk.kind == "procedure" and name in blk.params) or info["parameter"]:
                section = "PARAMETER"
            elif info["storage"]:
                section = info["storage"]
            elif info["external"] or blk is None or blk.kind == "package":
                section = "STATIC"
            else:
                section = "AUTOMATIC"
        else:
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent, parent_index = (stack[-1][1], stack[-1][2]) if stack else (None, None)
            section = stack[0][3] if stack else (info["storage"] or "AUTOMATIC")
        redefines = None
        if info["defined"]:
            redefines = _ref_name(self.retok(info["defined"]))
        elif info["based"]:
            inner = info["based"].replace(" ", "").upper()
            if inner.startswith("ADDR(") and inner.endswith(")"):
                redefines = _ref_name(self.retok(inner[5:-1]))
        src = self.sources[tok.src]
        item = {"level": level, "name": name, "pic": info["pic"], "usage": info["usage"], "occurs": occurs,
                "redefines": redefines, "value": info["init"], "section": section, "parent": parent,
                "parent_index": parent_index, "copybook": src.copybook, "file": src.file, "line": tok.line,
                "fd": None, "type": info["type"], "dimensions": dimensions, "based": info["based"],
                "defined": info["defined"], "like": info["like"], "external": info["external"], "block": None,
                "_blk": blk}
        if info["like"]:
            self.warn(tok, f"{name} takes its members from {info['like']} through the LIKE attribute; they are not repeated in the map")
        stack.append((level, name, len(self.items), section))
        self.items.append(item)

    @staticmethod
    def retok(text: str) -> list:
        return _lex([" " + text], (2, max(72, len(text) + 2)), 0)

    @staticmethod
    def dimensions(dims: list) -> Tuple[List[dict], dict]:
        out: List[dict] = []
        count: Optional[int] = 1
        depending = None
        refer_max: Optional[int] = None
        for group in _split_list(dims):
            refer = None
            bound: list = []
            k = 0
            while k < len(group):
                if group[k].k == "w" and group[k].u == "REFER" and k + 1 < len(group) and group[k + 1].t == "(":
                    close = _match(group, k + 1, len(group))
                    refer = _ref_name(group[k + 2:close])
                    k = close + 1
                    continue
                bound.append(group[k])
                k += 1
            colon = next((m for m, x in enumerate(bound) if x.t == ":"), None)
            lower = _int(_text(bound[:colon])) if colon is not None else 1
            upper = _int(_text(bound[colon + 1:] if colon is not None else bound))
            out.append({"lower": lower, "upper": upper})
            if refer and depending is None:
                depending = refer
                refer_max = upper if isinstance(upper, int) else None
            if isinstance(lower, int) and isinstance(upper, int) and count is not None and not refer:
                count *= max(upper - lower + 1, 0)
            else:
                count = None
                if depending is None and not isinstance(upper, int) and upper not in ("*", ""):
                    depending = upper
        occurs = {"min": count, "max": count if count is not None else refer_max,
                  "depending_on": depending if count is None else None, "keys": [], "indexed_by": []}
        return out, occurs

    def declare_file(self, name: str, tok, info: dict) -> None:
        if name in self.files:
            self.warn(tok, f"file {name} is declared again; the map keeps the first declaration "
                           f"(line {self.files[name]['line']})")
            return
        env = info["env"]
        org = None
        if env:
            words = {x.u for x in self.retok(env) if x.k == "w"}
            org = next((o for o in _ORGANIZATIONS if o in words), None)
        rec = {"name": name, "assign": None, "organization": org, "access": None, "record": None, "io": [],
               "dd": None, "status": None, "keys": [], "records": [], "line": tok.line, "kind": "FILE",
               "attributes": list(dict.fromkeys(info["file_attrs"])), "env": env, "title": None,
               "transmission": None, "declared": True, "handlers": []}
        rec.update(self.where(tok))
        self.files[name] = rec

    # ---- after the parse
    def resolve_proc(self, name: str, blk: Optional[_Blk]) -> Optional[_Blk]:
        b = blk
        while b is not None:
            if name in b.procs:
                return b.procs[name]
            if b.kind == "procedure" and (b.name == name or name in b.aliases):
                return b
            b = b.parent
        return self.top_procs.get(name) or self.entry_map.get(name)

    def literal_values(self, name: str) -> List[str]:
        out: List[str] = []
        for item in self.items:
            v = item.get("value")
            if item["name"] == name and v and v[:1] in ("'", '"'):
                out.append(_lit(v).strip().upper())
        for v in self.assign_lits.get(name, []):
            if v not in out:
                out.append(v)
        return out

    def external_name(self, name: str) -> str:
        decl = self.entries_decl.get(name)
        return decl["ext"] if decl else name

    def finish(self, path: Path, margins: Tuple[int, int]) -> dict:
        file_rel = self.sources[0].file
        externals = [b for b in self.blocks if b.kind == "procedure" and b.external]
        mains = [b for b in externals if b.main]
        idb = mains[0] if mains else (externals[0] if externals else None)
        if len(mains) > 1:
            self.warn(None, f"{len(mains)} procedures have OPTIONS(MAIN) ({', '.join(b.name for b in mains)}); "
                            f"the map uses {idb.name}")
        if len(externals) > 1:
            self.warn(None, f"{len(externals)} external procedures in one file; mapped as one program with id "
                            f"{idb.name}, the others are paragraphs with external: true")
        if idb is None:
            self.warn(None, "no PROCEDURE statement found; the file is mapped under its member name")
        self.idb = idb
        # paragraph names: a procedure name used again in another scope is qualified by its parent
        counts: Dict[str, int] = {}
        for b in self.blocks:
            if self.is_paragraph(b):
                counts[b.name] = counts.get(b.name, 0) + 1
        taken: Set[str] = set()
        for b in self.blocks:
            if not self.is_paragraph(b):
                continue
            name = b.name
            if counts[name] > 1 and name in taken:
                parent = self.para_name(b.parent)
                name = f"{parent}.{b.name}" if parent and f"{parent}.{b.name}" not in taken else f"{b.name}-{b.line}"
            taken.add(name)
            self.display[b] = name
        data_names = {i["name"] for i in self.items if i["name"] != "FILLER"}
        for b in self.blocks:
            data_names.update(b.params)

        # calls: FETCH first, so that a CALL of a fetched entry is known to be dynamic
        fetched: Dict[str, List[str]] = {}
        for rc in self.raw_calls:
            if rc["form"] != "FETCH":
                continue
            title = rc.get("title")
            if title and len(title) == 1 and title[0].k == "s":
                cands = [_lit(title[0].t).strip().upper()]
            elif title:
                cands = self.literal_values(_ref_name(title) or "")
            else:
                cands = [self.external_name(rc["name"])]
            fetched.setdefault(rc["name"], [])
            for c in cands:
                if c and c not in fetched[rc["name"]]:
                    fetched[rc["name"]].append(c)
        for rc in self.raw_calls:
            ctx, t, rec = rc["ctx"], rc["tok"], rc["rec"]
            name = rc["name"]
            if rc["form"] == "CALL" and not rc["qualified"] and name not in self.entry_vars:
                target = self.resolve_proc(name, ctx.blk)
                if target is not None:
                    self.add_perform(target, name, t, rec, ctx)
                    continue
                if name in _BUILTIN_SUBROUTINES and name not in self.entries_decl:
                    continue
            self.add_call(rc["form"], name, rc["ref"] if rc["qualified"] else None, rc["args"], t, rec, ctx, fetched)

        # function references in expressions: internal procedures and external entries with RETURNS
        seen_refs: Set[Tuple[int, str]] = set()
        warned_macros: Set[str] = set()
        for a, b, ctx, owner in self.expr_spans:
            for k in range(a, min(b, self.n)):
                t = self.toks[k]
                if t.k != "w" or (k > 0 and self.toks[k - 1].t in (".", "->", "=>")):
                    continue
                name = t.u
                key = (id(owner), name)
                follows = k + 1 < self.n and self.toks[k + 1].t == "("
                if name in self.loader.macro_procs and name not in warned_macros:
                    warned_macros.add(name)
                    self.warn(t, f"{name} is a preprocessor procedure, which is not evaluated; the expression "
                                 "is mapped as written")
                    continue
                if key in seen_refs or name in data_names:
                    continue
                target = self.resolve_proc(name, ctx.blk)
                if target is not None and (target.returns or follows):
                    seen_refs.add(key)
                    pr = self.add_perform(target, name, t, owner, ctx)
                    pr["function"] = True
                elif name in self.entries_decl and self.entries_decl[name]["returns"]:
                    seen_refs.add(key)
                    self.add_call("FUNCTION", name, None, [], t, owner, ctx, fetched)

        self.compute_loops()
        for c in self.conditions:
            owner = c.pop("_owner", None)
            c["in_loop"] = owner.get("in_loop") if owner else None
            names: List[str] = []
            for x in list(c.pop("_extra", [])) + c.pop("_toks", []):
                if x.k == "w" and x.u in data_names and x.u not in names:
                    names.append(x.u)
            c["data_items"] = names
        self.build_files()
        self.check_gotos()

        paragraphs = []
        for b in self.blocks:
            if b is idb or b.kind == "package":
                continue
            p = {"name": self.para_name(b), "section": None, "start_line": b.line, "end_line": b.end_line,
                 "kind": b.kind, "parent": self.para_name(b.parent)}
            if b.kind == "procedure":
                p["external"] = b.external
                p["params"] = list(b.params)
            cb = self.sources[b.src].copybook
            if cb:
                p["copybook"] = cb
            paragraphs.append(p)
        entries = []
        for b in externals:
            for alias in [b.name] + b.aliases:
                entries.append({"name": alias, "line": b.line, "kind": "procedure", "main": b.main})
        for name, tok, proc in self.entry_stmts:
            if proc is not None and proc.external:
                entries.append({"name": name, "line": tok.line, "kind": "entry", "main": False})

        for group in (self.statements, self.performs, self.calls, self.gotos, self.sql, self.cics, self.conditions,
                      self.labels, self.items):
            for rec in group:
                blk = rec.get("_blk")
                if "paragraph" in rec:
                    rec["paragraph"] = self.para_name(blk)
                if "from" in rec:
                    rec["from"] = self.para_name(blk)
                if "block" in rec:
                    rec["block"] = self.para_name(blk)
                if rec.get("_target") is not None:
                    target = rec["_target"]
                    rec["to"] = self.para_name(target) if self.is_paragraph(target) else target.name
                for key in _PRIVATE:
                    rec.pop(key, None)
        files = list(self.files.values())
        for f in files:
            for io in f["io"]:
                io["paragraph"] = self.para_name(io.pop("_blk", None))
            for h in f["handlers"]:
                h["paragraph"] = self.para_name(h.pop("_blk", None))
                h.pop("_src", None)

        sql_cursors = {s["cursor"]: s["tables"] for s in self.sql if s["verb"] == "DECLARE CURSOR" and s["cursor"]}
        for s in self.sql:
            if s["cursor"] and not s["tables"] and s["cursor"] in sql_cursors:
                s["tables"] = list(sql_cursors[s["cursor"]])
        for c in self.cics:
            prog = c["options"].get("program")
            if isinstance(prog, str) and prog[:1] not in ("'", '"'):
                c["candidates"] = self.literal_values(prog.upper())

        copybooks = [dict(cb) for cb in self.loader.copybooks]
        warnings: List[dict] = []
        for w in self.loader.warnings + self.loader.pp_warnings() + self.warnings:
            if w not in warnings:
                warnings.append(w)
        text = zscan.read_text(path)
        return {
            "id": idb.name if idb is not None else zscan.member_name(path),
            "language": LANGUAGE,
            "file": file_rel,
            "sha256": zscan.sha256_file(path),
            "format": "fixed",
            "margins": [margins[0], margins[1]],
            "member": zscan.member_name(path),
            "lines": len(text.splitlines()),
            "partial": any(cb["resolved"] is None for cb in copybooks),
            "copybooks": copybooks,
            "files": files,
            "data_items": self.items,
            "paragraphs": paragraphs,
            "sections": [],
            "performs": self.performs,
            "calls": self.calls,
            "gotos": self.gotos,
            "sql": self.sql,
            "cics": self.cics,
            "conditions": self.conditions,
            "statements": self.statements,
            "procedure_using": list(idb.params) if idb is not None else [],
            "procedure_using_line": idb.params_line if idb is not None else None,
            "sql_includes": list(self.loader.sql_includes),
            "entries": entries,
            "labels": self.labels,
            "warnings": warnings,
        }

    def is_paragraph(self, blk: _Blk) -> bool:
        return blk is not self.idb and blk.kind != "package"

    def para_name(self, blk: Optional[_Blk]) -> Optional[str]:
        while blk is not None and not self.is_paragraph(blk):
            blk = blk.parent
        return self.display.get(blk, blk.name) if blk is not None else None

    def add_perform(self, target: _Blk, name: str, t, owner: dict, ctx: _Ctx) -> dict:
        pr = {"from": None, "to": target.name, "thru": None, "loop": None, "inline": False, "line": t.line,
              "end_line": owner["end_line"] if owner.get("_src", t.src) == t.src else t.line, "in_loop": ctx.loop}
        if name != target.name:
            pr["entry"] = name
        pr.update(self.where(t))
        pr.update({"_blk": ctx.blk, "_target": target, "_src": t.src})
        self.performs.append(pr)
        return pr

    def add_call(self, form: str, name: str, ref: Optional[str], args: List[str], t, owner: dict, ctx: _Ctx,
                 fetched: Dict[str, List[str]]) -> None:
        dynamic = form == "FETCH" or name in fetched or name in self.entry_vars or ref is not None
        c = {"target": ref or self.external_name(name), "dynamic": dynamic, "line": t.line, "paragraph": None,
             "using": list(args), "in_loop": ctx.loop, "form": form}
        if dynamic:
            if name in fetched:
                cands = list(fetched[name])
            elif name in self.entry_vars:
                cands = []
                for item in self.items:
                    value = self.retok(item["value"]) if item["name"] == name and item.get("value") else []
                    if value and value[0].k == "w":
                        cands.append(self.external_name(value[0].u))
                for w in self.assign_words.get(name, []):
                    cands.append(self.external_name(w))
            else:
                cands = []
            c["candidates"] = list(dict.fromkeys(cands))
        c.update(self.where(t))
        c["_blk"] = ctx.blk
        self.calls.append(c)

    def compute_loops(self) -> None:
        """in_loop of the blocks that calls reach from a loop: the nearest loop wins (fewest calls, then the
        latest loop line). Recursion is a warning; a loop made by recursion is not reported."""
        graph: Dict[_Blk, List[_Blk]] = {}
        for pr in self.performs:
            target = pr.get("_target")
            caller = pr["_blk"].runs_in() if pr.get("_blk") is not None else None
            if target is None or caller is None:
                continue
            graph.setdefault(caller, [])
            if target not in graph[caller]:
                graph[caller].append(target)
        cyclic = sorted({self.para_name(b) or b.name for comp in _sccs(graph) for b in comp
                         if len(comp) > 1 or b in graph.get(b, [])})
        if cyclic:
            names = ", ".join(cyclic[:20]) + (f" and {len(cyclic) - 20} more" if len(cyclic) > 20 else "")
            self.warn(None, f"recursive calls among {names}: a loop made by recursion is not reported as in_loop")
        heap: list = []
        for seq, pr in enumerate(self.performs):
            target, loop = pr.get("_target"), pr.get("in_loop")
            if target is not None and loop:
                heapq.heappush(heap, (0, -loop["via"], seq, target, loop))
        seq = len(self.performs)
        best: Dict[_Blk, dict] = {}
        while heap:
            dist, neg_via, _, blk, loop = heapq.heappop(heap)
            if blk in best:
                continue
            best[blk] = loop
            for nb in graph.get(blk, []):
                if nb not in best:
                    seq += 1
                    heapq.heappush(heap, (dist + 1, neg_via, seq, nb, loop))
        for group in (self.statements, self.calls, self.sql, self.cics, self.performs):
            for rec in group:
                blk = rec.get("_blk")
                if rec.get("in_loop") is None and blk is not None and blk.runs_in() in best:
                    rec["in_loop"] = best[blk.runs_in()]

    def build_files(self) -> None:
        for io in self.raw_io:
            self.file_rec(io["file"])
        for h in self.handlers:
            self.file_rec(h["file"])
        for io in self.raw_io:
            f = self.files[io["file"]]
            rec = io["rec"]
            mode = io["mode"]
            if io["verb"] == "OPEN" and mode is None:
                mode = next((m for m in ("INPUT", "OUTPUT", "UPDATE") if m in f["attributes"]), None)
                if mode is None and "PRINT" in f["attributes"]:
                    mode = "OUTPUT"  # PRINT implies STREAM OUTPUT
            entry = {"verb": io["verb"], "line": rec["line"], "paragraph": None, "in_loop": rec["in_loop"]}
            if mode:
                entry["mode"] = mode
            if rec.get("copybook"):
                entry["copybook"] = rec["copybook"]
            entry["_blk"] = io["ctx"].blk
            f["io"].append(entry)
            for r in io["records"]:
                if r and r not in f["records"]:
                    f["records"].append(r)
            for k in io["keys"]:
                if k and k not in f["keys"]:
                    f["keys"].append(k)
            if io["verb"] == "OPEN" and io["title"]:
                f.setdefault("_titles", []).append(io["title"])
            for a in io["attrs"]:
                if a not in f["attributes"]:
                    f.setdefault("_open_attrs", []).append(a)
            for h in self.handlers:
                if h["file"] != io["file"] or io["verb"] not in _CONDITION_VERBS.get(h["condition"], set()):
                    continue
                if h["condition"] == "KEY" and not io["keys"]:
                    continue
                phrase = {"kind": f"ON {h['condition']}", "line": h["line"]}
                if h.get("copybook"):
                    phrase["copybook"] = h["copybook"]
                phrases = rec.setdefault("phrases", [])
                if phrase not in phrases:
                    phrases.append(phrase)
        for h in self.handlers:
            entry = {"condition": h["condition"], "line": h["line"], "end_line": h["end_line"], "unit": h["unit"],
                     "_blk": h["_blk"]}
            if h.get("copybook"):
                entry["copybook"] = h["copybook"]
            self.files[h["file"]]["handlers"].append(entry)
        for f in self.files.values():
            verbs = {x["verb"] for x in f["io"]}
            attrs = set(f["attributes"]) | set(f.pop("_open_attrs", []))
            if "RECORD" in attrs or verbs & {"READ", "WRITE", "REWRITE", "DELETE", "LOCATE"}:
                f["transmission"] = "RECORD"
            elif attrs & {"STREAM", "PRINT"} or verbs & {"GET", "PUT"}:
                f["transmission"] = "STREAM"
            if "DIRECT" in attrs:
                f["access"] = "DIRECT"
            elif "SEQUENTIAL" in attrs or f["transmission"] == "RECORD":
                f["access"] = "SEQUENTIAL"  # the PL/I default for RECORD files
            f["record"] = f["records"][0] if f["records"] else None
            titles = f.pop("_titles", [])
            if titles:
                first = titles[0]
                f["assign"] = f["title"] = _text(first)
                if len(first) == 1 and first[0].k == "s":
                    value = _lit(first[0].t).strip()
                    f["dd"] = value.upper() if value and not value.startswith("/") else None
                else:
                    self.warn(None, f"file {f['name']}: TITLE({f['assign']}) is chosen at run time; DD name unknown")
                if len({_text(x) for x in titles}) > 1:
                    self.warn(None, f"file {f['name']} is opened with several TITLEs; dd is the first one")
            elif len(f["name"]) <= 8:
                f["dd"] = f["name"]
            else:
                self.warn(None, f"file {f['name']}: the name is longer than 8 characters and no TITLE is given; "
                                "the DD name is not known")

    def file_rec(self, name: str) -> dict:
        if name not in self.files:
            self.files[name] = {"name": name, "assign": None, "organization": None, "access": None, "record": None,
                                "io": [], "dd": None, "status": None, "keys": [], "records": [], "line": None,
                                "kind": "FILE", "attributes": [], "env": None, "title": None, "transmission": None,
                                "declared": False, "handlers": []}
        return self.files[name]

    def check_gotos(self) -> None:
        by_name: Dict[str, List[dict]] = {}
        for lab in self.labels:
            by_name.setdefault(lab["name"], []).append(lab)
        procs = {b.name for b in self.blocks}
        for g in self.gotos:
            loop = g.get("_loop")
            for name in g["to"]:
                if name in by_name:
                    if not loop:
                        continue
                    rng = self.loop_ranges.get((loop["file"], loop["via"]))
                    if rng is None:
                        continue
                    src, start, end = rng
                    inside = any(lab["_src"] == src and start <= lab["line"] <= end for lab in by_name[name])
                    if not inside:
                        self.warnings.append({"file": loop["file"], "line": g["line"],
                                              "message": f"GO TO {name} at line {g['line']} leaves the DO loop at "
                                                         f"line {loop['via']}; in_loop does not follow GO TO"})
                elif name in self.label_vars:
                    self.warnings.append({"file": self.sources[g["_src"]].file, "line": g["line"],
                                          "message": f"GO TO {name}: a LABEL variable, the target is chosen at run "
                                                     "time; flow not followed"})
                elif name not in procs:
                    self.warnings.append({"file": self.sources[g["_src"]].file, "line": g["line"],
                                          "message": f"GO TO target {name} is not a label in this program"})


def _sccs(graph: Dict[Any, List[Any]]) -> List[List[Any]]:
    """Strongly connected components of a call graph (Tarjan, iterative)."""
    index: Dict[Any, int] = {}
    low: Dict[Any, int] = {}
    on_stack: Set[Any] = set()
    stack: List[Any] = []
    out: List[List[Any]] = []
    for root in list(graph):
        if root in index:
            continue
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(graph.get(root, [])))]
        while work:
            node, neighbours = work[-1]
            advanced = False
            for nb in neighbours:
                if nb not in index:
                    index[nb] = low[nb] = len(index)
                    stack.append(nb)
                    on_stack.add(nb)
                    work.append((nb, iter(graph.get(nb, []))))
                    advanced = True
                    break
                if nb in on_stack:
                    low[node] = min(low[node], index[nb])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w is node:
                        break
                out.append(comp)
    return out


# --------------------------------------------------------------------------- public interface
def classify(path, text: str) -> str:
    """program (an external procedure or package), include (a member to %INCLUDE) or skip (not PL/I).

    A file with OPTIONS(MAIN), a PACKAGE or *PROCESS options and a PROCEDURE is a program
    whatever its extension. Otherwise an include extension (.inc, .cpy...) means include, and
    a PROCEDURE statement means program. PL/I statements without one make an include member;
    text with no PL/I statement is skipped.
    """
    p = Path(path)
    lines = text.splitlines()
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    if first.startswith("/*") and "REXX" in first.upper():
        return "skip"
    margins, skip, _ = _process_options(lines)
    loader = _Loader(None, p.parent, margins)
    loader.sources.append(_Source(p, p.name, None))
    toks = loader.expand(_lex(lines, margins, 0, skip), (), p)
    has_proc = main = package = plish = False
    i, n = 0, len(toks)
    while i < n:
        j, labels = _skip_labels(toks, i, n)
        semi = _next_semi(toks, j)
        if semi >= n:
            break
        if j < semi and toks[j].k == "w":
            w = toks[j].u
            if w in ("PROC", "PROCEDURE") and labels:
                has_proc = True
                opts = _options(toks[j + 1:semi])
                main = main or any(x.u == "MAIN" for x in (opts.get("OPTIONS") or []))
            elif w == "PACKAGE":
                package = True
            elif w in _PLI_KEYWORDS or _is_assignment(toks, j, semi):
                plish = True
        i = semi + 1
    if main or package or (has_proc and skip):
        return "program"
    if p.suffix.lower() in INCLUDE_EXT:
        return "include" if (has_proc or plish) else "skip"
    if has_proc:
        return "program"
    return "include" if plish else "skip"


def scan_program(path, include_dirs=(), root: Optional[Path] = None) -> dict:
    """One program record (app-map.json contract version 1, language "pli") for a PL/I source file.

    include_dirs: folders (or files) searched for %INCLUDE members, relative to root or
    absolute, or an IncludeIndex built once for many programs. The program's own folder is
    searched only when it is listed; %INCLUDE 'path' is read relative to the including file.
    root: the project root (default: the current directory); paths in the record are
    relative to it, or absolute outside it. Raises OSError when the file cannot be read.
    """
    base = zscan.project_root(root)
    p = Path(path)
    if not p.is_absolute():
        p = base / p
    if isinstance(include_dirs, IncludeIndex):
        index = include_dirs
    else:
        if isinstance(include_dirs, (str, Path)):
            include_dirs = [include_dirs]
        index = IncludeIndex.cached(list(include_dirs), base)
    lines = zscan.read_text(p).splitlines()
    margins, skip, problem = _process_options(lines)
    loader = _Loader(index, base, margins)
    toks = loader.load(p, None, skip)
    if problem:
        loader.warn(loader.sources[0].file, min(skip) if skip else None, problem)
    toks = loader.expand(toks, (zscan.member_name(p),), p)
    parser = _Parser(toks, loader)
    parser.parse()
    return parser.finish(p, margins)
