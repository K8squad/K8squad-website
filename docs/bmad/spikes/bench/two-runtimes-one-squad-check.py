#!/usr/bin/env python3
"""two-runtimes-one-squad-check.py — Story 5.5 falsification (OpenClaw + Hermes, one squad).

The §10.1 / FR-D3 / NFR-EXT1 / S6 load-bearing invariant: two runtimes of DIFFERENT `type`
run REAL Runs in ONE squad (one Team namespace) sharing ONE spine — one coordination record,
one fenced-claim/lease/fence mechanism, one runtime-agnostic dispatch path, one Agent-Card
negotiation, one per-user credential model — and the ONLY per-runtime code lives inside each
shim's native-translation, never in the core, coord services, or the shared coord record. Five
cruxes make the moat real rather than a demo:

  (H) SAME-SPINE (AC1, §6.2/§6.3). Both Runs claim from ONE shared work-item backlog through a
      TYPE-BLIND fenced claim. `runtime.type` never touches a claim/lease/fence decision; there
      is no per-`type` queue or backlog partition. A per-type queue means the two runtimes cannot
      share one squad's work — the S6 failure.
  (Z) ZERO-CORE-CHANGE (AC1/C10, NFR-EXT1). The one Story-5.1 dispatch client drives both,
      unchanged; two runtimes with identical capability cards produce a BYTE-IDENTICAL dispatch
      trace (recorded from the real verb calls, not a constant). A `type ==` branch forks the
      trace — even a behaviour-neutral fork (the ISI-2377 probe class).
  (R) BOTH REAL, NO FACADE (AC2, design §10). Each Run's artifact is stamped with the runtime
      that produced it; the stamp equals the claimed agent's `runtime.type`. A facade Hermes shim
      that forwards SubmitTask to OpenClaw's gateway collapses the stamps to one runtime — only
      OpenClaw ever executed, and the "second runtime" is a lie ("if it did, the seam would have
      leaked").
  (C) CREDENTIAL ISOLATION (AC3, §11). Each Run mounts its OWN per-user Secret (second-runtime
      static-API-key shape); no shared master credential (FR-G1); neither runtime reads the
      other's Secret (§9.1 least-privilege). A shared master both draw from is the vendor-lock §11
      forbids.
  (K) CAPABILITY-NEGOTIATED (AC4, §10.1/FR-D4). The core routes each Run by THAT runtime's own
      honest card — not by assuming one runtime has the other's capabilities — and routes AROUND
      a declared gap pre-dispatch (Story 5.2). Borrowing OpenClaw's caps for Hermes dispatches a
      task Hermes cannot do → mid-Run failure.

Differential falsification (same discipline as southbound-a2a-check.py / agent-card-check.py):
each property runs a NAIVE/cheating design that MUST break (teeth) alongside the conformant design
that MUST hold. AND each conformant invariant is MUTATION-PROVEN: `--mutate=<H|Z|R|C|K>` injects
the corresponding bug into the CONFORMANT path and the check goes RED (exit 1), so no invariant is
vacuous. Baseline `python3 two-runtimes-one-squad-check.py` exits 0; each `--mutate=NAME` exits 1.

Models the squad-level co-residency in-process; real-runtime promotion rides the ISI-2114
conformance suite (§12, Story 5.6, Ollama lane) — the §21 gate that lets S6 be *claimed*.
"""
import json
import sys


# ---- which conformant invariant to sabotage (mutation-proof harness). Empty = baseline. ----
MUTATE = ""


def mut(name):
    """True iff we are injecting the `name` bug into the conformant path (verifies teeth)."""
    return MUTATE == name


# The capability keys carried on every Agent Card (Story 5.2 honesty contract, FR-D4).
CAP_KEYS = ("streaming", "tool_calls", "interactive", "byo_model_endpoint")


class CapabilityFailure(Exception):
    """A capability gap discovered at dispatch time — the leak type-assumption reintroduces."""


# ============================================================================================
# The shared coordination spine (§6.2/§6.3) — ONE backlog, TYPE-BLIND fenced claim.
# ============================================================================================

