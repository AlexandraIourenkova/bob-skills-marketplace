# Generation prompts

This file explains when to generate a picture instead of searching for one, how to write prompts that give consistent, text-free, 16:9 slide visuals in the theme's colours, and how to disclose generated images. Read it when sources.md has no good picture for a slide, when a deck needs a matching series of abstract visuals, or when the user asks for generated images. The agent writes the prompts; the user runs them in the generator the company allows and saves the results into `images/`.

## When to generate, when not to

| Generate when | Search or shoot instead when |
|---|---|
| The subject is abstract: trust, latency, migration, risk, momentum | The slide shows a real product, screen or device |
| The slide needs a metaphor that no photo shows without a cliché | The slide shows real people: the team, a customer, an executive |
| The deck needs a series of six or more visuals in one style | The slide shows a real place presented as fact: the plant, the office, the site |
| No photo fits the theme's palette and treatment | The content is a chart, a number or data of any kind; draw it with deck-dataviz |
| The stock look must be avoided | A logo, a trademark or a brand element is involved |
| Title and section backdrops, textures, dividers | The company's policy on generated media says no, or the user has not confirmed it yet |

Before the first generated image in a deck, ask the user whether generated images are allowed for this deck and whether a specific generator is mandated. Record the answer in the deck's `images/credits.md`.

## The prompt formula

One prompt is nine slots in this order. Fill every slot. Drop nothing.

| Slot | What goes in | Example |
|---|---|---|
| Subject | One thing, concrete, no list | "a single glass bridge spanning a canyon" |
| Setting | Where it is, how much of the frame it takes | "wide landscape, bridge in the right third" |
| Style family | One phrase from the table below | "editorial photograph" |
| Composition | 16:9, negative space on the side where the text goes, rule of thirds, camera height | "16:9, empty sky on the left for text, low camera" |
| Lighting | One source, one time of day | "soft overcast light, no harsh shadows" |
| Palette | The theme's colours in words, taken from `colors.bg`, `colors.accent`, `colors.accent2` | "deep navy background, electric cyan highlights, no other colours" |
| Mood | One or two words | "calm, precise" |
| Detail level | Simple or detailed, clean or textured | "clean surfaces, minimal detail" |
| Technical | The fixed tail, identical in every prompt | "no text, no letters, no numbers, no watermark, no logo, no signature, sharp focus, 16:9" |

Colour words from hex: name the hue and the depth, not the code. `#0F62FE` is "bright cobalt blue", `#002D9C` is "deep navy", `#F4F4F4` is "off-white", `#DA1E28` is "signal red", `#FF832B` is "warm orange", `#009D9A` is "teal", `#8A3FFC` is "violet". Give two colours at most plus the background; with three or more the generator picks its own.

Three complete prompts built with the formula:

1. Title backdrop, boardroom theme: "A single glass bridge spanning a wide canyon, wide landscape with the bridge in the right third, editorial photograph, 16:9, empty sky on the left for text, low camera, soft overcast light with no harsh shadows, off-white sky and deep navy rock with bright cobalt blue reflections and no other colours, calm and precise mood, clean surfaces with minimal detail, no text, no letters, no numbers, no watermark, no logo, no signature, sharp focus, 16:9."
2. Section divider, cyber-steel theme: "Layered translucent planes receding into darkness, a centred stack filling the lower two thirds, abstract geometric render, 16:9, empty dark space in the top third for text, rim light from the right, near-black background with cyan edges and a violet glow and no other colours, focused and quiet mood, smooth surfaces with fine detail, no text, no letters, no numbers, no watermark, no logo, no signature, sharp focus, 16:9."
3. Growth slide, warm-human theme: "A young olive tree in a terracotta pot on a wooden table, tree in the right half with the table running out of frame, flat vector illustration, 16:9, plain empty wall on the left for text, warm afternoon light from a window, cream background with terracotta and sage green and no other colours, hopeful and unhurried mood, simple shapes with minimal detail, no text, no letters, no numbers, no watermark, no logo, no signature, sharp focus, 16:9."

## Style families

