#!/usr/bin/env python3
"""Screen 16 — Adaptive navigation: Admin vs non-admin (ISI-2307 items 2 + 5).

Shows the two real rails side by side so the difference is legible at a glance:
  * ADMIN rail — Dashboard (fleet) + all-projects selector + "Users & Roles".
  * NON-ADMIN rail (Operator/Viewer) — no Dashboard, no Users & Roles, settings
    read-only, and an "authorized only" project selector.
Plus a callout on the authorized-projects rule (item 5).

Realizes docs/bmad/ux/rbac-nav-ia-revision.md §4. Renders 1440x900; PNG 1.5x.
"""
import console_kit_rbac as R
from console_kit_rbac import text, rect, line, dot, chip, _stk, access_badge, ic_project, ic_lock


def diff_note(T, x, y, w, sign, label):
    """A +/− delta chip explaining what the non-admin rail loses/keeps."""
    if sign == "-":
        bg, c, glyph = T["r_bg"], T["r_txt"], "−"
    elif sign == "~":
        bg, c, glyph = T["a_bg"], T["a_txt"], "~"
    else:
        bg, c, glyph = T["g_bg"], T["g_txt"], "+"
    s = [rect(x, y, 20, 20, bg, rx=6, stroke=c + "55")]
    s.append(text(x + 10, y + 15, glyph, 13, c, w=700, anchor="middle"))
    s.append(text(x + 30, y + 15, label, 11.5, T["t2"]))
    return "".join(s)


def rail_panel(T, x, y, access, title, subtitle, badge_level):
    """Render a scaled-down real rail inside a labelled card at (x,y)."""
    card_w, card_h = 300, 600
    s = [rect(x, y, card_w, card_h, T["panel"], rx=16, stroke=T["border"])]
    # title strip
    s.append(text(x + 22, y + 32, title, 15, T["t1"], w=700))
    b, bw = access_badge(T, x + card_w - 22 - _measure(badge_level), y + 18, badge_level)
    s.append(b)
    s.append(text(x + 22, y + 52, subtitle, 10.5, T["t3"]))
    s.append(rect(x + 16, y + 64, card_w - 32, 1, T["divider"]))
    # embed the actual rail, scaled to fit
    scale = 0.86
    rail_svg = R.build_rail_rbac(T, active="overview" if access != "admin" else "dashboard",
                                 access=access, authorized_projects=2, height=int((card_h - 90) / scale))
    s.append(f'<g transform="translate({x+18},{y+80}) scale({scale})">{rail_svg}</g>')
    return "".join(s)


def _measure(level):
    return 22 + len(level.upper()) * 7.2


def build_content(T):
    s = []
    lx = 260
    s.append(text(lx, 96, "Adaptive navigation", 20, T["t1"], w=700))
    s.append(text(lx, 116, "The same console renders a different rail per access level. Items a user cannot "
                           "act on are removed, not disabled — no dead affordances.", 11.5, T["t3"]))
    s.append(rect(lx, 128, 1164, 1, T["border"]))

    # two rails side by side
    s.append(rail_panel(T, lx, 150, "admin", "Admin", "platform engineer — full fleet", "Admin"))
    s.append(rail_panel(T, lx + 330, 150, "operator", "Non-admin", "operator / viewer — scoped", "Operator"))

    # ---- right column: the delta + authorized-projects rule ----
    rx0, rw = 940, 484
    s.append(rect(rx0, 150, rw, 300, T["card"], rx=13, stroke=T["border"]))
    s.append(text(rx0 + 20, 180, "What changes for non-admin", 14, T["t1"], w=700))
    s.append(rect(rx0 + 16, 194, rw - 32, 1, T["divider"]))
    dy = 216
    for sign, lbl in [
        ("-", "Dashboard (fleet-wide) — hidden"),
        ("-", "Users & Roles — hidden (admin only)"),
        ("~", "Project selector — authorized projects only"),
        ("~", "Configuration & Credentials — read-only"),
        ("+", "Overview · Agents · Build · Tickets · Runs · Discussion — kept, scoped"),
    ]:
        s.append(diff_note(T, rx0 + 22, dy, rw - 44, sign, lbl))
        dy += 34

    # authorized-projects selector callout (item 5)
    cy0 = 470
    s.append(rect(rx0, cy0, rw, 230, T["panel"], rx=13, stroke=T["accent"] + "44"))
    s.append(rect(rx0, cy0, 3, 230, T["accent"], rx=2))
    s.append(ic_lock(rx0 + 26, cy0 + 28, T["accent2"]))
    s.append(text(rx0 + 44, cy0 + 32, "Project selector — authorized only", 13.5, T["t1"], w=700))
    s.append(text(rx0 + 20, cy0 + 56, "A non-admin never sees projects they lack membership for. The", 11, T["t3"]))
    s.append(text(rx0 + 20, cy0 + 72, "selector lists only granted projects; unknown project_id → 404.", 11, T["t3"]))
    # mock selector open — 3 total, 2 authorized
    selx, sely, selw = rx0 + 20, cy0 + 88, rw - 40
    s.append(rect(selx, sely, selw, 40, T["activebg"], rx=10, stroke=T["accent"] + "66"))
    s.append(ic_project(selx + 22, sely + 20, T["accent2"]))
    s.append(text(selx + 40, sely + 25, "ksquad-console", 13, T["t1"], w=700))
    s.append(chip(selx + selw - 128, sely + 9, 112, 22, "2 authorized ▾", T["panel"], T["border"], T["t3"], size=10))
    oy = sely + 48
    rows = [("ksquad-console", True), ("billing-svc", True), ("data-pipeline", False)]
    for name, ok in rows:
        c = T["t1"] if ok else T["t4"]
        s.append(ic_project(selx + 22, oy + 12, c if ok else T["t4"]))
        s.append(text(selx + 40, oy + 16, name, 12, c, mono=True, w=600 if ok else 400))
        if ok:
            s.append(f'<path d="M{selx+selw-30} {oy+11} l3 3 l6 -7" {_stk(T["g_txt"],1.8)}/>')
        else:
            s.append(ic_lock(selx + selw - 26, oy + 12, T["t4"]))
            s.append(text(selx + selw - 44, oy + 16, "no access", 9.5, T["t4"], anchor="end"))
        oy += 26

    s.append(text(lx, 884, "Enforcement is server-side (BFF authz + K8s RBAC); the rail difference is presentation of "
                           "the same authorization. Realizes rbac-nav-ia-revision.md §4.", 10.5, T["t4"]))
    return "".join(s)


def build(T):
    # host chrome uses the admin header (this is an admin viewing the IA); content carries both rails
    return (R.build_rail_rbac(T, active="agents", access="admin")
            + R.build_header_rbac(T, "Navigation", "Adaptive rail · access-level aware",
                                  level="Admin")
            + build_content(T))


if __name__ == "__main__":
    R.write_pair("16-adaptive-nav", build)
