# The process interview

The interview fills slots. It ends when the slots are full or marked unknown, not after a number of questions. Take everything the user's documents already answer first, then ask only for the rest.

## Slots

| Slot | What to learn | A question that works |
|---|---|---|
| Outcome | What the process is for, in the words of whoever receives its result | "When this goes well, who gets what?" |
| Trigger | What starts a case, and how often | "What makes someone start? How many times a week?" |
| Steps | What happens, in order, from the trigger to the outcome | "Walk me through the last case you remember." |
| Actors | Who does each step: a role, a team, a system, an outside party | "Who touches it at this point?" |
| Systems | Where the information lives at each step | "Where do you look, and where do you type?" |
| Time | Minutes of work per step, and how long a case waits between steps | "How long does that take when nothing goes wrong? And how long does it sit before the next person picks it up?" |
| Volume | Cases per week or month, and the share that goes wrong | "How many of these in a normal month? How many come back?" |
| Pain | Where it hurts most, and for whom | "If you could remove one step, which?" |
| Rules | What may not change: law, audit, policy, a system that stays | "What would get you in trouble if we changed it?" |
| Expectation | What the user imagines the solution doing | "Picture it working. What do you see on the screen?" |
| Success | The number that would prove it worked | "What would you measure to know it is better?" |
| Data | Whether real data may be used for the build | "Can a copy of real cases leave the company? If unsure: no." |

## How to ask

- **Start from a case, not from the process.** "The last one you remember" gets real steps; "how does the process work" gets the official version.
- **A newcomer** gets one question at a time, with options where a list is possible ("minutes, hours, days?"). Say why you ask when the reason is not obvious.
- **An experienced user** gets the open slots in one message, as a short numbered list.
- **Waiting is a step.** Whenever work passes from one actor to another, ask how long it sits. Record it as its own step with kind `wait`. Most of the elapsed time of most processes is here.
- **Separate work from wait.** "It takes three days" usually means forty minutes of work and three days of queue.
- **Never fill a time or a volume yourself.** An unknown is written as unknown and goes onto the list of questions for the process owner.
- **Play it back.** After the steps are in, render the diagram and ask what is wrong with it. People correct a picture more readily than they describe a process.

## Marks for the numbers

- `measured`: taken from a system report or timed on real cases. Record which report, which period, how many cases.
- `estimate`: the user's own figure from experience, or worked out from measured parts. Record whose estimate.
- `assumption`: nobody knows; a placeholder to be checked. Record how to check it.

One mark covers all the step times of a process (`process.basis`), so take the weakest: one assumed step makes the set an assumption until it is checked.

## Questions for the process owner

When the user does not live inside the process, the open slots become a short list they can send or ask in ten minutes. Write it into `challenge/brief.md` under "Open", phrased for a business person:

- How many cases a month, and how many need a second round?
- For the last case you remember: who did what, and where did it wait longest?
- What would you stop doing tomorrow if you could?
- What must stay exactly as it is, and why?
