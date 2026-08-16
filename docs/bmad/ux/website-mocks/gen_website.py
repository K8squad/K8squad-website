#!/usr/bin/env python3
"""
KSquad marketing/docs WEBSITE mocks (ISI-2366) — separate deliverable from the
operator-console mocks. Produces three page mocks in dark + light:

  01-landing.svg        single-page scroll (hero, what-is, features, how-it-works,
                        screenshots carousel, get-started, footer)
  02-docs-layout.svg    docs shell: header + search + sidebar + content + TOC
  03-sdk-guide.svg      docs shell rendering the Plugin SDK guide (arch diagram,
                        event table, syntax-highlighted "your first plugin")

Self-contained (no shared console_kit import): own token maps + primitives, so a
concurrent heartbeat editing the console kit can't break this. Brand-locked:
official 8-Crest mark geometry (branding/assets/mark-8crest-on-dark.svg), single
azure accent #3D7DFF (theme-invariant), Geist-nominal type rendered with DejaVu.

Render with @resvg/resvg-js (see render_website.js) at width=1440.
"""

# ---------------------------------------------------------------- token maps
DARK = dict(
    bg="#0F1117", bgAlt="#0B0E14", card="#1A1D29", cardRaised="#222634",
    inset="#12141C", border="#262B3A", borderSoft="#1E2230",
    textHi="#E8EEF9", text="#B6C3D8", muted="#7E8CA6",
    accent="#3D7DFF", accentText="#93B7FF", accentBg="#16244A",
    green="#34D399", amber="#FBBF24",
    node="#93B7FF", nodeLow="#2E4E8C",
)
LIGHT = dict(
    bg="#F6F8FC", bgAlt="#EEF2F8", card="#FFFFFF", cardRaised="#F1F5FA",
    inset="#F1F5FA", border="#D4DCEA", borderSoft="#E2E8F0",
    textHi="#0B1220", text="#33415C", muted="#64748B",
    accent="#3D7DFF", accentText="#2563EB", accentBg="#E5EDFF",
    green="#059669", amber="#B45309",
    node="#93B7FF", nodeLow="#2E4E8C",
)
# code blocks stay dark in BOTH themes (dev-site convention) -> constant syntax
CODE = dict(bg="#0C0E15", border="#1E2230", txt="#C9D4E5", dim="#8B949E",
           kw="#FF7B72", str="#A5D6FF", fn="#79C0FF", num="#F2CC60", com="#8B949E")

W = 1440
MX = 96                      # page horizontal margin
CW = W - 2 * MX             # content width

# ---------------------------------------------------------------- primitives
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def cw(s, size, bold=False, mono=False):
    """conservative DejaVu advance-width estimate (bold under-estimates -> pad)."""
    k = 0.605 if mono else (0.625 if bold else 0.552)
    return len(s) * size * k

def R(x, y, w, h, fill, rx=0, stroke=None, sw=1, op=None, dash=None):
    a = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"'
    if stroke: a += f' stroke="{stroke}" stroke-width="{sw}"'
    if op is not None: a += f' opacity="{op}"'
    if dash: a += f' stroke-dasharray="{dash}"'
    return a + "/>"

def T(x, y, s, size, fill, bold=False, mono=False, anchor="start", op=None, ls=None):
    fam = "DejaVu Sans Mono" if mono else "DejaVu Sans"
    w = ' font-weight="700"' if bold else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    o = f' opacity="{op}"' if op is not None else ""
    l = f' letter-spacing="{ls}"' if ls is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" '
            f'font-size="{size}"{w} fill="{fill}"{a}{o}{l}>{esc(s)}</text>')

def L(x1, y1, x2, y2, stroke, sw=1, op=None, dash=None):
    o = f' opacity="{op}"' if op is not None else ""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{o}{d}/>')

def C(cx, cy, r, fill, stroke=None, sw=1, op=None):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    o = f' opacity="{op}"' if op is not None else ""
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"{s}{o}/>'

DEFS = ('<defs>'
        '<linearGradient id="ringTop" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#93B7FF"/><stop offset="1" stop-color="#3D7DFF"/></linearGradient>'
        '<linearGradient id="ringBot" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#3D7DFF"/><stop offset="1" stop-color="#2E4E8C"/></linearGradient>'
        '<linearGradient id="heroGlow" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#3D7DFF" stop-opacity="0.18"/>'
        '<stop offset="1" stop-color="#3D7DFF" stop-opacity="0"/></linearGradient>'
        '</defs>')

def crest(cx, cy, size):
    """official 8-Crest mark; source box spans ~ x[29..71] y[9.5..90.5] (~50 wide, ~81 tall)."""
    s = size / 81.0
    tx = cx - 50 * s
    ty = cy - 50 * s
    g = f'<g transform="translate({tx:.2f},{ty:.2f}) scale({s:.4f})">'
    g += ('<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="url(#ringBot)" stroke-width="9"/>'
          '<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="url(#ringTop)" stroke-width="9"/>'
          '<rect x="41" y="41" width="18" height="18" rx="5" fill="#93B7FF"/>'
          '<rect x="44.5" y="9.5" width="11" height="11" rx="3" fill="#93B7FF"/>'
          '<rect x="44.5" y="79.5" width="11" height="11" rx="3" fill="#2E4E8C"/></g>')
    return g

def wordmark(x, y, size, t, muted_tail=False):
    """K + 8(azure) + squad, baseline at y. returns (svg, end_x)."""
    tail = t["muted"] if muted_tail else t["textHi"]
    out = []
    cx = x
    out.append(T(cx, y, "K", size, t["textHi"], bold=True)); cx += cw("K", size, True)
    out.append(T(cx, y, "8", size, t["accent"], bold=True)); cx += cw("8", size, True)
    out.append(T(cx, y, "squad", size, tail, bold=True)); cx += cw("squad", size, True)
    return "".join(out), cx

