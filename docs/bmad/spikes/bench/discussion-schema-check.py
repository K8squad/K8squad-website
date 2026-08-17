#!/usr/bin/env python3
"""Story 10.1 (ISI-2702) falsification — the per-Project `discussion` schema + apiserver
surface is threaded, append-only, provenance-tagged, Project/Team-scoped, and STRUCTURALLY
coordination-free (arch §7.5 Theme J / FR-J1…J4, ADR-001, ADR-019; the substrate 10.2/10.3
stand on and 10.4 turns into a *tested* covert-channel guarantee).

WHY THIS BENCH EXISTS
---------------------
CEO/architect locked decision (§7.5, ADR-019): a Project's discussion room is *conversation,
not custody* — a collaboration/visibility surface the memory service can query, built with the
EXACT append-only + server-stamped-provenance discipline of the §6.1 coordination record and
the §7.3.1 memory write-auth boundary, and carrying NO coordination affordance by construction.
A design is only real if it is FALSIFIABLE: a plausible-but-wrong "discussion service" that
still "stores threaded messages" can quietly (a) reopen a lateral coordination channel, (b)
let a caller forge authorship, (c) drop the tenancy scope, or (d) hard-delete the record. Five
ways it silently breaks, none caught by "messages thread correctly":

  1. ROOM-TABLE / COORDINATION-COLUMN — a `discussion_room` table is added (R1 anti-pattern),
     or ANY custody column (`claim`/`lease`/`fence_token`/`state`/`holder`/`assignee`) creeps
     onto a table, or a custody-transfer verb (claim/checkout/transition/complete/reassign)
     appears on the API. Now the room can BE a coordination record. The schema MUST be exactly
     the two §7.5 tables (`discussion_thread`, `discussion_message`), room = Project (keyed by
     `project_id`), with NO custody column and NO custody verb — the fence is structural.

  2. UNSCOPED / UNATTRIBUTED ROW — `project_id`/`team_id`/`author_principal`/`created_at` become
     nullable, so an unscoped or unattributed row is representable. These MUST be NOT NULL (and
     `author_run_id` MUST exist, nullable) so tenancy (10.2/10.3, NFR-SEC7) and provenance (10.2)
     are enforced *over* the columns, not by hope.

  3. CLIENT-SUPPLIED AUTHOR — the write path reads `author_*` from the request body (a
     `author`/`author_type`/`author_name` field). Now a caller impersonates anyone. Provenance
     MUST be server-stamped from the authenticated context (§7.3.1/§6.5); a body-supplied author
     is ignored or rejected, never honored — impersonation is un-representable.

  4. DESTRUCTIVE RETRACT — retraction becomes a `DELETE`/`ON DELETE CASCADE`, or the forward
     migration carries a `DROP`/`TRUNCATE` of the record. The record MUST be append-only;
     retraction is the soft `invalidated_at` stamp (§7.4) and default reads filter it out.

  5. TENANCY-BLIND READ — the read plan drops the Team-scope predicate and filters by
     `project_id` alone. A cross-tenant read leaks another Team's threads. Reads MUST be scoped
     by `project_id` AND the caller's authorized Team scope (§7.3.3, deny-by-default; cross-tenant
     → no rows / 404-not-403, FR-J4).

The check is a DIFFERENTIAL, stdlib-only (`python3 discussion-schema-check.py`):

  LAYER A — a faithful model of the schema + write/read plan a discussion service would define.
  It first proves a NAIVE service (a `discussion_room`+`state`/`holder` table, a client-supplied
  author, nullable `project_id`/`author_principal`, `ON DELETE CASCADE` destructive retract, a
  team-blind read) FAILS every invariant INV1–INV5 — so the harness has teeth — then proves the
  §7.5 conformant schema PASSES them all. The naive model mirrors the real anti-pattern shape
  (author_type/author_name, room table, cascade delete) so this is not a strawman.

  LAYER B — a mutation battery: starting from the §7.5 schema, each single guardrail-weakening
  mutation must flip its designated invariant RED (add a `state` column → INV1; null
  `author_principal` → INV2; read `author` from the body → INV3; retract via `DELETE` → INV4;
  strip the Team-scope predicate → INV5). The coordination-free crux (INV1/AC4) is the primary
  tooth — the same property 10.4 verifies at runtime in the L4 covert-channel suite (ISI-2245).

Exit non-zero if the naive model passes any invariant, the conformant model fails any, or any
mutation fails to flip its designated invariant.
"""
import sys

