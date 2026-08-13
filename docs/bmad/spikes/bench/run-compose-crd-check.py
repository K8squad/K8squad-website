#!/usr/bin/env python3
"""Story 8.5 falsification — compose Team/Agent/Role/Skill/Project CRDs from the console (arch §13, FR-F5, R6).

FR-F5 / UX 04-compose-crd (Sam, S3): "Given the compose screen, When I create/edit core CRDs, Then valid
CRs are applied via apiserver; And the console is NOT an IDE/code editor/dashboard (scope guard, R6)." This is
the SECOND write affordance in Epic 8 (after 8.4 kill, ISI-2267) and the RICHEST — create/edit of the five
core kinds {Team, Agent, Role, Skill, Project}. Where 8.4 introduced ONE gated mutation, 8.5 introduces a
gated *authoring surface*, so its whole job is to compose declarative CRs correctly:

  * the form is a THIN PRODUCER of declarative CRs — the apply goes browser → Next.js BFF → apiserver, and
    the CR passes the SAME server-side validation (Story 1.3 CEL + ValidatingAdmissionWebhook) as a raw
    `kubectl apply`. The console has NO second/looser validation path: an invalid compose is rejected by the
    SERVER, not merely by a client-side check that a forged request could skip (FR-F5 "valid CRs applied via
    apiserver", Story 1.3 fail-closed);
  * it composes DECLARATIVE CRs — it does NOT edit orchestration code, execute anything, or become a general
    IDE / code editor / dashboard. The console is a legibility + composition surface, NOT an IDE (R6 scope
    guard, PRD §11.5 / epics Epic-8 objective). The output is CRs; the reconciler acts (ADR-002);
  * compose is a WRITE-tier mutate affordance gated by per-project role (arch §12.3/8.16): `maintainer`,
    `admin`, AND `contributor` compose CRDs in scope; only `viewer` gets NO compose affordance (absent from
    the DOM, not display:none) AND the API denies a forged compose — the server re-checks every call. The
    maintainer↔contributor delta is PROJECT MEMBERSHIP/SETTINGS ADMINISTRATION, NOT CRD composition: arch
    §12.3 (ADR-033/035, the authoritative "one enforcement point, every surface" wall) grants `contributor`
    "compose (create/edit CRDs, start/kill Runs)" — a `contributor` is project-scoped WRITE. (The epics prose
    enumeration "Story 15.3" is looser and omits contributor-compose; where it conflicts with §12.3 the
    authoritative wall governs. Arch §15 is the Coordination-Spine risk section — there is no arch §15.3.);
  * composing an Agent binds runtime + role + skills + a CREDENTIAL REF (`secret://user/name`), NEVER an
    inline credential value — the secret value appears in NO sink (form state, the YAML mirror, the CR spec,
    the apiserver payload). CRs carry Secret REFS only (NFR-SEC3 / §11 ADR-010, Story 5.4 injection);
  * the form and the live read-only CRD YAML mirror are declared to be THE SAME resource (UX §3.4): the
    kubectl-ready YAML reflects exactly the CR the apply produces — no drift between form intent and applied
    CR — and the mirror is READ-ONLY (a legibility view, not an editable free-form code buffer; still not an
    IDE, R6);
  * compose covers EXACTLY the five core kinds {Team, Agent, Role, Skill, Project}, create + edit — it is not
    a general editor for arbitrary CRD kinds, and edit is a DECLARATIVE revision applied through the apiserver
    (a new CR revision the reconciler observes — Project goal-versioning §3.6), not an out-of-band imperative
    patch.

A "the compose form rendered and a CR got created" demo passes even if the form ships its own looser
validation the server never re-runs, POSTs straight at the apiserver/kube, turns into a code editor, inlines
the credential value, lets a VIEWER compose, drifts the YAML from the applied CR, or accepts arbitrary kinds.
So this is a DIFFERENTIAL check over the COMPOSE-CRD DESIGN a console would ship. We first prove the NAIVE
"raw compose editor" anti-pattern is DETECTED as violating every invariant (real teeth), then prove the
§13/FR-F5 conformant design violates nothing.

Invariants (C1-C7, one per AC):
  C1  VALID CRs, SERVER-VALIDATED (FR-F5 / Story 1.3): the compose applies CRs through the apiserver, which
      re-runs the SAME CEL + ValidatingAdmissionWebhook validation (Story 1.3, failurePolicy=Fail) as any
      kubectl apply. The console is NOT the validator — a client-only check the server never re-runs is a
      broken-validation regression (a forged/invalid compose slips through).
  C2  BFF CHOKE POINT (§13/ADR-013): the mutating apply call terminates at the Next.js BFF, which proxies the
      apiserver. The browser NEVER applies the CR against the Go apiserver or kube directly (the mutating
      twin of 8.2's S2 / 8.4's K2).
  C3  DECLARATIVE CRs, NOT AN IDE (R6 scope guard, ADR-002): the console composes DECLARATIVE CRs and applies
      them — it does NOT edit orchestration code, execute/run anything, or act as a general IDE / code editor
      / dashboard. A compose surface that edits code or executes has become the thing R6 forbids.
  C4  RBAC MUTATE-AFFORDANCE GATE (the crux, arch §12.3/8.16): compose passes the deny-by-default wall and is
      a WRITE-tier affordance. `maintainer`/`admin`/`contributor` → compose any core kind in scope; only
      `viewer` → NO compose affordance (absent from the DOM) AND the API denies a forged compose; out-of-scope
      → existence-hidden; and the server RE-CHECKS every call (never client-trusted). Any wrong decision — a
      visible viewer compose button, a viewer allowed to compose, or trusting the client's role claim — breaks
      the gate. (The maintainer↔contributor delta is membership/settings admin, NOT compose — §12.3.)
  C5  CREDENTIAL IS A SECRET REF, NEVER INLINE (NFR-SEC3 / §11 ADR-010, Story 5.4): composing an Agent binds
      a per-user Secret REF (`secret://user/name`); the credential VALUE is never inlined into the form, the
      YAML mirror, the CR spec, or the apiserver payload. An inline credential value in any sink is a
      secret-leak regression.
  C6  FORM AND YAML MIRROR ARE THE SAME RESOURCE (UX §3.4): the live read-only CRD YAML mirror reflects
      EXACTLY the CR the apply produces (kubectl-ready) — no drift between the form's intent and the applied
      CR — and the mirror is READ-ONLY (a legibility view, not an editable code buffer). Drift, or an
      editable free-form buffer, breaks the two-representations-one-CR contract (and re-opens R6).
  C7  FIVE CORE KINDS, CREATE + EDIT, DECLARATIVE (FR-F5 scope): compose covers EXACTLY {Team, Agent, Role,
      Skill, Project}, create + edit. It is not a general editor for arbitrary CRD kinds, and edit is a
      DECLARATIVE revision applied through the apiserver (reconciler-observed), not an imperative out-of-band
      patch. Accepting an arbitrary kind or an imperative edit path is out of scope.

Mutation-proof harness (no vacuous guard): `--mutate=<SERVER_SKIP_VALIDATION|CLIENT_ONLY_VALIDATION|
DIRECT_API|CODE_EDITOR|EXECUTES|VIEWER_AFFORDANCE|NO_RECHECK|INLINE_SECRET|YAML_DRIFT|EDITABLE_YAML|
ARBITRARY_KIND|IMPERATIVE_EDIT>` injects ONE single defect into the CONFORMANT §13/FR-F5 design; the check
then goes RED with EXACTLY one violation (each named guard is INDEPENDENTLY mutation-proven — one arm per
guard, so no guard shadows another and the ISI-2346-F1 vacuous-tooth class is excluded by construction).
Baseline `python3 run-compose-crd-check.py` exits 0; each `--mutate=NAME` exits 1 with exactly one violation.
"""

