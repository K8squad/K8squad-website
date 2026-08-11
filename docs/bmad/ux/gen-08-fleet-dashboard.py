#!/usr/bin/env python3
"""Generate screen 08 — Fleet dashboard (dark + light), KSquad operator console.

Revision v5 (ISI-2150, CEO addition 2026-08-11): the dashboard now leads with a
**Live assignments** panel — the real-time "who's doing what right now" view:
agent ↔ work item ↔ project mapping, status (running/paused/blocked), elapsed time,
and a per-row link to the agent's OTel trace. Live rows pulse (SSE). It pairs with
the org diagram (screen 09 · ISI-2161) and the run stream (screen 02 · FR-F2).

Preserved from v4: the KPI tile row, the live/recent runs list, and the right
column (Credential health · Recent artifacts · Namespaces). The standalone 24h
run-activity bar chart is folded into a compact sparkline in the panel header so
no approved signal is lost while the live-ops panel becomes the hero.

Renders 1440x900 SVG; PNGs are the audited 1.5x (2160x1350) via resvg.
"""
from console_kit import (DARK, LIGHT, status, text, rect, dot, chip,
                         build_rail, build_header, write_pair, F, FM)

MAIN_X, MAIN_W = 260, 816       # left/main column
RIGHT_X, RIGHT_W = 1096, 320    # right column


def kpi_tiles(T):
    s = []
    tiles = [  # label, value, value_color, sub, live
        ("ACTIVE RUNS", "5", T["g_txt"], "streaming now", True),
        ("SQUADS", "8", T["t1"], "across 3 namespaces", False),
        ("ARTIFACTS · 24h", "37", T["accent2"], "+12 today", False),
        ("PAUSED", "1", T["a_txt"], "credential expired", False),
        ("SUCCESS · 24h", "94%", T["g_txt"], "32 of 34 runs", False),
    ]
    x = MAIN_X
    w = 218.4
    for label, val, vc, sub, live in tiles:
        s.append(rect(x, 84, w, 92, T["card"], rx=12, stroke=T["border"]))
        s.append(text(x + 16, 110, label, 10, T["t3"], w=600, ls="0.5"))
        s.append(text(x + 16, 144, val, 30, vc, w=700))
        s.append(text(x + 16, 164, sub, 10.5, T["t4"]))
        if live:
            s.append(f'<circle cx="{x+w-16}" cy="108" r="4" fill="{T["g_dot"]}">'
                     f'<animate attributeName="opacity" values="1;0.3;1" dur="1.6s" '
                     f'repeatCount="indefinite"/></circle>')
        x += w + 16
    return "".join(s)


def spark(T, x, y):
    """Compact 24h run-activity sparkline (folds the old bar chart into the header)."""
    vals = [3, 2, 2, 1, 2, 3, 5, 7, 9, 11, 8, 7, 10, 12, 8, 6, 8, 10, 11, 9, 7, 5, 4, 6]
    mx = max(vals)
    s = [text(x, y - 22, "Run activity · 24h", 10, T["t4"], w=600)]
    bw, gap, mh = 5, 2.4, 26
    for i, v in enumerate(vals):
        h = 3 + (v / mx) * mh
        bx = x + i * (bw + gap)
        last = i == len(vals) - 1
        c = T["g_dot"] if last else T["accent"]
        op = "" if last else ' opacity="0.7"'
        s.append(f'<rect x="{bx}" y="{y - h}" width="{bw}" height="{h}" rx="1.5" '
                 f'fill="{c}"{op}/>')
        if last:
            s.append(f'<rect x="{bx}" y="{y - h}" width="{bw}" height="{h}" rx="1.5" '
                     f'fill="none" stroke="{T["g_dot"]}" stroke-width="1">'
                     f'<animate attributeName="opacity" values="0.9;0.2;0.9" dur="1.8s" '
                     f'repeatCount="indefinite"/></rect>')
    s.append(text(x, y + 12, "00:00", 8.5, T["t4"], mono=True))
    s.append(text(x + 23 * (bw + gap) + bw, y + 12, "now", 8.5, T["t4"], mono=True, anchor="end"))
    return "".join(s)


