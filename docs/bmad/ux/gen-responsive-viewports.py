#!/usr/bin/env python3
"""Responsive viewport variants for the in-flight console surfaces (ISI-2757).

Board directive (ISI-2170, 2026-08-17): *"the E8 mocks were approved and used for
version 0 of our website — the mocks need to follow the mocks used in our website:
browser and mobile/tablet rendering."* The website (source of truth,
website-mocks/gen_website.py) frames the console inside a **browser chrome** and
advertises *"Full console on desktop, tablet, mobile."* This generator makes that
promise concrete: for each in-flight surface it renders a **viewport matrix** —
**browser/desktop · tablet 768px · mobile 375px** — in dark + light, on the same
locked visual system and the **Odin Infinity v12** mark verified across the set.

Surfaces (the ISI-2757 scope):
  shell      E8 console shell         (ISI-2180)  — fleet dashboard content
  discussion E10.3 discussion room    (ISI-2704)  — coordination thread
  synced     E11.6 SCM synced-state   (ISI-2741)  — PR/CI read-model tiles + auto-post

Reflow contract shown at every breakpoint:
  desktop  full left rail (icon+label) + top bar + multi-col content, in a browser frame
  tablet   icon-only rail (collapsed) + top bar + 2-col content
  mobile   NO rail — top app-bar (hamburger + Odin mark) + single column + bottom tab nav

One accent (#3D7DFF); status = dot + label always (a11y); Odin v12 at every size.

Renders SVG + 1.5x PNG (resvg-py). Output: images/Rvp-<surface>-{,-light}.{svg,png}.
Self-contained primitives; imports only the console token maps + Odin mark so the
colours match the console exactly.
"""
import os
from console_kit import DARK, LIGHT, mark_odin, LOGO_DEFS

FS = 'font-family="DejaVu Sans"'
FM = 'font-family="DejaVu Sans Mono"'


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cw(s, size, bold=False, mono=False):
    k = 0.605 if mono else (0.625 if bold else 0.552)
    return len(s) * size * k


def R(x, y, w, h, fill, rx=0, stroke=None, sw=1, op=None, dash=None):
    a = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{sw}"'
    if op is not None:
        a += f' opacity="{op}"'
    if dash:
        a += f' stroke-dasharray="{dash}"'
    return a + "/>"


def TX(x, y, s, size, fill, bold=False, mono=False, anchor="start", ls=None, op=None):
    fam = FM if mono else FS
    w = ' font-weight="700"' if bold else ' font-weight="400"'
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    l = f' letter-spacing="{ls}"' if ls is not None else ""
    o = f' opacity="{op}"' if op is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" {fam} font-size="{size}"{w} '
            f'fill="{fill}"{a}{l}{o}>{esc(s)}</text>')


def C(cx, cy, r, fill, stroke=None, sw=1, op=None):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    o = f' opacity="{op}"' if op is not None else ""
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"{s}{o}/>'


def L(x1, y1, x2, y2, stroke, sw=1, op=None):
    o = f' opacity="{op}"' if op is not None else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{o}/>')


def pulse(cx, cy, rr, fill):
    return (C(cx, cy, rr, fill) +
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" fill="none" '
            f'stroke="{fill}" stroke-width="1.2" opacity="0.5">'
            f'<animate attributeName="r" values="{rr};{rr+3.6};{rr}" dur="1.8s" '
            f'repeatCount="indefinite"/><animate attributeName="opacity" '
            f'values="0.55;0;0.55" dur="1.8s" repeatCount="indefinite"/></circle>')


