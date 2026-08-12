#!/usr/bin/env python3
"""Screens 20 + 21 — Agents: dual organizational views (dark + light).

ISI-2321 (CEO 2026-08-12 nav-IA revision) adds a NEW requirement to the global
**Agents** screen: a toggle between two org views over the *same* agents —

  View 1  Role-Based Org   → agents grouped by Role in swimlanes
                             (coordinator · coder · reviewer · tester …)
  View 2  Leadership Org    → chain-of-command tree (BigBoss → Leaders →
                             Squad leads → individual agents)

Both drill into an agent → detail (screen 11). Screen 20 renders View 1 active,
screen 21 renders View 2 active — the toggle is shown in each so the affordance
reads in a static mock. Reuses the revised Project-rooted rail (console_kit_ia,
active="agents"). Renders 1440x900; PNGs 1.5x (2160x1350) via resvg.
"""
import console_kit_ia as K
from console_kit_ia import text, rect, dot, chip, line


# --------------------------------------------------------------------------- #
# shared: the Role-Based ⇄ Leadership toggle
# --------------------------------------------------------------------------- #
def org_toggle(T, active):
    x, y, cw = 260, 84, 158
    s = [rect(x, y, cw * 2 + 8, 34, T["panel"], rx=10, stroke=T["border"])]
    for i, (k, label) in enumerate([("role", "Role-Based Org"), ("leadership", "Leadership Org")]):
        ox = x + 4 + i * cw
        if k == active:
            s.append(rect(ox, y + 4, cw, 26, T["accent"], rx=8))
        c = "#fff" if k == active else T["t2"]
        s.append(text(ox + cw / 2, y + 21, label, 12.5, c, w=700 if k == active else 500, anchor="middle"))
    s.append(text(x + cw * 2 + 26, y + 22, "same agents · organized two ways", 11.5, T["t3"]))
    # live legend (right)
    lx = 1000
    s.append(dot(lx, y + 17, 4, T["g_dot"], pulse=True))
    s.append(text(lx + 12, y + 21, "LIVE", 10.5, T["g_txt"], w=700, ls="0.6"))
    for sk, lab in [("running", "running"), ("paused", "paused"), ("blocked", "blocked"), ("idle", "idle")]:
        lx += 92 if sk != "running" else 74
        d, txt, _, _ = K.status(T, sk)
        s.append(dot(lx, y + 17, 3.6, d))
        s.append(text(lx + 12, y + 21, lab, 11, T["t2"], w=500))
    return "".join(s)


def agent_card(T, x, y, w, h, name, st, assignment, project, sel=False):
    d, txt, bg, bd = K.status(T, st)
    stroke = T["accent"] if sel else T["border"]
    s = [rect(x, y, w, h, T["activebg"] if sel else T["card"], rx=12, stroke=stroke)]
    if sel:
        s.append(rect(x, y, 3, h, T["accent"], rx=2))
    # avatar
    s.append(f'<circle cx="{x+26}" cy="{y+26}" r="13" fill="{T["accent"]}22" stroke="{T["accent"]}66"/>')
    s.append(text(x + 26, y + 30, name[0], 12, T["accent2"], w=700, anchor="middle"))
    s.append(text(x + 48, y + 24, name, 13.5, T["t1"], w=700))
    # status dot + label
    s.append(dot(x + 48 + 4, y + 38, 3.4, d, pulse=(st == "running")))
    s.append(text(x + 60, y + 42, st.capitalize(), 10.5, txt, w=600))
    # divider
    s.append(rect(x + 14, y + 54, w - 28, 1, T["divider"]))
    # current assignment
    s.append(text(x + 16, y + 74, "ASSIGNMENT", 8.5, T["t4"], w=700, ls="0.5"))
    s.append(text(x + 16, y + 90, assignment, 11, T["t2"], w=500))
    # project affiliation chip
    s.append(chip(x + 16, y + h - 30, 10 + len(project) * 7.2, 20, project, T["panel"], T["border"], T["accent2"], size=10.5, mono=True))
    return "".join(s)


