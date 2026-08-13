#!/usr/bin/env python3
"""opencode-shim-check.py — Story 5.8 falsification (the `opencode` runtime shim, v1).

Story 5.8 ships the CONCRETE `opencode` runtime shim (`shims/opencode`), the third member of the
v1 shim set {OpenClaw, Hermes, opencode} pulled forward from Phase 2 (CEO 2026-08-11, ADR-026 /
§10.1). Where Story 5.7 (byo-model-endpoint-check.py) owns the CONTROL-PLANE model-endpoint SEAM
(resolve an Agent → an ordinary runtime + a Secret-resolved base-URL), THIS story owns the RUNTIME
that actually speaks the wire: opencode drives a REAL A2A Run against a local Ollama model via its
OpenAI-compatible provider (`baseURL …:11434/v1`) with ZERO paid credential, passes the conformance
Ollama lane (Story 5.6 / ISI-2114), AND runs paid providers unchanged (the endpoint is config, not
baked in). Five cruxes make the SHIM real rather than a re-skin or a facade:

  (O) OLLAMA OVER THE OpenAI-COMPATIBLE WIRE, $0 (AC1, §10.3). Given a resolved Ollama endpoint
      (`http://…:11434/v1`) + model, the opencode shim DIALS THAT endpoint over the
      OpenAI-compatible wire with NO paid credential in the request path — the ISI-2157 "$0 CI
      lane" claim. A naive shim silently routes the local Run to a paid vendor and/or attaches a
      paid API key — spending credits the Ollama lane exists to avoid.
  (P) PAID PROVIDER UNCHANGED — ONE SHIM, ENDPOINT IS CONFIG (AC2). The SAME opencode shim runs a
      PAID-provider Agent by swapping ONLY the resolved endpoint+token config — no `opencode`
      variant, no second image, no Ollama-only internal path. A naive shim special-cases Ollama vs
      paid so only one route works (the "runs paid providers unchanged" claim broken).
  (V) SIX-VERB A2A CONTRACT, A REAL RUN, NO FACADE, NO CORE BRANCH (AC1, S6 / §10.1 / C10). A
      SubmitTask drives a genuine opencode run lifecycle → SSE progress → EmitArtifact
      (task-in → run → artifacts-out), each artifact stamped `produced_by == "opencode"`, driven by
      the runtime-agnostic Story-5.1 client with NO `type:opencode` branch in the core. A naive
      FACADE forwards SubmitTask to another runtime's gateway (openclaw/hermes/a paid vendor) so
      opencode never actually executes — the artifact stamp collapses to the other runtime.
  (H) HONEST CARD THAT ACTUALLY HONORS THE OVERRIDE (AC1, FR-D4 / §10.1). opencode's OWN Agent Card
      advertises `byoModelEndpoint:true`, and a BYO submit REALLY dials the resolved override
      base-URL — the capability is not a lie. A naive shim advertises the flag TRUE but ignores the
      override and dials a BAKED-IN host: a silent mid-Run failure on a model it claimed to honor
      (the §10.3 *Honesty* violation).
  (G) THE CONFORMANCE OLLAMA LANE IS THE SHIP-GATE — WITH TEETH (AC1/AC2, C1–C10 / Story 5.6). The
      Ollama lane passes the shim ONLY on real evidence: a Run executed BY opencode, artifacts were
      produced, and ZERO paid credits were spent. A naive lane reports "pass" WITHOUT asserting the
      Run executed / artifacts exist / no paid credential was used — a VACUOUS green (the
      ISI-2346-F1 / ISI-2218-F1 teeth-loss pattern) that would rubber-stamp a shim that never ran.

Differential falsification (same discipline as byo-model-endpoint-check.py /
two-runtimes-one-squad-check.py / conformance-suite-check.py): each property runs a NAIVE/cheating
design that MUST break (teeth) alongside the conformant design that MUST hold. AND each conformant
invariant is MUTATION-PROVEN: `--mutate=<O|P|V|H|G>` injects the corresponding bug into the
CONFORMANT path and the check goes RED (exit 1), so no invariant is vacuous. Baseline
`python3 opencode-shim-check.py` exits 0; each `--mutate=NAME` exits 1.

Models the shim's submit/stream/artifact surface in-process; real-runtime promotion rides the
ISI-2114 conformance Ollama lane (§12, Story 5.6) — a live `opencode` container against a real
`ollama serve` (`ollama launch opencode`), task-in → run → artifacts-out at $0 — the §21 gate that
lets the "opencode ran a real Run against a local model" claim be *proven*.
"""
import sys


