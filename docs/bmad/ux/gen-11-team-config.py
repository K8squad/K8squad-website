#!/usr/bin/env python3
"""Generate screen 11 — Team configuration (dark + light), KSquad operator console.

"Your actual organization" — a read-only roster of the live company: teams → agents,
each agent's role + runtime (Claude Code / OpenCode / Ollama / OpenClaw / Process),
grouped by function, with the 1:1 OpenCode backup failover noted. Data mirrors the
live Agent registry (30 agents: 15 active + 15 backup) at 2026-08-12.

CEO ask (Henrik, ISI-2153 review 2026-08-12): "a team configuration screen, where you
can see your actual organization." Complements the 09 org-hierarchy diagram with the
concrete real-company roster. Read-only view (compose/edit lives in the Compose screen).

Light variant mirrors the SAME token roles as the rest of the set (no new hues).
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
BASE = dict(running="#34D399", paused="#FBBF24", blocked="#FB7185", idle="#64748B")


def status(T, s):
    m = {"running": (T["g_dot"], T["g_txt"], T["g_bg"]),
         "paused":  (T["a_dot"], T["a_txt"], T["a_bg"]),
         "blocked": (T["r_dot"], T["r_txt"], T["r_bg"]),
         "idle":    (T["i_dot"], T["i_txt"], T["i_bg"])}
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


def rect(x, y, w, h, fill, rx=0, stroke="none", sw=1):
    r = f' rx="{rx}" ry="{rx}"' if rx else ' rx="0" ry="0"'
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}"{r} '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


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
ACTIVE = "agents"


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
        act = key == ACTIVE
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


def build_header(T):
    s = []
    s.append(rect(236, 0, 1204, 60, T["bg"]))
    s.append(rect(236, 59, 1204, 1, T["border"]))
    s.append(text(260, 30, "Team configuration", 17, T["t1"], w=700))
    s.append(text(260, 47, "Your organization · read-only roster (Agent · Role · Runtime)", 11.5, T["t3"]))
    s.append(f'<circle cx="1400" cy="30" r="15" fill="{T["avatar"]}" stroke="{T["border"]}"/>')
    s.append(text(1400, 34, "PN", 11.5, T["accent2"], w=700, anchor="middle"))
    s.append(rect(1283.6, 15, 84.4, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(dot(1297.6, 30, 3, T["accent"]))
    s.append(text(1307.6, 34, "ns: all", 12, T["t2"], mono=True))
    s.append(rect(1071.6, 15, 200, 30, T["panel"], rx=8, stroke=T["border"]))
    s.append(f'<circle cx="1086.6" cy="30" r="4.5" fill="none" stroke="{T["t4"]}" stroke-width="1.5"/>')
    s.append(f'<path d="M1090.1 33.5 l3 3" stroke="{T["t4"]}" stroke-width="1.5" stroke-linecap="round"/>')
    s.append(text(1101.6, 34, "Search agents, teams…", 12, T["t4"]))
    return "".join(s)


# ------------------------------ ORG DATA (live roster @ 2026-08-12) -----------
# runtime label -> is "primary" azure runtime (Claude Code) gets the accent chip
TEAMS = [
    ("Leadership", [
        ("BigBoss", "CEO · direction & gates", "Claude Code", "running"),
    ]),
    ("Engineering", [
        ("Architect", "Solution design", "Claude Code", "running"),
        ("Claude Code", "Feature engineer", "Claude Code", "idle"),
        ("Code Reviewer", "Adversarial review", "Claude Code", "idle"),
        ("Testing Architect", "E2E & QA automation", "Claude Code", "idle"),
        ("DevOps Engineer", "CI/CD & deploy", "Claude Code", "idle"),
        ("Observability Agent", "OTel & telemetry", "Claude Code", "running"),
    ]),
    ("Research", [
        ("Brainstormer", "Ideation & concepts", "Claude Code", "idle"),
        ("Challenger", "Red-team / critique", "Claude Code", "idle"),
        ("Research Engineer", "Tech & domain research", "Claude Code", "idle"),
    ]),
    ("Product & Content", [
        ("Product Manager", "PRD & scope", "Claude Code", "idle"),
        ("Story Writer", "Epics & stories", "Claude Code", "running"),
        ("Content Writer", "Docs & copy", "Claude Code", "idle"),
        ("Graphic Designer", "UX & visual system", "Claude Code", "running"),
        ("Video Creator", "Media production", "Claude Code", "idle"),
    ]),
    ("Platform & Ops", [
        ("ProxOps", "Proxmox / cluster", "Claude Code", "idle"),
        ("GitHub Monitor", "PR / CI watch", "Process", "running"),
        ("Alfred", "Gateway agent", "OpenClaw", "idle"),
        ("Saver", "Local inference", "Ollama", "idle"),
    ]),
]

RUNTIMES = [  # label, detail, is_primary
    ("Claude Code", "14 agents · claude_local", True),
    ("OpenCode", "15 backups · opencode_local", False),
    ("Ollama", "Saver · ollama_agent", False),
    ("OpenClaw", "Alfred · openclaw_gateway", False),
    ("Process", "GitHub Monitor · CI watcher", False),
]

ROW_H = 40
HDR_H = 42
PAD_B = 14


def runtime_chip(T, x_right, y_mid, label, primary):
    w = 18 + len(label) * 6.6
    x = x_right - w
    if primary:
        bg, bd, tx = T["activebg"], T["accent"] + "55", T["accent2"]
    else:
        bg, bd, tx = T["panel"], T["border"], T["t2"]
    return chip(x, y_mid - 11, w, 22, label, bg, bd, tx, size=11, mono=True), x


def agent_row(T, x, y, w, name, role, runtime, st):
    s = []
    d, _, _, _ = status(T, st)
    s.append(dot(x + 20, y + ROW_H / 2, 4, d, pulse=(st == "running")))
    s.append(text(x + 36, y + 17, name, 13, T["t1"], w=700))
    s.append(text(x + 36, y + 32, role, 10.5, T["t3"]))
    ch, cx = runtime_chip(T, x + w - 14, y + ROW_H / 2, runtime, runtime == "Claude Code")
    s.append(ch)
    return "".join(s)


def team_panel(T, x, y, w, title, agents):
    h = HDR_H + len(agents) * ROW_H + PAD_B
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    # header
    s.append(text(x + 18, y + 27, title, 12.5, T["t2"], w=700, ls="0.4"))
    cw = 20 + len(f"{len(agents)}") * 7 + 30
    s.append(chip(x + w - 14 - 58, y + 12, 58, 20, f"{len(agents)} agent" + ("s" if len(agents) != 1 else ""),
                  T["panel"], T["border"], T["t3"], size=10))
    s.append(rect(x + 14, y + HDR_H - 4, w - 28, 1, T["divider"]))
    ry = y + HDR_H
    for i, (name, role, runtime, st) in enumerate(agents):
        if i:
            s.append(rect(x + 14, ry, w - 28, 1, T["divider"]))
        s.append(agent_row(T, x, ry, w, name, role, runtime, st))
        ry += ROW_H
    return "".join(s), h


def runtimes_panel(T, x, y, w):
    rows = RUNTIMES
    h = HDR_H + len(rows) * 34 + 40
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    s.append(text(x + 18, y + 27, "RUNTIMES", 12.5, T["t2"], w=700, ls="0.4"))
    s.append(rect(x + 14, y + HDR_H - 4, w - 28, 1, T["divider"]))
    ry = y + HDR_H + 4
    for label, detail, primary in rows:
        if primary:
            bg, bd, tx = T["activebg"], T["accent"] + "55", T["accent2"]
        else:
            bg, bd, tx = T["panel"], T["border"], T["t2"]
        cw = 18 + len(label) * 6.6
        s.append(chip(x + 18, ry, cw, 22, label, bg, bd, tx, size=11, mono=True))
        s.append(text(x + 18 + cw + 12, ry + 15, detail, 10.5, T["t3"]))
        ry += 34
    s.append(rect(x + 14, ry + 2, w - 28, 1, T["divider"]))
    s.append(text(x + 18, ry + 24, "Each primary has a 1:1 OpenCode backup (failover).", 10, T["t4"]))
    return "".join(s)


def build_content(T):
    s = []
    # summary line + source note
    s.append(text(260, 92, "IsItObservable Labs  ·  15 active agents across 5 teams  ·  4 runtimes  ·  +15 OpenCode backups",
                  12, T["t2"], w=600))
    s.append(text(1416, 92, "Source: Agent registry (live)  ·  read-only", 11, T["t4"], anchor="end"))
    s.append(rect(260, 104, 1164, 1, T["border"]))

    col_w = 372
    gap = 24
    x1 = 260
    x2 = x1 + col_w + gap
    x3 = x2 + col_w + gap
    top = 122

    # Column 1: Leadership + Engineering
    y = top
    p, h = team_panel(T, x1, y, col_w, *TEAMS[0]); s.append(p); y += h + 16
    p, h = team_panel(T, x1, y, col_w, *TEAMS[1]); s.append(p)

    # Column 2: Research + Product & Content
    y = top
    p, h = team_panel(T, x2, y, col_w, *TEAMS[2]); s.append(p); y += h + 16
    p, h = team_panel(T, x2, y, col_w, *TEAMS[3]); s.append(p)

    # Column 3: Platform & Ops + Runtimes
    y = top
    p, h = team_panel(T, x3, y, col_w, *TEAMS[4]); s.append(p); y += h + 16
    s.append(runtimes_panel(T, x3, y, col_w))

    # footer note
    s.append(text(260, 872, "Read-only view — add / assign / retire agents in Compose.  Live status via SSE.",
                  11, T["t4"]))
    return "".join(s)


def build(T):
    body = rect(0, 0, 1440, 900, T["bg"]) + build_rail(T) + build_header(T) + build_content(T)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" '
            f'viewBox="0 0 1440 900" {F}>{body}</svg>')


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "images")
    for suffix, T in [("", DARK), ("-light", LIGHT)]:
        path = os.path.join(out, f"11-team-configuration{suffix}.svg")
        with open(path, "w") as f:
            f.write(build(T))
        print("wrote", path)
