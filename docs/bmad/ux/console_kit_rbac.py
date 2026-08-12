#!/usr/bin/env python3
"""Console-user RBAC extension kit for the KSquad operator console (ISI-2307).

Additive layer on top of `console_kit_ia` — reuses the locked visual system
(dark #0B1220 + azure #3D7DFF; light mirror), the 8-Crest logo lockup, the icon
set, and the token maps. Adds only what the RBAC screens (15–18) need:

  * a **role-adaptive** nav rail (`build_rail_rbac`) — Admin sees Dashboard +
    "Users & Roles"; non-admin (Operator/Viewer) does not, and the project
    selector is labelled "authorized only".
  * a Users icon + an **access-level badge** (Admin / Operator / Viewer).
  * login primitives (large centred logo lockup, SSO button, input field).
  * a phone frame + role-adaptive **bottom nav** for the mobile screen.

The existing kit is not modified; screens 13/14 keep rendering unchanged.
Realizes docs/bmad/ux/rbac-nav-ia-revision.md (the recreated IA reference).
"""
import console_kit_ia as K
from console_kit_ia import (DARK, LIGHT, text, rect, line, dot, chip, _stk,
                            F, FM, esc, svg_open,
                            ic_dashboard, ic_overview, ic_agents, ic_project,
                            ic_build, ic_tickets, ic_runs, ic_discussion,
                            ic_config, ic_creds, build_logo, RAIL_W)

# ---- extra glyphs -----------------------------------------------------------

def ic_users(cx, cy, c):
    """Two people — the Users & Roles item."""
    return (f'<g {_stk(c,1.5)}>'
            f'<circle cx="{cx-4}" cy="{cy-4}" r="2.6"/>'
            f'<path d="M{cx-9} {cy+6} a5 5 0 0 1 10 0"/>'
            f'<circle cx="{cx+5.5}" cy="{cy-3}" r="2.1"/>'
            f'<path d="M{cx+1.5} {cy+5.5} a4.2 4.2 0 0 1 8 0"/></g>')


def ic_shield(cx, cy, c):
    return (f'<g {_stk(c,1.5)}>'
            f'<path d="M{cx} {cy-8} l7 3 v5 c0 4.5 -3 7.5 -7 9 c-4 -1.5 -7 -4.5 -7 -9 v-5 z"/>'
            f'<path d="M{cx-3} {cy} l2 2.2 l4 -4.5"/></g>')


def ic_lock(cx, cy, c):
    return (f'<g {_stk(c,1.5)}>'
            f'<rect x="{cx-6}" y="{cy-1}" width="12" height="9" rx="2"/>'
            f'<path d="M{cx-3.5} {cy-1} v-2.5 a3.5 3.5 0 0 1 7 0 v2.5"/>'
            f'<circle cx="{cx}" cy="{cy+3.5}" r="1.1" fill="{c}" stroke="none"/></g>')


# ---- access-level badge -----------------------------------------------------
# Admin = azure (privileged); Operator = green (acts); Viewer = slate (read-only)
def _access_colors(T, level):
    lv = level.lower()
    if lv == "admin":
        return T["accent"], T["accent2"], T["activebg"]
    if lv == "operator":
        return T["g_dot"], T["g_txt"], T["g_bg"]
    return T["i_dot"], T["i_txt"], T["i_bg"]          # viewer


def access_badge(T, x, y, level, w=None, size=11):
    dot_c, txt_c, bg = _access_colors(T, level)
    label = level.upper()
    w = w if w is not None else 22 + len(label) * 7.2
    h = 22
    s = [rect(x, y, w, h, bg, rx=h / 2, stroke=txt_c + "55")]
    s.append(dot(x + 12, y + h / 2, 3, dot_c))
    s.append(text(x + 22, y + h / 2 + 4, label, size, txt_c, w=700, ls="0.4"))
    return "".join(s), w


# ---- role-adaptive rail -----------------------------------------------------

