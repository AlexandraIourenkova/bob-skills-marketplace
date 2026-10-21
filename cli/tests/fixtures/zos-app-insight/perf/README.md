# cobol-perf-review test fixtures

Synthetic COBOL for the tests of the cobol-perf-review skill (`cli/tests/test_zos_app_insight_perf.py`).
Every file here is original, written by the Bob Skills Marketplace team for these tests, and licensed
under Apache-2.0 like the rest of the repository. Nothing is copied from IBM samples or any other source.

- `cobol/PERFPOS.cbl`: one positive case for every check inside a PERFORM UNTIL loop: OPEN and CLOSE
  (one pair under an IF), singleton SELECT, INSERT, UPDATE, DELETE and a cursor OPEN, a static and a
  dynamic CALL with CANCEL, a serial SEARCH on a keyed table and on a 400-entry table, DISPLAY
  counters and amounts in arithmetic, a DISPLAY subscript that is also a VARYING variable,
  INITIALIZE of a group with a table, STRING, UNSTRING and INSPECT; and a DISPLAY counter in a
  `PERFORM 3 TIMES` loop at the top, which must come out low.
- `cobol/PERFNEG.cbl`: the tuned or loop-free twin of each case: OPEN and CLOSE, a CALL, a singleton
  SELECT and a STRING before the loop; FETCH and UPDATE WHERE CURRENT OF in a loop; SEARCH ALL; a
  serial SEARCH on a 20-entry table; counters with a group USAGE COMP-3; a COMP-5 subscript and
  index names; INITIALIZE of an elementary item; reference modification.
- `cobol/PERFPART.cbl`: copies PERFGONE, which is missing on purpose, so its items must be listed as
  not checked; PERFTAB's items inherit USAGE COMP-3 from their group; PART-CNT is defined in two
  groups with different usage and used qualified; ADD CORRESPONDING; a DISPLAY subscript in an
  EVALUATE WHEN; an out-of-line PERFORM VARYING.
- `cobol/PERFCALC.cbl`: a subroutine with no loop, called by PERFPOS inside its loop.
- `copy/PERFTAB.cpy`: the copybook PERFPART finds.
