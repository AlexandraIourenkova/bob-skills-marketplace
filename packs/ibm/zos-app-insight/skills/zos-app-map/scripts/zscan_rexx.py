#!/usr/bin/env python3
"""zscan_rexx: REXX execs as programs of the zos-app-insight map (a zscan language module).

zscan.py calls this module for REXX files. It uses only the standard library and zscan's
public helpers, has no import-time side effects, reads only the files it is given and the
members its %INCLUDE directives name, and writes nothing.

  LANGUAGE = "rexx"
  classify(path, text) -> "program" | "include" | "skip"
  scan_program(path, include_dirs=(), root=None) -> dict      one program record

classify:
  "program"  a REXX exec. The REXX marker is the word REXX in a comment before the first
             clause (TSO wants it on line 1 for SYSPROC; a .rexx/.rex/.exec file is REXX
             without it, as in SYSEXEC).
  "include"  a member of routines meant for the REXX compiler's /*%INCLUDE*/ directive:
             it starts with a label, has RETURN and no EXIT; or it holds only %INCLUDE
             directives and comments.
  "skip"     a CLIST: a .clist file without the REXX marker, or text without it whose
             first statement is PROC n or that has CONTROL or SET &name statements.

The program record has every key of contract version 1 (references/map-format.md):
  id            member name (file stem, upper case); format "free"; lines; sha256; file.
  copybooks     /*%INCLUDE member*/ and /*%INCLUDE dd(member)*/ compiler directives, in the
                COBOL copybook shape {name, library, resolved, replacing: false, line,
                nested_in, replacing_pairs: []}. The member's text is expanded as the
                compiler does (records from it carry `copybook`); the interpreter treats
                the directive as a comment, and a warning says so.
  files         one entry per DD the exec allocates, frees or reads and writes with EXECIO:
                {name, assign, dd, kind: "DD", organization: null, access ("SEQUENTIAL"
                when EXECIO uses it, else null), record: null, records: [], keys: [],
                status: null, line, io, dsns}. A DD name held in a variable gives
                name "{VAR}", dd null, dynamic: true and candidates (literal values).
                io: {verb ("EXECIO", "ALLOC", "FREE"), line, end_line, paragraph,
                in_loop, mode (DISKR, DISKRU, DISKW: EXECIO only), count, stem, options
                (FINIS, OPEN, SKIP, LIFO, FIFO), linenum, dsn [as written], disp (SHR,
                OLD, MOD, NEW), changes, via ("BPXWDYN"), copybook}; absent keys mean
                "not given".
  data_items    [] (REXX has no declarations; see `variables`).
  paragraphs    labels {name, section: null, start_line, end_line, procedure, expose}.
  sections      [].
  performs      CALL of an internal label and function calls of an internal label:
                {from, to, thru: null, loop: null, inline: false, line, end_line,
                in_loop, via ("CALL" or "function"), using: [arguments as written]}.
  calls         routines outside the exec and programs it runs: {target, dynamic, line,
                paragraph, using, in_loop, via}; via is "CALL", "function", "LINKMVS",
                "ATTCHMVS", "LINKPGM", "ATTCHPGM", "LINK", "ATTACH", "TSO CALL",
                "TSO EXEC", "TSO %", "ISPEXEC SELECT PGM" or "ISPEXEC SELECT CMD".
                Optional: library (data set of TSO CALL or EXEC), candidates (literal
                values of the variable of a dynamic target), system: true for routines
                z/OS supplies (BPXWDYN, SYSCALLS, RXSUBCOM...). Built-in functions and
                the TSO/E external functions (LISTDSI, OUTTRAP, SYSDSN...) are not calls.
  gotos         SIGNAL label: {to: [label], line, paragraph, depending_on: null};
                SIGNAL VALUE expr: {to: [], depending_on: "expr"} and a warning.
  sql           ADDRESS DSNREXX "EXECSQL ...": the 1.0 SQL record {line, end_line,
                paragraph, verb, tables, cursor, host_vars, multi_row, text, in_loop} plus
                statement (S1 of PREPARE, EXECUTE, DECLARE C1 CURSOR FOR S1), sql_from
                (the variable after PREPARE ... FROM or EXECUTE IMMEDIATE), candidates
                [{line, text, verb, tables}] (literal values of that variable, unknown
                parts as {source}) and dynamic: true when `tables` come from candidates.
  cics          [].
  conditions    IF (with else_line), WHEN (subject: null, select_line), WHILE and UNTIL
                of DO loops: {kind, text, tokens, start_line, end_line, paragraph,
                data_items (the variables the condition reads), in_loop}.
  statements    {verb, line, end_line, paragraph, operands, in_loop}. verb is the keyword
                (SAY, PARSE, CALL, IF, DO, SELECT, SIGNAL, EXIT, RETURN, LEAVE...), ASSIGN
                for an assignment, or the host command environment for a command (TSO,
                MVS, ISPEXEC, ISREDIT, LINKMVS, ATTCHMVS, LINKPGM, DSNREXX, SYSCALL,
                CONSOLE, or the name an ADDRESS gives). A command statement also has
                command (its first word, TSO abbreviations expanded: ALLOC, DELETE,
                SUBMIT...; null when unknown), text (the command with parts the scanner
                cannot evaluate written {as in the source}), dynamic, address_line (the
                ADDRESS instruction that chose the environment; null for the TSO
                default), options (KEY(value) operands, keys lower case, flags true),
                datasets (data set names as written) and changes: true for commands that
                change data sets or submit or cancel jobs: TSO ALLOC NEW, DELETE, RENAME,
                SUBMIT, OUTPUT, CANCEL, HDELETE, RECEIVE; EXECIO DISKW; ISPEXEC LMMADD,
                LMMREP, LMMDEL, LMPUT, LMMOVE, LMCOPY, LMRENAME, LMMREN, LMCOMP, FTCLOSE,
                TBSAVE; ISREDIT SAVE, REPLACE, CREATE, MOVE; SYSCALL unlink, rmdir,
                rename, mkdir, write, writefile, chmod, chown, truncate, link, symlink.
                A DO statement has loop (its kind or null); a SELECT statement has
                otherwise_line; an ADDRESS statement that only switches environments has
                environment (null for ADDRESS VALUE, whose later commands get verb
                UNKNOWN). An assignment that calls BPXWDYN to allocate also gets datasets
                and changes. Records from an included member carry copybook.
  in_loop       {via, kind, file} or null: via is the line of the DO; kind is iterative
                (DO i = ...), times (DO expr), while, until or forever. A record is in a
                loop inside a repeating DO (the innermost wins) or in a label range
                reached through CALL or a function call from one (the nearest wins). A
                label range runs to the next label unless the routine ends with RETURN,
                EXIT or SIGNAL. SIGNAL is not followed.
  procedure_using       variables of the exec's first ARG or PARSE ARG before any label.
  procedure_using_line  its line, or null.
  sql_includes  [].
  warnings      {file, line, message}.

Added keys: language ("rexx"), variables [{name, kind ("stem" or "simple"), line,
set_by: [{how, line}], copybook?}] for every stem and every variable set by PARSE, ARG,
PULL, EXECIO, OUTTRAP or EXECSQL INTO; loops [{line, end_line, kind, control, text,
paragraph, in_loop, leave_lines, copybook?}]; traps [{condition, action (SIGNAL or CALL),
on, target, line, paragraph, resolved}] for SIGNAL ON and CALL ON; environments (the host
command environments used, in order of first use).

The scanner is a tokenizer plus heuristics, not the REXX interpreter. ADDRESS is followed in
text order (REXX restores it after an internal CALL), starting from TSO. A symbol that the
exec never assigns stands for its own name in upper case, as in REXX; RC, RESULT, SIGL,
SQL host variables, SYSxxx variables and every variable after an INTERPRET stay {unknown}.
Source text is data: nothing read from an exec is executed or followed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import zscan

LANGUAGE = "rexx"
MAX_INCLUDE_DEPTH = 12
REXX_SUFFIXES = {".rexx", ".rex", ".exec", ".clist"}
UNKNOWN_SUFFIXES = {"", ".txt", ".mbr"}

SYMBOL_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.!?_@#$\u00a2")
_OPERATORS = sorted({
    "\\==", "\u00ac==", "/==", ">>=", "<<=", "\\>>", "\\<<", "\u00ac>>", "\u00ac<<",
    "==", "\\=", "\u00ac=", "/=", "<>", "><", ">=", "<=", ">>", "<<", "\\>", "\\<", "\u00ac>", "\u00ac<",
    "||", "&&", "**", "//", "+", "-", "*", "/", "%", "|", "&", "=", "\\", "\u00ac", ">", "<",
}, key=len, reverse=True)

KEYWORDS = frozenset({
    "ADDRESS", "ARG", "CALL", "DO", "DROP", "ELSE", "END", "EXIT", "IF", "INTERPRET", "ITERATE",
    "LEAVE", "NOP", "NUMERIC", "OPTIONS", "OTHERWISE", "PARSE", "PROCEDURE", "PULL", "PUSH", "QUEUE",
    "RETURN", "SAY", "SELECT", "SIGNAL", "THEN", "TRACE", "UPPER", "WHEN",
})

BUILTINS = frozenset({
    "ABBREV", "ABS", "ADDRESS", "ARG", "B2X", "BITAND", "BITOR", "BITXOR", "C2D", "C2X", "CENTER",
    "CENTRE", "CHANGESTR", "CHARIN", "CHAROUT", "CHARS", "COMPARE", "CONDITION", "COPIES", "COUNTSTR",
    "D2C", "D2X", "DATATYPE", "DATE", "DBADJUST", "DBBRACKET", "DBCENTER", "DBLEFT", "DBRIGHT",
    "DBRLEFT", "DBRRIGHT", "DBTODBCS", "DBTOSBCS", "DBUNBRACKET", "DBVALIDATE", "DBWIDTH", "DELSTR",
    "DELWORD", "DIGITS", "ERRORTEXT", "EXTERNALS", "FIND", "FORM", "FORMAT", "FUZZ", "INDEX", "INSERT",
    "JUSTIFY", "LASTPOS", "LEFT", "LENGTH", "LINEIN", "LINEOUT", "LINES", "LINESIZE", "MAX", "MIN",
    "OVERLAY", "POS", "QUEUED", "RANDOM", "REVERSE", "RIGHT", "SIGN", "SOURCELINE", "SPACE", "STREAM",
    "STRIP", "SUBSTR", "SUBWORD", "SYMBOL", "TIME", "TRACE", "TRANSLATE", "TRUNC", "USERID", "VALUE",
    "VERIFY", "WORD", "WORDINDEX", "WORDLENGTH", "WORDPOS", "WORDS", "X2B", "X2C", "X2D", "XRANGE",
    # TSO/E external functions, always there under TSO/E
    "GETMSG", "LISTDSI", "MSG", "MVSVAR", "OUTTRAP", "PROMPT", "SETLANG", "STORAGE", "SYSCPUS",
    "SYSDSN", "SYSVAR", "TRAPMSG",
})
SYSTEM_ROUTINES = frozenset({"BPXWDYN", "BPXWUNIX", "SYSCALLS", "RXSUBCOM", "RXSOCKET", "SOCKET", "IRXEXCOM"})

PROGRAM_ENVS = ("LINKMVS", "ATTCHMVS", "LINKPGM", "ATTCHPGM", "LINK", "ATTACH")
TSO_NAMES = {
    "ALLOCATE": "ALLOC", "ALLOC": "ALLOC", "DEL": "DELETE", "DELETE": "DELETE", "REN": "RENAME",
    "RENAME": "RENAME", "SUB": "SUBMIT", "SUBMIT": "SUBMIT", "OUT": "OUTPUT", "OUTPUT": "OUTPUT",
    "EX": "EXEC", "EXEC": "EXEC", "HDEL": "HDELETE", "HDELETE": "HDELETE", "LISTD": "LISTDS",
    "LISTC": "LISTCAT", "LISTA": "LISTALC", "XMIT": "TRANSMIT",
}
TSO_CHANGES = {"DELETE", "RENAME", "SUBMIT", "OUTPUT", "CANCEL", "HDELETE", "RECEIVE"}
ISPEXEC_CHANGES = {"LMMADD", "LMMREP", "LMMDEL", "LMPUT", "LMMOVE", "LMCOPY", "LMRENAME", "LMMREN", "LMCOMP",
                   "FTCLOSE", "TBSAVE"}
ISREDIT_CHANGES = {"SAVE", "REPLACE", "CREATE", "MOVE"}
SYSCALL_CHANGES = {"UNLINK", "RMDIR", "RENAME", "MKDIR", "WRITE", "WRITEFILE", "CHMOD", "CHOWN", "TRUNCATE",
                   "FTRUNCATE", "LINK", "SYMLINK"}
TSO_COMMANDS = {  # names that ISPEXEC SELECT CMD() runs as TSO commands, not execs
    "ALLOC", "ALLOCATE", "FREE", "DELETE", "RENAME", "LISTDS", "LISTCAT", "LISTALC", "SUBMIT", "STATUS",
    "CANCEL", "OUTPUT", "SEND", "TIME", "PROFILE", "CALL", "EXEC", "EX", "TSO", "ISPF", "PDF", "ISPSTART",
}
DD_KEYS = {"F", "FI", "FIL", "FILE", "DD", "DDN", "DDNA", "DDNAM", "DDNAME"}
DSN_KEYS = {"DA", "DAT", "DATA", "DATAS", "DATASE", "DATASET", "DS", "DSN", "DSNA", "DSNAM", "DSNAME"}
DISPOSITIONS = ("SHR", "OLD", "MOD", "NEW")
TRAP_CONDITIONS = {"ERROR", "FAILURE", "HALT", "NOVALUE", "SYNTAX", "NOTREADY", "LOSTDIGITS"}
SET_BY_REXX = {"RC", "RESULT", "SIGL", "SQLCODE", "SQLSTATE", "SQLERRMC", "SQLERRP"}  # special variables
_HOST_VAR = re.compile(r":\s*([A-Za-z@#$!?_][A-Za-z0-9@#$!?_]*)")
_KEY_VALUE = re.compile(r"^([A-Za-z@#$][A-Za-z0-9@#$-]*)\((.*?)\)?$", re.S)
_FLAG = re.compile(r"^[A-Za-z@#$][A-Za-z0-9@#$-]*$")


# --------------------------------------------------------------------------- tokens
class _Tok:
    __slots__ = ("k", "t", "u", "line", "src", "blank")

    def __init__(self, k: str, t: str, line: int, src: int, blank: bool):
        self.k = k  # sym, str, op, ( ) , ; :, eol, inc (a %INCLUDE directive)
        self.t = t
        self.u = t.upper()
        self.line = line
        self.src = src
        self.blank = blank  # whitespace or a comment before the token

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"_Tok({self.k},{self.t!r},{self.line})"


def _normalise(text: str) -> str:
    return "\n".join(str(text).splitlines())


def _is_number(text: str) -> bool:
    body = text
    if len(body) > 1 and body[-1] in "eE":
        return False
    for ch in ("e", "E"):
        if ch in body:
            body, _, exp = body.partition(ch)
            if not exp.lstrip("+-").isdigit():
                return False
    digits = body.replace(".", "", 1)
    return bool(digits) and digits.isdigit()


def _tokenize(text: str, src: int) -> Tuple[List[_Tok], List[Tuple[int, str]]]:
    """Tokens of one file (line ends as eol tokens) and problems found [(line, message)]."""
    toks: List[_Tok] = []
    problems: List[Tuple[int, str]] = []
    n = len(text)
    i = 0
    line = 1
    blank = True
    while i < n:
        c = text[i]
        if c == "\n":
            toks.append(_Tok("eol", "", line, src, True))
            line += 1
            i += 1
            blank = True
            continue
        if c in " \t\f\v\r":
            blank = True
            i += 1
            continue
        if c == "/" and text.startswith("/*", i):
            start = line
            depth = 0
            j = i
            closed = False
            while j < n:
                if text.startswith("/*", j):
                    depth += 1
                    j += 2
                    continue
                if text.startswith("*/", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        closed = True
                        break
                    continue
                if text[j] == "\n":
                    line += 1
                j += 1
            if not closed:
                problems.append((start, "comment not closed before the end of the file"))
            body = text[i + 2:j - 2] if closed else text[i + 2:]
            head = body.lstrip()
            if head[:8].upper() == "%INCLUDE":
                toks.append(_Tok("inc", head[8:].strip(), start, src, True))
            i = j
            blank = True
            continue
        if c in "'\"":
            j = i + 1
            closed = False
            while j < n and text[j] != "\n":
                if text[j] == c:
                    if j + 1 < n and text[j + 1] == c:
                        j += 2
                        continue
                    j += 1
                    closed = True
                    break
                j += 1
            if not closed:
                problems.append((line, "string not closed on its line"))
            elif j < n and text[j] in "xXbB" and (j + 1 >= n or text[j + 1] not in SYMBOL_CHARS):
                j += 1
            toks.append(_Tok("str", text[i:j], line, src, blank))
            blank = False
            i = j
            continue
        if c in SYMBOL_CHARS:
            j = i
            while j < n and text[j] in SYMBOL_CHARS:
                j += 1
            word = text[i:j]
            if ((word[0].isdigit() or word[0] == ".") and word[-1] in "eE" and j + 1 < n and text[j] in "+-"
                    and text[j + 1].isdigit() and _is_number(word[:-1])):
                k = j + 1
                while k < n and text[k].isdigit():
                    k += 1
                word = text[i:k]
                j = k
            toks.append(_Tok("sym", word, line, src, blank))
            blank = False
            i = j
            continue
        if c in "(),;:":
            toks.append(_Tok(c, c, line, src, blank))
            blank = False
            i += 1
            continue
        for op in _OPERATORS:
            if text.startswith(op, i):
                toks.append(_Tok("op", op, line, src, blank))
                i += len(op)
                break
        else:
            toks.append(_Tok("op", c, line, src, blank))
            i += 1
        blank = False
    return _join_continuations(toks), problems


def _join_continuations(toks: List[_Tok]) -> List[_Tok]:
    """A comma that ends a line continues the clause on the next line; the comma becomes a blank."""
    out: List[_Tok] = []
    k = 0
    while k < len(toks):
        t = toks[k]
        if t.k == "," and k + 1 < len(toks) and toks[k + 1].k == "eol":
            k += 2
            if k < len(toks):
                toks[k].blank = True
            continue
        out.append(t)
        k += 1
    return out


def _str_value(text: str) -> Optional[str]:
    """Value of a REXX string token; None for hex and binary strings, which are not decoded."""
    if not text or text[0] not in "'\"":
        return None
    if text[-1] in "xXbB" and len(text) > 2 and text[-2] == text[0]:
        return None
    q = text[0]
    body = text[1:-1] if len(text) >= 2 and text[-1] == q else text[1:]
    return body.replace(q * 2, q)


def _join(toks: Sequence[_Tok]) -> str:
    """Tokens back to text, with one blank where the source had whitespace or a comment."""
    out = ""
    for k, t in enumerate(toks):
        if k and t.blank:
            out += " "
        out += t.t
    return out


def _match(toks: Sequence[_Tok], i: int) -> int:
    """Index of the ) that closes the ( at i, or the last index when it is not closed."""
    depth = 0
    for k in range(i, len(toks)):
        if toks[k].k == "(":
            depth += 1
        elif toks[k].k == ")":
            depth -= 1
            if depth == 0:
                return k
    return len(toks) - 1


def _split_commas(toks: Sequence[_Tok]) -> List[List[_Tok]]:
    parts: List[List[_Tok]] = [[]]
    depth = 0
    for t in toks:
        if t.k == "(":
            depth += 1
        elif t.k == ")":
            depth -= 1
        if t.k == "," and depth == 0:
            parts.append([])
        else:
            parts[-1].append(t)
    return parts


def _is_var(t: _Tok) -> bool:
    return t.k == "sym" and not (t.t[0].isdigit() or t.t[0] == ".")


def _stem(name: str) -> Optional[str]:
    return name.split(".", 1)[0] + "." if "." in name else None


# --------------------------------------------------------------------------- classify
def _leading_comments(text: str) -> Tuple[str, int]:
    """The text of the comments before the first token, and the offset of that token."""
    i, n = 0, len(text)
    parts: List[str] = []
    while i < n:
        if text[i] in " \t\r\n\f\v":
            i += 1
            continue
        if text.startswith("/*", i):
            depth, j = 0, i
            while j < n:
                if text.startswith("/*", j):
                    depth += 1
                    j += 2
                    continue
                if text.startswith("*/", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                    continue
                j += 1
            parts.append(text[i:j])
            i = j
            continue
        break
    return "\n".join(parts), i


def _looks_like_clist(text: str, start: int) -> bool:
    code = [ln.strip().upper() for ln in text[start:].splitlines() if ln.strip()]
    if not code:
        return False
    first = code[0].split()
    if first and first[0] == "PROC" and len(first) > 1 and first[1].isdigit():
        return True
    return any(ln.startswith("CONTROL ") or ln.startswith("SET &") or ln.startswith("SET&") for ln in code)


def classify(path, text) -> str:
    """What a REXX-like file is: "program" (an exec), "include" (a member for %INCLUDE) or "skip" (a CLIST)."""
    norm = _normalise(text)
    comments, start = _leading_comments(norm)
    marker = "REXX" in comments.upper()
    ext = Path(str(path)).suffix.lower()
    if not marker and (ext == ".clist" or _looks_like_clist(norm, start)):
        return "skip"
    toks, _ = _tokenize(norm, 0)
    code = [t for t in toks if t.k not in ("eol", "inc")]
    if not code:
        return "include" if any(t.k == "inc" for t in toks) else ("program" if marker else "skip")
    clauses = _split_clauses(toks)
    first = clauses[0] if clauses else None
    if first is not None and first.kind == "label":
        kinds = {c.kind for c in clauses}
        if "EXIT" not in kinds and "RETURN" in kinds:
            return "include"
    return "program"


# --------------------------------------------------------------------------- clauses
class _Clause:
    __slots__ = ("toks", "kind", "block")

    def __init__(self, toks: List[_Tok], kind: str):
        self.toks = toks
        self.kind = kind  # label, assign, command, or a keyword (IF, DO, THEN, ELSE, END...)
        self.block = 0

    @property
    def line(self) -> int:
        return self.toks[0].line

    @property
    def src(self) -> int:
        return self.toks[0].src

    @property
    def end_line(self) -> int:
        return max(t.line for t in self.toks if t.src == self.toks[0].src)


def _kind(toks: List[_Tok]) -> str:
    first = toks[0]
    if first.k == "sym" and len(toks) > 1 and toks[1].k == "op" and toks[1].t == "=":
        return "assign"
    if first.k == "sym" and first.u in KEYWORDS:
        return first.u
    return "command"


def _split_clauses(toks: Sequence[_Tok]) -> List[_Clause]:
    clauses: List[_Clause] = []

    def emit(ts: List[_Tok]) -> None:
        while ts:
            if len(ts) >= 2 and ts[0].k in ("sym", "str") and ts[1].k == ":":
                clauses.append(_Clause(ts[:2], "label"))
                ts = ts[2:]
                continue
            kind = _kind(ts)
            if kind in ("ELSE", "OTHERWISE", "THEN"):
                clauses.append(_Clause(ts[:1], kind))
                ts = ts[1:]
                continue
            if kind in ("IF", "WHEN"):
                depth, cut = 0, None
                for k in range(1, len(ts)):
                    x = ts[k]
                    if x.k == "(":
                        depth += 1
                    elif x.k == ")":
                        depth -= 1
                    elif depth <= 0 and x.k == "sym" and x.u == "THEN":
                        cut = k
                        break
                if cut is not None:
                    clauses.append(_Clause(ts[:cut], kind))
                    clauses.append(_Clause([ts[cut]], "THEN"))
                    ts = ts[cut + 1:]
                    continue
            clauses.append(_Clause(ts, kind))
            return

    cur: List[_Tok] = []
    for t in toks:
        if t.k in ("eol", ";", "inc"):
            if cur:
                emit(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        emit(cur)
    return clauses


# --------------------------------------------------------------------------- command text
def _atoms(toks: Sequence[_Tok]) -> List[Tuple[str, List[_Tok]]]:
    """Expression pieces at depth 0: ("op", [op]) or ("term", tokens of a string, symbol, call or group)."""
    out: List[Tuple[str, List[_Tok]]] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.k == "op":
            out.append(("op", [t]))
            i += 1
            continue
        if t.k == "(":
            j = _match(toks, i)
            out.append(("term", list(toks[i:j + 1])))
            i = j + 1
            continue
        if t.k in ("sym", "str") and i + 1 < len(toks) and toks[i + 1].k == "(" and not toks[i + 1].blank:
            j = _match(toks, i + 1)
            out.append(("term", list(toks[i:j + 1])))
            i = j + 1
            continue
        out.append(("term", [t]))
        i += 1
    return out


def _render(toks: Sequence[_Tok], assigned: Optional[set]) -> Tuple[str, List[Tuple[str, Optional[str]]]]:
    """The value of a concatenation expression as far as it is known.

    Strings give their value, constant symbols their text, a symbol the exec never assigns
    its own name in upper case (REXX semantics; `assigned` None means none is known).
    Anything else is written {as in the source}. Returns (text, unknown parts as
    [(source text, variable name or None)]).
    """
    groups: List[Tuple[str, List[_Tok]]] = []  # (joiner before the group, tokens)
    forced: Optional[str] = None  # "" after ||
    pending = False  # an operator waits for its right operand
    for kind, ts in _atoms(toks):
        if kind == "op":
            if ts[0].t == "||":
                forced, pending = "", False
                continue
            if groups and forced is None:
                groups[-1][1].extend(ts)  # a binary operator, or a prefix one after another operator
            else:
                groups.append((forced or "", list(ts)))  # a prefix operator starts a new group
                forced = None
            pending = True
            continue
        if pending:
            groups[-1][1].extend(ts)
            pending = False
            continue
        if groups:
            groups.append((forced if forced is not None else (" " if ts[0].blank else ""), list(ts)))
        else:
            groups.append(("", list(ts)))
        forced = None
    text = ""
    unknown: List[Tuple[str, Optional[str]]] = []
    for k, (join, ts) in enumerate(groups):
        if k:
            text += join
        piece: Optional[str] = None
        if len(ts) == 1:
            t = ts[0]
            if t.k == "str":
                piece = _str_value(t.t)
            elif t.k == "sym" and not _is_var(t):
                piece = t.t
            elif (t.k == "sym" and assigned is not None and "." not in t.t and t.u not in assigned
                  and not t.u.startswith("SYS")):  # LISTDSI and other TSO/E functions set SYSxxx variables
                piece = t.u
        if piece is None:
            src = _join(ts)
            name = ts[0].u if len(ts) == 1 and _is_var(ts[0]) else None
            unknown.append((src, name))
            piece = "{" + src + "}"
        text += piece
    return text, unknown


def _cmd_words(text: str) -> List[str]:
    """Words of a command: blanks split them outside quotes, parentheses and {unknown} parts."""
    words: List[str] = []
    cur = ""
    depth = 0
    brace = 0
    quote: Optional[str] = None
    for ch in text:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if brace:
            cur += ch
            brace += {"{": 1, "}": -1}.get(ch, 0)
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "{":
            brace = 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch in " \t" and depth == 0:
            if cur:
                words.append(cur)
            cur = ""
            continue
        cur += ch
    if cur:
        words.append(cur)
    return words


def _values(inside: str) -> List[str]:
    """Items of a parenthesised operand: DA('A.B' 'C.D') gives two."""
    return [w for w in _cmd_words(inside.replace(",", " ")) if w]


def _options(words: Sequence[str]) -> Tuple[Dict[str, object], List[str]]:
    """KEY(value) operands and bare flags (keys lower case), and the positional operands."""
    options: Dict[str, object] = {}
    positional: List[str] = []
    for w in words:
        m = _KEY_VALUE.match(w)
        if m and "(" in w:
            options.setdefault(m.group(1).lower(), m.group(2).strip())
        elif _FLAG.match(w):
            options.setdefault(w.lower(), True)
        else:
            positional.append(w)
    return options, positional


def _placeholder(word: str) -> bool:
    return word.startswith("{") and word.endswith("}")


def _member_of(spec: str) -> Tuple[Optional[str], Optional[str]]:
    """'LIB.NAME(MEMBER)' or *(MEMBER) or LIB(MEMBER) -> (member, library as written)."""
    s = spec.strip()
    if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
        s = s[1:-1]
    if "(" in s and s.endswith(")"):
        lib, _, rest = s.partition("(")
        member = rest[:-1].strip()
        member = member if _placeholder(member) else member.upper()
        return member or None, (lib.strip() or None) if lib.strip() != "*" else None
    return None, s or None


# --------------------------------------------------------------------------- includes
class _Source:
    __slots__ = ("path", "file", "copybook")

    def __init__(self, path: Path, file: str, copybook: Optional[str]):
        self.path, self.file, self.copybook = path, file, copybook


class _IncludeIndex:
    """Members by name, from the include folders and the exec's own folder."""

    def __init__(self, folders: Sequence[Path], program: Path):
        self.by_name: Dict[str, List[Tuple[Path, int]]] = {}
        files = list(zscan.iter_source_files(folders))
        try:
            files += sorted(p for p in program.parent.iterdir() if p.is_file() and not p.name.startswith("."))
        except OSError:
            pass
        seen = set()
        for order, p in enumerate(files):
            real = os.path.realpath(p)
            if real in seen:
                continue
            seen.add(real)
            self.by_name.setdefault(zscan.member_name(p), []).append((p, order))

    def resolve(self, name: str, library: Optional[str], from_file: Path) -> Optional[Path]:
        found = self.by_name.get(name.upper())
        if not found:
            return None
        here = os.path.realpath(from_file.parent).split(os.sep)

        def score(item: Tuple[Path, int]):
            path, order = item
            parts = os.path.realpath(path.parent).split(os.sep)
            lib = 0 if library and any(p.upper() == library.upper() for p in parts) else 1
            ext = path.suffix.lower()
            rank = 0 if ext in REXX_SUFFIXES else (1 if ext in UNKNOWN_SUFFIXES else 2)
            common = 0
            for a, b in zip(here, parts):
                if a != b:
                    break
                common += 1
            return (lib, rank, -common, order)

        return sorted(found, key=score)[0][0]


def _include_spec(text: str) -> Tuple[Optional[str], Optional[str]]:
    """%INCLUDE member or %INCLUDE dd(member) -> (member, dd)."""
    words = text.split()
    if not words:
        return None, None
    spec = words[0].strip("'\"")
    if "(" in spec:
        lib, _, rest = spec.partition("(")
        member = rest.split(")")[0].strip()
        return (member.upper() or None), (lib.upper() or None)
    return spec.upper(), None


# --------------------------------------------------------------------------- the scan
class _Scan:
    def __init__(self, path: Path, include_dirs: Sequence, root: Optional[Path]):
        self.root = zscan.project_root(root)
        p = Path(path)
        self.path = p if p.is_absolute() else self.root / p
        self.file = zscan.rel(self.path, self.root)
        self.include_dirs = [Path(d) if Path(d).is_absolute() else self.root / d for d in include_dirs]
        self.sources: List[_Source] = [_Source(self.path, self.file, None)]
        self.copybooks: List[dict] = []
        self.warnings: List[dict] = []
        self._index: Optional[_IncludeIndex] = None
        self.clauses: List[_Clause] = []
        self.blocks: List[dict] = []
        self.statements: List[dict] = []
        self.performs: List[dict] = []
        self.calls: List[dict] = []
        self.gotos: List[dict] = []
        self.sql: List[dict] = []
        self.conditions: List[dict] = []
        self.loops: List[dict] = []
        self.traps: List[dict] = []
        self.variables: Dict[str, dict] = {}
        self.environments: List[str] = []
        self.assigned: Optional[set] = set()
        self.literals: Dict[str, List[Tuple[str, int, int, bool]]] = {}
        self.labels: Dict[str, int] = {}
        self.using: List[str] = []
        self.using_line: Optional[int] = None
        self._file_rows: Dict[str, dict] = {}
        self.block_statements: Dict[int, int] = {}
        self._sql_candidates: Dict[str, List[dict]] = {}

    # ---- helpers
    def warn(self, src: Optional[int], line: Optional[int], message: str) -> None:
        file = self.sources[src].file if src is not None else self.file
        rec = {"file": file, "line": line, "message": message}
        if rec not in self.warnings:
            self.warnings.append(rec)

    def where(self, src: int) -> dict:
        cb = self.sources[src].copybook
        return {"copybook": cb} if cb else {}

    def index(self) -> _IncludeIndex:
        if self._index is None:
            self._index = _IncludeIndex(self.include_dirs, self.path)
        return self._index

    # ---- pass 0: tokens with %INCLUDE members spliced in
    def load(self) -> List[_Tok]:
        text = _normalise(zscan.read_text(self.path))
        toks, problems = _tokenize(text, 0)
        for line, message in problems:
            self.warn(0, line, message)
        return self.expand(toks, (zscan.member_name(self.path),), self.path)

    def expand(self, toks: List[_Tok], stack: Tuple[str, ...], from_path: Path) -> List[_Tok]:
        out: List[_Tok] = []
        for t in toks:
            if t.k != "inc":
                out.append(t)
                continue
            name, library = _include_spec(t.t)
            out.append(_Tok("eol", "", t.line, t.src, True))
            if name is None:
                self.warn(t.src, t.line, "%INCLUDE without a member name")
                continue
            path = self.index().resolve(name, library, from_path)
            self.copybooks.append({
                "name": name, "library": library, "resolved": zscan.rel(path, self.root) if path else None,
                "replacing": False, "line": t.line, "nested_in": self.sources[t.src].copybook, "replacing_pairs": [],
            })
            if path is None:
                self.warn(t.src, t.line, f"%INCLUDE member {name} not found; its routines are missing from this map "
                                         "and calls to them count as external")
                continue
            key = zscan.member_name(path)
            if key in stack or len(stack) >= MAX_INCLUDE_DEPTH:
                chain = " -> ".join(stack + (key,))
                self.warn(t.src, t.line, f"%INCLUDE {name} not expanded: nesting loop or depth over "
                                         f"{MAX_INCLUDE_DEPTH} ({chain})")
                continue
            src = len(self.sources)
            self.sources.append(_Source(path, zscan.rel(path, self.root), name))
            inner, problems = _tokenize(_normalise(zscan.read_text(path)), src)
            for line, message in problems:
                self.warn(src, line, message)
            out.extend(self.expand(inner, stack + (key,), path))
            out.append(_Tok("eol", "", t.line, t.src, True))
        return out

    # ---- pass 1: labels and what the exec assigns
    def find_blocks(self) -> None:
        current: Optional[int] = None
        for c in self.clauses:
            if c.kind == "label":
                t = c.toks[0]
                name = t.u if t.k == "sym" else (_str_value(t.t) or t.t).upper()
                self.blocks.append({"name": name, "start_line": t.line, "end_line": t.line, "src": t.src,
                                    "procedure": False, "expose": [], "ends": False})
                current = len(self.blocks) - 1
                if name in self.labels:
                    first = self.blocks[self.labels[name]]
                    self.warn(t.src, t.line, f"label {name} also at line {first['start_line']} of "
                                             f"{self.sources[first['src']].file}; CALL and SIGNAL use the first")
                else:
                    self.labels[name] = current
            elif current is None:
                self.blocks.append({"name": None, "start_line": c.line, "end_line": c.line, "src": c.src,
                                    "procedure": False, "expose": [], "ends": False})
                current = 0
            c.block = current if current is not None else 0
            if c.kind != "label":
                b = self.blocks[c.block]
                if c.src == b["src"]:
                    b["end_line"] = max(b["end_line"], c.end_line)

    def collect_assignments(self) -> None:
        interpret = False
        self.assigned.update(SET_BY_REXX)
        for c in self.clauses:
            ts = c.toks
            for t in ts:  # host variables of EXECSQL statements are set by DB2
                if t.k == "str":
                    self.assigned.update(m.group(1).upper() for m in _HOST_VAR.finditer(_str_value(t.t) or ""))
            if c.kind == "assign":
                self.assigned.add(ts[0].u)
            elif c.kind in ("ARG", "PULL"):
                self.assigned.update(n for n, _ in _template_targets(ts[1:]))
            elif c.kind == "PARSE":
                _, _, template = _parse_parts(ts)
                self.assigned.update(n for n, _ in _template_targets(template))
            elif c.kind == "DO" and len(ts) > 2 and _is_var(ts[1]) and ts[2].k == "op" and ts[2].t == "=":
                self.assigned.add(ts[1].u)
            elif c.kind == "INTERPRET":
                interpret = True
        for c in self.clauses:
            if c.kind == "assign":
                text, unknown = _render(c.toks[2:], self.assigned)
                self.literals.setdefault(c.toks[0].u, []).append((text, c.line, c.src, not unknown))
        if interpret:
            self.assigned = None  # INTERPRET can set any variable: no symbol is known to be unset

    def candidates(self, name: Optional[str]) -> List[str]:
        out: List[str] = []
        for text, _, _, complete in self.literals.get(name or "", []):
            value = text.strip().upper()
            if complete and value and value not in out:
                out.append(value)
        return out

    # ---- variables
    def note_var(self, name: str, src: int, line: int, how: Optional[str]) -> None:
        stem = _stem(name)
        key = stem or name
        rec = self.variables.get(key)
        if rec is None:
            if stem is None and how is None:
                return
            rec = {"name": key, "kind": "stem" if stem else "simple", "line": line, "set_by": []}
            rec.update(self.where(src))
            self.variables[key] = rec
        if how:
            entry = {"how": how, "line": line}
            entry.update(self.where(src))
            if entry not in rec["set_by"]:
                rec["set_by"].append(entry)

    def note_output(self, name: str, src: int, line: int, how: Optional[str]) -> None:
        """A STEM operand: name. is a stem; a name without the dot is a prefix (name1, name2...)."""
        if name.endswith("."):
            self.note_var(name.upper(), src, line, how)
        elif how:
            self.note_var(name.upper(), src, line, how + " (prefix)")

    def note_stems(self, toks: Iterable[_Tok]) -> None:
        for t in toks:
            if _is_var(t) and "." in t.t:
                self.note_var(t.u, t.src, t.line, None)

    # ---- records
    def loop_ctx(self, stack: List[dict]) -> Optional[dict]:
        for e in reversed(stack):
            if e["type"] == "DO" and e["loop"]:
                return {"via": e["line"], "kind": e["loop"], "file": e["file"]}
        return None

    def statement(self, c: _Clause, verb: str, operands: Sequence[_Tok], loop: Optional[dict]) -> dict:
        rec = {"verb": verb, "line": c.line, "end_line": c.end_line, "paragraph": self.blocks[c.block]["name"],
               "operands": [t.t for t in operands], "in_loop": loop}
        rec.update(self.where(c.src))
        rec["_b"] = c.block
        self.statements.append(rec)
        self.block_statements[c.block] = self.block_statements.get(c.block, 0) + 1
        return rec

    def condition(self, kind: str, toks: Sequence[_Tok], start: _Tok, c: _Clause, owner: dict) -> dict:
        rec = {"kind": kind, "text": _join(toks), "tokens": [t.t for t in toks], "start_line": start.line,
               "end_line": max([t.line for t in toks if t.src == start.src] or [start.line]),
               "paragraph": self.blocks[c.block]["name"], "data_items": _reads(toks)}
        if kind == "IF":
            rec["else_line"] = None
        rec.update(self.where(start.src))
        rec["_owner"] = owner
        self.conditions.append(rec)
        return rec

    def routine_call(self, name: str, quoted: bool, args: List[List[_Tok]], via: str, c: _Clause, t: _Tok,
                     loop: Optional[dict]) -> None:
        """A CALL or a function call: internal label, built-in, system routine or external routine."""
        using = [_join(a) for a in args if a]
        if not quoted and name in self.labels:
            pr = {"from": self.blocks[c.block]["name"], "to": name, "thru": None, "loop": None, "inline": False,
                  "line": t.line, "end_line": c.end_line, "in_loop": loop, "via": via, "using": using}
            pr.update(self.where(t.src))
            pr["_b"] = c.block
            self.performs.append(pr)
            return
        if name in BUILTINS:
            if name == "OUTTRAP" and args and args[0]:
                value = _str_value(args[0][0].t) if args[0][0].k == "str" else None
                if value and value.strip() and value.strip().upper() != "OFF":
                    self.note_output(value.strip(), t.src, t.line, "OUTTRAP")
            return
        rec = {"target": name, "dynamic": False, "line": t.line, "paragraph": self.blocks[c.block]["name"],
               "using": using, "in_loop": loop, "via": via}
        if name in SYSTEM_ROUTINES:
            rec["system"] = True
        rec.update(self.where(t.src))
        rec["_b"] = c.block
        self.calls.append(rec)
        if name == "BPXWDYN" and args:
            text, unknown = _render(args[0], self.assigned)
            words = _cmd_words(text)
            if words and words[0].upper() in ("ALLOC", "FREE"):
                stmt = self.statements[-1] if self.statements and self.statements[-1]["line"] == c.line else None
                self.tso_alloc_free(words[0].upper(), words[1:], stmt, c, t, unknown, via="BPXWDYN")

    def function_calls(self, c: _Clause, toks: Sequence[_Tok], loop: Optional[dict], skip: Iterable[int] = ()) -> None:
        skip = set(skip)
        for i, t in enumerate(toks):
            if i in skip or t.k not in ("sym", "str"):
                continue
            if i + 1 < len(toks) and toks[i + 1].k == "(" and not toks[i + 1].blank:
                if t.k == "sym" and not _is_var(t):
                    continue
                name = t.u if t.k == "sym" else (_str_value(t.t) or "").upper()
                if not name:
                    continue
                j = _match(toks, i + 1)
                args = _split_commas(toks[i + 2:j]) if j > i + 1 else []
                self.routine_call(name, t.k == "str", args, "function", c, t, loop)

    def call_record(self, target: str, dynamic: bool, via: str, using: List[str], c: _Clause,
                    loop: Optional[dict], var: Optional[str] = None, library: Optional[str] = None) -> dict:
        rec = {"target": target, "dynamic": dynamic, "line": c.line, "paragraph": self.blocks[c.block]["name"],
               "using": using, "in_loop": loop, "via": via}
        if library:
            rec["library"] = library
        if dynamic:
            rec["candidates"] = self.candidates(var)
        if target.upper() in SYSTEM_ROUTINES:
            rec["system"] = True
        rec.update(self.where(c.src))
        rec["_b"] = c.block
        self.calls.append(rec)
        return rec

    def target_of(self, word: str, unknown: List[Tuple[str, Optional[str]]]) -> Tuple[str, bool, Optional[str]]:
        """(target, dynamic, variable) for a command word naming a program or exec."""
        if _placeholder(word):
            inner = word[1:-1]
            var = next((n for s, n in unknown if s == inner), None)
            return (var or inner.upper()), True, var
        return word.strip("'\"").upper(), False, None

    # ---- files
    def file_row(self, word: str, unknown: List[Tuple[str, Optional[str]]], line: int) -> dict:
        dynamic = _placeholder(word)
        name = word.upper() if dynamic else word.strip("'\"").upper()
        row = self._file_rows.get(name)
        if row is None:
            row = {"name": name, "assign": word, "organization": None, "access": None, "record": None,
                   "records": [], "keys": [], "status": None, "line": line, "kind": "DD",
                   "dd": None if dynamic else name, "io": [], "dsns": []}
            if dynamic:
                var = next((n for s, n in unknown if s == word[1:-1]), None)
                row["dynamic"] = True
                row["candidates"] = self.candidates(var)
            self._file_rows[name] = row
        return row

    def add_io(self, row: dict, stmt: Optional[dict], c: _Clause, src: int, io: dict) -> None:
        io.update({"line": c.line, "end_line": c.end_line, "paragraph": self.blocks[c.block]["name"]})
        io.update(self.where(src))
        io["_stmt"] = stmt
        row["io"].append(io)

    def tso_alloc_free(self, command: str, words: Sequence[str], stmt: Optional[dict], c: _Clause, t: _Tok,
                       unknown: Sequence[Tuple[str, Optional[str]]] = (), via: Optional[str] = None) -> None:
        options, positional = _options(words)
        dds: List[str] = []
        dsns: List[str] = []
        for key, value in options.items():
            if key.upper() in DD_KEYS and isinstance(value, str):
                dds.extend(_values(value))
            elif key.upper() in DSN_KEYS and isinstance(value, str):
                dsns.extend(_values(value))
        disp = next((d for d in DISPOSITIONS if options.get(d.lower()) is True), None)
        changes = command == "ALLOC" and disp == "NEW"
        if stmt is not None:
            if dsns:
                stmt.setdefault("datasets", [])
                stmt["datasets"].extend(d for d in dsns if d not in stmt["datasets"])
            if changes:
                stmt["changes"] = True
        for dd in dds:
            if dd.upper() in ("SYSEXEC", "SYSPROC") and command == "ALLOC":
                self.warn(t.src, t.line, f"ALLOC of {dd.upper()} changes where external execs are found; "
                                         "the map does not follow it")
            row = self.file_row(dd, list(unknown), c.line)
            io: dict = {"verb": command}
            if command == "ALLOC":
                io["dsn"] = list(dsns)
                if disp:
                    io["disp"] = disp
                for d in dsns:
                    if d not in row["dsns"]:
                        row["dsns"].append(d)
            if changes:
                io["changes"] = True
            if via:
                io["via"] = via
            self.add_io(row, stmt, c, t.src, io)
        if not dds and command == "ALLOC" and not dsns and positional:
            self.warn(t.src, t.line, "ALLOC without FILE() or DATASET(); not mapped as a file")

    def execio(self, text: str, unknown: List[Tuple[str, Optional[str]]], stmt: dict, c: _Clause, t: _Tok) -> None:
        cut = _option_paren(text)
        head, opts = (text[:cut], text[cut + 1:]) if cut is not None else (text, "")
        words = _cmd_words(head)
        if len(words) < 4:
            self.warn(t.src, t.line, f"EXECIO with fewer operands than count, mode and DD: {text.strip()}")
            return
        mode = words[2].upper()
        if mode not in ("DISKR", "DISKRU", "DISKW"):
            self.warn(t.src, t.line, f"EXECIO mode {words[2]} not understood")
            return
        row = self.file_row(words[3], unknown, c.line)
        row["access"] = "SEQUENTIAL"
        io: dict = {"verb": "EXECIO", "mode": mode, "count": words[1]}
        if len(words) > 4:
            io["linenum"] = words[4]
        owords = opts.replace(")", " ").split()
        flags = [w.upper() for w in owords if w.upper() in ("FINIS", "OPEN", "SKIP", "LIFO", "FIFO")]
        if flags:
            io["options"] = flags
        upper = [w.upper() for w in owords]
        if "STEM" in upper:
            k = upper.index("STEM")
            if k + 1 < len(owords):
                stem = owords[k + 1]
                io["stem"] = stem.upper() if not _placeholder(stem) else stem
                if not _placeholder(stem):
                    self.note_output(stem, t.src, t.line, f"EXECIO {mode}" if mode != "DISKW" else None)
        if mode == "DISKW":
            io["changes"] = True
            stmt["changes"] = True
        self.add_io(row, stmt, c, t.src, io)

    # ---- host commands
    def command(self, c: _Clause, toks: Sequence[_Tok], env: str, address_line: Optional[int],
                loop: Optional[dict]) -> None:
        text, unknown = _render(toks, self.assigned)
        words = _cmd_words(text)
        first = words[0].upper() if words and not _placeholder(words[0]) else None
        if env == "TSO" and first in ("ISPEXEC", "ISREDIT"):
            env, words = first, words[1:]
            first = words[0].upper() if words and not _placeholder(words[0]) else None
        if env not in self.environments:
            self.environments.append(env)
        command = TSO_NAMES.get(first, first) if env == "TSO" and first else first
        rec = self.statement(c, env, toks, loop)
        rec.update({"command": command, "text": text, "dynamic": bool(unknown), "address_line": address_line})
        self.function_calls(c, toks, loop)
        self.note_stems(toks)
        t = toks[0] if toks else c.toks[0]
        rest = words[1:]
        if env in ("TSO", "MVS") and command == "EXECIO":
            self.execio(text, unknown, rec, c, t)
            return
        if env in ("TSO", "ISPEXEC"):
            options, _ = _options(rest)
            if options:
                rec["options"] = options
        if env == "TSO":
            self.tso(command, rest, text, unknown, rec, c, t, loop)
        elif env == "ISPEXEC":
            self.ispexec(command, rest, unknown, rec, c, t, loop)
        elif env == "ISREDIT":
            if command in ISREDIT_CHANGES:
                rec["changes"] = True
        elif env in PROGRAM_ENVS:
            if words:
                target, dynamic, var = self.target_of(words[0], unknown)
                self.call_record(target, dynamic, env, [w.upper() for w in rest], c, loop, var)
            else:
                self.warn(t.src, t.line, f"ADDRESS {env} without a program name")
        elif env == "DSNREXX":
            if command == "EXECSQL":
                self.execsql(text, unknown, c, t, loop)
        elif env == "SYSCALL":
            if command in SYSCALL_CHANGES:
                rec["changes"] = True
        if env == "UNKNOWN":
            self.warn(t.src, t.line, "host command for an environment chosen at run time (ADDRESS VALUE)")

    def tso(self, command: Optional[str], rest: List[str], text: str, unknown, rec: dict, c: _Clause, t: _Tok,
            loop: Optional[dict]) -> None:
        if command in ("ALLOC", "FREE"):
            self.tso_alloc_free(command, rest, rec, c, t, unknown)
            return
        if command in TSO_CHANGES:
            rec["changes"] = True
            dsns = [w for w in rest if w[:1] in ("'", '"') or (_placeholder(w) and command != "OUTPUT")]
            if command in ("DELETE", "HDELETE") and rest and rest[0].startswith("(") and not dsns:
                dsns = _values(rest[0][1:-1] if rest[0].endswith(")") else rest[0][1:])
            if command in ("SUBMIT", "DELETE", "RENAME", "HDELETE") and not dsns and rest and "(" not in rest[0]:
                dsns = [rest[0]] + ([rest[1]] if command == "RENAME" and len(rest) > 1 else [])
            if dsns:
                rec["datasets"] = dsns
            return
        if command == "CALL" and rest:
            member, library = _member_of(rest[0])
            if _placeholder(rest[0]):
                target, dynamic, var = self.target_of(rest[0], unknown)
                self.call_record(target, dynamic, "TSO CALL", rest[1:], c, loop, var)
            elif member:
                target, dynamic, var = self.target_of(member, unknown)
                self.call_record(target, dynamic, "TSO CALL", rest[1:], c, loop, var, library=library)
                if library:
                    rec["datasets"] = [rest[0]]
            else:
                self.warn(t.src, t.line, f"TSO CALL of {rest[0]} without a member name; program not known")
            return
        if command == "EXEC" and rest:
            member, library = _member_of(rest[0])
            if _placeholder(rest[0]):
                target, dynamic, var = self.target_of(rest[0], unknown)
                self.call_record(target, dynamic, "TSO EXEC", rest[1:], c, loop, var)
            elif member:
                args = rest[1:]
                if args and args[-1].upper() in ("EXEC", "CLIST"):
                    args = args[:-1]
                target, dynamic, var = self.target_of(member, unknown)
                self.call_record(target, dynamic, "TSO EXEC", args, c, loop, var, library=library)
                rec["datasets"] = [rest[0]]
            else:
                self.warn(t.src, t.line, f"TSO EXEC of {rest[0]} without a member name; exec not known")
            return
        if command and command.startswith("%") and len(command) > 1:
            self.call_record(command[1:], False, "TSO %", rest, c, loop)
            return
        if command == "ALTLIB":
            self.warn(t.src, t.line, "ALTLIB changes where external execs are found; the map does not follow it")
        elif command == "EXECUTIL" and any("SEARCHDD" in w.upper() for w in rest):
            self.warn(t.src, t.line, "EXECUTIL SEARCHDD changes where external execs are found; the map does not follow it")

    def ispexec(self, service: Optional[str], rest: List[str], unknown, rec: dict, c: _Clause, t: _Tok,
                loop: Optional[dict]) -> None:
        if service in ISPEXEC_CHANGES:
            rec["changes"] = True
        if service == "LIBDEF":
            self.warn(t.src, t.line, "ISPEXEC LIBDEF changes ISPF libraries at run time; the map does not follow it")
        if service != "SELECT":
            return
        options, _ = _options(rest)
        pgm = options.get("pgm")
        cmd = options.get("cmd")
        parm = options.get("parm")
        if isinstance(pgm, str) and pgm:
            target, dynamic, var = self.target_of(pgm, unknown)
            self.call_record(target, dynamic, "ISPEXEC SELECT PGM", [parm] if isinstance(parm, str) else [], c,
                             loop, var)
        elif isinstance(cmd, str) and cmd:
            words = _cmd_words(cmd)
            if not words:
                return
            target, dynamic, var = self.target_of(words[0], unknown)
            target = target.lstrip("%")
            if target and target not in TSO_COMMANDS:
                self.call_record(target, dynamic, "ISPEXEC SELECT CMD", words[1:], c, loop, var)

    def execsql(self, text: str, unknown, c: _Clause, t: _Tok, loop: Optional[dict]) -> None:
        body = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        parsed = zscan.parse_sql(_for_sql(body))
        words = [w.upper() for w in _cmd_words(_for_sql(body))]
        rec = {"line": c.line, "end_line": c.end_line, "paragraph": self.blocks[c.block]["name"],
               "verb": parsed["verb"], "tables": parsed["tables"], "cursor": parsed["cursor"],
               "host_vars": parsed["host_vars"], "multi_row": parsed["multi_row"], "text": body, "in_loop": loop}
        statement = None
        source_var = None
        if parsed["verb"] == "PREPARE" and len(words) > 1:
            statement = words[1]
            if "FROM" in words:
                k = words.index("FROM")
                if k + 1 < len(words) and words[k + 1].startswith(":"):
                    source_var = words[k + 1][1:]
        elif parsed["verb"] == "EXECUTE" and len(words) > 1:
            if words[1] == "IMMEDIATE" and len(words) > 2 and words[2].startswith(":"):
                source_var = words[2][1:]
            elif words[1] != "IMMEDIATE":
                statement = words[1]
        elif parsed["verb"] == "DECLARE CURSOR" and "FOR" in words:
            k = words.index("FOR")
            if k + 1 < len(words) and not words[k + 1].startswith(("SELECT", "WITH", "(")):
                statement = words[k + 1]
        if statement:
            rec["statement"] = statement
        if source_var:
            rec["sql_from"] = source_var
            if source_var not in self._sql_candidates:
                cands = []
                for value, line, src, _ in self.literals.get(source_var, []):
                    p = zscan.parse_sql(_for_sql(value))
                    cand = {"line": line, "text": value, "verb": p["verb"], "tables": p["tables"]}
                    cand.update(self.where(src))
                    cands.append(cand)
                self._sql_candidates[source_var] = cands
            rec["candidates"] = [dict(x, tables=list(x["tables"])) for x in self._sql_candidates[source_var]]
        if parsed["verb"] in ("FETCH", "SELECT") and "INTO" in words:
            k = words.index("INTO")
            for w in words[k + 1:]:
                for part in w.split(","):
                    if part.startswith(":") and len(part) > 1:
                        self.note_var(part[1:].upper(), t.src, t.line, f"EXECSQL {parsed['verb']}")
        rec.update(self.where(c.src))
        rec["_b"] = c.block
        self.sql.append(rec)

    # ---- pass 2: instructions
    def parse(self) -> None:
        stack: List[dict] = []
        env, address_line = "TSO", None
        previous: Tuple[str, Optional[int]] = ("TSO", None)
        last: Tuple[int, int] = (0, 0)
        for c in self.clauses:
            if c.kind == "label":
                self.settle(stack, False)
                if stack:
                    e = stack[-1]
                    self.warn(c.src, c.line, f"label {self.blocks[c.block]['name']} inside the open {e['type']} of "
                                             f"line {e['line']}; closed here")
                    self.close_all(stack, last)
                continue
            end = (c.end_line, c.src)
            last = end
            if c.kind == "ELSE":
                self.settle(stack, True)
                top = stack[-1] if stack else None
                if top is not None and top["type"] == "IF" and top["state"] == "then-done":
                    top["state"] = "else"
                    top["cond"]["else_line"] = c.line
                else:
                    self.warn(c.src, c.line, "ELSE without an IF to pair with")
                continue
            self.settle(stack, False)
            top = stack[-1] if stack else None
            if c.kind == "THEN":
                if top is not None and top["type"] == "IF" and top["state"] == "cond":
                    top["state"] = "then"
                elif top is not None and top["type"] == "SELECT" and top["state"] == "when-cond":
                    top["state"] = "when-then"
                else:
                    self.warn(c.src, c.line, "THEN without IF or WHEN")
                continue
            if top is not None and top["type"] == "IF" and top["state"] == "cond":
                self.warn(c.src, c.line, f"IF of line {top['line']} has no THEN")
                top["state"] = "then"
            if top is not None and top["type"] == "SELECT" and top["state"] == "when-cond":
                self.warn(c.src, c.line, f"WHEN of line {top['when']['start_line']} has no THEN")
                top["state"] = "when-then"
            loop = self.loop_ctx(stack)
            kind = c.kind
            if kind == "WHEN":
                if top is not None and top["type"] == "SELECT" and top["state"] == "body":
                    cond = self.condition("WHEN", c.toks[1:], c.toks[0], c, top["rec"])
                    cond["subject"] = None
                    cond["select_line"] = top["line"]
                    top["when"] = cond
                    top["state"] = "when-cond"
                    self.function_calls(c, c.toks[1:], loop)
                    self.note_stems(c.toks[1:])
                else:
                    self.warn(c.src, c.line, "WHEN outside a SELECT, or after OTHERWISE")
                continue
            if kind == "OTHERWISE":
                if top is not None and top["type"] == "SELECT" and top["state"] == "body":
                    top["state"] = "otherwise"
                    top["rec"]["otherwise_line"] = c.line
                else:
                    self.warn(c.src, c.line, "OTHERWISE outside a SELECT")
                continue
            if kind == "END":
                if not any(e["type"] in ("DO", "SELECT") for e in stack):
                    self.warn(c.src, c.line, "END without DO or SELECT")
                    continue
                while stack[-1]["type"] not in ("DO", "SELECT"):
                    e = stack.pop()
                    self.warn(c.src, c.line, f"{e['type']} of line {e['line']} has no instruction before this END")
                    self.close_if(e, e["then_end"])
                e = stack.pop()
                if e["type"] == "SELECT" and e["state"] in ("when-cond", "when-then"):
                    self.warn(c.src, c.line, f"WHEN of line {e['when']['start_line']} has no instruction before END")
                self.extend(e["rec"], (c.line, c.src))
                if e.get("loop_rec") is not None:
                    self.extend(e["loop_rec"], (c.line, c.src))
                self.ended(stack, e, False)
                self.done(stack, end)
                continue
            top_level = not stack
            if kind == "IF":
                rec = self.statement(c, "IF", c.toks[1:], loop)
                cond = self.condition("IF", c.toks[1:], c.toks[0], c, rec)
                stack.append({"type": "IF", "state": "cond", "rec": rec, "cond": cond, "line": c.line, "src": c.src,
                              "block": c.block, "then_end": None})
                self.function_calls(c, c.toks[1:], loop)
                self.note_stems(c.toks[1:])
                continue
            if kind == "DO":
                self.do(c, stack, loop)
                continue
            if kind == "SELECT":
                rec = self.statement(c, "SELECT", c.toks[1:], loop)
                rec["otherwise_line"] = None
                stack.append({"type": "SELECT", "state": "body", "rec": rec, "when": None, "line": c.line,
                              "src": c.src, "block": c.block})
                continue
            if kind == "ADDRESS":
                env, address_line, previous = self.address(c, loop, env, address_line, previous)
            elif kind == "command":
                self.command(c, c.toks, env, address_line, loop)
            else:
                self.instruction(c, loop, stack)
            if top_level:  # the last instruction of a routine decides whether it runs on into the next label
                rest = c.toks[1:]
                goto = kind == "SIGNAL" and bool(rest) and not (rest[0].k == "sym" and rest[0].u in ("ON", "OFF"))
                self.blocks[c.block]["ends"] = kind in ("EXIT", "RETURN") or goto
            self.done(stack, end)
        self.settle(stack, False)
        for e in reversed(stack):
            if e["type"] in ("DO", "SELECT"):
                self.warn(e["src"], e["line"], f"{e['type']} has no END before the end of the exec")
        self.close_all(stack, last)

    def extend(self, rec: dict, end: Optional[Tuple[int, int]], key: str = "end_line") -> None:
        """Move rec's end line to end (line, source) when that line is in the same file as rec."""
        if end is None:
            return
        src = next((k for k, s in enumerate(self.sources) if s.copybook == rec.get("copybook")), 0)
        if end[1] == src:
            rec[key] = max(rec.get(key) or 0, end[0])

    def ended(self, stack: List[dict], e: dict, ends: bool) -> None:
        """A compound instruction closed; at the top level it is the routine's last instruction so far."""
        if not stack:
            self.blocks[e["block"]]["ends"] = ends

    def settle(self, stack: List[dict], is_else: bool) -> None:
        """Close the IFs whose THEN branch is complete when the next clause is not ELSE."""
        while stack and stack[-1]["type"] == "IF" and stack[-1]["state"] == "then-done":
            if is_else:
                return
            e = stack.pop()
            self.close_if(e, e["then_end"])
            self.ended(stack, e, False)
            self.done(stack, e["then_end"])

    def done(self, stack: List[dict], end: Optional[Tuple[int, int]]) -> None:
        """One instruction is complete: the THEN, ELSE or WHEN waiting for it moves on."""
        while stack:
            top = stack[-1]
            if top["type"] == "IF":
                if top["state"] == "then":
                    top["state"] = "then-done"
                    top["then_end"] = end
                    return
                if top["state"] == "else":
                    stack.pop()
                    self.close_if(top, end)
                    self.ended(stack, top, False)
                    continue
                return
            if top["type"] == "SELECT" and top["state"] == "when-then":
                top["state"] = "body"
                self.extend(top["when"], end)
            return

    def close_if(self, e: dict, end: Optional[Tuple[int, int]]) -> None:
        if e["type"] != "IF":
            return
        self.extend(e["cond"], end)
        self.extend(e["rec"], end)

    def close_all(self, stack: List[dict], end: Tuple[int, int]) -> None:
        while stack:
            e = stack.pop()
            if e["type"] == "IF":
                self.close_if(e, e["then_end"] or end)
            else:  # a DO or SELECT without END runs to the last clause before the label or the end of the exec
                self.extend(e["rec"], end)
                if e.get("loop_rec") is not None:
                    self.extend(e["loop_rec"], end)
                if e["type"] == "SELECT" and e.get("when") is not None and e["state"] == "when-then":
                    self.extend(e["when"], end)
            self.ended(stack, e, False)

    def do(self, c: _Clause, stack: List[dict], loop: Optional[dict]) -> None:
        toks = c.toks[1:]
        kind, control, conds, _ = _do_spec(toks)
        rec = self.statement(c, "DO", toks, loop)
        rec["loop"] = kind
        entry = {"type": "DO", "rec": rec, "line": c.line, "loop": kind, "file": self.sources[c.src].file,
                 "src": c.src, "block": c.block, "loop_rec": None}
        if kind:
            lrec = {"line": c.line, "end_line": c.line, "kind": kind, "control": control, "text": _join(toks),
                    "paragraph": self.blocks[c.block]["name"], "in_loop": loop, "leave_lines": []}
            lrec.update(self.where(c.src))
            lrec["_b"] = c.block
            self.loops.append(lrec)
            entry["loop_rec"] = lrec
        for word, ctoks in conds:
            if ctoks:
                self.condition(word, ctoks, _word_tok(toks, word), c, rec)
        self.function_calls(c, toks, loop, skip=[k for k, t in enumerate(toks)
                                                   if t.k == "sym" and t.u in ("TO", "BY", "FOR", "WHILE", "UNTIL")])
        self.note_stems(toks)
        stack.append(entry)

    def address(self, c: _Clause, loop: Optional[dict], env: str, address_line: Optional[int],
                previous: Tuple[str, Optional[int]]):
        toks = c.toks
        if len(toks) == 1:
            rec = self.statement(c, "ADDRESS", [], loop)
            rec["environment"] = previous[0]
            return previous[0], previous[1], (env, address_line)
        second = toks[1]
        if (second.k == "sym" and second.u == "VALUE") or second.k == "(" or second.k == "op":
            rec = self.statement(c, "ADDRESS", toks[1:], loop)
            rec["environment"] = None
            self.warn(c.src, c.line, "ADDRESS VALUE chooses the environment at run time; later commands are "
                                     "listed under UNKNOWN")
            self.function_calls(c, toks[2:] if second.u == "VALUE" else toks[1:], loop)
            return "UNKNOWN", c.line, (env, address_line)
        name = second.u if second.k == "sym" else (_str_value(second.t) or second.t).upper()
        if len(toks) == 2:
            rec = self.statement(c, "ADDRESS", toks[1:], loop)
            rec["environment"] = name
            if name not in self.environments:
                self.environments.append(name)
            return name, c.line, (env, address_line)
        self.command(c, toks[2:], name, c.line, loop)
        return env, address_line, previous

    def instruction(self, c: _Clause, loop: Optional[dict], stack: List[dict]) -> None:
        toks = c.toks
        kind = c.kind
        b = self.blocks[c.block]
        if kind == "assign":
            self.statement(c, "ASSIGN", toks, loop)
            target = toks[0]
            if "." in target.t:
                self.note_var(target.u, target.src, target.line, "assign")
            self.function_calls(c, toks[2:], loop)
            self.note_stems(toks[2:])
            return
        verb = kind
        self.statement(c, verb, toks[1:], loop)
        rest = toks[1:]
        if verb in ("ARG", "PULL", "PARSE"):
            if verb == "PARSE":
                how, source, template = _parse_parts(toks)
                self.function_calls(c, source, loop)
                self.note_stems(source)
            else:
                how, template = verb, rest
            for name, t in _template_targets(template):
                self.note_var(name, t.src, t.line, how)
            if how.endswith("ARG") and self.using_line is None and b["name"] is None and c.src == 0:
                self.using = [n for n, _ in _template_targets(template)]
                self.using_line = c.line
            return
        if verb == "CALL":
            self.call_instruction(c, rest, loop)
            return
        if verb == "SIGNAL":
            self.signal(c, rest, loop)
            return
        if verb == "PROCEDURE":
            if b["name"] is not None and self.block_statements.get(c.block, 0) > 1:
                self.warn(c.src, c.line, f"PROCEDURE is not the first instruction after label {b['name']}")
            b["procedure"] = True
            if rest and rest[0].u == "EXPOSE":
                b["expose"] = [t.u for t in rest[1:] if t.k == "sym"]
            return
        if verb == "INTERPRET":
            self.warn(c.src, c.line, "INTERPRET runs code built at run time; it is not analysed")
        if verb in ("LEAVE", "ITERATE"):
            name = rest[0].u if rest and rest[0].k == "sym" else None
            for e in reversed(stack):
                if e["type"] == "DO" and e["loop"] and (name is None or e["loop_rec"]["control"] == name):
                    if verb == "LEAVE":
                        e["loop_rec"]["leave_lines"].append(c.line)
                    break
            else:
                self.warn(c.src, c.line, f"{verb} outside a repeating DO" + (f" with control variable {name}" if name else ""))
            return
        self.function_calls(c, rest, loop)
        self.note_stems(rest)

    def call_instruction(self, c: _Clause, rest: List[_Tok], loop: Optional[dict]) -> None:
        if not rest:
            self.warn(c.src, c.line, "CALL without a routine name")
            return
        first = rest[0]
        if first.k == "sym" and first.u in ("ON", "OFF") and len(rest) > 1:
            self.trap(c, "CALL", rest, loop)
            return
        if first.k not in ("sym", "str"):
            self.warn(c.src, c.line, "CALL of a routine whose name is not a symbol or a string")
            return
        name = first.u if first.k == "sym" else (_str_value(first.t) or "").upper()
        args = _split_commas(rest[1:]) if len(rest) > 1 else []
        self.routine_call(name, first.k == "str", args, "CALL", c, first, loop)
        self.function_calls(c, rest[1:], loop)
        self.note_stems(rest[1:])

    def signal(self, c: _Clause, rest: List[_Tok], loop: Optional[dict]) -> None:
        b = self.blocks[c.block]
        if not rest:
            self.warn(c.src, c.line, "SIGNAL without a label")
            return
        first = rest[0]
        if first.k == "sym" and first.u in ("ON", "OFF") and len(rest) > 1:
            self.trap(c, "SIGNAL", rest, loop)
            return
        g = {"to": [], "line": c.line, "paragraph": b["name"], "depending_on": None}
        if (first.k == "sym" and first.u == "VALUE" and len(rest) > 1) or first.k in ("(", "op"):
            expr = rest[1:] if first.u == "VALUE" else rest
            g["depending_on"] = _join(expr)
            self.warn(c.src, c.line, "SIGNAL VALUE: the target label is chosen at run time; flow not followed")
            self.function_calls(c, expr, loop)
        else:
            name = first.u if first.k == "sym" else (_str_value(first.t) or "").upper()
            g["to"] = [name]
            if name not in self.labels:
                self.warn(c.src, c.line, f"SIGNAL target {name} is not a label of this exec")
        g.update(self.where(c.src))
        g["_b"] = c.block
        self.gotos.append(g)

    def trap(self, c: _Clause, action: str, rest: List[_Tok], loop: Optional[dict]) -> None:
        on = rest[0].u == "ON"
        condition = rest[1].u
        target = None
        if on:
            target = condition
            if len(rest) > 3 and rest[2].u == "NAME":
                target = rest[3].u if rest[3].k == "sym" else (_str_value(rest[3].t) or "").upper()
        if condition not in TRAP_CONDITIONS:
            self.warn(c.src, c.line, f"{action} {rest[0].u} {condition}: not a REXX condition")
        if action == "CALL" and condition in ("SYNTAX", "NOVALUE", "LOSTDIGITS"):
            self.warn(c.src, c.line, f"CALL ON {condition} is not allowed in REXX; only SIGNAL can trap it")
        rec = {"condition": condition, "action": action, "on": on, "target": target, "line": c.line,
               "paragraph": self.blocks[c.block]["name"], "resolved": bool(target and target in self.labels)}
        rec.update(self.where(c.src))
        self.traps.append(rec)
        if on and target and target not in self.labels:
            self.warn(c.src, c.line, f"{action} ON {condition}: label {target} is not in this exec")

    # ---- pass 3: loops reached through CALL
    def compute_loops(self) -> None:
        n = len(self.blocks)
        ranges: Dict[int, List[int]] = {}

        def range_of(k: int) -> List[int]:
            if k not in ranges:
                out = [k]
                m = k
                while not self.blocks[m]["ends"] and m + 1 < n:
                    m += 1
                    out.append(m)
                ranges[k] = out
            return ranges[k]

        graph: Dict[int, List[int]] = {k: [] for k in range(n)}
        sources = []
        for pr in self.performs:
            target = self.labels.get(pr["to"])
            if target is None:
                continue
            rng = range_of(target)
            for k in rng:
                if k not in graph[pr["_b"]]:
                    graph[pr["_b"]].append(k)
            if pr["in_loop"]:
                sources.append((rng, pr["in_loop"]))
        for comp in _cycles(graph):
            names = [self.blocks[k]["name"] or "(entry)" for k in sorted(comp)]
            self.warn(None, None, f"recursive routine calls among {', '.join(names[:20])}: legal in REXX; "
                                  "in_loop takes the nearest loop")
        best: Dict[int, Tuple[int, int, int, dict]] = {}
        for rng, ctx in sources:
            dist = {k: 0 for k in rng}
            queue = list(rng)
            pos = 0
            while pos < len(queue):
                k = queue[pos]
                pos += 1
                for nb in graph[k]:
                    if nb not in dist:
                        dist[nb] = dist[k] + 1
                        queue.append(nb)
            for k, d in dist.items():
                cand = (d, len(rng), -ctx["via"], ctx)
                if k not in best or cand[:3] < best[k][:3]:
                    best[k] = cand
        for group in (self.statements, self.calls, self.sql, self.performs, self.loops):
            for rec in group:
                if rec.get("in_loop") is None and rec.get("_b") in best:
                    rec["in_loop"] = dict(best[rec["_b"]][3])
        for cnd in self.conditions:
            owner = cnd.pop("_owner", None)
            cnd["in_loop"] = owner.get("in_loop") if owner else None

    # ---- assembling the record
    def files(self) -> List[dict]:
        out = []
        for row in self._file_rows.values():
            for io in row["io"]:
                stmt = io.pop("_stmt", None)
                io["in_loop"] = stmt.get("in_loop") if stmt else None
            out.append(row)
        return out

    def sql_tables(self) -> None:
        by_statement: Dict[str, List[str]] = {}
        for s in self.sql:
            if s.get("candidates") and not s["tables"]:
                tables: List[str] = []
                for cand in s["candidates"]:
                    tables.extend(t for t in cand["tables"] if t not in tables)
                if tables:
                    s["tables"] = tables
                    s["dynamic"] = True
            if s.get("statement") and s["verb"] == "PREPARE":
                by_statement.setdefault(s["statement"], [])
                by_statement[s["statement"]].extend(t for t in s["tables"] if t not in by_statement[s["statement"]])
        cursor_tables: Dict[str, List[str]] = {}
        for s in self.sql:
            if s["verb"] == "DECLARE CURSOR" and s.get("cursor"):
                tables = s["tables"] or by_statement.get(s.get("statement") or "", [])
                if tables and not s["tables"]:
                    s["tables"] = list(tables)
                    s["dynamic"] = True
                cursor_tables[s["cursor"]] = list(s["tables"])
        for s in self.sql:
            if not s["tables"]:
                if s.get("cursor") and cursor_tables.get(s["cursor"]):
                    s["tables"] = list(cursor_tables[s["cursor"]])
                    s["dynamic"] = True
                elif s["verb"] == "EXECUTE" and by_statement.get(s.get("statement") or ""):
                    s["tables"] = list(by_statement[s["statement"]])
                    s["dynamic"] = True

    def paragraphs(self) -> List[dict]:
        out = []
        for b in self.blocks:
            if b["name"] is None:
                continue
            rec = {"name": b["name"], "section": None, "start_line": b["start_line"], "end_line": b["end_line"],
                   "procedure": b["procedure"], "expose": b["expose"]}
            cb = self.sources[b["src"]].copybook
            if cb:
                rec["copybook"] = cb
            out.append(rec)
        return out

    def run(self) -> dict:
        toks = self.load()
        self.clauses = _split_clauses(toks)
        self.find_blocks()
        self.collect_assignments()
        self.parse()
        self.compute_loops()
        self.sql_tables()
        if any(cb for cb in self.copybooks):
            self.warn(0, self.copybooks[0]["line"], "%INCLUDE is a REXX compiler directive: the members are expanded "
                                                    "as the compiler does; the interpreter reads it as a comment")
        files = self.files()
        for group in (self.statements, self.performs, self.calls, self.gotos, self.sql, self.loops):
            for rec in group:
                rec.pop("_b", None)
        text = zscan.read_text(self.path)
        return {
            "id": zscan.member_name(self.path), "language": LANGUAGE, "file": self.file,
            "sha256": zscan.sha256_file(self.path), "format": "free", "lines": len(text.splitlines()),
            "copybooks": self.copybooks, "files": files, "data_items": [], "paragraphs": self.paragraphs(),
            "sections": [], "performs": self.performs, "calls": self.calls, "gotos": self.gotos, "sql": self.sql,
            "cics": [], "conditions": self.conditions, "statements": self.statements,
            "procedure_using": self.using, "procedure_using_line": self.using_line, "sql_includes": [],
            "variables": list(self.variables.values()), "loops": self.loops, "traps": self.traps,
            "environments": self.environments, "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- small parsers
def _word_tok(toks: Sequence[_Tok], word: str) -> _Tok:
    return next((t for t in toks if t.k == "sym" and t.u == word), toks[0])


def _do_spec(toks: Sequence[_Tok]) -> Tuple[Optional[str], Optional[str], List[Tuple[str, List[_Tok]]], int]:
    """(kind, control variable, [(WHILE or UNTIL, tokens)], index where the conditions start)."""
    if not toks:
        return None, None, [], 0
    first = toks[0]
    control = None
    if first.k == "sym" and first.u == "FOREVER" and not (len(toks) > 1 and toks[1].t == "="):
        kind, start = "forever", 1
    elif first.k == "sym" and first.u in ("WHILE", "UNTIL") and not (len(toks) > 1 and toks[1].t == "="):
        kind, start = first.u.lower(), 0
    elif _is_var(first) and len(toks) > 1 and toks[1].k == "op" and toks[1].t == "=":
        kind, start, control = "iterative", 2, first.u
    else:
        kind, start = "times", 0
    conds: List[Tuple[str, List[_Tok]]] = []
    depth = 0
    current: Optional[Tuple[str, List[_Tok]]] = None
    cond_start = len(toks)
    for k in range(start, len(toks)):
        t = toks[k]
        if depth == 0 and t.k == "sym" and t.u in ("WHILE", "UNTIL"):
            current = (t.u, [])
            conds.append(current)
            cond_start = min(cond_start, k)
            continue
        if t.k == "(":
            depth += 1
        elif t.k == ")":
            depth -= 1
        if current is not None:
            current[1].append(t)
    return kind, control, conds, cond_start


def _parse_parts(toks: Sequence[_Tok]) -> Tuple[str, List[_Tok], List[_Tok]]:
    """PARSE [UPPER|LOWER|CASELESS] source template -> (how, source tokens, template tokens)."""
    k = 1
    while k < len(toks) and toks[k].k == "sym" and toks[k].u in ("UPPER", "LOWER", "CASELESS"):
        k += 1
    if k >= len(toks):
        return "PARSE", [], []
    word = toks[k].u
    how = f"PARSE {word}"
    if word == "VAR":
        return how, list(toks[k + 1:k + 2]), list(toks[k + 2:])
    if word == "VALUE":
        depth = 0
        for m in range(k + 1, len(toks)):
            t = toks[m]
            if t.k == "(":
                depth += 1
            elif t.k == ")":
                depth -= 1
            elif depth == 0 and t.k == "sym" and t.u == "WITH":
                return how, list(toks[k + 1:m]), list(toks[m + 1:])
        return how, list(toks[k + 1:]), []
    return how, [], list(toks[k + 1:])


def _template_targets(toks: Sequence[_Tok]) -> List[Tuple[str, _Tok]]:
    """Variables a parsing template sets: symbols that are not patterns."""
    out: List[Tuple[str, _Tok]] = []
    depth = 0
    after_sign = False
    for t in toks:
        if t.k == "(":
            depth += 1
            continue
        if t.k == ")":
            depth -= 1
            after_sign = False
            continue
        if depth:
            continue
        if t.k == "op" and t.t in ("+", "-", "="):
            after_sign = True
            continue
        if after_sign:
            after_sign = False
            continue
        if _is_var(t) and t.u not in [n for n, _ in out]:
            out.append((t.u, t))
    return out


def _reads(toks: Sequence[_Tok]) -> List[str]:
    """Variables an expression reads: symbols that are not constants or function names."""
    out: List[str] = []
    for k, t in enumerate(toks):
        if not _is_var(t):
            continue
        if k + 1 < len(toks) and toks[k + 1].k == "(" and not toks[k + 1].blank:
            continue
        if t.u not in out:
            out.append(t.u)
    return out


def _option_paren(text: str) -> Optional[int]:
    """Index of the ( that starts EXECIO options, outside quotes and {unknown} parts."""
    quote = None
    brace = 0
    for k, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
            continue
        if brace:
            brace += {"{": 1, "}": -1}.get(ch, 0)
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "{":
            brace = 1
        elif ch == "(":
            return k
    return None


def _for_sql(text: str) -> str:
    """SQL text for zscan.parse_sql: {unknown} parts become ? so they are not read as names."""
    out = ""
    depth = 0
    for ch in text:
        if ch == "{":
            if depth == 0:
                out += "?"
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
        elif not depth:
            out += ch
    return out


def _cycles(graph: Dict[int, List[int]]) -> List[List[int]]:
    """Groups of routines that call each other (strongly connected components with a cycle)."""
    index: Dict[int, int] = {}
    low: Dict[int, int] = {}
    on: set = set()
    stack: List[int] = []
    out: List[List[int]] = []
    counter = [0]
    for start in graph:
        if start in index:
            continue
        work = [(start, iter(graph[start]))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on.add(start)
        while work:
            node, it = work[-1]
            advanced = False
            for nb in it:
                if nb not in index:
                    index[nb] = low[nb] = counter[0]
                    counter[0] += 1
                    stack.append(nb)
                    on.add(nb)
                    work.append((nb, iter(graph[nb])))
                    advanced = True
                    break
                if nb in on:
                    low[node] = min(low[node], index[nb])
            if advanced:
                continue
            work.pop()
            if low[node] == index[node]:
                comp = []
                while True:
                    x = stack.pop()
                    on.discard(x)
                    comp.append(x)
                    if x == node:
                        break
                if len(comp) > 1 or node in graph[node]:
                    out.append(comp)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return out


# --------------------------------------------------------------------------- public API
def scan_program(path, include_dirs: Sequence = (), root=None) -> dict:
    """One program record (contract version 1, language "rexx") for the REXX exec at path.

    include_dirs are searched, then the exec's own folder, for /*%INCLUDE*/ members.
    Relative paths are taken from root (default: the current directory, the project root).
    """
    return _Scan(Path(path), list(include_dirs or ()), Path(root) if root is not None else None).run()
