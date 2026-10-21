# zos-app-insight PL/I test fixtures

A small PL/I part of the synthetic order-billing application, for the tests of
`zscan_pli.py` in the zos-app-insight pack. Every file here is original, written by the
Bob Skills Marketplace team for these tests, and licensed under Apache-2.0 like the rest
of the repository. Nothing is copied from IBM samples or any other source.

- `src/BILLMAIN.pli`: the main procedure, in the default margins (columns 2 to 72) with
  sequence numbers in columns 73 to 80. Internal procedures (one a function with RETURNS),
  an external CALL of the COBOL routine PRICECAL, a FETCH of BILLTAX with its module name
  in a variable, %INCLUDE members (one in the `LIB(MEMBER)` form, one nested, and AUDITPL,
  missing on purpose), DCL structures with levels, dimensions, BASED, DEFINED, INIT,
  FIXED DEC, FIXED BIN, CHAR VARYING and PIC, two files with OPEN, READ, WRITE, CLOSE and
  ON ENDFILE, an ON ERROR BEGIN block, EXEC SQL with a cursor FETCH inside DO UNTIL and a
  singleton SELECT in a procedure called from a loop, IF with an ELSE IF chain, SELECT with
  WHEN and OTHERWISE, DO WHILE, DO UNTIL, iterative DO, nested loops, GO TO inside a loop
  and one that leaves it, and a preprocessor %IF that the scanner warns about.
- `src/BILLSUB.pli`: an external subroutine with `*PROCESS MARGINS(1,80)`: its code starts
  in column 1 and one declaration runs past column 72. A keyed VSAM file with READ KEY,
  REWRITE and ON KEY.
- `inc/`: the include members BILLREC, BILLCNT (includes BILLWS) and BILLWS.
