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
> architecture, nine key-screen mocks, and a coherent visual system — all scoped to
> **legibility + composition**, never an IDE (FR-F scope guard · risk R6).
>
> **What this is not.** Not a component library, not final pixel spec, not a framework choice.
> Frontend stack and SSE wire format are **Architecture's** call (§10.5 → Phase 3). This doc
> constrains the *look and the flows*, not the *how*.

Primary personas (PRD §5): **Priya — Platform Engineer** (operator; needs legibility + kill) and
**Sam — Squad Author / Tech Lead** (needs compose + live stream + artifact inspection).

---

## 0. Revision v2 — logo + light mode (ISI-2150, CEO feedback 2026-08-11)

Two CEO changes are applied here:

1. **v2 logo embedded.** The header/rail brand glyph is now the **selected K8squad 8-Crest v2**
   mark (two stacked rounded-square squad-containers + coordinator waist node — the approved mark
   published to `assets/logo/` · `branding/` on the `assets/k8squad-logo` branch, Henrik-approved
   ISI-2138). The small-size header lockup uses the *simplified* crest geometry (rings + coordinator
   + lead nodes) proven legible at favicon scale. Swapped into all six screens, both themes.
2. **Light-mode variants shipped.** Every screen now has a `*-light.svg/png` sibling. Light mode
   **mirrors the same token roles** (not new hues) — see the two visual-system sheets:
   `00-visual-system.png` (dark) and `00-visual-system-light.png` (light). Status semantics are
   preserved with darker on-light hues (green `#059669`, amber `#B45309`, rose `#E11D48`, slate
   `#64748B`, violet `#7C3AED`) over light tints, always paired with dot + label (a11y unchanged).

Delivered this revision: `00`–`05` in dark (logo-swapped) **and** light. The rail on `00`–`05`
now also carries the new **Dashboard / Builds / Discussion** entries (see §0b), so the menu is
consistent across the whole set.

---

## 0b. Revision v3 — three new screens (ISI-2160, CEO request)

The three new CEO-requested screens now ship, each in **dark + light**, on the same locked system
(dark canvas `#0B1220` + single azure accent `#3D7DFF`; reserved status hues; v2 8-Crest rail lockup;
light mode mirrors token roles). Light siblings are generated from each dark SVG by the audited
dark→light token map (accent `#3D7DFF` is theme-invariant; status hues darken for on-light contrast).

| # | Screen | File | Surface |
|---|--------|------|---------|
| 06 | Build browser | `images/06-build-browser.png` | Browse/inspect produced builds + artifacts, read-only |
| 07 | Discussion room | `images/07-discussion-room.png` | Coordination record as a threaded room (not chat · I4) |
| 08 | Fleet dashboard | `images/08-fleet-dashboard.png` | Fleet-level stat tiles + trends over squads/runs |

**Rail evolution.** The left rail now carries **Dashboard** (new fleet landing, top of rail), **Builds**,
and **Discussion** (both Runs-adjacent surfaces) — an **8-entry rail** (Dashboard · Overview · Runs ·
Builds · Discussion · Projects · Agents · Credentials). This revision re-rendered **all** screens
(`00`–`08`, both themes) against the new rail, so every mock shows the same menu.

---

## 0c. Revision v4 — team organization diagram (ISI-2150, CEO request 2026-08-11)

A 10th screen ships in **dark + light** on the same locked system — the **team/squad org chart**
(Paperclip-style). It is rendered as the destination for the existing **Agents** rail entry (no new
rail item — the locked 8-entry rail is preserved, and "Agents" finally gets a real surface).

| # | Screen | File | Surface |
|---|--------|------|---------|
| 09 | Team organization | `images/09-team-organization.png` | **Team → Agent → Role** lineage tree; live status; click-through to agent detail |

**What it shows.** A three-column lineage tree — **Teams** → **Agents** → **Roles** — with the
selected parent connected to its children by accent elbow connectors, plus a click-through **agent
detail** panel on the right. Every node carries real-time status (**idle / running / blocked /
paused**) as a **dot + label** (a11y unchanged), the agent's **runtime type** badge (`AgentRuntime.type`
— e.g. Claude Code / OpenCode / Ollama adapter), and **role** badges. Detail panel surfaces runtime, namespace, bound roles, skills,
credential ref, current run, and the data provenance: **Team / Agent / Role CRDs (read-only)** with
**live status via SSE**. Source: `gen-09-team-org.py` (token-mirrored dark/light generator).