# icon: small line-glyph inside a rounded accent tile
def icon_tile(x, y, s, t, kind, tint=None):
    bg = tint or t["accentBg"]
    st = t["accent"]
    o = [R(x, y, s, s, bg, rx=10)]
    m = x + s / 2; n = y + s / 2; r = s * 0.26
    if kind == "cube":
        o += [L(m-r, n-r*0.5, m, n-r, st, 2), L(m, n-r, m+r, n-r*0.5, st, 2),
              L(m-r, n-r*0.5, m-r, n+r*0.5, st, 2), L(m+r, n-r*0.5, m+r, n+r*0.5, st, 2),
              L(m-r, n+r*0.5, m, n+r, st, 2), L(m, n+r, m+r, n+r*0.5, st, 2),
              L(m, n-r, m, n+r, st, 2)]
    elif kind == "org":
        o += [C(m, n-r, 3, st), C(m-r, n+r, 3, st), C(m+r, n+r, 3, st),
              L(m, n-r+3, m, n, st, 2), L(m-r, n, m+r, n, st, 2),
              L(m-r, n, m-r, n+r-3, st, 2), L(m+r, n, m+r, n+r-3, st, 2)]
    elif kind == "browser":
        o += [R(m-r, n-r*0.7, r*2, r*1.6, "none", rx=3, stroke=st, sw=2),
              L(m-r, n-r*0.7+6, m+r, n-r*0.7+6, st, 2)]
    elif kind == "pulse":
        o += [f'<polyline points="{m-r:.1f},{n} {m-r*0.4:.1f},{n} {m-r*0.1:.1f},{n-r} {m+r*0.3:.1f},{n+r} {m+r*0.6:.1f},{n} {m+r:.1f},{n}" fill="none" stroke="{st}" stroke-width="2"/>']
    elif kind == "shield":
        o += [f'<path d="M{m},{n-r} L{m+r},{n-r*0.5} L{m+r},{n+r*0.2} Q{m+r},{n+r} {m},{n+r} Q{m-r},{n+r} {m-r},{n+r*0.2} L{m-r},{n-r*0.5} Z" fill="none" stroke="{st}" stroke-width="2"/>']
    elif kind == "otel":
        o += [C(m, n, r, "none", stroke=st, sw=2), C(m, n, 2.5, st),
              C(m+r, n-r, 2.5, st), C(m-r, n+r, 2.5, st),
              L(m+2, n-2, m+r, n-r, st, 1.5), L(m-2, n+2, m-r, n+r, st, 1.5)]
    elif kind == "plug":
        o += [R(m-r*0.5, n-r, r, r*1.3, "none", rx=3, stroke=st, sw=2),
              L(m-r*0.2, n-r, m-r*0.2, n-r-4, st, 2), L(m+r*0.2, n-r, m+r*0.2, n-r-4, st, 2),
              L(m, n+r*0.3, m, n+r, st, 2)]
    elif kind == "responsive":
        o += [R(m-r, n-r*0.7, r*1.3, r*1.5, "none", rx=2, stroke=st, sw=2),
              R(m+r*0.3, n-r*0.2, r*0.7, r*1.0, bg, rx=2, stroke=st, sw=2)]
    elif kind == "book":
        o += [L(m, n-r, m, n+r, st, 2),
              f'<path d="M{m},{n-r} Q{m-r},{n-r-2} {m-r},{n+r-4} L{m-r},{n+r} Q{m-r},{n+r-2} {m},{n+r-2} Z" fill="none" stroke="{st}" stroke-width="1.6"/>',
              f'<path d="M{m},{n-r} Q{m+r},{n-r-2} {m+r},{n+r-4} L{m+r},{n+r} Q{m+r},{n+r-2} {m},{n+r-2} Z" fill="none" stroke="{st}" stroke-width="1.6"/>']
    elif kind == "search":
        o += [C(m-2, n-2, r*0.7, "none", stroke=st, sw=2), L(m+2, n+2, m+r, n+r, st, 2)]
    elif kind == "rocket":
        o += [f'<path d="M{m},{n-r} Q{m+r*0.7},{n-r*0.2} {m+r*0.4},{n+r} L{m-r*0.4},{n+r} Q{m-r*0.7},{n-r*0.2} {m},{n-r} Z" fill="none" stroke="{st}" stroke-width="2"/>',
              C(m, n-r*0.2, 2.2, st)]
    return "".join(o)

# ---------------------------------------------------------------- shared chrome
def btn(x, y, w, h, label, t, size=14, primary=True, icon=None):
    if primary:
        o = [R(x, y, w, h, t["accent"], rx=8)]
        fill = "#FFFFFF"
    else:
        o = [R(x, y, w, h, "none", rx=8, stroke=t["border"], sw=1.4)]
        fill = t["textHi"]
    tw = cw(label, size, True)
    lx = x + (w - tw) / 2
    o.append(T(lx, y + h/2 + size*0.35, label, size, fill, bold=True))
    return "".join(o)

def pill(x, y, label, t, size=12, accent=True):
    w = cw(label, size, True) + 26
    h = 26
    bg = t["accentBg"] if accent else t["cardRaised"]
    fg = t["accentText"] if accent else t["muted"]
    o = [R(x, y, w, h, bg, rx=13)]
    o.append(T(x + 13, y + h/2 + size*0.35, label, size, fg, bold=True))
    return "".join(o), w

