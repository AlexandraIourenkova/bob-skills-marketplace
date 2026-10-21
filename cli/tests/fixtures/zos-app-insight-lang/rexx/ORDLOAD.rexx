/* REXX *************************************************************
 * ORDLOAD: load the day's orders, price each line and write the     *
 * billing file. Synthetic test data for zos-app-insight, Apache-2.0. *
 /* a nested comment: the header must not end here */                *
 ********************************************************************/
parse arg runDate mode .
signal on novalue
total = 0
say 'ORDLOAD can''t run twice a day; run date' runDate
say "Mode ""TEST"" bills nothing"
call ORDAUDIT 'START', runDate
stamp = ordstamp(runDate)
"ALLOC FI(ORDIN) DA('BILL.ORDERS.DAILY') SHR REUSE"
"ALLOC FI(ORDOUT) DA('BILL.ORDERS.PRICED') NEW CATALOG",
  "SPACE(5,5) TRACKS RECFM(F B) LRECL(80)"
if rc <> 0 then signal failed
"EXECIO * DISKR ORDIN (STEM ord. FINIS"
lines = words(ord.1)
do i = 1 to ord.0
  parse var ord.i custId 9 qty 13 price .
  call price_line custId, qty, price
  queue left(custId, 8) || right(lineTotal, 10)
  "EXECIO 1 DISKW ORDOUT"
end
"EXECIO 0 DISKR ORDCTL (OPEN"
more = 1
do while more
  "EXECIO 1 DISKR ORDCTL (STEM ctl."
  if rc = 2 then more = 0
  else call check_control ctl.1
end
"EXECIO 0 DISKR ORDCTL (FINIS"
select
  when mode = 'TEST' then say 'test run, nothing is billed'
  when mode = 'RERUN' then do
    say 'rerun of' runDate
    "DELETE 'BILL.ORDERS.PRICED.OLD'"
  end
  otherwise nop
end
tries = 0
do forever
  tries = tries + 1
  if sysdsn("'BILL.ORDERS.LOCK'") <> 'OK' then leave
  if tries > 3 then leave
  call ORDWAIT 5
end
address ispexec
"VGET (ZUSER) SHARED"
"DISPLAY PANEL(ORDPAN1)"
address tso
parmArea = runDate || mode
address linkmvs "PRICECAL parmArea"
ssid = 'DB2T'
address tso "SUBCOM DSNREXX"
if rc then s_rc = rxsubcom('ADD', 'DSNREXX', 'DSNREXX')
address dsnrexx "CONNECT" ssid
sqlText = "SELECT CUST_NAME FROM BILL.CUSTOMER WHERE CUST_ID = ?"
address dsnrexx
"EXECSQL DECLARE C1 CURSOR FOR S1"
"EXECSQL PREPARE S1 FROM :sqlText"
"EXECSQL OPEN C1 USING :custId"
"EXECSQL FETCH C1 INTO :custName"
"EXECSQL CLOSE C1"
"DISCONNECT"
address tso
do 2
  queue ''
end
"SUBMIT 'BILL.JCL(ORDNIGHT)'"
"FREE FI(ORDIN ORDOUT)"
say 'priced' total
exit 0

price_line: procedure expose total lineTotal
  parse arg cust, qty, price
  lineTotal = qty * price
  if qty > 100 then lineTotal = lineTotal * 0.95
  total = total + lineTotal
  return

check_control: procedure
  parse arg card
  if left(card, 1) = '*' then return
  say fmt_amount(substr(card, 10, 9))
  return

failed:
  say 'ORDLOAD failed at line' sigl 'rc' rc
  exit 12

novalue:
  say 'variable without a value at line' sigl
  exit 16
/*%INCLUDE ORDUTIL */
