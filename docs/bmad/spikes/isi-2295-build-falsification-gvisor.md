---
title: "ISI-2295 — Build-heavy gVisor falsification run (spike §6) + rootless-dockerd docker:true (§5.3.3)"
author: "ProxOps"
date: "2026-08-12"
issue: "ISI-2295"
parent: "ISI-2292 (v1 pool constants LOCKED); watches ISI-2113 §6 falsification"
cluster: "observable-agentsandbox (gVisor RuntimeClass `gvisor` = runsc, live)"
verdict: "§6 TRIGGERED — build-path gvisor/runc ratio ≈1.95x (representative compile) .. ≈5.4x (syscall-storm), both > 1.5x"
decision_owner: "Architect"
---

# ISI-2295 — Build-heavy gVisor falsification: result

## 0. TL;DR (flag loudly, as §6 requires)

**§6 falsification condition (gVisor steady-state overhead > ~1.5x runc on the
critical build path) is TRIGGERED.** On a representative, non-model-bound
`docker build`, gVisor is **~1.95x** runc wall-clock (p50); on a deliberately
syscall/exec-heavy stressor it is **~5.4x**. Per the issue's operational
definition (`>1.5x = FLAG`), this **nominally reopens the ISI-2113 runtime-default
decision** and is routed to the Architect.

**Two load-bearing caveats the Architect must weigh before acting — this is NOT a
naive "abandon gVisor" signal:**

1. **The test deliberately isolates the build burst with ZERO model-wait masking.**
   §3 of the ISI-2113 spike argues the build/IO overhead is amortised against
   model-wait in a real agent Run. This bench removes that masking by design
   ("NOT model inference"), so the ~1.95x is the *unmasked build-burst* cost, not
   the end-to-end agent-Run cost. For chat-like Runs (mostly model-wait) the
   end-to-end impact is far below 1.95x; for CI-like `docker:true` build Runs it
   is more exposed. **The number is real; how much it matters depends on the
   Run mix.**
2. **The overhead is almost certainly runsc-platform-dependent.** gVisor's cost
   here is filesystem-gofer + syscall-interception on an IO/syscall-heavy path.
   If the node's runsc uses the **systrap/ptrace platform (no KVM)** — the common
   default — build-heavy Runs pay a large tax. This cluster has **nested-virt
   available** (per the issue notes), so **enabling the runsc KVM platform is a
   concrete mitigation to measure BEFORE any runtime-default change.**

**§5.3.3 (rootless-dockerd docker:true on gVisor): INCONCLUSIVE (partial).**
Rootless dockerd **starts, is API-live, pulls images, and creates containers**
under gVisor — but a full multi-step build's **RUN step fails** at per-container
network-namespace setup (`setns … operation not permitted`) in the non-standard
rootless network config this harness was forced into by gVisor's lack of
nft/iptables and vpnkit-egress failure. Not cleanly attributable to gVisor vs
harness → needs a follow-up with the production rootless-dockerd sidecar config.

---

## 1. Method

- Cluster `observable-agentsandbox`, RuntimeClass `gvisor` (handler `runsc`), 1 CP
  + 2 identical workers (4 vCPU / 12 GiB). Kernel 6.8.0-88, containerd 1.7.25.
- Builder: `docker:27-dind`, **dockerd started directly** (the stock
  `dockerd-entrypoint.sh` runs an `iptables --version`/nft preflight under
  `set -eu` that is **fatal on gVisor** — its netstack has no nft). Flags:
  `--iptables=false --ip6tables=false --bridge=none --storage-driver=overlay2`;
  builds run `--network=host` (offline, no NAT needed). Same daemon config on both
  runtimes ⇒ the RuntimeClass is the only variable.
