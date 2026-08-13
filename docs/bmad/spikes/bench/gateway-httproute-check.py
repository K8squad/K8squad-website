#!/usr/bin/env python3
"""Story 9.1 (ISI-2250) falsification — the Helm chart CREATES the Gateway + HTTPRoute
exposure for the console + apiserver, apiserver route preserves SSE, fails fast if
`gateway.className` is unset, and NEVER creates a GatewayClass (arch §16.1, ADR-022,
Theme L / FR-L1…L3; chart impl = ISI-2149 / ISI-2286).

WHY THIS BENCH EXISTS
---------------------
The chart is the install seam: on ANY cluster with a Gateway API controller (cilium /
envoy / istio / traefik), `helm install --set gateway.className=<x>` must render a
`Gateway` (listeners + TLS from values) and `HTTPRoute`s binding the console + apiserver
Services — and the apiserver route MUST preserve the SSE progress stream (§13): no
response buffering, no default idle timeout that cuts a long-lived stream. Four ways a
plausible-but-wrong chart silently breaks the acceptance, none caught by "it renders":

  1. SSE-KILLER — the apiserver HTTPRoute omits the timeout override (or sets a finite
     one), so the GatewayClass's default route timeout (Envoy's 15s) cuts the live Run
     stream. The chart renders, `kubectl get httproute` is green, and the console's live
     channel dies 15s in. The timeout MUST be disabled (`timeouts.request: "0s"`) on the
     APISERVER route specifically — the SSE endpoint (§13), not the console route.

  2. NOT-FROM-VALUES — gatewayClassName / hostnames / cert-secret hardcoded or
     cluster-defaulted. "It renders" but only on the author's cluster; the platform
     engineer's cilium/traefik class is ignored. §16.1: these are REQUIRED values
     inputs, never a hardcode, never the cluster default.

  3. SILENT-FALLBACK — `gateway.className` unset does NOT fail the install; the chart
     falls back to a hardcoded/default class and dangles a route against a class that
     may not exist. §16.1: install MUST fail fast with a clear error.

  4. CREATES-A-CLASS — the chart renders a `GatewayClass` object. §16.1: the chart
     REFERENCES the operator-provided GatewayClass and NEVER creates one (creating one
     collides with the controller's own and is not the chart's to own).

Two falsification layers, both stdlib-only (`python3 gateway-httproute-check.py`):

  LAYER A — model-based mutation battery. A faithful mini-renderer of the chart's
  gateway-mode exposure + fail-fast validate (mirrors the real templates). Six checks
  C1–C6 ↔ the acceptance. A battery of broken-chart mutations; EACH must be caught by a
  designated check going RED, and the §16.1-conformant baseline is GREEN on all six.
  Differential checks (render two distinct value profiles and assert the output tracks
  the input) give the teeth against hardcoding that "it renders once" cannot.

  LAYER B — file-grounded pass over the PINNED real chart snapshot
  (`helm-chart-isi2149/`, k8squad@5e6442d). Asserts the SHIPPED templates satisfy each
  invariant, and — crucially — text-mutates each real template and asserts the detector
  flips RED, so the file-grounded checks have teeth on the real artifact, not just the
  model. Ties the model to reality: if the shipped chart drifts, Layer B fails.

Exit non-zero if any mutation survives (Layer A), any real-chart invariant is violated,
or any file-grounded detector fails to flip (Layer B).
"""
import copy
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "helm-chart-isi2149")


# ══════════════════════════════════════════════════════════════════════════════════════
#  Value profiles — two distinct installs. Differential checks assert output tracks input.
# ══════════════════════════════════════════════════════════════════════════════════════

