# ISI-2671 — Re-review PR #52 blast-radius suite (Story 14.4): B1/B2/M1

**Reviewer:** Amelia (Code Reviewer, agent 729ea3e1) · **Date:** 2026-08-16
**Verdict:** ⛔ **CANNOT confirm GREEN / CANNOT merge PR #52 as asked** — the premise
of the re-review is stale. Corrective **PR #53 opened** to land the surviving fix.

## TL;DR

The ISI-2671 ask was "confirm `blast-radius.yml` GREEN on the real kind run and merge
PR #52 @ `8b14881`." That is not executable: **PR #52 is already merged into `main` as
`bd9ba1c` — a *different* lineage than `8b14881`** — and it landed **only the B2 fix**.
**B1 and M1 are LIVE on `main`**, so `blast-radius.yml` on `main` cannot go GREEN. The
coherent remediation `8b14881` sits on an orphaned branch off `1f34983` that never reached
`main`. I reconciled the surviving B1+M1 hunks onto `origin/main` as **PR #53**.

## Ground truth (git-verified, not API)

| Fact | Evidence |
|------|----------|
| `origin/main` head | `bd9ba1c` "fix(blast-radius): S4-4 teardown-wipe mounted its own subPath" (**B2 only**) |
| `8b14881` on main? | `git merge-base --is-ancestor 8b14881 origin/main` → **NO** |
| Two forked lineages | main = `0a42898`→`bd9ba1c`; fix = `1f34983`→`8b14881` (never merged) |
| **B1 LIVE on main** | `04-infra-stubs.yaml:51` `name: model.internal`, `:103` `name: control-plane.ksquad` — Service names with dots → **invalid DNS-1035** → `kubectl apply` rejects → `run-s4.sh` `set -euo pipefail` fixture loop aborts before any S4 case |
| main is **incoherent** | Deployments renamed to `model-internal`/`control-plane`, but Services fronting them keep dotted names, and `03-egress-proxy.yaml:24` points `control-plane.ksquad-infra.svc` at a Service that isn't named that |
| **M1 LIVE on main** | `03-egress-proxy.yaml:17` `resolver kube-dns.kube-system.svc.cluster.local` — a DNS name; nginx cannot bootstrap-resolve its own resolver hostname |
| B2 on main | ✅ already fixed by `bd9ba1c` |

## Corrective PR #53 (`fix/isi-2671-blast-radius-dns1035-resolver` @ `9305653`, base `main`)

Applies **only the B1+M1 hunks** (checked out from `8b14881`); **B2/`s4-4` left untouched**:

- `04-infra-stubs.yaml` — Services → `model-internal` / `control-plane` (DNS-1035 valid)
- `03-egress-proxy.yaml` — `/model` upstream → `model-internal.…` FQDN; `resolver 10.96.0.10` (kube-dns ClusterIP, kind default service CIDR, ponytail-commented upgrade path)
- `s4-2-exfil-audited.sh` — `MODEL_DIRECT` → `model-internal.…` FQDN
- `02-egress-allow.yaml` — comment only

Anchor's abstract allowlist hostnames (`model.internal` / `control-plane.ksquad`) unchanged —
they model upstream hostnames, not k8s Service labels.

### Static verification (GREEN)
- `bash -n` clean · all 3 YAML parse · both Service names DNS-1035-valid
- upstream FQDN ↔ Service-name coherence: `model-internal`, `control-plane` match on all 3 sites
- `resolver` is now an IP

## What still needs to happen (the AC confirmations ISI-2671 asks for)
`blast-radius.yml` triggers on `pull_request → main` with `paths: test/blast-radius/**`, so it
**runs automatically on PR #53** — that IS the real kind run (kind + Calico + hostile-Run,
S4-1..S4-6 differential arms). The runtime AC confirmations that B1 blocked (S4-2 audit delta,
S4-4 residue, S4-5 404-not-403, S4-1/2/3 mutation arms) are confirmed **iff PR #53's
blast-radius job goes GREEN**. Auto-merge is disabled repo-wide → **merge is manual on green**.

## Non-blocking follow-up
The S4-1/S4-3 arm-ordering nit from the ISI-2668 review is not addressed here (out of scope for
the B1/M1 reconcile). If worth hardening, file a follow-up — do not block PR #53.

## Disposition
`in_review` — PR #53 open; CI (blast-radius.yml + security.yml) is the GREEN gate; merge to
`main` on green (board/repo-admin merge authority, DCO-only), or re-wake me to verify+merge.

## Addendum (2026-08-16, run a2c7efb2) — the gate was un-runnable; root-caused + fixed
Verifying the "GREEN on the real kind run" premise exposed a deeper problem than the stale-main
lineage: **`blast-radius.yml` job `s4` targeted `runs-on: ubuntu-latest`**, but K8squad is
**self-hosted-only** (gitrunner, ISI-2602/ISI-2612). GitHub-hosted runners are not serviceable,
so the job **startup-failed in ~2s with 0 steps / no runner** on every ref. Actions history:
**4/4 = failure, never once green** (main `bd9ba1c` and PR #53 `9305653` both 2s/0-step). No S4
step had ever executed — the fixture fixes (B1/M1/B2) were never exercised by CI.

Cross-check: `e2e`, `spine-chaos`, `ci`, `build-images` all use `[self-hosted, linux, x64]`;
`e2e` runs `helm/kind-action` on it and has gone green (`d863169d`). blast-radius's `ubuntu-latest`
was a lone misconfiguration.

**Fix:** commit `1675d2e` (DCO-signed) on the PR #53 branch switches `runs-on` →
`[self-hosted, linux, x64]`. New run `actions/runs/31958678495`… (`31959678495`) on head
`1675d2e` is now **in_progress** — first real dispatch of the S4 suite.

**Also red on clean `main` (pre-existing, NOT this PR, out of 14.4 scope):** `CI`, `Security`,
`Build Images`. **Related follow-up:** `security.yml` has two `ubuntu-latest` jobs with the same
un-runnable defect — separate infra ticket.

## Disposition (updated)
`in_review` — monitor = **live** blast-radius run `31959678495` on `1675d2e`. GREEN ⇒ B1/M1 +
runtime ACs validated ⇒ merge-ready (board/repo-admin, DCO-only; auto-merge disabled). RED with
real S4 output ⇒ genuine review finding to triage.
