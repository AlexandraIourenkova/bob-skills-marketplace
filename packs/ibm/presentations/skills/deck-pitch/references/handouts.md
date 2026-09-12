# Handouts, follow-up and the day of the talk

This file covers everything around the talk that is not the talk: the one-page leave-behind, the reading version of the deck, the appendix, the follow-up email, the rehearsal plan, the day-of checklist, accessibility, and how to name and send the files. Read it after the Q&A bank exists (see `qa.md`) and before you fill the "One-pager", "Follow-up email", "Rehearsal log" and "Day-of checklist" sections of `talk-kit.md`. The one-pager and the email are written from the same three key messages as the pitch, so they never say something the deck does not. The examples use the sample deck from `pitch.md`.

## 1. The one-pager

A leave-behind for the people in the room and the people who were not. One page. It is read in two minutes, on a phone, by someone who will decide without the speaker present.

Structure, top to bottom:

1. Title: the ask, as a sentence. "Approve two enterprise onboarding hires for Q4."
2. Context in one line: who is asking, for what decision, by when.
3. Three messages, each with its evidence number and source. One paragraph of two sentences each, or a three-row table.
4. The decision and the date. The cost. The owner of the outcome and the metric.
5. Contact: the speaker's name and one channel.

Leave out: the agenda, the history, the alternatives (a one-line mention at most), the risks (one line: "two risks, both owned, detail in the deck"), and any chart that needs a caption longer than the chart.

Build it as a Markdown document, `one-pager.md`, next to the talk kit. The user turns it into a PDF or a Word file with the office-docs pack: `docx_build.py` for the document, `docx_to_pdf.py` for the PDF, or `pdf_build.py` directly. Keep the Markdown to headings, short paragraphs and one table; that converts cleanly.

Sample one-pager:

```markdown
# Approve two enterprise onboarding hires for Q4

Proposal from Maria Startseva to the leadership team. Decision needed by 30 September 2026.

| Message | Evidence | Source |
|---|---|---|
| Enterprise customers doubled and onboarding did not keep up | 52 to 104 customers; time to first value 21 to 47 days | Finance close and CRM onboarding report, August 2026 |
| Late onboarding costs customers and revenue | churn 9 percent against 3 percent in the first 90 days; 1.1 M ARR in the queue | CRM onboarding report, September 2026 |
| Two specialists for 240 K fix it and pay back with four retained accounts | target 25 days by 31 January; average contract 60 K | capacity model, deck slide A1 |

Decision: approve two enterprise onboarding specialist roles, 240 K fully loaded for the year, opened 1 October.
Owner: Maria Startseva. Metric: time to first value under 25 days by 31 January, weekly on the customer success dashboard.
Alternatives considered: contractors (310 K), automation (Q2, mid-market only), reassignment (renewals at risk). Detail in the deck, slide A3.

Contact: maria.startseva, or the #customer-success channel.
```

## 2. Reading deck versus talk deck

The talk deck is designed to be spoken over: short headlines, one visual, notes hold the words. A reading deck is read alone, on a laptop, with nobody speaking. Make a separate reading version when the deck is sent by email before or instead of the talk, when the audience includes people who will not attend, or when the decision is taken later from the file.

| Element | Talk deck | Reading deck |
|---|---|---|
| Headline | under 70 characters, the point | a full sentence, may reach 90 characters |
| Body | bullets or one visual | the same, plus a short paragraph of context taken from the notes |
| Sources | `Source:` line where numbers appear | on every slide with a number, with the report name and date |
| Builds and animation | allowed | none; every slide is complete on arrival |
| Appendix | present, for jumping | included and referenced from the main slides |
| Notes | the talk track | removed or replaced by the context paragraph |

Derive it from the same storyboard, never from the built pptx:

1. Copy the storyboard to `storyboard-reading.md`.
2. For each content slide, turn the first `Notes:` paragraph into a plain paragraph under the bullets, cut to two or three sentences. Delete the remaining `Notes:` lines or leave them; the reading check ignores them.
3. Lengthen headlines that are fragments into sentences. Keep the numbers.
4. Add a `Source:` line to every slide with a number.
5. Add "Detail on slide A3" style references where the main deck relies on the speaker to point at the appendix.
6. Check it with `storyboard_check.py storyboard-reading.md --reading`: notes become optional and slides may be denser. Then build it with `deck_build.py` to a separate file name (see section 8).

Three formats carry the reading version, all from that one storyboard: a PDF printed from the static HTML for the people who read or print it, an interactive HTML file as a link for the people who will click through it themselves, and the pptx only for the people who edit. The HTML file carries the speaker notes inside it, so build the shared copies from a storyboard with the `Notes:` lines stripped (`grep -v '^Notes:' storyboard-reading.md > storyboard-share.md`). Commands and trade-offs: `../presentation/references/html-decks.md`.

