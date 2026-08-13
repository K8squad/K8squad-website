#!/usr/bin/env python3
"""byo-model-endpoint-check.py — Story 5.7 falsification (BYO Ollama / model-endpoint seam).

The §10.3 / ADR-026 / FR-D4 load-bearing invariant: an `Agent` targets a BYO model endpoint
(its own Ollama / any OpenAI-compatible server) via a per-user `modelEndpointRef` Secret + a
per-`Agent` `model` — and this rides the EXISTING shim seam as a MODEL-ENDPOINT OVERRIDE consumed
by any runtime advertising the `byoModelEndpoint` capability. It is NOT a new `AgentRuntime.type`,
NOT a new image, and touches ZERO core code. The model axis (§10.3) is orthogonal to the
agent-runtime axis (§5.3/§10.1): treating "Ollama" as an `AgentRuntime.type` is the category error
ADR-026 forbids. Five cruxes make the seam real rather than a re-skin:

  (M) MODEL≠RUNTIME AXIS (AC1, ADR-026 — THE moat). BYO Ollama enters as `Agent.spec.model` +
      an endpoint resolved from `modelEndpointRef`, consumed by a `byoModelEndpoint`-capable
      runtime (`opencode` by default, Story 5.8). The runtime-type registry gains NO `ollama`
      entry, no new image is built, and the core dispatch path is unchanged. A naive design
      registers `type: ollama` (or requires a new image) — a new runtime surface where the
      architecture says there is only a model-endpoint override.
  (W) OPENAI-COMPATIBLE WIRE, ENDPOINT IS CONFIG (AC2). The resolved runtime rides the
      OpenAI-compatible wire to the endpoint resolved from the Secret; the SAME runtime image
      retargets a paid provider by swapping ONLY the endpoint config (the endpoint is not baked
      in). A naive shim hardcodes its base-URL, so the Ollama Agent and the paid-provider Agent —
      same image — reach the SAME (wrong) endpoint; retargeting would need a new image.
  (N) CAPABILITY-NEGOTIATED + HONEST GAP (AC3, FR-D4/§10.1). A runtime advertises
      `byoModelEndpoint` on its Agent Card; the core routes the endpoint+model only to a runtime
      that advertises it, and routes a BYO-endpoint Agent AROUND a runtime that does NOT
      (pre-dispatch, Story 5.2) — never dispatch-then-fail silently mid-Run on a weak local model.
      A naive core assumes every runtime is byoModelEndpoint-capable → dispatches to a fixed-vendor
      runtime that cannot retarget → mid-Run failure.
  (C) CREDENTIAL LOCK REINFORCED (AC4, §11 third story / FR-G1). The endpoint URL (+ optional
      token) is a PER-USER Secret ref (`modelEndpointRef`); there is no shared platform endpoint
      and no shared master credential. A naive design falls back to a shared platform endpoint
      when the ref is absent → both Agents draw the same platform endpoint (the vendor-lock §11
      forbids, reopened on the model axis).
  (E) EGRESS ALLOWLISTED, DEFAULT-DENY HOLDS (AC4, §12.2). The BYO endpoint host joins the Team
      NetworkPolicy model-endpoint allowlist; default-deny still holds, so an un-allowlisted host
      is BLOCKED. A naive design opens egress (allow-all) so the endpoint "just works" — turning
      the BYO seam into an exfil hole around the §12.2 default-deny.

Differential falsification (same discipline as two-runtimes-one-squad-check.py /
southbound-a2a-check.py): each property runs a NAIVE/cheating design that MUST break (teeth)
alongside the conformant design that MUST hold. AND each conformant invariant is MUTATION-PROVEN:
`--mutate=<M|W|N|C|E>` injects the corresponding bug into the CONFORMANT path and the check goes
RED (exit 1), so no invariant is vacuous. Baseline `python3 byo-model-endpoint-check.py` exits 0;
each `--mutate=NAME` exits 1.

Models the resolve/dispatch/egress seam in-process; real-runtime promotion rides the ISI-2114
conformance Ollama lane (§12, Story 5.6) — task-in → run → artifacts-out against an Ollama endpoint
with zero paid credentials — the §21 gate that lets the BYO-Ollama claim be *proven*.
"""
import json
import sys