import argparse
import sys

# --- role model (per-project, arch §12.3; global admin bypass) -------------------------------------------
# compose is a WRITE-tier mutate affordance. arch §12.3 (ADR-033/035 — the authoritative RBAC wall) grants
# `contributor` "compose (create/edit CRDs, start/kill Runs)": contributor is project-scoped WRITE. The
# maintainer↔contributor delta is Project MEMBERSHIP/SETTINGS administration, NOT CRD composition. Only
# `viewer` is read-only. (The epics prose enumeration "Story 15.3" omits contributor-compose and is looser;
# §12.3 is authoritative where they conflict — see ISI-2461. Arch §15 is a different section entirely.)
COMPOSERS = {"maintainer", "admin", "contributor"}   # write-tier: admin = global_role=admin fleet bypass
CORE_KINDS = {"Team", "Agent", "Role", "Skill", "Project"}   # the exact FR-F5 set


def authorize_compose(design, caller_role, kind, in_scope):
    """The server-side compose authorization decision (re-checked on EVERY call, never client-trusted).

    Returns True iff the caller may apply a CR of `kind` in this scope. This is the SAME deny-by-default
    §12.3 wall every surface passes — there is no console-specific authz path (r21). Write-tier roles
    (maintainer/admin/contributor) compose; `viewer` is denied.
    """
    if not design["server_rechecks"]:
        # NO_RECHECK: the API trusts the client's assertion instead of re-resolving membership → allow-all
        # (a `viewer` slips through — the classic broken-access-control regression).
        return True
    if kind not in design["allowed_kinds"]:
        return False  # not a composable kind (C7 also guards this; the API must reject it regardless)
    if not in_scope:
        return False  # existence-hiding: out-of-scope Project is not visible, let alone composable
    return caller_role in COMPOSERS   # write-tier composes; `viewer` (or lower) is read-only → deny