def profile(name):
    """Two fully-specified, DISTINCT gateway-mode value sets (A and B). Every field a
    hardcoding mutation might freeze differs between them, so a differential check catches
    the freeze."""
    if name == "A":
        return {
            "release": "ksq",
            "console": {"service": {"port": 80, "targetPort": 3000}},
            "apiserver": {"service": {"port": 80, "targetPort": 8080}},
            "exposure": {
                "mode": "gateway",
                "hostnames": {"console": "ksquad.a.example.com",
                              "apiserver": "api.a.example.com"},
                "gateway": {
                    "gatewayClassName": "cilium",
                    "listeners": {
                        "http":  {"enabled": True, "port": 80},
                        "https": {"enabled": True, "port": 443, "certSecretName": "tls-a"},
                    },
                    "httpsRedirect": True,
                },
                "ingress": {"className": "", "tls": {"enabled": False, "secretName": ""},
                            "annotations": {}},
            },
            "storage": {"storageClassName": "fast-a",
                        "postgres": {"storageClassName": ""},
                        "workspace": {"storageClassName": "", "accessMode": "ReadWriteOnce"},
                        "nats": {"storageClassName": ""}},
        }
    # profile B — every exposure field distinct from A
    return {
        "release": "ksq",
        "console": {"service": {"port": 8080, "targetPort": 3000}},
        "apiserver": {"service": {"port": 9090, "targetPort": 8080}},
        "exposure": {
            "mode": "gateway",
            "hostnames": {"console": "console.b.example.com",
                          "apiserver": "sse.b.example.com"},
            "gateway": {
                "gatewayClassName": "envoy",
                "listeners": {
                    "http":  {"enabled": True, "port": 8081},
                    "https": {"enabled": True, "port": 8443, "certSecretName": "tls-b"},
                },
                "httpsRedirect": False,
            },
            "ingress": {"className": "", "tls": {"enabled": False, "secretName": ""},
                        "annotations": {}},
        },
        "storage": {"storageClassName": "fast-b",
                    "postgres": {"storageClassName": ""},
                    "workspace": {"storageClassName": "", "accessMode": "ReadWriteOnce"},
                    "nats": {"storageClassName": ""}},
    }


class FailFast(Exception):
    """Models a Helm `{{ fail }}` — install aborts before any object is applied."""


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER A — faithful mini-renderer of the chart's gateway-mode exposure + validate.
#  Mirrors deploy/helm/ksquad/templates/{gateway,httproute,service}.yaml + _helpers.tpl
#  (ksquad.validate). The renderer is the "provisioner"; mutations subclass/patch it.
# ══════════════════════════════════════════════════════════════════════════════════════