**Click-through pairing (ISI-2161 ⇄ ISI-2162).** The detail panel's primary action now reads
**"Open agent detail · runs + logs →"** (sub-caption *run history · tool-call · LLM · build · traces*),
naming its destination explicitly: the **Agent detail — run history + logs** screen (screen 11,
ISI-2162, CEO 2026-08-11). This screen is the *entry point* (current Run at a glance); screen 11 is the
*drill-down* (Run list with status/duration/tokens → tabbed logs → OTel trace links → live SSE tail on
active Runs). The two are the org-chart→detail pair the CEO requested. Screen 11 itself is built under
**ISI-2162** and lands in the ISI-2150 mock revision as the 11th screen.

---

## 0d. Revision v5 — live-ops screens (ISI-2150, CEO additions 2026-08-11)

Two more CEO changes ship here, both on the same locked system. The shared rail / top-bar / token
scaffolding is now factored into `console_kit.py`, so every new screen renders identically in
dark + light (screens `00`–`09` keep their existing generators/SVGs untouched).

1. **Dashboard live-assignments panel** (comment 46ed0fd5). Screen `08` is re-rendered with a **Live
   assignments** hero panel — the real-time *"who's doing what right now"* view: **agent ↔ work item ↔
   project** mapping, per-agent status (running / paused / blocked) as **dot + label**, elapsed time,
   and a per-row **OTel-trace** link; live rows pulse (SSE). It preserves the KPI tiles, the live/recent
   runs list, and the right column (Credential health · Recent artifacts · Namespaces); the standalone
   24h run-activity chart is folded into a compact header sparkline so no approved signal is lost. Pairs
   with the org diagram (screen 09 · ISI-2161) and the run stream (screen 02 · FR-F2) for the full
   live-ops picture. Source: `gen-08-fleet-dashboard.py`.
2. **11th screen — Agent detail: Run history + logs** (comment 26d37213 · ISI-2162 · Paperclip pattern).
   New screen `10` — see §3.9.

| # | Screen | File | Surface |
|---|--------|------|---------|
| 10 | Agent detail — runs + logs | `images/10-agent-runs.png` | **Run history** (status/duration/tokens) + per-Run **tabbed logs**; live SSE tail; OTel-trace per Run |

### 3.9 Agent detail — Run history + logs — `images/10-agent-runs.png` · ISI-2162 · Paperclip pattern
The agent drill-down reached from the org diagram (§0c) and the **Agents** rail entry. An **identity
card** (avatar · runtime · namespace · bound roles · live status · 142-runs / 96%-success / 24h-tokens
quick stats) sits over a two-pane split. **Left — Run history:** a scannable Run list, each row a
**status pill + Run id** (mono), **duration** and **token** counts, relative time, and the work item;
the active Run is accent-selected. **Right — Run drill-down:** a Run header (status · SSE, duration ·
tokens · model, and **"Open OTel trace ↗"** with the trace/span id), a **tab bar** (All · Task · Tool
calls · LLM · Build · Errors, each with a count) over a monospaced **log stream**. Each log line is
kind-badged: **TASK** (work-item checkout), **TOOL** (tool calls + results), **LLM** (model step with
**▲ prompt / ▼ completion token counts** + latency), **BUILD** (build output, links to the **Build
browser** §3.6), **ERROR** (assertion + stack trace), plus **NOTE** (coordination record) and **MEM**
(knowledge-record write, violet — the two-records principle, §6 PRD). The final active-Run line carries
a **live-pulsing head** — the SSE log tail — and the footer restates it: *"live SSE log tail — streaming
while the Run is active."* Per the Gate-2 Architect data-contract (arch r12 · §8 Run lifecycle · §6.5
coordination audit · §12.1 scope), this page is a pure **read model**: **read-only, Team-scoped** (an
identity-card chip and the header state it), and Run **status & kill stay in the existing Run controls —
never on this page** (no mutate / claim / kill affordance). The work-item / claim / handoff / artifact /
status trail is a read-only, upsert-keyed projection of the coordination audit (§6.5). Source:
`gen-10-agent-runs.py` (token-mirrored dark/light generator).

---

## 0e. Revision v6 — team configuration / actual organization (ISI-2153, CEO review 2026-08-12)

