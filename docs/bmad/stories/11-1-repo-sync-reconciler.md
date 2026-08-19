# Story 11.1: Repo-sync reconciler per Project (provider seam + webhook + poll fallback)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The FIRST Epic-11 story — the repo-sync reconciler foundation every later SCM story
> (issue mirror 11.2, PR/CI sync 11.3, artifacts 11.4, outbound reflection, CI-failure
> auto-post) rides.** A `repo-sync` control loop runs **one per `Project` with `repo.sync`
> configured** and reconciles the linked repo against a **`SourceControlProvider` interface
> (`pkg/scm`, §17.3) — GitHub is the v1 impl**, GitLab/Gitea drop in behind the same seam
> with **zero reconciler change** (the §10.2 spec-drift discipline). It is **level-triggered**:
> an **HMAC-verified webhook only *triggers* a reconcile** (fast path), and a **periodic
> provider-list poll — interval from values — is the correctness backstop** that guarantees
> convergence when webhooks are lossy/absent (webhooks are at-least-once). The reconcile is an
> **idempotent upsert keyed by external id** (a redelivered webhook is a no-op). The HMAC
> signature (per-`Project` `webhookSecretRef`) is **verified before any payload is parsed**;
> a bad/absent signature is dropped, never reconciled (D8, NFR-SEC8). The provider token is a
> **per-user/per-`Project` BYO Secret ref** (Epic 7, D3/FR-G1), scoped **mirror-read**, never a
> shared platform/master token, **never logged / echoed / injected into an agent Run**. The
> mirror it writes is **UNTRUSTED-EXTERNAL, provenanced** (`external_origin`) — a mirror, **not**
> the source of truth: the fenced coordination record (§6) stays authoritative, the mirror is
> **single-writer on external-owned fields only** and **never writes coord custody** (claim/
> lease/fence), and our own reflected writes are **echo-suppressed** so they cannot re-enter as
> fresh inbound changes. A GitHub-coupled reconciler (branches on the concrete provider), a
> webhook whose payload IS the state (edge-triggered), a non-idempotent upsert, a webhook-only
> sync with no poll fallback, a parse-before-verify webhook, a shared/leaked token, a mirror row
> treated as trusted control input, a mirror that writes custody, or a missing echo-suppression
> is a **regression**. Read AC1, AC2, AC4, AC5, and AC6 literally.

## Story

As **the system**,
I want a **repo-sync reconciler per `Project`** — talking to a `SourceControlProvider` seam
(GitHub v1), driven by an HMAC-verified webhook fast path (Epic 9 HTTPRoute ingress) with a
periodic poll fallback, authorized by the per-user BYO Secret refs (Epic 7) — that keeps an
**untrusted-external, provenanced mirror** of the linked repo's issues/PRs/checks/artifacts,
so that **the console and dashboards can reflect real SCM state (FR-H1…H5) without the mirror
ever becoming the source of truth, without a shared platform token, and without coordination
custody ever crossing the seam (§6 no-P2P intact).**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 11 row **11.1** — a **repo-sync
  reconciler** per `Project`, webhook-driven with periodic poll fallback (interval via values);
  credentials from the **per-user Secret refs** (BYO, Epic 7), never a shared platform token;
  **provider seam** — reconciler talks to a `SourceControlProvider` interface, GitHub is the v1
  impl. Theme H, FR-H1…H5.
- **Architecture:** `docs/bmad/03-architecture.md` **§5.4** (repo-sync reconciler & provider
  seam — the load-bearing section, read it whole), **§5.1** (`Project.repo.sync{provider,
  webhookSecretRef,mirror{},reflectOutbound}`), **§10.2** (provider-seam spec-drift discipline),
  **§7.3.2** (untrusted-external provenance envelope — same as memory/discussion), **§6** (fenced
  claim / no-P2P — custody never crosses the seam), **§11** (BYO per-user Secret discipline),
  **§17.3** (`pkg/scm`). **ADR-018** (repo-sync provider seam + mirror-not-authority +
  field-ownership/echo-suppression). **ADR-001** (one Postgres — the `scm` schema is one more
  schema, not a new datastore).
- **Mirror shape (this story establishes the reconciler; the schema rows fill in as later
  stories land):** the `scm` schema — `scm_repo`, `scm_issue_mirror`, `scm_pr_mirror`,
  `scm_check_run`, `scm_artifact_ref` — is written by the inbound reconciler on **external-owned
  fields only**. `scm_pr_mirror.review_state` and the `head_sha → run.commit_sha` Run/branch
  correlation are **elaborated by 11.3**; the issue⇄work-item map is **11.2**. 11.1 pins the
  **loop + seam + ingress + credential + provenance contract** those consume.
