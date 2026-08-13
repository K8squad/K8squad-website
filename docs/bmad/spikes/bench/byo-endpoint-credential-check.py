#!/usr/bin/env python3
"""Story 7.5 falsification — Ollama / BYO-endpoint credential shape (arch §10.3/§11, ADR-026, FR-G1/G2).

This is the THIRD concrete credential story, beside 7.2 (Claude-family OAuth-refresh) and 7.3
(second-runtime static API key). Its distinctive crux is the SHAPE of the credential: for a BYO
Ollama / OpenAI-compatible Agent (Story 5.7) the "credential" is an **endpoint** — an endpoint URL
(+ an OPTIONAL token) held in a **per-user Secret ref** (`Agent.spec.modelEndpointRef`) — while the
**model name is plain, non-secret Agent-level config** (`Agent.spec.model`). The §11 credential table
now reads **Two → Three stories** (ADR-026): this row is

    Acquisition = an endpoint URL (+ optional token) supplied DIRECTLY into a per-user Secret. There
                  is NO paid-provider token, NO interactive OAuth step, NO refresh token.
    Placement   = endpoint (+ optional token) lives in the Secret; the **model name is plain
                  Agent-level config** (`Agent.spec.model`) — the two axes are NOT co-located.
    Lifecycle   = **static** — no ~8h TTL, no refresh controller, no ~9-day window; the endpoint
                  Secret changes ONLY when the operator rotates it (an in-place Secret update).
    Injection   = the shim maps the Secret to the runtime's model config (the OpenAI-compatible
                  base-URL, e.g. `…:11434/v1`); the endpoint/token material is never logged (5.4).
    Reachability= an UNREACHABLE endpoint surfaces as **Paused(endpoint_unreachable)** (the shared
                  7.4 path), resumed on the operator's Secret update / endpoint recovery — NEVER an
                  opaque failure (crashloop / silent Run-fail).
    Token type / lifecycle = **pinned per runtime as capability metadata** (FR-G2) — `static-endpoint`
                  — so the core hardcodes no vendor's flow (vendor-neutral by construction).

This is a DIFFERENTIAL check over the credential *lifecycle a driver would produce* for a BYO-endpoint
Agent. The teeth: a happy-path "the pod reached an endpoint and ran" demo passes even if the platform
(a) falls back to a SHARED platform endpoint (the vendor-lock §11 forbids, reopened on the endpoint
axis), (b) bakes the endpoint into plain CR config while stuffing the model name into the Secret
(inverting the placement split), (c) grafts the Claude ~8h refresh controller / a ~9-day cred_expired
pause onto a static endpoint, (d) crashloops opaquely instead of Pausing legibly when the endpoint is
down, (e) hardcodes oauth-refresh in the core, or (f) echoes the endpoint token. So we first prove the
SHARED/CLAUDE-SHAPED anti-pattern is DETECTED as violating every BYO-endpoint invariant — then prove
the §11 static-endpoint lifecycle violates nothing and pauses EXACTLY once, on an endpoint-unreachable
signal, resuming when the operator updates the Secret.

Invariants (E1-E7, mapped to AC1-AC7):
  E1  ENDPOINT-VIA-SECRET: the endpoint is resolved from a per-user Secret ref (`modelEndpointRef`),
      NEVER a shared platform endpoint. A shared-endpoint fallback is the §11 vendor-lock, reopened.
  E2  PLACEMENT SPLIT: the endpoint (+ optional token) lives in the Secret; the model name lives in
      plain Agent-level config (`Agent.spec.model`). Endpoint-in-plain-CR (private endpoint leaks into
      the CR, rotation becomes a CR edit) or model-in-Secret (non-secret config coupled to the
      credential) inverts the shape.
  E3  STATIC — NO REFRESH CONTROLLER: the Secret is written ONLY by the operator (provision +
      rotation); there is NO ~8h controller refresh write. A static endpoint has nothing to refresh.
  E4  IN-PLACE ROTATION: rotation updates the SAME per-user Secret name — never a freshly minted
      Secret that strands existing mounters.
  E5  REACHABILITY IS LEGIBLE: an unreachable endpoint yields Paused(endpoint_unreachable) — resumed
      on the operator's Secret update — and NOTHING else (no cred_expired/reauth timer pause, no
      opaque crashloop / silent Run-fail). Non-vacuous: it must ACTUALLY pause once and resume.
  E6  VENDOR-NEUTRAL LIFECYCLE: the lifecycle the core applies equals the Agent Card's advertised
      credentialLifecycle (FR-G2) — 'static-endpoint' — not a hardcoded oauth-refresh.
  E7  NO MATERIAL LEAK: the endpoint URL / optional token never appears on an observable surface
      (Agent Card, screen-05 health, NATS events, logs) — only credentialType/credentialLifecycle
      metadata + the Secret NAME do (NFR-SEC3, §17.1).

Mutation-proof harness (no vacuous guard): `--mutate=<SHARED_ENDPOINT|PLACEMENT_INVERTED|
CONTROLLER_REFRESH|SECRET_CHURN|OPAQUE_FAIL|CORE_HARDCODE|LEAK>` injects the corresponding single
defect into the CONFORMANT static-endpoint path; the check then goes RED with EXACTLY that one
violation (no guard shadows another; the ISI-2346-F1 vacuous-tooth class is excluded by construction).
Baseline `python3 byo-endpoint-credential-check.py` exits 0; each `--mutate=NAME` exits 1. stdlib only.

Runtime proof (owned elsewhere). The real endpoint mount + unreachable→Paused→resume is exercised on a
cluster by 5.4 (injection contract), 7.4 (pause/resume), and the ISI-2114/ISI-2157 conformance Ollama
lane ($0, no paid credential); this model check guards the construction-time credential *shape* — 7.5's
crux and the third-story lock the §11 credential table records.
"""
import sys

