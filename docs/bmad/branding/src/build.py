#!/usr/bin/env python3
# K8squad logo system builder. Emits self-contained SVGs (wordmark outlined to
# vector paths, marks are pure geometry) to out/. Palette inherited from console
# ISI-2126 — azure-mono only, no status hues.
import os
from glyphs import layout

SANS = "fonts/GeistSans.ttf"
MONO = "fonts/GeistMono.ttf"
OUT = "out"
os.makedirs(OUT, exist_ok=True)

# ---- palette (ISI-2126 console tokens) ---------------------------------------
AZURE   = "#3D7DFF"   # Squad Azure — hero
AZ_HI   = "#93B7FF"   # lead / highlight tint
AZ_LO   = "#16244A"   # recede
AZ_MID  = "#2E4E8C"   # interpolated mid-low (depth only, still azure family)
CANVAS  = "#0B1220"   # on-dark ground
TEXTHI  = "#E8EEF9"   # knockout / on-dark ink
INK     = "#0B1220"   # on-light ink
BORDER  = "#25324B"   # container border on dark
SQUAD_D = "#9FB2D0"   # 'squad' text on dark (lighter than K8)
SQUAD_L = "#5C6E8A"   # 'squad' text on light

# ---- helpers -----------------------------------------------------------------
def rsq(cx, cy, s, fill, rx=None, extra=""):
    rx = s*0.28 if rx is None else rx
    return (f'<rect x="{cx-s/2:.2f}" y="{cy-s/2:.2f}" width="{s:.2f}" height="{s:.2f}" '
            f'rx="{rx:.2f}" fill="{fill}" {extra}/>')

def ring(cx, cy, s, sw, stroke, rx):
    return (f'<rect x="{cx-s/2:.2f}" y="{cy-s/2:.2f}" width="{s:.2f}" height="{s:.2f}" '
            f'rx="{rx:.2f}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>')

def line(x1,y1,x2,y2,stroke,sw,op=1.0):
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" opacity="{op}"/>')

# ---- MARK B: 8-Crest (hero symbol / avatar) ----------------------------------
# Two stacked rounded-SQUARE rings = two squads huddled, pinched at a shared
# waist node (coordinator + the numeronym-8 lineage hinge). NOT a racetrack.
def mark_B(cs, detail=True, gid=""):
    g = f'g{gid}'
    top = ring(50, 34, 42, 9, cs["ring_top"], 13)
    bot = ring(50, 66, 42, 9, cs["ring_bot"], 13)
    waist = rsq(50, 50, 18, cs["node_hi"], rx=5)
    s = f'<g>{bot}{top}{waist}'
    if detail:
        # two lead-agent nodes on the top (front) squad, one rear on the bottom
        s += rsq(50, 15, 11, cs["node_hi"], rx=3)
        s += rsq(50, 85, 11, cs["node_lo"], rx=3)
    s += '</g>'
    return s

# ---- MARK A: Squad Formation (banner mark) -----------------------------------
# A flying wedge of CRD-square nodes pointing right — lead in front, squad
# falling in behind, thin A2A connectors. Composed, not scattered.
def mark_A(cs, connectors=True, container=True):
    lead=(70,50); mid=[(48,37),(48,63)]; rear=[(27,27),(27,73)]
    parts=[]
    if container:
        parts.append(f'<rect x="6" y="6" width="88" height="88" rx="22" '
                     f'fill="{cs.get("ctr_fill","none")}" stroke="{cs.get("ctr_stroke","none")}" stroke-width="2"/>')
    if connectors:
        c=cs["conn"]
        for m in mid: parts.append(line(lead[0],lead[1],m[0],m[1],c,2.4,0.9))
        parts.append(line(mid[0][0],mid[0][1],rear[0][0],rear[0][1],c,2.4,0.75))
        parts.append(line(mid[1][0],mid[1][1],rear[1][0],rear[1][1],c,2.4,0.75))
    for r in rear: parts.append(rsq(r[0],r[1],15,cs["node_lo"],rx=4.2))
    for m in mid:  parts.append(rsq(m[0],m[1],17,cs["node_mid"],rx=4.8))
    parts.append(rsq(lead[0],lead[1],21,cs["node_hi"],rx=6))
    return "".join(parts)

