---
name: presentation
description: Make a presentation from scratch or from the user's material (data, documents, notes) as one workflow. A brief, a story with one headline per slide, five conceptually different style concepts previewed as an HTML page for the user to choose from, charts and pictures, then the deck itself, by default as an interactive HTML presentation to click through or share as a link, and on request as a PDF or a styled 16:9 PowerPoint file from the same storyboard. Ends with a talk kit (pitch versions, speaker notes, Q&A bank, one-pager, follow-up email). Use when the user asks for a presentation, a deck, slides, a pitch deck, a keynote, a board or investor update, a conference talk, a training deck, or says "сделай презентацию", "подготовь слайды", "нужна дека", "презентация по этим данным". The step skills deck-story, deck-style, deck-dataviz, deck-images and deck-pitch cover single steps; this skill runs them in order.
---

# presentation

Two decisions belong to the user and come before the build: the storyline (the headline outline) and the style concept. Everything the workflow produces goes into a `deck/` folder next to the user's material; the user's own files are never overwritten.

Paths below are relative to `.bob/skills/` (or `~/.bob/skills/` for a global install). Scripts run with `uv run --with <library> python <script>`: python-pptx for `deck_build.py` and `deck_inspect.py`, matplotlib for `chart_render.py`, pillow for `visual_assets.py`, pandas for `data_profile.py`; the other scripts need only Python 3.11+. Every script has `--help`, never touches the network and writes only the output path it is given.

## 1. Brief

1. Read what the user gave: files, links, notes, an old deck. For a spreadsheet or CSV run `uv run --with pandas python deck-story/scripts/data_profile.py <file>` and keep the output for the story step. For an existing `.pptx` run `deck_inspect.py` on it to read its text and notes.
2. Fill `deck/brief.md` from `references/brief-template.md`: audience, the goal in one sentence (the decision or action wanted), format (live talk, reading deck, pitch, workshop, keynote, demo), time slot and slide budget, language and script, material available, constraints (brand colour, template, must-have slides), the one thing to remember, known objections.
3. Ask the user for what the material cannot tell you, in one message, with the follow-up question tool when it is available. The audience, the goal and the format are answers, not guesses: the same numbers become a different deck for a board, a customer or a team of engineers. Offer concrete options so the answer is one click:
   - **Audience**: executives or a board, investors, customers or prospects, technical peers, the whole company or a team, a conference, students, partners, regulators.
   - **Goal**: a decision, a status report, persuading or selling, teaching, aligning or inspiring, warning about a risk.
   - **Format and time**: live talk, remote talk, reading deck, pitch, workshop, keynote, demo; minutes in the slot.
   - **Language** when the request and the material differ.

   Only when the user declines to answer, state the defaults you fall back to (live talk, 15 minutes, the language of the request, the general set of style concepts) and say that the deck can be re-pointed later.

## 2. Story

1. Pick the structure with the decision table in `deck-story/references/narratives.md`; take depth, tone and slide budget from `deck-story/references/audiences.md`; for data use the method in `deck-story/references/data-to-story.md`.
2. Write `deck/storyboard.md` in the format of `references/storyboard-format.md`: headlines first, each one the point of the slide, then the evidence, `Takeaway:` where there is a so-what, `Source:` for every number, `Notes:` on every content slide with what to say and where the numbers come from.
3. Check it and fix what you agree with:

   ```bash
   uv run python presentation/scripts/storyboard_check.py deck/storyboard.md --minutes 15
   ```

   Add `--reading` for a deck that is read instead of presented. The output starts with the headline test: the headlines alone must tell the story.
4. Show the user the headline outline (copy it from the check output) with one line on the structure chosen, and ask whether the storyline is right. Change what they ask for, re-run the check, and continue only with an agreed outline.

## 3. Style

1. Generate five concepts with the deck's own words:

   ```bash
   uv run --with pillow python deck-style/scripts/style_preview.py --title "<deck title>" --subtitle "<subtitle>" \
     --headline "<a real headline>" --bullets "<bullet>;<bullet>;<bullet>" --takeaway "<takeaway>" \
     --numbers "<value>|<label>|<detail>;<value>|<label>|<detail>" --section "<a chapter name>" \
     -o deck/style-preview.html
   ```

   Without options the five default concepts are shown: Swiss Minimal, IBM Carbon, Cyber Steel, Pencil Sketch and Geometric Poster. Add `--audience <the audience the user named>` only when the user actually named it, never from a guess; every preset still keeps one dark concept in the set. Other options: `--brand-accent "#RRGGBB"` adds a concept built on the company colour (shown first); `--script cyrillic|hebrew|arabic` swaps the fonts for ones that cover the script; `--rtl` previews right-to-left slides; `--pick a,b,c,d,e` chooses the five yourself (see `deck-style/references/concepts.md` for all fifteen concepts and how to pick five that differ).
