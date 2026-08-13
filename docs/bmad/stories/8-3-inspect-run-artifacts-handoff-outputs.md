# Story 8.3: Inspect Run artifacts + handoff outputs

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🔑 THIS IS THE ARTIFACT-INSPECTION SURFACE (FR-F3, UX `03-artifact-inspection`).** *"Given a
> completed/collecting Run, When I open artifacts, Then I can inspect artifact blobs + handoff outputs
> (from the coordination record)."* The load-bearing crux is **not** a pretty preview pane — it is that the
> surface is a **read-only projection of the durable, content-addressed `coord.artifact` rows** (§6.5): it
> **invents no store, no diff engine, no authZ path**. Every blob is read from the same content-addressed
> coordination record story **2.8** writes handoffs to and **8.7c** writes build snapshots to; every read
> goes **through the Next.js BFF** (§13 / ADR-013), is **scoped per-principal with existence-hiding `404`s**
> (NFR-SEC5, the **8.7d** gate — worktree blobs may carry the owner's BYO secrets), carries **server-stamped
> provenance** (FR-B4 / D4 / FR-I3), serves bytes **verified against the row's recorded `sha256`**, and is
> **bounded fail-safe** (8.7a caps). The pixel-level crux (UX §3.3): **no edit / apply / re-run / mutate
> affordance** rides the surface — *"apply happens in the repo PR the Fixer opened, not here (scope guard ·
> not an IDE)."* The **handoff** output is rendered as **advisory context** (Story 2.8): its 7 fields are
> shown, but **no custody / claim / fence affordance** rides it. Read AC1–AC7 literally: a surface that reads
> a re-invented store, streams the browser from the Go apiserver, serves an unverified blob, returns a
> same-Team non-owner's blob, hangs an Edit/Apply button on the preview, fabricates provenance client-side, or
> streams an unbounded blob has committed the FR-F3 defect, not shipped the feature.

## Gate status (read first)

This story carries **no spike gate**. It is pure console/BFF read-model wiring over settled seams. The
**durable content-addressed coordination record** is already decided (§6.5 audit / ADR-040 — *no bespoke
`run_trace`/artifact-viewer table*); the **content-addressed `coord.artifact` row** is already shipped by
Story **2.8** (handoff, `sha256`, `UNIQUE(work_item_id,run_id,kind)`) and extended by **8.7c** (build
snapshot); the **BFF choke point** is already decided (§13 / ADR-013); the **per-principal existence-hiding
gate** is already specified by **8.7d** (NFR-SEC5, `404`-not-`403`); the **fail-safe body caps** are already
established by **8.7a**; and the **read-only scope guard (R6)** is a first-principle of the whole console
(UX §1 principle 5, §3.3). This story **applies** those settled decisions as the concrete artifact-inspection
surface and pins them with a runnable falsification; it does not reopen them.

## Story

