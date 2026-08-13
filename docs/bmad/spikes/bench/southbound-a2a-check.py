#!/usr/bin/env python3
"""ISI-2213 (Story 5.1) — southbound A2A invocation (core side) falsification.

The locked claim (FR-D1, arch §10.1/§8, NFR-EXT2/I4, ISI-2114 §3): when a Run
dispatches, the CORE submits an A2A task, streams SSE progress into the Run's
event stream, and collects artifacts — reaching the agent through **only** the
six A2A MUST-verbs + the Agent Card, with **zero lateral protocol and zero
runtime-`type` special-casing** (the moat / C10 / NFR-EXT1). This is the
control-plane half of the shim seam; ISI-2114 owns the *shim* half (conformance
C1–C10) and Story 5.2 owns Agent-Card *generation*. Five properties are the
entire correctness content of THIS story, and each is mutation-checked:

  (M — the moat, headline) The core dispatch is runtime-AGNOSTIC: identical for
      every `AgentRuntime.type`, and it NEVER touches a runtime-native side
      channel. A cheating core with an `if type == "openclaw"` branch that reaches
      OpenClaw's native gateway dispatches fine on openclaw but is detectably
      runtime-coupled the moment the type is swapped to hermes (and touches the
      native channel). The conformant core produces a byte-identical dispatch
      trace across both types and leaves `native_calls == 0`.
  (D — deterministic-id dedup, §6.4 C1) The core submits `a2a_task_id = run_id`
      and writes a durable dispatch marker in the SAME txn as the transition, so
      NO crash window produces two agent executions: crash after-submit/before-marker
      re-submits the same id and the shim reattaches; crash before-submit submits once.
  (S — SSE ordering + at-least-once dedup + resume) The core orders progress on
      `seq` (never wall clock), dedups on `(a2a_task_id, seq)`, and re-`StreamEvents`
      resumes from `lastSeq` after a dropped connection — so the ingested run-event
      log is strictly increasing, gap-free, each seq once, despite duplicates,
      reorders, and a mid-stream drop.
  (A — artifact collection fenced + idempotent, §5/C2/C3) Artifacts are collected
      through the FENCED coord API (never a raw write): a re-entered Collecting phase
      upserts the same content-addressed `(work_item, run, kind)` row (one row, not
      two), and a zombie shim that lost its lease is rejected on a STALE fence.
  (T — task-state mapping distinct, §3.1) The A2A task states map to Run phases
      without conflation: `auth-required` → Paused (NOT a Run failure), `completed`
      → collect→done, `failed` → the 3.2 failure edge, `canceled` → Cancelled.

This is a *differential* falsification, not a happy-path demo: every property runs
a NAIVE/cheating design that MUST break (teeth) alongside the conformant design
that MUST hold. If any naive arm stops breaking, the check fails LOUD — the clean
conformant result would then prove nothing. Stdlib only; `python3` it directly.
"""
import sys

RUN_ID = "run-7f3a"
WORK_ITEM = "wi-42"


# ─────────────────────────── the shim model (ISI-2114 §3) ───────────────────────────

class Runtime:
    """A shim sidecar exposing the six A2A MUST-verbs (§3) PLUS a runtime-native
    side channel a cheating core could reach for. `native_calls` counts moat
    violations; a conformant core keeps it 0 for EVERY runtime type. `executions`
    counts agent executions started (C1 invariant: must settle at exactly 1)."""

    def __init__(self, type_):
        self.type = type_
        self.executions = 0
        self.native_calls = 0
        self._session = None        # dedup key == a2a_task_id (deterministic, == run_id)
        self._fence = None
        # The dispatch trace is RECORDED from the real verb calls (verb + args), NOT
        # a hardcoded constant. This is what gives AC1 teeth: a conformant path that
        # forks on `runtime.type` (different envelope, verb order, capability
        # assumption) produces a DIVERGENT recorded trace even when it never reaches
        # the native channel. The trace deliberately excludes `self.type` and card
        # *content* — only the calls the core makes — so two runtimes with identical
        # cards yield identical traces iff the core did not couple to the runtime.
        self.trace = []

    # V1 SubmitTask — deterministic id + dedup (§6.4 C1).
    def submit_task(self, a2a_task_id, envelope, fence):
        self.trace.append(("submit", a2a_task_id, envelope, fence))   # args recorded
        if self._session == a2a_task_id:
            return "reattached"      # second submit with existing id ⇒ NO second execution
        self._session, self._fence = a2a_task_id, fence
        self.executions += 1
        return "started"

    # V2 StreamEvents — native progress as SSE (§4), delivered at-least-once with a
    # mid-stream drop. `since_seq` is the resume cursor the core supplies (lastSeq).
    def stream_events(self, a2a_task_id, since_seq):
        # Source stream is gap-free 1..5 (§4). The WIRE duplicates, reorders, and
        # drops: batch 1 delivers 1,2,2(dup),3 then the connection drops; the core
        # resumes at lastSeq and batch 2 redelivers 3 (at-least-once across the
        # resume boundary) and delivers 5 BEFORE 4 (reorder).
        if since_seq < 1:
            return ([(1, "status", {"state": "working"}),
                     (2, "tool", {"name": "git", "phase": "start"}),
                     (2, "tool", {"name": "git", "phase": "start"}),   # at-least-once DUP
                     (3, "message", {"text": "analysing", "trust": "untrusted"})],
                    True)            # dropped=True → caller must resume from lastSeq
        return ([(3, "message", {"text": "analysing", "trust": "untrusted"}),  # redelivered
                 (5, "status", {"state": "completed"}),                        # REORDER: 5 before 4
                 (4, "tool", {"name": "git", "phase": "result"})],
                False)

    # V6 GetAgentCard — capability contract (§6). The core negotiates against THIS,
    # never against a hardcoded per-type assumption.
    def get_agent_card(self):
        self.trace.append(("card",))     # the fact of negotiation, NOT card content
        return {"schemaVersion": "ksquad.a2a/v1",
                "runtime": {"type": self.type},
                "capabilities": {"streaming": True, "interactivePrompt": False}}

    # THE FORBIDDEN lateral path: runtime-specific native invocation (OpenClaw
    # gateway / Hermes native). A conformant core must NEVER call this.
    def native_gateway(self, cmd):
        self.native_calls += 1
        self.trace.append(("native", self.type, cmd))   # forks the trace too
        return f"{self.type}-native:{cmd}"


