---
name: deck-style
description: Choose the visual style of a presentation with the user instead of guessing. Generates an HTML preview page with five conceptually different style concepts drawn on the deck's own five slides by the same renderer that builds the deck, so the preview is the deck, and turns the user's answer into a theme.json that the PowerPoint builder, the HTML deck, the chart renderer and the image scripts all read. Fifteen built-in concepts from minimal Swiss and IBM Carbon to a cyber steel HUD, pencil sketch, geometric poster and a dark midnight gold; each with its own ornament, every set of five keeps a dark option, contrast checked, brand colour and Cyrillic, Hebrew or Arabic fonts supported. Use when the user asks how the deck should look, wants to see options or a mockup before slides are built, mentions colours, fonts, corporate branding or a template, or says "выбери стиль", "покажи варианты оформления", "не нравится дизайн".
---

# deck-style

Output: `deck/style-preview.html` (five concepts for the user to choose from) and `deck/theme.json` (the chosen one). The user chooses; you do not pick the style silently unless they asked for speed.

## 1. Generate the preview with the deck's own words

```bash
uv run --with pillow python scripts/style_preview.py \
  --title "Subscriptions now carry the business" --subtitle "FY2026 mid-year review" \
  --author "Maria Startseva" --date "September 2026" \
  --headline "Revenue grew 18 percent, and subscriptions did the work" \
  --bullets "Total revenue 12.4 M, up 18 percent;Subscriptions are 61 percent of revenue;Services fell 9 percent as planned" \
  --takeaway "The mix shift we planned for 2027 arrived a year early." \
  --numbers "18%|Revenue growth|year on year;61%|Subscription share|of total revenue;2x|Enterprise customers|52 to 104" \
  --chart-title "Every quarter of 2026 beat the same quarter of 2025" --section "What it cost us" \
  -o deck/style-preview.html
```

Real text from the storyboard, never the defaults: the user judges the style on their own slides. Each card shows the title slide large and the bullets, chart, big-number and section slides as thumbnails; clicking one enlarges it. The page is self-contained, so it opens from disk with no server.

Without `--audience` the five defaults are deliberately far apart: `swiss` (white, black grotesk, one bright signal colour), `carbon` (IBM Carbon: strict column grid, Plex, IBM blue), `cyber-steel` (steel black, hazard amber and cyan, HUD brackets, mono headlines), `sketch` (paper, pencil hatching, handwritten headlines) and `geometric` (Bauhaus circles and triangles, cobalt and vermilion). `midnight` (near-black, warm gold, serif) is the second dark concept, for a board or an evening event.

Run it without `--audience` unless the user named the audience; the default five are the concepts above. `--audience executives|investors|customers|technical|team|conference|training|research` reorders the set for a room the user has named, and every preset keeps one dark concept so that direction is never hidden.

Other options: `--pick a,b,c,d,e` and `--exclude` override; `--brand-accent "#RRGGBB"` adds a concept built on the company colour and puts it first; `--script cyrillic|hebrew|arabic` swaps fonts that lack the glyphs; `--rtl` previews right-to-left; `--list` prints all sixteen concepts. `references/concepts.md` says what each concept is for and how to keep the five genuinely different.

## 2. Ask, and read the answer

Open the file for the user (`open deck/style-preview.html` on macOS, `xdg-open` on Linux, `start` on Windows) or give them the path. Under every concept card the page repeats the title slide with each picture set from the library that suits that style (abstract vector, black and white photo art, dark technology, people at work, paper craft, desk objects), plus the options "none" and "generated". Ask one question with two parts: which concept, and which picture set, both by number or name, and what to change. Paste the numbered lines the command printed; they are the real names and descriptions in the page, including the picture sets per concept. Do not write your own descriptions, do not translate a concept into a different one, and never pick the picture set yourself: the same style looks corporate with desk objects and playful with paper craft, and that is the user's call. The page tells them they can combine ("2 with the colours of 4"). Wait for the answer.

The table in `references/concepts.md` maps common answers ("more corporate", "warmer", "our brand is green", "I like none of them") to the concept and the overrides to use.

## 3. Write the theme

```bash
uv run --with pillow python scripts/style_preview.py --choose editorial --pictures pack-b -o deck/theme.json
uv run --with pillow python scripts/style_preview.py --choose editorial --pictures none --accent "#0F62FE" --heading-font "IBM Plex Sans" -o deck/theme.json
```

`--pictures` records the picture set the user chose (`pack-a` to `pack-h`, `none`, or `generated`); `library --for-theme deck/theme.json` then hands out that set's pictures, and refuses to guess when the key is missing.

Overrides: `--accent`, `--accent2`, `--bg`, `--text`, `--heading-font`, `--body-font`, `--align center`, `--name`. The command prints the contrast ratios and says when one is below the floor (text on background 4.5:1, accent on background 3:1, text on accent panels 4.5:1); fix it by darkening or lightening the accent rather than shipping grey on white.

`references/theme-format.md` documents every key, the fonts that ship with Office on Windows and macOS, which of them cover Cyrillic, Hebrew and Arabic, and how to hand-edit a theme.

## 4. Use it everywhere

`deck_build.py --theme deck/theme.json` builds the PowerPoint file, `deck_html.py --theme deck/theme.json` the HTML deck (interactive and printable), `chart_render.py --theme deck/theme.json` renders charts in the same palette, `visual_assets.py --theme deck/theme.json` generates backdrops and treats photos in it. One theme file, one look, three formats.

The preview page is drawn by the HTML deck renderer, so the slides on the cards are the real slides. The PowerPoint file uses the same colours, sizes, layouts and ornaments; the difference is fonts, which PowerPoint substitutes when a family is missing on the machine that opens the file.

## 5. When the deck must sit on a corporate template

This pack draws its own layouts, so a corporate `.potx` is a different route: keep the storyboard and build it with the office-docs `pptx_build.py --template brand.pptx` (bullets, charts and pictures survive; `big-number`, `timeline`, `quote` and `two-column` fall back to bullets). Say that before choosing. When only the colours must match, `--brand-accent` plus `--heading-font` is usually enough and keeps the layouts.

## 6. Report

The concept chosen, in the user's own words, the overrides applied, the contrast result, and where `theme.json` is. Record it in `deck/brief.md`.
