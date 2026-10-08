# The walkthrough

Two passes: you walk the solution as a first-time user, then a real person does, while the team watches and says nothing.

## Pass one: your own walk

Start from nothing: a fresh clone or a fresh browser profile, the README as the only guide. Write down every point where you had to know something the screen did not tell you.

### Any solution

| Look at | Ask |
|---|---|
| The first minute | Can a stranger start it from the README alone? How many steps before anything appears? |
| The first screen | Does it say what this is for and what to do first? Is there one obvious first action? |
| Time to first value | How long from start to the first useful result? This is the number for the blueprint's adoption section. |
| The empty state | What does it show before any data exists: a blank page, or the next step? |
| The wait | When something takes more than a second, does the user see that it is working, and on what? |
| The error | Break it once on purpose (wrong input, missing file, service off). Does the message say what happened and what to do, in the user's words? |
| The words | Are labels in the user's vocabulary or the builder's? ("Exception inbox", not "Triage queue v2".) |
| The way back | Can the user undo, cancel, or return to where they were? |
| Trust | When the solution claims something, can the user see where it came from? |
| The end | Does the user know they are done, and what happened as a result? |

### An agent or a chat

| Look at | Ask |
|---|---|
| The opening | Does it say what it can do, with two or three example requests to pick? An empty box is the hardest interface there is. |
| The first answer | Short enough to read, with the answer first? |
| Not knowing | Ask something outside its job. Does it say so plainly and offer what it can do, or invent an answer? |
| Ambiguity | Ask something vague. Does it ask one clarifying question, or guess? |
| Actions | Before it changes anything, does it say what it will do and wait? Afterwards, does it say what it did? |
| Evidence | Does an answer from data show the source: the row, the document, the link? |
| Recovery | After a wrong turn, can the user correct it in one sentence, or must they start over? |
| Tone | Does it sound like a colleague of the user, in the user's language? |

### A command-line tool or an API

| Look at | Ask |
|---|---|
| `--help` | Does it exist, with one example that works when pasted? |
| Defaults | Does the plain command do the common thing? |
| Errors | Do they name the argument and the fix? |
| Output | Readable by a person, and parseable when asked? |

## Rating a finding

| Severity | Meaning | In a challenge |
|---|---|---|
| **Blocks** | A first-time user cannot get past it without help | Fix before anything else; it will happen in front of the judges |
| **Slows** | They get past it, with confusion or a wrong first try | Fix when it sits on the demo path |
| **Polish** | They notice, and it costs nothing | Fix last, or list it as known |

Write each finding as: where, what the user sees, what they expected, the smallest fix. Order by severity, then by whether it is on the demo path.

## Pass two: one real person, five minutes

Your walk finds what a careful reader finds. A real user finds the rest. One person from outside the team is enough to find the worst problem; three find most of them.

Give the team this script:

1. Pick someone who has not seen the solution: ideally the kind of person it is for.
2. Say only: "This helps with [the problem, in one sentence]. Please try to [the main task]. Say aloud what you are thinking. We will not help; that is the point."
3. Start a timer. Watch. Do not explain, do not point, do not defend.
4. Write down: where they hesitated, what they clicked first, what they said, where they asked for help, and the time when they first got a useful result.
5. Afterwards ask three questions: What did you think this was for? What was the most confusing moment? Would you use it tomorrow, and what would stop you?

What they did is evidence. What they say they would do is weaker; record it as their opinion.

## Adoption

The usability criterion also asks how quickly the solution could be put to use by its real users. Answer four questions, from the walk and from the brief:

- **Where do they meet it?** In a tool they already open every day, or somewhere new?
- **What do they need first?** An account, an install, a permission, training?
- **What is the first useful minute?** The time to first value, measured in pass two when a person was timed, an estimate otherwise.
- **What stays as a fallback?** What can they still do the old way on day one?
