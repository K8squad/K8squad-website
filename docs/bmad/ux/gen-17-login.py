#!/usr/bin/env python3
"""Screen 17 — Login (desktop, ISI-2307 item 3).

Split layout: left = brand panel (8-Crest mark, tagline, trust line); right =
sign-in card. Primary path is SSO/OIDC ("Sign in with SSO") — the console never
stores a human password. Realizes rbac-nav-ia-revision.md §1. 1440x900; PNG 1.5x.
"""
import console_kit_rbac as R
from console_kit_rbac import (text, rect, line, dot, chip, _stk,
                              big_logo, sso_button, input_field, ic_lock, ic_shield)


def build(T):
    s = [rect(0, 0, 1440, 900, T["bg"])]
    # ---- left brand panel ----
    lw = 620
    s.append(rect(0, 0, lw, 900, T["rail"]))
    s.append(rect(lw - 1, 0, 1, 900, T["border"]))
    s.append(big_logo(T, 120, 150, scale=0.9))
    s.append(text(190, 138, "KSquad", 30, T["t1"], w=700, ls="0.3"))
    s.append(text(190, 168, "operator console", 14, T["t4"], ls="0.6"))
    s.append(text(80, 300, "Run squads of agents", 30, T["t1"], w=700))
    s.append(text(80, 338, "on your own cluster.", 30, T["accent2"], w=700))
    s.append(text(80, 384, "Sign in with your organization identity. Your access level and", 13.5, T["t3"]))
    s.append(text(80, 404, "projects come from your team's directory — nothing to manage here.", 13.5, T["t3"]))
    # trust bullets
    by = 470
    for glyph, lbl in [(ic_shield, "SSO / OIDC — no passwords stored by the console"),
                       (ic_lock, "Access scoped by your directory groups (least privilege)")]:
        s.append(glyph(96, by, T["accent2"]))
        s.append(text(120, by + 5, lbl, 12.5, T["t2"]))
        by += 40
    s.append(dot(96, 838, 3, T["g_dot"]))
    s.append(text(110, 842, "prod-euc1 · connected", 11, T["t3"], mono=True))

    # ---- right sign-in card ----
    cx = lw + (1440 - lw) / 2
    cardw = 400
    cx0 = cx - cardw / 2
    cy0 = 250
    cardh = 400
    s.append(rect(cx0, cy0, cardw, cardh, T["card"], rx=18, stroke=T["border"]))
    s.append(text(cx, cy0 + 52, "Sign in", 22, T["t1"], w=700, anchor="middle"))
    s.append(text(cx, cy0 + 78, "Continue to the operator console", 12, T["t3"], anchor="middle"))
    # primary SSO
    s.append(sso_button(T, cx0 + 32, cy0 + 108, cardw - 64, "Sign in with SSO", primary=True))
    # divider
    dy = cy0 + 176
    s.append(line(cx0 + 32, dy, cx0 + cardw / 2 - 24, dy, T["divider"]))
    s.append(line(cx0 + cardw / 2 + 24, dy, cx0 + cardw - 32, dy, T["divider"]))
    s.append(text(cx, dy + 5, "or", 11, T["t4"], anchor="middle"))
    # secondary: email (for IdP-less dev / fallback)
    s.append(input_field(T, cx0 + 32, cy0 + 216, cardw - 64, "Work email",
                         "you@company.io", placeholder=True))
    s.append(sso_button(T, cx0 + 32, cy0 + 286, cardw - 64, "Continue with email", primary=False))
    s.append(text(cx, cy0 + 360, "Access is granted by your platform admin.", 10.5, T["t4"], anchor="middle"))
    # footer legal
    s.append(text(cx, 720, "By continuing you agree to your organization's acceptable-use policy.",
                  10.5, T["t4"], anchor="middle"))
    return "".join(s)


if __name__ == "__main__":
    R.write_pair("17-login", build)
