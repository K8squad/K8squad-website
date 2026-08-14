#!/usr/bin/env python3
"""Story 9.4 (ISI-2253) falsification — the Helm chart brings up NATS with JetStream
ENABLED as the plugin event bus (stateful dependency #2), single-replica default with a
JetStream PVC whose StorageClass comes from values (never cluster-default, HA via a
values toggle), and the apiserver outbox RELAY publishes events to it in a way that can
NEVER block a Run/claim/write (arch §16 / §17.4 / ADR-023; §16.2 storage; chart impl =
ISI-2253, PR #18 / k8squad@598f3f5).

WHY THIS BENCH EXISTS
---------------------
CEO decision (2026-08-11): "data in Postgres, events on NATS." One `helm install` must
yield Postgres (CNPG) + NATS/JetStream + control plane, and — the whole point — the bus
must be UNABLE to block the core. Five ways a plausible-but-wrong chart silently breaks
the acceptance, none caught by "it renders":

  1. NO-JETSTREAM — NATS comes up as core-NATS only (no JetStream). Plugins lose the
     replay/catch-up substrate (§17.4); a plugin offline during an event never sees it.
     JetStream MUST be enabled.

  2. TOGGLE-INERT — the HA replica count is hardcoded and ignores nats.ha.enabled, OR an
     even/<3 HA replica count is accepted (no JetStream RAFT quorum). Single-replica is
     the default; HA is a values toggle with an ODD, >=3 quorum — same shape as CNPG.

  3. CLUSTER-DEFAULT-PVC — the JetStream file-store PVC omits storageClassName (or
     hardcodes one), so JetStream silently binds the cluster-default StorageClass that
     §16.2 forbids; or an unset class does NOT fail the install. It MUST come from
     storage.nats.storageClassName (fallback storage.storageClassName) and fail fast.

  4. RELAY-UNWIRED — the relay ConfigMap hardcodes the NATS URL (ignoring release/values)
     or drops the subject taxonomy prefix, so events have nowhere/wrong to publish. The
     URL is release-derived/values-driven; subjects are ksquad.{entity}.{project}.{squad}.
     {event_type}.

  5. NATS-DOWN-BLOCKS — the relay is wired into the write path or apiserver health
     (relay.blocksWritePath=true / relay.natsHealthGatesApiserver=true), OR turning the
     bus off (nats.enabled=false) fails the core install. Then NATS-down blocks a
     Run/claim/write — the exact isolation the CEO forbids. The outbox is the durable
     buffer; the relay is best-effort and out-of-band; bus-off still installs the core.

Two falsification layers, both stdlib-only (`python3 nats-jetstream-check.py`):

  LAYER A — model-based mutation battery. A faithful mini-renderer of the chart's NATS
  workload, the StorageClass resolution + ksquad.validate fail-fast, and the event-relay
  ConfigMap. Six checks C1-C6 <-> AC1-AC6. A battery of broken-chart mutations; EACH must
  be caught by a designated check going RED, and the §16/§17.4-conformant baseline is
  GREEN on all six. Differential checks (render two distinct value profiles and assert
  the output tracks the input) give the teeth against hardcoding.

  LAYER B — file-grounded pass over the PINNED real chart snapshot
  (`helm-chart-isi2149/`, k8squad@598f3f5). Asserts the SHIPPED templates satisfy each
  invariant, and text-mutates each real template and asserts the detector flips RED, so
  the file-grounded checks have teeth on the real artifact, not just the model.

Exit non-zero if any mutation survives (Layer A), any real-chart invariant is violated,
or any file-grounded detector fails to flip (Layer B).
"""
import copy
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "helm-chart-isi2149")
SNAP_COMMIT = "598f3f5"


# ══════════════════════════════════════════════════════════════════════════════════════
#  Value profiles — two distinct installs. Differential checks assert output tracks input.
# ══════════════════════════════════════════════════════════════════════════════════════

def base_values():
    return {
        "release": "ksq",
        "namespace": "nsA",
        "storage": {"storageClassName": "std", "nats": {"storageClassName": "", "size": "5Gi"}},
        "nats": {
            "enabled": True,
            "image": "nats:2.10-alpine",
            "port": 4222,
            "jetstream": {"enabled": True, "maxFileStore": "4Gi"},
            "ha": {"enabled": False, "replicas": 3},
        },
        "events": {"relay": {"enabled": True, "subjectPrefix": "ksquad", "natsUrl": ""}},
    }


def profile(name):
    """Two fully-specified, DISTINCT value sets. Every field a hardcoding mutation might
    freeze differs between them (release, namespace, StorageClass, replicas), so a
    differential check catches the freeze."""
    v = base_values()
    if name == "default":            # single-replica, global StorageClass
        return v
    if name == "ha":                 # HA quorum, per-family StorageClass, distinct release/ns
        v["release"] = "prod"
        v["namespace"] = "nsB"
        v["storage"]["nats"]["storageClassName"] = "nats-class"
        v["nats"]["ha"] = {"enabled": True, "replicas": 3}
        return v
    raise ValueError(name)


