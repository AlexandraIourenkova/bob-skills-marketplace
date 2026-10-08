# The idea grid

Ideas come out alike unless something forces them apart. The grid is that force: every set of ideas has to cover several rows and several columns, and each cell asks a different question of the user's own context.

## Rows: the direction

| Direction | Key in the spec | The question it asks |
|---|---|---|
| A new application | `new-app` | What do people do in a spreadsheet, by email or by phone because no tool exists? |
| Modernise an existing one | `modernise` | Which system does everyone fear to touch, and what would one safe change be worth? |
| Bob with MCP | `mcp` | Which internal system would become useful to every developer and agent if it could be asked in plain language? |
| An AI agent | `agent` | Where does someone gather facts from three places before they can decide anything? |
| Anything else that brings value | `other` | What would the team build if nobody had named categories? |

## Columns: the kind of value

| Value | Looks like | The number to look for |
|---|---|---|
| Time returned | waiting, searching, retyping | hours per case × cases per month |
| Errors avoided | rework, complaints, penalties | error rate × cost of one error |
| Revenue | faster quotes, fewer lost deals, a new offer | conversion, response time, deal size |
| Risk reduced | audits, compliance, a single person who knows | incidents, findings, days of exposure |
| Knowledge unlocked | answers that exist but cannot be found | questions asked per day, time to an answer |

## Rules for a set

- Six to eight ideas. At least three directions and at least three kinds of value.
- Every idea names a real role in the user's world ("the two dispatchers on the night shift"), never "users" or "employees".
- At least one idea that **replaces** a way of working instead of speeding it up.
- At least one **small and certain** idea, and one **ambitious** idea whose risk is stated plainly.
- At most one idea of the kind everybody builds (a chat over documents, a meeting summariser), and only with an argument for why this one is different.
- No two ideas with the same demo moment.

## Ways to get unstuck

Use these on the user's context when the first pass gives look-alikes.

- **Follow one case.** Take one order, ticket, patient or invoice from start to end and list where it waits.
- **Ask who is asked.** The person everyone interrupts with questions holds an idea.
- **Invert the trigger.** What if the work started before anyone asked for it?
- **Remove a role from the loop**, then ask what that role actually added: usually a decision, which stays, and a search, which goes.
- **Find the spreadsheet.** Every shared spreadsheet is an application nobody built.
- **Look at what is thrown away**: logs nobody reads, forms nobody analyses, recordings nobody replays.
- **Shrink it.** The version for one team, one document type, one corridor.
- **Borrow.** How does another industry solve the same shape of problem?

## The card

Each idea is one card in `challenge/ideas.json` (format in `solution-blueprint/references/spec-format.md`, section `ideas`).

| Field | What goes in |
|---|---|
| `title` | A result, not a technology: "Quotes in a minute", not "LLM quoting engine". |
| `direction` | A key from the rows above. |
| `pitch` | One sentence: what it does, for whom. |
| `who` | The role, how many of them, what it costs them today. A number only when the user gave it. |
| `demo` | The single moment in the demo when the room understands. |
| `why` | The argument: why this can win, naming the criterion it is strongest on and what makes it feasible in the time. |
| `risk` | The honest reason it could fail, and what would have to be true in week one. |
| `scores` | Four numbers, 1 to 5, with the rubric in `judging-criteria.md`. |
| `recommended`, `verdict` | Exactly one card is recommended; its verdict says why in one sentence. |