As **an operator (Priya) or squad author (Sam) opening a completed/collecting Run's artifacts**,
I want **to inspect the blobs the Run produced — diff / comment / report / file / log — and its structured
handoff outputs, all read from the durable coordination record, served through the BFF, scoped to me, with
their provenance visible and their bytes verified — and with no way to edit, apply, or re-run anything from
this surface**,
so that **I can see exactly what a squad produced and what it handed off, the audit trail is made visible at
the pixel level (FR-B4 / D4 / NFR-OBS1), the raw worktree content (which may hold my BYO secrets) is legible
only to me (NFR-SEC5), and the surface stays a read-only lens — apply happens in the repo PR the agent
opened, never here (R6 scope guard / not an IDE).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md`
  - **§9.6 FR-F3** — *"The console SHALL let an operator **inspect a Run's artifacts + handoff outputs** from
    the coordination record."* (MVP) — the requirement this story implements.
  - **FR-F1** (the squad/run views this opens from), **FR-F2** (the live SSE stream — Story 8.2 — that
    **deep-links** to this artifact surface by artifact/handoff event), **FR-B4 / FR-D4** (the coordination
    record is the audit trail; provenance is first-class), **FR-I3** (server-stamped provenance on every
    record), **NFR-SEC5** (per-principal read scope — worktree/artifact content is legible only to the owning
    principal), **NFR-OBS1** (the audit trail is queryable/visible).
  - **NFR-OBS3** — no per-item ids (`run.id`/`work_item.id`/`agent`/`user.id`) as metric labels; the
    inspection surface is legibility, never a consumption axis.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§6.5 (audit) / content-addressed `coord.artifact`.** Every produced artifact (diff/comment/report/file/
    log) and every handoff is a **durable, content-addressed row** in the coordination record (`sha256`,
    provenance-tagged). This is the **only** source this surface reads — **ADR-040**: there is **no** separate
    artifact-viewer store or bespoke table; the surface **projects** the durable rows.
  - **§13 — Operator Console → BFF rule.** *"The browser never talks to the Kubernetes API or Postgres
    directly; the Next.js server proxies/aggregates the Go apiserver — one authorization choke point"* —
    identity-aware (§12.3): the BFF holds the HttpOnly session cookie, the apiserver mints the internal JWT,
    the deny-by-default RBAC middleware is the single wall. The artifact reads are **GET-through-BFF**.
  - **§9.4 — workspace/worktree read model + owning-principal gate.** The artifact blobs derive from the Run's
    worktree over the Project workspace and **may contain the owning principal's BYO secrets**; reads are
    gated by the Run's **already-recorded initiating principal** (no new field — 8.7d AC5).
  - **§12.3 / §12.1 — Identity/RBAC + Team tenancy.** The read passes the **deny-by-default RBAC wall**; the
    visibility model is **per-principal, not Team-legible** (ISI-2166 / arch r15): a same-Team non-owner is
    denied. The BFF adds **no** second authz path; the console adds **no** client-side authz.
- **UX:** `docs/bmad/ux/README.md §3.3` + `images/03-artifact-inspection.png` (+ `-light`). A **master–detail**:
  an **artifact list** (diff / comment / report / file / log, each with producer + a one-line metric) beside a
  **read-only preview**. Default is a syntax-tinted unified **diff** with a **provenance strip** (*work item
  #88 · produced by Fixer (Hermes) · 02:48 · sha*) — the audit trail made visible (FR-B4 / D4 / NFR-OBS1). A
  **Download** action exports; there is deliberately **no edit affordance**. The footer states the guard in
  words: *"apply happens in the repo PR the Fixer opened, not here (scope guard · not an IDE)."* This is
  where **R6** is held at the pixel level. (Responsive: §Artifact inspection row = list + side detail pane;
  mobile = list + row-expand, ≥44px rows, no hover-only artifact menu.)
- **ADR:** No new ADR. This story **applies** **ADR-013** (Next.js BFF vs SPA-direct-to-kube — the choke-point
  decision this surface honors) and **ADR-040** (audit/coord record is the firehose; **no** separate viewer
  table — the surface projects the durable content-addressed rows, not a bespoke store). The per-principal
  existence-hiding model is the **8.7d / ISI-2166** decision, applied here.
- **Depends on:**
  - **Story 2.1 / 2.6 / 2.8** — the `coord` schema, the **audit trail (§6.5)**, and the **content-addressed
    `coord.artifact` row** (the handoff writer; `sha256`, `UNIQUE(work_item_id,run_id,kind)`) this surface
    reads (ISI-2196 audit, ISI-2198 handoff, ISI-2394 coord spine).
  - **Story 8.7c** — the **build-snapshot `coord.artifact`** produced at Run completion (the file/diff blobs
    for a completed Run); this surface renders those same rows. **8.7a** — the fail-safe **body caps** this
    surface reuses. **8.7d** — the **per-principal existence-hiding BFF gate** (NFR-SEC5) this surface reads
    through (do **not** reimplement the gate — call it).
  - **Story 8.2** — the live SSE stream that **deep-links** here on an `ARTIFACT` / `HANDOFF` event; this
    surface is the deep-link target, not the stream owner.
  - **Story 15.x / §12.3** — the `pkg/auth` session→JWT + deny-by-default RBAC wall the reads open through.
- **Tightly coupled with (owned elsewhere):**
  - **Story 8.7 (build browser, 8.7a–e)** — the per-Run file tree / per-file diff / code viewer. **8.7 extends
    FR-F3**: blobs and handoffs stay reachable from the **same** surface (epic 8.7 AC). This story owns the
    **artifact/handoff list + read-only preview** (screen 03); the build browser (screen 06) is the
    changed-file-tree lens over the worktree — the two link to each other, neither reimplements the other.
  - **Story 2.8 (handoff artifact)** — the 7-field **advisory** handoff this surface renders. Handoff is
    **advisory context** (custody stays fenced release→re-dispatch→claim); the surface **shows** the fields,
    it does not carry a custody/claim affordance.

## What the artifact-inspection surface does (the §6.5/§13 read model — authoritative)

1. **Read the durable, content-addressed coordination record — not a re-invented store (AC1).** The list and
   every preview are a **projection of the `coord.artifact` rows** (§6.5, content-addressed by `sha256`) — the
   same rows 2.8 (handoff) and 8.7c (build snapshot) write. There is **no** bespoke artifact-viewer table and
   **no** in-memory scrape (ADR-040).

2. **Through the BFF, hiding the Go API (AC2).** The browser reads through the **Next.js BFF**, which proxies
   the Go apiserver; the browser **never** connects to the apiserver directly and holds **no** apiserver
   URL/credential — one authorization choke point (§13 / ADR-013).

3. **Content-addressed integrity — the bytes are the artifact (AC3).** The served blob's bytes **hash to the
   row's recorded `sha256`**; a blob whose bytes do not match its digest is **rejected**, never rendered as
   the artifact (2.8 content-addressing). The provenance strip shows the `sha`.

4. **Per-principal existence-hiding scope (AC4 — the security crux, NFR-SEC5).** A caller who is **not** the
   Run's owning principal — **including a same-Team non-owner** — gets **`404`** (not the blob, not a `403`):
   do not confirm the artifact exists. The **owner** gets `200`. This is the **8.7d** gate, read through here.

5. **Read-only, no mutate affordance (AC5 — R6 scope guard, the pixel-level crux).** The surface carries
   **only** read/navigate/**download** affordances — **no** edit / apply / re-run / claim / grant-custody
   verb. *"Apply happens in the repo PR the Fixer opened, not here (not an IDE)."* The **handoff** is
   **advisory** (2.8): its 7 fields render, but no custody/claim/fence affordance rides it.

6. **Server-stamped provenance on every artifact/handoff (AC6).** Every row carries **server-stamped**
   provenance from the coordination record — **kind** ∈ {`diff`,`comment`,`report`,`file`,`log`,`handoff`},
   **producer** (agent·role), **work item**, **timestamp**, **sha** (FR-B4 / D4 / FR-I3) — never
   client-fabricated. The provenance strip is the audit trail made visible.

7. **Bounded fail-safe body + observability (AC7).** An oversize blob returns `tooLarge:true` with **no** body;
   a binary blob returns `binary:true` with **no** text body (8.7a caps — never an unbounded/hostile stream).
   The inspection span carries **only** magnitudes/status (`too_large`, `binary`, `bytes_returned`) — **never**
   blob content, an artifact `sha`, or a per-item id as a metric label (NFR-OBS3).

## Acceptance Criteria

**AC1 — the surface projects the durable, content-addressed coordination record (not a re-invented store).**
Given a completed/collecting Run, When the operator opens artifacts, Then the list and every preview are a
**projection of the `coord.artifact` rows** (§6.5, content-addressed by `sha256` — the same rows Story 2.8 /
8.7c write), **not** a bespoke artifact-viewer table or an in-memory scrape (ADR-040: no separate store). A
design that reads a re-invented store is the FR-F3 / ADR-040 defect.

**AC2 — the reads go through the Next.js BFF, hiding the Go API.** Given the artifact surface, When the browser
loads a blob/handoff, Then the read **terminates at the Next.js BFF**, which **proxies** the Go apiserver
(§13). The browser **never** connects to the Go apiserver directly and holds **no** apiserver URL/credential —
the BFF is the **one authorization choke point** (holds the HttpOnly session cookie, forwards the
apiserver-minted JWT). A design that reads the browser straight from the apiserver leaks the Go API and
bypasses the RBAC/JWT wall (ADR-013 defect).

**AC3 — content-addressed integrity: the served bytes hash to the recorded `sha256`.** Given an artifact row,
When its blob is served, Then the served bytes **hash to the row's recorded `sha256`** (2.8 content-addressing)
— a blob whose bytes do not match its digest is **rejected** and never rendered as the artifact. The
provenance strip surfaces the `sha`.

**AC4 — per-principal existence-hiding scope; same-Team non-owner → `404` (the security crux, NFR-SEC5).**
Given principals **A** and **B** in the **same Team/Project**, and a Run owned by A
(`Run.owningPrincipal == A`), When **B** opens any of A's artifacts/handoffs, Then every read returns
**`404`** — not the blob and **not** a `403` (do not confirm existence). **Positive control (non-vacuous):**
when **A** (the owner) opens the same artifacts, Then they return `200` with the blob + provenance. The gate
is the **8.7d** per-principal gate (read the Run's **already-recorded** owning principal — no new field), not
a Team-legible read.

**AC5 — read-only surface, no mutate affordance (R6 scope guard, the pixel-level crux).** Given the artifact
surface, When it renders, Then it carries **only** read / navigate / **download** affordances — **no** edit /
apply / re-run / claim / grant-custody verb anywhere (an edit affordance is **structurally absent**, not
merely disabled). The footer states the guard in words: *"apply happens in the repo PR the Fixer opened, not
here (scope guard · not an IDE)."* And the **handoff** output is **advisory** (Story 2.8): its 7 fields render,
but **no** custody / claim / fence affordance rides it. A mutate/edit affordance on the surface reintroduces
the console-as-IDE / no-P2P violation the architecture forbids (R6 · §6/§7.5).

**AC6 — server-stamped provenance on every artifact/handoff.** Given any rendered artifact/handoff, When its
provenance strip renders, Then it carries **server-stamped** provenance from the coordination record —
**kind** ∈ {`diff`,`comment`,`report`,`file`,`log`,`handoff`}, **producer** (agent·role), **work item**,
**timestamp**, **sha** (FR-B4 / D4 / FR-I3) — **never** client-fabricated. The provenance strip is the audit
trail made visible (NFR-OBS1).

**AC7 — bounded fail-safe body + observability.** Given an oversize or binary blob, When it is inspected, Then
an oversize blob returns `tooLarge:true` with **no** body and a binary blob returns `binary:true` with **no**
text body (8.7a caps — never an unbounded/hostile stream). And the inspection surface emits **only** ordinary
console/BFF request telemetry — **no** new domain metric, and the read span carries **only** magnitudes/status
(`too_large`, `binary`, `bytes_returned`), **never** blob content, an artifact `sha`, or a per-item id
(`run.id`/`work_item.id`/`agent`/`user.id`) as a metric label (NFR-OBS3).

## Runnable check (the falsification)

`docs/bmad/spikes/bench/artifact-inspection-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check over the artifact-inspection **DESIGN** a console+BFF would ship. It first proves the
**FR-F3 anti-pattern** — a "bespoke-store-editor" client (reads a re-invented artifact store, streams the
browser straight from the Go apiserver, serves the blob **without** checking its `sha`, returns a same-Team
non-owner's blob, hangs an Edit/Apply/Re-run button on the preview, fabricates provenance client-side, and
streams an unbounded blob) — is **DETECTED as violating every invariant** (so the harness has real teeth),
then proves the **§6.5/§13 durable-coord read-model** design violates nothing **and actually serves the owner
an integrity-verified, provenance-stamped, bounded blob while `404`-hiding the same artifact from a same-Team
non-owner**.

