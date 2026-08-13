#!/usr/bin/env python3
"""Story 8.6 falsification — surface credential/auth state, incl. the paused-on-expiry signal (FR-F6, S10).

Screen 05 (`05-credential-auth-state`) is the operator's **Settings → Credentials** legibility surface: for
each Agent it shows **per-agent credential health** — *connected / refreshing / expired·paused* — and, the
literal FR-F6 ask, **a clear paused-on-expiry signal** when an Agent's Run is `Paused(cred_expired)` (§7.4),
with the actionable one-click re-login remedy ("Connect Claude" / `ksquad auth login` parity, 7.7). It is a
**pure read model, coordination-free** (R6): health is **DERIVED** from the leader-elected credential
controller's Secret state (§5.2/§11.1) + the Run's `Paused` condition (§7.4) — it invents **no new
credential store, no console-owned health field** (ADR-020). It is served **through the Next.js BFF**
(§13/ADR-013), **scoped in-assembly per §12.3** (a caller sees only their own Agents' health; `admin` gets
the fleet "All agents / ns: all" view), carries **health/reason metadata only** — **never the token bytes**
(NFR-SEC3/§17.1) — and hangs **no token-paste / edit / rotate-in-console field**: the ONLY mutating
affordance is the sanctioned browser-OAuth re-login handoff, because the operator **never handles token
strings** (§11.1 zero-touch). Read every AC literally: surfacing another principal's credential row, echoing
the Secret value, rendering a Paused(cred_expired) Run as a generic/blank error, or hanging a paste-token
box is a **security / FR-F6 regression**, not a cosmetic bug.

This is a MODEL/differential check (a sibling of artifact-inspection-check.py and pause-resume-credential-
check.py), stdlib-only, `python3` it directly. It first proves the **FR-F6 anti-pattern** — a "raw-secrets
admin panel" client (reads a bespoke health field it wrote itself, points the browser straight at the Go
apiserver, shows every principal's row, prints the token bytes, hangs a paste-token box, renders the expired
Run as a generic error, and only knows how to render the Claude family) — is **DETECTED as violating every
invariant** (real teeth), then proves the §11.1/§13 derived read-model design violates nothing and
**actually renders the owner an explicit paused-on-expiry signal with the re-login remedy while hiding the
Secret material and every out-of-scope principal's row, uniformly across all three credential families**.

Invariants (C1-C7, each mapped to an AC of story 8.6):
  C1  DERIVED, NOT STORED: credential health is a projection DERIVED from the controller's Secret state
      (§5.2/§11.1) + the Run's `Paused` condition (§7.4) — NOT a console-owned/duplicated health field
      (ADR-020: no new store). The console shows status; the controller owns refresh.
  C2  PAUSED IS LEGIBLE (the FR-F6 crux): a Run in the `Paused` condition renders an EXPLICIT signal — a
      legible status + the specific reason (cred_expired / cred_invalid / rate_limited / endpoint_unreachable)
      + an actionable, reason/family-driven remedy — NEVER a generic error / blank / opaque failure / a
      silent 'connected'. The mapping is STRUCTURAL (a Paused Run is NEVER connected), not a pause-reason
      whitelist, so a new reason (7.6 rate_limited) slots in. (The read-side mirror of 7.4-P2.)
  C3  BFF CHOKE POINT: the browser reads through the Next.js BFF, which proxies the Go apiserver; the browser
      never connects to the apiserver/kube/Postgres directly and holds no apiserver URL (§13/ADR-013).
  C4  SCOPED IN-ASSEMBLY, EXISTENCE-HIDING: the §12.3 caller sees only the Agents within their membership —
      an out-of-scope principal's credential row is STRUCTURALLY ABSENT (not returned-then-hidden), counts
      included; `global_role=admin` gets the fleet "All agents" view (bypass). Per-user Secret ref (§11).
  C5  NO CREDENTIAL MATERIAL: the projection carries the Secret *ref* + health/reason/expiry METADATA only —
      the token/secret *bytes* appear on NO field and NO span (NFR-SEC3/§17.1). Health legibility never
      requires the material.
  C6  READ-ONLY + SANCTIONED RE-LOGIN ONLY (zero-touch, §11.1): the surface's only mutating affordance is the
      sanctioned browser-OAuth "Connect Claude" / re-login handoff — NO paste-token / edit / apply /
      rotate-in-console field. The operator never types a token string (7.7).
  C7  FAMILY-NEUTRAL HEALTH: the health surface renders uniformly for every credential family
      (claude-oauth / static-key / ollama-endpoint, §11/7.2/7.3/7.5) over states
      {connected, refreshing, expired-paused} — it does NOT special-case one vendor (mirrors 7.4-P1).

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT design; the check then goes RED with the
mapped invariant failing:
  --mutate=SHADOW_STORE    read a console-owned health field, not the derived state   -> C1 RED
  --mutate=OPAQUE_EXPIRY   render the Paused(cred_expired) Run as a generic error      -> C2 RED
  --mutate=PAUSE_WHITELIST collapse a non-whitelisted Paused reason to 'connected'     -> C2 RED
  --mutate=DIRECT_API      point the browser straight at the Go apiserver              -> C3 RED
  --mutate=CROSS_PRIN      surface an out-of-scope principal's credential row          -> C4 RED
  --mutate=LEAK_MATERIAL   echo the token bytes into a field/span                      -> C5 RED
  --mutate=TOKEN_PASTE     hang a paste-token / edit affordance on the surface         -> C6 RED
  --mutate=FAMILY_SPECIAL  only render health for the Claude family                    -> C7 RED

Baseline `python3 credential-auth-state-check.py` exits 0; each `--mutate=NAME` exits 1 with the mapped
violation. The check exits non-zero if the raw-secrets-admin-panel model STOPS violating (teeth lost), if
the derived read model EVER violates an invariant, or if it fails to actually render the owner an explicit
paused-on-expiry signal with the re-login remedy while hiding the Secret material + the out-of-scope row.

Runtime proof (owned elsewhere). The real GET-through-BFF, the live per-principal scoping, and the browser
OAuth re-login handoff are exercised by the console E2E (`05-testing`) and 7.4/7.7 on the actual controller
Secret state. This model check guards the **construction-time contract** — 8.6's crux and exactly what FR-F6
asked (surface credential state, with a clear paused-on-expiry signal).
"""
import sys

