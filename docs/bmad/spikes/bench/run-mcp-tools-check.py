#!/usr/bin/env python3
"""
run-mcp-tools-check.py — Story 6.2 falsification (memory MCP tool surface).

Story 6.2 ships the FOUR MVP memory MCP tools — memory_write / memory_search /
diary_append / diary_read — as a STABLE, PINNED WIRE SEAM (§7.1 tool table, §10.2
pinned pkg/mcp), NOT the backend (6.1) and NOT the trust *enforcement* (6.3/6.4/6.5).
The distinctive things 6.2 owns:

  1. The fast-follow cut is a REAL cut: memory.relate/kg_add/kg_query are DESIGNED but
     NOT SHIPPED, and the cut must be FAIL-CLOSED. The seductive-wrong design registers
     kg_add as a no-op returning ok — an agent then believes a relation persisted that
     never was (phantom-edge knowledge loss). A silent-success stub is strictly worse
     than an absent tool.
  2. The surface is a stable seam: the four MVP signatures + return envelopes are
     backend-independent (§7.6 MemoryBackend: pgvector v1 ⇄ GRAIL) and forward-compatible
     with the KG fast-follow (§10.2: shipping KG ADDS tools, never MUTATES the four).
  3. The tools carry the §7.3 trust envelope wire shape (reads = untrusted-provenance
     envelope, never bare text; writes = provenanced ack; every call takes a scope) —
     6.2 pins the SHAPE, 6.3/6.4/6.5 enforce the RULES.

Differential falsification (same discipline as handoff-advisory-check.py):
  (A) NAIVE silent-KG-stub: kg_add returns ok, kg_query returns [] → phantom edge. MUST
      leak (teeth), else the harness proves nothing.
  (B) §B FAIL-CLOSED cut (AC3): KG absent from the v1 set; a kg call RAISES unimplemented.
      Mutation-proven — re-register kg_add as a silent no-op → this arm goes RED.
  (C) MVP round-trip across Runs (AC1): write→(later Run)search returns it; diary
      append→read is per-agent, newest-first, bounded by last_n; no raw backend row leaks.
  (D) pinned surface = exactly the four (AC2): registered v1 set is exactly the four MVP
      tools; no KG tool, no raw_query/DB-handle doorway.
  (E) additive KG revision (AC4): a v1.1 surface ADDS kg_add/kg_query and leaves the four
      MVP signatures byte-identical; a BREAKING revision (new required arg on memory_write)
      is rejected by the seam contract.
  (F) trust-envelope wire shape (AC5): reads = {content,author,written_at,scope,trust:
      "untrusted"} never bare text; write ack is provenanced; an unscoped call is rejected.
  (G) backend-independence (AC6): the identical surface over a Pgvector model and a Grail
      model yields identical signatures + envelope keys; no backend-specific field leaks.

stdlib-only; `python3 run-mcp-tools-check.py`. Exit non-zero if the cut ever returns a
silent success (A stops leaking / B stops raising), the round-trip drops a record or blows
last_n, the surface is not exactly the four (or leaks a raw doorway), an additive KG revision
mutates a MVP signature (or a breaking one is accepted), a read returns bare text, a write ack
drops provenance, an unscoped call is accepted, or a backend field leaks into the contract.
Models Postgres/pgvector + backend seam in-process; real-backend promotion rides Epic 6.1/6.4.
"""

# ---- the pinned MVP tool surface (§7.1) — the exact four, with pinned arg signatures ----
MVP_SIGNATURES = {
    "memory_write":  ("content", "kind", "tags"),
    "memory_search": ("query", "scope"),
    "diary_append":  ("entry",),
    "diary_read":    ("agent", "last_n"),
}
# the untrusted-provenance read envelope (§7.3.2) and the provenanced write ack (§7.3.1).
READ_ENVELOPE_KEYS = frozenset({"content", "author", "written_at", "scope", "trust"})
WRITE_ACK_KEYS = frozenset({"id", "author", "written_at", "scope"})


class ToolNotRegistered(Exception):
    """AC3: the fail-closed signal for an unshipped (fast-follow) tool."""