CEO ask (Henrik, ISI-2153 review): *"we need a team configuration screen, where you can see your
actual organization."* A **12th screen** ships in **dark + light** on the same locked system —
`11-team-configuration` — populated from the **live Agent registry** (not sample data): the real
company roster of **15 active agents across 5 teams + 15 OpenCode backups**, so it reads as *your
organization*, not a demo.

| # | Screen | File | Surface |
|---|--------|------|---------|
| 11 | Team configuration | `images/11-team-configuration.png` | Real company roster — **team → agent → role → runtime**; read-only, live status |

Each team is a card (**Leadership · Engineering · Research · Product & Content · Platform & Ops**);
each agent row shows **name · role · runtime badge** with a live status dot. The **RUNTIMES** panel
surfaces all four adapters actually in the company — **Claude Code** (`claude_local`, the azure/primary
chip), **OpenCode** (`opencode_local`, the 15 backups), **Ollama** (`ollama_agent` · Saver), **OpenClaw**
(`openclaw_gateway` · Alfred) — plus **Process** (GitHub Monitor / CI) — and notes the **1:1 OpenCode
backup failover**. It is a pure **read model** (R6): add / assign / retire happens in **Compose**, not
here — live status via SSE. This complements the abstract **team-organization hierarchy** diagram
(screen 09, §0c): 09 shows the Team→Agent→Role *pattern*; 11 shows the *actual* org for real config
legibility. Source: `gen-11-team-config.py` (token-mirrored dark/light generator).

---

## 0f. Revision v7 — Settings / OTLP exporter config (ISI-2288, CEO 2026-08-12 · Gate-2 Architect §13/§17.2/ADR-029)

CEO ask (Henrik, ISI-2288): *"a Settings page where users define their OTLP exporter URL (where to send
logs, metrics, traces), plus a general settings surface."* The Gate-2 Architect data-contract scopes it
as a **general settings surface whose first pane is OTLP exporter config** — a **read-write form over the
`OTelConfig` CRD** (ISI-2289), written via the **apiserver BFF (no direct kube)** and **RBAC-gated** to
authorized operators. A **13th screen** ships in **dark + light** on the same locked system.

| # | Screen | File | Surface |
|---|--------|------|---------|
| 12 | Settings — OTLP exporter | `images/12-settings.png` | Per-signal exporter form (traces/metrics/logs) over the `OTelConfig` CRD; form ⇄ live YAML; RBAC-gated; opt-in default |

**Layout — three columns.** (1) A **settings sub-nav** groups the surface: *TELEMETRY* (OTLP Exporter ·
Sampling defaults), *PLATFORM* (General · Namespaces · Appearance), *ACCESS & SECURITY* (Operators & RBAC
· Secrets) — OTLP Exporter is the active first pane. Entry point is a **Settings gear** in the rail
footer (the locked 8-item primary rail is unchanged). (2) The **form** mirrors the CRD **per signal** —
each with **endpoint**, **protocol** (`gRPC | HTTP` segmented control), **authentication**, **resource
attributes** (key=value chips), and **sampling**. (3) A **live `OTelConfig` YAML preview** (form ⇄ YAML,
like Compose / FR-F5) plus two guard notes: **RBAC-gated** (apiserver BFF, no direct kube) and
**Secrets referenced, never stored**.

**Three exporter states in one view** encode the data-contract:
- **Traces** — *Configured*, form fully **expanded** (endpoint `otel-collector.observability.svc:4317`,
  gRPC, sampling `0.10`, resource attrs, auth).
- **Metrics** — *Configured*, **collapsed** one-line summary with an *Edit* affordance.
- **Logs** — the **empty / first-run state** (dashed card, *Not configured*): *"Logs stay in-cluster
  until you add an exporter"* + `+ Configure exporter`. This is the **opt-in default** the contract
  calls for — telemetry stays in-cluster until an exporter is added (header sub-line states it too).

**Secret safety (S-class).** Authentication is a **Secret *reference*** (`secret://otlp-headers`) shown
with a lock glyph and the line *"References a Secret — the token is never shown or stored here."* The UI
references a Secret; it never renders or persists a raw token. The write path (`Save configuration →
OTelConfig` via apiserver BFF) depends on the CRD (ISI-2289); the mock proceeds in parallel. Source:
`gen-12-settings.py` (self-contained token-mirrored dark/light generator).

---