class CoordRecord:
    """One squad's shared work-item backlog + fenced claim. The conformant claim is TYPE-BLIND
    (§6.2): a Run's `runtime.type` is NEVER consulted. The naive design partitions the backlog by
    type (per-`type` queue), so a Run can only claim items whose `eligible_type` matches it —
    starving cross-runtime claims (S6 fails)."""

    def __init__(self, partition_by_type=False):
        self.partition_by_type = partition_by_type
        self._items = {}           # work_item_id -> {"eligible_type": str, "claimed_by": run_id|None}
        self.type_consulted = []   # every claim that read `runtime.type` (must stay empty conformant)

    def enqueue(self, work_item_id, eligible_type):
        # `eligible_type` is a provenance stamp only; a real squad's work is runtime-agnostic, so
        # the conformant claim IGNORES it. It exists solely to give the naive partition something
        # to (wrongly) gate on.
        self._items[work_item_id] = {"eligible_type": eligible_type, "claimed_by": None}

    def claim(self, work_item_id, run):
        """Fenced first-come claim. Returns True iff this Run won the item."""
        item = self._items[work_item_id]
        # (H) mutation OR the naive arm: consult `runtime.type` — a per-`type` backlog partition.
        if self.partition_by_type or mut("H"):
            self.type_consulted.append((work_item_id, run.runtime_type))
            if item["eligible_type"] != run.runtime_type:
                return False                       # cross-type claim rejected → starves the runtime
        if item["claimed_by"] is not None:
            return False                           # already claimed (fenced, §6.3)
        item["claimed_by"] = run.run_id
        return True

    def holder(self, work_item_id):
        return self._items[work_item_id]["claimed_by"]


# ============================================================================================
# Agents / runtimes / Runs.
# ============================================================================================

class AgentCard:
    """Each runtime's OWN honest card (Story 5.2). Capabilities are the runtime's real ceiling."""

    def __init__(self, runtime_type, capabilities, credential_type):
        self.runtimeType = runtime_type
        self.capabilities = {k: bool(capabilities.get(k, False)) for k in CAP_KEYS}
        self.credentialType = credential_type      # capability metadata only (FR-G2), never material


class Run:
    def __init__(self, run_id, runtime_type, agent, work_item_id, fence):
        self.run_id = run_id
        self.runtime_type = runtime_type
        self.agent = agent                          # agent name (owns its per-user Secret)
        self.work_item_id = work_item_id
        self.fence = fence


# ============================================================================================
# Per-user credential Secrets (§11 second-runtime = static API key) — MATERIAL never shared.
# ============================================================================================

class SecretStore:
    def __init__(self):
        self._rows = {}   # secret_name -> {"owner": agent, "material": token}

    def put(self, name, owner_agent, material):
        self._rows[name] = {"owner": owner_agent, "material": material}
        return self

    def mount(self, secret_name, requesting_agent):
        """A Run mounts its OWN Secret. A cross-runtime read (requesting != owner) is REJECTED
        (§9.1 least-privilege) — unless the naive shared-master design owns it as 'platform'."""
        row = self._rows[secret_name]
        if row["owner"] != requesting_agent and row["owner"] != "platform":
            raise PermissionError(f"{requesting_agent} may not read Secret owned by {row['owner']} (§9.1)")
        return row["material"]


# ============================================================================================
# The shims — the ONLY per-runtime code. Each translates to its NATIVE runtime and stamps the
# artifact it produces with its own `runtime_type`. A facade forwards across the boundary.
# ============================================================================================

class Artifact:
    def __init__(self, run_id, kind, produced_by):
        self.run_id = run_id
        self.kind = kind
        self.produced_by = produced_by              # the runtime that ACTUALLY executed (the stamp)


class OpenClawShim:
    runtime_type = "openclaw"

    def execute(self, run):
        # translate to OpenClaw native session (design §9); produce a real artifact stamped 'openclaw'.
        return Artifact(run.run_id, "diff", produced_by="openclaw")


