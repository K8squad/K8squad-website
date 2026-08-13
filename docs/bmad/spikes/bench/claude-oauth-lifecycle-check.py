#!/usr/bin/env python3
"""Story 7.2 falsification — Claude-family OAuth credential lifecycle (arch §11, §11.1, ADR-032, FR-G2).

Story 7.1 pins the credential *reference shape* (per-user Secret ref, no shared master, per-namespace).
Story 7.2 is the CLAUDE-FAMILY instantiation of that shape, and its distinctive crux is the **zero-touch
lifecycle** the CEO's 2026-08-12 real-world finding locked in (§11.1 / ADR-032) — the model that
*retired* the ISI-2112 gate. This is a DIFFERENTIAL check over the credential *lifecycle a driver would
produce* for a fleet of concurrent Claude agent pods sharing one per-user OAuth Secret over a timeline.
It asserts the §11.1 invariants that separate the zero-touch controller model from the RETIRED
manual-`setup-token`/per-pod-refresh model:

  AC1  One-time OAuth provisions a per-user Secret holding BOTH an access token AND a refresh token
       (credentialType=claude-oauth, credentialLifecycle=oauth-refresh). A static-only bearer (no refresh
       token) is the retired anti-pattern — it hard-breaks at the ~8h access-token TTL.
  AC2  The leader-elected credential controller is the SOLE writer of the Secret across the whole
       timeline; agent pods are READ-ONLY mounters and never refresh. >1 distinct writer == the
       thundering-refresh race ADR-032 forbids.
  AC3  Refresh writes back to the SAME Secret name in place — the name is stable across every refresh, so
       existing mounters never break. Minting a fresh Secret per refresh churns the name and strands
       mounters.
  AC4  The ~8h access-token expiry causes ZERO Run pauses (the controller refreshes pre-emptively); the
       ONLY credential pause is Paused(cred_expired) at the ~9-day refresh-window lapse, and only when the
       subscription is idle across that whole window. The retired model pauses at every ~8h boundary.
  AC5  N pods mounting the ONE Secret concurrently is ADMITTED — shared-credential concurrency is correct
       (Paperclip field-proven), not a claim/lease conflict.
  AC6  Token MATERIAL never appears on any observable surface (Agent Card, screen-05 health, NATS refresh
       events) — only credentialType/credentialLifecycle metadata does (NFR-SEC3, §17.1).

Why differential: a happy-path "the pod mounted a token and ran" demo passes with a lifecycle that
refreshes per-pod (racing writers), stores a static non-refreshing bearer, pauses the Run every 8h, or
logs the token on provision. We first prove a NAIVE lifecycle (the RETIRED ISI-2112 manual/per-pod model:
static bearer, each pod re-provisions its own token at 8h, Run pauses every 8h, concurrency treated as a
conflict, token echoed on provision) is DETECTED as violating every invariant -- so the harness has real
teeth -- then prove the §11.1 zero-touch lifecycle violates nothing and pauses EXACTLY once, at the
9-day window lapse, only under idleness. stdlib only; `python3 claude-oauth-lifecycle-check.py`.
"""
import sys

ACCESS_TTL_H = 8            # Claude OAuth access token ~8h
REFRESH_LEAD_H = 1         # controller refreshes 1h before access expiry (pre-emptive)
WINDOW_H = 9 * 24          # ~9-day refresh-window / inactivity lapse -> re-login
SECRET = "alice-claude-oauth"
NS = "ksquad-team-alpha-3f1a"
N_PODS = 6                 # concurrent Claude agent pods, all mounting the ONE Secret


def _refresh_hours(active_until_h, horizon_h):
    """Hours at which a pre-emptive refresh fires while the subscription is active: 1h before each ~8h
    access-token expiry (7, 15, 23, ...), but only up to when the fleet is still active."""
    hrs, t = [], ACCESS_TTL_H - REFRESH_LEAD_H
    while t <= horizon_h:
        if t <= active_until_h:
            hrs.append(t)
        t += ACCESS_TTL_H
    return hrs


# ---- lifecycle drivers: each returns the credential lifecycle a design would produce ---------------

