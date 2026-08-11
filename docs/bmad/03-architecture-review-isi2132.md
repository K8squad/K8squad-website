# Architecture Review — KSquad Phase 3 (ISI-2132)

**Reviewer:** Amelia (Code Reviewer) · **Date:** 2026-08-10
**Target:** `docs/bmad/03-architecture.md` @ 3ddb171 (branch `bmad/architecture-isi2119`)
**Method:** adversarial layers — Blind Hunter (correctness), Edge Case Hunter (race/isolation), Acceptance Auditor (claim-vs-evidence)
**Verdict:** **CONDITIONAL PASS.** Structural spine is sound (storage split, namespace tenancy, shim seam, integrate-not-build memory). But the coordination-spine correctness — the doc's own #1 correctness-critical track (§1.1, R10) — is **asserted, not designed**, and one genuine correctness hole (F1) is open. Gate 2 may proceed; **F1–F4 must be closed in the coordination-spine epic's design step before any code**; F5–F7 before the memory/tenancy epics.

> **Meta (answered up front):** the review request's section anchors (§6.3 fencing design, §6.4 idempotent reconcile, §7.3 memory, §12/§17.1 tenancy, §18 ADR trades, §21 seams) **do not exist in the committed doc.** §6 has only 6.1/6.2; ADRs are a status list (App. A); tenancy is §9. The correctness-critical fencing (§6.3) and re-entrancy (§6.4) the request pointed at are one-sentence assertions — which *is* finding F2.

---

## BLOCKING — close before the R10 coordination-spine epic (sequenced first, §4.7)

### F1 · Critical · Fencing protects only the checkout row, not the state-mutating resources — the GC-pause zombie writer is NOT closed
`§6.2` `§5.3` `§9.3`
The `holder = run_id` + `lease_epoch` guard fences writes to `checkouts`/`work_items` **only**. A GC-paused/partitioned holder R1 whose lease expires is reclaimed to R2 (§5.3), but R1's sandbox is **still alive** and keeps mutating the shared per-Project PVC (§9.3), the memory store (§8), the git remote, and object-store artifacts — **none of which check the lease/epoch.** Textbook fencing (Kleppmann) requires the *protected resource* to reject stale tokens; here the protected resources have no fence. → R1 and R2 concurrently write the same per-Project workspace (corruption); R1 writes memory/git after eviction.
**Fix:** the reclaim path must actively **fence the pod** (terminate / cordon / revoke PVC mount + egress) *before* releasing the checkout. Lease expiry from a GC pause is indistinguishable from death at the lease layer but the pod is alive at the resource layer — the controller (§5.3) currently treats "lease expired" as "dead," which is the bug.
**This is the direct answer to the issue's question ("close the race for ALL state-mutating writes?"): NO.**

### F2 · Critical · `lease_epoch` is named but not designed and not in the schema
`§6.2` `§6.1` `§4.2`
§6.2 cites "monotonic `lease_epoch`," but the `checkouts` schema (§4.2/§6.1) is `(work_item_id, holder=run_id, lease_expires_at)` — **no epoch column**, and no resource consumes an epoch. The fencing token is decorative. For the build the doc itself calls "the single most correctness-critical" (§1.1/R10), the fencing token and the re-entrancy path must be *designed* (schema + guard + who checks the epoch) before Epics, not asserted.

### F3 · High · `checkouts` cardinality undefined → renew/reclaim fencing may be unsound
`§6.1` `§6.2`
One row per work_item (holder rewritten on reclaim), or append-only one-row-per-claim? The doc doesn't say, and it decides correctness: if append-only, a zombie R1's renewal `UPDATE … WHERE holder=R1` succeeds on its stale row while R2 holds a newer row → **two live leases on one item, authority ambiguous.** Pin the cardinality + uniqueness constraint (recommend: exactly one active checkout per work_item, `lease_epoch` incremented on every reclaim, renewal guarded by `holder AND epoch`).

### F4 · High · Idempotent-reconcile claim (§5.2) is unproven for side-effecting steps — Dispatching double-submits
`§5.2`
"Re-entering any phase reads durable state and continues" holds only for *naturally idempotent* steps. **Dispatching** submits an A2A task to the shim (external side effect). Controller crash *after submit, before persisting `status=Running`* → restart re-enters Dispatching → submits again → **agent runs twice** (double git/build). Same risk in **Collecting** (artifact double-write).
**Fix:** deterministic A2A task id derived from `run_id` (dedup at the shim), or a durable "dispatched" marker written atomically-with/before submit. This is the §6.4 re-entrancy question — today the answer is "not for external-effect steps."

---

## IMPORTANT — resolve during Epics / feed the §14 gates

### F5 · High · Memory/apiserver don't authenticate the *calling principal* → intra-squad provenance is forgeable (breaks §8.4 & F16)
`§8.4` `§4.4`
§8.4 hangs the entire trust model on per-principal provenance, but §4.4 has agents reach `ksquad-memory` "over the squad-scoped network path" with **no per-principal auth stated.** If the endpoint trusts a squad-shared token or a sandbox-asserted `principal_id`, a hostile Run forges another principal's provenance — collapsing "authorized + provenanced" writes. **Per-principal credentials (not per-squad) for memory/api calls are a prerequisite for §8.4 to hold.**

