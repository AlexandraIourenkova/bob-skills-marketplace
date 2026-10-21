# cobol-perf-review checks

Since 1.1 the review covers PL/I and REXX as well as COBOL. Which checks run on which language:

| Language | Checks |
|---|---|
| COBOL | every check below except the three REXX ones |
| PL/I | io-open-close-in-loop, sql-in-loop, static-call-in-loop, dynamic-call-in-loop |
| REXX | sql-in-loop (ADDRESS DSNREXX), static-call-in-loop and dynamic-call-in-loop (external routines, LINKMVS, ATTCHMVS, TSO CALL and EXEC, ISPEXEC SELECT), execio-in-loop, alloc-free-in-loop, host-command-in-loop |
| Assembler | none in 1.1: the report lists Assembler programs as not reviewed. Their loops are inferred from branches (the map gives each a confidence) and registers are not followed, so a per-loop fact would be a guess. |

`perf.py scan` reports patterns that cost CPU or I/O on z/OS when they run many times. Each finding is a fact: the statement, its file and line, the loop around it (the PERFORM line and its kind, plus the outer loops), the data items involved and the source lines as evidence. There is no score. A finding matters in proportion to how often its loop runs, which the map cannot know: measure before and after every change (see [Measuring](#measuring)).

The heading of each check is its id, so `references/checks.md#<id>` in a finding points here. The COBOL samples are short illustrations, not drop-in code: adapt names, sizes and error handling to the program.

Confidence:

- **high**: the pattern is there and the usual fix applies as described.
- **medium**: the pattern is there, but whether the fix pays off depends on something the map cannot see: a record layout shared with files or callers, an IF around the statement, the size of the callee's work, a WHEN that does not test the key.
- **low**: listed only with `--min-confidence low`. Besides STRING, UNSTRING and INSPECT, any finding whose loop is a `PERFORM n TIMES` with a literal n of 10 or less, inside no other loop, in a program that no other program calls from a loop, is made low; its fact says how many times the loop runs, and `detail.confidence_before_loop_count` keeps the level it had.

A loop is what `in_loop` in app-map.json says: an inline PERFORM with UNTIL, VARYING or TIMES, or a paragraph reached through PERFORM from such a loop (PL/I: a DO loop, or a procedure called from one; REXX: a repeating DO, or a label called from one). GO TO loops are not seen. When another program calls this one inside its loop, the report says so in a note; the checks themselves look at loops inside each program.

## io-open-close-in-loop

OPEN or CLOSE inside a loop. Confidence high; medium when an IF or WHEN inside the loop encloses it.

**Why it costs time.** OPEN and CLOSE are system services, not data moves. OPEN finds the data set in the catalog, reads its label, builds the control blocks and gets buffers; for VSAM it also reads the index. CLOSE writes the last buffer, updates the label and the catalog, and writes SMF records. A READ or WRITE mostly moves bytes inside a buffer. A pair of OPEN and CLOSE per record costs far more than the record's own I/O, and OPEN EXTEND with CLOSE per record also writes a short block every time.

**Fix.** Open once before the loop, close once after it.

Before:

```cobol
       2000-PROCESS.
           OPEN EXTEND AUDIT-FILE
           WRITE AUDIT-REC FROM WS-AUDIT
           CLOSE AUDIT-FILE
           PERFORM 2100-READ-NEXT.
```

After:

```cobol
       1000-INIT.
           OPEN INPUT  IN-FILE
                EXTEND AUDIT-FILE.
       2000-PROCESS.
           WRITE AUDIT-REC FROM WS-AUDIT
           PERFORM 2100-READ-NEXT.
       9000-END.
           CLOSE IN-FILE AUDIT-FILE.
```

**Known false positives.** An OPEN behind a first-time switch (`IF NOT AUDIT-OPEN`), which runs once: the report shows the enclosing IF as a guard and gives medium. A loop that runs once. A deliberate close and reopen, for example to switch to the next input file of a list, or to free a data set for another job at a checkpoint. A CLOSE on an error path just before the program ends.

**Measure.** The step's EXCP count for that DD and its CPU and elapsed time (SMF type 30, or the step summary in the job log). The number of SMF type 14 or 15 records for the data set (one per CLOSE of a non-VSAM data set) or type 62 and 64 (VSAM OPEN and CLOSE) shows how many times it was opened.

## sql-in-loop

PL/I: EXEC SQL as in COBOL. REXX: `ADDRESS DSNREXX "EXECSQL ..."`; an EXECUTE of a prepared singleton statement counts as that statement, and a PREPARE inside a loop is medium (the statement is compiled again on every pass: prepare it once before the loop).

An EXEC SQL singleton SELECT, INSERT, searched UPDATE, searched DELETE or MERGE inside a loop: high. An OPEN of a cursor inside a loop (a nested cursor): medium. Not reported: FETCH, CLOSE, UPDATE or DELETE WHERE CURRENT OF, and statements that already work on many rows (ROWSET, or FOR n ROWS; the map's `multi_row`).

**Why it costs time.** Each EXEC SQL crosses from the program into Db2 through the attachment and back. A singleton SELECT per row repeats a full index probe (from the root page to the leaf) where one cursor over a join would read the pages in sequence with prefetch. An INSERT per row repeats the call and the per-statement work for every row. For a million input records, a few tens of microseconds per call is tens of CPU seconds.

**Fix.** Work on the set: one cursor over a join instead of a SELECT per row, a multi-row INSERT or FETCH, a lookup table loaded once into working storage (then `SEARCH ALL`), or a cache of the last key when the input is sorted.

Before:

```cobol
       2000-PROCESS.
           EXEC SQL
               INSERT INTO STOCK.MOVES_LOG (ITEM, QTY)
               VALUES (:IN-ITEM, :IN-QTY)
           END-EXEC
           PERFORM 2100-READ-NEXT.
```

After (host-variable arrays, one call per 100 rows; flush the rest at the end):

```cobol
       01  LOG-COUNT           PIC S9(4) COMP-5 VALUE 0.
       01  LOG-ARRAYS.
           05  LOG-ITEM        PIC X(6)  OCCURS 100.
           05  LOG-QTY         PIC S9(5) COMP-3 OCCURS 100.

       2000-PROCESS.
           ADD 1 TO LOG-COUNT
           MOVE IN-ITEM TO LOG-ITEM (LOG-COUNT)
           MOVE IN-QTY  TO LOG-QTY (LOG-COUNT)
           IF LOG-COUNT = 100
               PERFORM 2500-FLUSH-LOG
           END-IF
           PERFORM 2100-READ-NEXT.
       2500-FLUSH-LOG.
           EXEC SQL
               INSERT INTO STOCK.MOVES_LOG (ITEM, QTY)
               VALUES (:LOG-ITEM, :LOG-QTY)
               FOR :LOG-COUNT ROWS ATOMIC
           END-EXEC
           MOVE 0 TO LOG-COUNT.
```

For a SELECT per row, the usual after-state is a cursor that joins the driving table with the looked-up one, or, when the input is a file, the lookup table read once at the start into an OCCURS table with ASCENDING KEY.

**Known false positives.** A loop that runs a few times, such as a retry loop. A lookup whose key never repeats and whose table is too large to load. Rows that must be committed or checked one by one for a business reason. The cursor of a nested-cursor finding may be opened once per outer row on purpose, with a different key each time; a join usually still wins, but check the access path first.

**Measure.** Db2 accounting (SMF type 101, IFCID 3) for the plan or package: class 1 and class 2 elapsed and CPU time, the count of each SQL statement type, and getpages. The step CPU in SMF type 30. Compare row counts and table contents after the change.

## static-call-in-loop

PL/I: CALL of an external entry. REXX: CALL or a function call of an external exec (searched for and interpreted on every call), and the programs and execs a host command runs (LINKMVS, ATTCHMVS, LINKPGM, TSO CALL, TSO EXEC, `%name`, ISPEXEC SELECT): each loads and runs the program again. Fix for REXX: bring a small routine in as an internal label, or run the program once with all the rows (a data set or a stem it reads).

`CALL 'literal'` inside a loop. Confidence medium.

**Why it costs time.** A static call is a branch with a parameter list, which is cheap. What repeats is the callee: its own work, the re-initialization of a program compiled with the INITIAL attribute, LOCAL-STORAGE allocated on every call, and Language Environment set-up. With the DYNAM compiler option, `CALL 'literal'` is a dynamic call at run time; see [dynamic-call-in-loop](#dynamic-call-in-loop).

**Fix.** Pass a batch of rows in one call, or move a few lines of logic in line. Check the callee for INITIAL and LOCAL-STORAGE it does not need.

Before:

```cobol
       2000-PROCESS.
           CALL 'TAXCALC' USING IN-REC WS-TAX
           PERFORM 2100-READ-NEXT.
```

After:

```cobol
       2000-PROCESS.
           ADD 1 TO BATCH-COUNT
           MOVE IN-REC TO BATCH-REC (BATCH-COUNT)
           IF BATCH-COUNT = 500
               CALL 'TAXCALC' USING BATCH-COUNT BATCH-TABLE
               PERFORM 2600-WRITE-BATCH
               MOVE 0 TO BATCH-COUNT
           END-IF
           PERFORM 2100-READ-NEXT.
```

**Known false positives.** A callee whose work dominates, so the call itself is noise and batching changes nothing. Language Environment callable services (CEE...), made to be called per record. A call on an error path inside the loop.

**Measure.** The step's CPU time (SMF type 30), and a sampling profiler (for example IBM Application Performance Analyzer) for the share of time in the callee and in the call linkage.

## dynamic-call-in-loop

PL/I: a FETCH inside a loop is low (an entry already fetched is not loaded again, but a RELEASE in the loop makes the next FETCH load it), a CALL of a fetched entry is medium. REXX: LINKMVS, ATTCHMVS or CALL of a program whose name is in a variable, high.

`CALL identifier` inside a loop. Confidence high. The finding lists the literals the identifier can hold and any CANCEL of it inside a loop.

**Why it costs time.** A dynamic CALL goes through a Language Environment routine on every call: it looks the name up among the loaded programs and, on the first call, searches STEPLIB, JOBLIB or the link list and loads the module. After a CANCEL, the next CALL loads it again from disk. A CANCEL inside the loop turns every iteration into a module load.

**Fix.** Keep CANCEL out of the loop. Resolve the target once: a procedure pointer set before the loop skips the lookup, or a static call by literal with NODYNAM when the module can be link-edited with the caller.

Before:

```cobol
       01  WS-PRICER           PIC X(8) VALUE 'PRICER'.

       2000-PROCESS.
           CALL WS-PRICER USING IN-REC WS-PRICE
           CANCEL WS-PRICER
           PERFORM 2100-READ-NEXT.
```

After:

```cobol
       01  WS-PRICER-PTR       USAGE PROCEDURE-POINTER.

       1000-INIT.
           SET WS-PRICER-PTR TO ENTRY 'PRICER'.
       2000-PROCESS.
           CALL WS-PRICER-PTR USING IN-REC WS-PRICE
           PERFORM 2100-READ-NEXT.
```

**Known false positives.** A dispatcher whose identifier names a different program on each pass (still, a table of procedure pointers set once per name helps). A callee that must start fresh each time and relies on CANCEL for it: move that reset into the callee instead. A loop that runs a few times.

**Measure.** The step's CPU and elapsed time; the EXCP count on the STEPLIB or JOBLIB DD in SMF type 30, which shows repeated loads.

## serial-search-keyed

`SEARCH` (serial) on a table whose OCCURS has ASCENDING or DESCENDING KEY. Confidence high when a WHEN tests the key with `=`, medium when it does not.

**Why it costs time.** A serial SEARCH compares the entries one by one from the current index: about half the table on a hit and all of it on a miss. SEARCH ALL is a binary search: about log2(n) comparisons, 6 instead of 30 to 60 for 60 entries. The KEY clause shows the table was meant to be searched that way.

**Fix.** Use SEARCH ALL. It needs the table in key order, a WHEN made only of `=` conditions on key fields (joined by AND), and either a full table or OCCURS DEPENDING ON set to the loaded count.

Before:

```cobol
           SET PR-IX TO 1
           SEARCH PRICE-ENTRY
               AT END MOVE ZERO TO WS-RATE
               WHEN PR-ITEM (PR-IX) = IN-ITEM
                   MOVE PR-RATE (PR-IX) TO WS-RATE
           END-SEARCH
```

After:

```cobol
           SEARCH ALL PRICE-ENTRY
               AT END MOVE ZERO TO WS-RATE
               WHEN PR-ITEM (PR-IX) = IN-ITEM
                   MOVE PR-RATE (PR-IX) TO WS-RATE
           END-SEARCH
```

**Known false positives.** The table is not really in key order: the compiler does not check the KEY clause, so look at how the table is loaded. A serial SEARCH that starts from a saved index on purpose, to continue a scan. Duplicate keys where the first match in load order matters. A table that is searched once per run.

**Measure.** The step's CPU time, and a profiler for the share of time in the paragraph that searches.

## serial-search-large

`SEARCH` (serial) on a table of more than 100 entries (the OCCURS maximum) with no KEY. Confidence medium.

**Why it costs time.** As above, without a way to stop early on a miss: every miss compares all entries. A 400-entry table searched for each of a million records is up to 400 million comparisons.

**Fix.** Load the table in key order (ORDER BY in the cursor, or sort the input), declare the key and use SEARCH ALL. When the table cannot be sorted, put the most used entries first.

Before:

```cobol
       01  WS-SITE-TABLE.
           05  SITE-ENTRY OCCURS 400 TIMES INDEXED BY SITE-IX.
               10  SITE-CODE   PIC X(6).
               10  SITE-NAME   PIC X(20).
```

After (and SEARCH ALL as in [serial-search-keyed](#serial-search-keyed)):

```cobol
       01  WS-SITE-TABLE.
           05  SITE-COUNT      PIC S9(4) COMP-5 VALUE 0.
           05  SITE-ENTRY OCCURS 1 TO 400 TIMES
                   DEPENDING ON SITE-COUNT
                   ASCENDING KEY IS SITE-CODE
                   INDEXED BY SITE-IX.
               10  SITE-CODE   PIC X(6).
               10  SITE-NAME   PIC X(20).
```

**Known false positives.** The table holds far fewer entries than its OCCURS maximum: perf.py uses the declared maximum. The most frequent entries are already first. The table is searched once per run.

**Measure.** As for serial-search-keyed.

## display-arithmetic-in-loop

ADD, SUBTRACT, MULTIPLY, DIVIDE or COMPUTE inside a loop on a numeric item whose USAGE is DISPLAY (zoned decimal), taken from the item or from its group; also the variable of a PERFORM VARYING, which the loop adds to on every pass. One finding per data item, with every line that uses it. Confidence high for WORKING-STORAGE and LOCAL-STORAGE items, medium for FILE and LINKAGE items.

**Why it costs time.** The machine does decimal arithmetic on packed data or binary arithmetic in registers. A DISPLAY number is packed before each statement and unpacked, with a sign fix, after it. COMP-3 (packed decimal) skips the conversions; COMP-5 (native binary) uses register arithmetic and is the fastest for counters and subscripts up to 9 digits. Above 9 digits binary needs 64-bit arithmetic and conversions for scaling, so COMP-3 is the safer choice. COMP and BINARY follow the TRUNC option: with TRUNC(STD) the compiler adds code to truncate to the PIC digits; COMP-5 does not.

**Fix.** Counters: `PIC S9(n) COMP-5` (or COMP). Amounts and anything with decimal places: `PIC S9(n)V99 COMP-3`, with a sign and an odd total of digits so the packed field has no spare half byte.

Before:

```cobol
       01  WS-COUNTERS.
           05  WS-MOVE-COUNT   PIC 9(7)     VALUE ZERO.
           05  WS-VALUE-TOTAL  PIC S9(9)V99 VALUE ZERO.
```

After:

```cobol
       01  WS-COUNTERS.
           05  WS-MOVE-COUNT   PIC S9(9)    COMP-5 VALUE ZERO.
           05  WS-VALUE-TOTAL  PIC S9(9)V99 COMP-3 VALUE ZERO.
```

Before changing a USAGE, check every place that depends on the bytes: a REDEFINES of the item or its group, a group MOVE into or out of the group, a DISPLAY or a report line that prints it, a record written to a file, a parameter passed to another program. `zscan.py show <PROGRAM>` and the data dictionary list them.

**Known false positives.** An item in a record layout (FILE or LINKAGE section): changing it changes the file or the interface, and when the field is used once per record a working copy costs the same conversion; that is why it is medium. A loop that runs a few times. Recent compilers with OPTIMIZE and a high ARCH level make DISPLAY arithmetic cheaper, but not free.

**Measure.** The step's CPU time (SMF type 30) on the same input. Compare the output files byte for byte: the change must not alter results or printed formats.

## display-subscript-in-loop

A numeric item with USAGE DISPLAY used as a subscript inside a loop: in a statement, in an IF, EVALUATE WHEN or SEARCH WHEN condition, or in the UNTIL of a looping PERFORM. Index names (INDEXED BY) and binary or packed subscripts are not reported. One finding per data item; when it is also the loop's VARYING variable, that is part of the same finding. Confidence as for display-arithmetic-in-loop.

**Why it costs time.** To address `TAB (I)` the program converts I to binary, multiplies by the entry length and adds the table address. A DISPLAY subscript is converted on every reference. An index already holds the byte offset, so the address is one load and an add. With the SSRANGE option every reference is also range-checked, which makes each reference cost more.

**Fix.** Give the table INDEXED BY and loop on the index, or make the subscript `PIC S9(4) COMP-5` (`S9(8)` for tables over 9,999 entries).

Before:

```cobol
       01  WS-SUB              PIC 9(3) VALUE ZERO.

           PERFORM VARYING WS-SUB FROM 1 BY 1 UNTIL WS-SUB > 20
               ADD WS-RATE TO BIN-AMT (WS-SUB)
           END-PERFORM
```

After:

```cobol
       01  WS-BIN-AMOUNTS.
           05  BIN-AMT  PIC S9(7)V99 COMP-3 OCCURS 20 INDEXED BY BIN-IX.

           PERFORM VARYING BIN-IX FROM 1 BY 1 UNTIL BIN-IX > 20
               ADD WS-RATE TO BIN-AMT (BIN-IX)
           END-PERFORM
```

An index belongs to its table: change it with SET, not MOVE, and to print it SET a numeric item TO the index first.

**Known false positives.** A subscript taken from an input record and used once per record: a binary copy costs the same conversion. A subscript that is also printed or written, so its DISPLAY form is needed: keep it and add a binary copy for the subscripting. A short loop.

**Measure.** The step's CPU time on the same input.

## initialize-group-in-loop

INITIALIZE of a group item inside a loop. Confidence high when the group holds a table (OCCURS), medium otherwise. The finding gives the number of elementary fields INITIALIZE sets (FILLER and REDEFINES skipped, OCCURS multiplied).

**Why it costs time.** INITIALIZE becomes one move per elementary field: SPACES to each alphanumeric, ZERO to each numeric field (with a conversion for DISPLAY and packed fields), repeated for every table entry. A MOVE of a prepared copy of the group is one block move.

**Fix.** Initialize a template once before the loop and move it into the group in the loop, or reset only the fields the loop changes.

Before:

```cobol
       2000-PROCESS.
           INITIALIZE WS-SLIP
           MOVE IN-ITEM TO SLIP-ITEM
```

After (WS-SLIP-EMPTY has the length of WS-SLIP; the compiler listing's data map shows it):

```cobol
       01  WS-SLIP-EMPTY       PIC X(190).

       1000-INIT.
           INITIALIZE WS-SLIP
           MOVE WS-SLIP TO WS-SLIP-EMPTY.
       2000-PROCESS.
           MOVE WS-SLIP-EMPTY TO WS-SLIP
           MOVE IN-ITEM TO SLIP-ITEM
```

**Known false positives.** A small group of a few fields. INITIALIZE ... REPLACING that sets only one category. A group with OCCURS DEPENDING ON, where a group MOVE uses the current length: check that the template matches. A loop that runs a few times.

**Measure.** The step's CPU time.

## string-op-in-loop

STRING, UNSTRING or INSPECT inside a loop. Confidence low: listed only with `--min-confidence low`.

**Why it costs time.** These statements examine their operands byte by byte: STRING and UNSTRING look for each delimiter, INSPECT scans the whole field for each TALLYING or REPLACING phrase. Inside a loop over many records the scans add up. When every piece has a fixed length, moves with reference modification do the same work with block moves.

**Fix.** Use fixed-position moves when the lengths are fixed, move work that does not depend on the record out of the loop, or keep the statement when the loop is short.

Before:

```cobol
           STRING IN-ITEM DELIMITED BY SIZE
                  ' - '   DELIMITED BY SIZE
                  IN-NOTE DELIMITED BY SIZE
                  INTO WS-LINE
           END-STRING
```

After (only because every part is DELIMITED BY SIZE):

```cobol
           MOVE IN-ITEM TO WS-LINE (1:6)
           MOVE ' - '   TO WS-LINE (7:3)
           MOVE IN-NOTE TO WS-LINE (10:40)
```

**Known false positives.** Parsing of variable data, where nothing simpler exists. A short loop. Most real programs have a few of these; that is why they are low.

**Measure.** The step's CPU time, and a profiler for the share of time in the paragraph.

## execio-in-loop

REXX `EXECIO` inside a loop. Confidence high when it reads or writes one record per call (`EXECIO 1`) or the whole file on every pass (`EXECIO *`); medium for a larger count.

**Why it costs time.** Each EXECIO is a call into TSO/E with its own parameter checking, and with DISKW one record per call the buffer is handed over record by record. Interpreted REXX adds the cost of the command string itself. Thousands of one-record EXECIO calls cost far more than one call with a stem.

**Fix.**

```rexx
/* before: one record per pass */
do i = 1 to n
  push line.i
  "EXECIO 1 DISKW OUTDD"
end
/* after: build a stem, write it once */
do i = 1 to n
  out.i = line.i
end
out.0 = n
"EXECIO" out.0 "DISKW OUTDD (STEM out. FINIS"
```

Reading: `"EXECIO * DISKR INDD (STEM rec. FINIS"` once, then loop over `rec.1` to `rec.0`. For a file too large for storage, read in blocks of a few thousand records (`EXECIO 5000 DISKR INDD (STEM rec.`) instead of one.

**Known false positives.** A loop that runs a handful of times; a data set read one record at a time on purpose to stop early (then read in blocks); an exec waiting on a file another task writes.

**Measure.** The step's CPU time and EXCP count for the DD (SMF type 30), before and after.

## alloc-free-in-loop

REXX `ALLOC` or `FREE` (TSO commands, or BPXWDYN) inside a loop. Confidence high.

**Why it costs time.** Dynamic allocation searches the catalog, may wait for an ENQ on the data set name, and may mount a volume; FREE releases all of it. Per iteration it costs far more than the records the iteration reads.

**Fix.** Allocate once before the loop, free once after. When the data set name changes per iteration, sort the work by data set and allocate each one once; keep a DD per data set open when there are few.

```rexx
/* before */
do i = 1 to n
  "ALLOC FI(WORK) DA('"dsn"') SHR REUSE"
  "EXECIO * DISKR WORK (STEM rec. FINIS"
  "FREE FI(WORK)"
end
/* after: one allocation for the data set the loop reads */
"ALLOC FI(WORK) DA('"dsn"') SHR REUSE"
"EXECIO * DISKR WORK (STEM rec. FINIS"
do i = 1 to rec.0
  /* work on rec.i */
end
"FREE FI(WORK)"
```

**Known false positives.** A loop over a list of data sets that must each be allocated once (that is one allocation per data set, the minimum).

**Measure.** Elapsed time and CPU of the step; SMF type 30 allocation counts.

## host-command-in-loop

A host command (ADDRESS TSO, MVS, ISPEXEC, ISREDIT, SYSCALL...) inside a loop, other than EXECIO, ALLOC, FREE, programs run (see static-call-in-loop) and SQL. Confidence medium for TSO, MVS and CONSOLE commands, low for ISPF and z/OS UNIX services, which are made to be called per row.

**Why it costs time.** Every TSO command is attached as a command processor: its load module is located, a parameter list is built and the command parses its operands. LISTDS, LISTCAT or SYSDSN-like checks per item multiply catalog searches.

**Fix.** One command for the whole set (LISTCAT with a LEVEL pattern, one LISTDS with several names, OUTTRAP around one call), or move the command before the loop when its result does not change. For ISPF tables, use one TBSCAN or TBSORT instead of reading every row with TBSKIP when only some rows are needed.

```rexx
/* before: one LISTDS per name */
do i = 1 to dsn.0
  "LISTDS '"dsn.i"'"
end
/* after: one LISTCAT for the level, trapped once */
call outtrap "cat."
"LISTCAT LEVEL('"hlq"')"
call outtrap "OFF"
```

**Known false positives.** Commands that must run per item (a SUBMIT per generated job, an ISPF display per screen).

**Measure.** CPU time of the step or the TSO session; for ISPF, the number of service calls (ISPF trace).

## Measuring

- Use the same input, the same volume and a quiet system for the run before and the run after; run each at least twice.
- Batch: the step's CPU time (TCB and SRB), EXCP counts per DD and elapsed time from SMF type 30 (subtype 4 for steps), or the step summary in the job log.
- Db2: accounting records (SMF type 101): class 1 and class 2 CPU and elapsed time, SQL counts by type, getpages.
- CICS: performance class records (SMF type 110): CPU time and response time per transaction.
- Record the compile options of both builds: OPTIMIZE, ARCH, NUMPROC, TRUNC, SSRANGE and DYNAM change the generated code as much as some of these fixes.
- Compare outputs: files byte for byte, report lines, Db2 row counts. A performance fix must not change results.

## What 1.1 does not check

- Loops built with GO TO, and loops in a calling program (a note in the report says when a program is called from another program's loop).
- DISPLAY numbers compared in conditions inside loops, such as the UNTIL of the loop itself.
- Packed (COMP-3) subscripts, which are converted too, at a lower cost than DISPLAY.
- EXEC CICS commands inside loops, COMMIT frequency, SORT, READ INTO and WRITE FROM moves.
- Buffering and blocking (BLKSIZE, BUFNO, VSAM BUFND and BUFNI) and anything set in JCL rather than in the program.
- Assembler programs (listed as not reviewed in 1.1).
- PL/I: arithmetic and conversions on PICTURE and character data in loops, FIXED DECIMAL precision, STRING built-ins, ON-unit cost, and REPEAT/UNTIL loops built with GO TO.
- REXX: string handling and stem growth in loops, INTERPRET, compiled versus interpreted execs, and anything after an ADDRESS VALUE whose environment is unknown.

For a full performance analysis at scale, with IBM's own analysers and refactoring, point to the IBM Bob Premium Package for Z.