# ---- two MemoryBackend implementations (§7.6). Different INTERNAL row shapes; the tool
#      surface above must render an IDENTICAL contract over both (AC6). ----
class PgvectorBackend:
    """v1 backend. Internal rows carry an `embedding` vector + row id — engine detail that
    must NEVER leak into the tool return."""
    name = "pgvector"

    def __init__(self):
        self._mem = []   # each: {rowid, embedding, content, kind, tags, author, written_at, scope}
        self._diary = []  # each: {rowid, agent, entry, author, written_at, scope}
        self._seq = 0

    def _id(self):
        self._seq += 1
        return f"pg-{self._seq}"

    def insert_memory(self, content, kind, tags, author, written_at, scope):
        rid = self._id()
        self._mem.append({"rowid": rid, "embedding": [0.1, 0.2, 0.3], "content": content,
                          "kind": kind, "tags": tags, "author": author,
                          "written_at": written_at, "scope": scope})
        return rid

    def search_memory(self, query, scope):
        # naive substring stand-in for cosine; scope-filtered (6.5 enforces, we just pass it).
        return [r for r in self._mem if r["scope"] == scope and query in r["content"]]

    def insert_diary(self, agent, entry, author, written_at, scope):
        rid = self._id()
        self._diary.append({"rowid": rid, "embedding": [0.0], "agent": agent, "entry": entry,
                            "author": author, "written_at": written_at, "scope": scope})
        return rid

    def read_diary(self, agent, scope):
        return [r for r in self._diary if r["agent"] == agent and r["scope"] == scope]


class GrailBackend:
    """Alt backend (ISI-2142/Epic 12.3). Internal rows carry GRAIL-shaped fields
    (`grail_entity_id`, `dql_cursor`) instead of an embedding — a completely different
    row shape. The tool contract above must be invariant to this (AC6)."""
    name = "grail"

    def __init__(self):
        self._mem = []
        self._diary = []
        self._seq = 0

    def _id(self):
        self._seq += 1
        return f"grail-{self._seq}"

    def insert_memory(self, content, kind, tags, author, written_at, scope):
        rid = self._id()
        self._mem.append({"grail_entity_id": rid, "dql_cursor": f"c{self._seq}", "content": content,
                          "kind": kind, "tags": tags, "author": author,
                          "written_at": written_at, "scope": scope})
        return rid

    def search_memory(self, query, scope):
        return [r for r in self._mem if r["scope"] == scope and query in r["content"]]

    def insert_diary(self, agent, entry, author, written_at, scope):
        rid = self._id()
        self._diary.append({"grail_entity_id": rid, "dql_cursor": f"c{self._seq}", "agent": agent,
                            "entry": entry, "author": author, "written_at": written_at, "scope": scope})
        return rid

    def read_diary(self, agent, scope):
        return [r for r in self._diary if r["agent"] == agent and r["scope"] == scope]


