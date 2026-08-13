#!/usr/bin/env python3
"""ISI-2199 (Story 2.9) — coordinator dispatch (delegation-with-feedback) falsification.

The locked-decision claim: a coordinator (squad-lead Agent) learns a completed
dependency's results and dispatches downstream work as

    read-of-record  →  coordinator DECIDES  →  new FENCED dispatch

and NEVER as a peer-to-peer back-channel. Concretely, three properties must hold
simultaneously and are the entire correctness content of this story:

  (P1) NO agent-to-agent channel. B never messages A and B never *drives* the
       next dispatch. The coordinator learns B's `{findings, recommended_next,
       artifacts_for_downstream}` (Story 2.8) SOLELY by READING the coordination
       record / scoped memory recall (Story 6.6). If you delete that read, the
       coordinator is blind — there is no second (covert) path.
  (P2) The coordinator DEFINES and PRIORITIZES the next work item. B's
       `recommended_next` is ADVISORY: the coordinator may OVERRIDE it. The
       dispatched item is `created_by = coordinator`, never `created_by = B`.
  (P3) NO custody transfer. B never hands its claim/lease to C. B RELEASES
       (fenced, §6.3), the item goes `open`, the control plane re-dispatches,
       C CLAIMS FRESH — so C's fence is a NEW monotonic acquire, strictly
       greater than B's, never B's fence inherited.

This is a *differential* falsification, not a happy-path demo. It runs the same
delegation twice and asserts:

  (A) a NAIVE "helpful" design — B, on completing, MESSAGES the coordinator AND
      directly dispatches the next item per its own `recommended_next`, handing
      C its own lease — DOES violate all three properties (a real back-channel
      exists, B authored/drove the dispatch, custody was inherited) → proves the
      check has teeth; and
  (B) the §6.6/§2.8/§2.2 design produces ZERO back-channel rows, a
      coordinator-authored + coordinator-overridden next item, and a fresh
      higher fence for C — WHILE the coordinator still successfully learns B's
      results from the record.

If (A) ever stops violating (no back-channel detected) the check fails LOUD,
because then (B)'s clean result proves nothing. Stdlib only; `python3` it.
"""
import sys

COORD, B, C = "coordinator", "agentB", "agentC"


class World:
    """In-process model of the coord record (§6.1) + memory (§7) + the FORBIDDEN
    P2P message channel (§7.5). In a correct design `messages` stays empty."""

    def __init__(self):
        self.items = {}          # id -> dict(state, created_by, holder, fence, priority, blocked_by, handoff)
        self.memory = []         # provenanced recall entries (§6.6 mirror), trust="untrusted"
        self.messages = []       # a B->A channel. MUST remain empty (no-P2P, FR-B3)
        self._fence = 0          # monotonic fence dispenser for the whole record (§6.2)

    def create(self, wid, by, priority=0, blocked_by=None):
        self.items[wid] = dict(state="backlog", created_by=by, holder=None,
                               fence=None, priority=priority, blocked_by=blocked_by,
                               handoff=None, custody_via=None)

    def open_for_dispatch(self, wid):
        self.items[wid]["state"] = "open"

    def claim(self, wid, who):
        """§6.2 conditional acquire: only an unheld/open item, bumps the monotonic fence.
        Stamps `custody_via='conditional_acquire'` so a *fresh higher fence alone* can't
        be forged by a direct custody push — AC4 requires the acquire, not just fc>fb."""
        it = self.items[wid]
        assert it["holder"] is None and it["state"] in ("open", "backlog"), f"{wid} not claimable by {who}"
        self._fence += 1
        it["holder"], it["fence"], it["state"] = who, self._fence, "in_progress"
        it["custody_via"] = "conditional_acquire"
        return it["fence"]

    def complete(self, wid, who, handoff):
        it = self.items[wid]
        assert it["holder"] == who, "only the holder completes"
        it["handoff"], it["state"] = handoff, "done"

    def release(self, wid, who):
        """Fenced release (§6.3): holder lets go; item returns to the pool. Custody
        does NOT move to anyone — it becomes claimable, fence cleared."""
        it = self.items[wid]
        assert it["holder"] == who
        it["holder"], it["fence"], it["state"] = None, None, "open"


