# zos-app-insight Assembler test fixtures

A small synthetic billing application in HLASM for the tests of `zscan_asm.py` in the
zos-app-insight pack. Every file here is original, written by the Bob Skills Marketplace
team for these tests, and licensed under Apache-2.0 like the rest of the repository.
Nothing is copied from IBM samples or any other source.

- `src/BILLRUN.asm`: a batch program in fixed format with sequence numbers in columns
  73-80, `*` and `.*` comment lines, a CSECT with AMODE, RMODE, ENTRY and EXTRN, USING,
  DCBs continued in column 72 (one with a remark before the continuation), OPEN, GET, PUT
  and CLOSE, GET and PUT inside a BCT loop, BAL to internal subroutines, a conditional
  branch back to an earlier label, a BCTR loop whose target comes from an LA and one whose
  target does not, CALL of an external routine, LINK with EP=, LOAD with EPLOC= in a
  register and with EP=, a V-type address constant, DS and DC with duplication factors
  and nominal values, a `DS 0CL40` group, a character constant continued across
  column 71, a library macro (BSAVE), a macro nobody defines (TRACEPT), a COPY member
  that nests another, and a COPY member that is missing on purpose (AUDITDS).
- `src/BILLSQL.asm`: a CICS and DB2 program: EXEC SQL INCLUDE, a cursor declared over
  two lines, FETCH and EXEC CICS LINK in a loop closed by an unconditional branch, LINK
  with EPLOC= to a field set by DC and MVC, XCTL, a DO WHILE structured-macro loop, a
  branch table, and a branch back to the exit routine that is not a loop.
- `copy/BILLREC.asm`: a DSECT copy member with a `DS 0CL12` group, EQU flags, an
  alignment `DS 0F`, a duplicated field, ORG redefinition, and a nested COPY of INVLINE.
- `copy/INVLINE.asm`: a DSECT. `copy/CUSTDCL.asm`: host variables for EXEC SQL INCLUDE.
- `maclib/BSAVE.mac`: a macro definition member (MACRO ... MEND).