# ---- health states screen 05 renders (UX STATUS column) --------------------------------------------
# Derived purely from (controller Secret state, Run condition). "expired-paused" is the FR-F6 signal.
HEALTH_STATES = {"connected", "refreshing", "expired-paused"}

# affordances allowed on the credential surface (R6 + §11.1 zero-touch). The re-login is a browser-OAuth
# HANDOFF, not a token field — the operator never types a token string. Anything else is a mutate leak.
READONLY_AFFORDANCES = {"view", "navigate", "relogin_oauth"}

# the three credential families FR-G3/§11 requires health to render for (7.2 / 7.3 / 7.5).
FAMILIES = {"claude-oauth", "static-key", "ollama-endpoint"}

# markers that would betray real credential material leaking onto an observable surface.
KEY_MATERIAL_MARKERS = ("sk-LIVE", "refresh_token=", "-material-", "BEGIN PRIVATE KEY")


# ---- the Agents + their DERIVED-source state (controller Secret state + Run condition) --------------
# Each Agent carries ONLY what the read model is allowed to derive from: the controller's Secret state
# (§5.2/§11.1) and the Run's condition (§7.4). `stored_health` is the C1 anti-pattern — a console-owned
# duplicate field (deliberately STALE for the paused Agent, so reading it both mislabels the source AND
# hides the FR-F6 signal). The token *bytes* live in `_secret_material` — NEVER a projected field.
def build_agents():
    return [
        # sam's Claude-family Run PAUSED on expiry -> the FR-F6 headline row (mock: fixer-hermes #139).
        {"agent": "fixer-hermes", "runtime": "Hermes", "family": "claude-oauth",
         "secret_ref": "secret://sam/hermes-oauth", "token_type": "OAuth", "principal": "sam",
         "run": "#139", "expires": "expired 6m ago",
         "controller_state": "expired", "run_condition": "Paused", "run_reason": "cred_expired",
         "stored_health": "connected",  # STALE bespoke duplicate — the C1 defect would trust this
         "_secret_material": "refresh_token=sk-LIVE-hermes-oauth-material-DO-NOT-SURFACE"},
        # sam's static-key Run healthy (mock: reviewer-openclaw #143).
        {"agent": "reviewer-openclaw", "runtime": "OpenClaw", "family": "static-key",
         "secret_ref": "secret://sam/openclaw-key", "token_type": "API key", "principal": "sam",
         "run": "#143", "expires": "— (static)",
         "controller_state": "valid", "run_condition": "Running", "run_reason": None,
         "stored_health": "connected",
         "_secret_material": "sk-LIVE-openclaw-static-material-DO-NOT-SURFACE"},
        # sam's Claude-family token mid-refresh by the leader-elected controller (mock: tester-hermes #142).
        {"agent": "tester-hermes", "runtime": "Hermes", "family": "claude-oauth",
         "secret_ref": "secret://sam/hermes-oauth", "token_type": "OAuth", "principal": "sam",
         "run": "#142", "expires": "in 41m",
         "controller_state": "refreshing", "run_condition": "Running", "run_reason": None,
         "stored_health": "refreshing",
         "_secret_material": "refresh_token=sk-LIVE-hermes-oauth-material-DO-NOT-SURFACE"},
        # sam's static-key Run PAUSED on an INVALID credential (7.3) -> cred_invalid must render a legible
        # non-connected signal (AC2 enumerates it); the old 2-reason whitelist mis-rendered this 'connected'.
        {"agent": "auditor-openclaw", "runtime": "OpenClaw", "family": "static-key",
         "secret_ref": "secret://sam/openclaw-audit-key", "token_type": "API key", "principal": "sam",
         "run": "#145", "expires": "invalid",
         "controller_state": "invalid", "run_condition": "Paused", "run_reason": "cred_invalid",
         "stored_health": "connected",
         "_secret_material": "sk-LIVE-openclaw-audit-material-DO-NOT-SURFACE"},
        # sam's Claude Run PAUSED rate-limited (7.6 forward-compat) — controller_state is VALID, so ONLY the
        # Paused condition makes it legible; a pause-reason whitelist would mis-render this 'connected'.
        {"agent": "builder-hermes", "runtime": "Hermes", "family": "claude-oauth",
         "secret_ref": "secret://sam/hermes-oauth", "token_type": "OAuth", "principal": "sam",
         "run": "#146", "expires": "in 55m",
         "controller_state": "valid", "run_condition": "Paused", "run_reason": "rate_limited",
         "stored_health": "connected",
         "_secret_material": "refresh_token=sk-LIVE-hermes-oauth-material-DO-NOT-SURFACE"},
        # sam's BYO-Ollama endpoint Run paused unreachable -> proves C7 family-neutrality (7.5).
        {"agent": "runner-ollama", "runtime": "opencode", "family": "ollama-endpoint",
         "secret_ref": "secret://sam/ollama-endpoint", "token_type": "endpoint", "principal": "sam",
         "run": "#140", "expires": "n/a",
         "controller_state": "endpoint_unreachable", "run_condition": "Paused",
         "run_reason": "endpoint_unreachable", "stored_health": "connected",
         "_secret_material": "http://ollama.internal:11434 token=sk-LIVE-ollama-material-DO-NOT-SURFACE"},
        # dana's Run — a DIFFERENT principal; sam must never see this row (C4 existence-hiding).
        {"agent": "writer-openclaw", "runtime": "OpenClaw", "family": "claude-oauth",
         "secret_ref": "secret://dana/oc-oauth", "token_type": "OAuth", "principal": "dana",
         "run": "#141", "expires": "in 5h 12m",
         "controller_state": "valid", "run_condition": "Running", "run_reason": None,
         "stored_health": "connected",
         "_secret_material": "refresh_token=sk-LIVE-dana-oauth-material-DO-NOT-SURFACE"},
        # priya's Run — another out-of-scope principal for sam.
        {"agent": "reviewer-hermes", "runtime": "Hermes", "family": "claude-oauth",
         "secret_ref": "secret://priya/hermes-oauth", "token_type": "OAuth", "principal": "priya",
         "run": "#144", "expires": "in 2h 48m",
         "controller_state": "valid", "run_condition": "Running", "run_reason": None,
         "stored_health": "connected",
         "_secret_material": "refresh_token=sk-LIVE-priya-oauth-material-DO-NOT-SURFACE"},
    ]


