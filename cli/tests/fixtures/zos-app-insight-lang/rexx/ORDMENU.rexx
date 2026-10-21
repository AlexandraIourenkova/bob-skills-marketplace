/* REXX - ORDMENU: menu of the order-billing team (test data, Apache-2.0) */
arg choice
call on error name cmd_error
address tso newstack
"ALTLIB ACTIVATE APPLICATION(EXEC) DATASET('BILL.EXEC')"
x = outtrap('lst.')
"LISTDS 'BILL.ORDERS.DAILY' MEMBERS"
x = outtrap('OFF')
prog = 'ORDSTAT'
if choice = 'S' then prog = 'ORDSUMM'
address linkmvs prog "choice"
address attchmvs "ORDARCH"
"CALL 'BILL.LOADLIB(ORDPURGE)' 'DAYS=30'"
"%ORDRPT" choice
"EXEC 'BILL.EXEC(ORDLOAD)' 'TEST' EXEC"
address ispexec "LIBDEF ISPPLIB DATASET ID('BILL.PANELS')"
address ispexec "SELECT CMD(%ORDHELP 2) NEWAPPL(ORD)"
address ispexec "SELECT PGM(ORDBROW) PARM(DAILY)"
rc = bpxwdyn("ALLOC FI(ORDTMP) DA('BILL.ORDERS.TEMP') NEW CATALOG")
address syscall "writefile /u/bill/ordmenu.log 644 lst."
address mvs "EXECIO 0 DISKW ORDTMP (FINIS"
address isredit "SAVE"
exit 0

cmd_error:
  say 'command failed rc' rc 'line' sigl
  return