2. Open the page for the user (`open deck/style-preview.html` on macOS, `xdg-open` on Linux, `start` on Windows; or tell them the path) and ask which concept and which picture set they want. Under each concept the page shows the title slide with every picture set from the library that suits that style, so both decisions are made from the same page. Relay the numbered lines the script printed, word for word: they carry the real name and description of each concept and of its picture sets. Never describe a concept from memory, never rename one, and never choose the picture set yourself. The page explains how to answer ("2 with pictures 3", "2, no pictures", "2 with the colours of 4"). Wait for the answer.
3. Write the theme, with overrides when the user combined concepts:

   ```bash
   uv run --with pillow python deck-style/scripts/style_preview.py --choose <id> --pictures <pack-x|none|generated> -o deck/theme.json
   ```

   Overrides: `--accent`, `--accent2`, `--bg`, `--text`, `--heading-font`, `--body-font`, `--align center`, `--name`. Record both choices in the brief.

## 4. Visuals

1. Charts: one message per chart, the slide headline states it (`deck-dataviz/references/chart-choice.md`, then `chart-makeover.md`). Bar, line, area, pie and doughnut go into the storyboard as native ```` ```chart ```` blocks (editable in PowerPoint, drawn in the theme colours, `"highlight"` for the one bar that matters). Waterfall, slope, lollipop, bullet, small multiples, scatter, heatmap and annotated charts are rendered with `chart_render.py` (spec in `deck-dataviz/references/chart-spec.md`) and placed with `![alt](charts/name.png)`:

   ```bash
   uv run --with matplotlib python deck-dataviz/scripts/chart_render.py deck/charts/bridge.json --theme deck/theme.json -o deck/charts/bridge.png
   ```

2. Pictures (`deck-images/references/treatment.md` for placement, `library.md` for the bundled set, `sources.md` for open sets, `prompts.md` for generation):
   - **Pictures from the set the user chose with the style.** The pack ships 86 pictures in eight sets (abstract vector, black and white photo art, dark technology, people at work, paper craft, desk objects, IBM-style isometric, IBM dark premium), or a backdrop generated from the theme colours. `theme.json` carries the user's choice; the library command reads it and names the title picture and the section pictures, then treat them straight into the deck:

     ```bash
     uv run --with pillow python deck-images/scripts/visual_assets.py library --for-theme deck/theme.json
     uv run --with pillow python deck-images/scripts/visual_assets.py treat "$(uv run --with pillow python deck-images/scripts/visual_assets.py library --pick growth)" --theme deck/theme.json --crop 16:9 --width 1920 -o deck/images/backdrop.jpg
     ```

     The command names one picture for the title and a list for the sections. Treat each into `deck/images/` under its own name and put `backdrop: images/<title>.jpg` and `section_backdrop: images/<section>.jpg` plus the `backdrop_scrim` it recommends in the front matter. Text over a picture goes on the left: the library pictures carry their subject on the right, so leave `backdrop_text` at its default (`left`), and on a `split` slide the picture takes the right half. The rule: **the title picture appears once and nowhere else**; sections either repeat one neutral picture or each chapter gets its own through a `![alt](images/x.jpg)` line under its `# Chapter` heading; content pictures are used once each. `library --find <words>` finds a picture for a slide by keyword (growth, decision, security, journey); such a picture goes on a `split` slide, half picture and half text, or full-bleed on an `image` slide.
   - **A generated backdrop** when the library has nothing that fits or the user wants an abstract one:

     ```bash
     uv run --with pillow python deck-images/scripts/visual_assets.py backdrop --theme deck/theme.json --pattern mesh -o deck/images/backdrop.svg
     uv run --with pillow python deck-images/scripts/visual_assets.py backdrop --theme deck/theme.json --pattern mesh -o deck/images/backdrop.png
     ```

     Then `backdrop: images/backdrop.svg` and `backdrop_scrim: none` in the front matter. The SVG is a few kilobytes and stays crisp in the HTML deck; the PNG of the same name is what the .pptx uses. Quiet patterns (`mesh`, `gradient`, `waves`, `noise`, `contours`) sit under text; `shapes`, `arcs`, `bands`, `dots` and `grid` are graphic and want a title style that leaves them room. `--seed` gives another variation, `--intensity 0.5` a calmer one for a section deck.
   - The user's own photos: `visual_assets.py treat` with one treatment for the whole deck (crop, duotone or tint, scrim for a headline).
   - Pictures nobody has yet: `visual_assets.py placeholder --text "Photo: ..."` so the deck can be reviewed, plus, in the report, the search terms with a source or a generation prompt for each. The user saves the files into `deck/images/`; you record them in `deck/images/credits.md`.
3. The deck carries its own furniture, so use it: the chapter name stands above every headline once the storyboard has `#` chapters, a chapter called `Appendix` letters the slides after it A1, A2 and drops them from the timing, and `confidentiality: Internal use` in the front matter marks an internal deck in the footer (leave it out for anything a customer sees). A chart takes `annotations` for one short note with a leader line and `target` for a plan line; use them where they say something the headline does not, not on every chart.
4. Icons: three or four tiles with an icon, a label and a line of detail (`layout: icons`, names from `visual_assets.py icon --list`) turn a list of features or steps into a slide people remember. Bold words in a headline take the accent colour (`**35 percent**`), so mark the one number or word that matters.
5. Put the `![alt](images/...)` lines and chart blocks into the storyboard and choose the layout per slide (`layout:` only when the automatic choice is wrong). A deck of only headline-and-bullets slides is the dull deck; aim for a picture, a chart, a number or a tile slide between every two text slides.

