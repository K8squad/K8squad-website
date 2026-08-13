#!/usr/bin/env python3
"""Story 8.4 falsification — kill a Run in ≤2 clicks from the console (arch §13, FR-F4/FR-A6, S2).

FR-F4 / UX (on 01-squad-overview + 02-run-stream-sse): "Given a Running Run, When I click kill (≤2 clicks),
Then the console calls apiserver → Run Cancelling (Epic 3.3)." This is the console/UI half of the kill edge
whose CONTROL-PLANE half is Story 3.3 (ISI-2203, DONE — the fence-first teardown-then-release to the
absorbing terminal `Cancelled`). It is the FIRST WRITE AFFORDANCE in Epic 8 — every prior console story
(8.1 overview, 8.2 run-stream, 8.7 build-browser) is read-only, no-P2P, and kill was explicitly held OUT of
the 8.2 stream as "a separate authorized control-plane action, not a stream verb" (S6). So 8.4's entire job
is to introduce ONE gated mutation correctly:

  * it is reachable in ≤2 clicks (kill → confirm), on BOTH the overview and the run-stream, with NO kubectl
    fallback (FR-A6/S2);
  * the click records ONE DECLARATIVE cancel intent on the Run (stamped with the initiating principal,
    §12.4) — it does NOT itself SIGKILL the pod, release the checkout, or set the phase (that is the
    reconciler's job, Story 3.3 §A / ADR-002 desired-state). The console fires one signal and observes;
  * the mutating call goes browser → Next.js BFF → apiserver, NEVER browser → kube/Postgres directly
    (§13/ADR-013 choke point — the mutating twin of 8.2's S2);
  * kill is a MUTATE affordance gated by per-project role (§12.3/15.3/8.16): `maintainer`/`admin` kill any
    Run in scope; `contributor` kills OWN Runs only; `viewer` gets NO kill affordance (absent from the DOM,
    not display:none) AND the API rejects it — the server re-checks every call (the console is never the
    sole enforcement point, 8.16);
  * a repeated fire (double-click, client retry) is an IDEMPOTENT no-op — one kill, one terminal `Cancelled`
    (Story 3.3 F-DOUBLECLICK);
  * the transition is NEVER opaque: `Cancelling` (reason=OperatorKill, by-whom §12.4) then terminal
    `Cancelled` streams over the EXISTING SSE bus (8.2 §4.4), distinct from `Failed` (Story 3.3 AC6/FR-G3);
  * the affordance is offered ONLY on a killable (non-terminal) Run — a Succeeded/Failed/Cancelled Run shows
    no kill and killing a terminal Run is rejected (`Cancelled` is absorbing, Story 3.3 AC4).

A "the kill button rendered and something got cancelled" demo passes even if the button calls kube directly,
tears the sandbox down client-side, is shown to viewers, lets a contributor kill anyone's Run, needs a
kubectl fallback, shows an opaque spinner conflated with `Failed`, and offers kill on already-terminal Runs.
So this is a DIFFERENTIAL check over the KILL-AFFORDANCE DESIGN a console would ship. We first prove the
NAIVE "raw kill button" anti-pattern is DETECTED as violating every invariant (real teeth), then prove the
§13/FR-F4 conformant design violates nothing.

Invariants (K1-K7, one per AC):
  K1  ≤2 CLICKS, no kubectl (FR-A6/S2): the kill affordance is reachable in ≤2 clicks (kill → confirm) on
      BOTH the overview and the run-stream surfaces, with NO kubectl fallback. Needing >2 clicks or a
      kubectl escape hatch is the S2 regression.
  K2  BFF CHOKE POINT (§13/ADR-013): the mutating kill call terminates at the Next.js BFF, which proxies the
      apiserver. The browser NEVER issues the kill against the Go apiserver or kube directly — one
      authorization choke point (the mutating twin of 8.2's S2). A kill call pointed at the apiserver/kube
      leaks the API and bypasses the RBAC/JWT wall.
  K3  DECLARATIVE INTENT, not imperative teardown (ADR-002, Story 3.3 §A): the click records ONE durable
      cancel intent on the Run, stamped with the initiating principal (§12.4). The console does NOT itself
      tear down the pod / release the checkout / set the phase — the reconciler completes the rest. A
      console that performs the teardown client-side has taken over a control-plane responsibility.
  K4  RBAC MUTATE-AFFORDANCE GATE (the crux, §12.3/15.3/8.16): the kill verb passes the deny-by-default
      wall. `viewer` → NO affordance (absent from the DOM) AND the API denies; `contributor` → OWN Runs
      only (killing another's Run is denied); `maintainer`/`admin` → any Run in scope; and the server
      RE-CHECKS every call (the console is never the sole enforcement point). Any wrong decision — a visible
      viewer button, a contributor killing another's Run, or trusting the client — breaks the gate.
  K5  IDEMPOTENT INTENT (Story 3.3 F-DOUBLECLICK): the same kill issued twice is a no-op the second time —
      one kill → one teardown → one release → one terminal `Cancelled`, regardless of how many clicks
      arrive. A design that re-fires the teardown per click is not idempotent.
  K6  NEVER-OPAQUE, live over the EXISTING SSE bus, distinct from `Failed` (Story 3.3 AC6/FR-G3): after the
      fire the Run reflects `Cancelling` (reason=OperatorKill, by-whom) then terminal `Cancelled` over the
      SAME SSE bus (8.2 §4.4) — no new transport, no polling loop — and the terminal state is visibly
      DISTINCT from `Failed`. An opaque spinner, a new poll, or conflating `Cancelled` with `Failed` breaks
      legibility.
  K7  ONLY KILLABLE (non-terminal) RUNS (Story 3.3 AC4 absorbing): the kill affordance is offered ONLY on a
      non-terminal Run; a Succeeded/Failed/Cancelled Run shows no kill and killing an already-terminal Run
      is rejected. `Cancelled` is a sink — you cannot cancel a done Run.

Mutation-proof harness (no vacuous guard): `--mutate=<CLICKS|DIRECT_API|IMPERATIVE|UNSTAMPED|
VIEWER_AFFORDANCE|CONTRIB_ANY|NO_RECHECK|NONIDEMPOTENT|OPAQUE|KILL_TERMINAL>` injects ONE single defect into
the CONFORMANT §13/FR-F4 design; the check then goes RED with EXACTLY one violation (no guard shadows
another; the ISI-2346-F1 vacuous-tooth class is excluded by construction). Baseline `python3
run-kill-twoclicks-check.py` exits 0; each `--mutate=NAME` exits 1 with exactly one violation.
"""