class Chart:
    """Baseline §16.1-conformant renderer. render() -> list of k8s objects (dicts)."""

    # --- helpers (mirror _helpers.tpl) ---
    def fullname(self, v):     return v["release"]
    def console_name(self, v): return self.fullname(v) + "-console"
    def api_name(self, v):     return self.fullname(v) + "-apiserver"

    def storage_class(self, v, family):
        return v["storage"][family]["storageClassName"] or v["storage"]["storageClassName"]

    # --- ksquad.validate (fail-fast pre-flight; runs on every render) ---
    def validate(self, v):
        ex = v["exposure"]
        mode = ex["mode"]
        if mode not in ("gateway", "ingress", "clusterip"):
            raise FailFast(f"exposure.mode must be one of gateway|ingress|clusterip, got {mode!r}")
        if mode != "clusterip":
            if not ex["hostnames"]["console"]:
                raise FailFast("exposure.hostnames.console is REQUIRED for gateway/ingress modes")
            if not ex["hostnames"]["apiserver"]:
                raise FailFast("exposure.hostnames.apiserver is REQUIRED for gateway/ingress modes (the SSE endpoint, §13)")
        if mode == "gateway":
            self.validate_gateway(v)
        for fam in ("postgres", "workspace", "nats"):
            if not self.storage_class(v, fam):
                raise FailFast(f"storage.storageClassName (or storage.{fam}.storageClassName) is REQUIRED — never the cluster default (§16.2)")

    def validate_gateway(self, v):
        g = v["exposure"]["gateway"]
        if not g["gatewayClassName"]:
            raise FailFast("exposure.gateway.gatewayClassName is REQUIRED when exposure.mode=gateway — the chart references, never creates, a GatewayClass")
        if g["listeners"]["https"]["enabled"] and not g["listeners"]["https"]["certSecretName"]:
            raise FailFast("exposure.gateway.listeners.https.certSecretName is REQUIRED when the https listener is enabled")
        if not g["listeners"]["http"]["enabled"] and not g["listeners"]["https"]["enabled"]:
            raise FailFast("at least one exposure.gateway.listeners.{http,https}.enabled must be true (ISI-2286 F2)")

    # --- render ---
    def render(self, v):
        self.validate(v)
        objs = self.render_services(v)
        if v["exposure"]["mode"] == "gateway":
            objs += self.render_gateway(v)
            objs += self.render_httproutes(v)
        return objs

    def render_services(self, v):
        return [
            {"kind": "Service", "name": self.console_name(v), "component": "console",
             "port": v["console"]["service"]["port"]},
            {"kind": "Service", "name": self.api_name(v), "component": "apiserver",
             "port": v["apiserver"]["service"]["port"]},
        ]

    def render_gateway(self, v):
        g = v["exposure"]["gateway"]
        listeners = []
        if g["listeners"]["http"]["enabled"]:
            listeners.append({"name": "http", "protocol": "HTTP",
                              "port": g["listeners"]["http"]["port"]})
        if g["listeners"]["https"]["enabled"]:
            listeners.append({"name": "https", "protocol": "HTTPS",
                              "port": g["listeners"]["https"]["port"],
                              "tls": {"mode": "Terminate",
                                      "certificateRefs": [{"kind": "Secret",
                                                           "name": g["listeners"]["https"]["certSecretName"]}]}})
        return [{"kind": "Gateway", "name": self.fullname(v),
                 "gatewayClassName": g["gatewayClassName"], "listeners": listeners}]

    def serve_section(self, v):
        # ternary "https" "http" $g.listeners.https.enabled — prefer https listener.
        return "https" if v["exposure"]["gateway"]["listeners"]["https"]["enabled"] else "http"

    def render_httproutes(self, v):
        g = v["exposure"]["gateway"]
        sect = self.serve_section(v)
        gw = self.fullname(v)
        routes = [
            {"kind": "HTTPRoute", "name": self.console_name(v), "component": "console",
             "parentRef": gw, "sectionName": sect,
             "hostname": v["exposure"]["hostnames"]["console"],
             "timeouts": None,  # console route needs no timeout override
             "backendRef": {"name": self.console_name(v), "port": v["console"]["service"]["port"]}},
            {"kind": "HTTPRoute", "name": self.api_name(v), "component": "apiserver",
             "parentRef": gw, "sectionName": sect,
             "hostname": v["exposure"]["hostnames"]["apiserver"],
             # SSE PRESERVATION (§13, §16.1): disable route + backend timeout.
             "timeouts": {"request": "0s", "backendRequest": "0s"},
             "backendRef": {"name": self.api_name(v), "port": v["apiserver"]["service"]["port"]}},
        ]
        if g["httpsRedirect"] and g["listeners"]["http"]["enabled"] and g["listeners"]["https"]["enabled"]:
            routes.append({"kind": "HTTPRoute", "name": self.fullname(v) + "-https-redirect",
                           "component": "exposure", "parentRef": gw, "sectionName": "http",
                           "hostname": [v["exposure"]["hostnames"]["console"],
                                        v["exposure"]["hostnames"]["apiserver"]],
                           "redirect": {"scheme": "https", "statusCode": 301}})
        return routes


# small render helpers used by checks -----------------------------------------------------

def try_render(chart, v):
    """Return (objs, failfast_msg_or_None)."""
    try:
        return chart.render(copy.deepcopy(v)), None
    except FailFast as e:
        return None, str(e)


def find(objs, kind, component=None):
    for o in objs or []:
        if o["kind"] == kind and (component is None or o.get("component") == component):
            return o
    return None


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER A — checks C1–C6 (each returns (ok: bool, detail: str)). Differential where a
#  hardcode would otherwise slip through.
# ══════════════════════════════════════════════════════════════════════════════════════

