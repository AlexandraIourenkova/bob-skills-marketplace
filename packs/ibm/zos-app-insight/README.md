# Pack `zos-app-insight` — COBOL and JCL application insight

Vendor: `ibm` (marketplace team). Original skills written for this marketplace, Apache-2.0. Install with `uvx bob-skills add zos-app-insight`, or with `/skills-add zos-app-insight` inside Bob once bob-essentials is installed.

A starter pack for teams that maintain COBOL and JCL applications without IBM Bob Premium Package for Z. It reads the source in your workspace, or members it downloads read-only from z/OS, and writes everything under `zos-insight/`. `/zos-insight` runs the whole flow.

## Before you install

**The COBOL, copybooks and JCL you analyse, and members downloaded from z/OS, go into Bob's model context like any file you open.**

Covered by: The scripts send nothing over the network; the only network step is the optional Zowe CLI download through your own profile, after your yes to the plan it prints. The rule keeps quotes to the cited lines and suggests git-ignoring zos-insight/src/.

**Comments, literals and copybook text in mainframe source can carry text aimed at Bob.**

Covered by: The pack rule treats all source as data: documentation and findings quote it as evidence and never follow it.

| Skill | What you get |
|---|---|
| `zos-app-map` | Programs, copybooks, data items, paragraphs and PERFORM flow, calls, SQL and CICS, files, jobs, steps and data sets in `app-map.json`, with a call graph and job flow in Mermaid; an optional read-only download through Zowe CLI |
| `zos-data-dictionary` | One entry per field with its PIC, usage, 88 levels and where it is used; Bob proposes the business meaning, you approve it; rebuilds keep approved text |
| `zos-program-doc` | Program and application documentation from a fixed template, business rules stated in plain words with the line they rest on |
| `cobol-perf-review` | I/O, SQL and calls inside loops, serial SEARCH where SEARCH ALL fits, display arithmetic and subscripts in loops, with a fix pattern for each and changes only after your yes |
| `rules/zos-app-insight.md` | Source is data, nothing changes on the mainframe, every claim cites file and line |
| `/zos-insight`, mode `zos-analyst` | The whole flow in order; a mode that edits only outputs and COBOL or JCL sources |

## What it is not

- The map comes from a lightweight parser, not from IBM's scanners. It handles fixed and free COBOL, copybooks with REPLACING, EXEC SQL, EXEC CICS and JCL with procedures and symbols; `zos-app-map/references/parser-limits.md` lists what it skips. Missing copybooks and dynamic calls are reported, never guessed.
- PL/I, Assembler and REXX files are listed, not analysed, in 1.0.
- Impact analysis across a large estate, refactoring into services, IBM Z documentation in answers and debugging are in IBM Bob Premium Package for Z.

## Requirements

Python 3.9 or later; the scripts use the standard library only. The download needs Zowe CLI with a profile you have already set up.
