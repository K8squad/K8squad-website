#!/usr/bin/env python3
"""
audit-trail-check.py — Story 2.6 falsification (audit trail = queryable coordination record).

The §6.5 load-bearing invariant: the `coord` schema *is* the audit log. Every coordination
mutation — checkout (claim acquire/renew/release), comment, artifact registration, state
transition, completion — writes ONE immutable append-only `coord.audit_log` row IN THE SAME
TRANSACTION as the mutation itself (§6.5/§6.6). The row records who (principal +
initiated_by_user_id §12.4) / what (event + kind + target) / when (monotonic bigserial +
timestamp + fence) / result (outcome). The apiserver exposes a read-only, RBAC-scoped query
API filterable by work item / actor / time (FR-B4/D4/NFR-OBS1). The audit table is
AUDIT-ONLY — the high-volume shim Run-trace firehose (tool_call|llm_call|build_output|error,
§10.1) does NOT land here (ADR-040); it rides SSE + OTel (§17.2).

The crux for an *audit trail* is COMPLETENESS-BY-CONSTRUCTION: a mutation and its audit row
must be atomic (co-committed), so no crash can ever leave a durable coordination mutation with
no audit row (a "hole" that makes who/what/when/result non-guaranteed). A naive design that
logs the audit as a separate best-effort write AFTER the mutation commits loses rows on a
crash-between — that is a correctness failure for an audit trail, not a bug ticket.

Differential falsification (same discipline as handoff-advisory-check.py / reclaim-fencing-check.py):
  (A) NAIVE separate-log audit — the audit is a best-effort append AFTER the mutation commits.
      A crash in the between-window leaves a durable mutation with NO audit row (a hole). MUST
      detectably orphan a mutation (teeth); if it ever stops, the harness proves nothing.
  (B) §6.5 CO-COMMIT audit — mutation + audit row share one transaction: both commit or both
      roll back. The same crash window leaves ZERO orphans — every durable mutation has its
      audit row; a rolled-back mutation has none. Completeness holds by construction.
  (C) immutability (§6.5, structural) — UPDATE/DELETE/TRUNCATE on a committed audit row are all
      rejected (append-only trigger); the naive mutable log lets who-did-what be edited/erased
      (teeth). The bigserial sequence is monotonic + gap-free under the coordination-only stream.
  (D) queryability (FR-B4/AC4) — the read API filters by work_item / actor / time (and their
      intersection), returns who/what/when/result on every row, is complete (every event kind
      for a work item is returned), and is RBAC-scoped (§12.3 deny-by-default drops rows outside
      the caller's project membership).
  (E) audit-only, NOT the trace firehose (ADR-040/AC5) — coordination events land in the audit
      trail; the shim firehose (tool_call|llm_call|...) does NOT. A naive design that dumps the
      firehose into audit_log is shown to pollute the monotonic coordination sequence and break
      the bounded-volume immutability the audit relies on (teeth).

stdlib-only; `python3 audit-trail-check.py`. Exit non-zero if (A) stops orphaning, or if (B)-(E)
ever leave a mutation with no audit row / let an audit row be mutated / drop a who/what/when/result
field / mis-scope a query / let firehose rows enter the audit trail. Models Postgres row + txn
semantics in-process; real-Postgres promotion rides the Story 2.7 chaos harness.
"""

# ---- the bounded set of coordination events the audit trail records (§6.5) ----
# checkout ≡ claim (per Story 2.1 name mapping); each is a low-volume coordination event.
COORD_EVENTS = frozenset({
    "claim_acquired", "claim_renewed", "claim_released",
    "comment_added", "artifact_registered", "state_transition", "run_completed",
})
# The high-volume shim Run-trace firehose (§10.1) — NEVER persisted to audit_log (ADR-040).
FIREHOSE_EVENTS = frozenset({"tool_call", "llm_call", "build_output", "error"})

# who/what/when/result — the four columns FR-B4 requires on every audit row.
AUDIT_REQUIRED = frozenset({"who", "what", "when", "result"})


class CrashBetween(Exception):
    """Injected between the durable mutation and the (separate) audit write."""


