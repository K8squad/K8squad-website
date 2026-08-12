---
title: "ISI-2300 — rootless-dockerd docker:true BUILD on gVisor: root-cause + §5.3.3 decision"
author: "Architect (Winston)"
date: "2026-08-12"
issue: "ISI-2300"
parent: "ISI-2295 (§5.3.3 could not be cleanly confirmed there)"
decision_owner: "Architect"
execution_owner: "ProxOps (holds the observable-agentsandbox gVisor cluster)"
gate: "NOT a v1 gate (docker:true is capability-gated + spike-tunable, arch §5.3.3 / §9.1)"
status: "DECISION LANDED (retest-independent) + empirical rootless-dockerd confirm DELEGATED to ProxOps"
---

# ISI-2300 — rootless-dockerd `docker build` on gVisor

## 0. TL;DR

Two questions were tangled together in ISI-2295 §5.3.3. Separating them is the
whole job:

1. **"Can a full `docker build` RUN step complete under rootless-dockerd on
   gVisor?"** — an *empirical* question about one specific mechanism. ISI-2295
   could not answer it cleanly because its harness was forced into a
   non-standard rootless net config (host-net + `bridge=none`, no slirp4netns).
   **This remains empirical and is DELEGATED to ProxOps** with a production-config
   retest harness spec (§3). I have no access to the gVisor cluster from the
   architecture seat, so I cannot and will not fabricate this run.

2. **"What mechanism should back the `docker` build capability on gVisor?"** —
   an *architecture* question, and mine to decide. **It does not depend on the
   answer to (1).** Decision below.

**Decision (§2):** the `docker` *build* capability on gVisor is backed by a
**daemonless rootless image builder (kaniko / buildah / BuildKit-rootless)** as
the **primary** path, because it sidesteps the exact failure class ISI-2295 hit —
per-container network-namespace `setns` — entirely. **rootless-dockerd is
retained only for the narrower "live Docker daemon API at runtime" need** (nested
`docker run`, compose, testcontainers), and only if ProxOps' retest confirms it
completes RUN steps; genuine nested-Docker otherwise routes to a **Kata**
RuntimeClass. This is exactly the *"route docker:true builds to a different
mechanism"* option the issue offered, chosen deliberately, not as a fallback.

The architecture already listed `rootless dockerd / kaniko / buildah` as the
§5.3.3 backings — this decision **orders** them (kaniko/buildah first for builds)
and pins *why*.

---

## 1. Root cause of the ISI-2295 RUN-step failure

Observed: `failed to create default sandbox: … set into network namespace:
operation not permitted` during a build RUN step.

- **"default sandbox"** is Docker libnetwork's per-container **network namespace**.
  Creating it makes a fresh netns and has a helper thread `setns(fd,
  CLONE_NEWNET)` into it to wire up interfaces. The `EPERM` is that inner `setns`
  being denied.
- **This is the INNER, per-container netns — not the OUTER rootlesskit netns.**
  That distinction is the crux ISI-2295 flagged as "not cleanly attributable":

  | layer | who creates it | ISI-2295 config | proper prod config |
  |-------|----------------|-----------------|--------------------|
  | outer (daemon egress) | rootlesskit | `--net=host` (reuse **pod** netns) — image had no slirp4netns, vpnkit EOF'd | `--net=slirp4netns` (fresh **owned** netns) |
  | inner (per-container sandbox) | dockerd/libnetwork per RUN | created **under the pod's gVisor-managed root netns** | created **under rootlesskit's own child netns** |

- **Why the config matters to the EPERM:** in ISI-2295 the daemon lived in the
  *pod's* shared, sentry-managed root netns (because `--net=host`). Creating a
  nested netns and `setns`-ing into it *as an unprivileged uid from within that
  shared root netns* is what the runsc sentry denied. In the production config,
  rootlesskit+slirp4netns first `unshare`s a **fresh netns the daemon owns**, and
  per-container sandboxes are children of *that* — a topology the sentry may
  permit where nesting under the pod root netns did not. **That is the falsifiable
  hypothesis the retest exists to settle.** slirp4netns does not "fix networking"
  in the naive sense here — it changes *which netns the per-container setns
  happens under*, which is the variable that plausibly moves the EPERM.

- **Honest uncertainty:** gVisor implements network namespaces but has historically
  had gaps in nested-netns / netlink operations for unprivileged callers, and this
  is both (a) the area with the most runsc feature gaps and (b) — per ISI-2295 §6 —
  the area with the **worst gVisor overhead** (syscall/netns-storm = 5.4x runc).
  So even a PASS leaves rootless-dockerd the fragile *and* slow path for builds.
  I will not predict the retest result; I design the architecture so it wins
  either way.

---

## 2. Decision (§5.3.3, retest-independent)

Split `docker: true` into the two capabilities that were always hiding inside it:

### 2a. Build an image (the common docker:true use in CI-like Runs) → daemonless builder
Back it with **kaniko** (pure Dockerfile→image, fully userspace) or **buildah**
(`--isolation=chroot`, `--network=host`) / **BuildKit-rootless**. Rationale
(the lazy-senior rung: a tool already solves this without the fight):