import argparse
import sys

# --- role model (per-project, §15.3; global admin bypass, §12.3) -----------------------------------------
# grade governs the KILL mutate affordance: maintainer=any in scope, contributor=own-only, viewer=none.
KILLERS_ANY = {"maintainer", "admin"}   # admin = global_role=admin fleet bypass


def authorize_kill(design, caller_role, run_owned_by_caller, run_in_scope):
    """The server-side kill authorization decision (re-checked on EVERY call, never client-trusted).

    Returns True iff the caller may record a cancel intent on this Run. This is the SAME deny-by-default
    §12.3 wall every surface passes — there is no console-specific authz path (r21).
    """
    if not design["server_rechecks"]:
        # NO_RECHECK: the API trusts the client's assertion instead of re-resolving membership → allow-all.
        return True
    if not run_in_scope:
        return False  # existence-hiding: out-of-scope Run is not even visible, let alone killable
    if caller_role in KILLERS_ANY:
        return True
    if caller_role == "contributor":
        # own-only unless the design has been mutated to let contributors kill anyone's Run
        return True if design["contributor_kills_any"] else run_owned_by_caller
    # viewer (or anything lower): read-only, no kill
    return False


def affordance_visible(design, caller_role):
    """Whether the kill BUTTON is rendered in the DOM for this role (8.16 — absent, not display:none)."""
    if caller_role in KILLERS_ANY or caller_role == "contributor":
        return True
    # viewer: no mutate affordance — unless mutated to leak it
    return design["viewer_sees_affordance"]


# --- invariants (K1-K7) ----------------------------------------------------------------------------------