def C1_gateway_listeners_tls_from_values(chart):
    """Gateway rendered with listeners + TLS FROM VALUES (not hardcoded/defaulted)."""
    a, ea = try_render(chart, profile("A"))
    b, eb = try_render(chart, profile("B"))
    if ea or eb:
        return False, f"gateway-mode render failed: {ea or eb}"
    ga, gb = find(a, "Gateway"), find(b, "Gateway")
    if not ga or not gb:
        return False, "no Gateway object rendered in gateway mode"
    # gatewayClassName tracks values (A=cilium, B=envoy) → not hardcoded, not defaulted
    if ga["gatewayClassName"] != "cilium" or gb["gatewayClassName"] != "envoy":
        return False, f"gatewayClassName not from values: A={ga['gatewayClassName']} B={gb['gatewayClassName']}"
    # https listener present, TLS Terminate, certRef tracks values (tls-a/tls-b)
    for g, want_cert, want_port in ((ga, "tls-a", 443), (gb, "tls-b", 8443)):
        https = next((l for l in g["listeners"] if l["name"] == "https"), None)
        if not https:
            return False, "https listener missing"
        if https["port"] != want_port:
            return False, f"https listener port not from values (got {https['port']}, want {want_port})"
        if https["tls"]["mode"] != "Terminate":
            return False, "https listener TLS mode != Terminate"
        cert = https["tls"]["certificateRefs"][0]["name"]
        if cert != want_cert:
            return False, f"cert secret not from values (got {cert}, want {want_cert})"
        http = next((l for l in g["listeners"] if l["name"] == "http"), None)
        if not http:
            return False, "http listener missing"
    # http listener port tracks values (A=80, B=8081)
    ha = next(l for l in ga["listeners"] if l["name"] == "http")
    hb = next(l for l in gb["listeners"] if l["name"] == "http")
    if ha["port"] != 80 or hb["port"] != 8081:
        return False, "http listener port not from values"
    return True, "Gateway listeners + TLS cert + class all track values (A≠B)"


def C2_httproutes_bind_both_services(chart):
    """Two HTTPRoutes: console→console svc, apiserver→apiserver svc; parentRef the
    Gateway; sectionName a REAL enabled listener; hostnames from values."""
    for prof in ("A", "B"):
        v = profile(prof)
        objs, e = try_render(chart, v)
        if e:
            return False, f"[{prof}] render failed: {e}"
        gw = find(objs, "Gateway")["name"]
        enabled = {l["name"] for l in find(objs, "Gateway")["listeners"]}
        cr = find(objs, "HTTPRoute", "console")
        ar = find(objs, "HTTPRoute", "apiserver")
        if not cr or not ar:
            return False, f"[{prof}] missing console or apiserver HTTPRoute"
        # each route binds ITS OWN service (the classic misbind: apiserver→console)
        if cr["backendRef"]["name"] != find(objs, "Service", "console")["name"]:
            return False, f"[{prof}] console route backendRef != console Service"
        if ar["backendRef"]["name"] != find(objs, "Service", "apiserver")["name"]:
            return False, f"[{prof}] apiserver route backendRef != apiserver Service (misbind)"
        if cr["backendRef"]["name"] == ar["backendRef"]["name"]:
            return False, f"[{prof}] both routes bind the SAME service"
        # parentRef → the Gateway; sectionName not dangling
        for r in (cr, ar):
            if r["parentRef"] != gw:
                return False, f"[{prof}] {r['component']} route parentRef != Gateway"
            if r["sectionName"] not in enabled:
                return False, f"[{prof}] {r['component']} route sectionName {r['sectionName']!r} is a DANGLING listener (enabled={enabled})"
        # hostnames from values (differential-safe: compare to this profile's values)
        if cr["hostname"] != v["exposure"]["hostnames"]["console"]:
            return False, f"[{prof}] console route hostname not from values"
        if ar["hostname"] != v["exposure"]["hostnames"]["apiserver"]:
            return False, f"[{prof}] apiserver route hostname not from values"
        # backend ports from values
        if ar["backendRef"]["port"] != v["apiserver"]["service"]["port"]:
            return False, f"[{prof}] apiserver backend port not from values"
    return True, "console+apiserver routes bind their own Services, parentRef Gateway, live listener, hosts from values"


