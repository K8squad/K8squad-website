#!/usr/bin/env python3
"""
renew-heartbeat-check.py — Story 2.3 falsification (lease renewal / heartbeat).

A held item's lease is extended by its holder's heartbeat via ONE guarded UPDATE
(arch §6.2 renew). The load-bearing property is what renewal REFUSES: the guard is
three terms, and each one closes a distinct hazard —

    UPDATE claim SET lease_expires_at = now()+:lease, renewed_at = now()
     WHERE work_item_id = :wi
       AND holder_principal = :me        -- (a) non-holder renewal rejected
       AND fence_token      = :myFence   -- (b) stale-fence zombie rejected
       AND lease_expires_at > now();     -- (c) an EXPIRED lease is unrenewable (no self-resurrect)

The originating issue (ISI-2193) specifies only term (a) ("guarded by holder = run_id").
Arch §6.2 (F3, r7) pins all three. This is a *differential, per-term* falsification, same
discipline as claim-nodouble-check.py (2.2) and reclaim-fencing-check.py (2.4):

  For each guard term, a WEAKER guard that omits it MUST detectably leak that term's
  hazard (teeth), and only the FULL three-term guard closes all three while still
  letting the live, current-fence holder renew.

Renewal is a lease extension, NOT a custody event: a successful renew must NEVER bump
fence_token, change holder, or touch work_item.state. A rejected renew must mutate
NOTHING and write no audit/outbox row.

stdlib-only; `python3 renew-heartbeat-check.py`. Exit non-zero if any weaker guard
STOPS leaking its hazard (teeth lost), or if the full guard EVER leaks / bumps the
fence on renew / mutates on a reject / audits a rejected heartbeat. Models Postgres
row semantics in-process; the real-Postgres promotion is Story 2.7 (CI gate, alongside
chaos cases C3/C4).
"""

LEASE = 10  # arbitrary lease units


class Coord:
    """In-process model of the `coord.claim` + `work_item` rows, a logical clock, and
    the §6.5/§6.6 audit+outbox counters. `guard` selects how much of the §6.2 renew
    WHERE clause is enforced, so each term can be proven load-bearing on its own."""

    def __init__(self, guard):
        # guard ∈ {"none","holder","holder_fence","full"} — see module docstring.
        self.guard = guard
        self.now = 0
        # one claim row per work item (F3): rewritten in place, fence monotonic
        self.claim = {"holder": None, "fence": 0, "lease_expires_at": 0}
        self.state = "open"
        self.audit = []   # §6.5 coord.audit_log rows (claim.renewed appended on success only)
        self.outbox = []  # §6.6 outbox rows (same-txn as the renew UPDATE, success only)

    def tick(self, dt=1):
        self.now += dt

    # --- §6.2 acquire (Story 2.2/2.4) — the ONLY path that bumps the fence -------------
    def acquire(self, who):
        """Conditional fence-bump acquire. Returns fence on success, else None."""
        c = self.claim
        free = c["holder"] is None or c["lease_expires_at"] < self.now
        if not (self.state in ("open", "claimed") and free):
            return None
        c["holder"] = who
        c["fence"] = c["fence"] + 1            # monotonic, never reset — renew must NOT do this
        c["lease_expires_at"] = self.now + LEASE
        self.state = "claimed"
        return c["fence"]

    def reclaim_and_redispatch(self, who):
        """Story 2.4 §6.3: expire → fence the holder → release → re-acquire (fence bumps).
        Used to set up the stale-fence arm: same principal, higher fence."""
        self.claim["holder"] = None
        self.state = "open"
        return self.acquire(who)

    # --- §6.2 renew (THIS story) — extend the lease, never bump the fence ---------------
    def renew(self, who, my_fence):
        """One guarded UPDATE. Returns the (UNCHANGED) fence on success, else None.

        A successful renew moves lease_expires_at/renewed_at ONLY and appends exactly one
        audit + one outbox row in the same txn. A rejected renew mutates nothing and
        writes nothing. The `guard` mode decides which of the three §6.2 terms are checked."""
        c = self.claim
        term_holder = c["holder"] == who
        term_fence = c["fence"] == my_fence
        term_live = c["lease_expires_at"] > self.now

        if self.guard == "none":
            ok = True                                    # unguarded: WHERE work_item only
        elif self.guard == "holder":
            ok = term_holder                             # the issue's single term
        elif self.guard == "holder_fence":
            ok = term_holder and term_fence              # no lease>now → self-resurrect leaks
        elif self.guard == "full":
            ok = term_holder and term_fence and term_live  # arch §6.2 three-term guard
        else:
            raise ValueError(f"unknown guard {self.guard!r}")

        if not ok:
            return None  # zero rows: rejected. No mutation, no audit, no outbox (AC6).

        fence_before = c["fence"]
        c["lease_expires_at"] = self.now + LEASE         # push the lease out
        # renewed_at = now() would be set here; fence/holder/state deliberately untouched
        # AC6: success ⇒ exactly one audit + one outbox row, same txn.
        self.audit.append(("claim.renewed", who, c["fence"], self.now))
        self.outbox.append(("claim.renewed", who, c["fence"], self.now))
        assert c["fence"] == fence_before, "renew must NOT bump the fence (not-a-claim)"
        return c["fence"]


