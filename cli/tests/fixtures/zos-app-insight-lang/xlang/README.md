# zos-app-insight cross-language test fixtures

Original files, written by the Bob Skills Marketplace team for the integration tests of the
zos-app-insight pack, and licensed under Apache-2.0 like the rest of the repository. Nothing
is copied from IBM samples or any other source. They tie the PL/I, REXX and Assembler
fixtures of the folders next to this one to COBOL and JCL:

- `cobol/BILLDRV.cbl`: a COBOL program that calls the PL/I entry RECALC and, inside a
  `PERFORM 3 TIMES`, the Assembler entry BILLALT.
- `pli/BILLCALC.pli`: an external PL/I procedure with a second entry point (RECALC) and a
  CALL of an external routine inside an iterative DO loop.
- `jcl/BILLJOB.jcl`: steps that run the PL/I program BILLMAIN, the PL/I entry RECALC, the
  Assembler program BILLRUN, two REXX execs through IKJEFT01 (`%ORDLOAD` and
  `EXEC 'BILL.EXEC(ORDMENU)'`, next to a TSO command, LISTCAT) and one through IRXJCL.