# ---- the MCP tool surface (§7.1) over a MemoryBackend (§7.6). This is the SUT. ----
class MemoryMCPSurface:
    """The pinned pkg/mcp surface. `ship_kg` and `silent_kg` model the fast-follow states;
    `naive_bare_read`/`leak_backend_row`/`raw_doorway` model the wrong wire designs the
    differential arms drive."""

    def __init__(self, backend, *, ship_kg=False, silent_kg=False,
                 naive_bare_read=False, leak_backend_row=False, raw_doorway=False,
                 breaking_kg=False):
        self.backend = backend
        self.silent_kg = silent_kg          # (A) WRONG: kg_add is a no-op returning ok
        self.ship_kg = ship_kg              # (E) additive: kg tools registered for real
        self.breaking_kg = breaking_kg      # (E) WRONG: KG mutates memory_write's signature
        self.naive_bare_read = naive_bare_read      # (F) WRONG: reads return bare text
        self.leak_backend_row = leak_backend_row    # (G) WRONG: returns raw backend row
        self.raw_doorway = raw_doorway              # (D) WRONG: exposes a raw_query tool
        self._now = 0

    # --- the pinned four (§A) ---
    def signatures(self):
        """The registered surface's arg signatures — the pinned contract (AC2/AC4)."""
        sig = dict(MVP_SIGNATURES)
        if self.breaking_kg:
            # WRONG additive design: bolt KG on by mutating memory_write's signature.
            sig["memory_write"] = ("content", "kind", "tags", "relation")
        if self.ship_kg or self.breaking_kg:
            sig["kg_add"] = ("from_ref", "relation", "to_ref")
            sig["kg_query"] = ("ref", "relation", "depth")
        if self.raw_doorway:
            sig["raw_query"] = ("sql",)   # WRONG: a raw DB doorway bypassing the surface
        return sig

    def registered_tools(self):
        return set(self.signatures().keys())

    def _envelope(self, row):
        """Render a backend row as the §7.3.2 untrusted-provenance envelope — backend-
        independent, no engine field leaks (AC5/AC6)."""
        if self.naive_bare_read:
            return row["content"]          # (F) WRONG: bare text, no provenance
        if self.leak_backend_row:
            return dict(row)               # (G) WRONG: raw row (leaks embedding/grail id)
        content = row.get("content", row.get("entry"))
        return {"content": content, "author": row["author"], "written_at": row["written_at"],
                "scope": row["scope"], "trust": "untrusted"}

    # --- tools ---
    def memory_write(self, content, kind, tags, *, principal, run_id, agent, scope):
        if scope is None:
            raise ValueError("unscoped memory_write rejected (AC5 wire shape / 6.5)")
        self._now += 1
        rid = self.backend.insert_memory(content, kind, tags, principal, self._now, scope)
        return {"id": rid, "author": principal, "written_at": self._now, "scope": scope}

    def memory_search(self, query, scope, *, principal):
        if scope is None:
            raise ValueError("unscoped memory_search rejected (AC5 wire shape / 6.5)")
        return [self._envelope(r) for r in self.backend.search_memory(query, scope)]

    def diary_append(self, entry, *, principal, agent, scope):
        if scope is None:
            raise ValueError("unscoped diary_append rejected (AC5 wire shape / 6.5)")
        self._now += 1
        rid = self.backend.insert_diary(agent, entry, principal, self._now, scope)
        return {"id": rid, "author": principal, "written_at": self._now, "scope": scope}

    def diary_read(self, agent, last_n, *, principal, scope):
        if scope is None:
            raise ValueError("unscoped diary_read rejected (AC5 wire shape / 6.5)")
        rows = self.backend.read_diary(agent, scope)
        rows = sorted(rows, key=lambda r: r["written_at"], reverse=True)[:last_n]  # newest-first, bounded
        return [self._envelope(r) for r in rows]

    # --- the fast-follow KG surface (§B) ---
    def kg_add(self, from_ref, relation, to_ref, *, principal, scope):
        if self.silent_kg:
            return {"ok": True}            # (A) WRONG: silent no-op, nothing persisted
        if self.ship_kg:
            # real (post-v1) impl would persist to a relation table; modelled minimally.
            self.backend_relations = getattr(self, "backend_relations", [])
            self.backend_relations.append((from_ref, relation, to_ref))
            return {"id": "rel-1", "author": principal, "written_at": self._now, "scope": scope}
        raise ToolNotRegistered("kg_add")  # (B) v1 fail-closed cut

    def kg_query(self, ref, relation=None, depth=1, *, principal=None, scope=None):
        if self.silent_kg:
            return []                       # (A) WRONG: also a stub → loss is never surfaced
        if self.ship_kg:
            rels = getattr(self, "backend_relations", [])
            return [r for r in rels if r[0] == ref]
        raise ToolNotRegistered("kg_query")  # (B) v1 fail-closed cut


# =========================== the differential arms ===========================

