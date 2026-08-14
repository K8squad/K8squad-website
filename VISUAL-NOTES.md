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
| `how-it-works.png` / `.svg` | **"How it works" band** — 4-step flow Install → Agents → Squad → Run |

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
3. **Feature glyphs (7)** — optional per §3; not shipped this pass. Say the word and I'll add one
   azure-line glyph per feature card in the same style as the `how-it-works` glyphs.
4. **Generator sign-off** — once we agree on Docusaurus vs Starlight I'll finalize favicon sizes and any
   theme CSS you need.

---

## 6. ISI-2471 — website visual polish pass (shipped 2026-08-14)

Design → build handoff, wired directly into the Astro site (`src/pages/index.astro` + `public/`).

1. **Enriched hero** — `hero-art.svg/png` (2400×1350, text-free). The sparse v1 is replaced by the
   8-Crest mark left-of-centre tied by a dashed coordination spine into a denser, depth-layered squad
   formation (3 clusters, live/glowing SSE nodes, radar rings, faint NOC dot-grid, border frame). Site
   overlays the headline in real Geist, so the art stays wordmark-free. Wired at `public/hero-art.svg`.
2. **Feature-card icons (7)** — one azure line-glyph per **live** landing card (the CW grid moved from
   the stale 8-item mock to 7 cards). `assets/brand/icons/feat-{orchestrate,reconcile,workitems,
   credentials,safe,legible,quickstart}.svg` (+ .png/@2x). Stroke 5, round, transparent, theme-invariant
   (azure #3D7DFF reads on both dark #131D31 and light #FFFFFF cards). Mapping:
   01 orchestrate=hub→shim→swappable runtimes · 02 reconcile=sync-loop around the Run · 03 workitems=
   durable record + lease padlock · 04 credentials=key · 05 safe=shield+check · 06 legible=console+SSE
   pulse · 07 quickstart=rocket. Added to each card via a `.feature-head` row (icon + number) in
   `index.astro`; served from `public/icons/`.
3. **OG / social card** — `og-image.svg/png` (1200×630): official banner lockup (8-Crest mark + outlined
   Geist "K8squad" wordmark, verbatim from `banner-on-dark.svg`) + "Your agents, in formation." +
   headline + k8squad.io/Apache-2.0/Open-source chips + formation motif. Wired at `public/og-image.png`
   (matches the `og:image` absolute URL already in `index.astro`).
4. **Logo/favicon** — refreshed `apple-touch-icon` (180px from the dark mark) + `mark-8crest-on-light-512.png`
   for parity; `favicon.svg`, `mark-8crest.svg` unchanged (already correct in `public/`).
5. **Visual QA** — `npm run build` clean (28 pages); all `/icons/feat-*.svg`, `/hero-art.svg`,
   `/og-image.png`, `/apple-touch-icon.png` resolve in `dist/index.html`. Hero, OG, and both icon sheets
   (dark + light) verified on-brand: single azure accent, border-forward, mark geometry crisp, glyphs
   legible at card size. No purple, no second accent.

Open item #3 above (feature glyphs) is now **shipped**. Regenerators: `/tmp/svgrender/gen_ksquad_assets.py`
(hero/OG/how-it-works), `/tmp/svgrender/gen_icons_v2.py` (7 icons), `render_isi2471.js` (PNG export).
