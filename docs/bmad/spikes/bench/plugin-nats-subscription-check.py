#!/usr/bin/env python3
"""Story 12.2 (ISI-2261) falsification — the PLUGIN-FACING SUBSCRIBE contract of the event
seam. Given the NATS connection + the ksquad.{entity}.{project}.{squad}.{event_type} subject
taxonomy, a plugin subscribes with `nats_sub("ksquad.run.*.*.completed")` and receives event
JSON with NATS WILDCARD flexibility and JetStream REPLAY/CATCH-UP for events missed while
offline; its config + outbound credentials come from per-user Secret refs (BYO, Epic 7); and a
failing/dead/absent plugin — or NATS being down — can NEVER block or slow the core (the relay
is decoupled from the write path; the durable Postgres outbox buffers). arch §17.4 (Subject
taxonomy / Plugin model / Guard 1-3) + epics row 12.2.

WHY THIS BENCH EXISTS
---------------------
12.1 pinned the PRODUCER half (same-txn outbox append → relay → NATS, at-least-once). 12.2 is
the CONSUMER half: the plugin-facing API is `nats_sub`, NOT a bespoke SDK/outbox contract (the
CEO plugin-simplicity goal). A subscribe seam is only real if it is FALSIFIABLE — a
plausible-but-wrong one that still "delivers some events" can silently drop the guarantees the
epic's acceptance names. Five ways it silently breaks, none caught by "an event arrived":

  1. NO-WILDCARD / BESPOKE-SDK — the API forces exact subjects (a plugin can't say
     `ksquad.run.*.*.completed`), or replaces `nats_sub` with an outbox-consumer framework the
     plugin dev must implement (poll/dedup/cursors). The plugin-facing API MUST be `nats_sub`
     with NATS wildcard flexibility (`*` one token, `>` tail).  → C1

  2. NO-REPLAY — the subscription binds CORE-NATS fire-and-forget, or an EPHEMERAL JetStream
     consumer with no durable cursor: events published while the plugin was offline are lost,
     and a restart re-reads from "now". A plugin MUST catch up on what it missed via a DURABLE
     JetStream consumer.  → C2

  3. SHARED-CRED / INLINE-SECRET — the plugin's NATS account (and any outbound creds) come from
     a shared master credential or an inline literal instead of per-user Secret refs declared
     per Project/squad. Config + creds MUST be per-user Secret refs (BYO, Epic 7 §11).  → C3

  4. PUB-GRANT / CUSTODIAL-PAYLOAD — the plugin's NATS creds carry a PUB grant on coord
     subjects, or the event JSON carries a live fence/claim TOKEN a plugin could replay for
     custody. Plugin creds MUST be subscribe-only and events MUST be non-custodial read-only
     projections (12.4 owns the full guardrail; 12.2 pins that the subscribe API it introduces
     adds no publish/mutate affordance).  → C4

  5. IN-WRITE-PATH / BACKPRESSURE / LIVENESS-GATE — the subscribe path is wired so a stuck,
     crashed, or absent plugin (or a fully-down NATS) applies backpressure to the relay/write
     path or gates apiserver liveness. The plugin MUST run out-of-process, never in the
     reconcile path; NATS-down/plugin-dead delays fan-out only, never a Run/claim/write.  → C5

Two falsification layers, both stdlib-only (`python3 plugin-nats-subscription-check.py`):

  LAYER A — model-based mutation battery. A faithful model of the subscribe seam: a JetStream
  with retained messages + durable consumer cursors + NATS wildcard matching, a plugin
  subscribe API (`nats_sub`), the plugin credential/config source, the creds permission set +
  event payload shape, and the out-of-process isolation of a core write. Five checks C1-C5 ↔
  AC1-AC5; the §17.4-conformant baseline is GREEN on all five. A mutation battery — EACH
  mutation must flip its designated check RED (genuine coupling is reported, not hidden).

  LAYER B — file-grounded pass over PINNED real artifacts: the shipped relay ConfigMap
  (helm-chart-isi2149/templates/event-relay.yaml, k8squad@598f3f5) whose subject taxonomy
  prefix + decoupling flags are the producer contract the subscribe side mirrors, and the
  normative subscribe text-of-record in the architecture (§17.4: `nats_sub`, wildcard subjects,
  JetStream replay/catch-up, per-user Secret refs, out-of-process, subscribe-only/read-only).
  Each detector must PASS on the shipped text and FLIP when the text is mutated.

Exit non-zero if any mutation survives, any check is vacuous (satisfiable but not falsifiable),
any real-artifact invariant is violated, or any file-grounded detector fails to flip.
"""
import copy
import os
import re
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
ARCH = os.path.normpath(os.path.join(REPO, "..", "..", "03-architecture.md"))
RELAY_CM = os.path.join(REPO, "helm-chart-isi2149", "templates", "event-relay.yaml")

