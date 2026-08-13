#!/usr/bin/env python3
"""Story 7.1 falsification — per-user Secret refs, no shared master (arch §11, §12.1, AD-9/ADR-010, FR-G1).

Differential check. It models the credential *resolution an Agent composer/reconciler would produce*
for a set of sample Agents across two squads, then asserts the arch §11 + §12.1 credential-isolation
invariants over those resolutions:

  AC1  Every composed Agent resolves to a concrete PER-USER Secret ref (credentialSecretRef, or the
       BYO model-endpoint Secret for §10.3 endpoints). No Agent composes on a silent platform-default /
       shared token — a missing/empty ref is a rejection, never a fallback to a shared credential.
  AC2  KSquad stores NO shared master credential: the platform holds no master-credential catalog, and
       no Agent's resolved Secret is a well-known shared master or a control-plane (`ksquad-system`)
       Secret. Custody stays with the principal (D3/AD-9).
  AC3  Creds are per-namespace, never cross-squad: the resolved Secret lives in the Agent's OWN Team
       namespace (§12.1). A namespace-qualified ref pointing at another squad's namespace (or
       ksquad-system) is rejected fail-closed — the ref is name-only, resolved in-namespace by
       construction, so a Team can never reference another Team's Secret.

Why differential: a happy-path "it mounted a Secret" demo passes with a broken composer that honors a
cross-squad ref, falls back to a shared master when no ref is set, or admits a control-plane master
Secret. We first prove a NAIVE composer (keeps a shared master catalog, resolves a missing ref to that
master, honors cross-namespace + system-namespace refs verbatim) is DETECTED as violating every
invariant -- so the harness has real teeth -- then prove the §11/§12.1 composer violates nothing and
rejects exactly the hostile Agents. stdlib only; `python3 per-user-secret-ref-check.py`.
"""
import sys

SYSTEM_NS = "ksquad-system"                       # the control plane; never a squad credential source
# Well-known shared master names a naive design might introduce (ADR-010 explicitly excludes these).
SHARED_MASTER_NAMES = {"ksquad-master-creds", "ksquad-shared-provider-token", "platform-anthropic-key"}


class Rejected(Exception):
    """Admission/compose rejection — the composer fail-closes rather than resolving a hostile ref."""


def _ref_parts(agent):
    """The Agent's credential pointer: credentialSecretRef, or the BYO §10.3 modelEndpointRef Secret.

    A ref is either a bare name (str) — resolved in the Agent's OWN namespace by construction — or a
    namespace-qualified {name, namespace} dict, which is the shape a cross-squad leak would take.
    Returns (name, namespace_or_None) or (None, None) when the Agent carries no credential ref.
    """
    ref = agent.get("credentialSecretRef") or agent.get("modelEndpointRef")
    if ref is None:
        return None, None
    if isinstance(ref, str):
        return ref, None                          # name-only -> resolves in own ns
    return ref.get("name"), ref.get("namespace")  # namespace-qualified -> a potential cross-ns pointer


# ---- composers: each resolves an Agent to the Secret the shim would be handed --------------------