def check(design):
    """Return the list of invariant violations for a kill-affordance design descriptor."""
    v = []

    # K1 — ≤2 clicks, both surfaces, no kubectl
    if design["clicks_to_kill"] > 2:
        v.append(f"K1 kill needs {design['clicks_to_kill']} clicks — FR-A6/S2 requires ≤2 (kill → confirm)")
    if not {"overview", "run_stream"}.issubset(set(design["surfaces"])):
        v.append("K1 kill affordance missing from a required surface — must be on BOTH overview (8.1) and run-stream (8.2)")
    if design["kubectl_fallback"]:
        v.append("K1 kill falls back to kubectl — S2 requires the operator act WITHOUT kubectl")

    # K2 — BFF choke point (mutating twin of 8.2 S2)
    if design["kill_call_target"] != "bff":
        v.append(f"K2 kill call targets '{design['kill_call_target']}' — the browser must call the Next.js BFF, never the apiserver/kube directly (§13/ADR-013)")

    # K3 — declarative intent, not imperative teardown
    if design["action"] != "record_cancel_intent":
        v.append(f"K3 console action is '{design['action']}' — it must record a DECLARATIVE cancel intent, not perform the teardown (ADR-002/3.3 §A)")
    if design["client_teardown"]:
        v.append("K3 console tears the sandbox down / releases the checkout client-side — that is the reconciler's job (Story 3.3), not the UI's")
    if not design["intent_stamps_principal"]:
        v.append("K3 cancel intent does not stamp the initiating principal (§12.4) — the kill must record WHO issued it")

    # K4 — RBAC mutate-affordance gate (the crux). Evaluate the full decision table + affordance visibility.
    #   viewer   : no button, API denies (own or not)
    #   contributor: button, kills OWN only (other → denied)
    #   maintainer: button, kills ANY in scope
    rbac_ok = True
    # viewer must NOT see the affordance and must be denied by the API
    if affordance_visible(design, "viewer"):
        rbac_ok = False
    if authorize_kill(design, "viewer", run_owned_by_caller=True, run_in_scope=True):
        rbac_ok = False
    # contributor: own allowed, other DENIED
    if not authorize_kill(design, "contributor", run_owned_by_caller=True, run_in_scope=True):
        rbac_ok = False
    if authorize_kill(design, "contributor", run_owned_by_caller=False, run_in_scope=True):
        rbac_ok = False
    # maintainer: any in scope allowed
    if not authorize_kill(design, "maintainer", run_owned_by_caller=False, run_in_scope=True):
        rbac_ok = False
    # out-of-scope Run: even a maintainer cannot kill what is not in scope (existence-hiding)
    if authorize_kill(design, "maintainer", run_owned_by_caller=False, run_in_scope=False):
        rbac_ok = False
    if not rbac_ok:
        v.append("K4 RBAC mutate-gate broken — viewer must have NO affordance + API-deny, contributor kills OWN-only, maintainer/admin kill any in scope, server re-checks every call (§12.3/15.3/8.16)")

    # K5 — idempotent intent
    if not design["idempotent_intent"]:
        v.append("K5 repeated kill re-fires the teardown — the intent must be idempotent (one kill → one terminal Cancelled, Story 3.3 F-DOUBLECLICK)")

    # K6 — never-opaque, existing SSE bus, distinct from Failed
    if design["feedback_transport"] != "existing_sse":
        v.append(f"K6 kill feedback rides '{design['feedback_transport']}' — the Cancelling→Cancelled transition must stream over the EXISTING SSE bus (8.2 §4.4), no new transport/polling")
    if design["opaque_feedback"]:
        v.append("K6 kill shows an opaque spinner — the Cancelling reason (OperatorKill, by-whom §12.4) must be surfaced (FR-G3 never-opaque)")
    if not design["terminal_distinct_from_failed"]:
        v.append("K6 terminal Cancelled is conflated with Failed — an operator kill must be visibly distinct from a died-and-exhausted Run (Story 3.3 AC6)")

    # K7 — only killable (non-terminal) Runs
    if design["offers_kill_on_terminal"]:
        v.append("K7 kill is offered on a terminal Run — a Succeeded/Failed/Cancelled Run is not killable (Cancelled is absorbing, Story 3.3 AC4)")

    return v


# --- designs ---------------------------------------------------------------------------------------------

def conformant_design():
    """The §13/FR-F4 kill-affordance design that holds K1-K7."""
    return {
        "clicks_to_kill": 2,                      # kill → confirm
        "surfaces": ["overview", "run_stream"],   # reachable on both 8.1 and 8.2
        "kubectl_fallback": False,                # S2: no kubectl
        "kill_call_target": "bff",                # browser → Next.js BFF → apiserver
        "action": "record_cancel_intent",         # declarative desired-state (ADR-002 / 3.3 §A)
        "client_teardown": False,                 # reconciler tears down, not the UI
        "intent_stamps_principal": True,          # §12.4 who-issued-it
        "server_rechecks": True,                  # API re-resolves membership every call (8.16)
        "viewer_sees_affordance": False,          # viewer button absent from DOM (8.16)
        "contributor_kills_any": False,           # contributor own-only (§15.3)
        "idempotent_intent": True,                # F-DOUBLECLICK no-op
        "feedback_transport": "existing_sse",     # rides 8.2's bus (§4.4)
        "opaque_feedback": False,                 # Cancelling reason surfaced (FR-G3)
        "terminal_distinct_from_failed": True,    # Cancelled ≠ Failed (3.3 AC6)
        "offers_kill_on_terminal": False,         # only non-terminal Runs (3.3 AC4)
    }


