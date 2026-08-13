#!/usr/bin/env python3
"""Story 7.4 falsification — graceful pause/resume on credential expiry/rotation (arch §7.2/§10/§11, FR-G3, S10).

Stories 7.2 and 7.3 each pin ONE credential *lifecycle* — WHEN and WHY a credential goes bad:
  - 7.2 (Claude-family, oauth-refresh): the only credential pause is Paused(cred_expired) at the ~9-day
        re-login lapse; resume triggers on the referenced Secret updating (operator re-logs in).
  - 7.3 (second runtime, static-key):   the only credential pause is Paused(cred_invalid) on a provider
        auth-failure; resume triggers on the referenced Secret updating (operator rotates the key).
And 7.5 (BYO Ollama, endpoint model) contributes a THIRD family: the credential is a model-endpoint URL
[+ optional token] Secret; its fault is the endpoint going unreachable/invalid, and it recovers when the
endpoint is restored.

Story 7.4 owns none of those *lifecycles* — it owns the ONE thing they all plug into: the **Run
pause/resume STATE MACHINE**. FR-G3 / S10: "Given a Running Run whose credential expires/rotates, When the
controller detects it, Then the Run moves to a Paused condition, emits a clear operator signal, and resumes
on refresh — never fails opaquely — and this holds for the OAuth-refresh, static-key, AND Ollama-endpoint
models." The load-bearing crux of THIS story is that the pause/resume machinery is **uniform and legible**:
one reducer reacts to a *normalized* credential-state signal so every family — including a runtime added
later — gets pause/resume for free, and a credential fault is **NEVER** allowed to surface opaquely (as a
Failed/terminal/silently-hung Run). A design that special-cases the pause path per vendor, lets a fault
bubble up as a generic Run failure, tears the Run down on pause, resumes on a blind timer while the
credential is still bad, pauses silently, or leaks the credential material has committed the FR-G3 defect,
not shipped the feature.

This is a DIFFERENTIAL check over the Run-condition transitions a controller REDUCER would produce for a
credential fault→recovery on each of the three families. The teeth: a happy-path "the Run kept running"
demo passes even if a credential fault would actually crash-loop the pod opaquely. So we first prove the
FR-G3 ANTI-PATTERN — the "opaque failure" reducer (a credential fault surfaces as Run.Failed, terminal, no
operator signal, no resume) — is DETECTED as violating every pause/resume invariant, then prove the §7.2/§11
graceful reducer violates nothing and ACTUALLY resumes all three families on their recovery signal.

Invariants (P1-P6, one per AC):
  P1  UNIFORM machinery: the reducer dispatches on a NORMALIZED credential-state signal, identically for
      every family — it does NOT branch on the vendor/runtime/model family. A per-family special-case in
      the core transition is the defect that denies a later runtime (Ollama-endpoint) pause/resume "for
      free" (mirrors the §10.1 zero-lateral-branch / 7.3 vendor-neutral crux).
  P2  NEVER OPAQUE (the FR-G3 crux): every credential fault yields Run condition = Paused with an
      operator-legible reason. ZERO faults may surface as Failed / a terminal state / a silent Running-hang.
  P3  PAUSED is NON-TERMINAL and reversible: Paused is not an absorbing/terminal state and the Run is NOT
      torn down — its progress/lease is preserved so it RESUMES (not restarts) when the credential recovers.
  P4  RESUME is driven by the RECOVERY SIGNAL, fail-closed: resume fires on the observed recovery signal
      (secret_updated / endpoint_reachable), and NEVER while the fault still persists — no blind-timer
      resume. (Non-vacuous: the model must ACTUALLY resume each family when recovery arrives.)
  P5  A clear operator SIGNAL is emitted on every pause (condition reason + event naming the actionable
      fix) — no silent pause.
  P6  The signal carries reason METADATA only, NEVER the credential material (NFR-SEC3, §17.1).

Mutation-proof harness (no vacuous guard): `--mutate=<FAMILY_SPECIAL|OPAQUE_FAIL|TERMINAL_PAUSE|
BLIND_RESUME|SILENT_PAUSE|LEAK>` injects the corresponding single defect into the CONFORMANT graceful path;
the check then goes RED with EXACTLY one violation (no guard shadows another; the ISI-2346-F1 vacuous-tooth
class is excluded by construction). Baseline `python3 pause-resume-credential-check.py` exits 0; each
`--mutate=NAME` exits 1. stdlib only.

Runtime proof (owned elsewhere). The real Running→Paused→Running transition on a cluster (an actual
credential fault, the emitted operator event, and resume-on-refresh) is exercised by 7.2/7.3/7.5 on their
respective credentials plus the ISI-2114 conformance lane; this model check guards the construction-time
pause/resume *state machine* — 7.4's crux and the thing FR-G3/S10 asked (graceful, uniform, never opaque).
"""
import sys

