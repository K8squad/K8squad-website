# Story X.2: Residue/reuse test across Runs and principals (the runtime residue oracle)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY IS THE RUNTIME PROOF THAT STORY 4.5 DELIBERATELY DEFERRED HERE (arch §9.3
> teardown-and-replace / ADR-006, §9.4 per-principal scoping F6/D7, §12.1; FR-C6, NFR-SEC5, R12;
> S4 blast-radius suite testing §6.5; L4 §14.4).** Story 4.5 (ISI-2211) shipped the *mechanism*
> (teardown-and-replace + per-principal PVC subpath) and a **static-shape** falsification
> (`teardown-scoping-check.py`) that modelled the reconciler's *decision* — then said in its own
> words: *"actual zero-residue is a property of pod destruction + subpath isolation, observed by
> the runtime test, not decidable [in the shape model]."* **This story is that runtime test.** It
> plants a known poison token into every residue channel §9.3 names during Run 1, tears down /
> replaces per policy, then has a **second Run by a different principal** probe every channel and
> assert it observes **nothing** authored by Run 1. **The test is policy-agnostic on purpose: it
> is the gate any future reset-in-place optimization must pass** (Story 4.5 AC1: reset-in-place is
> allowed *only if* ISI-2113 shows replace-cost prohibitive **and a residue test passes** — this
> is that residue test). Because ADR-006's thesis is *"proving an in-place scrub left zero residue
> is a losing game,"* a scrub that misses even one channel (tmpfs secret, poisoned build-cache,
> credential env) is **DETECTED** and the gate **blocks the optimization by construction**. A green
> run here is a **required CI artifact** (§6.5 reuse-residue case, absorbed into the L4 §14.4 S4
> suite). Read AC-C2/C4/C7 literally.

## Story

As **a security owner running many principals' Runs on one shared Project workspace + warm pool**,
I want **a runtime test that plants poison in every residue channel during one Run and then proves a subsequent Run by a different principal can observe none of it (no filesystem / in-memory / credential / scratch / git-worktree / build-cache / cross-principal-PVC state bleeds across Runs or principals)**,
so that **the "no reuse/residue" guarantee (arch §9.3/§9.4, FR-C6, NFR-SEC5, R12) is proven at runtime — not asserted — and the same test stands as the gate any proposed reset-in-place optimization (ISI-2113) must clear before it may replace teardown-and-replace.**

## Context & prerequisites (read first)

- **Epic:** `docs/bmad/04-epics-and-stories.md` — **Epic X — Isolation test suite** (X.1 hostile-Run,
  **X.2 residue/reuse**, X.3 poisoning). *"Isolation is tested, not asserted."* Epic X is retained in
  place but **rolls up under E14 / L4 §6.5** — its three stories are the L4 blast-radius cases
  (§14.4 absorbs X.1/X.2/X.3). X.2 row (verbatim): *"Given a sandbox/PVC reused after a Run, When the
  residue test runs, Then no filesystem/in-memory/credential/scratch state bleeds across Runs or
  principals (teardown-and-replace, per-principal scope). … Gates the reset-in-place optimization
  decision."*
- **PRD:** `docs/bmad/02-prd.md` — **NFR-SEC5** (*"Warm-pool sandboxes and persistent workspaces
  SHALL NOT leak state across Runs or principals"*), **FR-C6** (*"A warm-pool sandbox reused across
  Runs SHALL be reset to a clean state or torn down and [replaced]"*), **FR-C2** (persistent Project
  workspace across Runs — the cache this story must prove **persists same-principal** while
  **isolating cross-principal**), **D7** (per-principal isolation), **R12** (*"Warm-pool/PVC state
  bleed across Runs/principals"* — the risk this test retires), **F6** (Challenger: warm-pool hygiene
  is a security req). This story is the **S4 reuse/residue case** the PRD routed to the blast-radius
  test.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§9.3 — Hygiene: teardown-and-replace (F6/D7, FR-C6, NFR-SEC5).** The decision under test and the
    **canonical list of residue channels** this story must cover: *"proving an in-place scrub left
    zero residue (**scratch files, in-memory secrets, git worktree state, poisoned build cache**) is a
    losing game; destroying the pod is provably clean. … A sandbox is never reused across Runs or
    principals."* (ADR-006.)
  - **§9.4 — Workspace & concurrency, per-principal scoping (F6/D7).** *"the build cache is partitioned
    per principal (separate subpath/volume) … a shared Project workspace never exposes one user's
    secrets/source to another agent's Run. Verified by the S4 blast-radius test's reuse/residue case
    (NFR-SEC5)."* The persistent PVC channel is the sixth residue vector; same-principal cache reuse
    (FR-C2) must **not** be flagged.
  - **§12.1 — Tenancy boundary:** per-principal Secret isolation within a Team namespace — the
    credential-env residue channel ties here.
  - **§17.1 / testing §6.5 — "tested, not asserted."** The **S4 blast-radius suite** runs *in kind
    against a hostile-Run fixture*; the **reuse-residue (F6/F7)** row is this story: *"after
    teardown-and-replace, a fresh sandbox exposes no prior-Run scratch/secret/worktree state;
    per-principal PVC scoping holds."*
