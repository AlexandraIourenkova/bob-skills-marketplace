# app-map.json, contract version 1

`zscan.py map` writes `zos-insight/map/app-map.json` and `app-map.md`. The other zos-app-insight skills read the JSON; this page is the contract. Since 1.1 the map holds COBOL, PL/I, REXX and Assembler programs in the same `programs` list, each with a `language`; the section "Languages" at the end maps each language onto the keys below. Fields marked *(added)* go beyond the pack spec's minimum; readers must not fail when a later version adds more.

Paths are relative to the project root, in `/` form. A folder outside the project is kept as an absolute path. Line numbers are physical lines (1-based) of the file the record names: the program file, or the copybook in `copybook`.

## Top level

| Key | Value |
|---|---|
| `version` | `1` |
| `generated` | UTC time, ISO 8601 with `Z` |
| `parser` | `"zscan 1.0"` |
| `roots` | scanned folders |
| `copy_dirs` | *(added)* `--copy-dir` folders |
| `programs` | program records of every language: one per COBOL PROGRAM-ID (a file with nested programs gives several), one per PL/I, REXX or Assembler member |
| `copybooks` | copybook and include members found: `{name, file, language, lines, sha256, used_by: [program ids], includes: [names]}`; `language` *(added in 1.1)* is `cobol`, `pli`, `rexx` or `asm` (Assembler COPY members and macro definitions). The same name can appear twice, from two folders or two languages; to know which file a program read, use `programs[].copybooks[].resolved` |
| `jobs` | job records |
| `procs` | procedure records, in-stream and cataloged |
| `edges` | `{from, to, kind}` plus extra fields per kind |
| `not_analysed` | `{"pli": [files], "asm": [files], "rexx": [files]}`; the three keys are always there. Since 1.1 it lists only the files a language reader skips (a CLIST among REXX files, a file the reader failed on: see `warnings`); other files are analysed |
| `unresolved` | `copybooks`, `programs`, `procs`, `includes`, `dynamic_calls` (below) |
| `utilities` | *(added)* system programs the jobs run (IEFBR14, SORT, IKJEFT01...): `{name, jobs}` |
| `warnings` | map-wide warnings `{file, line, message}`; `file` and `line` may be null |

`unresolved`:

- `copybooks`: `{name, library, programs: [{id, file}]}`; those programs have `partial: true`. *(added)* Each program comes with its file, since two files can declare the same PROGRAM-ID.
- `programs`: `{name, kinds, referenced_by}`; kinds are `call`, `cics-link`, `cics-xctl`, `exec-pgm`.
- `procs`: `{name, jobs}`; `includes`: `{member, job, line}`.
- `macros` *(added in 1.1)*: `{name, programs: [{id, file, line}]}`, Assembler macros called but defined in no scanned folder and not known IBM macros (`programs[].macros` with `found: false` and `system: false`).
- `dynamic_calls`: `{program, file, identifier, line}` (plus `cics` for LINK or XCTL) when no literal for the identifier was found.

## Program record

