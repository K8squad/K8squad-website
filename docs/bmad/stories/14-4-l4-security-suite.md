# Story 14.4: L4 security suite [CVE/SAST/secrets + S4 blast-radius]

Status: ready-for-dev

<!-- ISI-2245. Absorbs Epic X.1/X.2/X.3 (hostile-Run / residue / poisoning) + the 10.4/12.4
     covert-channel guards. §6.7 full RBAC matrix stays owned by 15.8 (referenced, not duplicated). -->

> **🔒 THIS IS THE "TESTED, NOT ASSERTED" SECURITY GATE (§17.1).** Two halves, one workflow family:
> a **supply-chain half** (`security.yml` — govulncheck / npm audit / Trivy / gitleaks / CodeQL) that
> **fails the build** on an exploitable dependency vuln, a fixable CRITICAL/HIGH image CVE, a
> committed secret, or a CodeQL alert; and a **blast-radius half** (`blast-radius.yml` — the **S4
> suite** in kind against a **hostile-Run fixture**) that proves a Run executing arbitrary code is
> **contained** — it cannot cross a namespace, exfil past the egress allowlist, read a sibling
> principal's Run, inherit residue from a torn-down sandbox, or turn memory into a covert coordination
> channel. Both halves **gate** — they do not warn. A curated `.trivyignore` with **expiry + written
> justification, reviewed like code**, is the *only* CVE escape hatch.

## Story

As **the security owner gating every change to the platform**,
I want **an L4 security suite that (a) runs `govulncheck` + `npm audit` + Trivy + gitleaks + CodeQL as
required PR gates on exploitable/fixable findings, and (b) runs the S4 blast-radius suite in kind
against a hostile-Run fixture — default-deny egress, cross-namespace isolation, reuse-residue,
cross-principal read-authZ, and memory-poisoning/covert-channel — each case differential and
fail-loud**,
so that **the architecture's security model is proven on every PR and on schedule rather than
asserted in a doc: a shipped image carries no known-exploitable/fixable CVE, no secret ever lands in
the repo, and a hostile Run's blast radius is bounded to its own sandbox (PRD NFR-SEC1/3/4/5/6, D8,
review F5/F6/F7/F11, S4).**

## Context & prerequisites

- **PRD / NFRs:** `docs/bmad/02-prd.md` — **NFR-SEC1** (cross-squad isolation), **NFR-SEC3**
  (credentials never logged/echoed), **NFR-SEC4** (default-deny egress), **NFR-SEC5** (per-principal
  read scoping / no residue), **NFR-SEC6** (memory provenance / no covert channel), **D8** (external
  integrations untrusted). The mandate is §17.1 "security is tested, not asserted".
- **Testing strategy:** `docs/bmad/05-testing-strategy.md` — **§6.1** dependency scan, **§6.2** image
  CVE (Trivy primary + Grype release cross-check, gate on CRITICAL/HIGH-with-fix), **§6.3** SAST
  (CodeQL Go+JS), **§6.4** secrets (gitleaks), **§6.5** the **S4 blast-radius case table** (the six
  cases this story implements), **§6.6** supply-chain (SBOM/cosign — owned by 14.6), **§10.1**
  `security.yml` in the workflow set, **§10.4** the ratified required-check names, **§11.1** runner
  fleet. §6.7 (the full authN/authZ RBAC matrix) is **15.8's** — this story implements only the S4
  isolation/existence-hiding cases that §6.5 already names.
- **Architecture:** `docs/bmad/03-architecture.md` — **§4.3** isolation test suite (first-class CI
  artifact), **§9.3** teardown-and-replace (reuse-residue proof), **§9.4** per-principal build-browser
  read scoping (cross-principal read-authZ), **§12.1** namespace-per-Team tenancy, **§12.2** egress
  control (default-deny + allowlist + proxy audit), **§7.3** memory trust boundary (provenance, no
  covert channel), **§17.1** untrusted-input threat model (F5/F6/F7/F11).
- **Epics:** `docs/bmad/04-epics-and-stories.md` — the **14.4** row; the **Epic X** promotion note
  ("X.1 hostile-Run, X.2 residue, X.3 poisoning are the L4 blast-radius cases; no story lost"); the
  **10.4/12.4** covert-channel guardrails; the **15.8→14.4** absorption line.