| Family | Descriptor phrase to paste | Good for |
|---|---|---|
| Flat vector | "flat vector illustration, solid fills, no gradients, no outlines, geometric shapes" | Process, concepts, people without faces |
| Isometric 3D | "isometric illustration, 30 degree projection, clean edges, soft ambient occlusion" | Architecture, infrastructure, flows |
| Clay 3D render | "clay 3D render, matte materials, soft studio light, rounded forms" | Playful and startup themes, product-like objects |
| Editorial photograph | "editorial photograph, 35 mm lens, natural light, shallow depth of field, documentary style" | Backdrops, places, materials |
| Watercolour | "loose watercolour painting, wet edges, white paper showing through" | Nature, warm-human, academic covers |
| Ink line art | "single-weight black ink line drawing, no shading, white background" | Mono-ink, editorial |
| Abstract geometric | "abstract geometric composition, overlapping planes, hard edges" | Swiss, geometric, dividers |
| Paper cut | "layered paper cut-out, soft drop shadows between layers" | Nature, playful, warm-human |
| Gradient mesh | "smooth gradient mesh, out-of-focus colour fields, no shapes" | Startup-gradient, cyber-steel backdrops |
| Glassmorphism | "frosted glass panels, blurred colour behind, thin light edges" | Dark-tech, data-studio |
| Blueprint | "technical blueprint drawing, white lines on a deep blue ground, fine grid" | Engineering, academic |
| Collage | "cut-paper collage of photographic fragments and flat colour blocks" | Editorial, geometric |

## Theme to style map

| Theme | Style family (first, second) | Palette words | Avoid |
|---|---|---|---|
| swiss | Abstract geometric, editorial photograph in black and white | white, black, signal red as the single accent | Gradients, more than one colour |
| editorial | Editorial photograph, collage | cream, charcoal, one warm accent such as oxblood or ochre | Neon, 3D renders |
| boardroom | Editorial photograph, flat vector | white, cobalt blue, deep navy | Cartoon characters, pastels |
| carbon | Editorial photograph, flat vector | white, IBM blue, black, one bright Carbon accent | Cartoon characters, pastels |
| cyber-steel | Gradient mesh, blueprint | steel black, hazard amber, cyan | Daylight scenes, warm pastels |
| sketch | Ink line art, watercolour | paper white, pencil grey, ink blue, red pencil | Photographs, gradients, 3D |
| geometric | Abstract geometric, paper cut | off-white, vermilion, cobalt, mustard | Soft light, fine detail, realism |
| midnight | Editorial photograph, abstract geometric | near-black warm, gold, muted teal | Bright white scenes, neon |
| warm-human | Flat vector, watercolour | terracotta, sand, cream, sage | Cold blues, chrome |
| data-studio | Abstract geometric, glassmorphism | off-white, teal, orange | Photographs of people, texture |
| academic | Blueprint, ink line art | white, muted blue, light grey | Loud colour, 3D |
| nature | Watercolour, paper cut | forest green, sand, moss | Neon, tech motifs |
| startup-gradient | Gradient mesh, clay 3D render | violet to pink, deep purple ground | Flat black, corporate blue |
| mono-ink | Ink line art, editorial photograph in black and white | black, white, one grey | Any colour |
| playful | Clay 3D render, flat vector | pastel mint, lavender, peach, butter yellow | Dark grounds, realism |

Read the exact colours from the deck's theme.json and translate them. The table gives the usual words; the theme file wins.

## Composition by slot

| Slot | What the builder does | Ask the generator for |
|---|---|---|
| `backdrop:` (title, sections, closing) | Covers the slide, darkens the whole picture by about half, draws the title over it | Even density, no single subject, no faces, low contrast: a texture or a wide empty scene |
| Full-bleed `image` slide | Covers the slide, dark band 2.6 in tall at the bottom with the headline and the `Source:` line in it | Subject in the upper two thirds, quiet lower band, horizon on the upper third |
| Picture beside bullets | Fits the picture into the right 58 percent of the content area, text on the left | No negative space needed inside the picture; subject facing left; ratio 4:3 or 3:2 |
| Grid cell | Fits two to four pictures into equal cells | One centred subject, plain ground, same ratio and same scale in every cell |
| Icon row | Fits each icon into its column | Not a generator job; use an icon set from sources.md |

## Consistency across a deck