class Coord:
    """The fenced coord artifact API (§5/§6.3). The shim/core never writes Postgres
    directly — the coord API validates the fence INSIDE the write txn and upserts on
    `UNIQUE(work_item_id, run_id, kind)` + sha256."""

    def __init__(self):
        self.artifacts = {}         # (work_item, run, kind) -> sha256  (one row per key)
        self.live_fence = 1         # the Run's current fence (§6.2)

    def put_artifact(self, work_item, run, kind, sha, fence, fenced=True):
        if fenced and fence != self.live_fence:
            return "rejected-stale-fence"       # §6.3 / C3: zombie shim can't write
        self.artifacts[(work_item, run, kind)] = sha   # idempotent upsert (§6.4 C2)
        return "committed"


# ─────────────────────────── (M) the moat: runtime-agnostic dispatch ───────────────────────────

def conformant_dispatch(rt):
    """CORE dispatch using ONLY the card + the six verbs. No `type` branching, no
    native channel — identical for every runtime. Returns the RECORDED dispatch trace
    (rt.trace, derived from the real verb calls incl. args) so a type-fork in the
    dispatch — even one that never reaches the native channel — is caught, and asserts
    native_calls stays 0."""
    card = rt.get_agent_card()                          # V6 — negotiate, don't assume
    assert card["capabilities"]["streaming"], "SSE V2 is mandatory (§6.1)"
    rt.submit_task(RUN_ID, envelope="<ctx>", fence=1)   # V1 — deterministic id
    # Trace is DERIVED from the calls made, deliberately excludes rt.type / card
    # content: identical across types iff the core did not couple to the runtime.
    return tuple(rt.trace)


def cheating_dispatch(rt):
    """CORE dispatch that leaks the moat: a runtime-`type` special-case reaches
    OpenClaw's native gateway (a lateral protocol). It 'works' on openclaw and forks
    the path on type — exactly the coupling C10/NFR-EXT1 forbids."""
    rt.get_agent_card()
    if rt.type == "openclaw":                           # ← the moat leak (type ==)
        rt.native_gateway("start-session")              # ← lateral protocol
        rt.submit_task(RUN_ID, envelope="<ctx>", fence=1)
        return tuple(rt.trace)
    rt.submit_task(RUN_ID, envelope="<ctx>", fence=1)   # divergent path for other types
    return tuple(rt.trace)


def check_moat():
    oc, hm = Runtime("openclaw"), Runtime("hermes")
    conf_oc, conf_hm = conformant_dispatch(oc), conformant_dispatch(hm)
    conformant_agnostic = (conf_oc == conf_hm)                 # identical trace across types
    conformant_no_native = (oc.native_calls == 0 and hm.native_calls == 0)

    oc2, hm2 = Runtime("openclaw"), Runtime("hermes")
    cheat_oc, cheat_hm = cheating_dispatch(oc2), cheating_dispatch(hm2)
    cheating_forks = (cheat_oc != cheat_hm)                    # path forked on type
    cheating_touched_native = (oc2.native_calls > 0)          # reached the lateral channel
    cheating_leaks = cheating_forks and cheating_touched_native

    print(f"[M] conformant : trace(openclaw)==trace(hermes)? {conformant_agnostic}  "
          f"native_calls oc={oc.native_calls} hm={hm.native_calls} (must be 0)")
    print(f"[M] cheating   : trace forks on type? {cheating_forks}  native_calls oc={oc2.native_calls} (>0 leak)")
    print(f"[M]   -> conformant_agnostic={conformant_agnostic} conformant_no_native={conformant_no_native} "
          f"cheating_leaks={cheating_leaks} (all True: the moat has teeth)")
    return conformant_agnostic and conformant_no_native and cheating_leaks


