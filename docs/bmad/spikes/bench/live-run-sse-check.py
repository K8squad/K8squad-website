#!/usr/bin/env python3
"""Story 8.2 falsification — live Run progress via SSE through the Next.js BFF proxy (arch §13/§3.1, FR-F2, NFR-PERF2).

FR-F2 / UX 02-run-stream-sse: "Given a Running Run, When I open its stream, Then progress streams live via
SSE through the Next.js BFF proxy (hiding the Go API)." This is the FOUNDATIONAL live-stream story — the ONE
EventSource + BFF proxy that 8.8f (live-Run map), 8.10 (org diagram), 8.11 (agent log tail), and 8.14/8.17
(deep-links) all ride. The load-bearing crux is the *transport shape*, not a pretty timeline: the browser
holds ONE `EventSource` to the **Next.js BFF**, which proxies the Go apiserver's SSE progress bus
**unbuffered**; the browser never touches the Go apiserver directly (§13 one-choke-point BFF rule), never
polls, and the stream is a **projection of the DURABLE coordination record** (§6.5 audit / §6.6 outbox) — so
a reconnect *resumes* from `Last-Event-ID` with no lost events, "durable state, not ephemeral chat" (FR-B3).
It carries provenanced, RBAC-scoped, read-only legibility — NO mutate/claim affordance rides the stream
(no-P2P on the console); Kill Run (FR-F4) is a separate authorized control-plane action, not a stream verb.

A "the timeline rendered some lines" demo passes even if the browser is polling the Go API directly,
un-scoped, buffered until Run-completion, and dropping events on every reconnect. So this is a DIFFERENTIAL
check over the STREAM DESIGN a console would ship. We first prove the FR-F2 ANTI-PATTERN — a
"direct-poll ephemeral" client (the browser polls the Go apiserver directly, unscoped, buffered, in-memory
only, with a claim button on the feed) — is DETECTED as violating every transport invariant (real teeth),
then prove the §13/§3.1 BFF-SSE durable-read-model design violates nothing AND actually replays across a
reconnect with no loss.

Invariants (S1-S7, one per AC):
  S1  SSE PUSH, not polling: progress arrives as server-pushed SSE events over ONE EventSource — never a
      client polling loop (repeated GET on an interval). A poll loop is the FR-F2/NFR-PERF2 regression.
  S2  BFF PROXY hides the Go API (the transport crux): the browser's stream connection terminates at the
      Next.js BFF, which proxies the apiserver SSE. The browser NEVER connects to the Go apiserver directly
      — one authorization choke point (§13). A stream URL pointing the browser at the apiserver leaks the
      API and bypasses the RBAC/JWT wall.
  S3  UNBUFFERED passthrough: the BFF (and any gateway, §16.1 SSE note) flushes each event to the browser as
      it arrives — no response buffering that batches events until the stream closes. A buffered proxy turns
      "live" into "on-completion" (the NFR-PERF2 defect).
  S4  RBAC-SCOPED, deny-by-default: the stream is opened THROUGH the §12.3 RBAC wall — the caller may stream
      only a Run it is entitled to see; no second/BFF authz path, no client-side authz. An unscoped stream
      (any Run id streams to anyone) is the regression.
  S5  DURABLE + RESUMABLE projection (not ephemeral chat): the stream projects the DURABLE coordination
      record (§6.5/§6.6), so on reconnect (`Last-Event-ID`) it resumes from the last delivered event with NO
      loss and NO gap — the events are durable, replayable rows (FR-B3). An in-memory-only stream that drops
      events across a reconnect has broken this. (Non-vacuous: the model must ACTUALLY replay the tail.)
  S6  READ MODEL, no coordination affordance (no-P2P on the console): the stream carries read-only
      legibility only — NO mutate/claim/lease/fence/transition affordance rides it. Kill Run (FR-F4) is a
      separate authorized control-plane action, not a stream verb. A claim/mutate channel on the feed
      reintroduces the console coordination affordance the architecture forbids.
  S7  SERVER-STAMPED PROVENANCE: every streamed event carries server-stamped provenance derived from the
      coordination record — kind in {CHECKOUT,COMMENT,HANDOFF,MEMORY,ARTIFACT}, actor (agent·role),
      timestamp (FR-I3) — never client-fabricated. A client-authored event is not the durable record.

Mutation-proof harness (no vacuous guard): `--mutate=<POLL|DIRECT_API|BUFFERED|UNSCOPED|EPHEMERAL|
P2P_AFFORDANCE|CLIENT_PROV>` injects the corresponding single defect into the CONFORMANT BFF-SSE design; the
check then goes RED with EXACTLY one violation (no guard shadows another; the ISI-2346-F1 vacuous-tooth class
is excluded by construction). Baseline `python3 live-run-sse-check.py` exits 0; each `--mutate=NAME` exits 1.
stdlib only.

Runtime proof (owned elsewhere). The real EventSource→BFF→apiserver SSE on a cluster (an actual Running Run,
the browser opening the stream through the BFF with no direct-to-apiserver reachability, unbuffered flush
under the §16.1 gateway, and reconnect-resume) is exercised by the console E2E (05-testing) + the §16.1
Gateway SSE conformance; this model check guards the construction-time TRANSPORT shape — 8.2's crux and the
thing FR-F2 asked (live, via SSE, through the BFF, hiding the Go API).
"""
import sys

