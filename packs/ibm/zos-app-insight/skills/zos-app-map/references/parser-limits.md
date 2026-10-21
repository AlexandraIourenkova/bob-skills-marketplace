# What zscan understands, and what it does not

zscan 1.0 is a tokenizer with heuristics, not a COBOL compiler or a JCL converter. It reads text the way a careful person would and records facts with line numbers. When it cannot tell, it says so in a warning or leaves a field null; it never turns "not understood" into zero or "none found".

## COBOL source

Understood:

- Fixed format: sequence area (columns 1-6) and columns 73-80 ignored; indicator column 7 with `*` and `/` comments, `D` debug lines (skipped, as without WITH DEBUGGING MODE), `-` continuation of words and of literals (the open literal runs to column 72); floating `*>` comments; tabs expanded to 8.
- Free format: `>>SOURCE FORMAT FREE`, or detected when division headers, level numbers and COPY start before column 7; `*>` comments.
- `CBL`/`PROCESS` lines, `EJECT`, `SKIP1-3` and `TITLE` are skipped.
- COPY name, `COPY 'name'`, `OF`/`IN` library, `SUPPRESS`, `REPLACING` with pseudo-text, words, literals, `LEADING` and `TRAILING`. Pseudo-text with a non-word character at both ends (`:TAG:`, `(PFX)`) is replaced inside words too, as IBM compilers do for tagged copybooks. Nested copybooks are expanded to 12 levels; a loop is a warning.
- EXEC SQL INCLUDE of a member other than SQLCA and SQLDA is expanded like a COPY.
- Several programs in one file (nested or batched) are split by IDENTIFICATION DIVISION and mapped one by one.
- FILE-CONTROL SELECT and ASSIGN, ORGANIZATION, ACCESS, RECORD KEY, FILE STATUS; FD and SD with their 01 records.
- Data entries 01-49, 66, 77, 88: PIC, USAGE (and bare COMP, COMP-3, BINARY...), OCCURS with TO, DEPENDING ON, ASCENDING and DESCENDING KEY, INDEXED BY, REDEFINES, RENAMES, VALUE and VALUES with THRU.
- PROCEDURE DIVISION USING, DECLARATIVES, sections, paragraphs, every statement verb, IF/ELSE/END-IF, EVALUATE/WHEN with ALSO, SEARCH and SEARCH ALL with WHEN, scope terminators and conditional phrases (AT END, INVALID KEY, ON SIZE ERROR, ON OVERFLOW, ON EXCEPTION, END-OF-PAGE and their NOT forms), each recorded on its statement with its line. A data name that starts with END- (END-OF-FILE) is a name, not a terminator.
- PERFORM: out of line with THRU and section targets, inline, with TIMES, UNTIL, WITH TEST BEFORE/AFTER, VARYING ... AFTER; SORT INPUT and OUTPUT PROCEDURE ranges.
- CALL with a literal or an identifier, USING (BY REFERENCE, CONTENT, VALUE), RETURNING; GO TO, also with DEPENDING ON.
- EXEC SQL: verb, tables after FROM, JOIN, INSERT INTO, UPDATE, MERGE INTO, LOCK TABLE; cursors (DECLARE, OPEN, FETCH, CLOSE, WHERE CURRENT OF); host variables.
- EXEC CICS: command, options as written.

Not understood, or only partly:

- The REPLACE statement is not applied; a warning says where it is. Names after it may differ from the compiled program.
- Compiler options are unknown: a CALL literal can still be dynamic at run time (DYNAM), and `D` lines are always treated as comments.
- Qualified names (`X OF Y`) are kept as tokens; data items are matched by name only, so a name used in several groups maps to each of them.
- Dynamic CALL and CICS PROGRAM(identifier): the target is the identifier; `candidates` lists literals from its VALUE and from `MOVE 'X' TO identifier`. A target set any other way (from a file, a table, STRING) stays unknown and is listed under `unresolved.dynamic_calls`.
- `in_loop` follows PERFORM only. GO TO is not followed: a loop built from GO TO is not seen, and a GO TO out of a performed range is a warning. Recursive PERFORM is a warning and is not unrolled. ALTER and GO TO DEPENDING ON are warnings.
- A period inside an inline PERFORM ends it, with a warning. An ELSE or END-x with nothing to close is skipped.
- A phrase is given to the current statement when its verb takes it, else to the innermost open statement that takes it (`NOT AT END` after the statements of an `AT END`). Two nested statements of the same verb without their END-x can be paired the wrong way, as a reader could.
- Tokens after a continuation carry the continuation line. A pseudo-text or name split by a continuation keeps its first line.
- `name_in_copybook` is left out on a line whose REPLACING changed the number of words; the name in the map is then the replaced one.
- EXEC CICS HANDLE CONDITION, HANDLE AID and HANDLE ABEND targets are not followed as flow.
- EXEC DLI and other EXEC blocks are recorded as statements only. Object-oriented COBOL, report writer and screen sections are not interpreted.
- SQL inside dynamic statements (PREPARE, EXECUTE IMMEDIATE with a host variable) has no tables.
- Literal continuation in free format is understood only in the `-` form.

