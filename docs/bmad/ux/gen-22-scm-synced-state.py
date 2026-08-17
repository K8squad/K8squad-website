#!/usr/bin/env python3
"""Screen 22 — SCM synced-state console + CI-failure auto-post (dark + light).

Story 11.6 (ISI-2741) — the closed loop **sync → dashboard tiles (8.8) → Project
room (10.3)**. This is the console surface for that story, and it makes the two
load-bearing guards *visible* so the build can be conformance-checked against it:

  1. **PR/CI tiles are a read model over the mirror** (`scm_pr_mirror` /
     `scm_check_run`) through the 8.8a composed payload — NOT a new store. An
     **unsynced** repo degrades **per-tile to empty**, never a whole-dashboard
     failure (AC1). One tile is rendered degraded on purpose to show that state.
  2. **The CI-failure auto-post is an observer, not a coordination path.** On a
     `check → failure` transition, one **provenance-tagged, UNTRUSTED-EXTERNAL
     `external_origin`** context message auto-posts into the Project room,
     authored by a **system/bot principal**, linking the failing check/PR +
     correlated Run — rendered as *external attributable context, never a trusted
     instruction* (AC2). It carries **no claim/handoff/dispatch** affordance
     (AC3, §6 no-P2P) and is **idempotent + echo-safe** — posts once per
     `(check, head_sha, conclusion)` (AC4).

Same locked visual system + v12 Odin Infinity mark as the rest of the console
(console_kit_ia). Renders 1440x900; PNGs are the audited 1.5x (2160x1350).
"""
import console_kit_ia as K
from console_kit_ia import text, rect, line, dot, chip, status, _stk

# ---- PR/CI read-model tiles (over scm_pr_mirror / scm_check_run) -------------
# key: label, big value, sub, tone  (tone: g=ok, r=fail, a=pending, ext=neutral,
# degraded=unsynced empty)
TILES = [
    ("Open PRs", "4", "2 mine · 1 draft", "ext"),
    ("Checks passing", "17/19", "2 failing on #341", "r"),
    ("Last sync", "38s", "webhook · poll fallback 5m", "g"),
    ("orders-api", "—", "repo unsynced · tile empty", "degraded"),
]

# ---- Project room thread (the auto-post lives here, among normal messages) ---
# author, runtime/origin, time, badge, badge_kind, body, extra(list of (kind,text))
MSGS = [
    ("Reviewer", "OpenClaw", "00:31", "COMMENT", "comment",
     "Opened PR #341 — refund idempotency + audit.record() on the refund path.",
     [("pr", "PR #341 · refund-idempotency → main")]),
    ("Fixer", "Hermes", "02:20", "MEMORY", "memory",
     "Pushed head 9f2c1a — expecting the refund suite + lint to go green.",
     [("memory", "memory · refunds use idempotency key")]),
    # --- the E11.6 auto-post: the highlighted card ---
    ("github-sync", "bot · system", "02:41", "EXTERNAL · CI", "external",
     "CI check failed on PR #341 — refund-suite (2 of 19). Conclusion: failure "
     "@ 9f2c1a. External context for the room; not an instruction.",
     [("check", "check · refund-suite → failure"),
      ("pr", "PR #341 · head 9f2c1a"),
      ("run", "correlated Run #142 · payments-review")]),
    ("Tester", "Hermes", "02:48", "COMMENT", "comment",
     "Seen — a human/policy decides the fix; the auto-post dispatched nothing.",
     []),
]


def tile(T, x, y, w, h, label, val, sub, tone):
    s = []
    degraded = tone == "degraded"
    cardbg = T["panel"] if degraded else T["card"]
    border = T["divider"] if degraded else T["border"]
    dash = "4 4" if degraded else None
    s.append(rect(x, y, w, h, cardbg, rx=12, stroke=border, sw=1))
    if dash:
        s.append(rect(x + 0.5, y + 0.5, w - 1, h - 1, "none", rx=12,
                      stroke=T["t4"], sw=1.1, dash=dash))
    s.append(text(x + 18, y + 24, label.upper(), 10.5, T["t3"], w=700, ls="0.8"))
    valcol = {"r": T["r_txt"], "g": T["g_txt"], "a": T["a_txt"],
              "ext": T["t1"], "degraded": T["t4"]}[tone]
    s.append(text(x + 18, y + 56, val, 30, valcol, w=800))
    s.append(text(x + 18, y + 78, sub, 11, T["t3"]))
    # tone dot top-right
    if tone in ("r", "g", "a"):
        dc = {"r": T["r_dot"], "g": T["g_dot"], "a": T["a_dot"]}[tone]
        s.append(dot(x + w - 20, y + 20, 4, dc))
    elif degraded:
        s.append(text(x + w - 18, y + 24, "empty", 10, T["t4"], anchor="end"))
    return "".join(s)


