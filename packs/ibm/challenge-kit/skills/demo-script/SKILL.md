---
name: demo-script
description: Plan the demonstration of a challenge or hackathon entry - one claim, one case carried from start to outcome on the real screen, the single moment the room understands, timings for each step, the demo data and its reset, a prepared answer for every way it can break, a recorded backup and a checklist for the day. Writes the run of show and fills the demo section of the blueprint. Use when the team prepares to show their PoC, asks how to demo, what to show in three minutes, how to prepare for demo day or what to do if the demo fails, or says "сценарий демо", "как показать решение", "подготовка к демо", "demo script", "run of show".
---

# demo-script

A working solution shown badly loses to a modest one shown well. This skill turns what the team built into three minutes that make one point, and prepares for the run that goes wrong.

Everything goes into `challenge/`. Follow the challenge-kit rule. The skill plans and writes; it does not run the solution against a real tenant or system, and it changes no code.

## 1. What is being shown

Read `challenge/brief.md`, `challenge/blueprint.json` (the hero number, the process, the demo and adoption sections) and `challenge/usability.md` when it exists: every finding rated "blocks" on the demo path is fixed before the demo is planned around it.

Ask what the brief does not say, with options: how long the slot is (take the limit from the hackathon site), who watches (judges, executives, a technical panel), whether it is live, remote or a recorded video, and what actually runs today. Plan only around what runs; a step that is not built is said, not shown.

## 2. One claim, one case, one moment

Read `references/run-of-show.md`.

- **The claim**: the sentence the audience should repeat afterwards. Usually the blueprint's hero number in words.
- **The case**: the plain case that shows it. With data from `poc-scope`, pick a row from the answer key in `challenge/data/manifest.json` and name it by id.
- **The moment**: the single step where the claim becomes visible. Everything before it is setup, everything after is brief.

Propose them and ask the user to agree before writing the steps.

## 3. The run of show

Write `challenge/demo.md`:

- the claim, the audience and the time limit;
- the beats in the shape of the reference file, each with its seconds, what is on the screen, and what is said, in the presenter's own spoken language, short enough to say in the time;
- the demo case by id, and the reset: the command or the steps that put it back to its starting state;
- the table of failures with the prepared answer for each, filled in for this solution;
- the recording: what to record, when, and where the file is kept;
- the checklist for the day.

Add up the seconds. When the total is over the limit, cut a step; never plan to talk faster.

## 4. Into the blueprint

Write the `demo` section of `challenge/blueprint.json`: one card per step of the path with its `time`, and a headline that is the claim. Render the blueprint again with the `solution-blueprint` skill. To look at the storyboard alone, a spec with `meta` (`"partial": true`) and `demo` renders as one section.

## 5. Rehearse

Give the team the rehearsal: three full runs with a timer, the second one in front of someone outside the team, the third with a planned failure (someone switches the network off at step two) to practise the switch to the recording. After each run, the watcher answers two questions: what was this for, and what was the moment? When their answers differ from the claim, change the script, not the audience.

Update the brief with what was decided and what is still to be done before the day.

## Works next to

The `presentations` pack writes the slides around the demo and, in its `deck-pitch` skill, the spoken pitch at several lengths and a bank of prepared answers. Offer it when the team also needs a deck; it is installed only when the user asks.

## Variations

- **A recorded video instead of a live demo.** The same shape. Record in one take when possible, add no effects, and put the claim as text on the first and the last frame.
- **Nothing runs end to end yet.** Show the part that runs, and say the rest over the blueprint's process diagram. Say plainly which is which.
- **An agent demo.** Prepare the exact requests to paste. Include one request outside the agent's job, to show that it says so.
