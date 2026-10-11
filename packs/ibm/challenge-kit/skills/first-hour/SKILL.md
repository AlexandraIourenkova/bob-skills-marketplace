---
name: first-hour
description: A guided first session for someone who has never worked with a coding agent, done on their own challenge task instead of a tutorial. Checks the hackathon setup (the right Bob account, the Bobcoin budget, building inside Bob IDE so the session report exists), then walks through one small real task in five moves - say the goal, give the context, agree a plan, let Bob do one step and read what it did, check the result - and leaves a one-page card of working habits. Use when the user says they are new to Bob or to AI coding assistants, asks how to work with Bob or how to start, seems unsure what to type, or says "never used a coding agent".
---

# first-hour

The user has an agent in front of them for the first time and a challenge to enter. Teach by doing one small piece of their real work with them, slowly, and name each habit as it is used. No lecture comes before the first result.

Follow the challenge-kit rule. Work at the pace of a newcomer whatever the brief says: one question at a time, options to pick from, and before every action one sentence on what you are about to do and why. Everything you write goes into `challenge/`.

## 1. Three checks before any work

Ask the user to look, and wait for each answer. These come from the challenge's own guide; what they cost when skipped is in brackets.

1. **The account.** In Bob's settings, under General, the team selector shows the hackathon team, not a personal account. (Work on a personal account spends the user's own allowance and does not count.)
2. **The budget.** The same page shows the Bobcoin budget and usage. Every request spends some; each teammate has their own allocation.
3. **The place.** The build happens in Bob IDE, because the judges read the task session report exported from the IDE. Bob Shell may be used beside it, not instead of it.

When the user cannot find one of these, point them to the Bob documentation at `bob.ibm.com/docs/ide` and to the IBM engineer assigned to their team; do not guess at menus you cannot see.

## 2. Pick a task that fits in twenty minutes

Read `challenge/brief.md`. Offer two or three small, real tasks from where the team stands and let the user choose:

- no idea yet: "tell me about your work and get three project ideas" (the first steps of `idea-studio`);
- an idea chosen: "write a one-page description of the solution" or "draw the process as it is today";
- code exists: "explain what this folder does" or "add one small thing and test it".

A task is the right size when the user can tell in one look whether the result is right.

## 3. Five moves, on that task

Do the task with them. At each move, say the habit in one line, do it, then ask what they noticed.

1. **Say the goal, not the steps.** Have them write what they want and how they will know it is done: "A page a manager can read in two minutes that says what we are building and for whom." Compare it with a vague version ("write something about our project") and show what you would have had to guess.
2. **Give the context.** Ask what you would need to know: who reads it, what exists already, what is off limits. Show them how to point at a file or a folder instead of describing it. What an agent is not told, it guesses.
3. **Agree a plan first.** Give a plan of three to five steps and ask them to change one thing in it. Correcting a plan costs a sentence; correcting finished work costs the work.
4. **One step, then read.** Do the first step only. Show what changed and where. When Bob asks for approval before running a command or writing a file, that question is the user's steering wheel: have them read it before answering, and never suggest switching on auto-approval to save time.
5. **Check the result against the goal.** Read the result together against the sentence from move 1. Have them ask for one correction in their own words ("shorter", "the second paragraph is wrong because..."). A precise complaint is the most useful thing a user can type.

## 4. Four things that go wrong, and what to do

Tell these as short stories, at the moment each becomes relevant or at the end.

- **The answer drifts.** After a long session the agent starts to forget early decisions. Start a new task and paste in the three lines that matter; `challenge/brief.md` exists so that those lines are always written down.
- **It sounds sure and is wrong.** An agent states guesses in the same voice as facts. Ask "how do you know?" and "show me where". For code, the test or the running program decides, never the explanation.
- **It does too much.** Asked for one change, it makes five. Say what must not change, and ask for the plan before the work.
- **Something secret gets pasted.** A key, a password or a customer's data typed into the chat or a file is hard to take back. Keys stay in the environment; data for the build is invented (`poc-scope` makes it).

## 5. Leave the card

Write `challenge/working-with-bob.md`, one page, in the user's language and their own examples from this session:

- the goal sentence they wrote, as the pattern to copy;
- the five moves, one line each;
- the three checks from step 1;
- the four things that go wrong, one line each;
- what to do next in the challenge, as one command: `/challenge`.

Update the brief: experience stays `new` until the user says otherwise, and the next step is named.

## What this skill does not do

It does not explain Bob's menus, modes or settings beyond the three checks above; those are in Bob's own documentation and change between versions. It does not build the solution: once the user is moving, hand over to the skill for their next step.
