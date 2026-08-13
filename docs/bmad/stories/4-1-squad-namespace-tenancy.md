# Story 4.1: Squad = namespace tenancy (the isolation boundary)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS STORY LAYS THE ISOLATION BOUNDARY EVERY OTHER SECURITY GUARANTEE STANDS ON (arch §12.1,
> AD-5, ADR-011, D2).** Cross-squad isolation (NFR-SEC1), per-namespace credentials/PVCs, egress
> control (§12.2), and memory scoping (Epic 6.5) all assume that a `Team` **is** a Kubernetes
> namespace and that the control plane lives **elsewhere**. The load-bearing invariants are:
> **(1)** `Team` → namespace is **1:1 and deterministic** — adding squads = adding namespaces, no
> control-plane redesign (NFR-SCALE1); **(2)** the agent workload's grants are **least-privilege and
> namespaced** — a namespaced `Role`/`RoleBinding`, **never** a `ClusterRole` binding or a wildcard
> that reaches another squad (D2); **(3)** the control plane runs in a **separate system namespace**
> (`ksquad-system`), so a compromised sandbox cannot sit in the operator's blast radius. A reconciler
> that binds a `ClusterRole`, reuses one namespace for two Teams, or drops the quota/NetworkPolicy
> baseline is a **security failure, not a bug ticket**. Read AC2 and AC4 literally.

## Story

As a **platform engineer standing up squads on a shared cluster**,
I want **each `Team` to reconcile into its own dedicated Kubernetes namespace — provisioned with a least-privilege ServiceAccount + Role/RoleBinding, a `ResourceQuota` + `LimitRange`, and the boundary for per-namespace Secrets/PVCs — while the control plane stays in a separate `ksquad-system` namespace**,
so that **one squad can never reach another squad's workspace, Secrets, or network by construction; adding a squad is adding a namespace (no control-plane redesign); and least privilege is enforced by the platform, not by agent good behavior (arch §12.1, AD-5, D2, NFR-SEC1/NFR-SCALE1).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **D2** (least privilege by construction: RBAC, NetworkPolicy,
  Secrets, PVCs scope every workload), **NFR-SEC1** (cross-squad isolation), **NFR-SCALE1** (adding
  squads scales without control-plane redesign).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§12.1 — Tenancy boundary — a squad is a namespace (OQ7).** The authoritative decision: `Team` →
    one namespace; namespace is the RBAC / NetworkPolicy / quota / Secret boundary; a Team's Projects,
    Runs, sandbox pods, workspace PVCs and per-user Secrets live in **its** namespace; the control
    plane lives in `ksquad-system`. *"Adding squads = adding namespaces — no control-plane redesign."*
    Least privilege: an agent's ServiceAccount gets exactly its Role/Project grants, **never
    cluster-wide.**
  - **§12.2 — Egress control (OQ4/D5).** The **default-deny egress NetworkPolicy** baseline this story
    lays down; the **model-endpoint allowlist / `egressPolicyRef` proxy refinement** layers on top (see
    "Out of scope").
  - **§4 topology (line ~239) / §3.1 diagram (line ~225):** **Control plane** = `ksquad-system`
    (operator, apiserver, memory service, Postgres). **Data plane** = the per-`Team` namespace (sandbox
    pods, shims, agent runtimes, workspace PVCs). This story provisions the data-plane namespace; it
    does **not** move or touch `ksquad-system`.
  - **§5.1 `Team` CRD row:** `Team{ projects[], agents[] (refs), namespaceStrategy }` → **Team
    reconciler ensures namespace, RBAC, NetworkPolicy, quota.** This story **is** that reconciler's
    tenancy-provisioning path.
  - **§9.4 — Workspace & concurrency (per-principal scoping F6/D7):** the per-`Project` workspace PVC
    and per-principal build-cache partition live **in** this namespace. This story owns the namespace +
    the *boundary*; the PVC *shape/mount* is Story 4.3, and per-principal scoping within it is Story 4.5.
- **ADR:** **ADR-011 (Tenancy — namespace-per-Team)**, arch line ~2201: chosen over namespace-per-Project,
  namespace-per-Run, and label-selector tenancy. Do not re-litigate; implement it.
- **Depends on:** **Story 1.2** (the `Team` CRD type — `apiVersion: ksquad.io/v1alpha1`, kind `Team`,
  with `spec.namespaceStrategy`) and **Story 1.3** (the operator scaffold that runs reconcilers). If the
  `Team` type is not yet generated, wire against the §5.1 row and gate the envtest on it.
