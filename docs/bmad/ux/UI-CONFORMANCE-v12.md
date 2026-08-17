# UI-follows-mocks conformance — logo v12 (ISI-2749)

> **What this is.** The per-screen target the console *build* must match, pinned to the
> refreshed **logo v12 (Odin Infinity)** mock set. Board directive (ISI-2170, 2026-08-17):
> *"make sure our UI follows the mocks build and shared on our website using our logo v12."*
>
> **Scope of this pass:** the console surfaces still in flight —
> **E8 console shell (ISI-2180)**, **E10.3 discussion room (ISI-2704 / ISI-2695)**,
> **E11.6 synced-state console + CI-failure auto-post (ISI-2741)**.
>
> **How to use.** Each row is a build acceptance item: the implemented UI must match the
> referenced mock element. `[ ]` = to verify against the running console; the graphic-design
> side of each item is **DONE** (mock exists at v12). Reference screens live in
> `docs/bmad/ux/images/` (dark + `-light` sibling). Source of truth for the mark:
> `docs/bmad/branding/assets/logo-v12/LOGO-SPEC.md`.

---

## 0. Global shell contract (applies to every screen — E8 and everything mounted in it)

Logo v12 + the locked visual system are a **whole-shell contract**; every surface inherits it.

### 0.1 Logo v12 (Odin Infinity) — `LOGO-SPEC.md`
- [ ] **G-L1** Rail/header lockup is the **Odin Infinity** mark (two rounded-square ∞ links +
  Valknut knot), **not** the v2 8-Crest and **not** the early placeholder glyph.
- [ ] **G-L2** Mark is **blue-only** — `#93B7FF` (light link), `#3D7DFF` (primary), `#2E4E8C`
  (dark link/done), `#4D8BFF` (bright centre). No other hue in the mark.
- [ ] **G-L3** Links carry the light→dark diagonal gradient (top-left light → bottom-right dark).
- [ ] **G-L4** Header lockup wordmark is the **K8squad** logotype (azure numeral 8), sub-label
  "operator console".
- [ ] **G-L5** Favicon / app-icon uses the **compact glyph** (`odin-infinity-glyph.svg`) below ~48px,
  not the full mark. Favicon raster set = `branding/assets/logo-v12/favicon-*`.
- [ ] **G-L6** Mark stays crisp at the ~30px console-header size (use the glyph geometry, not a
  downscaled full lockup with chain/side boxes).

### 0.2 Palette & tokens (dark + light) — `00-visual-system{,-light}`
- [ ] **G-P1** Dark canvas `#0B1220`; single azure accent `#3D7DFF` (theme-invariant across dark/light).
- [ ] **G-P2** One accent only. Status hues are **reserved**: green (running/done), amber (paused),
  rose (blocked/fail), slate (idle), violet (memory). No decorative gradients, no AI-purple.
- [ ] **G-P3** Light mode **mirrors token roles** (not new hues): status hues darken for on-light
  contrast (green `#059669`, amber `#B45309`, rose `#E11D48`, slate `#64748B`, violet `#7C3AED`).
- [ ] **G-P4** One corner-radius scale: 6 chip · 8 control/input/button · 12–14 card · full for dots/avatars.
- [ ] **G-P5** Border-forward, low elevation — hairline borders over heavy shadows.

### 0.3 Theming T1–T7 (the ISI-2279 whole-shell theming contract, re-anchored to v12)
- [ ] **G-T1** Theme toggle swaps the **entire** shell (rail, header, canvas, cards), not per-component.
- [ ] **G-T2** Accent `#3D7DFF` is invariant; only neutrals + status tints remap.
- [ ] **G-T3** Every screen ships a `-light` sibling that is token-mirrored from its dark source.
- [ ] **G-T4** Mark renders correctly on both grounds (no dark-only fill assumptions).
- [ ] **G-T5** Status pills keep AA contrast on their tinted grounds in both themes.
- [ ] **G-T6** Focus ring = visible 1.5px accent ring on every interactive element, both themes.
- [ ] **G-T7** No color-only signalling — every state = dot **+** shape/icon **+** text label.