```
[model] FR-F3 bespoke-store-editor client : 7 violation(s) -> DETECTED
[model]   - A1: artifacts read from 'bespoke' store, not the durable coord record (§6.5/ADR-040)
[model]   - A2: browser reads through 'apiserver', not the Next.js BFF (§13/ADR-013)
[model]   - A3: served blob does not hash to its recorded sha256 (content-addressing broken, 2.8/§6.5)
[model]   - A4: same-Team non-owner got status=200 body=set — must be 404 existence-hiding (NFR-SEC5/8.7d)
[model]   - A5: mutate/edit affordance(s) ['apply', 'edit', 'rerun'] on the inspection surface — R6 scope guard
[model]   - A6: provenance source='client' — must be server-stamped, not client (FR-I3)
[model]   - A7: oversize/binary blob streamed as an unbounded body (8.7a caps ignored)
[model] §6.5/§13 durable-coord read model: 0 violation(s); source=coord, browser->bff, integrity-verified,
        per-principal 404, read-only, server-provenance, bounded
[artifact] PASS — the bespoke-store-editor client detectably breaks every invariant; the §6.5/§13
           durable-coord design holds A1-A7 ... and actually serves the owner a verified blob
           while 404-hiding the same artifact from a same-Team non-owner.
```

It encodes AC1–AC7 as assertions (A1–A7) over the inspection design: **(A1)** durable content-addressed
coord source, not a re-invented store; **(A2)** the browser reads through the BFF, never the Go apiserver
directly; **(A3)** the served bytes hash to the recorded `sha256`; **(A4)** a same-Team non-owner gets `404`
existence-hiding while the owner gets `200` (non-vacuous — the gate must actually **allow** the owner and
**deny** the non-owner); **(A5)** only read/navigate/download affordances, handoff advisory; **(A6)** every
row is server-stamped provenance with a legible kind; **(A7)** oversize→`tooLarge` and binary→no-text-body,
and the span carries magnitudes only.