- **Webhook ingress:** the apiserver exposes the **HMAC-verified** webhook endpoint reached via
  the **Epic 9 Gateway/HTTPRoute** (`docs/bmad/stories/9-1-chart-gateway-httproute.md`). It
  subscribes to `push` / `pull_request` / `issues` / `check_run` / `release` (FR-H3). Webhooks
  are **lossy + at-least-once**, so a webhook only *triggers* a reconcile — the periodic
  provider-list reconcile is what guarantees eventual convergence.
- **Credentials:** the provider token is a **per-user/per-`Project` BYO Secret ref** (Epic 7,
  `docs/bmad/stories/7-1-*`), scoped **mirror-read** (+ optional status-write only when
  `reflectOutbound`, which is off by default and out of 11.1 scope). Never a shared master token
  to GitHub; **never logged, echoed, or exposed to an agent Run** (NFR-SEC8).
- **Trust boundary (D8, §7.3.2):** every synced work item / mirror row carries `external_origin`
  provenance (provider, repo, external id, actor) and is **untrusted-external** — rendered in the
  console as *external, attributable* data, consumed by agents through the **same
  untrusted-provenance envelope as memory/discussion**, **never trusted control input**.
- **Conflict / loop model (OQ13 — resolved, §5.4):** **field-ownership split** — external-owned
  fields (title/body/state/CI result) written **only** by the inbound reconciler; KSquad-owned
  fields (linked work-item id, claim/lease/custody §6) written **only** by the coordination
  record and **never** by the mirror. **Echo-suppression** — a KSquad-authored provider write is
  origin-marked (bot actor + marker) and dropped on the way back in, so a reflected write can
  never re-enter as a fresh inbound change and ping-pong. Combined with the idempotent
  external-id upsert, the sync is **convergent, not oscillating**.
- **Scope guard:** 11.1 is the **inbound reconciler + seam + ingress + credential + provenance
  contract**. **Outbound reflection** (`reflectOutbound`) is off by default and out of scope
  here (later story). The **CI-failure discussion auto-post** and the **event-bus fan-out**
  (§7.5 / ADR-023) ride this loop's mirror-state transitions but are their own stories. This
  story adds **no coordination path** — claim/lease/fence stays server-side (§6).

## Acceptance Criteria

**AC1 — the reconciler talks ONLY to the `SourceControlProvider` seam (the seam crux).**
Given a `Project` with `repo.sync` configured, When the reconciler reconciles, Then it consumes
**only the normalized `SourceControlProvider` interface** (`pkg/scm`, §17.3) — it does **not**
branch on the concrete provider or import provider-specific API types into the loop. GitHub is
the **v1 impl**; a second provider (GitLab/Gitea) drops in behind the **same interface** and the
reconciler produces **identical mirror state** from identical records — provider-specific churn
**never reaches coord** (§10.2 discipline). A reconciler that branches on `provider == "github"`
(so a drop-in provider yields nothing) is a **regression**.

**AC2 — level-triggered: a webhook TRIGGERS an idempotent reconcile (the correctness crux).**
Given an inbound webhook, When it is verified (AC4), Then it only **triggers** a
**level-triggered reconcile** — the reconciler reads the provider's current state and
**idempotent-upserts every record keyed by external id** — it does **not** write the webhook
payload directly as the state. A **redelivered** webhook (at-least-once delivery) is a **no-op**:
the mirror is unchanged, no duplicate row. An **edge-triggered** reconciler (payload is the
state) or a **non-idempotent** upsert (a new row per delivery) is a **regression**.

**AC3 — periodic poll fallback, interval from values (the convergence backstop).**
Given webhooks are **absent or lossy**, When the periodic provider-list poll ticks, Then it runs
the **same level-triggered reconcile** and **converges** the mirror to the provider's current
state — so a missed webhook is **not** permanent drift. The **poll interval comes from values**
(`repo.sync.pollIntervalSeconds` / chart values), never a hardcode: two `Project`s with distinct
intervals schedule distinctly. A **webhook-only** sync (no poll) or a **hardcoded** interval is a
**regression**.