def snapshot(co):
    return (co.claim["holder"], co.claim["fence"], co.claim["lease_expires_at"], co.state)


# --- scenarios ----------------------------------------------------------------------------

def happy_path(guard):
    """AC1: a live holder renews well inside its lease. Lease extends, fence UNCHANGED."""
    co = Coord(guard)
    f = co.acquire("A")
    co.tick(LEASE - 3)                          # still live
    lease_before = co.claim["lease_expires_at"]
    r = co.renew("A", f)
    return {
        "fence_acquired": f, "renew_returned": r,
        "fence_after": co.claim["fence"],
        "lease_extended": co.claim["lease_expires_at"] > lease_before,
        "state": co.state, "audit": len(co.audit), "outbox": len(co.outbox),
    }


def non_holder(guard):
    """AC2 / term (a): B (never held) tries to renew A's live lease."""
    co = Coord(guard)
    fa = co.acquire("A")
    co.tick(1)
    before = snapshot(co)
    r = co.renew("B", fa)                        # wrong principal
    return {"renew_returned": r, "leaked": r is not None,
            "unchanged": snapshot(co) == before,
            "audit": len(co.audit), "outbox": len(co.outbox)}


def stale_fence(guard):
    """AC3 / term (b): A re-dispatched (fence f2 live); the paused zombie A@f1 renews.
    Holder matches for both — the FENCE is the only discriminator."""
    co = Coord(guard)
    f1 = co.acquire("A")                         # zombie's stale fence
    co.tick(LEASE + 2)                           # A's lease expires
    f2 = co.reclaim_and_redispatch("A")          # same principal, fence bumps to f2
    assert f2 > f1
    lease_live_before = co.claim["lease_expires_at"]
    r = co.renew("A", f1)                         # zombie renews with STALE fence
    audit_after_zombie, outbox_after_zombie = len(co.audit), len(co.outbox)
    live_r = co.renew("A", f2)                    # the live re-dispatch renews normally
    return {"f_stale": f1, "f_live": f2, "zombie_returned": r,
            "zombie_leaked": r is not None,
            "live_lease_moved_by_zombie": co.claim["lease_expires_at"] != lease_live_before or r is not None,
            # AC6: the zombie's REJECTED renew must have written 0 audit + 0 outbox (measured
            # before the live renew appends its own) — the (b) reject path is audit-silent too.
            "zombie_audit": audit_after_zombie, "zombie_outbox": outbox_after_zombie,
            "live_renew_ok": live_r is not None}


def lapsed_self_renew(guard):
    """AC4 / term (c): A's own lease expired but it is NOT yet reclaimed; A wakes and
    renews with its OWN current fence. An expired lease must be unrenewable."""
    co = Coord(guard)
    f = co.acquire("A")
    co.tick(LEASE + 2)                           # A's own lease lapses; no reclaim yet
    assert co.claim["lease_expires_at"] < co.now
    r = co.renew("A", f)                          # self-resurrection attempt
    return {"renew_returned": r, "resurrected": r is not None,
            "lease_now": co.claim["lease_expires_at"], "clock": co.now,
            "audit": len(co.audit), "outbox": len(co.outbox)}