# ---- which conformant invariant to sabotage (mutation-proof harness). Empty = baseline. ----
MUTATE = ""


def mut(name):
    """True iff we are injecting the `name` bug into the conformant path (verifies teeth)."""
    return MUTATE == name


# The v1 runtime-type registry (§10.1). opencode is a first-class member alongside OpenClaw/Hermes;
# Ollama is DELIBERATELY absent — it is the model backend opencode DIALS, not a runtime (ADR-026,
# Story 5.7). One image per type; the endpoint the image is pointed at is config.
V1_RUNTIME_TYPES = ("opencode", "openclaw", "hermes")
OPENCODE_IMAGE = "ghcr.io/ksquad/shims/opencode:v1"


class CapabilityFailure(Exception):
    """A byoModelEndpoint gap surfaced mid-Run — the (H) leak reintroduces (should be pre-declared)."""


# ============================================================================================
# A resolved dispatch target (produced by the Story-5.7 control-plane resolver). The shim treats
# base_url as CONFIG: an Ollama `…:11434/v1` or a paid vendor URL, whichever was resolved.
# ============================================================================================

class DispatchTarget:
    def __init__(self, base_url, model, token=None, token_is_paid=False):
        self.base_url = base_url            # OpenAI-compatible base-URL the shim must dial
        self.model = model                  # e.g. "qwen3" (Ollama) or "claude-sonnet-5" (paid)
        self.token = token                  # None for a keyless local Ollama endpoint
        self.token_is_paid = token_is_paid  # True iff `token` is a metered paid-vendor credential


class Artifact:
    """A run output. `produced_by` is stamped with the runtime that ACTUALLY executed (S6 / §10.1) —
    a facade would stamp the runtime it forwarded to, never `opencode`."""

    def __init__(self, kind, sha, produced_by):
        self.kind = kind
        self.sha = sha
        self.produced_by = produced_by


class RunResult:
    def __init__(self, executed_by, artifacts, events, dialed, paid_credentials_used):
        self.executed_by = executed_by                    # the runtime that ran the lifecycle
        self.artifacts = artifacts                        # EmitArtifact outputs (task-in→artifacts-out)
        self.events = events                              # SSE progress stream (monotonic seq)
        self.dialed = dialed                              # base-URLs the provider actually called
        self.paid_credentials_used = paid_credentials_used  # metered tokens spent this Run


# ============================================================================================
# The `opencode` shim (shims/opencode). Implements the six A2A MUST-verbs itself and translates to
# opencode-native execution over an OpenAI-compatible provider. The naive flags below model the
# leaks each mutation injects.
# ============================================================================================

class OpenCodeShim:
    runtime_type = "opencode"

    def __init__(self, facade_to=None, baked_url=None, ollama_only=False):
        # facade_to != None → (V) NAIVE: forward SubmitTask to another runtime's gateway (fake run).
        self.facade_to = facade_to
        # baked_url != None → (H) NAIVE: ignore the resolved override, dial a compiled-in host.
        self.baked_url = baked_url
        # ollama_only → (P) NAIVE: an Ollama-only internal path that breaks a paid-provider Agent.
        self.ollama_only = ollama_only

    # V6 GetAgentCard (§6) — opencode's OWN honest card. byoModelEndpoint:true (it accepts an
    # OpenAI-compatible base-URL override); credentials are metadata only, never material (C7).
    def card(self):
        return {
            "runtimeType": "opencode",
            "capabilities": {
                "byoModelEndpoint": True,     # honest: opencode natively accepts a base-URL override
                "interactive": False,
                "streaming": True,
            },
            "credentialLifecycle": "static",  # BYO endpoint token is static (no vendor OAuth)
        }

    # V1 SubmitTask + V2 StreamEvents + V5 EmitArtifact — a REAL opencode run lifecycle. Returns a
    # RunResult stamped with the runtime that actually executed.
    def submit(self, task_id, target):
        # (V) facade: forward to another runtime's gateway. THAT runtime executes — not opencode.
        if self.facade_to is not None:
            return self.facade_to.submit(task_id, target)

        # (P) an Ollama-only shim cannot run a paid-provider Agent (the "unchanged" claim broken).
        if self.ollama_only and target.token_is_paid:
            raise ValueError("opencode shim special-cased to Ollama-only — paid provider unsupported")

        # Provider selection over the OpenAI-compatible wire: dial the RESOLVED base-URL (config).
        base = self.baked_url if self.baked_url is not None else target.base_url  # (H) baked ⇒ ignore override

        dialed = [base]
        paid_used = []
        # $0 discipline: a keyless local Ollama endpoint spends no paid credential. Only a metered
        # paid token counts against the $0 lane.
        if target.token is not None and target.token_is_paid:
            paid_used.append(target.token)

        # translate to opencode-native execution → SSE progress → a real artifact stamped 'opencode'.
        events = [{"seq": 0, "type": "run.started"},
                  {"seq": 1, "type": "run.progress"},
                  {"seq": 2, "type": "run.completed"}]
        artifacts = [Artifact("diff", f"sha-{task_id}", produced_by="opencode")]
        return RunResult("opencode", artifacts, events, dialed, paid_used)


