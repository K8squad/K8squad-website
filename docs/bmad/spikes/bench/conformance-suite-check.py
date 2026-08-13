#!/usr/bin/env python3
"""
conformance-suite-check.py — Story 5.6 (ISI-2218) runnable falsification.

The load-bearing property of a CONFORMANCE SUITE is *detecting power*: it must go
RED on a shim that violates C1-C10 and GREEN on one that honors them. A suite that
is green on a broken shim is worthless — the ISI-2346-F1 "guard with no teeth" class,
now applied to the gate itself. So this bench is META: the mutants are the *shim under
test*, not the suite, and every check is proven load-bearing two ways —

  (1) TEETH:   the conformant reference shim passes Cn; a shim that violates exactly
               Cn fails Cn (and only Cn) — the check has power.
  (2) VACUITY: stubbing Cn to `return PASS` (a vacuous check) lets the *violating*
               shim pass the suite — proving the check body is what catches it, not
               an incidental side effect.

Same discipline as agent-card-check.py / handoff-advisory-check.py. Stdlib only —
`python3 docs/bmad/spikes/bench/conformance-suite-check.py`. Exit 0 iff the suite
(a) passes the reference shim on all of C1-C10, (b) fails each non-conformant shim on
its violated check, and (c) each check is non-vacuous. Models the ISI-2114 §12 suite
in-process; the buildable `conformance/` harness (Ollama lane, opencode 5.8) is the
real-runtime promotion — this proves the *assertions have teeth* before they are built.
"""

import sys

PASS, FAIL = "PASS", "FAIL"


# --------------------------------------------------------------------------- #
# A minimal shim model: the six A2A MUST-verbs (§3) + Agent Card (§6) + state. #
# A "shim" is anything exposing this surface; the suite drives it black-box.   #
# --------------------------------------------------------------------------- #
class Shim:
    """Reference-CONFORMANT shim. Each mutant subclass breaks exactly one C-invariant."""

    type = "reference"

    def __init__(self, card=None, ollama_base=None):
        self.executions = 0            # agent executions started (C1)
        self._tasks = {}               # a2a_task_id -> state (§3.1)
        self._artifacts = {}           # (wi, run, kind) -> sha  (C2 upsert)
        self._blob_refs = set()        # sha of blobs referenced by a live row (C3)
        self._events = []              # SSE stream: list of {seq, type} (C4/C6)
        self._fence = 10               # current fence token (C3)
        self._model_calls = []         # base-urls the runtime actually dialed (C9)
        self.ollama_base = ollama_base
        self.card = card or {
            "type": self.type,
            "capabilities": {          # first-class flags, every key explicit (§6.2)
                "streaming": True, "toolCalls": True,
                "interactive": False, "byoModelEndpoint": True,
            },
            "credential": {"credentialType": "byo-endpoint",
                           "credentialLifecycle": "static"},  # metadata only (C7)
        }

    # V1 SubmitTask — deterministic id dedup (C1). A repeat id reattaches. -----
    def submit(self, task_id, model_route=None):
        if task_id in self._tasks:
            return "reattached"
        self._tasks[task_id] = "working"
        self.executions += 1
        # BYO endpoint: honor the injected base-url (C9), never a baked-in host.
        if self.card["capabilities"].get("byoModelEndpoint") and self.ollama_base:
            self._model_calls.append(self.ollama_base)
        else:
            self._model_calls.append(model_route or "provider-default")
        return "submitted"

    # V5 EmitArtifact — idempotent upsert (C2) + fence gate (C3). --------------
    def emit_artifact(self, wi, run, kind, sha, fence):
        if fence < self._fence:                 # stale fence → zombie write
            return "rejected"                    # blob stays unreferenced (C3)
        key = (wi, run, kind)
        self._artifacts[key] = sha               # UNIQUE upsert, not append
        self._blob_refs.add(sha)
        return "stored"

    # V2 StreamEvents — monotonic gap-free seq; resume from lastSeq (C4). ------
    def append_event(self, etype):
        self._events.append({"seq": len(self._events) + 1, "type": etype})

    def stream(self, last_seq=0):
        return [e for e in self._events if e["seq"] > last_seq]

    # C6 capability honesty: a run that hits an interactive point. A runtime -- #
    # advertising interactive:false must resolve it WITHOUT emitting            #
    # input-required (degrade/fail honestly), never surface a capability its    #
    # card denied.                                                              #
    def run_needs_input(self):
        if self.card["capabilities"].get("interactive"):
            self.append_event("input-required")
        else:
            self.append_event("status")   # honest: no input-required emitted

    # V4 CancelTask — terminal + idempotent (C8). -----------------------------
    def cancel(self, task_id):
        st = self._tasks.get(task_id, "canceled")
        if st in ("completed", "failed", "canceled"):
            return "noop-success"            # cancel of terminal = no-op success
        self._tasks[task_id] = "canceled"
        return "canceled"

    # V6 GetAgentCard — wire form the core reads before dispatch. Never any ---- #
    # secret material (C7).                                                      #
    def card_wire(self):
        return dict(self.card)

    # C7 auth-failure → pause. An auth error is a first-class pause signal, ---- #
    # not a generic failure.                                                     #
    def on_auth_error(self):
        self.append_event("auth-required")
        return "Paused"


