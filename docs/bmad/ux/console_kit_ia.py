#!/usr/bin/env python3
"""Project-rooted navigation IA kit for the KSquad operator console (ISI-2291).

Realizes the CEO 2026-08-12 navigation directive (Stories 8.13 nav-shell + 8.14
Project→Tickets) as a shared, hierarchical nav rail + breadcrumb header. Same locked
system as the flat-rail kit (console_kit.py): dark canvas #0B1220 + single azure
accent #3D7DFF; reserved status hues; v2 8-Crest rail lockup; light mode mirrors
token roles. Screens 13 (nav-IA map) and 14 (Project Tickets) import this.

The rail is NO LONGER a flat screen list. It groups:
  GLOBAL   → Dashboard (fleet) · Overview (squad) · Agents (filterable)
  PROJECT  → [context selector] → Build · Tickets · Runs · Discussion  (scoped)
  SETTINGS → Configuration · Credentials
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
    mem="#A78BFA", mem_bg="#241B3A",
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
    mem="#7C3AED", mem_bg="#F1EBFD",
)
BASE = dict(running="#34D399", paused="#FBBF24", blocked="#FB7185", idle="#64748B",
            done="#34D399", open="#64748B", claimed="#3D7DFF")


def status(T, s):
    m = {"running":  (T["g_dot"], T["g_txt"], T["g_bg"]),
         "done":     (T["g_dot"], T["g_txt"], T["g_bg"]),
         "paused":   (T["a_dot"], T["a_txt"], T["a_bg"]),
         "blocked":  (T["r_dot"], T["r_txt"], T["r_bg"]),
         "open":     (T["i_dot"], T["i_txt"], T["i_bg"]),
         "idle":     (T["i_dot"], T["i_txt"], T["i_bg"]),
         "claimed":  (T["accent2"], T["accent2"], T["activebg"])}
    dot_, txt, bg = m[s]
    return dot_, txt, bg, BASE.get(s, "#64748B") + "55"


F = 'font-family="DejaVu Sans"'
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


def line(x1, y1, x2, y2, c, sw=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="{sw}"{d}/>'


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


# ---- centered nav glyphs (~18px), color-parameterised -----------------------
def _stk(c, sw=1.6):
    return f'fill="none" stroke="{c}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'


def ic_dashboard(cx, cy, c):
    return (f'<g {_stk(c)}>'
            f'<line x1="{cx-6}" y1="{cy+5}" x2="{cx-6}" y2="{cy}"/>'
            f'<line x1="{cx}" y1="{cy+5}" x2="{cx}" y2="{cy-4}"/>'
            f'<line x1="{cx+6}" y1="{cy+5}" x2="{cx+6}" y2="{cy-1}"/>'
            f'<line x1="{cx-8}" y1="{cy+7}" x2="{cx+8}" y2="{cy+7}"/></g>')


def ic_overview(cx, cy, c):
    r = 3.2
    return (f'<g {_stk(c)}>'
            f'<rect x="{cx-7}" y="{cy-7}" width="{r*2}" height="{r*2}" rx="1.3"/>'
            f'<rect x="{cx+0.6}" y="{cy-7}" width="{r*2}" height="{r*2}" rx="1.3"/>'
            f'<rect x="{cx-7}" y="{cy+0.6}" width="{r*2}" height="{r*2}" rx="1.3"/>'
            f'<rect x="{cx+0.6}" y="{cy+0.6}" width="{r*2}" height="{r*2}" rx="1.3"/></g>')


def ic_agents(cx, cy, c):
    return (f'<g {_stk(c,1.5)}>'
            f'<circle cx="{cx}" cy="{cy-4.5}" r="2.3"/>'
            f'<circle cx="{cx-6}" cy="{cy+4}" r="2"/>'
            f'<circle cx="{cx+6}" cy="{cy+4}" r="2"/>'
            f'<line x1="{cx}" y1="{cy-2}" x2="{cx-5}" y2="{cy+2}"/>'
            f'<line x1="{cx}" y1="{cy-2}" x2="{cx+5}" y2="{cy+2}"/></g>')


def ic_project(cx, cy, c):
    return (f'<g {_stk(c)}>'
            f'<path d="M{cx-8} {cy-5} h5 l2 2.5 h8 v9.5 a1.4 1.4 0 0 1 -1.4 1.4 '
            f'h-12.2 a1.4 1.4 0 0 1 -1.4 -1.4 z"/></g>')


def ic_build(cx, cy, c):
    return (f'<g {_stk(c)}>'
            f'<path d="M{cx} {cy-7} l7 4 v6 l-7 4 l-7 -4 v-6 z"/>'
            f'<path d="M{cx-7} {cy-3} l7 4 l7 -4"/>'
            f'<path d="M{cx} {cy+1} v6.5"/></g>')


def ic_tickets(cx, cy, c):
    return (f'<g {_stk(c,1.5)}>'
            f'<rect x="{cx-7}" y="{cy-7}" width="14" height="14" rx="2.5"/>'
            f'<path d="M{cx-4} {cy-3.2} l1.6 1.6 l3 -3.4"/>'
            f'<line x1="{cx-4}" y1="{cy+3}" x2="{cx+4.5}" y2="{cy+3}"/></g>')


def ic_runs(cx, cy, c):
    return (f'<g {_stk(c)}>'
            f'<path d="M{cx-8} {cy} h3 l2 -5 l3 10 l2 -5 h3"/></g>')


def ic_discussion(cx, cy, c):
    return (f'<g {_stk(c,1.5)}>'
            f'<path d="M{cx-7} {cy-6} h14 a1.5 1.5 0 0 1 1.5 1.5 v6 a1.5 1.5 0 0 1 -1.5 1.5 '
            f'h-8 l-4 3.2 v-3.2 h-2 a1.5 1.5 0 0 1 -1.5 -1.5 v-6 a1.5 1.5 0 0 1 1.5 -1.5 z"/></g>')


def ic_config(cx, cy, c):
    spokes = ""
    import math
    for i in range(6):
        a = i * math.pi / 3
        x1 = cx + 4.2 * math.cos(a); y1 = cy + 4.2 * math.sin(a)
        x2 = cx + 7.2 * math.cos(a); y2 = cy + 7.2 * math.sin(a)
        spokes += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>'
    return f'<g {_stk(c,1.5)}><circle cx="{cx}" cy="{cy}" r="3.4"/>{spokes}</g>'


def ic_creds(cx, cy, c):
    return (f'<g {_stk(c,1.5)}>'
            f'<circle cx="{cx-3.5}" cy="{cy-2}" r="3.2"/>'
            f'<path d="M{cx-1.2} {cy+0.3} l6 6 M{cx+3} {cy+4.5} l1.6 -1.6 M{cx+4.8} {cy+6.3} l1.6 -1.6"/></g>')


# ---- rail model -------------------------------------------------------------
# Each entry: (kind, key, label, icon_or_None)
#   kind: 'section' | 'item' | 'selector' | 'subitem'
RAIL = [
    ("section", None, "GLOBAL", None),
    ("item", "dashboard", "Dashboard", ic_dashboard),
    ("item", "overview", "Overview", ic_overview),
    ("item", "agents", "Agents", ic_agents),
    ("section", None, "PROJECT", None),
    ("selector", "project", "ksquad-console", ic_project),
    ("subitem", "build", "Build", ic_build),
    ("subitem", "tickets", "Tickets", ic_tickets),
    ("subitem", "runs", "Runs", ic_runs),
    ("subitem", "discussion", "Discussion", ic_discussion),
    ("section", None, "SETTINGS", None),
    ("item", "configuration", "Configuration", ic_config),
    ("item", "credentials", "Credentials", ic_creds),
]

RAIL_W = 236


def build_logo(T):
    return (f'<g transform="translate(30,34) scale(0.33735) translate(-50,-50)">'
            f'<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
            f'<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
            f'<rect x="45" y="25.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
            f'<rect x="45" y="64.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
            f'<rect x="42.5" y="42.5" width="15" height="15" rx="4.2" fill="{T["logodot"]}"/></g>'
            + text(52, 32, "KSquad", 17, T["t1"], w=700, ls="0.2")
            + text(52, 46, "operator console", 10, T["t4"], ls="0.4"))


def build_rail_ia(T, active, project_open=True):
    """Hierarchical Project-rooted rail. `active` = key of current node."""
    s = [rect(0, 0, RAIL_W, 900, T["rail"]), rect(RAIL_W - 1, 0, 1, 900, T["border"])]
    s.append(build_logo(T))
    y = 78
    sub_ys = []          # collect subitem centers to draw the connector spine
    selector_cy = None
    for kind, key, label, icon in RAIL:
        act = key == active
        if kind == "section":
            s.append(text(20, y + 4, label, 10, T["t4"], w=700, ls="1.6"))
            y += 22
        elif kind == "item":
            cy = y + 15
            if act:
                s.append(rect(10, y, 216, 30, T["activebg"], rx=9, stroke=T["accent"] + "44"))
                s.append(rect(10, y, 3, 30, T["accent"], rx=2))
            c = T["accent2"] if act else T["t3"]
            s.append(icon(30, cy, c))
            s.append(text(52, cy + 4.5, label, 13.5, T["t1"] if act else T["t2"], w=600 if act else 500))
            if key == "agents":
                s.append(chip(150, y + 5, 66, 20, "filter ▾", T["panel"], T["border"], T["t3"], size=9.5))
            y += 36
        elif kind == "selector":
            # project context selector — a dropdown control, azure-tinted (root context)
            selector_cy = y + 20
            s.append(rect(12, y, 212, 40, T["activebg"], rx=10, stroke=T["accent"] + "66"))
            s.append(rect(12, y, 3, 40, T["accent"], rx=2))
            s.append(icon(32, y + 20, T["accent2"]))
            s.append(text(50, y + 15, label, 13, T["t1"], w=700))
            s.append(text(50, y + 30, "active project · switch ▾", 9.5, T["t4"]))
            # chevron
            s.append(f'<path d="M208 {y+16} l4 4 l4 -4" {_stk(T["t3"],1.6)}/>')
            y += 48
        elif kind == "subitem":
            cy = y + 14
            sub_ys.append(cy)
            if act:
                s.append(rect(28, y, 198, 28, T["activebg"], rx=8, stroke=T["accent"] + "44"))
                s.append(rect(28, y, 3, 28, T["accent"], rx=2))
            c = T["accent2"] if act else T["t3"]
            s.append(icon(54, cy, c))
            s.append(text(74, cy + 4.5, label, 12.5, T["t1"] if act else T["t2"], w=600 if act else 500))
            y += 32
    # connector spine: from selector down through subitems (tree affordance)
    if selector_cy is not None and sub_ys:
        spine_x = 40
        s.insert(2, line(spine_x, selector_cy + 14, spine_x, sub_ys[-1], T["border"], sw=1.4))
        for scy in sub_ys:
            s.insert(3, line(spine_x, scy, 48, scy, T["border"], sw=1.4))
    # compose + footer
    s.append(rect(16, 820, 204, 40, T["accent"], rx=9))
    s.append(text(112, 845, "+  Compose", 13.5, "#fff", w=600, anchor="middle"))
    s.append(rect(16, 868, 204, 24, T["panel"], rx=8, stroke=T["border"]))
    s.append(dot(32, 880, 3, T["g_dot"]))
    s.append(text(44, 884, "prod-euc1 · connected", 10.5, T["t3"], mono=True))
    return "".join(s)


def crumb(T, x, y, project, section):
    """Breadcrumb: [📁 project ▾] › section — returns (svg, end_x)."""
    s = []
    pw = 26 + len(project) * 7.4 + 18
    s.append(rect(x, y - 15, pw, 28, T["panel"], rx=8, stroke=T["border"]))
    s.append(ic_project(x + 15, y - 1, T["accent2"]))
    s.append(text(x + 27, y + 3.5, project, 12.5, T["t1"], w=600))
    s.append(f'<path d="M{x+pw-14} {y-2} l4 4 l4 -4" {_stk(T["t3"],1.5)}/>')
    cx = x + pw + 12
    s.append(text(cx, y + 4, "›", 15, T["t4"], w=600))
    cx += 16
    s.append(text(cx, y + 4, section, 14, T["t1"], w=700))
    return "".join(s), cx + len(section) * 8.4


def build_header(T, project, section, subtitle):
    s = [rect(RAIL_W, 0, 1204, 60, T["bg"]), rect(RAIL_W, 59, 1204, 1, T["border"])]
    cr, _ = crumb(T, 260, 26, project, section)
    s.append(cr)
    s.append(text(260, 48, subtitle, 11, T["t3"]))
    s.append(f'<circle cx="1400" cy="30" r="15" fill="{T["avatar"]}" stroke="{T["border"]}"/>')
    s.append(text(1400, 34, "PN", 11.5, T["accent2"], w=700, anchor="middle"))
    s.append(rect(1283.6, 15, 84.4, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(dot(1297.6, 30, 3, T["accent"]))
    s.append(text(1307.6, 34, "ns: all", 12, T["t2"], mono=True))
    s.append(rect(1071.6, 15, 200, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(f'<circle cx="1086.6" cy="30" r="4.5" fill="none" stroke="{T["t4"]}" stroke-width="1.5"/>')
    s.append(f'<path d="M1090.1 33.5 l3 3" stroke="{T["t4"]}" stroke-width="1.5" stroke-linecap="round"/>')
    s.append(text(1101.6, 34, "Search tickets, runs, artifacts…", 12, T["t4"]))
    return "".join(s)


def build_subnav(T, x, y, w, active, tabs=None):
    """Project sub-navigation tab strip: Build · Tickets · Runs · Discussion."""
    tabs = tabs or [("build", "Build"), ("tickets", "Tickets"),
                    ("runs", "Runs"), ("discussion", "Discussion")]
    s = [rect(x, y + 30, w, 1, T["border"])]
    cx = x + 4
    for key, label in tabs:
        act = key == active
        tw = len(label) * 8 + 20
        c = T["t1"] if act else T["t3"]
        s.append(text(cx + tw / 2, y + 20, label, 13, c, w=700 if act else 500, anchor="middle"))
        if act:
            s.append(rect(cx + 6, y + 29, tw - 12, 2.5, T["accent"], rx=1.5))
        cx += tw + 8
    return "".join(s)


def svg_open(T):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" '
            f'viewBox="0 0 1440 900" {F}>' + rect(0, 0, 1440, 900, T["bg"]))


def write_pair(basename, build_fn):
    import os
    out = os.path.join(os.path.dirname(__file__), "images")
    for suffix, T in [("", DARK), ("-light", LIGHT)]:
        path = os.path.join(out, f"{basename}{suffix}.svg")
        with open(path, "w") as f:
            f.write(svg_open(T) + build_fn(T) + "</svg>")
        print("wrote", path)