def run_B(w, wb):
    """B claims WB, does the work, writes the Story-2.8 handoff artifact, mirrors
    it to memory. This half is IDENTICAL in both designs — B always emits results
    to the record. The designs differ ONLY in what B does *after*."""
    fb = w.claim(wb, B)
    handoff = dict(did="analysed auth flow", decisions=["use existing lib"],
                   next="wire the token refresh", blockers=[],
                   findings="refresh endpoint is rate-limited at 5rpm",
                   recommended_next="WC_token_refresh", priority_hint=1,
                   artifacts_for_downstream=["auth-notes.md"])
    w.complete(wb, B, handoff)
    # §6.6 mirror: provenanced, untrusted-recall tier — recall, never a handoff channel.
    w.memory.append(dict(author=B, scope="squad", trust="untrusted", content=handoff))
    return fb, handoff


def naive_after_B(w, wb, fb):
    """NAIVE 'helpful' design: B pushes the result to the coordinator AND drives
    the next dispatch itself, handing C its own lease. Every line here is a
    property violation — that is the point."""
    # (P1 violation) B messages the coordinator directly — a B->A back-channel.
    w.messages.append(dict(frm=B, to=COORD, body="done, dispatch WC next"))
    # (P2 violation) B authors + dispatches the next item per ITS OWN recommendation.
    rec = w.items[wb]["handoff"]["recommended_next"]
    w.create(rec, by=B, priority=w.items[wb]["handoff"]["priority_hint"])
    w.open_for_dispatch(rec)
    # (P3 violation) B hands C its own lease — custody transfer, fence inherited.
    it = w.items[rec]
    it["holder"], it["fence"], it["state"] = C, fb, "in_progress"
    return rec, it["fence"]


def refence_handoff_after_B(w, wb):
    """SUBTLER custody shortcut: the item is even coordinator-authored and gets a
    *fresh higher fence* — but custody is PUSHED directly to C without ever going
    open → §6.2 conditional acquire. A P3 check that only asserts `f_c > f_b` would
    green-light this. It must be caught by `custody_via != conditional_acquire`."""
    coord_choice = "WD_rate_limit_guard"
    w.create(coord_choice, by=COORD, priority=9)
    w._fence += 1                                   # fresh fence bump (NOT inherited)
    it = w.items[coord_choice]
    it["holder"], it["fence"], it["state"] = C, w._fence, "in_progress"
    return coord_choice, it["fence"]


def spine_after_B(w, wb):
    """§2.9 design: B did nothing beyond emitting to the record (run_B). The
    COORDINATOR now independently READS the record, DECIDES (overriding B's
    recommendation), authors + prioritizes the next item, and dispatches it OPEN;
    C then CLAIMS FRESH. No message, no B-authored item, no inherited custody."""
    # Coordinator learns B's results ONLY by reading the record / memory recall.
    recall = [m for m in w.memory if m["scope"] == "squad"]
    read = w.items[wb]["handoff"]
    learned = bool(recall) and read is not None and "rate-limited" in read["findings"]
    # Coordinator DECIDES — and OVERRIDES B's recommended_next with its own choice
    # + its own priority (proves recommended_next is advisory, coordinator prioritizes).
    coord_choice = "WD_rate_limit_guard"           # != read["recommended_next"] ("WC_token_refresh")
    coord_priority = 9                              # != read["priority_hint"] (1)
    w.create(coord_choice, by=COORD, priority=coord_priority)
    w.open_for_dispatch(coord_choice)               # re-dispatch as an OPEN item
    fc = w.claim(coord_choice, C)                    # C claims FRESH -> new fence
    return coord_choice, fc, learned, read["recommended_next"]


