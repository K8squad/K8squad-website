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
import hashlib
import re
import sys

SYSTEM_NS = "ksquad-system"
RESERVED_NS = {"kube-system", "kube-public", "kube-node-lease", "default", SYSTEM_NS}
DNS1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")  # a K8s namespace name label


# ---- provisioners: each returns the list of objects it would create for a Team --------------------

def team_ns(team):
    """Deterministic, DNS-1123-safe, collision-safe 1:1 namespace name for a Team (§12.1, F4).

    `Team` is a *namespaced* CRD, so two Teams in different namespaces may share a display name;
    the name alone is neither unique nor guaranteed DNS-1123. We normalize the display name to a
    bounded DNS-1123 prefix and disambiguate with a short hash of the Team's UID. Resolved once and
    recorded on `status.namespace`; the same (name, uid) always maps to the same namespace.
    """
    name, uid = team["name"], team["uid"]
    norm = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")[:40].strip("-") or "team"
    h = hashlib.sha1(uid.encode()).hexdigest()[:8]
    return f"ksquad-team-{norm}-{h}"


def provision_correct(team):
    """The arch §12.1 scaffold: namespaced least-privilege + quota + limitrange + default-deny."""
    ns = team_ns(team)
    return [
        {"kind": "Namespace", "name": ns,
         "labels": {"ksquad.io/team": team["name"], "ksquad.io/tenancy": "squad"}},
        {"kind": "ServiceAccount", "namespace": ns, "name": "ksquad-agent"},
        # F1: the Role floor never grants namespace-wide `secrets: list`. `list` returns *every*
        # principal's BYO Secret in the namespace, defeating §12.1 per-principal isolation and
        # bypassing §9.4/Story 4.5 workspace scoping. Secrets are get-by-name (resourceNames) only;
        # per-principal narrowing (a Secret name per Run) is added by the Run reconciler on top.
        {"kind": "Role", "namespace": ns, "name": "ksquad-agent",
         "rules": [{"resources": ["configmaps"], "verbs": ["get", "list"]},
                   {"resources": ["secrets"], "verbs": ["get"],
                    "resourceNames": ["ksquad-agent-config"]},
                   {"resources": ["pods"], "verbs": ["get", "list", "watch"]}]},
        {"kind": "RoleBinding", "namespace": ns, "name": "ksquad-agent",
         "roleRef": {"kind": "Role", "name": "ksquad-agent"},
         "subjects": [{"kind": "ServiceAccount", "name": "ksquad-agent", "namespace": ns}]},
        {"kind": "ResourceQuota", "namespace": ns, "name": "ksquad-quota"},
        {"kind": "LimitRange", "namespace": ns, "name": "ksquad-limits"},
        {"kind": "NetworkPolicy", "namespace": ns, "name": "default-deny",
         "podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
        # F2: default-deny alone leaves Runs unable to resolve DNS or reach the control plane, so the
        # namespace baseline pins two companion egress-allow policies (§12.2): allow-DNS (kube-dns :53)
        # and allow-control-plane (ksquad-system). The §12.2 model-endpoint allowlist layers further
        # egress on top of these; it does not replace them. All three ship together as the baseline.
        {"kind": "NetworkPolicy", "namespace": ns, "name": "allow-dns",
         "podSelector": {}, "policyTypes": ["Egress"],
         "egress": [
             {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}}],
              "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
         ]},
        {"kind": "NetworkPolicy", "namespace": ns, "name": "allow-control-plane",
         "podSelector": {}, "policyTypes": ["Egress"],
         "egress": [
             {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": SYSTEM_NS}}}]},
         ]},
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
        {"kind": "Role", "namespace": ns, "name": "ksquad-agent",    # F1 violation:
         "rules": [{"resources": ["secrets"], "verbs": ["get", "list"]}]},  # namespace-wide secrets list
        # AC3 violation: no ResourceQuota, no LimitRange.
        # AC4 violation: no default-deny NetworkPolicy, no allow-DNS/control-plane companion.
    ]


# ---- invariant checks: return a list of violation strings -----------------------------------------

