#!/usr/bin/env python3
"""Generate screen 09 — Team organization diagram (dark + light), KSquad operator console.

Team -> Agent -> Role lineage tree with live status (idle/running/blocked/paused),
runtime-type badges, role badges, click-through agent-detail panel.
Data source: Team/Agent/Role CRDs (read-only); live status via SSE.

Light variant mirrors the SAME token roles as the rest of the set (no new hues).
Renders 1440x900 SVG; PNGs are the audited 1.5x (2160x1350) via cairosvg.
ISI-2150 (CEO feedback 2026-08-11) — 10th screen alongside the existing 9.
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
# canonical base hues for chip borders (theme-invariant, +alpha)
BASE = dict(running="#34D399", paused="#FBBF24", blocked="#FB7185", idle="#64748B")

def status(T, s):
    """Return (dot, txt, bg, border) for a status key."""
    m = {"running": (T["g_dot"], T["g_txt"], T["g_bg"]),
         "paused":  (T["a_dot"], T["a_txt"], T["a_bg"]),
         "blocked": (T["r_dot"], T["r_txt"], T["r_bg"]),
         "idle":    (T["i_dot"], T["i_txt"], T["i_bg"])}
    dot, txt, bg = m[s]
    return dot, txt, bg, BASE[s] + "55"

F  = 'font-family="DejaVu Sans"'
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
ACTIVE = "agents"


def build_rail(T):
    s = []
    # rail bg + divider
    s.append(rect(0, 0, 236, 900, T["rail"]))
    s.append(rect(235, 0, 1, 900, T["border"]))
    # logo mark
    s.append(f'<g transform="translate(30,34) scale(0.33735) translate(-50,-50)">'
             f'<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
             f'<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
             f'<rect x="45" y="25.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
             f'<rect x="45" y="64.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
             f'<rect x="42.5" y="42.5" width="15" height="15" rx="4.2" fill="{T["logodot"]}"/></g>')
    s.append(text(52, 32, "KSquad", 17, T["t1"], w=700, ls="0.2"))
    s.append(text(52, 46, "operator console", 10, T["t4"], ls="0.4"))
    # nav
    for label, ty, icon, key in NAV:
        act = key == ACTIVE
        if act:
            s.append(rect(10, ty - 24, 216, 38, T["activebg"], rx=9, stroke=T["accent"] + "44"))
            s.append(rect(10, ty - 24, 3, 38, T["accent"], rx=2))
        c = T["accent2"] if act else T["t3"]
        s.append(icon(c))
        s.append(text(52, ty, label, 13.5, T["t1"] if act else T["t2"], w=600 if act else 500))
    # compose button
    s.append(rect(16, 468, 204, 40, T["accent"], rx=9))
    s.append(text(112, 493, "+  Compose", 13.5, "#fff", w=600, anchor="middle"))
    # context footer
    s.append(rect(16, 826, 204, 54, T["panel"], rx=9, stroke=T["border"]))
    s.append(dot(34, 853, 3.5, T["g_dot"]))
    s.append(text(48, 849, "prod-euc1", 12.5, T["t2"], w=600, mono=True))
    s.append(text(48, 866, "context · connected", 10.5, T["t4"]))
    return "".join(s)


def build_header(T):
    s = []
    s.append(rect(236, 0, 1204, 60, T["bg"]))
    s.append(rect(236, 59, 1204, 1, T["border"]))
    s.append(text(260, 30, "Team organization", 17, T["t1"], w=700))
    s.append(text(260, 47, "Team → Agent → Role hierarchy · live status via SSE", 11.5, T["t3"]))
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


def legend_item(x, y, s_key, T):
    d, txt, _, _ = status(T, s_key)
    label = s_key.capitalize()
    return dot(x, y, 3.6, d) + text(x + 12, y + 4, label, 11, T["t2"], w=500)


def build_content(T):
    s = []
    # ---- top legend / meta row (y ~ 100) ----
    s.append(dot(266, 100, 4, T["g_dot"], pulse=True))
    s.append(text(280, 104, "LIVE", 10.5, T["g_txt"], w=700, ls="0.6"))
    s.append(text(316, 104, "SSE", 10.5, T["t3"], w=600, mono=True))
    lx = 372
    for sk in ("running", "paused", "blocked", "idle"):
        s.append(legend_item(lx, 100, sk, T))
        lx += 96
    s.append(text(1416, 104, "Source: Team · Agent · Role CRDs  (read-only)", 11, T["t4"], anchor="end"))

    # ---- column headers ----
    s.append(text(260, 140, "TEAMS", 10, T["t4"], w=700, ls="0.8"))
    s.append(text(568, 140, "AGENTS", 10, T["t4"], w=700, ls="0.8"))
    s.append(text(876, 140, "ROLES", 10, T["t4"], w=700, ls="0.8"))
    s.append(text(1108, 140, "AGENT DETAIL", 10, T["t4"], w=700, ls="0.8"))

    # ---------- TEAMS column (x=260 w=264) ----------
    teams = [  # name, ns, agents, status, selected
        ("payments-review", "team-payments", 3, "running", True),
        ("checkout-hardening", "team-checkout", 2, "paused", False),
        ("docs-sync", "developer-portal", 2, "idle", False),
    ]
    ty = 156
    for name, ns, n, st, sel in teams:
        h = 76
        d, txt, bg, bd = status(T, st)
        if sel:
            s.append(rect(260, ty, 264, h, T["activebg"], rx=12, stroke=T["accent"]))
            s.append(rect(260, ty, 3, h, T["accent"], rx=2))
        else:
            s.append(rect(260, ty, 264, h, T["card"], rx=12, stroke=T["border"]))
        s.append(dot(282, ty + 24, 4, d, pulse=(st == "running")))
        s.append(text(296, ty + 28, name, 13.5, T["t1"], w=700))
        s.append(chip(280, ty + 40, 118, 20, ns, T["panel"], T["border"], T["accent2"], size=11, mono=True))
        s.append(text(408, ty + 54, f"{n} agents", 11, T["t3"], w=500))
        s.append(text(508, ty + 28, st.capitalize(), 11, txt, w=600, anchor="end"))
        ty += 92

    # ---------- connectors: selected Team -> Agents ----------
    ac = T["accent"]
    s.append(f'<g stroke="{ac}" stroke-width="1.5" fill="none" opacity="0.55" stroke-linecap="round">')
    s.append('<path d="M524 194 H546"/><path d="M546 194 V418"/>')
    s.append('<path d="M546 202 H568"/><path d="M546 310 H568"/><path d="M546 418 H568"/>')
    s.append('</g>')

    # ---------- AGENTS column (x=568 w=264) ----------
    agents = [  # name, runtime, status, roles, selected, run
        ("Reviewer", "Claude Code", "running", ["Reviewer", "Approver"], True),
        ("Fixer", "OpenCode", "running", ["Fixer"], False),
        ("Tester", "Ollama adapter", "idle", ["Tester"], False),
    ]
    ay = 156
    for name, rt, st, roles, sel in agents:
        h = 92
        d, txt, bg, bd = status(T, st)
        if sel:
            s.append(rect(568, ay, 264, h, T["activebg"], rx=12, stroke=T["accent"]))
            s.append(rect(568, ay, 3, h, T["accent"], rx=2))
        else:
            s.append(rect(568, ay, 264, h, T["card"], rx=12, stroke=T["border"]))
        # avatar
        s.append(f'<circle cx="592" cy="{ay+26}" r="13" fill="{T["accent"]}22" stroke="{T["accent"]}66"/>')
        s.append(text(592, ay + 30, name[0], 12, T["accent2"], w=700, anchor="middle"))
        s.append(text(614, ay + 24, name, 13.5, T["t1"], w=700))
        # runtime badge
        rtw = 8 + len(rt) * 7.4
        s.append(chip(614, ay + 34, rtw, 20, rt, T["panel"], T["border"], T["t2"], size=11))
        # status dot+label (top-right)
        s.append(dot(812, ay + 20, 3.6, d, pulse=(st == "running")))
        s.append(text(806, ay + 24, st.capitalize(), 11, txt, w=600, anchor="end"))
        # role chips row
        rx = 614
        for role in roles:
            rw = 12 + len(role) * 6.6
            s.append(chip(rx, ay + 62, rw, 20, role, T["panel"], T["border"], T["t3"], size=11))
            rx += rw + 8
        ay += 108

    # ---------- connectors: selected Agent -> Roles ----------
    s.append(f'<g stroke="{ac}" stroke-width="1.5" fill="none" opacity="0.55" stroke-linecap="round">')
    s.append('<path d="M832 202 H854"/><path d="M854 192 V280"/>')
    s.append('<path d="M854 192 H876"/><path d="M854 280 H876"/>')
    s.append('</g>')

    # ---------- ROLES column (x=876 w=196) ----------
    roles = [  # name, desc, primary
        ("Reviewer", "reviews diffs · files findings", True),
        ("Approver", "may release work items", False),
    ]
    ry = 156
    for name, desc, primary in roles:
        h = 72
        s.append(rect(876, ry, 196, h, T["card"], rx=12, stroke=T["border"]))
        s.append(f'<circle cx="894" cy="{ry+24}" r="3" fill="{T["accent2"]}"/>')
        s.append(text(906, ry + 28, name, 13, T["t1"], w=700))
        if primary:
            s.append(chip(876 + 196 - 66, ry + 13, 54, 18, "PRIMARY", T["accent"] + "1F", T["accent"] + "44", T["accent2"], size=8.5, ls="0.4"))
        s.append(text(894, ry + 46, desc, 10.5, T["t3"], w=400))
        s.append(text(894, ry + 62, "CRD · read-only", 10, T["t4"], w=600, mono=True))
        ry += 88

    # empty-state hint under roles
    s.append(text(894, ry + 6, "roles bind runtime + skills", 10, T["t4"], w=400))
    s.append(text(894, ry + 22, "+ credential ref (compose)", 10, T["t4"], w=400))

    # ---------- AGENT DETAIL panel (x=1108 w=308) ----------
    px, pw = 1108, 308
    s.append(rect(px, 156, pw, 668, T["card"], rx=12, stroke=T["border"]))
    # header
    s.append(f'<circle cx="{px+34}" cy="196" r="20" fill="{T["accent"]}22" stroke="{T["accent"]}66"/>')
    s.append(text(px + 34, 202, "R", 17, T["accent2"], w=700, anchor="middle"))
    s.append(text(px + 66, 192, "Reviewer", 16, T["t1"], w=700))
    s.append(text(px + 66, 210, "agent · payments-review", 11, T["t3"]))
    # status row
    d, txt, bg, bd = status(T, "running")
    s.append(rect(px + 20, 234, pw - 40, 40, bg, rx=9, stroke=bd))
    s.append(dot(px + 40, 254, 4, d, pulse=True))
    s.append(text(px + 56, 250, "Running", 12.5, txt, w=700))
    s.append(text(px + 56, 265, "streaming · status via SSE", 10, T["t3"]))
    s.append(text(px + pw - 20, 258, "Run #142 · 3m", 11, T["accent2"], w=600, anchor="end"))
    # meta rows
    s.append(rect(px + 20, 292, pw - 40, 1, T["divider"]))
    meta = [("Runtime", "Claude Code · sandboxed"),
            ("Namespace", "team-payments"),
            ("Bound roles", "Reviewer · Approver"),
            ("Skills", "diff-review · lint · report"),
            ("Credential", "gh-app · payments (ref)")]
    my = 322
    for k, v in meta:
        s.append(text(px + 20, my, k, 11, T["t4"], w=600))
        s.append(text(px + pw - 20, my, v, 11.5, T["t2"], w=500, anchor="end"))
        my += 30
    # source note
    s.append(rect(px + 20, my - 6, pw - 40, 1, T["divider"]))
    s.append(text(px + 20, my + 22, "SOURCE", 9.5, T["t4"], w=700, ls="0.6"))
    for line in ["Team / Agent / Role CRDs (read-only)",
                 "live status via SSE watch stream"]:
        my += 22
        s.append(dot(px + 24, my + 18, 2.6, T["accent2"]))
        s.append(text(px + 36, my + 22, line, 10.5, T["t3"], w=400))
    # buttons
    by = 764
    s.append(rect(px + 20, by, pw - 40, 40, T["accent"], rx=9))
    s.append(text(px + pw / 2, by + 25, "Open agent detail  →", 13, "#fff", w=600, anchor="middle"))

    return "".join(s)


def build(T):
    body = rect(0, 0, 1440, 900, T["bg"]) + build_rail(T) + build_header(T) + build_content(T)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" '
            f'viewBox="0 0 1440 900" {F}>{body}</svg>')


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "images")
    for suffix, T in [("", DARK), ("-light", LIGHT)]:
        path = os.path.join(out, f"09-team-organization{suffix}.svg")
        with open(path, "w") as f:
            f.write(build(T))
        print("wrote", path)
