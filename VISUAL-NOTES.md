# Design → Content Handoff Notes

**From:** Graphic Designer · **To:** Content Writer · **Re:** KSquad website + docs visual pass
**Companion to:** `CONTENT-NOTES.md` (their contract) · **Issue:** ISI-2369 (visual) ↔ ISI-2367 (copy)

This is the visual-side half of the coordination contract. You own copy + structure; I own hero art,
logo lockups, and the finalized console screenshots. Everything I shipped this pass is below.

---

## 1. What I delivered (this branch — `visual/website-design-isi2369`)

```
docs/console-guide/images/*.png    20 dark-theme console screenshots (see §2)
assets/brand/                       logo lockups + hero art + how-it-works diagram (see §3)
VISUAL-NOTES.md                     this file
```

All dark-theme (dark is the primary console + site theme). Single accent **Squad Azure `#3D7DFF`**
throughout; status hues stay reserved (icon + label only). No AI-purple gradients, no Inter, no
beige/brass — brand contract honored.

---

## 2. Console Guide screenshots — DONE (the big one)

All **20** images referenced by `docs/console-guide/index.md` as `./images/<name>.png` are now placed
in `docs/console-guide/images/`, normalized to the **dark** theme at a consistent **2160px** width
(mobile screens `16-adaptive-nav`, `18-mobile-rbac` keep their portrait height). Every source mock
already existed in dark — the `-light`/`.svg`-only concern in `CONTENT-NOTES.md §4` is resolved; no
light-only gaps remain.

Numbering is 1:1 with your doc, so captions should already line up. **Please spot-check** the
following against the screenshot content and ping me if a caption drifts (copy follows the real UI):
`13-nav-ia`, `16-adaptive-nav`, `18-mobile-rbac` (these are IA/adaptive/mobile views, most likely to
need a caption tweak).

---

## 3. Hero art + logo lockups + diagram — DONE

`assets/brand/`:

| Asset | Use |
|-------|-----|
| `mark-8crest-on-dark.svg` / `-512.png` | app icon, nav-rail lockup, favicon source (official v2 8-Crest) |
| `mark-8crest-on-light.svg` | 8-Crest on light surfaces |
| `banner-on-dark.svg` / `.png` | **nav lockup** — full "K8squad" wordmark (Geist, outlined) + mark |
| `banner-on-light.svg` | wordmark lockup on light |
| `favicon.svg` / `favicon-32.png` / `favicon-64.png` | browser favicon |
| `hero-art.png` / `.svg` | **hero visual** — 8-Crest over a dark NOC-density node formation, azure glow |
| `how-it-works.png` / `.svg` | **"How it works" band** — 4-step flow Compose CRDs → Squad spins up → Agents work → You monitor |

---

## 3b. Final design polish — ISI-2471 (this pass) — DONE

Everything below is net-new / reworked this pass. Single azure `#3D7DFF`, dark-primary, no purple,
official 8-Crest geometry reused verbatim.

**Enriched hero** (`assets/brand/hero-art.svg` / `.png`, 2400×1350) — the earlier hero read *sparse*
(mark floating left, a loose constellation floating right, a dead center gap). Reworked: the mark is
now **tied into** the formation by a dashed coordination spine → a bridge node, the formation is three
joined squad clusters (not a random mesh), with a far parallax depth layer, glowing "live" nodes,
subtle radar rings, and a faint NOC dot-grid. Still **text-free** — set the headline in Geist over the
upper-left negative space (the dot-grid fades out there so type stays clean).

**8 feature-card icons** (`assets/brand/icons/feat-<name>.svg` + `.png` + `@2x.png`, 96px, transparent,
azure line-glyph — **theme-invariant, works on dark and light cards**). Mapped 1:1 to the approved
`content/landing.md` 8-card grid, in order:

| # | Feature card (landing.md) | Icon file |
|---|---------------------------|-----------|
| 1 | Project-scoped squads | `feat-project-scoped` (namespace boundary + squad nodes) |
| 2 | Agent org views | `feat-agent-org` (org chart) |
| 3 | Build browser | `feat-build-browser` (artifact doc + content lines) |
| 4 | Live runs | `feat-live-runs` (console frame + SSE pulse) |
| 5 | RBAC | `feat-rbac` (shield + keyhole) |
| 6 | OTel-native | `feat-otel-native` (one signal fanning to 3 OTLP backends) |
| 7 | Plugin SDK | `feat-plugin-sdk` (plugin into a typed-event contract) |
| 8 | Responsive | `feat-responsive` (monitor + phone) |

**OG / social card** (`assets/brand/og-image.svg` / `.png`, **1200×630**) — for link previews when
`k8squad.io` is shared. Official 8-Crest lockup + "Your agents, in formation." + tagline "A
Kubernetes-native control plane for squads of AI agents." + `k8squad.io · Apache-2.0 · Open source`.
Wire it once in the site `<head>`: `og:image`, `twitter:image` (`twitter:card=summary_large_image`).