def check_isolation(teams, provision):
    """Assert §12.1 isolation invariants over the objects `provision` makes for each Team."""
    viol = []
    ns_by_team = {}
    for team in teams:
        tn = team["name"]
        objs = provision(team)

        nss = [o for o in objs if o["kind"] == "Namespace"]
        if len(nss) != 1:
            viol.append(f"{tn}: expected exactly 1 Namespace, got {len(nss)}")  # AC1
            continue
        ns = nss[0]["name"]
        ns_by_team[ns] = ns_by_team.get(ns, []) + [tn]

        # AC1/F4: the resolved namespace name must be a valid DNS-1123 label (<=63 chars).
        if not DNS1123.match(ns) or len(ns) > 63:
            viol.append(f"{tn}: namespace {ns!r} is not a DNS-1123 label / >63 chars (AC1/F4)")

        # AC7: no Team namespace may be a system/reserved namespace, and nothing lands in ksquad-system.
        if ns in RESERVED_NS:
            viol.append(f"{tn}: namespace {ns!r} is a reserved/system namespace (AC7)")
        for o in objs:
            if o.get("namespace") == SYSTEM_NS or (o["kind"] == "Namespace" and o["name"] == SYSTEM_NS):
                viol.append(f"{tn}: object {o['kind']}/{o.get('name')} created in {SYSTEM_NS} (AC7)")

        # AC2: least-privilege, namespaced. No cluster-scoped RBAC, no wildcards, SA-only binding.
        for o in objs:
            if o["kind"] in ("ClusterRole", "ClusterRoleBinding"):
                viol.append(f"{tn}: {o['kind']}/{o['name']} — agent grants must be namespaced, not cluster-wide (AC2)")
            if o["kind"] == "Role":
                for rule in o.get("rules", []):
                    res, verbs = rule.get("resources", []), rule.get("verbs", [])
                    if "*" in res or "*" in verbs:
                        viol.append(f"{tn}: Role/{o['name']} has wildcard resources/verbs (AC2)")
                    # F1: secrets must be get-by-name only. A namespace-wide `list`/`watch` on secrets
                    # (or `get` without resourceNames) exposes every principal's BYO Secret (§12.1).
                    if "secrets" in res:
                        wide = sorted(set(verbs) & {"list", "watch"})
                        if wide:
                            viol.append(f"{tn}: Role/{o['name']} grants namespace-wide secrets {wide} "
                                        f"— defeats §12.1 per-principal Secret isolation (AC2/F1)")
                        if not rule.get("resourceNames"):
                            viol.append(f"{tn}: Role/{o['name']} grants secrets without resourceNames "
                                        f"(get-by-name) scoping (AC2/F1)")
            if o["kind"] == "RoleBinding":
                for s in o.get("subjects", []):
                    if s.get("kind") != "ServiceAccount" or s.get("namespace") != ns:
                        viol.append(f"{tn}: RoleBinding/{o['name']} binds non-SA or cross-ns subject {s} (AC2)")

        # AC3 + AC4: quota, limitrange, default-deny NetworkPolicy all present in the namespace.
        kinds = {o["kind"] for o in objs}
        for req in ("ResourceQuota", "LimitRange"):
            if req not in kinds:
                viol.append(f"{tn}: namespace {ns} missing {req} (AC3)")
        deny = [o for o in objs if o["kind"] == "NetworkPolicy"
                and o.get("podSelector") == {}
                and set(o.get("policyTypes", [])) == {"Ingress", "Egress"}]
        if not deny:
            viol.append(f"{tn}: namespace {ns} missing default-deny NetworkPolicy (AC4)")
        # F2: a default-deny with no companion egress-allow makes Runs non-functional (no DNS, no
        # control plane). Require a companion allow policy for kube-dns (:53) AND ksquad-system.
        allow = [o for o in objs if o["kind"] == "NetworkPolicy"
                 and "Egress" in o.get("policyTypes", []) and o.get("egress")]
        dns_ok = any(p.get("port") == 53 for o in allow for r in o["egress"] for p in r.get("ports", []))
        cp_ok = any(SYSTEM_NS in str(t) for o in allow for r in o["egress"] for t in r.get("to", []))
        if deny and not (dns_ok and cp_ok):
            viol.append(f"{tn}: namespace {ns} default-deny has no companion allow for DNS+{SYSTEM_NS} "
                        f"egress — Runs cannot resolve DNS or reach the control plane (AC4/F2)")

    # AC1: distinct Teams -> distinct namespaces (no collision), deterministic mapping.
    for ns, owners in ns_by_team.items():
        if len(owners) > 1:
            viol.append(f"{' and '.join(owners)} share namespace {ns!r} — Team->namespace not 1:1 (AC1)")
    for team in teams:  # deterministic: same Team resolves to same name twice
        if team_ns(team) != team_ns(team):
            viol.append(f"{team['name']}: namespace name is non-deterministic (AC1)")
    return viol


def main():
    teams = [{"name": "alpha", "uid": "3f1a-aaaa"}, {"name": "bravo", "uid": "9c2b-bbbb"}]

    # F4 teeth: an un-normalized `ksquad-team-<name>` is neither DNS-1123 nor collision-safe; the
    # normalized + UID-hashed name is both. Prove the raw form would be rejected before trusting it.
    hostile = {"name": "Alpha.Squad_1", "uid": "raw-uid"}
    raw = f"ksquad-team-{hostile['name']}"
    if DNS1123.match(raw):
        print("[model] FAIL — F4 demo lost teeth: raw namespace name is unexpectedly DNS-1123 valid.")
        return 1
    norm = team_ns(hostile)
    if not DNS1123.match(norm) or len(norm) > 63:
        print(f"[model] FAIL — normalized namespace {norm!r} is not a DNS-1123 label ≤63 chars (F4).")
        return 1
    if team_ns({"name": "dup", "uid": "u1"}) == team_ns({"name": "dup", "uid": "u2"}):
        print("[model] FAIL — same display name + different UID collided; UID hash must disambiguate (F4).")
        return 1
    print(f"[model] F4 name safety : raw {raw!r} rejected; normalized {norm!r} DNS-1123 + UID-disambiguated")

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
