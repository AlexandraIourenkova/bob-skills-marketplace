---
name: deck-images
description: Pictures for a presentation. Bundled Carbon icons and pattern tiles, generated backdrops, prompts for images the user makes once and reuses, plus where to get photographs legally and how to place everything so the deck looks designed. Covers open image sets (public domain, Creative Commons, Unsplash and similar, icon and illustration sets) with their licences and the credits record, prompts for image generators that match the deck's theme, and offline scripts that make on-theme abstract backdrops in SVG or PNG for title and section slides, apply one consistent treatment to the user's photos (crop, duotone, tint, scrim) and produce labelled placeholders for pictures that have not arrived yet. Use when a deck needs photos, illustrations, icons or a background, when the user asks where to find images, whether an image may be used, how to generate one, or says "нужны картинки", "найди изображения", "сгенерируй фон".
---

# deck-images

The skill never downloads pictures. It generates what can be generated offline, gives the user search terms and sources for the rest, and records the credits.

## 1. Decide what each slide needs

Go through the storyboard and mark, per slide: a full-bleed photo, a picture next to the text, an icon row, a diagram, an abstract backdrop, or nothing. Most slides need nothing; a picture that decorates rather than shows something costs attention. `references/treatment.md` has the placement patterns with sizes for the 13.33 x 7.5 in slide.

## 2. Generate what you can, offline

```bash
uv run --with pillow python scripts/visual_assets.py backdrop --theme deck/theme.json --pattern mesh -o deck/images/backdrop.svg
uv run --with pillow python scripts/visual_assets.py backdrop --theme deck/theme.json --pattern mesh -o deck/images/backdrop.png
uv run --with pillow python scripts/visual_assets.py treat photo.jpg --theme deck/theme.json --crop 16:9 --duotone --scrim bottom --width 1920 -o deck/images/04-team.jpg
uv run --with pillow python scripts/visual_assets.py placeholder --theme deck/theme.json --text "Photo: the onboarding team at a customer site" -o deck/images/06-team.png
```

- **A generated backdrop is the third option** beside a library picture and no picture at all, and the style preview shows it next to the packs: strict `grid`, diagonal `bands`, `contours`, `waves` and soft `mesh` drawn from the theme's own colours, so nothing clashes and there is no licence to record. The user picks it on the preview page, it lands in `theme.json` as `pictures: generated:grid`, and `library --for-theme` prints the two commands: the title at full strength, the sections quieter (`--intensity 0.55`) with a different seed.
- `backdrop`: an abstract on-theme background for the title and section slides, generated for every deck unless the user brings a photograph. Patterns: `gradient`, `mesh`, `waves`, `noise` and `contours` are quiet enough to sit under text; `shapes`, `arcs`, `bands`, `dots` and `grid` are graphic and want space. `--seed` gives another variation, `--intensity 0.5` a calmer one, `--format svg` or an `.svg` output writes vector art of a few kilobytes for the HTML deck. Write both formats with the same name and pattern (`backdrop.svg` and `backdrop.png`, since the .pptx cannot place SVG), then set `backdrop: images/backdrop.svg` and `backdrop_scrim: none` in the front matter. `backdrop_scrim: dark` is the default and is what a photograph needs.
- `treat`: one treatment for every photo in the deck (`--crop`, `--focus`, `--width`, `--duotone`, `--tint`, `--grayscale`, `--scrim bottom`, `--rounded`). Mixing treatments is the clearest sign of an unplanned deck.
- `placeholder`: a labelled stand-in so the layout can be reviewed while the real picture is pending.

## 3. Icons and textures ship with the skill

Nothing to search and no licence to chase:

```bash
uv run --with pillow python scripts/visual_assets.py icon --find growth
uv run --with pillow python scripts/visual_assets.py icon rocket --theme deck/theme.json --color accent -o deck/images/icons/rocket.svg
uv run --with pillow python scripts/visual_assets.py pattern circuit --theme deck/theme.json --strength 0.1 -o deck/images/texture.svg
```

