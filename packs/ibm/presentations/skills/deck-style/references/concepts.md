# Style concepts

`scripts/style_preview.py` ships sixteen concepts. Each one is a complete look: canvas and accent colours, a six-colour chart palette, font names for the .pptx and CSS font stacks for HTML, point sizes, and layout traits (accent bar, title and section treatment, corner radius, bullet glyph, cards, ornament). The preview draws five of them on the user's own five slides through `deck_html.py`, the same engine that builds the HTML deck, so a card is the deck and not a mockup. The user picks one, `--choose <id>` writes it as `theme.json`, and every other script in the pack reads that file. This page says what each concept is for, how to pick five that genuinely differ, how to read the answer, and how to invent a concept when none of them fit.

## The sixteen concepts

| id | Name | Look | Best for | Not for |
|---|---|---|---|---|
| `swiss` | Swiss Minimal | white, black Helvetica type, one signal red, no bars, no cards | product and design audiences, keynotes, calm confident decks | dense finance reviews |
| `carbon` | IBM Carbon | white, Plex type, IBM blue and violet, column grid, cards | IBM and enterprise audiences, boards, status reviews, approvals | anything that must feel informal |
| `carbon-dark` | IBM Carbon Dark | Carbon g100 near-black, Plex type, blue and purple accents, column grid, cards | IBM audiences in a dark room, launches, platform and architecture reviews | printed handouts, bright rooms |
| `cyber-steel` | Cyber Steel | steel black canvas, amber and cyan, HUD brackets, mono headlines | developer conferences, security and platform demos, launches | printed handouts, bright rooms |
| `sketch` | Pencil Sketch | paper white, pencil hatching, handwritten headlines, ink accents | workshops, early concepts, design reviews, teaching | boards, regulators, final numbers |
| `geometric` | Geometric Poster | bone canvas, vermilion and cobalt shapes, geometric sans, big type | keynotes, campaigns, all-hands, back-row reading | dense data, long reading decks |
| `midnight` | Midnight Gold | near-black warm canvas, gold and muted teal, Georgia headlines, underline rule, cards | boards and executives in a dark room, investor evenings, awards and launch events | printed handouts, bright rooms, workshops |
| `editorial` | Editorial Serif | cream paper, Georgia headlines, oxblood and forest, underline rule | thought leadership, strategy narratives, research | developer or product demos |
| `boardroom` | Boardroom Blue | white, IBM blue, top bar, split title panel, cards | executives outside IBM, status reviews, approvals | anything that must feel creative |
| `data-studio` | Data Studio | pale grey canvas, teal and orange, mono numbers, tight sizes, grid | analysts, finance reviews, dashboards, reading decks | inspirational keynotes |
| `academic` | Academic Clean | white, slate text, muted blue, Cambria headlines, top bar | research results, lectures, technical reviews, training | sales pitches |
| `warm-human` | Warm and Human | warm off-white, terracotta and olive, round cards, bottom band | customer stories, HR and culture, community and non-profit | audits, technical reviews |
| `nature` | Earth and Nature | sand canvas, deep green and ochre, round corners, split title | sustainability, agriculture, wellbeing, ESG reporting | fintech, security |
| `startup-gradient` | Startup Gradient | white, violet and pink, big rounded cards, large KPIs | investor pitches, product marketing, launches | boards, regulators |
| `mono-ink` | Monochrome Ink | black on white only, Georgia headlines, thin rules, no cards | architecture, law, luxury, decks that should feel printed | decks that colour-code data |
| `playful` | Playful Pastel | pastel blocks, rounded bold type, sticker shapes, pill corners | education, workshops, internal events, consumer products | executives, investors |

Every shipped concept passes the contrast floors: text on background 4.5:1, muted text on background 4.5:1, accent on background 3:1, text on accent panels 4.5:1. The script computes the four ratios, prints them on each preview card and repeats them on the `--choose` line, so a change that breaks a floor is visible before the deck is built.

## The five defaults

`swiss`, `carbon`, `cyber-steel`, `sketch` and `geometric` are shown when neither `--audience` nor `--pick` is given. They differ on canvas, type, temperature and ornament at the same time, which is the point: the user is choosing a direction, not a shade.

### Swiss Minimal (`swiss`)

