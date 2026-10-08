# The run of show

A demo is a three-minute argument made with a working thing. It has one claim, one path and one moment.

## The shape

| Beat | Time | What happens |
|---|---|---|
| **The person and the pain** | 20 to 30 s | One sentence about who this is for and what their day is like. No architecture, no history of the project. |
| **The before** | 15 to 20 s | The old way, shown or said in one image: three systems, a three-day wait. |
| **The path** | 90 to 120 s | One case, from its start to its outcome, on the real screen. Three to five steps. |
| **The moment** | inside the path | The single step where the room understands. Slow down here and say nothing for two seconds. |
| **The number** | 15 s | What changed, with its mark: measured, estimate or assumption. |
| **What is next** | 15 s | The pilot, in one sentence. Stop. |

Three minutes is a default. Take the limit from the hackathon site and fit the path to it; a demo that ends early is remembered better than one that is cut off.

## Rules for the path

- **One case.** The plain one that shows the value. A second case only when it shows something the first cannot, such as the solution saying "I do not know".
- **The user's seat.** Show what the user sees. The terminal, the logs and the code belong in questions and answers.
- **Say what you see, not what you built.** "The cause is already named" beats "our triage agent calls the three-way match tool".
- **No live typing of anything long.** Paste, or have the input ready.
- **Show a real limit once.** A solution that visibly asks a person before it acts, or says what it cannot do, earns more trust than a flawless run.
- **IBM technology by name, once**, at the step where it does its work.

## The data

- A dedicated demo case, known by its id, that always behaves the same. With `poc-scope`, take it from the answer key in `challenge/data/manifest.json`.
- Reset before every run: the same starting state each time, by one command or one written procedure.
- Nothing real on the screen: invented names, invented prices, no browser tabs or notifications from the presenter's own work.

## When it breaks

It will, once. Decide now what happens then.

| Failure | Prepared answer |
|---|---|
| No network, or the service is down | A recording of the full run, made in advance, on the presenter's machine and one other |
| One step hangs | A sentence to say while waiting ten seconds, then switch to the recording at that step |
| The model answers differently | The path is chosen so that any reasonable answer still makes the point; the exact wording is never promised aloud beforehand |
| The wrong state from a previous run | The reset, done before walking on |
| Projector, resolution, font size | Browser zoom set in advance; a check from the back of the room |

Record the backup when the path first runs cleanly, and again after every change to the path. A recording of last week's version is no backup.

## The checklist for the day

- The reset has been run. The demo case is in its starting state.
- Logged in everywhere needed; sessions will not expire in the next hour.
- Notifications off. Other windows closed. Zoom set.
- The recording is open in a second window.
- One person presents, one person watches the clock.
- The first sentence is known by heart.
