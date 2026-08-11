#!/usr/bin/env python3
"""Shared scaffolding for the KSquad operator-console mocks — tokens, primitives,
left rail, and top bar. Extracted from gen-09-team-org.py so every screen renders
the SAME locked system (dark canvas #0B1220 + single azure accent #3D7DFF; reserved
status hues; v2 8-Crest rail lockup; light mode mirrors token roles).

Used by gen-08-fleet-dashboard.py and gen-10-agent-runs.py. Screen 09 keeps its own
inline copy (committed self-contained). ISI-2150 (CEO feedback 2026-08-11).
"""

# --- token maps: dark / light (mirror the 00 visual-system sheet) ------------
DARK = dict(
    bg="#0B1220", rail="#0D1728", border="#25324B", card="#131D31", panel="#0E1626",
    divider="#1A2438", t1="#E8EEF9", t2="#B6C3D8", t3="#7E8CA6", t4="#586581",
    accent="#3D7DFF", accent2="#93B7FF", activebg="#16244A", avatar="#1A2842",
    logodot="#93B7FF", track="#0E1626", rowline="#1A2438",
    g_dot="#34D399", g_txt="#34D399", g_bg="#0F2E24",
    a_dot="#FBBF24", a_txt="#FBBF24", a_bg="#33280A",
    r_dot="#FB7185", r_txt="#FB7185", r_bg="#331521",
    i_dot="#64748B", i_txt="#64748B", i_bg="#182234",
    mem="#A78BFA", mem_bg="#241B3A",
)
LIGHT = dict(
    bg="#F6F8FC", rail="#EEF2F8", border="#D4DCEA", card="#FFFFFF", panel="#F1F5FA",
    divider="#ECF1F8", t1="#0B1220", t2="#33415C", t3="#64748B", t4="#6C7688",
    accent="#3D7DFF", accent2="#2563EB", activebg="#E5EDFF", avatar="#ECF1F8",
    logodot="#2563EB", track="#E7ECF4", rowline="#ECF1F8",
    g_dot="#059669", g_txt="#059669", g_bg="#E7F6EF",
    a_dot="#D97706", a_txt="#B45309", a_bg="#FCF3E2",
    r_dot="#E11D48", r_txt="#E11D48", r_bg="#FCE9EC",
    i_dot="#64748B", i_txt="#475569", i_bg="#EEF1F6",
    mem="#7C3AED", mem_bg="#F1EBFD",
)
# canonical base hues for chip borders (theme-invariant, +alpha)
BASE = dict(running="#34D399", paused="#FBBF24", blocked="#FB7185",
            idle="#64748B", failed="#FB7185", succeeded="#34D399")


def status(T, s):
    """Return (dot, txt, bg, border) for a status key."""
    m = {"running":   (T["g_dot"], T["g_txt"], T["g_bg"]),
         "succeeded": (T["g_dot"], T["g_txt"], T["g_bg"]),
         "paused":    (T["a_dot"], T["a_txt"], T["a_bg"]),
         "blocked":   (T["r_dot"], T["r_txt"], T["r_bg"]),
         "failed":    (T["r_dot"], T["r_txt"], T["r_bg"]),
         "idle":      (T["i_dot"], T["i_txt"], T["i_bg"])}
    dot_c, txt, bg = m[s]
    return dot_c, txt, bg, BASE[s] + "55"


F = 'font-family="DejaVu Sans"'
FM = 'font-family="DejaVu Sans Mono"'


def esc(s):
    return s.replace("&", "&amp;")


def text(x, y, s, size, fill, w=400, anchor="start", mono=False, ls=None):
    ff = FM if mono else F
    lsp = f' letter-spacing="{ls}"' if ls is not None else ""
    return (f'<text x="{x}" y="{y}" {ff} font-size="{size}" fill="{fill}" '
            f'font-weight="{w}" text-anchor="{anchor}"{lsp}>{esc(s)}</text>')


def rect(x, y, w, h, fill, rx=0, stroke="none", sw=1):
    r = f' rx="{rx}" ry="{rx}"' if rx else ' rx="0" ry="0"'
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}"{r} '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def dot(cx, cy, rr, fill, pulse=False):
    s = f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="{fill}"/>'
    if pulse:
        s += (f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="none" stroke="{fill}" '
              f'stroke-width="1.4" opacity="0.5"><animate attributeName="r" '
              f'values="{rr};{rr+4.6};{rr}" dur="1.8s" repeatCount="indefinite"/>'
              f'<animate attributeName="opacity" values="0.55;0;0.55" dur="1.8s" '
              f'repeatCount="indefinite"/></circle>')
    return s


