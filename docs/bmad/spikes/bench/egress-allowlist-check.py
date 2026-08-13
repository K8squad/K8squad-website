#!/usr/bin/env python3
"""Story 4.6 falsification — default-deny egress + model-endpoint allowlist + optional proxy
(arch §12.2, AD-7, ADR-012, D5, NFR-SEC4).

Differential check. Story 4.1 already lays the namespace egress *baseline* (default-deny +
allow-DNS + allow-control-plane). This story layers, on top of that baseline, the **explicit
model-endpoint allowlist** and the **optional `Project.egressPolicyRef` forward-proxy** path.

The crux this harness pins is a property of Kubernetes NetworkPolicy that makes the naive
"allowlist" silently open:

  * NetworkPolicy egress is **purely additive** — the effective reachable set of a pod is the
    UNION of the `to:` selectors of every egress-allow rule that selects it. There is NO deny rule
    that can override a too-broad allow. "Default-deny" only means anything because *absence* of an
    allow = deny. Therefore an allow rule with an **empty `to:`** (allow all destinations on those
    ports) or `to: ipBlock 0.0.0.0/0` is **allow-all** and defeats default-deny — you cannot "layer
    default-deny back on top" to fix it.

  * The `HTTPS_PROXY` env var is **advisory** — a non-proxy-aware or hostile process ignores it and
    egresses directly. Proxy mode is enforced ONLY by the NetworkPolicy: the direct-model allow must
    be **replaced** by an allow-to-proxy-only. If both the direct-model allow AND the proxy allow
    select the pod, direct egress is still open and the proxy is unenforced.

We model the effective egress-reachable set of a Run pod as the union of allow rules selecting it,
then assert (INV-1) direct mode reaches exactly {DNS, control-plane, resolved model endpoint} and
NOT the internet-at-large; (INV-2) proxy mode reaches exactly {DNS, control-plane, proxy} and NOT
the model endpoint directly nor the internet, with HTTPS_PROXY injected and NO_PROXY covering
cluster-internal; and that the model endpoint is **derived from the Agent's resolved endpoint**
(§10.3), not a hardcoded vendor CIDR (D5 — egress is policy, not hardcode).

We first prove NAIVE provisioners are DETECTED (empty-`to` allow, 0.0.0.0/0 allow, default-deny
removed, proxy-env-only-with-direct-still-open, hardcoded-vendor-CIDR) — so the harness has teeth —
then prove the §12.2 provisioner violates nothing. stdlib only; `python3 egress-allowlist-check.py`.
"""
import ipaddress
import sys

SYSTEM_NS = "ksquad-system"
DNS_NS = "kube-system"

# ---- destinations a Run pod might try to reach (the probe set) -------------------------------------
# Each is (label, kind, ns_or_none, ip_or_none, port). "internet" is the exfil probe: a public IP
# that is NOT a model endpoint, NOT the proxy, NOT DNS, NOT the control plane. It must be UNreachable.
DNS_DST      = ("dns",      "ns", DNS_NS,    None,            53)
CP_DST       = ("control",  "ns", SYSTEM_NS, None,            443)
MODEL_DST    = ("model",    "ip", None,      "203.0.113.10",  443)   # resolved Agent model endpoint
PROXY_DST    = ("proxy",    "ip", None,      "198.51.100.5",  8080)  # the forward proxy
INTERNET_DST = ("internet", "ip", None,      "8.8.8.8",       443)   # exfil probe — must be denied
PROBES = [DNS_DST, CP_DST, MODEL_DST, PROXY_DST, INTERNET_DST]

# What the Agent CRD actually resolves its model endpoint to (§10.3). The allowlist must be DERIVED
# from THIS, not from a hardcoded vendor CIDR. Here the squad runs a BYO/relocated endpoint.
AGENT_MODEL_CIDR = "203.0.113.10/32"
HARDCODED_VENDOR_CIDR = "203.0.113.200/32"  # a wrong, baked-in guess — denies the real endpoint


# ---- selector matching: does an egress `to:` selector match a destination? -------------------------

def selector_matches(sel, dst):
    _, kind, ns, ip, _ = dst
    if sel.get("any"):                     # empty `to:` -> allow ALL destinations (the footgun)
        return True
    if "cidr" in sel:
        if ip is None:
            return False
        net = ipaddress.ip_network(sel["cidr"])
        if net.prefixlen == 0:             # 0.0.0.0/0 -> allow-all
            return True
        return ipaddress.ip_address(ip) in net
    if "ns" in sel:
        return kind == "ns" and ns == sel["ns"]
    return False


