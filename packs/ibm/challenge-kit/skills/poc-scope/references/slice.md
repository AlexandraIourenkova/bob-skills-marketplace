# Cutting a proof of concept

A proof of concept proves one thing to one audience. Everything in this file serves that sentence.

## The thin slice

A slice is one type of case, carried from its trigger to its outcome through every layer, however roughly. Three screens that each work halfway prove less than one path that works to the end.

Choose the slice by four questions, in this order:

1. **Which case type is most frequent?** The plain case, not the interesting one.
2. **Does it pass through the step where the value is?** A slice that skips the hard part proves the easy part.
3. **Can its data be invented convincingly?** If the case only makes sense with real records, pick another or simplify it.
4. **Can a stranger follow it in the demo?** One actor, one screen, one decision.

Write the slice as a single sentence: "A price-mismatch invoice arrives, the agent names the cause and proposes the fix, the clerk approves, the invoice is released." Everything not in that sentence is out of the first week.

## In, mocked, out

Sort every component of the solution into one of three columns and keep the table in the brief.

| | Meaning | Rule |
|---|---|---|
| **Real** | Built and running in the proof of concept | The part the entry is judged on: the logic, the agent, the experience |
| **Mocked** | Stands in for a system the team cannot or may not reach | Behind the same interface the real system has, so that swapping it is a configuration change |
| **Out** | Not in the proof of concept | Named, with the phase it belongs to; it goes into the blueprint's roadmap |

A mock is honest when it says it is one: in its name, in the blueprint (`status: mock`) and in the demo.

## Mocks behind real interfaces

- Write the interface first: the three or four operations the solution needs from the system (`get_invoice`, `get_order`, `release_invoice`), with their inputs and outputs. Take the names and shapes from the real system's API when it is documented.
- The mock implements that interface over the invented tables. So does the real adapter, later.
- Operations that would write to a company system only record what they would have done. Nothing in a proof of concept changes a real system.
- For an agent on watsonx Orchestrate the interface is the tool: the tool's name, description and arguments stay, its body is swapped.

## Invented data

- **Shape from the real thing, values from nowhere.** Copy the column names, the types, the ranges and the proportions of the real data. Copy no row.
- **Plant the cases.** Decide which cases the demo and the tests need (twenty price mismatches, fourteen with freight added, the rest clean) and plant exactly those. The generator writes the answer key.
- **Enough to look real, small enough to read.** A few hundred rows. A judge who opens the file should see variety, not ten rows repeated.
- **Mark it.** The data folder says in its manifest that the data is synthetic, and the README says so too.

What must never go into the repository, even "just for testing": customer and employee names, e-mail addresses, prices from real contracts, internal documents, screenshots of real systems, anything exported from production.

## Proof of concept, pilot, production

| | Proof of concept | Pilot | Production |
|---|---|---|---|
| Proves | It can work | It works here, for these people | It keeps working |
| Data | Invented | Real, limited, read-only first | Real |
| Systems | Mocked | One real adapter | All |
| Users | The team, one friendly user | A handful | Everyone |
| Leaves out | Security review, scale, edge cases | Scale, rare cases | Nothing |

Each line the proof of concept leaves out is a line in the blueprint's roadmap with a gate. Saying what is left out, and when it comes, is what the first judging criterion means by "fully thought out".

## Signs the slice is too wide

- The plan for week one has more than one case type.
- A dependency on another team sits before the first demo.
- Nobody can say what the demo's single screen is.
- "We will connect it at the end."