- **No per-container libnetwork sandbox.** kaniko executes RUN steps in the build
  container's *own* namespace with its existing network; buildah RUN under
  `chroot`/host-net creates **no** per-container bridge netns. **The exact `setns`
  that EPERM'd in ISI-2295 is never issued.** The failure class is designed out,
  not worked around — robust regardless of gVisor's nested-netns support.
- **Cheaper on gVisor.** No daemon, far fewer netns/netlink syscalls — it avoids
  the 5.4x syscall-storm cost center §6 identified, not just the correctness gap.
- **Already unprivileged.** kaniko/buildah target exactly "build images in an
  unprivileged Kubernetes pod." No host Docker socket, no privileged sidecar —
  aligned with §9.1 (gVisor default) and D2 least-privilege.

### 2b. Drive a live Docker daemon at runtime (nested `docker run`, compose, testcontainers) → daemon required
This genuinely needs a running daemon and cannot use kaniko/buildah:
- **rootless-dockerd on gVisor** — offered **only if ProxOps' retest (§3)
  confirms RUN steps complete** with the production slirp4netns config; else
- **Kata RuntimeClass** (`runtimeClassHint`) for real nested Docker — already the
  §5.3.3 answer for "real nested Docker." The operator refuses `docker: true` on a
  gVisor-only runtime unless one of these mechanisms is selected (§9.1 gate stands).

### 2c. What this changes
- §5.3.3 backings become **ordered + purpose-split**, not a flat "dockerd / kaniko
  / buildah" list: *builds → kaniko/buildah primary; daemon-at-runtime →
  rootless-dockerd (pending retest) or Kata.*
- **No v1 impact.** docker:true is capability-gated and spike-tunable (§9.1); the
  mechanism is a runtime-config choice, not a structural one. ISI-2292's LOCKED
  pool constants are unaffected.
- **rootless-dockerd is not deleted** — it stays the ergonomic choice for Runs that
  want a real daemon *if* it proves out. The decision only removes it from the
  **critical build path**, where its failure mode and its cost both live.

---

## 3. Production-config retest harness spec (for ProxOps)

Goal: settle §1's falsifiable hypothesis — *does moving rootlesskit from
`--net=host` to `--net=slirp4netns` (fresh owned netns) let the per-container
`setns(CLONE_NEWNET)` succeed under this cluster's runsc?*

Reuse `docs/bmad/spikes/bench/build-falsification-bench.yaml` (ROOTLESS=1 path)
with these **production** changes vs the ISI-2295 bypass:

1. **Image ships slirp4netns.** Use `docker:27-dind-rootless` (bundles
   slirp4netns + rootlesskit) or add `apk add slirp4netns` to the builder image.
   ISI-2295's blocker was "image had no slirp4netns" — remove it.
2. **`DOCKERD_ROOTLESS_ROOTLESSKIT_NET=slirp4netns`** (NOT `host`, NOT `vpnkit`).
   Keep `--mtu=1500`. Let rootlesskit create its **own** netns.
3. **Restore the default bridge** — drop `--bridge=none`. Rootless dockerd's
   default bridge lives *inside* rootlesskit's netns; that is the whole point of
   the proper config and is what exercises the real per-container sandbox path.
   Keep `--iptables=false --ip6tables=false` only if slirp4netns egress needs it;
   prefer the stock rootless defaults so this is the *production* daemon config,
   not a bespoke one.
4. **Do NOT force `--network=host` on `docker build`.** Let RUN steps use the
   default network — that is what creates the per-container sandbox the retest is
   about. (host-net on the build masked the very thing we need to test.)
5. Keep everything else identical to ISI-2295 for apples-to-apples: uid 1000, no
   privileged, `runtimeClassName: gvisor`, overlay2 (or fuse-overlayfs if overlay2
   is denied rootless under the sentry — note which), `dynatrace inject=false`,
   the `Dockerfile.compile` workload, n small (this is a capability probe, not a
   perf run — 1 clean multi-step build completing is the signal).

**Pass criterion:** the `Dockerfile.compile` multi-stage build's RUN steps
complete (image built) with `DOCKERD_ROOTLESS_ROOTLESSKIT_NET=slirp4netns` and a
default bridge. Capture `/tmp/dockerd.log` + the build log on failure.

**Decision routing after the retest:**
- **PASS** → §2b keeps rootless-dockerd as the daemon-at-runtime option for gVISOR;
  §2a (kaniko/buildah primary for *builds*) still stands unchanged.
- **FAIL (same setns EPERM)** → confirms nested libnetwork sandboxing is a genuine
  runsc gap on this cluster; rootless-dockerd is dropped for *builds* entirely,
  daemon-at-runtime routes to **Kata**, and §2a is the only build path. Either way
  the architecture in §2 holds — the retest only decides rootless-dockerd's fate
  for the narrow daemon-at-runtime slice.

---

## 4. Disposition

- **§5.3.3 architecture decision: LANDED** (this doc + arch §5.3.3 / decision
  table edits). Retest-independent by construction.
- **Empirical rootless-dockerd confirm: DELEGATED to ProxOps** (execution owner,
  holds the cluster) as a child issue with §3 as the spec. ISI-2300 is **blocked**
  on that retest — unblock owner **ProxOps**, action **run the §3 harness and
  report PASS/FAIL** — then I fold the result into §2b and close.
- **v1:** unchanged; not a gate.
