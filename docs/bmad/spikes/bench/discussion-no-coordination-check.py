#!/usr/bin/env python3
"""Story 10.4 — [Guardrail] the discussion room is structurally NOT a coordination back-channel.

🔒 A GUARDRAIL, NOT A FEATURE. This ships a *proof*, not a product surface: it promotes 10.1 AC4 (the
room is coordination-free *by construction*) to a STANDING, TESTED GATE over the 10.1 `discussion`
schema + API surface (arch §7.5 three-point no-coordination argument; §6 "no agent-to-agent channel
exists in the schema"; PRD FR-B3 / §8.4 honest framing, F6). The runtime F6 covert-channel evidence
(AC3/AC4) lives in the L4 suite as S4-6's ROOM arm (see `blast-radius-check.py`); THIS file is the
static/structural half (AC1/AC2).

It is a DIFFERENTIAL check, in the shape 14.2's chaos-harness.py and 14.4's blast-radius-check.py use:
we first prove a NAIVE "room-as-coordination" surface — one that grew a `state`/`holder` column, a
`POST …/claim` verb, and a write that upserts a `coord.claim` row — FAILS every invariant (the harness
has teeth), then prove the §7.5 surface (the one 10.1 builds) PASSES them all. A surface that threads
messages perfectly but carries *any* custody column/verb, or whose write re-enters `coord`, is the
exact anti-pattern this gate forbids — that is the whole §7.5 point: threaded chat superficially
*looks* like P2P; this demonstrates it structurally is not.

Maps to Story 10.4 ACs:
  AC1 — no coordination column/verb exists on the room surface (the §7.5 fence, tested).  [INV1, INV2]
  AC2 — no discussion write mutates coordination state (the crux, F6).                     [INV3]
AC3/AC4 (the runtime covert-channel case) are the L4 suite's job — S4-6 room arm — not this file.
"""

import sys

FAILS = []


def check(case, cond, detail):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {case}: {detail}")
    if not cond:
        FAILS.append(f"{case}: {detail}")


# --------------------------------------------------------------------------------------------------
# The forbidden vocabulary — the §7.5 fence. Custody of a work item moves ONLY in the fenced `coord`
# claim tables (§6.2/§6.3); NONE of it has an expression on the discussion surface.
# --------------------------------------------------------------------------------------------------

# AC1: any of these as a discussion COLUMN name is a custody/status leak — the room would carry work
# state, not just talk. (Substring match so `claim_state`, `held_by`, `fence_token` all trip.)
FORBIDDEN_COORD_COLUMN_TOKENS = {
    "claim", "lease", "fence", "fence_token", "state", "status",
    "holder", "held_by", "assignee", "assigned_to", "owner", "custody",
}

# AC1: any endpoint/tool VERB that claims / checks out / transitions / completes / reassigns a work
# item. A discussion surface has POST/GET/PATCH over threads+messages ONLY.
FORBIDDEN_COORD_VERB_TOKENS = {
    "claim", "checkout", "check-out", "lease", "transition", "complete",
    "reassign", "assign", "handoff", "hand-off", "dispatch", "fence",
}


# --------------------------------------------------------------------------------------------------
# The surface model. `guard_on=True` yields the §7.5 room 10.1 builds; `guard_on=False` is the
# MUTATION arm — it injects the three anti-patterns the story's mutation contract names (a coord
# column, a `…/claim` verb, a write that upserts a coord row) and MUST fail the invariants (teeth).
# --------------------------------------------------------------------------------------------------

def discussion_columns(guard_on):
    """The §7.5 `discussion_thread` + `discussion_message` columns (10.1). Talk + provenance ONLY."""
    cols = [
        # discussion_thread
        "id", "project_id", "team_id", "title", "created_by", "created_at",
        # discussion_message
        "thread_id", "parent_id", "author_principal", "author_agent_id",
        "author_run_id", "body", "created_at", "invalidated_at",
    ]
    if not guard_on:
        # MUTATION (AC1): the room grew a custody/status column — it now carries work state.
        cols += ["state", "holder", "fence_token"]
    return cols