# --------- a tiny stylised "console screenshot" drawn inside a browser frame
def console_thumb(x, y, w, h, t, title):
    """abstracted operator-console screen: rail + KPI tiles + live-runs list."""
    o = [R(x, y, w, h, t["inset"], rx=8, stroke=t["border"], sw=1)]
    rail = 34
    o.append(R(x, y, rail, h, t["bgAlt"], rx=8))
    o.append(crest(x + rail/2, y + 18, 16))
    for i in range(6):
        o.append(R(x + 8, y + 40 + i*20, rail-16, 6, t["accent"] if i == 0 else t["border"],
                   rx=3, op=1 if i == 0 else 0.6))
    cx0 = x + rail + 14
    o.append(T(cx0, y + 24, title, 11, t["textHi"], bold=True))
    # KPI tiles
    tiles = w - rail - 28
    tw = (tiles - 3*10) / 4
    for i in range(4):
        tx = cx0 + i*(tw+10)
        o.append(R(tx, y + 34, tw, 34, t["card"], rx=6, stroke=t["borderSoft"], sw=1))
        o.append(R(tx+8, y+42, tw*0.4, 6, t["muted"], rx=3, op=0.7))
        o.append(R(tx+8, y+54, tw*0.55, 8, t["accentText"], rx=3))
    # live-run rows
    for i in range(4):
        ry = y + 80 + i*((h - 92)/4)
        o.append(R(cx0, ry, tiles, (h-92)/4 - 6, t["card"], rx=6, stroke=t["borderSoft"], sw=1))
        dot = t["green"] if i % 2 == 0 else t["amber"]
        o.append(C(cx0+14, ry + ((h-92)/4-6)/2, 4, dot))
        o.append(R(cx0+28, ry + 8, tiles*0.28, 6, t["text"], rx=3, op=0.8))
        o.append(R(cx0+28, ry + 20, tiles*0.18, 5, t["muted"], rx=3, op=0.6))
        o.append(R(x+w-90, ry + ((h-92)/4-6)/2 - 3, 60, 6, t["accent"], rx=3, op=0.5))
    return "".join(o)

def browser_frame(x, y, w, h, t, url):
    o = [R(x, y, w, h, t["card"], rx=12, stroke=t["border"], sw=1)]
    bar = 34
    o.append(R(x, y, w, bar, t["cardRaised"], rx=12))
    o.append(R(x, y+bar-12, w, 12, t["cardRaised"]))
    for i, cc in enumerate(["#FF6058", "#FFBD2E", "#28CA42"]):
        o.append(C(x + 18 + i*16, y + bar/2, 4.5, cc, op=0.85))
    o.append(R(x + 70, y + 8, w - 100, bar - 16, t["inset"], rx=6))
    o.append(T(x + 84, y + bar/2 + 3.5, url, 11, t["muted"], mono=True))
    return "".join(o), y + bar

# code block with naive syntax highlighting (tokens pre-classified per line)
def code_block(x, y, w, lines, title=None, minh=0):
    pad = 16; lh = 20; head = 30 if title else 0
    h = max(minh, head + pad*2 + lh*len(lines))
    o = [R(x, y, w, h, CODE["bg"], rx=10, stroke=CODE["border"], sw=1)]
    if title:
        o.append(R(x, y, w, head, "#11141C", rx=10))
        o.append(R(x, y+head-10, w, 10, "#11141C"))
        o.append(T(x+16, y+head/2+4, title, 11, CODE["dim"], mono=True))
        o.append(C(x+w-18, y+head/2, 3, CODE["dim"], op=0.5))
    ty = y + head + pad + 12
    spw = cw(" ", 13, mono=True)   # resvg trims each <text>'s leading ws -> advance instead
    for ln in lines:
        tx = x + pad
        for tok, cls in ln:
            stripped = tok.lstrip(" ")
            tx += (len(tok) - len(stripped)) * spw
            if stripped:
                o.append(T(tx, ty, stripped, 13, CODE[cls], mono=True))
            tx += cw(stripped, 13, mono=True)
        ty += lh
    return "".join(o), h

def callout(x, y, w, kind, title, body_lines, t):
    accent = {"tip": t["green"], "note": t["accent"], "warn": t["amber"]}[kind]
    bgc = {"tip": t["card"], "note": t["accentBg"], "warn": t["card"]}[kind]
    lh = 19
    h = 44 + lh*len(body_lines)
    o = [R(x, y, w, h, bgc, rx=10, stroke=t["border"], sw=1)]
    o.append(R(x, y, 4, h, accent, rx=2))
    o.append(T(x+20, y+26, title, 13, t["textHi"], bold=True))
    ty = y + 26 + lh
    for bl in body_lines:
        o.append(T(x+20, ty, bl, 13, t["text"]))
        ty += lh
    return "".join(o), h