### 0.4 Rail & header (shared chrome)
- [ ] **G-R1** Left rail carries the v12 lockup top-left; nav entries match the mock rail for the
  surface (global 8-entry rail on fleet screens; Project-rooted hierarchical rail on Project screens).
- [ ] **G-R2** `+ Compose` primary button pinned bottom of rail; context footer chip
  ("prod-euc1 · connected") below it.
- [ ] **G-R3** Header = breadcrumb/title + subtitle, search, `ns:` scope chip, principal avatar.

---

## 1. E8 — console shell (ISI-2180) · ref `01`–`21`, anchor `08-fleet-dashboard`

The shell is the frame every other surface mounts in. Conformance = the running Next.js console
matches the mock chrome + the fleet landing.

- [ ] **E8-1** Shell renders the **global 8-entry rail** (Dashboard · Overview · Runs · Builds ·
  Discussion · Projects · Agents · Credentials) with the v12 lockup — ref `08-fleet-dashboard`.
- [ ] **E8-2** Fleet dashboard stat tiles (Active runs · Squads · Artifacts 24h · Paused · Success 24h)
  match layout + the reserved-hue value colors — ref `08`.
- [ ] **E8-3** "Live assignments" table (agent ↔ work item ↔ project, status pill, elapsed, trace link)
  with the **LIVE · SSE** marker + run-activity sparkline — ref `08`. SSE is the one EventSource (8.2).
- [ ] **E8-4** "Credential health" mini-bar (Valid/Expiring/Expired) + "Recent artifacts" +
  "Namespaces" side panels — ref `08`.
- [ ] **E8-5** "Live & recent runs" list with progress bars + status pills (Running/Paused/Failed) —
  ref `08`.
- [ ] **E8-6** Runtime-type badges on agents (Claude Code / OpenCode / Ollama adapter / Hermes) render
  as the mock chips — ref `08`, `09`.
- [ ] **E8-7** Theme toggle produces the `-light` variant of the shell 1:1 (G-T1..T7).
- [ ] **E8-8** Read-only scope guard holds — no IDE affordances; artifacts/build views are projections
  (ref `03`, `06`), never editors (FR-F scope guard R6).
- [ ] **E8-9** Every route's title/breadcrumb/subnav matches its mock (screens `01`–`21`).

---

## 2. E10.3 — discussion room in console (ISI-2704 / ISI-2695) · ref `07-discussion-room`

The room is a **collab surface, not a coordination channel**. The mock encodes that in how messages
are rendered.

- [ ] **E10-1** Room header = `Discussion › #<id> <title>`, subtitle "Coordination thread — agents
  comment on the shared work item"; stage/message count top-right — ref `07`.
- [ ] **E10-2** Thread messages carry **author · runtime** (e.g. "Reviewer · OpenClaw") + timestamp +
  a **provenance badge** per message: `COMMENT` / `HANDOFF` / `MEMORY` / `ARTIFACT` — ref `07`.
- [ ] **E10-3** Provenance badge colors follow the reserved map: memory = violet, artifact = green,
  handoff = slate/neutral, comment = accent — ref `07`.
- [ ] **E10-4** Referenced memory/artifact chips render inline under the message (e.g.
  `memory · refunds use idempotency key`, `artifact · refund-fix.diff (+42 −11)`) — ref `07`.
- [ ] **E10-5** Right column: **Participants** (status: Done/Active/Queued as dot+label), **Work item**
  (progress + stage path checkout → memory → tests + Run link), **Referenced artifacts** — ref `07`.