def _rail_model(access, authorized_projects):
    """Return the rail entry list for a given access level.
    access: 'admin' | 'operator' | 'viewer'."""
    admin = access == "admin"
    proj_sub = "all projects  ▾" if admin else f"{authorized_projects} authorized  ▾"
    m = [("section", None, "GLOBAL", None, None)]
    if admin:
        m.append(("item", "dashboard", "Dashboard", ic_dashboard, None))
    m += [
        ("item", "overview", "Overview", ic_overview, None),
        ("item", "agents", "Agents", ic_agents, None),
        ("section", None, "PROJECT", None, None),
        ("selector", "project", "ksquad-console", ic_project, proj_sub),
        ("subitem", "build", "Build", ic_build, None),
        ("subitem", "tickets", "Tickets", ic_tickets, None),
        ("subitem", "runs", "Runs", ic_runs, None),
        ("subitem", "discussion", "Discussion", ic_discussion, None),
        ("section", None, "SETTINGS", None, None),
        ("item", "configuration", "Configuration", ic_config, None if admin else "read-only"),
        ("item", "credentials", "Credentials", ic_creds, None if admin else "read-only"),
    ]
    if admin:
        m.append(("item", "users", "Users & Roles", ic_users, "admin"))
    return m


def build_rail_rbac(T, active, access="admin", authorized_projects=3, height=900):
    """Role-adaptive Project-rooted rail. Non-admin drops Dashboard + Users&Roles
    and labels the selector 'authorized only'. `active` = current node key."""
    RAIL = _rail_model(access, authorized_projects)
    s = [rect(0, 0, RAIL_W, height, T["rail"]), rect(RAIL_W - 1, 0, 1, height, T["border"])]
    s.append(build_logo(T))
    y = 78
    sub_ys, selector_cy = [], None
    for kind, key, label, icon, tag in RAIL:
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
            if tag == "admin":
                s.append(chip(168, y + 5, 58, 20, "admin", T["accent"], T["accent"], "#fff", size=9.5))
            elif tag == "read-only":
                s.append(chip(140, y + 5, 76, 20, "read-only", T["panel"], T["border"], T["t3"], size=9))
            elif key == "agents":
                s.append(chip(150, y + 5, 66, 20, "filter ▾", T["panel"], T["border"], T["t3"], size=9.5))
            y += 36
        elif kind == "selector":
            selector_cy = y + 20
            s.append(rect(12, y, 212, 40, T["activebg"], rx=10, stroke=T["accent"] + "66"))
            s.append(rect(12, y, 3, 40, T["accent"], rx=2))
            s.append(icon(32, y + 20, T["accent2"]))
            s.append(text(50, y + 15, label, 13, T["t1"], w=700))
            s.append(text(50, y + 30, tag, 9.5, T["t4"]))
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
    if selector_cy is not None and sub_ys:
        spine_x = 40
        s.insert(2, line(spine_x, selector_cy + 14, spine_x, sub_ys[-1], T["border"], sw=1.4))
        for scy in sub_ys:
            s.insert(3, line(spine_x, scy, 48, scy, T["border"], sw=1.4))
    # footer: connected pill only (Compose is context-dependent; keep it simple)
    s.append(rect(16, height - 32, 204, 24, T["panel"], rx=8, stroke=T["border"]))
    s.append(dot(32, height - 20, 3, T["g_dot"]))
    s.append(text(44, height - 16, "prod-euc1 · connected", 10.5, T["t3"], mono=True))
    return "".join(s)


def build_header_rbac(T, section, subtitle, user="Priya Nair", initials="PN", level="Admin"):
    """Header with an access-level badge next to the avatar."""
    s = [rect(RAIL_W, 0, 1440 - RAIL_W, 60, T["bg"]), rect(RAIL_W, 59, 1440 - RAIL_W, 1, T["border"]),
         text(260, 30, section, 18, T["t1"], w=700), text(260, 48, subtitle, 11, T["t3"])]
    _b, bw = access_badge(T, 0, 0, level)          # measure width only
    badge, bw = access_badge(T, 1360 - bw, 19, level)
    s.append(badge)
    s.append(f'<circle cx="1400" cy="30" r="15" fill="{T["avatar"]}" stroke="{T["border"]}"/>')
    s.append(text(1400, 34, initials, 11.5, T["accent2"], w=700, anchor="middle"))
    return "".join(s)


# ---- login primitives -------------------------------------------------------

def big_logo(T, cx, cy, scale=0.62):
    """Centred 8-Crest mark + wordmark for the login/mobile splash."""
    g = (f'<g transform="translate({cx},{cy}) scale({scale}) translate(-50,-50)">'
         f'<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
         f'<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="{T["accent"]}" stroke-width="9"/>'
         f'<rect x="45" y="25.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
         f'<rect x="45" y="64.5" width="10" height="10" rx="2.8" fill="{T["logodot"]}"/>'
         f'<rect x="42.5" y="42.5" width="15" height="15" rx="4.2" fill="{T["logodot"]}"/></g>')
    return g


