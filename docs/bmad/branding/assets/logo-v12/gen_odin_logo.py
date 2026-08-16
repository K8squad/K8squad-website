#!/usr/bin/env python3
"""Odin Infinity logo (v12) — hand-crafted production SVG.
Design spec (ISI-2514, Henrik-approved 2026-08-14):
  - Two rounded-square ring links forming an infinity (8-Crest rotated 90 into oo)
  - Valknut-inspired interlocking weave at the centre overlap
  - Three blue task boxes: claimed (left) -> in-progress (centre diamond) -> done (right)
  - Blue-only palette: #93B7FF / #3D7DFF / #2E4E8C
  - Subtle dotted task chain connecting the three boxes
Rendered flat-vector with a light top-left / dark bottom-right tube bevel.
"""

# ---- palette -------------------------------------------------------------
LIGHT   = "#93B7FF"
PRIMARY = "#3D7DFF"
DARK    = "#2E4E8C"
BRIGHT  = "#4D8BFF"   # active task box

# ---- geometry ------------------------------------------------------------
VB_W, VB_H = 720, 400
CY  = 200
TW  = 30            # tube (stroke) width
RX  = 60            # link corner radius
HALF = 105          # link half-side (centreline)
LCX, RCX = 250, 470 # left / right link centres
CX = (LCX + RCX) / 2  # centre of overlap = 360

def rrect_path(cx, cy, half, rx):
    """Closed rounded-square centreline path."""
    x0, y0 = cx - half, cy - half
    s = half * 2
    return (f"M{x0+rx},{y0} h{s-2*rx} a{rx},{rx} 0 0 1 {rx},{rx} "
            f"v{s-2*rx} a{rx},{rx} 0 0 1 {-rx},{rx} h{-(s-2*rx)} "
            f"a{rx},{rx} 0 0 1 {-rx},{-rx} v{-(s-2*rx)} "
            f"a{rx},{rx} 0 0 1 {rx},{-rx} z")

left_path  = rrect_path(LCX, CY, HALF, RX)
right_path = rrect_path(RCX, CY, HALF, RX)

# centre Valknut knot: two small rounded-square rings rotated 45 (diamonds),
# offset left/right of centre and interlaced -> woven medallion.
KH   = 46     # knot loop half-side
KOFF = 26     # horizontal offset of each loop from centre
KW   = 20     # knot tube width
knotA_path = rrect_path(CX - KOFF, CY, KH, 16)   # left diamond loop  (light)
knotB_path = rrect_path(CX + KOFF, CY, KH, 16)   # right diamond loop (dark)

def link(path, grad, w=TW):
    return (f'<path d="{path}" fill="none" stroke="url(#{grad})" '
            f'stroke-width="{w}" stroke-linejoin="round"/>')

# clip: bottom-centre band -> right link drawn over left there (link interlock)
weave_clip_bottom = f'<rect x="{CX-70}" y="{CY}" width="140" height="{CY-60}"/>'
# clip: bottom half of knot -> loop B drawn over loop A there (knot interlock)
knot_weave = f'<rect x="{CX-90}" y="{CY}" width="180" height="120"/>'

# task boxes on the dotted chain
BOX = 38
def sq(cx, cy, s, fill, rx=8):
    return f'<rect x="{cx-s/2}" y="{cy-s/2}" width="{s}" height="{s}" rx="{rx}" fill="{fill}"/>'
def diamond(cx, cy, s, fill, rx=7):
    return (f'<g transform="rotate(45 {cx} {cy})">'
            f'<rect x="{cx-s/2}" y="{cy-s/2}" width="{s}" height="{s}" rx="{rx}" fill="{fill}"/></g>')

LBOX_X, RBOX_X = 210, 510
chain_y = CY

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VB_W} {VB_H}" role="img" aria-label="KSquad — Odin Infinity">
  <defs>
    <linearGradient id="gLeft" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{LIGHT}"/><stop offset="1" stop-color="{PRIMARY}"/>
    </linearGradient>
    <linearGradient id="gRight" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{PRIMARY}"/><stop offset="1" stop-color="{DARK}"/>
    </linearGradient>
    <linearGradient id="gKnot" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{LIGHT}"/><stop offset="1" stop-color="{DARK}"/>
    </linearGradient>
    <clipPath id="clipBottom">{weave_clip_bottom}</clipPath>
    <clipPath id="clipKnot">{knot_weave}</clipPath>
  </defs>

  <!-- dotted task chain -->
  <line x1="{LBOX_X}" y1="{chain_y}" x2="{RBOX_X}" y2="{chain_y}"
        stroke="{DARK}" stroke-width="4" stroke-linecap="round"
        stroke-dasharray="1 14" opacity="0.85"/>

  <!-- interlocked links: right, then left over, then right-over-left at bottom -->
  {link(right_path, "gRight")}
  {link(left_path, "gLeft")}
  <g clip-path="url(#clipBottom)">{link(right_path, "gRight")}</g>

  <!-- centre Valknut knot: two 45-rotated diamond loops interlaced -->
  <g transform="rotate(45 {CX} {CY})">
    {link(knotA_path, "gLeft", KW)}
    {link(knotB_path, "gRight", KW)}
    <g clip-path="url(#clipKnot)">{link(knotA_path, "gLeft", KW)}</g>
  </g>

  <!-- task boxes: claimed (bright) -> in-progress (centre diamond) -> done (dark) -->
  {sq(LBOX_X, chain_y, BOX, PRIMARY)}
  <g transform="rotate(45 {CX} {CY})"><rect x="{CX-23}" y="{CY-23}" width="46" height="46" rx="8" fill="{DARK}"/></g>
  {diamond(CX, CY, 38, BRIGHT)}
  {sq(RBOX_X, chain_y, BOX, DARK)}
</svg>'''

import os
os.makedirs("/tmp/odin", exist_ok=True)
with open("/tmp/odin/odin-infinity-mark.svg", "w") as f:
    f.write(svg)
print("wrote /tmp/odin/odin-infinity-mark.svg", len(svg), "bytes")