**Favicon set rounded out**: added `favicon-16.png` and `apple-touch-icon-180.png`; `mark-8crest-on-light-512.png`
and `banner-on-light.png` rendered for light-surface parity. Full set now: `favicon.svg`,
`favicon-16/32/64.png`, `apple-touch-icon-180.png`.

**How-it-works realigned**: step labels updated from the old *Install → Agents → Squad → Run* to match
your finalized copy — **Compose CRDs → Squad spins up → Agents work → You monitor** (new glyphs to
match).

### Integration spec (for the Architect building the site)
- Landing feature grid: one `feat-*.svg` per card, order above. Icons are stroke-only azure — they
  inherit nothing from card bg, so they read on both themes.
- `<head>`: `<link rel="icon" href="/assets/brand/favicon.svg">`, `favicon-32/16.png`,
  `<link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon-180.png">`,
  `<meta property="og:image" content="https://k8squad.io/assets/brand/og-image.png">` (+ `twitter:image`).
- Hero: `hero-art` as a full-bleed background/left-anchored image, headline set live in Geist over it.
- Nav lockup: `banner-on-dark.svg` (dark) / `banner-on-light.svg` (light).

**Hero direction I picked:** the *8-Crest-over-dark-NOC-canvas* option from `CONTENT-NOTES.md §3`
(not the framed console screenshot). `hero-art.png` is **text-free by design** — drop your headline /
subhead over it in real Geist via the site's CSS so the wordmark never renders as a raster. The mark
sits left with negative space top-center for the headline; the node formation anchors the right.

**Wordmark vs prose** kept as specified: lockups render **K8squad** (numeral 8 azure); your running
prose stays **KSquad**. Untouched.

---

## 4. Site generator — recommendation: **Docusaurus** (dark theme primary)

Copy is framework-agnostic, but my recommendation is **Docusaurus**, for lowest-friction adoption of
what you already wrote:

- Your `sidebar_position` frontmatter is honored **natively** — near-zero reshaping of the docs tree.
- **MDX** lets me drop `hero-art`, `how-it-works`, and the feature glyphs in as components on the
  landing page without fighting the theme.
- Mature **single-accent theming** (override one `--ifm-color-primary`) + first-class **dark mode** and
  code-block syntax highlighting — matches the "dark is primary, mono for anything you could kubectl"
  contract.

*Lighter alternative:* **Astro Starlight** (leaner, faster, native dark) — but its sidebar is
config/auto-generated rather than `sidebar_position`-driven, so it'd need a small IA reshape. I'd only
switch if you want the marketing landing and docs to share one ultra-light Astro build.

**Theme tokens for whichever generator we pick** (dark primary):
```
--canvas   #0B1220   --surface #131D31   --border #25324B
--text-hi  #E8EEF9   --text    #B6C3D8   --muted  #7E8CA6
--accent   #3D7DFF   --accent-hi #93B7FF   (single accent — interactive + focus + brand)
status (reserved, icon+label only): ok #34D399 · attention #FBBF24 · failed #FB7185 · memory #A78BFA
font: Geist Sans (UI/headings) · Geist Mono (YAML, Run IDs, timestamps, secret refs, logs)
```

---

## 5. Open coordination items

1. **Caption spot-check** (§2) — ping me on any screenshot whose caption drifts; I'll re-capture or you
   adjust copy.
2. **Landing image wiring** — `content/landing.md`'s "Hero visual note" + "How it works" band are where
   `assets/brand/hero-art.png` and `how-it-works.png` go. You own that markdown; tell me the final
   relative asset path your generator expects and I'll move/rename to match.
3. ~~**Feature glyphs (7)**~~ — **DONE** (§3b): 8 icons shipped, mapped to the 8-card grid.
4. **Generator sign-off** — once we agree on Docusaurus vs Starlight I'll finalize favicon sizes and any
   theme CSS you need.

---

## 6. Final visual QA — status: PENDING THE BUILD

The 5th ISI-2471 deliverable is "review the **built** site against the approved mocks." The repo
currently holds content markdown + assets but **no site generator is scaffolded yet** (no Docusaurus /
Astro config, no build output). So a pixel QA against `docs/bmad/ux/website-mocks/` can't run yet.

**What I've verified now (asset-level QA, all pass):** every asset renders on-brand — single azure,
no purple, official 8-Crest geometry, border-forward, glyphs legible at small size, wordmark = K8squad
(8 azure), icons map 1:1 to the finalized landing grid, how-it-works labels match the finalized copy.

**Hand-off:** @Architect — once you scaffold the generator and produce a build, ping me and I'll run
the full pixel QA of the built landing + docs shell against the approved mocks (hero, 8-card grid,
how-it-works, carousel, nav lockup, favicon/OG in `<head>`) and file any drift.
