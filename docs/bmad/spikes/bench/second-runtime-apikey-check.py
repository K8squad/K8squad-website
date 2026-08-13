#!/usr/bin/env python3
"""Story 7.3 falsification — second-runtime (OpenClaw/Hermes) API-key credential (arch §10/§11, FR-G2, OQ11/F15).

Story 7.1 pins the credential *reference shape* (per-user Secret ref, no shared master, per-namespace).
Story 7.2 is the CLAUDE-family instantiation of that shape — a zero-touch OAuth-*refresh* lifecycle.
Story 7.3 is the OTHER concrete story, and its distinctive crux is exactly the thing OQ11/F15 asked and
the §11 credential table answers: the non-Claude runtime's credential model is **vendor-neutral, not
Claude-shaped**. Per §11 (row "Second runtime (OpenClaw/Hermes — non-Claude)"):

    Acquisition = a long-lived **API key / provider token supplied directly** (NO interactive OAuth step,
                  NO refresh token).
    Lifecycle   = **static** — there is no ~8h access-token TTL, no centralized refresh controller, and
                  no ~9-day refresh-window; the key changes ONLY if the provider rotates it.
    Secret      = per-user Secret ref holding the API key (Story 7.1 shape).
    Rotation    = an **operator Secret update** (§11 pause/resume: "Resume triggers on the referenced
                  Secret updating (operator rotates the token)").
    Token type / refresh = **pinned per that runtime in THIS story** (OQ11), read as capability metadata
                  (FR-G2), so the **core hardcodes no vendor's flow**.

This is a DIFFERENTIAL check over the credential *lifecycle a driver would produce* for a second-runtime
API-key Agent. The teeth: a happy-path "the pod mounted a key and ran" demo passes even if the platform
wrongly treats the second runtime as Claude. So we first prove the CLAUDE-SHAPED lifecycle (the OQ11/F15
anti-pattern: interactive-OAuth acquisition storing a refresh token, a leader-elected controller
"refreshing" the key every ~8h, a fresh Secret minted per refresh, a spurious ~9-day cred_expired pause,
and a core that hardcodes the oauth-refresh lifecycle for every runtime) is DETECTED as violating every
static-key invariant — then prove the §11 static-key lifecycle violates nothing and pauses EXACTLY once,
on a provider auth-failure, resuming when the operator updates the Secret.

Invariants (SC1-SC6, one per AC):
  SC1  Acquisition is a direct API key: has an api key, NO refresh token, NOT via interactive OAuth. A
       provisioning path that runs OAuth / stores a refresh token is Claude-shaping (category error).
  SC2  No refresh controller: the Secret is written ONLY by the operator (provision + rotation); there is
       NO ~8h controller refresh write. A static key has nothing to refresh — a refresh writer is the
       Claude lifecycle grafted onto a static key.
  SC3  Rotation is an in-place update of the SAME per-user Secret name — never a freshly minted Secret
       that strands existing mounters.
  SC4  No auto-expiry pause. A static key does not self-expire on an ~8h or ~9-day timer, so the pause set
       carries NO cred_expired / reauth_setup_token. The ONLY credential pause is Paused(cred_invalid) on
       a runtime auth-failure signal, and it resumes on the operator's Secret update (the shared 7.4 path).
  SC5  Lifecycle is PINNED PER RUNTIME as metadata and the core is VENDOR-NEUTRAL: the lifecycle the core
       applies equals the Agent Card's advertised credentialLifecycle (FR-G2) — which for this runtime is
       'static-key'. A core that hardcodes 'oauth-refresh' for all runtimes is the OQ11/F15 defect.
  SC6  Key MATERIAL never appears on an observable surface (Agent Card, screen-05 health, NATS events,
       logs) — only credentialType/credentialLifecycle metadata does (NFR-SEC3, §17.1).

Mutation-proof harness (no vacuous guard): `--mutate=<OAUTH_ACQUIRE|CONTROLLER_REFRESH|SECRET_CHURN|
NINE_DAY_PAUSE|CORE_HARDCODE|LEAK>` injects the corresponding single defect into the CONFORMANT static-key
path; the check then goes RED with EXACTLY that one violation (no guard shadows another; the ISI-2346-F1
vacuous-tooth class is excluded by construction). Baseline `python3 second-runtime-apikey-check.py` exits 0;
each `--mutate=NAME` exits 1. stdlib only.

Runtime proof (owned elsewhere). The real second-runtime credential mount + auth-failure→Paused→resume is
exercised on a cluster by 5.4 (injection contract) + 7.4 (pause/resume) + the ISI-2114 conformance lane;
this model check guards the construction-time credential *model* — 7.3's crux and the thing OQ11/F15 asked.
"""
import sys