# ─────────────────────────── (D) deterministic-id dispatch dedup (§6.4 C1) ───────────────────────────

def dispatch_reentrant(rt, crash_point):
    """Conformant dispatch with a durable marker written in the SAME txn as the
    submit. Deterministic id = run_id, so a re-entry is safe at either crash window.
    The crash fires exactly ONCE (the first pass); reconcile re-entries then proceed."""
    marker = {"dispatched_task_id": None}
    crashed = {"fired": False}

    def attempt():
        # crash BEFORE submit: process dies before anything happens; re-entry submits once.
        if crash_point == "before_submit" and not crashed["fired"]:
            crashed["fired"] = True
            return  # simulated crash, no submit, no marker
        rt.submit_task(RUN_ID, envelope="<ctx>", fence=1)      # deterministic id
        # crash AFTER submit BEFORE marker: shim already has the session; marker unset.
        if crash_point == "after_submit_before_marker" and not crashed["fired"]:
            crashed["fired"] = True
            return  # simulated crash before the marker commits
        marker["dispatched_task_id"] = RUN_ID

    attempt()          # first pass (crashes once, at the configured window)
    attempt()          # reconcile re-entry — re-submits same deterministic id ⇒ shim dedups
    attempt()          # idempotent settle
    return rt.executions


def dispatch_nondeterministic(rt):
    """NAIVE dispatch: a fresh (uuid-like) task id per submit and NO marker → a
    re-entry starts a SECOND agent execution. The teeth for §6.4 C1."""
    for i in range(2):
        rt.submit_task(f"{RUN_ID}-{i}", envelope="<ctx>", fence=1)  # different id each time
    return rt.executions


def check_dispatch_dedup():
    a = Runtime("openclaw"); execs_a = dispatch_reentrant(a, "after_submit_before_marker")
    b = Runtime("openclaw"); execs_b = dispatch_reentrant(b, "before_submit")
    conformant_once = (execs_a == 1 and execs_b == 1)
    n = Runtime("openclaw"); execs_n = dispatch_nondeterministic(n)
    naive_double = (execs_n == 2)
    print(f"[D] conformant : executions after-submit-crash={execs_a} before-submit-crash={execs_b} (both 1)")
    print(f"[D] naive      : executions with nondeterministic id={execs_n} (2 = double-dispatch)")
    print(f"[D]   -> conformant_exactly_once={conformant_once} naive_double_dispatch={naive_double} (both True)")
    return conformant_once and naive_double


# ─────────────────────────── (S) SSE ordering + dedup + resume ───────────────────────────

def ingest_conformant(rt):
    """Consume V2 StreamEvents into the run-event log: dedup on (task, seq), order
    on seq, resume from lastSeq after a drop. Result must be gap-free 1..N, each once."""
    seen, log, last_seq = set(), [], 0
    while True:
        batch, dropped = rt.stream_events(RUN_ID, since_seq=last_seq)
        for seq, typ, payload in batch:
            if seq in seen:                      # at-least-once → dedup on (task, seq)
                continue
            seen.add(seq); log.append((seq, typ))
            last_seq = max(last_seq, seq)         # cursor for resume
        if not dropped:
            break
    log.sort(key=lambda e: e[0])                  # order on seq, NEVER wall clock
    return [s for s, _ in log]


def ingest_naive(rt):
    """NAIVE: append in arrival order, no dedup, order on arrival (≈ wall clock).
    Duplicates get double-counted and the reorder survives — detectably wrong."""
    log, last_seq = [], 0
    for _ in range(2):
        batch, dropped = rt.stream_events(RUN_ID, since_seq=last_seq)
        for seq, typ, payload in batch:
            log.append((seq, typ))                # no dedup
            last_seq = max(last_seq, seq)
        if not dropped:
            break
    return [s for s, _ in log]                     # no sort


def _gapfree_increasing(seqs):
    return seqs == list(range(1, len(seqs) + 1)) and len(seqs) == len(set(seqs))


