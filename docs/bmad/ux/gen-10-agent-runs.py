#!/usr/bin/env python3
"""Generate screen 10 (11th console screen) — Agent detail: Run history + logs
(dark + light), KSquad operator console.

CEO requirement (Henrik, 2026-08-11 · ISI-2162): the agent-detail page must show
Run history + logs in the Paperclip pattern —
  · a Run list with status / duration / tokens, and
  · per-Run drill-down to tabbed logs: task/work-item · tool-call · LLM (prompt/
    response + token counts) · build output (links to the build browser) · error
    traces, with a live SSE log tail on the active Run and an OTel-trace link per Run.

Reached by click-through from the team-organization diagram (screen 09 · ISI-2161)
and the Agents rail entry. Renders 1440x900 SVG; PNGs are the audited 1.5x via resvg.
"""
from console_kit import (DARK, LIGHT, status, text, rect, dot, chip,
                         build_rail, build_header, write_pair, F, FM)

# ---- identity card ----------------------------------------------------------
def identity(T):
    x, y, w, h = 260, 84, 1156, 84
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    s.append(f'<circle cx="{x+40}" cy="{y+42}" r="24" fill="{T["accent"]}22" stroke="{T["accent"]}66"/>')
    s.append(text(x + 40, y + 49, "R", 20, T["accent2"], w=700, anchor="middle"))
    s.append(text(x + 78, y + 34, "Reviewer", 18, T["t1"], w=700))
    # status pill inline with name
    d, txt, bg, bd = status(T, "running")
    s.append(rect(x + 176, y + 18, 96, 24, bg, rx=12, stroke=bd))
    s.append(dot(x + 192, y + 30, 3.8, d, pulse=True))
    s.append(text(x + 206, y + 34, "Running", 11.5, txt, w=600))
    # chips row
    cx = x + 78
    for label, mono in [("Claude Code · sandboxed", False), ("ns: team-payments", True),
                        ("role: Reviewer", False), ("role: Approver", False),
                        ("read-only · Team-scoped", False)]:
        cw = 16 + len(label) * (6.6 if mono else 6.4)
        s.append(chip(cx, y + 48, cw, 20, label, T["panel"], T["border"], T["t2"], size=10.5, mono=mono))
        cx += cw + 8
    # right-side quick stats
    stats = [("RUNS", "142"), ("SUCCESS", "96%"), ("TOKENS · 24h", "1.2M")]
    sx = x + w - 20
    for label, val in reversed(stats):
        s.append(text(sx, y + 34, val, 20, T["t1"], w=700, anchor="end"))
        s.append(text(sx, y + 52, label, 9.5, T["t4"], w=600, ls="0.5", anchor="end"))
        sx -= 130
    return "".join(s)


# ---- run history (left panel) ----------------------------------------------
def run_history(T):
    x, y, w, h = 260, 184, 356, 692
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    s.append(text(x + 20, y + 30, "Run history", 14, T["t1"], w=700))
    s.append(text(x + w - 20, y + 30, "142 total", 11, T["t4"], w=600, anchor="end"))
    s.append(rect(x + 16, y + 44, w - 32, 1, T["divider"]))
    runs = [  # status, id, when, duration, tokens, note, selected
        ("running", "#142", "now", "03:12", "48.2k", "work item #88", True),
        ("succeeded", "#141", "18m ago", "04:36", "72.1k", "work item #85", False),
        ("succeeded", "#140", "1h ago", "02:05", "35.7k", "work item #84", False),
        ("paused", "#139", "3h ago", "—", "31.0k", "token expired", False),
        ("failed", "#138", "2h ago", "01:12", "9.4k", "retry 2/3", False),
        ("succeeded", "#137", "5h ago", "06:20", "88.4k", "work item #79", False),
        ("succeeded", "#135", "yesterday", "03:44", "51.7k", "work item #76", False),
        ("succeeded", "#131", "yesterday", "05:02", "63.9k", "work item #71", False),
    ]
    ry = y + 58
    rh = 76
    for st, rid, when, dur, tok, note, sel in runs:
        d, txt, bg, bd = status(T, st)
        if sel:
            s.append(rect(x + 12, ry, w - 24, rh - 8, T["activebg"], rx=10, stroke=T["accent"]))
            s.append(rect(x + 12, ry, 3, rh - 8, T["accent"], rx=2))
        else:
            s.append(rect(x + 12, ry, w - 24, rh - 8, T["panel"], rx=10, stroke=T["border"]))
        # status pill
        label = st.capitalize()
        pw = 26 + len(label) * 6.4
        s.append(rect(x + 26, ry + 14, pw, 20, bg, rx=10, stroke=bd))
        s.append(dot(x + 37, ry + 24, 3.2, d, pulse=(st == "running")))
        s.append(text(x + 46, ry + 28, label, 10.5, txt, w=600))
        s.append(text(x + 26 + pw + 12, ry + 28, rid, 13, T["t1"], w=700, mono=True))
        s.append(text(x + w - 26, ry + 28, when, 10, T["t4"], anchor="end"))
        # meta line: duration · tokens · note
        s.append(text(x + 26, ry + 52, f"⏱ {dur}", 10.5, T["t3"], mono=True))
        s.append(text(x + 120, ry + 52, f"{tok} tok", 10.5, T["t3"], mono=True))
        s.append(text(x + w - 26, ry + 52, note, 10, T["t4"], anchor="end"))
        ry += rh
    return "".join(s)


