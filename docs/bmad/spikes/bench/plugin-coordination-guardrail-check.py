#!/usr/bin/env python3
"""Story 12.4 (ISI-2263) falsification — plugins are STRUCTURALLY unable to become a
coordination path. The plugin contract is read-only event consumption: the SDK exposes no
claim/handoff/state-mutation surface, the event seam is one-way (outbox→NATS→plugin, never
NATS→coord), plugin NATS credentials are subscribe-only, and a misbehaving plugin cannot
mutate coordination state or satisfy a work-item transition — no matter what it publishes,
replays, or calls (arch §17.4 Guard 1–3 + §6.6 "emit-only and read-only downstream"; sibling
of the §7.5/10.4 room guardrail; feeds the §6.5 14.4 covert-channel / blast-radius suite).

WHY THIS BENCH EXISTS
---------------------
CEO locked decision (2026-08-11, §17.4/ADR-023): "plugins are observers, not a coordination
path — no claim/handoff/state-transition capability, ever." A guardrail is only real if it is
FALSIFIABLE: a plausible-but-wrong plugin seam that still "compiles and delivers events" can
quietly reopen coordination. Six ways it silently breaks, none caught by "events arrive":

  1. SDK-MUTATION-SURFACE — a convenience helper (`claim()`, `transition_state()`,
     `complete_work_item()`, `outbox_publish()`) creeps into the plugin SDK. Now a plugin
     coordinates by CALLING the SDK. The SDK surface MUST be subscribe/read-only.

  2. NATS-PUB-GRANT — the plugin's NATS account is granted PUB on `ksquad.>` (or any coord
     subject) "so it can emit its own events." A plugin can now inject messages onto the bus.
     Plugin creds MUST be subscribe-only (no PUB that re-enters coordination).

  3. RELAY-BIDIRECTIONAL — a NATS→coord consumer is added (the relay, or a new worker, reads a
     subject and applies it to the coord record). Now anything on the bus can move a work item.
     The seam MUST be one-way: outbox→NATS only; NOTHING a plugin publishes re-enters coord.

  4. PLUGIN-AS-MUTATION-AUTHORITY — the coord mutation path accepts a plugin identity as a
     legitimate writer (bypassing the authenticated-apiserver-principal + fence §6.2/6.3 gate).
     Coordination custody MUST require an apiserver principal + fence; a plugin is not one.

  5. CUSTODIAL-EVENT-PAYLOAD — the event JSON carries a live fence/claim/lease TOKEN, so a
     plugin can REPLAY it to gain custody. Events MUST be non-custodial projections — a
     read-only snapshot, never a capability.

  6. CONSUMER-APPLIES-PUBLISH — some core consumer treats a plugin-published, transition-shaped
     message as an actual work-item transition. Publishing MUST be inert w.r.t. coordination.

Two falsification layers, both stdlib-only (`python3 plugin-coordination-guardrail-check.py`):

  LAYER A — model-based mutation battery. A faithful model of the plugin seam: the SDK surface,
  the plugin NATS permission set, the relay/seam topology, the coord-mutation authority gate,
  and event payload shape. A HostilePlugin adversary runs every attack it can (call each SDK
  op, publish a forged transition, replay an event's payload for custody, write the outbox
  directly). Six checks C1–C6 ↔ AC1–AC6; the conformant baseline is GREEN on all six and the
  adversary's entire battery FAILS. A battery of guardrail-weakening mutations; EACH must be
  caught by its designated check going RED (and re-open at least one attack).

  LAYER B — file-grounded pass over PINNED real artifacts: the shipped relay ConfigMap
  (helm-chart-isi2149/templates/event-relay.yaml, k8squad@598f3f5 — publish-only + decoupled,
  no inbound consume/apply key) and the normative guardrail text-of-record in the architecture
  (§17.4 Guard 1–3 + §6.6 emit-only clause). Each detector must PASS on the shipped text and
  FLIP when the text is mutated, so the file-grounded checks have teeth on real artifacts.

Exit non-zero if any mutation survives, any attack succeeds on the conformant model, any
real-artifact invariant is violated, or any file-grounded detector fails to flip.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "helm-chart-isi2149")
SNAP_COMMIT = "598f3f5"
ARCH = os.path.join(HERE, "..", "..", "03-architecture.md")


# ══════════════════════════════════════════════════════════════════════════════════════
#  Model of the plugin seam. `mut` injects a guardrail-weakening bug. The conformant seam
#  (mut=None) is the §17.4/§6.6 contract; every field a weakening mutation might flip is
#  named here so a check can catch the flip.
# ══════════════════════════════════════════════════════════════════════════════════════

# The read/subscribe-only operations a conformant plugin SDK is allowed to expose.
READ_ONLY_OPS = {"nats_sub", "event_read", "event_ack", "replay_from"}

# Operations that MUTATE coordination/knowledge state. NONE may appear in the SDK surface.
MUTATION_OPS = {
    "claim", "lease_renew", "fence", "handoff",
    "transition_state", "complete_work_item", "outbox_publish",
}


def seam(mut=None):
    """Return the plugin-seam model. Conformant unless `mut` weakens a specific invariant."""
    m = {
        # (1) The operations the plugin SDK exposes. Conformant = read/subscribe only.
        "sdk_surface": set(READ_ONLY_OPS),
        # (2) The plugin's NATS account permissions. Conformant = SUB on ksquad.>, no PUB
        #     that re-enters coordination (own _INBOX for request-reply is not a coord subject).
        "nats_sub_allow": ["ksquad.>"],
        "nats_pub_allow": [],                       # NO publish onto the event bus
        # (3) Seam topology. Conformant = one-way: the relay tails the outbox and publishes to
        #     NATS; there is NO NATS→coord consumer that applies bus messages to the record.
        "relay_direction": "outbox->nats",
        "nats_to_coord_consumer": False,
        # (4) Who may mutate coordination state. Conformant = ONLY an authenticated apiserver
        #     principal holding the fence (§6.2/6.3). A plugin identity is never in this set.
        "coord_mutation_authorities": {"apiserver_authenticated_principal_with_fence"},
        # (5) Event payload shape. Conformant = a non-custodial projection — it carries NO live
        #     fence/claim/lease token that could be replayed to gain custody.
        "event_payload_has_custody_token": False,
        # (6) Does any core consumer apply a plugin-PUBLISHED, transition-shaped message as an
        #     actual work-item transition? Conformant = never (publishing is coord-inert).
        "consumer_applies_published_transition": False,
    }
    if mut == "sdk_add_claim":
        m["sdk_surface"].add("claim")
    elif mut == "sdk_add_transition":
        m["sdk_surface"].add("transition_state")
    elif mut == "sdk_add_outbox_publish":
        m["sdk_surface"].add("outbox_publish")
    elif mut == "nats_pub_grant":
        m["nats_pub_allow"] = ["ksquad.>"]          # plugin can now inject onto the bus
    elif mut == "relay_bidirectional":
        m["nats_to_coord_consumer"] = True          # a NATS→coord applier appears
        m["relay_direction"] = "outbox<->nats"
    elif mut == "plugin_is_authority":
        m["coord_mutation_authorities"].add("plugin_identity")
    elif mut == "custodial_payload":
        m["event_payload_has_custody_token"] = True  # fence token rides in the event JSON
    elif mut == "consumer_applies_publish":
        m["consumer_applies_published_transition"] = True
    return m


# ══════════════════════════════════════════════════════════════════════════════════════
#  HostilePlugin — the adversary. It runs against a seam model and returns, for each attack,
#  whether it SUCCEEDED in mutating coordination state. On a conformant seam every attack
#  fails; a weakening mutation is meant to re-open at least one of them.
# ══════════════════════════════════════════════════════════════════════════════════════

def attacks(s):
    """Return {attack_name: succeeded?}. Succeeded == the plugin mutated coord state."""
    res = {}

    # A1 — call an SDK mutation op directly. Succeeds iff the SDK exposes one.
    res["call_sdk_mutation"] = bool(s["sdk_surface"] & MUTATION_OPS)

    # A2 — publish a forged message onto a coordination subject at all. Succeeds iff the plugin
    #      is granted PUB on a coord subject. (Independent lock #1 on the publish path: being
    #      able to inject onto the coord bus is itself a breach of "subscribe-only", §17.4 G1.)
    res["publish_onto_coord_subject"] = any(
        p == "ksquad.>" or p.startswith("ksquad.") for p in s["nats_pub_allow"]
    )

    # A2b — have a published, transition-shaped message APPLIED as a real transition. Succeeds
    #       iff a core consumer applies plugin-published messages. (Independent lock #2 on the
    #       publish path: publishing must be coord-inert.) Moving a work item via the bus needs
    #       BOTH A2 and A2b — defense-in-depth — but each lock is independently load-bearing.
    res["published_message_applied"] = bool(s["consumer_applies_published_transition"])

    # A3 — feed a bus message back into coord via a NATS→coord consumer (bidirectional relay).
    #      Succeeds iff such a consumer exists (the seam is no longer one-way).
    res["bus_message_reenters_coord"] = bool(s["nats_to_coord_consumer"])

    # A4 — present a plugin identity as a coord mutation authority. Succeeds iff the mutation
    #      path accepts it (bypassing the apiserver-principal + fence gate).
    res["plugin_authorized_to_mutate"] = "plugin_identity" in s["coord_mutation_authorities"]

    # A5 — replay a consumed event's payload to acquire custody. Succeeds iff the event carried
    #      a live custody token (fence/claim/lease) the plugin can replay.
    res["replay_event_for_custody"] = bool(s["event_payload_has_custody_token"])

    # A6 — write the transactional outbox directly to smuggle a coord event. Succeeds iff the
    #      SDK hands the plugin an outbox-publish op (the outbox is behind the seam, not the SDK).
    res["direct_outbox_write"] = "outbox_publish" in s["sdk_surface"]

    return res


def any_attack_succeeds(mut=None):
    return any(attacks(seam(mut)).values())


# ══════════════════════════════════════════════════════════════════════════════════════
#  Checks C1–C6 ↔ AC1–AC6. Each takes the mutation under test (None = conformant baseline)
#  and returns True on a conformant seam, False on a weakened one — so a mutation is CAUGHT
#  when its designated check returns False.
# ══════════════════════════════════════════════════════════════════════════════════════

def c1_sdk_read_only(mut):
    """AC1 — the plugin SDK surface is subscribe/read-only: it exposes NO coordination-mutation
    op (claim/lease/fence/handoff/transition/complete/outbox-publish)."""
    s = seam(mut)
    return not (s["sdk_surface"] & MUTATION_OPS) and s["sdk_surface"] <= READ_ONLY_OPS


def c2_nats_subscribe_only(mut):
    """AC2 — plugin NATS credentials are subscribe-only: SUB on the event subjects, NO PUB onto
    any coord subject (nothing a plugin publishes can re-enter coordination)."""
    s = seam(mut)
    has_sub = bool(s["nats_sub_allow"])
    no_coord_pub = not any(
        p == "ksquad.>" or p.startswith("ksquad.") for p in s["nats_pub_allow"]
    )
    return has_sub and no_coord_pub


def c3_seam_one_way(mut):
    """AC3 — the event seam is ONE-WAY: relay tails the outbox → NATS; there is NO NATS→coord
    consumer, and a plugin-published message is never applied as a transition (§17.4 Guard 1)."""
    s = seam(mut)
    return (s["relay_direction"] == "outbox->nats"
            and not s["nats_to_coord_consumer"]
            and not s["consumer_applies_published_transition"])


def c4_mutation_requires_fenced_principal(mut):
    """AC4 — coordination mutation requires an authenticated apiserver principal holding the
    fence (§6.2/6.3); a plugin identity is NEVER a mutation authority (§17.4 Guard 2)."""
    s = seam(mut)
    return (s["coord_mutation_authorities"] == {"apiserver_authenticated_principal_with_fence"}
            and "plugin_identity" not in s["coord_mutation_authorities"])


def c5_events_non_custodial(mut):
    """AC5 — events are non-custodial projections: the payload carries NO live fence/claim/lease
    token that could be replayed to gain custody (custody stays in the fenced coord record)."""
    return not seam(mut)["event_payload_has_custody_token"]


def c6_adversary_battery_fails(mut):
    """AC6 — the composite structural proof: the HostilePlugin adversary runs its full attack
    battery and EVERY attack fails to mutate coordination state (§6.5 14.4 covert-channel test)."""
    return not any_attack_succeeds(mut)


CHECKS = {
    "C1": ("AC1 SDK surface subscribe/read-only",      c1_sdk_read_only),
    "C2": ("AC2 plugin NATS creds subscribe-only",     c2_nats_subscribe_only),
    "C3": ("AC3 seam one-way (no NATS→coord)",         c3_seam_one_way),
    "C4": ("AC4 mutation needs fenced apiserver principal", c4_mutation_requires_fenced_principal),
    "C5": ("AC5 events non-custodial (no token)",      c5_events_non_custodial),
    "C6": ("AC6 hostile-plugin battery all-fail",      c6_adversary_battery_fails),
}

# Mutation → the check that must catch it. Every weakening also re-opens ≥1 adversary attack,
# so C6 is a redundant backstop for the surface checks (asserted separately below).
MUTATIONS = [
    ("M1  SDK exposes claim()",                  "sdk_add_claim",          "C1"),
    ("M2  SDK exposes transition_state()",       "sdk_add_transition",     "C1"),
    ("M3  SDK exposes outbox_publish()",         "sdk_add_outbox_publish", "C1"),
    ("M4  plugin NATS creds granted PUB ksquad.>", "nats_pub_grant",       "C2"),
    ("M5  relay bidirectional (NATS→coord)",     "relay_bidirectional",    "C3"),
    ("M6  consumer applies published transition","consumer_applies_publish","C3"),
    ("M7  plugin identity is mutation authority","plugin_is_authority",    "C4"),
    ("M8  event payload carries fence token",    "custodial_payload",      "C5"),
]


def run_layer_a():
    print("=" * 92)
    print("LAYER A — model-based mutation battery (plugin-seam model + HostilePlugin adversary).")
    print("          Baseline GREEN on C1–C6; every mutation caught by its check AND re-opens ≥1 attack.")
    print("=" * 92)
    ok_all = True

    print("\n  Baseline (§17.4/§6.6-conformant plugin seam):")
    for cid, (label, fn) in CHECKS.items():
        ok = fn(None)
        ok_all &= ok
        print(f"    [{'GREEN' if ok else 'RED  '}] {cid} {label}")

    print("\n  HostilePlugin adversary battery on the conformant seam (every attack MUST fail):")
    base_attacks = attacks(seam(None))
    for name, succeeded in base_attacks.items():
        ok = not succeeded
        ok_all &= ok
        print(f"    [{'BLOCKED ' if ok else 'BREACHED'}] {name}")

    print("\n  Mutation battery (each flips its check RED AND re-opens the adversary):")
    for mlabel, mut, cid in MUTATIONS:
        label, fn = CHECKS[cid]
        caught = not fn(mut)
        reopened = any_attack_succeeds(mut)            # weakening must give the adversary a way in
        ok = caught and reopened
        ok_all &= ok
        print(f"    [{'CAUGHT ' if ok else 'SURVIVED'}] {mlabel:<42} → {cid} "
              f"{'RED' if caught else 'still GREEN'}, adversary {'in' if reopened else 'STILL OUT'}")
    return ok_all


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER B — file-grounded pass over pinned real artifacts. Each detector must (i) PASS on the
#  shipped text and (ii) FLIP when the text is mutated, so the checks have teeth on the real
#  artifacts, not just the model.
# ══════════════════════════════════════════════════════════════════════════════════════

def read_abs(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def det_relay_publish_only(t):
    """The shipped relay ConfigMap PUBLISHES (has relay.natsUrl) and carries NO inbound
    consume/apply key — it never reads a subject to mutate coord (one-way, §17.4)."""
    publishes = bool(re.search(r'relay\.natsUrl:', t))
    no_inbound = not re.search(r'relay\.(consumeSubject|applyToCoord|inboundSubject|subscribe)\b', t)
    return publishes and no_inbound


def det_relay_decoupled(t):
    """The relay is decoupled from the write path — flipping blocksWritePath/health-gate is a
    regression the ConfigMap pins as strings (isolation, §17.4)."""
    return bool(re.search(r'relay\.blocksWritePath:\s*"false"', t)
                and re.search(r'relay\.natsHealthGatesApiserver:\s*"false"', t))


def det_arch_guard_no_reenter(t):
    """§17.4 Guard 1 / §6.6 — nothing a plugin publishes on NATS re-enters coordination; the
    relay is one-way outbox→NATS, never NATS→coord."""
    c = re.sub(r"\s+", " ", t)
    return ("re-enters" in c and "one-way outbox→NATS, never" in c and "NATS→coord)" in c)


def det_arch_guard_no_fence_surface(t):
    """§17.4 Guard 2 / §6.6 — the plugin contract is read-only event consumption; the event seam
    has NO claim/lease/fence surface; custody stays in the fenced coord record."""
    c = re.sub(r"\s+", " ", t)
    return ("read-only event consumption" in c
            and "There is no plugin affordance to claim, lease, fence, hand off" in c)


def det_arch_write_out_is_public_api(t):
    """§17.4 Guard 3 — a plugin that acts on the world does so as an ordinary authored/audited
    API client (D8), outside the event seam, with NO coordination primitive."""
    c = re.sub(r"\s+", " ", t)
    return ("no coordination primitive" in c and "authored, audited API client" in c)


# (label, absolute-path, detector, (find, replace)) — the raw `find` exists verbatim in the
# shipped text; replacing it must flip the (whitespace-collapsing) detector.
FG_DETECTORS = [
    ("FG1 relay publish-only (no inbound consume)",
     os.path.join(SNAP, "templates", "event-relay.yaml"), det_relay_publish_only,
     ('relay.jetstream: "true"', 'relay.consumeSubject: "ksquad.>"')),
    ("FG2 relay decoupled from write path",
     os.path.join(SNAP, "templates", "event-relay.yaml"), det_relay_decoupled,
     ('relay.blocksWritePath: "false"', 'relay.blocksWritePath: "true"')),
    ("FG3 §17.4/§6.6 guard: publish never re-enters coord",
     ARCH, det_arch_guard_no_reenter,
     ('one-way outbox→NATS, never', 'bidirectional, and')),
    ("FG4 §17.4/§6.6 guard: read-only, no claim/lease/fence surface",
     ARCH, det_arch_guard_no_fence_surface,
     ('read-only event consumption', 'read-write coordination participation')),
    ("FG5 §17.4 Guard 3: write-out via public API, no coord primitive",
     ARCH, det_arch_write_out_is_public_api,
     ('authored, audited API client', 'lateral coordination channel')),
]


def run_layer_b():
    print("\n" + "=" * 92)
    print(f"LAYER B — file-grounded pass over pinned real artifacts (event-relay.yaml @{SNAP_COMMIT}")
    print("          + §17.4/§6.6 guardrail text-of-record in 03-architecture.md)")
    print("=" * 92)
    ok_all = True
    for label, path, det, (find_s, repl_s) in FG_DETECTORS:
        try:
            text = read_abs(path)
        except FileNotFoundError:
            print(f"  [FAIL] {label:<52} pinned artifact missing: {path}")
            ok_all = False
            continue
        shipped = det(text)
        if find_s in text:
            flipped = not det(text.replace(find_s, repl_s, 1))
        else:
            flipped = False
            print(f"  (note) mutation anchor {find_s!r} not found in {os.path.basename(path)}")
        teeth = shipped and flipped
        ok_all &= teeth
        print(f"  [{'PASS' if teeth else 'FAIL'}] {label:<52} shipped={'ok' if shipped else 'VIOLATED'}  "
              f"flips-on-mutation={'yes' if flipped else 'NO'}")
    return ok_all


def main():
    a = run_layer_a()
    b = run_layer_b()
    print("\n" + "=" * 92)
    if a and b:
        print("✓ ALL GREEN — baseline passes C1–C6; the HostilePlugin battery is fully blocked; all 8 "
              "guardrail-weakening mutations are caught and each re-opens the adversary; 5 file-grounded "
              "detectors pass on the shipped relay + §17.4/§6.6 guard text and have teeth. Story 12.4 "
              "acceptance is falsifiable.")
        return 0
    print("✗ FAILURES ABOVE — see RED / SURVIVED / BREACHED / VIOLATED rows.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