# ---- which conformant invariant to sabotage (mutation-proof harness). Empty = baseline. ----
MUTATE = ""


def mut(name):
    """True iff we are injecting the `name` bug into the conformant BFF-SSE design (verifies teeth)."""
    return MUTATE == name


ALLOWED_KINDS = {"CHECKOUT", "COMMENT", "HANDOFF", "MEMORY", "ARTIFACT"}
FORBIDDEN_AFFORDANCES = {"claim", "reassign", "transition", "mutate", "lease", "fence", "handoff-write"}

# The durable coordination-record events a Running Run emits (§6.5 audit / §6.6 outbox). The stream is a
# PROJECTION of these durable rows — the source of both provenance (S7) and reconnect-replay (S5).
DURABLE_LOG = [
    {"id": 1, "kind": "CHECKOUT", "actor": "Reviewer·reviewer", "ts": "02:48:01", "source": "coord_record"},
    {"id": 2, "kind": "COMMENT",  "actor": "Reviewer·reviewer", "ts": "02:48:07", "source": "coord_record"},
    {"id": 3, "kind": "ARTIFACT", "actor": "Reviewer·reviewer", "ts": "02:48:19", "source": "coord_record"},
    {"id": 4, "kind": "HANDOFF",  "actor": "Reviewer·reviewer", "ts": "02:48:22", "source": "coord_record"},
    {"id": 5, "kind": "MEMORY",   "actor": "Fixer·fixer",       "ts": "02:49:03", "source": "coord_record"},
    {"id": 6, "kind": "COMMENT",  "actor": "Fixer·fixer",       "ts": "02:49:11", "source": "coord_record"},
]

# The mid-stream reconnect the durable projection must survive: the client last saw event id=3, drops the
# connection, and reconnects with `Last-Event-ID: 3`. A durable projection must replay exactly {4,5,6}.
LAST_EVENT_ID = 3


# ---- the stream design: what the console + BFF ship for the live Run stream ------------------------

def bff_sse_design():
    """The §13/§3.1 conformant design: ONE EventSource → Next.js BFF → apiserver SSE progress bus,
    unbuffered, RBAC-scoped, a DURABLE-record projection that resumes on Last-Event-ID, read-only with
    server-stamped provenance. Each mutation grafts ONE FR-F2 defect onto this conformant path so exactly
    one invariant flips."""

    # S1: progress arrives as server-pushed SSE over one EventSource — never a client polling loop.
    transport = "poll" if mut("POLL") else "sse"

    # S2 (the crux): the browser's stream terminates at the BFF, which proxies the apiserver. DIRECT_API
    # points the browser at the Go apiserver directly, leaking the API and bypassing the choke point.
    browser_connects_to = "apiserver" if mut("DIRECT_API") else "bff"

    # S3: the BFF passes SSE through unbuffered — each event flushes as it arrives (no batch-until-close).
    proxy_buffering = True if mut("BUFFERED") else False

    # S4: the stream is opened through the §12.3 deny-by-default RBAC wall — only entitled Runs.
    rbac_scoped = False if mut("UNSCOPED") else True

    # S5: the stream projects the DURABLE coordination record, so it replays on reconnect. EPHEMERAL makes
    # it in-memory only — a reconnect loses everything after the drop.
    durable_projection = False if mut("EPHEMERAL") else True

    # S6: read-only legibility — no coordination affordance rides the stream. P2P_AFFORDANCE grafts a claim
    # button onto the feed (the console coordination affordance no-P2P forbids). Kill Run (FR-F4) is a
    # SEPARATE authorized control-plane POST, not a stream verb — never in this list.
    affordances = ["open-run", "navigate-work-item", "navigate-agent"]
    if mut("P2P_AFFORDANCE"):
        affordances.append("claim")

    # S7: every event carries server-stamped provenance from the coord record. CLIENT_PROV lets the client
    # fabricate one event (source='client') — not the durable record.
    events = [dict(e) for e in DURABLE_LOG]
    if mut("CLIENT_PROV"):
        events[2] = {**events[2], "source": "client", "actor": "browser-injected"}

    return {
        "transport": transport, "browser_connects_to": browser_connects_to,
        "proxy_buffering": proxy_buffering, "rbac_scoped": rbac_scoped,
        "durable_projection": durable_projection, "affordances": affordances, "events": events,
    }