# ── NATS subject wildcard matching (the AC1 "wildcard flexibility") ──────────────────────────
def nats_match(filt, subject):
    """NATS semantics: '.'-delimited tokens; '*' matches exactly one token; '>' matches one or
    more trailing tokens and must be the last token of the filter."""
    f = filt.split(".")
    s = subject.split(".")
    for i, tok in enumerate(f):
        if tok == ">":
            return i < len(s)          # '>' must cover at least one token
        if i >= len(s):
            return False
        if tok != "*" and tok != s[i]:
            return False
    return len(f) == len(s)


# ── A minimal-but-faithful JetStream + subscribe seam ───────────────────────────────────────
class JetStream:
    """Retains published messages (JetStream = catch-up buffer) and tracks a per-durable
    cursor, so a returning plugin replays what it missed. Ephemeral (durable=None) always
    starts at 'now' → no catch-up."""
    def __init__(self, durable_supported=True, retain=True):
        self.log = []                  # [(subject, payload_dict)]
        self.cursors = {}              # durable_name -> next unread index
        self.durable_supported = durable_supported
        self.retain = retain

    def publish(self, subject, payload):
        if self.retain:
            self.log.append((subject, payload))

    def subscribe(self, durable, filt):
        """Return every retained message matching `filt` since this durable's cursor, and
        advance the cursor. Ephemeral/core-NATS: start at end, deliver nothing retained."""
        if not self.durable_supported or durable is None:
            # fire-and-forget: only future live messages; nothing replayed
            self.cursors["__ephemeral__"] = len(self.log)
            return []
        start = self.cursors.get(durable, 0)
        out = [(subj, pl) for subj, pl in self.log[start:] if nats_match(filt, subj)]
        self.cursors[durable] = len(self.log)
        return out


def make_config():
    """The §17.4-conformant baseline subscribe contract."""
    return {
        "api": "nats_sub",             # plugin-facing API (not a bespoke outbox SDK)
        "wildcard": True,              # nats_sub accepts wildcard filters
        "jetstream_durable": True,     # durable JetStream consumer (replay/catch-up)
        "cred_source": "per_user_secret_ref",   # BYO, Epic 7 §11
        "config_scope": "per_project_squad",     # declared per Project/squad
        "cred_pub_subjects": [],       # subscribe-only: NO pub grant
        "payload_custodial": False,    # events are non-custodial projections (no token)
        "out_of_process": True,        # sidecar/service, never in-process reconcile
        "in_reconcile_path": False,    # not wired into the write txn
        "nats_gates_liveness": False,  # apiserver readiness never references NATS/plugin
    }


COORD_SUBJECT = "ksquad.workitem.projectX.squad1.claimed"


# ── C1..C5 — each returns True (GREEN) iff the AC holds for `cfg` ────────────────────────────
def c1_wildcard_subscribe(cfg):
    """AC1: plugin subscribes with `nats_sub` + NATS wildcard and receives matching event JSON;
    a non-matching subject is not delivered."""
    if cfg["api"] != "nats_sub":
        return False                   # bespoke outbox-consumer SDK, not nats_sub
    js = JetStream()
    js.publish("ksquad.run.projectX.squad1.completed", {"kind": "run", "state": "completed"})
    js.publish("ksquad.run.projectX.squad1.failed", {"kind": "run", "state": "failed"})
    filt = "ksquad.run.*.*.completed" if cfg["wildcard"] else "ksquad.run.projectX.squad1.completed"
    got = js.subscribe("plugin-a", filt)
    # must receive the completed event JSON ...
    if not any(pl.get("state") == "completed" for _, pl in got):
        return False
    # ... and NOT the failed one (subject discrimination) ...
    if any(pl.get("state") == "failed" for _, pl in got):
        return False
    # ... and wildcard flexibility must actually be exercisable: a broad filter matches many.
    if not cfg["wildcard"]:
        return False
    broad = js.subscribe("plugin-b", "ksquad.run.projectX.>")
    return len(broad) == 2             # '>' catches completed + failed