# ---- the actionable remedy: reason/family-driven, NOT a hardcoded OAuth re-login ---------------------
# AC2 requires "each with its own actionable remedy" — a Claude OAuth token re-login does NOT fix a
# rate-limit backoff (7.6) or an unreachable BYO-Ollama endpoint (7.5). The remedy is derived from the
# pause reason + credential family so the Go port never hardcodes `relogin_oauth` for endpoint faults.
def remedy_for(a):
    reason = a["run_reason"] or a["controller_state"]
    if reason == "rate_limited":
        return "wait_retry"        # 7.6: a rate-limited pause resolves on backoff, not a re-login
    if a["family"] == "ollama-endpoint" or reason == "endpoint_unreachable":
        return "check_endpoint"    # 7.5: an unreachable BYO-Ollama endpoint is a config fault, not OAuth
    return "relogin_oauth"         # 7.7: OAuth / static-key credential re-auth handoff ("Connect Claude")


# ---- the health derivation: the executable spec (controller state + Run condition -> health) --------
# The ONLY inputs are the DERIVED sources. The mapping is STRUCTURAL, not a pause-reason whitelist: a Run
# in the `Paused` condition is NEVER "connected" — it renders "expired-paused" with the reason surfaced
# from `run_reason` (cred_expired / cred_invalid / rate_limited / endpoint_unreachable ...) so a new pause
# reason (e.g. 7.6 rate_limited) slots in without a special-case. An expired/invalid/unreachable controller
# state also renders "expired-paused"; a refreshing controller -> "refreshing"; else "connected". The
# `status` is the paused-health bucket in HEALTH_STATES; `reason` carries the specific, legible cause. The
# token bytes are NEVER read here.
def derive_health(a, source):
    if source == "stored":
        # C1 DEFECT: trust the console-owned duplicate instead of deriving. It is stale for the paused Agent.
        status = a["stored_health"]
        reason, remedy = None, None
    elif a["run_condition"] == "Paused":
        # a Paused Run is NEVER connected — surface the reason legibly for EVERY pause reason (not a
        # 2-reason whitelist); this is the read-side mirror of 7.4-P2 (never-opaque), incl. cred_invalid/
        # rate_limited (7.3 / 7.6).
        status = "expired-paused"
        reason = a["run_reason"] or a["controller_state"]
        remedy = remedy_for(a)
    elif a["controller_state"] in ("expired", "invalid", "endpoint_unreachable"):
        status = "expired-paused"
        reason = a["controller_state"]
        remedy = remedy_for(a)
    elif a["controller_state"] == "refreshing":
        status, reason, remedy = "refreshing", None, None
    else:
        status, reason, remedy = "connected", None, None
    return status, reason, remedy