def compose_correct(agent, platform_catalog):
    """The §11/§12.1 composer: name-only per-user ref resolved in the Agent's own namespace, no shared
    master, cross-namespace/system refs rejected fail-closed (AD-9/ADR-010, FR-G1)."""
    name, ns = _ref_parts(agent)
    own_ns = agent["ns"]
    # AC1: a missing/empty ref is a rejection — NEVER a fall-through to a platform-default token.
    if not name:
        raise Rejected(f"{agent['name']}: no per-user credentialSecretRef — refusing to compose "
                       f"(no shared-master fallback, AC1/FR-G1)")
    # AC3: name-only resolves in-namespace; a namespace-qualified ref may only name the own namespace.
    if ns is not None and ns != own_ns:
        raise Rejected(f"{agent['name']}: credential ref points at namespace {ns!r} != own {own_ns!r} "
                       f"— cross-squad Secret ref rejected (AC3/§12.1)")
    # AC2: never a control-plane (system-ns) Secret, never a well-known shared master. This guard is
    # reached by a name-only OR own-ns-qualified shared-master ref — so it is the *decisive* rejector
    # for `master-grab-local` (F1: a system-ns master would be caught by the AC3 branch first, leaving
    # this branch un-exercised / teeth-less; the name-only own-ns case forces it to fire).
    if name in SHARED_MASTER_NAMES:
        raise Rejected(f"{agent['name']}: ref names shared master {name!r} — KSquad holds no shared "
                       f"master credential (AC2/AD-9)")
    # F2: the resolved namespace is *derived from the ref* (own_ns for a name-only ref, else the
    # already-validated == own_ns), not hardcoded — so the AC3 admitted-resolution check is
    # non-vacuous: a mutation that dropped the cross-ns guard above would surface a foreign namespace
    # here, not silently collapse to own_ns.
    resolved_ns = ns if ns is not None else own_ns
    return {"agent": agent["name"], "secretNamespace": resolved_ns, "secretName": name,
            "source": "per-user"}


def compose_naive(agent, platform_catalog):
    """A plausible-but-wrong composer: keeps a shared master, falls back to it when no ref is set, and
    honors cross-namespace / system-namespace refs verbatim. Every invariant this story pins is
    violated -- the harness must catch it."""
    name, ns = _ref_parts(agent)
    if not name:
        # AC1/AC2 violation: silent fallback to the shared platform master in ksquad-system.
        master = platform_catalog["master"]
        return {"agent": agent["name"], "secretNamespace": SYSTEM_NS, "secretName": master,
                "source": "shared-master"}
    if ns is None:
        # A name-only ref is handled the same as the correct composer — so the differential is crisp:
        # the valid Agents pass under BOTH composers, and only the hostile refs below expose the gap.
        return {"agent": agent["name"], "secretNamespace": agent["ns"], "secretName": name,
                "source": "per-user"}
    # AC3/AC2 violation: honor a namespace-qualified ref verbatim — another squad's ns, or the
    # control plane — instead of rejecting it. This is the cross-squad leak the story forbids.
    return {"agent": agent["name"], "secretNamespace": ns, "secretName": name, "source": "as-referenced"}


# ---- invariant checks: return a list of violation strings -----------------------------------------

def check_credentials(agents, compose, platform_catalog):
    """Resolve every Agent and assert the §11/§12.1 credential-isolation invariants over the result.

    Returns (violations, rejected) where `rejected` maps Agent name -> reason for the fail-closed set.
    """
    viol, rejected, resolutions = [], {}, []

    # AC2: the platform must hold NO shared master credential catalog (custody stays per-principal).
    if platform_catalog.get("master"):
        viol.append(f"platform holds a shared master credential {platform_catalog['master']!r} "
                    f"in {SYSTEM_NS} — KSquad stores no shared master (AC2/AD-9/ADR-010)")

    for agent in agents:
        try:
            res = compose(agent, platform_catalog)
        except Rejected as r:
            rejected[agent["name"]] = str(r)
            continue
        resolutions.append((agent, res))

    for agent, res in resolutions:
        # AC1: the resolved credential must be a per-user Secret, not a shared/default one.
        if res["source"] != "per-user":
            viol.append(f"{agent['name']}: resolved via {res['source']!r} not a per-user Secret ref "
                        f"(AC1/FR-G1)")
        # AC2: never a control-plane Secret, never a well-known shared master.
        if res["secretNamespace"] == SYSTEM_NS:
            viol.append(f"{agent['name']}: credential resolved in control-plane ns {SYSTEM_NS} (AC2)")
        if res["secretName"] in SHARED_MASTER_NAMES:
            viol.append(f"{agent['name']}: credential is shared master {res['secretName']!r} (AC2)")
        # AC3: the Secret must live in the Agent's OWN Team namespace — never cross-squad.
        if res["secretNamespace"] != agent["ns"]:
            viol.append(f"{agent['name']}: credential in ns {res['secretNamespace']!r} != own squad "
                        f"ns {agent['ns']!r} — cross-squad credential (AC3/§12.1)")
    return viol, rejected