# ---- which conformant invariant to sabotage (mutation-proof harness). Empty = baseline. ----
MUTATE = ""


def mut(name):
    """True iff we are injecting the `name` bug into the conformant static-endpoint path (verifies teeth)."""
    return MUTATE == name


ACCESS_TTL_H = 8            # the ~8h Claude access-token TTL — a BYO endpoint has NO such TTL
WINDOW_H = 9 * 24          # the ~9-day Claude refresh-window — a BYO endpoint has NO such window
HORIZON_H = 12 * 24        # 12-day timeline in hours
UNREACH_H = 100            # the operator's endpoint goes unreachable out-of-band at this hour
RECOVER_H = 104           # operator rotates modelEndpointRef to a reachable endpoint -> Run resumes

RUNTIME = "opencode"                          # the byoModelEndpoint-capable runtime (Story 5.8)
MODEL = "qwen3"                               # Agent.spec.model — PLAIN, non-secret Agent-level config
SECRET = "alice-ollama-endpoint"             # per-user modelEndpointRef Secret (Story 7.1 shape)
NS = "ksquad-team-alpha-3f1a"                 # the Agent's own Team namespace
ENDPOINT = "http://alice-ollama.hosted.example:11434/v1"   # endpoint URL (held in the Secret)
ENDPOINT_TOKEN = "ollama-tok-LIVE-endpoint-material"       # OPTIONAL bearer token (held in the Secret)
CRED_TYPE = "byo-endpoint"
LIFECYCLE = "static-endpoint"                # the runtime's PINNED lifecycle metadata (FR-G2)
SHARED_PLATFORM_ENDPOINT = "http://ksquad-shared-ollama.svc:11434/v1"   # the §11-forbidden fallback


def _refresh_hours(horizon_h):
    """The ~8h-cadence pre-expiry refresh hours a Claude-shaped controller would (wrongly) run."""
    hrs, t = [], ACCESS_TTL_H - 1
    while t <= horizon_h:
        hrs.append(t)
        t += ACCESS_TTL_H
    return hrs


# ---- lifecycle drivers: each returns the credential lifecycle a design would produce --------------