# ---- which conformant invariant to sabotage (mutation-proof harness). Empty = baseline. ----
MUTATE = ""


def mut(name):
    """True iff we are injecting the `name` bug into the conformant static-key path (verifies teeth)."""
    return MUTATE == name


ACCESS_TTL_H = 8            # the ~8h Claude access-token TTL — the second runtime has NO such TTL
WINDOW_H = 9 * 24          # the ~9-day Claude refresh-window — the second runtime has NO such window
HORIZON_H = 12 * 24        # 12-day timeline in hours
REVOKE_H = 100             # provider invalidates the key out-of-band at this hour (scenario B)
ROTATE_H = 104            # operator rotates: updates the SAME Secret -> Run resumes

RUNTIME = "openclaw"                     # the non-Claude second runtime (Hermes is symmetric)
SECRET = "alice-openclaw-apikey"        # per-user Secret (Story 7.1 shape), in the Team namespace
NS = "ksquad-team-alpha-3f1a"
CRED_TYPE = "openclaw-api-key"
LIFECYCLE = "static-key"                 # the runtime's PINNED lifecycle metadata (FR-G2) — NOT oauth-refresh
API_KEY_ENV = "OPENCLAW_API_KEY"        # the shim maps the Secret to this runtime-native env (5.4)
N_PODS = 6                               # concurrent second-runtime agent pods, all mounting the ONE Secret


def _refresh_hours(horizon_h):
    """The ~8h-cadence pre-expiry refresh hours a Claude-shaped controller would (wrongly) run."""
    hrs, t = [], ACCESS_TTL_H - 1
    while t <= horizon_h:
        hrs.append(t)
        t += ACCESS_TTL_H
    return hrs


# ---- lifecycle drivers: each returns the credential lifecycle a design would produce --------------

def lifecycle_static_key():
    """The §11 second-runtime row: a long-lived API key supplied DIRECTLY into a per-user Secret; no
    OAuth, no refresh token, no refresh controller; the key changes ONLY on operator rotation = an
    in-place Secret update; the only pause is Paused(cred_invalid) on a provider auth-failure, resumed
    when the operator updates the Secret."""
    # Acquisition: the operator supplies the provider API key directly into the per-user Secret.
    provisioned = {
        "has_apikey": True,
        # A static API key has NO refresh token. OAUTH_ACQUIRE grafts the Claude acquisition on.
        "has_refresh": True if mut("OAUTH_ACQUIRE") else False,
        "acquired_via": "interactive-oauth" if mut("OAUTH_ACQUIRE") else "direct-api-key",
        "credentialType": CRED_TYPE,
        "credentialLifecycle": LIFECYCLE,
    }
    # Writes: operator provisions once. There is NO controller refresh — nothing to refresh.
    writes = [(0, "operator", SECRET, "provision")]
    if mut("CONTROLLER_REFRESH"):
        # Graft the Claude ~8h refresh controller onto a static key: a refresh writer that must not exist.
        for h in _refresh_hours(HORIZON_H):
            writes.append((h, "controller", SECRET, "refresh"))

    pauses, resumes = [], []
    # Scenario B: the provider invalidates the key out-of-band -> runtime auth-failure -> Paused.
    pauses.append((REVOKE_H, "cred_invalid"))
    # Operator rotates: updates the SAME Secret in place -> Run resumes (the shared 7.4 path).
    rotate_name = "alice-openclaw-apikey-v2" if mut("SECRET_CHURN") else SECRET   # churn strands mounters
    writes.append((ROTATE_H, "operator", rotate_name, "rotation"))
    resumes.append((ROTATE_H, "secret_updated"))
    if mut("NINE_DAY_PAUSE"):
        # A static key does not self-expire; a ~9-day cred_expired timer pause is the Claude lifecycle.
        pauses.append((REVOKE_H + WINDOW_H, "cred_expired"))

    observable = [
        f"agentCard.credentialType={CRED_TYPE}",
        f"agentCard.credentialLifecycle={LIFECYCLE}",
        "screen05.health=connected",
        f"nats.event=credential.rotated secret={SECRET}",
    ]
    if mut("LEAK"):
        observable.append(f"log: injected {API_KEY_ENV}=sk-openclaw-LIVE-KEY-material-LEAKED")

    return {"writes": writes, "pauses": pauses, "resumes": resumes, "provisioned": provisioned,
            "cardLifecycle": provisioned["credentialLifecycle"], "observable": observable}