def direct_poll_ephemeral_design():
    """The FR-F2 ANTI-PATTERN: the browser POLLS the Go apiserver directly (no BFF), unscoped, the proxy
    buffers, the stream is in-memory only (no reconnect replay), and a claim button rides the feed. Every
    transport invariant is violated — the harness must catch it on every axis."""
    return {
        "transport": "poll", "browser_connects_to": "apiserver",
        "proxy_buffering": True, "rbac_scoped": False,
        "durable_projection": False, "affordances": ["open-run", "claim"],
        # client-fabricated timeline lines with a non-record kind — not the durable coordination record.
        "events": [{"id": 1, "kind": "chat", "actor": "browser", "ts": "?", "source": "client"}],
    }


# ---- replay across a reconnect: the durable projection's non-vacuous S5 proof ----------------------

def replay_after_reconnect(design, last_event_id):
    """What the stream delivers after a reconnect at `Last-Event-ID: last_event_id`. A DURABLE projection
    replays the coord-record tail (ids > last_event_id); an ephemeral in-memory stream lost them."""
    if not design["durable_projection"]:
        return []   # in-memory only — everything after the drop is gone
    return [e for e in DURABLE_LOG if e["id"] > last_event_id]


# ---- invariant checks: return a list of violation strings ------------------------------------------

def check_stream_invariants(d):
    """Assert the §13/§3.1 live-Run-stream transport invariants over one stream design."""
    viol = []

    # S1: SSE push, never a polling loop.
    if d["transport"] != "sse":
        viol.append(f"progress delivered via {d['transport']!r}, not server-pushed SSE — FR-F2/NFR-PERF2 "
                    f"requires ONE EventSource, never a client polling loop (S1)")

    # S2 (the crux): the browser connects to the BFF, never the Go apiserver directly.
    if d["browser_connects_to"] != "bff":
        viol.append(f"the browser opens the stream against {d['browser_connects_to']!r} directly — the "
                    f"Next.js BFF must proxy the apiserver SSE so the Go API stays hidden behind one "
                    f"authorization choke point (S2/§13 'no direct kube/apiserver')")

    # S3: the proxy is unbuffered — events flush as they arrive.
    if d["proxy_buffering"]:
        viol.append("the BFF/gateway BUFFERS the SSE response (batches events until close) — 'live' becomes "
                    "'on-completion'; the proxy must flush each event as it arrives (S3/§16.1 SSE/NFR-PERF2)")

    # S4: the stream passes the deny-by-default RBAC wall.
    if not d["rbac_scoped"]:
        viol.append("the stream is UNSCOPED (any Run id streams to any caller) — it must open through the "
                    "§12.3 deny-by-default RBAC wall; no second/client-side authz path (S4)")

    # S5: durable, resumable projection — a reconnect replays the coord-record tail with no loss.
    resumed = replay_after_reconnect(d, LAST_EVENT_ID)
    expected_tail = [e["id"] for e in DURABLE_LOG if e["id"] > LAST_EVENT_ID]
    if [e["id"] for e in resumed] != expected_tail:
        viol.append(f"reconnect at Last-Event-ID={LAST_EVENT_ID} replayed "
                    f"{[e['id'] for e in resumed]} not {expected_tail} — the stream must project the DURABLE "
                    f"coordination record (§6.5/§6.6) and resume with no lost events, not be ephemeral chat "
                    f"(S5/FR-B3)")

    # S6: read model — no coordination affordance rides the stream.
    riding = sorted(set(d["affordances"]) & FORBIDDEN_AFFORDANCES)
    if riding:
        viol.append(f"the stream carries coordination affordance(s) {riding} — the live stream is read-only "
                    f"legibility; claim/lease/transition never ride it, and Kill Run (FR-F4) is a separate "
                    f"authorized control-plane action, not a stream verb (S6/no-P2P on the console)")

    # S7: every event is a server-stamped coord-record projection with a legible kind.
    for e in d["events"]:
        if e.get("source") != "coord_record":
            viol.append(f"event id={e.get('id')} has provenance source={e.get('source')!r} — every streamed "
                        f"event must be a SERVER-STAMPED projection of the coordination record, never "
                        f"client-fabricated (S7/FR-I3)")
        elif e.get("kind") not in ALLOWED_KINDS:
            viol.append(f"event id={e.get('id')} kind={e.get('kind')!r} is not a coordination-record kind "
                        f"{sorted(ALLOWED_KINDS)} — the stream renders durable coord events, not chat "
                        f"(S7/FR-B3)")
    return viol


