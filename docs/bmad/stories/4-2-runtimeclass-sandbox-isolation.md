# Story 4.2: RuntimeClass-selected sandbox isolation (the per-Run kernel boundary)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY SETS THE KERNEL-LEVEL ISOLATION BOUNDARY FOR UNTRUSTED AGENT CODE (arch §9.1,
> §9.3, AD-3, ADR — sandbox runtime).** A Run executes **arbitrary shell / git / build** commands
> authored by an LLM (PRD threat model NFR-SEC2). Story 4.1 gave every squad its own namespace
> (the RBAC/network/quota boundary); this story gives every **Run** its own **kernel/syscall
> boundary** via `RuntimeClass`, so a hostile Run cannot escape its sandbox to the node, another
> squad's pods, or the control plane. The load-bearing invariants are: **(1)** every sandbox pod
> carries a **`runtimeClassName`** resolving to **gVisor (default) or Kata (opt-in)** — **never
> `runc` for untrusted code**; **(2)** the selected `RuntimeClass` **must exist on the cluster** and
> the operator **fail-closes** if it is absent — it **never silently downgrades to `runc`**;
> **(3)** every Run is a **distinct sandbox** (teardown-and-replace §9.3) — no process/net/fs
> boundary is shared across Runs, principals, or squads. A reconciler that emits a pod with no
> `runtimeClassName`, that falls back to `runc` when gVisor is missing, or that reuses one pod
> across two Runs is a **security failure, not a bug ticket**. Read AC2 and AC4 literally.

## Gate status (read first)

**GATE ISI-2113 — CLEARED.** The spike (`spikes/isi-2113-warm-pool-sandbox-latency.md`) and its
hardware run (**ISI-2292 / ISI-2294**, cluster `observable-agentsandbox`, k8s v1.35.3,
containerd 1.7.25, `RuntimeClass gvisor`→`runsc` verified sentry-real) **ratified the RuntimeClass
pick on measured evidence**:

- **Warm-claim latency (S9 / NFR-PERF1, p50 ≤2s / p95 ≤5s): PASS.** gVisor warm-claim
  **p50 0.110 s / p95 0.135 s** (~15–37× headroom). A warm pod is already `Ready`, so RuntimeClass
  moves *replenish time R*, not the user-felt claim — and gVisor's `R = 1.716 s` actually **beats
  runc's 3.560 s**, so gVisor is **not** a warm-pool-size tax (§9.2).
- **Decision (ratified): gVisor default / Kata opt-in / `runc` trusted-dev-only.** This **supersedes
  the epic-text placeholder "Kata default / gVisor fallback"** — the confirming gate is authoritative
  (arch §9.1 note "ISI-2113 — decision ratified"). Encode gVisor-as-default.
- **Steady-state overhead — honest disposition (ISI-2295 build-falsification, §6 TRIGGERED):**
  gVisor's tax is **real on build-heavy bursts** — compile p50 **1.95×** runc, syscall-storm/churn
  **5.4×** — so the "≤15% overhead" bar is met **only for LLM-bound wall-clock** (model-API-bound,
  where the tax is masked, arch §9.1 point 3), **not** for a pure build loop. The decision holds
  anyway because **isolation is decided before latency** (PRD §1 tiebreaker): `runc`'s shared-kernel
  boundary is disqualified for untrusted code regardless of speed. Build-heavy high-assurance tenants
  take **Kata opt-in**; the common docker-build path uses a **rootless daemonless builder** that
  sidesteps gVisor's syscall cost center (§5.3.3, ISI-2300/ISI-2319, AC6). This is a documented,
  bounded cost — **not** a silently-swallowed regression.

## Story

