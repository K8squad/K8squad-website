# Story 5.6: Runnable conformance suite — the gate that makes "works in any squad, zero core changes" a fact, not a promise

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🧭 THIS IS THE GATE THAT ENFORCES THE MOAT (arch §7.5 / §12, FR-D5, S5/S6, NFR-EXT1). [GATE-BLOCKING]**
> Epic 5's whole claim is *"a vendor drops a runtime into any squad with zero core changes."* Stories
> 5.1–5.5 build the seam; **this story is the executable proof that a given shim actually honors it.**
> A vendor runs **one command** against their shim + a throwaway Ollama container and gets a **pass/fail
> verdict on C1–C10** — Agent Card validity, task-lifecycle, SSE progress, artifact emission,
> capability-flag honesty, credential-metadata correctness — with **no paid credentials and no access to
> Squad's core source**. Passing **is** the definition of "conformant": *works in any squad, zero core
> changes.* The load-bearing property of this deliverable is **not** that it runs — it is that it has
> **teeth**: the suite MUST go RED on a non-conformant shim and GREEN on a conformant one. A conformance
> suite that is green on a broken shim is worse than none — it launders a leaky runtime as certified.
> That is the exact **ISI-2346-F1 "guard with no teeth"** failure, now applied to the gate itself. Read
> the load-bearing invariants and AC2 literally — the teeth are the story.

## The load-bearing invariants (read first — the falsification proves these)

The suite is a projection of the **ISI-2114 §12 assertions C1–C10** into a **vendor-runnable harness**.
Four properties make that harness *worth running* — each is mutation-checked in the runnable
falsification, each maps to a named risk:

1. **TEETH / ADVERSARIAL VALIDITY (AC2, the crux — R1/R3, ISI-2346-F1 class).** Every check Cn must
   **FAIL a shim that violates Cn** and **PASS one that honors it**. A check that is green on both is
   **vacuous** and certifies nothing. This is the one invariant a conformance suite cannot get wrong:
   its value is entirely its *detecting power*. The falsification is therefore **meta** — it mutates the
   **shim under test**, not the suite, and asserts the suite catches each mutation; then it proves each
   headline check is **load-bearing** by stubbing it vacuous and showing the violating shim leaks
   through. A suite whose checks pass a broken shim has *negative* value (false assurance).

2. **VENDOR-INDEPENDENCE / SELF-CONTAINED ($0) (AC1 / AC4, FR-D5, ISI-2157).** The suite is a runnable
   `conformance/` harness a **third party** executes with **one command** against **their** shim — no
   Squad core source, no cluster access, no paid API key. Its default lane resolves the model to a **BYO
   Ollama endpoint** (§11 / §10.3), driven by the **`opencode` runtime (Story 5.8)**, so proving
   conformance costs **$0**. Output is a **machine-readable C1–C10 pass/fail matrix + a process exit
   code** (0 = conformant). "Independently executable" is a correctness property, not a convenience: a
   suite that needs Squad's private infra cannot certify an outside vendor.

3. **CAPABILITY-FLAG HONESTY IS BIDIRECTIONAL (AC3 → C5/C6, FR-D4 / R3).** The suite catches **both**
   directions of dishonesty: a card that **omits** a gap or **forges** a capability the runtime lacks
   (C5 fidelity), **and** a runtime that **exercises** a capability its card declared `false` — e.g.
   emits `input-required` while advertising `interactive:false` (C6 honesty). Omission and forgery are
   both defects; the R3 leak is a card the core reads as "capable" dispatching to a runtime that is not.

4. **NO-SECRET-MATERIAL + AUTH-LIFECYCLE (AC3 → C7, FR-G2 / §11 / §10.1).** The suite **fails** a shim
   whose Agent Card carries token bytes (the "shim never logs credential material" rule), and one whose
   auth failure surfaces as a generic `failed` instead of the first-class `auth-required` → `Paused`
   pause signal. Credential correctness is metadata-shape + lifecycle, never material.

## Story