def reachable(policies, dst):
    """A destination is reachable iff SOME egress-allow rule (in any policy selecting the pod) has a
    `to:` selector matching it. Union semantics — this is exactly how K8s NetworkPolicy composes."""
    for pol in policies:
        if "Egress" not in pol.get("policyTypes", []):
            continue
        for rule in pol.get("egress", []):
            tos = rule.get("to")
            sels = [{"any": True}] if not tos else tos   # NO `to:` == allow all destinations
            for sel in sels:
                if selector_matches(sel, dst):
                    return True
    return False


def has_default_deny(policies):
    return any(p.get("podSelector") == {} and set(p.get("policyTypes", [])) == {"Ingress", "Egress"}
               and not p.get("egress") and not p.get("ingress") for p in policies)


# ---- provisioners: (policies, pod_env) a reconciler would apply to a Run pod -----------------------

def baseline():
    """Story 4.1 namespace baseline: default-deny + allow-DNS + allow-control-plane."""
    return [
        {"name": "default-deny", "podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
        {"name": "allow-dns", "podSelector": {}, "policyTypes": ["Egress"],
         "egress": [{"to": [{"ns": DNS_NS}], "ports": [{"protocol": "UDP", "port": 53}]}]},
        {"name": "allow-control-plane", "podSelector": {}, "policyTypes": ["Egress"],
         "egress": [{"to": [{"ns": SYSTEM_NS}]}]},
    ]


def provision_direct(model_cidr=AGENT_MODEL_CIDR):
    """§12.2 DIRECT mode: baseline + an explicit model-endpoint allow DERIVED from the Agent."""
    pols = baseline() + [
        {"name": "allow-model-endpoint", "podSelector": {"ksquad.io/run": ""},
         "policyTypes": ["Egress"],
         "egress": [{"to": [{"cidr": model_cidr}], "ports": [{"protocol": "TCP", "port": 443}]}]},
    ]
    return pols, {}  # no proxy env in direct mode


def provision_proxy():
    """§12.2 PROXY mode (Project.egressPolicyRef): the direct-model allow is REPLACED by an
    allow-to-proxy-only, and HTTPS_PROXY/NO_PROXY are injected. Default-deny + DNS + CP remain."""
    pols = baseline() + [
        {"name": "allow-egress-proxy", "podSelector": {"ksquad.io/run": ""},
         "policyTypes": ["Egress"],
         "egress": [{"to": [{"cidr": "198.51.100.5/32"}], "ports": [{"protocol": "TCP", "port": 8080}]}]},
    ]
    env = {"HTTPS_PROXY": "http://198.51.100.5:8080", "HTTP_PROXY": "http://198.51.100.5:8080",
           # NO_PROXY must cover cluster-internal so control-plane/DNS/in-cluster traffic is NOT
           # misrouted through the corporate proxy (and keeps working if the proxy is down).
           "NO_PROXY": f"{SYSTEM_NS}.svc,.svc,.cluster.local,10.0.0.0/8,169.254.169.254"}
    return pols, env


# ---- naive (wrong) provisioners the harness MUST detect -------------------------------------------

def naive_empty_to():
    """"Allowlist" with an empty `to:` on 443 — reads as "allow model traffic" but is allow-ALL."""
    pols = baseline() + [
        {"name": "allow-model-endpoint", "podSelector": {"ksquad.io/run": ""},
         "policyTypes": ["Egress"],
         "egress": [{"ports": [{"protocol": "TCP", "port": 443}]}]},  # NO `to:` -> allow all :443
    ]
    return pols, {}


def naive_world_cidr():
    """Allow `0.0.0.0/0` — the other way to accidentally ship open egress."""
    pols = baseline() + [
        {"name": "allow-model-endpoint", "podSelector": {"ksquad.io/run": ""},
         "policyTypes": ["Egress"],
         "egress": [{"to": [{"cidr": "0.0.0.0/0"}], "ports": [{"protocol": "TCP", "port": 443}]}]},
    ]
    return pols, {}


def naive_removed_deny():
    """Adds the model allow but DROPS the default-deny (open by default again)."""
    pols = [p for p in provision_direct()[0] if p["name"] != "default-deny"]
    return pols, {}


def naive_proxy_env_only():
    """Proxy mode done as env-only: HTTPS_PROXY set, but the direct-model allow is STILL present, so a
    non-proxy-aware/hostile process egresses straight to the model endpoint — proxy unenforced."""
    pols, _ = provision_direct()   # direct-model allow left in place
    env = {"HTTPS_PROXY": "http://198.51.100.5:8080"}  # advisory only
    return pols, env


def naive_hardcoded_vendor():
    """Allow a HARDCODED vendor CIDR instead of the Agent's resolved endpoint — denies the real
    (BYO/relocated) endpoint and allows an address the squad never uses (D5 violation: hardcode)."""
    return provision_direct(model_cidr=HARDCODED_VENDOR_CIDR)


# ---- the invariant checks -------------------------------------------------------------------------

def check_direct(pols, env):
    v = []
    if not has_default_deny(pols):
        v.append("default-deny NetworkPolicy is absent — namespace is open by default (INV-1)")
    want = {"dns": True, "control": True, "model": True, "proxy": False, "internet": False}
    for dst in PROBES:
        label = dst[0]
        got = reachable(pols, dst)
        if got != want[label]:
            v.append(f"direct mode: {label} reachable={got}, want {want[label]} "
                     f"(allowlist must be exactly DNS+control-plane+model, nothing else) (INV-1)")
    return v


def check_proxy(pols, env):
    v = []
    if not has_default_deny(pols):
        v.append("proxy mode dropped default-deny (INV-2)")
    want = {"dns": True, "control": True, "model": False, "proxy": True, "internet": False}
    for dst in PROBES:
        label = dst[0]
        got = reachable(pols, dst)
        if got != want[label]:
            v.append(f"proxy mode: {label} reachable={got}, want {want[label]} — proxy is enforced "
                     f"by policy (direct-model allow REPLACED), not by env alone (INV-2)")
    if "HTTPS_PROXY" not in env:
        v.append("proxy mode: HTTPS_PROXY not injected into the sandbox (INV-2)")
    if "cluster.local" not in env.get("NO_PROXY", "") and ".svc" not in env.get("NO_PROXY", ""):
        v.append("proxy mode: NO_PROXY does not cover cluster-internal — control-plane/DNS misrouted "
                 "through the corporate proxy (INV-2)")
    return v


def check_derivation(pols):
    """D5: the model allow must match the Agent's RESOLVED endpoint, not a hardcoded guess."""
    v = []
    if not reachable(pols, MODEL_DST):
        v.append("the Agent's resolved model endpoint is NOT reachable — allowlist was not derived "
                 "from the Agent (hardcoded/stale); the Run cannot reach its model (D5)")
    return v


def main():
    rc = 0

    # --- teeth: every naive provisioner must be DETECTED --------------------------------------------
    naive_cases = [
        ("empty-`to` allow (=allow-all :443)", naive_empty_to, check_direct),
        ("0.0.0.0/0 allow (=allow-all)",       naive_world_cidr, check_direct),
        ("default-deny removed",               naive_removed_deny, check_direct),
        ("proxy env-only, direct still open",  naive_proxy_env_only, check_proxy),
    ]
    for name, prov, check in naive_cases:
        pols, env = prov()
        v = check(pols, env)
        print(f"[model] NAIVE {name}: {len(v)} violation(s) -> {'DETECTED' if v else 'NONE (teeth lost!)'}")
        for x in v:
            print(f"[model]   - {x}")
        if not v:
            print(f"[model] FAIL — naive '{name}' should be caught but was not; harness has no teeth.")
            rc = 1

    # hardcoded-vendor is a derivation (D5) violation: it denies the real endpoint.
    pols, _ = naive_hardcoded_vendor()
    v = check_derivation(pols)
    print(f"[model] NAIVE hardcoded vendor CIDR: {len(v)} violation(s) -> "
          f"{'DETECTED' if v else 'NONE (teeth lost!)'}")
    for x in v:
        print(f"[model]   - {x}")
    if not v:
        print("[model] FAIL — hardcoded-vendor endpoint should be caught (D5) but was not.")
        rc = 1

    # --- the §12.2 provisioner must hold every invariant, in BOTH modes -----------------------------
    pols, env = provision_direct()
    v = check_direct(pols, env) + check_derivation(pols)
    print(f"[model] §12.2 DIRECT mode : {len(v)} violation(s) -> "
          f"{'reaches exactly DNS+control-plane+model; internet DENIED' if not v else 'BROKEN'}")
    for x in v:
        print(f"[model]   - {x}")
    rc = rc or (1 if v else 0)

    pols, env = provision_proxy()
    v = check_proxy(pols, env)
    print(f"[model] §12.2 PROXY mode  : {len(v)} violation(s) -> "
          f"{'reaches DNS+control-plane+proxy only; model-direct & internet DENIED; HTTPS_PROXY+NO_PROXY set' if not v else 'BROKEN'}")
    for x in v:
        print(f"[model]   - {x}")
    rc = rc or (1 if v else 0)

    if rc == 0:
        print("[model] PASS — naive open-egress footguns detectably break isolation; "
              "§12.2 allowlist holds default-deny + narrow allow in both direct and proxy modes.")
    else:
        print("[model] FAIL — see violations above.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