# --------------------------------------------------------------------------- #
# View 1 — Role-Based Org (swimlanes)
# --------------------------------------------------------------------------- #
ROLE_LANES = [
    ("Coordinator", "squad leads · route & unblock", [
        ("Atlas", "running", "ISI-2311 · auth-session", "payments", True),
        ("Nomad", "idle", "— awaiting assignment", "checkout", False),
    ]),
    ("Coder", "implement · fix · ship", [
        ("Fixer", "running", "ISI-2166 · build-scope", "payments", False),
        ("Forge", "running", "ISI-2295 · gvisor bench", "platform", False),
        ("Patch", "paused", "ISI-2290 · AUP posture", "docs", False),
    ]),
    ("Reviewer", "review diffs · file findings", [
        ("Amelia", "running", "review · ISI-2321", "platform", False),
        ("Lint", "idle", "— awaiting review", "payments", False),
    ]),
    ("Tester", "e2e · QA · verify", [
        ("Proof", "running", "A5 auth tests", "payments", False),
        ("Verify", "blocked", "waiting on fixture", "checkout", False),
    ]),
]


def swimlane(T, x, y, w, role, desc, agents):
    h = 160
    s = [rect(x, y, w, h, T["panel"], rx=14, stroke=T["border"])]
    s.append(rect(x, y, 3, h, T["accent"] + "66", rx=2))
    # role header column (left, ~200)
    s.append(text(x + 22, y + 34, role, 15.5, T["t1"], w=700))
    s.append(chip(x + 22, y + 46, 78, 20, f"{len(agents)} agents", T["activebg"], T["accent"] + "44", T["accent2"], size=10))
    s.append(text(x + 22, y + 92, "ROLE", 9, T["t4"], w=700, ls="0.6"))
    # desc wrapped across two short lines
    s.append(text(x + 22, y + 110, desc, 10.5, T["t3"], w=400))
    s.append(rect(x + 190, y + 18, 1, h - 36, T["divider"]))
    # agent cards row
    cx = x + 210
    cw, ch = 210, 124
    for (name, st, assignment, project, sel) in agents:
        s.append(agent_card(T, cx, y + 18, cw, ch, name, st, assignment, project, sel))
        cx += cw + 16
    return "".join(s), h


def build_role_view(T):
    s = [org_toggle(T, "role")]
    s.append(text(260, 150, "Role-Based Org", 18, T["t1"], w=700))
    s.append(text(410, 150, "— agents grouped by Role · each Role is a swimlane · click a card → agent detail (screen 11)",
                  11.5, T["t3"]))
    x, w = 260, 1156
    y = 166
    for role, desc, agents in ROLE_LANES:
        card, h = swimlane(T, x, y, w, role, desc, agents)
        s.append(card)
        y += h + 14
    s.append(text(260, 878, "Source: Agent · Role CRDs (read-only) · live status via SSE.  "
                            "Cards show agent · status · current assignment · project affiliation.", 11, T["t4"]))
    return "".join(s)


# --------------------------------------------------------------------------- #
# View 2 — Leadership Org (chain-of-command tree)
# --------------------------------------------------------------------------- #
def node_box(T, cx, y, w, h, title, sub, accent=False, status_key=None):
    x = cx - w / 2
    stroke = T["accent"] if accent else T["border"]
    bg = T["activebg"] if accent else T["card"]
    s = [rect(x, y, w, h, bg, rx=12, stroke=stroke)]
    if accent:
        s.append(rect(x, y, 3, h, T["accent"], rx=2))
    s.append(text(x + 16, y + 23, title, 13.5, T["t1"], w=700))
    s.append(text(x + 16, y + 40, sub, 10.5, T["t3"]))
    if status_key:
        d, _, _, _ = K.status(T, status_key)
        s.append(dot(x + w - 16, y + 20, 4, d, pulse=(status_key == "running")))
    return "".join(s)


def connect(T, pcx, py, child_cxs, cy):
    mid = (py + cy) / 2
    c = T["accent"] + "88"
    s = [f'<g stroke="{c}" stroke-width="1.5" fill="none" stroke-linecap="round">']
    s.append(f'<path d="M{pcx} {py} V{mid}"/>')
    if len(child_cxs) > 1:
        s.append(f'<path d="M{min(child_cxs)} {mid} H{max(child_cxs)}"/>')
    for ccx in child_cxs:
        s.append(f'<path d="M{ccx} {mid} V{cy}"/>')
    s.append("</g>")
    return "".join(s)


def tier_label(T, y, label):
    return (rect(262, y, 4, 20, T["accent"] + "66", rx=2) +
            text(276, y + 15, label, 10.5, T["t4"], w=700, ls="0.8"))


