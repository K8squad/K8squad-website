#!/usr/bin/env python3
"""Screen 15 — Users & Roles (admin only).

Admin-only console screen (ISI-2307 item 1). Three panels:
  * user list — identity, access level, project count, status;
  * access-level assignment — the selected user's Admin/Operator/Viewer control;
  * project-membership matrix — user × project grants (the source of the
    "authorized projects only" selector on every non-admin screen).

Realizes docs/bmad/ux/rbac-nav-ia-revision.md §2–§3. Renders 1440x900; PNG 1.5x.
"""
import console_kit_rbac as R
from console_kit_rbac import (text, rect, line, dot, chip, _stk, access_badge,
                              ic_users, ic_project, ic_shield)

USERS = [
    # (name, email, initials, level, projects, status)
    ("Priya Nair",     "priya@acme.io",   "PN", "Admin",    "all", "active"),
    ("David Osei",     "david@acme.io",   "DO", "Operator", "2",   "active"),
    ("Lena Fischer",   "lena@acme.io",    "LF", "Operator", "1",   "active"),
    ("Sam Rivera",     "sam@acme.io",     "SR", "Viewer",   "1",   "active"),
    ("Yuki Tanaka",    "yuki@acme.io",    "YT", "Operator", "3",   "invited"),
]

PROJECTS = ["ksquad-console", "billing-svc", "data-pipeline"]
# membership grid: name -> set of authorized project indices ('all' for admin)
GRANTS = {
    "Priya Nair":   "all",
    "David Osei":   {0, 1},
    "Lena Fischer": {0},
    "Sam Rivera":   {2},
    "Yuki Tanaka":  {0, 1, 2},
}
SELECTED = "David Osei"


def avatar(T, x, y, initials, r=15):
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{T["avatar"]}" stroke="{T["border"]}"/>'
            + text(x, y + 4, initials, 11, T["accent2"], w=700, anchor="middle"))


def user_row(T, x, y, w, u, selected):
    name, email, initials, level, projects, st = u
    if selected:
        s = [rect(x, y, w, 56, T["activebg"], rx=10, stroke=T["accent"] + "55"),
             rect(x, y, 3, 56, T["accent"], rx=2)]
    else:
        s = [rect(x, y, w, 56, T["card"], rx=10, stroke=T["border"])]
    s.append(avatar(T, x + 30, y + 28, initials))
    s.append(text(x + 54, y + 24, name, 13.5, T["t1"], w=700))
    s.append(text(x + 54, y + 40, email, 10.5, T["t3"], mono=True))
    badge, bw = access_badge(T, x + w - 250, y + 17, level)
    s.append(badge)
    pl = "all projects" if projects == "all" else f"{projects} project" + ("s" if projects != "1" else "")
    s.append(text(x + w - 96, y + 26, pl, 11, T["t2"], anchor="start"))
    if st == "invited":
        s.append(chip(x + w - 96, y + 32, 66, 18, "invited", T["a_bg"], T["a_txt"] + "55", T["a_txt"], size=9))
    else:
        s.append(dot(x + w - 88, y + 40, 3, T["g_dot"]))
        s.append(text(x + w - 78, y + 44, "active", 10, T["t3"]))
    return "".join(s)


def level_option(T, x, y, w, level, desc, chosen):
    stroke = T["accent"] if chosen else T["border"]
    bg = T["activebg"] if chosen else T["panel"]
    s = [rect(x, y, w, 52, bg, rx=10, stroke=stroke)]
    # radio
    s.append(f'<circle cx="{x+22}" cy="{y+26}" r="7" fill="none" stroke="{T["accent"] if chosen else T["t3"]}" stroke-width="1.6"/>')
    if chosen:
        s.append(dot(x + 22, y + 26, 3.4, T["accent"]))
    badge, bw = access_badge(T, x + 40, y + 15, level)
    s.append(badge)
    s.append(text(x + 40, y + 44, desc, 10.5, T["t3"]))
    return "".join(s)


