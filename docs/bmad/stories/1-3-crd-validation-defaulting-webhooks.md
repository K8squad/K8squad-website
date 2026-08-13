# Story 1.3: CRD validation + defaulting webhooks

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🛡️ THIS IS THE ADMISSION GATE FOR THE CRD SURFACE 1.2 LANDED.** Story 1.2 defined the *shape* of
> `Team`/`Agent`/`Role`/`Skill`/`Project`/`Run` (+ `AgentRuntime`). This story makes the apiserver
> **reject a malformed or dangling CR at admission, with a message that tells the operator exactly what
> to fix** — before any reconciler ever sees it. Two properties are load-bearing:
> **(1)** the split between what **CEL/OpenAPI markers** can enforce (fields of the *same* object) and
> what needs a **validating admission webhook** (existence of a *referenced* object — `Team`→`Project`,
> `Agent`→`AgentRuntime`/`Role`/`Skill`/Secret). CEL cannot read another object; a cross-object rule
> written as a CEL `XValidation` is a **silent no-op** that admits the dangling ref. **(2)** the runtime
> flavor enum is **open-ended for shim vendors (FR-D3)** — a `type` outside the conformant set is
> **admitted behind an explicit `experimental` flag, never hard-rejected** (§5.3.1). Encoding
> `AgentRuntime.type` as a closed `+kubebuilder:validation:Enum` would lock out every future shim and
> violate FR-D3. Read AC3 and AC4 literally — those two are where this story earns its keep.

## Story

As a **developer applying CRs against the `ksquad.io/v1alpha1` API**,
I want **admission validation + defaulting for the CRD types — fail-closed enum checks and same-object
CEL rules in-schema, cross-object required-relationship checks in a validating webhook, and a mutating
webhook that fills sane defaults**,
so that **an invalid CR (a `Run.status.phase` outside the enum, an `Agent` whose `credentialSecretRef`
or `runtimeRef` does not resolve, a `Team` referencing a missing `Project`) is rejected at admission
with a clear, actionable message — while the runtime flavor enum stays open-ended for shim vendors
(FR-D3) so a new vendor runtime is admitted (behind `experimental`) without a CRD schema change.**

## Context & prerequisites (read first)

- **Architecture (authoritative):**
  - **§5.1 CRDs (`ksquad.io/v1alpha1`)** — the field surface these rules validate (Story 1.2 encoded it).
  - **§5.2 Operator** — *"CRD validation via CEL/webhooks (e.g. an `Agent` must resolve a credential
    Secret before it is admitted — **fail closed**, PRD NFR-SEC\*)."* This story is the concrete build
    of that sentence.
  - **§5.3.1 `AgentRuntime` CRD** — `type` (`claude-code | kimi-code | opencode | codex | openclaw |
    hermes`), `image`, `cliVersion`, `capabilities{docker,github,packageInstall}`. **Crux:** *"A `type`
    that has not passed conformance is admitted only behind an explicit `experimental` flag."* That is
    the FR-D3 open-endedness contract — the known set is the *conformant/preferred* set, not a closed
    schema enum.
  - **§5.3.3** — the capability fail-closed rule: `docker: true` on a gVisor-only RuntimeClass is
    rejected **unless** a rootless-dockerd sidecar or a Kata RuntimeClass is available. This is an
    *intra-object* rule (fields of the same `AgentRuntime`/`Skill.requires`) → CEL, not a webhook.
  - **§11 Credentials (ADR-010/ADR-032)** — the credential model has **three shapes** (§11 table):
    Claude-family **OAuth**, second-runtime **API key**, and **BYO model endpoint**. This is the
    "credential type" known set the ticket names → an enum classifier `oauth | apiKey | byoEndpoint`.
  - **§8** — the `Run.status.phase` state machine (the closed phase enum).
- **PRD:** **FR-D3** (OpenClaw/Hermes ship at v1; Claude Code/OpenCode follow — the *ecosystem
  extensibility* requirement that forbids a closed runtime enum), **FR-A1…A3** (declarative CRD
  surface), **NFR-SEC\*** (fail-closed admission).