# ============================================================================================
# The runtime-agnostic core dispatch client (Story 5.1, internal/a2a). It drives ANY shim through
# the identical six-verb surface and MUST NOT branch on shim.runtime_type (C10, zero-core-change).
# ============================================================================================

def core_dispatch(shim, task_id, target):
    """C10: drive the shim as a black box. No `if shim.runtime_type == 'opencode'` anywhere."""
    return shim.submit(task_id, target)


def host_of(base_url):
    return base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


# ============================================================================================
# Fixtures — a local Ollama target (keyless, `…:11434/v1`) and a paid-provider target (metered key).
# ============================================================================================

def _ollama_target():
    return DispatchTarget("http://ollama.alice.svc.cluster.local:11434/v1", "qwen3",
                          token=None, token_is_paid=False)


def _paid_target():
    return DispatchTarget("https://api.anthropic-proxy.acme/v1", "claude-sonnet-5",
                          token="sk-bob-PAID", token_is_paid=True)


# ============================================================================================
# Scenarios.
# ============================================================================================

def run_ollama_zero_cost_wire():
    """(O) AC1/§10.3: the opencode shim dials the RESOLVED Ollama `…:11434/v1` endpoint over the
    OpenAI-compatible wire and spends NO paid credential. The naive arm routes the local Run to a
    paid vendor + attaches a paid key."""
    shim = OpenCodeShim()
    if mut("O"):
        # naive: route the Ollama Run to a paid vendor AND attach a paid key ($0 lane violated).
        target = DispatchTarget("https://api.paid-vendor.example/v1", "qwen3",
                                token="sk-LEAKED-PAID", token_is_paid=True)
    else:
        target = _ollama_target()

    r = core_dispatch(shim, "wi-1", target)
    dialed_host = host_of(r.dialed[0])
    return {
        "executed_by": r.executed_by,
        "dialed_ollama": dialed_host.startswith("ollama.") or dialed_host == "127.0.0.1",
        "dialed_port_11434": ":11434/" in r.dialed[0],
        "paid_credits_spent": len(r.paid_credentials_used),
        "dialed": r.dialed[0],
    }


def run_paid_provider_unchanged():
    """(P) AC2: the SAME opencode shim runs a PAID-provider Agent by config alone — one shim, the
    endpoint is config. The naive Ollama-only shim breaks the paid Run."""
    conformant = OpenCodeShim(ollama_only=mut("P"))   # mutation makes the conformant shim Ollama-only

    ollama = core_dispatch(conformant, "wi-ollama", _ollama_target())

    paid_ok = True
    paid_dialed = None
    try:
        paid = core_dispatch(conformant, "wi-paid", _paid_target())
        paid_dialed = paid.dialed[0]
    except ValueError:
        paid_ok = False

    return {
        "ollama_ran": ollama.executed_by == "opencode",
        "paid_ran": paid_ok,
        "same_shim": True,                              # one instance drove both routes
        "paid_dialed": paid_dialed,
    }