def assign_row(T, ry, a):
    """One live-assignment row: agent · status · work item · project · elapsed · trace."""
    name, initial, runtime, st, wid, wtitle, proj, ns, elapsed = a
    d, txt, bg, bd = status(T, st)
    live = st == "running"
    s = []
    # agent
    s.append(f'<circle cx="302" cy="{ry+18}" r="13" fill="{T["accent"]}22" stroke="{T["accent"]}66"/>')
    s.append(text(302, ry + 22, initial, 12, T["accent2"], w=700, anchor="middle"))
    s.append(text(324, ry + 14, name, 13, T["t1"], w=700))
    rtw = 8 + len(runtime) * 6.9
    s.append(chip(324, ry + 22, rtw, 18, runtime, T["panel"], T["border"], T["t3"], size=10))
    # status
    s.append(dot(552, ry + 18, 3.8, d, pulse=live))
    s.append(text(566, ry + 22, st.capitalize(), 11.5, txt, w=600))
    # work item
    s.append(text(648, ry + 14, wid, 12, T["t1"], w=700, mono=True))
    s.append(text(648, ry + 31, wtitle, 10.5, T["t3"]))
    # project
    s.append(text(838, ry + 14, proj, 11.5, T["t2"], w=600, mono=True))
    s.append(text(838, ry + 31, ns, 10, T["t4"], mono=True))
    # elapsed + trace link
    s.append(text(1044, ry + 14, elapsed, 12, T["t2"], w=600, mono=True, anchor="end"))
    s.append(text(1044, ry + 31, "trace →", 10, T["accent2"], w=600, anchor="end"))
    return "".join(s)


def live_assignments(T):
    x, y, w, h = MAIN_X, 196, MAIN_W, 330
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    # header
    s.append(text(x + 20, y + 28, "Live assignments", 14, T["t1"], w=700))
    s.append(text(x + 20, y + 45, "who's doing what right now · agent ↔ work item ↔ project", 11, T["t3"]))
    # LIVE · SSE badge
    s.append(dot(x + 470, y + 24, 4, T["g_dot"], pulse=True))
    s.append(text(x + 484, y + 28, "LIVE", 10.5, T["g_txt"], w=700, ls="0.6"))
    s.append(text(x + 520, y + 28, "SSE", 10.5, T["t3"], w=600, mono=True))
    # compact activity sparkline (folded-in chart), right side of header
    s.append(spark(T, x + 590, y + 40))
    s.append(rect(x + 20, y + 58, w - 40, 1, T["divider"]))
    # column headers
    hy = y + 76
    s.append(text(x + 20, hy, "AGENT", 9.5, T["t4"], w=700, ls="0.6"))
    s.append(text(552, hy, "STATUS", 9.5, T["t4"], w=700, ls="0.6"))
    s.append(text(648, hy, "WORK ITEM", 9.5, T["t4"], w=700, ls="0.6"))
    s.append(text(838, hy, "PROJECT", 9.5, T["t4"], w=700, ls="0.6"))
    s.append(text(x + w - 20, hy, "ELAPSED", 9.5, T["t4"], w=700, ls="0.6", anchor="end"))
    # rows
    agents = [  # name, initial, runtime, status, wid, title, project, ns, elapsed
        ("Reviewer", "R", "Claude Code", "running", "#88", "verify refund idempotency", "payments-service", "team-payments", "03:12"),
        ("Fixer", "F", "OpenCode", "running", "#91", "produce refund-fix diff", "payments-service", "team-payments", "01:48"),
        ("Docs-Writer", "D", "Claude Code", "running", "#77", "sync portal guide", "developer-portal", "developer-portal", "06:20"),
        ("Tester", "T", "Ollama adapter", "paused", "#94", "token expired · awaiting refresh", "checkout-api", "team-checkout", "12:04"),
        ("Linter", "L", "OpenCode", "blocked", "#96", "waiting on Reviewer approval", "platform-iac", "platform-iac", "00:32"),
    ]
    ry = y + 90
    for i, a in enumerate(agents):
        if i:
            s.append(rect(x + 20, ry - 4, w - 40, 1, T["rowline"]))
        s.append(assign_row(T, ry, a))
        ry += 48
    return "".join(s)


def run_row(T, ry, r):
    st_key, rid, squad, repo, note, prog = r
    d, txt, bg, bd = status(T, st_key)
    live = st_key == "running"
    label = st_key.capitalize()
    pill_w = 30 + len(label) * 6.6
    s = [rect(MAIN_X + 20, ry - 16, pill_w, 22, bg, rx=11, stroke=bd)]
    s.append(dot(MAIN_X + 32, ry - 5, 3.4, d, pulse=live))
    s.append(text(MAIN_X + 41, ry - 1, label, 11.5, txt, w=600))
    s.append(text(432, ry - 3, rid, 12.5, T["t1"], w=700, mono=True))
    s.append(text(484, ry - 3, squad, 12.5, T["t2"], w=600))
    s.append(text(640, ry - 3, repo, 10.5, T["t4"], mono=True))
    s.append(text(484, ry + 12, note, 10.5, T["t4"]))
    s.append(rect(826, ry - 4, 150, 6, T["track"], rx=3))
    s.append(rect(826, ry - 4, int(150 * prog), 6, d, rx=3))
    s.append(text(1056, ry - 1, "Open →", 11.5, T["accent2"], w=600, anchor="end"))
    return "".join(s)