1. Write one style block: the style family phrase, the lighting, the palette words and the technical tail, in one sentence. Paste it unchanged into every prompt for the deck. Change only the subject, the setting and the composition.
2. When the generator supports a seed, keep the same seed for the series. When it supports a reference image, use the first picture you accepted as the reference for the rest.
3. Generate three or four variants of every prompt. Pick the one with the calmest composition: fewest elements, largest quiet area, one clear subject. Not the most impressive one.
4. Look at all accepted pictures side by side as thumbnails before placing them. One that stands out in colour or density gets regenerated.
5. Keep a log at `images/prompts.md` in the deck folder: file name, slot, generator and version, date, seed if any, the full prompt, the negative prompt. The log is what makes a replacement possible in three months.

```markdown
| File | Slot | Generator | Date | Seed | Prompt | Negative |
|---|---|---|---|---|---|---|
| images/01-backdrop.png | title backdrop | (generator name and version) | 2026-09-10 | 4821 | (full prompt) | (negative prompt) |
```

## Negative prompts and exclusions

Put these in the negative prompt where the generator has one, and in the technical tail where it does not.

- Text of any kind: letters, numbers, captions, signs, labels, typography, watermarks, signatures.
- Logos, brands, trademarks, recognisable products, flags.
- Faces of real people, celebrity likenesses, and photorealistic faces in general when the slide has a person.
- Extra fingers, extra limbs, distorted hands, distorted faces, melted objects.
- Busy detail in the area reserved for text; say "empty" or "plain" for that region in the composition slot.
- Frames, borders, vignettes, split panels, mock-up devices, fake user interfaces.
- Stock clichés: handshakes, rockets, light bulbs, chess, puzzle pieces, arrows, globes with connection lines.

## Common failures and fixes

| What comes back | Fix in the prompt |
|---|---|
| Letters or fake signage | Put the tail at the front of the prompt as well; add "no signage, no labels" to the negative prompt; avoid subjects that carry text in real life (shops, dashboards, books) |
| Subject dead centre, no room for text | Name the third: "subject in the right third, left two thirds empty"; add "asymmetric composition" |
| Colours drift from the theme | Cut to two colours plus the background and say "no other colours"; name the background colour first |
| Too busy | Add "minimal detail, few elements, plain ground"; reduce the setting to one noun |
| Faces appear where none were asked for | Add "no people" to the subject slot and "faces" to the negative prompt |
| Looks like stock photography | Change the style family, not the subject: editorial photograph to abstract geometric or paper cut |
| Variants all look different | Fix the seed; shorten the prompt; every extra adjective widens the spread |
| Wrong ratio | Say "16:9" at the start and in the tail; crop with `treat` afterwards rather than asking again |

## Prompt library by slide role

Replace `[style]` with the theme's style family phrase, `[palette]` with its palette words, `[side]` with the side where the text goes and `[opposite]` with the other side. Every prompt ends with `[tail]`, the technical tail: "no text, no letters, no numbers, no watermark, no logo, no signature, sharp focus, 16:9".