def run_six_verb_real_run_no_facade():
    """(V) AC1/S6/§10.1/C10: SubmitTask → run lifecycle → SSE → artifacts, stamped `opencode`,
    driven by the runtime-agnostic client with NO core type-branch. The naive facade forwards to
    another runtime's gateway → the artifact stamp collapses to that runtime."""
    # a real second runtime the facade could forward to (its artifacts stamp 'openclaw').
    class OpenClawShim:
        runtime_type = "openclaw"

        def submit(self, task_id, target):
            return RunResult("openclaw", [Artifact("diff", f"oc-{task_id}", "openclaw")],
                             [{"seq": 0, "type": "run.started"}], [target.base_url], [])

    shim = OpenCodeShim(facade_to=OpenClawShim() if mut("V") else None)
    r = core_dispatch(shim, "wi-2", _ollama_target())
    stamps = {a.produced_by for a in r.artifacts}
    return {
        "executed_by": r.executed_by,
        "artifact_stamps": sorted(stamps),
        "sse_monotonic": [e["seq"] for e in r.events] == sorted(e["seq"] for e in r.events),
        "produced_artifacts": len(r.artifacts),
    }


def run_honest_card_honors_override():
    """(H) AC1/FR-D4/§10.1: opencode's card advertises byoModelEndpoint:true AND a BYO submit REALLY
    dials the resolved override base-URL. The naive shim advertises true but ignores the override,
    dialing a baked-in host — a silent mid-Run failure on a capability it claimed."""
    baked = "https://api.baked-vendor.example/v1"
    shim = OpenCodeShim(baked_url=baked if mut("H") else None)

    card = shim.card()
    advertises = card["capabilities"]["byoModelEndpoint"]

    target = _ollama_target()
    r = core_dispatch(shim, "wi-3", target)
    dialed = r.dialed[0]
    honored = host_of(dialed) == host_of(target.base_url)

    # honesty cross-check: advertising the flag but NOT honoring the override is dishonest.
    dishonest = advertises and not honored
    return {"advertises": advertises, "honored_override": honored,
            "dialed": dialed, "dishonest": dishonest}


def conformance_ollama_lane(shim, target, *, teeth=True):
    """The Story 5.6 / ISI-2114 Ollama lane distilled to its ship-gate assertion: PASS iff a Run
    executed BY opencode, artifacts were produced, SSE progressed, and ZERO paid credits were spent.
    `teeth=False` (the G mutation) guts the evidence checks → a vacuous green."""
    r = core_dispatch(shim, "lane-wi", target)
    if not teeth:
        return True                                     # (G) NAIVE: rubber-stamp without evidence
    executed = r.executed_by == "opencode"
    produced = len(r.artifacts) >= 1 and all(a.produced_by == "opencode" for a in r.artifacts)
    progressed = len(r.events) >= 1
    zero_paid = len(r.paid_credentials_used) == 0
    return executed and produced and progressed and zero_paid


def run_conformance_lane_has_teeth():
    """(G) AC1/AC2/Story 5.6: the Ollama lane passes the REAL shim and — crucially — FAILS a
    cheating shim that never really ran (no artifacts) or spent a paid credit. The naive lane
    (teeth off) rubber-stamps the cheat."""
    teeth = not mut("G")

    # real shim on the Ollama target → the lane passes.
    real_pass = conformance_ollama_lane(OpenCodeShim(), _ollama_target(), teeth=teeth)

    # a cheating shim that produces NO artifacts (never really executed a Run).
    class VacuousShim:
        runtime_type = "opencode"

        def submit(self, task_id, target):
            return RunResult("opencode", [], [], [target.base_url], [])  # nothing produced

    lane_fails_on_vacuous = not conformance_ollama_lane(VacuousShim(), _ollama_target(), teeth=teeth)

    # a shim that spent a paid credit on the "$0" lane must also fail.
    lane_fails_on_paid = not conformance_ollama_lane(
        OpenCodeShim(), _paid_target(), teeth=teeth)      # paid target ⇒ paid credit spent

    return {"real_pass": real_pass,
            "lane_fails_on_vacuous": lane_fails_on_vacuous,
            "lane_fails_on_paid": lane_fails_on_paid}