- **Depends on (deployable-in-kind, not just authored):** **Epic 4** — 4.1 squad=namespace tenancy
  (ISI-2207), 4.2 RuntimeClass isolation (ISI-2208), 4.5 teardown+PVC scoping (ISI-2211), 4.6
  default-deny egress + allowlist (ISI-2212); **Epic 6** — memory service + provenance/trust (ISI-2222
  / 2224 / 2225 / 2226); **Story 8.7d** — the BFF per-principal read gate (ISI-2274). Each S4 case is
  a *live* assertion against the primitive it names — a case can only bite once its primitive is
  deployable in kind (see **§ Dependency gating** below; cases self-skip-with-reason until then, never
  silently drop — the spine-chaos.yml precedent, 14.2).
- **Sibling / precedent:** **14.2** (ISI-2200) — the L2 gate this story mirrors in shape: a required,
  fail-loud, differential suite with a language-neutral falsification anchor in
  `docs/bmad/spikes/bench/`.

## Absorption ledger

This story is the canonical L4 gate. It **absorbs**:

- **Epic X.1** (hostile-Run blast-radius, Arch §4.3 / S4 / NFR-SEC1; gated on the ISI-2113 RuntimeClass
  pick) → **S4-1** (default-deny egress) + **S4-3** (cross-namespace isolation).
- **Epic X.2** (reuse/residue) → **S4-4** (teardown-and-replace exposes no prior-Run residue, §9.3).
- **Epic X.3** (memory-poisoning / provenance forgery) → **S4-6** (poisoning + covert-channel, §7.3).
- **10.4** (discussion room structurally not a coordination back-channel) + **12.4** (agent identity /
  no P2P) covert-channel guards → the **covert-channel arm of S4-6**: a hostile Run cannot drive a
  coordinator via memory/room state; coordination rides shared work-items + fencing only (§6, F6).
- **8.7d** cross-principal read gate (ISI-2274) → **S4-5** (principal B `GET`ing A's Run build view →
  `404`, same-Team; existence-hiding, NFR-SEC5).
- **15.8 (partial):** the **isolation / existence-hiding** cases (§6.7.3 per-Project isolation) overlap
  S4-3/S4-5 and land here; the **full authN/authZ RBAC matrix** (§6.7.1/.2/.4/.5/.6/.7 — sessions,
  role×verb, escalation, adaptive-nav) stays **15.8's**, referenced not duplicated.

## The two halves

### Half A — supply-chain gates (`security.yml`, exists as skeleton — harden to teeth)

| Mechanism | Tool + gate | §Test | Required check name (§10.4) |
|-----------|-------------|-------|-----------------------------|
| **A1** dependency/module vulns (Go) | `govulncheck ./...` — call-graph-aware, gates on **known-exploitable** only | §6.1 | `govulncheck (Go modules)` |
| **A2** dependency vulns (console) | `npm audit --audit-level=high` | §6.1 | `npm audit (console)` |
| **A3** image + fs/config CVEs | **Trivy** `--severity CRITICAL,HIGH --ignore-unfixed --exit-code 1` (+ `secret` scanner); **Grype** cross-check on **release** images (14.6/`build-images.yml`) | §6.2 | `Trivy (filesystem + config)` |
| **A4** secrets | **gitleaks** working-tree on PR; **full git-history** scan on schedule; zero-tolerance | §6.4 | `Gitleaks (secrets)` |
| **A5** SAST | **CodeQL** (Go + JavaScript/TypeScript), PR + weekly | §6.3 | `CodeQL (go)`, `CodeQL (javascript)` |

**Escape hatch:** a checked-in `.trivyignore` — each entry carries a CVE id, an **expiry date**, and a
one-line **justification**; entries are reviewed like code and an expired entry is itself a gate
failure (the "curated, reviewed" discipline, §6.2 / 14.6).

### Half B — the S4 blast-radius suite (`blast-radius.yml`, new — kind + hostile-Run fixture)

Runs in **kind** against a **hostile-Run fixture** (a pod that actively tries to escape its sandbox).
Each case is **differential**: removing the guard it targets flips the case **RED**.