- **92 Carbon icons** in `assets/icons`, Apache-2.0, one licence file for the whole set, grouped as data, business, people, status, security, technology, direction and actions. `icon --list` prints the groups, `--find <word>` searches names and keywords, `--color` takes a theme role or a hex colour. One set per deck, one size, always with a label; never one icon per bullet.
- **12 tileable patterns** in `assets/patterns`, written for this pack. `pattern --list` describes them. Keep `--strength` between 0.06 and 0.12 behind text; a texture that competes with the words is a mistake, not a decoration.

Icons and patterns are SVG for the HTML deck. For the .pptx the builder uses the bundled PNG glyphs (`assets/icons/png`, black on transparent), recolours them in the theme accent and saves them next to the deck, so an `icons` slide looks the same in both formats. A pattern texture in the .pptx needs a PNG backdrop instead (`visual_assets.py backdrop`).

## 4. The picture library ships with the skill

`assets/library` holds 72 pictures in seven packs, made by the pack authors from the prompts in `references/library.md`: abstract vector (pack-a), black and white photo art (pack-b), dark technology (pack-c), people at work without faces (pack-d), paper craft (pack-e), desk objects (pack-f) and IBM-style isometric (pack-g). No search, no licence to chase; `assets/library/NOTICE` and `manifest.json` carry the provenance and the keywords.

```bash
uv run --with pillow python scripts/visual_assets.py library --for-theme deck/theme.json
uv run --with pillow python scripts/visual_assets.py library --find "security risk"
uv run --with pillow python scripts/visual_assets.py library --pick pack-b/road
```

Titles over a picture always sit on the left: the library pictures carry their subject on the right. `--for-theme` reads the picture set the user chose (`pictures` in theme.json, written by `style_preview.py --choose ... --pictures`) and names one picture for the title, a list for the sections (one per chapter, or one neutral picture to repeat), the scrim and the text side; when the theme carries no choice and several sets suit the style, it lists them and tells you to ask instead of guessing; `--find` searches names and keywords; `--pick` prints the path for `treat`. One picture, one place: the title picture is never reused, a section picture may repeat when it is neutral, a content picture is used once. Treat straight into the deck: crop to 16:9, JPEG (`-o deck/images/<name>.jpg`, about 200 KB), `--duotone` when the picture's colours fight the theme, `--scrim bottom` for a full-bleed picture that carries a headline. The user's own additions live in `~/Pictures/deck-library` with the same layout (`--dir` for another place) and are listed after the bundled ones. Record "AI-generated image, library <pack>/<name>" in the speaker notes of the slide.

## 5. Real pictures: tell the user where and how

`references/sources.md` lists open sources with their licences: public domain and Creative Commons collections, Unsplash, Pexels, Pixabay, museum and agency archives, illustration sets, icon sets (one set per deck, one weight), patterns, maps. It also has the licence cheat sheet (what may be used commercially, what needs attribution, what forbids modification) and the rules for logos, trademarks, screenshots and identifiable people.

For each missing picture give the user: what the slide needs in one sentence, three search terms, one or two sources with the licence to expect, and the file name to save it as (`deck/images/<slide>-<subject>.jpg`). The company brand portal comes first when there is one.

## 6. Generated pictures

`references/library.md` is the shorter route: three ready packs of prompts (abstract vector, black and white photo art, dark technology) that the user generates once and reuses across decks, with the folder convention and the rights in three lines. `references/prompts.md` has the prompt formula (subject, setting, style family, composition with negative space for the text, lighting, the theme palette in words, mood, no text or logos), a style family for each theme concept, a library of ready prompts by slide role, and the consistency method (one style sentence reused across the deck). Ask the user whether generated images are allowed for this deck, note "AI-generated image" in the speaker notes, and keep the prompt in the credits file. No likenesses of real people, no brand logos, no generated charts.

## 7. Record the credits

`deck/images/credits.md`, one row per picture: file, what it shows, author, source, licence, modifications, and the prompt for generated ones. Attribution for CC BY goes on a credits slide in the appendix or in the caption; the notes carry the rest. A picture whose licence you cannot establish does not go into the deck.

## 8. Check before building

`references/treatment.md` ends with a ten-item review: licence recorded, one treatment, resolution (1920 px for full-bleed, 1200 px for half), cropped not stretched, text legible over scrims, alt text written in the `![alt](...)` line, no orphan icons, file sizes under about 1 MB each. Report the pictures still pending with their search terms or prompts.
