---
title: Operator-console UX & visual direction — KSquad
author: Graphic Designer (IsItObservable Labs)
date: 2026-08-10
status: draft-for-architecture
source_ticket: ISI-2126
feeds: PRD FR-F (ISI-2118 §9.6) → Phase 3 Architecture → Phase 4 Epics
inputs:
  - docs/bmad/02-prd.md          # §5 personas, §9.6 FR-F, §10.5 NFR-USE2, §11.4
  - docs/bmad/01-brainstorming.md # Theme F
non_blocking: true               # parallel to the CEO gate on ISI-2118; not a blocker
---

# KSquad Operator Console — UX & Visual Direction

> **What this is.** The UX/visual direction the PRD delegated (§11.4, NFR-USE2). It gives
> Architecture and Epics a concrete target for the "polished UI/UX" mandate: an information
> architecture, five key-screen mocks, and a coherent visual system — all scoped to
> **legibility + composition**, never an IDE (FR-F scope guard · risk R6).
>
> **What this is not.** Not a component library, not final pixel spec, not a framework choice.
> Frontend stack and SSE wire format are **Architecture's** call (§10.5 → Phase 3). This doc
> constrains the *look and the flows*, not the *how*.

Primary personas (PRD §5): **Priya — Platform Engineer** (operator; needs legibility + kill) and
**Sam — Squad Author / Tech Lead** (needs compose + live stream + artifact inspection).

---

## 1. Design principles

The console is an **operator surface**, not a marketing site or a playground. Five rules, applied to
every screen (rendered on the visual-system sheet, `images/00-visual-system.png`):

1. **Legibility over decoration.** A NOC surface: calm, dense, high-contrast, scannable at a glance.
   Priya's #1 need (brainstorming Theme F) is *"what exists, what's running, what did it produce."*
2. **One accent, reserved status hues.** A single brand/interactive accent (azure `#3D7DFF`). The
   status palette (green/amber/rose/slate) is **functional and reserved** — it never appears as
   chrome, so a colored dot always *means* a Run state.
3. **Mono for anything you could `kubectl`.** CRD YAML, Run IDs, timestamps, `secret://` refs and
   logs are monospaced. The console **mirrors** CRDs, it never hides them (supports S3: author via
   console *or* YAML).
4. **Motion means "live."** The only animation is the SSE pulse on running Runs / streaming events
   (FR-F2). No decorative motion. If it moves, it's telling you something changed.
5. **Read-only inspection, not authoring-of-code.** Artifacts and diffs are *inspected*, never
   edited in-console. This is the structural guard against R6 (console → IDE creep).

Taste dials for this product: **DESIGN_VARIANCE 3** (utility tool — convention beats novelty,
left-rail + content, no centered hero), **MOTION_INTENSITY 2** (live-only), **VISUAL_DENSITY 3–4**
(operators want density).

---

## 2. Information architecture

A persistent **left rail** (primary objects, all mapping to CRDs) + a **top bar** (context, search,
identity). Anti-center by construction — no hero, no wasted canvas.

```
KSquad · operator console
├─ Overview        squads at a glance — Teams × Projects × live Run status   ← FR-F1  (Priya lands here)
├─ Runs            live + historical Runs; open one → Run detail
│   ├─ Live stream   SSE coordination timeline (checkout · comment · artifact · handoff)  ← FR-F2
│   ├─ Artifacts     inspect handoff outputs, read-only (diffs, reports, comments, logs)   ← FR-F3
│   └─ [Kill Run]    2-click cancel from the Run header                                    ← FR-F4 (S2)
├─ Projects        repos + workspaces (Project CRD)
├─ Agents          agents / runtimes / roles / skills registry
├─ Credentials     per-agent BYO token state + "paused on expired token" signal            ← FR-F6 (S10)
└─ + Compose       author Project / Team / Agent / Role / Skill (form ⇆ live CRD YAML)      ← FR-F5 (S3)

Top bar:  context switcher (kube-context)  ·  namespace / tenant selector  ·  global search  ·  identity
Rail footer:  connected cluster context (green = reconciling)
```

**Navigation model.** The five rail objects *are* the CRD kinds an operator reasons about. Runs are
the verb; everything else is a noun. Search spans squads, runs, and artifacts. The namespace selector
is the multi-tenancy lens (OQ7 — squad = tenancy boundary); "ns: all" is the fleet view.