def c2_jetstream_replay(cfg):
    """AC2: events published while the plugin was OFFLINE are replayed on reconnect (durable
    JetStream consumer), not lost."""
    js = JetStream(durable_supported=cfg["jetstream_durable"])
    durable = "plugin-a" if cfg["jetstream_durable"] else None
    # first connect, consume what exists (nothing yet)
    js.subscribe(durable, "ksquad.run.>")
    # plugin goes offline; two events happen
    js.publish("ksquad.run.projectX.squad1.completed", {"n": 1})
    js.publish("ksquad.run.projectY.squad2.completed", {"n": 2})
    # plugin reconnects with the SAME durable and must catch up on both
    missed = js.subscribe(durable, "ksquad.run.>")
    return len(missed) == 2

def c3_byo_secret_refs(cfg):
    """AC3: plugin config + outbound creds come from per-user Secret refs declared per
    Project/squad — never a shared master credential, never inline."""
    return (cfg["cred_source"] == "per_user_secret_ref"
            and cfg["config_scope"] == "per_project_squad")

def c4_subscribe_only_noncustodial(cfg):
    """AC4: plugin creds are subscribe-only (no PUB on coord subjects) and events are
    non-custodial (no replayable token) — the subscribe API adds no publish/mutate affordance."""
    # subscribe-only: no pub grant that matches any coord subject
    for grant in cfg["cred_pub_subjects"]:
        if nats_match(grant, COORD_SUBJECT):
            return False
    # non-custodial: the delivered payload carries no fence/claim/lease token
    payload = {"kind": "workitem", "state": "claimed"}
    if cfg["payload_custodial"]:
        payload["fence_token"] = 42    # a capability a plugin could replay for custody
    return not any(k in payload for k in ("fence_token", "claim_token", "lease_token"))

def c5_never_blocks_core(cfg):
    """AC5: a stuck/dead/absent plugin — or NATS wholly down — cannot block or slow a
    Run/claim/write, and cannot gate apiserver liveness. Out-of-process, decoupled."""
    def core_write(nats_down, plugin_stuck):
        # committed unless the seam was (mis)wired INTO the write path
        blocked = cfg["in_reconcile_path"] and (nats_down or plugin_stuck)
        committed = not blocked
        ready = not (cfg["nats_gates_liveness"] and nats_down)
        return committed, ready
    if not cfg["out_of_process"]:
        return False
    # worst case: NATS down AND the plugin consumer wedged
    committed, ready = core_write(nats_down=True, plugin_stuck=True)
    return committed and ready


CHECKS = [
    ("C1", "nats_sub + wildcard subscribe", c1_wildcard_subscribe),
    ("C2", "JetStream replay/catch-up", c2_jetstream_replay),
    ("C3", "BYO per-user Secret refs", c3_byo_secret_refs),
    ("C4", "subscribe-only + non-custodial", c4_subscribe_only_noncustodial),
    ("C5", "never blocks/slows the core", c5_never_blocks_core),
]


def run_checks(cfg):
    return {cid: fn(cfg) for cid, _, fn in CHECKS}


# ── mutations: each flips its target check(s) RED ───────────────────────────────────────────
def mut_no_wildcard(c):      c["wildcard"] = False
def mut_bespoke_sdk(c):      c["api"] = "outbox_consumer_sdk"
def mut_core_nats(c):        c["jetstream_durable"] = False
def mut_shared_cred(c):      c["cred_source"] = "shared_master"
def mut_inline_secret(c):    c["cred_source"] = "inline_literal"
def mut_global_scope(c):     c["config_scope"] = "global"
def mut_pub_grant(c):        c["cred_pub_subjects"] = ["ksquad.>"]
def mut_custodial(c):        c["payload_custodial"] = True
def mut_in_write_path(c):    c["in_reconcile_path"] = True
def mut_in_process(c):       c["out_of_process"] = False
def mut_liveness_gate(c):    c["nats_gates_liveness"] = True

MUTATIONS = [
    ("M1  NO-WILDCARD (exact subjects only)",        mut_no_wildcard,   {"C1"}),
    ("M2  BESPOKE-OUTBOX-SDK (not nats_sub)",        mut_bespoke_sdk,   {"C1"}),
    ("M3  CORE-NATS / EPHEMERAL (no replay)",        mut_core_nats,     {"C2"}),
    ("M4  SHARED-MASTER-CRED",                        mut_shared_cred,   {"C3"}),
    ("M5  INLINE-SECRET",                             mut_inline_secret, {"C3"}),
    ("M6  GLOBAL-CONFIG-SCOPE (not per-squad)",       mut_global_scope,  {"C3"}),
    ("M7  PUB-GRANT on coord subjects",               mut_pub_grant,     {"C4"}),
    ("M8  CUSTODIAL-PAYLOAD (replayable token)",      mut_custodial,     {"C4"}),
    ("M9  IN-RECONCILE-PATH (blocks write)",          mut_in_write_path, {"C5"}),
    ("M10 IN-PROCESS (in reconcile)",                 mut_in_process,    {"C5"}),
    ("M11 NATS-GATES-LIVENESS",                       mut_liveness_gate, {"C5"}),
]