# ---- MARK C: Helm, Re-crewed (flagged heritage) ------------------------------
# Hub (CRD square) + 5 spokes, each ending in an agent node. NO outer rim ->
# deliberately NOT the k8s ship-wheel. 5 (a squad), fewer than k8s' seven.
import math
def mark_C(cs):
    cx,cy=50,50; R=33; parts=[]
    angles=[-90,-90+72,-90+144,-90+216,-90+288]
    for i,a in enumerate(angles):
        rad=math.radians(a); ex=cx+R*math.cos(rad); ey=cy+R*math.sin(rad)
        col = cs["node_hi"] if i==0 else (cs["node_mid"] if i in (1,4) else cs["node_lo"])
        sw  = cs["conn"]
        parts.append(line(cx,cy,cx+ (R-9)*math.cos(rad), cy+(R-9)*math.sin(rad), sw,3,0.9))
        parts.append(rsq(ex,ey,15 if i==0 else 13,col,rx=4))
    parts.append(rsq(cx,cy,20,cs["node_hub"],rx=6))
    return "".join(parts)

# ---- gradients ---------------------------------------------------------------
def defs():
    return f'''<defs>
  <linearGradient id="ringTop" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{AZ_HI}"/><stop offset="1" stop-color="{AZURE}"/>
  </linearGradient>
  <linearGradient id="ringBot" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{AZURE}"/><stop offset="1" stop-color="{AZ_MID}"/>
  </linearGradient>
  <linearGradient id="wedge" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{AZ_MID}"/><stop offset="1" stop-color="{AZ_HI}"/>
  </linearGradient>
</defs>'''

# colour schemes ---------------------------------------------------------------
CS_COLOR = dict(ring_top="url(#ringTop)", ring_bot="url(#ringBot)", node_hi=AZ_HI,
                node_lo=AZ_MID, node_mid=AZURE, conn=AZURE, node_hub=AZ_HI,
                ctr_stroke=BORDER, ctr_fill="none")
def cs_mono(c):
    return dict(ring_top=c, ring_bot=c, node_hi=c, node_lo=c, node_mid=c, conn=c,
               node_hub=c, ctr_stroke=c, ctr_fill="none")

# ---- wordmark (outlined Geist paths) -----------------------------------------
def wordmark(font, k_col, eight_col, squad_col, size=100, baseline=0):
    # runs: (text, wght, colour). '8' emphasised heavier + hero colour; squad lighter.
    runs=[("K",620,k_col),("8",700,eight_col),("s",480,squad_col),("q",480,squad_col),
          ("u",480,squad_col),("a",480,squad_col),("d",480,squad_col)]
    s = size/1000.0
    x=0; parts=[]
    for text,wght,col in runs:
        gl,w = layout(font, text, wght)
        for gp in gl:
            parts.append(f'<path d="{gp["d"]}" fill="{col}" '
                         f'transform="translate({(x+gp["x"])*s:.2f},{baseline:.2f}) scale({s:.4f},{-s:.4f})"/>')
        x += w
    return "".join(parts), x*s

# ---- file assembly -----------------------------------------------------------
def svg(w,h,body,bg=None,extradefs=""):
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">{defs()}{extradefs}{rect}{body}</svg>')

def write(name, content):
    p=os.path.join(OUT,name)
    open(p,"w").write(content); print("wrote", name, len(content),"B")

def avatar(mark_body, bg, rounded=True, pad=14, size=100):
    # 512 canvas rounded-square ground with mark centred
    inner = 100
    scale = (512-2*0)/100
    g=f'<g transform="translate(0,0) scale(5.12)">{mark_body}</g>'
    ground = f'<rect width="512" height="512" rx="{96 if rounded else 0}" fill="{bg}"/>' if bg else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
            f'viewBox="0 0 512 512">{defs()}{ground}{g}</svg>')

# --- AVATARS (square) ---
write("mark-8crest-on-dark.svg",      avatar(mark_B(CS_COLOR), CANVAS))
write("mark-8crest-on-light.svg",     avatar(mark_B(CS_COLOR), "#FFFFFF"))
write("mark-8crest-reversed.svg",     avatar(mark_B(cs_mono(TEXTHI)), AZURE))   # white-on-azure knockout
write("mark-8crest-mono-dark.svg",    avatar(mark_B(cs_mono(TEXTHI)), CANVAS))  # 1-colour on dark
write("mark-8crest-mono-light.svg",   avatar(mark_B(cs_mono(INK)), "#FFFFFF"))  # 1-colour on light