# ---- the credential-state projection (what screen 05's console+BFF must match) ----------------------
#
# `project(design, caller, agents, mut)` -> (rows the caller sees, meta). Each row carries the Secret REF +
# health metadata only. `mut` names the single injected defect for the mutation harness.
def project(design, caller, agents, mut=None):
    source = "stored" if mut == "SHADOW_STORE" else design["source"]          # C1
    scoped = design["scope"] == "per_principal" and mut != "CROSS_PRIN"       # C4
    admin = caller == "admin"

    rows = []
    for a in agents:
        # --- scope in-assembly, existence-hiding (C4): out-of-scope rows never enter the payload -------
        if scoped and not admin and a["principal"] != caller:
            continue

        status, reason, remedy = derive_health(a, source)

        # C2: PAUSE_WHITELIST re-introduces the deleted 2-reason whitelist defect — a Paused Run whose reason
        # is NOT in ("cred_expired", "endpoint_unreachable") collapses to 'connected', silently misclassifying
        # cred_invalid (7.3) / rate_limited (7.6) as healthy. A Paused Run is NEVER connected.
        if (mut == "PAUSE_WHITELIST" and a["run_condition"] == "Paused"
                and a["run_reason"] not in ("cred_expired", "endpoint_unreachable")):
            status, reason, remedy = "connected", None, None

        # C2: the paused-on-expiry Run must render an EXPLICIT signal. OPAQUE_EXPIRY overwrites it with a
        # generic error and drops the remedy.
        if mut == "OPAQUE_EXPIRY" and status == "expired-paused":
            status, reason, remedy = "error", None, None

        # C7: a family-blind surface only knows how to render the Claude family -> non-Claude rows lose
        # their status. FAMILY_SPECIAL grafts this defect onto the conformant path; the NAIVE panel is
        # family-blind by construction.
        if (mut == "FAMILY_SPECIAL" or design.get("family_blind")) and a["family"] != "claude-oauth":
            status, reason, remedy = "unknown", None, None

        row = {
            "agent": a["agent"], "runtime": a["runtime"], "family": a["family"],
            "secret_ref": a["secret_ref"], "token_type": a["token_type"], "principal": a["principal"],
            "run": a["run"], "expires": a["expires"],
            "status": status, "reason": reason, "remedy": remedy,
        }
        # C5: LEAK_MATERIAL echoes the token bytes onto a projected field. The conformant path never does.
        if mut == "LEAK_MATERIAL" or design.get("emit_material"):
            row["token"] = a["_secret_material"]
        rows.append(row)

    return rows, _meta(design, mut)