def affordance_visible(design, caller_role):
    """Whether the compose AFFORDANCE is rendered in the DOM for this role (8.16 — absent, not display:none)."""
    if caller_role in COMPOSERS:   # write-tier (maintainer/admin/contributor) sees the compose entry
        return True
    # viewer: no mutate affordance — unless mutated to leak it
    return design["viewer_sees_affordance"]


def credential_value_leaks(design):
    """C5 helper: does the raw credential VALUE reach any sink? Conformant = only a `secret://` ref."""
    if design["credential_mode"] != "secret_ref":
        return True
    return bool(design["credential_value_in_sink"])


# --- invariants (C1-C7) ----------------------------------------------------------------------------------

def check(design):
    """Return the list of invariant violations for a compose-CRD design descriptor."""
    v = []

    # C1 — valid CRs, re-validated server-side (Story 1.3), not a client-only check
    if not design["server_validates"]:
        v.append("C1 apply skips server-side validation — the apiserver must re-run the Story 1.3 CEL + "
                 "ValidatingAdmissionWebhook (failurePolicy=Fail) on every apply (FR-F5 'valid CRs via apiserver')")
    if design["client_only_validation"]:
        v.append("C1 validation is client-only — a forged/invalid compose the server never re-checks slips "
                 "through; the console is NOT the validator (Story 1.3)")

    # C2 — BFF choke point (mutating twin of 8.2 S2 / 8.4 K2)
    if design["apply_call_target"] != "bff":
        v.append(f"C2 apply call targets '{design['apply_call_target']}' — the browser must call the Next.js "
                 f"BFF, never the apiserver/kube directly (§13/ADR-013)")

    # C3 — declarative CRs, NOT an IDE (R6)
    if design["surface_kind"] != "declarative_crd_form":
        v.append(f"C3 compose surface is a '{design['surface_kind']}' — the console composes DECLARATIVE CRs, "
                 f"it is NOT an IDE / code editor / dashboard (R6 scope guard)")
    if design["executes_orchestration"]:
        v.append("C3 compose executes/runs orchestration — the console applies declarative CRs and the "
                 "reconciler acts (ADR-002); it never executes (R6)")
    if not design["composes_declarative_cr"]:
        v.append("C3 compose does not emit a declarative CR — the output must be a Team/Agent/Role/Skill/"
                 "Project CR, not imperative orchestration (ADR-002/R6)")

    # C4 — RBAC mutate-affordance gate (the crux). Evaluate the decision table + affordance visibility.
    #   viewer      : NO affordance, API denies (read-only — the only role that cannot compose)
    #   contributor : affordance, composes ANY core kind in scope (write-tier, §12.3)
    #   maintainer  : affordance, composes ANY core kind in scope (+ membership/settings admin, out of scope here)
    rbac_ok = True
    # viewer must NOT see the affordance and must be denied by the API
    if affordance_visible(design, "viewer"):
        rbac_ok = False
    if authorize_compose(design, "viewer", "Agent", in_scope=True):
        rbac_ok = False
    # contributor is write-tier: MUST see the affordance and be ALLOWED to compose (arch §12.3)
    if not affordance_visible(design, "contributor"):
        rbac_ok = False
    if not authorize_compose(design, "contributor", "Agent", in_scope=True):
        rbac_ok = False
    # maintainer: any core kind in scope allowed
    if not authorize_compose(design, "maintainer", "Team", in_scope=True):
        rbac_ok = False
    # out-of-scope Project: even a maintainer cannot compose what is not in scope (existence-hiding)
    if authorize_compose(design, "maintainer", "Agent", in_scope=False):
        rbac_ok = False
    if not rbac_ok:
        v.append("C4 RBAC mutate-gate broken — only `viewer` may have NO compose affordance + API-deny; "
                 "maintainer/admin/contributor (write-tier) compose any core kind in scope, out-of-scope is "
                 "existence-hidden, and the server re-checks every call (arch §12.3/8.16)")

    # C5 — credential is a Secret ref, never inline
    if credential_value_leaks(design):
        v.append("C5 credential value is inlined (mode or a sink leaks it) — composing an Agent must bind a "
                 "per-user Secret REF (secret://user/name); the value belongs in NO sink (NFR-SEC3/§11)")

    # C6 — form and YAML mirror are the same resource, mirror read-only
    if not design["yaml_mirror_matches_cr"]:
        v.append("C6 the YAML mirror drifts from the applied CR — the form and the live YAML must be the SAME "
                 "resource, kubectl-ready (UX §3.4)")
    if design["yaml_mirror_editable_code"]:
        v.append("C6 the YAML mirror is an editable free-form code buffer — it must be a READ-ONLY legibility "
                 "view, not a code editor (UX §3.4 / R6)")

    # C7 — five core kinds, create+edit, declarative
    if design["allowed_kinds"] != CORE_KINDS:
        extra = sorted(set(design["allowed_kinds"]) - CORE_KINDS)
        missing = sorted(CORE_KINDS - set(design["allowed_kinds"]))
        v.append(f"C7 composable kinds != the FR-F5 set — extra={extra}, missing={missing}; compose covers "
                 f"EXACTLY {sorted(CORE_KINDS)}, not arbitrary CRD kinds")
    if not design["edit_is_declarative_revision"]:
        v.append("C7 edit is an imperative out-of-band patch — edit must be a DECLARATIVE CR revision applied "
                 "through the apiserver, reconciler-observed (§3.6 goal-versioning / ADR-002)")

    return v