- **overlay2** storage on both = the realistic production driver. (An early vfs
  pass was discarded as a driver artifact — vfs copies every layer, amplifying
  gVisor's IO overhead unrepresentatively.)
- Isolation: timed pods run **one at a time, pinned to the same single worker**
  (no cross-pod CPU contention; identical node for every cell).
- `dynatrace.com/inject: "false"` on every pod (reuse of the ISI-2294 opt-out).
- Base images pre-pulled **before** timing (build path is timed, not image pull).
  Each timed build is `--no-cache`. n=10 timed iterations + 1 warm-up per cell.
- Two workloads:
  - **compile** (PRIMARY, representative): multi-stage `golang:1.22-alpine` →
    `go build` of 1500 generated funcs (CPU-bound compile + object-file IO + a
    few toolchain subprocesses), offline (GOPROXY=off) → `alpine` final stage.
  - **churn** (SECONDARY, worst-case bound): `alpine` multi-stage with 600+ tiny
    process spawns + per-file gzip/sha256 + tar + cross-stage COPY — deliberately
    syscall/exec-heavy (gVisor's worst case), reported as an upper bound only.

Harness (reproducible): `docs/bmad/spikes/bench/build-falsification-bench.yaml`
(ConfigMap: Dockerfiles + `run.sh`), `build-falsification-jobs.yaml`,
`run-matrix.sh`, raw `results-isi2295.txt`.

---

## 2. Results (overlay2, n=10, seconds, single isolated worker)

### 2a. compile — representative critical build path (PRIMARY)

| runtime | p50 | p95 | min | all iters (s) |
|---------|----:|----:|----:|---------------|
| runc    | **4.56** | ~7.0 | 4.41 | 4.41 4.44 4.49 4.51 4.52 4.59 5.29 5.94 6.29 7.02 |
| gvisor  | **8.90** | ~11.2 | 7.94 | 7.94 8.21 8.44 8.83 8.84 8.96 9.01 10.23 10.30 11.20 |

- **gvisor/runc p50 ratio = 8.90 / 4.56 = 1.95x**
- p95/p95 ≈ 1.60x; min/min = 1.80x → **every framing is > 1.5x.**
- (runc's later iters crept up from mild late contention, which only makes the
  ratio *more conservative*; it still trips.)

### 2b. churn — syscall/exec-storm worst-case bound (SECONDARY)

| runtime | p50 | p95 | min |
|---------|----:|----:|----:|
| runc    | 2.50 | ~4.0 | 2.40 |
| gvisor  | 13.49 | ~14.4 | 9.52 |

- **gvisor/runc p50 ratio = 13.49 / 2.50 = 5.4x** (process-creation + gofer IO is
  gVisor's cost center; this is the ceiling, not the representative path).

### 2c. §5.3.3 — rootless dockerd under gVisor (capability probe)

| stage | result |
|-------|--------|
| rootlesskit userns + copy-up | ✓ works under gVisor |
| dockerd daemon start (uid 1000, **no privileged**) | ✓ `DOCKERD_READY`, vfs |
| image pull (egress) | ✓ with rootlesskit `--net=host` (+`--ip-forward=false`, since the sentry denies the non-root `/proc/sys/net/ipv4/ip_forward` write) |
| container create (WORKDIR step) | ✓ ran + removed an intermediate container |
| **build RUN step** | ✗ `failed to create default sandbox: … set into network namespace: operation not permitted` |

Rootless dockerd is clearly *functional* under gVisor; the failure is the
per-RUN network-namespace `setns`, which this harness's gVisor-forced rootless
net config (no slirp4netns in the image; vpnkit egress EOF'd; had to use host-net
+ bridge=none) does not satisfy. **Not a clean gVisor verdict — follow-up needed.**

---

## 3. Disposition

- **§6: TRIGGERED / FLAGGED.** Routed to the Architect (decision owner) via an
  interaction on ISI-2295. Recommended path *before* reopening ISI-2113:
  **measure the runsc KVM platform** (nested-virt is available) on the same
  compile workload — if it collapses the ~1.95x toward ~1.1–1.3x, the
  gVisor-default stands and this becomes a node-config action, not a
  runtime-default reversal.
- **§5.3.3:** delegated follow-up (child issue) to retest rootless-dockerd build
  completion with a proper rootless bootstrap / the production sidecar config.
- **v1:** unchanged. ISI-2292's LOCKED pool constants are not a function of this
  ratio; this run is the strengthening evidence the Architect asked to see, not a
  v1 gate.