# ---- which conformant invariant to sabotage (mutation-proof harness). Empty = baseline. ----
MUTATE = ""


def mut(name):
    """True iff we are injecting the `name` bug into the conformant graceful path (verifies teeth)."""
    return MUTATE == name


# The three credential-lifecycle families FR-G3 requires pause/resume to hold for (7.2 / 7.3 / 7.5).
# Each names its fault reason (WHEN the credential goes bad — owned by that story) and the recovery signal
# that resumes the Run. 7.4's job is that ONE reducer serves all three identically.
FAMILIES = [
    {"family": "claude-oauth",    "fault": "cred_expired",         "recovery": "secret_updated",
     "remedy": "re-login in screen 05 (operator)"},
    {"family": "static-key",      "fault": "cred_invalid",         "recovery": "secret_updated",
     "remedy": "rotate the per-user Secret (operator)"},
    {"family": "ollama-endpoint", "fault": "endpoint_unreachable", "recovery": "endpoint_reachable",
     "remedy": "restore the model endpoint (operator)"},
]

# The family the single-defect mutations corrupt. Deliberately the runtime that must get pause/resume "for
# free" — proving the machinery is not silently Claude-only.
MUT_FAMILY = "ollama-endpoint"

NORMALIZED_SIGNAL = "cred_state"   # the ONE signal the reducer is allowed to dispatch on (family-neutral)


# ---- the controller reducer: given a family's fault→recovery, produce the Run-condition transition ----

def graceful_transition(fam):
    """The §7.2/§11 graceful reducer for ONE family. Reacts to the NORMALIZED credential-state signal, so
    the transition is identical across families: fault -> Paused(reason)+operator signal, work preserved;
    recovery signal -> resume (not restart). The mutations below each graft ONE FR-G3 defect onto this
    conformant path for the MUT_FAMILY only, so exactly one invariant flips."""
    is_mut = fam["family"] == MUT_FAMILY

    # P1: the reducer dispatches on the normalized cred-state signal, NEVER on the vendor family. A
    # per-family branch is what denies a later runtime pause/resume for free. (Global defect: FAMILY_SPECIAL
    # rewires ALL families to dispatch on `family`; the P1 guard reports it once, not per-family.)
    branch_key = "family" if mut("FAMILY_SPECIAL") else NORMALIZED_SIGNAL

    # P2: a credential fault becomes a legible Paused condition — never an opaque Failed/terminal state.
    condition = "Failed" if (is_mut and mut("OPAQUE_FAIL")) else "Paused"

    # P3: Paused is non-terminal and the Run is not torn down — progress/lease preserved so it can resume.
    terminal = True if (is_mut and mut("TERMINAL_PAUSE")) else False
    torn_down = terminal

    # P4: resume fires on the observed recovery signal, fail-closed. BLIND_RESUME resumes on a fixed timer
    # while the credential is still bad (recovery not yet observed).
    if is_mut and mut("BLIND_RESUME"):
        resume_trigger, recovery_observed = "retry_timer", False
    else:
        resume_trigger, recovery_observed = fam["recovery"], True
    resumed = (condition == "Paused" and not terminal)   # a torn-down / Failed Run cannot resume

    # P5: a clear operator signal is emitted on pause (condition reason + actionable event).
    signal_emitted = False if (is_mut and mut("SILENT_PAUSE")) else True

    # P6: the signal carries reason metadata only — never credential material.
    observable = []
    if signal_emitted:
        observable = [
            f"run.condition={condition} reason={fam['fault']}",
            f"event=CredentialPaused family={fam['family']} action={fam['remedy']}",
            f"nats.event=run.paused reason={fam['fault']}",
        ]
    if is_mut and mut("LEAK"):
        observable.append(f"log: paused holding {fam['family'].upper()}_KEY=sk-LIVE-KEY-material-LEAKED")

    return {
        "family": fam["family"], "branch_key": branch_key, "condition": condition, "reason": fam["fault"],
        "terminal": terminal, "torn_down": torn_down, "resumed": resumed,
        "resume_trigger": resume_trigger, "recovery_observed": recovery_observed,
        "signal_emitted": signal_emitted, "observable": observable,
    }