def _meta(design, mut):
    endpoint = "apiserver" if mut == "DIRECT_API" else design["endpoint"]     # C3
    affordances = set(design["affordances"])
    if mut == "TOKEN_PASTE":
        affordances = affordances | {"paste_token", "edit"}                   # C6
    source = "stored" if mut == "SHADOW_STORE" else design["source"]
    return {"endpoint": endpoint, "affordances": affordances, "source": source}


def build_span_attrs(rows, mut=None):
    """OBS: the credential span carries ONLY status magnitudes — never a Secret ref value or token (C5)."""
    attrs = {
        "ksquad.cred.rows": len(rows),
        "ksquad.cred.paused": sum(1 for r in rows if r["status"] == "expired-paused"),
    }
    if mut == "LEAK_MATERIAL":
        # the leak defect also drips a token onto the span (the exfil edge C5 forbids).
        attrs["ksquad.cred.sample"] = next((r.get("token") for r in rows if r.get("token")), "")
    return attrs


# ---- the two designs -------------------------------------------------------------------------------
CONFORMANT = {
    "source": "derived",                       # C1 — derived from controller state + Run condition
    "endpoint": "bff",                         # C3 — through the Next.js BFF, hiding the Go API
    "scope": "per_principal",                  # C4 — scope-in-assembly existence-hiding
    "affordances": {"view", "navigate", "relogin_oauth"},  # C6 — read-only + sanctioned OAuth re-login
    "emit_material": False,                     # C5 — metadata only, never the token bytes
}
NAIVE = {
    "source": "stored",                        # C1 fail — console-owned duplicate health field
    "endpoint": "apiserver",                   # C3 fail — browser straight at the Go API
    "scope": "none",                           # C4 fail — every principal's row surfaced
    "affordances": {"view", "paste_token", "edit", "rotate"},  # C6 fail — token-paste/edit box
    "emit_material": True,                      # C5 fail — prints the token bytes
    "family_blind": True,                       # C7 fail — only knows the Claude family
}