def main():
    ns_alpha, ns_bravo = "ksquad-team-alpha-3f1a", "ksquad-team-bravo-9c2b"
    agents = [
        # Valid per-user refs: name-only, resolved in each Agent's own squad namespace.
        {"name": "alice-claude", "ns": ns_alpha, "family": "claude",
         "credentialSecretRef": "alice-claude-oauth"},
        {"name": "alice-hermes", "ns": ns_alpha, "family": "second",
         "credentialSecretRef": "alice-hermes-key"},
        {"name": "bob-ollama", "ns": ns_bravo, "family": "byo",              # §10.3 BYO endpoint Secret
         "modelEndpointRef": "bob-ollama-endpoint"},
        # HOSTILE 1 — cross-squad ref: an alpha Agent points at bravo's Secret (AC3).
        {"name": "xsquad-leak", "ns": ns_alpha, "family": "claude",
         "credentialSecretRef": {"name": "bob-claude-oauth", "namespace": ns_bravo}},
        # HOSTILE 2 — shared master in the control plane (AC2 + AC3: it is *also* a cross-ns ref).
        {"name": "master-grab", "ns": ns_alpha, "family": "claude",
         "credentialSecretRef": {"name": "ksquad-master-creds", "namespace": SYSTEM_NS}},
        # HOSTILE 2b — shared master named IN THE AGENT'S OWN NAMESPACE (name-only). This passes the
        # AC3 cross-ns branch (ns == own), so ONLY the AC2 shared-master-name guard can reject it — the
        # teeth for that guard (F1: `master-grab` alone is caught by AC3 first, leaving AC2 untested).
        {"name": "master-grab-local", "ns": ns_alpha, "family": "claude",
         "credentialSecretRef": "ksquad-master-creds"},
        # HOSTILE 3 — no credential ref at all; a naive composer falls back to the shared master (AC1).
        {"name": "no-cred", "ns": ns_alpha, "family": "claude", "credentialSecretRef": None},
    ]
    expected_rejects = {"xsquad-leak", "master-grab", "master-grab-local", "no-cred"}

    # Naive world: the platform maintains a shared master credential (the exact ADR-010 anti-pattern).
    naive_catalog = {"master": "ksquad-master-creds"}
    naive, naive_rej = check_credentials(agents, compose_naive, naive_catalog)
    print(f"[model] naive composer : {len(naive)} credential-isolation violation(s) -> "
          f"{'DETECTED' if naive else 'NONE (teeth lost!)'}; rejected={sorted(naive_rej)}")
    for v in naive:
        print(f"[model]   - {v}")
    if not naive:
        print("[model] FAIL — naive composer should break credential isolation but did not; no teeth.")
        return 1
    if naive_rej:
        print("[model] FAIL — naive composer unexpectedly rejected a hostile ref; it must admit them.")
        return 1

    # §11/§12.1 world: no shared master catalog; hostile refs fail closed.
    good_catalog = {"master": None}
    good, good_rej = check_credentials(agents, compose_correct, good_catalog)
    print(f"[model] §11 composer    : {len(good)} violations; rejected={sorted(good_rej)}; "
          f"admitted={len(agents) - len(good_rej)}")
    for v in good:
        print(f"[model]   - {v}")
    for name, reason in sorted(good_rej.items()):
        print(f"[model]   reject {name}: {reason}")
    if good:
        print("[model] FAIL — §11/§12.1 composer must hold every credential-isolation invariant.")
        return 1
    if set(good_rej) != expected_rejects:
        print(f"[model] FAIL — expected rejects {sorted(expected_rejects)}, got {sorted(good_rej)}.")
        return 1

    print("[model] PASS — naive detectably breaks credential isolation; §11/§12.1 composer holds "
          "AC1-AC3 (per-user Secret ref, no shared master, per-namespace never cross-squad).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