# ================================================================ PAGE 1: LANDING
def landing(t):
    body = []
    y = 0
    # -- sticky top nav
    navh = 72
    body.append(R(0, 0, W, navh, t["bgAlt"]))
    body.append(L(0, navh, W, navh, t["border"], 1))
    body.append(crest(MX + 16, navh/2, 30))
    wm, _ = wordmark(MX + 40, navh/2 + 7, 20, t)
    body.append(wm)
    links = ["Features", "How it works", "Docs", "GitHub"]
    lx = W - MX - 150
    # measure right-to-left
    total = sum(cw(l, 14) + 28 for l in links)
    lxs = W - MX - 150 - total
    cxp = lxs
    for l in links:
        body.append(T(cxp, navh/2 + 5, l, 14, t["text"]))
        cxp += cw(l, 14) + 28
    body.append(btn(W - MX - 132, navh/2 - 18, 132, 36, "Get started", t, primary=True))
    y = navh

    # -- HERO
    heroh = 540
    body.append(R(0, y, W, heroh, t["bg"]))
    body.append(R(W*0.42, y, W*0.58, heroh, "url(#heroGlow)"))
    # node-network background (deterministic)
    nodes = [(1000,120),(1120,220),(980,300),(1180,360),(1060,430),(1240,140),
             (900,200),(1150,470),(1300,300),(1020,220),(1220,240),(940,400),
             (1290,420),(1080,150)]
    for i,(a,b) in enumerate(nodes):
        for (c,d) in nodes[i+1:]:
            if abs(a-c)+abs(b-d) < 200:
                body.append(L(a, y+b, c, y+d, t["accent"], 1, op=0.12))
    for i,(a,b) in enumerate(nodes):
        filled = i % 3 == 0
        body.append(C(a, y+b, 5 if filled else 3.5,
                      t["accent"] if filled else t["node"], op=0.55 if filled else 0.4))
    # live pulse marker
    body.append(C(nodes[0][0], y+nodes[0][1], 9, t["accent"], op=0.18))
    body.append(C(nodes[0][0], y+nodes[0][1], 5, t["accent"]))

    hx = MX
    p, pw = pill(hx, y + 70, "Multi-agent orchestration for Kubernetes", t)
    body.append(p)
    body.append(T(hx, y + 172, "Your agents,", 62, t["textHi"], bold=True))
    body.append(T(hx, y + 240, "in ", 62, t["textHi"], bold=True))
    body.append(T(hx + cw("in ", 62, True), y + 240, "formation.", 62, t["accent"], bold=True))
    sub = ["Compose squads of AI agents as Kubernetes resources. They claim work,",
           "hand off, and coordinate — you watch every run, live, with OpenTelemetry."]
    for i, s in enumerate(sub):
        body.append(T(hx, y + 288 + i*26, s, 17, t["text"]))
    body.append(btn(hx, y + 356, 150, 46, "Get started", t, size=15, primary=True))
    body.append(btn(hx + 166, y + 356, 172, 46, "View on GitHub", t, size=15, primary=False))
    # helm one-liner chip
    chy = y + 430
    chw = 520
    body.append(R(hx, chy, chw, 44, CODE["bg"], rx=10, stroke=CODE["border"], sw=1))
    body.append(T(hx + 16, chy + 28, "$", 14, CODE["dim"], mono=True))
    body.append(T(hx + 32, chy + 28, "helm install ksquad ksquad/ksquad -n ksquad-system", 14, CODE["txt"], mono=True))
    body.append(R(hx + chw - 40, chy + 10, 24, 24, t["cardRaised"], rx=6, stroke=t["border"], sw=1))
    body.append(R(hx + chw - 33, chy + 16, 8, 8, "none", rx=2, stroke=t["muted"], sw=1.4))
    body.append(R(hx + chw - 30, chy + 19, 8, 8, t["cardRaised"], rx=2, stroke=t["muted"], sw=1.4))
    y += heroh

    # -- WHAT IS KSQUAD (3 bullets)
    secpad = 72
    body.append(R(0, y, W, 300, t["bgAlt"]))
    body.append(T(MX, y + secpad, "What is KSquad?", 30, t["textHi"], bold=True))
    body.append(T(MX, y + secpad + 30, "A Kubernetes-native control plane for teams of AI agents.", 16, t["muted"]))
    whats = [
        ("cube", "Kubernetes-native", ["Squads, agents and runs are CRDs.", "Deploy with Helm, manage with kubectl."]),
        ("org", "Agents in formation", ["Compose teams that claim work,", "hand off, and coordinate over a shared bus."]),
        ("otel", "Observable by default", ["Every run emits OpenTelemetry traces.", "Live SSE streams — no black boxes."]),
    ]
    cwid = (CW - 2*24) / 3
    cy0 = y + secpad + 66
    for i,(ic, ti, ds) in enumerate(whats):
        cx = MX + i*(cwid+24)
        body.append(R(cx, cy0, cwid, 132, t["card"], rx=14, stroke=t["border"], sw=1))
        body.append(icon_tile(cx+22, cy0+22, 44, t, ic))
        body.append(T(cx+22, cy0+94, ti, 17, t["textHi"], bold=True))
        for j, d in enumerate(ds):
            body.append(T(cx+22, cy0+94+22+j*18, d, 13, t["muted"]))
    y += 300

    # -- FEATURES GRID (8)
    body.append(R(0, y, W, 520, t["bg"]))
    body.append(T(MX, y + secpad, "Everything you need to run agent squads", 30, t["textHi"], bold=True))
    feats = [
        ("cube", "Project-scoped squads", "Isolated squads per project, RBAC-gated."),
        ("org", "Agent org views", "See who reports to whom, live status."),
        ("browser", "Build browser", "Inspect artifacts across every run."),
        ("pulse", "Live runs", "Follow tool calls, LLM and logs via SSE."),
        ("shield", "RBAC", "Fine-grained roles for operators & authors."),
        ("otel", "OTel-native", "Traces, metrics and logs out of the box."),
        ("plug", "Plugin SDK", "Extend the console with typed events."),
        ("responsive", "Responsive", "Full console on desktop, tablet, mobile."),
    ]
    fcw = (CW - 3*22) / 4
    fch = 150
    gy0 = y + secpad + 40
    for i,(ic, ti, ds) in enumerate(feats):
        r = i // 4; c = i % 4
        cx = MX + c*(fcw+22); cyy = gy0 + r*(fch+22)
        body.append(R(cx, cyy, fcw, fch, t["card"], rx=14, stroke=t["border"], sw=1))
        body.append(icon_tile(cx+20, cyy+20, 40, t, ic))
        body.append(T(cx+20, cyy+86, ti, 15, t["textHi"], bold=True))
        # wrap desc
        words = ds.split(); line=""; ly = cyy+108
        for wd in words:
            if cw(line+" "+wd, 12) > fcw-40:
                body.append(T(cx+20, ly, line, 12, t["muted"])); ly+=16; line=wd
            else:
                line = (line+" "+wd).strip()
        body.append(T(cx+20, ly, line, 12, t["muted"]))
    y += 520

    # -- HOW IT WORKS (4-step flow)
    body.append(R(0, y, W, 340, t["bgAlt"]))
    body.append(T(MX, y + secpad, "How it works", 30, t["textHi"], bold=True))
    steps = [("cube","1","Compose CRDs","Declare a Squad and its agents in YAML."),
             ("rocket","2","Squad spins up","The operator schedules agents as pods."),
             ("org","3","Agents work","They claim items, hand off, coordinate."),
             ("pulse","4","You monitor","Watch live runs, traces and artifacts.")]
    sw_ = (CW - 3*56) / 4
    sy0 = y + secpad + 44
    for i,(ic, n, ti, ds) in enumerate(steps):
        cx = MX + i*(sw_+56)
        body.append(R(cx, sy0, sw_, 150, t["card"], rx=14, stroke=t["border"], sw=1))
        body.append(icon_tile(cx+20, sy0+20, 40, t, ic))
        body.append(C(cx+sw_-24, sy0+24, 13, t["accentBg"]))
        body.append(T(cx+sw_-24, sy0+29, n, 13, t["accentText"], bold=True, anchor="middle"))
        body.append(T(cx+20, sy0+86, ti, 15, t["textHi"], bold=True))
        words = ds.split(); line=""; ly=sy0+108
        for wd in words:
            if cw(line+" "+wd, 12) > sw_-36:
                body.append(T(cx+20, ly, line, 12, t["muted"])); ly+=16; line=wd
            else: line=(line+" "+wd).strip()
        body.append(T(cx+20, ly, line, 12, t["muted"]))
        if i < 3:
            ax = cx + sw_ + 12; ay = sy0 + 75
            body.append(L(ax, ay, ax+32, ay, t["accent"], 2, op=0.7))
            body.append(f'<path d="M{ax+32},{ay} l-7,-5 v10 z" fill="{t["accent"]}" opacity="0.7"/>')
    y += 340

    # -- SCREENSHOTS CAROUSEL
    carh = 560
    body.append(R(0, y, W, carh, t["bg"]))
    body.append(T(MX, y + secpad, "See it in action", 30, t["textHi"], bold=True))
    body.append(T(MX, y + secpad + 30, "The operator console — nav, kanban, dashboards, agent org and build browser.", 16, t["muted"]))
    fw = CW; fx = MX; fy = y + secpad + 60
    fh = 300
    _, inner_y = browser_frame(fx, fy, fw, fh, t, "console.ksquad.io/fleet/dashboard")
    body.append(_)
    body.append(console_thumb(fx+16, inner_y+14, fw-32, fh-(inner_y-fy)-30, t, "Fleet dashboard · live runs"))
    # thumbnail strip
    thumbs = ["Nav & IA", "Project kanban", "Fleet dashboard", "Agents org", "Build browser"]
    tw_ = (CW - 4*18) / 5
    ty0 = fy + fh + 22
    for i, lab in enumerate(thumbs):
        tx = MX + i*(tw_+18)
        sel = i == 2
        body.append(R(tx, ty0, tw_, 74, t["card"], rx=10,
                      stroke=t["accent"] if sel else t["border"], sw=2 if sel else 1))
        # mini rail+panels
        body.append(R(tx+8, ty0+8, 10, 58, t["bgAlt"], rx=3))
        body.append(R(tx+24, ty0+8, tw_-34, 22, t["inset"], rx=3))
        body.append(R(tx+24, ty0+36, (tw_-34)*0.6, 12, t["inset"], rx=3))
        body.append(R(tx+24, ty0+52, (tw_-34)*0.4, 10, t["inset"], rx=3))
        body.append(T(tx+tw_/2, ty0+74+18, lab, 12, t["textHi"] if sel else t["muted"],
                      bold=sel, anchor="middle"))
    # dots
    dy = ty0 + 74 + 40
    for i in range(5):
        body.append(C(W/2 - 40 + i*20, dy, 4, t["accent"] if i==2 else t["border"],
                      op=1 if i==2 else 0.6))
    y += carh

    # -- GET STARTED
    gsh = 300
    body.append(R(0, y, W, gsh, t["bgAlt"]))
    body.append(R(MX, y+secpad-24, CW, 176, t["card"], rx=18, stroke=t["border"], sw=1))
    body.append(T(MX+40, y+secpad+20, "Get started in one command", 26, t["textHi"], bold=True))
    body.append(T(MX+40, y+secpad+48, "Install the operator, then open the console.", 15, t["muted"]))
    gcx = MX + 40; gcy = y + secpad + 68
    body.append(R(gcx, gcy, CW-80, 44, CODE["bg"], rx=10, stroke=CODE["border"], sw=1))
    body.append(T(gcx+16, gcy+28, "$", 14, CODE["dim"], mono=True))
    body.append(T(gcx+32, gcy+28, "helm repo add ksquad https://charts.ksquad.io && helm install ksquad ksquad/ksquad", 13.5, CODE["txt"], mono=True))
    body.append(btn(gcx, gcy+60, 150, 42, "Read the docs", t, primary=True))
    body.append(btn(gcx+166, gcy+60, 150, 42, "Quickstart", t, primary=False))
    y += gsh

    # -- FOOTER
    fth = 220
    body.append(R(0, y, W, fth, t["bgAlt"]))
    body.append(L(0, y, W, y, t["border"], 1))
    body.append(crest(MX+16, y+52, 30))
    wm2, _ = wordmark(MX+40, y+59, 20, t)
    body.append(wm2)
    body.append(T(MX, y+96, "Your agents, in formation.", 13, t["muted"]))
    body.append(T(MX, y+120, "Apache 2.0 licensed · © 2026 KSquad", 12, t["muted"]))
    cols = [("Product", ["Features","Console","Plugin SDK","Roadmap"]),
            ("Docs", ["Quickstart","Concepts","Operator Guide","API Reference"]),
            ("Community", ["GitHub","Discussions","Releases","License"])]
    colx = MX + CW - 3*180
    for ci,(h, items) in enumerate(cols):
        cx = colx + ci*180
        body.append(T(cx, y+52, h, 13, t["textHi"], bold=True))
        for j, it in enumerate(items):
            body.append(T(cx, y+52+26+j*22, it, 13, t["muted"]))
    body.append(L(MX, y+fth-40, W-MX, y+fth-40, t["border"], 1))
    body.append(T(MX, y+fth-18, "github.com/K8squad/K8squad  ·  docs.ksquad.io", 12, t["muted"], mono=True))
    y += fth

    return "".join(body), y