# ---- which conformant invariant to sabotage (mutation-proof harness). Empty = baseline. ----
MUTATE = ""


def mut(name):
    """True iff we are injecting the `name` bug into the conformant path (verifies teeth)."""
    return MUTATE == name


# The v1 runtime-type registry (§10.1, Story 5.5/5.8). Ollama is DELIBERATELY absent — it is a
# model backend, not a runtime type (ADR-026). A design that adds it here has committed the
# category error.
V1_RUNTIME_TYPES = ("opencode", "openclaw", "hermes")

# Runtime images are keyed by `type` ONLY — never by the model endpoint. Same type ⇒ same image,
# whatever endpoint it is pointed at (that is the whole "no new image" claim).
RUNTIME_IMAGES = {
    "opencode": "ghcr.io/ksquad/shims/opencode:v1",
    "openclaw": "ghcr.io/ksquad/shims/openclaw:v1",
    "hermes":   "ghcr.io/ksquad/shims/hermes:v1",
}


class CapabilityFailure(Exception):
    """A model-endpoint capability gap discovered at dispatch time — the leak (N) reintroduces."""


class EgressBlocked(Exception):
    """Default-deny egress rejected a host not on the model-endpoint allowlist (§12.2)."""


# ============================================================================================
# Per-user Secrets — `modelEndpointRef` resolves an endpoint URL (+ optional token). MATERIAL is
# never inlined on the Agent spec and never a shared platform default (§11 third story, FR-G1).
# ============================================================================================

class SecretStore:
    def __init__(self):
        self._rows = {}   # secret_name -> {"owner": principal, "endpoint": url, "token": str|None}

    def put(self, name, owner, endpoint, token=None):
        self._rows[name] = {"owner": owner, "endpoint": endpoint, "token": token}
        return self

    def resolve(self, secret_name, requesting_principal):
        """Resolve a per-user endpoint Secret. A cross-principal read is rejected (§9.1); a
        'platform'-owned row models the naive shared default."""
        row = self._rows[secret_name]
        if row["owner"] != requesting_principal and row["owner"] != "platform":
            raise PermissionError(
                f"{requesting_principal} may not read Secret owned by {row['owner']} (§9.1)")
        return row["endpoint"], row["token"]


# ============================================================================================
# Agent / AgentCard / resolved dispatch target.
# ============================================================================================

class AgentCard:
    """A runtime's OWN honest card (Story 5.2). `byoModelEndpoint` is a first-class capability
    flag (FR-D4): a runtime that can accept an OpenAI-compatible base-URL override advertises it;
    one that only speaks a fixed vendor endpoint does NOT."""

    def __init__(self, runtime_type, byo_model_endpoint):
        self.runtimeType = runtime_type
        self.capabilities = {"byoModelEndpoint": bool(byo_model_endpoint)}


class Agent:
    """An `Agent` CRD (§5.1). BYO Ollama is expressed as `model` + `modelEndpointRef` — NOT as a
    special runtime. `runtimeRef` still names an ordinary runtime type (opencode by default)."""

    def __init__(self, name, principal, runtime_type, model, model_endpoint_ref):
        self.name = name
        self.principal = principal              # the BYO-credential / metering principal (§11)
        self.runtimeRef = runtime_type          # an ordinary AgentRuntime.type (opencode/…)
        self.model = model                      # e.g. "qwen3", "llama3", or "claude-sonnet-…"
        self.modelEndpointRef = model_endpoint_ref  # per-user Secret ref → endpoint URL (+ token)


class DispatchTarget:
    """What the resolver hands the SAME core dispatch path — image is type-keyed, the endpoint is
    resolved config layered on top. The core reads these fields identically for every Agent."""

    def __init__(self, runtime_type, image, base_url, model, token):
        self.runtime_type = runtime_type
        self.image = image
        self.base_url = base_url                # the OpenAI-compatible base-URL the shim will call
        self.model = model
        self.token = token


