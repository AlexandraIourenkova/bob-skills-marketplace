# zos-app-insight REXX test fixtures

Small synthetic REXX execs for the tests of zscan_rexx.py, the REXX module of the
zos-app-insight map. Every file here is original, written by the Bob Skills Marketplace
team for these tests, and licensed under Apache-2.0 like the rest of the repository.
Nothing is copied from IBM samples or any other source.

- `ORDLOAD.rexx`: the order-billing load exec. A header with a nested comment, PARSE ARG,
  SIGNAL ON NOVALUE and SIGNAL to a label, strings with doubled quotes, an external CALL
  and an external function next to built-in functions (WORDS, LEFT, SYSDSN), ALLOC with
  a comma continuation, ALLOC NEW and FREE, EXECIO DISKR with a stem, EXECIO DISKW inside
  DO i = 1 TO n, EXECIO DISKR inside DO WHILE, IF/ELSE, SELECT/WHEN/OTHERWISE, DO FOREVER
  with LEAVE, DO n, ADDRESS ISPEXEC, ADDRESS LINKMVS running PRICECAL, DSNREXX with a
  prepared cursor, TSO DELETE and SUBMIT, internal routines with PROCEDURE EXPOSE, and a
  `/*%INCLUDE ORDUTIL */` compiler directive at the end.
- `ORDUTIL.rexx`: a member of routines that ORDLOAD includes; it starts with a label and
  has no EXIT, so it is classified as an include member.
- `ORDMENU.rexx`: a menu exec with CALL ON ERROR, OUTTRAP, ALTLIB, a LINKMVS program
  name held in a variable, ATTCHMVS, TSO CALL, EXEC and an implicit `%` exec, ISPEXEC
  LIBDEF and SELECT, BPXWDYN, SYSCALL, ADDRESS MVS EXECIO and ISREDIT SAVE.
- `ORDCLEAN.clist`: a CLIST, which the REXX module skips.

The data set, program and table names are invented for the tests.