class HermesShim:
    runtime_type = "hermes"

    def __init__(self, facade_to=None):
        # facade_to != None → NAIVE (R): forward to another runtime's gateway (fake second runtime).
        self.facade_to = facade_to

    def execute(self, run):
        target = self.facade_to
        if mut("R"):                                # mutation: route the conformant Hermes via OpenClaw
            target = OpenClawShim()
        if target is not None:
            return target.execute(run)              # only OpenClaw executes → artifact stamped 'openclaw'
        # translate to Hermes native (design §10); produce a real artifact stamped 'hermes'.
        return Artifact(run.run_id, "diff", produced_by="hermes")


# ============================================================================================
# The core's runtime-agnostic dispatch client (Story 5.1) — ONE path, NO `type` branch.
# ============================================================================================

OPENCLAW_CAPS = {"streaming": True, "tool_calls": True, "interactive": False, "byo_model_endpoint": True}


def canonical_args(run, card):
    """Trace args derived from the CARD + envelope only — NEVER from `runtime.type`. So two
    runtimes with identical capability cards produce identical args (C10); a `type`-fork that
    changes verb order/args forks the trace even if it never reaches a native channel."""
    return {"caps": [k for k in CAP_KEYS if card.capabilities[k]], "wi": run.work_item_id}


def dispatch(run, card, shims, *, type_branch=False, assume_caps=None):
    """Drive one Run through the six A2A verbs. Records (verb, args) — the dispatch trace. The
    conformant path never reads `runtime.type`; it negotiates against the Run's OWN card."""
    trace = []
    # (K) capability negotiation: route AROUND a gap pre-dispatch (Story 5.2). `assume_caps` (or
    # the K mutation) borrows another runtime's caps instead of reading this runtime's honest card.
    effective = card.capabilities
    if assume_caps is not None:
        effective = assume_caps
    if mut("K"):
        effective = OPENCLAW_CAPS                   # mutation: assume OpenClaw's caps for everyone
    # (Z) the C10 seam: NO branch on runtime.type. The naive arm / mutation forks for hermes.
    if type_branch or mut("Z"):
        if run.runtime_type == "hermes":
            trace.append(("GetStatus", {"precheck": True}))   # a hermes-only fork (behaviour-neutral)
    trace.append(("SubmitTask", canonical_args(run, card)))
    trace.append(("StreamEvents", {"resume_from": 0}))
    artifact = shims[run.runtime_type].execute(run)
    trace.append(("EmitArtifact", {"kind": artifact.kind}))
    return trace, artifact, effective


def trace_bytes(trace):
    return json.dumps(trace, sort_keys=True, separators=(",", ":"))


# ============================================================================================
# Fixtures — one squad (one Team namespace) with an OpenClaw agent and a Hermes agent.
# ============================================================================================

def _openclaw_card():
    return AgentCard("openclaw",
                     {"streaming": True, "tool_calls": True, "interactive": False,
                      "byo_model_endpoint": True}, credential_type="api-key")


def _hermes_card(interactive=False):
    # Hermes' OWN honest card — its capabilities are NOT assumed from OpenClaw.
    return AgentCard("hermes",
                     {"streaming": True, "tool_calls": True, "interactive": interactive,
                      "byo_model_endpoint": True}, credential_type="api-key")


# ============================================================================================
# Scenarios.
# ============================================================================================

