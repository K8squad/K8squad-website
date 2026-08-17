# Story 14.6: Supply-chain provenance [SBOM · CVE · cosign]

Status: in-review

<!-- ISI-2745. Impl of Epic 14.6 (04-epics-and-stories.md:683). Original spec issue ISI-2247.
     Reviewer: Testing Architect. Unblocked by ISI-2742 (reusable component-matrix) merging to
     main as a122390 — this lane now consumes that single-source-of-truth fan-out. -->

> **🔏 EVERY IMAGE CARRIES ITS PROVENANCE.** On each build we emit a **Syft SBOM** (artifact +,
> on release, a cosign attestation), **CVE-scan** it with **Trivy** (gate on fixable CRITICAL/HIGH),
> and on **release tags** additionally **Grype cross-check** + **cosign keyless (OIDC) sign/attest**
> the SBOM + an **SLSA build-provenance** attestation on the pushed digest. The **only** CVE escape
> hatch is the curated **`.trivyignore`** (expiry + written justification, reviewed like code,
> expiry-linted by `security.yml`) — now honored by **both** the filesystem scan and this image scan.

## Story

As **a security owner**,
I want **supply-chain provenance on every image — SBOM, CVE gate, and (on release) signature +
attestations — wired as the supply-chain lane of the component-matrix pipeline**,
so that **a shipped image is traceable to its source and dependencies, carries no known-fixable
CRITICAL/HIGH CVE, and release artifacts are cryptographically verifiable (PRD NFR-SEC3, §6.6/§11.3,
S4 supply-chain).**

## Acceptance criteria (from Epic 14.6)

- **Given** `build-images.yml`, **when** an image builds, **then** a **Syft SBOM** is produced as an
  artifact/attestation **and Trivy** CVE-scans it. ✅
- **And** release images are **cosign** keyless (OIDC) **sign+attest** with the SBOM attached. ✅
- **And** the only CVE escape hatch is a curated **`.trivyignore`** with expiry+justification,
  reviewed like code. ✅ (wired into this image scan via `trivyignores: .trivyignore`, same list the
  `security.yml` filesystem scan + expiry-lint already govern — one list, no per-lane drift.)
- **And** wired as the **supply-chain lane of the component-matrix pipeline** (ISI-2742). ✅

## What shipped (delta on `origin/main` `a122390`)

`build-images.yml` refactor — the SBOM/Trivy/cosign scaffolding already existed on main; this story
turned it into a spec-complete, reuse-driven supply-chain lane:

1. **Reuse (the unblocked core).** Added a `components` job (`uses: ./.github/workflows/component-matrix.yml`)
   and a `plan` job that unions the reusable primitive's **`go`** (operator/apiserver/memory) and
   **`node`** (console) outputs into the build matrix (deriving `Dockerfile.<c>` + a source-presence
   srcprobe). The component list now lives in **exactly one place** (ISI-2742) — no lane-to-lane drift.
   The prior inline `matrix.component` list is removed. Guard-hardening (ISI-2644: srcprobe = the
   entrypoint dir, skip-with-reason until source lands) is preserved via the derived srcprobe.
2. **`.trivyignore` as the sole escape hatch.** The image Trivy scan now sets `trivyignores: .trivyignore`
   (matching `security.yml`'s filesystem scan), so the one expiry-linted, reviewed-like-code list
   governs both scans — closing the AC that was previously only enforced on the fs scan.
3. **Grype release cross-check.** `anchore/scan-action` (severity-cutoff high, only-fixed, fail-build)
   on `v*` tags — the §6.1/§6.6 "Trivy primary + Grype cross-check on release images" second-scanner.
4. **SLSA build provenance.** `actions/attest-build-provenance` on `v*` tags, pushed to the registry
   alongside the cosign SBOM attestation — keyless, uses the already-declared `id-token`/`attestations`
   permissions, no stored key (§11.5).

Unchanged and already correct on main: keyless cosign sign+attest, multi-arch buildx, lowercased
digest ref resolution (syft/trivy reject mixed-case `K8squad`), `id-token`/`attestations`/`packages`
permissions, SBOM artifact upload.

## Runner-constraint compliance (epic-14-ci-runner-constraints)

- **R1:** every job — `components` (reusable emit), `plan`, `build` — runs on `[self-hosted, linux, x64]`.
  K8squad has no hosted-runner minutes; a `ubuntu-latest` job would queue forever and wedge the lane.
- SBOM/scan/sign steps stay gated on `github.event_name != 'pull_request'` (image only pushed off-PR)
  and release steps on `startsWith(github.ref, 'refs/tags/v')`, so PRs still validate wiring without
  requiring a pushed image.

## Verification

- `actionlint .github/workflows/build-images.yml` → clean (reusable-workflow `uses` + `needs.*.outputs`
  refs resolved; matrix-from-`fromJSON` well-formed).
- `plan` union python simulated with the real component-matrix outputs → yields the exact 4-component
  matrix (operator/apiserver/memory/console) with correct Dockerfile + srcprobe.
- YAML parses; jobs = `components`, `plan`, `build`.

## Scope boundary

- CVE **filesystem/config** scan, govulncheck, gitleaks, CodeQL and the `.trivyignore` **expiry-lint**
  remain owned by `security.yml` (Story 14.4 / ISI-2245) — this story consumes that same `.trivyignore`,
  it does not duplicate the lint.
- Branch-protection **required-check marking** for `image / *` is repo-admin scope (§11.4, ISI-2674) —
  out of scope here (emit-now / require-later).
- Shim images (`Dockerfile.shim`, per-runtime) are Phase-2 (ISI-2114), not yet a container-image lane.