- **Blocks / is consumed by:** **4.2** (sandbox pods land in this namespace under the namespaced SA),
  **4.3** (Project workspace PVC provisioned here), **4.5** (per-principal scoping over these PVCs),
  **Epic 5** (Run reconcile schedules pods into this namespace), **Epic 6.5** (memory scope = this
  namespace / Team, AD-5), **§12.2** egress refinement (extends this namespace's NetworkPolicy),
  **Epic X.1** (the hostile-Run blast-radius test that *proves* this boundary holds).

## What the Team reconciler provisions (the §12.1 scaffold — authoritative)

On every reconcile of a `Team`, ensure (create-or-update, idempotent — AC5) the following objects. All
objects are **owned by the `Team`** (owner reference) except the namespace-scoped children, which are
owned by the namespace; a `Team` finalizer drives teardown (AC6).

1. **Namespace** — name **deterministically derived** from the `Team` (e.g. `ksquad-team-<team.name>`
   or `<namespaceStrategy.prefix><team.name>`, resolved once and recorded on `status.namespace`).
   1:1 with the `Team` (AC1). Labelled for the tenancy filter: `ksquad.io/team=<team.name>`,
   `ksquad.io/tenancy=squad` — the same label the memory/coord tenancy predicate (§7.3.3, §12.1) and
   NetworkPolicy selectors key on. **Never** `ksquad-system`.

2. **ServiceAccount** — one namespaced SA for the squad's agent workloads (e.g. `ksquad-agent`), in the
   Team namespace. Sandbox pods (4.2) run as this SA. **No** `automountServiceAccountToken` beyond what
   the workload needs.

3. **Role + RoleBinding** (namespaced — **NOT** `ClusterRole`/`ClusterRoleBinding`, AC2): the Role
   grants **exactly** the API access an agent workload needs **within its own namespace** (e.g. read
   its own ConfigMaps/Secrets by name, read pod status). No wildcard `resources: ["*"]` or
   `verbs: ["*"]`, no `nonResourceURLs`, no cross-namespace reach. The RoleBinding binds the Role to the
   `ksquad-agent` SA **only**. Per-Project grant narrowing (a Role per Project) is compatible and
   additive; the floor is namespaced-least-privilege.

4. **ResourceQuota** — one per namespace, bounding the squad's total CPU/memory/storage/pod/PVC count
   (values from `namespaceStrategy` / Helm defaults). A squad cannot starve the cluster or another
   squad. **Must exist** (AC3).

5. **LimitRange** — default + max container CPU/memory (and default PVC request), so a pod that omits
   requests/limits still lands bounded and cannot be scheduled unbounded. **Must exist** (AC3).

6. **Default-deny NetworkPolicy** — a baseline `podSelector: {}` policy with
   `policyTypes: [Ingress, Egress]` denying all cross-namespace ingress/egress (allow only intra-
   namespace + DNS as needed). This is the §12.1 cross-squad isolation baseline; the §12.2 model-
   endpoint **allowlist** and `egressPolicyRef` proxy layer **on top** of it (Out of scope, below).
   A namespace that ships without this policy is open by default — **must exist** (AC4).

7. **Secret / PVC boundary (not the objects themselves):** per-user Secrets (§11, BYO-per-principal)
   and per-`Project` workspace PVCs (§9.4, Story 4.3) are created **into this namespace** by their own
   owners. This story guarantees the *namespace + RBAC boundary* that makes those per-namespace and
   per-principal isolated; it does not mint the Secrets or size the PVCs.

**Control-plane separation (AC7):** none of the above is created in `ksquad-system`. The operator (which
*runs* in `ksquad-system`) writes these objects **into the Team namespace**. The reconciler must refuse
(fail-closed) to resolve a Team namespace equal to `ksquad-system` or any reserved system namespace.

## Acceptance Criteria

**AC1 — `Team` → namespace is 1:1 and deterministic.**
Given a `Team`, When it reconciles, Then exactly one dedicated namespace exists whose name is
deterministically derived from the `Team` and recorded on `status.namespace`. And two distinct `Team`s
never resolve to the same namespace (no collision). And re-reconciling the same `Team` does not create a
second namespace (AC5). And adding a squad is adding a namespace — no control-plane object is mutated
(NFR-SCALE1).

**AC2 — the agent workload's grants are least-privilege and namespaced (the D2 crux).**
Given the provisioned RBAC, When an agent workload acts, Then its access is granted **only** by a
namespaced `Role` + `RoleBinding` in its own namespace — **never** a `ClusterRole`/`ClusterRoleBinding`,
and never a `Role` rule with wildcard `resources`/`verbs` or any cross-namespace reach. And the
RoleBinding binds the Role to the squad's `ServiceAccount` only (not `system:authenticated`, not a
group). A grant that reaches another squad's namespace or a cluster-scoped resource is a **construction
failure**, not a runtime check.

**AC3 — every namespace ships with a ResourceQuota and a LimitRange.**
Given a reconciled `Team` namespace, When it is inspected, Then it contains **both** a `ResourceQuota`
(bounding aggregate CPU/memory/storage/pod/PVC count) **and** a `LimitRange` (default + max per
container, default PVC request). A pod that omits requests/limits is bounded by the LimitRange; the
squad's aggregate is bounded by the quota. Neither may be absent.

