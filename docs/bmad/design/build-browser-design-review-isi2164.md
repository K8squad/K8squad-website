---
title: Build Browser Component Design — Code Review
issue: ISI-2164 (reviews ISI-2148 design: docs/bmad/design/build-browser-component-design.md)
reviewer: Amelia (Code Reviewer)
date: 2026-08-11
verdict: CHANGES-REQUESTED — 1 BLOCKING + 5 important + 4 minor
gate: 8.7d (per-principal scoping) cannot be sliced until B1 resolves; 8.7a–c,e may proceed in parallel
---

# Build Browser Design Review (ISI-2164 → ISI-2148)

**Verdict: CHANGES-REQUESTED.** The git-projection core is sound and the ponytail scoping (git as
diff engine, no VFS, snapshot-only v1) is right. But the design's own stated crux — *per-principal*
read scoping — is specified as *per-Team* and its blocking acceptance evidence is misattributed to a
suite that does not test it. That must resolve before Story Writer finalizes 8.7d.

## BLOCKING

### B1 — "Per-principal" scoping is actually per-Team, and AC3's cited proof (S4) does not test it
Files: `build-browser-component-design.md` §5 (L114–133), §8 AC3 (L159–161); `03-architecture.md`
§9.4 (L1063–1082); `05-testing-strategy.md` §6.5 (L198–208).

- §5 Layer 1 (primary gate) authorizes `runId` against "principal + **Team scope** … same filter as
  the rest of the console" (L118–121). That is **Team** granularity → two principals in one Team both
  pass Layer 1.
- Layer 2 is the **Team** namespace (L122–124) — Team↔Team, not principal↔principal.
- Layer 3 (per-principal cache partition, L125–127) governs **build-cache residue/poisoning**, NOT the
  primary read path. The `tree`/`diff`/`file` endpoints read the **Run's own worktree** via the shim
  `git show/diff` (§2, §4.1) — Layer 3 never gates that path.
- Net: **no layer denies principal A reading principal B's Run build view when A and B share a Team.**
- Yet AC3 (L159–161) asserts exactly that denial — "principal A cannot read principal B's Run build
  view — returns 404 … **This is the blocking security gate**" — and cites **S4** as the proof.
  S4's five cases (`05-testing-strategy.md` §6.5) are: default-deny egress, exfil-via-allowlist,
  **cross-namespace** isolation, **reuse-residue**, memory-poisoning. **None is a cross-principal,
  same-Team authZ case.** reuse-residue = post-teardown residue *between Runs* (F6/F7); cross-namespace
  = Team↔Team. Neither exercises A↔B within one Team on a read endpoint.

This is **F7 from the ISI-2132 architecture review resurfacing** (per-Project-PVC persistence vs
per-principal scope — "stated contradiction, no mechanism"), now at the read API. Two coupled defects:
(a) the *mechanism* for per-principal 404 on the read endpoints is unspecified — the design leans on
cache-partition, which does not cover the git read path; (b) the *acceptance evidence* points at a
suite with no matching case.

**Required before slicing 8.7d:** the Architect must pick and pin the console visibility model —
1. **Team-legible** (same-Team principals *can* read each other's Runs) → AC3 is wrong; rewrite it. or
2. **Per-principal** (AC3 stands) → Layer 1 must check `Run.owningPrincipal == caller.principal`
   (not just Team scope), and S4 must gain an explicit **cross-principal-same-Team read-authZ** case
   (NFR-SEC5). The runnable check (I4) should assert the 404.

The blocking gate cannot be sliced on this ambiguity.

## IMPORTANT

### I1 — RO-reader raw-FS full-tree read bypasses the git-object path-safety invariant
§3 (L73–75) guarantees "no raw FS `open`, git-object-resolved" so `../`/symlink-escape are structurally
impossible — true for the shim `git show` path. But §4.2 (L104–107) has the RO-reader "mount the Project
PVC **`RO`** at the Run's commit." A PVC mount is **filesystem**-scoped, not object-scoped: the same PVC
physically holds other principals' concurrent worktrees (§9.4 L1058–1062) and the per-principal cache
subpaths (§9.4 L1063). A full-tree FS **walk** in the reader can traverse into a sibling principal's
worktree/residue — the exact leak Layer 3 claims to prevent. The reader must read object-scoped
(`git --git-dir … show`/checkout `runRef` into scratch) or mount a **principal-scoped subpath**, never
walk the raw shared-PVC root. Fast-follow 8.7f, but pin the invariant before the story exists.

### I2 — Size caps must be size-first, not materialize-then-measure (read-tier DoS)
§3 (L70–72) states the caps are "fail-safe" but not *how*. `tooLarge`/`binary` require inspecting the
blob. If the cap trips *after* `git show` streams a multi-GiB file into memory, it is an OOM/DoS on the
BFF/reader tier — reachable via a hostile Run's authored file. Specify `git cat-file -s <sha>` (size
check) + bounded streaming read **before** the body is materialized.

