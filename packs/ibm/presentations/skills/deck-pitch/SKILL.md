---
name: deck-pitch
description: Everything around the slides. The spoken pitch at four lengths, a per-slide talk track with timings, a Q&A bank with prepared answers and backup slides, a one-page leave-behind, the follow-up email, a rehearsal plan and a day-of checklist. Written from the deck's own storyboard so every answer points at a slide. Use when the user has a deck and needs to present it, asks how to open or close, what to say per slide, how long it will take, what questions to expect, how to handle a hostile question, wants an elevator pitch or a one-pager, or says "подготовь питч", "какие вопросы зададут", "что говорить на слайдах".
---

# deck-pitch

Output: `deck/talk-kit.md`, filled from `assets/talk-kit-template.md`. The storyboard is the source: the headlines are the spine, the notes are the raw talk track, and every Q&A answer names a slide or a backup slide.

## 1. Three key messages

Read the headline outline (`storyboard_check.py` prints it) and pick the three headlines the audience must be able to repeat the next day. Each gets its evidence number and the slide it lives on. Everything else in the kit is built from these three.

## 2. Pitch versions and the talk track

`references/pitch.md` has the method and full worked examples: the 30-second version (who, what, why it matters, the ask), 2 minutes (adds the evidence and the main objection), 5 minutes (adds one example and the alternatives considered), and the per-slide talk track: first sentence, evidence to point at, transition, seconds. It also carries the structures by goal (investor pitch, internal proposal, sales, status update, technical review, conference talk, all-hands), seven opening hooks with examples, the closings that work, the timing arithmetic at about 130 words per minute with the 85 percent rule, delivery notes, and what to cut when the slot is halved.

Check the total against the deck: `storyboard_check.py --minutes <N>` estimates the talk from the notes, so write the notes first and let the number come out.

## 3. Q&A bank

`references/qa.md` turns each slide into the questions it invites, lists eight to ten questions per audience (executives, investors, customers, technical peers, all-hands, skeptics, regulators), and ranks them by damage times likelihood. Write full answers for the top ten, each with its evidence and its backup slide. The answer frameworks are there too: answer in one sentence then the reason and the example, what to say when the answer is not known yet, how to reframe a loaded question, the parking lot, and how to handle the room, remote Q&A and difficult moments.

At least ten filled entries go into the kit. Every entry names the slide or the backup slide that carries the evidence.

## 4. Backup slides

Methodology, the full data table, alternatives considered with costs, risks and mitigations, timeline detail, glossary. Add them to the storyboard after a `# Appendix` section slide, rebuild the deck, and write their slide numbers into the Q&A entries so they can be reached during the talk.

## 5. Leave-behind, follow-up, rehearsal, day-of

`references/handouts.md` covers the one-pager (the ask as the title, three messages with their numbers, the decision and date, contact), the reading version of the deck (derived from the same storyboard, checked with `--reading`), the appendix strategy, the follow-up email sent within a day, the three-run rehearsal plan with the headline-only run, the day-of checklist, accessibility (describing charts aloud, alt text, pacing), and the file rules for sending the deck.

## 6. Hand over

Report the kit's path, the estimated talk length against the slot, the three messages, the number of Q&A entries and backup slides added, and anything the user still has to decide (the exact ask, a number you could not source, a question you could not answer).