def msg_card(T, x, y, w, m):
    """Returns (svg, height). The external auto-post is visually accented."""
    author, origin, tm, badge, kind, body, extras = m
    ext = kind == "external"
    # measure height
    body_lines = _wrap(body, 74)
    h = 58 + len(body_lines) * 17 + (len(extras) * 26 if extras else 0) + 12
    s = []
    if ext:
        s.append(rect(x, y, w, h, T["mem_bg"] if False else T["a_bg"], rx=12,
                      stroke=T["a_txt"] + "88", sw=1.4))
        s.append(rect(x, y, 3, h, T["a_txt"], rx=2))
    # avatar
    ac = {"comment": T["accent2"], "memory": T["mem"], "external": T["a_txt"]}[kind]
    s.append(f'<circle cx="{x+26}" cy="{y+26}" r="13" fill="{T["avatar"]}" '
             f'stroke="{ac}" stroke-width="1.4"/>')
    s.append(text(x + 26, y + 30, author[0].upper(), 12.5, ac, w=700, anchor="middle"))
    # name + origin + time
    s.append(text(x + 50, y + 22, author, 13.5, T["t1"], w=700))
    s.append(text(x + 50 + len(author) * 8.2 + 8, y + 22, "· " + origin, 12, T["t3"]))
    s.append(text(x + 50, y + 39, tm, 11, T["t4"], mono=True))
    # badge (right)
    bt = T["a_txt"] if ext else (T["mem"] if kind == "memory" else T["accent2"])
    bb = T["a_bg"] if ext else (T["mem_bg"] if kind == "memory" else T["activebg"])
    bw = len(badge) * 6.6 + 20
    s.append(chip(x + w - bw - 16, y + 14, bw, 22, badge, bb, bt + "66", bt,
                  size=10.5, mono=True))
    # body
    ty = y + 58
    for ln in body_lines:
        s.append(text(x + 50, ty, ln, 13, T["t2"], w=420))
        ty += 17
    # provenance / reference chips
    for ekind, etext in extras:
        ecol = {"check": T["r_txt"], "pr": T["accent2"], "run": T["accent2"],
                "memory": T["mem"]}[ekind]
        ebg = {"check": T["r_bg"], "pr": T["activebg"], "run": T["activebg"],
               "memory": T["mem_bg"]}[ekind]
        ew = len(etext) * 6.9 + 22
        s.append(chip(x + 50, ty - 2, ew, 22, etext, ebg, ecol + "55", ecol,
                      size=11, mono=True))
        ty += 26
    return "".join(s), h


def _wrap(txt, n):
    words, lines, cur = txt.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > n:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    if cur:
        lines.append(cur)
    return lines