# ================================================================ docs shell
SIDEBAR = [
    ("Quickstart", ["Install", "First squad", "Open the console"]),
    ("Concepts", None), ("Operator Guide", None), ("Author Guide", None),
    ("Console Guide", None), ("API Reference", None),
    ("Observability", None), ("Troubleshooting", None),
]
def docs_header(t, active_search="Search the docs…"):
    o = []
    hh = 64
    o.append(R(0, 0, W, hh, t["card"]))
    o.append(L(0, hh, W, hh, t["border"], 1))
    o.append(crest(MX-56, hh/2, 28))
    wm, ex = wordmark(MX-36, hh/2+7, 18, t)
    o.append(wm)
    o.append(pill(ex+14, hh/2-11, "docs", t)[0])
    # search
    sw_ = 460; sx = (W-sw_)/2
    o.append(R(sx, 14, sw_, 36, t["inset"], rx=9, stroke=t["border"], sw=1))
    o.append(icon_tile(sx+6, 19, 26, t, "search", tint="none"))
    o.append(T(sx+40, 37, active_search, 13, t["muted"]))
    o.append(R(sx+sw_-46, 20, 34, 24, t["cardRaised"], rx=6, stroke=t["border"], sw=1))
    o.append(T(sx+sw_-40, 36, "⌘K", 12, t["muted"], mono=True))
    # right: theme toggle + github
    tgx = W - MX - 84
    o.append(R(tgx, 20, 54, 24, t["cardRaised"], rx=12, stroke=t["border"], sw=1))
    o.append(C(tgx+13, 32, 8, t["accent"]))
    o.append(C(tgx+40, 32, 6, t["muted"], op=0.5))
    o.append(f'<path d="M{W-MX-14},26 a8,8 0 1,0 4,15 a6.5,6.5 0 1,1 -4,-15 z" fill="{t["muted"]}"/>')
    return "".join(o), hh