# --- designs ---------------------------------------------------------------------------------------------

def conformant_design():
    """The §13/FR-F5 compose-CRD design that holds C1-C7."""
    return {
        "server_validates": True,                       # C1: apiserver re-runs Story 1.3 CEL+webhook
        "client_only_validation": False,                # C1: no looser client-only path
        "apply_call_target": "bff",                     # C2: browser → Next.js BFF → apiserver
        "surface_kind": "declarative_crd_form",         # C3: a CRD form, not an IDE/editor/dashboard
        "executes_orchestration": False,                # C3: applies CRs, reconciler acts (ADR-002)
        "composes_declarative_cr": True,                # C3: output is a declarative CR
        "server_rechecks": True,                        # C4: API re-resolves membership every call (8.16)
        "viewer_sees_affordance": False,                # C4: viewer button absent from DOM (only read-only role)
        "credential_mode": "secret_ref",                # C5: secret://user/name, never a value
        "credential_value_in_sink": False,              # C5: raw value in no sink
        "yaml_mirror_matches_cr": True,                 # C6: mirror == applied CR (kubectl-ready)
        "yaml_mirror_editable_code": False,             # C6: read-only legibility view, not a code buffer
        "allowed_kinds": set(CORE_KINDS),               # C7: exactly the five core kinds
        "edit_is_declarative_revision": True,           # C7: edit = declarative CR revision (§3.6)
    }


def naive_design():
    """The 'raw compose editor' anti-pattern — a console that ships a compose screen the lazy way. Must be
    DETECTED as violating every invariant, or the harness has no teeth."""
    return {
        "server_validates": False,                      # trusts its own client-side check
        "client_only_validation": True,                 # "the form validates; just POST it"
        "apply_call_target": "kube",                    # browser talks to kube directly (SPA-to-kube)
        "surface_kind": "code_editor",                  # a raw YAML/code editor (the IDE R6 forbids)
        "executes_orchestration": True,                 # "run this squad now" button in the editor
        "composes_declarative_cr": False,               # emits an imperative apply script, not a CR
        "server_rechecks": False,                       # trusts the client's role claim (viewer slips through)
        "viewer_sees_affordance": True,                 # even a viewer sees the compose button
        "credential_mode": "inline_value",              # paste the token straight into the form
        "credential_value_in_sink": True,               # value lands in the YAML mirror + CR spec
        "yaml_mirror_matches_cr": False,                # the editor buffer drifts from what is applied
        "yaml_mirror_editable_code": True,              # free-form editable code buffer
        "allowed_kinds": CORE_KINDS | {"Run", "ConfigMap"},  # edits arbitrary kinds too
        "edit_is_declarative_revision": False,          # edit = imperative in-place patch
    }