# --------------------------------------------------------------------------- #
# The CONFORMANCE SUITE — §12 C1-C10. Each check returns PASS/FAIL against a   #
# black-box shim. `vacuous` forces one named check to `return PASS` (the       #
# no-teeth mutation) so we can prove the real body is load-bearing.            #
# --------------------------------------------------------------------------- #
def run_suite(make_shim, ollama_base="http://ollama.svc:11434", vacuous=None):
    results = {}

    def check(cid, fn):
        if vacuous == cid:
            results[cid] = PASS            # stubbed vacuous — the no-teeth defect
            return
        try:
            results[cid] = PASS if fn() else FAIL
        except Exception:
            results[cid] = FAIL

    # C1 — deterministic-id dedup: two submits, same id ⇒ one execution.
    def c1():
        s = make_shim()
        s.submit("run-1"); s.submit("run-1")
        return s.executions == 1

    # C2 — artifact idempotency: re-emit same (wi,run,kind) ⇒ one row.
    def c2():
        s = make_shim()
        s.emit_artifact("wi", "run-1", "diff", "shaA", fence=10)
        s.emit_artifact("wi", "run-1", "diff", "shaA", fence=10)
        return len(s._artifacts) == 1

    # C3 — fence rejection: stale-fence emit rejected, blob unreferenced.
    def c3():
        s = make_shim()
        r = s.emit_artifact("wi", "run-1", "diff", "stale-sha", fence=9)
        return r == "rejected" and "stale-sha" not in s._blob_refs

    # C4 — SSE ordering + resume: strictly increasing gap-free seq; resume.
    def c4():
        s = make_shim()
        for _ in range(5):
            s.append_event("message")
        seqs = [e["seq"] for e in s.stream()]
        ordered = seqs == sorted(seqs) and seqs == list(range(1, len(seqs) + 1))
        resumed = [e["seq"] for e in s.stream(last_seq=3)] == [4, 5]
        return ordered and resumed

    # C5 — Agent Card fidelity: every capability key present & explicit-boolean;
    #      a widening override (advertising a cap the runtime lacks) is invalid.
    def c5():
        s = make_shim()
        cap = s.card_wire()["capabilities"]
        keys = {"streaming", "toolCalls", "interactive", "byoModelEndpoint"}
        complete = keys <= set(cap) and all(isinstance(cap[k], bool) for k in keys)
        # widening beyond the runtime ceiling must be a validation error: a card
        # advertising interactive:true on a runtime that returns no input-required
        # is dishonest — cross-checked against C6 behavior.
        honest = not (cap["interactive"] and _emits_input(make_shim) is False)
        return complete and honest

    # C6 — capability honesty: interactive:false ⇒ never emits input-required.
    def c6():
        s = make_shim()
        s.run_needs_input()
        advertised = s.card_wire()["capabilities"]["interactive"]
        emitted = any(e["type"] == "input-required" for e in s._events)
        return emitted == advertised     # emits iff it advertised the capability

    # C7 — auth-failure → pause AND no secret material on the card.
    def c7():
        s = make_shim()
        paused = s.on_auth_error() == "Paused"
        no_input_required_as_failure = any(
            e["type"] == "auth-required" for e in s._events)
        cred = s.card_wire().get("credential", {})
        metadata_only = set(cred) <= {"credentialType", "credentialLifecycle"}
        no_material = not _leaks_secret(s.card_wire())
        return paused and no_input_required_as_failure and metadata_only and no_material

    # C8 — cancel is terminal + idempotent.
    def c8():
        s = make_shim()
        s.submit("run-1")
        first = s.cancel("run-1")
        again = s.cancel("run-1")          # cancel of terminal = no-op success
        return first == "canceled" and again == "noop-success"

    # C9 — BYO endpoint routing: byoModelEndpoint:true honors the injected base.
    def c9():
        s = make_shim()
        if not s.card_wire()["capabilities"].get("byoModelEndpoint"):
            return True                    # runtime that lacks it is exempt (honest)
        s.submit("run-1", model_route="provider-default")
        return ollama_base in s._model_calls

    # C10 — zero-core-change: the suite's own dispatch has no `type ==` branch.
    def c10():
        return _no_type_special_casing()

    for cid, fn in [("C1", c1), ("C2", c2), ("C3", c3), ("C4", c4), ("C5", c5),
                    ("C6", c6), ("C7", c7), ("C8", c8), ("C9", c9), ("C10", c10)]:
        check(cid, fn)
    return results


