#!/usr/bin/env python3
"""Generate screen 12 — Settings (dark + light), KSquad operator console.

A general platform-settings surface whose FIRST pane is OTLP exporter config:
a read-write form over the `OTelConfig` CRD (ISI-2289), written via the apiserver
BFF (no direct kube), RBAC-gated to authorized operators. Per-signal exporter
config for traces / metrics / logs — each: endpoint, protocol (grpc|http), auth
(a Secret *reference* — the UI never shows or stores a raw token),
resourceAttributes, sampling.

Default state is opt-in: no exporter configured → telemetry stays in-cluster.
This mock encodes all three states in one view — Traces configured (full form
expanded), Metrics configured (collapsed summary), Logs empty/first-run
("stays in-cluster until you add an exporter").

CEO ask (Henrik, ISI-2288 2026-08-12) + Gate-2 Architect data-contract
(§13 / §17.2 / ADR-029). Read-write config screen like Compose (FR-F5),
dark + light (FR-F7). Light variant mirrors the SAME token roles — no new hues.
Renders 1440x900 SVG; PNGs are the audited 1.5x (2160x1350) via @resvg/resvg-js.
"""

# --- token maps: dark / light (mirror the 00 visual-system sheet) ------------
DARK = dict(
    bg="#0B1220", rail="#0D1728", border="#25324B", card="#131D31", panel="#0E1626",
    divider="#1A2438", t1="#E8EEF9", t2="#B6C3D8", t3="#7E8CA6", t4="#586581",
    accent="#3D7DFF", accent2="#93B7FF", activebg="#16244A", avatar="#1A2842",
    logodot="#93B7FF",
    g_dot="#34D399", g_txt="#34D399", g_bg="#0F2E24",
    a_dot="#FBBF24", a_txt="#FBBF24", a_bg="#33280A",
    r_dot="#FB7185", r_txt="#FB7185", r_bg="#331521",
    i_dot="#64748B", i_txt="#64748B", i_bg="#182234",
)
LIGHT = dict(
    bg="#F6F8FC", rail="#EEF2F8", border="#D4DCEA", card="#FFFFFF", panel="#F1F5FA",
    divider="#ECF1F8", t1="#0B1220", t2="#33415C", t3="#64748B", t4="#6C7688",
    accent="#3D7DFF", accent2="#2563EB", activebg="#E5EDFF", avatar="#ECF1F8",
    logodot="#2563EB",
    g_dot="#059669", g_txt="#059669", g_bg="#E7F6EF",
    a_dot="#D97706", a_txt="#B45309", a_bg="#FCF3E2",
    r_dot="#E11D48", r_txt="#E11D48", r_bg="#FCE9EC",
    i_dot="#64748B", i_txt="#475569", i_bg="#EEF1F6",
)
BASE = dict(running="#34D399", paused="#FBBF24", blocked="#FB7185", idle="#64748B",
            succeeded="#34D399")


def status(T, s):
    m = {"running":   (T["g_dot"], T["g_txt"], T["g_bg"]),
         "succeeded": (T["g_dot"], T["g_txt"], T["g_bg"]),
         "paused":    (T["a_dot"], T["a_txt"], T["a_bg"]),
         "blocked":   (T["r_dot"], T["r_txt"], T["r_bg"]),
         "idle":      (T["i_dot"], T["i_txt"], T["i_bg"])}
    dot_, txt, bg = m[s]
    return dot_, txt, bg, BASE[s] + "55"


F  = 'font-family="DejaVu Sans"'
FM = 'font-family="DejaVu Sans Mono"'


def esc(s):
    return s.replace("&", "&amp;")


def text(x, y, s, size, fill, w=400, anchor="start", mono=False, ls=None):
    ff = FM if mono else F
    lsp = f' letter-spacing="{ls}"' if ls is not None else ""
    return (f'<text x="{x}" y="{y}" {ff} font-size="{size}" fill="{fill}" '
            f'font-weight="{w}" text-anchor="{anchor}"{lsp}>{esc(s)}</text>')