| Key | Value |
|---|---|
| `id` | PROGRAM-ID, upper case (other languages: see "Languages"). Duplicate ids are kept; links use the first and a warning says so |
| `language` | *(added in 1.1)* `cobol`, `pli`, `rexx` or `asm` |
| `file`, `sha256`, `format`, `lines` | source file, SHA-256 of its bytes, `fixed` or `free`, physical line count |
| `partial` | *(added)* true when a copybook was not found |
| `procedure_using` | *(added)* names after PROCEDURE DIVISION USING |
| `procedure_using_line` | *(added)* line of that USING in the program file, or null |
| `sql_includes` | *(added)* members of EXEC SQL INCLUDE in order, SQLCA and SQLDA included (`["SQLCA"]`); empty when there is none |
| `run_by` | *(added)* `{job, step, file, via?, entry?}`; `step` is `STEP` or `STEP.PROCSTEP`; `via` is the TSO or REXX batch program (`IKJEFT01`, `IKJEFT1B`, `IRXJCL`) for a DSN RUN PROGRAM or an exec its input names; `entry` *(1.1)* is the secondary entry point the step named (`EXEC PGM=RECALC` for a PL/I ENTRY or an Assembler ENTRY) |
| `copybooks` | `{name, library, resolved, replacing, line, nested_in, replacing_pairs}`; `resolved` is a path or null; `nested_in` *(added)* is the including copybook or null; `line` is in the including file; `library` is `"SQL INCLUDE"` for EXEC SQL INCLUDE; `replacing_pairs` *(added)* `[[from, to], ...]` as written, pseudo-text without its `==`, with a third element `leading` or `trailing` for those forms. REPLACING applies to that copybook's text only, not to copybooks it nests |
| `files` | see below |
| `data_items` | see below |
| `paragraphs` | `{name, section, start_line, end_line}` |
| `sections` | *(added)* `{name, start_line, end_line}` |
| `performs` | `{from, to, thru, loop, inline, line, end_line, in_loop}`; `from` is the paragraph (null before the first one); `to` is null for an inline PERFORM; `loop` is `until`, `varying`, `times` or null; `end_line` *(added)* is the END-PERFORM (or closing period) line of an inline PERFORM and the last line of the statement otherwise; `sort` *(added)* is `input` or `output` for a SORT procedure |
| `calls` | `{target, dynamic, line, paragraph, using, in_loop}`; for a dynamic call `target` is the identifier and `candidates` *(added)* lists literals it holds (VALUE, MOVE 'X' TO it); `returning` when given |
| `gotos` | `{to: [paragraphs], line, paragraph, depending_on}` |
| `sql` | `{line, end_line, paragraph, verb, tables, cursor, host_vars, multi_row, text, in_loop}`; verb is the first keyword, or `DECLARE CURSOR`, `DECLARE TABLE`; OPEN, FETCH and CLOSE inherit the cursor's tables; data-division blocks have `paragraph: null`. *(added)* `end_line` is the END-EXEC line; `text` the statement between EXEC SQL and END-EXEC, its lines joined by one space; `multi_row` is true for ROWSET or FOR n ROWS |
| `cics` | `{line, end_line, paragraph, command, options, in_loop}`; `command` like `LINK`, `READ`, `SEND MAP`, `READQ TS`; option values as written (a quoted value is a literal), bare options are `true`; `candidates` *(added)* for PROGRAM(identifier); `end_line` *(added)* the END-EXEC line |
| `conditions` | `{kind, text, tokens, start_line, end_line, paragraph, data_items, in_loop}`; kinds `IF`, `EVALUATE`, `WHEN`, `UNTIL`, `SEARCH-WHEN`; WHEN also has `subject`, and its `data_items` include the subject's. *(added)* `tokens` are the condition's tokens as written (the same split as `operands`; use them instead of splitting `text`); `else_line` (IF only) is the line of its own ELSE, or null; `end_line` is the line of the END-IF, END-EVALUATE or period that closes it, or of the last line inside it when something else closes it; `in_loop` is the loop of the statement the condition belongs to: the IF, the EVALUATE of a WHEN, the SEARCH of a SEARCH-WHEN, the PERFORM of an UNTIL (for UNTIL that is the loop around the PERFORM, not its own) |
| `statements` | `{verb, line, end_line, paragraph, operands, in_loop, phrases?}`; *(added)* `end_line` is the last line of the statement: for IF, EVALUATE, SEARCH, inline PERFORM and statements with phrases the line of the END-x or period that closes them; `phrases` lists the conditional phrases of the statement `{kind, line}`, kind one of `AT END`, `NOT AT END`, `INVALID KEY`, `NOT INVALID KEY`, `ON SIZE ERROR`, `NOT ON SIZE ERROR`, `ON OVERFLOW`, `NOT ON OVERFLOW`, `ON EXCEPTION`, `NOT ON EXCEPTION`, `END-OF-PAGE`, `NOT END-OF-PAGE` (the optional words ON, AT and KEY are normalised). The statements inside a phrase follow as their own records |
| `warnings` | `{file, line, message}` |

