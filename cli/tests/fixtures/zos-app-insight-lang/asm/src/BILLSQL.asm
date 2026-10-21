* BILLSQL: CICS transaction that settles a region's customers in DB2.
* Original test fixture, Apache-2.0.
BILLSQL  CSECT
         DFHEIENT
         EXEC  SQL INCLUDE SQLCA
         EXEC  SQL DECLARE C1 CURSOR FOR SELECT CUSTID, BALANCE        X
               FROM BILL.CUSTOMER WHERE REGION = :REGION
         EXEC  SQL OPEN C1
FETCHTOP EXEC  SQL FETCH C1 INTO :CUSTID, :BALANCE
         CLC   SQLCODE,=F'100'
         BE    FETCHEND
         EXEC  CICS LINK PROGRAM('CUSTINQ') COMMAREA(COMM)             X
               LENGTH(80)
         B     FETCHTOP                next row
FETCHEND EXEC  SQL CLOSE C1
         EXEC  CICS LINK PROGRAM(PGMNAME) COMMAREA(COMM)
         MVC   NEXTPGM,=CL8'BILLEND'
         LINK  EPLOC=NEXTPGM
         DO    WHILE=(CLI,MOREFLAG,EQ,C'Y')
         EXEC  SQL UPDATE BILL.CUSTOMER SET BALANCE = 0                X
               WHERE CUSTID = :CUSTID
         ENDDO
         L     R15,RETCODE
         SLL   R15,2
         B     RCTAB(R15)              a branch table
RCTAB    B     RCOK
         B     RCERR
RCOK     XCTL  EP=BILLMENU             on to the menu program
EXIT     DFHEIRET RCREG=R15
RCERR    MVC   COMM(8),=CL8'FAILED'
         B     EXIT                    back to the exit, not a loop
*
PGMNAME  DC    CL8'CUSTUPD'
NEXTPGM  DC    CL8'BILLNXT'
MOREFLAG DC    C'N'
RETCODE  DC    F'0'
COMM     DS    CL80
REGION   DS    CL4
         EXEC  SQL INCLUDE CUSTDCL
         DFHEISTG
         DFHEIEND
         END   BILLSQL
