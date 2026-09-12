# Story structures

This file is the catalogue of narrative structures for a deck. Read it after the audience and the goal are known (audiences.md) and before writing the storyboard: pick one structure from the decision table, copy its skeleton, replace every placeholder with a headline that passes the headline test, then write the storyboard from that headline sequence. When the user brings no material at all, run the interview at the end of this file first.

## Pick a structure

| Goal | Audience | Material in hand | Structure |
|---|---|---|---|
| Get a decision | Executives, a board, a steering group | A recommendation and its evidence | Pyramid (answer first); Options and a recommendation when they expect to choose |
| Get a decision on a change | Any leadership group that does not yet feel the urgency | A problem and a proposed change | SCQA |
| Sell or pitch | Prospects, buyers, investors | A product and a pain it removes | Problem, Agitate, Solve; Before, After, Bridge when the pain is mild |
| Inspire | Conference, all-hands, keynote | A vision and a few proof points | Sparkline |
| Tell a customer story | Prospects, a conference | One customer, a before and an after | Hero's journey |
| Review a period or an event | A team, a steering group | Results, an incident, a sprint | What, So what, Now what |
| Report progress | Sponsors, a steering group | Milestones and a status table | Chronological journey |
| Explain a strategy | Leadership, investors, the whole company | Bets that mature at different times | Three acts, three horizons |
| Show a product | Prospects, users, an internal team | A working product | Demo tour |
| Present analysis | Anyone who will act on the numbers | A dataset with findings (data-to-story.md) | Data story arc |

When two structures fit, take the one that puts the ask earlier. Executives leave early; the ask must survive.

## The twelve structures

Each skeleton lists slide slots. A slot is one `##` headline. Slots in brackets are optional. Replace every placeholder with a full-sentence headline before writing any bullets.

### 1. SCQA: Situation, Complication, Question, Answer

Fits: a proposal that changes something, for an audience that shares the starting picture but not the urgency.

| Slot | Example: moving billing from on-premises to cloud |
|---|---|
| Situation: [what everyone in the room accepts] | Billing runs on two servers installed in 2016 |
| Complication: [what changed] | Support ends in March 2027 and spare parts already take six weeks |
| Question: [the question this raises] | What keeps invoices going out after March 2027? |
| Answer: [the recommendation] | Move billing to the cloud platform in two waves before March |
| Evidence 1: [why the answer works] | The pilot processed 40 000 invoices in July with zero errors |
| Evidence 2: [cost or risk answered] | Migration costs 310 K once and saves 120 K a year |
| [Risks and their owners] | Two risks remain, cut-over and the deadline; both have owners |
| Ask: [decision and date] | Approve wave one by 30 September to hit the March deadline |

Pitfalls: four slides of Situation (one is enough, the audience lives in it); stating the Question and then answering a different one.

### 2. Pyramid, answer first (Minto)

Fits: executives and boards, anyone who reads the first slide and then argues.

| Slot | Example: quarterly finance review |
|---|---|
| Answer: [the recommendation or main conclusion] | Q3 beat plan by 6 percent; approve two enterprise hires for Q4 |
| Reason 1: [first supporting argument] | Subscriptions grew 18 percent and now carry 61 percent of revenue |
| Reason 2 | Costs stayed flat at 8.1 M while volume rose 14 percent |
| Reason 3 | Onboarding is the bottleneck: 23 customers wait 40 days each |
| [Evidence under a reason, one slide each when needed] | The onboarding backlog grew every month since April |
| Risks: [what could go wrong] | FX and one late renewal could cost 0.4 M in Q4 |
| Ask: [decision with date and cost] | Two hires, 240 K a year, decision by 30 September |

Pitfalls: burying the answer on slide six because it "needs context"; three reasons that overlap (each reason is a different kind of argument: growth, cost, capacity).

### 3. Sparkline: what is, what could be

Fits: keynotes and all-hands where the aim is belief, not a decision. The talk alternates the present with a better future and ends on the "new bliss".

| Slot | Example: keynote on field service |
|---|---|
| What is: [the present, concrete] | Technicians drive 90 minutes a day to jobs a call could fix |
| What could be: [the future, concrete] | Half of those visits become a ten-minute video call |
| What is: [a second present pain] | Parts arrive after the technician on one visit in four |
| What could be | The part is in the van because the fault was found yesterday |
| Proof: [evidence the future is possible] | Two regions tried it: first-time fix rose from 71 to 88 percent |
| Call to adventure: [what the audience must do] | Every region moves to remote diagnosis first by June |
| New bliss: [the future, felt] | Customers stop waiting at home; technicians fix, not drive |