### I3 — `file` API has an undefined "not captured in snapshot" case
The design's own ponytail note (§4.2 L109–112): snapshot-only cannot show an unchanged file for a
completed Run. But `GET …/file?path=<unchanged>&ref=run` on a snapshot-only completed Run has **no
defined response** in §3 (L62–64) — `content:null`? `tooLarge`? 404? Add an explicit marker
(`notCaptured:true` or 404-with-reason) so 8.7c and 8.7e implement one contract, not divergent guesses.

### I4 — The one runnable check (§8.6) under-covers the security-critical ACs
§8.6 (L164–168) proves only the git-projection happy path (AC1). The three security ACs — traversal
rejection (AC4), cap enforcement (AC5), cross-principal 404 (AC3) — have **no co-located check**. For a
design whose crux is security, the runnable check must also assert `../`/absolute/symlink-escape are
rejected and caps trip. As written it greenlights projection while the risky logic is untested.

### I5 — Snapshot-emit vs pod-teardown race is acknowledged but not ordered
§7 (L151–152) says surface snapshot-emit failure — good — but the *invariant* is missing: teardown
(§9.3) must not proceed until the `build-snapshot` `coord.artifact` upsert is durably committed-or-
explicitly-failed. Otherwise completed Runs intermittently have **no build view** (silent degrade to
404). Pin the ordering dependency in 8.7c (§6.1/§6.4 upsert must win the race against §9.3 teardown).

## MINOR

- **M1 (§2 L48–49, §8):** live-Run `base` (merge-base) is recomputed per read against a moving
  `Project.repo` default ref → tree shifts under the user though the Run didn't change. Pin base at Run
  start (record merge-base commit in Run status); completed Runs already freeze it in snapshot meta — do
  the same live.
- **M2 (§3 L69, §4.1):** no read-concurrency cap on the shim verb. On-demand git in the *running* Run's
  pod, driven by client polling + diff fetches, contends with the agent's actual work (CPU/IO). Add a
  per-Run read concurrency/debounce cap so observation can't degrade the observed Run.
- **M3 (§8 AC1):** add the empty-changed-set case (console shows "no changes", not error) and define
  fail-closed behavior when `base...runRef` has no merge-base (unrelated histories).
- **M4 (§3 L66, §5):** confirm `meta.artifacts:[…]` and Epic 8.3 artifact-inspection reachability apply
  the same principal scope filter — else listing leaks the existence/URIs of sibling-principal artifacts.

## Confirmed-correct (no change)
- git-as-diff-engine, no VFS/snapshot format of our own (§2) — right call, ADR-021 / ponytail rung 4.
- Fence-guarded, content-addressed `build-snapshot` upsert (§4.2) — re-entrancy-correct (§6.4).
- 404-not-403 existence-hiding (§5.1) — correct.
- Symlink-escape genuinely impossible via git-object resolution — a symlink is a blob of its target
  string, never dereferenced by `git show`. Correct.
- Story DAG 8.7a→{b,c}→d→e with the NFR-SEC5 gate on 8.7d, snapshot-only v1 ponytail cut — clean.

## Disposition
- **B1 → Architect (216ef42c):** resolve the visibility model + fix AC3/S4. Blocks finalizing **8.7d**.
- **I1–I5, M1–M4 → Story Writer (dd210f94):** fold into 8.7a–f AC before finalizing stories.
- 8.7a/8.7b/8.7c/8.7e may be sliced now; only 8.7d is gated on B1.