| Role | Slot | Prompt |
|---|---|---|
| Title backdrop A | `backdrop:` in the front matter | Wide horizon over a still surface at dawn, horizon on the lower third, [style], 16:9, empty upper half, single low light source, [palette], calm mood, minimal detail, [tail] |
| Title backdrop B | `backdrop:` | Close-up of a woven or layered material filling the frame, no single subject, [style], 16:9, even density so text reads anywhere over a scrim, soft top light, [palette], quiet mood, fine texture, [tail] |
| Section divider A | `backdrop:` or an `image` slide | A single path crossing an empty field from bottom left to upper right, [style], 16:9, empty [side] half, flat overcast light, [palette], purposeful mood, minimal detail, [tail] |
| Section divider B | `image` slide | Stacked horizontal bands of colour like geological strata, bands in the lower two thirds, [style], 16:9, plain upper third, no visible light source, [palette], steady mood, clean edges, [tail] |
| Abstract data or technology | picture beside bullets | A lattice of small spheres joined by thin lines fading into the distance, lattice on the [opposite] side, [style], 16:9, empty [side] half, rim light, [palette], precise mood, fine detail, [tail] |
| Growth | picture beside bullets | A young plant on a plain ground seen from the side, plant in the [opposite] third, [style], 16:9, empty [side] two thirds, morning side light, [palette], hopeful mood, minimal detail, [tail] |
| Teamwork without the cliché | picture beside bullets | Several hands of different skin tones arranging wooden blocks on a table seen from above, blocks in the [opposite] half, [style], 16:9, plain table on the [side], soft window light, [palette], focused mood, moderate detail, [tail] |
| Customer journey | `image` slide with a caption | A winding road through gentle hills from the foreground to a small town on the horizon, road curving from bottom [side] to top [opposite], [style], 16:9, open sky above, late afternoon light, [palette], inviting mood, moderate detail, [tail] |
| Security | picture beside bullets | A smooth vault-like door set into a plain wall, door in the [opposite] third, [style], 16:9, empty wall on the [side], one soft overhead light, [palette], solid mood, minimal detail, [tail] |
| Sustainability | picture beside bullets | A single tree on a low hill under a wide sky, tree in the [opposite] third, [style], 16:9, empty sky on the [side], clear morning light, [palette], calm mood, minimal detail, [tail] |
| Migration or transformation | `image` slide | A bridge from a cluttered stone bank to an open ordered bank, bridge spanning the middle, [style], 16:9, empty water below for a caption, even daylight, [palette], deliberate mood, moderate detail, [tail] |
| AI and automation | picture beside bullets | Neat rows of identical objects with one row being sorted by an unseen mechanism, rows in the [opposite] half, [style], 16:9, empty surface on the [side], soft top light, [palette], orderly mood, moderate detail, [tail] |
| Global reach | `image` slide | An abstract network of points and arcs on a plain sphere with no country borders, sphere in the [opposite] half, [style], 16:9, empty [side] half, rim light, [palette], expansive mood, fine detail, [tail] |
| Process or workflow | picture beside bullets | Four stepping stones across a shallow stream in a straight line, stones in the [opposite] half, [style], 16:9, empty water on the [side], flat light, [palette], steady mood, minimal detail, [tail] |
| Risk | picture beside bullets | A tall stack of thin plates balanced on a narrow base, stack in the [opposite] third, [style], 16:9, empty [side] two thirds, hard side light with a long shadow, [palette], tense mood, minimal detail, [tail] |
| Closing or ask | `backdrop:` for the closing slide, or an `image` slide | An open door in a plain wall with light coming through, door in the [opposite] third, [style], 16:9, empty wall on the [side], warm light from beyond the door, [palette], decisive mood, minimal detail, [tail] |
| Placeholder texture | any pending picture, until the real one arrives | Even fine-grained texture like unbleached paper or brushed metal filling the frame, no subject, [style], 16:9, uniform density, flat light, [palette] in the palest tone, neutral mood, [tail] |

## Rules and disclosure

1. No likeness of any real person, including public figures, employees and customers. If a slide needs a real person, use a real photograph with consent.
2. No brand logos or trademarks, yours included. Logos come from the brand portal as files, never from a generator.
3. Nothing generated is presented as a real product, place, event or result. A generated "office" is a backdrop, not the office.
4. Ask the user whether generated images are allowed for this deck and record the answer. Follow the company's policy on generated media and the generator's own terms; some generators restrict commercial use on free tiers.
5. Disclose: "AI-generated image" in the `Notes:` line of every slide that has one, or on the credits slide when the deck has one. Keep the generator name and the full prompt in `images/credits.md`.
6. Prefer generated images for abstract backdrops, dividers and metaphors. Leave products, people and places to real photography.
7. Never generate charts, diagrams with numbers, maps with borders, or anything the audience might read as data.

## After generation

1. Crop and unify with `visual_assets.py treat`: crop to 16:9 for full-bleed pictures and backdrops, or to the box ratio for a contained picture, then apply the deck's one treatment (see treatment.md).
2. Check the size: at least 1920 px wide for full-bleed and backdrops, 1200 px for a half-slide picture. Upscale in the generator, not in Pillow.
3. Look for artefacts at 100 percent: stray letters, warped edges, doubled objects, a subject cut by the frame. Regenerate rather than retouch.
4. Build the deck and look at the slide at full size with the headline over it. The quiet area must still be quiet under the scrim and the text.
5. Write the credits row and the prompt log row before moving to the next picture.
