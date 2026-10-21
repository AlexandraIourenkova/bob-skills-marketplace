       IDENTIFICATION DIVISION.
       PROGRAM-ID. PERFNEG.
      *----------------------------------------------------------------
      *  Synthetic test program for cobol-perf-review: the negative
      *  twin of PERFPOS. Each pattern here is the tuned form, or sits
      *  outside every loop, so no check may fire.
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MOVE-FILE ASSIGN TO MOVES.
           SELECT AUDIT-FILE ASSIGN TO AUDIT.
       DATA DIVISION.
       FILE SECTION.
       FD  MOVE-FILE
           RECORDING MODE IS F.
       01  MOVE-REC.
           05  MV-ITEM             PIC X(6).
           05  MV-QTY              PIC S9(5) COMP-3.
           05  MV-NOTE             PIC X(40).
       FD  AUDIT-FILE
           RECORDING MODE IS F.
       01  AUDIT-REC               PIC X(80).
       WORKING-STORAGE SECTION.
       01  WS-EOF                  PIC X VALUE 'N'.
           88  END-OF-MOVES        VALUE 'Y'.
       01  WS-COUNTERS USAGE COMP-3.
           05  WS-MOVE-COUNT       PIC S9(7) VALUE ZERO.
           05  WS-VALUE-TOTAL      PIC S9(9)V99 VALUE ZERO.
       01  WS-SUB                  PIC S9(4) COMP-5 VALUE ZERO.
       01  WS-DISPLAY-COUNT        PIC 9(5) VALUE ZERO.
       01  WS-PRICE-TABLE.
           05  PRICE-ENTRY OCCURS 60 TIMES
                   ASCENDING KEY IS PR-ITEM
                   INDEXED BY PR-IX.
               10  PR-ITEM         PIC X(6).
               10  PR-RATE         PIC V999.
       01  WS-SMALL-TABLE.
           05  SMALL-ENTRY OCCURS 20 TIMES INDEXED BY SM-IX.
               10  SM-CODE         PIC X(2).
       01  WS-BIN-AMOUNTS.
           05  BIN-AMT             PIC S9(7)V99 COMP-3 OCCURS 20.
       01  WS-SLIP.
           05  SLIP-ITEM           PIC X(6).
           05  SLIP-QTY            PIC S9(5) COMP-3.
       01  WS-RATE                 PIC SV999 COMP-3.
       01  WS-ITEM-HOLD            PIC X(6).
       01  WS-TEXT                 PIC X(80).
           EXEC SQL INCLUDE SQLCA END-EXEC.
           EXEC SQL
               DECLARE ITEMCUR CURSOR FOR
               SELECT ITEM, QTY
                 FROM STOCK.ITEMS
                FOR UPDATE OF QTY
           END-EXEC.
       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT MOVE-FILE
                OUTPUT AUDIT-FILE
           INITIALIZE WS-SLIP
           CALL 'PERFCALC' USING MOVE-REC
           ADD 1 TO WS-DISPLAY-COUNT
           STRING 'RUN ' DELIMITED BY SIZE INTO WS-TEXT
           EXEC SQL
               SELECT RATE INTO :WS-RATE
                 FROM STOCK.RATES
                WHERE ITEM = 'ALL'
           END-EXEC
           EXEC SQL OPEN ITEMCUR END-EXEC
           PERFORM FETCH-ITEM UNTIL SQLCODE NOT = 0
           EXEC SQL CLOSE ITEMCUR END-EXEC
           PERFORM READ-MOVE
           PERFORM COUNT-MOVE UNTIL END-OF-MOVES
           CLOSE MOVE-FILE AUDIT-FILE
           GOBACK.
       FETCH-ITEM.
           EXEC SQL
               FETCH ITEMCUR INTO :WS-ITEM-HOLD, :SLIP-QTY
           END-EXEC
           IF SQLCODE = 0
               EXEC SQL
                   UPDATE STOCK.ITEMS SET QTY = 0
                    WHERE CURRENT OF ITEMCUR
               END-EXEC
           END-IF.
       READ-MOVE.
           READ MOVE-FILE
               AT END SET END-OF-MOVES TO TRUE
           END-READ.
       COUNT-MOVE.
           ADD 1 TO WS-MOVE-COUNT
           COMPUTE WS-VALUE-TOTAL = WS-VALUE-TOTAL + MV-QTY
           SEARCH ALL PRICE-ENTRY
               AT END MOVE ZERO TO WS-RATE
               WHEN PR-ITEM (PR-IX) = MV-ITEM
                   MOVE PR-RATE (PR-IX) TO WS-RATE
           END-SEARCH
           SET SM-IX TO 1
           SEARCH SMALL-ENTRY
               WHEN SM-CODE (SM-IX) = MV-ITEM (1:2)
                   CONTINUE
           END-SEARCH
           PERFORM VARYING WS-SUB FROM 1 BY 1 UNTIL WS-SUB > 20
               ADD WS-RATE TO BIN-AMT (WS-SUB)
           END-PERFORM
           INITIALIZE SLIP-QTY
           MOVE MV-ITEM TO SLIP-ITEM
           MOVE MV-NOTE (1:20) TO WS-TEXT (1:20)
           WRITE AUDIT-REC FROM MOVE-REC
           PERFORM READ-MOVE.