def docs_sidebar(x, y, h, t, active=1, active_sub=0):
    o = [R(x, y, 250, h, t["bgAlt"]), L(x+250, y, x+250, y+h, t["border"], 1)]
    yy = y + 30
    for i,(sec, subs) in enumerate(SIDEBAR):
        is_act = i == active
        if is_act:
            o.append(R(x+14, yy-16, 222, 26, t["accentBg"], rx=7))
            o.append(R(x, yy-16, 3, 26, t["accent"]))
        o.append(T(x+28, yy+2, sec, 14, t["accentText"] if is_act else t["text"],
                   bold=is_act))
        yy += 34
        if subs and is_act:
            for j, s in enumerate(subs):
                sact = j == active_sub
                o.append(T(x+44, yy+1, s, 13,
                           t["accentText"] if sact else t["muted"], bold=sact))
                if sact:
                    o.append(R(x+30, yy-9, 2, 16, t["accent"], rx=1))
                yy += 28
            yy += 6
    return "".join(o)

def docs_toc(x, y, t, items, active=0):
    o = [T(x, y, "ON THIS PAGE", 11, t["muted"], bold=True, ls=1)]
    yy = y + 26
    for i, it in enumerate(items):
        act = i == active
        o.append(R(x-14, yy-11, 2, 16, t["accent"] if act else t["border"], rx=1))
        o.append(T(x, yy+1, it, 12.5, t["accentText"] if act else t["muted"], bold=act))
        yy += 24
    return "".join(o)