The empty one. No ornament, no cards, no accent bar: white paper, near-black Helvetica or Arial at 46 pt titles and 32 pt headlines, and a single signal red (`#F5200C`) used only where the eye must go, with electric blue (`#0038FF`) as the second colour. It fails immediately if the slides are crowded, which makes it a good pick when the deck should force the story to be short. Images: editorial photography, desaturated or black and white, one subject, plenty of empty space.

### IBM Carbon (`carbon`)

The corporate grid. Three hairline column rules run down every content slide, the title slide splits into an IBM blue panel and a text column, sections get a blue side band, and content sits on light grey cards. Type is IBM Plex Sans with IBM Plex Mono for code; the palette is IBM blue `#0F62FE` with violet, teal and magenta from Carbon for charts. Images: clean product and workplace photography, blue duotone, or Carbon icons in one weight.

### IBM Carbon Dark (`carbon-dark`)

The same corporate system on a dark canvas: Carbon g100 near-black `#161616`, layer grey `#262626` cards, IBM Plex Sans, blue `#4589FF` and purple `#BE95FF`, with the chart palette Carbon uses on dark. The title sits on the canvas under a short blue rule rather than in a blue panel, so the brightest thing on the slide stays the data. Sections keep the blue side band and content slides keep the column rules. Pick it when the room is dark or the deck is about a product, and `carbon` when it will be printed or read on a laptop. Images: dark product renders, glass and brushed metal, blue-lit machine rooms, Carbon icons in one weight; the IBM dark premium set (`pack-h`) is drawn for this look.

### Cyber Steel (`cyber-steel`)

The technical dark one. Steel black `#0F1216`, hazard amber `#FFC300` as the accent, cyan `#35D6FF` as the second colour, an amber bar down the left edge, and a HUD ornament: corner brackets on every slide and a two-digit slide tag in the mono face. Headlines are monospaced (JetBrains Mono or Consolas), body text is a plain sans, so the deck reads as a console rather than a slideshow. Images: night city and machine-room photography, wireframes, dark UI screenshots, amber and cyan glows.

### Pencil Sketch (`sketch`)

The unfinished one. Warm paper `#FBFAF6` under diagonal pencil hatching, an underline rule below each headline, slightly rounded corners and no cards, with ink blue `#2E5AAC` and red `#C0392B` as the two marks. Headlines render in a handwriting stack in HTML and in Trebuchet MS in the .pptx, so the same theme looks hand-drawn in the browser and merely informal in PowerPoint. Images: pencil and ink drawings, whiteboard photographs, hand-drawn diagrams, never polished stock photos.

### Geometric Poster (`geometric`)

The loud one. Bone canvas `#F7F4EF`, vermilion `#D93518` and cobalt `#1B4BD6`, Century Gothic or Futura, the largest sizes in the library (48 pt titles, 72 pt numbers), section slides flooded in the accent, and a Bauhaus shape composition on covers with a bottom edge bar on content slides. Text columns narrow to 58 percent on covers to leave the shapes room. Images: flat cut-out shapes, high-contrast photography on colour blocks, isometric illustration.

### Midnight Gold (`midnight`), the dark alternative

Not one of the five defaults: it is the second dark concept, for a dark room where the deck must feel elegant rather than technical. Warm near-black canvas `#14120F` with `#1F1C17` cards, warm gold `#C9A227` as the accent, muted teal `#6FA8A0` as the second colour, Georgia headlines over Calibri body text, an underline rule under each headline, a gold band on section slides, corners barely rounded, and no ornament at all. Titles are 44 pt, numbers 66 pt. Text reads at 16:1 on the canvas and the gold at 7.7:1, so it survives a weak projector. It is the dark option in the `executives`, `investors`, `customers`, `conference` and `research` presets, and the fallback when `cyber-steel` is excluded. Images: low-key photography, dark product shots, gold or amber light; never bright white images.

## A dark concept is always in the set

The library has two dark concepts, `cyber-steel` and `midnight`. The five defaults include `cyber-steel`, and every `--audience` preset includes one of the two.

The script also guarantees it. When `--pick` is not given and the set left after `--exclude` has no dark concept, the script keeps the first four ids and puts a dark one fifth: `cyber-steel`, or `midnight` when `cyber-steel` is excluded. The reason is that a set without a dark option hides a whole direction from the user. They never see the deck as it looks in a dark room, so they cannot ask for it by number, and a taste they would have chosen is simply missing from the page.

Two ways to get a light-only set on purpose: `--pick a,b,c,d,e`, which shows exactly the list you write, or `--exclude cyber-steel,midnight`, which leaves the script no fallback. Use either when the user has already ruled dark out, for a printed handout or a bright room.