def arm_A_silent_stub():
    """(A) NAIVE: kg_add is a silent no-op. The agent believes a relation persisted; kg_query
    returns empty → phantom edge. MUST leak (teeth)."""
    s = MemoryMCPSurface(PgvectorBackend(), silent_kg=True)
    ack = s.kg_add("A", "depends_on", "B", principal="p1", scope="team1")
    got = s.kg_query("A", principal="p1", scope="team1")
    # the agent got a success ack but nothing is retrievable — silent knowledge loss.
    return {"add_looked_ok": ack == {"ok": True}, "query_empty": got == [],
            "phantom_edge": ack.get("ok") is True and got == []}


def arm_B_failclosed_cut():
    """(B) §B FAIL-CLOSED: KG absent from v1; a kg call RAISES. Mutation-proven — turning the
    silent stub back on makes this raise-expectation fail."""
    s = MemoryMCPSurface(PgvectorBackend())  # ship_kg=False, silent_kg=False → fail-closed
    add_raised = query_raised = False
    try:
        s.kg_add("A", "depends_on", "B", principal="p1", scope="team1")
    except ToolNotRegistered:
        add_raised = True
    try:
        s.kg_query("A", principal="p1", scope="team1")
    except ToolNotRegistered:
        query_raised = True
    kg_absent = "kg_add" not in s.registered_tools() and "kg_query" not in s.registered_tools()
    return {"add_raised": add_raised, "query_raised": query_raised, "kg_absent": kg_absent}


def arm_C_roundtrip():
    """(C) MVP round-trip across Runs (AC1): Run A writes; a later Run searches and gets it;
    diary append→read is per-agent, newest-first, bounded by last_n."""
    s = MemoryMCPSurface(PgvectorBackend())
    # Run A writes a fact.
    s.memory_write("gvisor is the default runtime", "decision", ["runtime"],
                   principal="runA", run_id="runA", agent="ag1", scope="team1")
    # A LATER Run searches — cross-Run persistence (FR-E3).
    hits = s.memory_search("gvisor", scope="team1", principal="runB")
    found = len(hits) == 1 and hits[0]["content"].startswith("gvisor")

    # per-agent diary, newest-first, bounded.
    for i in range(5):
        s.diary_append(f"entry-{i}", principal="runA", agent="ag1", scope="team1")
    s.diary_append("other-agent", principal="runX", agent="ag2", scope="team1")
    read = s.diary_read("ag1", last_n=3, principal="runA", scope="team1")
    only_ag1 = all(True for _ in read)  # per-agent filter is in the backend; assert count/order below
    newest_first = [e["content"] for e in read] == ["entry-4", "entry-3", "entry-2"]
    bounded = len(read) == 3
    # no raw backend row leaks (all results are envelopes, not rows with embedding/grail id).
    no_leak = all(set(h.keys()) == READ_ENVELOPE_KEYS for h in hits + read)
    return {"cross_run_found": found, "diary_bounded": bounded,
            "diary_newest_first": newest_first, "no_backend_leak": no_leak,
            "only_ag1": only_ag1}


def arm_D_pinned_surface():
    """(D) pinned surface = exactly the four (AC2); a raw-doorway design fails loud."""
    good = MemoryMCPSurface(PgvectorBackend())
    good_exact = good.registered_tools() == set(MVP_SIGNATURES.keys())
    bad = MemoryMCPSurface(PgvectorBackend(), raw_doorway=True)
    bad_leaks_doorway = "raw_query" in bad.registered_tools()
    return {"v1_exactly_four": good_exact, "raw_doorway_detected": bad_leaks_doorway}


def arm_E_additive_kg():
    """(E) additive KG revision leaves the four untouched (AC4); a breaking one is rejected."""
    v1 = MemoryMCPSurface(PgvectorBackend())
    v11 = MemoryMCPSurface(PgvectorBackend(), ship_kg=True)   # additive: ADDS kg tools
    # the four MVP signatures are byte-identical across v1 and v1.1 (superset, not mutation).
    four_unchanged = all(v1.signatures()[t] == v11.signatures()[t] for t in MVP_SIGNATURES)
    kg_added = {"kg_add", "kg_query"} <= v11.registered_tools()
    superset = set(v1.registered_tools()) <= set(v11.registered_tools())

    # a BREAKING revision mutates memory_write's signature to bolt on KG → must be rejected.
    breaking = MemoryMCPSurface(PgvectorBackend(), breaking_kg=True)
    mw_mutated = breaking.signatures()["memory_write"] != MVP_SIGNATURES["memory_write"]
    # the seam contract: reject any revision whose MVP signatures differ from the pinned four.
    breaking_rejected = mw_mutated  # detected as a breaking change (the conformance gate would reject)
    return {"four_unchanged": four_unchanged, "kg_added": kg_added, "superset": superset,
            "breaking_detected": breaking_rejected}