# ---- the runnable check ----------------------------------------------------------------------------
def evaluate(design, mut, agents):
    """Return the list of (invariant, detail) violations for `design` as seen by caller `sam`."""
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    CALLER = "sam"
    rows, meta = project(design, CALLER, agents, mut=mut)
    by_agent = {r["agent"]: r for r in rows}

    # C1 — health DERIVED from the controller state + Run condition, not a console-owned store.
    check("C1", meta["source"] == "derived",
          f"credential health read from a {meta['source']!r} field, not DERIVED from the controller Secret "
          f"state + Run condition (ADR-020 no new store; §5.2/§11.1)")

    # C2 — the paused-on-expiry Run renders an EXPLICIT signal with the re-login remedy (FR-F6 crux).
    paused = by_agent.get("fixer-hermes")
    check("C2", paused is not None and paused["status"] == "expired-paused"
          and paused["reason"] == "cred_expired" and paused["remedy"] == "relogin_oauth",
          f"Paused(cred_expired) Run rendered as {paused and (paused['status'], paused['reason'], paused['remedy'])} "
          f"— FR-F6 requires an explicit paused-on-expiry signal + reason + one-click re-login remedy, "
          f"never a generic/blank error (C2/§7.4)")

    # C2 (cred_invalid, 7.3) — a Paused(cred_invalid) Run must ALSO render a legible non-connected signal,
    # NOT silently 'connected'. AC2 enumerates cred_invalid as a paused-on-expiry-class reason; the old
    # 2-reason whitelist had ZERO teeth on it.
    invalid_paused = by_agent.get("auditor-openclaw")
    check("C2", invalid_paused is not None and invalid_paused["status"] == "expired-paused"
          and invalid_paused["reason"] == "cred_invalid",
          f"Paused(cred_invalid) Run rendered as {invalid_paused and (invalid_paused['status'], invalid_paused['reason'])} "
          f"— a Paused Run is NEVER 'connected'; every pause reason (incl. cred_invalid, 7.3) must render an "
          f"explicit legible signal (C2/§7.4, AC2 never-opaque mirror of 7.4-P2)")

    # C2 (rate_limited, 7.6 forward-compat) — a Paused(rate_limited) Run with a VALID controller state is
    # legible ONLY via the Paused condition; a reason whitelist would mis-render it 'connected'. The mapping
    # must be structural so 7.6 slots in without special-casing.
    rate_paused = by_agent.get("builder-hermes")
    check("C2", rate_paused is not None and rate_paused["status"] == "expired-paused"
          and rate_paused["reason"] == "rate_limited",
          f"Paused(rate_limited) Run rendered as {rate_paused and (rate_paused['status'], rate_paused['reason'])} "
          f"— 7.6 forward-compat: a rate-limited pause must slot in as a legible signal keyed by the reason, "
          f"without special-casing (C2/§7.4, Dev Notes 7.6)")

    # C3 — through the BFF, never the Go apiserver directly.
    check("C3", meta["endpoint"] == "bff",
          f"browser reads through {meta['endpoint']!r}, not the Next.js BFF (§13/ADR-013)")

    # C4 — scope in-assembly: an out-of-scope principal's row is structurally absent (existence-hiding).
    foreign = sorted({r["agent"] for r in rows if r["principal"] != CALLER})
    check("C4", not foreign,
          f"out-of-scope principals' credential rows surfaced to {CALLER!r}: {foreign} — must be "
          f"structurally absent (scope-in-assembly existence-hiding, §12.3/§11 per-user Secret)")
    # positive control (non-vacuous): the caller's OWN rows are present, not scoped to nothing.
    own = [r for r in rows if r["principal"] == CALLER]
    check("C4", len(own) >= 3,
          f"caller {CALLER!r} sees only {len(own)} of their own Agents — scope must ADMIT the owner "
          f"(non-vacuous; not an over-broad deny)")

    # C5 — no credential material on any row field or span.
    leaked = [(r["agent"], k, v) for r in rows for k, v in r.items()
              if isinstance(v, str) and any(m in v for m in KEY_MATERIAL_MARKERS)]
    check("C5", not leaked,
          f"token/secret material on projected field(s) {[(a, k) for a, k, _ in leaked]} — the surface "
          f"carries the Secret ref + metadata only, never the material (NFR-SEC3/§17.1)")
    attrs = build_span_attrs(rows, mut=mut)
    span_leak = [k for k, v in attrs.items() if isinstance(v, str) and any(m in v for m in KEY_MATERIAL_MARKERS)]
    check("C5", not span_leak,
          f"credential span attr(s) {span_leak} carry token material — spans hold magnitudes only (NFR-OBS3)")

    # C6 — read-only + sanctioned OAuth re-login ONLY; no token-paste/edit/rotate box.
    bad_affordances = meta["affordances"] - READONLY_AFFORDANCES
    check("C6", not bad_affordances,
          f"mutating affordance(s) {sorted(bad_affordances)} on the credential surface — the only sanctioned "
          f"write is the browser-OAuth re-login handoff; the operator never types a token (§11.1/7.7)")
    # positive control: the sanctioned re-login IS offered on the paused row (the remedy must be reachable).
    check("C6", "relogin_oauth" in meta["affordances"],
          "the sanctioned re-login affordance is absent — the expired state must offer one-click re-login "
          "(non-vacuous; FR-F6 remedy)")

    # C7 — family-neutral: EVERY family renders a legible health state, uniformly. The "only knows the
    # Claude family" defect leaves a non-Claude row with no legible state.
    fam_rows = {r["family"]: r for r in rows}
    non_neutral = sorted(fam for fam, r in fam_rows.items() if r["status"] not in HEALTH_STATES)
    check("C7", not non_neutral,
          f"families {non_neutral} render no legible health state — the surface must be family-neutral over "
          f"{sorted(HEALTH_STATES)} for claude-oauth/static-key/ollama-endpoint (C7/§11, mirrors 7.4-P1)")

    return fails