def run_same_spine():
    """(H) AC1: an OpenClaw Run and a Hermes Run claim from ONE shared backlog via a TYPE-BLIND
    fenced claim. Conformant: both claim, `type` never consulted. Naive per-`type` queue: the
    Hermes Run cannot claim an item stamped for openclaw → starved (the two cannot share a squad)."""
    coord = CoordRecord()
    # one shared backlog; both items carry a provenance stamp the conformant claim IGNORES.
    coord.enqueue("wi-A", eligible_type="openclaw")
    coord.enqueue("wi-B", eligible_type="openclaw")   # both stamped 'openclaw' — a real squad's work
    oc = Run("run-oc", "openclaw", "agent-oc", "wi-A", fence="f1")
    hm = Run("run-hm", "hermes", "agent-hm", "wi-B", fence="f1")
    oc_won = coord.claim("wi-A", oc)
    hm_won = coord.claim("wi-B", hm)                    # hermes claims from the SAME backlog

    # naive per-type partition: the same two claims against a type-partitioned backlog.
    naive = CoordRecord(partition_by_type=True)
    naive.enqueue("wi-A", eligible_type="openclaw")
    naive.enqueue("wi-B", eligible_type="openclaw")
    naive_oc = naive.claim("wi-A", Run("r1", "openclaw", "a", "wi-A", "f"))
    naive_hm = naive.claim("wi-B", Run("r2", "hermes", "a", "wi-B", "f"))

    return {"oc_won": oc_won, "hm_won": hm_won,
            "type_consulted": coord.type_consulted,           # must stay empty (type-blind)
            "naive_oc_won": naive_oc, "naive_hm_starved": naive_hm is False}


def run_zero_core_change():
    """(Z) AC1/C10: two runtimes with IDENTICAL capability cards produce a BYTE-IDENTICAL dispatch
    trace. A `type ==` branch forks it. Trace args come from the card, not from `type`."""
    shims = {"openclaw": OpenClawShim(), "hermes": HermesShim()}
    # identical capability cards for the C10 comparison (same caps ⇒ same dispatch).
    card = {"streaming": True, "tool_calls": True, "interactive": False, "byo_model_endpoint": True}
    oc_card = AgentCard("openclaw", card, "api-key")
    hm_card = AgentCard("hermes", card, "api-key")
    oc = Run("run-oc", "openclaw", "agent-oc", "wi-A", "f")
    hm = Run("run-hm", "hermes", "agent-hm", "wi-A", "f")

    conf_oc, _, _ = dispatch(oc, oc_card, shims)
    conf_hm, _, _ = dispatch(hm, hm_card, shims)
    cheat_oc, _, _ = dispatch(oc, oc_card, shims, type_branch=True)
    cheat_hm, _, _ = dispatch(hm, hm_card, shims, type_branch=True)

    return {"conf_identical": trace_bytes(conf_oc) == trace_bytes(conf_hm),
            "cheat_forked": trace_bytes(cheat_oc) != trace_bytes(cheat_hm),
            "conf_oc": conf_oc}


def run_both_real_no_facade():
    """(R) AC2: each Run's artifact is stamped with the runtime that produced it, equal to the
    claimed agent's `runtime.type`. A facade Hermes (forwarding to OpenClaw) collapses the stamp."""
    real = {"openclaw": OpenClawShim(), "hermes": HermesShim()}
    facade = {"openclaw": OpenClawShim(), "hermes": HermesShim(facade_to=OpenClawShim())}
    oc = Run("run-oc", "openclaw", "agent-oc", "wi-A", "f")
    hm = Run("run-hm", "hermes", "agent-hm", "wi-B", "f")

    oc_art = real["openclaw"].execute(oc)
    hm_art = real["hermes"].execute(hm)
    facade_hm_art = facade["hermes"].execute(hm)

    return {"oc_stamp": oc_art.produced_by, "hm_stamp": hm_art.produced_by,
            "facade_hm_stamp": facade_hm_art.produced_by,
            "oc_run_type": oc.runtime_type, "hm_run_type": hm.runtime_type}