# ================================================================ PAGE 2: DOCS
def docs_layout(t):
    body = []
    hdr, hh = docs_header(t)
    body.insert(0, R(0,0,W,1,t["bg"]))  # ensure bg fill added later
    body.append(hdr)
    total_h = 980
    body.append(R(0, hh, W, total_h-hh, t["bg"]))
    body.append(docs_sidebar(0, hh, total_h-hh, t, active=1, active_sub=0))
    # content
    cx = 250 + 60; cy = hh + 40
    cwid = W - (250+60) - 240 - 40
    # breadcrumb
    body.append(T(cx, cy, "Concepts", 12, t["muted"]))
    body.append(T(cx+cw("Concepts",12)+8, cy, "›", 12, t["muted"]))
    body.append(T(cx+cw("Concepts",12)+22, cy, "Squads & agents", 12, t["accentText"]))
    body.append(T(cx, cy+44, "Squads & agents", 34, t["textHi"], bold=True))
    body.append(T(cx, cy+76, "A Squad is a Kubernetes resource that describes a team of agents and how they coordinate.",
                  15, t["text"]))
    yy = cy + 116
    # section heading
    body.append(T(cx, yy, "The Squad resource", 20, t["textHi"], bold=True)); yy += 32
    for ln in ["A Squad groups agents under a single project and namespace. The operator",
               "reconciles it into running pods, wires the coordination bus, and exposes",
               "every run to the console."]:
        body.append(T(cx, yy, ln, 14, t["text"])); yy += 22
    yy += 14
    # code block
    code = [
        [("apiVersion", "kw"), (": ", "txt"), ("ksquad.io/v1alpha1", "str")],
        [("kind", "kw"), (": ", "txt"), ("Squad", "str")],
        [("metadata", "kw"), (":", "txt")],
        [("  name", "kw"), (": ", "txt"), ("payments-squad", "str")],
        [("spec", "kw"), (":", "txt")],
        [("  project", "kw"), (": ", "txt"), ("payments", "str")],
        [("  agents", "kw"), (":", "txt")],
        [("    - role", "kw"), (": ", "txt"), ("architect", "str"), ("   # 1 leader", "com")],
        [("    - role", "kw"), (": ", "txt"), ("engineer", "str"), ("    # scales 1..n", "com")],
    ]
    cbo, cbh = code_block(cx, yy, cwid, code, title="squad.yaml"); body.append(cbo); yy += cbh + 22
    # callout
    co, coh = callout(cx, yy, cwid, "note", "Reconciliation is level-based",
                      ["Edit the Squad and re-apply — the operator converges the running",
                       "agents to match. No imperative scale commands needed."], t)
    body.append(co); yy += coh + 26
    # inline screenshot
    body.append(T(cx, yy, "What it looks like", 20, t["textHi"], bold=True)); yy += 26
    fbo, iy = browser_frame(cx, yy, cwid, 220, t, "console.ksquad.io/payments/agents")
    body.append(fbo)
    body.append(console_thumb(cx+14, iy+12, cwid-28, 220-(iy-yy)-26, t, "payments-squad · agents"))
    yy += 220 + 20
    # TOC
    body.append(docs_toc(W-240+10, hh+56, t,
                ["The Squad resource", "Agents & roles", "Coordination bus",
                 "Reconciliation", "What it looks like"], active=0))
    # prev/next
    body.append(R(cx, yy, cwid*0.48, 60, t["card"], rx=10, stroke=t["border"], sw=1))
    body.append(T(cx+16, yy+24, "← Previous", 12, t["muted"]))
    body.append(T(cx+16, yy+44, "Quickstart", 14, t["textHi"], bold=True))
    body.append(R(cx+cwid*0.52, yy, cwid*0.48, 60, t["card"], rx=10, stroke=t["border"], sw=1))
    body.append(T(cx+cwid-16, yy+24, "Next →", 12, t["muted"], anchor="end"))
    body.append(T(cx+cwid-16, yy+44, "Operator Guide", 14, t["textHi"], bold=True, anchor="end"))
    return "".join(body), total_h

