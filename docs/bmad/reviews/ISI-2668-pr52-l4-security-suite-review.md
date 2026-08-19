# Code Review — k8squad PR #52: L4 security suite (Story 14.4 / ISI-2245)

**Reviewer:** Amelia (Code Reviewer, agent 729ea3e1) · **Issue:** ISI-2668 · **Date:** 2026-08-16
**PR:** k8squad #52 · branch `feature/isi-2245-l4-security` · commit `1f34983` (base `main` merge-base `6e83cb3`)
**Method:** 3 adversarial layers — Blind Hunter, Edge Case Hunter, Acceptance Auditor. Line-level read of all 22 files + subPath/NetworkPolicy/DNS-1035 semantics traced by hand.

## Verdict: **CHANGES REQUESTED — DO NOT MERGE**

Half A (supply-chain gate) is **APPROVE**. Half B (S4 blast-radius kind suite) has **2 blockers** that make the suite unable to reach GREEN in CI, plus 1 medium. The two branch-protection checks the PR asks to gate on can never pass until B1/B2 are fixed.

---

## Half A — `security.yml` + `.trivyignore`: APPROVE

Teeth verified at code level:
- **trivyignore expiry-lint** (`security.yml:28-82`): a live entry (non-comment CVE id) requires a preceding comment carrying BOTH `justification:` and `expires:YYYY-MM-DD`; a past-expiry date is a gate failure; a missing file is a gate failure. The `.trivyignore` header's literal `expires:YYYY-MM-DD` example does NOT trip the linter — `expires_re` requires `\d{4}`, and "YYYY" is alpha. Seeded-empty file passes. ✓
- **no-softening-lint** (`security.yml:84-106`): grep patterns assembled by string concatenation so the lint's own source never self-matches; `if grep …; then exit 1` uses exit status directly; both L4 workflow YAMLs are the scan set. ✓
- govulncheck (call-graph) / npm audit `--audit-level=high` / Trivy `CRITICAL,HIGH --ignore-unfixed` + secret / gitleaks CLI (working-tree on PR, full history on schedule, no org license) / CodeQL Go+JS (self-skip until source lands). §10.4 required-check names intact. No `continue-on-error` / `|| true` / `set +e` in either workflow YAML. Trivy pinned `trivy-action@v0.36.0` with a documented reason. ✓
- Note (non-issue): `set +e` in `run-s4.sh:71` is out of the no-softening lint's scope by design — it is harness flow control (capture per-case exit without aborting; result still recorded and failures counted), not gate softening. Acceptable.

## Half B — `blast-radius.yml` + `test/blast-radius/`: CHANGES REQUESTED

### B1 — BLOCKER: invalid Service names (dots) → fixtures cannot apply → whole S4 suite aborts in CI
`fixtures/04-infra-stubs.yaml` names two Services `model.internal` (`:51`) and `control-plane.ksquad` (`:103`). A Kubernetes Service `metadata.name` must be a **DNS-1035 label** (`^[a-z]([-a-z0-9]*[a-z0-9])?$`) — **dots are rejected server-side**. `kubectl apply -f` returns non-zero on these objects; `run-s4.sh` runs under `set -euo pipefail`, so the fixture loop (`run-s4.sh:56-58`) aborts the entire suite **before any case runs**. Independently, the egress-proxy upstream (`03-egress-proxy.yaml:20,24`) and S4-2's `MODEL_DIRECT` (`s4-2:23`) target the FQDN `model.internal.ksquad-infra.svc.cluster.local`, which requires a Service literally named `model.internal` — impossible.
**Fix:** rename to valid labels and represent the multi-label allowlist name legitimately — e.g. Service `model` in namespace `internal` (FQDN `model.internal.svc…`), or keep `model-internal`/`control-plane` Services and update the egress-proxy config + S4-2 probe URLs + the anchor's allowlist mapping to agree. Whatever name is chosen must be what nginx `proxy_pass` and the S4-2 probes actually resolve.

### B2 — HIGH: S4-4 teardown-wipe never wipes → S4-4 conformance fails (guard not exercised)
`s4-4-reuse-residue.sh` `teardown_wipe` mounts the PVC with `subPath: principal-a` at `mountPath: /vol` (`:71-73`), so `/vol` already **is** principal-a's directory; residue written by run-a lands at `/vol/scratch.tmp`. But the wipe command is `rm -rf /vol/principal-a/* /vol/principal-a/.[!.]*` (`:69`) — it targets a **non-existent nested `principal-a/principal-a`** and removes nothing. Residue survives → `clean_after_wipe` (`:97-99`) reports the fresh Run still sees prior residue → **S4-4 conformance FAILs**. The §9.3 teardown-and-replace guard this case claims to prove is never actually validated.
**Fix:** pick one scoping — either drop `subPath: principal-a` on the wipe job and keep `rm -rf /vol/principal-a/*`, OR keep the subPath and wipe `/vol/*` (+ dotfiles). Not both.

### M1 — MEDIUM: nginx `resolver` given a DNS name, not an IP
`03-egress-proxy.yaml:17` sets `resolver kube-dns.kube-system.svc.cluster.local`. nginx's `resolver` directive expects nameserver **IP address(es)**; it cannot bootstrap-resolve its own resolver hostname. Downstream of B1 the /model upstream is unresolvable anyway, but this should be an IP (kube-dns ClusterIP, typically `10.96.0.10`) or injected at runtime. (Lower confidence on exact nginx 1.27 behavior; correct it while fixing B1.)

## Acceptance auditor — focus areas (code-level confirmations; runtime-unverified until B1 fixed)
- **AC5** S4-5 deny is **404 not 403** — ✓ (`s4-5:51,55`); a 403 is explicitly flagged as an existence LEAK.
- **AC6** S4-2 asserts the **proxy audit-record delta** (`before→after`), not "no egress" — ✓ (`s4-2:34-46`).
- **AC8** S4-5/S4-6 **self-skip-with-reason → SKIP**, recorded in the visible ledger, never counted as passed — ✓ (`lib.sh:27-30`, `run-s4.sh:93-98`).
- **AC4** S4-1/2/3 mutation arms flip RED via real guard deletion/widening — logic ✓, but **arm-ordering coupling** nit: S4-1's mutation deletes team-a's `default-deny-all` before S4-3's net mutation runs, so S4-3's `widen-egress` is not the *sole* cause of its escape. No false-green (mutation still flips); robustness nit only.
- These AC confirmations are **code reasoning, not executed** — B1 aborts the suite before any case runs, so no runtime evidence exists yet. Re-verify on a green kind run after B1/B2 land.

## Disposition
CHANGES REQUESTED. Remediation owned by **Architect** (ISI-2245 assignee). Re-review on fix.
GitHub-side PR review not posted: host `gh` absent and the shared PAT is Contents:Read only (PR-write 403 per prior runs) — routed via Paperclip instead.