def C3_apiserver_route_preserves_sse(chart):
    """The APISERVER route (the SSE endpoint, §13) disables the route timeout so a
    long-lived progress stream is never cut. request timeout must be 0s — not absent,
    not finite."""
    objs, e = try_render(chart, profile("A"))
    if e:
        return False, f"render failed: {e}"
    ar = find(objs, "HTTPRoute", "apiserver")
    t = ar.get("timeouts")
    if not t:
        return False, "apiserver route has NO timeout override — GatewayClass default (e.g. Envoy 15s) will cut the SSE stream"
    req = t.get("request")
    if req != "0s":
        return False, f"apiserver route request timeout is {req!r}, not '0s' — a finite/default timeout cuts SSE"
    # backendRequest must not silently re-introduce a finite cap
    if "backendRequest" in t and t["backendRequest"] not in ("0s", None):
        return False, f"apiserver backendRequest timeout {t['backendRequest']!r} re-caps the stream"
    return True, "apiserver route timeouts.request='0s' (SSE stream never cut)"


def C4_fail_fast_when_class_unset(chart):
    """Install FAILS FAST if gateway.className unset — never falls back to a default/
    hardcoded class. Also: https-without-cert and zero-listeners fail fast."""
    # (a) unset gatewayClassName MUST fail — and MUST NOT render a class-defaulted Gateway
    v = profile("A"); v["exposure"]["gateway"]["gatewayClassName"] = ""
    objs, e = try_render(chart, v)
    if objs is not None:
        gw = find(objs, "Gateway")
        cls = gw["gatewayClassName"] if gw else "<none>"
        return False, f"unset gatewayClassName did NOT fail — chart rendered with class {cls!r} (silent fallback)"
    if "gatewayClassName" not in e:
        return False, f"failed, but not on gatewayClassName: {e}"
    # (b) https listener enabled but no cert → fail fast
    v = profile("A"); v["exposure"]["gateway"]["listeners"]["https"]["certSecretName"] = ""
    _, e2 = try_render(chart, v)
    if e2 is None or "certSecretName" not in e2:
        return False, "https listener without certSecretName did not fail fast"
    # (c) both listeners disabled → fail fast (no dangling sectionName)
    v = profile("A")
    v["exposure"]["gateway"]["listeners"]["http"]["enabled"] = False
    v["exposure"]["gateway"]["listeners"]["https"]["enabled"] = False
    _, e3 = try_render(chart, v)
    if e3 is None or "at least one" not in e3:
        return False, "gateway with zero listeners did not fail fast"
    return True, "unset class + https-no-cert + zero-listeners all fail fast (no silent fallback)"


def C5_never_creates_gatewayclass(chart):
    """The chart NEVER renders a GatewayClass object — it references the operator's."""
    for prof in ("A", "B"):
        objs, e = try_render(chart, profile(prof))
        if e:
            return False, f"[{prof}] render failed: {e}"
        if find(objs, "GatewayClass"):
            return False, f"[{prof}] chart rendered a GatewayClass object — must only REFERENCE one"
    return True, "no GatewayClass object rendered in any profile (reference-only)"


def C6_https_redirect_from_values(chart):
    """http→https redirect is values-driven: profile A (httpsRedirect=true, both
    listeners) renders a RequestRedirect route on the http listener; profile B
    (httpsRedirect=false) does NOT."""
    a, ea = try_render(chart, profile("A"))
    b, eb = try_render(chart, profile("B"))
    if ea or eb:
        return False, f"render failed: {ea or eb}"
    ra = find(a, "HTTPRoute", "exposure")
    rb = find(b, "HTTPRoute", "exposure")
    if not ra:
        return False, "profile A (httpsRedirect=true) rendered NO redirect route"
    if ra.get("redirect", {}).get("scheme") != "https" or ra["sectionName"] != "http":
        return False, "redirect route is not a RequestRedirect→https on the http listener"
    if rb is not None:
        return False, "profile B (httpsRedirect=false) STILL rendered a redirect route (not values-driven)"
    return True, "redirect route present iff httpsRedirect=true (values-driven)"


CHECKS = [
    ("C1", "Gateway listeners + TLS from values", C1_gateway_listeners_tls_from_values),
    ("C2", "HTTPRoutes bind console + apiserver svc", C2_httproutes_bind_both_services),
    ("C3", "apiserver route preserves SSE (0s)",     C3_apiserver_route_preserves_sse),
    ("C4", "fail-fast when gateway.className unset",  C4_fail_fast_when_class_unset),
    ("C5", "never creates a GatewayClass",            C5_never_creates_gatewayclass),
    ("C6", "https-redirect is values-driven",         C6_https_redirect_from_values),
]


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER A — mutations. Each is a broken Chart; the `caught_by` check(s) MUST go RED and
#  the baseline MUST be GREEN on all. A mutation no check catches = a hole in the bench.
# ══════════════════════════════════════════════════════════════════════════════════════