As **a runtime vendor (and Squad's own CI, §14 / ISI-2157)**,
I want **a single-command, self-contained conformance suite that runs the ISI-2114 §12 C1–C10 assertions
against any shim — checking Agent Card validity, task-lifecycle dedup/cancel, SSE ordering + resume,
artifact idempotency + fencing, capability-flag honesty (both directions), and credential-metadata
correctness — with the model resolved to a BYO Ollama endpoint driven by the `opencode` runtime so it
needs zero paid credentials, and that emits a machine-readable C1–C10 verdict + a pass/fail exit code**,
so that **"a conformant runtime drops into any squad with zero core changes" (S5/S6/NFR-EXT1) is an
*executable, adversarially-valid* fact rather than a promise — a passing shim is certified drop-in, a
non-conformant shim is caught before it reaches a squad (never laundered as certified by a toothless
gate), and any vendor can prove conformance for $0, closing the FR-D5 gate that S5/S6 sit behind.**

## ⚠️ Scope reconciliation — 5.6 vs ISI-2114 vs 5.1/5.2/5.3/5.7/5.8/5.10 (read first — they interlock on purpose)

The epic issue (ISI-2218) says *"Given a shim, when the suite runs, then it checks Agent Card validity,
task-lifecycle, SSE progress, artifact emission, capability-flag honesty, credential-metadata
correctness; Ollama lane included."* Several neighbours own the *pieces the suite asserts against*; this
story owns exactly **the vendor-runnable harness that asserts them** and consumes the rest:

| Concern | Owned by | This story does |
|---|---|---|
| The **assertions themselves** — C1–C10 definitions, six-verb contract, SSE/Card/artifact schemas, the §12 spec | **ISI-2114** (`design/agent-shim-interface-spec.md` §12) | **implements** C1–C10 as a runnable harness; does not redefine them |
| The **buildable reference OpenClaw shim** + the harness **scaffold** (`pkg/shim/openclaw`, `conformance/`) | **ISI-2114 child spike** (§13) | **wraps/packages** the scaffold into a vendor-facing single-command suite; is the reference shim's first consumer |
| **Generating** the Agent Card from the CRD (the card C5/C6 validate) | **Story 5.2** (ISI-2214) | **checks** the card's fidelity/honesty; does not generate it |
| **Pinning** the A2A/MCP wire rev the suite asserts against | **Story 5.3** (`pkg/a2a@rev`) | asserts against the **pinned** rev (§8 spec-drift); an upgrade re-runs this suite before release |
| The **core-side A2A client** (C10's zero-core-change counterpart) | **Story 5.1** (ISI-2213) | runs the **C10 grep-gate** (no `type ==` in reconciler/coord) + a second-runtime lane |
| The **BYO Ollama model endpoint** + credential shape | **Story 5.7 / 7.5** (§10.3, ADR-026) | **uses** it as the $0 lane; does not build the endpoint or its Secret |
| The **`opencode` runtime shim** that drives the Ollama lane | **Story 5.8** | the reference runtime the Ollama lane runs; this story wires the lane, 5.8 supplies the runtime |
| **CI wiring** of the suite into the nightly/release free-testing lane | **Story 14.8 / ISI-2157/2158** | ships the runnable suite 14.8 **invokes**; does not own the CI workflow |
| The **`rate_limited` capability + signal** (a future C-check) | **Story 5.10** | leaves a **C-slot** for it (§5.10 says "conformance checks the signal"); does not implement 5.10 |

**One-line boundary:** ISI-2114 §12 answered *"what must a shim satisfy to be conformant?"* (C1–C10).
This story answers *"how does a vendor **run** those checks — one command, $0, machine-readable verdict —
such that the checks actually **catch** a non-conformant shim rather than rubber-stamp it?"* The teeth,
the packaging, and the Ollama lane are this story; the assertion semantics and the reference shim binary
are consumed from ISI-2114 and its child spike.

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **FR-D5** (a runnable conformance suite executable independently;
  suite owned by ISI-2114), **FR-D4** (capability flags first-class — C5/C6), **NFR-EXT1/EXT2**
  (zero-core-change extensibility — C10), **S5/S6** (a vendor runtime drops into a squad; two runtimes
  in one squad), **FR-OLLAMA / ISI-2157** (the $0 CI/conformance lane).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§7.5 "launch runtimes + conformance"** — the shim conformance suite is the S5/S6 gate; a runtime
    is drop-in **iff** it passes.
  - **§10.1 "Shim placement & contract"** — capability flags first-class (FR-D4/R3); **"the shim never
    logs credential material"** (C7's no-material teeth).
  - **§10.2 / §8 "Spec-drift isolation"** — the suite asserts against the **pinned** `pkg/a2a@rev`
    (Story 5.3); a rev bump re-runs the suite before release.
  - **§10.3 / ADR-026 "model-endpoint seam"** — Ollama is a **model backend, not an `AgentRuntime.type`**;
    the BYO endpoint is the credential-free lane (C9 + the $0 lane).
  - **§11.2 (`shims/conformance`)** — the suite's home in the shim workspace.
- **Companion design (consumed, NOT re-specified):** **`docs/bmad/design/agent-shim-interface-spec.md`
  (ISI-2114)** — **§12 the conformance suite** and its **C1–C10 table** (the authoritative assertion
  list this story implements verbatim), **§3** the six MUST-verbs, **§4** the SSE schema, **§5** the
  artifact contract, **§6** the Agent Card schema + CRD→card mapping, **§7** the credential-injection
  contract, **§9** the OpenClaw reference shim, **§11** the Ollama lane, **§13** the delegated buildable
  harness (the scaffold this story packages), **§14 AC1–AC5** (the spike's own acceptance).
- **Depends on:**
  - **ISI-2114** — **`done`** on the board (the §12 spec + reference OpenClaw shim + `conformance/`
    scaffold are its deliverable; the epic-doc "todo" note is stale). This is the **gate** 5.6 sits
    behind; it has landed, so 5.6 can be authored and built, not just scoped provisionally.
  - **Story 5.2** (ISI-2214 — Agent Card generation the C5/C6 checks validate). Soft: the suite can run
    against the §6.1 card schema.
  - **Story 5.7 / 7.5** (BYO Ollama endpoint + its Secret shape — the $0 lane's model backend).
  - **Story 5.8** (`opencode` runtime — the reference runtime the Ollama lane drives; **board-ratified
    into v1**, ISI-2131). Hard dependency for the *runnable* Ollama lane; the harness structure + teeth
    land against the reference OpenClaw shim first.
  - **Story 5.3** (`pkg/a2a@rev` — the pinned rev the suite asserts against).
- **Blocks / is consumed by:** **Story 14.8 / ISI-2157/2158** (the $0 CI free-testing lane invokes this
  suite; scaffolded-and-skipped-with-reason until 5.6 + 5.8 land), **Story 5.7/5.8** (their DoD is
  "passes the conformance Ollama lane"), **Story 5.10** (adds the `rate_limited` C-check into the slot
  this suite leaves), **every future runtime shim** (the drop-in certificate).

## The conformance suite contract (authoritative)

### §A — The suite IS the ISI-2114 §12 C1–C10, run black-box against the shim's six verbs (AC1/AC3)

The suite drives the shim through **only** the six A2A MUST-verbs (§3) + the Agent Card (§6) — the same
black-box surface the core uses — and runs each assertion:

| Check | What it asserts (ISI-2114 §12) | Epic-AC phrase it satisfies |
|---|---|---|
| **C1** | Deterministic-id dedup: two `SubmitTask` same id ⇒ exactly one agent execution | task-lifecycle conformance |
| **C2** | Artifact idempotency: re-emit same `(work_item_id, run_id, kind)`+sha ⇒ one row (upsert) | artifact emission |
| **C3** | Fence rejection: `EmitArtifact` with a stale fence ⇒ rejected, blob unreferenced | artifact emission |
| **C4** | SSE ordering + resume: strictly-increasing gap-free `seq`; re-`StreamEvents` resumes from `lastSeq` | SSE progress |
| **C5** | Agent Card fidelity: card reflects CRD+runtime; every cap key present & explicit-boolean; a widening override ⇒ validation error | Agent Card validity + capability-flag honesty |
| **C6** | Capability honesty: a runtime advertising `interactive:false` **never** emits `input-required` | capability-flag honesty |
| **C7** | Auth-failure → `auth-required`→`Paused` (never generic `failed`) **and** no secret material on the card | credential-metadata correctness |
| **C8** | Cancel is terminal + idempotent: `CancelTask` drains to `canceled`; cancelling a terminal task = no-op success | task-lifecycle conformance |
| **C9** | BYO endpoint routing: `byoModelEndpoint:true` runtime honors the injected Ollama base-URL | Ollama lane |
| **C10** | Zero-core-change: runtime joins with no reconciler/coord diff (grep-gate: no `type ==` special-casing) | "works in any squad, zero core changes" |

The suite makes **no assumption about `runtime.type`** — it is the C10 property applied to the harness
itself. Two runtimes with identical capability cards run the **identical** check path.

### §B — The suite has TEETH: it is validated adversarially, not by a happy-path demo (AC2, the crux)

A conformance suite is only as good as its detecting power. The suite ships with a **differential
falsification** that, for each Cn, runs it against a **shim that violates exactly Cn** and asserts the
verdict is **RED**, and against the **reference-conformant shim** and asserts **GREEN**. It further
proves each headline check is **load-bearing** by **stubbing that check vacuous** (`return PASS`) and
showing the violating shim then **leaks through** — the check body, not an incidental side effect, is
what catches the defect. **A green-on-broken check fails the story.** This is the same discipline as the
sibling benches, but aimed at the gate itself: the thing that certifies runtimes must itself be certified
to catch non-conformance.

### §C — The Ollama lane is the DEFAULT lane, $0, driven by `opencode` (AC4)

The suite resolves the model to a **BYO Ollama endpoint** (§11/§10.3) served by a throwaway Ollama
container with a **digest-pinned small model**, driven by the **`opencode` runtime (5.8)**. The **same**
C1–C10 assertions run on this lane — it is **not** a reduced subset. No paid API key is ever required
(C9 proves the injected base-URL is honored, not a baked-in provider). This is what makes the suite a
**$0 way for any vendor to prove conformance** and the substrate for the 14.8 CI lane.

## Acceptance Criteria

**AC1 — the suite runs the full ISI-2114 §12 C1–C10 against a shim through only the six verbs + card,
and emits a machine-readable verdict + exit code (FR-D5).**
Given any shim exposing the six A2A MUST-verbs and an Agent Card, When the suite runs, Then it executes
**all** of C1–C10 black-box (Agent Card validity C5, task-lifecycle C1/C8, SSE progress C4, artifact
emission C2/C3, capability-flag honesty C5/C6, credential-metadata correctness C7, BYO routing C9,
zero-core-change C10), and emits a **C1–C10 pass/fail matrix** plus a **process exit code** (`0` iff all
pass). And the suite drives the shim through **only** the six verbs + the card — no runtime-native side
channel — so it certifies exactly what the core relies on.

**AC2 — the suite has TEETH: it fails a non-conformant shim on the violated check and passes a conformant
one; every check is non-vacuous (the crux — R1/R3, ISI-2346-F1 class).**
Given a shim that violates a specific Cn, When the suite runs, Then the verdict for Cn is **FAIL** (RED);
given the reference-conformant shim, Then **all** of C1–C10 are **PASS**. And each headline check is
**load-bearing**: replacing its body with `return PASS` (vacuous) lets the violating shim **pass** — the
check, not a side effect, is what catches the defect. A suite that is **green on a broken shim** is a
**defect that fails this story** — it would launder a leaky runtime as certified (the false-assurance
failure a toothless gate produces). *Mutation-proven in the falsification: `double`(C1), `append`(C2),
`nofence`(C3), `unordered`(C4), `omitcap`(C5), `dishonest`(C6), `authfail`+`leak`(C7), `recancel`(C8),
`baked`(C9) each turn their check RED; vacuating C1/C3/C6/C7/C9 leaks their violator through.*

**AC3 — capability-flag honesty is checked BOTH directions; credential correctness is metadata-shape +
no material (FR-D4 / FR-G2 / §10.1).**
Given a card that **omits** a gap or **forges** a capability the runtime lacks (widening override), When
C5 runs, Then it **FAILs** (validation error / non-explicit flag). Given a runtime that emits
`input-required` while advertising `interactive:false`, When C6 runs, Then it **FAILs** — advertised
`false` must mean *never exercised*. Given a card carrying token bytes, or an auth failure surfacing as
generic `failed`, When C7 runs, Then it **FAILs** — the card carries `{credentialType,
credentialLifecycle}` metadata only, and an auth error is the first-class `auth-required`→`Paused` pause
signal.

**AC4 — the Ollama lane runs the same C1–C10 with the model resolved to a BYO endpoint, driven by
`opencode`, for $0 (FR-OLLAMA / §10.3 / ISI-2157, Ollama lane included).**
Given the suite's default lane, When it runs, Then the model is resolved to a **BYO Ollama endpoint**
(§11) served by a digest-pinned small model and driven by the **`opencode` runtime (5.8)**, the **same**
C1–C10 assertions run (not a reduced subset), and **no paid API credential** is required. And C9 proves
the runtime **honors the injected base-URL** — a shim that dials a baked-in paid provider **FAILs** C9.
This is the vendor's $0 conformance path and the substrate the 14.8 CI lane invokes.

**AC5 — passing the suite = drop-in with zero core changes; the seam is proven non-single-runtime-shaped
(C10, S5/S6, NFR-EXT1).**
Given a shim that passes C1–C10, When it joins a squad, Then **no change to the Run reconciler / coord
services** is required (C10 grep-gate: no `type ==` special-casing on the dispatch path). And the suite
is run against a **second runtime `type`** (Hermes stub or `opencode`) through the **identical** harness,
demonstrating the seam is not shaped to one runtime (ISI-2114 §14 AC3). Passing the suite **is** the
FR-D5 definition of conformance: *works in any squad, zero core changes.*

**AC6 — the suite is self-contained and independently executable (FR-D5, "execute independently").**
Given a third-party vendor with only their shim, When they run the suite, Then it executes with **one
command** against their shim + a throwaway Ollama container — **no Squad core source, no cluster access,
no paid API key** — and returns the C1–C10 verdict + exit code. A suite that requires Squad's private
infra to certify an outside vendor is a defect: "independently executable" is the FR-D5 requirement, not
a convenience.

## Runnable check (the falsification)

`docs/bmad/spikes/bench/conformance-suite-check.py` — stdlib-only, `python3` it directly. A **meta
differential** falsification (same discipline as `agent-card-check.py` / `handoff-advisory-check.py`),
**not** a happy-path demo. It models the ISI-2114 §12 suite in-process and mutates the **shim under
test** — never the suite — so the assertions' **teeth** are what is proven. **Verified GREEN (exit 0):**

- **(B) reference-CONFORMANT shim on the Ollama lane ⇒ suite all-green.** All of C1–C10 `PASS` with the
  model resolved to a BYO Ollama base-URL, **$0**, zero paid credits. If the reference shim ever fails a
  check, the suite over-rejects (rejects a conformant runtime) — also a defect.
- **(A) TEETH — each non-conformant shim fails its violated check (RED).** Ten mutant shims, each
  breaking exactly one invariant: `double`→C1 (no dedup), `append`→C2 (rows not upserted), `nofence`→C3
  (stale write lands), `unordered`→C4 (seq reversed), `omitcap`→C5 (gap omitted, not explicit-`false`),
  `dishonest`→C6 (`interactive:false` yet emits `input-required`), `authfail`→C7 (auth→generic `failed`),
  `leak`→C7 (token bytes on the card), `recancel`→C8 (re-cancel not no-op), `baked`→C9 (dials a baked-in
  paid provider, ignores the injected base). Each turns its check **RED**. **Reported honestly:** the
  `omitcap`(C5) mutant *also* reds C6 — an omitted capability key is legitimately **both** a fidelity
  and an honesty defect; collateral REDs are informational (more detecting power), the guarded direction
  is a violation the suite fails to *catch*.
- **(C) VACUITY — every headline check is load-bearing.** Stubbing C1/C3/C6/C7/C9 to `return PASS` and
  re-running each against **its own violating shim** shows the violator now **leaks through** (`PASS`) —
  proving the check body, not an incidental side effect, is what catches the defect. If vacuating a
  check did **not** let its violator pass, the check would be certifying by accident.

Exits non-zero if the reference shim fails any check (over-rejection), a non-conformant shim **passes**
its violated check (no teeth — the ISI-2346-F1 defect), or a headline check is vacuous (not
load-bearing). Models the §12 suite in-process; **real-runtime promotion** is the buildable
`conformance/` harness (ISI-2114 §13 child, Ollama lane, `opencode` 5.8) wired into the 14.8 CI lane —
this bench proves the **assertions have teeth** before that harness is built, so the buildable version
can't quietly ship a green-on-broken gate.

## Out of scope (owned elsewhere)

- **The C1–C10 assertion *semantics*, the six-verb/SSE/Card/artifact schemas, the reference OpenClaw shim
  binary, and the `conformance/` harness scaffold** (ISI-2114 §12/§13 + its child spike — this story
  *packages and gives teeth to* them, does not redefine them). **Agent Card generation** (Story 5.2 —
  the card C5/C6 check). **The core A2A client** (Story 5.1 — C10's core-side counterpart). **The
  `pkg/a2a@rev` pin** (Story 5.3 — the rev the suite asserts against). **The BYO Ollama endpoint + its
  Secret** (Story 5.7/7.5). **The `opencode` runtime** (Story 5.8 — the Ollama lane's runtime). **The CI
  workflow** that invokes the suite nightly/on-release (Story 14.8 / ISI-2157/2158 — this story ships the
  runnable suite it calls). **The `rate_limited` C-check** (Story 5.10 — added into the slot this suite
  leaves). This story ships the **vendor-runnable C1–C10 suite, its teeth (adversarial validity + the
  Ollama $0 lane), and the differential falsification that proves a non-conformant shim is caught** — the
  FR-D5 gate that turns "works in any squad, zero core changes" from a promise into an executable fact.
