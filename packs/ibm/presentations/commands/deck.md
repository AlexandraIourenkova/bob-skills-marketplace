---
description: Make a presentation with the presentations pack: brief, storyline, five style concepts to choose from, charts and pictures, a styled .pptx, and the talk kit
argument-hint: <topic, or a file such as report.md or data.xlsx> [--minutes 15] [--audience executives|investors|customers|technical|team|conference|training|research]
---

Make a presentation for `$ARGUMENTS` with the `presentation` skill, all steps in order. Work in a `deck/` folder next to the material and never overwrite the user's files.

1. **Brief.** Read the material named in the arguments (profile a spreadsheet with `deck-story/scripts/data_profile.py`). Fill `deck/brief.md`. Ask the user for audience, goal, format and time, and language, in one message with concrete options to pick from. Never guess the audience: it changes the story, the depth and the style set.
2. **Story.** Pick the narrative from `deck-story/references/narratives.md`, write `deck/storyboard.md` (one `## Headline` per slide, `Takeaway:`, `Source:`, `Notes:`), run `presentation/scripts/storyboard_check.py --minutes <N>`, fix the warnings, then show the headline outline and ask the user to approve or change the storyline.
3. **Style.** Run `deck-style/scripts/style_preview.py` with the deck's own title and a real headline (`--audience` only when the user named the audience, `--brand-accent` when the company colour is known, `--script` for Cyrillic, Hebrew or Arabic), open `deck/style-preview.html`, relay the numbered concept lines the script printed word for word, and ask the user to choose. Write `deck/theme.json` with `--choose <id>`.
4. **Visuals.** Charts as native chart blocks or rendered with `deck-dataviz/scripts/chart_render.py`. A generated backdrop for the title and section slides by default (`visual_assets.py backdrop`, SVG for HTML plus a PNG of the same name for the .pptx, `backdrop_scrim: none` in the front matter). Treated photos and placeholders with the same script; search terms, sources and prompts for the pictures the user still has to provide; credits in `deck/images/credits.md`.
5. **Build and verify.** `deck_html.py deck/storyboard.md --theme deck/theme.json -o deck/<name>.html` is the default output; iterate there. Render its pages to images with headless Chrome and look at every slide. Build the PDF (`--mode static`, then print to PDF) and the PowerPoint file (`deck_build.py`, then `deck_inspect.py`) when the user asks for them.
6. **Talk kit.** Fill `deck/talk-kit.md` from `deck-pitch/assets/talk-kit-template.md`: key messages, pitches, talk track, Q&A bank with backup slides, one-pager, follow-up email, rehearsal plan.
7. **Report.** Paths of everything produced (HTML deck first, then storyboard, theme, preview, talk kit), slide count and estimated minutes, warnings accepted, images pending with their search terms or prompts. Close with the offer to produce a PDF or a PowerPoint file from the same storyboard.

Stop and ask the user at steps 2 and 3; the deck is built only after both answers.
