#!/usr/bin/env python3
"""Screen 14 — Project → Tickets (dark + light), KSquad operator console.

Story 8.14 (CEO 2026-08-12): the work items scoped to the selected Project. A
master-detail view — list of tickets (status · assignee · counts) on the left, and
a ticket detail (append-only provenanced comments, artifacts, checkout/holder, and
links to Runs 8.2 + build outputs 8.7) on the right. Read + navigate only: CRD
compose/edit stays in Compose (8.5); claim/coordination stays server-side (R6).

Data mirrors the Epic 2 coordination record for project `ksquad-console`. Wrapped by
the Project-rooted nav rail + breadcrumb + sub-nav (console_kit_ia). Renders 1440x900;
PNGs are the audited 1.5x (2160x1350) via @resvg/resvg-js.
"""
import console_kit_ia as K
from console_kit_ia import text, rect, chip, dot, line, status, _stk

# Ticket tree: parent → sub-tickets. Node = (id, title, status, initials, comments,
# updated, expanded, selected, [children]); child = (id, title, status, initials, comments, updated)
TREE = [
    ("ISI-2291", "Console nav-rail + breadcrumb IA mocks", "claimed", "GD", 6, "12m", True, True, [
        ("ISI-2291.1", "Nav-rail hierarchy + rail kit", "done", "GD", 2, "20m"),
        ("ISI-2291.2", "Project → Tickets tree view", "claimed", "GD", 3, "3m"),
        ("ISI-2291.3", "File explorer + Project dashboard", "open", "GD", 1, "1m"),
    ]),
    ("ISI-2288", "Settings page — OTelConfig + platform", "claimed", "UX", 3, "1h", False, False, []),
    ("ISI-2151", "Architecture r13 — NATS delivery seam", "done", "AR", 14, "5h", True, False, [
        ("ISI-2151.1", "Outbox → relay → nats_sub", "done", "AR", 4, "6h"),
        ("ISI-2151.2", "ADR-023 one-way delivery seam", "done", "AR", 2, "6h"),
    ]),
    ("ISI-2120", "Phase-4 epics — nav IA threading", "blocked", "SW", 5, "1d", False, False, []),
    ("ISI-2116", "Program — Phase 4 delivery track", "open", "BB", 2, "2d", False, False, []),
]

COMMENTS = [
    ("Henrik", "human · CEO", "09:14", "Console must be Project-rooted, not a flat screen list. Thread it into the epics doc and cut a design ticket.", False),
    ("Story Writer", "agent · claude_local", "09:31", "Threaded Story 8.13 (nav shell) + 8.14 (Tickets) into Epic 8. Existing screens re-parent unchanged.", False),
    ("Graphic Designer", "agent · claude_local", "10:02", "Building nav-rail IA + Project→Tickets mocks — dark + light, v2 8-Crest.", False),
    ("github-monitor", "scm · commit d18dc51", "10:20", "epics(phase4): OTelConfig CRD + settings folded into Epic 8.", True),
]

ARTIFACTS = [("13-nav-ia.svg", "svg"), ("14-project-tickets.svg", "svg"), ("04-epics-and-stories.md", "doc")]


def trunc(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def count_pill(T, x, y, label, n, st):
    d, tx, bg, bd = status(T, st)
    w = 48 + len(label) * 8 + 22
    s = [rect(x, y, w, 34, T["card"], rx=9, stroke=T["border"])]
    s.append(dot(x + 16, y + 17, 4, d))
    s.append(text(x + 28, y + 21, label, 12, T["t2"], w=600))
    s.append(text(x + w - 16, y + 21, str(n), 13.5, T["t1"], w=700, anchor="end"))
    return "".join(s), w


def avatar(T, cx, cy, initials, r=11):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{T["avatar"]}" stroke="{T["border"]}"/>'
            + text(cx, cy + 3.5, initials, r - 2.5, T["accent2"], w=700, anchor="middle"))


def comment_glyph(T, x, y, n):
    return (f'<path d="M{x} {y-4} h11 a1.4 1.4 0 0 1 1.4 1.4 v4.5 a1.4 1.4 0 0 1 -1.4 1.4 '
            f'h-6 l-3 2.4 v-2.4 h-2 a1.4 1.4 0 0 1 -1.4 -1.4 v-4.5 a1.4 1.4 0 0 1 1.4 -1.4 z" '
            f'{_stk(T["t4"],1.3)}/>' + text(x + 20, y + 5, str(n), 10.5, T["t3"], mono=True))


def chevron(T, cx, cy, expanded, c):
    if expanded:
        return f'<path d="M{cx-4} {cy-2} l4 4 l4 -4" {_stk(c,1.6)}/>'
    return f'<path d="M{cx-2} {cy-4} l4 4 l-4 4" {_stk(c,1.6)}/>'