class AuditTrail:
    """In-process model of coord mutations + coord.audit_log + the read query API.

    separate_log=True  → the WRONG design: the mutation commits first, THEN a best-effort audit
                         append runs. A crash in the between-window orphans the mutation (hazard A).
    mutable_log=True   → the WRONG design: audit rows accept UPDATE/DELETE/TRUNCATE (hazard C).
    firehose_in_audit=True → the WRONG design: shim firehose rows are appended to audit_log,
                         polluting the monotonic coordination sequence (hazard E).
    """

    def __init__(self, separate_log=False, mutable_log=False, firehose_in_audit=False):
        self.separate_log = separate_log
        self.mutable_log = mutable_log
        self.firehose_in_audit = firehose_in_audit
        self.now = 0
        self._seq = 0
        # the durable coordination mutations (claims/comments/artifacts/transitions/completions)
        self.mutations = []          # each: {"event", "work_item", ...}
        # coord.audit_log — append-only, monotonic bigserial
        self.audit = []              # each: {seq, ts, who, what, when, result, work_item}

    def tick(self, dt=1):
        self.now += dt

    def _next_seq(self):
        self._seq += 1               # monotonic, never reset/reused (§6.1/§6.5)
        return self._seq

    def _audit_row(self, event, work_item, principal, initiated_by_user_id, fence, result):
        assert event in COORD_EVENTS, f"only coordination events belong in audit_log: {event}"
        seq = self._next_seq()
        return {
            "seq": seq,
            "ts": self.now,
            # who: the acting principal + the human on whose behalf (§12.4)
            "who": {"principal": principal, "initiated_by_user_id": initiated_by_user_id},
            # what: event type + its target
            "what": {"event": event, "work_item": work_item, "fence": fence},
            # when: durable ordering witnesses
            "when": {"seq": seq, "ts": self.now, "fence": fence},
            # result: the outcome (acquired / rejected / released / committed / new_state …)
            "result": result,
            "work_item": work_item,
        }

    # ---- the coordination mutation + its audit row (§6.5/§6.6) ----
    def record(self, event, work_item, principal, initiated_by_user_id, fence, result,
               crash_between=False):
        """Apply one coordination mutation and its audit row.

        §6.5 co-commit (default): the mutation and the audit row are one transaction — a crash
        aborts BOTH (rollback), never one. Naive separate-log: the mutation commits, then the
        audit append runs; a crash between orphans the mutation.
        """
        mutation = {"event": event, "work_item": work_item, "principal": principal, "fence": fence}
        row = self._audit_row(event, work_item, principal, initiated_by_user_id, fence, result)

        if self.separate_log:
            # WRONG: mutation is durable first...
            self.mutations.append(mutation)
            if crash_between:
                raise CrashBetween("crashed after mutation, before audit write")  # audit row lost
            self.audit.append(row)
        else:
            # §6.5: atomic. A crash rolls the whole txn back — neither the mutation nor the row
            # persists, so there is never a durable mutation without its audit row.
            if crash_between:
                raise CrashBetween("txn aborted — nothing committed")
            self.mutations.append(mutation)
            self.audit.append(row)
        return row

    # ---- shim Run-trace firehose (§10.1) — SSE + OTel only, NEVER audit_log (ADR-040) ----
    def record_trace(self, event, work_item):
        assert event in FIREHOSE_EVENTS, "record_trace is only for the shim firehose"
        if self.firehose_in_audit:
            # WRONG design: the firehose pollutes the monotonic coordination sequence.
            seq = self._next_seq()
            self.audit.append({"seq": seq, "ts": self.now,
                               "who": {"principal": "shim", "initiated_by_user_id": None},
                               "what": {"event": event, "work_item": work_item, "fence": None},
                               "when": {"seq": seq, "ts": self.now, "fence": None},
                               "result": "trace", "work_item": work_item})
        # right design: goes to SSE + OTel — modeled as a no-op on audit_log.

    # ---- immutability (§6.5 append-only trigger) ----
    def try_update(self, seq, **changes):
        if not self.mutable_log:
            raise PermissionError("audit_log is append-only: UPDATE rejected (§6.5)")
        for r in self.audit:
            if r["seq"] == seq:
                r.update(changes)
                return True
        return False

    def try_delete(self, seq):
        if not self.mutable_log:
            raise PermissionError("audit_log is append-only: DELETE rejected (§6.5)")
        before = len(self.audit)
        self.audit = [r for r in self.audit if r["seq"] != seq]
        return len(self.audit) != before

    def try_truncate(self):
        if not self.mutable_log:
            raise PermissionError("audit_log is append-only: TRUNCATE rejected (§6.5)")
        self.audit = []
        return True

    # ---- the read-only query API (§6.5, RBAC-scoped §12.3) ----
    def query(self, work_item=None, actor=None, since=None, until=None, member_of=None):
        """Filter by work item / actor(principal) / time-range, RBAC-scoped, ordered by seq.

        member_of: the set of work_items the caller may see (their project membership, §12.3).
        None means an unscoped/admin read; a set means deny-by-default — rows outside are dropped.
        """
        rows = sorted(self.audit, key=lambda r: r["seq"])
        out = []
        for r in rows:
            if work_item is not None and r["work_item"] != work_item:
                continue
            if actor is not None and r["who"]["principal"] != actor:
                continue
            if since is not None and r["when"]["ts"] < since:
                continue
            if until is not None and r["when"]["ts"] > until:
                continue
            if member_of is not None and r["work_item"] not in member_of:
                continue  # RBAC deny-by-default (§12.3)
            out.append(r)
        return out


