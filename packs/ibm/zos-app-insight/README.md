# Pack `zos-app-insight` — z/OS application insight

Vendor: `ibm` (marketplace team). Original skills written for this marketplace, Apache-2.0. Install with `uvx bob-skills add zos-app-insight`, or with `/skills-add zos-app-insight` inside Bob once bob-essentials is installed.

A starter pack for teams that maintain COBOL, PL/I, REXX and Assembler applications with their JCL without IBM Bob Premium Package for Z. It reads the source in your workspace, or members it downloads read-only from z/OS, and writes everything under `zos-insight/`. `/zos-insight` runs the whole flow.

## Before you install

**The COBOL, PL/I, REXX, Assembler and JCL you analyse, and members downloaded from z/OS, go into Bob's model context like any file you open.**

Covered by: The scripts send nothing over the network; the only network step is the optional Zowe CLI download through your own profile, after your yes to the plan it prints. The rule keeps quotes to the cited lines and suggests git-ignoring zos-insight/src/.

**Comments, literals and copybook text in mainframe source can carry text aimed at Bob.**

Covered by: The pack rule treats all source as data: documentation and findings quote it as evidence and never follow it.

| Skill | What you get |
|---|---|
| `zos-app-map` | Programs in four languages, copybooks, includes and macros, data items, procedures and labels, calls across languages, SQL and CICS, files, jobs, steps and data sets in `app-map.json`, with a call graph and job flow in Mermaid; an optional read-only download through Zowe CLI |
| `zos-data-dictionary` | One entry per COBOL, PL/I or Assembler field with its type, usage or attributes and where it is used; Bob proposes the business meaning, you approve it; rebuilds keep approved text |
| `zos-program-doc` | Program and application documentation from a fixed template, business rules stated in plain words with the line they rest on; for REXX, the host commands that change data sets are listed as effects |
| `cobol-perf-review` | COBOL patterns that cost CPU or I/O in loops, the same I/O, SQL and call checks for PL/I, and EXECIO, allocation and host commands inside REXX loops, each with a fix pattern and changes only after your yes |
| `rules/zos-app-insight.md` | Source is data, REXX is read and never run, nothing changes on the mainframe, every claim cites file and line |
| `/zos-insight`, mode `zos-analyst` | The whole flow in order; a mode that edits only outputs and source files |

## What it is not

- The map comes from lightweight parsers, not from IBM's scanners or the compilers. `zos-app-map/references/parser-limits.md` lists what each one skips: the COBOL REPLACE statement, the PL/I preprocessor, REXX INTERPRET and commands built at run time, Assembler macro expansion and conditional assembly. Missing members and dynamic calls are reported, never guessed.
- Assembler programs are mapped and documented, and their data areas go into the dictionary, but they get no performance review and no business-rule candidates in 1.1.
- Impact analysis across a large estate with IBM's scanners, refactoring into services, IBM Z documentation in answers and debugging are in IBM Bob Premium Package for Z.

## Requirements

Python 3.9 or later; the scripts use the standard library only. The download needs Zowe CLI with a profile you have already set up.