## 0g. Revision v8 — Project-rooted navigation IA (ISI-2291, CEO 2026-08-12 · Stories 8.13 + 8.14)

CEO directive (Henrik, 2026-08-12): *"the console must present a **Project-rooted navigation IA**, not a
flat screen list."* The nav rail is **re-architected from a flat 8-item list into a grouped hierarchy** —
the **Project** is the scoping root because it already is in the `project_id`-scoped data model (Runs,
tickets, discussion, builds all sit under the `Project` CRD, §6.1/§5.1). Two screens ship in **dark +
light** on the same locked system. Existing screens (`00`–`12`) are **re-parented unchanged** — only the
nav wrapping / routing changes (App Router nested layouts).

| # | Screen | File | Surface |
|---|--------|------|---------|
| 13 | Navigation IA — hierarchy map | `images/13-nav-ia.png` | The new rail (real) + an annotated map of the tree: which nodes are **global** vs **project-scoped**, the **context selector**, the **breadcrumb** and **sub-nav** patterns |
| 14 | Project → Tickets | `images/14-project-tickets.png` | Work items scoped to the selected Project — master-detail: list (status · assignee · counts) + detail (provenanced comments · artifacts · checkout/holder · linked Runs 8.2 / builds 8.7) |
| 15 | Users & Roles (admin) | `images/15-users-roles.png` | **Console-user RBAC** (ISI-2307): user list · **access-level** assignment (Admin/Operator/Viewer) · **project-membership matrix**. Admin-only. See `rbac-nav-ia-revision.md` |
| 16 | Adaptive navigation | `images/16-adaptive-nav.png` | **Admin vs non-admin** rails side by side (Dashboard + Users&Roles are admin-only; settings read-only for non-admin) + the **authorized-projects selector** rule |
| 17 | Login (desktop) | `images/17-login.png` | **SSO / OIDC** sign-in — brand panel + sign-in card; console stores no human password; access from directory groups |
| 18 | Mobile — RBAC | `images/18-mobile-rbac.png` | Mobile **SSO login flow** + **role-adaptive bottom nav** (admin gets a *Manage* tab; non-admin sees authorized projects only) |

**The new rail (`console_kit_ia.py`).** Three groups replace the flat list:
- **GLOBAL** — **Dashboard** (fleet, 8.8) · **Overview** (squad, 8.1) · **Agents** (org diagram 8.10 +
  agent detail 8.11, with an inline **`filter ▾`** chip — filterable by squad / project). These read
  **across the fleet** and are **not** project-scoped.
- **PROJECT** — a **context selector** (azure-tinted dropdown, `active project · switch ▾`) sets the
  active Project; its node **expands** to indented sub-items joined by a connector spine: **Build** (8.7)
  · **Tickets** (8.14) · **Runs** (8.2) · **Discussion** (10.3) — **all scoped to the selected Project**.
- **SETTINGS** — **Configuration** (OTelConfig, 8.12) · **Credentials** (8.6).

**Breadcrumb + sub-nav.** The top bar always shows `📁 project ▾ › section` (the Project chip is a
quick-switch). The selected Project's four sub-sections are also surfaced as a **tab strip**
(Build · Tickets · Runs · Discussion) at the top of the content area, mirroring the indented rail
sub-items. Both patterns are documented as live callouts on screen 13.

**Project → Tickets (8.14, new content screen).** Fills the one Project sub-item without an existing
screen. **Read + navigate only** — CRD compose/edit stays in Compose (8.5); **claim / coordination stay
server-side (R6)**. The detail pane reads the **Epic 2 coordination record** (§6.1): append-only
**provenanced comments** (human / agent / **SCM** — the SCM post carries a violet commit-provenance
chip, mirroring the two-records / memory tag), **artifacts**, **checkout/holder + lease** state, and
**links to each ticket's Runs (8.2) and build outputs (8.7)**. Source: `gen-13-nav-ia.py` +
`gen-14-project-tickets.py` (both import `console_kit_ia.py`, the hierarchical-rail kit; token-mirrored
dark/light).

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
├─ Dashboard       fleet-level stat tiles + trends over squads/runs (ns: all)              ← new · screen 08
├─ Overview        squads at a glance — Teams × Projects × live Run status   ← FR-F1  (Priya lands here)
├─ Runs            live + historical Runs; open one → Run detail
│   ├─ Live stream   SSE coordination timeline (checkout · comment · artifact · handoff)  ← FR-F2
│   ├─ Artifacts     inspect handoff outputs, read-only (diffs, reports, comments, logs)   ← FR-F3
│   ├─ Builds        browse produced builds + their artifacts, read-only                   ← new · screen 06
│   ├─ Discussion    coordination record as a threaded room (not chat · I4)                ← new · screen 07
│   └─ [Kill Run]    2-click cancel from the Run header                                    ← FR-F4 (S2)
├─ Projects        repos + workspaces (Project CRD)
├─ Agents          agents / runtimes / roles / skills registry
├─ Credentials     per-agent BYO token state + "paused on expired token" signal            ← FR-F6 (S10)
└─ + Compose       author Project / Team / Agent / Role / Skill (form ⇆ live CRD YAML)      ← FR-F5 (S3)