def input_field(T, x, y, w, label, value, placeholder=False, icon=None):
    s = [text(x, y - 8, label, 11, T["t3"], w=600)]
    s.append(rect(x, y, w, 44, T["panel"], rx=10, stroke=T["border"]))
    tx = x + 16
    if icon:
        s.append(icon(x + 18, y + 22, T["t3"]))
        tx = x + 38
    s.append(text(tx, y + 27, value, 13, T["t4"] if placeholder else T["t1"], w=400 if placeholder else 500))
    return "".join(s)


def sso_button(T, x, y, w, label="Sign in with SSO", primary=True):
    h = 46
    bg = T["accent"] if primary else T["panel"]
    fg = "#fff" if primary else T["t2"]
    stroke = "none" if primary else T["border"]
    s = [rect(x, y, w, h, bg, rx=10, stroke=stroke)]
    # small shield glyph on primary
    if primary:
        s.append(ic_shield(x + 24, y + h / 2, "#fff"))
        s.append(text(x + w / 2 + 12, y + h / 2 + 5, label, 14, fg, w=700, anchor="middle"))
    else:
        s.append(text(x + w / 2, y + h / 2 + 5, label, 13.5, fg, w=600, anchor="middle"))
    return "".join(s)


# ---- mobile frame + bottom nav ----------------------------------------------
PHONE_W, PHONE_H = 390, 800          # logical device px (iPhone-ish)


def phone_frame(T, x, y, inner_fn, title_dark=True):
    """Draw a phone bezel at (x,y) and fill it via inner_fn(T, ox, oy) which draws
    the screen content in the phone's local coordinate space (0..PHONE_W)."""
    bezel = 12
    s = [rect(x - bezel, y - bezel, PHONE_W + 2 * bezel, PHONE_H + 2 * bezel, "#05070C", rx=44, stroke="#1A2438", sw=2)]
    s.append(rect(x, y, PHONE_W, PHONE_H, T["bg"], rx=32))
    # clip-less: content assumed to stay within bounds
    s.append(f'<g transform="translate({x},{y})">')
    # status bar
    s.append(text(22, 30, "9:41", 13, T["t1"], w=700))
    s.append(dot(PHONE_W - 60, 25, 2.4, T["t2"]))
    s.append(rect(PHONE_W - 48, 20, 20, 10, "none", rx=2, stroke=T["t3"]))
    s.append(rect(PHONE_W - 46, 22, 14, 6, T["t2"], rx=1))
    s.append(inner_fn(T, 0, 0))
    # notch
    s.append(rect(PHONE_W / 2 - 42, 8, 84, 22, "#05070C", rx=11))
    s.append('</g>')
    return "".join(s)


def mobile_bottom_nav(T, oy, access="admin", active="overview"):
    """Role-adaptive bottom tab bar in phone-local coords. Returns svg string."""
    admin = access == "admin"
    tabs = [("overview", "Squads", ic_overview),
            ("agents", "Agents", ic_agents),
            ("tickets", "Tickets", ic_tickets),
            ("runs", "Runs", ic_runs)]
    if admin:
        tabs.append(("users", "Manage", ic_users))
    n = len(tabs)
    bar_h = 68
    by = PHONE_H - bar_h
    s = [rect(0, by, PHONE_W, bar_h, T["rail"]), rect(0, by, PHONE_W, 1, T["border"])]
    cw = PHONE_W / n
    for i, (key, label, icon) in enumerate(tabs):
        cx = cw * i + cw / 2
        act = key == active
        c = T["accent2"] if act else T["t3"]
        if act:
            s.append(rect(cx - 20, by + 8, 40, 3, T["accent"], rx=1.5))
        s.append(icon(cx, by + 26, c))
        s.append(text(cx, by + 50, label, 10, c, w=700 if act else 500, anchor="middle"))
    return "".join(s)


def write_pair(basename, build_fn, w=1440, h=900):
    """Write dark + light SVG pair. Supports non-default canvas (mobile)."""
    import os
    out = os.path.join(os.path.dirname(__file__), "images")
    for suffix, T in [("", DARK), ("-light", LIGHT)]:
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
                f'viewBox="0 0 {w} {h}" {F}>' + rect(0, 0, w, h, T["bg"]))
        path = os.path.join(out, f"{basename}{suffix}.svg")
        with open(path, "w") as f:
            f.write(head + build_fn(T) + "</svg>")
        print("wrote", path)