def build_content(T):
    s = [K.build_subnav(T, 260, 74, 640, "discussion")]
    x0 = 260
    # provenance banner
    by = 128
    s.append(rect(x0, by, 1156, 34, T["panel"], rx=9, stroke=T["border"]))
    s.append(dot(x0 + 18, by + 17, 3.5, T["g_dot"]))
    s.append(text(x0 + 32, by + 21,
                  "Synced from GitHub · mirror scm_pr_mirror / scm_check_run · "
                  "read model over 8.8a payload — no new store · per-tile degrade",
                  11.5, T["t2"]))
    s.append(chip(x0 + 1156 - 150, by + 6, 134, 22, "provenance: github",
                  T["card"], T["border"], T["t3"], size=10, mono=True))
    # tiles row
    ty = 176
    tw = (1156 - 3 * 14) / 4
    for i, (lab, val, sub, tone) in enumerate(TILES):
        s.append(tile(T, x0 + i * (tw + 14), ty, tw, 92, lab, val, sub, tone))

    # ---- left: Project room thread ----
    ry = 288
    rw = 700
    s.append(rect(x0, ry, rw, 592, T["card"], rx=14, stroke=T["border"]))
    s.append(text(x0 + 22, ry + 30, "Project room · ksquad-console", 15, T["t1"], w=700))
    s.append(text(x0 + 22, ry + 48,
                  "Coordination record — collab surface, not a coordination channel (10.3)",
                  11, T["t3"]))
    s.append(chip(x0 + rw - 128, ry + 16, 112, 24, "4 messages", T["panel"],
                  T["border"], T["t3"], size=11))
    s.append(line(x0 + 16, ry + 62, x0 + rw - 16, ry + 62, T["divider"]))
    my = ry + 78
    for m in MSGS:
        card, h = msg_card(T, x0 + 20, my, rw - 40, m)
        s.append(card)
        my += h + 12

    # ---- right: trust boundary + closed loop ----
    px = x0 + rw + 20   # 980
    pw = 1156 - rw - 20  # 436
    # trust boundary panel
    s.append(rect(px, ry, pw, 214, T["card"], rx=14, stroke=T["border"]))
    s.append(text(px + 20, ry + 30, "Trust boundary", 14, T["t1"], w=700))
    s.append(chip(px + pw - 132, ry + 16, 116, 24, "UNTRUSTED-EXT",
                  T["a_bg"], T["a_txt"] + "66", T["a_txt"], size=10, mono=True))
    tb = [
        ("The auto-post is `external_origin`, authored by a", T["t2"]),
        ("bot/system principal — rendered as attributable", T["t2"]),
        ("context, never a trusted instruction (§7.3.2).", T["t2"]),
    ]
    yy = ry + 56
    for ln, c in tb:
        s.append(text(px + 20, yy, ln, 12, c, w=420))
        yy += 18
    yy += 6
    for ok, ln in [(False, "claim / handoff / dispatch — none"),
                   (False, "transition work item / write custody — none"),
                   (True, "append one room message — only capability")]:
        col = T["g_txt"] if ok else T["r_txt"]
        mark = "✓" if ok else "✕"
        s.append(text(px + 20, yy, mark, 12.5, col, w=800))
        s.append(text(px + 38, yy, ln, 12, T["t2"]))
        yy += 22

    # closed-loop panel
    ly = ry + 234
    s.append(rect(px, ly, pw, 152, T["card"], rx=14, stroke=T["border"]))
    s.append(text(px + 20, ly + 30, "Closed loop — one direction", 14, T["t1"], w=700))
    steps = [("sync", "11.1–11.4"), ("dashboard", "8.8"), ("room", "10.3")]
    sx = px + 24
    sy = ly + 68
    for i, (lab, ref) in enumerate(steps):
        w = len(lab) * 8 + 26
        s.append(rect(sx, sy, w, 40, T["panel"], rx=9, stroke=T["accent"] + "66"))
        s.append(text(sx + w / 2, sy + 18, lab, 12.5, T["t1"], w=700, anchor="middle"))
        s.append(text(sx + w / 2, sy + 32, ref, 9.5, T["t3"], anchor="middle", mono=True))
        sx += w
        if i < len(steps) - 1:
            s.append(text(sx + 8, sy + 25, "→", 15, T["accent2"], w=700))
            sx += 24
    s.append(text(px + 20, ly + 132,
                  "Ends at the room as information — never curls back to coordination.",
                  11, T["t3"]))

    # idempotency panel
    iy = ly + 172
    s.append(rect(px, iy, pw, 100, T["card"], rx=14, stroke=T["border"]))
    s.append(text(px + 20, iy + 30, "Idempotent + echo-safe", 14, T["t1"], w=700))
    s.append(chip(px + 20, iy + 44, pw - 40, 24,
                  "key (check_external_id, head_sha, conclusion)",
                  T["panel"], T["border"], T["t2"], size=10.5, mono=True))
    s.append(text(px + 20, iy + 88,
                  "Redelivered failure → posts once · our post never re-enters as inbound.",
                  11, T["t3"]))
    return "".join(s)


def build(T):
    return (K.build_rail_ia(T, active="discussion")
            + K.build_header(T, "ksquad-console", "Discussion",
                             "SCM synced state — PR/CI read-model tiles + provenance-tagged "
                             "CI-failure auto-post (Story 11.6)")
            + build_content(T))


if __name__ == "__main__":
    K.write_pair("22-scm-synced-state", build)