# ============================================================================================
# Driver.
# ============================================================================================

def main():
    print("[model] Story 5.8 opencode runtime shim — real A2A Run vs local Ollama ($0), paid "
          "unchanged" + (f"  [MUTATE={MUTATE}]" if MUTATE else "") + "\n")

    # (O) Ollama over the OpenAI-compatible wire, $0.
    o = run_ollama_zero_cost_wire()
    print(f"[model] (O) AC1  (Ollama over OpenAI-compatible wire, $0): {o}")
    assert o["executed_by"] == "opencode", "the opencode shim must execute the local Run itself"
    assert o["dialed_ollama"] and o["dialed_port_11434"], \
        "the shim must dial the RESOLVED Ollama `…:11434/v1` endpoint over the OpenAI-compatible wire"
    assert o["paid_credits_spent"] == 0, \
        "TEETH LOST: a local Ollama Run must spend ZERO paid credentials (ISI-2157 $0 lane)"
    print("[model]        → opencode dials the local Ollama endpoint at $0; the naive arm routes the "
          "Run to a paid vendor and spends a credential\n")

    # (P) paid provider unchanged — one shim, endpoint is config.
    p = run_paid_provider_unchanged()
    print(f"[model] (P) AC2  (paid provider unchanged, one shim): {p}")
    assert p["ollama_ran"], "the opencode shim must run the Ollama Agent"
    assert p["paid_ran"], \
        "TEETH LOST: the SAME opencode shim must run a PAID-provider Agent by config (endpoint is config)"
    print("[model]        → one opencode shim retargets Ollama vs a paid provider by config alone; the "
          "Ollama-only naive shim breaks the paid Run\n")

    # (V) six-verb real Run, no facade, no core branch.
    v = run_six_verb_real_run_no_facade()
    print(f"[model] (V) AC1  (six-verb real Run, no facade, C10): {v}")
    assert v["executed_by"] == "opencode" and v["artifact_stamps"] == ["opencode"], \
        "the Run must be executed BY opencode — a facade forwarding elsewhere collapses the stamp"
    assert v["produced_artifacts"] >= 1 and v["sse_monotonic"], \
        "task-in → run → artifacts-out with monotonic SSE progress must hold"
    print("[model]        → opencode runs a real lifecycle and stamps its own artifacts; the facade "
          "forwards to another runtime's gateway so opencode never actually executes\n")

    # (H) honest card that actually honors the override.
    h = run_honest_card_honors_override()
    print(f"[model] (H) AC1  (honest card honors the override, FR-D4): {h}")
    assert h["advertises"], "opencode's card must advertise byoModelEndpoint:true"
    assert h["honored_override"] and not h["dishonest"], \
        "TEETH LOST: advertising byoModelEndpoint but dialing a baked-in host is a dishonest capability"
    print("[model]        → opencode advertises byoModelEndpoint AND dials the resolved override; the "
          "naive shim claims the flag but ignores the override (silent mid-Run failure)\n")

    # (G) conformance Ollama lane is the ship-gate — with teeth.
    g = run_conformance_lane_has_teeth()
    print(f"[model] (G) AC1/AC2  (conformance Ollama lane ship-gate, teeth): {g}")
    assert g["real_pass"], "the real opencode shim must PASS the conformance Ollama lane"
    assert g["lane_fails_on_vacuous"], \
        "TEETH LOST: the lane must FAIL a shim that produced no artifacts (vacuous green, ISI-2346-F1)"
    assert g["lane_fails_on_paid"], \
        "TEETH LOST: the $0 lane must FAIL a shim that spent a paid credential"
    print("[model]        → the lane passes only on real evidence (a Run executed, artifacts produced, "
          "$0); the naive lane rubber-stamps a shim that never ran\n")

    print("[model] PASS — the opencode shim is a real v1 runtime: it dials a local Ollama endpoint "
          "over the OpenAI-compatible wire at $0 (O), runs paid providers unchanged from one image "
          "(P), executes a genuine six-verb Run with no facade and no core branch (V), advertises a "
          "capability it actually honors (H), and passes a conformance Ollama lane that has teeth "
          "(G). Every naive design detectably breaks.")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg.startswith("--mutate="):
            MUTATE = arg.split("=", 1)[1]
    main()
