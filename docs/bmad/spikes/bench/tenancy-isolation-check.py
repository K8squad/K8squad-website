#!/usr/bin/env python3
"""Story 4.1 falsification — squad = namespace tenancy isolation (arch §12.1, AD-5, ADR-011).

Differential check. It models the *set of Kubernetes objects a Team reconciler would create* for a
couple of sample Teams, then asserts the arch §12.1 isolation invariants over that set:

  AC1  Team -> namespace is 1:1 and deterministic; distinct Teams -> distinct namespaces.
  AC2  agent grants are namespaced least-privilege: NO ClusterRole/ClusterRoleBinding, no wildcard
       ('*') resources/verbs, no cross-namespace reach; RoleBinding subject is the squad SA only.
  AC3  every namespace ships a ResourceQuota AND a LimitRange.
  AC4  every namespace ships a default-deny NetworkPolicy (podSelector {}, Ingress+Egress).
  AC7  nothing is created in ksquad-system; no Team namespace resolves to ksquad-system.

Why differential: a happy-path "it made a namespace" demo passes with a broken, over-permissive
provisioner. We first prove a NAIVE provisioner (ClusterRole bind, one shared namespace, no quota,
no LimitRange, no default-deny) is DETECTED as violating -- so the harness has real teeth -- then
prove the §12.1 provisioner violates nothing. stdlib only; `python3 tenancy-isolation-check.py`.
"""
import sys

SYSTEM_NS = "ksquad-system"
RESERVED_NS = {"kube-system", "kube-public", "kube-node-lease", "default", SYSTEM_NS}


# ---- provisioners: each returns the list of objects it would create for a Team --------------------

def team_ns(team):
    """Deterministic 1:1 namespace name for a Team (§12.1)."""
    return f"ksquad-team-{team}"