def subticket_row(T, x, y, w, child, last):
    """Compact nested sub-ticket row with tree guide."""
    cid, title, st, ini, ncom, upd = child
    s = []
    d, tx, bg, bd = status(T, st)
    # tree guide: elbow from the parent spine (drawn by the card) into this row
    s.append(line(x + 34, y + 13, x + 46, y + 13, T["border"], sw=1.4))
    s.append(dot(x + 54, y + 13, 3.5, d, pulse=(st == "claimed")))
    s.append(text(x + 66, y + 17, cid, 10.5, T["t3"], w=600, mono=True))
    s.append(text(x + 138, y + 17, trunc(title, 30), 11.5, T["t2"]))
    s.append(chip(x + w - 84, y + 4, 66, 18, st, bg, bd, tx, size=9))
    s.append(comment_glyph(T, x + w - 150, y + 13, ncom))
    s.append(avatar(T, x + w - 108, y + 13, ini, r=8))
    return "".join(s)


def ticket_card(T, x, y, w, node):
    tid, title, st, ini, ncom, upd, expanded, sel, children = node
    has_kids = len(children) > 0
    hdr = 62
    body = (len(children) * 34 + 10) if (expanded and has_kids) else 0
    h = hdr + body
    s = []
    if sel:
        s.append(rect(x, y, w, h, T["activebg"], rx=11, stroke=T["accent"] + "55"))
        s.append(rect(x, y, 3, h, T["accent"], rx=2))
    else:
        s.append(rect(x, y, w, h, T["card"], rx=11, stroke=T["border"]))
    d, tx, bg, bd = status(T, st)
    # chevron (only parents) + status dot
    if has_kids:
        s.append(chevron(T, x + 24, y + 22, expanded, T["t2"]))
    s.append(dot(x + 42, y + 22, 4, d, pulse=(st == "claimed")))
    s.append(text(x + 56, y + 26, tid, 11.5, T["accent2"] if sel else T["t2"], w=700, mono=True))
    if has_kids:
        s.append(chip(x + 140, y + 15, 74, 18, f"{len(children)} sub-tickets", T["panel"], T["border"], T["t3"], size=9))
    s.append(chip(x + w - 92, y + 11, 78, 20, st, bg, bd, tx, size=10))
    s.append(text(x + w - 106, y + 26, upd, 10, T["t4"], anchor="end"))
    s.append(text(x + 56, y + 46, trunc(title, 38), 12.5, T["t1"], w=600 if sel else 500))
    s.append(avatar(T, x + w - 24, y + 42, ini, r=10))
    s.append(comment_glyph(T, x + w - 96, y + 42, ncom))
    # nested sub-tickets
    if expanded and has_kids:
        # vertical spine from the parent dot down through the children
        cy0 = y + hdr
        s.append(line(x + 34, y + 30, x + 34, cy0 + (len(children) - 1) * 34 + 13, T["border"], sw=1.4))
        ry = cy0
        for i, ch in enumerate(children):
            s.append(subticket_row(T, x, ry, w, ch, i == len(children) - 1))
            ry += 34
    return "".join(s), h


def comment_block(T, x, y, w, c):
    author, prov, when, body, is_scm = c
    ini = "".join(p[0] for p in author.replace("-", " ").split()[:2]).upper()
    s = []
    s.append(avatar(T, x + 15, y + 12, ini, r=12))
    s.append(text(x + 36, y + 8, author, 12.5, T["t1"], w=700))
    prov_c = T["mem"] if is_scm else T["t4"]
    prov_bg = T["mem_bg"] if is_scm else T["panel"]
    pw = 20 + len(prov) * 6.0
    s.append(chip(x + 36 + len(author) * 7.6 + 10, y - 2, pw, 18, prov, prov_bg, T["border"], prov_c, size=9.5, mono=True))
    s.append(text(x + w - 6, y + 8, when, 10, T["t4"], anchor="end"))
    # body (single wrapped-in-copy line)
    s.append(text(x + 36, y + 28, body, 11.5, T["t2"]))
    return "".join(s)