Each guard is **independently load-bearing** — mutation-verified via `--mutate=NAME`, which injects one
single defect into the conformant durable-coord design (`BESPOKE`, `DIRECT_API`, `SHA_MISMATCH`, `CROSS_PRIN`,
`MUTATE`, `CLIENT_PROV`, `UNBOUNDED`) and flips the check **RED with exactly one mapped violation** and no
guard shadowing another (the ISI-2346-F1 vacuous-tooth class is excluded by construction; `BESPOKE`
additionally trips A3 because a re-invented store is intrinsically not content-addressed — honest, and A1 is
the mapped tooth). Baseline `python3 artifact-inspection-check.py` exits 0; each `--mutate=NAME` exits 1 with
the single mapped violation. The check exits non-zero if the bespoke-store-editor model *stops* violating
(teeth lost), if the durable-coord model *ever* violates an invariant, or if it fails to actually serve the
owner the verified blob while `404`-hiding it from the same-Team non-owner.

**Runtime proof (owned by the console E2E + 8.7d gate).** The actual GET→BFF→apiserver read on a real
cluster — a completed Run, the owner opening the blob **through the BFF** with no direct-to-apiserver
reachability, the live `404` on a same-Team non-owner, and the fail-safe caps under load — is exercised by the
console E2E (`05-testing`) and the **8.7d** BFF per-principal scoping gate (NFR-SEC5, S4 blast-radius suite).
The model check guards the **construction-time contract** — 8.3's crux and exactly what FR-F3 asked (inspect
the blobs + handoffs, from the coordination record, read-only, scoped).