## 3. Appendix strategy

The appendix holds what a questioner may ask for and what a reader may want to check. It is not a place for slides that were cut for being weak; those are deleted. A chapter called `Appendix` in the storyboard does the numbering: every slide after it shows A1, A2 in its footer, the chapter label above the headline reads A, and the timing check leaves them out. Reference them from the main deck as "detail on A3".

What goes in, in this order: the backup slides from `qa.md` (methodology, full data table, alternatives with costs, risks and mitigations, timeline detail), then the glossary, then credits and sources. Order by the likelihood of the question, most likely first, so the speaker's jumps are short.

- Start it with a section slide: `# Appendix`. In the storyboard that is a `#` line after the closing slide.
- Label every backup slide in its headline: "A1. Methodology: how time to first value is measured". The label is stable across versions even when physical slide numbers move.
- Reference it from the main deck in the notes and in the reading version: "detail on slide A3". The speaker says the label; the talk kit maps labels to physical numbers for jumping.
- A backup slide follows the same rules as a main slide: one point, a headline that states it, a source line. Tables may run to nine rows; beyond that, split them.
- The reading deck includes the appendix. The talk deck includes it too; it is never hidden slides.

## 4. Follow-up email

Sent within 24 hours, by the speaker, to everyone who attended and to the people who decide. It repeats the three messages, states the decision or the next step with a date and an owner, and carries the parking-lot answers.

Template:

```
Subject: <the decision>: <status or date>

<one line of thanks, with the date of the meeting>

<the three messages, one line each, with the evidence number>

<the decision taken, or the next step, with the date and the owner>

<answers to the questions parked in the meeting, one line each>

<attachments: the one-pager as PDF, the reading deck as PDF>

<offer of a short call, with two time slots>
```

Filled example:

```
Subject: Two enterprise onboarding hires: decision needed by 30 September

Thank you for the time on Tuesday.

Three things from the discussion:
1. Enterprise customers doubled to 104 in twelve months; time to first value went from 21 to 47 days.
2. Accounts onboarded late churn at 9 percent in the first 90 days against 3 percent on time; 1.1 M of ARR is in the queue today.
3. Two onboarding specialists, 240 K for the year, bring the metric back to 25 days and pay for themselves with four retained accounts.

Decision: approval of the two roles by 30 September, so recruiting opens on 1 October. Owner: Maria Startseva. First review of the metric: 15 May.

Questions from the meeting:
- Contractor option (Piet): 310 K for the same hours plus two months of ramp-up; detail on slide A3 of the attached deck.
- Year-two cost (Anna): 246 K with the standard increase; no additional tooling.
- Whether the churn gap holds by segment (Lena): it does in both halves of the year; I will send the segment cut by Thursday.

Attached: the one-pager (PDF) and the reading deck (PDF).

If a fifteen-minute call helps before Friday, I am free Thursday at 10:00 or Friday at 09:00.
```

Rules: no new claims that were not in the deck or the meeting; every date has an owner; the subject line survives being read in a notification.

## 5. Rehearsal plan

Three runs, each with a purpose, each logged in the talk kit's rehearsal table (run, date, total time, sections over time, fixes made).

| Run | How | What to fix after it |
|---|---|---|
| 1. Read-through for flow | Read the talk track aloud at a desk, slide by slide, in order. No clock. | transitions that do not connect, headlines the speaker stumbles on, numbers that differ between slide and notes |
| 2. Timed run out loud | Stand up, click through the real deck, a clock visible, no stopping. Record the time at each section slide. | sections over their share: cut in the order from `pitch.md` section 6; slides under 30 seconds: merge; the total must land at 85 percent of the slot |
| 3. Run with a listener | A colleague listens, then asks the hardest three questions from the Q&A bank. Then asks three of their own. | answers over 60 seconds, answers with no slide behind them, questions that were not in the bank (add them) |

Before the third run, the "headline only" run: the speaker goes through the deck saying one sentence per slide, the first sentence from the talk track, nothing else. Under three minutes for a 20-minute deck. If the story holds at that length, the deck holds; if a slide has no sentence, it has no point.

Log format for the talk kit, one row per run:

| Run | Date | Total time | Sections over time | Fixes made |
|---|---|---|---|---|
| 2 timed | 2026-09-14 | 19:10 of 17:00 target | evidence (7:40 of 6:00), alternatives (3:10 of 2:30) | cut the second example on slide 5; alternatives to one line each, detail on A3 |