def rect(x, y, w, h, fill, rx=0, stroke="none", sw=1, dash=None):
    r = f' rx="{rx}" ry="{rx}"' if rx else ' rx="0" ry="0"'
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}"{r} '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def dot(cx, cy, rr, fill, pulse=False):
    s = f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="{fill}"/>'
    if pulse:
        s += (f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="none" stroke="{fill}" '
              f'stroke-width="1.5" opacity="0.5"><animate attributeName="r" '
              f'from="{rr}" to="{rr+5}" dur="1.6s" repeatCount="indefinite"/>'
              f'<animate attributeName="opacity" from="0.5" to="0" dur="1.6s" '
              f'repeatCount="indefinite"/></circle>')
    return s


def chip(x, y, w, h, label, bg, border, txt, size=11.5, mono=False, ls=None):
    pad = 11
    return (rect(x, y, w, h, bg, rx=h / 2 if h <= 24 else 6, stroke=border) +
            text(x + pad, y + h / 2 + 4, label, size, txt, w=600, mono=mono, ls=ls))


# ---- rail nav icons (color-parameterised, from the locked set) --------------
STK = 'fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'

def ic_dashboard(c): return f'<g {STK.format(c=c)}><path d="M25 98 v14 h14"/><path d="M28 108 l3 -4 l3 2 l4 -6"/></g>'
def ic_overview(c):  return f'<g {STK.format(c=c)}><rect x="24" y="143" width="6.5" height="6.5" rx="1.5"/><rect x="33.5" y="143" width="6.5" height="6.5" rx="1.5"/><rect x="24" y="152.5" width="6.5" height="6.5" rx="1.5"/><rect x="33.5" y="152.5" width="6.5" height="6.5" rx="1.5"/></g>'
def ic_runs(c):      return f'<g {STK.format(c=c)}><path d="M24 197 h4 l2 -5 l3 10 l2 -5 h3"/></g>'
def ic_builds(c):    return f'<g {STK.format(c=c)}><path d="M32 236 l6.5 3.5 v7 l-6.5 3.5 l-6.5 -3.5 v-7 z"/><path d="M25.5 239.5 l6.5 3.5 l6.5 -3.5"/><path d="M32 243 v7"/></g>'
def ic_discussion(c):return f'<g {STK.format(c=c)}><rect x="25" y="282" width="14" height="10" rx="2.5"/><path d="M29 292 v3 l3 -3"/><path d="M28 285.5 h8 M28 288.5 h5"/></g>'
def ic_projects(c):  return f'<g {STK.format(c=c)}><rect x="25" y="327" width="13" height="16" rx="1.5"/><path d="M25 338 h13"/><path d="M28.5 327 v11"/></g>'
def ic_agents(c):    return f'<g {STK.format(c=c)}><rect x="25.5" y="377" width="13" height="10" rx="2.5"/><path d="M32 374 v3"/><circle cx="32" cy="374" r="1.2" fill="{c}"/><circle cx="29.5" cy="382" r="1" fill="{c}"/><circle cx="34.5" cy="382" r="1" fill="{c}"/></g>'
def ic_creds(c):     return f'<g {STK.format(c=c)}><circle cx="28.5" cy="424" r="3.5"/><path d="M31 426.5 l6 6 M35 430.5 l1.5 -1.5 M37 432.5 l1.5 -1.5"/></g>'

def ic_settings(c, cx=32, cy=787):
    return (f'<g fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round">'
            f'<circle cx="{cx}" cy="{cy}" r="4.6"/>'
            f'<circle cx="{cx}" cy="{cy}" r="1.7" fill="{c}" stroke="none"/>'
            f'<path d="M{cx} {cy-7.6} v2.4 M{cx} {cy+7.6} v-2.4 M{cx-7.6} {cy} h2.4 M{cx+7.6} {cy} h-2.4 '
            f'M{cx-5.4} {cy-5.4} l1.6 1.6 M{cx+5.4} {cy+5.4} l-1.6 -1.6 '
            f'M{cx-5.4} {cy+5.4} l1.6 -1.6 M{cx+5.4} {cy-5.4} l-1.6 1.6"/></g>')