def lifecycle_claude_shaped():
    """The OQ11/F15 ANTI-PATTERN: the second runtime modeled as if it were Claude. Interactive-OAuth
    acquisition storing a refresh token, a leader-elected controller "refreshing" the key every ~8h,
    a fresh Secret minted per refresh, a spurious ~9-day cred_expired pause, key echoed on provision.
    Every static-key invariant is violated — the harness must catch it."""
    provisioned = {"has_apikey": True, "has_refresh": True, "acquired_via": "interactive-oauth",
                   "credentialType": CRED_TYPE, "credentialLifecycle": "oauth-refresh"}
    writes = [(0, "controller", SECRET, "provision")]
    for i, h in enumerate(_refresh_hours(HORIZON_H)):
        writes.append((h, "controller", f"{SECRET}-r{i}", "refresh"))    # controller refresh + name churn
    pauses = [(WINDOW_H, "cred_expired")]                                # spurious ~9-day timer pause
    return {"writes": writes, "pauses": pauses, "resumes": [], "provisioned": provisioned,
            "cardLifecycle": provisioned["credentialLifecycle"],
            "observable": [f"log: minted {API_KEY_ENV}=sk-openclaw-LIVE-KEY-material-LEAKED",
                           f"agentCard.credentialLifecycle=oauth-refresh"]}


# ---- the core's lifecycle resolution — vendor-neutral (metadata-driven) vs hardcoded --------------

def core_applied_lifecycle(card_lifecycle):
    """What lifecycle the CORE actually applies to the Run. Vendor-neutral (FR-G2): it reads the Agent
    Card's advertised credentialLifecycle. CORE_HARDCODE models a core that ignores metadata and bakes
    in the Claude oauth-refresh flow for every runtime — the OQ11/F15 not-vendor-neutral defect."""
    if mut("CORE_HARDCODE"):
        return "oauth-refresh"
    return card_lifecycle


# ---- invariant checks: return a list of violation strings -----------------------------------------

KEY_MATERIAL_MARKERS = ("sk-openclaw", f"{API_KEY_ENV}=", "-material-", "refresh_token=")


def check_static_invariants(lc):
    """Assert the §11 second-runtime static-key invariants over one lifecycle. Returns violations."""
    viol = []
    p = lc["provisioned"]

    # SC1: direct API key — an api key, NO refresh token, NOT acquired via interactive OAuth.
    if not p["has_apikey"] or p["has_refresh"] or p["acquired_via"] != "direct-api-key":
        viol.append(f"acquisition is not a direct API key (has_refresh={p['has_refresh']}, "
                    f"acquired_via={p['acquired_via']!r}) — the second runtime takes a long-lived key "
                    f"supplied directly; an OAuth flow / stored refresh token is Claude-shaping (SC1/§11/OQ11)")

    # SC2: no refresh controller — the Secret is written ONLY by the operator (provision + rotation).
    refreshers = {actor for _, actor, _, kind in lc["writes"] if kind == "refresh"}
    writers = {actor for _, actor, _, _ in lc["writes"]}
    if refreshers or writers - {"operator"}:
        viol.append(f"Secret written by non-operator {sorted(writers - {'operator'}) or sorted(refreshers)} "
                    f"— a static key has no ~8h TTL to refresh; only the operator writes it "
                    f"(provision + rotation), never a refresh controller (SC2/§11)")

    # SC3: rotation is in-place on the SAME Secret name — never a freshly minted Secret.
    names = {name for _, _, name, _ in lc["writes"]}
    if names != {SECRET}:
        viol.append(f"writes churn Secret name(s) {sorted(names)} != {{{SECRET!r}}} — rotation is an "
                    f"in-place update of the same per-user Secret so mounters keep resolving (SC3/§11)")

    # SC4: no auto-expiry pause; the only credential pause is cred_invalid (runtime auth-failure).
    reasons = [r for _, r in lc["pauses"]]
    bad = [r for r in reasons if r != "cred_invalid"]
    if bad:
        viol.append(f"Run paused for {bad} — a static key does not self-expire on an ~8h/~9-day timer; "
                    f"the only credential pause is Paused(cred_invalid) on a provider auth-failure, "
                    f"resumed on the operator's Secret update (SC4/§11/7.4)")

    # SC5: the core applies the runtime's PINNED lifecycle metadata (vendor-neutral), == 'static-key'.
    applied = core_applied_lifecycle(lc["cardLifecycle"])
    if applied != lc["cardLifecycle"] or applied != LIFECYCLE:
        viol.append(f"core applied lifecycle {applied!r} but the runtime's pinned Agent-Card metadata is "
                    f"{lc['cardLifecycle']!r} (expected {LIFECYCLE!r}) — the core must be vendor-neutral "
                    f"and read the lifecycle from metadata, not hardcode Claude's oauth-refresh (SC5/FR-G2/OQ11)")

    # SC6: no key material on any observable surface — metadata only.
    for line in lc["observable"]:
        if any(m in line for m in KEY_MATERIAL_MARKERS):
            viol.append(f"key material leaked on an observable surface: {line!r} — only "
                        f"credentialType/credentialLifecycle metadata may surface (SC6/NFR-SEC3/§17.1)")
    return viol


