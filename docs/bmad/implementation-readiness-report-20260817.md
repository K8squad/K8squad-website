---
title: Implementation-readiness — finalization epics E13/E14/E11/E10
owner: Winston (Architect)
issue: ISI-2748
parent-directive: ISI-2170 (finalize E13/E14/E9/E11/E10 — E9 closed)
date: 2026-08-17
scope: spec hardening + implementation-readiness for the finalization tail
stepsCompleted:
  - e14-runner-buildability
  - e13-13.4-13.6-ac-sanity
  - e11-11.2-11.6-vs-11.1-seam
  - e10-10.2-10.3-blocker-readiness
  - spec-edits-applied
verdict: READY-WITH-FIXES (2 gaps closed this pass; blockers named for E10/E11 build)
---

# Implementation-readiness: E13 / E14 / E11 / E10 finalization tail

Board directive **ISI-2170** — finalize E13, E14, E9 (closed), E11, E10. This is the Architect
pass raising spec quality and confirming implementation-readiness so the Coder lanes land cleanly.
**Two concrete gaps found and closed this pass** (E14 runner contract, E11 seam `base_ref`); the
remaining items are correctly build-gated on named blockers, not spec defects.

## Summary table

| Epic | Stories reviewed | Verdict | Action taken |
|------|------------------|---------|--------------|
| **E14** | 14.1/14.5/14.6/14.7/14.8 (ISI-2742–2746) | **Gap → fixed** | Authored `stories/epic-14-ci-runner-constraints.md`; pointer added to 14.7 row + 13.6 drop-in corrected |
| **E13** | 13.4 (ISI-2236), 13.6 (ISI-2238) | **Ready** | AC sanity confirmed; 13.6's hosted-runner YAML corrected (rolls into E14 fix) |
| **E11** | 11.2/11.3/11.4/11.6 vs 11.5/11.1 seam | **Gap → fixed** | Added `base_ref`/`baseRef` to 11.5's PR capability + AC4 vocabulary |
| **E10** | 10.2 (ISI-2703), 10.3 (ISI-2704) | **Ready, build-gated** | Blockers confirmed correct; no spec change needed |

## 1. E14 — Testing / CI / supply-chain (buildable against 2 self-hosted runners)

**Finding (real gap).** The E14 story rows and several Epic-13 drop-in snippets were written with
the implicit assumption of GitHub-**hosted** runners (`runs-on: ubuntu-latest`). The
`K8squad/K8squad` repo has **no hosted-runner minutes** — every workflow runs on two self-hosted
homelab VMs (`gitrunner` .190 / 7.9 GB, `gitrunner-2` .191 / 16 GB, both labelled
`[self-hosted, linux, x64]`). A job that requests `ubuntu-latest` **queues forever**. The task's
three confirm-items map directly onto this:

- **Runner labels** — not reflected anywhere in 14.1/14.5/14.6/14.7/14.8. 14.7 only said
  "Node 24-compatible action pins."
- **Concurrency ≤2** — not reflected. Two executors, only .191 (16 GB) safely hosts a heavy
  Go/golangci/Trivy job; a matrix fan-out that assumes unbounded parallel legs starves the queue
  and re-triggers the OOM churn ISI-2612 fixed.
- **OOM caps (ISI-2614/ISI-2612)** — not reflected. The golangci workflow-level cap
  (`--concurrency=1 --timeout=10m`, `GOMAXPROCS=1/GOGC=30/GOMEMLIMIT=3800MiB`, merged `a6b456d`)
  is the 14.5 L5 lint story's hard requirement and was invisible to the spec.

**Fix applied.** Authored `docs/bmad/stories/epic-14-ci-runner-constraints.md` — the authoritative
buildable runner contract (R1 self-hosted labels, R2 concurrency ≤2 + heavy-lane serialization,
R3 golangci OOM cap, R4 no swap reliance on the 7.9 GB box, R5 skeleton-skip on self-hosted, R6
Ollama lane is CPU/self-hosted not GPU-hosted). Corrected drop-in YAML shapes included. The five
child issues (ISI-2742/2743/2744/2745/2746) reference it. Epics-doc 14.7 row and 13.6's drop-in
snippet now point to it.