def live_runs(T):
    x, y, w, h = MAIN_X, 542, MAIN_W, 334
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    s.append(text(x + 20, y + 28, "Live & recent runs", 13.5, T["t1"], w=700))
    s.append(text(x + w - 20, y + 28, "View all →", 11.5, T["accent2"], w=600, anchor="end"))
    s.append(rect(x + 20, y + 42, w - 40, 1, T["divider"]))
    runs = [  # status, id, squad, repo, note, progress
        ("running", "#143", "infra-lint", "platform-iac", "Reviewer checked out #88", 0.40),
        ("running", "#142", "payments-review", "payments-service", "Fixer producing diff…", 0.66),
        ("paused", "#139", "checkout-hardening", "checkout-api", "token expired · fixer-hermes", 0.50),
        ("failed", "#138", "api-contract", "orders-api", "retrying (attempt 2/3)…", 0.30),
    ]
    ry = y + 76
    for i, r in enumerate(runs):
        if i:
            s.append(rect(x + 20, ry - 34, w - 40, 1, T["rowline"]))
        s.append(run_row(T, ry, r))
        ry += 68
    return "".join(s)


def cred_health(T):
    x, y, w = RIGHT_X, 196, RIGHT_W
    s = [rect(x, y, w, 168, T["card"], rx=12, stroke=T["border"])]
    s.append(text(x + 18, y + 28, "Credential health", 13, T["t1"], w=700))
    s.append(rect(x + 18, y + 42, w - 36, 1, T["divider"]))
    # stacked bar (valid/expiring/expired = 9/2/1)
    bx, bw = x + 18, w - 36
    s.append(rect(bx, y + 58, bw, 10, T["track"], rx=5))
    total = 12
    seg = [(9, T["g_dot"]), (2, T["a_dot"]), (1, T["r_dot"])]
    cx = bx
    for n, c in seg:
        sw = bw * n / total
        s.append(rect(cx, y + 58, sw, 10, c))
        cx += sw
    rows = [("Valid", T["g_dot"], "9"), ("Expiring", T["a_dot"], "2"), ("Expired", T["r_dot"], "1")]
    ry = y + 92
    for label, c, n in rows:
        s.append(dot(x + 23, ry - 4, 4, c))
        s.append(text(x + 36, ry, label, 12, T["t2"]))
        s.append(text(x + w - 18, ry, n, 12, T["t1"], w=700, anchor="end"))
        ry += 24
    return "".join(s)


def recent_artifacts(T):
    x, y, w = RIGHT_X, 384, RIGHT_W
    s = [rect(x, y, w, 246, T["card"], rx=12, stroke=T["border"])]
    s.append(text(x + 18, y + 28, "Recent artifacts", 13, T["t1"], w=700))
    s.append(text(x + w - 18, y + 28, "Builds →", 11, T["accent2"], w=600, anchor="end"))
    s.append(rect(x + 18, y + 42, w - 36, 1, T["divider"]))
    items = [  # kind letter, color, name, sub
        ("D", T["g_dot"], "refund-fix.diff", "+42 −11"),
        ("C", T["accent"], "findings.md", "3 findings"),
        ("F", T["t2"], "portal-guide.md", "docs-sync"),
        ("R", T["accent2"], "contract.json", "orders-api"),
        ("L", T["t3"], "run-141.log", "audit trail"),
    ]
    iy = y + 49
    for letter, c, name, sub in items:
        s.append(rect(x + 18, iy, 24, 24, c + "22", rx=6, stroke=c + "55"))
        s.append(text(x + 30, iy + 17, letter, 11, c, w=700, anchor="middle"))
        s.append(text(x + 52, iy + 12, name, 12, T["t1"], w=600, mono=True))
        s.append(text(x + 52, iy + 26, sub, 10, T["t4"]))
        iy += 38
    return "".join(s)


def namespaces(T):
    x, y, w = RIGHT_X, 650, RIGHT_W
    s = [rect(x, y, w, 226, T["card"], rx=12, stroke=T["border"])]
    s.append(text(x + 18, y + 28, "Namespaces", 13, T["t1"], w=700))
    s.append(rect(x + 18, y + 42, w - 36, 1, T["divider"]))
    ns = [("team-payments", T["g_dot"], "3 squads · 2 live"),
          ("developer-portal", T["i_dot"], "2 squads · idle"),
          ("platform-iac", T["g_dot"], "3 squads · 1 live")]
    ny = y + 58
    for name, c, sub in ns:
        s.append(dot(x + 24, ny, 3.5, c))
        s.append(text(x + 38, ny + 4, name, 12, T["t2"], w=600, mono=True))
        s.append(text(x + 38, ny + 19, sub, 10, T["t4"]))
        ny += 40
    return "".join(s)


def build(T):
    return (build_rail(T, "dashboard") +
            build_header(T, "Dashboard", "Operator overview — fleet health + live agent assignments across all namespaces") +
            kpi_tiles(T) + live_assignments(T) + live_runs(T) +
            cred_health(T) + recent_artifacts(T) + namespaces(T))


if __name__ == "__main__":
    write_pair("08-fleet-dashboard", build)
