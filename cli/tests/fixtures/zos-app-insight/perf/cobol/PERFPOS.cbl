       IDENTIFICATION DIVISION.
       PROGRAM-ID. PERFPOS.
      *----------------------------------------------------------------
      *  Synthetic test program for cobol-perf-review: one positive
      *  case for every check. Reads stock movements and prices them.
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MOVE-FILE ASSIGN TO MOVES
               FILE STATUS IS WS-MOVE-STATUS.
           SELECT AUDIT-FILE ASSIGN TO AUDIT.
           SELECT ERR-FILE ASSIGN TO ERRLOG.
       DATA DIVISION.
       FILE SECTION.
       FD  MOVE-FILE
           RECORDING MODE IS F.
       01  MOVE-REC.
           05  MV-ITEM             PIC X(6).
           05  MV-QTY              PIC 9(5).
           05  MV-PRICE            PIC 9(5)V99.
           05  MV-NOTE             PIC X(40).
       FD  AUDIT-FILE
           RECORDING MODE IS F.
       01  AUDIT-REC               PIC X(80).
       FD  ERR-FILE
           RECORDING MODE IS F.
       01  ERR-REC                 PIC X(80).
       WORKING-STORAGE SECTION.
       01  WS-MOVE-STATUS          PIC XX VALUE SPACES.
       01  WS-EOF                  PIC X VALUE 'N'.
           88  END-OF-MOVES        VALUE 'Y'.
       01  WS-COUNTERS.
           05  WS-MOVE-COUNT       PIC 9(7) VALUE ZERO.
           05  WS-VALUE-TOTAL      PIC S9(9)V99 VALUE ZERO.
           05  WS-BIN              PIC 9(3) VALUE ZERO.
           05  WS-ERR-COUNT        PIC S9(4) COMP VALUE ZERO.
       01  WS-PRICE-TABLE.
           05  PRICE-ENTRY OCCURS 60 TIMES
                   ASCENDING KEY IS PR-ITEM
                   INDEXED BY PR-IX.
               10  PR-ITEM         PIC X(6).
               10  PR-RATE         PIC V999.
       01  WS-SITE-TABLE.
           05  SITE-ENTRY OCCURS 400 TIMES INDEXED BY SITE-IX.
               10  SITE-CODE       PIC X(6).
               10  SITE-NAME       PIC X(20).
       01  WS-BIN-AMOUNTS.
           05  BIN-AMT             PIC S9(7)V99 COMP-3 OCCURS 20.
       01  WS-SLIP.
           05  SLIP-ITEM           PIC X(6).
           05  SLIP-LINE OCCURS 8 TIMES.
               10  SLIP-QTY        PIC S9(5) COMP-3.
               10  SLIP-TEXT       PIC X(20).
       01  WS-RATE                 PIC SV999 COMP-3.
       01  WS-SITE-NAME            PIC X(20).
       01  WS-PRICER               PIC X(8) VALUE 'PERFRATE'.
       01  WS-TEXT                 PIC X(80).
       01  WS-WORD-1               PIC X(20).
       01  WS-WORD-2               PIC X(20).
       01  WS-SPACES               PIC S9(4) COMP VALUE ZERO.
       01  WS-PASS                 PIC 9 VALUE ZERO.
           EXEC SQL INCLUDE SQLCA END-EXEC.
           EXEC SQL
               DECLARE SITECUR CURSOR FOR
               SELECT SITE_NAME
                 FROM STOCK.SITES
                WHERE SITE_ITEM = :MV-ITEM
           END-EXEC.
       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT MOVE-FILE
           PERFORM 3 TIMES
               ADD 1 TO WS-PASS
           END-PERFORM
           PERFORM READ-MOVE
           PERFORM PRICE-MOVE UNTIL END-OF-MOVES
           GOBACK.
       READ-MOVE.
           READ MOVE-FILE
               AT END SET END-OF-MOVES TO TRUE
           END-READ.
       PRICE-MOVE.
           OPEN EXTEND AUDIT-FILE
           ADD 1 TO WS-MOVE-COUNT
           COMPUTE WS-VALUE-TOTAL = WS-VALUE-TOTAL + MV-QTY * MV-PRICE
           EXEC SQL
               SELECT RATE INTO :WS-RATE
                 FROM STOCK.RATES
                WHERE ITEM = :MV-ITEM
           END-EXEC
           EXEC SQL
               INSERT INTO STOCK.MOVES_LOG (ITEM, QTY)
               VALUES (:MV-ITEM, :MV-QTY)
           END-EXEC
           EXEC SQL
               UPDATE STOCK.ITEMS SET ON_HAND = ON_HAND - :MV-QTY
                WHERE ITEM = :MV-ITEM
           END-EXEC
           EXEC SQL
               DELETE FROM STOCK.HOLDS WHERE ITEM = :MV-ITEM
           END-EXEC
           EXEC SQL OPEN SITECUR END-EXEC
           EXEC SQL FETCH SITECUR INTO :WS-SITE-NAME END-EXEC
           EXEC SQL CLOSE SITECUR END-EXEC
           CALL 'PERFCALC' USING MOVE-REC
           CALL WS-PRICER USING MOVE-REC WS-RATE
           CANCEL WS-PRICER
           SET PR-IX TO 1
           SEARCH PRICE-ENTRY
               AT END MOVE ZERO TO WS-RATE
               WHEN PR-ITEM (PR-IX) = MV-ITEM
                   MOVE PR-RATE (PR-IX) TO WS-RATE
           END-SEARCH
           SET SITE-IX TO 1
           SEARCH SITE-ENTRY
               WHEN SITE-CODE (SITE-IX) = MV-ITEM
                   MOVE SITE-NAME (SITE-IX) TO WS-SITE-NAME
           END-SEARCH
           MOVE 1 TO WS-BIN
           PERFORM VARYING WS-BIN FROM 1 BY 1 UNTIL WS-BIN > 20
               ADD WS-RATE TO BIN-AMT (WS-BIN)
           END-PERFORM
           INITIALIZE WS-SLIP
           MOVE MV-ITEM TO SLIP-ITEM
           STRING MV-ITEM DELIMITED BY SIZE
                  MV-NOTE DELIMITED BY '  '
                  INTO WS-TEXT
           END-STRING
           UNSTRING MV-NOTE DELIMITED BY SPACE
               INTO WS-WORD-1 WS-WORD-2
           END-UNSTRING
           INSPECT MV-NOTE TALLYING WS-SPACES FOR ALL SPACE
           IF MV-QTY = ZERO
               OPEN EXTEND ERR-FILE
               WRITE ERR-REC FROM MOVE-REC
               CLOSE ERR-FILE
           END-IF
           WRITE AUDIT-REC FROM MOVE-REC
           CLOSE AUDIT-FILE
           PERFORM READ-MOVE.