class M_HardcodeClass(Chart):
    """SSE fine, but gatewayClassName frozen to a literal, ignoring values → C1."""
    def render_gateway(self, v):
        v = copy.deepcopy(v); v["exposure"]["gateway"]["gatewayClassName"] = "nginx-fixed"
        return Chart.render_gateway(self, v)

class M_DefaultClassFallback(Chart):
    """Unset class silently defaults instead of failing → C4."""
    def validate_gateway(self, v):
        if not v["exposure"]["gateway"]["gatewayClassName"]:
            v["exposure"]["gateway"]["gatewayClassName"] = "default"   # silent fallback
        Chart.validate_gateway(self, v)
    def render_gateway(self, v):
        v = copy.deepcopy(v)
        if not v["exposure"]["gateway"]["gatewayClassName"]:
            v["exposure"]["gateway"]["gatewayClassName"] = "default"
        return Chart.render_gateway(self, v)

class M_DropApiTimeout(Chart):
    """apiserver route omits the timeout override → default route timeout cuts SSE → C3."""
    def render_httproutes(self, v):
        rs = Chart.render_httproutes(self, v)
        find(rs, "HTTPRoute", "apiserver")["timeouts"] = None
        return rs

class M_FiniteApiTimeout(Chart):
    """apiserver route sets a finite 60s timeout → SSE cut at 60s → C3."""
    def render_httproutes(self, v):
        rs = Chart.render_httproutes(self, v)
        find(rs, "HTTPRoute", "apiserver")["timeouts"] = {"request": "60s", "backendRequest": "60s"}
        return rs

class M_TimeoutOnConsoleOnly(Chart):
    """0s timeout put on the console route, apiserver left defaulted → C3."""
    def render_httproutes(self, v):
        rs = Chart.render_httproutes(self, v)
        find(rs, "HTTPRoute", "console")["timeouts"] = {"request": "0s", "backendRequest": "0s"}
        find(rs, "HTTPRoute", "apiserver")["timeouts"] = None
        return rs

class M_MisbindApiToConsole(Chart):
    """apiserver route backendRef points at the console service → C2."""
    def render_httproutes(self, v):
        rs = Chart.render_httproutes(self, v)
        find(rs, "HTTPRoute", "apiserver")["backendRef"] = {"name": self.console_name(v),
                                                            "port": v["console"]["service"]["port"]}
        return rs

class M_RenderGatewayClass(Chart):
    """Chart also renders a GatewayClass object → C5."""
    def render_gateway(self, v):
        objs = Chart.render_gateway(self, v)
        objs.append({"kind": "GatewayClass", "name": "ksquad-class",
                     "controller": "example.com/gateway"})
        return objs

class M_SkipClassValidate(Chart):
    """validate no longer requires gatewayClassName; render tolerates empty → C4."""
    def validate_gateway(self, v):
        g = v["exposure"]["gateway"]
        if g["listeners"]["https"]["enabled"] and not g["listeners"]["https"]["certSecretName"]:
            raise FailFast("certSecretName is REQUIRED")
        if not g["listeners"]["http"]["enabled"] and not g["listeners"]["https"]["enabled"]:
            raise FailFast("at least one listener")
        # gatewayClassName check REMOVED

class M_IgnoreRedirect(Chart):
    """httpsRedirect value ignored — redirect route never rendered → C6."""
    def render_httproutes(self, v):
        rs = Chart.render_httproutes(self, v)
        return [r for r in rs if r.get("component") != "exposure"]

class M_HardcodeHostnames(Chart):
    """Console/apiserver route hostnames frozen to literals → C2 (and C6)."""
    def render_httproutes(self, v):
        v2 = copy.deepcopy(v)
        v2["exposure"]["hostnames"] = {"console": "ksquad.example.com",
                                       "apiserver": "api.example.com"}
        return Chart.render_httproutes(self, v2)