- [ ] **E10-6** Operator note composer at the bottom ("Add an operator note to the coordination
  record…" + Comment button) — a note, not a dispatch — ref `07`.
- [ ] **E10-7** No coordination affordances in the room UI — no claim/handoff/dispatch buttons; the room
  is append-of-record only (Story 10.4 guardrail). Ref `07` + `22`.
- [ ] **E10-8** `-light` variant token-mirrored (G-T3).

---

## 3. E11.6 — synced-state console + CI-failure auto-post (ISI-2741) · ref `22-scm-synced-state` (NEW)

The closed loop **sync → dashboard tiles (8.8) → room (10.3)**. The mock makes the two AC guards
visible; the build must preserve them structurally, not just visually.

**AC1 — PR/CI tiles are a read model over the mirror, degrading per-tile**
- [ ] **E11-1** PR/CI tiles (Open PRs · Checks passing · Last sync) render from the
  `scm_pr_mirror` / `scm_check_run` mirror through the **8.8a composed payload** — **no new
  aggregation service, no rollup store** — ref `22` tiles row.
- [ ] **E11-2** An **unsynced** repo degrades **that tile to empty** (dashed "empty" state), never a
  whole-dashboard failure — ref `22`, the `orders-api · repo unsynced · tile empty` tile.
- [ ] **E11-3** Tile values use reserved hues (failing checks = rose, fresh sync = green) + dot, not
  color-only — ref `22`.
- [ ] **E11-4** Provenance banner states the read-model discipline ("mirror … · read model over 8.8a
  · no new store · per-tile degrade") + `provenance: github` chip — ref `22`.

**AC2 — CI failure auto-posts a provenance-tagged message to the Project room**
- [ ] **E11-5** On a `check → failure` transition, one message renders in the Project room authored by
  a **system/bot principal** ("github-sync · bot · system") with an **`EXTERNAL · CI`** badge —
  ref `22`, the accented (amber) card.
- [ ] **E11-6** The auto-post is visually marked **UNTRUSTED-EXTERNAL / `external_origin`** and reads
  as *external attributable context, never a trusted instruction* — ref `22` "Trust boundary" panel.
- [ ] **E11-7** It links the failing check + PR + **correlated Run** (chips: `check · refund-suite →
  failure`, `PR #341 · head 9f2c1a`, `correlated Run #142`) — ref `22`.

**AC3 — the auto-post is an observer, never a coordination path (§6 no-P2P)**
- [ ] **E11-8** The room UI exposes **no** claim / handoff / dispatch / transition-work-item / write-
  custody control on the auto-post — its only affordance is being a message — ref `22` "Trust
  boundary" (✕ claim/handoff/dispatch · ✓ append one room message = only capability).

**AC4 — idempotent + echo-safe**
- [ ] **E11-9** UI does not double-render a redelivered failure; the surface reflects **one** post per
  `(check_external_id, head_sha, conclusion)` — ref `22` "Idempotent + echo-safe" panel.
- [ ] **E11-10** "Closed loop — one direction" is honored: sync → dashboard → room ends at the room as
  information; the UI never surfaces a path curling back into coordination — ref `22`.
- [ ] **E11-11** `-light` variant token-mirrored (G-T3) — ref `22-scm-synced-state-light`.

---

## 3.5 Responsive viewports — website-fidelity (ISI-2757) · ref `Rvp-shell` · `Rvp-discussion` · `Rvp-synced`

Board directive (ISI-2170, 2026-08-17): *"the E8 mocks were approved and used for version 0 of our
website — the mocks need to follow the mocks used in our website: browser and mobile/tablet
rendering."* The website (source of truth, `website-mocks/`) frames the console inside a **browser
chrome** and advertises *"Full console on desktop, tablet, mobile."* Each in-flight surface now has a
**viewport matrix** mock — **browser/desktop · tablet 768px · mobile 375px**, dark + light — pinning the
reflow the build must match. Reference sheets (dark + `-light` sibling):

| Surface | Matrix sheet | Owner |
|---------|--------------|-------|
| E8 console shell (fleet content) | `Rvp-shell{,-light}` | ISI-2180 |
| E10.3 discussion room | `Rvp-discussion{,-light}` | ISI-2704 |
| E11.6 SCM synced-state | `Rvp-synced{,-light}` | ISI-2741 |

**Breakpoint contract (applies to every surface mounted in the shell)**
- [ ] **R-1 Desktop (≥1280px).** Full **icon+label left rail** + top bar + multi-column content. On the
  website it is shown inside a **browser frame** (traffic-light chrome + URL bar) — the console's own
  desktop route is the same layout without the frame — ref each `Rvp-*` desktop column.
- [ ] **R-2 Tablet (768px).** Rail **collapses to an icon-only rail** (~48–56px, no labels); content
  reflows to **2 columns** (KPI/tiles 2-up); top bar keeps title + avatar, drops inline search into an
  icon — ref each `Rvp-*` tablet column.
- [ ] **R-3 Mobile (375px).** **No left rail.** Top **app-bar** = hamburger (☰) + **Odin mark** + title +
  avatar; content is a **single column**, cards full-bleed; primary nav becomes a **bottom tab bar**
  (Home · Runs · Rooms · Projects · More) with the active tab accent-underlined — ref each `Rvp-*`
  mobile column.
- [ ] **R-4 Brand at every breakpoint.** Odin Infinity v12 mark renders at desktop, tablet **and**
  mobile; on mobile the wordmark may collapse to the **mark alone** — never absent, never the v2 crest.
- [ ] **R-5 One accent + status law survive reflow.** Single accent `#3D7DFF` at all sizes; every Run/CI
  state stays **dot + text label** (never color-alone) even in the compact mobile cards (G-T7).
- [ ] **R-6 Density, not truncation.** Operator density preserved; data-dense tables **scroll
  horizontally** on small screens rather than dropping columns/meaning (matches doc §5 a11y).
- [ ] **R-7 Surface-specific reflow holds the guards.** The E11.6 **degraded tile** stays a per-tile
  empty state at every width (never a full-dashboard failure); the E11.6 **CI-failure auto-post** stays
  a single `EXTERNAL · CI` observer card with **no** claim/handoff/dispatch affordance at every width;
  the E10.3 room stays append-of-record with an operator-note composer at every width.
- [ ] **R-8 `-light` parity per viewport.** Each matrix sheet ships a token-mirrored `-light` sibling;
  the reflow is identical, only neutrals + status tints remap (G-T3).

---

## 4. Divergence flags (raised for Architect + implementers)

- **D1 — Website vs repo mocks (source-of-truth reconciliation).** The board names *the mocks
  published on our website* as the intended look. The **live website rollout of v12 is a separate
  lane (ISI-2516)** per `LOGO-SPEC.md` §Rollout; the in-repo `website-mocks/` (landing/docs/sdk) have
  v12 applied. **Action:** confirm the live k8squad.io header lockup is v12 (not still v2/placeholder);
  if the live site lags, ISI-2516 is the owner. No console-mock divergence found.
- **D2 — E11.6 had no mock before this pass.** Screen `22` is **new** (authored under ISI-2749). It is
  the first pixel target for the 11.6 build; the Architect should confirm the tiles route (Project
  dashboard vs Discussion tab) — the mock places the synced-state tiles + room on the **Project →
  Discussion** surface, matching "auto-post into the Project room (10.3)".
- **D3 — "Epic 8 DONE" = specs + SVG mocks, not shipped UI.** Real console frontend begins at the
  ISI-2180 shell (PR#61). These conformance rows are the gate the *build* is checked against; they are
  **not** claims that the UI already matches.
- **D4 — Leftover 8-Crest defs.** `apply-odin-infinity.py` leaves the now-unused `ringTop/ringBot`
  gradient defs in ~38 SVGs (harmless, documented). Not a divergence; noted so a reviewer greping for
  "crest" isn't alarmed.

---

## 5. Handoff

| Surface | Build owner (issue) | Mock reference | Checklist |
|---------|--------------------|----------------|-----------|
| E8 console shell | ISI-2180 | `08` + `01`–`21` + `Rvp-shell` | §0 + §1 + §3.5 |
| E10.3 discussion room | ISI-2704 / ISI-2695 | `07` + `Rvp-discussion` | §0 + §2 + §3.5 |
| E11.6 synced-state + auto-post | ISI-2741 | `22` (new) + `Rvp-synced` | §0 + §3 + §3.5 |
| Responsive viewports (all three) | ISI-2757 | `Rvp-*{,-light}` | §3.5 |
| Console-surface specs | Architect (ISI-2748) | this doc | §4 divergences |

**Regeneration:** edit `gen-22-scm-synced-state.py` (or any `gen-*`) → re-run → then
`python3 apply-odin-infinity.py images/*.svg` (idempotent v12 pass) → render PNGs at 2160×1350.
The responsive matrix sheets regenerate self-contained: `python3 gen-responsive-viewports.py`
(imports only the console token maps + Odin mark; writes `images/Rvp-*.{svg,png}` in dark + light).
