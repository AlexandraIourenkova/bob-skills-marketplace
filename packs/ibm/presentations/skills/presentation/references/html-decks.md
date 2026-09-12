# HTML decks

`deck_html.py` builds a presentation from the same `storyboard.md` and the same `theme.json` as the PowerPoint file. One source, three outputs: the `.pptx` from `deck_build.py`, an interactive HTML deck to present from or share as a link, and a static HTML page that prints to a PDF. The slides carry the same colours, fonts, sizes and layouts in all three, because both builders read the same theme and the same storyboard (`storyboard-format.md`). Read this file when the user asks for a link, a PDF, a handout, or a deck for people who do not have PowerPoint.

| The audience wants | Hand over | Build with |
|---|---|---|
| to edit the slides | the `.pptx` | `deck_build.py` |
| you to present it, or a link they click through themselves | the interactive HTML | `deck_html.py` |
| a PDF or a printed handout | the PDF printed from the static HTML, or the `.pptx` exported from PowerPoint | `deck_html.py --mode static`, then print |

Build the `.pptx` and the interactive HTML by default. Add the PDF whenever the deck is sent instead of spoken.

## 1. The two modes

```bash
uv run python presentation/scripts/deck_html.py deck/storyboard.md --theme deck/theme.json -o deck/topic.html
uv run python presentation/scripts/deck_html.py deck/storyboard.md --theme deck/theme.json --mode static -o deck/topic-print.html
```

| Flag | What it does |
|---|---|
| `-o, --output` | the output `.html` path, required |
| `--theme theme.json` | the theme from `deck-style`. Without it the built-in Boardroom Blue theme is used |
| `--mode interactive` | default: one slide at a time, navigation, notes, overview |
| `--mode static` | the slides stacked as pages, `@page` set to the slide size, for printing |
| `--builds` | interactive only: bullets, big-number tiles and timeline steps appear one at a time |
| `--link-images` | keep pictures as relative links instead of embedding them. The images folder must travel with the file |
| `--strict` | exit 1 and write nothing when there are warnings |

The script needs only Python 3.11 or later, no extra library, and touches no network. Warnings go to stderr with the slide number (long headline, too many bullets, missing picture, dropped items). Fix the storyboard, not the output, and build again.

## 2. What the interactive deck does

The slide is a fixed stage of 1280 x 720 px (13.333 x 7.5 in at 96 px per inch, the size PowerPoint uses for 16:9). The stage is scaled to the window as a whole, so nothing reflows and the layout matches the `.pptx` slide for slide. A small window shows the whole slide, letterboxed on a dark background.

| Key | Effect |
|---|---|
| Right arrow, space, Enter, PageDown | next build step, then the next slide |
| Left arrow, Backspace, PageUp | previous build step, then the previous slide |
| Home, End | first slide, last slide |
| 1 to 9 | jump to that slide |
| N | speaker notes panel at the bottom of the screen |
| O | overview grid of every slide; click a cell to jump there |
| F | fullscreen on and off |
| P | print view on and off (the stacked layout, ready for the browser print command) |
| ? | help card listing the keys |
| Escape | close the notes panel, the overview and the help card |

Keys pressed with Cmd, Ctrl or Alt are left to the browser, so Cmd+P and Ctrl+P still open the print dialog.

- **Mouse.** A click in the left quarter of the window goes back, a click anywhere else goes forward. Clicks do nothing while the print view is on.
- **Touch.** A horizontal swipe of more than about 45 px moves one slide.
- **Address bar.** The current slide number is written to the address as `#7`, so a copied link opens on that slide and the browser back button walks back through the slides visited.
- **Chrome.** A thin progress bar along the bottom edge, a counter such as `4 / 17` in the bottom right, and a button bar next to it: back, forward, Overview (O), Notes (N), PDF (P), and help.
- **Notes.** The `Notes:` paragraphs of the slide, shown in a panel over the lower part of the screen. A slide without notes says so.

## 3. Printing to PDF

The static file is one page per slide. `@page{size:1280px 720px;margin:0}` sets the paper to the slide, so no scaling and no margins are needed in the dialog.

1. Build with `--mode static`.
2. Open the file in the browser and print it.
3. In the dialog: background graphics on, margins none, scale 100. Paper size follows the `@page` rule.
4. Save as PDF. A 17-slide deck gives a 17-page PDF, each page 960 x 540 pt, which is 13.33 x 7.5 in.

