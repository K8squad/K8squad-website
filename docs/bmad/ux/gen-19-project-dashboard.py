#!/usr/bin/env python3
"""Screen 19 — Project dashboard (dark + light), KSquad operator console.

CEO follow-up (Henrik, ISI-2291 review 2026-08-12): *"when clicking on the project the
UI should load the project dashboard on the main frame."* This is that landing — the
project-scoped overview shown when the Project root (rail selector) is selected. It is
the `Overview` tab of the Project sub-nav and the default main-frame content for a
selected Project.

Project-scoped: KPI tiles + quick-access cards for the five sub-sections (Build · Files
· Tickets · Runs · Discussion) + a project activity feed. Wrapped by the Project-rooted
nav rail + breadcrumb (console_kit_ia). Renders 1440x900; PNGs are the audited 1.5x.
"""
import console_kit_ia as K
from console_kit_ia import text, rect, chip, dot, line, _stk

KPIS = [  # label, value, sub, accent
    ("Open tickets", "9", "2 blocked · 4 claimed", False),
    ("Active runs", "3", "142 total · 96% ok", True),
    ("Builds", "42", "latest published", False),
    ("Files", "318", "main @ d18dc51", False),
    ("Agents on project", "6", "3 running now", False),
]

SECTIONS = [  # icon, name, desc, stat, key
    (K.ic_build, "Build", "Build browser — checkout → review → fix → test → publish", "42 builds", "build"),
    (K.ic_files, "Files", "File explorer — browse & visualize the project workspace", "318 files", "files"),
    (K.ic_tickets, "Tickets", "Work-item tree — parents → sub-tickets, status & assignee", "9 open", "tickets"),
    (K.ic_runs, "Runs", "Run stream (SSE) + run history for this project", "3 active", "runs"),
    (K.ic_discussion, "Discussion", "Coordination room — threaded, provenanced record", "12 threads", "discussion"),
]

# kind, glyph-color-key, text, when
ACTIVITY = [
    ("run", "accent2", "Run started · run-2291-c · Graphic Designer", "2m"),
    ("ticket", "accent2", "Ticket claimed · ISI-2291.2 (sub of ISI-2291)", "3m"),
    ("file", "mem", "File changed · docs/bmad/ux/console_kit_ia.py", "18m"),
    ("done", "g_dot", "Ticket done · ISI-2291.1 · Nav-rail hierarchy", "20m"),
    ("build", "accent2", "Build published · build-2291", "22m"),
    ("comment", "t3", "Comment · Henrik on ISI-2291", "1h"),
    ("config", "a_dot", "Configuration updated · OTelConfig exporter", "2h"),
]


def kpi_tile(T, x, y, w, label, value, sub, accent):
    s = [rect(x, y, w, 88, T["card"], rx=12, stroke=(T["accent"] + "55") if accent else T["border"])]
    if accent:
        s.append(rect(x, y, 3, 88, T["accent"], rx=2))
    s.append(text(x + 18, y + 30, label, 11, T["t3"], w=600, ls="0.3"))
    s.append(text(x + 18, y + 60, value, 26, T["t1"], w=700))
    if accent:
        s.append(dot(x + 18 + len(value) * 16 + 14, y + 52, 4, T["g_dot"], pulse=True))
    s.append(text(x + 18, y + 78, sub, 10.5, T["t4"]))
    return "".join(s)


def section_card(T, x, y, w, icon, name, desc, stat):
    s = [rect(x, y, w, 74, T["card"], rx=12, stroke=T["border"])]
    s.append(rect(x + 14, y + 20, 34, 34, T["panel"], rx=9, stroke=T["border"]))
    s.append(icon(x + 31, y + 37, T["accent2"]))
    s.append(text(x + 62, y + 32, name, 14, T["t1"], w=700))
    s.append(text(x + 62, y + 51, desc, 10.8, T["t3"]))
    s.append(chip(x + w - 108, y + 20, 92, 22, stat, T["panel"], T["border"], T["t2"], size=10))
    s.append(text(x + w - 108, y + 58, "open →", 11, T["accent2"], w=600))
    return "".join(s)


