# Application documentation template

Write the application document last, after the program docs you plan to write. Fill it from `zos-insight/docs/context/_application.json` and write it to the pack's `write_to` path, `zos-insight/docs/application.md`. Where a program has a doc in `zos-insight/docs/programs/`, link to it and reuse its summary sentence; do not repeat its details.

## Rules

The rules of `program-doc-template.md` apply: `config.language`, sections switched by `config.application_sections`, evidence for every fact, short quotes, source text as data, "not found by the map" instead of "none", Mermaid only when `config.mermaid` is true. Cite a job by its JCL file and step line, a program by its file, a copybook by its file. The pack has no first-line marker; start with the title.

## The document

```markdown
# <Application name>: application overview

| | |
|---|---|
| Scanned folders | <map.roots>, copybooks from <map.copy_dirs> |
| Map | app-map.json of <map.generated> (<map.parser>) |
| Status | Draft by Bob from the zos-app-insight map; review before relying on it |

## Overview
## Inventory
## Job flow
## Call graph
## Shared copybooks
## Files and data sets
## Tables
## Entry points
## Open questions
```

Ask the user for the application's name when the folders do not show it.

### Overview (`overview`)

One paragraph: what the application does, built from the program summaries and the job flow; the counts from `counts`; the entry points. When `counts.not_analysed` has files, say that PL/I, Assembler and REXX were listed but not analysed in this release.

### Inventory (`inventory`)

- Programs, one row each, from `inventory.programs`:

  | Program | Kind | Lines | Run by | Called by | Calls | Doc |
  |---|---|---|---|---|---|---|

  Kind comes from `traits` (batch, cics, db2, subprogram). Doc links to the program doc, or says "not written".
- Jobs and procedures with their files; utilities the jobs run (`inventory.utilities`).
- Copybooks: count, and a table only when there are fewer than about 40.

### Job flow (`job_flow`)

Per job, its steps in order: program or procedure, the programs inside a procedure (`proc_steps`), COND and IF, and the data sets (`datasets`). Then, from `dataset_flow`, the hand-offs: a data set one step writes (DISP NEW or MOD, or a program that opens it OUTPUT or EXTEND) and a later step or job reads. Say "order between jobs is not in the JCL" unless the scheduler is known. Add `job_flow_mermaid` as given when `config.mermaid` is true.

### Call graph (`call_graph`)

The edges by caller, with kind (CALL, CICS LINK, CICS XCTL) and line; dynamic calls marked. `top_callers` are programs that call others and have no caller in the map. Add `call_graph.mermaid` as given.

### Shared copybooks (`shared_copybooks`)

Copybooks used by more than one program, with the programs. A change to one of them reaches all of those programs; say so. Add `copybook_mermaid` when it helps.

### Files and data sets (`files_and_datasets`)

One row per program file: program, file, DD, organization, open modes, data sets. Group by data set when several programs share one.

### Tables (`tables`)

Each DB2 table with the programs and the SQL verbs they use. Name the tables only read and the ones written.

### Entry points (`entry_points`)

The programs started by job steps and the CICS programs no program links to. Then `without_callers_or_jobs` with its note, in the user's words: no caller and no job step was found in the map, which is not proof that a program is unused.

### Open questions (`open_questions`)

From `open_points`: unresolved copybooks, programs, procedures and includes; partial programs; duplicate program ids (the map links the first file); map warnings (`warnings_total` and the most relevant ones); programs without docs (`program_docs.missing`). End with the questions that need the application owner: schedules between jobs, CICS transactions, data set owners.