def provision_correct(team):
    """The arch §12.1 scaffold: namespaced least-privilege + quota + limitrange + default-deny."""
    ns = team_ns(team)
    return [
        {"kind": "Namespace", "name": ns,
         "labels": {"ksquad.io/team": team, "ksquad.io/tenancy": "squad"}},
        {"kind": "ServiceAccount", "namespace": ns, "name": "ksquad-agent"},
        {"kind": "Role", "namespace": ns, "name": "ksquad-agent",
         "rules": [{"resources": ["configmaps", "secrets"], "verbs": ["get", "list"]},
                   {"resources": ["pods"], "verbs": ["get", "list", "watch"]}]},
        {"kind": "RoleBinding", "namespace": ns, "name": "ksquad-agent",
         "roleRef": {"kind": "Role", "name": "ksquad-agent"},
         "subjects": [{"kind": "ServiceAccount", "name": "ksquad-agent", "namespace": ns}]},
        {"kind": "ResourceQuota", "namespace": ns, "name": "ksquad-quota"},
        {"kind": "LimitRange", "namespace": ns, "name": "ksquad-limits"},
        {"kind": "NetworkPolicy", "namespace": ns, "name": "default-deny",
         "podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
    ]


def provision_naive(team):
    """A plausible-but-wrong provisioner: cluster-wide bind, ONE shared namespace, no quota/limits,
    no default-deny NetworkPolicy. Every AC this story pins is violated -- the harness must catch it."""
    ns = "ksquad-shared"  # AC1 violation: not per-Team
    return [
        {"kind": "Namespace", "name": ns, "labels": {}},
        {"kind": "ServiceAccount", "namespace": ns, "name": "ksquad-agent"},
        {"kind": "ClusterRole", "name": "ksquad-agent-cluster",      # AC2 violation
         "rules": [{"resources": ["*"], "verbs": ["*"]}]},           # AC2 violation: wildcard
        {"kind": "ClusterRoleBinding", "name": "ksquad-agent-cluster",  # AC2 violation
         "roleRef": {"kind": "ClusterRole", "name": "ksquad-agent-cluster"},
         "subjects": [{"kind": "Group", "name": "system:authenticated"}]},
        # AC3 violation: no ResourceQuota, no LimitRange.
        # AC4 violation: no default-deny NetworkPolicy.
    ]


# ---- invariant checks: return a list of violation strings -----------------------------------------

def check_isolation(teams, provision):
    """Assert §12.1 isolation invariants over the objects `provision` makes for each Team."""
    viol = []
    ns_by_team = {}
    for team in teams:
        objs = provision(team)

        nss = [o for o in objs if o["kind"] == "Namespace"]
        if len(nss) != 1:
            viol.append(f"{team}: expected exactly 1 Namespace, got {len(nss)}")  # AC1
            continue
        ns = nss[0]["name"]
        ns_by_team[team] = ns

        # AC7: no Team namespace may be a system/reserved namespace, and nothing lands in ksquad-system.
        if ns in RESERVED_NS:
            viol.append(f"{team}: namespace {ns!r} is a reserved/system namespace (AC7)")
        for o in objs:
            if o.get("namespace") == SYSTEM_NS or (o["kind"] == "Namespace" and o["name"] == SYSTEM_NS):
                viol.append(f"{team}: object {o['kind']}/{o.get('name')} created in {SYSTEM_NS} (AC7)")

        # AC2: least-privilege, namespaced. No cluster-scoped RBAC, no wildcards, SA-only binding.
        for o in objs:
            if o["kind"] in ("ClusterRole", "ClusterRoleBinding"):
                viol.append(f"{team}: {o['kind']}/{o['name']} — agent grants must be namespaced, not cluster-wide (AC2)")
            if o["kind"] == "Role":
                for rule in o.get("rules", []):
                    if "*" in rule.get("resources", []) or "*" in rule.get("verbs", []):
                        viol.append(f"{team}: Role/{o['name']} has wildcard resources/verbs (AC2)")
            if o["kind"] == "RoleBinding":
                for s in o.get("subjects", []):
                    if s.get("kind") != "ServiceAccount" or s.get("namespace") != ns:
                        viol.append(f"{team}: RoleBinding/{o['name']} binds non-SA or cross-ns subject {s} (AC2)")

        # AC3 + AC4: quota, limitrange, default-deny NetworkPolicy all present in the namespace.
        kinds = {o["kind"] for o in objs}
        for req in ("ResourceQuota", "LimitRange"):
            if req not in kinds:
                viol.append(f"{team}: namespace {ns} missing {req} (AC3)")
        deny = [o for o in objs if o["kind"] == "NetworkPolicy"
                and o.get("podSelector") == {}
                and set(o.get("policyTypes", [])) == {"Ingress", "Egress"}]
        if not deny:
            viol.append(f"{team}: namespace {ns} missing default-deny NetworkPolicy (AC4)")

    # AC1: distinct Teams -> distinct namespaces (no collision), deterministic mapping.
    seen = {}
    for team, ns in ns_by_team.items():
        if ns in seen:
            viol.append(f"{team} and {seen[ns]} share namespace {ns!r} — Team->namespace not 1:1 (AC1)")
        seen[ns] = team
    for team in ns_by_team:  # deterministic: same Team resolves to same name twice
        if provision(team)[0]["name"] != provision(team)[0]["name"]:
            viol.append(f"{team}: namespace name is non-deterministic (AC1)")
    return viol


def main():
    teams = ["alpha", "bravo"]

    naive = check_isolation(teams, provision_naive)
    print(f"[model] naive provisioner: {len(naive)} isolation violation(s) -> "
          f"{'DETECTED' if naive else 'NONE (teeth lost!)'}")
    for v in naive:
        print(f"[model]   - {v}")
    if not naive:
        print("[model] FAIL — naive provisioner should violate isolation but did not; harness has no teeth.")
        return 1

    good = check_isolation(teams, provision_correct)
    ns_list = [team_ns(t) for t in teams]
    distinct = len(set(ns_list)) == len(ns_list) and SYSTEM_NS not in ns_list
    print(f"[model] §12.1 provisioner : {len(good)} violations; {len(teams)} Teams -> "
          f"{len(set(ns_list))} distinct namespaces, neither == {SYSTEM_NS}"
          if distinct else f"[model] §12.1 provisioner namespace mapping FAILED: {ns_list}")
    for v in good:
        print(f"[model]   - {v}")
    if good or not distinct:
        print("[model] FAIL — §12.1 scaffold must hold every isolation invariant.")
        return 1

    print("[model] PASS — naive detectably breaks isolation; §12.1 scaffold holds AC1-AC4/AC7.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