# ══════════════════════════════════════════════════════════════════════════════════════
#  Mini-renderer — mirrors templates/nats.yaml, templates/event-relay.yaml, and the
#  ksquad.validate fail-fast in templates/_helpers.tpl. `mut` injects a broken-chart bug.
# ══════════════════════════════════════════════════════════════════════════════════════

def render(v, mut=None):
    out = {"validate_error": None, "nats": None, "relay": None}
    nsc = v["storage"]["nats"]["storageClassName"] or v["storage"]["storageClassName"]
    ha = v["nats"]["ha"]

    # ── ksquad.validate (fail-fast) ──
    if v["nats"]["enabled"]:
        if not nsc and mut != "skip_sc_failfast":
            out["validate_error"] = "storage StorageClassName REQUIRED — never the cluster default (§16.2)"
            return out
        if ha["enabled"]:
            r = int(ha["replicas"])
            if r < 3 and mut != "accept_lt3":
                out["validate_error"] = "nats.ha.replicas must be >= 3 (RAFT quorum)"
                return out
            if r % 2 == 0 and mut != "accept_even":
                out["validate_error"] = "nats.ha.replicas must be ODD (RAFT quorum)"
                return out
    if not v["nats"]["enabled"] and mut == "busoff_fails_core":
        out["validate_error"] = "NATS is required"       # M11: bus a hard dep (regression)
        return out

    # ── templates/nats.yaml (parent-rendered JetStream workload) ──
    if v["nats"]["enabled"]:
        replicas = int(ha["replicas"]) if ha["enabled"] else 1
        clustered = ha["enabled"]
        if mut == "hardcode_replicas":
            replicas = 1                                  # ignores the ha toggle
            clustered = False
        pvc_sc = nsc
        if mut == "pvc_cluster_default":
            pvc_sc = ""                                   # silent cluster-default
        out["nats"] = {
            "jetstream_enabled": v["nats"]["jetstream"]["enabled"] and mut != "disable_jetstream",
            "replicas": replicas,
            "clustered": clustered,
            "pvc_storageclass": pvc_sc,
        }

    # ── templates/event-relay.yaml (apiserver outbox → NATS relay config) ──
    if v["events"]["relay"]["enabled"]:
        rel = v["events"]["relay"]
        if rel["natsUrl"]:
            url = rel["natsUrl"]
        elif mut == "hardcode_url":
            url = "nats://localhost:4222"                 # frozen, ignores release/ns
        else:
            url = "nats://%s-nats.%s.svc:%d" % (v["release"], v["namespace"], v["nats"]["port"])
        out["relay"] = {
            "natsUrl": url,
            "subjectPrefix": "" if mut == "drop_subjects" else rel["subjectPrefix"],
            "jetstream": True,
            "decoupled": True,
            "blocksWritePath": (mut == "blocks_write"),
            "natsHealthGatesApiserver": (mut == "health_gate"),
            "busBundled": v["nats"]["enabled"],
        }
    return out


def render_p(profile_name, mut=None):
    return render(profile(profile_name), mut)


def render_ha(replicas, mut=None):
    v = base_values()
    v["storage"]["nats"]["storageClassName"] = "nats-class"
    v["nats"]["ha"] = {"enabled": True, "replicas": replicas}
    return render(v, mut)


# ══════════════════════════════════════════════════════════════════════════════════════
#  Checks C1–C6 ↔ AC1–AC6. Each takes the mutation under test (None = conformant baseline)
#  and returns True on a conformant chart, False on a broken one — so a mutation is CAUGHT
#  when its designated check returns False.
# ══════════════════════════════════════════════════════════════════════════════════════

def c1_jetstream(mut):
    """AC1 — JetStream enabled on both profiles (the replay substrate)."""
    return all(render_p(p, mut)["nats"] and render_p(p, mut)["nats"]["jetstream_enabled"]
               for p in ("default", "ha"))


def c2_replicas_toggle(mut):
    """AC2 — single-replica default; HA toggle actually changes replicas + clusters
    (differential: default→1 non-clustered, ha→3 clustered)."""
    d, h = render_p("default", mut)["nats"], render_p("ha", mut)["nats"]
    return bool(d and h and d["replicas"] == 1 and not d["clustered"]
                and h["replicas"] == 3 and h["clustered"])