def _seed(trail, work_item="W1", principal="runA", user="u1"):
    """Emit one of every coordination event kind against a work item (a full Run's worth)."""
    trail.record("claim_acquired", work_item, principal, user, fence=1, result="acquired")
    trail.tick()
    trail.record("claim_renewed", work_item, principal, user, fence=1, result="renewed")
    trail.tick()
    trail.record("comment_added", work_item, principal, user, fence=1, result="committed")
    trail.tick()
    trail.record("artifact_registered", work_item, principal, user, fence=1, result="committed")
    trail.tick()
    trail.record("state_transition", work_item, principal, user, fence=1, result="in_review")
    trail.tick()
    trail.record("run_completed", work_item, principal, user, fence=1, result="Succeeded")
    trail.tick()
    trail.record("claim_released", work_item, principal, user, fence=1, result="released")


# ---- (A) teeth: naive separate-log audit orphans a mutation under a crash-between ----
def run_naive_separate_log():
    trail = AuditTrail(separate_log=True)
    trail.record("claim_acquired", "W1", "runA", "u1", fence=1, result="acquired")
    # register an artifact, but crash AFTER the mutation commits and BEFORE the audit write:
    orphaned = False
    try:
        trail.record("artifact_registered", "W1", "runA", "u1", fence=1,
                     result="committed", crash_between=True)
    except CrashBetween:
        orphaned = True
    # the mutation is durable; its audit row is missing → a hole in the trail.
    n_mut = sum(1 for m in trail.mutations if m["event"] == "artifact_registered")
    n_aud = sum(1 for r in trail.audit if r["what"]["event"] == "artifact_registered")
    return {"crashed": orphaned, "durable_mutations": n_mut, "audit_rows": n_aud,
            "hole": n_mut > n_aud}


# ---- (B) §6.5 co-commit: the same crash leaves ZERO orphans ----
def run_cocommit_completeness():
    trail = AuditTrail(separate_log=False)
    trail.record("claim_acquired", "W1", "runA", "u1", fence=1, result="acquired")
    aborted = False
    try:
        trail.record("artifact_registered", "W1", "runA", "u1", fence=1,
                     result="committed", crash_between=True)
    except CrashBetween:
        aborted = True
    # atomic rollback: the mutation did NOT persist either → no durable mutation without a row.
    holes = 0
    for m in trail.mutations:
        match = [r for r in trail.audit
                 if r["what"]["event"] == m["event"] and r["work_item"] == m["work_item"]]
        if not match:
            holes += 1
    # and every audit row corresponds to a real mutation (no phantom audit either)
    phantoms = len(trail.audit) - len(trail.mutations)
    return {"aborted": aborted, "durable_mutations": len(trail.mutations),
            "audit_rows": len(trail.audit), "holes": holes, "phantoms": phantoms}