Pitfalls: only "what could be" (it sounds like marketing); a "what is" without a number (it sounds like a complaint).

### 4. Hero's journey, transformation

Fits: customer stories and case studies. The customer is the hero; the product is the guide, never the hero.

| Slot | Example: customer story, Northwind Freight |
|---|---|
| Ordinary world: [the customer before] | Northwind moved 12 000 pallets a day on spreadsheets and phone calls |
| Call: [the trigger] | A lost 2 M contract in 2024 forced a change |
| Guide: [where the product enters, briefly] | Northwind chose a routing platform and one integration partner |
| Trials: [what was hard, honestly] | Drivers rejected the app until dispatch changed the roster |
| Transformation: [the after, with numbers] | On-time delivery rose from 84 to 96 percent in nine months |
| Return: [what they do now that was impossible] | Northwind now bids for same-day contracts it used to decline |
| [Lesson for the audience] | Start with dispatch, not with the drivers |

Pitfalls: making the product the hero (audiences trust customers, not vendors); skipping the trials, which are what make the transformation credible.

### 5. Problem, Agitate, Solve

Fits: sales pitches and any deck where the audience underrates a pain.

| Slot | Example: pitching fraud detection to a bank |
|---|---|
| Problem: [the pain, named] | Card fraud cost Kestrel Bank 14 M last year |
| Agitate: [why it is worse than they think] | Losses doubled in two years; rules catch fraud 36 hours late |
| Agitate: [the cost of waiting] | Every month of delay adds about 1.2 M in losses |
| Solve: [the answer] | Real-time scoring stops 70 percent of fraud before the money leaves |
| Proof: [a similar customer] | A comparable bank cut losses by 62 percent in the first year |
| Ask | Run a 90-day pilot on the debit portfolio |

Pitfalls: agitating without a number (it reads as fear-mongering); solving before the audience feels the problem.

### 6. Before, After, Bridge

Fits: product launches, process changes, internal announcements where the pain is real but mild.

| Slot | Example: launching a scheduling feature |
|---|---|
| Before: [life today] | Managers spend four hours a week building shift rosters by hand |
| After: [life with the change] | The roster builds itself in ten minutes and managers only approve |
| Bridge: [what gets you from before to after] | Auto-scheduling ships on 15 October to all Pro accounts |
| How it works: [the minimum needed] | It reads availability, skills and labour rules you already store |
| Proof: [pilot results] | Twelve pilot sites cut roster time by 85 percent |
| Ask or next step | Enable it for your region in the admin console by 1 November |

Pitfalls: an After that is not concrete; a Bridge that lists features instead of the one change.

### 7. What, So what, Now what

Fits: reviews, retrospectives, post-incident reviews. Facts first, meaning second, actions third.

| Slot | Example: post-incident review, checkout outage |
|---|---|
| What: [the facts, neutral] | Checkout was down 47 minutes on 12 August; 3 100 orders lost |
| What: [the timeline] | A config change at 14:02 took the payment service down at 14:05 |
| So what: [the cause] | The change had no review because the pipeline treats config as data |
| So what: [what it reveals] | The same gap exists in four other services |
| Now what: [actions] | Config changes go through review from 1 September |
| Now what: [owners and dates] | Five services, five owners, all done by 30 September |
| [Ask] | Approve a two-week freeze on unreviewed config changes |

Pitfalls: blame mixed into the What (keep it neutral); a Now what with no owners or dates.

### 8. Three acts, three horizons

Fits: strategy decks. Three acts are setup, confrontation, resolution; three horizons are now, next and later.

| Slot | Example: payments strategy |
|---|---|
| Setup: [where we are and why it matters] | Card payments are 82 percent of revenue and growing 3 percent a year |
| Horizon 1, now: [defend the core] | Keep the card business at 40 percent margin for three more years |
| Horizon 2, next: [build the next business] | Instant payments reach 15 percent of volume by 2028 |
| Horizon 3, later: [place a few bets] | Two bets: embedded lending and cross-border wallets |
| Confrontation: [what makes it hard] | Horizon 2 cannibalises Horizon 1 by about 4 M a year |
| Resolution: [how the tension is resolved] | Fund Horizon 2 from card margin now, while it exists |
| Ask | Approve the 2027 budget split 70 / 25 / 5 |

Pitfalls: horizons with no numbers (a wish list); no confrontation slide, so the strategy sounds free.

### 9. Chronological journey

Fits: project updates and progress reports, when the audience wants to know where things stand.