| Case | Proves (the bounded blast radius) | Primitive under test | Arch | Review / NFR | Absorbs |
|------|-----------------------------------|----------------------|------|--------------|---------|
| **S4-1** default-deny egress | a sandbox with **no** allowlist entry cannot reach arbitrary endpoints; only model/tool/control-plane resolve | egress NetworkPolicy + proxy allowlist (4.6) | §12.2 | NFR-SEC4 | X.1 |
| **S4-2** exfil-via-allowlisted-endpoint (**named, not mistaken for containment**) | the allowlisted hole is **audited** by the egress proxy (attributable), not silently a containment gap | egress proxy audit (4.6) | §12.2 | F11 | X.1 |
| **S4-3** cross-namespace isolation | a **Team-A** pod cannot reach **Team-B** services / Secrets | namespace tenancy + default-deny NetPol + scoped RBAC (4.1) | §12.1 | NFR-SEC1 | X.1 |
| **S4-4** reuse-residue | after **teardown-and-replace**, a fresh sandbox exposes **no** prior-Run scratch / secret / worktree; per-principal PVC subpath holds | teardown + per-principal PVC scoping (4.5) | §9.3 | NFR-SEC5, F6/F7 | X.2 |
| **S4-5** cross-principal same-Team read-authZ | principal **B** `GET /api/runs/{A's runId}/build/{tree,diff,file,meta}` (same Team, B ≠ owner) → **`404`** (existence-hiding); **positive control:** owner A → `200`; cross-Team → `404` | BFF per-principal gate (8.7d) | §9.4 | NFR-SEC5, B1/F7 | 8.7d, 15.8 |
| **S4-6** memory-poisoning / provenance-forgery + **covert channel** | a hostile Run **cannot forge** another principal's provenance; reads surface as **untrusted**; memory/room is **not** a coordination back-channel (a coordinator cannot be driven off-record) | memory provenance/trust (6.x) + no-P2P room (10.4/12.4) | §7.3 | NFR-SEC6, F5/F6 | X.3, 10.4, 12.4 |

## Acceptance criteria

1. **AC1 — supply-chain gates fail loud, on the exploitable/fixable subset (Half A).** On PR:
   `govulncheck` fails on a **known-exploitable** Go vuln (call-graph reachable — an unreachable vuln
   does **not** gate); `npm audit --audit-level=high` fails on a high/critical console advisory; Trivy
   fails on a **CRITICAL or HIGH-with-a-fix** (`--ignore-unfixed`, so an unfixable HIGH does not wedge
   merges) fs/config/image finding; gitleaks fails on **any** committed secret; CodeQL (Go + JS/TS)
   fails on a reported alert. Each is a **required status check** with the §10.4 name.

2. **AC2 — `.trivyignore` is the only escape hatch, and it is reviewed like code.** A CVE is suppressed
   **only** via a checked-in `.trivyignore` entry carrying an **expiry date + justification**; an entry
   past its expiry is a **gate failure** (not a silent perpetual mute). There is no `continue-on-error`
   / `|| true` softening anywhere in Half A — a green Half A means clean, not "ran".

3. **AC3 — the S4 suite runs in kind against a real hostile-Run fixture (Half B).** `blast-radius.yml`
   stands up a **kind** cluster, installs the isolation primitives it exercises, deploys the
   **hostile-Run fixture** (a Run pod that actively probes for escape), and runs **S4-1…S4-6**. It is a
   **required check** on paths touching isolation (`config/**` NetworkPolicy/RBAC, egress proxy,
   teardown, the BFF read gate) + nightly. The suite **fails the build** on any escape.

4. **AC4 — every S4 case is differential (teeth, not theater).** For each S4-1…S4-6, a named mutation
   of the guard it targets (delete the egress NetworkPolicy → S4-1 RED; widen a Team-B RoleBinding →
   S4-3 RED; skip the teardown wipe → S4-4 RED; drop the `owningPrincipal` check → S4-5 goes `200`
   where `404` is required → RED; accept a forged provenance author → S4-6 RED). A PASS therefore
   proves the guard exists — an all-green suite against a spineless fixture is itself a failure the
   preflight catches.

5. **AC5 — S4-5 existence-hiding is `404`, never `403`.** In the build-browser read path, an
   out-of-scope caller (cross-principal same-Team, or cross-Team) gets **`404`** — the response never
   confirms the Run exists (§8.7d). Asserting `403` here is a leak and fails the case.

6. **AC6 — S4-2 names the allowlisted hole rather than hiding it (F11).** The exfil-via-allowlisted
   case does **not** assert "no egress"; it asserts the egress **proxy audit records** the allowlisted
   call (attributable), so the residual hole is observed, not mistaken for containment. A silent
   allowlisted egress (no audit record) fails the case.

7. **AC7 — S4-6 covert-channel: coordination is not driveable off-record.** The fixture's hostile Run
   writes a poisoned memory fact / room message intended to steer a coordinator's next dispatch; the
   assertion is that (a) the read is surfaced **untrusted** with the hostile author's provenance
   (un-forgeable), and (b) the coordinator's claim/dispatch decision rides **shared work-items +
   fencing only** — there is **no** memory/room semantics that mutate a claim/handoff/state
   (10.4/12.4, §6, F6). A path by which the fact silently becomes coordination state fails the case.