def c3_pvc_from_values(mut):
    """AC3 — JetStream PVC StorageClass tracks values (default→std, ha→nats-class) AND an
    unset class fails fast while nats.enabled."""
    d, h = render_p("default", mut)["nats"], render_p("ha", mut)["nats"]
    tracks = bool(d and h and d["pvc_storageclass"] == "std" and h["pvc_storageclass"] == "nats-class")
    v = base_values(); v["storage"]["storageClassName"] = ""   # both unset → must fail fast
    unset = render(v, mut)
    failfast = bool(unset["validate_error"] and "StorageClassName" in unset["validate_error"])
    return tracks and failfast


def c4_relay_wired(mut):
    """AC4 — relay publishes to a release-derived NATS URL + carries the subject taxonomy.
    Differential: the URL differs across profiles (release/ns), so a hardcode is caught."""
    d, h = render_p("default", mut)["relay"], render_p("ha", mut)["relay"]
    derived = bool(d and h
                   and d["natsUrl"] == "nats://ksq-nats.nsA.svc:4222"
                   and h["natsUrl"] == "nats://prod-nats.nsB.svc:4222")
    subjects = bool(d and d["subjectPrefix"] == "ksquad")
    return derived and subjects


def c5_isolation(mut):
    """AC5 — relay decoupled: never blocks the write path / apiserver health, AND bus-off
    still installs the core (relay buffers in the outbox)."""
    d = render_p("default", mut)["relay"]
    decoupled = bool(d and d["decoupled"] and not d["blocksWritePath"]
                     and not d["natsHealthGatesApiserver"])
    v = base_values(); v["nats"]["enabled"] = False            # bus off
    off = render(v, mut)
    core_up = bool(off["validate_error"] is None and off["relay"] and off["relay"]["busBundled"] is False)
    return decoupled and core_up


def c6_ha_quorum(mut):
    """AC6 — HA replica count must be ODD and >=3 (RAFT quorum) — even/<3 fails fast."""
    valid = render_ha(3, mut)["validate_error"] is None
    even_fails = render_ha(4, mut)["validate_error"] is not None
    lt3_fails = render_ha(1, mut)["validate_error"] is not None
    return valid and even_fails and lt3_fails


CHECKS = {
    "C1": ("AC1 JetStream enabled",                 c1_jetstream),
    "C2": ("AC2 single-replica default + HA toggle", c2_replicas_toggle),
    "C3": ("AC3 JetStream PVC class from values",   c3_pvc_from_values),
    "C4": ("AC4 relay wired to NATS (url+subjects)", c4_relay_wired),
    "C5": ("AC5 NATS-down never blocks (isolation)", c5_isolation),
    "C6": ("AC6 HA RAFT quorum fail-fast",          c6_ha_quorum),
}

# Mutation → the check that must catch it. Special-cased mutations note the check they hit.
MUTATIONS = [
    ("M1  disable JetStream (core-NATS only)",   "disable_jetstream",   "C1"),
    ("M2  hardcode replicas (toggle inert)",     "hardcode_replicas",   "C2"),
    ("M3  accept even HA replicas",              "accept_even",         "C6"),
    ("M4  accept <3 HA replicas",                "accept_lt3",          "C6"),
    ("M5  JetStream PVC → cluster default",       "pvc_cluster_default", "C3"),
    ("M6  skip NATS StorageClass fail-fast",     "skip_sc_failfast",    "C3"),
    ("M7  hardcode relay NATS URL",              "hardcode_url",        "C4"),
    ("M8  drop subject taxonomy prefix",         "drop_subjects",       "C4"),
    ("M9  relay blocksWritePath=true",           "blocks_write",        "C5"),
    ("M10 gate apiserver health on NATS",        "health_gate",         "C5"),
    ("M11 bus-off fails core install",           "busoff_fails_core",   "C5"),
]


def run_layer_a():
    print("=" * 92)
    print("LAYER A — model-based mutation battery (mini-renderer of nats.yaml + event-relay.yaml +")
    print("          ksquad.validate). Baseline GREEN on C1–C6; every mutation caught by its check.")
    print("=" * 92)
    ok_all = True

    print("\n  Baseline (§16/§17.4-conformant chart):")
    for cid, (label, fn) in CHECKS.items():
        ok = fn(None)
        ok_all &= ok
        print(f"    [{'GREEN' if ok else 'RED  '}] {cid} {label}")

    print("\n  Mutation battery (each must flip its designated check RED):")
    for mlabel, mut, cid in MUTATIONS:
        label, fn = CHECKS[cid]
        caught = not fn(mut)
        ok_all &= caught
        print(f"    [{'CAUGHT ' if caught else 'SURVIVED'}] {mlabel:<40} → {cid} {'RED' if caught else 'still GREEN'}")
    return ok_all


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER B — file-grounded pass over the pinned real chart snapshot. Each detector must
#  (i) PASS on the shipped template text and (ii) FLIP when the template is text-mutated.
# ══════════════════════════════════════════════════════════════════════════════════════