### F6 · High · "Memory never a coordination back-channel, enforced structurally" (§8.4) is an overclaim — intra-squad it is detection, not prevention (F16)
`§8.4` `§4.3`
Cross-squad P2P is structurally prevented by scope. **Intra-squad,** `memory.write(A)` + `memory.search(B)` *is* a lateral channel; provenance / "untrusted read" only **labels and weights** it — a convention, not a structural block. Two same-squad agents can coordinate via memory, bypassing the auditable work-item handoff (the "never P2P" locked decision). Honest framing: **cross-squad prevented; intra-squad attributed + audited, not prevented.** And §4.3's suite has **no covert-channel test** for F16 — it tests poisoning (trust) and residue (isolation), not coordination-bypass. Add one; soften the claim. **This is the issue's exact F16 question — provenance+scope mitigates, it does not prevent, intra-squad.**

### F7 · High · Per-Project-PVC persistence vs per-principal scope is a stated contradiction with no mechanism
`§9.3`
§9.3 wants both: per-Project PVC persisting source+build cache **across Runs** (FR-C2 — the point is cross-Run cache reuse) AND "PVC access scoped per principal, not merely per Project" (NFR-SEC5). A build cache shared across principals is exactly what per-principal scope forbids. Two goals, no reconciling mechanism (subpath-per-principal? separate PVCs? shared-read / principal-write?). The S4 residue test exposes this. Specify how cache-reuse and principal-isolation coexist.

### F8 · Medium · RuntimeClass fallback assumes Kata ≡ gVisor behavioral equivalence — false for arbitrary builds
`AD-3` `§14`
Kata→gVisor is treated as a latency/isolation tradeoff. They are **not behaviorally equivalent**: gVisor intercepts syscalls with a *partial* surface; build tools/agents that run under Kata (full VM) can fail under gVisor on unimplemented syscalls. **ISI-2113 must add a workload-compatibility acceptance criterion**, not only latency + hostile-Run containment — else the "fallback" breaks real Runs structurally. (Answers the issue's "seam truly pluggable?" — the RuntimeClass seam is pluggable at the pod spec but *not* behaviorally transparent.)

### F9 · Medium · Pause/resume (§10, FR-G3) assumes runtime resumability absent from the shim conformance suite (§7.5)
`§10` `§7.5`
Graceful `Paused`→resume presumes the agent runtime can suspend/resume a task mid-flight. A2A lifecycle has `input-required`, not credential-pause-resume. If OpenClaw/Hermes restart from scratch, pause/resume silently degrades to **kill/restart (lost partial work).** Make resumability a §7.5 conformance requirement, or scope FR-G3 to kill/restart honestly. Hidden coupling a credential spike (ISI-2112) could break.

### F10 · Medium · Node co-tenancy of hostile Runs unaddressed vs S4 blast radius
`§9.1` `§4.3`
Namespace-per-Team is a *soft* boundary; ResourceQuota bounds a namespace's *total*, not *per-node* contention. A hostile Run shares a kernel-host with other squads' pods (Kata mitigates escape, not resource-DoS / side-channel). No node-pool-per-tenant or anti-affinity for sandbox RuntimeClass. Name the residual and decide (dedicated sandbox node pool vs accepted risk).

### F11 · Medium · Allowlisted model endpoint is an unavoidable exfiltration path — name it
`§9.2` `§4.3`
Default-deny egress still must allowlist model endpoints for agents to function; a hostile agent exfiltrates via prompts to that allowed hole. The egress proxy audits, not prevents. Inherent to BYO-model, but the S4 suite should include an **exfil-attempt case** and the doc should acknowledge it rather than let "default-deny + allowlist" read as containment.

---

## CLARIFICATIONS

### F12 · Low · Claim SQL (queue-pop) ≠ workItemRef-driven reconcile (targeted)
`§6.2` `§5.2`
§6.2 SQL is `… WHERE state='open' … SKIP LOCKED LIMIT 1` (pop *any* open item), but §5.2 dispatches a Run against a specific `Run.spec.workItemRef`. Who assigns workItemRef — scheduler (targeted) or agents pulling the backlog (queue)? For a targeted claim it's `WHERE id=:ref AND state='open' FOR UPDATE`, and SKIP-LOCKED-returns-empty must be distinguished from already-claimed. Clarify the ownership model.

### F13 · Low · ADR index (App. A) records decisions, not trades
`App. A`
The request asked to flag ADRs where the rejected option was stronger — but App. A is a status list; only OQ9 (§3) and OQ10 (§8.2) argue the rejected alternative. AD-4/5/7/8 have no alternatives-considered / why-rejected / consequences. Capture the trade for tenancy (AD-5: namespace vs vcluster / cluster-per-tenant — ties to F10) and workspace (AD-8) so Epics doesn't relitigate.

---

## Disposition
- **F1–F4** (coordination-spine correctness) → route to Architect (ISI-2119) for a design pass **before the R10 foundational epic writes code.** Non-negotiable per the doc's own sequencing (§4.7 item 2).
- **F5–F7** → resolve at the memory/tenancy epic design step.
- **F8–F11** → fold acceptance criteria into ISI-2113 (F8), ISI-2112/§7.5 (F9), and the `test/isolation` suite (F10/F11).
- **F12–F13** → doc clarifications, non-blocking.

Nothing here blocks **starting** the CRD/scaffolding epic (§4.7 item 1) or the CEO Gate 2 review. The blockers are scoped to the coordination-spine and memory/tenancy tracks.