8. **AC8 — dependency-gated cases self-skip-with-reason, never silently drop (§ gating).** A case
   whose primitive is not yet deployable in kind emits a **`::notice::` skip-with-reason** and the job
   records it as skipped-not-passed (the spine-chaos.yml precedent). The suite never reports a
   green it did not earn; the skip ledger is visible in the run summary.

## Falsification anchor (language-neutral, `docs/bmad/spikes/bench/`)

Mirroring 14.2's `chaos-harness.py`, the S4 semantics are pinned by a **differential anchor**
`docs/bmad/spikes/bench/blast-radius-check.py` that models each case as *guard-on → contained* vs
*guard-off → escaped*, so the Go/kind implementation is a faithful translation and a broken guard is
provably caught before the kind wiring exists. The anchor is CI-runnable standalone (no cluster) and
is the source of truth the `blast-radius.yml` kind cases must reproduce 1:1.

## Implementation (k8squad source repo)

- `.github/workflows/security.yml` **(exists — harden)**: keep the five Half-A jobs + §10.4 check
  names; add (a) the `.trivyignore` escape-hatch file + an **expiry lint** step, (b) a **full
  git-history** gitleaks pass on the `schedule` trigger (working-tree on PR), (c) assert no
  `continue-on-error`/`|| true` softening remains. Grype-on-release lives in `build-images.yml` (14.6),
  cross-referenced here.
- `.github/workflows/blast-radius.yml` **(new)**: kind + the isolation primitives + the hostile-Run
  fixture; runs S4-1…S4-6; required on isolation-touching paths + nightly; self-skips-with-reason per
  case until its primitive is deployable (`::notice::`), never a silent drop.
- `test/blast-radius/` **(new)**: the hostile-Run fixture manifests (a probing Run pod), the S4 case
  drivers, and the per-case mutation harness (AC4). A faithful translation of the bench anchor.
- `.trivyignore` **(new)**: seeded empty with the header convention (id · expiry · justification).

## Dependency gating (which S4 cases bite now vs later)

| Case | Deployable-in-kind gate | Status |
|------|------------------------|--------|
| S4-1 / S4-2 egress | 4.6 egress NetPol + proxy (ISI-2212, DONE) | wire now |
| S4-3 cross-namespace | 4.1 namespace tenancy (ISI-2207, DONE) | wire now |
| S4-4 residue | 4.5 teardown + PVC scoping (ISI-2211, DONE) | wire now |
| S4-5 cross-principal read | 8.7d BFF gate (ISI-2274, DONE) + a deployable apiserver/console in kind | gated on kind-deployable apiserver (Epic 9 install) |
| S4-6 poisoning/covert | 6.x memory service deployable in kind (ISI-2222+, DONE code) | gated on kind-deployable memory |

Cases whose apiserver/memory image is not yet stood-up in kind **self-skip-with-reason** (AC8) until
the Epic 9 install path (9.x) makes those components deployable; the NetworkPolicy/namespace/egress
cases (S4-1/2/3/4) bite against the isolation primitives immediately.

## Verification evidence (to attach on implementation)

- Half A: a seeded exploitable Go vuln → `govulncheck` RED; a `--severity HIGH` fixable CVE in a test
  image → Trivy RED; a planted fake secret → gitleaks RED; each restored → green. `.trivyignore` with a
  past-expiry entry → RED.
- Half B: per-case mutation (AC4) each flips its case RED; restored → all-green (or
  skipped-with-reason where gated). S4-5 asserts `404`-not-`403`; S4-2 asserts the proxy audit record.
- The bench anchor `blast-radius-check.py` runs standalone (no cluster) and matches the kind cases 1:1.

## Out of scope / owner notes

- **Full RBAC matrix (§6.7.1/.2/.4/.5/.6/.7)** — sessions, role×verb, escalation, adaptive-nav — stays
  **15.8's**; 14.4 implements only the S4 isolation/existence-hiding overlap (S4-3/S4-5).
- **SBOM / cosign sign+attest / Grype-on-release** live in **14.6** (`build-images.yml`); 14.4
  cross-references them, does not own them.
- Marking the two checks **branch-protection-required** in GitHub settings is a **repo-admin** action
  (board/maintainer), not something the suite can self-assert (§11.4 precedent).
- Live pod-kill / resource-layer fidelity for S4-4 (kill mid-write, CNPG-backed) is a follow-up where
  the fixture gains that fidelity; the ordering guard is asserted at the API/manifest layer first.