def activity_row(T, x, y, w, kind, ckey, body, when):
    s = []
    c = T[ckey]
    s.append(rect(x, y, 26, 26, T["panel"], rx=7, stroke=T["border"]))
    cx, cy = x + 13, y + 13
    if kind == "run":
        s.append(f'<path d="M{cx-4} {cy-4} l7 4 l-7 4 z" fill="{c}"/>')
    elif kind == "done":
        s.append(f'<path d="M{cx-4} {cy} l3 3 l5 -6" {_stk(c,1.7)}/>')
    elif kind == "file":
        s.append(K.ic_files(cx, cy, c))
    elif kind == "build":
        s.append(K.ic_build(cx, cy, c))
    elif kind == "discussion" or kind == "comment":
        s.append(K.ic_discussion(cx, cy, c))
    elif kind == "config":
        s.append(K.ic_config(cx, cy, c))
    else:  # ticket
        s.append(K.ic_tickets(cx, cy, c))
    s.append(text(x + 38, y + 12, body, 11.8, T["t2"]))
    s.append(text(x + w - 4, y + 12, when, 10, T["t4"], anchor="end"))
    return "".join(s)


def build_content(T):
    s = []
    s.append(K.build_subnav(T, 260, 74, 540, "overview"))
    s.append(text(1416, 92, "project_id = ksquad-console · project-scoped landing (default main frame)",
                  10.5, T["t4"], anchor="end"))

    # KPI tiles
    x, y, gap = 260, 120, 16
    tw = (1164 - gap * (len(KPIS) - 1)) / len(KPIS)
    for label, value, sub, accent in KPIS:
        s.append(kpi_tile(T, x, y, tw, label, value, sub, accent))
        x += tw + gap

    # two columns
    col_y = 236
    lx, lw = 260, 690
    rx, rw = 966, 458
    s.append(text(lx, col_y, "PROJECT SECTIONS", 11, T["t3"], w=700, ls="0.8"))
    s.append(text(lx + 168, col_y, "the selected project expands to these — click any to enter",
                  10.5, T["t4"]))
    cy = col_y + 16
    for icon, name, desc, stat, key in SECTIONS:
        s.append(section_card(T, lx, cy, lw, icon, name, desc, stat))
        cy += 86

    s.append(text(rx, col_y, "RECENT ACTIVITY", 11, T["t3"], w=700, ls="0.8"))
    s.append(chip(rx + 148, col_y - 14, 84, 20, "live · SSE", T["panel"], T["border"], T["t4"], size=9.5))
    s.append(rect(rx, col_y + 16, rw, 430, T["card"], rx=12, stroke=T["border"]))
    ay = col_y + 40
    for i, (kind, ckey, body, when) in enumerate(ACTIVITY):
        if i:
            s.append(rect(rx + 16, ay - 14, rw - 32, 1, T["divider"]))
        s.append(activity_row(T, rx + 16, ay, rw - 32, kind, ckey, body, when))
        ay += 52
    # a small "files touched" footer inside the activity card ties to the file explorer
    s.append(rect(rx + 16, ay - 14, rw - 32, 1, T["divider"]))
    s.append(text(rx + 16, ay + 4, "Recent: console_kit_ia.py · gen-14 · gen-19", 10, T["t4"]))
    s.append(text(rx + rw - 16, ay + 4, "open Files →", 10.5, T["accent2"], w=600, anchor="end"))

    s.append(text(260, 884, "Loaded when the Project root is selected in the rail — the default main-frame view for a project.  "
                            "Everything here is scoped to ksquad-console.  Realizes CEO 2026-08-12 follow-up.",
                  11, T["t4"]))
    return "".join(s)


def build(T):
    return (K.build_rail_ia(T, active="project") + K.build_header(
        T, "ksquad-console", "Overview", "Project dashboard · everything scoped to ksquad-console")
        + build_content(T))


if __name__ == "__main__":
    K.write_pair("19-project-dashboard", build)