Records that come from a copybook's text also carry `copybook` (its name), and their `line` is in that copybook. `statements[].verb` is the COBOL verb (`GO TO`, `NEXT SENTENCE`, `EXEC SQL`, `EXEC CICS` for the blocks). `operands` are the tokens up to the next verb or phrase, as written: keywords included, literals with their quotes, parentheses as separate tokens (`WS-QTY`, `(`, `WS-SUB`, `)`).

`in_loop` is `{via, kind, file}` or null. `via` is the line of the looping PERFORM and `file` *(added)* the file that line is in (the program, or a copybook with PERFORM statements). A record is in a loop when it sits inside an inline PERFORM with UNTIL, VARYING or TIMES (the innermost one wins), or in a paragraph reached through PERFORM (THRU ranges and whole sections included) from such a loop or from an out-of-line PERFORM with UNTIL, VARYING or TIMES. When several loops reach it, the nearest wins (fewest PERFORM hops, then the narrowest range, then the latest line). GO TO is not followed; recursion and unfollowed flow are warnings.

### files

`{name, assign, organization, access, record, io, dd, status, keys, records, line, kind, datasets}`:
`assign` as written; `dd` *(added)* the DD name from it (`UT-S-CUSTMAST` gives `CUSTMAST`); `organization` and `access` default to `SEQUENTIAL` (null for an FD with no SELECT, which is also a warning); `record` the first 01 under the FD and `records` all of them; `keys` record keys; `status` the FILE STATUS item; `kind` `FD` or `SD`.
`io`: `{verb, line, paragraph, in_loop, mode?}` for OPEN (mode INPUT, OUTPUT, I-O, EXTEND), CLOSE, READ, WRITE, REWRITE, DELETE, START, RETURN, RELEASE, SORT and MERGE (mode USING or GIVING).
`datasets` *(added)*: for each job step that runs the program, the DD with the same name: `{job, step, dsn, dsn_resolved, disp, sysout, inline}`.

### data_items

`{level, name, pic, usage, occurs, redefines, value, section, parent, parent_index, copybook, file, line, fd}`:
`name` is `FILLER` when unnamed; `pic` upper case as written; `usage` the USAGE word (null means DISPLAY by default); `value` the VALUE text as written (88 levels: all values, `THRU` included); `section` `FILE`, `WORKING-STORAGE`, `LOCAL-STORAGE` or `LINKAGE`; `parent` the enclosing group (for an 88, its conditional variable); `copybook` the copybook name or null; `file` the source file the line belongs to; `fd` *(added)* the FD of a FILE SECTION item; `parent_index` *(added)* the index of `parent` in the same program's `data_items`, or null; `name_in_copybook` *(added)*, only on items of a copybook copied with REPLACING, the name as the copybook writes it (`:PFX:-CUST-ID` for `CM-CUST-ID`).
`occurs`: `{min, max, depending_on, keys: [{name, order}], indexed_by: []}` or null; a fixed OCCURS n has min = max = n; `order` is `ascending` or `descending`. A 66 level has `renames`.

## Jobs and procedures

Job: `{name, file, line, steps, symbols, includes, jcllib, dd}`. `symbols` are the SET values at the end of the job, quotes removed; `includes` `{member, resolved, line}`; `dd` the DDs before the first step (JOBLIB).