def build_content(T):
    s = []
    lx = 260
    # header band under the top header
    s.append(text(lx, 96, "Users & Roles", 20, T["t1"], w=700))
    s.append(chip(lx + 168, 82, 74, 20, "admin only", T["accent"], T["accent"], "#fff", size=9.5))
    s.append(text(lx, 116, "Manage who can sign in, their access level, and which projects they may see. "
                           "Backed by your OIDC groups — this maps group→access level + project membership.",
                  11.5, T["t3"]))
    s.append(rect(lx, 128, 1164, 1, T["border"]))

    # ---- left: user list ----
    top = 148
    lw = 700
    s.append(text(lx, top + 4, f"USERS · {len(USERS)}", 11, T["t4"], w=700, ls="1.2"))
    s.append(rect(lx + lw - 140, top - 12, 140, 28, T["accent"], rx=9))
    s.append(text(lx + lw - 70, top + 6, "+ Invite user", 12, "#fff", w=700, anchor="middle"))
    ry = top + 24
    for u in USERS:
        s.append(user_row(T, lx, ry, lw, u, u[0] == SELECTED))
        ry += 64

    # ---- right: detail for SELECTED — access level assignment ----
    rx0, rw = 992, 432
    ry0 = 148
    s.append(rect(rx0, ry0, rw, 250, T["card"], rx=13, stroke=T["border"]))
    s.append(avatar(T, rx0 + 32, ry0 + 34, "DO", r=18))
    s.append(text(rx0 + 62, ry0 + 30, SELECTED, 15, T["t1"], w=700))
    s.append(text(rx0 + 62, ry0 + 48, "david@acme.io", 11, T["t3"], mono=True))
    s.append(rect(rx0 + 14, ry0 + 64, rw - 28, 1, T["divider"]))
    s.append(text(rx0 + 18, ry0 + 88, "ACCESS LEVEL", 10.5, T["t4"], w=700, ls="1.2"))
    yy = ry0 + 100
    s.append(level_option(T, rx0 + 16, yy, rw - 32, "Admin", "all projects · settings · manage users", False))
    yy += 58
    s.append(level_option(T, rx0 + 16, yy, rw - 32, "Operator", "run & inspect · authorized projects only", True))
    # (Viewer option omitted for space; matrix below shows the rule)

    # ---- right lower: project membership matrix ----
    my = ry0 + 266
    mh = 226
    s.append(rect(rx0, my, rw, mh, T["card"], rx=13, stroke=T["border"]))
    s.append(ic_project(rx0 + 26, my + 26, T["accent2"]))
    s.append(text(rx0 + 44, my + 30, "Project membership", 13, T["t1"], w=700))
    s.append(text(rx0 + 18, my + 52, "Which projects this user may see. Drives the authorized-projects selector.",
                  10, T["t4"]))
    s.append(rect(rx0 + 14, my + 62, rw - 28, 1, T["divider"]))
    gy = my + 84
    grant = GRANTS[SELECTED]
    for i, p in enumerate(PROJECTS):
        on = grant == "all" or (isinstance(grant, set) and i in grant)
        rowc = T["t1"] if on else T["t3"]
        s.append(ic_project(rx0 + 30, gy, rowc))
        s.append(text(rx0 + 48, gy + 4, p, 12.5, rowc, w=600 if on else 400, mono=True))
        # toggle
        tx = rx0 + rw - 66
        tbg = T["accent"] if on else T["panel"]
        s.append(rect(tx, gy - 8, 44, 22, tbg, rx=11, stroke=T["border"] if not on else "none"))
        knob = tx + 30 if on else tx + 6
        s.append(f'<circle cx="{knob}" cy="{gy+3}" r="8" fill="#fff"/>')
        gy += 44

    # footer
    s.append(text(lx, 884, "Non-admin users never see this screen (adaptive nav, screen 16). "
                           "Access changes take effect on next sign-in · audit-logged.", 10.5, T["t4"]))
    return "".join(s)


def build(T):
    return (R.build_rail_rbac(T, active="users", access="admin")
            + R.build_header_rbac(T, "Settings", "Users & Roles · access administration",
                                  user="Priya Nair", initials="PN", level="Admin")
            + build_content(T))


if __name__ == "__main__":
    R.write_pair("15-users-roles", build)