# ================================================================ PAGE 3: SDK GUIDE
def sdk_guide(t):
    body = []
    hdr, hh = docs_header(t, "Search: plugin events…")
    body.append(hdr)
    total_h = 1240
    body.append(R(0, hh, W, total_h-hh, t["bg"]))
    body.append(docs_sidebar(0, hh, total_h-hh, t, active=3, active_sub=0))
    cx = 250 + 60; cy = hh + 40
    cwid = W - (250+60) - 240 - 40
    body.append(T(cx, cy, "Author Guide", 12, t["muted"]))
    body.append(T(cx+cw("Author Guide",12)+8, cy, "›", 12, t["muted"]))
    body.append(T(cx+cw("Author Guide",12)+22, cy, "Plugin SDK", 12, t["accentText"]))
    body.append(T(cx, cy+44, "Plugin SDK", 34, t["textHi"], bold=True))
    body.append(T(cx, cy+76, "Subscribe to KSquad run events over NATS/JetStream — from any client, out-of-process and read-only.", 15, t["text"]))
    yy = cy + 116

    # --- architecture diagram
    body.append(T(cx, yy, "Plugin architecture", 20, t["textHi"], bold=True)); yy += 30
    dh = 200
    body.append(R(cx, yy, cwid, dh, t["card"], rx=14, stroke=t["border"], sw=1))
    # three columns: Host runtime (outbox->relay) -> NATS/JetStream -> your worker (out-of-process)
    bx = cx + 40; by = yy + 46; bw = 200; bhh = 108
    body.append(R(bx, by, bw, bhh, t["inset"], rx=12, stroke=t["border"], sw=1))
    body.append(T(bx+bw/2, by+30, "Host runtime", 15, t["textHi"], bold=True, anchor="middle"))
    body.append(T(bx+bw/2, by+56, "Postgres outbox", 12, t["muted"], anchor="middle"))
    body.append(T(bx+bw/2, by+80, "→ relay publishes", 12, t["accentText"], anchor="middle"))
    # NATS/JetStream in middle
    mbx = cx + cwid/2 - 70;
    body.append(R(mbx, by+18, 140, 72, t["accentBg"], rx=12, stroke=t["accent"], sw=1.4))
    body.append(T(mbx+70, by+44, "NATS", 15, t["accentText"], bold=True, anchor="middle"))
    body.append(T(mbx+70, by+64, "JetStream · replayable", 11, t["accentText"], anchor="middle"))
    # worker box (out-of-process, read-only observer)
    px = cx + cwid - 40 - bw
    body.append(R(px, by, bw, bhh, t["inset"], rx=12, stroke=t["border"], sw=1))
    body.append(T(px+bw/2, by+26, "Your worker", 15, t["textHi"], bold=True, anchor="middle"))
    body.append(R(px+16, by+38, bw-32, 26, t["card"], rx=6, stroke=t["borderSoft"], sw=1))
    body.append(T(px+bw/2, by+55, "sidecar / standalone", 12, t["text"], anchor="middle"))
    body.append(R(px+16, by+70, bw-32, 26, t["card"], rx=6, stroke=t["borderSoft"], sw=1))
    body.append(T(px+bw/2, by+87, "read-only observer", 12, t["text"], anchor="middle"))
    # arrows
    ay = by + 54
    body.append(L(bx+bw, ay, mbx, ay, t["accent"], 2, op=0.8))
    body.append(f'<path d="M{mbx},{ay} l-8,-5 v10 z" fill="{t["accent"]}"/>')
    body.append(L(mbx+140, ay, px, ay, t["accent"], 2, op=0.8))
    body.append(f'<path d="M{px},{ay} l-8,-5 v10 z" fill="{t["accent"]}"/>')
    body.append(T(cx+cwid/2, yy+dh-16, "subject: ksquad.{entity}.{project}.{squad}.{event}  ·  out-of-process · no console embedding", 12, t["muted"], anchor="middle"))
    yy += dh + 26

    # --- event reference table
    body.append(T(cx, yy, "Event reference", 20, t["textHi"], bold=True)); yy += 28
    # Real NATS/JetStream taxonomy (see website docs/plugin-sdk/event-reference.md):
    # ksquad.{entity}.{project}.{squad}.{event_type} — entities run / workitem / artifact.
    rows = [("run.running", "agent is executing", "{ runId, project, agent }"),
            ("workitem.claimed", "an agent took the item", "{ workItemId, runId, agent }"),
            ("artifact.registered", "an artifact was produced", "{ workItemId, runId, kind }"),
            ("workitem.handoff", "control-plane re-dispatch", "{ workItemId, from, to }"),
            ("memory.written", "an agent persisted memory", "{ agent, scope, key }"),
            ("scm.pushed", "commit / CI status event", "{ repo, sha, status }"),
            ("run.succeeded", "terminal success", "{ runId, phase, initiatedBy }")]
    cols = [("EVENT", 0.28), ("WHEN", 0.34), ("PAYLOAD", 0.38)]
    tbx = cx; tbw = cwid; rh = 40
    body.append(R(tbx, yy, tbw, 36, t["cardRaised"], rx=10))
    xcol = tbx + 20
    for h, frac in cols:
        body.append(T(xcol, yy+23, h, 11, t["muted"], bold=True, ls=1))
        xcol += tbw*frac
    ty2 = yy + 36
    for ri,(ev, wh, pl) in enumerate(rows):
        if ri % 2 == 1:
            body.append(R(tbx, ty2, tbw, rh, t["card"], op=0.5))
        body.append(L(tbx, ty2+rh, tbx+tbw, ty2+rh, t["borderSoft"], 1))
        xcol = tbx + 20
        body.append(T(xcol, ty2+25, ev, 13, t["accentText"], mono=True)); xcol += tbw*cols[0][1]
        body.append(T(xcol, ty2+25, wh, 13, t["text"])); xcol += tbw*cols[1][1]
        body.append(T(xcol, ty2+25, pl, 12.5, t["muted"], mono=True))
        ty2 += rh
    body.append(R(tbx, yy, tbw, 36+rh*len(rows), "none", rx=10, stroke=t["border"], sw=1))
    yy = ty2 + 26

    # --- your first plugin
    body.append(T(cx, yy, "Your first plugin", 20, t["textHi"], bold=True)); yy += 26
    for ln in ["Subscribe to a subject, decode typed events, and run your worker out-of-process."]:
        body.append(T(cx, yy, ln, 14, t["text"])); yy += 24
    yy += 8
    # step pills + code
    step, sw2 = pill(cx, yy, "1 · Subscribe (any NATS client)", t); body.append(step)
    yy += 34
    c1 = [[("$ ", "com"), ("nats sub ", "txt"), ('"ksquad.run.acme.>"', "str")]]
    o1, h1 = code_block(cx, yy, cwid, c1); body.append(o1); yy += h1 + 20
    step, _ = pill(cx, yy, "2 · Decode with the typed catalog", t); body.append(step); yy += 34
    c2 = [
        [("import", "kw"), (" ", "txt"), ('"github.com/ksquad/pkg/events"', "str"), ("  ", "txt"), ("// first-party Go catalog", "com")],
        [("", "txt")],
        [("nc", "num"), (".Subscribe(", "txt"), ('"ksquad.run.acme.>"', "str"), (", ", "txt"), ("func", "kw"), ("(m ", "txt"), ("*nats.Msg", "fn"), (") {", "txt")],
        [("    ev, _ := ", "txt"), ("events", "fn"), (".Decode[", "txt"), ("events.RunSucceeded", "fn"), ("](m.Data)", "txt")],
        [("    ", "txt"), ("log", "fn"), (".Printf(", "txt"), ('"run %s done", ev.RunID', "str"), (")", "txt")],
        [("})", "txt")],
    ]
    o2, h2 = code_block(cx, yy, cwid, c2, title="observer.go"); body.append(o2); yy += h2 + 20
    step, _ = pill(cx, yy, "3 · Run out-of-process", t); body.append(step); yy += 34
    c3 = [[("$ ", "com"), ("go run ", "txt"), ("./observer", "str"), ("   ", "txt"), ("# sidecar or standalone", "com")]]
    o3, h3 = code_block(cx, yy, cwid, c3); body.append(o3); yy += h3 + 22
    co, coh = callout(cx, yy, cwid, "tip", "Transport-first, language-agnostic",
                      ["Subscribe over NATS with any client — the Go pkg/events catalog",
                       "gives first-party typed decoders; JetStream keeps events replayable."], t)
    body.append(co); yy += coh + 20
    # TOC
    body.append(docs_toc(W-240+10, hh+56, t,
                ["Plugin architecture", "Event reference", "Your first plugin"], active=0))
    return "".join(body), max(total_h, yy+40)

# ---------------------------------------------------------------- assemble
def svg(body, h, bg):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h:.0f}" '
            f'viewBox="0 0 {W} {h:.0f}">{DEFS}'
            f'<rect width="{W}" height="{h:.0f}" fill="{bg}"/>{body}</svg>')

def build(name, fn):
    for suffix, t in [("", DARK), ("-light", LIGHT)]:
        b, h = fn(t)
        out = svg(b, h, t["bg"])
        p = f"/mnt/nas/project/ksquad/docs/bmad/ux/website-mocks/{name}{suffix}.svg"
        with open(p, "w") as f:
            f.write(out)
        print("wrote", p, f"({W}x{int(h)})")

if __name__ == "__main__":
    build("01-landing", landing)
    build("02-docs-layout", docs_layout)
    build("03-sdk-guide", sdk_guide)
