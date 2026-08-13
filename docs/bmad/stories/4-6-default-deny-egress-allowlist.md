# Story 4.6: Default-deny egress + model-endpoint allowlist (+ optional per-squad proxy)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **🚪 THIS STORY MAKES "EGRESS IS AN ALLOWLIST" TRUE BY CONSTRUCTION — AND KUBERNETES NETWORKPOLICY
> IS PURELY ADDITIVE, WHICH IS THE WHOLE TRAP (arch §12.2, AD-7, ADR-012, D5, NFR-SEC4).** Story 4.1
> already ships the namespace *baseline* (default-deny + allow-DNS + allow-control-plane). This story
> layers the **explicit model-endpoint allowlist** and the **optional `Project.egressPolicyRef`
> forward-proxy** on top. The load-bearing facts a dev must internalize before writing a single
> `NetworkPolicy`: **(1)** NetworkPolicy egress composes as the **UNION of every allow rule's `to:`**
> — there is **no** deny rule that can claw back a too-broad allow. "Default-deny" means something
> *only* because absence-of-allow = deny. So an allow rule with an **empty `to:`** (allow all
> destinations on those ports) or `to: ipBlock 0.0.0.0/0` **is allow-all** and silently defeats
> default-deny — you **cannot** "add default-deny back on top" to fix it. **(2)** `HTTPS_PROXY` is an
> **advisory env var**; a non-proxy-aware or hostile process ignores it and egresses directly. Proxy
> mode is enforced **only** by the NetworkPolicy — the direct-model allow must be **replaced** by an
> allow-to-proxy-only, never merely accompanied by an env var. **(3)** The allowlist is **derived from
> the Agent's resolved model endpoint (§10.3) and `Project.egressPolicyRef`, reconciled** — never a
> vendor CIDR baked into the operator image (D5: *egress is policy, not hardcode*). An "allowlist" that
> is empty-`to`, `0.0.0.0/0`, drops the deny, sets the proxy env without pinning egress to the proxy,
> or hardcodes an endpoint is a **security failure, not a bug ticket**. Read AC1 and AC2 literally.

## Story

As a **security owner running squads on a shared cluster**,
I want **each squad namespace's egress to be default-deny with an explicit, reconciled allowlist to exactly the model endpoint(s) its Agents resolve + the control plane + DNS — and an optional `Project.egressPolicyRef` that routes model traffic through a per-squad forward proxy for corporate/proxied networks, enforced by NetworkPolicy (not just an env var)**,
so that **a Run can reach its model and the control plane but nothing else — no data exfiltration to the open internet, no lateral reach to another squad — the allowlist tracks the Agent's actual endpoint instead of a hardcoded guess, and a compromised or non-proxy-aware process in the sandbox cannot bypass the corporate proxy (arch §12.2, AD-7, ADR-012, D5, NFR-SEC4).**

## Context & prerequisites (read first)

- **PRD:** `docs/bmad/02-prd.md` — **D5** (*egress is policy, not hardcode*), **NFR-SEC4** (controlled
  egress / no uncontrolled data exfiltration), **NFR-SEC1** (cross-squad isolation), **R7** (corporate/
  proxied-network support).
