# Image treatment and placement

This file says how pictures go on slides so the deck looks designed rather than decorated: one treatment for the whole deck, the placement patterns the builder supports with their sizes, the composition and file rules, and a review checklist. Read it after the pictures are in `images/` (sourced per sources.md or generated per prompts.md) and before you write the `![alt](images/...)` lines in the storyboard. Read the checklist again before the deck ships.

## One treatment per deck

Mixing treatments is the most common tell of an unplanned deck: one duotone photo, one full-colour photo and one grey screenshot on consecutive slides. Choose one treatment when the theme is chosen and apply it to every photograph with `visual_assets.py treat`. Screenshots and flat illustrations get no colour treatment (they are cropped and framed, not tinted), which is one more reason not to put them next to photos.

| Treatment | What it does | Choose when | Themes it suits |
|---|---|---|---|
| none | Crop and resize only | The photos come from one shoot with the same light, or the brand portal set is already consistent | editorial, warm-human, nature, boardroom with brand photos |
| duotone | Maps shadows to `colors.accent2` or a dark tone and highlights to `colors.accent` or `colors.bg` | Photos from many sources must look like one set; the theme is strong in colour | cyber-steel, midnight, startup-gradient, geometric, data-studio, swiss (red on black) |
| tint | Full colour with a wash of the accent at low opacity | The photos are close in mood but not in colour temperature | boardroom, academic, playful, warm-human |
| grayscale plus one accent | Photos in black and white; the accent lives in the accent bar, the headline and the callouts, not in the photo | Editorial and minimal themes; screenshots and photos share a deck | mono-ink, swiss, editorial, academic |

Duotone and grayscale hide the difference between a 2010 stock photo and a 2026 phone picture. Tint does not; use it only when the originals are already close.

Backdrops and full-bleed pictures get a scrim from the builder: a dark band 2.6 in tall behind the headline on an image slide, and a dark veil of about half opacity over the whole backdrop on title and section slides. The scrim is applied in the deck, so do not bake one into the file with `treat` as well, unless the picture is so bright that the builder's band is not enough.

## Placement patterns

The slide is 13.33 by 7.5 in. Content sits inside 0.6 in margins (0.85 in on the left when the theme has a left accent bar), which gives a content area about 12.1 in wide, with 0.3 in gaps between boxes. The builder fits contained pictures with "contain": the picture keeps its ratio inside its box. Crop the picture to the box ratio first if it should fill the box.

| Pattern | Storyboard | Size on the slide | Rules |
|---|---|---|---|
| Full-bleed with scrim | `## Headline` then one `![alt](images/x.jpg)` and nothing else (layout `image`) | 13.33 x 7.5 in, "cover" crop, scrim 2.6 in tall at the bottom with the headline in it | Keep the subject in the upper two thirds. The `Source:` line goes into the band. A `Takeaway:` is not drawn here; move it to the notes. 16:9 file, 1920 px or wider. |
| Picture beside bullets | `## Headline`, bullets, one `![alt](...)` (layout `bullets`) | Text takes 42 percent of the content width on the left; the picture gets the remaining 58 percent minus the gap: about 6.7 in wide by 4.8 in tall, on the right (on the left in right-to-left decks) | Crop to about 4:3 or 3:2 so the picture fills the box height. Subject faces left toward the text. Two pictures stack vertically in that column; three are too many. |
| Two-up or three-up grid | `## Headline` and two or three `![alt](...)` lines, optional caption paragraph (layout `image`) | One row: cells about 5.9 in wide for two, 3.8 in wide for three, about 4.8 in tall (4.0 in with a caption) | Same ratio for every cell; crop all pictures to it. Same treatment, same scale of subject. Pair a before and an after, or show three options. |
| Four-up grid | Four `![alt](...)` lines | Two rows of two: cells about 5.9 by 2.3 in | Crop to a wide ratio, about 2.5:1, or accept letterboxing. Four is the limit. |
| Section backdrop | `backdrop: images/backdrop.png` in the front matter, or `--backdrop` on the build | Full slide behind the title, the sections and the closing, "cover" crop, dark veil over the whole picture | One picture for all sections. Low detail, no faces, even density. The title sits over it, so nothing important anywhere. `visual_assets.py backdrop` makes a safe one. |
| Icon row | `layout: two-column` with three `###` columns; each column has its label as the title, one line of text and one `![alt](icons/x.png)` | Each column about 3.8 in wide; the icon box takes the lower part of the column | Export each icon on a transparent canvas of the box ratio with the glyph at about a fifth of the canvas width, so the contain fit renders it at 0.6 to 0.8 in. Check the built slide. |
| Screenshot | `![alt](images/x.png)` beside bullets or on its own | Same boxes as above | Crop to the content. A thin border or a soft shadow from your image editor, rounded corners with `treat` when the theme uses rounded cards. No fake device or browser frames unless the brand guidelines use them. |