# ── The forbidden vocabularies (the fence, made explicit) ──────────────────────────────────
# Custody/status columns that would let a discussion row BE a coordination record (§7.5/§6.1).
COORDINATION_COLUMNS = {
    "claim", "lease", "fence_token", "state", "holder", "assignee", "status", "custody",
    "checked_out_by", "owner",
}
# Custody-transfer verbs that must NOT exist on the discussion API surface (§6.2/§6.3 only).
COORDINATION_VERBS = {"claim", "checkout", "transition", "complete", "reassign", "handoff"}
# The provenance columns that MUST be stamped by the server, never read from the request body.
SERVER_STAMPED = {"author_principal", "author_agent_id", "author_run_id", "created_by", "created_at"}
# Destructive verbs forbidden on the forward migration path (§7.4 append-only).
DESTRUCTIVE_VERBS = {"DROP", "DELETE", "TRUNCATE", "ON DELETE CASCADE"}


# ══════════════════════════════════════════════════════════════════════════════════════════
#  Model of the discussion schema + write/read plan. `mut` injects a single weakening bug; the
#  conformant model (mut=None) is the §7.5 contract. Every field a weakening might flip is named
#  so an invariant check can catch the flip. `naive=True` builds the whole anti-pattern at once.
# ══════════════════════════════════════════════════════════════════════════════════════════

def model(mut=None, naive=False):
    m = {
        # (INV1) Exactly the two §7.5 tables; the room IS the Project (keyed by project_id) — NO
        #        discussion_room table. Column sets carry NO coordination/custody column.
        "tables": {"discussion_thread", "discussion_message"},
        "thread_columns": {
            "id":         {"nullable": False},
            "project_id": {"nullable": False},   # room key + tenancy (R1)
            "team_id":    {"nullable": False},   # tenancy root (§7.3.3)
            "title":      {"nullable": False},
            "created_by": {"nullable": False},   # server-stamped opener
            "created_at": {"nullable": False},
        },
        "message_columns": {
            "id":               {"nullable": False, "fk": None},
            "thread_id":        {"nullable": False, "fk": "discussion_thread"},
            "parent_id":        {"nullable": True,  "fk": "discussion_message"},  # adjacency reply
            "author_principal": {"nullable": False},
            "author_agent_id":  {"nullable": True},   # present ⇒ agent; NULL ⇒ human (derived)
            "author_run_id":    {"nullable": True},   # Run linkage (R2), set only from a Run
            "body":             {"nullable": False},
            "created_at":       {"nullable": False},
            "invalidated_at":   {"nullable": True},   # soft-retract (§7.4)
        },
        # (INV3) Where each provenance field's VALUE comes from on a write.
        "provenance_source": {c: "server_context" for c in SERVER_STAMPED},
        # (INV4) Retraction semantics + the forward-migration verb set.
        "retract_mode": "soft",                                  # stamp invalidated_at, never DELETE
        "migration_verbs": ["CREATE SCHEMA", "CREATE TABLE", "CREATE INDEX", "ALTER TABLE ADD COLUMN"],
        # (INV5) Default read-plan predicates.
        "read_predicates": {"project_id", "team_scope", "invalidated_at IS NULL"},
        # (INV1) The API verb surface — reads + append + soft-retract only, NO coordination verb.
        "api_verbs": {"list_threads", "open_thread", "get_thread", "post_message", "retract_message"},
    }

    if naive:
        # The plausible-but-wrong service, matching the real anti-pattern shape (a room table with
        # a status/holder column, client-supplied author_type/author_name, nullable scope/author,
        # ON DELETE CASCADE hard-retract, and a team-blind read). Must fail every invariant.
        m["tables"] = {"discussion_room", "discussion_message"}
        m["message_columns"] = {
            "id":          {"nullable": False, "fk": None},
            "room_id":     {"nullable": False, "fk": "discussion_room"},
            "parent_id":   {"nullable": True,  "fk": "discussion_message"},
            "author_id":   {"nullable": True},          # unattributed row representable
            "author_type": {"nullable": True},          # client-declared agent/human flag
            "author_name": {"nullable": True},          # client-supplied display name
            "state":       {"nullable": True},          # a coordination/custody column!
            "body":        {"nullable": False},
            "created_at":  {"nullable": True},          # unattributed time
            "edited_at":   {"nullable": True},          # mutable edit, not soft-retract
        }
        m["thread_columns"] = {}                        # no thread table at all in the naive model
        m["provenance_source"] = {"author_type": "request_body", "author_name": "request_body"}
        m["retract_mode"] = "hard"                      # DELETE
        m["migration_verbs"] = ["CREATE TABLE", "ON DELETE CASCADE"]
        m["read_predicates"] = {"room_id"}              # team-blind
        m["api_verbs"] = {"list", "post", "delete", "transition"}   # a custody verb leaks in
        return m

    # ── single-mutation battery (LAYER B): start from §7.5, weaken exactly one thing ──
    if mut == "add_state_column":
        m["message_columns"]["state"] = {"nullable": True}        # custody column creeps in
    elif mut == "add_room_table":
        m["tables"].add("discussion_room")                        # R1 anti-pattern
    elif mut == "add_claim_verb":
        m["api_verbs"].add("claim")                               # custody-transfer verb
    elif mut == "null_author_principal":
        m["message_columns"]["author_principal"]["nullable"] = True
    elif mut == "null_project_id":
        m["thread_columns"]["project_id"]["nullable"] = True
    elif mut == "drop_run_id":
        del m["message_columns"]["author_run_id"]                 # provenance triple broken (R2)
    elif mut == "author_from_body":
        m["provenance_source"]["author_principal"] = "request_body"
    elif mut == "hard_retract":
        m["retract_mode"] = "hard"
    elif mut == "migration_has_delete":
        m["migration_verbs"].append("DELETE")
    elif mut == "read_no_invalidated_filter":
        m["read_predicates"].discard("invalidated_at IS NULL")
    elif mut == "read_team_blind":
        m["read_predicates"].discard("team_scope")
    return m


