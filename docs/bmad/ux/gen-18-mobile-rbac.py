#!/usr/bin/env python3
"""Screen 18 — Mobile: login flow + role-adaptive bottom nav (ISI-2307 item 4).

Three phone frames on one board:
  1. Login — SSO-first splash (mobile of screen 17).
  2. Admin home — Overview + bottom nav WITH the "Manage" (Users) tab.
  3. Non-admin home — same shell, bottom nav WITHOUT "Manage", authorized
     projects only.

Realizes rbac-nav-ia-revision.md §4 (mobile mirror). Canvas 1440x900; PNG 1.5x.
"""
import console_kit_rbac as R
from console_kit_rbac import (text, rect, line, dot, chip, _stk, access_badge,
                              big_logo, sso_button, ic_project, ic_overview,
                              ic_runs, ic_agents, mobile_bottom_nav, phone_frame,
                              PHONE_W, PHONE_H)


def screen_login(T, ox, oy):
    s = []
    s.append(big_logo(T, PHONE_W / 2, 200, scale=0.95))
    s.append(text(PHONE_W / 2, 300, "KSquad", 26, T["t1"], w=700, anchor="middle", ls="0.3"))
    s.append(text(PHONE_W / 2, 324, "operator console", 12, T["t4"], anchor="middle", ls="0.5"))
    s.append(text(PHONE_W / 2, 400, "Run squads on your cluster,", 13, T["t3"], anchor="middle"))
    s.append(text(PHONE_W / 2, 420, "from anywhere.", 13, T["t3"], anchor="middle"))
    s.append(sso_button(T, 40, 560, PHONE_W - 80, "Sign in with SSO", primary=True))
    s.append(sso_button(T, 40, 620, PHONE_W - 80, "Continue with email", primary=False))
    s.append(text(PHONE_W / 2, 700, "Access granted by your platform admin.", 10, T["t4"], anchor="middle"))
    return "".join(s)


def _home_header(T, level, initials):
    s = [rect(0, 44, PHONE_W, 60, T["bg"]), rect(0, 104, PHONE_W, 1, T["border"])]
    s.append(text(22, 82, "Squads", 20, T["t1"], w=700))
    b, bw = access_badge(T, PHONE_W - 22 - (22 + len(level) * 7.2) - 36, 60, level)
    s.append(b)
    s.append(f'<circle cx="{PHONE_W-24}" cy="70" r="14" fill="{T["avatar"]}" stroke="{T["border"]}"/>')
    s.append(text(PHONE_W - 24, 74, initials, 10.5, T["accent2"], w=700, anchor="middle"))
    return "".join(s)


def _squad_card(T, y, name, agents, status, running):
    s = [rect(20, y, PHONE_W - 40, 84, T["card"], rx=14, stroke=T["border"])]
    s.append(ic_project(44, y + 30, T["accent2"]))
    s.append(text(64, y + 30, name, 14, T["t1"], w=700))
    s.append(text(64, y + 50, f"{agents} agents", 11, T["t3"]))
    dc = T["g_dot"] if running else T["i_dot"]
    s.append(dot(PHONE_W - 60, y + 30, 3.4, dc, pulse=running))
    s.append(text(PHONE_W - 50, y + 34, status, 10.5, T["g_txt"] if running else T["t3"], anchor="start"))
    # mini progress
    s.append(rect(44, y + 62, PHONE_W - 88, 6, T["panel"], rx=3))
    s.append(rect(44, y + 62, (PHONE_W - 88) * (0.7 if running else 0.3), 6, T["accent"], rx=3))
    return "".join(s)


def screen_home(T, access, level, initials):
    def inner(TT, ox, oy):
        s = [_home_header(TT, level, initials)]
        # authorized-projects hint for non-admin
        if access != "admin":
            s.append(chip(20, 116, PHONE_W - 40, 24, "2 authorized projects", TT["activebg"],
                          TT["accent"] + "44", TT["accent2"], size=10))
            y = 152
        else:
            s.append(chip(20, 116, PHONE_W - 40, 24, "all projects · fleet view", TT["activebg"],
                          TT["accent"] + "44", TT["accent2"], size=10))
            y = 152
        for name, ag, st, run in [("ksquad-console", 5, "running", True),
                                  ("billing-svc", 3, "idle", False),
                                  ("data-pipeline", 4, "running", True)]:
            # non-admin sees only authorized (first two)
            if access != "admin" and name == "data-pipeline":
                continue
            s.append(_squad_card(TT, y, name, ag, st, run))
            y += 96
        s.append(mobile_bottom_nav(TT, 0, access=access, active="overview"))
        return "".join(s)
    return inner


def build(T):
    s = []
    # board title
    s.append(text(70, 60, "Mobile — login flow + role-adaptive bottom nav", 20, T["t1"], w=700))
    s.append(text(70, 82, "The mobile console mirrors desktop authorization: SSO-first login, and a bottom "
                          "nav that adds a Manage tab only for admins.", 11.5, T["t3"]))
    s.append(rect(70, 96, 1300, 1, T["border"]))

    # pitch = phone(390) + bezel(24) + gap(30) = 444; fits 3 across 1440 with 40px margins
    y = 140
    x1, x2, x3 = 52, 496, 940
    s.append(phone_frame(T, x1, y, screen_login))
    s.append(text(x1 + PHONE_W / 2, y + PHONE_H + 40, "1 · Login (SSO-first)", 12.5, T["t2"], w=700, anchor="middle"))
    s.append(phone_frame(T, x2, y, screen_home(T, "admin", "Admin", "PN")))
    s.append(text(x2 + PHONE_W / 2, y + PHONE_H + 40, "2 · Admin — bottom nav has Manage", 12.5, T["t2"], w=700, anchor="middle"))
    s.append(phone_frame(T, x3, y, screen_home(T, "operator", "Operator", "DO")))
    s.append(text(x3 + PHONE_W / 2, y + PHONE_H + 40, "3 · Non-admin — no Manage, authorized only", 12.5, T["t2"], w=700, anchor="middle"))
    return "".join(s)


if __name__ == "__main__":
    # taller canvas to fit the phones + captions
    R.write_pair("18-mobile-rbac", build, w=1440, h=1040)