| Slot | Example: ERP rollout status |
|---|---|
| Where we are: [status in one line, honest colour] | Three of five sites are live; the fourth slips by six weeks |
| Done: [since the last update] | Finance and procurement went live in Lyon on 2 August |
| Surprise: [what happened] | The Lyon data migration found 9 000 duplicate suppliers |
| Next: [a `timeline` slide] | Hamburg in October, Madrid in January |
| Risks: [a status `table`] | Two red risks: Hamburg testing capacity and the year-end freeze |
| Ask or decision | Approve two extra testers for Hamburg until October |

Pitfalls: the full history from kick-off every time (start from the last update); a green status with red details in the notes.

### 10. Options and a recommendation

Fits: decision meetings where the audience expects to choose and would resent a single answer.

| Slot | Example: choosing a data warehouse |
|---|---|
| Decision: [what we decide and by when] | Choose the warehouse platform for 2027 by 15 October |
| Criteria: [how we judge] | Four criteria: three-year cost, migration effort, skills, lock-in |
| Options: [the comparison table] | Three options scored against the four criteria |
| Recommendation: [the choice and why] | Option B costs 20 percent more but halves the migration effort |
| What we give up: [the honest downside] | Option B locks us in for three years |
| Ask | Approve Option B and a four-week proof of concept |

The comparison table on the options slide, in storyboard syntax:

```markdown
| Criterion | A: stay | B: managed cloud | C: open source |
|---|---|---|---|
| Cost, 3 years | 1.1 M | 1.4 M | 0.9 M |
| Migration effort | none | 4 months | 9 months |
| Skills in house | yes | partly | no |
| Lock-in | low | high | low |
```

Pitfalls: a straw-man option nobody would choose (the audience notices); criteria invented after the choice.

### 11. Demo tour: show rather than tell

Fits: product demos. Every slide is a screen or a moment; the deck is the spine, the product is the content.

| Slot | Example: expense app with receipt reading |
|---|---|
| Who and why: [the user and the job] | Sales reps file 20 expenses a month and hate every one |
| Scene 1: [the first moment they see] | Photograph a receipt: the app fills amount, merchant and category |
| Scene 2 | Submit from the phone; the manager approves in one tap |
| Scene 3: [the moment that sells] | Month-end close takes finance one afternoon instead of four days |
| Under the hood: [only for a technical audience] | Receipts are read by a model that gets 97 percent of amounts right |
| Cost and how to start | Live in two weeks with your existing card feed |
| Ask | A pilot with one sales team in Q4 |

Pitfalls: features in menu order instead of the order the user meets them; a demo with no fallback (a screenshot per scene saves a broken network).

### 12. Data story arc

Fits: analytics decks, research results, experiment readouts. Built with data-to-story.md.

| Slot | Example: onboarding email experiment |
|---|---|
| Context: [what was measured and why] | We tested a three-email onboarding series on 24 000 new users |
| Hook: [the surprising number] | Activation rose 9 points, but only for users who signed up on mobile |
| Evidence 1 | Mobile sign-ups activated at 41 percent against 32 in the control |
| Evidence 2 | Desktop sign-ups showed no change: 46 against 45 percent |
| Evidence 3 | The effect held across all four weeks and both regions |
| Insight: [what it means] | The series works where onboarding is hard, not where it is easy |
| Action | Ship the series to mobile sign-ups now; redesign desktop onboarding |

Pitfalls: method before results (method goes to the appendix); an insight that repeats the evidence instead of explaining it.

## Headline rules

1. The headline is the conclusion, not the topic. "Q3 results" is a topic; "Q3 beat plan by 6 percent" is a headline.
2. The headline test: read only the `##` lines from top to bottom. If the story holds without the slide bodies, the deck works. `storyboard_check.py` prints this outline first for exactly this reason.
3. One idea per slide. A headline with "and" joining two claims is two slides.
4. Put the number in the headline when there is one. Numbers are remembered; adjectives are not.
5. Use a verb. "Grew", "fell", "costs", "blocks", "needs" carry the claim.
6. Under 70 characters, so it fits on one line at 32 pt. Cut articles and qualifiers before cutting the number.

| Weak (a topic) | Strong (a conclusion) |
|---|---|
| Revenue overview | Revenue grew 18 percent on subscriptions |
| Customer churn | Churn doubled in the SMB tier since January |
| Migration options | Managed cloud halves the migration effort for 20 percent more |
| Team update | The team closed 140 tickets and the backlog still grew |
| Security posture | Four of nine services accept unreviewed config changes |
| Market analysis | The mid-market segment grows twice as fast as enterprise |
| Pilot results | The pilot cut roster time by 85 percent at twelve sites |
| Risks | Two risks can move the March deadline; both have owners |
| Next steps | Approve wave one by 30 September |
| Product roadmap | Three releases in 2027, each removes one manual step |