# ---- run detail (right panel) ----------------------------------------------
KIND = {  # label -> (bg_token, border_token, text_token)   neutral for tools/llm/build
    "TASK":  ("accent_tint", "accent_bd", "accent2"),
    "TOOL":  ("panel", "border", "t3"),
    "LLM":   ("panel", "border", "accent2"),
    "BUILD": ("panel", "border", "t2"),
    "NOTE":  ("panel", "border", "accent2"),
    "MEM":   ("mem_bg", "mem_bd", "mem"),
    "ERROR": ("err_bg", "err_bd", "err_tx"),
}


def kind_chip(T, x, y, label):
    bgmap = dict(accent_tint=T["accent"] + "1F", panel=T["panel"], mem_bg=T["mem_bg"], err_bg=T["r_bg"])
    bdmap = dict(accent_bd=T["accent"] + "44", border=T["border"], mem_bd=T["mem"] + "55", err_bd=T["r_dot"] + "55")
    txmap = dict(accent2=T["accent2"], t3=T["t3"], t2=T["t2"], mem=T["mem"], err_tx=T["r_txt"])
    bgk, bdk, txk = KIND[label]
    w = 12 + len(label) * 7.2
    return (rect(x, y, w, 18, bgmap[bgk], rx=5, stroke=bdmap[bdk]) +
            text(x + 6, y + 13, label, 9.5, txmap[txk], w=700, ls="0.3"))