- **Epics:** `docs/bmad/04-epics-and-stories.md` **Epic 1 story 1.3** (this story) — *"CRD validation +
  defaulting webhooks (or CEL validation) for the required relationships … an invalid CR is applied …
  admission rejects it with a clear message … enum fields (`runtime`, credential type) validate against
  the known set … Keep runtime enum open-ended enough for shim vendors (FR-D3)."*
- **Depends on (must be landable before this story is done):**
  - **Story 1.2 (ISI-2188)** — the six squad types exist as kubebuilder types with the §5.1 fields.
    This story adds validation/defaulting **on top of** those types.
  - **`AgentRuntime` type — see Prerequisite AC0.** Story 1.2 explicitly deferred the `AgentRuntime`
    *type* "to story 1.3" while the epics list scopes 1.3 as *validation+defaulting*. The type is
    therefore homeless. This story **folds in the `AgentRuntime` type definition** (Task 0) so its
    `type`/`capabilities`/`cliVersion` fields have something to validate and `Agent.runtimeRef` has a
    real target — but its *reason for existing* is the validation surface, not a seventh squad type. See
    Open Question 1 (route to Story Writer/Architect to confirm the fold vs. a dedicated 1.x).
- **Sibling / do-NOT-do-here:**
  - **`createdBy`/`ownedBy` immutability webhook is 1.6 (ISI-2304)** — that admission-defaulting +
    CEL-immutability rule for the principal-attribution fields is a *separate* story. Do **not** build
    the `ksquad.io/created-by` immutability rule here; only leave the annotation convention untouched.
  - **`OTelConfig` validation is 1.5** — the endpoint/protocol/Secret-ref checks for `OTelConfig` ride
    with that CRD's story, not this one.
  - **Reconciler-time resolution is Epic 1.3+ / per-epic.** This story rejects *at admission*. The
    deeper "does the referenced Secret actually contain a valid OAuth token / does the runtime image
    pull" checks are reconciler concerns (status conditions), **not** admission. Admission validates
    **existence + shape**, not liveness.
- **Blocks:** every epic that applies CRs and expects fail-closed admission — 5.7/5.8 (BYO/opencode
  runtime admitted via `experimental` + `byoModelEndpoint`), Epic 4 tenancy (`Team`→`Project` integrity),
  Epic 7 credentials (`Agent`→Secret resolves before admit).

## Acceptance Criteria

**AC1 — the validation is split by what each mechanism can actually enforce (§5.2).**
Given the CRD types, When validation is added, Then it is partitioned into exactly three mechanisms and
each rule lives in the **only** mechanism that can enforce it:
- **(a) CEL `+kubebuilder:validation:XValidation` + OpenAPI markers** — for **same-object** rules
  (enums, required fields, and intra-object cross-field rules like "`docker` capability requires a
  compatible RuntimeClass/sidecar", "`Skill.source` has exactly one of `inline`/`git`"). These run
  in-apiserver, need no webhook pod, and are the **default** (§5.2 "CEL/webhooks", CEL first).
- **(b) a `ValidatingAdmissionWebhook`** (controller-runtime) — for **cross-object** rules that require
  reading *another* object (existence of `Team.spec.projects[]`, `Agent.spec.runtimeRef`/`roleRef`/
  `skillRefs[]`/`credentialSecretRef`, `Run.spec.teamRef`/`projectRef`). **A cross-object rule MUST NOT
  be written as a CEL rule** — CEL evaluates against `self` only, so a CEL "the referenced Project
  exists" check cannot read the Project and silently admits the dangling ref (this is the AC8-FALSIFY
  case).
- **(c) a `MutatingAdmissionWebhook` (defaulting)** — for defaults that OpenAPI `+kubebuilder:default`
  cannot express or that depend on request context.
And each webhook is registered **fail-closed** (`failurePolicy: Fail`) so a webhook outage rejects
writes rather than admitting unvalidated CRs (NFR-SEC\*).

**AC2 — closed enum fields validate against their known set, fail-closed (§8, §5.3.6, §11).**
Given the closed-set fields, Then each carries `+kubebuilder:validation:Enum` (OpenAPI, in-schema) so an
out-of-set value is rejected at admission with a clear message:
- `Run.status.phase` ∈ `{Pending, Claiming, Running, Paused, Succeeded, Failed, Cancelled}` (§8);
- `Skill.spec.source.type` ∈ `{inline, git}` (§5.3.6);
- `Project.spec.repo.sync.provider` ∈ the supported SCM provider set (§5.4);
- the **credential-type classifier** ∈ `{oauth, apiKey, byoEndpoint}` (§11 three-row model) — see AC7
  for *where* this field lives.