def chip(x, y, w, h, label, bg, border, txt, size=11.5, mono=False, ls=None):
    pad = 11
    return (rect(x, y, w, h, bg, rx=h/2 if h <= 24 else 6, stroke=border) +
            text(x + pad, y + h/2 + 4, label, size, txt, w=600, mono=mono, ls=ls))


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

NAV = [  # (label, text_y, icon_fn, key)
    ("Dashboard", 110, ic_dashboard, "dashboard"),
    ("Overview", 156, ic_overview, "overview"),
    ("Runs", 202, ic_runs, "runs"),
    ("Builds", 248, ic_builds, "builds"),
    ("Discussion", 294, ic_discussion, "discussion"),
    ("Projects", 340, ic_projects, "projects"),
    ("Agents", 386, ic_agents, "agents"),
    ("Credentials", 432, ic_creds, "credentials"),
]


def build_rail(T, active):
    s = []
    s.append(rect(0, 0, 236, 900, T["rail"]))
    s.append(rect(235, 0, 1, 900, T["border"]))
    # v2 8-Crest logo mark
    s.append(f'<g transform="translate(30,34) scale(0.33735) translate(-50,-50)">'
             f'<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
             f'<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
             f'<rect x="45" y="25.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
             f'<rect x="45" y="64.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
             f'<rect x="42.5" y="42.5" width="15" height="15" rx="4.2" fill="{T["logodot"]}"/></g>')
    s.append(text(52, 32, "KSquad", 17, T["t1"], w=700, ls="0.2"))
    s.append(text(52, 46, "operator console", 10, T["t4"], ls="0.4"))
    for label, ty, icon, key in NAV:
        act = key == active
        if act:
            s.append(rect(10, ty - 24, 216, 38, T["activebg"], rx=9, stroke=T["accent"] + "44"))
            s.append(rect(10, ty - 24, 3, 38, T["accent"], rx=2))
        c = T["accent2"] if act else T["t3"]
        s.append(icon(c))
        s.append(text(52, ty, label, 13.5, T["t1"] if act else T["t2"], w=600 if act else 500))
    s.append(rect(16, 468, 204, 40, T["accent"], rx=9))
    s.append(text(112, 493, "+  Compose", 13.5, "#fff", w=600, anchor="middle"))
    s.append(rect(16, 826, 204, 54, T["panel"], rx=9, stroke=T["border"]))
    s.append(dot(34, 853, 3.5, T["g_dot"]))
    s.append(text(48, 849, "prod-euc1", 12.5, T["t2"], w=600, mono=True))
    s.append(text(48, 866, "context · connected", 10.5, T["t4"]))
    return "".join(s)


def build_header(T, title, subtitle):
    s = []
    s.append(rect(236, 0, 1204, 60, T["bg"]))
    s.append(rect(236, 59, 1204, 1, T["border"]))
    s.append(text(260, 30, title, 17, T["t1"], w=700))
    s.append(text(260, 47, subtitle, 11.5, T["t3"]))
    # avatar
    s.append(f'<circle cx="1400" cy="30" r="15" fill="{T["avatar"]}" stroke="{T["border"]}"/>')
    s.append(text(1400, 34, "PN", 11.5, T["accent2"], w=700, anchor="middle"))
    # ns pill
    s.append(rect(1283.6, 15, 84.4, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(dot(1297.6, 30, 3, T["accent"]))
    s.append(text(1307.6, 34, "ns: all", 12, T["t2"], mono=True))
    # search pill
    s.append(rect(1071.6, 15, 200, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(f'<circle cx="1086.6" cy="30" r="4.5" fill="none" stroke="{T["t4"]}" stroke-width="1.5"/>')
    s.append(f'<path d="M1090.1 33.5 l3 3" stroke="{T["t4"]}" stroke-width="1.5" stroke-linecap="round"/>')
    s.append(text(1101.6, 34, "Search squads, runs, artifacts…", 12, T["t4"]))
    return "".join(s)


def svg_open(T):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" '
            f'viewBox="0 0 1440 900" {F}>' + rect(0, 0, 1440, 900, T["bg"]))


def write_pair(basename, build_fn):
    """build_fn(T) -> inner svg string. Writes <basename>.svg and <basename>-light.svg."""
    import os
    out = os.path.join(os.path.dirname(__file__), "images")
    for suffix, T in [("", DARK), ("-light", LIGHT)]:
        path = os.path.join(out, f"{basename}{suffix}.svg")
        with open(path, "w") as f:
            f.write(svg_open(T) + build_fn(T) + "</svg>")
        print("wrote", path)