## The lines the script prints

After writing the page, the script prints a numbered list of the concepts it drew:

```
wrote deck/style-preview.html: 5 concepts; open it in a browser and ask the user to choose.
Show the user these lines as they are; do not describe the concepts from memory:
  1 Swiss Minimal [swiss]: White space, black grotesk type, one bright signal colour
  ...
  5 Midnight Gold [midnight] (dark): Near-black canvas, warm gold, serif headlines, quiet luxury
```

Those lines are the source of truth for what you tell the user. Relay them word for word: the number, the name, the id, the `(dark)` mark and the tagline. The numbers and names match the cards in the page, so "3" means the same thing to you and to the user. Do not write your own description of a concept, do not rename one, and do not swap a name for a concept you remember. The library changes and the printed lines change with it; a description from memory goes stale and sends the user to the wrong card.

A `note:` line follows when a concept sits below a contrast floor. Only a `brand` concept built from a colour the user gave can do that, and when it happens, pass the line on before the user chooses.

## Ornaments

`layout.ornament` is the trait that gives a concept its character. Both renderers draw it: `deck_build.py` with shapes and connectors, `deck_html.py` with absolutely positioned elements inside `.orn`.

| Value | In the .pptx | In HTML | Used by |
|---|---|---|---|
| `none` | nothing | nothing | swiss, midnight, editorial, boardroom, academic, warm-human, nature, startup-gradient, mono-ink |
| `grid` | three rectangles 0.012 in wide in `line`, full height, at 25, 50 and 75 percent of the content width, content slides only | the same three rules as 1 px elements at 70 percent opacity | carbon, data-studio |
| `hud` | four corner brackets in `accent` (0.28 in arms) on every slide, plus a two-digit slide tag in the mono font at the top right of content slides | the same brackets and tag, plus a 64 px hairline grid painted over the slide background | cyber-steel |
| `hatch` | straight connectors at 135 degrees every 0.62 in, in `line` mixed 45 percent into `bg`, on every slide | one repeating linear gradient at 135 degrees, 22 px pitch, 50 percent opacity | sketch |
| `shapes` | covers and sections: a circle in `accent2` top right, a triangle in `chart[2]`, a quarter circle in `accent` bottom left; content slides: a small `accent2` dot top right and a full-width `accent` bar 0.1 in tall along the bottom | the same, plus a translucent vertical bar in `chart[3]` down the right edge of covers | geometric, playful |

`hud` and `shapes` also shorten the headline box (0.6 in and 0.9 in in the .pptx, 54 px and 86 px in HTML) so a long headline never runs into the decoration.

## Picking five that differ

Five concepts are only useful when they differ on real axes. Cover at least four of these.

| Axis | One end | Other end |
|---|---|---|
| Canvas | light (`swiss`, `carbon`, `boardroom`) | dark (`cyber-steel`, `midnight`) or tinted (`nature`, `warm-human`) |
| Type | sans (`swiss`, `carbon`) or mono (`cyber-steel`) | serif (`editorial`, `mono-ink`, `academic`, `midnight`) or handwriting (`sketch`) |
| Temperature | cool (`carbon`, `cyber-steel`, `boardroom`) | warm (`warm-human`, `editorial`, `geometric`, `midnight`) |
| Volume | quiet (`mono-ink`, `swiss`, `academic`) | loud (`geometric`, `startup-gradient`, `playful`) |
| Density | sparse, one statement (`geometric`, `swiss`) | dense, many numbers (`data-studio`, `carbon`) |
| Register | corporate (`carbon`, `boardroom`, `mono-ink`) | creative (`sketch`, `playful`, `startup-gradient`) |

Rules:

1. Always include one safe choice the audience expects (`carbon` for IBM, `boardroom` outside it, `academic` for research, `startup-gradient` for investors) and one braver than they expect. The brave one is chosen more often than people admit.
2. Never show two concepts that differ only in colour. `carbon` and `boardroom` are one idea; pick one. The same goes for `editorial` with `academic`, and `warm-human` with `nature`.
3. Show one dark concept, not two: `cyber-steel` when the subject is technical, `midnight` when the deck should feel expensive. The picker adds one for you when your set has none.
4. Drop what the brief excludes: no `playful` for a board, no `geometric` for a reading deck, no dark concept for a printed handout or a bright room, no photography concept when there are no photographs.
5. When the company colour is known, run `--brand-accent "#RRGGBB"`. A `brand` concept built on that colour is added first and the other four still cover the axes.
6. For Cyrillic, Hebrew or Arabic text add `--script cyrillic|hebrew|arabic`. Fonts without the glyphs are swapped for ones that have them, the CSS stack is swapped too, and the card says which font was replaced.

