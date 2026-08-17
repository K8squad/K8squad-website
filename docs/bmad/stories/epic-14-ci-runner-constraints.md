---
title: Epic 14 — CI runner constraints (self-hosted homelab reality)
owner: Winston (Architect)
issue: ISI-2748
date: 2026-08-17
applies-to:
  - 14.1 (ISI-2743 L1 per-component)
  - 14.5 (ISI-2744 L5 quality + coverage)
  - 14.6 (ISI-2745 supply-chain SBOM/CVE/sign)
  - 14.7 (ISI-2742 component-matrix pipeline)
  - 14.8 (ISI-2746 $0 Ollama E2E lane)
stepsCompleted:
  - runner-inventory-from-ISI-2612-ISI-2617
  - oom-cap-inventory-from-ISI-2614
  - concurrency-and-label-contract
  - drop-in-yaml-corrections
---

# Epic 14 — CI runner constraints: build against the homelab, not GitHub-hosted

**Why this doc exists.** The Epic-14 story rows (`04-epics-and-stories.md` 14.1/14.5/14.6/14.7/14.8)
and several drop-in snippets across Epic 13 (e.g. 13.6's `cardinality-lint` example) were written
with the implicit assumption of GitHub-**hosted** runners (`runs-on: ubuntu-latest`). **The
`K8squad/K8squad` repo has no hosted-runner minutes — every workflow runs on two self-hosted
homelab VMs.** A workflow that requests `ubuntu-latest` sits **queued forever**. This is the
authoritative, buildable runner contract every E14 CI story must satisfy; the five child issues
above reference it so the Coder lanes land cleanly instead of wedging on a label mismatch.

Sources of truth (verified 2026-08-16/17): **ISI-2612** (gitrunner OOM containment + labels),
**ISI-2617** (gitrunner-2 provisioning), **ISI-2614** (golangci-lint workflow-level OOM cap,
merged `a6b456d`).

## 1. Runner inventory (the only two executors)

| Runner | Host | RAM | Labels | Role | Guardrails |
|--------|------|-----|--------|------|-----------|
| `gitrunner`   | 10.0.0.190 | 7.9 GB | `[self-hosted, linux, x64]` (group Default) | light + fallback | cgroup `MemoryHigh=6G`, `MemoryMax=6800M`, **`MemorySwapMax=0`** (swap-thrash → indefinite hang on a starved box — kept at 0 so a fat job is cgroup-OOM-killed fast); `.env` `GOMEMLIMIT=4GiB`, `GOGC=50`, `GOMAXPROCS=3`, `GOFLAGS=-p=2`; `Restart=always` |
| `gitrunner-2` | 10.0.0.191 | 16 GB  | `[self-hosted, linux, x64]` | heavy (golangci/go build/security scan) | cgroup `MemoryHigh=13G`, `MemoryMax=14500M`, `MemorySwapMax=6G`; `.env` `GOMEMLIMIT=10GiB`, `GOGC=50`, `GOMAXPROCS=6`, `GOFLAGS=-p=4`; `Restart=always` |

Both carry the **identical label set** `[self-hosted, linux, x64]` — there is no label that
distinguishes the 16 GB box from the 7.9 GB box. Heavy vs light placement is therefore **not**
selectable via `runs-on`; it is managed by concurrency + memory caps (below), so a heavy job that
lands on `gitrunner` (.190) must still fit under a 6.8 GB cgroup cap or it dies fast (by design).

## 2. The runner contract every E14 workflow MUST satisfy

**R1 — `runs-on: [self-hosted, linux, x64]`, never `ubuntu-latest`.** Every job in `ci.yml`,
`spine-chaos.yml`, `build-images.yml`, `security.yml`, `e2e.yml`, and the `cardinality-lint`
check (13.6, wired by 14.7) targets the self-hosted label set. `ubuntu-latest`/`ubuntu-24.04`
jobs never get picked up. (14.7 AC — amend "Node 24-compatible action pins" to also require
the self-hosted label; the Node-24 pin reason still holds: self-hosted runners ship their own
Node, and pinned actions must be Node-24-compatible.)

**R2 — concurrency ≤ 2, and heavy lanes serialize.** There are exactly two executors, and only
**one** (.191, 16 GB) can safely host a heavy Go/golangci/Trivy job — the 7.9 GB box swap-thrashes
or cgroup-OOMs a fat job. Matrix fan-out in `ci.yml` (operator/apiserver/memory/console + shim
matrix) MUST NOT assume unbounded parallel legs: use a **job/workflow `concurrency` group** so a
merge-train burst can't stack 5+ heavy legs onto two boxes and starve the queue. Practical rule:
cap the memory-heavy matrix (the Go `golangci`/`go build`/`govulncheck`/`trivy` legs) so at most
**two** run at once; light legs (cardinality-lint, DCO, chaos-model bench, `gofmt`) may ride either
box. Model this as `concurrency: { group: e14-heavy-${{ github.ref }}, cancel-in-progress: false }`
on the heavy legs (never `cancel-in-progress` on `main` — cancelling a merge-train run loses the
required-check signal).

**R3 — golangci-lint carries the ISI-2614 workflow-level OOM cap.** On top of the host `.env`
knobs (soft, insufficient alone — golangci's working set peaked ~7.7 GB on the 7.8 GB box), the
`golangci-lint run` step MUST pass `--concurrency=1 --timeout=10m` with step-scoped env
`GOMAXPROCS=1 GOGC=30 GOMEMLIMIT=3800MiB` (merged to main `a6b456d`, PR #38). This is
**strictly memory-reducing** and is the 14.5 L5 lint story's hard requirement — do not regress it.
Scope the env to the lint step only; leave build/test untouched.

**R4 — no `MemorySwapMax` reliance on the 7.9 GB box.** A job that needs >6.8 GB RSS on `gitrunner`
(.190) must be authored to fit or be pinned away — the box keeps `MemorySwapMax=0` so it fails fast
rather than hanging. Do not add swap headroom in workflow expectations; author the job to the cap.

**R5 — skeleton legs skip-with-reason (already in 14.7), and the skip is on the self-hosted
runner too.** A skipped/skeleton leg still declares `runs-on: [self-hosted, linux, x64]` so branch
protection can wire the required-check name now without wedging merges — a skeleton leg on
`ubuntu-latest` would queue-hang instead of skipping cleanly.

**R6 — the Ollama E2E lane (14.8) is a self-hosted lane, not a GPU-hosted-runner assumption.**
14.8's "Ollama service container / self-hosted GPU runner" resolves to: an Ollama **service
container** (small model pinned by digest) on the existing `[self-hosted, linux, x64]` runners —
there is **no** GPU runner in the homelab. The lane stays scaffolded + skipped-with-reason until
`opencode` (5.8) + ISI-2114 conformance land; when it runs, it runs CPU-bound on .191 (16 GB) with
a small quantized model, nightly/release/dispatch only (never per-PR — it can't share the two boxes
with the merge train).

## 3. Correct drop-in shapes (supersede the hosted-runner examples)

`cardinality-lint` (13.6 §Handoff, 14.7-wired) — the example currently reads `runs-on: ubuntu-latest`.
Correct shape:

```yaml
  cardinality-lint:
    name: cardinality-lint
    runs-on: [self-hosted, linux, x64]     # R1 — NOT ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # Node-24-compatible pin (R1)
      - name: Enforce §5.6 metric-label cardinality budget
        run: python3 hack/cardinality-lint.py internal shims console
```

golangci-lint leg (14.5 / `ci.yml` Go matrix) — must carry the R3 cap:

```yaml
      - name: golangci-lint
        env: { GOMAXPROCS: "1", GOGC: "30", GOMEMLIMIT: "3800MiB" }   # R3, step-scoped
        run: golangci-lint run --concurrency=1 --timeout=10m
```

## 4. What this does NOT change

- The **check-run names / branch protection** (14.7 §10.4) are unchanged — this is a `runs-on`
  label + concurrency + memory-cap contract, not a rename.
- The **test content** (L1/L5/L4/supply-chain/E2E gates) is unchanged — same gates, correct executor.
- **Capacity** (2 runners is a throughput bound, not a bug) — ISI-2617 already added the 2nd box;
  raising it further is a ProxOps provisioning item (ISI-2617 lineage), not an E14 spec change.

## References

- ISI-2612 (gitrunner OOM containment; labels `[self-hosted,linux,x64]`; `MemorySwapMax=0` lesson).
- ISI-2617 (gitrunner-2 @ .191, 16 GB — the heavy-job box; same labels).
- ISI-2614 (golangci workflow-level OOM cap, merged `a6b456d` / PR #38).
- `04-epics-and-stories.md` Epic 14 rows 14.1/14.5/14.6/14.7/14.8; `05-testing-strategy.md` §10–§11.
- 13.6 `stories/13-6-cardinality-budget-ci-check.md` §Handoff (drop-in corrected here).