As **the Run reconciler scheduling untrusted agent code onto a shared cluster**,
I want **every sandbox pod to be created under a selected `RuntimeClass` — gVisor by default, Kata
by opt-in, `runc` rejected for untrusted code — with the operator fail-closing when the selected
class is absent, and every Run getting its own distinct sandbox**,
so that **a hostile Run is contained at the kernel/syscall boundary and can never cross into the
node, another squad's pods/network/secrets, or the control plane; the isolation guarantee is
enforced by the platform runtime, not by agent good behavior (arch §9.1/§9.3, AD-3, NFR-SEC1/SEC2).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **NFR-SEC1** (cross-squad isolation), **NFR-SEC2** (untrusted-code
  threat model — arbitrary shell/git/build), **§1 tiebreaker** (isolation > latency), **S1** (RuntimeClass
  is a documented cluster prerequisite), **S4/S9** (hostile-Run containment + warm-claim SLO), **FR-C3**.
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§9.1 — Isolation runtime (OQ2, spike-ratified).** The authoritative decision this story encodes:
    **gVisor default; Kata opt-in for high-assurance; `runc` trusted-dev-only.** RuntimeClass is a
    **per-Team / per-Project knob** (`SandboxPool.runtimeClass`, `Role.runtimeClassHint`), **not a
    hardcode** — flipping the default is a config change, not a structural one. The "ISI-2113 —
    decision ratified" note is the gate evidence.
  - **§9.2 — Warm pool.** Warm pods are keyed by **(RuntimeClass × `AgentRuntime` image)**; a Run claim
    binds a pooled pod **of the matching RuntimeClass** — the class is chosen *before* the pool key, so a
    Kata Run never binds a gVisor pod (AC5).
  - **§9.3 — Hygiene: teardown-and-replace.** A sandbox is **destroyed** after its Run and the pool
    replenishes a **fresh** pod. **A sandbox is never reused across Runs or principals** — this is what
    makes "every Run a distinct sandbox" true (AC3); Story 4.5 owns the residue proof.
  - **§5.3.1 / §5.3.3 — pod assembly + capability gating.** `AgentRuntime.capabilities.docker` and the
    CEL/webhook fail-closed rule: **`docker: true` on a gVisor-only RuntimeClass is rejected** unless a
    rootless-dockerd sidecar / daemonless builder (kaniko/buildah/BuildKit-rootless) or a Kata RuntimeClass
    backs it (ISI-2300 decision, ISI-2319 retest PASS). AC6.
  - **§5.1 `Run` CRD row + §8 lifecycle `Claiming`:** the Run carries **`spec.sandboxPolicy`** (the
    RuntimeClass/isolation selection **input** to §9.1 assembly). At `Claiming` the reconciler requests a
    warm sandbox keyed by (RuntimeClass × image) and **assembles the pod** (§5.3.4) — this story fills the
    RuntimeClass-selection half of that assembly.
- **ADR:** **AD-3** (sandbox isolation via RuntimeClass) — the locked decision; and the §9.1 ratified
  runtime pick. Do not re-litigate the gVisor-default choice; implement it.
- **Depends on:**
  - **Story 4.1** (squad = namespace tenancy) — the sandbox pod lands **in the Team namespace** and runs
    as the namespaced **`ksquad-agent` ServiceAccount**; the RuntimeClass boundary composes *on top of*
    the namespace boundary (defence in depth: 4.1 = RBAC/net/quota, 4.2 = kernel/syscall).
  - **Story 1.2** (the `Run` / `SandboxPool` / `AgentRuntime` CRD types incl. `Run.spec.sandboxPolicy`,
    `SandboxPool.runtimeClass`, `Role.runtimeClassHint`) and **Story 1.3** (operator scaffold). If a type
    is not yet generated, wire against the §5.1 rows and gate envtest on it.
  - **Cluster prerequisite (S1):** the `RuntimeClass` objects (`gvisor` → `runsc`, optionally `kata`) are
    **installed on the cluster out of band** (infra/DevOps — the ISI-2294 posture). This story **selects
    among installed classes and fail-closes on absence**; it does **not** install the runtime handler.
