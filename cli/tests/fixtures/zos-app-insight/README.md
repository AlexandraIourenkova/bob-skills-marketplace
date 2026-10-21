# zos-app-insight test fixtures

A small synthetic order-billing application for the tests of the zos-app-insight pack.
Every file here is original, written by the Bob Skills Marketplace team for these tests,
and licensed under Apache-2.0 like the rest of the repository. Nothing is copied from IBM
samples or any other source.

- `cobol/`: ORDMAIN (fixed format with sequence numbers and columns 73-80, comment, page
  and debug lines, a continued literal, sections, PERFORM THRU, UNTIL, VARYING and TIMES,
  nested loops, static and dynamic CALL, GO TO, SEARCH ALL, IF inside EVALUATE), ORDDB2
  (free format, EXEC SQL with a cursor and a singleton SELECT inside a loop), ORDCICS
  (EXEC CICS READ, LINK and XCTL), PRICECAL (a subroutine with a LINKAGE SECTION),
  CUSTUPD (copies ORDREC as ORDMAIN does and CUSTREC with another REPLACING prefix; an
  IF/ELSE around READ with AT END, NOT AT END, INVALID KEY, NOT INVALID KEY, and COMPUTE
  ON SIZE ERROR).
- `copy/`: ORDREC, CUSTREC (tagged with `:PFX:` for COPY REPLACING), COMMLIB/WSCOMMON
  (copied with a library name, nests DATEWS) and DATEWS. AUDITREC is missing on purpose.
- `jcl/`: ORDNIGHT (continuations, SET symbols, an in-stream PROC, DD * data, a DSN with
  symbols, a cataloged PROC call with an override, a TSO batch step for DB2) and ORDWEEK
  (a missing PROC, a missing program and an unknown symbol, on purpose).
- `proclib/`: ORDPROC, the cataloged procedure.
- `legacy/`: one PL/I, one Assembler and one REXX file, listed as not analysed.

The comment in ORDMAIN that addresses an AI assistant is test data: it checks that source
text is quoted and never followed.
