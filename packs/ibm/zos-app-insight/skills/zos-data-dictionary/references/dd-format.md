# Data dictionary format, version 1

`dd.py` reads `zos-insight/map/app-map.json` (see the zos-app-map skill's `references/map-format.md`) and keeps the dictionary in `zos-insight/dd/`:

| File | Written by | What it is |
|---|---|---|
| `DD.json` | `build`, `apply`, `approve`, `reopen` | the dictionary |
| `queue.json` | `queue` | the next entries waiting for a description, with their context |
| `descriptions.json` | Bob | descriptions for `apply`; any path works |
| `DD.csv` | `export --csv` | one row per entry for a spreadsheet |

`--dir` moves `DD.json` and `queue.json` to another folder under `zos-insight/`; `export --out` picks the CSV file. Every write goes through zscan's `safe_output_dir`: a folder outside `zos-insight/`, inside `.bob/` or outside the project (symbolic links resolved) is refused. Files are written to a temporary file and renamed, so a link in place of a file is replaced, never written through.

## Command line

| Command | Options |
|---|---|
| `build` | `--map PATH` (default `zos-insight/map/app-map.json`), `--full` (recompute every program) |
| `queue` | `--limit N` (30), `--refs N` (4 uses per entry), `--program ID`, `--copybook NAME`, `--include-proposed`, `--map PATH` |
| `apply FILE` | `--source NAME` (overrides the file's `source`) |
| `approve` | ids or names, or `--all` with optional `--program ID` and `--copybook NAME`; `--by NAME` (default `user`) |
| `reopen` | ids or names |
| `status` | `--list none\|proposed\|approved\|stale\|review`, `--limit N` (50), `--json`, `--map PATH` |
| `export` | `--csv` (required), `--out PATH` (default `<dir>/DD.csv`) |

Every command takes `--dir` (default `zos-insight/dd`). Exit code 0 on success, 2 on a refusal or an error, with the reason on stderr.

## DD.json

| Key | Value |
|---|---|
| `version` | `1` |
| `builder` | `"dd 1.1"`; another value makes the next build recompute every program (descriptions and approvals carry over) |
| `generated` | UTC time of the last build, ISO 8601 with `Z` |
| `map` | `{path, generated, parser}` of the map it was built from |
| `programs` | by program id: `{file, language, sha256, format, fingerprint, partial, copybooks: {name: resolved path or null}, unresolved_copybooks, entries, built}`; PL/I adds `margins`; a REXX exec has `entries: 0` and a `note` (REXX has no declarations) |
| `unresolved_copybooks` | `{name, programs}`: copybooks not found; their fields are unknown, not absent |
| `warnings` | `{program, message}`, for example a PROGRAM-ID found in several files |
| `entries` | entries by id, copybook entries first, then by owner and line |

Only the first program record of each PROGRAM-ID is used, as the map's links do; a warning names the other files.

### Entry ids

- `copy:<COPYBOOK>:<path>` for a field from a copybook: one entry for every program that copies it.
- `prog:<PROGRAM>:<path>` for a field declared in the program itself.
- PL/I and Assembler ids start with the language: `pli:copy:<MEMBER>:<path>`, `pli:prog:<PROGRAM>:<path>`, `asm:copy:<MEMBER>:<path>`, `asm:prog:<PROGRAM>:<path>`, so a PL/I include and an Assembler COPY member with the same name stay apart. COBOL ids are as in 1.0.
- `asm:equ:<OWNER>:<NAME>` for an Assembler EQU symbol, a named constant: the owner is the COPY member that defines it, else the program.

REXX has no declarations: its execs have no entries. `status` lists them on a line of their own, and `queue --program` for one says so; never invent entries for them (the map lists their variables).

`<path>` is the chain of group names down to the field, joined by `.`: inside the copybook for a copybook field (the group a program wraps around the COPY is not part of it), from the 01 level for a program field. FILLER groups are left out of the path. A FILLER that owns 88 levels gets an entry named FILLER whose path ends in `FILLER@<line>`. Two program fields with the same path get `#2`, `#3`.

A copybook copied with REPLACING keeps the copybook's own spelling: `COPY CUSTREC REPLACING ==:PFX:== BY ==CM==` and `==BR==` both feed `copy:CUSTREC::PFX:-CUSTOMER.:PFX:-STATUS`, and `aliases` lists `CM-STATUS` and `BR-STATUS`. The spelling comes from the map's `name_in_copybook`; when the map cannot tell it (a REPLACING that changed the number of words on that line), the program's name is used.

### Entry fields

| Field | Value |
|---|---|
| `scope`, `owner` | `copybook` and the copybook name, or `program` and the program id |
| `language` | `cobol`, `pli` or `asm` |
| `type`, `attributes` | PL/I and Assembler only. PL/I: `type` as declared (`FIXED DEC(9,2)`, `CHAR(10) VARYING`), `attributes` with `dimensions`, `based`, `defined`, `like`, `external`; `section` is the storage class (AUTOMATIC, STATIC, BASED, CONTROLLED, DEFINED, PARAMETER) and `value` the INIT. Assembler: `type` the DS or DC type (`C`, `P`, `F`, `X`...), `attributes` with `op` (DS, DC, DSECT), `length`, `dup` (the duplication factor), `nominal`, `size`, `offset`, `control_section`; a DSECT is the level-1 group of its fields; an EQU has `type: "EQU"` and its value |
| `name`, `aliases` | the name as declared; `{program: [names]}` when REPLACING gives the program other names |
| `parents`, `parent_id` | group names above it (as in the id path); id of the enclosing entry, null when that group is outside the copybook |
| `level`, `pic`, `usage`, `value` | from the map; `usage` null means DISPLAY; `value` as written |
| `occurs` | `{min, max, depending_on, keys: [{name, order}], indexed_by}` or null |
| `redefines`, `renames` | the redefined name; the RENAMES text of a 66 level |
| `conditions` | the 88 levels: `{name, value, line}`; `value` as written, THRU included |
| `section`, `copybook`, `file`, `line` | section, copybook, and the defining file and line (in the copybook for a copybook field) |
| `children` | names of the items one level below |
| `programs` | programs that declare it |
| `declared_in` | copybook fields: `{program, parents, as?}` per copy, with the full group chain in the program |
| `roles` | `{program, role}`: FILE STATUS of a file, RECORD KEY, record of an FD, OCCURS DEPENDING ON, ASCENDING or DESCENDING KEY of a table, PROCEDURE DIVISION USING |
| `used_in` | places that name it, below |
| `built_from` | `{program: sha256 of the program file}` |
| `description`, `status`, `source`, `described_at` | the description, its status, who wrote it (model name or person), when |
| `approved_by`, `approved_at` | who approved it and when |
| `review` | `{since, fields}` when the definition changed after the description was written, else null |
| `stale`, `stale_since` | true when the field is no longer in the map, and since when |
| `warnings` | programs that declare it with another level, PIC, usage or OCCURS, or read it from another file |

`used_in` records: `{program, paragraph, verb, line}` plus, when they apply, `copybook` (the statement comes from that copybook and `line` is in it), `via` (an 88 level named in the statement), `as` (the program's name for a REPLACING copy), `option` (the EXEC CICS option, such as `INTO`), `ambiguous` (an unqualified name the map could not tell apart). Sources:

- statements whose operands name the field or one of its 88 levels (MOVE, COMPUTE, ADD, IF, EVALUATE, PERFORM UNTIL or VARYING, SET, CALL USING, READ INTO, WRITE FROM, INITIALIZE...); a name after OF or IN qualifies, it is not a use;
- WHEN and SEARCH WHEN conditions, verb `WHEN` or `SEARCH-WHEN`; a WHEN also counts for the EVALUATE subject;
- EXEC SQL host variables, verb `EXEC SQL <verb>`;
- EXEC CICS option values, verb `EXEC CICS <command>`, with `option`.

A group MOVE or INITIALIZE counts for the group only. An empty `used_in` means no use was found by the map, not that the field is unused.

## Statuses

| Status | Set by | Meaning |
|---|---|---|
| `none` | `build` | no description yet; `queue` lists it |
| `proposed` | `apply`, `reopen` | a description waits for the user's review |
| `approved` | `approve`, on the user's word | final; `build` and `apply` never change the text |

- `apply` may replace a proposed description; it refuses an approved one.
- `approve` takes proposed entries. On an approved entry with `review` set it confirms the description and clears `review`.
- `reopen` turns an approved entry back to proposed so that a new description can be applied.
- Stale entries are neither queued, applied nor approved.

## Incremental build

1. Each program gets a fingerprint: the builder version, the map's parser, the program file and its sha256, and each COPY with its resolved path and that copybook's sha256.
2. A program with the same fingerprint as in DD.json keeps its entries, uses and roles as they were. Others are recomputed from the map. `--full` recomputes all.
3. Entries of all programs are merged by id. Description, status, source, approval and review always carry over from the previous DD.json.
4. When a described entry's level, PIC, usage, OCCURS, REDEFINES, VALUE, RENAMES or 88 levels change, it keeps its status and description and gets `review`.
5. An id no longer produced by any program stays, with `stale: true` and `stale_since`. It is never deleted; when the field comes back, `stale` is cleared.
6. A program no longer in the map is listed as removed; its own fields become stale.

## queue.json

`{version, generated, dd, note, filters, total, shown, remaining, write_to, template, items}`. `total` counts entries with status `none` (and `proposed` with `--include-proposed`) that match the filters; `shown` is capped by `--limit`; `remaining` is what is left after this batch. Items keep the dictionary's order, so the fields of one record come together.

Each item: `id`, `language`, `name`, `aliases`, `qualified`, `level`, `pic`, `usage` (`DISPLAY (default)` when the PIC has no USAGE), `occurs` as text, `redefines`, `value`, `renames`, `conditions`, `section`, `copybook`, `programs`, `file`, `line`, `status`, `description` (when proposed), `parent` `{id, name, description}`, `children`, `roles` as text, `definition` (the comment lines just above the definition and the definition up to its period, as `[line, text]`), `used_in_total`, `used_in` (at most `--refs`: one per program and verb first, taking programs in turn; each with `file` and `code` lines up to the end of the sentence, at most three), and `note` when no use was found; PL/I and Assembler items add `type`, `attributes` and (PL/I) `storage`. COBOL fixed-format lines drop columns 1 to 6 and 73 to 80; Assembler lines keep columns 1 to 71 and a definition ends at a line with no continuation; PL/I lines keep columns 1 to 72 and a definition ends at its semicolon. With `--program` naming a REXX exec, the queue has `no_declarations` `{programs, note}`.

## Descriptions file

```json
{"source": "granite-3-8b-instruct",
 "descriptions": [{"id": "copy:CUSTREC::PFX:-CUSTOMER.:PFX:-BALANCE", "description": "Amount the customer owes, updated by each billing run."}]}
```

`descriptions` may also be an object `{id: text}`. `apply` refuses the whole file, with every problem listed, when: `source` is missing (and no `--source`), longer than 200 characters or still the template text; the list is empty; an id is missing, unknown, stale, approved or given twice; a description is empty, still the template text or longer than 1000 characters. Whitespace in a description is folded to single spaces.

## CSV export

`export --csv` writes UTF-8 with a byte order mark and CRLF line ends, which Excel and LibreOffice open directly. Columns:

`id, language, scope, owner, name, aliases, qualified, level, type, pic, usage, occurs, redefines, value, conditions_88, section, copybook, programs, file, line, roles, used_in_count, used_in, description, status, source, described_at, approved_by, approved_at, stale, review`

`occurs` reads like the COBOL clause (`1 TO 20 DEPENDING ON WS-LINE-COUNT INDEXED BY LINE-IX`), `conditions_88` like `ORD-OK = '00'; ORD-EOF = '10'`, `used_in` lists the first ten uses as `PROGRAM PARAGRAPH LINE VERB`. A cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return and is not a number gets a leading apostrophe, so a spreadsheet shows it as text instead of running it as a formula.