## 5. Build the HTML deck

HTML is the default output: it builds in a second, a change to the storyboard is visible immediately, and it is one file to share.

```bash
uv run python presentation/scripts/deck_html.py deck/storyboard.md --theme deck/theme.json -o deck/<topic>.html
```

One self-contained file: arrows, space or click to move, `O` overview, `N` speaker notes, `F` fullscreen, `P` print view, and the slide number in the address bar so a link opens on that slide. `--builds` reveals bullets one at a time; `--link-images` keeps pictures as links instead of embedding them.

Read the warnings on stderr (long headline, too many bullets, text that may overflow, dropped items) and fix the storyboard rather than the output; rebuild. Iterate here, not in PowerPoint.

The other two formats are built when the user asks for them, after the deck is right (`references/html-decks.md` compares them):

```bash
uv run python presentation/scripts/deck_html.py deck/storyboard.md --theme deck/theme.json --mode static -o deck/<topic>-print.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=deck/<topic>.pdf deck/<topic>-print.html
uv run --with python-pptx python presentation/scripts/deck_build.py deck/storyboard.md --theme deck/theme.json -o deck/<topic>.pptx
```

- **PDF** through the static HTML, one slide per page, for sending and printing.
- **PowerPoint** for people who will edit the slides or present from Office. Options: `--logo logo.png`, `--backdrop`, `--max-bullets`, `--strict`. Verify it with section 6 before handing it over.

## 6. Verify

Verification is on the built deck. For an HTML-only deck, render its pages to images (step 2 below); `deck_inspect.py` reads a .pptx, so run step 1 whenever you built one.

1. Read the .pptx back and check it against the storyboard, slide by slide: headlines, numbers, notes, pictures, and the checks section (shapes outside the slide, overlaps, probable overflow, tiny fonts):

   ```bash
   uv run --with python-pptx python presentation/scripts/deck_inspect.py deck/<topic>.pptx
   ```

2. Look at every slide as an image. The HTML deck is the fastest route and needs no extra software:

   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=deck/renders/deck.pdf deck/<topic>-print.html
   pdftoppm -r 80 -png deck/renders/deck.pdf deck/renders/slide
   ```

   The PowerPoint file renders the same way through LibreOffice when it is installed (`soffice --headless --convert-to pdf --outdir deck/renders deck/<topic>.pptx`). Check overflow, overlaps and unreadable labels. When neither browser nor LibreOffice is available, say that the visual review was skipped and ask the user to open the deck once.
3. Fix in the storyboard, rebuild, inspect again. Then run `storyboard_check.py` once more with the final storyboard.

## 7. Talk kit

Copy `deck-pitch/assets/talk-kit-template.md` to `deck/talk-kit.md` and fill it from the storyboard: three key messages, the 30-second, 2-minute and 5-minute pitches, the talk track per slide with seconds, at least ten Q&A entries with the evidence and the backup slide, the backup slides to add to the appendix, the one-pager, the follow-up email, the rehearsal plan (`deck-pitch/references/pitch.md`, `qa.md`, `handouts.md`). Put the backup slides into the storyboard after a `# Appendix` section slide and rebuild.

## 8. Hand over

Report in one message: the paths (HTML deck first, then anything else produced: PDF, PowerPoint, storyboard, theme, style preview, talk kit, renders), slide count and estimated minutes from the check, the concept chosen, warnings you accepted, pictures still pending with their search terms or prompts, credits recorded, and anything not done. Say in one line how to present it: open the file in a browser, `F` for fullscreen, arrows to move.

End with the offer, in one line: a PDF for sending, or a PowerPoint file for people who will edit the slides. Build either on request; both come from the same storyboard, so nothing is redone.

## Variations

- **Quick draft.** The user wants one deck now ("быстро", "just a draft"): ask the audience and the time in one short question, show the headline outline once, pick one concept yourself and say which and why (the preview page still goes into `deck/` so they can change it), build, inspect, hand over.
- **Reading deck.** Full-sentence headlines, a short context paragraph on each slide, sources on the slide, no builds; check with `--reading`. Hand over the PDF from the static HTML, not the interactive file.
- **Link instead of a file.** The interactive HTML is one self-contained document: it can be mailed, put in a repository or served by any static host. Remove the speaker notes from the shared copy when the audience should not read them.
- **Existing deck.** Read it with `deck_inspect.py` (or the office-docs `pptx_extract.py` when that pack is installed), rebuild the story from its content, and write a new file.
- **Corporate template.** This pack draws its own layouts from the theme. When the deck must sit on a corporate `.potx` or `.pptx`, keep the storyboard (its syntax is a superset of the office-docs outline) and build with the office-docs `pptx_build.py --template`; the layouts `big-number`, `timeline`, `quote` and `two-column` then fall back to bullets, so say so before choosing that route.
- **Only one step.** For "just the story", "just a style", "just this chart", "prepare me for questions", use the step skill directly; the files still go into `deck/` so the rest can follow later.
