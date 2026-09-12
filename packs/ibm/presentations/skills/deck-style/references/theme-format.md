# Theme format (theme.json)

`theme.json` is written by `style_preview.py --choose <id>` and read by `deck_build.py` (the .pptx), `deck_html.py` (the interactive and printable HTML), `chart_render.py` (standalone chart images) and `visual_assets.py` (backdrops and photo treatments). One file, one look, four outputs. Edit it by hand to tune a colour, a font or a size: unknown keys are ignored, and missing keys fall back to the built-in Boardroom Blue theme through a deep merge, so a partial file is valid. `deck_build.py` refuses to start when `bg`, `text` or `accent` is not a hex colour.

## A complete theme

This is the output of `style_preview.py --choose carbon -o theme.json`, with the colour block folded onto fewer lines.

```json
{
  "id": "carbon",
  "name": "IBM Carbon",
  "tagline": "Corporate grid, Plex type, IBM blue with bright Carbon accents",
  "best_for": "IBM and enterprise audiences, boards, status reviews, proposals that need approval",
  "mood": "strict, engineered, credible",
  "dark": false,
  "colors": {
    "bg": "#FFFFFF", "surface": "#F4F4F4", "text": "#161616", "muted": "#525252",
    "accent": "#0F62FE", "accent2": "#8A3FFC", "line": "#C6C6C6", "on_accent": "#FFFFFF",
    "chart": ["#0F62FE", "#8A3FFC", "#007D79", "#EE5396", "#FA4D56", "#4589FF"]
  },
  "fonts": {
    "heading": "IBM Plex Sans", "body": "IBM Plex Sans", "mono": "IBM Plex Mono",
    "css_heading": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif",
    "css_body": "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif",
    "css_mono": "'IBM Plex Mono', Consolas, ui-monospace, monospace"
  },
  "sizes": {"title": 42, "headline": 30, "body": 20, "small": 12, "number": 62},
  "layout": {
    "align": "left", "accent_bar": "none", "title_style": "split", "section_style": "band",
    "corner": 0, "bullet": "—", "cards": true, "ornament": "grid"
  },
  "image": "clean product and workplace photography, blue duotone, or Carbon icons in one weight",
  "contrast": {
    "text on background": 18.1,
    "muted text on background": 7.8,
    "accent on background (large text, bars)": 5.0,
    "text on accent (title panels)": 5.0
  }
}
```

## Keys

Short names in the second column: `pptx` is `deck_build.py`, `html` is `deck_html.py`, `charts` is `chart_render.py`, `images` is `visual_assets.py`, `preview` is `style_preview.py`.

| Key | Used by | Meaning |
|---|---|---|
| `id` | preview | the concept `--choose` wrote; kept for the record, no renderer reads it |
| `name`, `tagline`, `best_for`, `mood` | preview | free text shown on the preview card; `--name` overrides `name` |
| `pictures` | `visual_assets.py library --for-theme` | the picture set the user chose on the preview page: `pack-a` to `pack-f`, `none` or `generated`; written by `style_preview.py --choose --pictures`; without it the library command lists the sets that suit the style and asks |
| `dark` | none | metadata saying the canvas is dark, for you and for image briefs; `visual_assets.py backdrop` decides for itself from `bg` and takes `--dark` or `--light` |
| `colors.bg` | pptx, html, charts, images | slide background, and the fill behind chart labels |
| `colors.surface` | pptx, html, charts, images | cards, callout background, table bands; one step from `bg` |
| `colors.text` | pptx, html, charts, images | main text; at least 4.5:1 against `bg` |
| `colors.muted` | pptx, html, charts, images | footer, source, details, axis labels; at least 4.5:1 against `bg` |
| `colors.accent` | pptx, html, charts, images | bars, bullets, big numbers, rules, title panels, the highlighted series; at least 3:1 against `bg` |
| `colors.accent2` | pptx, html, charts, images | the second colour: second series, target lines, the negative case, the ornament circle |
| `colors.line` | pptx, html, charts, images | gridlines, table rules, the `grid` and `hatch` ornaments |
| `colors.on_accent` | pptx, html | text on accent panels: split title, section slide, table header row, timeline dots; at least 4.5:1 against `accent` |
| `colors.chart` | pptx, html, charts | six series colours in order; `chart[0]` is normally the accent, and `chart[2]` and `chart[3]` also colour the `shapes` ornament |
| `fonts.heading`, `fonts.body`, `fonts.mono` | pptx, charts | the font names written into the .pptx; `charts` uses `body` only. Headings, big numbers, quotes and callouts take `heading`; code and the HUD slide tag take `mono` |
| `fonts.number` | preview | an optional face for figures; `--script` swaps it, but both renderers currently draw big numbers in `heading` |
| `fonts.css_heading`, `fonts.css_body`, `fonts.css_mono` | html, preview | CSS font stacks for HTML; they may differ from the .pptx names on purpose, as `sketch` does with a handwriting stack |
| `fonts.replaced` | preview | written by `--script` to record which font was swapped, and shown on the card |
| `sizes.title` | pptx, html | title slide, in points; closing slides use `title - 4`, section titles `title - 2`, the `statement` layout `title` |
| `sizes.headline` | pptx, html | the headline on content slides, and the quote text |
| `sizes.body` | pptx, html | top-level bullets and paragraphs; nested levels step down 10 percent each |
| `sizes.small` | pptx, html | footer, page number, source line; the kicker headline is `small + 2` |
| `sizes.number` | pptx, html | big-number tiles at two tiles; one tile adds 12, three subtract 8, four subtract 14. The section slide label is `number * 0.6` |
| `layout.align` | pptx, html | `left` or `center`; right-to-left decks mirror the whole layout automatically |
| `layout.accent_bar` | pptx, html | `top` (thin bar across the top), `left` (bar down the edge, content shifts in), `underline` (short rule under the headline), `none` |
| `layout.title_style` | pptx, html | `plain`, `split` (accent panel with the title, text beside it), `band` (accent band along the bottom), `full` (whole slide in the accent). Closing slides use it too |
| `layout.section_style` | pptx, html | `accent` (whole slide in the accent), `band` (accent band down the left), `plain` |
| `layout.corner` | pptx, html | corner radius of cards and callouts as a fraction: 0 sharp, 0.06 slight, 0.25 pill-like |
| `layout.cards` | pptx, html | draw big-number tiles and two-column columns on `surface` cards (`true`) or on the bare canvas (`false`) |
| `layout.bullet` | pptx, html | the bullet glyph, for example `•`, `–`, `▪`, `›`, `■`, `●` or an em dash `—` |
| `layout.ornament` | pptx, html | `none`, `grid`, `hud`, `hatch` or `shapes`; `concepts.md` says what each one draws in both renderers |
| `image` | none | one line of guidance for deck-images and for picture searches; no script parses it |
| `contrast` | preview | the four ratios at the moment the file was written; recompute after editing a colour, do not hand-edit the numbers |

