# Pitch and talk track

This file tells you how to turn a finished storyboard into the spoken versions of the story: three key messages, a 30-second pitch, a 2-minute pitch, a 5-minute pitch and a per-slide talk track with seconds. Read it after the storyboard has passed `storyboard_check.py` and before you fill the "Key messages", "Pitch versions" and "Talk track" sections of `talk-kit.md`. The storyboard's headlines are the spine: every pitch is a subset of the headlines said out loud, and nothing in a pitch may contradict a slide. The speaker is the user. Write every pitch in the first person so the user can say it as written, and take the facts from the `Notes:` and `Source:` lines, never from memory.

## 1. Derive the pitches from the storyboard

Work in this order. Each step uses the output of the one before.

1. List the content headlines in deck order with their physical slide numbers (the outline that `storyboard_check.py` prints). Title and section slides count.
2. Pick the three key messages: the headlines the audience must be able to repeat the next day. One names the problem with a number, one names the cost of the problem or the strongest evidence, one names the proposal or the ask. Headlines that describe method, context or history support a message but are not one. If a message is not a headline in the deck, the deck is missing a slide: fix the storyboard first.
3. Write the 30-second pitch: who we are (skip when the room knows), what we found, why it matters, the ask with a date. Sixty to eighty words. Only the one or two numbers the audience will remember.
4. Write the 2-minute pitch: the 30-second pitch plus the evidence number behind each message with its source, plus the one objection you expect most and its answer in two sentences. About 250 words.
5. Write the 5-minute pitch: the 2-minute pitch plus one story or example (a named account, a before and after, a day in the life), plus the alternatives considered and why they lost. About 650 words.
6. Write the full talk track: one row per slide. For each: the first sentence (said before the audience has finished reading the headline), the evidence to point at, the transition to the next slide, and the seconds. Take the words from the `Notes:` lines. Do not add claims that are not in the storyboard.

### Sample storyboard, the spine for every example below

Internal proposal to the leadership team, 20-minute slot, a decision wanted. All examples in this file, in `qa.md` and in `handouts.md` use it.

| Slide | Headline |
|---|---|
| 1 | Two onboarding hires to protect enterprise revenue (title) |
| 2 | Where we are (section) |
| 3 | Enterprise customers doubled to 104 in twelve months |
| 4 | Time to first value grew from 21 to 47 days |
| 5 | Late-onboarded accounts churn three times more often in the first 90 days |
| 6 | 1.1 M of ARR is waiting in the onboarding queue today |
| 7 | What we propose (section) |
| 8 | Two onboarding specialists bring time to first value back to 25 days |
| 9 | The two hires cost 240 K and pay back with four retained accounts |
| 10 | Contractors, automation and reassignment all cost more or arrive later |
| 11 | Two risks, hiring time and ramp-up, and how we cover them |
| 12 | Approve two enterprise onboarding hires for Q4 (closing) |
| 13 to 19 | Appendix section and backup slides A1 to A6 (see `qa.md`) |

Key messages, each tied to the slide it lives on:

| # | Message | Evidence | Slide |
|---|---|---|---|
| 1 | Enterprise customers doubled and onboarding did not keep up | 52 to 104 customers; time to first value 21 to 47 days | 3, 4 |
| 2 | Late onboarding costs us customers and revenue | 9 percent versus 3 percent churn in the first 90 days; 1.1 M ARR in the queue | 5, 6 |
| 3 | Two specialists for 240 K fix it and pay back with four retained accounts | 25-day target; average contract 60 K, so four accounts cover the cost | 8, 9 |

### The 30-second pitch (elevator)

> We doubled our enterprise customers this year, to 104. Onboarding did not keep up: a new account now waits 47 days to get value, up from 21. Accounts that wait that long churn three times more often, and 1.1 million of ARR is sitting in the queue today. I am asking for two onboarding specialists, 240 K a year. Keeping four accounts pays for them. I need the decision by 30 September so they start in Q4.

Seventy-seven words, about 35 seconds at 130 words per minute. Who: implied, the room knows the speaker. What: the queue. Why it matters: the churn. The ask: two hires, a date.

### The 2-minute pitch