# ---- (C) immutability + monotonic gap-free sequence ----
def run_immutability():
    good = AuditTrail(mutable_log=False)
    _seed(good)
    seqs = [r["seq"] for r in good.audit]
    monotonic_gapfree = seqs == list(range(1, len(seqs) + 1))

    update_rejected = delete_rejected = truncate_rejected = False
    try:
        good.try_update(1, result="TAMPERED")
    except PermissionError:
        update_rejected = True
    try:
        good.try_delete(1)
    except PermissionError:
        delete_rejected = True
    try:
        good.try_truncate()
    except PermissionError:
        truncate_rejected = True

    # teeth: a mutable log lets who-did-what be rewritten and erased.
    bad = AuditTrail(mutable_log=True)
    _seed(bad)
    bad_edit = bad.try_update(1, who={"principal": "someone_else", "initiated_by_user_id": "x"})
    bad_delete = bad.try_delete(2)
    bad_truncate = bad.try_truncate()

    return {"monotonic_gapfree": monotonic_gapfree, "rows": len(seqs),
            "update_rejected": update_rejected, "delete_rejected": delete_rejected,
            "truncate_rejected": truncate_rejected,
            "bad_edit": bad_edit, "bad_delete": bad_delete, "bad_truncate": bad_truncate,
            "bad_rows_after_truncate": len(bad.audit)}


# ---- (D) queryability by work item / actor / time + who/what/when/result + RBAC scope ----
def run_queryability():
    trail = AuditTrail()
    _seed(trail, work_item="W1", principal="runA", user="u1")   # ts 0..6
    trail.tick(10)                                              # now = 16
    _seed(trail, work_item="W2", principal="runB", user="u2")   # ts 16..22

    by_item = trail.query(work_item="W1")
    by_actor = trail.query(actor="runB")
    by_time = trail.query(since=16, until=22)
    combined = trail.query(work_item="W2", actor="runB", since=16, until=22)

    # completeness: querying by work item returns EVERY coordination event kind for it.
    events_for_w1 = {r["what"]["event"] for r in by_item}

    # who/what/when/result present on every returned row.
    shape_ok = all(AUDIT_REQUIRED <= set(r.keys()) for r in trail.query())

    # RBAC deny-by-default (§12.3): a caller who is a member of only W1 must not see W2 rows.
    scoped = trail.query(member_of={"W1"})
    scoped_items = {r["work_item"] for r in scoped}

    return {
        "by_item_count": len(by_item), "by_item_all_w1": all(r["work_item"] == "W1" for r in by_item),
        "events_for_w1": events_for_w1, "covers_all_kinds": events_for_w1 == COORD_EVENTS,
        "by_actor_all_runB": all(r["who"]["principal"] == "runB" for r in by_actor),
        "by_time_in_window": all(16 <= r["when"]["ts"] <= 22 for r in by_time),
        "combined_count": len(combined),
        "shape_ok": shape_ok,
        "scoped_items": scoped_items, "rbac_drops_w2": scoped_items == {"W1"},
        "ordered_by_seq": [r["seq"] for r in by_item] == sorted(r["seq"] for r in by_item),
    }


# ---- (E) audit-only: the firehose never enters the audit trail (ADR-040) ----
def run_firehose_split():
    good = AuditTrail(firehose_in_audit=False)
    good.record("claim_acquired", "W1", "runA", "u1", fence=1, result="acquired")
    for ev in ("tool_call", "llm_call", "build_output", "error"):
        good.record_trace(ev, "W1")            # → SSE + OTel, no-op on audit_log
    good_seqs = [r["seq"] for r in good.query()]
    good_events = {r["what"]["event"] for r in good.query()}

    # teeth: dumping the firehose into audit_log pollutes the monotonic coordination sequence.
    bad = AuditTrail(firehose_in_audit=True)
    bad.record("claim_acquired", "W1", "runA", "u1", fence=1, result="acquired")
    for ev in ("tool_call", "llm_call", "build_output", "error"):
        bad.record_trace(ev, "W1")
    bad_events = {r["what"]["event"] for r in bad.audit}

    return {
        "good_audit_rows": len(good_seqs),
        "good_gapfree": good_seqs == list(range(1, len(good_seqs) + 1)),
        "good_no_firehose": good_events.isdisjoint(FIREHOSE_EVENTS),
        "bad_polluted": not bad_events.isdisjoint(FIREHOSE_EVENTS),
        "bad_audit_rows": len(bad.audit),
    }


