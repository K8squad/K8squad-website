#!/usr/bin/env python3
"""Screen 13 — Navigation IA: Project-rooted hierarchy (dark + light).

The CEO 2026-08-12 directive (Stories 8.13/8.14): the console is a Project-rooted
navigation hierarchy, NOT a flat screen list. This screen is the IA spec/mock —
the new hierarchical nav rail (real, on the left) plus an annotated map of the tree
in the content area: which nodes are GLOBAL vs PROJECT-scoped, the Project context
selector, the breadcrumb pattern (`Project › section`), and the sub-nav tab strip.

Pairs with screen 14 (Project → Tickets). Existing screens 8.1–8.12 are re-parented
unchanged — only the nav wrapping/routing changes. Renders 1440x900; PNGs 1.5x.
"""
import console_kit_ia as K
from console_kit_ia import text, rect, chip, dot, line, _stk


def scope_badge(T, x, y, kind):
    if kind == "global":
        return chip(x, y, 66, 20, "global", T["panel"], T["border"], T["t3"], size=10)
    if kind == "new":
        return chip(x, y, 46, 20, "NEW", T["accent"], T["accent"], "#fff", size=10)
    return chip(x, y, 108, 20, "project-scoped", T["activebg"], T["accent"] + "55", T["accent2"], size=10)


def node_row(T, x, y, w, icon, label, screen, scope, note, indent=False):
    s = []
    ix = x + (34 if indent else 16)
    tick_c = T["i_dot"] if scope == "global" else T["accent"]
    s.append(rect(x + 6, y + 8, 3, 28, tick_c, rx=2))
    if indent:
        s.append(line(x + 16, y + 22, x + 30, y + 22, T["border"], sw=1.4))
    s.append(icon(ix + 12, y + 22, T["accent2"] if scope != "global" else T["t3"]))
    s.append(text(ix + 30, y + 20, label, 13.5, T["t1"], w=700))
    s.append(text(ix + 30, y + 35, note, 10.5, T["t3"]))
    s.append(chip(x + w - 210, y + 12, 84, 20, screen, T["panel"], T["border"], T["t2"], size=10, mono=True))
    s.append(scope_badge(T, x + w - 118, y + 12, scope))
    return "".join(s)


def group_card(T, x, y, w, title, subtitle, rows):
    body_h = sum(r[6] for r in rows)
    h = 48 + body_h + 12
    s = [rect(x, y, w, h, T["card"], rx=13, stroke=T["border"])]
    s.append(text(x + 18, y + 26, title, 12.5, T["t2"], w=700, ls="0.6"))
    s.append(text(x + 18 + len(title) * 8 + 14, y + 26, subtitle, 10.5, T["t4"]))
    s.append(rect(x + 14, y + 40, w - 28, 1, T["divider"]))
    ry = y + 48
    for icon, label, screen, scope, note, indent, rh in rows:
        s.append(node_row(T, x + 6, ry, w - 12, icon, label, screen, scope, note, indent))
        ry += rh
    return "".join(s), h


def selector_row(T, x, y, w):
    """Project context selector as it appears at the root of the PROJECT group."""
    s = [rect(x + 6, y + 4, w - 12, 44, T["activebg"], rx=10, stroke=T["accent"] + "66")]
    s.append(rect(x + 6, y + 4, 3, 44, T["accent"], rx=2))
    s.append(K.ic_project(x + 28, y + 26, T["accent2"]))
    s.append(text(x + 46, y + 22, "ksquad-console", 13.5, T["t1"], w=700))
    s.append(text(x + 46, y + 37, "click → project dashboard · scopes Build · Files · Tickets · Runs · Discussion", 10, T["t4"]))
    s.append(f'<path d="M{x+w-30} {y+22} l4 4 l4 -4" {_stk(T["t3"],1.6)}/>')
    s.append(chip(x + w - 172, y + 15, 118, 22, "3 projects  ▾", T["panel"], T["border"], T["t3"], size=10.5))
    return "".join(s), 56


def callout(T, x, y, w, h, title, body_lines, sample_fn=None):
    s = [rect(x, y, w, h, T["panel"], rx=12, stroke=T["border"])]
    s.append(rect(x, y, 3, h, T["accent"], rx=2))
    s.append(text(x + 18, y + 26, title, 12.5, T["t1"], w=700))
    yy = y + 46
    if sample_fn:
        s.append(sample_fn(T, x + 18, yy))
        yy += 40
    for ln in body_lines:
        s.append(text(x + 18, yy, ln, 11, T["t3"]))
        yy += 17
    return "".join(s)


def sample_breadcrumb(T, x, y):
    cr, _ = K.crumb(T, x + 8, y + 16, "ksquad-console", "Tickets")
    return cr


def sample_subnav(T, x, y):
    # 6 tabs (Overview · Build · Files · Tickets · Runs · Discussion) — scaled to fit the callout
    inner = K.build_subnav(T, 0, 0, 460, "tickets")
    return f'<g transform="translate({x},{y-12}) scale(0.84)">{inner}</g>'