Step: `{name, pgm, proc, line, cond, parm, dd}`, with `pgm` or `proc` null. Optional: `if` (enclosing JCL IF condition), `overrides` (symbol values on EXEC of a procedure), `proc_source` (`in-stream` or `cataloged`), `proc_steps` (the procedure's steps with symbols resolved in this job), `runs` (program of a DSN RUN in SYSTSIN), `execs` *(added in 1.1)*: what a TSO or REXX batch step runs, `{name, how, line}`: from an IKJEFT01, IKJEFT1A or IKJEFT1B SYSTSIN in-stream deck (`%NAME` gives how `%`, `EXEC 'lib(NAME)'` or `EXEC NAME` gives `EXEC`, `CALL 'lib(NAME)'` gives `CALL`, a bare word that is not a TSO command gives `implicit`) or from PARM (`PARM`; IRXJCL runs the exec named first in its PARM). An `implicit` name links only to a REXX exec of the map with that name; the others link to a program of any language or are listed as not found (kind `tso-exec`).

DD: `{name, dsn, disp, inline, sysout, line, dsn_resolved}`; optional `concat` (an unnamed concatenation; `name` repeats the DD it extends), `dummy`, `path`, `inline_lines`, `override` (a `STEP.DD` override applied to a procedure step). `dsn` and `disp` are as written. `dsn_resolved` substitutes `&SYM` and `&SYM.` from, in this order, the EXEC overrides, the PROC defaults, then the job's SET values (and SET values in INCLUDE members found in the roots). It is null when a symbol has no value; a warning names the symbol, except for system symbols such as `&SYSUID`. `&&TEMP` names are kept.

Procedure: `{name, file, kind: "proc", source, line, defaults, steps}`; in-stream ones also have `job`. A cataloged procedure is found by member name (file name without extension) in the scanned folders; a file of steps with no JOB or PROC statement counts as one too.

## Edges

| kind | from | to | extra |
|---|---|---|---|
| `call` | program id | program id when the target is in the map (also when it was named by a secondary entry point), else the name | `line`, `dynamic` (true when taken from the identifier's literal), `via` *(1.1)* how the call is made when it is not a plain CALL (`FETCH`, `function`, `LINKMVS`, `ATTCHMVS`, `TSO EXEC`, `TSO %`, `TSO CALL`, `ISPEXEC SELECT PGM`, `LINK`, `XCTL`, `LOAD`, `V-con`...), `entry` *(1.1)* the entry name called when it differs from the program id |
| `perform` | `PROG:PARAGRAPH` (`PROG:(entry)` before the first) | `PROG:PARAGRAPH` or `PROG:SECTION` | `line`, `thru`, `loop` |
| `copy` | program id, or the copybook that nests it | copybook name | |
| `exec-pgm` | job or procedure name | program id (or the name when not in the map) | `step`, `via` (the TSO or REXX batch program for an exec), `entry` *(1.1)* |
| `exec-proc` | job or procedure name | procedure name | `step` |
| `dd-dataset` | `JOB:STEP` or `JOB:STEP.PROCSTEP` (`PROC:STEP` for a procedure no scanned job calls) | resolved DSN, else as written | `dd`, `disp` |
| `sql-table` | program id | table, qualified as written | `verbs` |
| `cics-link`, `cics-xctl` | program id | program name | `line`, `dynamic` |
| `file-assign` | program id | DD name of the ASSIGN | `file` |

A program is found by its id first, then by a secondary entry point (`programs[].entries`: PL/I ENTRY statements and Assembler ENTRY names). Calls the language readers mark `system: true` (BPXWDYN, SYSCALLS and other routines z/OS supplies) make no edge and are not listed as not found. A job's `exec-pgm` and `exec-proc` edges cover its own steps; the programs inside a procedure come through the procedure's edges and through `run_by`. Edges are unique by `(from, to, kind)`; the first occurrence keeps its extras.

## Loading the map from another skill

The scripts are stdlib Python 3.9+. A skill in the same pack imports zscan from its sibling folder:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "zos-app-map" / "scripts"))
import zscan