# ══════════════════════════════════════════════════════════════════════════════════════════
#  Invariants INV1–INV5 ↔ ACs. Each returns True on a conformant model, False on a weakened one.
# ══════════════════════════════════════════════════════════════════════════════════════════

def _all_columns(m):
    cols = set(m["thread_columns"]) | set(m["message_columns"])
    return cols


def inv1_coordination_free(m):
    """AC1/AC4 (the crux) — exactly the two §7.5 tables, NO `discussion_room` table, NO
    coordination/custody column on any table, and NO custody-transfer verb on the API."""
    tables_ok = m["tables"] == {"discussion_thread", "discussion_message"}
    no_room = not any("room" in t for t in m["tables"])
    no_coord_col = not (_all_columns(m) & COORDINATION_COLUMNS)
    no_coord_verb = not (m["api_verbs"] & COORDINATION_VERBS)
    return tables_ok and no_room and no_coord_col and no_coord_verb


def inv2_scoped_and_attributed(m):
    """AC2 — the load-bearing columns are NOT NULL so an unscoped/unattributed row is
    un-representable, and the `author_run_id` Run-linkage column exists (nullable, R2)."""
    tc, mc = m["thread_columns"], m["message_columns"]
    not_null_ok = (
        tc.get("project_id", {}).get("nullable") is False
        and tc.get("team_id", {}).get("nullable") is False
        and tc.get("created_by", {}).get("nullable") is False
        and tc.get("created_at", {}).get("nullable") is False
        and mc.get("author_principal", {}).get("nullable") is False
        and mc.get("created_at", {}).get("nullable") is False
    )
    run_id_ok = "author_run_id" in mc and mc["author_run_id"]["nullable"] is True
    return not_null_ok and run_id_ok


def inv3_server_stamped_author(m):
    """AC3 — every provenance field is stamped from the server context; NONE is read from the
    request body (impersonation un-representable, §7.3.1/§6.5)."""
    src = m["provenance_source"]
    stamped = all(src.get(c) == "server_context" for c in SERVER_STAMPED)
    no_body_author = not any(v == "request_body" for v in src.values())
    return stamped and no_body_author


def inv4_append_only(m):
    """AC2/§7.4 — retraction is the soft `invalidated_at` stamp, the forward migration carries no
    destructive verb, and the default read filters `invalidated_at IS NULL`."""
    soft = m["retract_mode"] == "soft"
    forward_only = not any(
        any(v in stmt.upper() for v in DESTRUCTIVE_VERBS) for stmt in m["migration_verbs"]
    )
    filters_invalidated = "invalidated_at IS NULL" in m["read_predicates"]
    return soft and forward_only and filters_invalidated


