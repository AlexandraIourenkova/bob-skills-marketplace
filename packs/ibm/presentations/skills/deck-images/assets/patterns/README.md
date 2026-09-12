# Pattern tiles

Twelve tileable SVG tiles written for this pack, Apache-2.0 like the rest of it, no third-party licence to carry. Each tile draws in `currentColor` on a transparent ground, so the colour comes from whatever places it.

`visual_assets.py pattern <name> --theme theme.json -o images/texture.svg` tiles one of them across a slide-sized SVG in a theme colour. Use it for a texture behind a section, a card or a quote, at low strength; a full-slide backdrop is usually better made with `visual_assets.py backdrop`, which composes rather than repeats.

| Tile | Reads as | Pairs with |
|---|---|---|
| `dots` | even dot field, quiet under text | any concept |
| `grid` | engineering grid | carbon, data-studio |
| `diagonal` | pencil hatching | sketch |
| `cross-hatch` | denser hatching, drawn by hand | sketch, editorial |
| `chevrons` | forward motion | roadmaps, timelines |
| `triangles` | flat geometric shapes | geometric, playful |
| `waves` | soft movement | nature, warm-human |
| `circuit` | technology, connections | cyber-steel, carbon |
| `topo` | contour lines, terrain | nature, midnight |
| `confetti` | celebration | playful, all-hands |
| `plus` | neutral texture | any concept |
| `bricks` | structure | academic, mono-ink |

Keep textures at 6 to 12 percent strength behind text. Anything stronger competes with the words.