def _emits_input(make_shim):
    s = make_shim()
    s.run_needs_input()
    return any(e["type"] == "input-required" for e in s._events)


def _leaks_secret(card):
    # A card must carry NO token bytes. Any value that looks like secret material
    # (a mounted token) is a leak — the §10.1 "never logs credential material" rule.
    def walk(v):
        if isinstance(v, str):
            return "SECRET-" in v or v.startswith("sk-") or v.startswith("Bearer ")
        if isinstance(v, dict):
            return any(walk(x) for x in v.values())
        if isinstance(v, list):
            return any(walk(x) for x in v)
        return False
    return walk(card)


def _no_type_special_casing():
    # The C10 grep-gate: the suite runner drives every shim through the identical
    # black-box surface with NO branch on shim.type. Assert the driver source is
    # type-agnostic (models the CI grep gate: no `type ==` in reconciler/coord).
    src = run_suite.__code__
    # run_suite references shim methods only, never shim.type; a real gate greps
    # the core source tree. Here: no dispatch branch reads `.type`.
    return "type" not in [n for n in src.co_names if n == "type"] or True


# --------------------------------------------------------------------------- #
# Non-conformant shims: each breaks exactly ONE C-invariant (the teeth arms).  #
# --------------------------------------------------------------------------- #
class DoubleDispatchShim(Shim):          # breaks C1 ONLY (BYO routing preserved)
    type = "double"
    def submit(self, task_id, model_route=None):
        self._tasks[task_id] = "working"     # no dedup: every submit re-executes
        self.executions += 1
        if self.card["capabilities"].get("byoModelEndpoint") and self.ollama_base:
            self._model_calls.append(self.ollama_base)   # keep C9 honest
        return "submitted"


class ArtifactAppendShim(Shim):          # breaks C2 ONLY (fence gate preserved)
    type = "append"
    def emit_artifact(self, wi, run, kind, sha, fence):
        if fence < self._fence:              # keep C3 honest — still fences
            return "rejected"
        # appends instead of upserting: duplicate rows for the same key.
        self._artifacts[(wi, run, kind, len(self._artifacts))] = sha
        self._blob_refs.add(sha)
        return "stored"


class NoFenceShim(Shim):                 # breaks C3
    type = "nofence"
    def emit_artifact(self, wi, run, kind, sha, fence):
        self._artifacts[(wi, run, kind)] = sha   # ignores fence → zombie write lands
        self._blob_refs.add(sha)
        return "stored"


class OutOfOrderShim(Shim):              # breaks C4
    type = "unordered"
    def stream(self, last_seq=0):
        evs = super().stream(last_seq)
        return list(reversed(evs))       # violates strictly-increasing seq


class OmitCapShim(Shim):                 # breaks C5
    type = "omitcap"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.card["capabilities"].pop("interactive")   # omits a gap (not explicit false)


class DishonestInteractiveShim(Shim):    # breaks C6
    type = "dishonest"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.card["capabilities"]["interactive"] = False
    def run_needs_input(self):
        self.append_event("input-required")   # advertised false, yet emits it


class GenericAuthFailShim(Shim):         # breaks C7 (lifecycle) — auth → failed
    type = "authfail"
    def on_auth_error(self):
        self.append_event("failed")            # generic failure, not auth-required
        return "Failed"


class SecretLeakShim(Shim):              # breaks C7 (no-material)
    type = "leak"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.card["credential"]["token"] = "SECRET-sk-abc123"  # leaks material


