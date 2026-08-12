# Story 1.2: Define Team, Agent, Role, Skill, Project, Run CRD types

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧱 THIS IS THE CRD SURFACE EVERY LATER EPIC BUILDS ON.** These six types are the **desired-state
> contract** for the whole platform — reconcilers (Epic 1.3+/§5.2), the Run state machine (Epic 3/§8),
> tenancy (Epic 4/§12.1), the shim seam (Epic 5/§10), credentials (Epic 7/§11), and the console read
> models (Epic 8/§13) all resolve or watch these objects. Two properties are load-bearing and
> non-negotiable: **(1)** work items, comments, claims, artifacts and memory records are **Postgres rows,
> NOT CRDs** (ADR-001/ADR-002) — a `Run` *references* a work item via an **opaque coordination-DB
> pointer** (`spec.workItemRef`), it never owns it as an etcd object; **(2)** every capability an `Agent`
> or `Skill` exposes is **CRD/operator-authorized, never self-declared at runtime** (§5.3.6, D8). Read AC6
> and AC7 literally — getting `workItemRef` wrong (embedding the work item, or making it an owned etcd
> object) reintroduces the split-brain ADR-001 exists to prevent.

## Story

As a **squad author scaffolding the `ksquad.io/v1alpha1` API**,
I want **the six squad-composition CRD types — `Team`, `Agent`, `Role`, `Skill`, `Project`, `Run` — defined as Go kubebuilder types with the exact `spec`/`status` fields from architecture §5.1**,
so that **the operator (Epic 1.3), the Run state machine (Epic 3), the shim (Epic 5) and the console (Epic 8) all resolve one versioned, validated desired-state contract — with `Run.spec.workItemRef` an opaque coordination-DB pointer (ADR-001), not an owned etcd object.**

## Context & prerequisites (read first)

- **Architecture (authoritative):** `docs/bmad/03-architecture.md` **§5.1 CRDs (`ksquad.io/v1alpha1`)** — the CRD table + the `> Work items … are not CRDs` note + the `createdBy` annotation note (r20). This story **encodes that table verbatim**. Also **§5.2** (operator: one reconciler per CRD, `status.observedGeneration` + conditions, CEL/webhook fail-closed validation), **§8** (`Run` lifecycle/phase enum), **§10.3** (`modelEndpointRef` BYO model-endpoint seam, ADR-026), **§5.3** (`AgentRuntime` — separate CRD, story 1.3, referenced by `Agent.runtimeRef`), **§5.3.6** (`Skill.spec.source` inline|git).
- **PRD:** `docs/bmad/02-prd.md` — **FR-A1** (declarative squad composition), **FR-A2** (CRD-defined agents/roles/skills). This story lands the *types*; the reconcilers that act on them are Epic 1.3+.
- **Epics:** `docs/bmad/04-epics-and-stories.md` — **Epic 1 story 1.2** (this story) + the **5.7 gap flag** (`modelEndpointRef` on `Agent` — closed here at Gate 2 before 5.7 builds) + **1.6/ISI-2304** (`createdBy`/`ownedBy` land *on top of* these types — do not pre-empt them; leave the `metadata.annotations[ksquad.io/created-by]` hook per the §5.1 note but the admission-defaulting/immutability webhook is 1.6).
- **Depends on (must be landable before this story is done):**
  - **Story 1.1** — the `ksquad.io` group at `v1alpha1` scaffolded (kubebuilder project, `zz_generated.deepcopy.go`, `config/crd`, namespaced-by-default, K8s libs pinned in `go.mod`). This story adds the six types **into** that group.
- **Sibling / do-NOT-do-here:**
  - **`AgentRuntime`** (§5.3) is a **separate CRD** authored in **story 1.3** (it is still absent from 1.2 per the 5.7 flag). This story defines `Agent.spec.runtimeRef` as a **ref to** it; it does not define the `AgentRuntime` type.
  - **`OTelConfig`** is **story 1.5** — a platform-scoped config CRD, **not** one of the six squad-composition types. Do not add it here.
  - **`SandboxPool`** is an **internal** CRD (§5.1, §9) — scaffold it only if 1.1's scope included it; the six squad types are the deliverable of *this* story.