### Storyboard lines for each pattern

```markdown
---
title: Field maintenance costs
backdrop: images/00-backdrop.png
---

## Turbine downtime fell by a third
![Engineer checking a wind turbine gearbox; the slide is about field maintenance costs.](images/03-turbine.jpg)
Source: Photo by Jane Doe via Unsplash

## Three levers cut the downtime
- Predictive alerts from the sensor feed
- Spare parts staged at the regional depot
- One crew per cluster instead of one per site
![Technician on a turbine platform, facing the bullets.](images/04-crew.jpg)

## Before and after the depot change
![Depot shelves half empty, 2025.](images/05-depot-before.jpg)
![Depot shelves staged by cluster, 2026.](images/05-depot-after.jpg)
The same depot, twelve months apart.

## What each crew gets
### Alerts
One feed, one dashboard.
![Alerts](icons/alerts.png)
### Parts
Staged by cluster.
![Parts](icons/parts.png)
### Coverage
One crew per cluster.
![Coverage](icons/coverage.png)

## Alerts reach the crew app in under a minute
- Push notification within 30 seconds
- One tap to acknowledge
![Crew app alert screen with the acknowledge button highlighted.](images/08-crew-app.png)
```

The first `##` slide is full-bleed with the `Source:` line in the band. The second puts the picture beside the bullets. The third is a two-up grid with a caption paragraph. The fourth is an icon row on three columns. The fifth is a screenshot beside bullets.

## Workflow

1. Save the originals in `images/originals/` under the final names.
2. Run `visual_assets.py treat` on each: crop to the slot ratio, the deck's one treatment, resize to the slot's minimum width.
3. Write the `![alt](images/...)` line with the final alt text and, for CC BY pictures, the `Source:` line.
4. Build the deck. Look at every picture slide at full size and as a thumbnail.
5. Fix in the file, not in PowerPoint: a crop or a tint changed by hand in the deck is lost at the next build.
6. Write the credits row (sources.md) and, for generated pictures, the prompt log row (prompts.md).

## Light and dark themes

The theme file says which it is: `dark: false` or `dark: true`.

| | Light theme | Dark theme |
|---|---|---|
| Photo treatment | Tint, or grayscale plus accent; duotone reads loud on white | Duotone from a dark tone to the accent, or none with a darker crop |
| Screenshot edge | 1 px line in `colors.line` | No line; a soft shadow, or a 1 px line one step lighter than the background |
| Screenshot theme | The product's light mode | The product's dark mode |
| Icons | `colors.accent` or `colors.text` | `colors.accent` or white |
| Illustrations | Full palette | The set's dark variant, or none; most flat sets are drawn for white |
| Backdrop | Pale `backdrop` mesh or gradient; the builder's veil does the rest | Deep `backdrop` mesh, low contrast so the title stays readable |


## Section dividers

