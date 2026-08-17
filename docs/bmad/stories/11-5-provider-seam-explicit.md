# Story 11.5: Provider seam explicit (`SourceControlProvider` interface locked for GitLab/Bitbucket drop-in)

Status: ready-for-dev (spec) — build gated on Epic-11 build wave (Wave-1 substrate)

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The interface-formalization story — it locks the `SourceControlProvider` seam that 11.1
> already defines so that 11.2–11.4 build against a *frozen* contract and a second provider
> (GitLab/Bitbucket) is a **new impl + config, zero reconciler rewrite**.** This is
> **near-zero net-new**: 11.1's reconciler already consumes *only* the normalized seam (AC1,
> §10.2 discipline). 11.5 makes the seam **explicit, exhaustive, and testable** — it enumerates
> every capability the reconciler needs (issues, PRs, checks, artifacts, webhook parsing +
> signature verification), pins them behind one Go interface in `pkg/scm` (§17.3), and proves
> **neutrality differentially**: identical normalized records reconcile through a `github` impl
> and a `gitlab` stub to **identical mirror state**. A seam that **leaks a provider-specific type**
> into the reconciler, a reconciler that **branches on `provider.name`**, a capability the loop
> reaches for **outside** the interface (a direct GitHub API call), or a webhook whose parsing/HMAC
> lives in the reconciler instead of the provider impl is a **regression**. This is the **same
> seam discipline as the §10 A2A/MCP shims** — the moat is that spec drift in one provider never
> reaches coord. Detail it **first** (before 11.2/11.3/11.4) so those stories reference a locked
> interface. Read AC1, AC2, AC5 literally.

## Story

As **a platform engineer**,
I want the **`SourceControlProvider` seam made explicit and exhaustive** — every SCM capability
the repo-sync reconciler needs (issues, PRs, checks, artifacts, webhook parsing, HMAC verification)
expressed **only** through one normalized Go interface in `pkg/scm` (§17.3), with GitHub as the v1
impl,
so that **a second provider (GitLab/Bitbucket) is a new impl + config with zero reconciler change,
provider-specific API churn never reaches coord (§10.2), and 11.2–11.4 build against a frozen
contract.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 11 row **11.5** — *the provider seam
  explicit so GitLab/Bitbucket can follow without redesign: all GitHub API access sits behind the
  provider interface (issues/PRs/checks/artifacts/webhook parsing); adding a provider = new impl +
  config, no reconciler rewrite.* **Same seam discipline as §10 shims.**
- **The contract this formalizes:** `docs/bmad/stories/11-1-repo-sync-reconciler.md` — AC1 ("the
  reconciler talks ONLY to the `SourceControlProvider` seam") and its **C1 differential** (reconcile
  the same records through `github` + `gitlab` → identical mirror state). 11.1 *defines* the seam;
  **11.5 freezes and enumerates it.** These two stories are satisfied-by-design together (the
  sequencing doc calls 11.5 near-zero net-new).
- **Architecture:** `docs/bmad/03-architecture.md` **§5.4** (repo-sync reconciler & provider seam —
  read whole), **§10.2** (provider-seam spec-drift discipline — the load-bearing analogy),
  **§17.3** (`pkg/scm` package home), **§5.1** (`Project.repo.sync{provider,...}` — the `provider`
  discriminator selects the impl at construction time, **not** at reconcile time). **ADR-018**
  (repo-sync provider seam + mirror-not-authority + field-ownership/echo-suppression).
- **Seam analogy (§10.2):** this is structurally the **same discipline** the A2A/MCP shims use —
  the reconciler is written against a normalized vocabulary; a provider adapter translates the
  concrete API (GitHub REST/GraphQL, GitLab, Bitbucket) to/from that vocabulary; **version/shape
  drift is contained in the adapter** and never crosses into the loop. See
  `docs/bmad/stories/5-6-conformance-suite.md` for the shim-seam conformance pattern this mirrors.
- **What the interface MUST cover (enumerated from 11.2–11.4/11.6 needs):**
  1. **Issues** — list + get + (optional, direction-gated) status/label write. (11.2)
  2. **Pull requests** — list + get with `state ∈ {open, merged, closed}` + `review_state` +
     `head_sha`. (11.3)
  3. **Checks / CI** — list check-runs per PR/ref with `conclusion` + published-artifact refs. (11.4)
  4. **Artifacts** — resolve a published artifact to a `scm_artifact_ref` (stable id + fetch
     descriptor; the seam returns a **reference**, never streams bytes through coord). (11.4)
  5. **Webhook parsing** — parse a raw delivery into a **normalized event** (kind + external ids +
     actor) *behind the seam*. (11.1/all)
  6. **Webhook signature verification** — verify the provider's HMAC scheme against a
     `webhookSecretRef` **before any parse** (each provider signs differently). (11.1 AC4)