## JCL

Understood: JOB, EXEC PGM= and PROC= (or a positional procedure name), DD with DSN, DISP, SYSOUT, DUMMY, PATH, `DD *` and `DD DATA` with DLM (in-stream data is counted, not stored), unnamed DD concatenations, `STEP.DD` overrides of procedure steps, continuation lines (a trailing comma, or an open apostrophe), comments after the operands, SET, PROC defaults, PEND, in-stream and cataloged procedures (by member name in the scanned folders, nested to 5 levels), INCLUDE members found in the scanned folders (their SET statements are applied), JCLLIB ORDER, IF/THEN/ELSE/ENDIF (kept as the step's `if` text), COND and PARM as written. A TSO batch step (IKJEFT01) with `DSN ... RUN PROGRAM(X)` in an in-stream SYSTSIN links the step to program X.

Symbol values are taken in this order: the EXEC statement that calls the procedure, the PROC statement's defaults, the job's SET statements. This is the common case of the JES rules, not all of them: system symbols (`&SYSUID`), symbols set by JES or by an INCLUDE member outside the scanned folders, and EXPORT SYMLIST are unknown, so `dsn_resolved` is null and a warning names the symbol.

Not interpreted: JES2 and JES3 control statements, OUTPUT, CNTL, the program's own PARM processing, step restart, GDG relative generations (`(+1)` is kept as written), and data sets referred back with `*.STEP.DD`.

## Files and languages

- COBOL: `.cbl`, `.cob`, `.cobol`, `.ccp`, `.cbp`, `.sqb`, `.pco`, and `.txt` or extension-less files that hold a PROGRAM-ID.
- Copybooks: `.cpy`, `.copy`, `.cpb`, `.cbk`, `.dclgen`, `.dcl`, and the same unknown extensions; any file can be found by member name when a COPY names it.
- JCL: `.jcl`, `.prc`, `.proc`, `.cntl`, `.jcls`, and COBOL, copybook, `.txt` or extension-less files whose first line starts with `//`.
- Listed as not analysed in 1.0: PL/I (`.pli`, `.pl1`, `.plx`, `.inc`), Assembler (`.asm`, `.mac`), REXX (`.rexx`, `.rex`, `.exec`, `.clist`, or `/* REXX` on the first line).
- Folders named `.git`, `.bob`, `node_modules`, `zos-insight` and other hidden folders are skipped; symbolic links are not followed.

## Warnings and what to do

| Warning | Meaning | What to do |
|---|---|---|
| copybook X not found | its data items and code are missing; the program is partial | add the folder with `--copy-dir`, or download the copybook library |
| PROGRAM-ID X also in ... | two files declare the same program; links use the first | scan one version of the application |
| PERFORM target X is not a paragraph or section | a typo, a name from a missing copybook, or a parse miss | check the line |
| recursive PERFORM among ... | the PERFORM graph has a cycle | read those paragraphs; `in_loop` is not followed there |
| GO TO ... leaves the range of the loop PERFORM | flow the map does not follow | check the jump by hand |
| GO TO ... DEPENDING ON / ALTER | the target is chosen at run time | check the paths by hand |
| REPLACE statement not applied | text after it may be renamed by the compiler | compare with the compiler listing |
| DSN ... uses &X with no value | a JCL symbol is unknown | scan the INCLUDE or PROCLIB member that sets it |
| period ends the inline PERFORM | unusual syntax, maybe a typo | check the line |
| no PROGRAM-ID found / no JOB, PROC or EXEC statement found | the file is not what its extension says, or a member of another kind | ignore, or move it out of the scanned folder |

For whole estates and exact compiler semantics, IBM's own tools in the IBM Bob Premium Package for Z are the next step.