def run(mut=None):
    agents = build_agents()
    naive_fails = evaluate(NAIVE, None, agents)              # teeth
    naive_hit = {inv for inv, _ in naive_fails}
    conf_fails = evaluate(CONFORMANT, mut, agents)            # baseline or single injected defect
    return naive_fails, naive_hit, conf_fails


MUTANTS = {
    "SHADOW_STORE": "C1", "OPAQUE_EXPIRY": "C2", "PAUSE_WHITELIST": "C2", "DIRECT_API": "C3",
    "CROSS_PRIN": "C4", "LEAK_MATERIAL": "C5", "TOKEN_PASTE": "C6", "FAMILY_SPECIAL": "C7",
}
ALL_INV = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]


def main(argv):
    mut = None
    for a in argv[1:]:
        if a.startswith("--mutate="):
            mut = a.split("=", 1)[1].strip().upper()
    if mut and mut not in MUTANTS:
        print(f"unknown mutant {mut!r}; choose from {', '.join(MUTANTS)}", file=sys.stderr)
        return 2

    naive_fails, naive_hit, conf_fails = run(mut=mut)

    # teeth gate: the raw-secrets-admin-panel model must trip every invariant, always.
    missing_teeth = [inv for inv in ALL_INV if inv not in naive_hit]
    if missing_teeth:
        print(f"[cred] TEETH LOST — the raw-secrets-admin-panel model no longer trips {missing_teeth}:")
        for inv, d in naive_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[cred] FAIL — the §11.1/§13 derived read model violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] FR-F6 raw-secrets-admin-panel client : {len(naive_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(naive_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §11.1/§13 derived credential read model: 0 violation(s); "
              "source=derived, browser->bff, scoped-per-principal, metadata-only, "
              "read-only+oauth-relogin, family-neutral")
        print("[cred] PASS — the raw-secrets-admin-panel client detectably breaks every invariant; the "
              "§11.1/§13\n       derived read model holds C1-C7 ... and actually renders the owner an explicit "
              "paused-on-\n       expiry signal with the re-login remedy while hiding the Secret material and "
              "every\n       out-of-scope principal's row, uniformly across all three credential families.")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[cred] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[cred] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