def run_credential_isolation():
    """(C) AC3/§11: each Run mounts its OWN per-user Secret; no shared master; a cross-runtime read
    is rejected. The naive design points both at one 'platform' master → the set collapses to one."""
    secrets = (SecretStore()
               .put("sec-oc", "agent-oc", "OPENCLAW_API_KEY=sk-oc-AAA")
               .put("sec-hm", "agent-hm", "HERMES_API_KEY=sk-hm-BBB"))
    oc = Run("run-oc", "openclaw", "agent-oc", "wi-A", "f")
    hm = Run("run-hm", "hermes", "agent-hm", "wi-B", "f")

    # conformant: each mounts its own (§11). The C mutation swaps both onto a shared master.
    oc_secret = "sec-oc" if not mut("C") else "sec-master"
    hm_secret = "sec-hm" if not mut("C") else "sec-master"
    if mut("C"):
        secrets.put("sec-master", "platform", "MASTER_KEY=sk-shared-XXX")
    oc_material = secrets.mount(oc_secret, oc.agent)
    hm_material = secrets.mount(hm_secret, hm.agent)

    # least-privilege: the Hermes Run may NOT read the OpenClaw agent's Secret (§9.1).
    cross_read_rejected = False
    try:
        secrets.mount("sec-oc", hm.agent)
    except PermissionError:
        cross_read_rejected = True

    # naive shared-master arm (independent of the mutation harness) — always demonstrated as teeth.
    naive = SecretStore().put("master", "platform", "MASTER_KEY=sk-shared-XXX")
    naive_oc = naive.mount("master", "agent-oc")
    naive_hm = naive.mount("master", "agent-hm")

    return {"distinct": oc_material != hm_material, "cross_read_rejected": cross_read_rejected,
            "no_shared_master": oc_secret != hm_secret,
            "naive_collapsed": naive_oc == naive_hm}


def run_capability_negotiated():
    """(K) AC4/§10.1: the core routes each Run by THAT runtime's own honest card. OpenClaw advertises
    `byo_model_endpoint:true` but this Hermes advertises it `false`; the conformant core routes a
    BYO-endpoint task AROUND Hermes pre-dispatch. The naive core assumes OpenClaw's caps for Hermes
    → dispatches a task Hermes cannot do → mid-Run CapabilityFailure. (The divergent axis is one
    OpenClaw HAS and Hermes LACKS, so borrowing OpenClaw's caps genuinely over-promises.)"""
    shims = {"openclaw": OpenClawShim(), "hermes": HermesShim()}
    # Hermes' OWN honest card — it does NOT support byo_model_endpoint (OpenClaw does; OPENCLAW_CAPS).
    hm_card = AgentCard("hermes",
                        {"streaming": True, "tool_calls": True, "interactive": False,
                         "byo_model_endpoint": False}, credential_type="api-key")
    hm = Run("run-hm", "hermes", "agent-hm", "wi-A", "f")

    def core_routes(effective_caps, task_needs):
        # the core routes around a declared gap (Story 5.2): dispatch only if the runtime CAN.
        return all(effective_caps.get(cap, False) for cap in task_needs)

    task_needs = ["byo_model_endpoint"]                       # a task requiring a BYO Ollama endpoint

    # conformant: negotiate against Hermes' OWN card → interactive False → route around (no dispatch).
    _, _, conf_eff = dispatch(hm, hm_card, shims)             # (K mutation poisons conf_eff → OpenClaw's)
    conf_dispatch = core_routes(conf_eff, task_needs)
    conf_failed = False
    if conf_dispatch:
        # only reached if the core (wrongly) said Hermes has byo_model_endpoint: the runtime fails.
        if not hm_card.capabilities["byo_model_endpoint"]:
            conf_failed = True

    # naive: assume OpenClaw's caps for Hermes → byo_model_endpoint True → dispatch → mid-Run failure.
    _, _, naive_eff = dispatch(hm, hm_card, shims, assume_caps=OPENCLAW_CAPS)
    naive_dispatch = core_routes(naive_eff, task_needs)
    naive_failed = False
    if naive_dispatch:
        # the runtime is asked to do what its honest card said it cannot → capability failure.
        if not hm_card.capabilities["byo_model_endpoint"]:
            naive_failed = True

    return {"conf_routed_around": conf_dispatch is False, "conf_failed_mid_run": conf_failed,
            "naive_dispatched": naive_dispatch, "naive_failed_mid_run": naive_failed}


# ============================================================================================
# Driver.
# ============================================================================================