- **Blocks:** Epic 1.3 (reconcilers), 1.4 (Helm CRD install), and every downstream epic that resolves these types (2/3/4/5/7/8). A wrong field name here ripples into all of them.

## Acceptance Criteria

**AC1 — six kubebuilder types in `api/v1alpha1`.**
Given the `ksquad.io/v1alpha1` group (1.1), When the types are defined, Then `Team`, `Agent`, `Role`, `Skill`, `Project`, `Run` each exist as a Go `+kubebuilder:object:root=true` type with `Spec` (and, where the table lists status, `Status`) structs, `make generate manifests` regenerates `zz_generated.deepcopy.go` and CRD manifests under `config/crd`, and all six register into the namespaced `ksquad.io` group. And each type carries a `//+kubebuilder:resource` shortname/category where it aids `kubectl` ergonomics (non-load-bearing).

**AC2 — `Team` spec (§5.1).**
Given `Team`, Then `spec` carries `projects[]` (refs), `agents[]` (refs), and `namespaceStrategy`. The `Team` is the **tenancy boundary** (§12.1) — its reconciler (1.3) ensures namespace/RBAC/NetworkPolicy/quota, but this story defines only the *type*.

**AC3 — `Agent` spec (§5.1, incl. the CEO 5.7 `modelEndpointRef` field).**
Given `Agent`, Then `spec` carries **all** of:
- `runtimeRef` → an `AgentRuntime` (story 1.3);
- `roleRef` → a `Role`;
- `skillRefs[]` → `Skill`s;
- `credentialSecretRef` → the per-user credential Secret (§11, BYO-lock ADR-010);
- `capabilityOverrides` — overrides applied to the generated **Agent Card** capabilities (§10.1) (the AC's `agentCardOverrides`);
- `model` — the resolved model name;
- **`modelEndpointRef?`** — **optional** ref to a per-user Secret holding a BYO / Ollama / OpenAI-compatible model endpoint (§10.3, ADR-026, `byoModelEndpoint` capability). *This is the field Epic 5.7 flagged as required at Gate 2 before 5.7 builds (CEO 2026-08-11) — it MUST be present.*
- `contextBudgetOverride?` (§8.5);
- `fallbackModel?` (§8/§10.3 rate-limit fallback — optionally its own endpoint/credential).

And `modelEndpointRef`, `contextBudgetOverride`, and `fallbackModel` are **optional** (`omitempty`, pointer/`?`) — an Agent on a paid provider with a default budget sets none of them.

**AC4 — `Role` and `Skill` specs (§5.1, §5.3.6).**
Given `Role`, Then `spec` carries `promptRef`, `defaultSkills[]`, `runtimeClassHint` (data-only, validated). Given `Skill`, Then `spec` carries `source{inline|git}` (§5.3.6 — `git` fetches a body via `pkg/scm` pinned to a commit SHA; the fetched body is **untrusted (D8)**), `mcpToolRefs[]`, `permissions`, and `requires{toolchains[], sidecars[]}` (§5.3.4 — drives operator pod assembly). The `permissions`/`mcpToolRefs` **capability envelope is CRD-authorized, never self-declared by a git-sourced body** (§5.3.6 trust boundary).

**AC5 — `Project` spec (§5.1, §5.4, §8.5).**
Given `Project`, Then `spec` carries `repo` (URL/ref/auth + `sync{provider, webhookSecretRef, mirror{}, reflectOutbound}` §5.4), `workspacePVC` (size/class), `egressPolicyRef`, `goals`, and `contextBudget` (§8.5 default budget).

**AC6 — `Run` spec + status (§5.1, §8) — `workItemRef` is the crux.**
Given `Run`, Then `spec` carries `teamRef`, `projectRef`, **`workItemRef`**, `inputs`, `sandboxPolicy`, `agents[]`, and `retryPolicy`; and `status` carries `phase`, `sandboxRef`, `claimedAt`, `conditions`, and `artifactRefs`. And:
- **`spec.workItemRef` is an opaque coordination-DB pointer string (ADR-001) — NOT an owned etcd object and NOT the embedded work item.** It is documented in the Go field comment as *"opaque id into the apiserver/coordination Postgres (§4/§6); the Run references the work item, it does not own or embed it (ADR-001)."* (This satisfies the §5.1 note verbatim; `workItemRef` is the arch table's `workItemSelector` under the ticket's field name.)
- **`status.phase`** is the §8 enum: `Pending | Claiming | Running | Paused | Succeeded | Failed | Cancelled` (CEL-validated to that set).
- `status.artifactRefs` are **refs** to artifact rows (coord/Postgres, §6.1) — the artifacts themselves are **not embedded** in the CRD.

**AC7 — no Postgres-row concept is a CRD (ADR-001/ADR-002).**
Given the six types, When defined, Then **no** type embeds or owns work items, comments, claims, artifacts, or memory records — those are Postgres rows behind the apiserver/memory APIs (§4). The only bridge is `Run.spec.workItemRef` / `Run.status.artifactRefs` as **opaque references**. Verified by a review check + the AC8 self-check (a Run round-trips through deepcopy carrying only a `workItemRef` string, never a nested work-item struct).

**AC8 — fail-closed validation markers + one runnable self-check (§5.2).**
Given each type, Then required refs carry `+kubebuilder:validation:Required` and the enums (`Skill.source`, `Run.status.phase`) carry `+kubebuilder:validation:Enum` so CEL/OpenAPI validation **fails closed** (e.g. an unknown `phase`, or a `Skill` with neither `inline` nor `git` source, is rejected at admission — the deeper "an `Agent` must resolve its credential Secret before admission" webhook is the reconciler's job in 1.3, referenced not built here). And this story leaves **one runnable check**: a table-driven `_test.go` that constructs each of the six types, round-trips it through the generated `DeepCopy`, and asserts (a) `Run.Spec.WorkItemRef` is a plain string field (no embedded work-item struct — AC7), (b) an out-of-set `Run.Status.Phase` fails validation, and (c) an `Agent` with `ModelEndpointRef` set marshals/unmarshals cleanly (AC3 — the 5.7 field is really there). No new framework — standard `testing`, matching 1.1 conventions.

## Tasks / Subtasks

- [ ] **Task 1 — `Team`, `Role`, `Skill` types (AC1, AC2, AC4).** *Data-mostly types first — no status subresource.*
  - [ ] `Team.Spec{ Projects []ObjectRef; Agents []ObjectRef; NamespaceStrategy string }`.
  - [ ] `Role.Spec{ PromptRef ...; DefaultSkills []ObjectRef; RuntimeClassHint string }`.
  - [ ] `Skill.Spec{ Source SkillSource (inline|git, §5.3.6, SHA-pinned git via pkg/scm); McpToolRefs []...; Permissions ...; Requires SkillRequires{ Toolchains[], Sidecars[] } }`. `+kubebuilder:validation:Enum` on `source`; document the D8 untrusted-body / CRD-authorized-envelope trust boundary in the field comment.
- [ ] **Task 2 — `Agent` type incl. `modelEndpointRef` (AC3).** *The 5.7 gate field lands here.*
  - [ ] `Agent.Spec` with `RuntimeRef`, `RoleRef`, `SkillRefs[]`, `CredentialSecretRef`, `CapabilityOverrides`, `Model`, **`ModelEndpointRef *SecretRef` (`omitempty`, §10.3/ADR-026)**, `ContextBudgetOverride *... (§8.5)`, `FallbackModel *... (§8/§10.3)`.
  - [ ] Field comments cross-reference §10.3 for `modelEndpointRef` and note it is the CEO-2026-08-11 / Epic-5.7 field.
- [ ] **Task 3 — `Project` type (AC5).**
  - [ ] `Project.Spec{ Repo RepoSpec{ URL/Ref/Auth, Sync SyncSpec{ Provider, WebhookSecretRef, Mirror, ReflectOutbound } }; WorkspacePVC PVCSpec{ Size, Class }; EgressPolicyRef; Goals; ContextBudget (§8.5) }`.
- [ ] **Task 4 — `Run` type: spec + status, `workItemRef` opaque (AC6, AC7).** *Get this one right — everything downstream watches it.*
  - [ ] `Run.Spec{ TeamRef; ProjectRef; WorkItemRef string /* opaque coord-DB pointer, ADR-001 */; Inputs ...; SandboxPolicy ...; Agents []ObjectRef; RetryPolicy ... }`.
  - [ ] `Run.Status{ Phase RunPhase (Enum: Pending|Claiming|Running|Paused|Succeeded|Failed|Cancelled, §8); SandboxRef; ClaimedAt *metav1.Time; Conditions []metav1.Condition; ArtifactRefs []ObjectRef /* refs, not embedded, §6.1 */; ObservedGeneration }`.
  - [ ] `+kubebuilder:subresource:status`; `+kubebuilder:validation:Enum` on `phase`.
  - [ ] Explicitly document (Go comment) that `WorkItemRef` is an opaque id, **not** an owned etcd object / **not** the embedded work item (ADR-001).
- [ ] **Task 5 — generate + validate + self-check (AC1, AC8).**
  - [ ] `make generate manifests` → `zz_generated.deepcopy.go` + six CRDs under `config/crd`; all register into the namespaced `ksquad.io/v1alpha1` group.
  - [ ] Add the table-driven `_test.go` self-check (AC8): six types constructed + deepcopy round-trip; `Run.Spec.WorkItemRef` is a string (no nested work item); out-of-set `phase` rejected; `Agent.ModelEndpointRef` round-trips.
  - [ ] **Do NOT** add the `createdBy`/`ownedBy` admission-defaulting webhook (that is 1.6/ISI-2304) — leave the `metadata.annotations[ksquad.io/created-by]` convention per the §5.1 note but no defaulting/immutability logic here.

## Dev Notes

- **This is the desired-state half of ADR-002; Postgres is the other half.** The single most common way to get this wrong is to reach for a CRD to model a work item, a comment, a claim, an artifact, or a memory record. **Don't.** Those are Postgres rows (§4/§6/§7). The `Run` CRD is the *only* type that touches coordination data, and it does so through **`spec.workItemRef` (an opaque id) + `status.artifactRefs` (refs)** — never by embedding or owning. Embedding the work item, or making `workItemRef` a K8s owner reference to an etcd object, reintroduces the exact dual-write/split-brain that ADR-001 (one Postgres, source-of-truth for coordination) exists to prevent.
- **`modelEndpointRef` is the Gate-2 field — it MUST be present (AC3).** Epic 5.7 explicitly flagged that arch §5.1 adds `modelEndpointRef` to the `Agent` CRD and *"Epic 1 story 1.2 must add that field at Gate 2 before 5.7 builds"* (CEO 2026-08-11). It is optional at runtime (a paid-provider Agent omits it) but the *field* is not optional in this story. It rides the **existing §10.3 model-endpoint seam (ADR-026)** — a Secret-ref endpoint + per-Agent `model`, negotiated by the `byoModelEndpoint` capability. It is **not** a new `AgentRuntime.type` and **not** a new image (that category error is recorded in ADR-026).
- **`AgentRuntime` is story 1.3, not this one.** `Agent.spec.runtimeRef` is a *ref*; the `AgentRuntime` CRD (§5.3, the pluggable coding-agent flavor + `cliVersion` policy) is authored separately. Same for `OTelConfig` (1.5, platform-scoped config, not a squad type). Keep this story to the six squad-composition types.
- **Capabilities are CRD-authorized, never self-declared (D8, §5.3.6).** A git-sourced `Skill` body is untrusted; its `permissions`/`mcpToolRefs` envelope is the operator's, set on the CRD, never elevated by the fetched repo. Encode the enum + the trust-boundary comment now so the reconciler (1.3) and the review-time covert-channel check (Epic 14) have something to enforce against.
- **Leave room for 1.6.** `createdBy`/`ownedBy` (ISI-2304) land on `Team`/`Project`/`Agent`/`Run` on top of these types with admission defaulting + immutability webhooks. This story only honors the `metadata.annotations[ksquad.io/created-by]` *convention* from the §5.1 note — no defaulting logic, no CEL immutability rule here (that's 1.6's AC).

### Project Structure Notes

- **Repo shape:** the Go monorepo is scaffolded by story 1.1. These types belong under **`api/v1alpha1/`** (kubebuilder convention, arch §11.2 `api/v1alpha1`), one file per kind (`team_types.go`, `agent_types.go`, `role_types.go`, `skill_types.go`, `project_types.go`, `run_types.go`) + the generated `zz_generated.deepcopy.go`. CRD manifests land under `config/crd`.
- **Conventions:** follow whatever 1.1 landed — kubebuilder markers, `metav1.TypeMeta`/`ObjectMeta` embedding, `metav1.Condition` for `Run.status.conditions`, standard `testing` table-driven `_test.go`. Do not introduce a new validation library; use `+kubebuilder:validation:*` markers + (deferred to 1.3) CEL/webhooks.
- **Refs are typed but light:** model cross-CRD refs (`runtimeRef`, `roleRef`, `skillRefs[]`, `teamRef`, `projectRef`, `agents[]`) as name (+optional namespace) refs, not K8s `OwnerReference`s — ownership/GC semantics are a reconciler concern (1.3), and `workItemRef`/`artifactRefs` point at Postgres, not etcd.

### References

- [Source: docs/bmad/03-architecture.md#5.1 CRDs (`ksquad.io/v1alpha1`)] — the six-type table (Team/Agent/Role/Skill/Project/Run) + the `Work items … are not CRDs` note + `createdBy` annotation note (r20); r26 (ISI-2188) added `roleRef`/`skillRefs`/`modelEndpointRef` to the Agent row and clarified `capabilityOverrides` = agent-card overrides.
- [Source: docs/bmad/03-architecture.md#5.2 Operator] — one reconciler per CRD, `status.observedGeneration` + conditions, CEL/webhook fail-closed admission (validation the reconcilers enforce; the *types* + markers land here).
- [Source: docs/bmad/03-architecture.md#8 Run Lifecycle] — the `status.phase` state machine `Pending→Claiming→Running→{Succeeded|Failed|Cancelled|Paused}`.
- [Source: docs/bmad/03-architecture.md#10.3 Model-provider seam (ADR-026)] — `Agent.spec.modelEndpointRef` = Secret-ref BYO/Ollama endpoint + per-Agent `model`, `byoModelEndpoint` capability; not an `AgentRuntime.type`.
- [Source: docs/bmad/03-architecture.md#5.3.6] — `Skill.spec.source` inline|git (SHA-pinned via pkg/scm); untrusted body (D8) but CRD-authorized capability envelope.
- [Source: docs/bmad/03-architecture.md ADR-001 / ADR-002] — one Postgres source-of-truth for coordination; CRDs for desired state — the reason `workItemRef` is a DB-row pointer, not an owned etcd object.
- [Source: docs/bmad/04-epics-and-stories.md — Epic 1 story 1.2 + story 5.7 gap flag] — the six-type AC + the `modelEndpointRef` Gate-2 requirement; `AgentRuntime`/`OTelConfig`/`createdBy` are sibling stories (1.3/1.5/1.6).

### Open questions (route to the named owner; do not block the six types on these)

1. **`inputs` / `sandboxPolicy` shape (Architect / Winston).** The ticket AC names `Run.spec.inputs` and `Run.spec.sandboxPolicy` (beyond the arch table's `workItemSelector`/`projectRef`/`agents[]`/`retryPolicy`). `inputs` = free-form run parameters folded into the §8.5 context envelope; `sandboxPolicy` = the RuntimeClass/isolation selection input to §9.1 sandbox assembly. Confirm these two are Run-spec fields (this story models them as such) vs. resolved elsewhere — *does not block Tasks 1–4; model them as opaque structured fields and refine in 1.3.*
2. **`AgentRuntime` sequencing (Architect / Story Writer).** `Agent.runtimeRef` points at a type authored in **1.3**. Confirm 1.3 lands the `AgentRuntime` type before Epic 5.7 builds (the 5.7 flag names both `modelEndpointRef` *and* the still-absent `AgentRuntime` CRD). This story closes the `modelEndpointRef` half; 1.3 closes the `AgentRuntime` half.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