These are genuinely closed sets (a new phase or a fourth credential shape is an architecture change, not
a vendor extension) — contrast AC3.

**AC3 — the runtime flavor enum is OPEN-ENDED for shim vendors (FR-D3) — the crux.**
Given `AgentRuntime.spec.type`, Then it is **NOT** a closed `+kubebuilder:validation:Enum`. Instead:
- the **conformant/known set** `{claude-code, kimi-code, opencode, codex, openclaw, hermes}` is
  documented and is the value the defaulting webhook and console offer;
- an **unknown `type`** (a new shim vendor's flavor) is **admitted iff `spec.experimental: true`** is
  set — a same-object CEL rule: `self.type in <knownSet> || self.experimental == true`;
- an unknown `type` **without** `experimental` is **rejected with a clear message** that names the fix:
  *"runtime type '<x>' is not in the conformant set (…); set spec.experimental: true to run a
  pre-conformance runtime, or pass the shim conformance suite (ISI-2114)."*
This satisfies both halves of the ticket at once: `Agent.runtime` "outside the enum" *is* rejected (when
non-experimental), **and** the enum stays open for vendors (FR-D3) — a new runtime needs **zero CRD
schema change**, only `experimental: true`. Encoding `type` as a closed OpenAPI enum is an explicit
FALSIFY failure (AC8).

**AC4 — cross-object required-relationship validation rejects dangling refs with a clear message (§5.2).**
Given a CR whose ref does not resolve, When it is applied, Then the validating webhook (AC1b) rejects it
with a message naming the **object, the field, and the missing target**:
- `Team.spec.projects[]` / `agents[]` → each referenced `Project`/`Agent` must exist (the ticket's
  headline example: *"Team 'x' references Project 'y' which does not exist in namespace 'z'"*);
- `Agent.spec.runtimeRef` → an `AgentRuntime` must exist; `roleRef` → a `Role`; `skillRefs[]` → each
  `Skill`; `credentialSecretRef` → a Secret must exist (§5.2 *"an Agent must resolve a credential Secret
  before it is admitted — fail closed"*);
- `Run.spec.teamRef` / `projectRef` → the `Team`/`Project` must exist.
Refs resolve **within the namespace** (namespaced group, §5.1) unless a ref carries an explicit
namespace. Admission validates **existence + kind**, not liveness/health (that is the reconciler's
status-condition job) — so a Secret that exists but holds an expired token still *admits* (and the Agent
reconciler surfaces the health condition). Each denial message is actionable (AC7).

**AC5 — capability fail-closed rules are intra-object CEL, not a webhook (§5.3.3).**
Given `AgentRuntime.spec.capabilities` (and `Skill.spec.requires`), Then the capability-safety rules are
**same-object CEL** (AC1a):
- `docker: true` is admitted only with a compatible mechanism selected (a `dockerd` sidecar path or a
  Kata-capable posture) — a gVisor-only + `docker:true` + no-sidecar CR is rejected (§5.3.3);
- `capabilities` default to **all-false** (fail-closed; AC6) so an unspecified capability is *denied*,
  never ambient (§5.3.1 "capabilities are declared, not ambient").
Because these read only fields of the same object, they are CEL — putting them in the webhook would be
correct-but-wasteful; putting the *cross-object* rules (AC4) in CEL would be silently wrong. AC1's
split is the invariant.

**AC6 — a defaulting (mutating) webhook fills fail-closed, sane defaults (§5.3.1).**
Given a CR with optional fields unset, When admitted, Then the mutating webhook (or `+kubebuilder:default`
where a static default suffices) sets:
- `Team.spec.namespaceStrategy` → the platform default strategy;
- `AgentRuntime.spec.experimental` → `false` (so an unknown type without an explicit opt-in is rejected,
  AC3);
- `AgentRuntime.spec.capabilities.{docker,github,packageInstall}` → `false` (fail-closed, AC5);
- `Run.status.phase` initial default → `Pending` where the reconciler has not yet set it (§8);
- other static shape defaults per §5.1.
Defaults are **fail-closed**: an omitted security-relevant field defaults to the *safe/denied* value,
never the permissive one. Static defaults use `+kubebuilder:default`; only context-dependent defaults
need the mutating webhook.

**AC7 — every denial message is clear and actionable (ticket "clear message"; NFR-USE).**
Given any admission rejection (AC2–AC5), Then the returned status message **names the offending
field-path, the observed value, and the fix** — e.g. `spec.credentialSecretRef: Secret
"claude-oauth" not found in namespace "squad-acme"` or `spec.phase: "Runing" is not a valid phase
(one of Pending|Claiming|…); did you mean "Running"?`. A bare `admission webhook denied the request`
with no field context is an AC7 failure. Where the credential-type classifier lands (a discriminator on
the Secret ref, or a `spec` field) is confirmed in Open Question 2; the *message contract* holds
wherever it lands.

**AC8 — one runnable falsification self-check with a mutation spine (§5.2; the review teeth).**
Given the webhooks + markers wired against a real apiserver (`envtest`), Then this story leaves **one
runnable table-driven check** that is falsifiable by construction:
- **Valid-CR baseline:** a fully-wired `Team`+`Project`+`Agent`+`AgentRuntime`+`Role`+`Skill`+`Run`
  fixture set **admits** (baseline green) — so the test is non-vacuous (it is possible to pass).
- **Invalid-CR table (each asserts rejection AND a message substring, AC7):**
  1. `Run.status.phase = "Bogus"` → rejected, msg names `phase` + the enum (AC2);
  2. `AgentRuntime.type = "acme-shim"`, `experimental` unset/false → rejected, msg names the conformant
     set + the `experimental` fix (AC3);
  3. `AgentRuntime.type = "acme-shim"`, `experimental: true` → **admitted** (AC3 open-endedness — this
     arm proves the enum is genuinely open, not just absent);
  4. `Agent.credentialSecretRef = "missing"` (no such Secret) → rejected, msg names the field + the
     namespace (AC4/AC7);
  5. `Team.projects = ["ghost"]` (no such Project) → rejected, msg names Team→Project (AC4);
  6. `AgentRuntime.docker=true` on a gVisor-only, no-sidecar posture → rejected (AC5).
- **Mutation spine (falsification — the anti-tautology teeth):** the check is designed so that
  **removing each guard flips its case from reject→admit**: delete the AC3 CEL rule → case 2 admits
  (RED); rewrite AC4's `runtimeRef`/`credentialSecretRef` existence check as a `self`-only CEL rule →
  cases 4/5 admit (RED, proving the CEL-can't-cross-objects trap is real); drop the `failurePolicy:
  Fail` → a killed webhook admits case 4 (RED). Each guard is thereby proven **load-bearing**, with no
  vacuous arm (case 3 + the valid baseline are the non-vacuous controls). No new framework — standard
  `testing` + controller-runtime `envtest`, matching 1.1/1.2 conventions.

## Tasks / Subtasks

- [ ] **Task 0 — land the `AgentRuntime` type (prerequisite; see OQ1).** Define `AgentRuntime`
  (`type`, `image`, `cliVersion`, `capabilities{docker,github,packageInstall}`, `credentialSecretRef`,
  `experimental bool`) per §5.3.1 as a kubebuilder type in `api/v1alpha1`, `make generate manifests`.
  *This exists so AC3/AC5 have a target and `Agent.runtimeRef` resolves; scope it minimally — the
  ImageUpdater/warm-pool behavior (§5.3.5) is not this story.*
- [ ] **Task 1 — closed-enum markers (AC2).** Add `+kubebuilder:validation:Enum` to `Run.status.phase`,
  `Skill.spec.source.type`, `Project.spec.repo.sync.provider`, and the credential-type classifier;
  regenerate CRDs; confirm out-of-set values reject in-schema (no webhook).
- [ ] **Task 2 — open-ended runtime rule (AC3, the crux).** Do **NOT** add an `Enum` marker to
  `AgentRuntime.spec.type`. Add the same-object CEL `XValidation`:
  `self.type in [<known set>] || self.experimental == true`, with `message` = the actionable
  conformant-set + `experimental` guidance (AC7).
- [ ] **Task 3 — intra-object capability CEL (AC5).** Encode the §5.3.3 `docker`-capability rule and the
  `Skill.source` exactly-one-of rule as same-object CEL `XValidation`.
- [ ] **Task 4 — validating webhook: cross-object refs (AC4).** Scaffold a controller-runtime
  `ValidatingAdmissionWebhook` covering `Team`/`Agent`/`Run`. For each ref, a client `Get` of the
  target; on not-found, deny with the field-path + missing-target message (AC7). Register
  `failurePolicy: Fail` (AC1, fail-closed).
- [ ] **Task 5 — mutating webhook: defaults (AC6).** Static defaults via `+kubebuilder:default`
  (`experimental=false`, capabilities `false`, `phase=Pending`); the mutating webhook only for
  context-dependent defaults (`namespaceStrategy`). Register the webhook.
- [ ] **Task 6 — envtest falsification self-check (AC8).** Table-driven `_test.go` under `envtest`: the
  valid baseline + the six invalid cases (assert reject + message substring) + case 3 admit. Document
  the mutation spine (which guard-deletion flips which case) as a comment block so the reviewer (Epic
  14 / code-review) has the teeth pre-mapped.
- [ ] **Task 7 — wiring + docs.** `config/webhook` manifests, cert-manager/`admissionregistration`
  registration per kubebuilder convention; do **NOT** touch the `createdBy` immutability rule (1.6) or
  `OTelConfig` validation (1.5).

## Dev Notes

- **The AC1 split is the whole story. Get it wrong and one half is silently useless.** CEL
  `XValidation` runs in-apiserver against `self` — it **cannot** read another object. So *every*
  cross-object existence rule (`Team`→`Project`, `Agent`→`Secret`/`AgentRuntime`, `Run`→`Team`) **must**
  be in the validating webhook; writing it as CEL produces a rule that always passes and admits the
  dangling ref. Conversely, same-object rules (enums, `docker`-capability, `source` one-of, the
  open-ended `type` rule) belong in CEL — a webhook for them is a needless pod on the write path. AC8's
  mutation spine exists precisely to catch a cross-object rule mis-filed as CEL (it flips green when the
  rule is neutered).
- **FR-D3 is why `AgentRuntime.type` is NOT a closed enum.** The ecosystem requirement is that new shim
  vendors (OpenClaw/Hermes at v1, then others) plug in **without a core/CRD change**. A closed
  `+kubebuilder:validation:Enum` on `type` would force a schema bump + redeploy for every new runtime —
  exactly the lock-in FR-D3 forbids. The resolution (§5.3.1) is a **known-set-OR-experimental** CEL
  rule: conformant runtimes are named and preferred; a pre-conformance runtime is admitted behind
  `experimental: true` and advertises the gap honestly. The ticket's "reject `Agent.runtime` outside the
  enum" and "keep runtime enum open-ended (FR-D3)" are both satisfied by this one rule — reject when
  *non-experimental*, admit when the vendor opts in.
- **Admission validates existence + shape, not liveness.** `credentialSecretRef` resolving means *the
  Secret exists*, not *the token is valid* — token validity/refresh is the credential controller's job
  (§11.1/ADR-032) surfaced as a status condition, not an admission decision. Blocking admission on
  liveness would make CR apply flaky against transient backend state; keep the admission line at
  existence + kind.
- **Fail-closed everywhere (NFR-SEC\*).** `failurePolicy: Fail` on both webhooks; capability defaults
  `false`; unknown runtime without `experimental` rejected; an omitted security-relevant field defaults
  to the denied value. A webhook outage must reject writes, not wave them through.
- **The ticket's "§7.2 (credentialType enum)" citation is stale — corrected to §11.** In the current
  architecture, **§7.2 is the memory data model** (`memory_record`/`diary_entry`), which has no
  credential enum. The credential model with its three shapes (OAuth / API key / BYO endpoint) is **§11
  (ADR-010, ADR-032)**. This story validates the credential-type classifier against that §11 three-row
  set. Flagged to the Architect as Open Question 3 (fix the epics-table cross-reference).
- **Leave room for 1.6 and 1.5.** `createdBy`/`ownedBy` admission-defaulting + immutability (ISI-2304)
  is 1.6; `OTelConfig` endpoint/protocol/Secret-ref validation is 1.5. Both are validation-shaped and
  will reuse this story's webhook scaffold — but their *rules* are their own stories. Do not pre-empt.

### Project Structure Notes

- **Repo shape:** markers live on the existing type files in `api/v1alpha1/` (Story 1.2). The webhooks
  land under `api/v1alpha1/*_webhook.go` (kubebuilder `webhook` convention) with generated manifests in
  `config/webhook`; wiring in the manager `main.go` (`SetupWebhookWithManager`). Cert wiring via
  cert-manager per the kubebuilder default (1.1's chart).
- **Conventions:** kubebuilder `+kubebuilder:validation:*` / `+kubebuilder:webhook:*` markers;
  controller-runtime `admission.Validator`/`admission.Defaulter` (or the newer
  `CustomValidator`/`CustomDefaulter`) interfaces — follow whatever 1.1/1.2 landed. Standard `testing` +
  `envtest`; no new validation library.
- **Namespaced refs:** ref resolution defaults to the CR's own namespace (namespaced group, §5.1);
  honor an explicit `namespace` on a ref where the type allows it.

### References

- [Source: docs/bmad/03-architecture.md#5.2 Operator] — *"CRD validation via CEL/webhooks (e.g. an
  Agent must resolve a credential Secret before it is admitted — fail closed)."* The sentence this story
  builds.
- [Source: docs/bmad/03-architecture.md#5.3.1 AgentRuntime CRD] — the runtime `type` known set +
  *"admitted only behind an explicit `experimental` flag"* (the FR-D3 open-endedness contract);
  `capabilities` declared-not-ambient.
- [Source: docs/bmad/03-architecture.md#5.3.3 Service sidecars] — the `docker`-capability fail-closed
  rule (intra-object → CEL, AC5).
- [Source: docs/bmad/03-architecture.md#5.1 CRDs] — the ref surface validated cross-object (AC4) and the
  closed enums (`Run.status.phase`, `Skill.source`, `sync.provider`).
- [Source: docs/bmad/03-architecture.md#8 Run Lifecycle] — the `status.phase` closed enum (AC2).
- [Source: docs/bmad/03-architecture.md#11 Credentials / ADR-010, ADR-032] — the three credential shapes
  (OAuth / API key / BYO endpoint) = the credential-type known set (AC2/AC7). **This is the correct home
  for the ticket's mislabeled "§7.2 credentialType enum" reference.**
- [Source: docs/bmad/02-prd.md FR-D3] — OpenClaw/Hermes ship at v1; Claude Code/OpenCode follow — the
  ecosystem-extensibility requirement that forbids a closed runtime enum (AC3).
- [Source: docs/bmad/04-epics-and-stories.md — Epic 1 story 1.3] — the story AC (invalid CR rejected
  with clear message; enum fields validate; runtime enum open-ended for shim vendors, FR-D3).

### Open questions (route to the named owner; do not block the validation surface on these)

1. **`AgentRuntime` type home (Story Writer / Architect).** Story 1.2 deferred the `AgentRuntime` *type*
   "to story 1.3"; the epics list scopes 1.3 as *validation+defaulting*. This story folds the type in
   (Task 0) so its fields have something to validate. Confirm the fold vs. carving a dedicated 1.x
   `AgentRuntime`-type story (and 5.7/5.8 depend on it existing before Phase-4 shim work). *Does not
   block Tasks 1–7 — model AgentRuntime here regardless; only the story-numbering bookkeeping is open.*
2. **Credential-type classifier placement (Architect / Winston).** The §11 model has three credential
   shapes but no explicitly-named `credentialType` field on any CRD today (`credentialSecretRef` is a
   bare Secret ref). Confirm whether the classifier is (a) a discriminator field on the ref, (b) a label
   on the Secret, or (c) inferred by the credential controller — this story validates the enum wherever
   it lands. *Model it as an optional `spec` discriminator for now; refine in Epic 7.*
3. **Fix the stale epics cross-reference (Architect).** Epics story 1.3 cites *"§7.2 (credentialType
   enum)"* but §7.2 is the memory data model; the credential model is §11. Route a one-line correction
   to the epics table (§7.2 → §11) so the reference stops misleading readers.

## Dev Agent Record

### Agent Model Used

_(dev agent to fill)_

### Debug Log References

### Completion Notes List

### File List