**AC4 — HMAC verified BEFORE any payload is parsed (the security crux, D8/NFR-SEC8).**
Given a webhook delivery, When it arrives, Then its **HMAC signature** (per-`Project`
`webhookSecretRef`) is **verified before the payload is parsed or acted on**; a **bad or absent**
signature is **dropped — no mirror write, no side effect, never reconciled**; only a
**good-signature** delivery triggers a reconcile. A **parse-before-verify** path (a forgery
mutates state before the check) or **accepting a bad signature** is a **regression**.

**AC5 — BYO per-`Project` token, mirror-read, never leaked (the credential crux, Epic 7).**
Given the reconciler authenticates to the provider, When it resolves its token, Then the token
comes from the **per-user/per-`Project` BYO Secret ref** (`repo.sync.tokenSecretRef`), scoped
**mirror-read**, and is **never a shared platform/master token**, **never logged or echoed**, and
**never injected into an agent Run's env** (NFR-SEC8). A **shared master token**, a **logged
token**, or a **token exposed to a Run** is a **regression**.

**AC6 — the mirror is UNTRUSTED-EXTERNAL, provenanced, not the source of truth (the trust crux).**
Given the reconciler writes a mirror row, When it upserts, Then the row is **untrusted-external**
(§7.3.2) and carries **`external_origin`** provenance (provider, repo, external id, actor); the
mirror is **single-writer on external-owned fields only** and **never writes coord custody**
(claim/lease/fence — §6); and our **own reflected write is echo-suppressed** (an
origin-marked/bot-authored delivery is dropped on the way back in) so it cannot re-enter as a
fresh inbound change. A mirror row treated as **trusted control input**, a **missing
`external_origin`**, a mirror that **writes custody**, or a **missing echo-suppression** is a
**regression**.

## Tasks / Subtasks

- [x] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/repo-sync-reconciler-check.py`) — a faithful model of the §5.4
  control loop: the `SourceControlProvider` seam, the webhook-trigger + poll-fallback event
  loop, HMAC-before-parse, BYO token resolution, and the untrusted-external provenanced mirror.
- [x] **Six checks C1–C6 ↔ AC1–AC6**, GREEN on the §5.4/ADR-018-conformant baseline.
- [x] **14-mutation battery**, each flipping its designated check RED — no vacuous survivors;
  C1/C3 differential (two providers / two intervals) for teeth against seam-bleed + hardcoding.
- [x] `python3 repo-sync-reconciler-check.py` → **exit 0**.
- [ ] **(Epic 11 build, later)** the real `pkg/scm` `SourceControlProvider` + GitHub v1 impl,
  the apiserver HMAC webhook endpoint behind the Epic 9 HTTPRoute, the level-triggered reconcile
  + periodic poll worker, and the `scm` schema upsert — owned by the operator/apiserver
  integration tests against a live GitHub. **11.1 pins the contract those satisfy.**

## Dev Notes

- **Why a model check, not Go:** k8squad currently ships only the API-group scaffold; there is
  **no Epic-11 Go artifact to ground against yet**. Per the Epic-8/9 pattern (e.g.
  `agent-detail-runs-check.py`, `nats-jetstream-check.py`), this story pins the **construction-time
  contract** as a runnable falsification harness so the acceptance is **falsifiable now** and the
  build (owned by the Epic 11 implementation ticket) has a red/green target. When the real chart/
  Go lands, a file-grounded Layer B (snapshot + text-mutation flip, as in the 9.x checks) is the
  natural follow-on.
- **Seam discipline (§10.2):** the model proves neutrality **differentially** — the identical
  normalized records reconcile through a `github` and a `gitlab` provider to identical mirror
  state; the seam-bleed mutation (branch on `provider.name`) makes the drop-in yield nothing, and
  C1 goes RED. This is the same discipline that isolates A2A/MCP spec drift.
- **Level-triggered is the backstop, webhook is the fast path:** the webhook only calls
  `reconcile_from_provider()`; convergence is guaranteed by the poll running the **same**
  reconcile. Idempotency is an upsert keyed by `(kind, external_id)` — the non-idempotent
  mutation keys by delivery pass instead, so a redelivery duplicates and C2 goes RED.
- **Custody never crosses the seam:** the field-ownership split is structural — the model's row
  carries external-owned fields + provenance only; the `mirror_writes_custody` mutation adds a
  `claim` field and C6 goes RED. The no-P2P/fenced-claim locks (§6) are untouched by SCM sync.

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/repo-sync-reconciler-check.py` → **exit 0**
  — baseline GREEN on C1–C6; all 14 mutations caught, no vacuous survivors.