# ============================================================================================
# The resolver (control-plane) — turns an Agent into a DispatchTarget. The conformant resolver
# NEVER invents a runtime type from the model and NEVER bakes an endpoint into the image.
# ============================================================================================

def resolve(agent, secrets, *, runtime_registry, cards):
    """Resolve an Agent to a DispatchTarget. Records nothing model-specific in the runtime
    registry: BYO Ollama is a model-endpoint override, not a runtime."""
    rtype = agent.runtimeRef

    # (M) mutation / naive category error: synthesise a runtime type from the model backend.
    if mut("M"):
        rtype = "ollama"                        # the forbidden ADR-026 category error
        runtime_registry.append("ollama")       # a new runtime surface where there is none
        RUNTIME_IMAGES.setdefault("ollama", "ghcr.io/ksquad/shims/ollama:v1")  # a new image

    if rtype not in runtime_registry:
        raise ValueError(f"unknown AgentRuntime.type {rtype!r} (Ollama is a model backend, "
                         f"not a runtime type — ADR-026)")

    card = cards[rtype]

    # (N) capability negotiation: a BYO-endpoint Agent may only be resolved onto a runtime that
    # advertises `byoModelEndpoint`. The core routes AROUND a runtime that does not (pre-dispatch).
    needs_byo = agent.modelEndpointRef is not None
    capable = card.capabilities["byoModelEndpoint"]
    if mut("N"):
        capable = True                          # assume every runtime is byo-capable (the leak)
    if needs_byo and not capable:
        # conformant: this is caught PRE-DISPATCH → the Agent is routed around this runtime.
        raise CapabilityFailure(
            f"runtime {rtype!r} does not advertise byoModelEndpoint — route around (Story 5.2)")

    # Resolve the endpoint. Conformant: from the per-user Secret ref ONLY (§11).
    if mut("C"):
        # (C) mutation / naive: ignore the per-user ref and draw a SHARED platform endpoint —
        # collapsing every Agent onto one master (the vendor-lock §11 forbids on the model axis).
        base_url, token = secrets.resolve("platform-default", "platform")
    elif agent.modelEndpointRef is not None:
        base_url, token = secrets.resolve(agent.modelEndpointRef, agent.principal)
    else:
        base_url, token = None, None            # a non-BYO Agent uses the runtime's built-in default

    # Image is keyed by TYPE only — the endpoint never changes the image (the "no new image" claim).
    image = RUNTIME_IMAGES[rtype]

    # (W) mutation / naive: bake a fixed base-URL into the shim, ignoring the resolved endpoint.
    if mut("W"):
        base_url = "https://api.openai.example/v1"   # hardcoded — cannot be retargeted

    return DispatchTarget(rtype, image, base_url, agent.model, token)


# ============================================================================================
# The Team NetworkPolicy — default-deny egress + a model-endpoint allowlist (§12.2). The BYO
# endpoint host must be ADDED to the allowlist; everything else stays blocked.
# ============================================================================================

class TeamEgress:
    def __init__(self, allow_all=False):
        self.allow_all = allow_all              # naive: default-allow (the exfil hole)
        self._allow_hosts = set()               # the model-endpoint allowlist (§12.2)

    def allowlist(self, host):
        self._allow_hosts.add(host)
        return self

    def dial(self, host):
        """Simulate an egress attempt under default-deny."""
        if self.allow_all or mut("E"):
            return True                          # default-allow — every host reachable (the leak)
        if host not in self._allow_hosts:
            raise EgressBlocked(f"egress to {host!r} blocked — not on model-endpoint allowlist (§12.2)")
        return True


def host_of(base_url):
    # tiny stdlib-only host extractor (avoid urllib import churn) — "scheme://host:port/…" → host.
    return base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


# ============================================================================================
# Fixtures — one squad, an Ollama-backed opencode Agent and a paid-provider opencode Agent, plus
# a fixed-vendor runtime that does NOT advertise byoModelEndpoint.
# ============================================================================================