def check_naive():
    w = World()
    w.create("WB", by=COORD); w.open_for_dispatch("WB")
    fb, _ = run_B(w, "WB")
    disp, fc = naive_after_B(w, "WB", fb)
    it = w.items[disp]
    back_channel = len(w.messages) > 0
    b_authored = it["created_by"] == B
    custody_inherited = fc == fb
    violates = back_channel and b_authored and custody_inherited
    print(f"[model] NAIVE  (B messages A + B drives dispatch + hands lease): "
          f"messages={len(w.messages)} next.created_by={it['created_by']!r} "
          f"C.fence={fc} (==B.fence {fb}? {custody_inherited})")
    print(f"[model]        -> back-channel={back_channel} b_authored={b_authored} "
          f"custody_inherited={custody_inherited} (all must be True: teeth)")

    # Second, subtler teeth arm: a coordinator-authored, fresh-higher-fence dispatch
    # whose custody was PUSHED to C directly (no conditional acquire). `f_c > f_b` is
    # True here, so a fence-only P3 check would MISS it — the acquire stamp catches it.
    w2 = World()
    w2.create("WB", by=COORD); w2.open_for_dispatch("WB")
    fb2, _ = run_B(w2, "WB")
    disp2, fc2 = refence_handoff_after_B(w2, "WB")
    it2 = w2.items[disp2]
    fence_looks_fresh = fc2 > fb2                          # would fool a fence-only check
    custody_forged = it2["custody_via"] != "conditional_acquire"   # but the acquire never happened
    refence_caught = fence_looks_fresh and custody_forged
    print(f"[model] NAIVE2 (coord-authored + fresh fence but custody PUSHED, no acquire): "
          f"C.fence={fc2}(>{fb2}? {fence_looks_fresh}) custody_via={it2['custody_via']!r}")
    print(f"[model]        -> fence_looks_fresh={fence_looks_fresh} custody_forged={custody_forged} "
          f"(both True: the fresh-fence shortcut is detectable, not just fence-copy)")
    return violates and refence_caught


def check_spine():
    w = World()
    w.create("WB", by=COORD); w.open_for_dispatch("WB")
    fb, handoff = run_B(w, "WB")
    disp, fc, learned, rec = spine_after_B(w, "WB")
    it = w.items[disp]
    no_back_channel = len(w.messages) == 0
    coord_authored = it["created_by"] == COORD
    overrode = disp != rec                                # dispatched != B's recommendation
    # AC4 crux: not merely fc>fb (a direct push can forge that) — custody MUST have
    # come through the §6.2 conditional acquire on an open item.
    fresh_custody = fc > fb and it["custody_via"] == "conditional_acquire"
    still_learned = learned                               # feedback still reached the coordinator
    ok = no_back_channel and coord_authored and overrode and fresh_custody and still_learned
    print(f"[model] §2.9   (read-of-record -> coordinator decides -> fenced dispatch): "
          f"messages={len(w.messages)} next.created_by={it['created_by']!r} "
          f"B.rec={rec!r} dispatched={disp!r} C.fence={fc}(>{fb}? {fresh_custody})")
    print(f"[model]        -> no_back_channel={no_back_channel} coord_authored={coord_authored} "
          f"overrode_recommendation={overrode} fresh_custody={fresh_custody} learned_from_record={still_learned}")
    return ok


def main():
    naive_violates = check_naive()
    spine_ok = check_spine()
    if not naive_violates:
        print("[model] FAIL — a naive design was NOT flagged (missing back-channel OR the "
              "fresh-fence custody shortcut slipped through); the check lost its teeth.")
        return 1
    if not spine_ok:
        print("[model] FAIL — §2.9 design broke a property (back-channel / B-authored / custody / no-feedback).")
        return 1
    print("[model] PASS — naive detectably back-channels+transfers custody; "
          "§2.9 keeps zero P2P, coordinator authors+overrides+prioritizes, "
          "C claims fresh, and the coordinator still learns B's results from the record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