NAV = [
    ("Dashboard", 110, ic_dashboard, "dashboard"),
    ("Overview", 156, ic_overview, "overview"),
    ("Runs", 202, ic_runs, "runs"),
    ("Builds", 248, ic_builds, "builds"),
    ("Discussion", 294, ic_discussion, "discussion"),
    ("Projects", 340, ic_projects, "projects"),
    ("Agents", 386, ic_agents, "agents"),
    ("Credentials", 432, ic_creds, "credentials"),
]


def build_rail(T):
    s = []
    s.append(rect(0, 0, 236, 900, T["rail"]))
    s.append(rect(235, 0, 1, 900, T["border"]))
    s.append(f'<g transform="translate(30,34) scale(0.33735) translate(-50,-50)">'
             f'<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
             f'<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
             f'<rect x="45" y="25.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
             f'<rect x="45" y="64.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
             f'<rect x="42.5" y="42.5" width="15" height="15" rx="4.2" fill="{T["logodot"]}"/></g>')
    s.append(text(52, 32, "KSquad", 17, T["t1"], w=700, ls="0.2"))
    s.append(text(52, 46, "operator console", 10, T["t4"], ls="0.4"))
    for label, ty, icon, key in NAV:
        s.append(icon(T["t3"]))
        s.append(text(52, ty, label, 13.5, T["t2"], w=500))
    s.append(rect(16, 468, 204, 40, T["accent"], rx=9))
    s.append(text(112, 493, "+  Compose", 13.5, "#fff", w=600, anchor="middle"))
    # --- Settings footer nav item (active) -----------------------------------
    s.append(rect(10, 768, 216, 38, T["activebg"], rx=9, stroke=T["accent"] + "44"))
    s.append(rect(10, 768, 3, 38, T["accent"], rx=2))
    s.append(ic_settings(T["accent2"]))
    s.append(text(52, 792, "Settings", 13.5, T["t1"], w=600))
    # context pill
    s.append(rect(16, 826, 204, 54, T["panel"], rx=9, stroke=T["border"]))
    s.append(dot(34, 853, 3.5, T["g_dot"]))
    s.append(text(48, 849, "prod-euc1", 12.5, T["t2"], w=600, mono=True))
    s.append(text(48, 866, "context · connected", 10.5, T["t4"]))
    return "".join(s)