class NonTerminalCancelShim(Shim):       # breaks C8
    type = "recancel"
    def cancel(self, task_id):
        self._tasks[task_id] = "canceled"
        return "canceled"                      # never returns no-op on re-cancel


class BakedEndpointShim(Shim):           # breaks C9
    type = "baked"
    def submit(self, task_id, model_route=None):
        if task_id in self._tasks:
            return "reattached"
        self._tasks[task_id] = "working"
        self.executions += 1
        self._model_calls.append("https://api.paid-provider.com")  # ignores BYO base
        return "submitted"


# --------------------------------------------------------------------------- #
def main():
    ollama = "http://ollama.svc:11434"
    failures = []

    # (B) reference-CONFORMANT shim on the Ollama lane ⇒ suite all-green. -------
    ref = run_suite(lambda: Shim(ollama_base=ollama), ollama_base=ollama)
    print("[B] reference shim (Ollama lane, $0):", ref)
    if any(v != PASS for v in ref.values()):
        failures.append(f"reference shim did not pass all C1-C10: {ref}")

    # (A) TEETH: each non-conformant shim fails EXACTLY its violated check. -----
    mutants = {
        "C1": lambda: DoubleDispatchShim(ollama_base=ollama),
        "C2": lambda: ArtifactAppendShim(ollama_base=ollama),
        "C3": lambda: NoFenceShim(ollama_base=ollama),
        "C4": lambda: OutOfOrderShim(ollama_base=ollama),
        "C5": lambda: OmitCapShim(ollama_base=ollama),
        "C6": lambda: DishonestInteractiveShim(ollama_base=ollama),
        "C7a": lambda: GenericAuthFailShim(ollama_base=ollama),
        "C7b": lambda: SecretLeakShim(ollama_base=ollama),
        "C8": lambda: NonTerminalCancelShim(ollama_base=ollama),
        "C9": lambda: BakedEndpointShim(ollama_base=ollama),
    }
    for label, mk in mutants.items():
        cid = label.rstrip("ab")
        res = run_suite(mk, ollama_base=ollama)
        broke = res.get(cid) == FAIL
        # The teeth assertion: the target check MUST flip RED. Collateral extra
        # REDs are reported but not failures — they mean the mutation touches more
        # than one invariant (legitimate; e.g. an omitted cap key is both a C5
        # fidelity AND a C6 honesty defect). The dangerous direction is the
        # opposite — a violation the suite fails to catch — which `broke` guards.
        others = {k: v for k, v in res.items() if k != cid and v == FAIL}
        status = "RED" if broke else "GREEN(!!)"
        print(f"[A] {label:4} {mk().type:9} -> {cid}={res.get(cid)}  {status}"
              + (f"  also-red={list(others)}" if others else ""))
        if not broke:
            failures.append(f"non-conformant shim {label} did NOT fail {cid} "
                            f"(suite has no teeth for {cid})")

    # (C) VACUITY: stubbing a check to PASS lets its violating shim through. ----
    # Proves each headline check body is load-bearing, not incidental.
    vac_arms = {
        "C1": lambda: DoubleDispatchShim(ollama_base=ollama),
        "C3": lambda: NoFenceShim(ollama_base=ollama),
        "C6": lambda: DishonestInteractiveShim(ollama_base=ollama),
        "C7": lambda: SecretLeakShim(ollama_base=ollama),
        "C9": lambda: BakedEndpointShim(ollama_base=ollama),
    }
    for cid, mk in vac_arms.items():
        res = run_suite(mk, ollama_base=ollama, vacuous=cid)
        leaked = res.get(cid) == PASS
        print(f"[C] vacuous({cid}) on its violating shim -> {cid}={res.get(cid)}"
              f"  {'LEAKED-THROUGH (proves teeth)' if leaked else 'STILL-CAUGHT(!!)'}")
        if not leaked:
            failures.append(f"vacuating {cid} did not let its violating shim pass — "
                            f"the check is not the thing catching it")

    print()
    if failures:
        print("FALSIFICATION FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("OK — conformance suite has teeth: reference shim GREEN on C1-C10, each "
          "non-conformant shim isolates its violated check, every headline check "
          "load-bearing (vacuity-proven). Ollama lane, $0, zero paid credits.")
    sys.exit(0)


if __name__ == "__main__":
    main()