class M_HardcodeCert(Chart):
    """https listener cert secret frozen to a literal → C1."""
    def render_gateway(self, v):
        v2 = copy.deepcopy(v)
        v2["exposure"]["gateway"]["listeners"]["https"]["certSecretName"] = "ksquad-tls"
        return Chart.render_gateway(self, v2)


MUTATIONS = [
    ("M1  hardcode gatewayClassName",       M_HardcodeClass(),        {"C1"}),
    ("M2  silent default-class fallback",   M_DefaultClassFallback(), {"C4"}),
    ("M3  drop apiserver timeout",          M_DropApiTimeout(),       {"C3"}),
    ("M4  finite 60s apiserver timeout",    M_FiniteApiTimeout(),     {"C3"}),
    ("M5  0s on console, not apiserver",    M_TimeoutOnConsoleOnly(), {"C3"}),
    ("M6  apiserver route → console svc",   M_MisbindApiToConsole(),  {"C2"}),
    ("M7  render a GatewayClass object",    M_RenderGatewayClass(),   {"C5"}),
    ("M8  skip gatewayClassName validate",  M_SkipClassValidate(),    {"C4"}),
    ("M9  ignore httpsRedirect value",      M_IgnoreRedirect(),       {"C6"}),
    ("M10 hardcode hostnames",              M_HardcodeHostnames(),    {"C2"}),
    ("M11 hardcode TLS cert secret",        M_HardcodeCert(),         {"C1"}),
]


def run_layer_a():
    print("=" * 92)
    print("LAYER A — model-based mutation battery (chart render + fail-fast validate)")
    print("=" * 92)
    baseline = Chart()
    print("\nBaseline (§16.1-conformant chart) — every check must be GREEN:")
    base_results = {}
    all_green = True
    for cid, desc, fn in CHECKS:
        ok, detail = fn(baseline)
        base_results[cid] = ok
        all_green &= ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid} {desc:<40} — {detail}")
    if not all_green:
        print("\n✗ BASELINE FAILED — the conformant chart model does not pass its own checks.")
        return False

    print("\nMutations — each must be CAUGHT (≥1 designated check flips RED):")
    header = "  " + " ".join(f"{c:>4}" for c, _, _ in CHECKS)
    print(header)
    ok_all = True
    for label, chart, expect in MUTATIONS:
        row, caught = [], False
        for cid, _, fn in CHECKS:
            try:
                passed, _ = fn(chart)
            except Exception as ex:                       # a mutation that crashes a check = caught
                passed = False
                _ = ex
            red = not passed
            if red and cid in expect:
                caught = True
            row.append(" RED" if red else "  . ")
        # teeth: at least one EXPECTED check must be RED for this mutation
        status = "caught" if caught else "SURVIVED"
        ok_all &= caught
        print(f"  {' '.join(f'{c:>4}' for c in row)}   {label:<34} expect{sorted(expect)} -> {status}")
        if not caught:
            print(f"       ✗ mutation SURVIVED — no expected check {sorted(expect)} went RED")
    return ok_all


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER B — file-grounded pass over the pinned real chart snapshot. Each detector must
#  (i) PASS on the shipped template text and (ii) FLIP when the template is text-mutated,
#  so the file-grounded checks have teeth on the real artifact, not just the model.
# ══════════════════════════════════════════════════════════════════════════════════════

def read(rel):
    p = os.path.join(SNAP, rel)
    with open(p, encoding="utf-8") as f:
        return f.read()


def det_sse_zero_timeout(texts):
    """apiserver HTTPRoute disables the timeout: the httproute template sets request 0s
    on the apiserver rule (the SSE endpoint) and NOT a finite value."""
    t = texts["templates/httproute.yaml"]
    m = re.search(r'timeouts:\s*\n\s*request:\s*"0s"\s*\n\s*backendRequest:\s*"0s"', t)
    finite = re.search(r'request:\s*"\d+s"', t) and not re.search(r'request:\s*"0s"', t)
    return bool(m) and not finite


def det_no_gatewayclass(texts):
    """No template renders a GatewayClass object (reference-only)."""
    for name, t in texts.items():
        if not name.startswith("templates/"):
            continue
        if re.search(r'^\s*kind:\s*GatewayClass\b', t, re.M):
            return False
    return True