Top bar:  context switcher (kube-context)  ·  namespace / tenant selector  ·  global search  ·  identity
Rail footer:  connected cluster context (green = reconciling)
```

**Navigation model.** The rail's *object* entries map to the CRD kinds an operator reasons about
(Overview → Team, Projects, Agents, Credentials); **Dashboard, Runs, Builds** and **Discussion** are
the verbs/views over them. Runs are the verb; everything else is a noun. Search spans squads, runs, and
artifacts. The namespace selector
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

### 3.6 Build browser — `images/06-build-browser.png`  · cross-run artifact catalog
A read-only catalog of **every artifact produced across Runs**. Left: a **facet rail** — filter by
**Type** (diff / report / file / log / image), **Squad**, and **Status**, each with live counts and
checkboxes (Diff + payments-review pre-selected). Main: a **build table** where each row is a produced
artifact — a kind-badged icon, artifact name in mono + one-line metric, a **type** chip, the **squad**,
the **Run** ref (mono), the **producer** (agent · role), and a **status pill** (Passed / Failed /
Superseded). The footer holds the same R6 guard as §3.3: *"read-only catalog — opening a build shows the
artifact inspection view; KSquad never mutates a produced artifact (scope guard · R6)."*

### 3.7 Discussion room — `images/07-discussion-room.png`  · two-records principle I4
The coordination discussion surface — and deliberately **not a chat**. It renders one work item's
*coordination record* as a **thread**: a header (work-item id, status pill, stage + message count) over
posts, each an agent (avatar + actor · role), timestamp (mono), body, and an event **kind tag**
(`COMMENT` / `HANDOFF` / `MEMORY` / `ARTIFACT`). A **memory** write is tagged violet with an inline
`memory · <fact>` chip — routed to the *knowledge record*, distinct from coordination (§6 PRD · I4); an
**artifact** post carries an inline artifact chip. Right rail: **participants** (per-agent state),
**work-item** progress, and **referenced artifacts**. The bottom bar is an **operator-note** affordance
— an operator annotation onto the durable coordination record (*"add an operator note to the coordination
record"*), explicitly the human oversight channel, **not** free-form agent chat: agents emit coordination
events; I4 is preserved.

### 3.8 Fleet dashboard — `images/08-fleet-dashboard.png`  · fleet operator view · **v5 (ISI-2150)**
The fleet landing (`ns: all`, top of rail). A row of **KPI tiles** — **Active runs** (pulsing) ·
**Squads** · **Artifacts · 24h** · **Paused** · **Success · 24h**. Below sits the **Live assignments**
hero panel (v5 · CEO 2026-08-11 · §0d) — the *"who's doing what right now"* view: **agent ↔ work item ↔
project** rows with per-agent status (dot + label), elapsed time, and an OTel-**trace →** link; live
rows pulse (SSE). Its header carries a compact 24h **run-activity sparkline** (the current hour pulses
green — the old standalone bar chart, folded in). Under it, the **live & recent runs** list (status
pill, Run id, squad · repo, one-line note, progress bar, Open →). The right column stacks **Credential
health** (a valid / expiring / expired stacked bar + counts), **Recent artifacts**, and a **Namespaces**
summary. Motion is live-only (Active-runs tile · running assignment dots · current-hour bar pulse);
every status still pairs colour + label. Source: `gen-08-fleet-dashboard.py`.

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
Epics (this doc's nine screens map cleanly to console stories under Theme F). Non-blocking to the CEO
gate on ISI-2118 per §11.4.