def lifecycle_zerotouch(horizon_h, active_until_h):
    """The §11.1 / ADR-032 zero-touch lifecycle: one-time OAuth -> per-user Secret (access+refresh);
    leader-elected controller is the sole refresher, writing back to the SAME Secret before each ~8h
    expiry; pods mount read-only; pause only if the ~9-day window lapses while idle."""
    # One-time OAuth provision: BOTH tokens land in the per-user Secret; controller owns the write.
    writes = [(0, "controller", SECRET)]
    provisioned = {"has_access": True, "has_refresh": True,
                   "credentialType": "claude-oauth", "credentialLifecycle": "oauth-refresh"}
    # Controller refreshes pre-emptively while active -> new access token, SAME Secret, one writer.
    for h in _refresh_hours(active_until_h, horizon_h):
        writes.append((h, "controller", SECRET))
    # Pauses: the ~8h expiry never pauses a Run (refresh precedes it). Only a full idle window lapses.
    pauses = []
    if horizon_h - active_until_h >= WINDOW_H:
        pauses.append((active_until_h + WINDOW_H, "cred_expired"))   # -> one-click re-login (screen 05)
    return {"writes": writes, "pauses": pauses, "provisioned": provisioned,
            "concurrency_admitted": True,          # N pods share one Secret — correct, not a conflict
            # observable surfaces carry METADATA only, never the token strings
            "observable": [f"agentCard.credentialType={provisioned['credentialType']}",
                           f"screen05.health=connected",
                           f"nats.event=credential.refresh secret={SECRET}"]}


def lifecycle_naive_manual(horizon_h, active_until_h):
    """The RETIRED ISI-2112 manual/per-pod model: a static bearer (no refresh token), each pod
    re-provisions its OWN token when it hits the ~8h TTL (racing writers), the Run pauses at every ~8h
    boundary for the manual `setup-token` step, concurrent mount is treated as a conflict, and the token
    is echoed on provision. Every §11.1 invariant is violated — the harness must catch it."""
    # Provision: a static bearer only — no refresh token stored (breaks at 8h without a manual redo).
    writes = [(0, "pod-0", SECRET)]
    provisioned = {"has_access": True, "has_refresh": False,
                   "credentialType": "claude-oauth", "credentialLifecycle": "static-bearer"}
    pauses = []
    # At each ~8h boundary the Run pauses (manual re-provision) and a *different* pod writes the token.
    t = ACCESS_TTL_H
    i = 0
    while t <= min(active_until_h, horizon_h):
        pauses.append((t, "reauth_setup_token"))           # spurious 8h pause (bad UX, retired)
        writes.append((t, f"pod-{i % N_PODS}", SECRET))     # racing per-pod writer
        i += 1
        t += ACCESS_TTL_H
    return {"writes": writes, "pauses": pauses, "provisioned": provisioned,
            "concurrency_admitted": False,          # over-cautious .credentials.json-sharing rejection
            "observable": [f"log: minted CLAUDE_CODE_OAUTH_TOKEN=sk-oauth-SECRET-material-LEAKED",
                           f"agentCard.credentialType=claude-oauth"]}


# ---- invariant checks: return a list of violation strings -----------------------------------------

TOKEN_MATERIAL_MARKERS = ("sk-oauth", "CLAUDE_CODE_OAUTH_TOKEN=", "refresh_token=", "-material-")