A picture on a section slide is never darkened. The chapter number, the chapter name and its subtitle sit on a solid panel in the accent colour covering the left third, and the picture keeps its own colours on the rest of the slide. Choose a picture whose subject sits right of centre, which is how every pack in the library is generated.

## Composition rules

1. The subject faces into the slide. A person looking left goes to the right of the text, and the reverse. A picture on the right with a subject looking right leads the eye off the slide.
2. Negative space where the text goes. On a full-bleed slide the headline sits in the bottom band; keep the subject above it. On a backdrop the title sits over the picture; keep the picture even.
3. Horizons and strong edges align to the margins or to the thirds, never a little off. A horizon that cuts the slide in half is dead; put it on the lower or the upper third.
4. Never stretch. If the ratio is wrong, crop with `treat`. A stretched face or logo is visible from the back of the room.
5. Rule of thirds for the subject; centre only when the picture is symmetrical on purpose.
6. No text over busy areas without a scrim. If the builder's band is not enough, choose a quieter picture, not a bigger scrim.
7. One picture per idea. Two pictures on a slide compare or contrast; they do not decorate.
8. Same scale of subject across a series: three portraits with heads the same size, three products at the same zoom.

## Resolution and file rules

| Use | Minimum width | Format | Notes |
|---|---|---|---|
| Full-bleed, backdrop | 1920 px (13.33 in at 144 dpi) | JPEG, quality 80 to 85 | 2560 px when the deck is shown on a 4K screen or printed |
| Half-slide picture beside bullets | 1200 px | JPEG for photos, PNG for illustrations | |
| Grid cell | 1000 px for two-up, 800 px for three-up and four-up | JPEG or PNG | |
| Screenshot | Native pixels of the cropped region, never upscaled | PNG | Take screenshots at 2x display scaling when possible |
| Icon | 256 px glyph on the transparent canvas | PNG, or SVG exported to PNG | |

- Keep each file under about 1 MB and the deck under 20 MB. Resize with `treat` before placing; the builder embeds the file as it is.
- The HTML deck embeds every picture as a base64 data URI, which costs about a third more than the file on disk, so size matters more there than in the pptx: a 2 MB photo adds about 2.7 MB to a file people will mail or open over a link.
- `deck_html.py --link-images` is the alternative: pictures stay as relative links and the `images/` folder travels with the HTML file. Use it for picture-heavy decks that live in a folder or a repository, not for a deck sent as one attachment.
- PNG for screenshots, flat illustrations, icons and anything with sharp edges or transparency. JPEG for photographs. Never JPEG for a screenshot; text edges smear.
- Strip metadata (location, camera serial, editing history). Pillow drops EXIF when it writes a new file, so a pass through `treat` is normally enough; check with your image tool when the source is a phone photo.
- Name files `images/<slide-number>-<subject>.png` or `.jpg`: `images/07-turbine.jpg`. Two digits for the slide number so the folder sorts in deck order. Renumber when slides move.
- Keep the originals untouched in `images/originals/` and treat into `images/`. A new treatment after a theme change starts from the originals.

## Screenshots

1. Crop to the region that matters. A full desktop screenshot shows a slide of window chrome and a postage stamp of content.
2. Highlight one thing per screenshot: a rectangle in `colors.accent`, 3 to 4 px, square corners, nothing else. No arrows, no circles, no red unless the accent is red.
3. Blur or replace personal data: names, emails, account numbers, internal hostnames, customer names in demo data. Use demo accounts and demo data where you can; blurring reads as hiding.
4. Use the product's light theme when the deck theme is light, and its dark theme when the deck is cyber-steel or midnight.
5. Keep the same zoom level and window width across all screenshots in the deck. Set the browser to one size and take them all in one sitting.
6. A border or a shadow, not a frame: a 1 px line in `colors.line` on light themes, a soft shadow on dark ones. Rounded corners only when the theme uses them.
7. Text in a screenshot must be readable from the back of the room, or the screenshot is too wide. Crop tighter or split it over two slides.