app_map = zscan.load_map()                     # zos-insight/map/app-map.json; MapError if missing or another version
prog = zscan.find_program(app_map, "ORDMAIN")  # None when absent
out = zscan.safe_output_dir("zos-insight/dd")  # UnsafePath outside zos-insight/, inside .bob/ or outside the project
```

| Function | What it does |
|---|---|
| `load_map(path=DEFAULT_MAP, root=None) -> dict` | read and check app-map.json; raises `MapError` |
| `scan(roots, copy_dirs=(), root=None, default_format="fixed") -> dict` | build the map in memory, write nothing; raises `MapError` for a missing folder. Every folder given is also an include folder for the PL/I, REXX and Assembler readers |
| `language_module(lang) -> module or None` | the reader of `pli`, `rexx` or `asm` (`zscan_pli.py`, `zscan_rexx.py`, `zscan_asm.py` next to zscan.py) |
| `tso_commands(lines, first_line=None) -> [{name, how, line}]` | the execs and programs a TSO batch input names (see `execs`) |
| `write_map(app_map, out_dir="zos-insight/map", root=None) -> (json_path, md_path)` | write both files under a checked folder |
| `safe_output_dir(path, root=None) -> Path` | absolute folder; raises `UnsafePath` unless it is under `zos-insight/` in the project and outside `.bob/`; symlinks are resolved first |
| `find_program(app_map, id)`, `programs_by_id(app_map)` | look up program records (first one per id) |
| `data_item_index(program) -> {name: [items]}` | items by name; a name can repeat in different groups |
| `edges_from(app_map, node, kinds=None)`, `edges_to(...)` | edge lists |
| `callers(app_map, id)`, `callees(app_map, id)` | program ids through call, cics-link and cics-xctl |
| `statements_in_loop(program)` | statements with `in_loop` set |
| `paragraph_at(program, line)` | the paragraph record holding a line of the program file |
| `read_source(file, root=None) -> [text]` | all lines of a file named in the map, read once per process (the cache is checked against the file's size and time); raises `OSError`; do not change the list |
| `code_slice(file, start, end, root=None) -> [(line, text)]` | source lines for evidence, through `read_source` |
| `render_markdown(app_map)`, `call_graph`, `copybook_graph`, `job_flow` | the Markdown and Mermaid pieces |

`root` defaults to the current directory, which is the project root when Bob runs the scripts.

## Languages *(added in 1.1)*

`zscan.py` reads COBOL and JCL itself and hands PL/I, REXX and Assembler files to the readers next to it. Each reader has `LANGUAGE`, `classify(path, text)` (`program`, `include` or `skip`) and `scan_program(path, include_dirs, root)`; its module docstring is the full list of its keys. A file is offered to a reader by suffix (`.pli`, `.pl1`, `.plx`, `.inc` for PL/I; `.rexx`, `.rex`, `.exec`, `.clist` for REXX; `.asm`, `.mac` for Assembler) or, for `.txt` and extension-less files, by content. `program` gives a program record, `include` a `copybooks` entry with its `language`, `skip` a line in `not_analysed`. A REXX exec that another exec pulls in with `/*%INCLUDE*/` is listed as an include, not a program.

Every 1.0 program key is present for every language; a key the language has no use for is an empty list or null. How each language fills them:

| Key | PL/I | REXX | Assembler |
|---|---|---|---|
| `id` | the OPTIONS(MAIN) procedure, else the first external procedure, else the member | the member name | the first CSECT, RSECT, START or ENTRY name, else the member |
| `format` | `fixed` (see `margins`) | `free` | `fixed` |
| `copybooks` | %INCLUDE and %XINCLUDE members (library from `LIB(MEMBER)`); EXEC SQL INCLUDE with library `SQL INCLUDE` | `/*%INCLUDE*/` compiler directives (the interpreter reads them as comments; a warning says so) | COPY members, EXEC SQL INCLUDE members, and macro definitions found in the folders with library `MACRO` |
| `files` | DCL ... FILE, io from OPEN, CLOSE, READ, WRITE, REWRITE, DELETE, LOCATE, GET, PUT; `dd` from TITLE, else the file name | one per DD the exec allocates, frees or reads and writes with EXECIO (`kind: "DD"`) | DCB and ACB with DDNAME (`kind` `DCB` or `ACB`), io from OPEN, CLOSE, GET, PUT, READ, WRITE and the VSAM request macros |
| `data_items` | DCL items with levels; dimensions give `occurs`; DEFINED and BASED(ADDR(x)) give `redefines`; INIT gives `value`; `section` is the storage class | none: REXX has no declarations (see `variables`) | DS and DC; a DSECT is a level-1 item with its fields as children; the duplication factor is `occurs`; ORG gives `redefines`; `section` is the control-section kind |
| `paragraphs` | internal procedures, BEGIN blocks and ON-units | labels | labels on instructions; `sections` are the control sections |
| `performs` | CALL of a procedure of the file, and DO loops as inline performs | CALL and function calls of an internal label | BAL, BAS, BRAS and similar to a label of the member |
| `calls` | CALL of an external entry, FETCH (dynamic), function references to external entries; `form` | external routines and programs run (`via`: CALL, function, LINKMVS, ATTCHMVS, LINKPGM, TSO CALL, TSO EXEC, TSO %, ISPEXEC SELECT...); `system: true` for routines z/OS supplies | CALL, LINK, XCTL, LOAD, ATTACH macros and V-type constants; `kind`; EP= literal is static, EPLOC=, DE= or a register dynamic |
| `gotos` | GO TO | SIGNAL (SIGNAL VALUE: `to: []`, `depending_on`) | the branch family to a label |
| `sql` | EXEC SQL | ADDRESS DSNREXX "EXECSQL ..." | EXEC SQL |
| `cics` | EXEC CICS | none | EXEC CICS |
| `conditions` | IF, SELECT, WHEN, OTHERWISE, WHILE, UNTIL | IF, WHEN, WHILE, UNTIL | none: compare-and-branch pairs are statements, not business rules |
| `statements` | verb, operands as tokens; `phrases` from the ON-units that cover the statement (`ON ENDFILE`, `ON KEY`...) | verb is the keyword, ASSIGN, or the host command environment (TSO, MVS, ISPEXEC, LINKMVS, DSNREXX...) with `command`, `text`, `dynamic`, `options`, `datasets`, `changes` | verb is the operation code; `label`, `kind` |
| `in_loop` | DO loops (iterative, WHILE, UNTIL, REPEAT, FOREVER) and procedures called from one | DO loops (iterative, times, while, until, forever) and labels called from one | backward branches (`kind: "branch"`) and structured DO macros (`do`), with `confidence` high, medium or low |

Keys added per language (readers must not fail when they are missing):

- PL/I: program `margins`, `member`, `entries` `[{name, line, kind (procedure or entry), main}]`, `labels`; data items `type`, `dimensions`, `based`, `defined`, `like`, `external`, `block`; files `attributes`, `env`, `title`, `transmission`, `declared`, `handlers` `[{condition, line, end_line, unit, paragraph}]`; paragraphs `kind` (procedure, begin, on-unit), `parent`, `external`, `params`; performs `function`, `entry`; calls `form` (CALL, FETCH, FUNCTION).
- REXX: program `variables` `[{name, kind (stem, simple), line, set_by}]`, `loops`, `traps` `[{condition, action, on, target, line, paragraph, resolved}]` (SIGNAL ON and CALL ON), `environments`; statements `command`, `text`, `dynamic`, `address_line`, `options`, `datasets`, `changes` (true for commands that create, delete or rewrite data or submit or cancel jobs), `loop`, `otherwise_line`, `environment`; files io `mode`, `count`, `stem`, `options`, `dsn`, `disp`, `changes`, `via`; calls `via`, `library`, `candidates`, `system`; sql `statement`, `sql_from`, `candidates`, `dynamic`; conditions `select_line`.
- Assembler: program `macros` `[{name, found, definition, definition_line, inline, system, count, line}]`, `macro_definitions`, `equates` `[{name, value, line, control_section, file}]`, `usings` (recorded, not interpreted), `entries` `[{name, line}]`, `externals`, `loops` `[{line, file, opcode, top, start_line, end_line, type, confidence}]`; `in_loop.confidence`; statements `label`, `kind`; performs `opcode`, `register`; gotos `opcode`, `conditional`, `backward`; calls `kind`, `candidates`; data items `type`, `length`, `dup`, `nominal`, `size`, `offset`, `definition`, `op`, `control_section`; files `options`, `rpls`; sections `kind`, `amode`, `rmode`.