def lifecycle_static_endpoint():
    """The §11 third-story row: an endpoint URL (+ optional token) supplied DIRECTLY into a per-user
    Secret; the model name is plain Agent-level config; no OAuth, no refresh token, no refresh
    controller; the endpoint Secret changes ONLY on operator rotation = an in-place update; the only
    pause is Paused(endpoint_unreachable) on a connectivity signal, resumed on the operator's Secret
    update."""
    # Placement: endpoint (+ optional token) in the Secret; model name in plain Agent config.
    if mut("PLACEMENT_INVERTED"):
        secret_holds = {"model": MODEL}                              # non-secret config coupled to cred
        plain_config = {"endpoint": ENDPOINT}                        # private endpoint leaks into the CR
    else:
        secret_holds = {"endpoint": ENDPOINT, "token": ENDPOINT_TOKEN}
        plain_config = {"model": MODEL}

    provisioned = {
        # A BYO endpoint has NO paid-provider token, NO OAuth, NO refresh token.
        "endpoint_source": "shared-platform-endpoint" if mut("SHARED_ENDPOINT") else "secret-ref",
        "has_refresh": False,
        "acquired_via": "direct-endpoint",
        "credentialType": CRED_TYPE,
        "credentialLifecycle": LIFECYCLE,
        "secret_holds": secret_holds,
        "plain_config": plain_config,
    }
    # Writes: operator provisions once. There is NO controller refresh — nothing to refresh.
    writes = [(0, "operator", SECRET, "provision")]
    if mut("CONTROLLER_REFRESH"):
        # Graft the Claude ~8h refresh controller onto a static endpoint: a writer that must not exist.
        for h in _refresh_hours(HORIZON_H):
            writes.append((h, "controller", SECRET, "refresh"))

    pauses, resumes, opaque_fail = [], [], False
    # Scenario: the operator's endpoint goes unreachable out-of-band -> connectivity signal.
    if mut("OPAQUE_FAIL"):
        # The defect 7.4 forbids: the pod crashloops / the Run fails opaquely, with no legible Paused.
        opaque_fail = True
    else:
        pauses.append((UNREACH_H, "endpoint_unreachable"))
        # Operator rotates modelEndpointRef in place to a reachable endpoint -> Run resumes.
        rotate_name = "alice-ollama-endpoint-v2" if mut("SECRET_CHURN") else SECRET   # churn strands mounters
        writes.append((RECOVER_H, "operator", rotate_name, "rotation"))
        resumes.append((RECOVER_H, "secret_updated"))

    # The shim injects the endpoint into the runtime model config (5.4); metadata surfaces reference
    # only the Secret NAME — never the endpoint URL or token material.
    observable = [
        f"agentCard.credentialType={CRED_TYPE}",
        f"agentCard.credentialLifecycle={LIFECYCLE}",
        f"agentCard.model={MODEL}",
        "screen05.health=connected",
        f"nats.event=credential.rotated secret={SECRET}",
    ]
    if mut("LEAK"):
        observable.append(f"log: injected model base-url {ENDPOINT} auth={ENDPOINT_TOKEN}")

    return {"writes": writes, "pauses": pauses, "resumes": resumes, "opaque_fail": opaque_fail,
            "provisioned": provisioned, "cardLifecycle": provisioned["credentialLifecycle"],
            "observable": observable}


def lifecycle_shared_claude_shaped():
    """The ANTI-PATTERN: the BYO endpoint modeled as a paid/Claude vendor. It falls back to a SHARED
    platform endpoint, bakes the endpoint into plain CR config while stuffing the model name into the
    Secret (placement inverted), stands up a leader-elected controller "refreshing" the endpoint every
    ~8h with a fresh Secret each time, fires a spurious ~9-day cred_expired pause, and echoes the
    endpoint token. Every BYO-endpoint invariant is violated — the harness must catch it."""
    provisioned = {"endpoint_source": "shared-platform-endpoint", "has_refresh": True,
                   "acquired_via": "interactive-oauth", "credentialType": CRED_TYPE,
                   "credentialLifecycle": "oauth-refresh",
                   "secret_holds": {"model": MODEL},          # model coupled into the Secret (inverted)
                   "plain_config": {"endpoint": SHARED_PLATFORM_ENDPOINT}}   # endpoint in plain CR
    writes = [(0, "controller", SECRET, "provision")]
    for i, h in enumerate(_refresh_hours(HORIZON_H)):
        writes.append((h, "controller", f"{SECRET}-r{i}", "refresh"))    # controller refresh + name churn
    pauses = [(WINDOW_H, "cred_expired")]                                # spurious ~9-day timer pause
    return {"writes": writes, "pauses": pauses, "resumes": [], "opaque_fail": False,
            "provisioned": provisioned, "cardLifecycle": provisioned["credentialLifecycle"],
            "observable": [f"log: minted model base-url {SHARED_PLATFORM_ENDPOINT} auth={ENDPOINT_TOKEN}",
                           "agentCard.credentialLifecycle=oauth-refresh"]}


# ---- the core's lifecycle resolution — vendor-neutral (metadata-driven) vs hardcoded --------------