def read(rel):
    with open(os.path.join(SNAP, rel), encoding="utf-8") as f:
        return f.read()


def det_jetstream_enabled(texts):
    """nats.yaml enables JetStream with a file store."""
    t = texts["templates/nats.yaml"]
    return bool(re.search(r'jetstream\s*\{', t) and "store_dir" in t)


def det_pvc_class_from_values(texts):
    """The JetStream volumeClaimTemplate sources storageClassName from $sc (the resolved
    ksquad.storageClass.nats), never a literal."""
    t = texts["templates/nats.yaml"]
    return bool(re.search(r'storageClassName:\s*\{\{\s*\$sc', t)
                and 'ksquad.storageClass.nats' in texts["templates/_helpers.tpl"])


def det_relay_wired(texts):
    """event-relay.yaml publishes to the ksquad.nats.url and carries the subject prefix."""
    t = texts["templates/event-relay.yaml"]
    return bool(re.search(r'relay\.natsUrl:\s*\{\{\s*include "ksquad\.nats\.url"', t)
                and re.search(r'relay\.subjectPrefix:', t))


def det_relay_decoupled(texts):
    """The isolation contract is present + greppable: the relay never blocks the write
    path / apiserver health, and the NATS StorageClass fail-fast is gated on nats.enabled
    so bus-off still installs the core."""
    t = texts["templates/event-relay.yaml"]
    isolated = bool(re.search(r'relay\.blocksWritePath:\s*"false"', t)
                    and re.search(r'relay\.natsHealthGatesApiserver:\s*"false"', t))
    h = texts["templates/_helpers.tpl"]
    bus_off_ok = bool(re.search(r'if\s+\.Values\.nats\.enabled', h))
    return isolated and bus_off_ok


def det_no_state_of_record(texts):
    """Docs assert NATS is event-flow-only — Postgres is the sole source of truth — so no
    operator mistakes JetStream retention for durable state (ADR-001 / §4)."""
    r = re.sub(r"\s+", " ", texts["README.md"])   # collapse line wraps
    return bool("sole source of truth" in r and "in-flight/replayable event copies" in r)


FG_DETECTORS = [
    ("FG1 JetStream enabled (file store)",       "templates/nats.yaml",
     det_jetstream_enabled,   ('jetstream {',                          'disabled {')),
    ("FG2 JetStream PVC class from values",      "templates/nats.yaml",
     det_pvc_class_from_values, ('storageClassName: {{ $sc | quote }}', 'storageClassName: "standard"')),
    ("FG3 relay wired to NATS url + subjects",   "templates/event-relay.yaml",
     det_relay_wired,         ('{{ include "ksquad.nats.url" . | quote }}', '"nats://localhost:4222"')),
    ("FG4 relay decoupled / bus-off core-up",    "templates/event-relay.yaml",
     det_relay_decoupled,     ('relay.blocksWritePath: "false"',       'relay.blocksWritePath: "true"')),
    ("FG5 NATS holds no state of record",        "README.md",
     det_no_state_of_record,  ('in-flight/replayable event copies',    'the durable store of record')),
]


def run_layer_b():
    print("\n" + "=" * 92)
    print(f"LAYER B — file-grounded pass over pinned real chart (helm-chart-isi2149/, k8squad@{SNAP_COMMIT})")
    print("=" * 92)
    names = ["templates/nats.yaml", "templates/event-relay.yaml", "templates/_helpers.tpl",
             "README.md"]
    try:
        texts = {n: read(n) for n in names}
    except FileNotFoundError as e:
        print(f"  ✗ pinned chart snapshot missing: {e}")
        return False

    ok_all = True
    for label, tgt, det, (find_s, repl_s) in FG_DETECTORS:
        shipped = det(texts)
        mutated = dict(texts)
        if find_s in mutated[tgt]:
            mutated[tgt] = mutated[tgt].replace(find_s, repl_s, 1)
            flipped = not det(mutated)
        else:
            flipped = False
            print(f"  (note) mutation anchor {find_s!r} not found in {tgt}")
        teeth = shipped and flipped
        ok_all &= teeth
        print(f"  [{'PASS' if teeth else 'FAIL'}] {label:<40} shipped={'ok' if shipped else 'VIOLATED'}  "
              f"detector-flips-on-mutation={'yes' if flipped else 'NO'}")
    return ok_all


def main():
    a = run_layer_a()
    b = run_layer_b()
    print("\n" + "=" * 92)
    if a and b:
        print("✓ ALL GREEN — baseline passes C1–C6; all 11 mutations caught; 5 file-grounded "
              "detectors pass on the shipped chart and have teeth. Story 9.4 acceptance is falsifiable.")
        return 0
    print("✗ FAILURES ABOVE — see RED / SURVIVED / VIOLATED rows.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