def build_leadership_view(T):
    s = [org_toggle(T, "leadership")]
    s.append(text(260, 150, "Leadership Org", 18, T["t1"], w=700))
    s.append(text(410, 150, "— chain of command · authority & delegation flow top → down · click any node → agent detail",
                  11.5, T["t3"]))

    # tier geometry
    t0y, t1y, t2y, t3y = 178, 288, 410, 532
    bigboss_cx = 838

    # connectors first (behind boxes)
    s.append(connect(T, bigboss_cx, t0y + 56, [470, 838, 1206], t1y))              # BigBoss → Leaders
    s.append(connect(T, 470, t1y + 56, [470], t2y))                               # Architect → Atlas
    s.append(connect(T, 838, t1y + 56, [838], t2y))                               # PM → Nomad
    s.append(connect(T, 470, t2y + 54, [360, 560], t3y))                          # Atlas → coder+reviewer
    s.append(connect(T, 838, t2y + 54, [740, 940, 1140], t3y))                    # Nomad → coder+reviewer+tester

    # tier labels (left gutter)
    s.append(tier_label(T, t0y + 18, "BIGBOSS"))
    s.append(tier_label(T, t1y + 18, "LEADERS"))
    s.append(tier_label(T, t2y + 17, "SQUAD LEADS"))
    s.append(tier_label(T, t3y + 16, "AGENTS"))

    # Tier 0 — BigBoss
    s.append(node_box(T, bigboss_cx, t0y, 200, 56, "BigBoss", "CEO · autonomy owner", accent=True))
    # Tier 1 — Leaders
    s.append(node_box(T, 470, t1y, 190, 56, "Winston", "System Architect", status_key="running"))
    s.append(node_box(T, 838, t1y, 190, 56, "John", "Product Manager", status_key="idle"))
    s.append(node_box(T, 1206, t1y, 190, 56, "Scribe", "Story Writer", status_key="idle"))
    # Tier 2 — Squad leads (coordinators)
    s.append(node_box(T, 470, t2y, 184, 54, "Atlas", "Coordinator · payments", status_key="running"))
    s.append(node_box(T, 838, t2y, 184, 54, "Nomad", "Coordinator · checkout", status_key="idle"))
    # Tier 3 — individual agents
    s.append(node_box(T, 360, t3y, 172, 52, "Fixer", "Coder", status_key="running"))
    s.append(node_box(T, 560, t3y, 172, 52, "Amelia", "Reviewer", status_key="running"))
    s.append(node_box(T, 740, t3y, 172, 52, "Proof", "Tester", status_key="running"))
    s.append(node_box(T, 940, t3y, 172, 52, "Forge", "Coder", status_key="running"))
    s.append(node_box(T, 1140, t3y, 172, 52, "Verify", "Tester", status_key="blocked"))

    # note card (bottom-right)
    nx, ny, nw = 1006, 620, 410
    s.append(rect(nx, ny, nw, 128, T["panel"], rx=12, stroke=T["border"]))
    s.append(rect(nx, ny, 3, 128, T["accent"], rx=2))
    s.append(text(nx + 18, ny + 26, "Authority / delegation flow", 12.5, T["t1"], w=700))
    for i, ln in enumerate([
        "BigBoss delegates to Leaders (Architect · PM ·",
        "Story Writer); Leaders own squads via a Coordinator;",
        "Coordinators direct the coder / reviewer / tester agents.",
        "Same agents as the Role-Based view — different lens.",
    ]):
        s.append(text(nx + 18, ny + 50 + i * 18, ln, 10.5, T["t3"]))

    s.append(text(260, 878, "Source: Team · Agent · Role CRDs (read-only) · reporting edges from Team ownership + coordinator binding.",
                  11, T["t4"]))
    return "".join(s)


# --------------------------------------------------------------------------- #
def _screen(view_fn):
    def build(T):
        return (K.build_rail_ia(T, active="agents") +
                K.build_header(T, "ksquad-console", "Agents", "Global · dual org views — Role-Based ⇄ Leadership") +
                view_fn(T))
    return build


if __name__ == "__main__":
    K.write_pair("20-agents-role-org", _screen(build_role_view))
    K.write_pair("21-agents-leadership-org", _screen(build_leadership_view))
