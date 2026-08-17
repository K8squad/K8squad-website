#!/usr/bin/env python3
"""Story 14.4 falsification anchor — the S4 blast-radius suite (§6.5, §17.1 "tested, not asserted").

🔒 Language-neutral, no-cluster DIFFERENTIAL model of the six S4 cases. Mirrors 14.2's chaos-harness.py:
for each case we first prove the GUARD-OFF variant ESCAPES (real teeth), then prove the GUARD-ON design
CONTAINS. The Go/kind `blast-radius.yml` implementation is a faithful 1:1 translation of this anchor — a
broken guard is caught HERE before the kind wiring exists, and an all-green kind run against a spineless
fixture is itself a failure this anchor's mutation arm forbids.

The hostile-Run fixture is a Run pod that actively probes for escape. Each S4 case models one escape
attempt and the primitive that bounds it:

  S4-1 default-deny egress        — no allowlist entry ⇒ arbitrary endpoint unreachable          (§12.2/NFR-SEC4, X.1)
  S4-2 exfil-via-allowlisted      — the allowlisted hole is AUDITED (attributable), not silent     (§12.2/F11, X.1)
  S4-3 cross-namespace isolation  — Team-A pod cannot reach Team-B svc/Secret                      (§12.1/NFR-SEC1, X.1)
  S4-4 reuse-residue              — teardown-and-replace leaves NO prior-Run scratch/secret/tree   (§9.3/NFR-SEC5, X.2)
  S4-5 cross-principal read-authZ — B GETs A's Run build view (same Team) ⇒ 404, existence-hiding  (§9.4/NFR-SEC5, 8.7d)
  S4-6 poisoning + covert-channel — forged provenance rejected; memory AND room ≠ coordination back-channel (§7.3/§7.5/NFR-SEC6, X.3/10.4/12.4)

A "the hostile pod ran and nothing obviously broke" demo passes even if egress is open, a Team-A pod can
list Team-B Secrets, a torn-down PVC still holds a prior principal's worktree, a same-Team peer reads
another principal's Run with a 403 (leaking existence) or a 200 (leaking content), a forged author is
accepted, or a poisoned memory fact silently becomes a coordinator's dispatch input. So this is a
differential check over the CONTAINMENT DESIGN, not a smoke test.
"""

import sys

FAILS = []


def check(case, cond, detail):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {case}: {detail}")
    if not cond:
        FAILS.append(f"{case}: {detail}")


# --------------------------------------------------------------------------------------------------
# The containment model. Each mechanism is a pure predicate over (attempt, guard_on). guard_on=False
# is the MUTATION arm (the guard deleted/widened) and MUST let the attempt escape — that is the teeth.
# --------------------------------------------------------------------------------------------------

ALLOWLIST = {"model.internal:443", "control-plane.ksquad:443", "tool-proxy:8080"}


def egress_reachable(dst, guard_on):
    """S4-1/S4-2: default-deny. guard_on ⇒ only allowlisted dsts resolve; off ⇒ everything resolves."""
    if not guard_on:
        return True  # NetworkPolicy deleted: default-ALLOW — arbitrary exfil endpoint reachable
    return dst in ALLOWLIST


def egress_audited(dst, guard_on):
    """S4-2/F11: an allowlisted call is recorded by the egress proxy (attributable), not silent."""
    if not guard_on:
        return False  # proxy audit disabled: the allowlisted hole is invisible = mistaken-for-containment
    return dst in ALLOWLIST  # audited iff it went through the allowlisted proxy path


def cross_ns_reachable(caller_team, target_team, guard_on):
    """S4-3: default-deny NetPol + scoped RBAC. guard_on ⇒ only same-team reachable."""
    if not guard_on:
        return True  # Team-B RoleBinding widened / NetPol dropped: cross-namespace reach
    return caller_team == target_team


def residue_after_teardown(guard_on):
    """S4-4: teardown-and-replace wipes per-principal scratch/secret/worktree. off ⇒ residue survives."""
    prior = {"scratch/tmp", "worktree/.git", "secret/token"}
    if not guard_on:
        return prior  # teardown wipe skipped: fresh sandbox inherits prior-Run residue
    return set()  # replaced sandbox is clean


def build_read_status(caller_principal, caller_team, run_owner, run_team, guard_on):
    """S4-5: authorizeRead allows iff (run∈team scope) AND (owner==caller). Deny ⇒ 404 (existence-hiding)."""
    if not guard_on:
        # owning-principal check dropped: any same-team caller reads → 200 (content leak)
        return 200 if caller_team == run_team else 404
    if caller_team == run_team and run_owner == caller_principal:
        return 200
    return 404  # never 403 — do not confirm existence


def memory_read(record, guard_on):
    """S4-6: a read is surfaced with un-forgeable provenance + trust tier. off ⇒ forged author accepted."""
    # record = {"claimed_author": ..., "stamped_author": ..., "trust": ...}
    if not guard_on:
        return {"author": record["claimed_author"], "trusted": True}  # forgery accepted
    return {"author": record["stamped_author"], "trusted": record["trust"] == "trusted"}


def coordination_driveable_by_memory(guard_on):
    """S4-6 covert-channel (10.4/12.4/F6): can a memory/room write mutate a claim/handoff/state?"""
    if not guard_on:
        return True  # room/memory grew claim/handoff semantics: off-record steering possible
    return False  # coordination rides shared work-items + fencing ONLY; memory is read-of-record