**Residual note for the Coder / DevOps (ISI-2742):** 14.8's "self-hosted GPU runner" phrasing is
aspirational — there is no GPU box in the homelab. The lane resolves to an Ollama **service
container** + small quantized model on `[self-hosted, linux, x64]`, nightly/release/dispatch only
(never per-PR — it can't share the two boxes with the merge train). Documented as R6.

**Verdict: buildable once the child issues adopt the runner-constraints doc.** No blocker; this is
a spec-adoption item, not a substrate gate.

## 2. E13 — Observability (13.4 / 13.6 AC sanity for the reviewer)

Both stories are **ready-for-dev**, thoroughly specified (AC + runnable falsification bench), and
map cleanly to the obs-plan. No AC defects.

- **13.4 token/cost metering (ISI-2236)** — AC1–AC8 are internally consistent and the load-bearing
  invariant (observe-not-enforce: the §5.9 budget fit is byte-identical with metering on/off) is
  mutation-checked in `token-metering-check.py`. The cardinality law (`user.id`/`work_item.id`
  ride as exemplars, never labels) is correctly deferred to 13.6 for enforcement. **Reviewer green
  light** — the only cross-check is that 8.8e (ISI-2325) reads the §17.2 rollup, not a private
  ledger (AC6), which is 8.8e's concern, not 13.4's.
- **13.6 cardinality lint (ISI-2238)** — AC1–AC6 hold; the crux (AC4: the same id on a
  span/exemplar/resource attr MUST NOT fire) is the correct metric-label-vs-correlation-axis
  boundary and is mutation-proven (M9 over-fire). **One correction applied:** the §Handoff drop-in
  YAML used `runs-on: ubuntu-latest` → would queue-hang; corrected to the self-hosted label set
  (rolls into the E14 runner contract). **Reviewer green light.**

## 3. E11 — SCM sync (11.2–11.6 vs the 11.1/11.5 SourceProvider contract)

11.2/11.4/11.6 align cleanly with the frozen `SourceControlProvider` seam. **One contract gap
found and fixed:**

- **Gap (fixed):** 11.3 AC1 and 11.4's `scm_pr_mirror` require **`base_ref`** (the PR target branch,
  needed to correlate a PR against the Run branch) on the PR record — but 11.5's enumerated seam
  listed only `state`/`review_state`/`head_sha`, and AC4's normalized vocabulary was
  `PullRequest{state,reviewState,headSHA}`. A seam frozen without `base_ref` would force 11.3 to
  reach outside the interface for the target branch — the exact regression 11.5 AC1 forbids.
  **Fix:** added `base_ref` to 11.5's PR capability (item 2) and `baseRef` to the AC4 vocabulary.
  The seam is now complete for 11.3/11.4 before it is treated as frozen.

- **Alignment confirmed:** all four tail stories (a) reach provider capability **only** through the
  `pkg/scm` seam (no direct GitHub call in the loop), (b) cite 11.1 (loop) + 11.5 (frozen seam) as
  prereqs, (c) carry a Cn↔ACn falsification bench. 11.6 correctly makes **no** provider access — it
  is a read model over the mirror + a room message-append (observer, not coordinator).

- **Build gate (correct, not a defect):** per `epic-11-sequencing-and-readiness.md`, E11 specs are
  detail-complete now but the **runtime build is gated on Wave-1 substrate** (Epic 2 coord record +
  apiserver, Epic 3 Run runtime, Epic 9 ingress, Epic 7 creds). 11.1 (ISI-2254) is `blocked` — the
  spec + model-check are done; the block is the runtime substrate gate, not a spec gap. Recommend
  the block be made legible (owner: 11.1 spec author / backup_Architect) as the sequencing doc §4.2
  already flags — unchanged by this pass.

## 4. E10 — Discussion rooms (10.2 / 10.3 readiness once blockers clear)

Both stories are **ready-for-dev** and correctly build-gated on named blockers. No spec change.

- **10.2 memory-indexer (ISI-2703)** — `blocked` on **ISI-2710** (memory runtime: indexer +
  `discussion_search` MCP tool). Gate 1 (10.1 schema/API, ISI-2709 PR#57 `aa29c54`) and the Epic-6
  memory substrate (6.1/6.4/6.5 done, `ForMemoryIndex` team-scoped + `invalidated_at` +
  server-stamped) are **on main**. AC1–AC5 reuse the Epic-6 untrusted-read envelope verbatim (no
  second trust model); the crux (AC2: room content returned `trust:"untrusted"`) is the primary
  tooth in `discussion-memory-check.py`. **Ready the moment ISI-2710 lands.** Per the epic, 10.2 is
  fast-follow-acceptable post-v1 — it does not gate the room's existence or 10.4.

- **10.3 console room (ISI-2704)** — `blocked` on **ISI-2180** (console shell — now SHELL in_review
  as PR#61). Gate 1 (10.1 REST §7.5) is done. AC1–AC6 are a pure consumer of the 10.1 API behind
  the shared BFF authz choke point (404-not-403, 8.7d reused), the 8.2 SSE channel, and 8.9
  theming — all Epic-8 substrate. **Ready to mount the moment PR#61 merges.**

- **Logo v12 coordination (Graphic Designer, ISI-2749):** the task asks console-surface specs
  (E8 / 10.3 / 11.6) track the logo v12 mocks. This is **shell-level theming (8.9), not per-room**
  — 10.3 explicitly inherits the whole-shell T1–T7 contract and renders no bespoke brand asset, and
  11.6 renders tiles over the mirror. So logo v12 lands once in the 8.9 shell and 10.3/11.6 inherit
  it; no per-story spec edit is needed. Flagged to the Graphic Designer as a shell-theming
  dependency, not a room-spec dependency.

## 5. Dispositions

1. **E14** — runner-constraints spec authored; 5 child issues (ISI-2742–2746) notified to adopt it.
   Buildable. No blocker.
2. **E13** — 13.4/13.6 AC-sane, reviewer green light; 13.6 YAML corrected.
3. **E11** — `base_ref` seam gap closed in 11.5; tail aligns with the frozen contract. Runtime build
   correctly substrate-gated (11.1 block is the substrate gate, to be made legible by the spec owner).
4. **E10** — 10.2/10.3 ready, build-gated on ISI-2710 (memory runtime) and ISI-2180 (console shell,
   PR#61) respectively; logo v12 is a shell-theming inherit, not a per-room edit.

**Overall: READY-WITH-FIXES.** The two real spec gaps (E14 runner contract, E11 `base_ref`) are
closed this pass. Everything else is either reviewer-ready (E13) or correctly gated on a named,
in-flight blocker (E10 build, E11 runtime).