> We doubled our enterprise customers this year, from 52 to 104. That is the good news, and it is slide 3.
>
> The onboarding team did not grow with them. Time to first value, the days from contract signature to the first live workflow, went from 21 days in September last year to 47 days last month. That number comes from the CRM onboarding report, and every account is listed in the appendix.
>
> Why it matters: accounts that wait more than 30 days churn at 9 percent in their first 90 days. Accounts onboarded on time churn at 3 percent. Three times the churn, on the tier that is now 61 percent of our revenue. This morning 1.1 million of annual recurring revenue is waiting in the queue: 18 accounts.
>
> I am asking for two enterprise onboarding specialists, 240 K fully loaded for the year. With two more people the queue clears in eight weeks and time to first value returns to about 25 days, where it was before the growth. At an average contract of 60 K we need to keep four accounts we would otherwise lose, and the hires are paid for.
>
> The objection I expect: why not wait for the annual plan in January? Because the queue grows by three accounts a month, and the contracts signed this quarter reach their 90-day mark before January. Waiting one quarter puts about 30 accounts, 1.8 million of ARR, through the late path: at the six-point churn gap that is about 110 K of ARR lost, against 60 K of salary for the same quarter.
>
> The decision I need by 30 September: approve the two roles, so recruiting starts in October and both people are in place by mid-November.

About 290 words, a little over two minutes. If the slot is strict, drop the sentence about 61 percent of revenue and the cost-of-waiting arithmetic.

### The 5-minute pitch

> Six months ago Halvorsen Freight signed a 90 K contract with us. Their IT team was ready in week two. Our onboarding lead was carrying 22 accounts and got to them in week seven. By week nine their sponsor had escalated to our CEO, and in week eleven they asked for an exit clause. We kept them, but it cost a senior engineer a month of roadmap time. Their sponsor told me afterwards that the product was never the problem; the wait was. Halvorsen is no longer the exception. It is the median.
>
> Here is what changed. We doubled our enterprise customers in twelve months, from 52 to 104. The onboarding team stayed at three people. Time to first value, the days from signature to the first live workflow, went from 21 days to 47. That is the CRM onboarding report, monthly medians, and the full table is in the appendix.
>
> Why it matters is on one chart. We split the last 84 enterprise accounts into two groups: onboarded within 30 days, and later. The on-time group churned at 3 percent in the first 90 days. The late group churned at 9 percent. Same product, same price, same sales team. The only difference is the wait. Enterprise is now 61 percent of revenue, so this is the tier we can least afford to lose. This morning 18 accounts are in the queue, worth 1.1 million of ARR.
>
> What I propose: two enterprise onboarding specialists. Each carries about 22 accounts a quarter, which is what the current lead manages when the queue is under control. The first hire takes the queue in order of contract value; the second takes new signatures, so the queue stops growing. With two more people the queue clears in eight weeks and time to first value returns to about 25 days by the end of January. The metric is on the customer success dashboard already, updated every Monday, so you can check it yourselves.
>
> The cost is 240 K fully loaded for the year, 120 K per role, at the grade Finance has approved for the current team. Our average enterprise contract is 60 K. If the two hires prevent four churns, they are paid for. At today's rates they prevent more than that: the difference between 9 and 3 percent churn on 104 accounts is six accounts a year.
>
> We looked at three alternatives before asking for headcount. Contractors: 310 K for the same hours, and they do not know the product, so the first two months go to training. Automation: we are building self-serve onboarding for the mid-market tier, and it lands in Q2, but enterprise onboarding is integration work with the customer's IT team and stays manual. Reassigning account managers: they carry 30 accounts each, and every hour they spend on onboarding is an hour not spent on renewals, which is the revenue we are trying to protect. The two hires are the cheapest option that arrives in time. We also asked whether sales should slow enterprise signatures until onboarding catches up. Nobody in this room wants that, and neither do I.
>
> Two risks. Hiring takes time: recruiting quotes eight weeks for this profile, so both start by mid-November if the roles open on 1 October. Ramp-up: a new specialist carries a full load after six weeks, and the current lead takes the two largest waiting accounts in the meantime. Both risks have an owner on slide 11. If both hires slip past December, I come back to this group with the contractor option as a bridge, at the cost on slide A3.
>
> The decision I am asking for by 30 September: approve two enterprise onboarding hires for Q4. Three things to remember: customers doubled and onboarding did not; late onboarding triples churn; two people for 240 K fix it and four retained accounts pay for them.

About 650 words, five minutes at 130 words per minute with pauses after the numbers. The story is the opening, the alternatives take one paragraph, the close repeats the three messages.

### The full talk track

Seconds are speaking time. The total is 895 seconds, 15 minutes, which leaves the 20-minute slot with room for interruptions, questions and the close after Q&A.

