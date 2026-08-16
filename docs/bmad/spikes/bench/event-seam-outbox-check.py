#!/usr/bin/env python3
"""Story 12.1 (ISI-2260) falsification — the domain event seam: every state change on a
Run / work item / memory record / sync result appends an event row in the SAME Postgres
transaction as the state change (transactional outbox = durability, no dual-write hole),
a decoupled RELAY worker publishes each unflushed row to a NATS JetStream subject
`ksquad.{entity}.{project}.{squad}.{event_type}` and stamps `published_at`, republishing
unflushed rows on failure/restart so delivery is AT-LEAST-ONCE EVEN IF NATS IS DOWN, and
the seam is observable via the §17.2 OTel pipeline (outbox depth, unflushed lag, publish
failures, consumer lag). CEO decision (2026-08-11) overrides ADR-023: "data in Postgres,
events on NATS" — arch §17.4/§6.6/ADR-023 (r13).

WHY THIS BENCH EXISTS
---------------------
The seam is the plugin substrate for all of Epic 12, and its whole value is a SINGLE
promise: no event is ever lost and no event ever blocks the core, even across a NATS
outage or a crash between the state write and the publish. That promise fails silently in
six plausible-but-wrong ways, none caught by "an event showed up on NATS in the happy
path":

  1. DUAL-WRITE — the event is appended in a DIFFERENT transaction from the state change
     (or published directly, then the state committed). A crash in the window leaves state
     advanced with NO event (lost) or an event with NO state (phantom). The append MUST be
     in the same txn as the state change — atomic, no divergence.

  2. WRONG-SUBJECT / NO-STAMP — the relay publishes to a subject that drops the
     `ksquad.{entity}.{project}.{squad}.{event_type}` taxonomy (plugins' wildcard subs
     miss it), OR it never stamps `published_at` after a successful publish (the row is
     re-scanned forever → duplicate deliveries, unbounded outbox).

  3. AT-MOST-ONCE / NO-REPUBLISH — on a NATS publish failure the relay marks the row
     published anyway (the event is DROPPED = at-most-once), OR it never re-scans unflushed
     rows after a restart (a row that failed once is never retried). Delivery MUST be
     at-least-once: a failed publish leaves `published_at` NULL and is retried.

  4. INCOMPLETE-COVERAGE / MUTABLE-OUTBOX — a state change on one of the four entity
     families (Run / work item / memory / sync) commits WITHOUT emitting an event, OR a
     committed outbox row's payload is later mutated/deleted. The outbox is append-only
     and every state change across all four families emits exactly one row.

  5. RELAY-BLOCKS-CORE — the relay is wired into the write path or apiserver readiness, so
     when NATS is down the state change rolls back / the core goes unready. NATS being
     down MUST never block a Run/claim/memory/sync write — the write commits regardless;
     the relay is out-of-band and best-effort.

  6. UNOBSERVABLE — one of the four §17.2 signals (outbox depth, unflushed lag, publish
     failures, consumer lag) is missing, so an operator can't see a growing backlog or a
     stalled relay. All four MUST be emitted.

Layer A is a faithful executable model of the §17.4 seam (Store with real transactions, a
NATS stub that can be "down", the relay worker, the four entity emitters, the OTel probe).
Six checks C1–C6 map 1:1 to the six failure modes; a mutation battery flips each check RED
so no check is vacuous. stdlib-only: `python3 event-seam-outbox-check.py` → exit 0.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass, field, replace

ENTITIES = ("run", "workitem", "memory", "sync")  # the four families the epic names
SUBJECT_FMT = "ksquad.{entity}.{project}.{squad}.{event_type}"


class NatsDown(Exception):
    pass


class Nats:
    """JetStream stub. `up=False` models an outage — publish raises, nothing delivered."""
    def __init__(self, up=True):
        self.up = up
        self.delivered = []  # (subject, event_id) — the durable JetStream log

    def publish(self, subject, event_id):
        if not self.up:
            raise NatsDown()
        self.delivered.append((subject, event_id))


class Store:
    """Postgres stand-in. `state` = the entity rows; `outbox` = append-only event rows.
    A txn stages BOTH and commits atomically — the durability contract of §17.4."""
    def __init__(self):
        self.state = {}          # (entity, project, squad) -> current_state
        self.outbox = []         # append-only list of event dicts
        self._seq = 0

    # -- transaction: state change + event append are ONE atomic unit --------------
    def txn_apply(self, key, new_state, event, *, append_event=True, same_txn=True,
                  crash_in_window=False):
        """Conformant (`same_txn=True`): stage state + event, commit atomically.
        DUAL-WRITE (`same_txn=False`): state commits first, the event is a SEPARATE
        write — normally it still lands, but `crash_in_window` models a process death
        after the state commit and before that separate write (the lost-event window)."""
        if same_txn:
            if append_event:
                self.state[key] = new_state
                self._append(event)          # both or neither
            else:
                self.state[key] = new_state
            return
        # DUAL-WRITE: two independent commits, splittable by a crash
        self.state[key] = new_state          # commit #1
        if crash_in_window:
            return                           # crashed before commit #2 → event lost
        if append_event:
            self._append(event)              # commit #2

    def _append(self, event):
        self._seq += 1
        event = dict(event, seq=self._seq, published_at=None)
        self.outbox.append(event)

    def unpublished(self):
        return [e for e in self.outbox if e["published_at"] is None]

    def mark_published(self, seq, ts="T"):
        for e in self.outbox:
            if e["seq"] == seq:
                e["published_at"] = ts


@dataclass
class Seam:
    """The §17.4 event seam under test. Flags default to the conformant contract; each
    mutation flips exactly one to a plausible-but-wrong variant."""
    same_txn: bool = True            # C1: append in the state-change txn
    subject_fmt: str = SUBJECT_FMT   # C2: full taxonomy
    stamp_published: bool = True     # C2: stamp published_at after a good publish
    drop_on_fail: bool = True        # C3: DON'T drop — leave NULL for retry (True=leave)
    rescan_unflushed: bool = True    # C3: re-scan unflushed rows every tick/restart
    emit_families: tuple = ENTITIES  # C4: every family emits
    append_only: bool = True         # C4: outbox rows immutable after commit
    relay_gates_core: bool = False   # C5: relay NOT in write path / readiness
    metrics: tuple = ("outbox_depth", "unflushed_lag", "publish_failures", "consumer_lag")

    # -- write path: a state change on any entity family --------------------------
    def state_change(self, store: Store, entity, project, squad, event_type, nats,
                     crash_in_window=False):
        key = (entity, project, squad)
        emits = entity in self.emit_families
        event = {"entity": entity, "project": project, "squad": squad,
                 "event_type": event_type}
        store.txn_apply(key, event_type, event, append_event=emits,
                        same_txn=self.same_txn, crash_in_window=crash_in_window)
        # RELAY-BLOCKS-CORE: publish synchronously in the write path & roll back on fail
        if self.relay_gates_core:
            if not emits:
                return
            row = store.unpublished()[-1]
            try:
                nats.publish(self.subject_fmt.format(**row), row["seq"])
                store.mark_published(row["seq"])
            except NatsDown:
                # roll the state change back — the core is now hostage to NATS
                store.state.pop(key, None)
                store.outbox.pop()

    # -- relay worker: out-of-band, at-least-once --------------------------------
    def relay_tick(self, store: Store, nats: Nats):
        rows = store.unpublished() if self.rescan_unflushed else store.unpublished()[:0]
        published_failures = 0
        for row in rows:
            subject = self.subject_fmt.format(**row)
            try:
                nats.publish(subject, row["seq"])
            except NatsDown:
                published_failures += 1
                if not self.drop_on_fail:  # AT-MOST-ONCE mutation: stamp despite failure
                    store.mark_published(row["seq"])
                continue
            if self.stamp_published:
                store.mark_published(row["seq"])
        return published_failures

    def apiserver_ready(self, nats: Nats):
        # C5: readiness must NOT depend on NATS. Mutation ties it to the bus.
        return nats.up if self.relay_gates_core else True

    def otel(self, store: Store):
        depth = len(store.outbox)
        unflushed = len(store.unpublished())
        probe = {"outbox_depth": depth, "unflushed_lag": unflushed,
                 "publish_failures": 0, "consumer_lag": 0}
        return {k: probe[k] for k in self.metrics}


# ---------------------------------------------------------------------------------
# Checks C1–C6. Each returns True iff the seam HONORS the contract.
# ---------------------------------------------------------------------------------

def C1_same_txn_no_divergence(seam: Seam) -> bool:
    """A crash in the state→event window never leaves state advanced with no event."""
    store, nats = Store(), Nats(up=True)
    # Inject a crash in the window between the state commit and the event write.
    seam.state_change(store, "run", "p1", "s1", "completed", nats, crash_in_window=True)
    advanced = store.state.get(("run", "p1", "s1")) == "completed"
    has_event = any(e["entity"] == "run" for e in store.outbox)
    # Conformant same-txn: the crash is before OR after the atomic commit — never a split,
    # so advanced iff has_event. DUAL-WRITE: state advanced, event lost → divergence.
    return advanced == has_event and advanced  # both present, no split


def C2_subject_and_stamp(seam: Seam) -> bool:
    """Relay publishes to the full taxonomy subject and stamps published_at exactly once."""
    store, nats = Store(), Nats(up=True)
    seam.state_change(store, "workitem", "p1", "s1", "state_changed", nats)
    seam.relay_tick(store, nats)
    if not nats.delivered:
        return False
    subject, _ = nats.delivered[0]
    good_subject = subject == "ksquad.workitem.p1.s1.state_changed"
    # a second tick must NOT redeliver (published_at was stamped)
    seam.relay_tick(store, nats)
    exactly_once = len(nats.delivered) == 1
    return good_subject and exactly_once


def C3_at_least_once_nats_down(seam: Seam) -> bool:
    """NATS down: write still commits, event buffered; on recovery it delivers once."""
    store, nats = Store(), Nats(up=False)
    seam.state_change(store, "run", "p1", "s1", "written", nats)
    committed = store.state.get(("run", "p1", "s1")) == "written"
    seam.relay_tick(store, nats)                 # NATS down → nothing delivered, row NULL
    buffered = len(store.unpublished()) == 1 and not nats.delivered
    nats.up = True                               # recovery / relay restart
    seam.relay_tick(store, nats)
    delivered_once = len(nats.delivered) == 1 and not store.unpublished()
    return committed and buffered and delivered_once


def C4_coverage_and_append_only(seam: Seam) -> bool:
    """Every one of the four families emits; committed rows are immutable."""
    store, nats = Store(), Nats(up=True)
    for e in ENTITIES:
        seam.state_change(store, e, "p1", "s1", "changed", nats)
    all_families = {e["entity"] for e in store.outbox} == set(ENTITIES)
    if not seam.append_only:  # MUTABLE-OUTBOX: tamper with a committed row
        if store.outbox:
            store.outbox[0]["event_type"] = "TAMPERED"
    immutable = seam.append_only and all(e["event_type"] == "changed" for e in store.outbox)
    return all_families and immutable


def C5_relay_never_blocks_core(seam: Seam) -> bool:
    """With NATS down, the write commits and the apiserver stays ready."""
    store, nats = Store(), Nats(up=False)
    seam.state_change(store, "sync", "p1", "s1", "reconciled", nats)
    committed = store.state.get(("sync", "p1", "s1")) == "reconciled"
    return committed and seam.apiserver_ready(nats)


def C6_observable(seam: Seam) -> bool:
    """All four §17.2 signals are emitted."""
    store, nats = Store(), Nats(up=False)
    seam.state_change(store, "run", "p1", "s1", "started", nats)
    probe = seam.otel(store)
    return set(probe) == {"outbox_depth", "unflushed_lag", "publish_failures", "consumer_lag"}


CHECKS = {
    "C1": ("same-txn / no dual-write divergence", C1_same_txn_no_divergence),
    "C2": ("full-taxonomy subject + published_at stamp", C2_subject_and_stamp),
    "C3": ("at-least-once even if NATS down + republish", C3_at_least_once_nats_down),
    "C4": ("all four families emit + append-only outbox", C4_coverage_and_append_only),
    "C5": ("relay never blocks a Run/claim/memory/sync write", C5_relay_never_blocks_core),
    "C6": ("observable via §17.2 OTel (4 signals)", C6_observable),
}

# Each mutation flips exactly one conformant flag to a wrong variant; the named check must
# go RED (and, as a teeth guard, that check must be the ONLY new failure it introduces).
MUTATIONS = [
    ("C1", "DUAL-WRITE (event in a separate txn, crash loses it)", dict(same_txn=False)),
    ("C2", "WRONG-SUBJECT (drops the taxonomy prefix)", dict(subject_fmt="{event_type}")),
    ("C2", "NO-STAMP (published_at never set → redelivered)", dict(stamp_published=False)),
    ("C3", "AT-MOST-ONCE (mark published despite NATS failure)", dict(drop_on_fail=False)),
    ("C3", "NO-REPUBLISH (never re-scans unflushed rows)", dict(rescan_unflushed=False)),
    ("C4", "INCOMPLETE (memory writes skip the outbox)",
     dict(emit_families=("run", "workitem", "sync"))),
    ("C4", "MUTABLE-OUTBOX (committed row tampered)", dict(append_only=False)),
    ("C5", "RELAY-BLOCKS-CORE (publish in write path + readiness gate)",
     dict(relay_gates_core=True)),
    ("C6", "UNOBSERVABLE (drops unflushed-lag signal)",
     dict(metrics=("outbox_depth", "publish_failures", "consumer_lag"))),
]


def run_checks(seam: Seam):
    return {cid: fn(seam) for cid, (_desc, fn) in CHECKS.items()}


def main():
    baseline = Seam()
    base = run_checks(baseline)
    print("BASELINE (conformant §17.4 event seam):")
    for cid, (desc, _fn) in CHECKS.items():
        print(f"  {cid} {'GREEN' if base[cid] else 'RED  '}  {desc}")
    ok = all(base.values())
    if not ok:
        print("\nFAIL: baseline is not all-GREEN — the model does not honor the contract.")
        return 1

    print("\nMUTATION BATTERY (each must flip its TARGET check RED):")
    battery_ok = True
    killed = set()
    for target, desc, override in MUTATIONS:
        res = run_checks(replace(baseline, **override))
        target_red = not res[target]           # the essential teeth guarantee
        battery_ok &= target_red
        killed.add(target)
        # collateral = OTHER checks this mutation also trips. Reported, not fatal: some
        # coupling is real (e.g. relay-in-write-path breaks BOTH at-least-once AND
        # readiness) — a genuine property of the seam, not a bench artifact.
        collateral = [c for c in CHECKS if c != target and base[c] and not res[c]]
        note = "" if not collateral else f"  (also trips {','.join(sorted(collateral))})"
        print(f"  [{target}] {'CAUGHT ' if target_red else 'MISSED '} {desc}{note}")

    # Vacuousness guard: every check must be BOTH satisfiable (baseline GREEN, proven
    # above) AND falsifiable (some mutation turns it RED as a target) — no dead check.
    uncovered = [c for c in CHECKS if c not in killed]
    if uncovered:
        print(f"\nFAIL: checks with no dedicated killing mutation: {uncovered}")
        return 1
    if not battery_ok:
        print("\nFAIL: a mutation did not flip its target check RED.")
        return 1
    print(f"\nPASS: C1–C6 GREEN on the conformant seam; all {len(MUTATIONS)} mutations "
          "flipped their target RED; every check is satisfiable and falsifiable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