- **ADR:** **ADR-006 (teardown-vs-reset — teardown-and-replace chosen).** Do **not** re-litigate the
  default. This story does not choose the policy; it builds the **gate** that would judge any
  challenger to it.
- **Depends on:**
  - **Story 4.5 (ISI-2211) — teardown-and-replace + per-principal PVC scoping** — the mechanism this
    test exercises, and the static-shape bench (`teardown-scoping-check.py`) this test completes. The
    two benches **share the `principal_subpath()` partition scheme** so they agree on the boundary.
  - **Story 4.2 (ISI-2208) — RuntimeClass isolation** — the per-Run pod boundary the residue lives in.
  - **Story 4.3 (ISI-2209) / 4.4 (ISI-2210) — workspace PVC + worktree-per-Run** — the git-worktree and
    build-cache residue channels.
  - **Epic 14.1/14.4 CI surface** — where this test is wired as the L4 §6.5 reuse-residue case.
  - **Spike ISI-2113 (RuntimeClass isolation + warm-pool sizing).** Informs the reset-vs-replace cost
    question. **This story is the security half of the answer:** even if ISI-2113 shows replace cost
    prohibitive, reset-in-place is admissible only if it passes THIS test (Story 4.5 AC1).
- **Not in scope (explicit):** X.1 hostile-Run cross-workspace/network/secret containment (separate
  story), X.3 memory-poisoning/provenance (separate story), the cross-principal-same-Team **build
  browser** read-authZ case (Story 8.7d, ISI-2274 — that is an application-layer 404 gate, not a
  residue channel). Egress default-deny (Story 4.6). This story owns **residue observation only.**

## Acceptance criteria (the residue oracle — every channel a first-class probe)

The verdict logic is the falsification oracle `docs/bmad/spikes/bench/residue-reuse-check.py`
(`violations()` + `observe()`); the runtime driver `residue-reuse-kind.sh` (§Runtime harness) feeds
real cluster observations into that oracle. Sequence for every case: **Run 1 (principal p1)** plants
`POISON-TOKEN-run1` in every channel and completes → **hygiene applied per policy** → **Run 2
(principal p2, same Project/pool)** probes every channel.

- **C1 — teardown-and-replace is clean across all six channels (the §9.3/§9.4 positive path).**
  Under the shipped policy (pod destroyed + fresh replenish, per-principal subpath), Run 2 observes
  **zero** poison on all six channels. This is the green CI artifact.
- **C2 — a sandbox is never reused across Runs/principals.** Run 2's pod is a **distinct, fresh** pod
  (different pod UID) from Run 1's — the §9.3 absolute. Reuse is a construction failure, not a bug
  ticket.
- **C3 — the six residue channels are each independently probed** (none decorative): `scratch-fs`
  (pod ephemeral /tmp + /workspace scratch), `in-mem-secret` (/dev/shm, memfd, env-resident tokens),
  `git-worktree` (staged index / branch / dirty tree), `build-cache-pod` (compiler/module cache in
  the pod), `cred-env` (credential env vars / mounted Secret files), `pvc-cross-principal` (persistent
  Project-PVC subpath authored by a **different** principal).
- **C4 — cross-principal is the crux.** Any poison Run 2 observes that was authored by **p1** is a
  **CROSS-PRINCIPAL leak** and fails the gate (NFR-SEC5). Same-Run self-observation is fine.
- **C5 — same-principal cache persists and is NOT flagged (positive control, FR-C2 / 4.5-AC5).** A
  later Run by **p1** legitimately re-reads p1's own persistent cache subpath — the oracle must **not**
  over-fire on it, or the test would defeat the persistent-cache feature it is meant to protect.