def naive_design():
    """The 'raw kill button' anti-pattern — a console that ships a kill button the lazy way. Must be
    DETECTED as violating every invariant, or the harness has no teeth."""
    return {
        "clicks_to_kill": 4,                      # dig through a menu, no confirm-first affordance
        "surfaces": ["run_stream"],               # only on the stream, not the overview
        "kubectl_fallback": True,                 # "or just kubectl delete pod"
        "kill_call_target": "kube",               # browser talks to kube directly (SPA-to-kube)
        "action": "teardown_pod",                 # imperative teardown from the client
        "client_teardown": True,                  # releases the checkout + sets phase client-side
        "intent_stamps_principal": False,         # no who-issued-it
        "server_rechecks": False,                 # trusts the client's role claim
        "viewer_sees_affordance": True,           # everyone sees the button (display:none at most)
        "contributor_kills_any": True,            # any authenticated user kills any Run
        "idempotent_intent": False,               # each click re-fires the teardown
        "feedback_transport": "poll",             # polls for status after firing
        "opaque_feedback": True,                  # a bare spinner, no reason
        "terminal_distinct_from_failed": False,   # shows "Failed" for a kill
        "offers_kill_on_terminal": True,          # kill button on a Succeeded Run too
    }


MUTATIONS = {
    "CLICKS":            lambda d: d.update(clicks_to_kill=3),
    "DIRECT_API":        lambda d: d.update(kill_call_target="apiserver"),
    "IMPERATIVE":        lambda d: d.update(client_teardown=True),
    "UNSTAMPED":         lambda d: d.update(intent_stamps_principal=False),
    "VIEWER_AFFORDANCE": lambda d: d.update(viewer_sees_affordance=True),
    "CONTRIB_ANY":       lambda d: d.update(contributor_kills_any=True),
    "NO_RECHECK":        lambda d: d.update(server_rechecks=False),
    "NONIDEMPOTENT":     lambda d: d.update(idempotent_intent=False),
    "OPAQUE":            lambda d: d.update(opaque_feedback=True),
    "KILL_TERMINAL":     lambda d: d.update(offers_kill_on_terminal=True),
}

# Which single invariant each mutation is expected to flip (for the no-shadow proof).
MUT_INVARIANT = {
    "CLICKS": "K1", "DIRECT_API": "K2", "IMPERATIVE": "K3", "UNSTAMPED": "K3",
    "VIEWER_AFFORDANCE": "K4", "CONTRIB_ANY": "K4", "NO_RECHECK": "K4",
    "NONIDEMPOTENT": "K5", "OPAQUE": "K6", "KILL_TERMINAL": "K7",
}


def main():
    ap = argparse.ArgumentParser(description="Story 8.4 kill-in-≤2-clicks falsification")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="inject one defect into the conformant design")
    args = ap.parse_args()

    # 1) Teeth: the naive raw-kill-button anti-pattern must be DETECTED violating every invariant.
    naive_v = check(naive_design())
    families = {x.split()[0] for x in naive_v}
    print(f"[model] NAIVE raw-kill-button anti-pattern : {len(naive_v)} violation(s) across {len(families)} invariant(s) -> DETECTED")
    for x in naive_v:
        print(f"[model]   - {x}")
    if families != {"K1", "K2", "K3", "K4", "K5", "K6", "K7"}:
        print(f"[model] FAIL — the naive anti-pattern stopped violating some invariant (teeth lost): {sorted(families)}")
        return 1

    # 2) The conformant §13/FR-F4 design (optionally mutated).
    design = conformant_design()
    if args.mutate:
        MUTATIONS[args.mutate](design)
    v = check(design)

    if args.mutate:
        fams = sorted({x.split()[0] for x in v})
        print(f"[model] conformant + --mutate={args.mutate}: {len(v)} violation(s) {fams}")
        for x in v:
            print(f"[model]   - {x}")
        expected = MUT_INVARIANT[args.mutate]
        if len(v) == 1 and fams == [expected]:
            print(f"[model] PASS — mutation {args.mutate} flips EXACTLY {expected} RED (no guard shadows another).")
            return 1  # a mutation MUST break the check (exit non-zero)
        print(f"[model] FAIL — mutation {args.mutate} expected exactly one violation on {expected}, got {fams}")
        return 2

    print(f"[model] §13/FR-F4 conformant kill design: {len(v)} violation(s); "
          f"clicks={design['clicks_to_kill']}, target={design['kill_call_target']}, "
          f"action={design['action']}, viewer_button={design['viewer_sees_affordance']}, "
          f"contributor_any={design['contributor_kills_any']}, idempotent={design['idempotent_intent']}, "
          f"feedback={design['feedback_transport']}")
    if v:
        print("[model] FAIL — the conformant design violated an invariant:")
        for x in v:
            print(f"[model]   - {x}")
        return 1
    print("[model] PASS — the naive raw-kill-button detectably breaks every invariant; the §13/FR-F4 design")
    print("        holds K1-K7 (≤2 clicks · BFF choke point · declarative intent · RBAC mutate-gate ·")
    print("        idempotent · never-opaque over the existing SSE bus · only killable Runs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
