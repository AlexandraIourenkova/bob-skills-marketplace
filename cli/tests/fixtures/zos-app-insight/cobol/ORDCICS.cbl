       IDENTIFICATION DIVISION.
       PROGRAM-ID. ORDCICS.
      *  Online order inquiry: reads a customer, prices it, moves on.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CUST-REC             PIC X(80).
       01  WS-CUST-KEY             PIC X(8).
       01  WS-NEXT-PGM             PIC X(8) VALUE SPACES.
       01  WS-COMMAREA             PIC X(100).
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC CICS READ FILE('CUSTFIL') INTO(WS-CUST-REC)
                     RIDFLD(WS-CUST-KEY)
           END-EXEC.
           EXEC CICS LINK PROGRAM('PRICECAL')
                     COMMAREA(WS-COMMAREA)
           END-EXEC.
           MOVE 'ORDMENU' TO WS-NEXT-PGM.
           EXEC CICS XCTL PROGRAM(WS-NEXT-PGM) END-EXEC.
           EXEC CICS RETURN END-EXEC.