def check_lifecycle(lc):
    """Assert the §11.1 zero-touch invariants over one lifecycle result. Returns a list of violations."""
    viol = []
    p = lc["provisioned"]

    # AC1: the provisioned Secret must hold BOTH access and refresh tokens (not a static-only bearer).
    if not (p["has_access"] and p["has_refresh"]):
        viol.append(f"provisioned Secret lacks a refresh token (has_refresh={p['has_refresh']}) — a "
                    f"static-only bearer hard-breaks at the ~8h TTL (AC1/§11.1)")
    if p.get("credentialLifecycle") != "oauth-refresh":
        viol.append(f"credentialLifecycle is {p.get('credentialLifecycle')!r}, not 'oauth-refresh' — "
                    f"Claude-family must advertise the refresh lifecycle (AC1/FR-G2)")

    # AC2: exactly ONE distinct writer (the leader-elected controller) across the whole timeline.
    writers = {actor for _, actor, _ in lc["writes"]}
    if writers != {"controller"}:
        viol.append(f"Secret written by {sorted(writers)} — the leader-elected controller must be the "
                    f"SOLE writer; any per-pod writer is the thundering-refresh race (AC2/ADR-032)")

    # AC3: every write targets the SAME Secret name (in-place write-back; mounters never strand).
    names = {name for _, _, name in lc["writes"]}
    if names != {SECRET}:
        viol.append(f"refresh churns Secret name(s) {sorted(names)} != {{{SECRET!r}}} — write-back must "
                    f"be in place so existing mounters keep resolving (AC3/§11.1)")

    # AC4: the ~8h access expiry causes NO pause; the only allowed pause is one cred_expired at a full
    # ~9-day window lapse. Any 8h-boundary reauth pause is the retired manual model.
    reasons = [r for _, r in lc["pauses"]]
    bad_pauses = [r for r in reasons if r != "cred_expired"]
    if bad_pauses:
        viol.append(f"Run paused for {bad_pauses} — the ~8h expiry must be refreshed, never paused; the "
                    f"only credential pause is Paused(cred_expired) at the ~9-day lapse (AC4/§11.1)")

    # AC5: concurrent pods sharing the ONE Secret must be admitted, not treated as a conflict.
    if not lc["concurrency_admitted"]:
        viol.append(f"concurrent mount of {SECRET!r} by {N_PODS} pods rejected as a conflict — "
                    f"shared-credential concurrency is correct (Paperclip-proven) (AC5/§11.1)")

    # AC6: no observable surface may contain token material — metadata only.
    for line in lc["observable"]:
        if any(m in line for m in TOKEN_MATERIAL_MARKERS):
            viol.append(f"token material leaked on an observable surface: {line!r} — only "
                        f"credentialType/credentialLifecycle metadata may surface (AC6/NFR-SEC3)")
    return viol


def _pause_shape_ok(lc, expect_window_pause):
    """The zero-touch model's pause set must be EXACTLY {cred_expired} when idle past the window, and
    EMPTY when active — a non-vacuous check that the 9-day lapse both fires when it should and stays
    silent when it should not."""
    reasons = sorted(r for _, r in lc["pauses"])
    return reasons == (["cred_expired"] if expect_window_pause else [])


def main():
    HORIZON = 12 * 24        # 12-day timeline in hours

    # Scenario A — fleet ACTIVE the whole horizon: zero-touch must never pause; retired model pauses 8-hourly.
    active_z = lifecycle_zerotouch(HORIZON, active_until_h=HORIZON)
    active_n = lifecycle_naive_manual(HORIZON, active_until_h=HORIZON)
    # Scenario B — fleet goes IDLE at h=48; the ~9-day refresh window then lapses -> exactly one re-login pause.
    idle_z = lifecycle_zerotouch(HORIZON, active_until_h=48)

    naive = check_lifecycle(active_n)
    print(f"[model] retired manual lifecycle : {len(naive)} lifecycle violation(s) -> "
          f"{'DETECTED' if naive else 'NONE (teeth lost!)'}")
    for v in naive:
        print(f"[model]   - {v}")
    if not naive:
        print("[model] FAIL — the retired manual/per-pod lifecycle should break §11.1 but did not; no teeth.")
        return 1

    zt = check_lifecycle(active_z) + check_lifecycle(idle_z)
    print(f"[model] §11.1 zero-touch lifecycle: {len(zt)} violation(s); "
          f"active_pauses={[r for _,r in active_z['pauses']]}; idle_pauses={[r for _,r in idle_z['pauses']]}; "
          f"writers={sorted({a for _,a,_ in active_z['writes']})}; concurrency_ok={active_z['concurrency_admitted']}")
    for v in zt:
        print(f"[model]   - {v}")
    if zt:
        print("[model] FAIL — the §11.1 zero-touch lifecycle must hold every credential-lifecycle invariant.")
        return 1

    # The pause SHAPE must be exactly right in both directions (non-vacuous AC4).
    if not _pause_shape_ok(active_z, expect_window_pause=False):
        print("[model] FAIL — active zero-touch fleet must never pause on the ~8h expiry.")
        return 1
    if not _pause_shape_ok(idle_z, expect_window_pause=True):
        print("[model] FAIL — an idle fleet past the ~9-day window must pause exactly once (cred_expired).")
        return 1

    print("[model] PASS — retired manual lifecycle detectably breaks §11.1; the zero-touch controller "
          "holds AC1-AC6 (access+refresh Secret, sole controller writer, in-place write-back, no 8h "
          "pause, concurrent mount OK, no material leaked) and pauses exactly once at the 9-day lapse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