| Slide | Headline | First sentence | Evidence to point at | Transition | Seconds |
|---|---|---|---|---|---|
| 1 | Two onboarding hires to protect enterprise revenue | "In the next fifteen minutes I will ask you to approve two hires, and I will show you the revenue they protect." | none | "Let me start with what changed this year." | 30 |
| 2 | Where we are | "Three numbers describe where we are. The first is the good one." | none | none | 10 |
| 3 | Enterprise customers doubled to 104 in twelve months | "We doubled enterprise customers in twelve months, from 52 to 104." | bar chart by quarter, Q3 highlighted; source: Finance close, August 2026 | "Growth like that lands on one team in particular." | 75 |
| 4 | Time to first value grew from 21 to 47 days | "A new enterprise account now waits 47 days for its first live workflow. A year ago it was 21." | line chart, monthly median; source: CRM onboarding report | "Waiting is not only annoying. It costs us the account." | 90 |
| 5 | Late-onboarded accounts churn three times more often | "Accounts onboarded late churn three times more often in their first 90 days." | two bars, 9 percent against 3 percent, cohort of 84 accounts; method on A1 | "Here is what that means in money, today." | 100 |
| 6 | 1.1 M of ARR is waiting in the onboarding queue today | "1.1 million of ARR is in the queue this morning: 18 accounts." | table of the five largest accounts; full list on A2 | "That is the problem. Here is the fix." | 80 |
| 7 | What we propose | "The proposal has three parts: the hires, the cost, and what we rejected." | none | none | 10 |
| 8 | Two specialists bring time to first value back to 25 days | "Two onboarding specialists bring time to first value back to 25 days." | capacity model, 22 accounts per person per quarter; queue clears in eight weeks | "What does that cost, and what does it return?" | 110 |
| 9 | The two hires cost 240 K and pay back with four retained accounts | "240 K for the year, and four retained accounts pay for it." | big numbers: 240 K, 60 K average contract, 4 accounts; source: Finance | "Headcount is not the only way, so we looked at three others." | 120 |
| 10 | Contractors, automation and reassignment all cost more or arrive later | "We rejected three alternatives, and here is why." | three columns with cost and arrival date; detail on A3 | "Two things could still go wrong." | 100 |
| 11 | Two risks, hiring time and ramp-up, and how we cover them | "The two risks are hiring time and ramp-up, and each has an owner." | timeline; recruiter's eight-week estimate; register on A4 | "So here is the decision on the table." | 80 |
| 12 | Approve two enterprise onboarding hires for Q4 | "I am asking you to approve two enterprise onboarding hires for Q4, decided by 30 September." | cost and date on the slide | "I will take questions now, then close with the three things to remember." | 90 |

After Q&A, return to slide 12 and say the three messages and the ask in four sentences. That is the last thing the room hears.

## 2. Structures by goal

Slots in order, with the share of speaking time in percent. Map each slot to one or more headlines; a slot with no headline is a missing slide, a headline with no slot is a candidate for the appendix.

| Goal | Slots and shares |
|---|---|
| Investor pitch | problem 10, solution 10, why now 5, market 10, product 15, traction 15, business model 10, competition 5, team 10, ask 10 |
| Internal proposal | decision wanted 5, evidence 35, cost 15, risk and mitigation 15, alternatives 15, ask 15 |
| Sales pitch | their problem 20, cost of inaction 15, the offer 25, proof 25, next step 15 |
| Status update | headline status 10, what changed 40, risks 25, decisions needed 25 |
| Technical review | context 10, options 25, recommendation 20, trade-offs 30, open questions 15 |
| Conference talk | hook 10, promise 5, three parts 70, payoff 15 |
| All-hands | why it matters to them 30, what happens next 40, what we ask of them 30 |

The sample deck is an internal proposal: decision wanted (slide 1), evidence (3 to 6), the fix (8), cost (9), alternatives (10), risk (11), ask (12).

## 3. Openings

The first 20 seconds must do three things: say what the talk is about in one sentence, say why this audience should care, and say what you will ask of them at the end. Never open with an agenda, the history of the project, or thanks for the invitation. The hook is the first sentence; the three things follow it.

| Hook | Example for the sample topic | Best for |
|---|---|---|
| A number | "Forty-seven days. That is how long a new enterprise customer waits before our product does anything for them." | executives, all-hands |
| A question | "How many of the customers we signed this quarter will still be here in March?" | teams, conference |
| A contrast | "A year ago onboarding took three weeks. Today it takes seven, and we sell the same product." | boards, status updates |
| A short customer story | "Halvorsen Freight was ready in week two. We got to them in week seven. In week eleven they asked for an exit clause." | sales, executives |
| A demo | "This is the onboarding queue as of eight o'clock this morning. Eighteen names. Watch what happens when I sort by contract value." | technical peers, customers |
| A quote | "'We bought a product and got a waiting list.' That is from the Halvorsen sponsor, in writing." | boards, all-hands |
| The decision on the table | "You will decide today whether we hire two onboarding specialists. Here is the evidence, in twelve slides." | internal proposals |

Pick one hook. Two hooks in a row read as indecision.

## 4. Closings

The last words are the ask. Never end on "Any questions?" or "Thank you": take questions before the close, then close. Four closings, in order of preference for a decision meeting:

1. The ask with a date: "Approve two enterprise onboarding hires by 30 September so they start in Q4."
2. The three messages: "Customers doubled and onboarding did not. Late onboarding triples churn. Two people for 240 K fix it." Then the ask.
3. The vision: "By February every enterprise customer is live within 25 days, and the queue is a dashboard nobody looks at." Then the ask.
4. The call to a specific next step: "I will send the one-pager tonight. I need one answer from each of you by Friday: yes, no, or what you need to say yes."

A closing slide with `layout: closing` carries the ask, the cost and the date. Say them; do not read them.

## 5. Transitions and signposting

Signposting tells the audience where they are. Use counts and repeat them: "three things, here is the first", "that was the first, the second is about cost". Transitions link the point just made to the next headline in one sentence; the talk track holds one per slide.

| Situation | Say |
|---|---|
| Entering a section | "Three numbers describe where we are. The first is the good one." |
| Between points in a section | "That is the volume. Now the speed." |
| From evidence to proposal | "That is the problem. Here is the fix." |
| From proposal to cost | "What does that cost, and what does it return?" |
| Into alternatives | "Headcount is not the only way, so we looked at three others." |
| Into risks | "Two things could still go wrong." |
| Into the ask | "So here is the decision on the table." |
| Back from a detour or question | "Back to the second point, cost." |
| Into the appendix | "The detail is on slide A3. Let me jump there." |

## 6. Timing

- Talk pace is about 130 words per minute for a prepared talk in a room, 110 for non-native audiences or interpreters, 150 for a fast conversational update. `storyboard_check.py --minutes N` uses 130.
- Talk length from the notes: count the words in all `Notes:` lines, divide by 130 for minutes. A content slide with no notes counts as 45 seconds. Add 10 seconds per slide for the click and the pause. The seconds column in the talk track must sum to the same figure within ten percent.
- Plan to finish at 85 percent of the slot: 17 minutes of a 20-minute slot, 25 of 30. The rest is interruptions, the demo that stalls, and the close after questions.
- When short on time, cut in this order: the appendix walk-through, the second example, the third piece of evidence on a slide, the alternatives detail (keep the one-line summary), the risk detail (keep the owners). Never cut the ask, the date or the three messages.
- Seconds per slide: under 30 means the slide is a transition and could merge with its neighbour; over 180 means the slide carries two points and should split.

## 7. Delivery notes

| Topic | Do this |
|---|---|
| Pace | Slower than conversation. One idea per breath. Speed up only for lists the slide already shows. |
| Pauses | After every number, two seconds. The audience reads the number while you breathe. |
| Eye contact | One sentence per person, across the room, not the same three faces. Remote: look at the camera lens for the first sentence of each slide, then at the notes. |
| Hands | Still or pointing at the slide. Not in pockets, not holding a pen that clicks. |
| Where to stand | Left of the screen from the audience's view, so eyes travel from you to the slide in reading order. Do not stand in the projector beam. |
| Notes versus speaking | Read nothing except quotes and exact numbers. Notes hold the first sentence and the transition; the rest is spoken. |
| The clicker | Advance after the transition sentence, not before it. Test the range. Know the back key. |
| When a slide fails | Say the headline from memory, give the number, move on. Never apologise for the technology or fix it in front of the room; the talk track carries every headline for this reason. |

## 8. Language notes

- Non-native audiences: sentences under fifteen words, one clause each. Say every number twice, once as a figure and once in context ("47 days, seven weeks"). Avoid idioms and sports metaphors. Slow to 110 words per minute and adjust the seconds column.
- Remote delivery: say the slide number when you advance ("slide 6, the queue"). Signpost twice as often; nobody can see you point. Put the ask in the chat as well as on the slide. Pause four seconds, not two, after questions; the audio lags.
- Translated decks: the pitch is translated from the talk kit, not from the slides, so the transitions survive. Numbers keep the source format and the units on the slide. Have a native speaker read the headlines aloud; a headline that takes two breaths in the target language is too long. Keep the English deck in the appendix when the audience is mixed.

## 9. When the slot is cut in half

It happens in the corridor: "you have ten minutes, not twenty". Do this before walking in.

1. Say the 2-minute pitch in your head. It is the talk now; the slides illustrate it.
2. Keep the title, the three slides that carry the key messages, the cost slide and the closing. For the sample deck: 1, 4, 5, 8, 9, 12. Skip the section slides by clicking through them.
3. Tell the room in the first sentence: "I have ten minutes, so I will show you three numbers and one decision. The rest is in the appendix and in the one-pager you will get tonight."
4. Cut every transition to its first clause. Cut the story. Keep every pause after a number.
5. Take questions on the skipped slides by jumping to them: the physical numbers are in the talk track.
6. Close with the ask and the date, exactly as written. The cut slot changes the evidence shown, never the ask.