# ── Layer B — file-grounded detectors over the shipped relay ConfigMap + arch §17.4 ─────────
def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()

def fg_detectors():
    """(name, text, predicate, mutate) — predicate PASSes on shipped text, FLIPs on mutate."""
    cm = read(RELAY_CM)
    arch = read(ARCH)
    return [
        ("FG1 relay subject taxonomy prefix (the subscribe surface mirrors)",
         cm, lambda t: "relay.subjectPrefix" in t and "{entity}.{project}.{squad}.{event_type}" in t,
         lambda t: t.replace("relay.subjectPrefix", "relay.noSubjects")),
        ("FG2 relay decoupled / never blocks write path",
         cm, lambda t: 'relay.blocksWritePath: "false"' in t and 'relay.decoupled: "true"' in t,
         lambda t: t.replace('relay.blocksWritePath: "false"', 'relay.blocksWritePath: "true"')),
        ("FG3 §17.4 plugin API is nats_sub + wildcard subjects",
         arch, lambda t: "nats_sub" in t and "wildcard" in t.lower(),
         lambda t: t.replace("nats_sub", "outbox_consumer")),
        ("FG4 §17.4 JetStream replay/catch-up for missed events",
         arch, lambda t: bool(re.search(r"replay/catch[ -]?up", t)) or "replay" in t.lower(),
         lambda t: t.replace("replay", "____").replace("catch up", "____").replace("catch-up", "____")),
        ("FG5 §17.4 per-user Secret refs + out-of-process + read-only",
         arch, lambda t: ("per-user Secret" in t and "out-of-process" in t
                          and "read-only" in t.lower()),
         lambda t: t.replace("per-user Secret", "shared master credential")),
    ]


def main():
    ok = True
    print("Story 12.2 (ISI-2261) — plugin NATS subscription falsification\n")

    # Layer A baseline
    base = run_checks(make_config())
    print("LAYER A — baseline (§17.4-conformant subscribe contract):")
    for cid, desc, _ in CHECKS:
        mark = "GREEN" if base[cid] else "RED  "
        print(f"  [{mark}] {cid} {desc}")
        if not base[cid]:
            ok = False
    if not all(base.values()):
        print("  !! baseline not fully GREEN — contract model is wrong.")

    # Layer A mutation battery — each must flip exactly its target(s) RED
    print("\nLAYER A — broken-seam mutation battery (each must flip its target RED):")
    for name, mutate, targets in MUTATIONS:
        cfg = copy.deepcopy(make_config())
        mutate(cfg)
        res = run_checks(cfg)
        reds = {cid for cid in res if not res[cid]}
        caught = targets.issubset(reds)
        # no collateral GREEN->stays: at least the target flips; report extra reds as coupling
        extra = reds - targets
        status = "caught" if caught else "SURVIVED"
        coupling = f"  (+coupled RED: {sorted(extra)})" if extra else ""
        print(f"  [{'OK ' if caught else 'FAIL'}] {name:44s} -> RED {sorted(targets)} [{status}]{coupling}")
        if not caught:
            ok = False

    # vacuity guard — every check must be both satisfiable (baseline GREEN) and falsifiable
    falsifiable = set()
    for _, mutate, targets in MUTATIONS:
        cfg = copy.deepcopy(make_config()); mutate(cfg)
        res = run_checks(cfg)
        for cid in targets:
            if not res[cid]:
                falsifiable.add(cid)
    print("\nVacuity guard — each check satisfiable AND falsifiable:")
    for cid, _, _ in CHECKS:
        good = base[cid] and cid in falsifiable
        print(f"  [{'OK ' if good else 'FAIL'}] {cid}: satisfiable={base[cid]} falsifiable={cid in falsifiable}")
        if not good:
            ok = False

    # Layer B — file-grounded detectors
    print("\nLAYER B — file-grounded detectors (pass on shipped text, flip on mutation):")
    for name, text, pred, mutate in fg_detectors():
        passes = pred(text)
        flips = not pred(mutate(text))
        good = passes and flips
        print(f"  [{'OK ' if good else 'FAIL'}] {name:58s} pass={passes} flips={flips}")
        if not good:
            ok = False

    print("\n" + ("ALL TEETH HOLD — exit 0" if ok else "TEETH BROKEN — exit 1"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