## Tasks / Subtasks

- [ ] **Task 1 — Artifact/handoff list + read-only preview (AC1, AC6).**
  - [ ] Console master–detail: the **artifact list** (kind badge {`diff`,`comment`,`report`,`file`,`log`,
    `handoff`} + producer + one-line metric) beside the **read-only preview** (default: syntax-tinted unified
    diff), per UX §3.3. Render from the **`coord.artifact` projection** — do **not** invent a store or a
    client-side event type.
  - [ ] Provenance strip on every preview (*work item · produced by agent (role) · timestamp · sha*),
    server-stamped (AC6). Handoff preview renders the **7 advisory fields** (2.8) — no custody/claim control.
- [ ] **Task 2 — BFF read route + content-addressed integrity (AC2, AC3).**
  - [ ] Next.js BFF GET route that **proxies** the apiserver artifact reads (list + blob + handoff),
    forwarding the apiserver-minted JWT from the HttpOnly session cookie. The browser holds **no** apiserver
    URL/credential.
  - [ ] Verify the served blob bytes **hash to the row's recorded `sha256`** (2.8); reject a mismatch — never
    render an unverified blob as the artifact.
- [ ] **Task 3 — Per-principal existence-hiding scope (AC4).**
  - [ ] Reads open **through** the **8.7d** per-principal gate (read the Run's already-recorded owning
    principal — no new field): a non-owner, **including a same-Team non-owner**, gets **`404`** (not `403`,
    not the blob); the owner gets `200`. **Do not reimplement the gate — call 8.7d.**