- **Deferred to Epic 11 build (integration):** the real `pkg/scm` seam + GitHub v1 impl, the HMAC
  webhook endpoint (verify-before-parse) behind the Epic 9 HTTPRoute, the periodic poll worker,
  the `scm` schema idempotent upsert, and the BYO-Secret token resolution — proven against a live
  GitHub by the operator/apiserver integration suite.

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 11 row 11.1 (FR-H1…H5), provider seam +
  webhook + poll fallback + BYO creds.
- [Source: docs/bmad/03-architecture.md#5.4] — repo-sync reconciler & provider seam (the
  load-bearing spec); §10.2 (seam discipline), §7.3.2 (untrusted-external), §6 (no-P2P), §11
  (BYO Secret), §17.3 (`pkg/scm`). ADR-018.
- [Source: docs/bmad/stories/9-1-chart-gateway-httproute.md] — the Epic 9 Gateway/HTTPRoute the
  HMAC webhook ingress is reached through.
- [Source: docs/bmad/stories/7-1-per-user-secret-refs.md] — the per-user BYO Secret-ref
  discipline the provider token follows.
- [Source: docs/bmad/stories/8-8d-pr-status-mini-board.md] — a downstream consumer of the
  `scm_pr_mirror` this reconciler populates (PR mini-board, degrades to empty until sync lands).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, agent 2230b001) — construction-time contract via runnable
falsification check (`repo-sync-reconciler-check.py`, Epic-8/9 model-check pattern).

### Debug Log References

- `python3 repo-sync-reconciler-check.py` → **exit 0**. Baseline GREEN on C1–C6; the 14-mutation
  battery all CAUGHT, no vacuous survivors.
- C1/C3 are **differential** (reconcile the same records through `github` + `gitlab`; schedule two
  distinct poll intervals) so seam-bleed and interval-hardcoding cannot survive as a frozen value.

### Completion Notes List

- Implemented C1–C6 falsification of the §5.4 repo-sync control loop with teeth via a 14-mutation
  broken-reconciler battery. **Load-bearing cruxes proven:** (C1) the reconciler is **provider-seam
  neutral** — GitHub v1 and a GitLab drop-in yield identical mirror state, branching on the
  concrete provider trips C1 RED (§10.2); (C2) a webhook is a **fast-path trigger** for a
  **level-triggered idempotent** reconcile (upsert keyed by external id) — edge-triggered /
  non-idempotent trips C2 RED; (C3) a **periodic poll — interval from values** — is the convergence
  backstop when webhooks are lossy/absent — webhook-only / hardcoded-interval trips C3 RED; (C4)
  the **HMAC signature is verified before any parse** (per-`Project` `webhookSecretRef`) — a
  bad/absent signature is dropped with no side effect — parse-before-verify / accept-bad-sig trips
  C4 RED (D8/NFR-SEC8); (C5) the provider token is a **per-`Project` BYO Secret ref, mirror-read,
  never shared/logged/exposed-to-a-Run** — a shared master / logged / Run-injected token trips C5
  RED (Epic 7, D3/FR-G1); (C6) the mirror is **untrusted-external + provenanced**, **single-writer
  on external-owned fields only**, **never writes coord custody**, and **echo-suppresses our own
  reflected write** — trusted-as-control / dropped-provenance / mirror-writes-custody / no-echo
  trips C6 RED (§7.3.2, §6, OQ13).
- **Mirror-not-authority is the through-line:** the fenced coordination record (§6) stays
  authoritative; SCM sync adds no coordination path and custody never crosses the seam.
- **Runtime proof deferred to the Epic 11 build ticket** — the real `pkg/scm` `SourceControlProvider`
  + GitHub v1 impl, the apiserver HMAC webhook endpoint behind the Epic 9 HTTPRoute, the poll
  worker, and the `scm` schema upsert — proven against a live GitHub by the operator/apiserver
  integration suite. This check guards the construction-time contract FR-H1…H5 + the epic asked
  for, and is the red/green target that build lands against.

### File List

- `docs/bmad/spikes/bench/repo-sync-reconciler-check.py` (new) — C1–C6 runnable falsification
  check, 14-mutation battery.
- `docs/bmad/stories/11-1-repo-sync-reconciler.md` (this file) — status→done + Dev Agent Record.