- **Architecture:** `docs/bmad/03-architecture.md`
  - **§12.2 — Egress control (OQ4 / D5 / NFR-SEC4 / R7).** The authoritative decision (ADR-012):
    *"default-deny egress NetworkPolicy per Team namespace + a model-endpoint allowlist, with an
    optional egress proxy for corporate networks."* **Default:** per-Team NetworkPolicy allowlisting
    the required model/tool endpoints (and the control plane); everything else denied. **Optional
    (R7):** a Team-level `egressPolicyRef` injects `HTTPS_PROXY` into sandboxes to route model traffic
    via a forward proxy — *native env + native NetworkPolicy, no bespoke egress gateway*. **This story
    is that decision's implementation.**
  - **§10.3 — BYO model-provider seam (Ollama / OpenAI-compatible, ADR-026).** *"A BYO Ollama endpoint
    (in-cluster Service or a LAN/remote host) is an **allowlisted egress target** on the Team
    NetworkPolicy — default-deny still holds; the endpoint joins the model-endpoint allowlist like any
    other provider."* The allowlist entry for the model is **derived from the Agent's resolved endpoint**
    (`Agent.spec.model` + `Agent.spec.modelEndpointRef` → a Secret-ref endpoint URL), **not** a static
    vendor address. This is the D5 crux: change the endpoint → the policy re-reconciles.
  - **§5.1 CRD rows:** `Project{ repo, workspacePVC, egressPolicyRef, goals, contextBudget }` →
    **Project reconciler → PVC, repo-sync bootstrap, NetworkPolicy.** The per-Project egress allowlist
    + proxy policy is **this reconciler's** NetworkPolicy path (Story 4.1's Team reconciler owns the
    namespace baseline; this story's Project reconciler owns the allowlist/proxy layer). `Agent{ model,
    modelEndpointRef?, … }` supplies the endpoint the allowlist is derived from.
  - **§4 / §12.1 topology:** control plane = `ksquad-system`; data plane = the per-`Team` namespace.
    The allow-control-plane companion (Story 4.1) already permits egress to `ksquad-system`; this story
    does **not** re-mint it, it **relies** on it.
- **ADR:** **ADR-012 (Egress — default-deny NetworkPolicy + optional proxy)**, arch line ~2202: chosen
  over open egress and a bespoke egress gateway (ponytail rung 4). **ADR-026** (BYO model endpoint —
  the allowlisted-egress-target rule). Do not re-litigate; implement them.
- **⚠ Citation note:** the Epic 4 table (line ~183) cites *"Arch §9.2"* for this story — that is
  **stale drift**; §9.2 is the **warm pool**. Egress control is **§12.2** (ADR-012). Build against
  **§12.2 / §10.3**, not §9.2.
- **Depends on:** **Story 4.1** (the namespace + default-deny/allow-DNS/allow-control-plane **baseline**
  this layers on — hard dependency; without the baseline this story's allow rules would sit over open
  egress); **Story 1.2** (the `Project.egressPolicyRef` field + `Agent.modelEndpointRef`); **Story 1.3**
  (the reconciler scaffold). If the fields aren't generated yet, wire against the §5.1 rows and gate
  the envtest on them.
- **Blocks / is consumed by:** **Epic 5** (Runs dispatch model calls that this allowlist gates; the
  BYO-Ollama lane §10.3 depends on the endpoint joining the allowlist), **Epic X** (the **S4
  blast-radius suite** — *default-deny egress* is one of its named runtime checks, Epic 14.4 / line
  ~668 — that *proves at runtime* a hostile Run cannot exfiltrate; this story builds the control, X.4
  attacks it).

## What the Project reconciler provisions (the §12.2 allowlist/proxy layer — authoritative)

On every reconcile of a `Project` (and on change of any Agent it uses, or of the referenced
`egressPolicyRef` config), ensure (create-or-update, idempotent — AC5) the following egress
NetworkPolicies in the **Team namespace**, selecting the Project's Run pods by label (e.g.
`ksquad.io/project=<project>`, `ksquad.io/run` present). **All of this is additive to — and never
removes — Story 4.1's `default-deny` + `allow-dns` + `allow-control-plane` baseline.**

### Mode A — Direct (default, no `egressPolicyRef`)

1. **`allow-model-endpoint`** — an egress-allow policy whose `to:` is the **resolved model
   endpoint(s)** of the Project's Agents, and **nothing broader**:
   - **In-cluster endpoint** (a BYO Ollama `Service`, §10.3): `to: [{namespaceSelector + podSelector}]`
     (or the Service's ClusterIP CIDR) on the model port.
   - **External endpoint** (vendor API or LAN/remote host): `to: [{ipBlock: {cidr: <resolved-IP>/32}}]`
     on 443 (or the endpoint's port). The IP/CIDR is **derived** by resolving `Agent.spec.model` +
     `Agent.spec.modelEndpointRef` — **never** a vendor CIDR compiled into the operator image (D5).
   - **Never** an empty `to:` and **never** `ipBlock 0.0.0.0/0` — both are allow-all and defeat
     default-deny (see the headline). Each allowed destination is an explicit, narrow selector.
2. **`allow-tool-endpoints`** *(only if the Project needs them)* — the same narrow-`to` shape for any
   additional **tool** endpoints the squad legitimately needs (e.g. a package registry, or direct SCM
   egress **only** where `Project.repo.sync.reflectOutbound` pushes from the sandbox rather than via the
   control-plane repo-sync mirror §5.4). Derived from `Project` config; **default is none** (the
   control-plane mirror handles SCM). Absence of a need = absence of a rule = denied.

### Mode B — Proxy (`Project.egressPolicyRef` set — corporate/proxied networks, R7)

`egressPolicyRef` references a config object (a `ConfigMap` holding `{proxyURL, noProxy, allowedCIDRs?}`
plus an optional `caBundleSecretRef` / proxy-auth `Secret` — there is **no** `EgressPolicy` CRD).
When set, the reconciler:

3. **Replaces** the direct-model allow with **`allow-egress-proxy`** — an egress-allow whose `to:` is
   **only** the proxy endpoint (its `ipBlock`/Service) on the proxy port. Direct egress to model/tool
   endpoints and to the internet stays **denied** — this is the *enforcement*. (The direct-model allow
   from Mode A must **not** also be present; if it were, the union would still permit direct egress and
   the proxy would be unenforced.)
4. **Injects proxy env into the sandbox** (via the shim / pod spec, §7.3 credential-injection seam,
   never logged): `HTTPS_PROXY`/`HTTP_PROXY` = the proxy URL, and **`NO_PROXY` covering cluster-internal**
   (`.svc`, `.cluster.local`, the pod/service CIDR, `ksquad-system`, `169.254.169.254`) so
   control-plane/DNS/in-cluster traffic is **not** misrouted through the corporate proxy and keeps
   working if the proxy is down. Proxy CA bundle mounted from `caBundleSecretRef` where the proxy does
   TLS interception.
5. **Fail-closed on a dangling / invalid `egressPolicyRef`:** if the referenced config is missing or
   malformed, the reconciler does **not** fall back to open or even direct egress — it keeps
   default-deny in force (model egress denied), sets an `EgressPolicyDegraded` condition on
   `status.conditions` naming the missing ref, and requeues. A misconfigured proxy fails **safe**, not
   **open**.

**Baseline is never removed (both modes):** `default-deny`, `allow-dns`, `allow-control-plane` (Story
4.1) remain in force at all times. This story only **adds narrow allows** (Mode A) or **swaps the model
allow for a proxy allow** (Mode B). Removing the default-deny to "make egress work" is the canonical
construction error.

## Acceptance Criteria

**AC1 — direct mode is a real allowlist: default-deny holds, and egress reaches exactly {DNS,
control-plane, resolved model endpoint} — nothing else (the NFR-SEC4 crux).**
Given a reconciled `Project` in direct mode, When its Run pod's effective egress is evaluated (the
**union** of every NetworkPolicy `to:` that selects it), Then it can reach cluster DNS (:53), the
control plane (`ksquad-system`), and its Agent's **resolved** model endpoint — **and cannot reach the
open internet** (an arbitrary public IP that is not the model endpoint). The `default-deny`
NetworkPolicy is present and unmodified. **No** allow rule this story adds has an empty `to:` or
`ipBlock 0.0.0.0/0`; each allowed destination is an explicit narrow selector. An allowlist that is
empty-`to`, `0.0.0.0/0`, or that dropped the default-deny is a **construction failure** — because
NetworkPolicy is additive, no later rule can claw a too-broad allow back.

**AC2 — proxy mode is enforced by NetworkPolicy, not by the env var (the R7 crux).**
Given a `Project` with `egressPolicyRef` set, When its Run pod's effective egress is evaluated, Then it
can reach DNS, the control plane, and **only the proxy endpoint** — direct egress to the model endpoint
and to the internet is **denied** (the direct-model allow was **replaced**, not accompanied). **And**
`HTTPS_PROXY`/`HTTP_PROXY` are injected into the sandbox with a **`NO_PROXY` that covers
cluster-internal** so control-plane/DNS/in-cluster traffic is not misrouted through the proxy. Setting
the proxy env while leaving direct egress open (env-only) is a **failure**: a non-proxy-aware or hostile
process would egress straight past the proxy.

**AC3 — the allowlist is derived from the Agent's endpoint, not hardcoded (D5).**
Given an Agent whose resolved model endpoint is a BYO/relocated address (§10.3), When the Project
reconciles, Then the `allow-model-endpoint` `to:` matches **that resolved endpoint** — so the Run can
reach its actual model — and the policy is **not** a vendor CIDR baked into the operator image. Changing
`Agent.spec.model` / `modelEndpointRef` (or `egressPolicyRef`) re-reconciles the policy **without an
operator redeploy**. An allowlist that denies the real endpoint (stale/hardcoded) or that allows an
address the squad never uses is a **failure**.

**AC4 — `egressPolicyRef` fails closed, never open.**
Given a `Project.egressPolicyRef` that points to a **missing or malformed** config, When the reconciler
runs, Then it does **not** open egress and does **not** silently fall back to direct model egress — it
keeps `default-deny` in force, sets an `EgressPolicyDegraded` condition naming the bad ref, and
requeues. A misconfigured egress policy is safe-by-default (Run cannot reach its model, surfaced as a
condition), never fail-open.

**AC5 — reconcile is idempotent and safe to re-drive.**
Given a controller that re-reconciles a `Project` (steady state, restart, crash mid-provision, or model
endpoint / `egressPolicyRef` change), When it re-enters, Then every egress policy is create-or-updated
(server-side apply / create-if-absent) — no duplicate policies, no error on the already-exists path, no
transient window where the direct-model allow **and** the proxy allow coexist (a switch to proxy mode
removes the direct-model allow in the same apply). A partially-applied Project converges; the baseline
(4.1) is never disturbed by this reconciler.

**AC6 — teardown removes only this layer.**
Given a `Project` is deleted (or `egressPolicyRef` is cleared), When the reconciler runs, Then the
Project's `allow-model-endpoint` / `allow-egress-proxy` (and injected proxy env) are removed via
`ownerReference`/finalizer, and the namespace **baseline** (`default-deny` + `allow-dns` +
`allow-control-plane`, owned by the Team reconciler, Story 4.1) is left intact. Clearing
`egressPolicyRef` reverts to direct mode (re-adds `allow-model-endpoint`, drops the proxy allow + env).

## Runnable check (the falsification)

`docs/bmad/spikes/bench/egress-allowlist-check.py` — stdlib-only, `python3` it directly. It is a
**differential** check that models the **effective egress-reachable set** of a Run pod as the **union**
of the `to:` selectors of every egress-allow rule selecting it (exactly how Kubernetes NetworkPolicy
composes — additive, no deny-override). It first proves five **naive** provisioners are **DETECTED** —
so the harness has real teeth — then proves the §12.2 provisioner violates nothing in **both** modes:

```
[model] NAIVE empty-`to` allow (=allow-all :443): 2 violation(s) -> DETECTED
[model]   - direct mode: proxy reachable=True, want False (allowlist must be exactly DNS+control-plane+model, nothing else) (INV-1)
[model]   - direct mode: internet reachable=True, want False (allowlist must be exactly DNS+control-plane+model, nothing else) (INV-1)
[model] NAIVE 0.0.0.0/0 allow (=allow-all): 2 violation(s) -> DETECTED
[model] NAIVE default-deny removed: 1 violation(s) -> DETECTED
[model]   - default-deny NetworkPolicy is absent — namespace is open by default (INV-1)
[model] NAIVE proxy env-only, direct still open: 3 violation(s) -> DETECTED
[model]   - proxy mode: model reachable=True, want False — proxy is enforced by policy (direct-model allow REPLACED), not by env alone (INV-2)
[model] NAIVE hardcoded vendor CIDR: 1 violation(s) -> DETECTED
[model]   - the Agent's resolved model endpoint is NOT reachable — allowlist was not derived from the Agent (hardcoded/stale); the Run cannot reach its model (D5)
[model] §12.2 DIRECT mode : 0 violation(s) -> reaches exactly DNS+control-plane+model; internet DENIED
[model] §12.2 PROXY mode  : 0 violation(s) -> reaches DNS+control-plane+proxy only; model-direct & internet DENIED; HTTPS_PROXY+NO_PROXY set
[model] PASS — naive open-egress footguns detectably break isolation; §12.2 allowlist holds default-deny + narrow allow in both direct and proxy modes.
```

It encodes the invariants as assertions over the reachable set: **(a)** an allow rule with **no `to:`**
matches **all** destinations (the K8s footgun) and an `ipBlock 0.0.0.0/0` matches all — both are
allow-all and flip `internet`/`proxy` reachable in direct mode (AC1/INV-1); **(b)** dropping the
`default-deny` policy is detected (AC1); **(c)** proxy mode with the direct-model allow left in place
leaves `model` directly reachable and the proxy unenforced (AC2/INV-2), and a `NO_PROXY` that omits
cluster-internal is flagged (AC2); **(d)** a hardcoded vendor CIDR leaves the Agent's **resolved**
endpoint unreachable (AC3/D5); **(e)** the §12.2 provisioner reaches **exactly** {DNS, control-plane,
model} in direct mode and {DNS, control-plane, proxy} in proxy mode, internet denied in both. It exits
non-zero if any naive provisioner *stops* being detected (teeth lost) or the §12.2 provisioner *ever*
violates an invariant.
**AC4 (fail-closed on dangling ref), AC5 (idempotency, incl. the no-coexistence-window on the
direct↔proxy switch) and AC6 (teardown leaves the 4.1 baseline intact)** are pinned in prose here and
exercised by the operator **envtest** (real API server) the dev writes with the reconciler — the model
check guards the *static reachability shape* (AC1–AC3), which is the construction-time crux.

## Out of scope (owned elsewhere)

- **The namespace egress baseline** — `default-deny` + `allow-dns` + `allow-control-plane` (**Story
  4.1**, §12.1/§12.2). This story **depends on** it and layers on top; it does not re-mint it.
- **Squad = namespace tenancy / cross-squad isolation** (**Story 4.1**, §12.1) and **RuntimeClass
  sandbox isolation** (**Story 4.2**, §9.1) — the network boundary here assumes the namespace + pod
  isolation those provide.
- **The credential-injection mechanics** the proxy env rides on (**Story 5.4**, §7.3) — this story
  *specifies* which env (`HTTPS_PROXY`/`NO_PROXY`) and that it is never logged; the generic
  Secret→env/volume mapping contract is 5.4's.
- **The BYO model-endpoint seam itself** (**§10.3 / Story 5.7**, ADR-026) — this story consumes the
  *resolved* endpoint to derive the allowlist; it does not implement endpoint resolution/negotiation.
- **The runtime blast-radius / exfiltration proof** (**Epic X / Epic 14.4 S4 suite**, NFR-SEC4) that
  *attacks* this control from a hostile Run in kind — this story builds the control; X.4 proves it
  holds at runtime.
