*---------------------------------------------------------------------* 00000100
* BILLRUN: nightly billing run. Reads usage records, prices each        00000200
* one and writes invoice lines. Original test fixture, Apache-2.0.      00000300
*---------------------------------------------------------------------* 00000400
.* a macro-style comment line: skipped as well                          00000500
BILLRUN  CSECT                                                          00000600
BILLRUN  AMODE 31                                                       00000700
BILLRUN  RMODE ANY                                                      00000800
         ENTRY BILLALT                                                  00000900
         EXTRN TAXTAB                                                   00001000
         BSAVE BASE=R12                library macro, defined in maclib 00001100
         USING BILLRUN,R12                                              00001200
         USING USAGEREC,R6                                              00001300
         LA    R6,INREC                point at the record's first byte 00001400
         MVC   HEADDATE(L'HEADDATE),=CL10'2026-10-21'                   00001500
         BAL   R14,OPENALL                                              00001600
         L     R5,MAXRECS              record limit: the BCT counter    00001700
READLOOP GET   USAGEIN,INREC                                            00001800
         AP    RECCNT,=P'1'                                             00001900
         BAL   R14,PRICEIT                                              00002000
         PUT   INVOUT,OUTREC                                            00002100
         BCT   R5,READLOOP             next record                      00002200
EOFIN    DS    0H                                                       00002300
         BAL   R14,CLOSEALL                                             00002400
         BAL   R14,TRIMNOTE                                             00002500
         BAS   R14,AUDITIT             AUDITIT was in AUDITDS           00002600
         CALL  TAXCALC,(TOTAL,RATE),VL                                  00002700
         LINK  EP=PRTFMT,PARAM=(OUTREC),VL=1                            00002800
         LOAD  EPLOC=(R3)              name set at run time             00002900
         LR    R15,R0                                                   00003000
         LOAD  EP=RATETBL                                               00003100
         L     R15,=V(DATEFMT)                                          00003200
         BASR  R14,R15                                                  00003300
         TRACEPT ID=9                  a macro nobody defines           00003400
         B     RETURN                                                   00003500
BILLALT  DS    0H                      second entry point               00003600
         SR    R15,R15                                                  00003700
RETURN   L     R13,4(,R13)                                              00003800
         LM    R14,R12,12(R13)                                          00003900
         BR    R14                                                      00004000
*                                                                       00004100
* PRICEIT: price one usage record; walk the tier table                  00004200
*                                                                       00004300
PRICEIT  ST    R14,PRICSAVE                                             00004400
         ZAP   AMOUNT,UR_UNITS                                          00004500
         MP    AMOUNT,UNITPRC                                           00004600
         LA    R7,TIERS                                                 00004700
         LA    R8,3                                                     00004800
TIERLOOP CP    AMOUNT,0(4,R7)                                           00004900
         BL    TIERDONE                                                 00005000
         LA    R7,4(,R7)                                                00005100
         BCTR  R8,0                    count down, no branch            00005200
         LTR   R8,R8                                                    00005300
         BNZ   TIERLOOP                conditional branch back          00005400
TIERDONE L     R14,PRICSAVE                                             00005500
         BR    R14                                                      00005600
*                                                                       00005700
OPENALL  OPEN  (USAGEIN,(INPUT),INVOUT,(OUTPUT))                        00005800
         BR    R14                                                      00005900
CLOSEALL CLOSE (USAGEIN,,INVOUT)                                        00006000
         BR    R14                                                      00006100
TRIMNOTE LA    R7,NOTE                                                  00006200
         LA    R9,TRIMTOP                                               00006300
         LA    R8,8                                                     00006400
TRIMTOP  CLI   0(R7),C' '                                               00006500
         BNE   TRIMEND                                                  00006600
         LA    R7,1(,R7)                                                00006700
         BCTR  R8,R9                   back to the address in R9        00006800
TRIMEND  L     R10,WAITADR                                              00006900
         BCTR  R4,R10                  an address from storage          00007000
         BR    R14                                                      00007100
*                                                                       00007200
* storage                                                               00007300
*                                                                       00007400
MAXRECS  DC    F'500'                                                   00007500
RECCNT   DC    PL4'0'                                                   00007600
AMOUNT   DS    PL8                                                      00007700
TOTAL    DC    PL8'0'                                                   00007800
RATE     DC    PL3'0.07'                                                00007900
UNITPRC  DC    P'125'                                                   00008000
TIERS    DC    3PL4'0'                 duplication factor 3             00008100
PRICSAVE DS    F                                                        00008200
WAITADR  DC    A(TRIMTOP)                                               00008300
SAVEAREA DC    18F'0'                                                   00008400
HEADING  DS    0CL40                                                    00008500
         DC    CL10'INVOICE'                                            00008600
HEADDATE DC    CL10' '                                                  00008700
         DC    20C'-'                                                   00008800
NOTE     DC    C'IT''S DUE ON RECEIPT,  TWO BLANKS KEPT, AND THIS TEXT X00008900
               RUNS PAST THE END OF THE LINE'                           00009000
INREC    DS    CL80                                                     00009100
OUTREC   DS    CL133                                                    00009200
USAGEIN  DCB   DDNAME=USAGEIN,DSORG=PS,MACRF=GM,RECFM=FB,LRECL=80,     X00009300
               EODAD=EOFIN                                              00009400
INVOUT   DCB   DDNAME=INVOICE,DSORG=PS,MACRF=PM,       output DCB      X00009500
               RECFM=FBA,LRECL=133                                      00009600
         COPY  AUDITDS                 missing on purpose               00009700
         COPY  BILLREC                                                  00009800
         YREGS                                                          00009900
         END   BILLRUN                                                  00010000