def core_applied_lifecycle(card_lifecycle):
    """What lifecycle the CORE actually applies to the Run. Vendor-neutral (FR-G2): it reads the Agent
    Card's advertised credentialLifecycle. CORE_HARDCODE models a core that ignores metadata and bakes
    in the Claude oauth-refresh flow for every runtime — the not-vendor-neutral defect."""
    if mut("CORE_HARDCODE"):
        return "oauth-refresh"
    return card_lifecycle


# ---- invariant checks: return a list of violation strings -----------------------------------------

KEY_MATERIAL_MARKERS = (ENDPOINT, ENDPOINT_TOKEN, SHARED_PLATFORM_ENDPOINT, "-material", "refresh_token=")


def check_endpoint_invariants(lc):
    """Assert the §11 BYO-endpoint (static-endpoint) invariants over one lifecycle. Returns violations."""
    viol = []
    p = lc["provisioned"]

    # E1: the endpoint is resolved from a per-user Secret ref, NEVER a shared platform endpoint.
    if p["endpoint_source"] != "secret-ref":
        viol.append(f"endpoint resolved from {p['endpoint_source']!r}, not a per-user modelEndpointRef "
                    f"Secret — a shared platform endpoint is the vendor-lock §11 forbids, reopened on "
                    f"the endpoint axis (E1/§11/FR-G1)")

    # E2: placement split — endpoint (+ optional token) in the Secret; model name in plain Agent config.
    endpoint_in_secret = "endpoint" in p["secret_holds"]
    model_in_plain = "model" in p["plain_config"]
    endpoint_in_plain = "endpoint" in p["plain_config"]
    model_in_secret = "model" in p["secret_holds"]
    if not endpoint_in_secret or not model_in_plain or endpoint_in_plain or model_in_secret:
        viol.append(f"placement inverted: secret_holds={sorted(p['secret_holds'])}, "
                    f"plain_config={sorted(p['plain_config'])} — the endpoint (+ optional token) must "
                    f"live in the Secret and the model name in plain Agent-level config; an endpoint in "
                    f"plain CR leaks the private endpoint & makes rotation a CR edit, and a model in the "
                    f"Secret couples non-secret config to the credential (E2/§10.3/ADR-026)")

    # E3: no refresh controller — the Secret is written ONLY by the operator (provision + rotation).
    refreshers = {actor for _, actor, _, kind in lc["writes"] if kind == "refresh"}
    writers = {actor for _, actor, _, _ in lc["writes"]}
    if refreshers or writers - {"operator"}:
        viol.append(f"Secret written by non-operator {sorted(writers - {'operator'}) or sorted(refreshers)} "
                    f"— a static endpoint has no ~8h TTL to refresh; only the operator writes it "
                    f"(provision + rotation), never a refresh controller (E3/§11)")

    # E4: rotation is in-place on the SAME Secret name — never a freshly minted Secret.
    names = {name for _, _, name, _ in lc["writes"]}
    if names != {SECRET}:
        viol.append(f"writes churn Secret name(s) {sorted(names)} != {{{SECRET!r}}} — rotation is an "
                    f"in-place update of the same per-user Secret so mounters keep resolving (E4/§11)")

    # E5: reachability is legible — Paused(endpoint_unreachable), never an opaque crashloop / other pause.
    if lc["opaque_fail"]:
        viol.append(f"endpoint went unreachable but the Run failed opaquely (crashloop / silent Run-fail) "
                    f"with no Paused condition — an unreachable endpoint must surface as "
                    f"Paused(endpoint_unreachable), not an opaque failure (E5/7.4/§11)")
    reasons = [r for _, r in lc["pauses"]]
    bad = [r for r in reasons if r != "endpoint_unreachable"]
    if bad:
        viol.append(f"Run paused for {bad} — a static endpoint does not self-expire on an ~8h/~9-day "
                    f"timer; the only pause is Paused(endpoint_unreachable) on a connectivity signal, "
                    f"resumed on the operator's Secret update (E5/§11/7.4)")

    # E6: the core applies the runtime's PINNED lifecycle metadata (vendor-neutral), == 'static-endpoint'.
    applied = core_applied_lifecycle(lc["cardLifecycle"])
    if applied != lc["cardLifecycle"] or applied != LIFECYCLE:
        viol.append(f"core applied lifecycle {applied!r} but the runtime's pinned Agent-Card metadata is "
                    f"{lc['cardLifecycle']!r} (expected {LIFECYCLE!r}) — the core must be vendor-neutral "
                    f"and read the lifecycle from metadata, not hardcode Claude's oauth-refresh (E6/FR-G2)")

    # E7: no endpoint/token material on any observable surface — metadata + Secret name only.
    for line in lc["observable"]:
        if any(m in line for m in KEY_MATERIAL_MARKERS):
            viol.append(f"endpoint material leaked on an observable surface: {line!r} — only "
                        f"credentialType/credentialLifecycle metadata + the Secret name may surface; the "
                        f"endpoint URL/token is injected into model config, never logged (E7/NFR-SEC3/§17.1)")
    return viol