Rehearse the close separately, five times, until the ask and the date come out the same way every time.

## 6. Day-of checklist

| Item | Why | When |
|---|---|---|
| Fonts present on the presenting machine, or the PDF export ready | a missing font reflows every slide | the day before |
| PDF backup on a stick and in the speaker's own email | the laptop, the network or the file can fail; the PDF never does | the day before |
| Aspect ratio of the room screen matches the deck (16:9 or 4:3) | a wrong ratio puts black bars or cuts the footer | the day before, ask the host |
| Presenter view working, notes readable at arm's length | notes hold the first sentences and the transitions | at setup, 30 minutes before |
| Clicker paired, spare batteries, the back key known | a dead clicker costs the flow | at setup |
| First slide up before the audience arrives | the room settles faster and the speaker is not fiddling | 10 minutes before |
| Water within reach | dry mouth by slide 6 | at setup |
| Phone silent, notifications off on the presenting machine | one notification on screen is what the room remembers | at setup |
| Appendix labels and physical slide numbers memorised, or on a card | jumping to A3 takes two seconds, searching takes twenty | the day before |
| Room contrast check from the back row | projectors wash out light grey, thin fonts and pale chart lines | at setup; switch to the high-contrast theme if needed |
| Remote: screen share tested with the actual deck, notes on a second monitor | sharing the wrong window or the notes is common | 15 minutes before |
| Remote: camera framing at eye level, light in front, the lens at the top of the screen | eye contact on camera reads as confidence | 15 minutes before |
| Remote: the slide numbers said aloud, the ask pasted in the chat | remote viewers cannot see pointing | during the talk |

## 7. Accessibility and inclusivity

- Alt text: every picture and chart in the storyboard has alt text that states the finding ("bar chart: enterprise customers rose from 52 to 104 in four quarters"), not the type of picture. `deck_build.py` stores it for screen readers.
- Captions: for recorded or streamed talks, turn on live captions in the meeting tool and say numbers as words when they matter ("forty-seven days").
- Describing charts aloud: say the finding, the axis and the one number that matters. Never "as you can see": some people in the room cannot, and remote audio may lag the slide.
- Colour independence: meaning never rides on colour alone. The highlighted bar also has a label; the risky item also has a marker. Check the deck in greyscale (print preview).
- Font sizes: 24 pt body in a room, 18 pt on a laptop, nothing smaller in charts than 12 pt. If a table needs 10 pt to fit, it is an appendix table.
- Pacing for interpreters and captioners: 110 words per minute, a pause at every slide change, numbers repeated once. Send the deck and the glossary to the interpreters two days ahead.
- Provide the deck in advance for screen-reader users and for anyone who asks: the reading version as PDF with a tagged structure, plus the storyboard Markdown itself, which reads well in a screen reader.
- Plain language: short sentences, no idioms, every acronym expanded on first use and in the glossary.

## 8. Versioning and files

- Names: `topic-audience-yyyy-mm-dd.pptx`, all lower case, hyphens, no spaces: `onboarding-hires-leadership-2026-09-16.pptx`, `onboarding-hires-leadership-2026-09-16-reading.pdf`, `onboarding-hires-one-pager-2026-09-16.pdf`. A new date is a new version; never "final", "final2" or "final-final".
- What to send: PDF for reading, always. The pptx only when the recipient needs to edit or present it, and then a copy built from the storyboard, not the speaker's working file.
- HTML options from the same storyboard: the interactive deck (`deck_html.py`) as a link for people who will click through it themselves, and the PDF printed from the static build (`deck_html.py --mode static`) for everyone else. Each is one self-contained file that opens offline.
- Before sending an HTML deck: build it from a storyboard without the `Notes:` lines, open it once, and keep the file under about 20 MB (`--link-images` when embedded pictures push it over).
- Before sending a pptx: remove the speaker notes (the talk track is the speaker's, not the audience's), delete any hidden slides, check the document properties for the author name and the company, and remove comments. `deck_inspect.py` lists notes and hidden slides; fix at the storyboard and rebuild rather than editing the file by hand.
- Before sending a PDF: check that fonts are embedded, that the appendix is included, and that the page count matches the slide count.
- Keep the storyboard, the theme and the talk kit next to the deck under version control. The pptx and the PDF are build outputs; the storyboard is the source. A change requested after the meeting goes into the storyboard, then a rebuild, then a new dated file.
- Metadata and hidden content: a deck built from the storyboard has no leftover slides, but a deck edited in PowerPoint may. Check the slide sorter for hidden slides and the notes pane on every slide once before the file leaves the machine.