def build_header(T):
    s = []
    s.append(rect(236, 0, 1204, 60, T["bg"]))
    s.append(rect(236, 59, 1204, 1, T["border"]))
    s.append(text(260, 30, "Settings", 17, T["t1"], w=700))
    s.append(text(260, 47, "Platform configuration · OTLP exporter · general · access", 11.5, T["t3"]))
    s.append(f'<circle cx="1400" cy="30" r="15" fill="{T["avatar"]}" stroke="{T["border"]}"/>')
    s.append(text(1400, 34, "PN", 11.5, T["accent2"], w=700, anchor="middle"))
    s.append(rect(1283.6, 15, 84.4, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(dot(1297.6, 30, 3, T["accent"]))
    s.append(text(1307.6, 34, "ns: all", 12, T["t2"], mono=True))
    s.append(rect(1071.6, 15, 200, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(f'<circle cx="1086.6" cy="30" r="4.5" fill="none" stroke="{T["t4"]}" stroke-width="1.5"/>')
    s.append(f'<path d="M1090.1 33.5 l3 3" stroke="{T["t4"]}" stroke-width="1.5" stroke-linecap="round"/>')
    s.append(text(1101.6, 34, "Search settings…", 12, T["t4"]))
    return "".join(s)


# ---------------------------------------------------------------- form widgets
def lock(x, y, c):
    return (f'<g fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round">'
            f'<rect x="{x}" y="{y}" width="11" height="8" rx="1.7"/>'
            f'<path d="M{x+2.2} {y} v-2.4 a3.3 3.3 0 0 1 6.6 0 v2.4"/></g>')


def label(x, y, s, T):
    return text(x, y, s, 10.5, T["t3"], w=700, ls="0.5")


def field_input(T, x, y, w, value, icon_lock=False, mono=True, ph=False, h=34):
    s = [rect(x, y, w, h, T["panel"], rx=8, stroke=T["border"])]
    tx = x + 14
    if icon_lock:
        s.append(lock(x + 13, y + h / 2 - 4, T["accent2"]))
        tx = x + 34
    col = T["t3"] if ph else T["t1"]
    s.append(text(tx, y + h / 2 + 4, value, 12, col, mono=mono))
    return "".join(s)


def seg(T, x, y, opts, active, segw=76, h=32):
    n = len(opts)
    s = [rect(x, y, segw * n, h, T["panel"], rx=8, stroke=T["border"])]
    if 0 <= active < n:
        s.append(rect(x + active * segw + 2, y + 2, segw - 4, h - 4, T["accent"], rx=6))
    for i, o in enumerate(opts):
        on = i == active
        s.append(text(x + i * segw + segw / 2, y + h / 2 + 4.5, o, 12,
                      "#fff" if on else T["t2"], w=600, anchor="middle"))
    return "".join(s)


def kvchip(T, x, y, k, v):
    lbl = f"{k} = {v}"
    w = 20 + len(lbl) * 6.5
    return chip(x, y, w, 26, lbl, T["panel"], T["border"], T["t2"], size=10.5, mono=True), w


def toggle(T, x, y, on):
    track = T["accent"] if on else T["panel"]
    bd = T["accent"] if on else T["border"]
    kx = x + 44 - 12 if on else x + 12
    return (rect(x, y, 44, 24, track, rx=12, stroke=bd) +
            f'<circle cx="{kx}" cy="{y+12}" r="8.5" fill="#fff"/>')


# ------------------------------------------------------------------- signals
def traces_card(T, x, y, w):
    s = []
    ix = x + 18
    right = x + w - 18
    h = 400
    s.append(rect(x, y, w, h, T["card"], rx=12, stroke=T["border"]))
    # header
    d, txt, bg, bd = status(T, "succeeded")
    s.append(dot(ix + 5, y + 28, 4.5, d))
    s.append(text(ix + 18, y + 32, "Traces", 14, T["t1"], w=700))
    s.append(chip(right - 96, y + 18, 96, 22, "Configured", bg, bd, txt, size=10.5))
    s.append(rect(x + 14, y + 48, w - 28, 1, T["divider"]))
    # endpoint
    s.append(label(ix, y + 78, "ENDPOINT", T))
    s.append(field_input(T, ix, y + 86, w - 36, "otel-collector.observability.svc:4317"))
    # protocol + sampling row
    s.append(label(ix, y + 148, "PROTOCOL", T))
    s.append(seg(T, ix, y + 156, ["gRPC", "HTTP"], 0))
    s.append(text(ix + 168, y + 178, "OTLP/gRPC on :4317", 11, T["t4"]))
    s.append(label(right - 274, y + 148, "SAMPLING", T))
    s.append(field_input(T, right - 274, y + 156, 120, "0.10", mono=True))
    s.append(text(right - 146, y + 178, "parent-based ratio · 10%", 11, T["t4"]))
    # auth
    s.append(label(ix, y + 222, "AUTHENTICATION", T))
    s.append(field_input(T, ix, y + 230, w - 36, "Secret · secret://otlp-headers",
                         icon_lock=True))
    s.append(text(ix, y + 292, "References a Secret — the token is never shown or stored here.",
                  10.5, T["t4"]))
    # resource attributes
    s.append(label(ix, y + 326, "RESOURCE ATTRIBUTES", T))
    cx = ix
    for k, v in [("service.namespace", "ksquad"),
                 ("deployment.environment", "prod-euc1")]:
        c, cw = kvchip(T, cx, y + 336, k, v)
        s.append(c)
        cx += cw + 10
    # + Add ghost
    s.append(rect(cx, y + 336, 62, 26, "none", rx=13, stroke=T["border"], dash="4 3"))
    s.append(text(cx + 31, y + 353, "+ Add", 11, T["t3"], w=600, anchor="middle"))
    return "".join(s), h


def metrics_card(T, x, y, w):
    h = 64
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    ix = x + 18
    right = x + w - 18
    d, txt, bg, bd = status(T, "succeeded")
    s.append(dot(ix + 5, y + h / 2, 4.5, d))
    s.append(text(ix + 18, y + 27, "Metrics", 14, T["t1"], w=700))
    s.append(chip(ix + 90, y + 21, 96, 22, "Configured", bg, bd, txt, size=10.5))
    s.append(text(ix + 18, y + 46, "otel-collector…:4317 · gRPC · secret://otlp-headers · Δ delta",
                  11, T["t3"], mono=True))
    s.append(text(right - 12, y + h / 2 + 4, "Edit  ›", 12, T["accent2"], w=600, anchor="end"))
    return "".join(s), h


def logs_card(T, x, y, w):
    """Empty / first-run state — the opt-in default."""
    h = 104
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"], dash="6 4")]
    ix = x + 18
    right = x + w - 18
    d, txt, bg, bd = status(T, "idle")
    s.append(dot(ix + 5, y + 30, 4.5, d))
    s.append(text(ix + 18, y + 34, "Logs", 14, T["t1"], w=700))
    s.append(chip(ix + 74, y + 22, 116, 22, "Not configured", bg, bd, txt, size=10.5))
    s.append(text(ix, y + 62, "Logs stay in-cluster until you add an exporter.",
                  12, T["t3"]))
    # actions
    s.append(rect(ix, y + 74, 174, 26, "none", rx=8, stroke=T["accent"] + "88"))
    s.append(text(ix + 87, y + 91, "+ Configure exporter", 11.5, T["accent2"], w=600, anchor="middle"))
    s.append(text(ix + 190, y + 91, "or copy from Traces", 11, T["t4"]))
    return "".join(s), h


# --------------------------------------------------------------------- subnav
SUBNAV = [
    ("group", "TELEMETRY", None, False),
    ("item", "OTLP Exporter", "otlp", True),
    ("item", "Sampling defaults", "sampling", False),
    ("group", "PLATFORM", None, False),
    ("item", "General", "general", False),
    ("item", "Namespaces", "ns", False),
    ("item", "Appearance", "appear", False),
    ("group", "ACCESS & SECURITY", None, False),
    ("item", "Operators & RBAC", "rbac", False),
    ("item", "Secrets", "secret", False),
]


def si(key, cx, cy, c):
    if key == "otlp":
        return f'<g fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"><path d="M{cx-5} {cy+4} v-3 M{cx} {cy+4} v-7 M{cx+5} {cy+4} v-5"/></g>'
    if key == "sampling":
        return f'<path d="M{cx-5.5} {cy-4} h11 l-3.7 5 v4 l-3.6 1.8 v-5.8 z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>'
    if key == "general":
        return f'<g fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"><path d="M{cx-5} {cy-3} h10 M{cx-5} {cy+3} h10"/><circle cx="{cx+1.5}" cy="{cy-3}" r="1.7" fill="{c}"/><circle cx="{cx-1.5}" cy="{cy+3}" r="1.7" fill="{c}"/></g>'
    if key == "ns":
        return f'<g fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"><path d="M{cx} {cy-5} l6 3 l-6 3 l-6 -3 z"/><path d="M{cx-6} {cy+1.5} l6 3 l6 -3"/></g>'
    if key == "appear":
        return f'<g stroke="{c}" stroke-width="1.4"><circle cx="{cx}" cy="{cy}" r="5" fill="none"/><path d="M{cx} {cy-5} a5 5 0 0 1 0 10 z" fill="{c}" stroke="none"/></g>'
    if key == "rbac":
        return f'<path d="M{cx} {cy-5.5} l5 2 v3 c0 3.2 -2.6 4.8 -5 5.8 c-2.4 -1 -5 -2.6 -5 -5.8 v-3 z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>'
    if key == "secret":
        return f'<g fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"><circle cx="{cx-3}" cy="{cy-2}" r="2.7"/><path d="M{cx-1} {cy} l5 5 M{cx+2} {cy+3} l1.6 -1.6 M{cx+4} {cy+5} l1.6 -1.6"/></g>'
    return ""


def build_subnav(T, x, y, w, h):
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    cy = y + 18
    for kind, txt, key, active in SUBNAV:
        if kind == "group":
            cy += 22
            s.append(text(x + 18, cy, txt, 9.5, T["t4"], w=700, ls="0.7"))
            cy += 24
            continue
        if active:
            s.append(rect(x + 8, cy - 22, w - 16, 34, T["activebg"], rx=8, stroke=T["accent"] + "44"))
            s.append(rect(x + 8, cy - 22, 3, 34, T["accent"], rx=2))
        c_ic = T["accent2"] if active else T["t3"]
        c_tx = T["t1"] if active else T["t2"]
        s.append(si(key, x + 24, cy - 5, c_ic))
        s.append(text(x + 40, cy, txt, 12.5, c_tx, w=600 if active else 500))
        cy += 36
    # footer tag in the card
    s.append(rect(x + 14, y + h - 44, w - 28, 1, T["divider"]))
    s.append(text(x + 18, y + h - 22, "KSquad console · v1", 10, T["t4"]))
    return "".join(s)


# ----------------------------------------------------------------- yaml preview
YAML = [
    "apiVersion: ksquad.io/v1",
    "kind: OTelConfig",
    "metadata:",
    "  name: default",
    "spec:",
    "  traces:",
    "    endpoint: otel-collector…:4317",
    "    protocol: grpc",
    "    auth:",
    "      secretRef: otlp-headers   # a Secret, not a token",
    "    sampling: 0.10",
    "    resourceAttributes:",
    "      service.namespace: ksquad",
    "      deployment.environment: prod",
    "  metrics:",
    "    endpoint: otel-collector…:4317",
    "    protocol: grpc",
    "    auth: { secretRef: otlp-headers }",
    "  logs: {}   # not configured",
]
CW = 9 * 0.60  # mono advance at size 9


def yaml_line(T, x0, y, raw):
    leading = len(raw) - len(raw.lstrip(" "))
    x = x0 + leading * CW
    body = raw.lstrip(" ")
    out = []
    code = body
    comment = ""
    if "#" in body:
        i = body.index("#")
        code = body[:i]
        comment = body[i:]
    stripped = code.rstrip()
    if ": " in code and not stripped.endswith(":"):
        ci = code.index(": ")
        keypart = code[:ci + 2]
        valpart = code[ci + 2:]
        out.append(text(x, y, keypart, 9, T["t3"], mono=True))
        out.append(text(x + len(keypart) * CW, y, valpart, 9, T["accent2"], mono=True))
    else:
        out.append(text(x, y, code, 9, T["t2"], mono=True))
    if comment:
        out.append(text(x + len(code) * CW, y, comment, 9, T["t4"], mono=True))
    return "".join(out)


def yaml_card(T, x, y, w):
    n = len(YAML)
    h = 46 + n * 17 + 16
    s = [rect(x, y, w, h, T["panel"], rx=12, stroke=T["border"])]
    s.append(text(x + 18, y + 28, "OTelConfig", 12.5, T["t2"], w=700, ls="0.3"))
    s.append(text(x + w - 18, y + 28, "live preview", 10.5, T["t4"], anchor="end"))
    s.append(rect(x + 14, y + 40, w - 28, 1, T["divider"]))
    ly = y + 60
    for raw in YAML:
        s.append(yaml_line(T, x + 18, ly, raw))
        ly += 17
    return "".join(s), h


def note_card(T, x, y, w, icon_key, title, lines):
    h = 34 + 22 + len(lines) * 16 + 14
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    s.append(si(icon_key, x + 25, y + 28, T["accent2"]))
    s.append(text(x + 40, y + 32, title, 12.5, T["t1"], w=700))
    ly = y + 54
    for ln in lines:
        s.append(text(x + 18, ly, ln, 10.8, T["t3"]))
        ly += 16
    return "".join(s), h


# ------------------------------------------------------------------- content
def build_content(T):
    s = []
    # columns
    x_nav, w_nav = 260, 196
    x_form, w_form = 476, 616
    x_side, w_side = 1112, 312
    top = 84

    # sub-nav
    s.append(build_subnav(T, x_nav, top, w_nav, 776))

    # ---- form column: header ----
    s.append(text(x_form, 104, "OTLP Exporter", 17, T["t1"], w=700))
    s.append(text(x_form, 124, "Ship traces, metrics & logs to your OpenTelemetry collector.",
                  11.5, T["t3"]))
    s.append(text(x_form, 142, "Off by default — telemetry stays in-cluster until you add an exporter.",
                  10.5, T["t4"]))
    # master toggle (top-right of form column)
    tog_right = x_form + w_form
    s.append(text(tog_right - 60, 114, "Export enabled", 11.5, T["t2"], w=600, anchor="end"))
    s.append(toggle(T, tog_right - 44, 102, True))

    y = 160
    p, h = traces_card(T, x_form, y, w_form); s.append(p); y += h + 16
    p, h = metrics_card(T, x_form, y, w_form); s.append(p); y += h + 16
    p, h = logs_card(T, x_form, y, w_form); s.append(p); y += h + 20

    # footer actions
    s.append(rect(x_form, y, w_form, 1, T["divider"])); y += 22
    s.append(rect(x_form, y, 176, 38, T["accent"], rx=9))
    s.append(text(x_form + 88, y + 24, "Save configuration", 13, "#fff", w=600, anchor="middle"))
    s.append(text(x_form + 196, y + 24, "Discard changes", 12.5, T["t2"], w=600))
    s.append(text(x_form + w_form, y + 24, "Writes OTelConfig via apiserver BFF",
                  10.5, T["t4"], anchor="end"))

    # ---- side column ----
    sy = 160
    p, h = yaml_card(T, x_side, sy, w_side); s.append(p); sy += h + 16
    p, h = note_card(T, x_side, sy, w_side, "rbac", "RBAC-gated",
                     ["Authorized operators only.",
                      "Written via apiserver BFF —",
                      "no direct kube access."]); s.append(p); sy += h + 16
    p, h = note_card(T, x_side, sy, w_side, "secret", "Secrets referenced, never stored",
                     ["KSquad stores a secretRef, not the",
                      "token. Rotate secrets in Credentials."]); s.append(p); sy += h + 16

    return "".join(s)


def build(T):
    body = rect(0, 0, 1440, 900, T["bg"]) + build_rail(T) + build_header(T) + build_content(T)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" '
            f'viewBox="0 0 1440 900" {F}>{body}</svg>')


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "images")
    for suffix, T in [("", DARK), ("-light", LIGHT)]:
        path = os.path.join(out, f"12-settings{suffix}.svg")
        with open(path, "w") as f:
            f.write(build(T))
        print("wrote", path)
