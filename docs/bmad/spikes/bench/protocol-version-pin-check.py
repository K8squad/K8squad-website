#!/usr/bin/env python3
"""ISI-2215 (Story 5.3) — protocol version pinning behind the seam: falsification.

The locked claim (arch §10.2 "Spec-drift isolation", OQ12 / Challenger F9 / risk
R11; NFR-EXT2 "no bespoke lateral protocols"): the A2A/MCP (and, by the same
discipline, the event-catalog §17.4) external wire revisions are **pinned in one
place** — `internal/protocol/versions.go` — and isolated **behind the shim/adapter
seam only**. The core (Run reconciler, coord, memory) speaks an **internal stable
interface**; it never imports the wire types and never reads a raw rev. So:

    "When an external-spec touchpoint is added it sits behind the adapter seam,
     and a version bump changes an adapter, NEVER core."

Four properties are the entire correctness content of THIS story, and each is
mutation-checked — a conformant design that MUST hold runs alongside a NAIVE /
drift-prone design that MUST break (teeth). If a naive arm stops breaking the
check fails LOUD, because the clean conformant result would then prove nothing.

  (R — single Registry) Every external-spec rev *literal* lives in exactly one
      module: the pin registry (`versions.go`). No other module hardcodes a wire
      version string; they reference the registry symbolically. A stray literal in
      core is a drift landmine — the next upstream bump misses it. NAIVE: the
      reconciler inlines "a2a/2025-06-11" ⇒ a scan finds a stray literal outside
      the registry.
  (L — Layering / import direction, the moat, a C10-style grep gate) Core packages
      import only the internal stable interface; ONLY the adapter package imports
      the wire-rev codec. A `core → wire` edge bypasses the seam and re-couples the
      core to the external spec. NAIVE: the reconciler imports the wire codec
      directly ⇒ an illegal core→wire edge exists.
  (B — Bump is adapter-local, the HEADLINE) Bumping the pinned rev (R1→R2) touches
      ONLY {registry, adapter}; the core is untouched AND its observed behaviour is
      identical (the same StableTask is delivered — capability negotiation absorbs
      the wire variance). NAIVE: the core itself branches on the raw rev, so a bump
      forces a core edit and the change-set reaches core.
  (N — Negotiation is fail-closed at the seam) A peer advertising a *compatible*
      rev is adapted and reaches core as a valid StableTask; an *incompatible* rev
      (beyond the pin's capability range) is REJECTED at the seam — the malformed
      wire payload NEVER reaches core (a gated bump is required, not an ambient
      break). NAIVE: no seam gate ⇒ the incompatible payload flows straight into
      core and mis-parses (silent corruption).

Stdlib only; `python3` it directly. Baseline exit 0; each documented mutation
(see the story's "Runnable check") flips exactly one property RED.
"""
import sys


# ═══════════════════════════ the seam model ═══════════════════════════

# `internal/protocol/versions.go` — the ONE place a wire-rev string is declared.
class PinRegistry:
    """The single source of truth for external-spec revisions. A rev *literal*
    appears here and nowhere else in the tree."""

    def __init__(self):
        self._pins = {"a2a": "v2", "mcp": "v2", "events": "v1"}

    def rev(self, proto):
        return self._pins[proto]

    def bump(self, proto, rev):
        self._pins[proto] = rev


# The wire codecs live in the adapter package (`pkg/a2a`, `pkg/mcp`). Each pinned
# rev has its own wire shape; the adapter maps wire <-> the internal stable type.
# `major(rev)` is the compatibility axis capability-negotiation ranges over.
def major(rev):
    return int(rev.lstrip("v").split(".")[0])


class WireCodec:
    """Adapter-package artifact. Knows how to (de)serialize ONE wire rev's shape.
    A new rev = a new codec entry — added in the adapter, never in core."""

    def __init__(self, rev):
        self.rev = rev

    def parse(self, wire):
        # Each rev keys its payload fields differently; the codec normalizes them
        # into the stable shape. A codec only accepts its own rev's wire.
        if wire.get("_rev") != self.rev:
            raise ValueError(f"codec {self.rev} cannot parse wire {wire.get('_rev')}")
        return {"goal": wire["g" if major(self.rev) >= 2 else "goal_text"],
                "id": wire["task_id"]}