def _cards():
    return {
        # opencode advertises byoModelEndpoint (native OpenAI-compatible provider, Story 5.8).
        "opencode": AgentCard("opencode", byo_model_endpoint=True),
        "openclaw": AgentCard("openclaw", byo_model_endpoint=True),
        "hermes":   AgentCard("hermes",   byo_model_endpoint=True),
        # a hypothetical runtime that only speaks a fixed vendor endpoint — honestly advertises NO.
        "fixedvendor": AgentCard("fixedvendor", byo_model_endpoint=False),
    }


def _secrets():
    return (SecretStore()
            # each Agent's own per-user endpoint Secret (§11 third story).
            .put("ep-ollama-alice", "alice", "http://ollama.alice.svc.cluster.local:11434/v1", token=None)
            .put("ep-paid-bob", "bob", "https://api.anthropic-proxy.acme/v1", token="sk-bob-PAID")
            # the naive shared platform default (only reachable via the C mutation).
            .put("platform-default", "platform", "https://models.platform.internal/v1", token="MASTER"))


# ============================================================================================
# Scenarios.
# ============================================================================================

def run_model_not_runtime_axis():
    """(M) AC1/ADR-026: a BYO-Ollama Agent resolves onto an ORDINARY runtime (opencode) with a
    model-endpoint override — the runtime registry gains no `ollama` type and no new image. The
    naive category error registers `type: ollama` and builds a new image."""
    registry = list(V1_RUNTIME_TYPES)
    cards = _cards()
    secrets = _secrets()
    agent = Agent("alice-ollama", "alice", "opencode", "qwen3", "ep-ollama-alice")

    tgt = resolve(agent, secrets, runtime_registry=registry, cards=cards)

    return {
        "resolved_type": tgt.runtime_type,                 # conformant: opencode (an existing type)
        "image": tgt.image,                                # conformant: the existing opencode image
        "registry_has_ollama": "ollama" in registry,       # conformant: False (no new type)
        "new_image_built": tgt.image not in RUNTIME_IMAGES.values() or "ollama" in RUNTIME_IMAGES,
        "reached_endpoint": tgt.base_url,
    }


def run_openai_wire_endpoint_is_config():
    """(W) AC2: the SAME opencode image retargets by CONFIG — the Ollama Agent and the paid Agent
    reach DIFFERENT base-URLs from the identical image. The naive baked-in shim collapses both to
    one hardcoded endpoint."""
    registry = list(V1_RUNTIME_TYPES)
    cards = _cards()
    secrets = _secrets()
    ollama_agent = Agent("alice-ollama", "alice", "opencode", "qwen3", "ep-ollama-alice")
    paid_agent = Agent("bob-paid", "bob", "opencode", "claude-sonnet-5", "ep-paid-bob")

    o = resolve(ollama_agent, secrets, runtime_registry=registry, cards=cards)
    p = resolve(paid_agent, secrets, runtime_registry=registry, cards=cards)

    return {
        "same_image": o.image == p.image,                  # conformant: True (one image)
        "distinct_endpoints": o.base_url != p.base_url,     # conformant: True (config, not baked in)
        "ollama_url": o.base_url, "paid_url": p.base_url,
    }


def run_capability_negotiated():
    """(N) AC3/FR-D4: a BYO-endpoint Agent routes onto opencode (advertises byoModelEndpoint) and
    is routed AROUND fixedvendor (does not) PRE-DISPATCH. The naive core assumes every runtime is
    capable → dispatches the un-retargetable fixedvendor → mid-Run failure."""
    registry = list(V1_RUNTIME_TYPES) + ["fixedvendor"]
    cards = _cards()
    secrets = _secrets()

    # capable runtime: resolves cleanly.
    good = Agent("alice-ollama", "alice", "opencode", "qwen3", "ep-ollama-alice")
    good_ok = True
    try:
        resolve(good, secrets, runtime_registry=registry, cards=cards)
    except CapabilityFailure:
        good_ok = False

    # incapable runtime: conformant resolve routes AROUND it (CapabilityFailure caught pre-dispatch).
    bad = Agent("carol-ollama", "carol", "fixedvendor", "qwen3", "ep-ollama-carol")
    secrets.put("ep-ollama-carol", "carol", "http://ollama.carol.svc:11434/v1")
    routed_around = False
    dispatched_then_failed = False
    try:
        resolve(bad, secrets, runtime_registry=registry, cards=cards)
        # only reached if the core (wrongly, via the N mutation) claimed fixedvendor is capable:
        # the runtime cannot honor the base-URL override → mid-Run capability failure.
        dispatched_then_failed = True
    except CapabilityFailure:
        routed_around = True                               # conformant: caught PRE-DISPATCH

    return {"good_ok": good_ok, "routed_around": routed_around,
            "dispatched_then_failed": dispatched_then_failed}