def check_sse():
    conf = ingest_conformant(Runtime("openclaw"))
    naive = ingest_naive(Runtime("openclaw"))
    conformant_clean = _gapfree_increasing(conf) and conf == [1, 2, 3, 4, 5]
    naive_broken = (not _gapfree_increasing(naive))       # dups + reorder ⇒ not clean
    print(f"[S] conformant : ingested seqs={conf} (must be 1..5, gap-free, each once)")
    print(f"[S] naive      : ingested seqs={naive} (dups/reorder ⇒ broken)")
    print(f"[S]   -> conformant_clean={conformant_clean} naive_broken={naive_broken} (both True)")
    return conformant_clean and naive_broken


# ─────────────────────────── (A) artifact collection fenced + idempotent ───────────────────────────

def check_artifact():
    coord = Coord()
    # Conformant re-entry: same content-addressed row upserted twice ⇒ ONE row.
    r1 = coord.put_artifact(WORK_ITEM, RUN_ID, "diff", sha="abc", fence=1)
    r2 = coord.put_artifact(WORK_ITEM, RUN_ID, "diff", sha="abc", fence=1)  # re-entered Collecting
    one_row = (len(coord.artifacts) == 1 and r1 == "committed" and r2 == "committed")
    # Zombie shim that lost its lease (fence bumped under it) is rejected (§6.3 / C3).
    coord.live_fence = 2
    zr = coord.put_artifact(WORK_ITEM, RUN_ID, "diff", sha="xyz", fence=1, fenced=True)
    zombie_rejected = (zr == "rejected-stale-fence" and coord.artifacts[(WORK_ITEM, RUN_ID, "diff")] == "abc")
    # NAIVE: a raw write that skips the fence check accepts the zombie ⇒ corruption.
    naive = Coord(); naive.live_fence = 2
    nr = naive.put_artifact(WORK_ITEM, RUN_ID, "diff", sha="xyz", fence=1, fenced=False)
    naive_accepts_zombie = (nr == "committed")
    print(f"[A] conformant : rows after double-upsert={len(coord.artifacts)} (1)  zombie_stale_fence={zr!r}")
    print(f"[A] naive      : unfenced write of zombie={nr!r} (accepted = corruption)")
    print(f"[A]   -> one_row={one_row} zombie_rejected={zombie_rejected} naive_accepts_zombie={naive_accepts_zombie}")
    return one_row and zombie_rejected and naive_accepts_zombie


# ─────────────────────────── (T) A2A task-state → Run-phase mapping (§3.1) ───────────────────────────

def map_task_state(task_state):
    """Distinct task-lifecycle → Run-phase mapping (§3.1). auth-required is a
    first-class pause signal, NOT a Run failure."""
    return {"working": "Running",
            "auth-required": "Paused",          # §11 — never `Failed`
            "completed": "Collecting",          # → done after artifact collection
            "failed": "FailureEdge",            # → Story 3.2 detection/backoff
            "canceled": "Cancelled"}[task_state]


def naive_map_task_state(task_state):
    """NAIVE: collapses auth-required into a generic failure ⇒ breaks pause/resume."""
    return "FailureEdge" if task_state in ("failed", "auth-required") else map_task_state(task_state)


def check_state_map():
    conformant_pauses = (map_task_state("auth-required") == "Paused")
    conformant_distinct = (map_task_state("failed") == "FailureEdge"
                           and map_task_state("completed") == "Collecting"
                           and map_task_state("canceled") == "Cancelled")
    naive_conflates = (naive_map_task_state("auth-required") == "FailureEdge")
    print(f"[T] conformant : auth-required->{map_task_state('auth-required')!r} (Paused, not Failed)  "
          f"failed->{map_task_state('failed')!r} completed->{map_task_state('completed')!r}")
    print(f"[T] naive      : auth-required->{naive_map_task_state('auth-required')!r} (conflated to failure)")
    print(f"[T]   -> conformant_pauses={conformant_pauses} conformant_distinct={conformant_distinct} "
          f"naive_conflates={naive_conflates}")
    return conformant_pauses and conformant_distinct and naive_conflates


# ─────────────────────────── driver ───────────────────────────

def main():
    results = {
        "M moat / runtime-agnostic dispatch": check_moat(),
        "D deterministic-id dispatch dedup":  check_dispatch_dedup(),
        "S SSE ordering + dedup + resume":    check_sse(),
        "A artifact fenced + idempotent":     check_artifact(),
        "T task-state mapping distinct":      check_state_map(),
    }
    print()
    failed = [k for k, ok in results.items() if not ok]
    if failed:
        for k in failed:
            print(f"[core] FAIL — property lost its teeth or the conformant path broke: {k}")
        return 1
    print("[core] PASS — the core dispatches southbound over A2A using only the six verbs "
          "+ the Agent Card (runtime-agnostic, zero native channel); deterministic-id dedup "
          "makes dispatch crash-safe (exactly one execution); SSE ingests gap-free/deduped/"
          "resumed into run_events; artifacts collect fenced + idempotent; and auth-required "
          "pauses rather than fails. Every naive counter-design is detectably broken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