write("mark-formation-on-dark.svg",   avatar(mark_A(CS_COLOR), CANVAS))
write("mark-formation-on-light.svg",  avatar(mark_A({**CS_COLOR,"ctr_stroke":"#C9D6EC"}), "#FFFFFF"))
write("mark-formation-mono-dark.svg", avatar(mark_A(cs_mono(TEXTHI)), CANVAS))

write("mark-helm-recrewed-on-dark.svg", avatar(mark_C(CS_COLOR), CANVAS))

# --- FAVICON (simplified 8-crest, no corner nodes) ---
def favicon(bg, mono=None):
    cs = cs_mono(mono) if mono else CS_COLOR
    body = mark_B(cs, detail=False)
    g=f'<g transform="scale(0.64) translate(0,0)"><g transform="scale(1)">{body}</g></g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" '
            f'viewBox="0 0 64 64">{defs()}<rect width="64" height="64" rx="14" fill="{bg}"/>{g}</svg>')
write("favicon.svg", favicon(CANVAS))
write("favicon-mono.svg", favicon(AZURE, mono=TEXTHI))

# --- HORIZONTAL BANNER (mark + wordmark + tagline) ---
def banner(bg, k_col, eight_col, squad_col, mark_cs, tagline_col, tagline=True, font=SANS, mono_mark=False):
    W,H=1180,320
    # mark on left
    ms=180; mx=90; my=(H-ms)/2
    markbody = mark_B(mark_cs)
    markg=f'<g transform="translate({mx},{my}) scale({ms/100})">{markbody}</g>'
    # wordmark
    wm, ww = wordmark(font, k_col, eight_col, squad_col, size=190)
    wx = mx+ms+70
    wbase = 150 + (190*0.72)/2   # roughly centre the cap height
    wmg=f'<g transform="translate({wx},{wbase})">{wm}</g>'
    tg=''
    if tagline:
        gl,tw = layout(font,"Your agents, in formation.",440)
        ts=34; tb=wbase+58
        paths=''.join(f'<path d="{g["d"]}" fill="{tagline_col}" transform="translate({wx+g["x"]*ts/1000:.2f},{tb:.2f}) scale({ts/1000:.4f},{-ts/1000:.4f})"/>' for g in gl)
        tg=paths
    ground=f'<rect width="{W}" height="{H}" fill="{bg}"/>' if bg else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{defs()}{ground}{markg}{wmg}{tg}</svg>')

write("banner-on-dark.svg",  banner(CANVAS, TEXTHI, AZURE, SQUAD_D, CS_COLOR, "#7E8CA8"))
write("banner-on-light.svg", banner("#FFFFFF", INK, AZURE, SQUAD_L, {**CS_COLOR,"ctr_stroke":"#C9D6EC"}, "#8794AC"))
write("banner-mono-dark.svg",banner(CANVAS, TEXTHI, TEXTHI, TEXTHI, cs_mono(TEXTHI), "#7E8CA8"))
write("banner-terminal-mono.svg", banner(CANVAS, TEXTHI, AZURE, SQUAD_D, CS_COLOR, "#7E8CA8", font=MONO))

# --- README banner (wide 1280x400, on-dark, tagline) ---
def readme_banner():
    W,H=1280,400
    ms=200; mx=120; my=(H-ms)/2
    markg=f'<g transform="translate({mx},{my}) scale({ms/100})">{mark_B(CS_COLOR)}</g>'
    wm,ww=wordmark(SANS, TEXTHI, AZURE, SQUAD_D, size=210)
    wx=mx+ms+80; wbase=185+(210*0.72)/2
    wmg=f'<g transform="translate({wx},{wbase})">{wm}</g>'
    gl,tw=layout(SANS,"Kubernetes-native agent squads.",440)
    ts=40; tb=wbase+66
    tgp=''.join(f'<path d="{g["d"]}" fill="#8FA0BE" transform="translate({wx+g["x"]*ts/1000:.2f},{tb:.2f}) scale({ts/1000:.4f},{-ts/1000:.4f})"/>' for g in gl)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{defs()}<rect width="{W}" height="{H}" fill="{CANVAS}"/>{markg}{wmg}{tgp}</svg>')
write("readme-banner.svg", readme_banner())

print("ALL SVGs written to", OUT)