**Two-records fidelity.** The console visibly respects the PRD's two-records principle (§6): the
**Live stream** and **Artifacts** read the *coordination record* (work items, comments, checkout,
audit trail — FR-B1…B4); a distinct **memory** event tag (violet) marks writes to the *knowledge
record* (FR-E). They are never blurred into one "chat" — there is no chat surface, by design (I4).

---

## 3. Key screens

Mocks live in `images/` (SVG source + 1.5× PNG). Dark shell is the primary theme; a light mode mirrors
the same tokens.

### 3.1 Squad overview — `images/01-squad-overview.png`  · FR-F1 · Priya
The landing surface. A fleet stat strip (**Squads / Runs live / Paused / Failed-24h**) over a grid of
**Team cards**. Each card answers, without `kubectl`: which **Project**, which **runtimes**
(OpenClaw / Hermes), which **roles**, the current **Run status pill** (live-pulsing when running),
and a one-line **last-run** footer. Paused (amber) and Failed (rose) cards are unmissable in a scan —
Priya's legibility win (S2). This is the empty-state target too: a fresh install shows one
self-explanatory "create a Project → compose a Team" card (journey §5.1).

### 3.2 Live Run stream (SSE) — `images/02-run-stream-sse.png`  · FR-F2 · FR-F4 · Sam & Priya
Run detail. Header carries the live **status**, run meta, and the **Kill Run** button (rose, always
one click from the header → 2-click kill with confirm, satisfying FR-F4 / S2 / FR-A6). The main column
is the **SSE timeline** of coordination events, each tagged by kind — `CHECKOUT`, `COMMENT`,
`HANDOFF`, `MEMORY`, `ARTIFACT` — with actor (agent · role), timestamp (mono), and a live-pulsing head
on the streaming event. The right rail summarizes **agents** (per-agent state), **work items**
(stage progress), and a **credentials** mini-status that deep-links to §3.5. The header line states
the source explicitly: *"via coordination record (work items · comments · artifacts)"* — reinforcing
that the stream is durable state, not ephemeral chat (FR-B3).