## Icons

1. One set for the deck (see sources.md), one weight, one size: 0.6 to 0.8 in on the slide.
2. Monochrome, in `colors.accent` or `colors.text`. Two-colour icons only when the set is designed that way (Phosphor duotone) and the second colour is the accent.
3. Always with a label. An icon without a word is a guess.
4. Never one icon per bullet. Icons mark three or four parallel things (pillars, phases, options), not lists.
5. Icons and photos do not share a slide. Icons and a chart do not share a slide.
6. Export as PNG with transparency, or place the SVG on the transparent canvas described above so the contain fit gives the right size.

## Illustrations

1. Match the palette. Recolour to `colors.accent` and `colors.accent2` when the set allows it (unDraw, Storyset, Humaaans and IRA Design all do). An illustration in its default blue on a terracotta theme is a mistake the audience sees before the headline.
2. One series for the whole deck: same set, same line weight, same level of detail. Do not mix Open Peeps with unDraw.
3. No illustration next to a photo on the same slide, and no illustration in a deck that is otherwise photographic. Choose one visual language for the deck.
4. Flat illustrations get no photo treatment. Crop, resize and rounded corners only.
5. Keep people in illustrations generic: no faces that resemble anyone, no uniforms of real organisations.

## Alt text

The alt text is the text inside `![...]`. The builder stores it as the picture description for screen readers, and it is what a reader with images turned off sees.

- One sentence per picture: what it shows and why it is there. "Engineer checking a wind turbine gearbox; the slide is about field maintenance costs."
- Decorative backdrops, textures and generated abstracts get "decorative background".
- Screenshots name the product and the region: "Billing settings page with the invoice frequency selector highlighted."
- Charts rendered as pictures state the finding, not the chart type: "Revenue by quarter, Q4 highest at 13.1 M."
- Icons name the concept, not the glyph: "Security", not "padlock icon".
- No "image of", no "picture of", no file names, no credits (credits go to the notes or the credits slide).

## Placeholders

While a picture is pending (the user still has to pick it, or generated images are not yet confirmed), do not leave the slide empty and do not use a random stand-in.

1. Run `visual_assets.py placeholder` with the intended description and the target size for the slot (16:9 for full-bleed, the box ratio for a contained picture). It writes a labelled PNG under the file name the storyboard uses.
2. Place it with the final alt text and file name, so the swap later is a file replacement and nothing else.
3. Build the deck and review the layout with the placeholders in: headline length, text wrap, grid balance.
4. List every pending picture in the report to the user: file name, slide, what it should show, where to get it (search terms and source, or the prompt), and the licence you expect.
5. When the real file arrives, run `treat`, overwrite the placeholder, rebuild, and write the credits row.

## Review checklist

Run through this before the deck ships. Every item is a yes, or the deck waits.

1. Licence recorded: every third-party picture has a row in `images/credits.md`, and no picture is "found on the web".
2. Treatment consistent: one treatment on all photos, screenshots and illustrations untinted, nothing mixed.
3. Resolution: 1920 px or wider for full-bleed and backdrops, 1200 px for half-slide, screenshots at native pixels.
4. Cropping: subject faces into the slide, horizons on the thirds, nothing important under the scrim band, nothing cut at the edge by accident.
5. Legibility: headline and `Source:` line readable over every scrim; the quiet area is still quiet under the text.
6. Alt text: one sentence on every picture, "decorative background" on backdrops.
7. No stretched picture: every picture at its own ratio, cropped rather than squeezed.
8. No orphan icon: every icon has a label, one set and one weight throughout, no icon per bullet.
9. Credits slide present when any picture is CC BY; every generated image marked "AI-generated image" in the notes or on the credits slide.
10. File sizes: no file over about 1 MB, deck under 20 MB, originals kept in `images/originals/`, file names in the `images/<slide-number>-<subject>` form.