# --- S4-6 ROOM arm (Story 10.4, additive to the memory arm above; 10.1 discussion surface) ---------
# The merged S4-6 exercised only the MEMORY arm. 10.4 co-owns the DISCUSSION-ROOM arm of this same
# case: a hostile Run posts a room message crafted to STEER a coordinator's next dispatch. The room
# is talk, not custody (arch §7.5) — modeled here 1:1 with the memory arm so the same teeth bite it.
# In the kind runtime (`blast-radius.yml`) this arm SELF-SKIPS-WITH-REASON (14.4 AC8) until the 10.1
# discussion apiserver image is deployable in kind (Epic 9 install), exactly as the memory arm gates
# on a kind-deployable memory service; the language-neutral anchor here always runs.

def room_read(record, guard_on):
    """S4-6 room arm (10.1 AC3 / §7.3.1/§7.3.2): a room message is surfaced with server-stamped,
    un-forgeable provenance + `trust:"untrusted"`. off ⇒ a body-supplied (forged) author is honored."""
    # record = {"claimed_author": ..., "stamped_author": ..., "trust": ...}
    if not guard_on:
        return {"author": record["claimed_author"], "trusted": True}  # forged author accepted
    return {"author": record["stamped_author"], "trusted": record["trust"] == "trusted"}


def coordination_driveable_by_room(guard_on):
    """S4-6 room arm (10.4/F6): can a DISCUSSION write mutate a claim/handoff/state? The §7.5 fence:
    the room schema/API has NO custody column/verb and NO write path into `coord` (10.4 AC1/AC2)."""
    if not guard_on:
        return True  # the room grew claim/handoff semantics: off-record steering via chat possible
    return False  # a room post moves ZERO work items; the coordinator dispatches on fenced items ONLY


def run_case(name, guard_off_escapes, guard_on_contains):
    """A case is valid iff guard-OFF escapes (teeth) AND guard-ON contains (conformance)."""
    print(f"\n{name}")
    check(name, guard_off_escapes(), "GUARD-OFF mutation ESCAPES (teeth present)")
    check(name, guard_on_contains(), "GUARD-ON design CONTAINS (conformant)")


run_case(
    "S4-1 default-deny egress",
    guard_off_escapes=lambda: egress_reachable("evil.exfil.net:443", guard_on=False) is True,
    guard_on_contains=lambda: egress_reachable("evil.exfil.net:443", guard_on=True) is False
    and egress_reachable("model.internal:443", guard_on=True) is True,
)

run_case(
    "S4-2 exfil-via-allowlisted (named, not hidden — F11)",
    guard_off_escapes=lambda: egress_audited("model.internal:443", guard_on=False) is False,
    guard_on_contains=lambda: egress_audited("model.internal:443", guard_on=True) is True,
)

run_case(
    "S4-3 cross-namespace isolation",
    guard_off_escapes=lambda: cross_ns_reachable("team-a", "team-b", guard_on=False) is True,
    guard_on_contains=lambda: cross_ns_reachable("team-a", "team-b", guard_on=True) is False
    and cross_ns_reachable("team-a", "team-a", guard_on=True) is True,
)

run_case(
    "S4-4 reuse-residue",
    guard_off_escapes=lambda: len(residue_after_teardown(guard_on=False)) > 0,
    guard_on_contains=lambda: len(residue_after_teardown(guard_on=True)) == 0,
)

run_case(
    "S4-5 cross-principal same-Team read-authZ (404, existence-hiding)",
    guard_off_escapes=lambda: build_read_status("B", "team-a", "A", "team-a", guard_on=False) == 200,
    guard_on_contains=lambda: build_read_status("B", "team-a", "A", "team-a", guard_on=True) == 404
    and build_read_status("A", "team-a", "A", "team-a", guard_on=True) == 200   # positive control
    and build_read_status("C", "team-c", "A", "team-a", guard_on=True) == 404,  # cross-Team
)

_forged = {"claimed_author": "victim-principal", "stamped_author": "hostile-run", "trust": "untrusted"}
run_case(
    "S4-6 poisoning/forgery + covert-channel (memory arm)",
    guard_off_escapes=lambda: memory_read(_forged, guard_on=False)["author"] == "victim-principal"
    or coordination_driveable_by_memory(guard_on=False) is True,
    guard_on_contains=lambda: memory_read(_forged, guard_on=True)["author"] == "hostile-run"
    and memory_read(_forged, guard_on=True)["trusted"] is False
    and coordination_driveable_by_memory(guard_on=True) is False,
)

# S4-6 ROOM arm (Story 10.4): a hostile Run posts a room message forging another principal AND crafted
# to steer the coordinator. GUARD-ON: the read is server-stamped to the REAL hostile principal (not the
# impersonated victim), surfaced untrusted, and the coordinator's dispatch rides fenced work-items ONLY
# — the room message flips no claim/handoff/state. Same forgery fixture as the memory arm; same teeth.
run_case(
    "S4-6 covert-channel (room arm — 10.4; kind: self-skip-with-reason until 10.1 apiserver deployable)",
    guard_off_escapes=lambda: room_read(_forged, guard_on=False)["author"] == "victim-principal"
    or coordination_driveable_by_room(guard_on=False) is True,
    guard_on_contains=lambda: room_read(_forged, guard_on=True)["author"] == "hostile-run"
    and room_read(_forged, guard_on=True)["trusted"] is False
    and coordination_driveable_by_room(guard_on=True) is False,
)

# Extra teeth: S4-5 must be 404, NEVER 403 (a 403 leaks existence — AC5).
print("\nS4-5 existence-hiding invariant (404 not 403)")
check("S4-5-403", build_read_status("B", "team-a", "A", "team-a", guard_on=True) != 403,
      "deny is 404, never 403 (no existence leak)")

print("\n" + "=" * 78)
if FAILS:
    print(f"RESULT: RED — {len(FAILS)} S4 invariant(s) violated:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("RESULT: GREEN — all six S4 cases differential (guard-off escapes, guard-on contains).")
sys.exit(0)