def _resume_shape_ok(lc):
    """Non-vacuous E5: the static model must ACTUALLY pause exactly once on the endpoint-unreachable
    signal AND resume on the operator's Secret update — proving AC5 is not vacuously met by 'never
    pause / crash silently'."""
    reasons = sorted(r for _, r in lc["pauses"])
    triggers = sorted(t for _, t in lc["resumes"])
    return reasons == ["endpoint_unreachable"] and triggers == ["secret_updated"] and not lc["opaque_fail"]


def main():
    argv = sys.argv[1:]
    global MUTATE
    for a in argv:
        if a.startswith("--mutate="):
            MUTATE = a.split("=", 1)[1]
    valid = {"", "SHARED_ENDPOINT", "PLACEMENT_INVERTED", "CONTROLLER_REFRESH", "SECRET_CHURN",
             "OPAQUE_FAIL", "CORE_HARDCODE", "LEAK"}
    if MUTATE not in valid:
        print(f"[model] unknown --mutate={MUTATE!r}; valid: {sorted(valid - {''})}")
        return 2

    # Teeth: the shared/Claude-shaped lifecycle must be DETECTED as violating the BYO-endpoint model.
    shaped = check_endpoint_invariants(lifecycle_shared_claude_shaped())
    print(f"[model] shared/Claude-shaped BYO-endpoint lifecycle : {len(shaped)} violation(s) -> "
          f"{'DETECTED' if shaped else 'NONE (teeth lost!)'}")
    for v in shaped:
        print(f"[model]   - {v}")
    if len(shaped) < 5:
        print("[model] FAIL — the shared/Claude-shaped lifecycle should break the BYO-endpoint model on "
              "every axis but did not; no teeth.")
        return 1

    # The §11 static-endpoint lifecycle must hold every invariant (or, under --mutate, break exactly one).
    lc = lifecycle_static_endpoint()
    static = check_endpoint_invariants(lc)
    writers = sorted({a for _, a, _, _ in lc["writes"]})
    print(f"[model] §11 static-endpoint lifecycle{f' [--mutate={MUTATE}]' if MUTATE else ''}: "
          f"{len(static)} violation(s); pauses={[r for _,r in lc['pauses']]}; "
          f"resumes={[t for _,t in lc['resumes']]}; opaque_fail={lc['opaque_fail']}; writers={writers}; "
          f"core_applies={core_applied_lifecycle(lc['cardLifecycle'])!r}")
    for v in static:
        print(f"[model]   - {v}")

    if MUTATE:
        # A mutation must flip the conformant path RED with EXACTLY ONE violation (no shadowing).
        if len(static) == 1:
            print(f"[model] PASS(mutation) — --mutate={MUTATE} flips the static-endpoint model RED with "
                  f"exactly one violation; the guard is independently load-bearing.")
            return 1
        print(f"[model] FAIL(mutation) — --mutate={MUTATE} produced {len(static)} violations, not exactly "
              f"one; a guard is vacuous or shadows another.")
        return 1

    if static:
        print("[model] FAIL — the §11 static-endpoint lifecycle must hold every BYO-endpoint invariant.")
        return 1
    if not _resume_shape_ok(lc):
        print("[model] FAIL — the static-endpoint model must pause exactly once (endpoint_unreachable) on "
              "the connectivity signal and resume on the operator Secret update (non-vacuous E5).")
        return 1

    print("[model] PASS — the shared/Claude-shaped lifecycle detectably breaks the BYO-endpoint model; the "
          "§11 third-story path holds E1-E7 (endpoint via per-user Secret, endpoint/model placement split, "
          "no refresh controller, in-place rotation, legible endpoint_unreachable pause, vendor-neutral "
          "lifecycle pinned per runtime, no material leaked) and pauses exactly once on the unreachable "
          "endpoint, resuming on the operator's Secret update.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