def _resume_shape_ok(lc):
    """Non-vacuous SC4: the static model must ACTUALLY pause exactly once on the provider auth-failure
    AND resume on the operator's Secret update — proving AC4 is not vacuously met by 'never pause'."""
    reasons = sorted(r for _, r in lc["pauses"])
    triggers = sorted(t for _, t in lc["resumes"])
    return reasons == ["cred_invalid"] and triggers == ["secret_updated"]


def main():
    argv = sys.argv[1:]
    global MUTATE
    for a in argv:
        if a.startswith("--mutate="):
            MUTATE = a.split("=", 1)[1]
    valid = {"", "OAUTH_ACQUIRE", "CONTROLLER_REFRESH", "SECRET_CHURN", "NINE_DAY_PAUSE",
             "CORE_HARDCODE", "LEAK"}
    if MUTATE not in valid:
        print(f"[model] unknown --mutate={MUTATE!r}; valid: {sorted(valid - {''})}")
        return 2

    # Teeth: the OQ11/F15 Claude-shaped lifecycle must be DETECTED as violating the static-key model.
    shaped = check_static_invariants(lifecycle_claude_shaped())
    print(f"[model] Claude-shaped second-runtime lifecycle : {len(shaped)} violation(s) -> "
          f"{'DETECTED' if shaped else 'NONE (teeth lost!)'}")
    for v in shaped:
        print(f"[model]   - {v}")
    if len(shaped) < 5:
        print("[model] FAIL — the Claude-shaped (OQ11/F15) lifecycle should break the static-key model on "
              "every axis but did not; no teeth.")
        return 1

    # The §11 static-key lifecycle must hold every invariant (or, under --mutate, break exactly one).
    lc = lifecycle_static_key()
    static = check_static_invariants(lc)
    writers = sorted({a for _, a, _, _ in lc["writes"]})
    print(f"[model] §11 static-key lifecycle{f' [--mutate={MUTATE}]' if MUTATE else ''}: "
          f"{len(static)} violation(s); pauses={[r for _,r in lc['pauses']]}; "
          f"resumes={[t for _,t in lc['resumes']]}; writers={writers}; "
          f"core_applies={core_applied_lifecycle(lc['cardLifecycle'])!r}")
    for v in static:
        print(f"[model]   - {v}")

    if MUTATE:
        # A mutation must flip the conformant path RED with EXACTLY ONE violation (no shadowing).
        if len(static) == 1:
            print(f"[model] PASS(mutation) — --mutate={MUTATE} flips the static-key model RED with exactly "
                  f"one violation; the guard is independently load-bearing.")
            return 1
        print(f"[model] FAIL(mutation) — --mutate={MUTATE} produced {len(static)} violations, not exactly "
              f"one; a guard is vacuous or shadows another.")
        return 1

    if static:
        print("[model] FAIL — the §11 static-key lifecycle must hold every static-key invariant.")
        return 1
    if not _resume_shape_ok(lc):
        print("[model] FAIL — the static-key model must pause exactly once (cred_invalid) on the provider "
              "auth-failure and resume on the operator Secret update (non-vacuous SC4).")
        return 1

    print("[model] PASS — the Claude-shaped lifecycle detectably breaks the static-key model; the §11 "
          "second-runtime path holds SC1-SC6 (direct API key, no refresh controller, in-place rotation, "
          "no auto-expiry pause, vendor-neutral lifecycle pinned per runtime, no material leaked) and "
          "pauses exactly once on a provider auth-failure, resuming on the operator's Secret update.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