- [ ] **Task 4 — Read-only surface, R6 scope guard (AC5).**
  - [ ] Read / navigate / **Download** only — **no** edit / apply / re-run / claim / grant-custody affordance
    (structurally absent, not disabled). Footer guard copy: *"apply happens in the repo PR the Fixer opened,
    not here (scope guard · not an IDE)."* Handoff rendered **advisory** (no custody/claim affordance).
  - [ ] Cross-link: the 8.2 live stream deep-links **into** this surface on an `ARTIFACT`/`HANDOFF` event;
    this surface links **out** to the 8.7 build browser (changed-file tree) — neither reimplements the other.
- [ ] **Task 5 — Bounded fail-safe body (AC7).**
  - [ ] Reuse the **8.7a** caps: oversize blob → `tooLarge:true`, no body; binary blob → `binary:true`, no
    text body. Never stream an unbounded/hostile blob.
- [ ] **Task 6 — Observability self-check (AC7).**
  - [ ] Confirm **no** new domain metric; only ordinary request telemetry. The read span carries **only**
    magnitudes/status (`too_large`, `binary`, `bytes_returned`) — no blob content, no artifact `sha`, no
    per-item id / `model` label (NFR-OBS3).
- [ ] **Task 7 — Falsification + E2E.**
  - [ ] `python3 docs/bmad/spikes/bench/artifact-inspection-check.py` exits 0; each `--mutate=NAME` exits 1
    with exactly one mapped violation.
  - [ ] Console E2E (`05-testing`): open a completed Run's artifacts, assert blobs+handoffs render through the
    BFF (no direct-to-apiserver) with server-stamped provenance and verified `sha`; assert a same-Team
    non-owner gets `404`; assert **no** edit/apply/re-run affordance on the surface.

## Dev Notes

- **Project a durable record — do not invent a store (ADR-040).** The list and every preview are a
  **projection of the content-addressed `coord.artifact` rows** (§6.5) — the same rows Story 2.8 (handoff) and
  8.7c (build snapshot) write. Do **not** stand up a bespoke artifact-viewer table or scrape blobs into an
  in-memory cache. Content-addressing (`sha256`) is the authority: the bytes you serve **are** the artifact
  only if they hash to the recorded digest (AC3).
- **The BFF is the choke point (ADR-013), and the scope gate is 8.7d — reuse both.** The browser talks to the
  Next.js BFF; the BFF proxies the apiserver — the browser never touches kube/apiserver directly (AC2). The
  per-principal existence-hiding gate is **already** the deliverable of **8.7d** (NFR-SEC5, `404`-not-`403`,
  same-Team non-owner denied) — **call it**, do not reimplement a second authz path. Worktree/artifact blobs
  may carry the owner's BYO secrets; a same-Team `200` is a security regression.
- **Read-only, R6 at the pixel level.** This is the surface where R6 is held in the UI (UX §3.3): inspect,
  provenance, **Download** — and deliberately **no edit affordance**. Apply happens in the repo PR the agent
  opened, not here — the console is **not an IDE**. The **handoff** is **advisory** (2.8): show the 7 fields,
  never a custody/claim/fence affordance — no-P2P holds on the console.
- **8.3 vs 8.7 (they link, neither reimplements the other).** 8.3 owns the **artifact/handoff list + read-only
  preview** (screen 03, FR-F3). 8.7 (build browser, screen 06) owns the **changed-file tree / per-file diff /
  code viewer** over the Run's worktree — it **extends** FR-F3 (blobs + handoffs stay reachable from the same
  surface). Cross-link the two; do not rebuild the git projection (8.7a) or the caps here — reuse them.

### Project Structure Notes

- **Repo shape (current, this branch):** greenfield console — the durable coord audit/artifact record (§6.5,
  Epic 2 / 2.8 / 8.7c), the BFF choke point (§13), and the per-principal gate (8.7d) are landing in parallel.
  This story lands the **console artifact/handoff list + read-only preview** under `console/` and the **BFF
  read route** in the Next.js server; the apiserver-side artifact read (project → content-addressed row →
  bytes, RBAC + per-principal gated) is the apiserver surface it proxies. It adds **no** new datastore and
  **no** new transport — it projects the existing durable content-addressed record over the existing BFF.