def opaque_transition(fam):
    """The FR-G3 ANTI-PATTERN: a credential fault is NOT handled by a pause/resume reducer at all — it
    bubbles up as a generic terminal Run.Failed (opaque), the Run is torn down, no operator signal, no
    resume. Every pause/resume invariant is violated — the harness must catch it on every family."""
    return {
        "family": fam["family"], "branch_key": NORMALIZED_SIGNAL, "condition": "Failed",
        "reason": "Error", "terminal": True, "torn_down": True, "resumed": False,
        "resume_trigger": "none", "recovery_observed": False, "signal_emitted": False,
        "observable": [],
    }


# ---- invariant checks: return a list of violation strings ------------------------------------------

KEY_MATERIAL_MARKERS = ("sk-LIVE", "_KEY=", "-material-", "refresh_token=")


def check_pause_resume_invariants(transitions):
    """Assert the §7.2/§11 graceful pause/resume invariants over the per-family transitions."""
    viol = []

    # P1: no transition may dispatch on the vendor family — the machinery is uniform (family-neutral).
    family_branched = sorted(t["family"] for t in transitions if t["branch_key"] != NORMALIZED_SIGNAL)
    if family_branched:
        viol.append(f"reducer branched on the vendor family for {family_branched} instead of the "
                    f"normalized {NORMALIZED_SIGNAL!r} signal — the pause/resume machinery must be uniform "
                    f"so a later runtime (Ollama-endpoint) gets pause/resume for free (P1/§10.1/FR-G3)")

    for t in transitions:
        f = t["family"]
        # P2: a credential fault must become a legible Paused condition — never opaque.
        if t["condition"] != "Paused":
            viol.append(f"[{f}] credential fault surfaced as Run.{t['condition']} (reason={t['reason']!r}) "
                        f"— FR-G3 forbids failing opaquely; every fault must become a legible "
                        f"Paused(reason) (P2/FR-G3/S10)")
        # P3: Paused is non-terminal and the Run is not torn down.
        if t["terminal"] or t["torn_down"]:
            viol.append(f"[{f}] Paused modeled as terminal/torn-down (terminal={t['terminal']}, "
                        f"torn_down={t['torn_down']}) — Paused must be reversible with the Run's progress "
                        f"preserved so it RESUMES, not restarts (P3/§8)")
        # P4: resume fires on the observed recovery signal, fail-closed — never a blind timer.
        if t["resumed"] and (t["resume_trigger"] not in (t_recovery(f),) or not t["recovery_observed"]):
            viol.append(f"[{f}] resumed on {t['resume_trigger']!r} without observing the recovery signal "
                        f"{t_recovery(f)!r} — resume must be driven by the credential recovering, never a "
                        f"blind timer while the fault persists (P4/§11 fail-closed)")
        # P5: a clear operator signal is emitted on pause.
        if t["condition"] == "Paused" and not t["signal_emitted"]:
            viol.append(f"[{f}] paused with no operator signal emitted — every pause must emit a clear "
                        f"operator condition + event naming the fix; no silent pause (P5/FR-G3)")
        # P6: no credential material on any observable surface.
        for line in t["observable"]:
            if any(m in line for m in KEY_MATERIAL_MARKERS):
                viol.append(f"[{f}] credential material leaked on an observable surface: {line!r} — the "
                            f"pause signal carries reason metadata only (P6/NFR-SEC3/§17.1)")
    return viol


