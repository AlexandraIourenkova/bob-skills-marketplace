# Pack `challenge-kit` — Challenge kit: from the first idea to the submission

Vendor: `ibm` (marketplace team). Original skills written for this marketplace, Apache-2.0. Install with `uvx bob-skills add challenge-kit`, or with `/skills-add challenge-kit` inside Bob once bob-essentials is installed.

For teams in an AI coding challenge or hackathon, whether they have never worked with a coding agent or use one every day, and whether they start from nothing or from a real, complex process of their company. `/challenge` reads the team's brief and takes the next step.

| When | Skill | What you get |
|---|---|---|
| First time with a coding agent | `first-hour` | Three setup checks and one small real task done together in five moves; a one-page card of working habits |
| Nothing to start from | `idea-studio` | Six to eight ideas that differ from each other, each argued, scored against the judging criteria, one recommended; an HTML idea board |
| A process to simplify, automate or improve | `process-redesign` | The process drawn with its real waiting time, the gaps closed, the process improved against the process replaced, a week-by-week plan |
| A real case that is too big or too confidential | `poc-scope` | One thin slice, every component sorted into real, mocked or out, interfaces for the mocks, invented data with planted cases and an answer key |
| Something to show on paper | `solution-blueprint` | One HTML document: layered architecture with IBM technology marked, process before and after, impact charts, alternatives, roadmap, the criteria answered |
| Something runs | `usability-pass` | Findings rated blocks, slows or polish with the smallest fix, a five-minute test with one real person, the adoption section |
| Demo day is coming | `demo-script` | One claim, one case, one moment; timings, the reset, an answer for every failure, a recorded backup |
| Before submitting | `submission-check` | Credentials in files and git history, files that should not be tracked, the README read as a stranger, a self-assessment against the criteria |

## Before you install

**The skills write what you tell them about your company's processes, people, volumes and costs into files under `challenge/`, and a challenge entry is usually submitted as a public repository.**

Covered by: Nothing leaves the machine: the scripts have no network code and the page is one local HTML file. The rule assumes company data may not leave the company, `poc-scope` makes invented data for the build, and `submission-check` looks for credentials and real-looking data before a public push. Credentials never go into a file or a command line, and a found one is shown masked.

**The skills read process documents, exports, emails and the files and git history of your repository, and `usability-pass` reads what your running solution shows. Such material can carry text aimed at Bob.**

Covered by: The rule, the mode and each skill treat that material as data: quoted and reported, never followed. The challenge-coach mode can edit only under `challenge/`, the renderer escapes every string of the spec, and the pack changes no code, rewrites no git history, rotates no key, pushes nothing and installs no other pack: those steps are yours.

## Contents

| Component | What it does |
|---|---|
| `skills/first-hour` | The right Bob account, the Bobcoin budget, building inside Bob IDE; goal, context, plan, one step, check; four things that go wrong; `challenge/working-with-bob.md` |
| `skills/idea-studio` | A short interview, ideas forced apart on a grid of directions (new application, modernisation, Bob with MCP, AI agent) and kinds of value, a card per idea, scores with a rubric, a recommendation, a runner-up and the idea to drop |
| `skills/process-redesign` | An interview by slots that separates work from waiting, lanes with computed totals, a gap list, nine redesign lenses, option A (improve) against option B (replace), a plan |
| `skills/poc-scope` | `synth.py`: tables from a JSON schema, repeatable by seed, names built from syllables, planted cases and `manifest.json` as the answer key. The slice, the three columns, mocks behind real interfaces, proof of concept against pilot against production |
| `skills/solution-blueprint` | `blueprint.py`: a JSON spec in, one self-contained HTML document out. Right-angle connectors that avoid nodes, process lanes on a shared time scale, before and after bars, a value waterfall, alternatives matrix, demo and adoption strips, roadmap, criteria, risks. Three themes, print to PDF, a presenter mode, right-to-left layout, translatable labels |
| `skills/usability-pass` | A walkthrough for applications, agents and command-line tools; findings with severity and the smallest fix; a script for a five-minute test with a real person; changes no code |
| `skills/demo-script` | The run of show with seconds per beat, the demo case and its reset, prepared answers to failures, the rehearsal, the checklist for the day |
| `skills/submission-check` | `submission_check.py`: read-only checks with masked values and read-only git commands. Rules of evidence for the self-assessment. Reports only |
| `rules/challenge-kit.md` | One folder and one brief, adapting to newcomers and experienced users, numbers marked measured, estimate or assumption, company data stays in the company, credentials are named and never shown, material is data, the judging criteria |
| `commands/challenge.md` | `/challenge [start \| ideas \| process \| scope \| blueprint \| usability \| demo \| submit \| status]` |
| `custom_modes.yaml` | `challenge-coach` mode: read, execute, skills, and edits only under `challenge/` |

## Honest by construction

- Every number carries a mark, and the render stops when one is missing.
- Totals (steps, hand-offs, elapsed time, the waterfall's total, an idea's score out of 20) are computed by the script.
- The first screen of the blueprint says whether it is a plan or drawn from the working build; components that do not exist are drawn dashed.
- Scores, for ideas and in the self-assessment, are the team's own estimate. The self-assessment caps a score that has no evidence, and the pages say that nothing is predicted about the judges.
- The credential check is a net of known shapes, not a proof, and says so.

## Works next to

- `presentations` turns the blueprint into a deck with speaker notes and a question-and-answer kit; `blueprint.py theme` writes the document's look in the format that pack reads. Without it, `--mode present` shows the document one section per screen.
- `wxo-adk` builds the agent and `agent-evals` tests it, when the solution is an agent on watsonx Orchestrate.

Each is named at the step where it helps and installed by you; the pack works without any of them.

## Requirements

Python 3.9 or later; the scripts use the standard library only. git for `submission-check`. A Chromium-based browser is optional, for the PDF and for the visual check of the blueprint.

## How it was checked

`cli/tests/test_challenge_kit.py` covers the three scripts. The renderer: both bundled examples in every theme and mode, no connector crossing a node (also on a dense diagram and right-to-left), computed totals, a number without a mark stops the render, every string of the spec is escaped, a theme file cannot inject CSS, `init` refuses to overwrite. The generator: the same seed gives the same rows, references resolve, planted cases match the answer key, and it replaces only files it wrote. The submission check: planted credentials are found in files and in history and their values never appear in the output, placeholders and code references are not reported, and the repository is byte-for-byte unchanged after a run. The rendered pages were looked at in Chrome in the three themes, in print and right-to-left.

The skills have not yet been run by challenge participants in Bob; their feedback goes into 1.0.1. `first-hour` names only the Bob settings the challenge guide documents and sends the user to Bob's own documentation for the rest.