- **Match conventions:** reuse the §13 BFF proxy pattern, the §12.3 RBAC wall, the **8.7d** per-principal gate,
  and the **8.7a** body caps; render the durable `coord.artifact` kinds and provenance (do not invent
  client-side artifact types or a bespoke store).

### References

- [Source: docs/bmad/02-prd.md#9.6 FR-F3] — inspect a Run's artifacts + handoff outputs from the coordination
  record (MVP).
- [Source: docs/bmad/02-prd.md — FR-B4 / FR-D4 / FR-I3 / NFR-OBS1 / NFR-SEC5 / NFR-OBS3] — coordination record
  as audit trail; server-stamped provenance; per-principal read scope; no per-item ids on metric labels.
- [Source: docs/bmad/03-architecture.md#6.5 — audit / content-addressed coord.artifact] — the durable
  content-addressed rows the surface projects (ADR-040: no separate viewer store).
- [Source: docs/bmad/03-architecture.md#13 — Operator Console → BFF rule] — browser never talks to kube/
  apiserver directly; the Next.js BFF is the one authorization choke point (identity-aware §12.3).
- [Source: docs/bmad/03-architecture.md#9.4 — workspace/worktree read model + owning-principal gate] — blobs
  derive from the Run's worktree and may carry BYO secrets; per-principal gated.
- [Source: docs/bmad/ux/README.md#3.3 + images/03-artifact-inspection.png] — master–detail artifact list +
  read-only preview, provenance strip, Download (no edit), R6 footer guard.
- [Source: docs/bmad/stories/2-8-structured-handoff-artifact.md] — the content-addressed `coord.artifact` row
  (`sha256`, UNIQUE) + the 7-field **advisory** handoff this surface renders (custody never rides it).
- [Source: docs/bmad/stories/8-7d-build-browser-bff-scoping-gate.md] — the per-principal existence-hiding BFF
  gate (NFR-SEC5, `404`-not-`403`) this surface reads through.
- [Source: docs/bmad/stories/8-7a-git-read-model-runnable-check.md] — the fail-safe body caps this surface
  reuses; and 8.7c (build-snapshot artifact) the surface renders.
- [Source: docs/bmad/stories/8-2-live-run-progress-via-sse.md] — the live SSE stream that deep-links into this
  surface on an `ARTIFACT`/`HANDOFF` event.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 8 row 8.3] — epic-level AC (UX 03-artifact-inspection;
  FR-F3; extended by 8.7).
- [Source: docs/bmad/spikes/bench/artifact-inspection-check.py] — the runnable falsification (A1–A7,
  mutation-proven).

### Open questions (route via ISI-2325; do not block the surface)

1. **Handoff-vs-artifact list grouping (Designer / Architect).** Confirm whether the handoff outputs render as
   a distinct list section/tab or interleave with the blob artifacts in the one master list (UX §3.3 shows one
   list). *Does not block the projection/scope/read-only contract (AC1–AC7).*
2. **Download scope under per-principal gate (Architect / Winston).** Confirm the **Download** action re-passes
   the same 8.7d per-principal gate + caps (a large blob download path) so Download is not a scope/cap bypass.
   *Does not block the inspect path; Download rides the same gate by construction.*

## Out of scope (owned elsewhere)

- **The content-addressed `coord.artifact` write path** (**2.1/2.6/2.8/8.7c**, §6.5) — the durable rows the
  surface projects. This story reads/renders them; it does not own the schema or the write path.
- **The per-principal existence-hiding BFF gate** (**8.7d**, NFR-SEC5) — the `404`-not-`403` authZ gate this
  surface reads **through**. This story calls it; it does not reimplement the gate.
- **The build browser** (**8.7a–e**, screen 06) — the changed-file tree / per-file diff / code viewer over the
  worktree. This story links to it and reuses its caps (8.7a); it does not rebuild the git projection.
- **The live SSE stream** (**8.2**, FR-F2) — the coordination-event feed that deep-links here. This surface is
  the deep-link target; it does not own the stream.
- **The Gateway `HTTPRoute`** (**9.1**, §16.1) — the edge in front of the apiserver. This story relies on it;
  it does not author the chart.