**AC4 — a default-deny NetworkPolicy is the namespace's baseline.**
Given a reconciled `Team` namespace, When network posture is inspected, Then a default-deny
`NetworkPolicy` (`podSelector: {}`, `policyTypes: [Ingress, Egress]`) is present, so a Run cannot reach
another squad's pods/services or the wider network by default. And any egress the squad needs is added
as an **explicit allowlist** on top (§12.2), never by removing the baseline. (This story lays the
baseline; the model-endpoint allowlist is §12.2 / Out of scope.)

**AC5 — reconcile is idempotent and safe to re-drive.**
Given a controller that re-reconciles a `Team` (steady state, restart, or crash mid-provision), When it
re-enters, Then every object is create-or-updated (server-side apply / create-if-absent) — no duplicate
namespace, no duplicate SA/Role/quota, no error on the already-exists path. A partially-provisioned
namespace converges to fully-provisioned on the next pass; the reconciler reports readiness via
`status.conditions` (e.g. `NamespaceReady`) so a half-built namespace is legible, never silently
assumed complete.

**AC6 — `Team` deletion tears the namespace down (finalizer, no orphan).**
Given a `Team` is deleted, When the finalizer runs, Then the Team namespace and all its contents
(SA/Role/quota/NetworkPolicy, and cascaded pods/PVCs/Secrets) are removed, and the finalizer is cleared
only after teardown completes — no orphaned namespace holding another tenant's future name, no leaked
PVC/Secret. `ksquad-system` is never touched.

**AC7 — the control plane stays in a separate system namespace.**
Given the operator runs in `ksquad-system`, When it provisions a Team namespace, Then **no** tenancy
object is created in `ksquad-system`, and the reconciler **fail-closes** (error + condition, no
provisioning) if a `Team` would resolve its namespace to `ksquad-system` or any reserved system
namespace. The data plane (sandbox pods, PVCs, shims) and the control plane never share a namespace.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/tenancy-isolation-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check: it first proves a **naive** over-permissive provisioner (binds a `ClusterRole`,
one shared namespace for all Teams, no quota/NetworkPolicy) **fails** the §12.1 isolation invariants —
so the harness demonstrably has the power to detect a boundary violation — then proves the §12.1
provisioner (namespaced least-privilege Role, 1:1 namespace, quota + LimitRange + default-deny NetPol,
`ksquad-system` separation) **passes** all of them.

```
[model] naive provisioner: 5 isolation violation(s) → DETECTED (ClusterRole bind, shared ns, no quota, no LimitRange, no default-deny NetPol)
[model] §12.1 provisioner : 0 violations; 2 Teams → 2 distinct namespaces, neither == ksquad-system
[model] PASS — naive detectably breaks isolation; §12.1 scaffold holds AC1–AC4/AC7.
```

It encodes the AC2/AC3/AC4/AC1/AC7 invariants as assertions over the *set of objects a reconciler would
create* for two sample Teams: (a) no `ClusterRole`/`ClusterRoleBinding` and no wildcard/cross-namespace
Role rule (AC2); (b) a `ResourceQuota` **and** a `LimitRange` per namespace (AC3); (c) a default-deny
`NetworkPolicy` per namespace (AC4); (d) distinct Teams → distinct namespaces, deterministic (AC1); (e)
no object in `ksquad-system` and no Team namespace == `ksquad-system` (AC7). It exits non-zero if the
naive provisioner *stops* violating (teeth lost) or the §12.1 provisioner *ever* violates one invariant.
**AC5 (idempotency) and AC6 (finalizer teardown)** are pinned in prose here and exercised by the
operator **envtest** (real API server) the dev writes with the reconciler — the model check guards the
*static isolation shape* (AC1–AC4/AC7), which is the construction-time crux.

## Out of scope (owned elsewhere)

- **RuntimeClass-selected sandbox isolation** for Runs (**4.2**, §9.1) — this story provisions the
  namespace the pods land in, not the pod runtime.
- **Project workspace PVC shape + mount** (**4.3**, §9.4) and **per-principal workspace/cache scoping +
  teardown-and-replace** (**4.5**, §9.3/§9.4) — this story owns the namespace boundary; those own what
  lives inside it.
- **Egress model-endpoint allowlist + `egressPolicyRef` proxy** (**§12.2**) — layers an explicit
  allowlist on top of AC4's default-deny baseline; not this story.
- **BYO per-principal Secret minting** (**§11**, Epic G/Agent credential model) — the namespace is the
  boundary; the Secrets are created by their owner into it.
- **The hostile-Run blast-radius test** (**Epic X.1**, S4, NFR-SEC1) that *proves at runtime* a Run
  cannot cross this boundary — this story builds the boundary; X.1 attacks it.