- **Scope guard:** 11.5 is **interface formalization + conformance harness only.** No new reconciler
  behavior, no new mirror rows (those are 11.2–11.4). It **must not** introduce a coordination path;
  the seam is read-mostly (mirror-read) with optional direction-gated writes owned by 11.2/11.3.
  **The real Go interface + GitHub v1 impl land in the Epic-11 build wave** (gated on Wave-1
  substrate per the sequencing doc); this story pins the construction-time contract they satisfy.

## Acceptance Criteria

**AC1 — every SCM capability the reconciler needs is on ONE interface, nothing else (the seam crux).**
Given the repo-sync codebase, When it is reviewed (and grepped), Then **all** provider access —
issues, PRs, checks, artifacts, webhook parse, webhook signature verify — is reached **only** through
the `SourceControlProvider` interface in `pkg/scm` (§17.3); the reconciler package imports **no**
provider-specific API client type (no `google/go-github`, no `xanzy/go-gitlab`) and makes **no**
direct provider HTTP call. A capability reached **outside** the interface (a direct GitHub call in
the loop, webhook HMAC verified in the reconciler instead of the provider impl) is a **regression**.

**AC2 — the reconciler is provider-neutral: same records → same mirror (the neutrality crux, differential).**
Given identical normalized records, When they reconcile through the **GitHub v1 impl** and a **GitLab
stub impl** behind the same interface, Then both produce **byte-identical mirror state** (same
`scm_*` rows, same provenance) — the reconciler **never branches on `provider.name`** and never
special-cases a concrete provider. A reconciler where `provider == "github"` gates behavior (so a
drop-in provider yields different/empty state) is a **regression**. *(This is 11.1's C1, re-asserted
as 11.5's acceptance — the seam is proven by the drop-in, not by inspection alone.)*

**AC3 — adding a provider is impl + config, zero reconciler edit (the drop-in crux).**
Given a new provider is needed, When it is added, Then the diff is **(a)** a new file implementing
`SourceControlProvider` + **(b)** a `provider:` value in `Project.repo.sync` (§5.1) + **(c)**
registration in the provider factory — and **zero lines** change in the reconcile loop, the mirror
upsert, or the webhook ingress. A change that requires editing the reconciler to onboard a provider
is a **regression** (the seam failed its purpose).

**AC4 — the interface is normalized, not GitHub-shaped (the vocabulary crux).**
Given the interface types, When reviewed, Then they are **provider-neutral vocabulary** — `Issue`,
`PullRequest{state,reviewState,headSHA}`, `CheckRun{conclusion}`, `ArtifactRef`, `Event{kind,ids,
actor}` — with **no GitHub-specific enum values or field names** leaking into the signature (no
`mergeable_state`, no GitHub node-id as the canonical id). Each provider adapter **maps** its native
shape onto this vocabulary. A GitHub-shaped interface that a GitLab impl cannot satisfy without
lying is a **regression**.

**AC5 — webhook parse + HMAC verify live behind the seam, verify-before-parse preserved (the security crux).**
Given an inbound raw webhook delivery, When it is handled, Then **signature verification** and
**payload parsing** are **provider-impl responsibilities** exposed through the interface
(`VerifySignature(secret, raw) → bool` **then** `ParseEvent(raw) → Event`), and the ingress calls
**verify before parse** (11.1 AC4, D8/NFR-SEC8) — the reconciler/ingress never inlines a
provider-specific HMAC scheme. A shared/inlined HMAC check, or a parse reachable before verify, is a
**regression**.

## Tasks / Subtasks

- [ ] **(Epic 11 build)** Define `pkg/scm.SourceControlProvider` (§17.3) enumerating the six
  capability groups (issues, PRs, checks, artifacts, webhook parse, webhook verify) in **normalized
  vocabulary** (AC4); document each method's field-ownership tag (external-owned vs never-written).
- [ ] **(Epic 11 build)** GitHub v1 impl mapping the native API onto the interface; a **GitLab stub
  impl** (compile-only, enough to prove the differential) so AC2/AC3 have teeth.
- [ ] **(Epic 11 build)** A **provider factory** keyed on `Project.repo.sync.provider` (§5.1) —
  construction-time selection, never a reconcile-time branch.
- [ ] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/scm-provider-seam-check.py`) in 11.1's model-check style: a faithful model
  of the seam — one interface, a factory, two impls (`github` + `gitlab`), an ingress that
  verify-then-parses.
- [ ] **Five checks C1–C5 ↔ AC1–AC5**, GREEN on the §5.4/§10.2/ADR-018-conformant baseline:
  - **C1 (AC1)** — grep-style: no provider-specific import/call outside the impl; every capability
    routes through the interface.
  - **C2 (AC2, differential)** — reconcile identical records through both impls → identical mirror
    rows.
  - **C3 (AC3)** — add a third stub impl by config only; reconciler source unchanged → still
    converges.
  - **C4 (AC4)** — interface signatures carry no GitHub-specific enum/field; the GitLab stub
    satisfies them without special-casing.
  - **C5 (AC5)** — ingress calls `VerifySignature` before `ParseEvent`; verify/parse are provider-impl
    methods.
- [ ] **Mutation battery** (≥10), each flipping its designated check RED, no vacuous survivors:
  seam-bleed (`import go-github` in loop / `if provider=="github"`) → C1/C2 RED; drop-in-requires-edit
  (factory branches into reconciler) → C3 RED; GitHub-shaped field in interface → C4 RED;
  parse-before-verify / inlined-HMAC → C5 RED.
- [ ] `python3 scm-provider-seam-check.py` → **exit 0** (baseline GREEN; all mutations CAUGHT).

## Dev Notes

- **Why first:** 11.2/11.3/11.4 all consume this interface. Freezing it before they are detailed/built
  means those stories reference a **locked** contract, not a moving one — no re-cut when a later
  story discovers a missing capability. This is why the sequencing doc puts 11.5 at the head of the
  detailing order despite its low numeric.
- **Why near-zero net-new:** 11.1 already wrote the reconciler against the seam (its AC1 + C1
  differential). 11.5 does not invent the seam — it **enumerates and freezes** it so the drop-in
  guarantee is a **tested** property, not a hopeful one. Expect the diff to be mostly the interface
  file + the GitLab stub + the conformance check.
- **Seam discipline is the moat (§10.2):** identical to how A2A/MCP protocol drift is contained in an
  adapter (`versions.go` / conformance suite, story 5.3/5.6), SCM provider drift is contained in the
  impl. The differential check is the teeth: a `provider.name` branch survives inspection but dies the
  moment a second impl must produce identical state.
- **Verify-before-parse is a seam property, not just an ingress property:** because each provider
  signs differently, the HMAC scheme **must** be a provider-impl method — otherwise the ingress
  inlines GitHub's scheme and a GitLab drop-in silently can't verify. This is why AC5 pins
  `VerifySignature`/`ParseEvent` **onto the interface**, ordered verify→parse.
- **No coordination path:** the seam is mirror-read (+ optional direction-gated writes owned by
  11.2/11.3). It **never** exposes claim/lease/fence; custody stays server-side (§6, no-P2P).

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/scm-provider-seam-check.py` → **exit 0** —
  baseline GREEN on C1–C5; mutation battery all CAUGHT, no vacuous survivors; C2/C3 **differential**
  (two/three impls → identical mirror) for teeth against seam-bleed.
- **Deferred to Epic 11 build (integration):** the real `pkg/scm.SourceControlProvider` + GitHub v1
  impl + GitLab stub, the provider factory keyed on `Project.repo.sync.provider`, proven by
  `pkg/scm` unit tests + the reconciler integration suite (the same records through two impls).

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 11 row 11.5 (provider seam explicit; same seam
  discipline as §10 shims).
- [Source: docs/bmad/stories/11-1-repo-sync-reconciler.md] — AC1 + C1 differential this story freezes.
- [Source: docs/bmad/03-architecture.md#5.4] — repo-sync reconciler & provider seam; §10.2 (seam
  spec-drift discipline), §17.3 (`pkg/scm`), §5.1 (`Project.repo.sync.provider`). ADR-018.
- [Source: docs/bmad/stories/5-6-conformance-suite.md] — the shim-seam conformance pattern this mirrors.
- [Source: docs/bmad/stories/epic-11-sequencing-and-readiness.md] — detailing order (11.5 first) + the
  build-gate rationale.

## Dev Agent Record

_(empty — spec authored by the Story Writer; the build wave fills this in when the real `pkg/scm`
interface + GitHub v1 impl land.)_
