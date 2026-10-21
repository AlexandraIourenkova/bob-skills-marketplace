       IDENTIFICATION DIVISION.
       PROGRAM-ID. PERFCALC.
      *----------------------------------------------------------------
      *  Synthetic subroutine for the cobol-perf-review tests. It has
      *  no loop of its own; PERFPOS calls it once per record.
      *----------------------------------------------------------------
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CALLS                PIC 9(7) VALUE ZERO.
       LINKAGE SECTION.
       01  LK-REC.
           05  LK-ITEM             PIC X(6).
           05  LK-QTY              PIC 9(5).
       PROCEDURE DIVISION USING LK-REC.
       MAIN-PARA.
           ADD 1 TO WS-CALLS
           GOBACK.