def inv5_tenancy_scoped_read(m):
    """AC5 — the read plan is scoped by `project_id` AND the caller's authorized Team scope
    (§7.3.3 deny-by-default; cross-tenant → 404-not-403, FR-J4)."""
    p = m["read_predicates"]
    return "project_id" in p and "team_scope" in p


INVARIANTS = {
    "INV1": ("AC1/AC4 coordination-free (two tables, no room, no custody col/verb)", inv1_coordination_free),
    "INV2": ("AC2   scoped+attributed NOT NULL, author_run_id exists",               inv2_scoped_and_attributed),
    "INV3": ("AC3   provenance server-stamped, body author ignored",                 inv3_server_stamped_author),
    "INV4": ("AC2/§7.4 append-only (soft retract, no destructive migration)",        inv4_append_only),
    "INV5": ("AC5   read scoped by project_id AND Team scope",                        inv5_tenancy_scoped_read),
}

# mutation → the ONE invariant that must catch it (RED). The crux INV1 is exercised three ways.
MUTATIONS = [
    ("M1  message gains a `state` custody column",       "add_state_column",           "INV1"),
    ("M2  a `discussion_room` table is added (R1)",      "add_room_table",             "INV1"),
    ("M3  API gains a `claim` custody verb",             "add_claim_verb",             "INV1"),
    ("M4  `author_principal` made nullable",             "null_author_principal",      "INV2"),
    ("M5  `project_id` made nullable",                   "null_project_id",            "INV2"),
    ("M6  `author_run_id` dropped (R2 broken)",          "drop_run_id",                "INV2"),
    ("M7  write reads `author_principal` from body",     "author_from_body",           "INV3"),
    ("M8  retract becomes a hard DELETE",                "hard_retract",               "INV4"),
    ("M9  forward migration carries a DELETE",           "migration_has_delete",       "INV4"),
    ("M10 default read drops `invalidated_at` filter",   "read_no_invalidated_filter", "INV4"),
    ("M11 read plan drops the Team-scope predicate",     "read_team_blind",            "INV5"),
]


def run_layer_a():
    print("=" * 94)
    print("LAYER A — differential: the NAIVE service fails every invariant; the §7.5 schema passes all.")
    print("=" * 94)
    ok_all = True

    print("\n  Naive service (discussion_room+state table, client-supplied author, cascade-delete,")
    print("  team-blind read) — EVERY invariant MUST be RED (proves the harness has teeth):")
    naive = model(naive=True)
    for iid, (label, fn) in INVARIANTS.items():
        red = not fn(naive)
        ok_all &= red
        print(f"    [{'RED  ' if red else 'GREEN'}] {iid} {label}"
              f"{'' if red else '   ← naive slipped through!'}")

    print("\n  Conformant §7.5 schema — EVERY invariant MUST be GREEN:")
    good = model()
    for iid, (label, fn) in INVARIANTS.items():
        green = fn(good)
        ok_all &= green
        print(f"    [{'GREEN' if green else 'RED  '}] {iid} {label}")
    return ok_all


def run_layer_b():
    print("\n" + "=" * 94)
    print("LAYER B — mutation battery: each single weakening of the §7.5 schema flips its invariant RED.")
    print("=" * 94)
    ok_all = True
    for mlabel, mut, iid in MUTATIONS:
        label, fn = INVARIANTS[iid]
        caught = not fn(model(mut=mut))
        ok_all &= caught
        print(f"    [{'CAUGHT ' if caught else 'SURVIVED'}] {mlabel:<44} → {iid} "
              f"{'RED' if caught else 'STILL GREEN — mutation escaped!'}")
    return ok_all


def main():
    a = run_layer_a()
    b = run_layer_b()
    print("\n" + "=" * 94)
    if a and b:
        print("✓ ALL GREEN — the naive discussion service fails INV1–INV5 (teeth confirmed); the §7.5")
        print("  schema passes all five; and all 11 guardrail-weakening mutations are caught by their")
        print("  designated invariant. The coordination-free crux (INV1/AC4) — no room table, no custody")
        print("  column, no custody verb — is the same property 10.4 tests at runtime. Story 10.1 is")
        print("  falsifiable.")
        return 0
    print("✗ FAILURES ABOVE — see RED (should-be-GREEN) / GREEN (should-be-RED) / SURVIVED rows.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