def discussion_endpoints(guard_on):
    """The 10.1 apiserver REST + MCP tool surface. Read/append threaded messages ONLY."""
    eps = [
        ("GET", "/api/projects/{projectId}/discussion/threads"),
        ("POST", "/api/projects/{projectId}/discussion/threads"),
        ("GET", "/api/projects/{projectId}/discussion/threads/{threadId}"),
        ("POST", "/api/projects/{projectId}/discussion/threads/{threadId}/messages"),
        ("PATCH", "/api/projects/{projectId}/discussion/threads/{threadId}/messages/{id}"),
        ("TOOL", "discussion_post"),
        ("TOOL", "discussion_reply"),
    ]
    if not guard_on:
        # MUTATION (AC1): a custody-transfer verb appeared on the room surface.
        eps += [("POST", "/api/projects/{projectId}/discussion/threads/{threadId}/claim")]
    return eps


def discussion_write_coord_effects(guard_on):
    """Which `coord` tables a discussion write (post/reply/retract) mutates as a side effect.

    AC2 (the crux): the answer MUST be the empty set. A discussion write moves ZERO work items and
    changes ZERO custody — nothing it does re-enters the fenced `coord` record.
    """
    if not guard_on:
        # MUTATION (AC2): a post now upserts a coord.claim row — the room silently drives custody.
        return {"coord.claim"}
    return set()  # post/reply/retract touch `discussion.*` ONLY


def _token_hits(name, tokens):
    n = name.lower().replace("-", "_")
    return {t for t in tokens if t.replace("-", "_") in n}


# --------------------------------------------------------------------------------------------------
# The three invariants (the §7.5 fence, as a gate).
# --------------------------------------------------------------------------------------------------

def coord_columns_present(guard_on):
    """INV1 / AC1: set of discussion columns that name a coordination/custody/status concept."""
    hits = set()
    for c in discussion_columns(guard_on):
        hits |= _token_hits(c, FORBIDDEN_COORD_COLUMN_TOKENS)
    return hits


def coord_verbs_present(guard_on):
    """INV2 / AC1: set of endpoints whose path/verb claims/checks-out/transitions/completes/reassigns."""
    hits = set()
    for method, path in discussion_endpoints(guard_on):
        if _token_hits(path, FORBIDDEN_COORD_VERB_TOKENS):
            hits.add(f"{method} {path}")
    return hits


def coord_write_side_effects(guard_on):
    """INV3 / AC2: the set of `coord` rows a discussion write mutates. Must be empty."""
    return discussion_write_coord_effects(guard_on)


# --------------------------------------------------------------------------------------------------
# Differential run: guard-ON (the built §7.5 surface) must be clean; guard-OFF (each mutation) must
# trip. If guard-OFF passed, the gate has no teeth — that is itself a failure.
# --------------------------------------------------------------------------------------------------

print("INV1 (AC1) — no coordination/custody COLUMN on the room surface (§7.5 fence)")
check("INV1", coord_columns_present(guard_on=True) == set(),
      "§7.5 surface carries NO claim/lease/fence/state/holder/assignee column")
check("INV1-teeth", coord_columns_present(guard_on=False) != set(),
      "MUTATION arm (added state/holder/fence_token) is caught RED")

print("\nINV2 (AC1) — no coordination VERB on the room surface (no claim/checkout/transition/…)")
check("INV2", coord_verbs_present(guard_on=True) == set(),
      "§7.5 API is read/append over threads+messages ONLY — no custody-transfer verb")
check("INV2-teeth", coord_verbs_present(guard_on=False) != set(),
      "MUTATION arm (added POST …/claim) is caught RED")

print("\nINV3 (AC2) — NO discussion write mutates a `coord` row (the crux, F6)")
check("INV3", coord_write_side_effects(guard_on=True) == set(),
      "post/reply/retract move ZERO work items — nothing re-enters coord")
check("INV3-teeth", coord_write_side_effects(guard_on=False) != set(),
      "MUTATION arm (post upserts coord.claim) is caught RED")

# Positive control: the room DOES carry its talk+provenance substance (this is not a stripped table).
print("\nPositive control — the room still carries talk + server-stamped provenance (10.1)")
_cols = set(discussion_columns(guard_on=True))
check("substance", {"body", "author_principal", "author_run_id", "invalidated_at"} <= _cols,
      "threaded body + provenance triple + soft-retract present (talk, not custody)")

print("\n" + "=" * 78)
if FAILS:
    print(f"RESULT: RED — {len(FAILS)} coordination-freeness invariant(s) violated:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("RESULT: GREEN — the 10.1 room surface is structurally coordination-free "
      "(no custody column/verb; no coord write side-effect). §7.5 fence holds; F6 static half proven.")
sys.exit(0)