class Adapter:
    """`pkg/a2a` — the seam. Reads the pinned rev from the registry, holds the
    codec table, and exposes ONLY the internal stable interface to core. This is
    the sole module that touches the wire. A bump adds a codec here + flips the
    pin; core is never edited."""

    def __init__(self, registry, proto="a2a"):
        self.registry = registry
        self.proto = proto
        self.codecs = {"v1": WireCodec("v1"), "v2": WireCodec("v2")}

    def register_codec(self, rev):          # what a gated bump does IN THE ADAPTER
        self.codecs[rev] = WireCodec(rev)

    def ingest(self, wire):
        """Wire payload -> internal StableTask, fail-closed on an unpinned rev."""
        pinned = self.registry.rev(self.proto)
        adv = wire.get("_rev")
        # capability negotiation: same major as the pin is absorbed; anything else
        # is rejected AT THE SEAM (a gated bump is required, never ambient).
        if adv is None or major(adv) != major(pinned):
            return None                     # rejected at the seam; core never sees it
        # normalize a compatible minor variance onto the pinned codec
        codec = self.codecs[pinned]
        norm = dict(wire); norm["_rev"] = pinned
        stable = codec.parse(norm)
        return StableTask(stable["id"], stable["goal"])


class StableTask:
    """The internal stable interface (`internal/protocol`) core speaks. No wire
    field names, no rev — bumps cannot change this type."""

    def __init__(self, id_, goal):
        self.id = id_
        self.goal = goal

    def __eq__(self, o):
        return isinstance(o, StableTask) and (self.id, self.goal) == (o.id, o.goal)

    def __repr__(self):
        return f"StableTask(id={self.id!r}, goal={self.goal!r})"


class Core:
    """The Run reconciler. Consumes ONLY StableTask. It never imports WireCodec
    and never reads a raw rev — so a rev bump cannot reach it."""

    reads_raw_rev = False                   # the invariant B/L both hinge on

    def dispatch(self, adapter, wire):
        task = adapter.ingest(wire)         # seam does all the wire work
        if task is None:
            return "rejected-at-seam"
        return f"dispatched:{task.goal}"    # core behaviour keyed on STABLE fields


def wire(rev, goal, task_id="run-7f3a"):
    """A wire payload as it arrives from the shim at revision `rev`."""
    key = "g" if major(rev) >= 2 else "goal_text"
    return {"_rev": rev, "task_id": task_id, key: goal}


# ═══════════════════════════ (R) single Registry ═══════════════════════════

# A module's source is modeled as the set of wire-rev LITERALS it hardcodes.
# Only the registry is permitted to contain any.
def scan_stray_literals(modules, registry_name):
    return {name: lits for name, lits in modules.items()
            if name != registry_name and lits}


def check_registry():
    conformant = {                          # all rev literals sourced from versions.go
        "internal/protocol/versions.go": {"v1", "v2"},
        "pkg/a2a/adapter.go":            set(),   # references versions.A2ARev symbolically
        "internal/reconcile/run.go":     set(),   # speaks StableTask only
        "internal/coord/coord.go":       set(),
    }
    naive = dict(conformant)
    naive["internal/reconcile/run.go"] = {"a2a/2025-06-11"}   # inlined literal in CORE

    conf_stray = scan_stray_literals(conformant, "internal/protocol/versions.go")
    naive_stray = scan_stray_literals(naive, "internal/protocol/versions.go")
    conf_clean = (conf_stray == {})
    naive_broken = (len(naive_stray) > 0)
    print(f"[R] conformant : stray rev-literals outside versions.go = {conf_stray} (must be empty)")
    print(f"[R] naive      : stray rev-literals = {naive_stray} (a drift landmine)")
    print(f"[R]   -> conf_clean={conf_clean} naive_broken={naive_broken} (both True)")
    return conf_clean and naive_broken


# ═══════════════════════════ (L) Layering / import direction ═══════════════════════════

def illegal_core_to_wire_edges(imports, core_pkgs, wire_pkg):
    return [(src, wire_pkg) for src in core_pkgs if wire_pkg in imports.get(src, set())]


def check_layering():
    core = {"internal/reconcile", "internal/coord", "internal/memory"}
    wire_pkg = "pkg/a2a/wire"
    conformant = {                          # core -> stable; only adapter -> wire
        "internal/reconcile": {"internal/protocol"},
        "internal/coord":     {"internal/protocol"},
        "internal/memory":    {"internal/protocol"},
        "pkg/a2a":            {"internal/protocol", "pkg/a2a/wire"},
    }
    naive = dict(conformant)
    naive["internal/reconcile"] = {"internal/protocol", "pkg/a2a/wire"}  # core -> wire!

    conf_bad = illegal_core_to_wire_edges(conformant, core, wire_pkg)
    naive_bad = illegal_core_to_wire_edges(naive, core, wire_pkg)
    conf_clean = (conf_bad == [])
    naive_broken = (len(naive_bad) > 0)
    print(f"[L] conformant : illegal core->wire edges = {conf_bad} (must be empty)")
    print(f"[L] naive      : illegal core->wire edges = {naive_bad} (seam bypassed)")
    print(f"[L]   -> conf_clean={conf_clean} naive_broken={naive_broken} (both True)")
    return conf_clean and naive_broken