### 3.3 Run artifact inspection — `images/03-artifact-inspection.png`  · FR-F3 · Sam
A master–detail: an **artifact list** (diff / comment / report / file / log, each with producer and a
one-line metric) beside a **read-only preview**. The default is a syntax-tinted unified **diff** with a
**provenance strip** (*work item #88 · produced by Fixer (Hermes) · 02:48 · sha*) — the audit trail
made visible (FR-B4 / D4 / NFR-OBS1). A **Download** action exports; there is deliberately **no edit
affordance**. The footer states the guard in words: *"apply happens in the repo PR the Fixer opened,
not here (scope guard · not an IDE)."* This is where R6 is held at the pixel level.

### 3.4 Compose flow — `images/04-compose-crd.png`  · FR-F5 · Sam (S3)
A stepper (**Project → Team → Agents → Roles & Skills → Review**) with a **split view**: a form on the
left, a **live, read-only CRD YAML mirror** on the right (`kubectl`-ready, the just-added agent
highlighted). Composing an Agent binds **runtime + role + skills + credential ref** — *no orchestration
code, only CRDs* (S3). The form and the YAML are declared to be *the same resource*; an author can work
in either and paste the result into `kubectl apply`. Credential is a **per-user Secret ref**
(`secret://sam/hermes-oauth`) with a live-valid dot (FR-G1, BYO subscription).

### 3.5 Credential / auth state — `images/05-credential-auth-state.png`  · FR-F6 · FR-G3 · Priya (S10)
The FR-F6 hero moment. A prominent **amber banner** — *"Run #139 paused — token expired"* — states the
graceful-pause contract in plain language (*coordination state preserved, resumes on refresh, nothing
lost*) with **Refresh token** + **How to (setup-token)** actions. Below, a per-agent **credential
table**: agent · runtime · `secret://` ref · token type · expiry · **status pill** · affected Run.
Expired/expiring rows are amber-tinted and sorted to attention. The footer restates the invariant:
*"KSquad never stores a shared master credential… expiry pauses the Run, never fails it opaquely
(FR-G3 · S10)."* Exact refresh UX is **gated on ISI-2112 evidence** (OQ1) — this screen shows the
*shape* of the signal, and is the surface that flexes when that evidence lands.

---

## 4. Visual system — `images/00-visual-system.png`

Full reference sheet for Architecture & frontend. Tokens below; light mode mirrors them.

### 4.1 Color

| Role | Token | Hex | Use |
|------|-------|-----|-----|
| Canvas | `canvas` | `#0B1220` | app background |
| Surface | `surface` | `#131D31` | cards |
| Raised | `surfaceRais` | `#1A2842` | popovers, avatars |
| Inset | `inset` | `#0E1626` | inputs, code, footers |
| Border | `border` | `#25324B` | 1px hairlines |
| Muted / Text / TextHi | `#7E8CA6` / `#B6C3D8` / `#E8EEF9` | text ramp |
| **Accent (single)** | `accent` | **`#3D7DFF`** | nav-active, primary btn, focus ring, links, brand |
| Accent text / bg | `#93B7FF` / `#16244A` | accent-on-dark text · accent tints |

**Status semantics — reserved, never chrome** (always paired with an icon + label; color never carries
meaning alone — a11y):

| State | Hex | Meaning |
|-------|-----|---------|
| Running / live | `#34D399` (pulsing) | Run active, streaming |
| Succeeded | `#34D399` (solid + check) | terminal OK |
| Paused / attention | `#FBBF24` | needs operator action (e.g. expired token) |
| Failed | `#FB7185` | terminal error (controller may be retrying) |
| Queued / idle | `#64748B` | pending / scheduled |
| Memory write | `#A78BFA` | knowledge-record event (distinct from coordination) |

No AI-purple gradients, no beige/brass; neutral Slate base + one azure accent (taste-skill compliant).
Violet appears **only** as the reserved memory-event tag, never as chrome.

### 4.2 Typography
- **Geist Sans** — UI, labels, headings. (Not default Inter — taste-skill rule.)
- **Geist Mono** — CRD YAML, Run IDs, timestamps, `secret://` refs, logs.
- Scale: 32 display · 22 H1 · 17 H2 · 14 body · 13 UI · 11 meta · 10 micro.
- *(Mocks are rendered with DejaVu as a metrics-close stand-in; production ships Geist.)*

### 4.3 Shape & components
- **One radius scale:** 6 chip · 8 control/input/button · 12 card · full for status dots & avatars.
- **Border-forward, low elevation** — hairline borders over heavy shadows (operator density, not glossy SaaS).
- Components shown: primary / secondary / destructive (Kill Run) buttons, focus-ringed input, chips,
  status pills (with live pulse), Team card, stat tile, stepper, master–detail, data table.

---

## 5. Accessibility & responsiveness (NFR-USE2)
- **Never color-only.** Every Run state = colored dot **+** icon/shape **+** text label.
- Body/UI text ≥ 13px; status pills carry a text label at 11.5px, AA contrast on their tinted grounds.
- Focus is a visible 1.5px accent ring on every interactive element (see the input on the system sheet).
- Target: desktop-first (operator workstation), graceful down to a narrow rail + stacked cards; the
  data-dense tables scroll horizontally rather than truncate meaning.

---

## 6. Traceability to FR-F & handoff

| FR / NFR | Where it lands |
|----------|----------------|
| FR-F1 squads at a glance | §3.1 Overview |
| FR-F2 live SSE progress | §3.2 Run stream |
| FR-F3 artifact inspection | §3.3 Artifacts (read-only) |
| FR-F4 cancel/kill | §3.2 header **Kill Run** (2-click) |
| FR-F5 compose CRDs | §3.4 Compose (form ⇆ YAML) |
| FR-F6 credential/auth state | §3.5 Credentials (paused-on-expiry banner) |
| FR-F scope guard (R6) | §1 principle 5, §3.3 read-only guard |
| FR-G1/G3, S10 | §3.5 (per-user Secret ref, graceful pause) |
| NFR-USE2 polished UI/UX | §4 visual system, §5 a11y |
| Two records (§6 PRD), FR-B/E | §2 IA, memory event tag |

**Open dependencies (not blockers):**
- **OQ1 / ISI-2112** — exact credential-refresh UX. §3.5 shows the signal shape; refresh flow finalizes
  when the token-longevity evidence lands.
- **Frontend stack, SSE wire format, auth/session** — **Architecture (Phase 3)**. This doc constrains
  look + flows only.

**Consumers:** Phase 3 Architecture (frontend approach, SSE contract, console↔API surface) and Phase 4
Epics (this doc's five screens map cleanly to console stories under Theme F). Non-blocking to the CEO
gate on ISI-2118 per §11.4.
