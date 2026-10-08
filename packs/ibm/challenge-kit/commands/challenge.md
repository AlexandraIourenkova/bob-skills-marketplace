---
description: Start or continue a challenge entry with the challenge-kit pack - a first session for newcomers, ideas, a process rethought, the scope and invented data, a solution blueprint with diagrams, a usability pass, the demo script and the check before submitting
argument-hint: [start | ideas | process <file or description> | scope | blueprint | usability | demo | submit | status]
---

Work on the challenge entry in this project. Follow the challenge-kit rule. Everything goes into `challenge/`.

1. **Brief.** Read `challenge/brief.md`. When it is missing, create it from `idea-studio/references/brief-template.md` and ask, in one message with options: how much the user has worked with coding agents (new, some, fluent), the team size and the hours a week each person has, and which of these is true: no idea yet, an idea in mind, or an existing process to simplify, automate or improve.
2. **Route.** With `$ARGUMENTS` naming a step, go to it. Otherwise take the step the brief says is next:
   - new to coding agents and nothing done yet (`start`): the `first-hour` skill, on a small piece of their real task;
   - no idea yet (`ideas`): the `idea-studio` skill;
   - an existing process (`process`): the `process-redesign` skill;
   - an idea in mind: sharpen it with `idea-studio` (its "half an idea" variation), then `process-redesign` when the idea changes how people work today;
   - an idea agreed, nothing built (`scope`): the `poc-scope` skill for the slice, the mocks and the invented data, then `solution-blueprint` as a plan;
   - a document needed (`blueprint`): the `solution-blueprint` skill;
   - something runs (`usability`, `demo`): the `usability-pass` skill, then the `demo-script` skill;
   - close to the deadline (`submit`): the `submission-check` skill.
   `status` only reports: what the brief holds, what is decided, what is open, which file to open.
3. **Stop for the user's decisions.** Which idea to build, which version of the process (improved or replaced) and what the blueprint claims are the user's. Show the page, ask, and wait.
4. **Close the step.** Update `challenge/brief.md`: what was decided, what is open, the next step. Say in one line what the user can open now and what comes next.

Never install another pack, push to a repository, rewrite git history or send anything outside this machine as part of this command. Say what is needed; those steps are the user's.