MUTATIONS = {
    "SERVER_SKIP_VALIDATION": lambda d: d.update(server_validates=False),
    "CLIENT_ONLY_VALIDATION": lambda d: d.update(client_only_validation=True),
    "DIRECT_API":             lambda d: d.update(apply_call_target="apiserver"),
    "CODE_EDITOR":            lambda d: d.update(surface_kind="code_editor"),
    "EXECUTES":               lambda d: d.update(executes_orchestration=True),
    "VIEWER_AFFORDANCE":      lambda d: d.update(viewer_sees_affordance=True),
    "NO_RECHECK":             lambda d: d.update(server_rechecks=False),
    "INLINE_SECRET":          lambda d: d.update(credential_mode="inline_value", credential_value_in_sink=True),
    "YAML_DRIFT":             lambda d: d.update(yaml_mirror_matches_cr=False),
    "EDITABLE_YAML":          lambda d: d.update(yaml_mirror_editable_code=True),
    "ARBITRARY_KIND":         lambda d: d.update(allowed_kinds=CORE_KINDS | {"ConfigMap"}),
    "IMPERATIVE_EDIT":        lambda d: d.update(edit_is_declarative_revision=False),
}

# Which single invariant each mutation is expected to flip (for the no-shadow proof). Each named guard has
# its OWN arm — two arms per multi-guard family (C1, C4, C6, C7) so no sub-guard is left vacuous (ISI-2346-F1).
MUT_INVARIANT = {
    "SERVER_SKIP_VALIDATION": "C1", "CLIENT_ONLY_VALIDATION": "C1",
    "DIRECT_API": "C2", "CODE_EDITOR": "C3", "EXECUTES": "C3",
    "VIEWER_AFFORDANCE": "C4", "NO_RECHECK": "C4",
    "INLINE_SECRET": "C5",
    "YAML_DRIFT": "C6", "EDITABLE_YAML": "C6",
    "ARBITRARY_KIND": "C7", "IMPERATIVE_EDIT": "C7",
}


def main():
    ap = argparse.ArgumentParser(description="Story 8.5 compose-CRD falsification")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="inject one defect into the conformant design")
    args = ap.parse_args()

    # 1) Teeth: the naive raw-compose-editor anti-pattern must be DETECTED violating every invariant.
    naive_v = check(naive_design())
    families = {x.split()[0] for x in naive_v}
    print(f"[model] NAIVE raw-compose-editor anti-pattern : {len(naive_v)} violation(s) across "
          f"{len(families)} invariant(s) -> DETECTED")
    for x in naive_v:
        print(f"[model]   - {x}")
    if families != {"C1", "C2", "C3", "C4", "C5", "C6", "C7"}:
        print(f"[model] FAIL — the naive anti-pattern stopped violating some invariant (teeth lost): {sorted(families)}")
        return 1

    # 2) The conformant §13/FR-F5 design (optionally mutated).
    design = conformant_design()
    if args.mutate:
        MUTATIONS[args.mutate](design)
    v = check(design)

    if args.mutate:
        fams = sorted({x.split()[0] for x in v})
        print(f"[model] conformant + --mutate={args.mutate}: {len(v)} violation(s) {fams}")
        for x in v:
            print(f"[model]   - {x}")
        expected = MUT_INVARIANT[args.mutate]
        if len(v) == 1 and fams == [expected]:
            print(f"[model] PASS — mutation {args.mutate} flips EXACTLY {expected} RED (no guard shadows another).")
            return 1  # a mutation MUST break the check (exit non-zero)
        print(f"[model] FAIL — mutation {args.mutate} expected exactly one violation on {expected}, got {fams}")
        return 2

    print(f"[model] §13/FR-F5 conformant compose design: {len(v)} violation(s); "
          f"target={design['apply_call_target']}, surface={design['surface_kind']}, "
          f"server_validates={design['server_validates']}, credential={design['credential_mode']}, "
          f"viewer_button={design['viewer_sees_affordance']}, composers={sorted(COMPOSERS)}, "
          f"kinds={sorted(design['allowed_kinds'])}")
    if v:
        print("[model] FAIL — the conformant design violated an invariant:")
        for x in v:
            print(f"[model]   - {x}")
        return 1
    print("[model] PASS — the naive raw-compose-editor detectably breaks every invariant; the §13/FR-F5 design")
    print("        holds C1-C7 (valid CRs server-validated · BFF choke point · declarative CRs not an IDE ·")
    print("        RBAC write-tier gate [contributor composes, viewer read-only] · credential Secret-ref not")
    print("        inline · form≡YAML mirror · five core kinds).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
