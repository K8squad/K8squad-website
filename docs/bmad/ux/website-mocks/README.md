# KSquad website mocks (ISI-2366)

Design mocks for the **public KSquad website** (target repo:
`github.com/K8squad/K8squad-website`) — distinct from the operator-console mocks
in `../images/`. Collaboration: **Content Writer** (ISI-2367) owns copy/structure,
**Graphic Designer** owns visual design.

## Deliverables

| File | Page | Themes |
|------|------|--------|
| `01-landing` | Single-page scroll landing | dark + light |
| `02-docs-layout` | Docs site shell (sidebar + search + TOC) | dark + light |
| `03-sdk-guide` | Plugin SDK guide layout | dark + light |

Each is committed as `*.svg` (source) + `*.png` (1440 px render). PNGs are also
attached to ISI-2366 (durable — the planning tree is gitignored/fragile).

### 01 — Landing page
Sticky nav → hero (*"Your agents, in formation."* + animated node-network + helm
one-liner + dual CTA) → **What is KSquad** (3 icon cards) → **Features grid**
(8 cards: Project-scoped squads, Agent org views, Build browser, Live runs, RBAC,
OTel-native, Plugin SDK, Responsive) → **How it works** (4-step flow: Compose CRDs
→ Squad spins up → Agents work → You monitor) → **Screenshots carousel** (browser
frame + console screen + 5-thumbnail strip + dots) → **Get started** (helm command
+ docs CTA) → footer (Product / Docs / Community + Apache 2.0).

### 02 — Docs layout
Header (8-crest + `docs` chip, centered `⌘K` search, dark/light toggle + GitHub) ·
250 px sidebar (Quickstart / Concepts / Operator Guide / Author Guide / Console
Guide / API Reference / Observability / Troubleshooting, active section expands) ·
content (breadcrumb, H1, prose, syntax-highlighted YAML, note callout, inline
console screenshot) · right "On this page" TOC · prev/next.

### 03 — SDK guide
Same docs shell rendering the **Plugin SDK** page, aligned to the real
**NATS/JetStream** architecture (ADR-023, ISI-2475/2478): architecture diagram
(Host runtime `Postgres outbox → relay` → **NATS/JetStream** replayable subjects
`ksquad.{entity}.{project}.{squad}.{event}` → **your worker** [sidecar/standalone,
read-only observer, out-of-process, no console embedding]) · event reference table
(real taxonomy: `run.*`, `workitem.*`, `artifact.registered`, `memory.written`,
`scm.pushed`) · **Your first plugin** 3-step transport-first walkthrough (`nats sub`
→ typed decode via first-party Go `pkg/events` in `observer.go` → `go run`
out-of-process) · language-agnostic tip callout. Brand/design system unchanged.

## Design system (locked to brand)
- **Dark:** bg `#0F1117`, cards `#1A1D29`, border `#262B3A`. **Light** mirrors the
  console token map (canvas `#F6F8FC`, cards `#FFFFFF`, …).
- **Single accent — Squad Azure `#3D7DFF`, theme-invariant.** The issue suggested
  `#3b82f6`; I used the locked brand azure `#3D7DFF` so the accent matches the
  8-crest mark and the console exactly (they are ~identical hues). One accent only.
- **Logo:** official 8-Crest mark geometry (`branding/assets/mark-8crest-on-dark.svg`),
  wordmark "K8squad" with the numeral **8** in azure (brand rule); prose says "KSquad".
- Type: Geist-nominal, rendered with DejaVu. Code blocks stay dark in both themes
  (dev-site convention) with a constant syntax palette.
- Radius scale 6/8/10-14/full; border-forward, low elevation. Taste-skill compliant:
  no AI-purple gradients, one accent, consistent radii; violet reserved.

## Rebuild
```
python3 gen_website.py                 # writes 6 SVGs here
node /tmp/svgrender/render_website.js  # SVG -> PNG @1440 (needs @resvg/resvg-js + DejaVu)
```
`gen_website.py` is self-contained (own token maps + primitives — no console_kit
import) so a concurrent console-kit edit can't break it.

## Open collaboration points (Content Writer / CEO)
- Hero tagline, feature blurbs and section copy are placeholders drawn from the
  issue brief — Content Writer to finalize wording (ISI-2367).
- Screenshots carousel uses stylized console frames; final site can drop in the
  real v6 console PNGs from `../images/` (13-nav-ia, 14-project-tickets,
  08-fleet-dashboard, 20-agents-role-org, 06-build-browser).
- Docs domain shown as `docs.ksquad.io` / charts `charts.ksquad.io` — confirm.