`--audience <name>` picks the five, in this order. Each preset stays close to the defaults and carries a dark concept.

| `--audience` | The five, in order |
|---|---|
| `executives` | carbon, swiss, midnight, geometric, editorial |
| `investors` | carbon, geometric, midnight, swiss, startup-gradient |
| `customers` | carbon, swiss, geometric, midnight, warm-human |
| `technical` | cyber-steel, carbon, swiss, sketch, data-studio |
| `team` | geometric, sketch, swiss, cyber-steel, warm-human |
| `conference` | geometric, cyber-steel, swiss, midnight, sketch |
| `training` | sketch, swiss, carbon, cyber-steel, playful |
| `research` | swiss, sketch, carbon, midnight, academic |

`--pick a,b,c,d,e` overrides the list and the dark guarantee, `--exclude a,b` removes ids from it, and `--brand-accent` puts `brand` first and keeps the first four of the rest (dropping `carbon`, whose blue would compete with the brand colour).

## Reading the user's answer

| The user says | Do |
|---|---|
| "3" or "Cyber Steel" | `--choose cyber-steel` |
| "2, but with the colours of 4" | `--choose carbon --accent <accent of 4> --accent2 <accent2 of 4>`, then say what you kept and what you swapped |
| "more corporate" | move one step toward `carbon`, `boardroom` or `mono-ink`; show two concepts, not five |
| "warmer", "friendlier" | `warm-human`, `nature`, or `editorial`; or keep the concept and pass `--accent` from a warm hue |
| "our brand is green" | `--brand-accent "#RRGGBB"` and `--choose brand`, or `--choose nature --accent "#RRGGBB"` |
| "darker" | `--choose midnight` for an elegant deck, `--choose cyber-steel` for a technical one; or any concept with `--bg "#101418" --text "#F2F4F8"`, then read the contrast line the command prints |
| "more premium", "more expensive" | `--choose midnight` in a dark room, `--choose mono-ink` on paper |
| "bigger text" | keep the concept, raise `sizes.body` to 22 and `sizes.headline` to 34 in `theme.json`, and cut words per slide |
| "I like none of them" | ask which deck they admire (a company, a talk), build a `brand` theme from its two colours and its type, and show two, not five |

Record the chosen id and the user's own words in `deck/brief.md`.

## Inventing a concept

A hand-written concept cannot be added to the preview page, so edit a copy of the nearest `theme.json` (every key is in `theme-format.md`) rather than starting from an empty file.

1. Canvas: set `bg` and `text` at 4.5:1 or better, then `surface` (cards, callouts, table bands) one step from `bg`, `muted` at 4.5:1 against `bg`, and `line` for rules and gridlines.
2. Accent: one `accent` that reads at 3:1 or more on the canvas, an `on_accent` (white or near-black) that reads at 4.5:1 or more on the accent, and an `accent2` for the second series, the target line and the negative case.
3. Chart palette: six colours in `colors.chart`, the accent first, then `accent2`, then two steps of them and two greys. Every colour must be separable next to its neighbour, not just against the background.
4. Fonts: pick from the Office-safe list in `theme-format.md` for `heading`, `body` and `mono`, then write the matching `css_heading`, `css_body` and `css_mono` stacks for HTML. The two may differ on purpose, as `sketch` does.
5. Traits in `layout`: `accent_bar`, `title_style`, `section_style`, `corner`, `cards`, `bullet`, and `ornament` (`none`, `grid`, `hud`, `hatch`, `shapes`). Pick the ornament last and only when it says something about the subject; `none` is a real answer.

Check it in both outputs before showing anything to the user, because the two renderers make different mistakes:

```bash
uv run --with python-pptx python ../presentation/scripts/deck_build.py deck/storyboard.md --theme deck/theme.json -o deck/check.pptx
python3 ../presentation/scripts/deck_html.py deck/storyboard.md --theme deck/theme.json -o deck/check.html
```

Look at the title slide, one bullets slide, one chart, one big-number slide and one section divider. In the .pptx watch for text that shrank to its floor and for fonts PowerPoint substituted; in HTML watch for text that overflowed, since the browser does not shrink anything.