def main():
    print("[model] Story 5.5 OpenClaw + Hermes — two runtimes, one squad, one seam"
          + (f"  [MUTATE={MUTATE}]" if MUTATE else "") + "\n")

    # (H) same spine: both claim from one shared backlog, type-blind; naive per-type queue starves.
    h = run_same_spine()
    print(f"[model] (H) AC1  (heterogeneous same-squad shared spine): {h}")
    assert h["oc_won"] and h["hm_won"], \
        "both runtimes must claim from the ONE shared backlog (S6 — two runtimes, one squad)"
    assert h["type_consulted"] == [], \
        "the fenced claim must be TYPE-BLIND — `runtime.type` never touches a claim decision (§6.2)"
    assert h["naive_hm_starved"], \
        "TEETH LOST: a per-`type` backlog partition should starve the cross-type claim"
    print("[model]        → both runtimes share one backlog via a type-blind claim; the per-type "
          "queue starves the second runtime (hazard is real)\n")

    # (Z) zero-core-change: identical cards → identical dispatch trace; type-branch forks.
    z = run_zero_core_change()
    print(f"[model] (Z) C10  (zero-core-change dispatch): conf_identical={z['conf_identical']} "
          f"cheat_forked={z['cheat_forked']}")
    assert z["conf_identical"], \
        "two runtimes with identical capability cards must produce a BYTE-IDENTICAL dispatch trace (C10)"
    assert z["cheat_forked"], \
        "TEETH LOST: a `type ==` branch must fork the dispatch trace (NFR-EXT1)"
    print("[model]        → identical cards ⇒ identical dispatch; the type-branch forks the trace\n")

    # (R) both real, no facade: artifact stamp == claimed runtime; facade collapses the stamp.
    r = run_both_real_no_facade()
    print(f"[model] (R) AC2  (both real, no facade): {r}")
    assert r["oc_stamp"] == r["oc_run_type"] == "openclaw", "OpenClaw Run's artifact ⟵ OpenClaw"
    assert r["hm_stamp"] == r["hm_run_type"] == "hermes", \
        "Hermes Run's artifact must be produced by Hermes — a REAL second executor, not a facade"
    assert r["facade_hm_stamp"] == "openclaw", \
        "TEETH LOST: a facade Hermes forwarding to OpenClaw should collapse the stamp to 'openclaw'"
    print("[model]        → each runtime produces its own artifact; the facade collapses to one "
          "runtime (the 'second runtime' would be a lie)\n")

    # (C) credential isolation: own per-user Secret; no shared master; cross-read rejected.
    c = run_credential_isolation()
    print(f"[model] (C) AC3  (per-runtime credential isolation, §11): {c}")
    assert c["distinct"] and c["no_shared_master"], \
        "each runtime mounts its OWN per-user Secret — no shared master credential (FR-G1/§11)"
    assert c["cross_read_rejected"], \
        "a cross-runtime Secret read must be rejected (§9.1 least-privilege)"
    assert c["naive_collapsed"], \
        "TEETH LOST: a shared-master design should collapse both runtimes onto one credential"
    print("[model]        → each runtime has its own key, cross-reads rejected; the shared master "
          "collapses the credential set (the vendor-lock §11 forbids)\n")

    # (K) capability-negotiated: route by each card; type-assumption dispatches an un-runnable task.
    k = run_capability_negotiated()
    print(f"[model] (K) AC4  (capability-negotiated, not type-assumed): {k}")
    assert k["conf_routed_around"] and not k["conf_failed_mid_run"], \
        "the core must route by Hermes' OWN card — an interactive task routes AROUND it pre-dispatch"
    assert k["naive_dispatched"] and k["naive_failed_mid_run"], \
        "TEETH LOST: assuming OpenClaw's caps for Hermes should dispatch an un-runnable task → failure"
    print("[model]        → the core routes by each runtime's honest card; type-assumption "
          "dispatches a task Hermes cannot do → mid-Run failure\n")

    print("[model] PASS — two different-`type` runtimes run real Runs in one squad on one spine: "
          "shared type-blind backlog (H), byte-identical dispatch with no type-branch (Z), two real "
          "executors with no facade (R), isolated per-user credentials with no shared master (C), and "
          "capability-negotiated routing (K). The naive designs each detectably break.")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg.startswith("--mutate="):
            MUTATE = arg.split("=", 1)[1]
    main()