def main():
    print("[model] Story 2.6 audit trail — queryable coordination record falsification\n")

    # (A) teeth: separate-log audit MUST orphan a mutation, or the harness is toothless.
    naive = run_naive_separate_log()
    print(f"[model] (A) NAIVE  (separate best-effort audit log): {naive}")
    assert naive["crashed"] and naive["hole"], \
        "TEETH LOST: a separate post-commit audit log should orphan a mutation on a crash-between"
    assert naive["durable_mutations"] == 1 and naive["audit_rows"] == 0, \
        "the artifact mutation is durable but its audit row is missing — the hole must be observable"
    print("[model]        → durable mutation with NO audit row (a hole in the trail) — hazard is real\n")

    # (B) §6.5 co-commit: the same crash leaves zero orphans (completeness by construction).
    cc = run_cocommit_completeness()
    print(f"[model] (B) §6.5  (co-committed mutation + audit row): {cc}")
    assert cc["aborted"], "the crash must abort the shared transaction"
    assert cc["holes"] == 0, "co-commit must never leave a durable mutation with no audit row (AC1)"
    assert cc["phantoms"] == 0, "co-commit must never leave a phantom audit row with no mutation (AC1)"
    assert cc["durable_mutations"] == cc["audit_rows"], "mutation count == audit row count (atomic)"
    print("[model]        → atomic rollback: no orphaned mutation, no phantom audit — trail is complete\n")

    # (C) immutability + monotonic gap-free sequence.
    imm = run_immutability()
    print(f"[model] (C) §6.5  (append-only immutability): {imm}")
    assert imm["monotonic_gapfree"], "the coordination-only stream must be a gap-free monotonic bigserial"
    assert imm["update_rejected"] and imm["delete_rejected"] and imm["truncate_rejected"], \
        "UPDATE/DELETE/TRUNCATE on audit_log must all be rejected (§6.5 append-only, structural)"
    assert imm["bad_edit"] and imm["bad_delete"] and imm["bad_truncate"], \
        "TEETH LOST: a mutable log should let who-did-what be edited/erased/truncated"
    assert imm["bad_rows_after_truncate"] == 0, "the mutable log's TRUNCATE should wipe the history"
    print("[model]        → committed audit rows are non-repudiable; mutable log leaks tampering (teeth)\n")

    # (D) queryability + who/what/when/result + RBAC scope.
    q = run_queryability()
    print(f"[model] (D) FR-B4 (query by work item / actor / time, RBAC-scoped): {q}")
    assert q["by_item_all_w1"] and q["by_item_count"] == len(COORD_EVENTS), \
        "query by work item must return exactly that item's coordination events"
    assert q["covers_all_kinds"], \
        "completeness: every checkout/comment/artifact/transition/completion is a queryable row (AC4)"
    assert q["by_actor_all_runB"], "query by actor must return only that principal's rows"
    assert q["by_time_in_window"], "query by time must return only in-window rows"
    assert q["combined_count"] == len(COORD_EVENTS), "combined filters intersect correctly"
    assert q["shape_ok"], "every audit row must carry who/what/when/result (FR-B4)"
    assert q["rbac_drops_w2"], "RBAC deny-by-default must drop rows outside the caller's membership (§12.3)"
    assert q["ordered_by_seq"], "results must be ordered by the monotonic seq"
    print("[model]        → complete, filterable, who/what/when/result, RBAC-scoped, ordered\n")

    # (E) audit-only: the firehose never enters the audit trail.
    fh = run_firehose_split()
    print(f"[model] (E) ADR-040 (audit-only, firehose → SSE+OTel): {fh}")
    assert fh["good_no_firehose"] and fh["good_gapfree"], \
        "the shim firehose must NOT enter audit_log — the coordination sequence stays clean (AC5)"
    assert fh["good_audit_rows"] == 1, "only the one coordination event lands in audit_log"
    assert fh["bad_polluted"] and fh["bad_audit_rows"] == 5, \
        "TEETH LOST: dumping the firehose into audit_log should pollute the coordination sequence"
    print("[model]        → firehose rides SSE+OTel; audit stays audit-only + bounded (teeth)\n")

    print("[model] PASS — separate-log audit detectably orphans mutations; §6.5 co-commit is complete, "
          "immutable, queryable (work item/actor/time, who/what/when/result, RBAC-scoped), audit-only.")


if __name__ == "__main__":
    main()