def run_credential_lock():
    """(C) AC4/§11: each Agent's endpoint comes from its OWN per-user Secret ref; there is no
    shared platform endpoint, and a cross-principal read is rejected. The naive fallback resolves a
    shared platform default → the endpoints collapse onto one shared master."""
    registry = list(V1_RUNTIME_TYPES)
    cards = _cards()
    secrets = _secrets()
    alice = Agent("alice-ollama", "alice", "opencode", "qwen3", "ep-ollama-alice")
    bob = Agent("bob-paid", "bob", "opencode", "claude-sonnet-5", "ep-paid-bob")

    a = resolve(alice, secrets, runtime_registry=registry, cards=cards)
    b = resolve(bob, secrets, runtime_registry=registry, cards=cards)

    # least-privilege: Bob's principal may NOT read Alice's endpoint Secret (§9.1).
    cross_read_rejected = False
    try:
        secrets.resolve("ep-ollama-alice", "bob")
    except PermissionError:
        cross_read_rejected = True

    # naive shared-platform arm (independent of the mutation harness) — always shown as teeth.
    naive = SecretStore().put("platform-default", "platform", "https://models.platform.internal/v1", "MASTER")
    naive_a, _ = naive.resolve("platform-default", "platform")
    naive_b, _ = naive.resolve("platform-default", "platform")

    return {"distinct_endpoints": a.base_url != b.base_url,
            "cross_read_rejected": cross_read_rejected,
            "naive_collapsed": naive_a == naive_b}


def run_egress_allowlist():
    """(E) AC4/§12.2: the BYO endpoint host is added to the Team model-endpoint allowlist and
    default-deny still blocks every other host. The naive allow-all design reaches an
    un-allowlisted host (the exfil hole)."""
    registry = list(V1_RUNTIME_TYPES)
    cards = _cards()
    secrets = _secrets()
    alice = Agent("alice-ollama", "alice", "opencode", "qwen3", "ep-ollama-alice")
    tgt = resolve(alice, secrets, runtime_registry=registry, cards=cards)

    endpoint_host = host_of(tgt.base_url)
    egress = TeamEgress().allowlist(endpoint_host)         # the resolved endpoint joins the allowlist

    # conformant: the allowlisted endpoint is reachable, a random host is BLOCKED.
    endpoint_reachable = egress.dial(endpoint_host)
    exfil_blocked = False
    try:
        egress.dial("evil.exfil.example")
    except EgressBlocked:
        exfil_blocked = True

    # naive allow-all arm — the un-allowlisted host is reachable.
    naive = TeamEgress(allow_all=True)
    naive_exfil_reachable = naive.dial("evil.exfil.example")

    return {"endpoint_reachable": endpoint_reachable, "exfil_blocked": exfil_blocked,
            "naive_exfil_reachable": naive_exfil_reachable}


# ============================================================================================
# Driver.
# ============================================================================================

