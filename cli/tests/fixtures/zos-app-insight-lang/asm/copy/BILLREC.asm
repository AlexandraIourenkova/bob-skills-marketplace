* BILLREC: the usage record, as a DSECT. Original test fixture.
USAGEREC DSECT
UR_KEY   DS    0CL12                   account and sequence
UR_ACCT  DS    CL8
UR_SEQ   DS    XL4
UR_DATE  DS    CL8                     YYYYMMDD
UR_UNITS DS    PL5
UR_FLAGS DS    X
UR_TAXED EQU   X'80'
UR_LATE  EQU   X'40'
         DS    0F
UR_AMTS  DS    3F                      three amounts
         ORG   UR_DATE
UR_YEAR  DS    CL4
UR_MMDD  DS    CL4
         ORG
UR_NOTE  DS    CL20
UR_LEN   EQU   *-USAGEREC
         COPY  INVLINE