def t_recovery(family):
    """The recovery signal that must drive resume for a given family (P4)."""
    return next(fam["recovery"] for fam in FAMILIES if fam["family"] == family)


def _resume_shape_ok(transitions):
    """Non-vacuous P2/P4: the graceful model must ACTUALLY pause every family (not dodge by never faulting)
    AND resume each on its OWN recovery signal — proving pause/resume is real, not vacuously 'never pause'."""
    if len(transitions) != len(FAMILIES):
        return False
    for t in transitions:
        if t["condition"] != "Paused" or not t["resumed"]:
            return False
        if t["resume_trigger"] != t_recovery(t["family"]) or not t["recovery_observed"]:
            return False
    return True


def main():
    argv = sys.argv[1:]
    global MUTATE
    for a in argv:
        if a.startswith("--mutate="):
            MUTATE = a.split("=", 1)[1]
    valid = {"", "FAMILY_SPECIAL", "OPAQUE_FAIL", "TERMINAL_PAUSE", "BLIND_RESUME", "SILENT_PAUSE", "LEAK"}
    if MUTATE not in valid:
        print(f"[model] unknown --mutate={MUTATE!r}; valid: {sorted(valid - {''})}")
        return 2

    # Teeth: the FR-G3 opaque-failure reducer must be DETECTED as violating the pause/resume model.
    opaque = check_pause_resume_invariants([opaque_transition(f) for f in FAMILIES])
    print(f"[model] FR-G3 opaque-failure reducer : {len(opaque)} violation(s) -> "
          f"{'DETECTED' if opaque else 'NONE (teeth lost!)'}")
    for v in opaque:
        print(f"[model]   - {v}")
    if len(opaque) < 5:
        print("[model] FAIL — a credential fault that surfaces opaquely (Run.Failed, terminal, no signal, "
              "no resume) should break the pause/resume model on every axis but did not; no teeth.")
        return 1

    # The §7.2/§11 graceful reducer must hold every invariant (or, under --mutate, break exactly one).
    transitions = [graceful_transition(f) for f in FAMILIES]
    graceful = check_pause_resume_invariants(transitions)
    print(f"[model] §7.2/§11 graceful pause/resume{f' [--mutate={MUTATE}]' if MUTATE else ''}: "
          f"{len(graceful)} violation(s); "
          f"conditions={ {t['family']: t['condition'] for t in transitions} }; "
          f"resumes={ {t['family']: t['resume_trigger'] for t in transitions} }")
    for v in graceful:
        print(f"[model]   - {v}")

    if MUTATE:
        # A mutation must flip the conformant path RED with EXACTLY ONE violation (no shadowing).
        if len(graceful) == 1:
            print(f"[model] PASS(mutation) — --mutate={MUTATE} flips the graceful model RED with exactly "
                  f"one violation; the guard is independently load-bearing.")
            return 1
        print(f"[model] FAIL(mutation) — --mutate={MUTATE} produced {len(graceful)} violations, not exactly "
              f"one; a guard is vacuous or shadows another.")
        return 1

    if graceful:
        print("[model] FAIL — the §7.2/§11 graceful reducer must hold every pause/resume invariant.")
        return 1
    if not _resume_shape_ok(transitions):
        print("[model] FAIL — the graceful model must pause EVERY family and resume each on its own "
              "recovery signal (non-vacuous P2/P4).")
        return 1

    print("[model] PASS — the opaque-failure reducer detectably breaks the pause/resume model; the "
          "§7.2/§11 graceful machinery holds P1-P6 (uniform family-neutral reducer, every fault -> legible "
          "Paused not opaque, Paused reversible with work preserved, resume driven by the recovery signal "
          "fail-closed, a clear operator signal on every pause, no material leaked) and resumes all three "
          "families (claude-oauth, static-key, ollama-endpoint) on their own recovery signal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