- **Blocks / is consumed by:** **Epic 5** (Run reconcile schedules these pods), **Story 4.5** (teardown-
  and-replace + per-principal scoping proves "distinct sandbox" holds across principals), **Epic X.1**
  (the **hostile-Run blast-radius test** that *proves at runtime* this boundary contains an attacker —
  the hard gate this story's boundary must satisfy).

## What the reconciler does (the §9.1 selection + assembly contract — authoritative)

At `Claiming`, when the Run reconciler requests/assembles a sandbox pod, it resolves and applies the
RuntimeClass by this contract:

1. **Resolve the RuntimeClass by precedence (most specific wins), defaulting to gVisor:**
   `Run.spec.sandboxPolicy.runtimeClass` → `Role.runtimeClassHint` → `SandboxPool.runtimeClass` →
   **`gvisor` (the §9.1 ratified default).** The resolved class name is recorded on the Run
   (`status.sandboxRef` / a `runtimeClass` status field) so the choice is auditable, and it is the
   **pool key dimension** (§9.2) so the claim binds a pod of that exact class.

2. **Reject `runc` for untrusted code (fail-closed, CEL/webhook — AC2).** A resolved class of `runc`
   (or the empty/absent `runtimeClassName`, which means "node default runtime" = runc-equivalent) is
   **rejected** unless the Run/Team carries an **explicit `trustedDev: true`** escape flag (a deliberate,
   audited, non-default opt-out for a trusted first-party dev sandbox). The default and the untrusted
   path resolve to gVisor or Kata **only**. "No `runtimeClassName` set" is a rejection, not a pass —
   an empty field silently runs on the node default runtime (runc), which is the exact hole this story
   closes.

3. **Require the selected class to exist on the cluster — fail-closed, NEVER downgrade (AC4).** Before
   binding/creating the pod, verify a `RuntimeClass` object of the resolved name exists. If it is
   **absent**, the reconciler **fails the Run closed** with a clear condition
   (`RuntimeClassUnavailable`, naming the missing class) and **does not** create the pod. It **must
   not** fall back to `runc` / the node default to "keep the Run moving" — a silent downgrade turns a
   missing-handler ops problem into an isolation breach. RuntimeClass availability is a **documented
   cluster prerequisite (S1)**; its absence is an operator-visible failure, not a degrade path.

4. **Emit the pod under the selected class, in the Team namespace, as `ksquad-agent` (AC1, AC3).** The
   sandbox pod spec carries `runtimeClassName: <resolved>`, lands in the **Team namespace** (Story 4.1),
   runs as the namespaced **`ksquad-agent` SA**, and is a **per-Run pod** — one Run, one sandbox. No
   pod is shared by two Runs; no pod is reused across Runs or principals (teardown-and-replace, §9.3 /
   Story 4.5).

5. **Bind from the warm pool by (RuntimeClass × image) key (AC5).** The warm-pool claim keys on the
   resolved RuntimeClass, so a Kata Run binds a Kata warm pod and a gVisor Run binds a gVisor warm pod —
   **never a cross-class bind** (a gVisor pod handed to a Kata Run would silently downgrade isolation).
   If no warm pod of that class exists, the reconciler triggers scale-up / cold-start of that class
   (§9.2) — it does **not** substitute another class.

6. **Gate `docker: true` by the RuntimeClass mechanism (fail-closed, AC6 — §5.3.3).** A runtime with
   `capabilities.docker: true` on a **gVisor** class is admitted **only** when backed by a supported
   mechanism — a **daemonless rootless builder** (kaniko / buildah / BuildKit-rootless, the primary
   build path, which avoids the `setns(CLONE_NEWNET)` that failed under gVisor in ISI-2295) **or**
   **rootless `dockerd`** with the ISI-2319 production config (`--net=slirp4netns`, `slirp4netns` baked
   into the sidecar image, unprivileged, uid 1000). Real **nested-virt** Docker beyond rootless requires
   a **Kata** class. `docker: true` on gVisor with **none** of these selected is **rejected** — the flag
   is the gate, the RuntimeClass decides the mechanism (§9.1, spike-tunable, not structural).

## Acceptance Criteria

**AC1 — every sandbox pod is created under a selected RuntimeClass (gVisor default).**
Given a Run reaches `Claiming`, When its sandbox pod is created, Then the pod spec carries a non-empty
`runtimeClassName` resolved by the precedence chain
(`Run.spec.sandboxPolicy.runtimeClass` → `Role.runtimeClassHint` → `SandboxPool.runtimeClass` →
**`gvisor`**), and the resolved class is recorded on the Run status so the choice is auditable. A pod
with **no** `runtimeClassName` (node-default runtime) is never emitted for an untrusted Run.

**AC2 — `runc` is rejected for untrusted code (the AD-3 crux, fail-closed).**
Given a resolved RuntimeClass, When it is `runc` **or** empty/node-default, Then the Run is **rejected
by CEL/webhook** (fail-closed) unless an explicit, audited **`trustedDev: true`** escape flag is set.
The default and every untrusted Run resolve to **gVisor or Kata only**. A Run that runs untrusted agent
code on the shared-kernel `runc` boundary is a **construction failure**, not a runtime check.

**AC3 — every Run is a distinct sandbox; no boundary shared across Runs/principals/squads.**
Given two Runs (same or different squads), When their sandboxes exist, Then each is its **own pod** with
its **own kernel/syscall boundary** (per-Run `runtimeClassName`), landing in its **Team namespace**
(Story 4.1) as the namespaced `ksquad-agent` SA — **no process, network, or filesystem namespace is
shared** across Runs or across squads, and no pod is reused across Runs or principals (teardown-and-
replace, §9.3; the residue proof is Story 4.5, the cross-squad blast-radius proof is Epic X.1).

**AC4 — the selected RuntimeClass must exist; the operator fail-closes, never downgrades.**
Given a resolved RuntimeClass, When no `RuntimeClass` object of that name exists on the cluster, Then
the reconciler **fails the Run closed** with a `RuntimeClassUnavailable` condition (naming the missing
class) and creates **no pod**. It **must not** fall back to `runc` / the node default. RuntimeClass
availability is a **documented cluster prerequisite (S1)**; its absence surfaces as an operator-legible
failure, never a silent isolation downgrade.

**AC5 — the warm-pool claim binds a pod of the matching RuntimeClass (no cross-class reuse).**
Given the warm pool is keyed by (RuntimeClass × `AgentRuntime` image), When a Run of resolved class C
claims, Then it binds a warm pod of class **C** or triggers scale-up/cold-start of class **C** — it
**never** binds a pod of a different class. A gVisor pod handed to a Kata Run (or vice-versa) is a
silent isolation change and is disallowed.

**AC6 — `docker: true` is gated by the RuntimeClass mechanism (fail-closed).**
Given an `AgentRuntime` with `capabilities.docker: true` on a **gVisor** class, When the pod is
assembled, Then it is admitted **only** if backed by a **daemonless rootless builder** (kaniko/buildah/
BuildKit-rootless) or **rootless `dockerd`** (ISI-2319 config: `--net=slirp4netns`, unprivileged),
**else it is rejected**; real nested-virt Docker requires a **Kata** class. `docker: true` on gVisor
with no backing mechanism selected is a construction failure (§5.3.3, ISI-2300/ISI-2319).

**AC7 — the hostile-Run containment gate is satisfiable, and the overhead cost is documented, not
hidden.** Given the boundary this story builds, When Epic X.1's hostile-Run blast-radius test attacks a
Run (attempt to reach another squad's workspace/network/secrets or the node), Then the attempt is
**contained** by the RuntimeClass boundary (the hard gate on the ISI-2113 pick). And the known cost —
gVisor's build-heavy overhead (ISI-2295: compile 1.95×, churn 5.4× runc; masked for LLM-bound Runs,
real for build bursts) — is **recorded** (this story's Gate-status section, arch §9.1), with **Kata
opt-in** as the documented high-assurance/heavy-build escape hatch; it is **not** silently swallowed.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/runtimeclass-selection-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check: it first proves a **naive** selector (leaves `runtimeClassName` empty / defaults
to `runc`, ignores the cluster-prerequisite check and downgrades to runc when gVisor is absent, reuses
one warm pod across two Runs, and admits `docker:true` on gVisor with no backing mechanism) **fails**
the §9.1 isolation invariants — so the harness demonstrably detects a boundary violation — then proves
the §9.1 selector (gVisor-default precedence chain, `runc` rejected without `trustedDev`, fail-closed on
missing class, per-Run distinct pods, RuntimeClass-keyed pool bind, docker-mechanism gate) **passes**
all of them.

```
[model] precedence : sandboxPolicy>runtimeClassHint>pool>gvisor-default resolves correctly across 4 cases
[model] naive selector : 20 isolation violation(s) -> DETECTED (empty runtimeClassName, runc-downgrade, non-approved class, cross-class reuse, ungated docker)
[model] §9.1 selector : 0 violations; rejected=[r-runc, r-missing, r-weak, r-docker-bad]; 4 admitted -> 4 distinct pods
[model] PASS — naive detectably breaks isolation; §9.1 selection contract holds AC1-AC6.
```

It encodes the AC1–AC6 invariants as assertions over the *pod-spec + admission decision a reconciler
would produce* for sample Runs: (a) a non-empty `runtimeClassName` resolved by the precedence chain,
gVisor-default (AC1); (b) `runc`/empty rejected unless `trustedDev`, and — as an **allowlist, not a
denylist** — any non-approved class (installed-but-not-gVisor/Kata, e.g. an operator-added weak
`sysbox`) is likewise rejected for untrusted code (AC2, the crux; "resolve to gVisor or Kata only");
(c) two Runs → two distinct
pods, no shared pod/namespace, no cross-Run reuse (AC3); (d) a resolved class absent from the cluster
**fails closed** — a selector that downgrades to `runc` is a violation (AC4); (e) the warm-pool bind
matches the resolved class — a cross-class bind is a violation (AC5); (f) `docker:true` on gVisor
without a rootless-builder/rootless-dockerd/Kata backing is a violation (AC6). It exits non-zero if the
naive selector *stops* violating (teeth lost) or the §9.1 selector *ever* violates one invariant.
**AC7 (runtime hostile-Run containment)** is pinned in prose here and **proven at runtime by Epic
X.1's blast-radius test on the RuntimeClass under test** (real cluster) — the model check guards the
*static selection shape* (AC1–AC6), which is the construction-time crux; kernel-boundary containment is
a property of the runtime handler (gVisor/Kata), not of the selection logic.

## Out of scope (owned elsewhere)

- **Squad = namespace tenancy** (**4.1**, §12.1) — the RBAC/network/quota boundary the sandbox lands
  inside; this story adds the kernel boundary on top, it does not provision the namespace.
- **Per-Project workspace PVC + concurrency** (**4.3 / 4.4**, §9.4) — what the sandbox mounts; not the
  runtime it runs under.
- **Teardown-and-replace + per-principal PVC scoping + the residue/reuse proof** (**4.5**, §9.3/§9.4,
  Epic X.2) — this story asserts "distinct per-Run pod, no reuse"; 4.5 owns the teardown mechanism and
  the residue test that *proves* no state bleeds.
- **Default-deny egress + allowlist** (**4.6**, §12.2) — the network boundary; composes with, but is
  not, the RuntimeClass boundary.
- **Warm-pool sizing curve** (**3.4 / 3.5**, §9.2) — this story consumes the (RuntimeClass × image)
  pool key; the sizing policy/constants are ISI-2113/ISI-2292's (already locked).
- **Installing the RuntimeClass handler on the cluster** (infra/DevOps, ISI-2294 posture, S1) — a
  documented prerequisite; this story selects among installed classes and fail-closes on absence.
- **The hostile-Run blast-radius test itself** (**Epic X.1**, S4, NFR-SEC1) — this story builds the
  boundary; X.1 attacks it and is the hard gate on the pick.