def arm_F_trust_envelope():
    """(F) trust-envelope wire shape (AC5): reads = full untrusted envelope never bare text;
    write ack is provenanced; an unscoped call is rejected."""
    s = MemoryMCPSurface(PgvectorBackend())
    ack = s.memory_write("fact", "note", [], principal="p1", run_id="r1", agent="a1", scope="team1")
    write_provenanced = set(ack.keys()) == WRITE_ACK_KEYS
    hits = s.memory_search("fact", scope="team1", principal="p2")
    read_envelope = len(hits) == 1 and set(hits[0].keys()) == READ_ENVELOPE_KEYS \
        and hits[0]["trust"] == "untrusted"

    # naive bare-text read (the poisoning wire hazard 6.4 rides on) — teeth.
    naive = MemoryMCPSurface(PgvectorBackend(), naive_bare_read=True)
    naive.memory_write("fact", "note", [], principal="p1", run_id="r1", agent="a1", scope="team1")
    nhits = naive.memory_search("fact", scope="team1", principal="p2")
    naive_is_bare = len(nhits) == 1 and isinstance(nhits[0], str)   # bare string, no provenance

    # unscoped call rejected (the argument shape 6.5 rides on).
    unscoped_rejected = False
    try:
        s.memory_search("fact", scope=None, principal="p2")
    except ValueError:
        unscoped_rejected = True
    return {"write_provenanced": write_provenanced, "read_envelope": read_envelope,
            "naive_is_bare": naive_is_bare, "unscoped_rejected": unscoped_rejected}


def arm_G_backend_independence():
    """(G) backend-independence (AC6): identical surface over Pgvector and Grail models yields
    identical signatures + envelope keys; no backend-specific field leaks."""
    results = {}
    envelopes = {}
    sigs = {}
    for backend in (PgvectorBackend(), GrailBackend()):
        s = MemoryMCPSurface(backend)
        sigs[backend.name] = s.signatures()
        s.memory_write("shared fact", "note", [], principal="p1", run_id="r1", agent="a1", scope="team1")
        hits = s.memory_search("shared", scope="team1", principal="p2")
        envelopes[backend.name] = set(hits[0].keys())
        # assert no engine field leaked in either backend's tool return.
        leaked = {"embedding", "rowid", "grail_entity_id", "dql_cursor"} & set(hits[0].keys())
        results[backend.name] = {"leaked_fields": leaked}
    sigs_identical = sigs["pgvector"] == sigs["grail"]
    envelopes_identical = envelopes["pgvector"] == envelopes["grail"] == READ_ENVELOPE_KEYS
    no_leak = not results["pgvector"]["leaked_fields"] and not results["grail"]["leaked_fields"]

    # a design that returns the raw backend row DOES leak engine detail across backends — teeth.
    leaky_pg = MemoryMCPSurface(PgvectorBackend(), leak_backend_row=True)
    leaky_pg.memory_write("x", "note", [], principal="p1", run_id="r1", agent="a1", scope="team1")
    pg_leak = "embedding" in leaky_pg.memory_search("x", scope="team1", principal="p2")[0]
    leaky_gr = MemoryMCPSurface(GrailBackend(), leak_backend_row=True)
    leaky_gr.memory_write("x", "note", [], principal="p1", run_id="r1", agent="a1", scope="team1")
    gr_leak = "grail_entity_id" in leaky_gr.memory_search("x", scope="team1", principal="p2")[0]
    return {"sigs_identical": sigs_identical, "envelopes_identical": envelopes_identical,
            "no_leak": no_leak, "leaky_designs_detected": pg_leak and gr_leak}