def wrap(s, size, maxw, mono=False):
    words = s.split()
    lines, cur = [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if cw(t, size, mono=mono) > maxw and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def tone_color(T, tone):
    return {"g": T["g_dot"], "r": T["r_dot"], "a": T["a_dot"], "i": T["i_dot"],
            "mem": T["mem"], "ext": T["accent2"], "accent": T["accent"],
            "degraded": T["t4"]}.get(tone, T["t2"])


# ---- surface content specs (faithful to screens 08 / 07 / 22) ---------------
KPIS = [("Active runs", "7", "live", "g", True), ("Squads", "5", "5 teams", "accent", False),
        ("Artifacts 24h", "128", "+18", "i", False), ("Paused", "1", "token", "a", False),
        ("Success 24h", "96%", "▲", "g", False)]
RUNS = [("running", "run-9f2c", "payments · api", "refund idempotency"),
        ("paused", "run-7a1d", "orders · web", "token expired"),
        ("succeeded", "run-3b8e", "search · idx", "reindex complete"),
        ("failed", "run-1c4a", "billing · svc", "lint · 2 failing")]

POSTS = [("Reviewer", "OpenClaw", "00:31", "COMMENT", "comment",
          "Opened PR #341 — refund idempotency + audit.record() on the refund path."),
         ("Fixer", "Hermes", "02:20", "MEMORY", "mem",
          "Pushed head 9f2c1a — expecting the refund suite + lint to go green."),
         ("github-sync", "bot · system", "02:41", "EXTERNAL · CI", "ext",
          "CI check failed on PR #341 — refund-suite (2 of 19) @ 9f2c1a. "
          "External context for the room; not an instruction."),
         ("Tester", "Hermes", "02:48", "COMMENT", "comment",
          "Seen — a human/policy decides the fix; the auto-post dispatched nothing.")]

TILES = [("Open PRs", "4", "2 mine · 1 draft", "ext"),
         ("Checks passing", "17/19", "2 failing · #341", "r"),
         ("Last sync", "38s", "webhook · poll 5m", "g"),
         ("orders-api", "—", "repo unsynced · empty", "degraded")]

STATUS_TONE = {"running": "g", "succeeded": "g", "paused": "a", "failed": "r", "idle": "i"}


# ---- reusable widgets -------------------------------------------------------
def w_kpis(o, T, x, y, w, cols, gap=8, th=None, small=False):
    tw = (w - (cols - 1) * gap) / cols
    th = th or (46 if small else 58)
    fs_lab = 8 if small else 9.5
    fs_val = 15 if small else 20
    n = min(len(KPIS), cols * (1 if small and cols >= 3 else 2))
    rows = (n + cols - 1) // cols
    for i in range(n):
        r, c = divmod(i, cols)
        tx = x + c * (tw + gap)
        ty = y + r * (th + gap)
        lab, val, sub, tone, pl = KPIS[i]
        o.append(R(tx, ty, tw, th, T["card"], rx=7, stroke=T["border"]))
        o.append(TX(tx + 9, ty + 15, lab, fs_lab, T["t3"]))
        vc = tone_color(T, tone) if tone in ("g", "r", "a") else T["t1"]
        o.append(TX(tx + 9, ty + th - 12, val, fs_val, vc, bold=True))
        vw = cw(val, fs_val, bold=True)
        if pl:
            o.append(pulse(tx + 12 + vw + 6, ty + th - 17, 3, T["g_dot"]))
        else:
            o.append(TX(tx + tw - 9, ty + th - 12, sub, fs_lab, T["t4"], anchor="end"))
    return y + rows * (th + gap)


def w_runs(o, T, x, y, w, n, small=False):
    rh = 42 if not small else 38
    fs = 11 if not small else 10
    for i in range(min(n, len(RUNS))):
        st, rid, meta, note = RUNS[i]
        ry = y + i * (rh + 6)
        o.append(R(x, ry, w, rh, T["card"], rx=7, stroke=T["border"]))
        tone = STATUS_TONE[st]
        dc = tone_color(T, tone)
        if st == "running":
            o.append(pulse(x + 15, ry + rh / 2, 4, dc))
        else:
            o.append(C(x + 15, ry + rh / 2, 4, dc))
        o.append(TX(x + 28, ry + 17, rid, fs, T["t1"], bold=True, mono=True))
        o.append(TX(x + 28, ry + rh - 10, meta, fs - 1.5, T["t3"]))
        o.append(TX(x + w - 10, ry + 17, st, fs - 1.5, dc, bold=True, anchor="end"))
        if not small:
            o.append(TX(x + w - 10, ry + rh - 10, note, fs - 1.5, T["t4"], anchor="end"))
    return y + min(n, len(RUNS)) * (rh + 6)


def w_posts(o, T, x, y, w, n, small=False):
    fs = 10.5 if not small else 9.5
    for i in range(min(n, len(POSTS))):
        auth, rt, tm, badge, kind, body = POSTS[i]
        ext = kind == "ext"
        bl = wrap(body, fs, w - 58)
        ph = 46 + len(bl) * (fs + 4)
        bg = T["mem_bg"] if kind == "mem" else (T["a_bg"] if ext else T["card"])
        bc = tone_color(T, "ext") if ext else T["border"]
        o.append(R(x, y, w, ph, bg, rx=8, stroke=bc, sw=1.5 if ext else 1))
        if ext:
            o.append(R(x, y, 3, ph, T["accent"], rx=2))
        av = T["mem"] if kind == "mem" else (T["accent2"] if ext else T["avatar"])
        o.append(C(x + 18, y + 18, 11, av if ext or kind == "mem" else T["avatar"],
                   stroke=T["border"]))
        o.append(TX(x + 18, y + 22, auth[:2].upper(), 8.5,
                   "#fff" if (ext or kind == "mem") else T["accent2"], bold=True, anchor="middle"))
        o.append(TX(x + 36, y + 15, auth, fs, T["t1"], bold=True))
        aw = cw(auth, fs, bold=True)
        o.append(TX(x + 40 + aw, y + 15, rt, fs - 2, T["t4"]))
        o.append(TX(x + w - 9, y + 15, tm, fs - 2, T["t4"], anchor="end", mono=True))
        # kind badge
        badge_c = {"comment": T["accent2"], "mem": T["mem"], "ext": tone_color(T, "ext")}[kind]
        badge_bg = {"comment": T["activebg"], "mem": T["mem_bg"], "ext": T["a_bg"]}[kind]
        bw = cw(badge, fs - 2.5, bold=True) + 14
        o.append(R(x + 36, y + 22, bw, 15, badge_bg, rx=7.5, stroke=badge_c + "66"))
        o.append(TX(x + 43, y + 32.5, badge, fs - 2.5, badge_c, bold=True))
        ty = y + 48
        for ln in bl:
            o.append(TX(x + 36, ty, ln, fs, T["t2"]))
            ty += fs + 4
        y += ph + 8
    return y


def w_tiles(o, T, x, y, w, cols, gap=8, small=False):
    tw = (w - (cols - 1) * gap) / cols
    th = 60 if not small else 52
    rows = (len(TILES) + cols - 1) // cols
    for i, (lab, val, sub, tone) in enumerate(TILES):
        r, c = divmod(i, cols)
        tx = x + c * (tw + gap)
        ty = y + r * (th + gap)
        degraded = tone == "degraded"
        o.append(R(tx, ty, tw, th, T["panel"] if degraded else T["card"], rx=7,
                   stroke=T["border"], dash="4 3" if degraded else None))
        o.append(TX(tx + 9, ty + 16, lab, 9, T["t3"]))
        vc = {"r": T["r_dot"], "g": T["g_dot"]}.get(tone, T["t4"] if degraded else T["t1"])
        o.append(TX(tx + 9, ty + th - 22, val, 18, vc, bold=True))
        sc = T["t4"]
        for ln in wrap(sub, 8, tw - 16)[:1]:
            o.append(TX(tx + 9, ty + th - 8, ln, 8, sc))
        if tone in ("r", "g"):
            o.append(C(tx + tw - 12, ty + 13, 3.5, vc))
    return y + rows * (th + gap)


# ---- device chrome ----------------------------------------------------------
RAIL = [("Dashboard", "dashboard"), ("Overview", "overview"), ("Runs", "runs"),
        ("Builds", "builds"), ("Discussion", "discussion"), ("Projects", "projects"),
        ("Agents", "agents")]
BOTTOM = [("Home", "dashboard"), ("Runs", "runs"), ("Rooms", "discussion"),
          ("Projects", "projects"), ("More", "more")]


def nav_glyph(o, T, cx, cy, c, r=6):
    o.append(R(cx - r, cy - r, r * 2, r * 2, "none", rx=3, stroke=c, sw=1.5))
    o.append(L(cx - r, cy, cx + r, cy, c, 1.5))


def chrome_desktop(o, T, ix, iy, iw, ih, title, url, active):
    # browser frame
    o.append(R(ix, iy, iw, ih, T["card"], rx=12, stroke=T["border"]))
    bar = 34
    o.append(R(ix, iy, iw, bar, T["panel"], rx=12))
    o.append(R(ix, iy + bar - 12, iw, 12, T["panel"]))
    for i, cc in enumerate(["#FF6058", "#FFBD2E", "#28CA42"]):
        o.append(C(ix + 18 + i * 15, iy + bar / 2, 4.5, cc, op=0.9))
    o.append(R(ix + 66, iy + 8, iw - 96, bar - 16, T["bg"], rx=6, stroke=T["border"]))
    o.append(C(ix + 80, iy + bar / 2, 3.6, "none", stroke=T["t4"], sw=1.3))
    o.append(TX(ix + 92, iy + bar / 2 + 3.5, url, 10.5, T["t3"], mono=True))
    px, py = ix, iy + bar
    pw, ph = iw, ih - bar
    o.append(R(px, py, pw, ph, T["bg"]))
    rw = 152
    o.append(R(px, py, rw, ph, T["rail"]))
    o.append(L(px + rw, py, px + rw, py + ph, T["border"], 1))
    o.append(mark_odin(px + 26, py + 26, 0.30))
    o.append(TX(px + 44, py + 25, "K", 14, T["t1"], bold=True))
    o.append(TX(px + 44 + cw("K", 14, True), py + 25, "8", 14, T["accent"], bold=True))
    o.append(TX(px + 44 + cw("K8", 14, True), py + 25, "squad", 14, T["t1"], bold=True))
    ny = py + 62
    for lab, key in RAIL:
        act = key == active
        if act:
            o.append(R(px + 8, ny - 15, rw - 18, 26, T["activebg"], rx=7, stroke=T["accent"] + "44"))
            o.append(R(px + 8, ny - 15, 3, 26, T["accent"], rx=2))
        c = T["accent2"] if act else T["t3"]
        nav_glyph(o, T, px + 24, ny - 3, c, 6)
        o.append(TX(px + 40, ny + 1, lab, 11.5, T["t1"] if act else T["t2"], bold=act))
        ny += 34
    o.append(R(px + 12, ny + 4, rw - 24, 28, T["accent"], rx=7))
    o.append(TX(px + rw / 2, ny + 22, "+  Compose", 11, "#fff", bold=True, anchor="middle"))
    # top bar within content
    cx = px + rw + 16
    th = 40
    o.append(TX(cx, py + 22, title, 14, T["t1"], bold=True))
    o.append(TX(cx, py + 37, "operator console", 9.5, T["t3"]))
    o.append(R(px + pw - 200, py + 12, 130, 26, T["panel"], rx=7, stroke=T["border"]))
    o.append(TX(px + pw - 186, py + 29, "Search…", 10, T["t4"]))
    o.append(C(px + pw - 30, py + 25, 12, T["avatar"], stroke=T["border"]))
    o.append(TX(px + pw - 30, py + 29, "PN", 9, T["accent2"], bold=True, anchor="middle"))
    return cx, py + th + 12, pw - rw - 32, ph - th - 24


def chrome_tablet(o, T, ix, iy, iw, ih, title, url, active):
    # tablet bezel (portrait)
    o.append(R(ix, iy, iw, ih, T["t4"] if False else "#0A0E17", rx=26))
    o.append(R(ix, iy, iw, ih, "#0A0E17", rx=26, stroke=T["border"], sw=1.5))
    m = 12
    sx, sy, swd, shd = ix + m, iy + m, iw - 2 * m, ih - 2 * m
    o.append(R(sx, sy, swd, shd, T["bg"], rx=14))
    # icon-only rail
    rw = 46
    o.append(R(sx, sy, rw, shd, T["rail"], rx=14))
    o.append(R(sx + rw - 14, sy, 14, shd, T["rail"]))
    o.append(L(sx + rw, sy, sx + rw, sy + shd, T["border"], 1))
    o.append(mark_odin(sx + rw / 2, sy + 22, 0.26))
    iy0 = sy + 52
    for lab, key in RAIL[:6]:
        act = key == active
        if act:
            o.append(R(sx + 6, iy0 - 12, rw - 12, 24, T["activebg"], rx=6))
        nav_glyph(o, T, sx + rw / 2, iy0, T["accent2"] if act else T["t3"], 6)
        iy0 += 30
    # top bar
    cx = sx + rw + 12
    o.append(TX(cx, sy + 24, title, 12, T["t1"], bold=True))
    o.append(C(sx + swd - 20, sy + 20, 10, T["avatar"], stroke=T["border"]))
    o.append(TX(sx + swd - 20, sy + 23.5, "PN", 8, T["accent2"], bold=True, anchor="middle"))
    o.append(L(cx, sy + 38, sx + swd - 12, sy + 38, T["border"], 1))
    return cx, sy + 48, swd - rw - 24, shd - 60


def chrome_mobile(o, T, ix, iy, iw, ih, title, url, active):
    # phone bezel
    o.append(R(ix, iy, iw, ih, "#0A0E17", rx=34, stroke=T["border"], sw=1.5))
    m = 9
    sx, sy, swd, shd = ix + m, iy + m, iw - 2 * m, ih - 2 * m
    o.append(R(sx, sy, swd, shd, T["bg"], rx=26))
    # notch
    o.append(R(sx + swd / 2 - 34, sy + 6, 68, 15, "#0A0E17", rx=7.5))
    top = sy + 30
    appbar = 40
    o.append(R(sx, top, swd, appbar, T["rail"]))
    o.append(L(sx, top + appbar, sx + swd, top + appbar, T["border"], 1))
    # hamburger
    hc = T["t2"]
    for k in range(3):
        o.append(L(sx + 14, top + 14 + k * 5, sx + 28, top + 14 + k * 5, hc, 1.6))
    o.append(mark_odin(sx + 44, top + appbar / 2, 0.24))
    o.append(TX(sx + 60, top + 25, title, 12, T["t1"], bold=True))
    o.append(C(sx + swd - 20, top + appbar / 2, 10, T["avatar"], stroke=T["border"]))
    o.append(TX(sx + swd - 20, top + appbar / 2 + 3.5, "PN", 8, T["accent2"], bold=True, anchor="middle"))
    # bottom tab bar
    bh = 50
    by = sy + shd - bh
    o.append(R(sx, by, swd, bh, T["rail"]))
    o.append(L(sx, by, sx + swd, by, T["border"], 1))
    tw = swd / len(BOTTOM)
    for i, (lab, key) in enumerate(BOTTOM):
        act = key == active
        c = T["accent2"] if act else T["t3"]
        cxp = sx + tw * i + tw / 2
        nav_glyph(o, T, cxp, by + 18, c, 6)
        o.append(TX(cxp, by + 40, lab, 8, c, bold=act, anchor="middle"))
        if act:
            o.append(R(cxp - 12, by + 2, 24, 2.5, T["accent"], rx=1.5))
    return sx + 12, top + appbar + 12, swd - 24, (by - (top + appbar) - 22)


# ---- per-surface content dispatch -------------------------------------------
def content(o, T, surface, viewport, cx, cy, cwd, chd):
    small = viewport != "desktop"
    if surface == "shell":
        cols = {"desktop": 5, "tablet": 2, "mobile": 2}[viewport]
        yy = w_kpis(o, T, cx, cy, cwd, cols, small=small)
        yy += 8
        o.append(TX(cx, yy + 4, "Live & recent runs", 10.5 if small else 12, T["t2"], bold=True))
        yy += 16
        n = {"desktop": 4, "tablet": 3, "mobile": 3}[viewport]
        w_runs(o, T, cx, yy, cwd, n, small=small)
    elif surface == "discussion":
        o.append(R(cx, cy, cwd, 30, T["panel"], rx=7, stroke=T["border"]))
        o.append(C(cx + 16, cy + 15, 4, T["a_dot"]))
        o.append(TX(cx + 28, cy + 13, "wi-88 · refund idempotency", 10.5 if small else 12, T["t1"], bold=True))
        o.append(TX(cx + 28, cy + 25, "IN REVIEW · 4 messages", 8.5, T["t3"]))
        yy = cy + 40
        n = {"desktop": 4, "tablet": 3, "mobile": 3}[viewport]
        yy = w_posts(o, T, cx, yy, cwd, n, small=small)
        # operator-note bar
        o.append(R(cx, yy + 2, cwd, 30, T["panel"], rx=8, stroke=T["border"]))
        o.append(TX(cx + 12, yy + 21, "Add an operator note to the coordination record…", 9, T["t4"]))
        o.append(R(cx + cwd - 58, yy + 6, 50, 18, T["accent"], rx=6))
        o.append(TX(cx + cwd - 33, yy + 19, "Post", 9, "#fff", bold=True, anchor="middle"))
    elif surface == "synced":
        cols = {"desktop": 4, "tablet": 2, "mobile": 2}[viewport]
        yy = w_tiles(o, T, cx, cy, cwd, cols, small=small)
        yy += 8
        o.append(TX(cx, yy + 4, "Project room · CI-failure auto-post", 10.5 if small else 12, T["t2"], bold=True))
        yy += 16
        # single external auto-post card (the E11.6 hero guard)
        body = ("CI check failed on PR #341 — refund-suite (2 of 19) @ 9f2c1a. "
                "External attributable context; no claim / handoff / dispatch.")
        fs = 10 if not small else 9
        bl = wrap(body, fs, cwd - 24)
        ph = 44 + len(bl) * (fs + 4)
        o.append(R(cx, yy, cwd, ph, T["a_bg"], rx=8, stroke=tone_color(T, "ext"), sw=1.5))
        o.append(R(cx, yy, 3, ph, T["accent"], rx=2))
        o.append(TX(cx + 14, yy + 18, "github-sync", fs, T["t1"], bold=True))
        o.append(TX(cx + 14 + cw("github-sync", fs, True) + 6, yy + 18, "bot · system", fs - 2, T["t4"]))
        o.append(TX(cx + cwd - 10, yy + 18, "02:41", fs - 2, T["t4"], anchor="end", mono=True))
        bw = cw("EXTERNAL · CI", fs - 2.5, bold=True) + 14
        o.append(R(cx + 14, yy + 24, bw, 15, T["a_bg"], rx=7.5, stroke=tone_color(T, "ext") + "88"))
        o.append(TX(cx + 21, yy + 34.5, "EXTERNAL · CI", fs - 2.5, tone_color(T, "ext"), bold=True))
        ty = yy + 50
        for ln in bl:
            o.append(TX(cx + 14, ty, ln, fs, T["t2"]))
            ty += fs + 4


# ---- matrix assembly --------------------------------------------------------
SURFACES = [
    ("shell", "E8 console shell", "ISI-2180", "Fleet dashboard",
     "console.ksquad.io/fleet/dashboard", "dashboard"),
    ("discussion", "E10.3 discussion room", "ISI-2704", "Discussion · wi-88",
     "console.ksquad.io/payments/discussion/wi-88", "discussion"),
    ("synced", "E11.6 SCM synced-state", "ISI-2741", "SCM · synced state",
     "console.ksquad.io/payments/scm/synced", "projects"),
]

CWD, CH = 2040, 1330


def build(surface, title, ticket, screen_title, url, active, T):
    o = [R(0, 0, CWD, CH, T["bg"])]
    # header
    o.append(mark_odin(60, 52, 0.42))
    o.append(TX(96, 44, "K", 22, T["t1"], bold=True))
    o.append(TX(96 + cw("K", 22, True), 44, "8", 22, T["accent"], bold=True))
    o.append(TX(96 + cw("K8", 22, True), 44, "squad", 22, T["t1"], bold=True))
    o.append(TX(240, 40, f"{title} — responsive viewports", 20, T["t1"], bold=True))
    o.append(TX(240, 62, f"{ticket} · website-fidelity · Odin Infinity v12 · one accent #3D7DFF · "
              "status = dot + label at every breakpoint", 11.5, T["t3"]))
    o.append(R(CWD - 260, 30, 200, 26, T["activebg"], rx=13, stroke=T["accent"] + "55"))
    o.append(TX(CWD - 160, 47, "ISI-2757", 12, T["accent2"], bold=True, anchor="middle"))

    top = 110
    # --- desktop / browser
    dx, dw, dh = 56, 1128, 730
    chrome = chrome_desktop(o, T, dx, top, dw, dh, screen_title, url, active)
    content(o, T, surface, "desktop", *chrome)
    o.append(TX(dx, top + dh + 26, "Desktop · browser · ≥ 1280px", 13, T["t1"], bold=True))
    o.append(TX(dx, top + dh + 44, "full left rail (icon + label) + top bar + multi-column content, in a browser frame",
               10.5, T["t3"]))

    # --- tablet 768
    tx, tw, thh = 1228, 388, 620
    chrome = chrome_tablet(o, T, tx, top, tw, thh, screen_title, url, active)
    content(o, T, surface, "tablet", *chrome)
    o.append(TX(tx, top + thh + 26, "Tablet · 768px", 13, T["t1"], bold=True))
    o.append(TX(tx, top + thh + 44, "collapsed icon-only rail + 2-column content", 10.5, T["t3"]))

    # --- mobile 375
    mx, mw, mh = 1668, 300, 630
    chrome = chrome_mobile(o, T, mx, top, mw, mh, screen_title, url, active)
    content(o, T, surface, "mobile", *chrome)
    o.append(TX(mx, top + mh + 26, "Mobile · 375px", 13, T["t1"], bold=True))
    o.append(TX(mx, top + mh + 44, "no rail — app-bar (☰ + Odin mark)", 10.5, T["t3"]))
    o.append(TX(mx, top + mh + 58, "single column + bottom tab nav", 10.5, T["t3"]))

    # --- reflow-contract band
    by = 990
    o.append(R(56, by, CWD - 112, 300, T["card"], rx=14, stroke=T["border"]))
    o.append(TX(80, by + 34, "Reflow contract — the console follows the website's responsive rendering", 16, T["t1"], bold=True))
    rules = [
        ("Rail", "desktop icon+label rail → tablet icon-only rail → mobile drops the rail for a bottom tab bar."),
        ("Content", "desktop multi-column (5 KPI / 4-col tiles) → tablet 2-column → mobile single column, cards full-bleed."),
        ("Chrome", "desktop wraps the page in a browser frame (matches the website carousel); tablet & mobile show device bezels."),
        ("Brand", "Odin Infinity v12 mark appears at every breakpoint; wordmark collapses to the mark alone on mobile."),
        ("Accent & status", "one accent #3D7DFF everywhere; every Run/CI state is a colour dot + text label (never colour-alone)."),
        ("Density", "operator density preserved; data tables scroll horizontally on small screens rather than truncate meaning."),
    ]
    ry = by + 66
    for k, v in rules:
        o.append(C(84, ry - 4, 3, T["accent"]))
        o.append(TX(96, ry, k, 12.5, T["accent2"], bold=True))
        o.append(TX(96 + 130, ry, v, 12, T["t2"]))
        ry += 26
    o.append(TX(80, by + 285, "Conformance target: docs/bmad/ux/UI-CONFORMANCE-v12.md §Responsive · implementer: Claude Code (console)",
               10.5, T["t4"], mono=True))
    return "".join(o)


def svg_wrap(inner, T):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CWD}" height="{CH}" '
            f'viewBox="0 0 {CWD} {CH}" {FS}>' + LOGO_DEFS + inner + "</svg>")


def main():
    out = os.path.join(os.path.dirname(__file__), "images")
    try:
        import resvg_py
    except ImportError:
        resvg_py = None
    for surface, title, ticket, screen_title, url, active in SURFACES:
        for suffix, T in [("", DARK), ("-light", LIGHT)]:
            base = f"Rvp-{surface}{suffix}"
            svg = svg_wrap(build(surface, title, ticket, screen_title, url, active, T), T)
            sp = os.path.join(out, base + ".svg")
            with open(sp, "w") as f:
                f.write(svg)
            print("wrote", sp)
            if resvg_py:
                png = resvg_py.svg_to_bytes(svg_string=svg)
                pp = os.path.join(out, base + ".png")
                with open(pp, "wb") as f:
                    f.write(png if isinstance(png, (bytes, bytearray)) else bytes(png))
                print("wrote", pp)


if __name__ == "__main__":
    main()