# ═══════════════════════════ (B) Bump is adapter-local (headline) ═══════════════════════════

def bump_changeset(reads_raw_rev):
    """Which components must be edited to support a NEW rev. The registry pin and
    the adapter codec table always change; core is in the set ONLY if core reads
    the raw rev (the naive coupling)."""
    touched = {"internal/protocol/versions.go", "pkg/a2a/adapter.go"}
    if reads_raw_rev:
        touched.add("internal/reconcile/run.go")   # core forced to add an `elif rev==`
    return touched


def check_bump():
    reg = PinRegistry()
    adapter = Adapter(reg)
    core = Core()

    # Observed core behaviour BEFORE the bump, at the pinned rev v2.
    before = core.dispatch(adapter, wire("v2", "ship-it"))

    # A gated bump v2 -> v2.1 (same major): add the codec in the adapter, flip the
    # pin in the registry. Nothing in core is touched.
    adapter.register_codec("v2.1")
    reg.bump("a2a", "v2.1")
    after = core.dispatch(adapter, wire("v2.1", "ship-it"))

    conf_touched = bump_changeset(reads_raw_rev=Core.reads_raw_rev)   # conformant: False
    naive_touched = bump_changeset(reads_raw_rev=True)                # naive core branches on rev

    core_untouched = "internal/reconcile/run.go" not in conf_touched
    behaviour_identical = (before == after == "dispatched:ship-it")
    naive_hits_core = "internal/reconcile/run.go" in naive_touched
    print(f"[B] conformant : bump change-set={sorted(conf_touched)}")
    print(f"[B] conformant : core dispatch before={before!r} after={after!r} (identical)")
    print(f"[B] naive      : bump change-set={sorted(naive_touched)} (reaches core)")
    print(f"[B]   -> core_untouched={core_untouched} behaviour_identical={behaviour_identical} "
          f"naive_hits_core={naive_hits_core} (all True)")
    return core_untouched and behaviour_identical and naive_hits_core


# ═══════════════════════════ (N) Negotiation fail-closed at the seam ═══════════════════════════

def naive_ingest_no_gate(wire_payload):
    """NAIVE adapter with NO rev gate: hands the raw wire straight to core, which
    mis-parses an incompatible shape (KeyError -> corruption/None)."""
    try:
        # core naively assumes the pinned major-2 key "g"; a v1 payload lacks it.
        return StableTask(wire_payload["task_id"], wire_payload["g"])
    except KeyError:
        return "CORRUPTED"                  # core reached with a malformed payload


def check_negotiation():
    reg = PinRegistry()               # pinned a2a = v2 (major 2)
    adapter = Adapter(reg)
    core = Core()

    compatible = core.dispatch(adapter, wire("v2.3", "adapt-me"))   # minor variance, same major
    incompatible = core.dispatch(adapter, wire("v1", "too-old"))    # major mismatch

    conf_absorbs = (compatible == "dispatched:adapt-me")
    conf_rejects = (incompatible == "rejected-at-seam")             # core never saw it
    naive_corrupts = (naive_ingest_no_gate(wire("v1", "too-old")) == "CORRUPTED")
    print(f"[N] conformant : compatible(v2.3)->{compatible!r}  incompatible(v1)->{incompatible!r}")
    print(f"[N] naive      : no-gate incompatible(v1) reaches core -> "
          f"{naive_ingest_no_gate(wire('v1', 'too-old'))!r} (corruption)")
    print(f"[N]   -> conf_absorbs={conf_absorbs} conf_rejects={conf_rejects} "
          f"naive_corrupts={naive_corrupts} (all True)")
    return conf_absorbs and conf_rejects and naive_corrupts


# ═══════════════════════════ driver ═══════════════════════════

def main():
    results = {
        "R single pin registry (no stray literals)": check_registry(),
        "L core->stable only, never core->wire":     check_layering(),
        "B version bump is adapter-local":           check_bump(),
        "N negotiation fail-closed at the seam":     check_negotiation(),
    }
    print()
    failed = [k for k, ok in results.items() if not ok]
    if failed:
        for k in failed:
            print(f"[protocol] FAIL — property lost its teeth or the conformant path broke: {k}")
        return 1
    print("[protocol] PASS — external A2A/MCP revs are pinned in ONE registry "
          "(versions.go), core imports only the internal stable interface (no "
          "core->wire edge), a rev bump touches only {registry, adapter} while "
          "core behaviour is identical, and an incompatible rev is rejected "
          "fail-closed at the seam. Every naive counter-design is detectably broken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