def _live_shape_ok(d):
    """Non-vacuous S5/S7: the conformant model must ACTUALLY deliver the durable events AND replay the full
    tail on reconnect — proving the projection is real, not vacuously 'stream nothing'."""
    if len(d["events"]) != len(DURABLE_LOG):
        return False
    resumed = replay_after_reconnect(d, LAST_EVENT_ID)
    return [e["id"] for e in resumed] == [e["id"] for e in DURABLE_LOG if e["id"] > LAST_EVENT_ID] \
        and len(resumed) > 0


def main():
    argv = sys.argv[1:]
    global MUTATE
    for a in argv:
        if a.startswith("--mutate="):
            MUTATE = a.split("=", 1)[1]
    valid = {"", "POLL", "DIRECT_API", "BUFFERED", "UNSCOPED", "EPHEMERAL", "P2P_AFFORDANCE", "CLIENT_PROV"}
    if MUTATE not in valid:
        print(f"[model] unknown --mutate={MUTATE!r}; valid: {sorted(valid - {''})}")
        return 2

    # Teeth: the FR-F2 direct-poll-ephemeral anti-pattern must be DETECTED as violating the transport model.
    anti = check_stream_invariants(direct_poll_ephemeral_design())
    print(f"[model] FR-F2 direct-poll-ephemeral client : {len(anti)} violation(s) -> "
          f"{'DETECTED' if anti else 'NONE (teeth lost!)'}")
    for v in anti:
        print(f"[model]   - {v}")
    if len(anti) < 6:
        print("[model] FAIL — a browser that polls the Go apiserver directly, unscoped, buffered, ephemeral, "
              "with a claim button on the feed should break the transport model on every axis but did not; "
              "no teeth.")
        return 1

    # The §13/§3.1 BFF-SSE design must hold every invariant (or, under --mutate, break exactly one).
    d = bff_sse_design()
    conformant = check_stream_invariants(d)
    print(f"[model] §13/§3.1 BFF-SSE durable read model{f' [--mutate={MUTATE}]' if MUTATE else ''}: "
          f"{len(conformant)} violation(s); transport={d['transport']}, "
          f"browser->{d['browser_connects_to']}, buffered={d['proxy_buffering']}, "
          f"rbac_scoped={d['rbac_scoped']}, durable={d['durable_projection']}")
    for v in conformant:
        print(f"[model]   - {v}")

    if MUTATE:
        # A mutation must flip the conformant path RED with EXACTLY ONE violation (no shadowing).
        if len(conformant) == 1:
            print(f"[model] PASS(mutation) — --mutate={MUTATE} flips the BFF-SSE design RED with exactly one "
                  f"violation; the guard is independently load-bearing.")
            return 1
        print(f"[model] FAIL(mutation) — --mutate={MUTATE} produced {len(conformant)} violations, not exactly "
              f"one; a guard is vacuous or shadows another.")
        return 1

    if conformant:
        print("[model] FAIL — the §13/§3.1 BFF-SSE design must hold every transport invariant.")
        return 1
    if not _live_shape_ok(d):
        print("[model] FAIL — the conformant model must actually deliver the durable events AND replay the "
              "full tail on reconnect (non-vacuous S5/S7).")
        return 1

    print("[model] PASS — the direct-poll-ephemeral client detectably breaks the transport model; the "
          "§13/§3.1 BFF-SSE design holds S1-S7 (SSE push not polling, the BFF proxy hides the Go API, "
          "unbuffered passthrough, RBAC-scoped, a durable coord-record projection that replays on "
          "Last-Event-ID, read-only with no coordination affordance, server-stamped provenance) and "
          "actually replays events {4,5,6} across a mid-stream reconnect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
