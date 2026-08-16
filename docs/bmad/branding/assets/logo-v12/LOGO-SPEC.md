# KSquad — Odin Infinity logo (v12) — production spec

Henrik-approved direction (2026-08-14, ISI-2514). Hand-crafted production vector
traced from the AI reference JPGs in this folder (`logo-canonical.jpg`,
`logo-dark-bg-2048.jpg`, `logo-transparent.jpg`, `logo-white-bg.jpg`).

## Files
| File | Use |
|------|-----|
| `odin-infinity-mark.svg` | **Primary mark** — horizontal (720×400 viewBox). Two rounded-square links forming ∞, Valknut knot centre, three-box task chain. Use in headers, docs, hero lockups. |
| `odin-infinity-glyph.svg` | **Compact glyph** — square (512×512). Links + knot only, no chain/side boxes. Use for favicons, app icons, avatars, anywhere below ~48px. |
| `odin-infinity-{transparent,dark,white}-2048.png` | Raster exports of the mark (2048px wide) for surfaces that can't take SVG. |
| `glyph-{transparent,dark}-512.png` | Raster exports of the glyph. |
| `favicon-*.png`, `favicon.ico` | Existing favicon raster set (from approved reference render). |

## Design elements
- **Two rounded-square ring links** forming an infinity (∞) — the 8-Crest rotated 90°.
- **Valknut / Odin interlock weave** at the centre where the links meet: two 45°-rotated
  diamond loops, interlaced over-under.
- **Three task boxes** on a dotted chain: claimed (bright square, left) → in-progress
  (bright centre diamond) → done (dark square, right).

## Palette (blue-only — no other hues)
| Token | Hex | Role |
|-------|-----|------|
| Light | `#93B7FF` | left link, knot highlight |
| Primary | `#3D7DFF` | dominant blue, active task boxes |
| Dark | `#2E4E8C` | right link, "done" box, depth |
| Bright | `#4D8BFF` | active centre diamond |

Links carry a light→dark diagonal gradient (top-left light, bottom-right dark) to give
the tube a subtle bevel while staying flat and crisp at any size.

## Regeneration
Vectors are generated deterministically — see `gen_odin_logo.py` / `gen_glyph.py`
(design tooling, kept with the Graphic Designer's working files). Edit those to adjust
geometry, then re-render with resvg.

## Rollout (downstream, other lanes)
- Console mocks + implementation → ISI-2515
- Website (k8squad.io) → ISI-2516
- GitHub org avatar / social → org-admin (Henrik)