def run_detail(T):
    x, y, w, h = 632, 184, 784, 692
    s = [rect(x, y, w, h, T["card"], rx=12, stroke=T["border"])]
    # ---- header ----
    s.append(text(x + 24, y + 34, "Run #142", 18, T["t1"], w=700))
    d, txt, bg, bd = status(T, "running")
    s.append(rect(x + 130, y + 18, 132, 24, bg, rx=12, stroke=bd))
    s.append(dot(x + 146, y + 30, 3.8, d, pulse=True))
    s.append(text(x + 160, y + 34, "Running · SSE", 11, txt, w=600))
    s.append(text(x + 24, y + 54, "Reviewer · work item #88 · payments-service", 11.5, T["t3"]))
    # right meta + OTel trace link
    s.append(text(x + w - 24, y + 30, "03:12 · 48.2k tok · claude-opus-4", 11.5, T["t2"], w=600, mono=True, anchor="end"))
    s.append(text(x + w - 24, y + 50, "Open OTel trace  ↗", 11, T["accent2"], w=600, anchor="end"))
    s.append(text(x + w - 24, y + 66, "trace 7f3a…c1  ·  span refund-review", 9.5, T["t4"], mono=True, anchor="end"))
    s.append(rect(x + 24, y + 78, w - 48, 1, T["divider"]))
    # ---- tab bar ----
    tabs = [("All", 15, True), ("Task", 1, False), ("Tool calls", 4, False),
            ("LLM", 4, False), ("Build", 2, False), ("Errors", 1, False)]
    tx = x + 24
    ty = y + 100
    for label, cnt, active in tabs:
        lbl = f"{label} · {cnt}"
        tw = 20 + len(lbl) * 6.6
        if active:
            s.append(rect(tx, ty - 16, tw, 26, T["accent"] + "1F", rx=8, stroke=T["accent"] + "55"))
            s.append(text(tx + tw / 2, ty + 2, lbl, 11.5, T["accent2"], w=700, anchor="middle"))
        else:
            s.append(text(tx + tw / 2, ty + 2, lbl, 11.5, T["t3"], w=500, anchor="middle"))
        tx += tw + 10
    # token summary strip (prompt/completion)
    s.append(text(x + w - 24, ty + 2, "▲ 8.6k prompt   ▼ 2.2k completion", 10.5, T["t4"], mono=True, anchor="end"))
    s.append(rect(x + 24, y + 126, w - 48, 1, T["divider"]))
    # ---- log body ----
    log = [  # ts, kind, message, right (tokens/latency)
        ("02:41:08", "TASK", "checked out work item #88 · verify refund idempotency", ""),
        ("02:41:10", "LLM", "claude-opus-4 · plan approach", "▲1,204 ▼388 · 1.9s"),
        ("02:41:12", "TOOL", "Read  src/payments/refund.ts", "142 lines"),
        ("02:41:13", "TOOL", "Grep  \"idempotencyKey\"  · 4 matches", ""),
        ("02:42:02", "LLM", "claude-opus-4 · draft patch", "▲2,510 ▼742 · 3.1s"),
        ("02:42:20", "TOOL", "Edit  src/payments/refund.ts", "+42 −11"),
        ("02:42:48", "BUILD", "build refund-fix #b91 queued  → Build browser", ""),
        ("02:43:31", "BUILD", "build #b91 · tests 41/42 passed", "3m 06s"),
        ("02:43:31", "ERROR", "AssertionError: refund not idempotent on retry", ""),
        ("", "", "    at refund.spec.ts:88:12  →  duplicate ledger entry", ""),
        ("02:43:40", "LLM", "claude-opus-4 · analyze failure", "▲3,180 ▼596 · 2.4s"),
        ("02:43:58", "TOOL", "Edit  src/payments/refund.ts", "+7 −2"),
        ("02:44:06", "MEM", "recorded: refund idempotency contract (knowledge record)", ""),
        ("02:44:10", "NOTE", "posted finding to coordination record · work item #88", ""),
        ("02:44:12", "LLM", "claude-opus-4 · re-verify idempotency …", "▲920 ▼— · streaming"),
    ]
    ly = y + 152
    step = 33
    bx = x + 24
    for i, (ts, kind, msg, right) in enumerate(log):
        streaming = right.endswith("streaming")
        if ts:
            s.append(text(bx, ly + 12, ts, 10, T["t4"], mono=True))
        cxx = bx + 66
        if kind:
            s.append(kind_chip(T, cxx, ly, kind))
        # message
        is_stack = not ts and not kind
        mcol = T["t4"] if is_stack else T["t2"]
        s.append(text(bx + 158, ly + 12, msg, 11 if not is_stack else 10, mcol, mono=True,
                      w=600 if kind in ("ERROR",) else 400))
        # streaming live head
        if streaming:
            s.append(dot(bx + 158 + len(msg) * 6.2 + 8, ly + 8, 3.4, T["g_dot"], pulse=True))
        # right column
        if right:
            rc = T["mem"] if kind == "LLM" else T["t4"]
            s.append(text(x + w - 24, ly + 12, right, 9.5, rc, mono=True, anchor="end"))
        ly += step
    # live tail footer
    s.append(rect(x + 24, y + h - 44, w - 48, 1, T["divider"]))
    s.append(dot(x + 34, y + h - 26, 3.6, T["g_dot"], pulse=True))
    s.append(text(x + 48, y + h - 22, "live SSE log tail — streaming while the Run is active", 10.5, T["t3"]))
    s.append(text(x + w - 24, y + h - 22, "Download run log  →", 10.5, T["accent2"], w=600, anchor="end"))
    s.append(text(x + w - 190, y + h - 22, "status & kill live in Run controls  ·", 10, T["t4"], anchor="end"))
    return "".join(s)


def build(T):
    return (build_rail(T, "agents") +
            build_header(T, "Agent detail", "Agents / Reviewer · Run history + logs · read-only, Team-scoped — status & kill stay in Run controls") +
            identity(T) + run_history(T) + run_detail(T))


if __name__ == "__main__":
    write_pair("10-agent-runs", build)