## Fonts

The .pptx does not embed fonts, so a deck should use fonts that exist where it will be opened. Present on Windows and macOS with Office installed: Arial, Arial Black, Arial Rounded MT Bold, Calibri, Cambria, Candara, Century Gothic, Consolas, Constantia, Corbel, Courier New, Franklin Gothic, Georgia, Gill Sans MT, Impact, Tahoma, Times New Roman, Trebuchet MS, Verdana. Windows only: Segoe UI. macOS only: Helvetica Neue, Avenir, Menlo.

Company fonts are a deliberate exception. `carbon` names IBM Plex Sans and IBM Plex Mono for the .pptx: correct on machines where Plex is installed, and silently substituted by PowerPoint everywhere else, which shifts line breaks and can push text past its box. Ship Plex only when the audience has it, or swap `fonts.heading` and `fonts.body` for Arial or Segoe UI and keep the Plex stack in `css_heading` for the HTML deck.

Script coverage, which is what `--script` enforces:

| Script | Fonts that cover it |
|---|---|
| Cyrillic | Arial, Arial Black, Calibri, Cambria, Century Gothic, Consolas, Courier New, Georgia, Impact, IBM Plex Sans, IBM Plex Mono, Palatino Linotype, Segoe UI, Tahoma, Times New Roman, Trebuchet MS, Verdana |
| Hebrew | Arial, Calibri, Courier New, Segoe UI, Tahoma, Times New Roman |
| Arabic | Arial, Calibri, Courier New, Segoe UI, Tahoma, Times New Roman |

`--script` replaces any other font with a safe serif, sans or mono equivalent, records the swap in `fonts.replaced`, and points `css_heading` and `css_body` at a stack for that script (PT Sans for Cyrillic, Arial Hebrew, Geeza Pro for Arabic). HTML always uses the `css_*` stacks and falls back inside the browser, so the preview can look right on a machine where the .pptx font is missing. That is why the two must be checked separately.

## Sizes that read

Headlines 28 to 34 pt, body 18 to 22 pt (24 in a large room), nothing the audience must read below 12 pt. `deck_build.py` estimates whether text fits and shrinks it one point at a time down to a floor, then warns that it overflowed. `deck_html.py` shrinks the same way in the browser, down to 15 pt body and 22 pt headline, and a slide that still does not fit overflows visibly. Both are symptoms of too many words, not of a floor set too high.

| Text | Starts at | Shrinks to |
|---|---|---|
| Headline | `headline` | 22 pt |
| Title and closing title | `title`, `title - 4` | 26 pt |
| Section title, label, subtitle | `title - 2`, `number * 0.6`, `body` | 26 pt, 24 pt, 16 pt |
| Cover subtitle | `body + 2` | 16 pt |
| Bullets and paragraphs | `body` | 15 pt |
| Two-column body, timeline step, caption | `body - 2` | 14 pt, 12 pt, 12 pt |
| Big number, its label | `number` scaled by tile count, `body` | 28 pt, 14 pt |
| Quote, attribution | `headline`, `body` | 20 pt, 14 pt |
| Statement, its paragraphs | `title`, `body + 2` | 28 pt, 16 pt |
| Takeaway callout | `body` | 14 pt |
| Source line | `small` | `small - 2` |
| Footer, page number, kicker | `small`, `small + 2` | no shrink |
| Table cells | 16 pt up to five rows, 14 pt up to seven, 12 pt beyond | no shrink |

## Checking a hand-edited theme

Build both outputs from the same storyboard and open them side by side.

```bash
uv run --with python-pptx python ../presentation/scripts/deck_build.py deck/storyboard.md --theme deck/theme.json -o deck/check.pptx
python3 ../presentation/scripts/deck_html.py deck/storyboard.md --theme deck/theme.json -o deck/check.html
```

Read the warnings on stderr first: they name the slide and say what shrank or overflowed. In the .pptx check that no font was substituted and that the accent panels are still readable; in HTML check the same slides for text running past its box. To recompute the contrast ratios after changing a colour, run `style_preview.py --choose <id> --accent "#RRGGBB" -o deck/theme.json` and read the line it prints: it names any ratio below the floor. For a visual comparison against the nearest shipped concept, `style_preview.py --pick <id> --title "..." -o check.html` draws it on the same five slides.