def build_content(T):
    s = []
    # title band
    s.append(text(260, 90, "Navigation IA — Project-rooted hierarchy", 20, T["t1"], w=700))
    s.append(text(260, 110, "The console is organized by a selected Project, not a flat screen list. "
                            "Dashboard + Overview stay global; everything under Project is scoped to it.",
                  12, T["t3"]))
    s.append(rect(260, 122, 1164, 1, T["border"]))

    lx, lw = 260, 700
    top = 140

    # GLOBAL group
    g_rows = [
        (K.ic_dashboard, "Dashboard", "screen 8.8", "global", "fleet health · consumption · live agent↔task↔project map", False, 46),
        (K.ic_overview, "Overview", "screen 8.1", "global", "squad status · active agents · recent activity", False, 46),
        (K.ic_agents, "Agents", "8.10 / 8.11", "global", "org diagram + agent detail — filterable by squad / project", False, 46),
    ]
    c1, h1 = group_card(T, lx, top, lw, "GLOBAL", "fleet & squad — not project-scoped", g_rows)
    s.append(c1)

    # PROJECT group (root context) — selector then sub-items
    py = top + h1 + 18
    p_rows = [
        (K.ic_build, "Build", "screen 8.7", "project", "build browser — checkout→review→fix→test→publish", True, 42),
        (K.ic_files, "Files", "screen 19", "new", "file explorer — browse & visualize project files", True, 42),
        (K.ic_tickets, "Tickets", "screen 8.14", "new", "work-item tree — parents → sub-tickets", True, 42),
        (K.ic_runs, "Runs", "screen 8.2", "project", "run stream (SSE) + run history", True, 42),
        (K.ic_discussion, "Discussion", "screen 10.3", "project", "coordination room — threaded record", True, 42),
    ]
    # custom card so we can put the selector at the top
    pbody = sum(r[6] for r in p_rows)
    ph = 48 + 56 + pbody + 12
    s.append(rect(lx, py, lw, ph, T["card"], rx=13, stroke=T["accent"] + "44"))
    s.append(text(lx + 18, py + 26, "PROJECT", 12.5, T["accent2"], w=700, ls="0.6"))
    s.append(text(lx + 18 + 7 * 8 + 14, py + 26, "root context — the selector scopes the four sub-sections", 10.5, T["t4"]))
    s.append(rect(lx + 14, py + 40, lw - 28, 1, T["divider"]))
    sel, selh = selector_row(T, lx + 6, py + 48, lw - 12)
    s.append(sel)
    ry = py + 48 + selh
    # spine down the sub-items
    s.append(line(lx + 22, ry + 4, lx + 22, ry + len(p_rows) * 42 - 20, T["accent"] + "66", sw=1.5))
    for icon, label, screen, scope, note, indent, rh in p_rows:
        s.append(node_row(T, lx + 6, ry, lw - 12, icon, label, screen, scope, note, indent))
        ry += rh

    # SETTINGS group
    sy = py + ph + 18
    st_rows = [
        (K.ic_config, "Configuration", "screen 8.12", "global", "OTelConfig CRD + platform settings", False, 46),
        (K.ic_creds, "Credentials", "screen 8.6", "global", "credential / auth state per runtime", False, 46),
    ]
    c3, h3 = group_card(T, lx, sy, lw, "SETTINGS", "platform configuration", st_rows)
    s.append(c3)

    # ---- right column: pattern callouts -------------------------------------
    rx, rw = 992, 432
    ry = 140
    s.append(callout(T, rx, ry, rw, 118, "Project context selector",
                     ["Top-of-rail dropdown sets the active Project.",
                      "Clicking the name loads the project dashboard",
                      "(screen 19) on the main frame; the chevron",
                      "switches project and re-scopes every sub-section."]))
    ry += 134
    s.append(callout(T, rx, ry, rw, 118, "Breadcrumb  —  Project › section",
                     ["Always shows the Project root then the current",
                      "section. The Project chip is a quick-switch."],
                     sample_fn=sample_breadcrumb))
    ry += 134
    s.append(callout(T, rx, ry, rw, 118, "Project sub-navigation",
                     ["Overview (dashboard) · Build · Files · Tickets ·",
                      "Runs · Discussion — a tab strip mirrored as the",
                      "indented rail sub-items."],
                     sample_fn=sample_subnav))
    ry += 134
    s.append(callout(T, rx, ry, rw, 96, "Scoping rule",
                     ["Global (Dashboard, Overview, Agents, Settings)",
                      "read across the fleet. Everything under Project",
                      "is filtered to project_id — mirrors the CRD model."]))

    # footer
    s.append(text(260, 884, "IA / nav only — existing screen content (8.1–8.12) is unchanged; App Router nested layouts re-wrap it.  "
                            "Realizes CEO 2026-08-12 directive · Stories 8.13 + 8.14.", 11, T["t4"]))
    return "".join(s)


def build(T):
    return (K.build_rail_ia(T, active="project") + K.build_header(
        T, "ksquad-console", "Navigation", "Information architecture · Project-rooted hierarchy")
        + build_content(T))


if __name__ == "__main__":
    K.write_pair("13-nav-ia", build)