def build_detail(T, x, y, w):
    s = [rect(x, y, w, 566, T["card"], rx=13, stroke=T["border"])]
    px = x + 24
    # header
    d, tx, bg, bd = status(T, "claimed")
    s.append(text(px, y + 34, "ISI-2291", 13, T["accent2"], w=700, mono=True))
    s.append(chip(px + 84, y + 21, 84, 22, "claimed", bg, bd, tx, size=11))
    s.append(chip(px + 176, y + 21, 66, 22, "high", T["r_bg"], T["r_dot"] + "55", T["r_txt"], size=11))
    s.append(text(px, y + 60, "Console nav-rail + breadcrumb IA mocks — Project-rooted hierarchy", 15.5, T["t1"], w=700))
    # meta row: assignee + checkout/holder
    my = y + 84
    s.append(rect(px, my, w - 48, 46, T["panel"], rx=10, stroke=T["border"]))
    s.append(avatar(T, px + 24, my + 23, "GD", r=12))
    s.append(text(px + 42, my + 20, "Graphic Designer", 12, T["t1"], w=600))
    s.append(text(px + 42, my + 34, "assignee", 10, T["t4"]))
    s.append(line(px + 200, my + 10, px + 200, my + 36, T["border"], sw=1))
    s.append(f'<g {_stk(T["g_dot"],1.5)}><path d="M{px+224} {my+20} l3 3 l6 -6"/></g>')
    s.append(text(px + 244, my + 20, "checked out · Graphic Designer", 11.5, T["t2"], w=600))
    s.append(text(px + 244, my + 34, "lease 42m remaining · coordination server-side", 10, T["t4"]))
    s.append(chip(px + w - 48 - 156, my + 12, 142, 22, "1 holder · no contention", T["g_bg"], T["g_dot"] + "55", T["g_txt"], size=10))

    # comments section
    cy = my + 68
    s.append(text(px, cy, "COMMENTS", 11, T["t3"], w=700, ls="0.8"))
    s.append(chip(px + 90, cy - 14, 132, 20, "append-only · provenanced", T["panel"], T["border"], T["t4"], size=9.5))
    s.append(text(px + w - 48, cy, f"{len(COMMENTS)} of 6", 10, T["t4"], anchor="end"))
    cy += 14
    for c in COMMENTS:
        s.append(rect(px, cy, w - 48, 1, T["divider"]))
        s.append(comment_block(T, px, cy + 22, w - 48, c))
        cy += 54

    # artifacts
    cy += 6
    s.append(text(px, cy, "ARTIFACTS", 11, T["t3"], w=700, ls="0.8"))
    cy += 14
    ax = px
    for name, kind in ARTIFACTS:
        aw = 30 + len(name) * 6.8
        s.append(rect(ax, cy, aw, 32, T["panel"], rx=8, stroke=T["border"]))
        ic = T["accent2"] if kind == "svg" else T["mem"]
        s.append(f'<g {_stk(ic,1.4)}><rect x="{ax+12}" y="{cy+9}" width="11" height="14" rx="1.6"/><path d="M{ax+15} {cy+14} h5 M{ax+15} {cy+17} h5"/></g>')
        s.append(text(ax + 30, cy + 21, name, 11, T["t2"], w=600, mono=True))
        ax += aw + 10

    # linked (Runs + build outputs)
    cy += 48
    s.append(text(px, cy, "LINKED", 11, T["t3"], w=700, ls="0.8"))
    cy += 14
    s.append(rect(px, cy, (w - 48 - 14) / 2, 40, T["panel"], rx=9, stroke=T["border"]))
    s.append(K.ic_runs(px + 22, cy + 20, T["accent2"]))
    s.append(text(px + 38, cy + 18, "run-2291-a · succeeded", 11.5, T["t1"], w=600, mono=True))
    s.append(text(px + 38, cy + 31, "→ Runs (8.2)", 9.5, T["t4"]))
    bx = px + (w - 48 - 14) / 2 + 14
    s.append(rect(bx, cy, (w - 48 - 14) / 2, 40, T["panel"], rx=9, stroke=T["border"]))
    s.append(K.ic_build(bx + 22, cy + 20, T["accent2"]))
    s.append(text(bx + 38, cy + 18, "build-2291 · published", 11.5, T["t1"], w=600, mono=True))
    s.append(text(bx + 38, cy + 31, "→ Build outputs (8.7)", 9.5, T["t4"]))

    # footer note
    s.append(rect(x + 14, y + 566 - 34, w - 28, 1, T["divider"]))
    s.append(text(px, y + 566 - 14, "Read + navigate — compose / edit lives in Compose (8.5); claim & coordination stay server-side (R6).",
                  10.5, T["t4"]))
    return "".join(s)


def build_content(T):
    s = []
    # sub-nav tab strip (now includes Overview + Files)
    s.append(K.build_subnav(T, 260, 74, 540, "tickets"))
    s.append(text(1416, 92, "project_id = ksquad-console · Epic 2 coordination record · read-only",
                  10.5, T["t4"], anchor="end"))

    # summary count pills
    py = 122
    x = 260
    for label, n, st in [("open", 9, "open"), ("claimed", 4, "claimed"),
                          ("blocked", 2, "blocked"), ("done", 9, "done")]:
        pill, pw = count_pill(T, x, py, label, n, st)
        s.append(pill)
        x += pw + 12
    s.append(text(x + 6, py + 22, "24 work items", 12, T["t3"], w=600))
    # view toggle (tree active) + sort
    s.append(chip(1424 - 118, py, 118, 34, "sort: updated ▾", T["card"], T["border"], T["t3"], size=10.5))
    s.append(chip(1424 - 118 - 140, py, 68, 34, "Tree", T["activebg"], T["accent"] + "55", T["accent2"], size=11))
    s.append(chip(1424 - 118 - 68, py, 60, 34, "List", T["card"], T["border"], T["t3"], size=11))

    # master list (left) — ticket tree, cards stack by rendered height
    lx, lw = 260, 470
    ly = py + 52
    yy = ly
    for node in TREE:
        card, ch = ticket_card(T, lx, yy, lw, node)
        s.append(card)
        yy += ch + 12

    # detail (right)
    s.append(build_detail(T, 746, ly, 678))
    return "".join(s)


def build(T):
    return (K.build_rail_ia(T, active="tickets") + K.build_header(
        T, "ksquad-console", "Tickets", "Work-item tree — parent → sub-tickets · status · assignee · comments · artifacts")
        + build_content(T))


if __name__ == "__main__":
    K.write_pair("14-project-tickets", build)