The same PDF without a dialog:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=deck.pdf deck.html
```

On Linux the binary is `google-chrome`. Chrome writes a line to stderr with the byte count; other lines about displays and web apps are noise.

The interactive deck prints as well: press P for the print view, then the browser print command. Its print stylesheet stacks every slide the same way, so the headless command above also works on the interactive file. One exception: with `--builds`, the steps of the slide on screen may still be hidden when you print, so print the static file for a deck built with builds.

## 4. What is inlined, and what it costs

Everything is in the one file: the CSS, the navigation script, the charts as inline SVG, the pictures as base64 data URIs. The result is a self-contained document. It opens offline, from a memory stick or a mail attachment, with no build step, no server and no network request.

| File | Size |
|---|---|
| 17-slide deck, SVG charts, pictures kept as links | about 38 KB |
| the same deck with two small PNG pictures embedded | about 64 KB |
| the same deck in static mode | about 58 KB |
| the PDF printed from it | about 470 KB |

Base64 costs about a third more than the file on disk, so an embedded 2 MB photo adds about 2.7 MB. Rules of thumb:

- Keep a file that will be shared under about 20 MB. Mail systems and chat tools start refusing above that.
- Resize pictures before placing them (`deck-images/references/treatment.md`), then embed.
- When the deck is picture-heavy and stays in a folder or a repository, use `--link-images` and ship the `images/` folder next to the HTML file.

## 5. Charts

The same fenced ```` ```chart ```` blocks that become native PowerPoint charts are drawn as inline SVG here: `bar`, `barh`, `stacked`, `barh-stacked`, `line`, `area`, `pie` and `doughnut`, with data labels, a legend, gridlines, tick labels in the `number_format` of the block, and the `highlight` key that puts the named categories in the accent colour and the rest in grey. Colours come from the theme palette, so a chart looks the same in both outputs.

Charts that `chart_render.py` produces (waterfall, slope, lollipop, bullet, small multiples, scatter, annotated line) are placed as `![alt](charts/name.png)` pictures and are embedded like any other picture.

SVG is drawn by the browser, so it stays sharp at any zoom and prints at the printer's resolution. A rendered PNG is as sharp as the file.

## 6. Sharing and hosting

One file, so the routes are simple: attach it to an email, commit it to a repository, copy it to a memory stick, or drop it on any static file host. The deck itself uploads nothing and calls nothing; opening it produces no network traffic.

The speaker notes are inside the file. They are hidden until N is pressed, and they are in the source for anyone who looks. Build the shared copy from a storyboard without them:

```bash
grep -v '^Notes:' deck/storyboard.md > deck/storyboard-public.md
uv run python presentation/scripts/deck_html.py deck/storyboard-public.md --theme deck/theme.json -o deck/topic-share.html
```

Keep the notes in the copy you present from. The same public storyboard is the right source for the printable page and the PDF.

## 7. Accessibility and robustness

- The slides are real text: selectable, searchable with the browser's find, and readable by a screen reader. Nothing is a picture of text.
- Structure: the deck title is an `h1`, section titles and slide headlines are `h2`, each slide is a `section` with an aria-label.
- Charts carry `role="img"` and an aria-label from the chart title. Pictures carry the alt text written in the storyboard, so write alt text that states the finding.
- Navigation works from the keyboard alone, and the button bar is made of real buttons.
- Light and dark themes are both explicit: every colour comes from `theme.json`, so the deck does not change with the viewer's system setting.
- JavaScript: the static file shows every slide without it (its only script shrinks body text that would overflow). The interactive file needs it to show any slide at all; with scripts blocked it shows the dark background and the button bar and nothing else. When the viewer's machine may block scripts, hand over the static file or the PDF.

## 8. Limits

- No PowerPoint animations and no slide transitions. `--builds` is the only reveal, and it applies to bullets, big-number tiles and timeline steps.
- No presenter view on a second screen. The notes panel opens over the lower part of the same screen, so on a shared screen the audience sees it too. For a two-screen setup, present from the `.pptx`, or keep the notes on paper or a phone.
- Fonts must exist on the viewer's machine. The theme lists CSS stacks (`css_heading`, `css_body`) and the browser falls back through them, which changes line breaks a little. For a deck that must look identical everywhere, hand over the PDF.
- Very long tables and very long bullet lists still overflow the slide. The fit script only shrinks body text down to about 15 pt. Take the build warnings seriously and split the slide.
- Right to left decks are supported through the storyboard `language:` key, the same as in the `.pptx`.
- The `.pptx` stays the format for anyone who must edit slides. An HTML deck is edited by editing the storyboard and building again.

## 9. Worked example

```bash
# 1. the PowerPoint file, for people who edit slides
uv run --with python-pptx python presentation/scripts/deck_build.py deck/storyboard.md --theme deck/theme.json -o deck/growth.pptx
# 2. the interactive deck to present from, speaker notes included
uv run python presentation/scripts/deck_html.py deck/storyboard.md --theme deck/theme.json -o deck/growth.html
# 3. a copy of the storyboard without the speaker notes
grep -v '^Notes:' deck/storyboard.md > deck/storyboard-public.md
# 4. the printable page, from the copy without notes
uv run python presentation/scripts/deck_html.py deck/storyboard-public.md --theme deck/theme.json --mode static -o deck/growth-print.html
# 5. the PDF, no dialog
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=deck/growth.pdf deck/growth-print.html
```

Hand over `growth.html` to the speaker, `growth.pdf` to everyone who reads the deck instead of attending, and `growth.pptx` only to whoever must edit the slides. For a link the audience clicks through, run command 2 again on `storyboard-public.md` and share that file.