def det_class_from_values(texts):
    """gateway.yaml sources gatewayClassName from a values variable ($g...), never a literal."""
    t = texts["templates/gateway.yaml"]
    return bool(re.search(r'gatewayClassName:\s*\{\{\s*\$g\.gatewayClassName', t))


def det_class_failfast(texts):
    """ksquad.validate fails fast when gateway.gatewayClassName is unset in gateway mode."""
    t = texts["templates/_helpers.tpl"]
    return bool(re.search(r'not\s+\.Values\.exposure\.gateway\.gatewayClassName', t)
                and re.search(r'gatewayClassName is REQUIRED', t))

def det_both_backends(texts):
    """httproute template binds BOTH the console and apiserver service backends — checked
    on the `- name:` backendRef bindings specifically (not the metadata name), so losing
    one backend flips the detector."""
    t = texts["templates/httproute.yaml"]
    console_backend = re.search(r'-\s*name:\s*\{\{\s*include "ksquad\.console\.fullname"', t)
    api_backend = re.search(r'-\s*name:\s*\{\{\s*include "ksquad\.apiserver\.fullname"', t)
    return bool(console_backend and api_backend and 'kind: HTTPRoute' in t)


FG_DETECTORS = [
    ("FG1 apiserver route disables timeout (SSE)", "templates/httproute.yaml",
     det_sse_zero_timeout, ('request: "0s"',        'request: "30s"')),
    ("FG2 no GatewayClass object rendered",        "templates/gateway.yaml",
     det_no_gatewayclass, ('kind: Gateway\n',       'kind: GatewayClass\n')),
    ("FG3 gatewayClassName sourced from values",   "templates/gateway.yaml",
     det_class_from_values, ('{{ $g.gatewayClassName | quote }}', 'nginx"  # hardcoded')),
    ("FG4 fail-fast on unset gatewayClassName",    "templates/_helpers.tpl",
     det_class_failfast, ('gatewayClassName is REQUIRED', 'gatewayClassName is optional')),
    ("FG5 both service backends bound",            "templates/httproute.yaml",
     det_both_backends, ('- name: {{ include "ksquad.apiserver.fullname" . }}',
                         '- name: {{ include "ksquad.console.fullname" . }}')),
]


def run_layer_b():
    print("\n" + "=" * 92)
    print(f"LAYER B — file-grounded pass over pinned real chart (helm-chart-isi2149/, k8squad@5e6442d)")
    print("=" * 92)
    # load real templates
    names = ["templates/httproute.yaml", "templates/gateway.yaml", "templates/service.yaml",
             "templates/ingress.yaml", "templates/_helpers.tpl", "templates/NOTES.txt"]
    try:
        texts = {n: read(n) for n in names}
    except FileNotFoundError as e:
        print(f"  ✗ pinned chart snapshot missing: {e}")
        return False

    ok_all = True
    for label, tgt, det, (find_s, repl_s) in FG_DETECTORS:
        shipped = det(texts)
        # mutate the real template text and assert the detector flips to False
        mutated = dict(texts)
        if find_s in mutated[tgt]:
            mutated[tgt] = mutated[tgt].replace(find_s, repl_s, 1)
            flipped = not det(mutated)
        else:
            flipped = False
            print(f"  (note) mutation anchor {find_s!r} not found in {tgt}")
        teeth = shipped and flipped
        ok_all &= teeth
        print(f"  [{'PASS' if teeth else 'FAIL'}] {label:<44} shipped={'ok' if shipped else 'VIOLATED'}  "
              f"detector-flips-on-mutation={'yes' if flipped else 'NO'}")
    return ok_all


# ══════════════════════════════════════════════════════════════════════════════════════

def main():
    a = run_layer_a()
    b = run_layer_b()
    print("\n" + "=" * 92)
    if a and b:
        print("✓ ALL GREEN — baseline passes C1–C6; all 11 mutations caught; 5 file-grounded "
              "detectors pass on the shipped chart and have teeth. Story 9.1 acceptance is falsifiable.")
        return 0
    print("✗ FAILURES ABOVE — see RED / SURVIVED / VIOLATED rows.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
