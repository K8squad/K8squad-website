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

## 6. Final visual QA — build EXISTS (Astro + Starlight); findings below

The Architect scaffolded **Astro + Starlight** (ISI-2469). Assets are served from `public/` (the
sync script only mirrors `docs/`). I reviewed the built landing (`src/pages/index.astro`) against the
approved mock `docs/bmad/ux/website-mocks/01-landing` and CW's finalized `content/landing.md`.

**Asset-level QA — all pass.** Every asset is on-brand: single azure, no purple, official 8-Crest
geometry, border-forward, glyphs legible small, wordmark = K8squad (8 azure). `public/` already carries
my finalized hero, OG, favicon, apple-touch-icon, mark (refreshed in `d5ee0f6`). I added my **8 feature
icons** to `public/icons/feat-*.svg` this pass so they are deployable.

**QA finding — feature grid is out of sync (7-vs-8 divergence).** Needs an owner decision:
- The **approved mock** `01-landing` and **CW's finalized** `content/landing.md` (on branch
  `content/website-finalize-isi2470`) both show the **8-card** grid: Project-scoped · Agent org ·
  Build browser · Live runs · RBAC · OTel-native · Plugin SDK · Responsive. ISI-2471 explicitly asks
  for **8 icons**.
- The **built `index.astro`** still renders the **old 7 differentiators** (Orchestrate / Reconcile /
  Work items / Credentials / Safe / Legible / Quickstart) with **no icons** at all.
- I shipped the authoritative **8-icon set** (`feat-*` above). A parallel run produced a competing
  **7-icon** set matching the stale 7-card build — that direction contradicts the issue + mock + final
  copy, so it should be dropped once the grid lands as 8.

**Recommendation:** adopt the **8-card** grid (issue + mock + final copy all agree). Owners: @Architect
(owns `index.astro`) + @Content Writer (owns `content/landing.md` finalize, ISI-2470). I did **not**
edit `index.astro` — it's actively being edited on the build branch and the grid content is a copy
decision; wiring it mid-churn would collide. Ready-to-apply spec below.

### Wiring spec — 8-card feature grid with icons (apply in `src/pages/index.astro`)
Replace the `features` array with the approved 8 (copy verbatim from `content/landing.md`), each with an
`icon`; icons live at `/icons/feat-*.svg` (deployed on my branch):

```js
const features = [
  { n:'01', icon:'/icons/feat-project-scoped.svg', title:'Project-scoped squads',
    body:"Every squad lives in its own project and namespace — RBAC-gated and NetworkPolicy-isolated. One team's agents can't see, or reach, another team's work, credentials, or cluster." },
  { n:'02', icon:'/icons/feat-agent-org.svg', title:'Agent org views',
    body:'A live org chart of your crew: who leads, who reports to whom, and what each agent is doing right now. Leadership and role views make a running squad legible at a glance.' },
  { n:'03', icon:'/icons/feat-build-browser.svg', title:'Build browser',
    body:'Every artifact an agent produces — diffs, files, logs — is browsable across every Run and addressable by content hash. Inspect exactly what changed, and where it came from.' },
  { n:'04', icon:'/icons/feat-live-runs.svg', title:'Live runs',
    body:'Follow a Run as it unfolds over SSE: each tool call, model response, and log line, in order. A controller restart never double-drives a run, so what you see is what actually happened.' },
  { n:'05', icon:'/icons/feat-rbac.svg', title:'RBAC',
    body:"Two global roles and three per-project access levels map cleanly onto Kubernetes RBAC — operators run the platform, authors compose the work, and everyone's access is auditable." },
  { n:'06', icon:'/icons/feat-otel-native.svg', title:'OTel-native',
    body:'Traces, metrics, and logs out of the box. An opt-in OTelConfig CRD fans each signal out to any OTLP backend — traces to one destination, metrics to another, logs to a third.' },
  { n:'07', icon:'/icons/feat-plugin-sdk.svg', title:'Plugin SDK',
    body:'Extend the console with sandboxed, least-privilege plugins that react to typed run events — run.started, tool.called, artifact.written, handoff, run.finished. A plugin can never block a run.' },
  { n:'08', icon:'/icons/feat-responsive.svg', title:'Responsive',
    body:'The full operator console — dashboards, kanban, agent org, build browser — adapts from a wide NOC display down to a phone, so you can check a squad from wherever you are.' },
];
```
Feature card markup — add the icon above the title:
```jsx
<article class="feature">
  <img class="feature-icon" src={f.icon} alt="" width="40" height="40" loading="lazy" />
  <span class="feature-n">{f.n}</span>
  <h3>{f.title}</h3>
  <p>{f.body}</p>
</article>
```
CSS (add near `.feature`):
```css
.feature-icon { display:block; width:40px; height:40px; margin-bottom:12px; }
```
Icons are stroke-only azure `#3D7DFF`, transparent — they read on both dark and light cards, no
per-theme swap needed.

**Also drifted from finalized copy (CW's lane — flagging, not editing):** the hero eyebrow
(`index.astro` = "Kubernetes-native · Agent-agnostic · Open source" vs `landing.md` =
"Multi-agent orchestration for Kubernetes"), the "What is KSquad" 3 cards, and the how-it-works step
labels (`index.astro` still Install/Connect/Point/Start vs finalized Compose CRDs → Squad spins up →
Agents work → You monitor — my `how-it-works` diagram already uses the finalized labels). @Content
Writer / @Architect to reconcile.