def main():
    print("[model] Story 5.7 BYO Ollama — model-endpoint seam (no new runtime type, no new image)"
          + (f"  [MUTATE={MUTATE}]" if MUTATE else "") + "\n")

    # (M) model≠runtime axis: BYO Ollama is a model-endpoint override, not an AgentRuntime.type.
    m = run_model_not_runtime_axis()
    print(f"[model] (M) AC1  (model≠runtime axis, ADR-026): {m}")
    assert m["resolved_type"] == "opencode", \
        "a BYO-Ollama Agent must resolve onto an ORDINARY runtime type (opencode), not `ollama`"
    assert not m["registry_has_ollama"], \
        "the runtime-type registry must gain NO `ollama` entry — Ollama is a model backend (ADR-026)"
    assert not m["new_image_built"], \
        "TEETH LOST: no new image is built for a BYO endpoint — the image is type-keyed (§10.3)"
    print("[model]        → BYO Ollama rides an existing runtime + model-endpoint override; the "
          "category error registers a runtime type / new image (the ADR-026 leak)\n")

    # (W) OpenAI-compatible wire, endpoint is config: same image retargets by config.
    w = run_openai_wire_endpoint_is_config()
    print(f"[model] (W) AC2  (OpenAI-compatible wire, endpoint is config): {w}")
    assert w["same_image"], \
        "the Ollama Agent and the paid Agent must share ONE opencode image (no new image)"
    assert w["distinct_endpoints"], \
        "TEETH LOST: the endpoint is CONFIG, not baked in — same image, different base-URLs"
    print("[model]        → one image retargets a paid provider vs Ollama by config alone; the "
          "baked-in shim collapses both to one hardcoded endpoint\n")

    # (N) capability-negotiated + honest gap: route around a runtime that lacks byoModelEndpoint.
    n = run_capability_negotiated()
    print(f"[model] (N) AC3  (capability-negotiated + honest gap): {n}")
    assert n["good_ok"], \
        "a byoModelEndpoint-capable runtime (opencode) must resolve the BYO endpoint cleanly"
    assert n["routed_around"] and not n["dispatched_then_failed"], \
        "a runtime that does NOT advertise byoModelEndpoint must be routed AROUND pre-dispatch"
    print("[model]        → the BYO endpoint routes only to a capable runtime; a non-capable "
          "runtime is routed around pre-dispatch (never silent mid-Run failure)\n")

    # (C) credential lock: per-user Secret ref, no shared platform endpoint, cross-read rejected.
    c = run_credential_lock()
    print(f"[model] (C) AC4  (credential lock reinforced, §11 third story): {c}")
    assert c["distinct_endpoints"], \
        "each Agent's endpoint comes from its OWN per-user Secret ref — no shared platform endpoint"
    assert c["cross_read_rejected"], \
        "a cross-principal endpoint-Secret read must be rejected (§9.1 least-privilege)"
    assert c["naive_collapsed"], \
        "TEETH LOST: a shared platform-default fallback should collapse both onto one endpoint"
    print("[model]        → each Agent resolves its own endpoint Secret, cross-reads rejected; the "
          "shared platform default reopens the vendor-lock §11 forbids\n")

    # (E) egress allowlisted: default-deny holds; un-allowlisted host blocked.
    e = run_egress_allowlist()
    print(f"[model] (E) AC4  (egress allowlisted, default-deny holds, §12.2): {e}")
    assert e["endpoint_reachable"], \
        "the BYO endpoint host must join the model-endpoint allowlist and be reachable (§12.2)"
    assert e["exfil_blocked"], \
        "default-deny must still block a host NOT on the allowlist"
    assert e["naive_exfil_reachable"], \
        "TEETH LOST: an allow-all egress should reach an un-allowlisted host (the exfil hole)"
    print("[model]        → the endpoint joins the allowlist under default-deny; allow-all turns "
          "the BYO seam into an exfil hole around §12.2\n")

    print("[model] PASS — BYO Ollama is a model-endpoint override on the existing shim seam: an "
          "ordinary runtime + a Secret-resolved endpoint, no new type/image/core change (M), one "
          "image retargeted by config over the OpenAI-compatible wire (W), capability-negotiated "
          "with honest gaps routed around (N), a per-user endpoint Secret with no shared master "
          "(C), and default-deny egress with the endpoint allowlisted (E). The naive designs each "
          "detectably break.")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg.startswith("--mutate="):
            MUTATE = arg.split("=", 1)[1]
    main()