## Openings

Open with the hook, not the agenda. The first content slide earns the next ten minutes.

| Hook | Example headline |
|---|---|
| A striking number | Card fraud cost us 14 M last year, twice the 2023 figure |
| A question | What keeps invoices going out after March 2027? |
| A contrast | We ship every two weeks; our competitor ships every day |
| A short story | One technician, one Tuesday, four visits, one fix |
| A demo | Watch a receipt become an expense in eight seconds |
| A customer quote | "We stopped losing contracts on delivery times" (COO, Northwind Freight) |
| What you will decide today | You choose between three warehouse options today; here is our pick |

## Endings

The last slide stays on screen during the discussion. It must carry what you want them to keep.

| Ending | Use when | Example |
|---|---|---|
| The ask | A decision is needed | Approve two hires, 240 K a year, by 30 September |
| Three messages | The goal was to inform | Revenue up 18 percent, costs flat, onboarding blocks Q4 |
| The vision | A keynote or an all-hands | Every fault diagnosed before the van leaves |
| The next step with a date | A working session | We reconvene on 4 October with the pilot numbers |

Do not end on "Thank you" or "Questions?". Both leave a blank wall behind the conversation and hand the room back with nothing to argue about. Put the ask or the three messages on the last slide with contacts under it (`layout: closing`) and take questions in front of it. If the culture requires a thank-you, say it; do not slide it.

## Transitions, sections and the agenda

- Sections (`#` lines) map to the parts of the structure: one per act, per horizon, or per SCQA letter in a long deck. Under about twelve content slides, use no sections. A section headline can be a claim too: "Where the growth came from" beats "Part 2".
- The agenda is optional. Use it for decks over fifteen slides or for audiences that expect one. Write it as a preview of the argument, not a list of topics: "Three things: growth came from subscriptions, costs held, onboarding blocks Q4".
- Transitions live in the notes, one sentence each: what the last slide showed, what the next one asks. Write them as `Notes:` on the slide that ends a section.

## Slide budgets

| Format | Minutes per slide | Typical count |
|---|---|---|
| Live talk with discussion | 1.5 to 2 | 20 minutes: 10 to 13 slides; 45 minutes: 22 to 30 |
| Live talk, no interruptions | 1 to 1.5 | 20 minutes: 13 to 20 |
| Keynote, big visuals | 0.5 to 1 | 45 minutes: 45 to 90, most of them one picture or one line |
| Lightning talk | 0.5 to 1 | 5 minutes: 5 to 10 |
| Pitch | 1 | 10 minutes: 10 to 12 |
| Reading deck, sent by email | no clock | 8 to 15 dense slides, appendix apart |
| Training | 2 to 4, plus exercises | one hour: 12 to 20, with an exercise every 15 minutes |

The 10/20/30 guideline (ten slides, twenty minutes, 30 pt fonts) is right for pitches and executive updates. It does not apply to reading decks (denser, no clock), keynotes (more slides, fewer words), training (fewer slides, more time on each) or board papers (the slides are an appendix to the paper). Pass `--minutes` to `storyboard_check.py` to test the count against the time.

## Starting from nothing: the interview

When the user has no material, ask these eight questions in one message. Accept short answers and ask again only for the missing ones.

1. Who is in the room, and who decides? (the audience; see audiences.md)
2. What do you want them to do at the end? (the ask)
3. What do they believe today about this topic? (the Situation, or the Before)
4. What evidence do you have: numbers, a pilot, a customer, a demo? (the Evidence slots)
5. What are the constraints: time, format, confidentiality, house template? (the slide budget and the style)
6. If they remember one sentence a week later, what is it? (the title slide and the closing)
7. What will they object to? (the Risks slot and the notes)
8. How long do you have, and will they read it in advance? (format and density)

| Answer | Where it goes |
|---|---|
| A decision wanted, evidence in hand | Pyramid; the ask is the first content slide and the last slide |
| A decision wanted, the audience does not feel the problem yet | SCQA, or Problem, Agitate, Solve |
| No decision, status only | Chronological journey, or What, So what, Now what |
| Belief wanted, no decision | Sparkline |
| The one sentence | Title slide subtitle, repeated as the closing headline |
| Objections | One slide each when strong, otherwise `Notes:` on the slide they attack |
| Evidence is a dataset | data-to-story.md first, then the Data story arc |
