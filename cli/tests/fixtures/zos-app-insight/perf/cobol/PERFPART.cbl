       IDENTIFICATION DIVISION.
       PROGRAM-ID. PERFPART.
      *----------------------------------------------------------------
      *  Synthetic test program for cobol-perf-review: copybook PERFGONE
      *  is missing on purpose, so the items it holds are unknown and
      *  the review must list them as not checked. PERFTAB is found.
      *  PART-CNT is defined twice; only the qualified uses resolve.
      *----------------------------------------------------------------
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY PERFGONE.
       COPY PERFTAB.
       01  WS-I                    PIC 9(3) VALUE ZERO.
       01  GRP-A.
           05  PART-CNT            PIC 9(5) VALUE ZERO.
       01  GRP-B.
           05  PART-CNT            PIC S9(5) COMP-3 VALUE ZERO.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM SUM-ONE
               VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 12
           GOBACK.
       SUM-ONE.
           ADD GONE-AMT TO GONE-TOTAL
           MOVE ZERO TO GONE-TAB (WS-I)
           ADD 1 TO PART-CNT OF GRP-A
           ADD 1 TO PART-CNT IN GRP-B
           ADD CORRESPONDING GRP-A TO GRP-B
           EVALUATE TRUE
               WHEN TB-AMT (WS-I) < ZERO
                   CONTINUE
               WHEN OTHER
                   ADD TB-AMT (WS-I) TO TB-TOTAL
           END-EVALUATE.