- **C6 — GATE semantics: the oracle blocks reset-in-place deviations by construction.** (a) A
  reset-in-place policy with a **partial** scrub (covers scratch-fs + git-worktree, misses in-mem-
  secret + build-cache-pod + cred-env) is **DETECTED** on exactly the un-scrubbed channels. (b) A
  reset-in-place policy claiming a **perfect** pod scrub but sharing **one** per-Project PVC subpath is
  **DETECTED** on `pvc-cross-principal` — proving §9.3 and §9.4 are **independently** load-bearing.
- **C7 — mutation contract (teeth, per channel).** Dropping **any single** channel probe makes the
  oracle **blind** to a real leak on that channel (a reset-in-place-partial policy then falsely
  PASSES). All six probes must be load-bearing — the ISI-2346-F1 / ISI-2363-F1 teeth-gap pattern,
  proven by `residue-reuse-check.py --mutate` (6/6 BLIND).

## Runtime harness (kind, required CI artifact)

The oracle (`residue-reuse-check.py`) is the **verdict**; the runtime driver binds it to a real
cluster so a green CI run is not a vacuous pass. `docs/bmad/spikes/bench/residue-reuse-kind.sh` (this
story's deliverable alongside the oracle) drives:

1. **Provision:** `kind` cluster + the ksquad chart (Team namespace, `SandboxPool`, one `Project` with
   its workspace PVC), RuntimeClass per Story 4.2. Two principals `p1`, `p2` in one Team/Project.
2. **Plant (Run 1 / p1):** submit a Run whose payload writes `POISON-TOKEN-run1` into each channel —
   a scratch file under `/tmp` and the worktree; a secret into `/dev/shm` and an env var; a poisoned
   entry into the pod build cache; and (legitimately) p1's own PVC cache subpath. Run completes.
3. **Hygiene:** let the pool replenish per the **policy under test** (default: teardown-and-replace;
   or a candidate reset-in-place policy passed via `--policy`).
4. **Probe (Run 2 / p2):** submit a Run by **p2** whose payload enumerates every channel and emits
   what it observes as JSON `{channel, token, author_run, author_principal}` lines.
5. **Judge:** pipe Run 2's observations into `residue-reuse-check.py --observed <file>`; assert
   `violations()==[]` **and** Run 2's pod UID ≠ Run 1's pod UID (C2). Non-empty violations → CI red.
6. **Controls:** repeat step 4 as a **second p1 Run** (C5 positive control — same-principal cache must
   be visible and must NOT fail); run the **partial-scrub** and **shared-PVC** policies (C6) to prove
   the gate fires on deviations even in-cluster.

Until the kind lane (ISI-2157/Epic-14 CI) is green in CI, the **offline oracle + mutation run is the
proof of teeth** and gates this story's merge; the kind driver is the required CI artifact wired in
the L4 §14.4 S4 job.

## Definition of Done

- [x] Falsification oracle `docs/bmad/spikes/bench/residue-reuse-check.py` (stdlib) — six-channel
      differential; `python3 …` → PASS (C1/C4/C5/C6), `--mutate` → 6/6 probes load-bearing (C7).
- [x] Runtime driver `docs/bmad/spikes/bench/residue-reuse-kind.sh` wired into the L4 §14.4 S4 CI job
       (Epic-14 CI lane, ISI-2157) — feeds real cluster observations into the oracle's `violations()`.
- [x] Shares `principal_subpath()` with `teardown-scoping-check.py` (boundary agreement with 4.5).
- [x] Story anchored to §9.3/§9.4/§12.1, FR-C6/C2, NFR-SEC5, R12, ADR-006, testing §6.5.
- [ ] Code review (adversarial) — mutation contract verified, no decorative probe, gate blocks
      reset-in-place by construction.

## Falsification / teeth

`docs/bmad/spikes/bench/residue-reuse-check.py` (stdlib, differential, policy-agnostic):
- **base run →** teardown-and-replace CLEAN (0/6); reset-in-place/partial DETECTED on exactly the
  un-scrubbed channels; reset-in-place/shared-PVC DETECTED on `pvc-cross-principal`; positive control
  (same-principal cache) NOT flagged. Exit 0.
- **`--mutate` →** each of the six channel probes dropped in turn makes the oracle BLIND to a real
  leak on that channel (6/6 load-bearing). Exit 0. **No probe is decorative** — the gate cannot be
  weakened one channel at a time.

This is the runtime completion of Story 4.5's shape bench: 4.5 proved the reconciler *decides*
teardown + per-principal subpath; X.2 proves that decision *leaves no observable residue* and stands
as the gate against any reset-in-place challenger (ADR-006, Story 4.5 AC1, ISI-2113).