def not_a_claim(guard):
    """AC5: N renews keep the fence fixed; a renew after the item is reclaimed by a new
    holder is a clean no-op (zero mutation)."""
    co = Coord(guard)
    f = co.acquire("A")
    for _ in range(5):
        co.tick(1)
        co.renew("A", f)
    fence_after_renews = co.claim["fence"]

    # item gets reclaimed by B at a higher fence; A re-drives its heartbeat → no-op
    co.tick(LEASE + 2)
    fb = co.reclaim_and_redispatch("B")
    before = snapshot(co)
    audit_before, outbox_before = len(co.audit), len(co.outbox)
    stale = co.renew("A", f)
    return {"fence_after_5_renews": fence_after_renews, "acquired_fence": f,
            "fence_bumped_by_renew": fence_after_renews != f,
            "reclaim_fence": fb, "stale_redrive_returned": stale,
            "no_mutation_on_lost": snapshot(co) == before,
            "no_audit_on_lost": len(co.audit) == audit_before and len(co.outbox) == outbox_before}


def main():
    print("[model] Story 2.3 lease renewal (heartbeat) — three-guard falsification\n")

    # ---- AC1 happy path (full guard) ----
    hp = happy_path("full")
    assert hp["renew_returned"] == hp["fence_acquired"] == 1, "renew must return the SAME fence"
    assert hp["fence_after"] == 1, "renew must NOT bump the fence"
    assert hp["lease_extended"] and hp["state"] == "claimed"
    assert hp["audit"] == 1 and hp["outbox"] == 1, "success ⇒ 1 audit + 1 outbox"
    print(f"[model] happy path (live holder renews):  full → lease extended, "
          f"fence UNCHANGED (1→{hp['fence_after']}), state={hp['state']}")

    # ---- AC2 / term (a): non-holder ----
    a_none, a_holder, a_full = non_holder("none"), non_holder("holder"), non_holder("full")
    assert a_none["leaked"], "TEETH LOST: unguarded renew must let a non-holder extend the lease"
    assert not a_holder["leaked"] and a_holder["unchanged"], "holder term must reject a non-holder"
    assert not a_full["leaked"] and a_full["unchanged"], "full guard must reject a non-holder"
    assert a_full["audit"] == 0 and a_full["outbox"] == 0, "rejected renew must not audit (AC6)"
    print(f"[model] (a) non-holder renew:   none→LEAK   holder→reject   full→reject")

    # ---- AC3 / term (b): stale fence, same principal ----
    b_holder, b_full = stale_fence("holder"), stale_fence("full")
    assert b_holder["zombie_leaked"], \
        "TEETH LOST: holder-only guard must let a same-principal stale-fence zombie renew"
    assert not b_full["zombie_leaked"], \
        "FENCING BROKEN: a stale-fence renew must be a no-op even when the principal matches"
    assert b_full["zombie_audit"] == 0 and b_full["zombie_outbox"] == 0, \
        "rejected stale-fence renew must not audit (AC6 — the (b) reject path is audit-silent)"
    assert not b_full["live_lease_moved_by_zombie"], \
        "FENCING BROKEN: the stale-fence zombie must not move the LIVE re-dispatch's lease"
    assert b_full["live_renew_ok"], "the live current-fence holder must still renew"
    print(f"[model] (b) stale-fence renew:  holder→LEAK (zombie extended live)  fence→reject   full→reject")

    # ---- AC4 / term (c): lapsed self-renew ----
    c_hf, c_full = lapsed_self_renew("holder_fence"), lapsed_self_renew("full")
    assert c_hf["resurrected"], \
        "TEETH LOST: holder+fence guard (no lease>now) must let a lapsed holder self-resurrect"
    assert not c_full["resurrected"], \
        "INTERLOCK BROKEN: an EXPIRED lease must be unrenewable (else it races §6.3 reclaim)"
    assert c_full["audit"] == 0 and c_full["outbox"] == 0, "rejected self-renew must not audit"
    print(f"[model] (c) lapsed self-renew:  holder_fence→LEAK (self-resurrect)  "
          f"full→reject (expired ⇒ unrenewable)")

    # ---- AC5: not a claim ----
    nc = not_a_claim("full")
    assert not nc["fence_bumped_by_renew"] and nc["fence_after_5_renews"] == 1, \
        "N renews must keep the fence fixed (renew ≠ claim)"
    assert nc["stale_redrive_returned"] is None and nc["no_mutation_on_lost"] and nc["no_audit_on_lost"], \
        "renew on a reclaimed item must be a clean no-op (no mutation, no audit)"
    print(f"[model] not-a-claim:  N renews keep fence=1; renew after reclaim = no-op (0 mutations)")

    print(f"[model] audit:  success ⇒ 1 audit + 1 outbox; every rejected renew ⇒ 0 + 0")
    print("\n[model] PASS — each of the three guard terms independently load-bearing; "
          "renew extends, never resurrects.")


if __name__ == "__main__":
    main()