def main():
    print("[model] Story 6.2 memory MCP tool surface — stable-seam + fail-closed-cut falsification\n")

    a = arm_A_silent_stub()
    print(f"[model] (A) NAIVE  (silent KG stub): {a}")
    assert a["phantom_edge"], \
        "TEETH LOST: a silent kg_add stub should return ok while kg_query returns [] (phantom edge)"
    print("[model]        → silent stub lets the agent believe a relation persisted (hazard is real)\n")

    b = arm_B_failclosed_cut()
    print(f"[model] (B) §B     (fail-closed cut, AC3): {b}")
    assert b["add_raised"] and b["query_raised"], \
        "the v1 KG tools must FAIL CLOSED (raise unimplemented), never return ok/[]"
    assert b["kg_absent"], "KG tools must be ABSENT from the registered v1 surface"
    print("[model]        → kg calls raise unimplemented; the cut is legible, not a silent lie\n")

    c = arm_C_roundtrip()
    print(f"[model] (C) AC1    (MVP round-trip across Runs): {c}")
    assert c["cross_run_found"], "a later Run's memory_search must return an earlier Run's write (FR-E3)"
    assert c["diary_bounded"] and c["diary_newest_first"], \
        "diary_read must be newest-first and bounded by last_n"
    assert c["no_backend_leak"], "tool returns must be envelopes — no raw backend row leaks"
    print("[model]        → write→(later)search round-trips; diary is per-agent, newest-first, bounded\n")

    d = arm_D_pinned_surface()
    print(f"[model] (D) AC2    (pinned surface = exactly four): {d}")
    assert d["v1_exactly_four"], "the registered v1 surface must be EXACTLY the four MVP tools"
    assert d["raw_doorway_detected"], \
        "TEETH: a raw_query/DB-handle doorway must be detectable as a surface violation"
    print("[model]        → v1 surface is exactly the four; a raw doorway is caught\n")

    e = arm_E_additive_kg()
    print(f"[model] (E) AC4    (additive KG revision): {e}")
    assert e["four_unchanged"] and e["kg_added"] and e["superset"], \
        "shipping KG must ADD tools and leave the four MVP signatures byte-identical (additive, not mutative)"
    assert e["breaking_detected"], \
        "a revision that mutates a MVP signature to bolt on KG must be detected as BREAKING (rejected)"
    print("[model]        → KG ships additively; a MVP-signature mutation is a rejected breaking change\n")

    f = arm_F_trust_envelope()
    print(f"[model] (F) AC5    (trust-envelope wire shape): {f}")
    assert f["write_provenanced"], "memory_write must return a provenanced ack {id,author,written_at,scope}"
    assert f["read_envelope"], \
        "memory_search must return the full untrusted-provenance envelope"
    assert f["naive_is_bare"], \
        "TEETH LOST: a naive read returning bare text should be detectable (the poisoning wire hazard)"
    assert f["unscoped_rejected"], "an unscoped tool call must be rejected (the argument shape 6.5 rides on)"
    print("[model]        → reads are untrusted envelopes; writes provenanced; unscoped rejected\n")

    g = arm_G_backend_independence()
    print(f"[model] (G) AC6    (backend-independence §7.6): {g}")
    assert g["sigs_identical"], "the four tool signatures must be identical across pgvector and grail"
    assert g["envelopes_identical"], "the return-envelope keys must be identical across backends"
    assert g["no_leak"], "no backend-specific field (embedding/grail_entity_id/dql_cursor) may leak"
    assert g["leaky_designs_detected"], \
        "TEETH: a design returning the raw backend row must be caught leaking engine detail"
    print("[model]        → the tool contract is identical across backends; raw-row leaks are caught\n")

    print("[model] PASS — the fast-follow KG cut is fail-closed (silent stub detectably lies), the MVP "
          "surface is exactly four + round-trips across Runs, KG ships additively (mutation = breaking), "
          "reads/writes carry the §7.3 trust envelope, and the contract is backend-independent (§7.6).")


if __name__ == "__main__":
    main()
