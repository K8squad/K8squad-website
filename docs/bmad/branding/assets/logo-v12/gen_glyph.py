#!/usr/bin/env python3
"""Compact square favicon / app-icon glyph — two links + Valknut knot only
(no dotted chain, no side task boxes), so it stays legible at 16-32px."""
LIGHT, PRIMARY, DARK, BRIGHT = "#93B7FF", "#3D7DFF", "#2E4E8C", "#4D8BFF"
S = 512
CX = CY = 256
TW = 40
HALF = 108
RX = 60
LCX, RCX = CX-92, CX+92

def rr(cx, cy, half, rx):
    x0, y0 = cx-half, cy-half; s = half*2
    return (f"M{x0+rx},{y0} h{s-2*rx} a{rx},{rx} 0 0 1 {rx},{rx} v{s-2*rx} "
            f"a{rx},{rx} 0 0 1 {-rx},{rx} h{-(s-2*rx)} a{rx},{rx} 0 0 1 {-rx},{-rx} "
            f"v{-(s-2*rx)} a{rx},{rx} 0 0 1 {rx},{-rx} z")

left, right = rr(LCX,CY,HALF,RX), rr(RCX,CY,HALF,RX)
KH,KOFF,KW = 50,28,26
kA, kB = rr(CX-KOFF,CY,KH,18), rr(CX+KOFF,CY,KH,18)

def ln(p,g,w): return f'<path d="{p}" fill="none" stroke="url(#{g})" stroke-width="{w}" stroke-linejoin="round"/>'

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" role="img" aria-label="KSquad">
  <defs>
    <linearGradient id="gL" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{LIGHT}"/><stop offset="1" stop-color="{PRIMARY}"/></linearGradient>
    <linearGradient id="gR" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PRIMARY}"/><stop offset="1" stop-color="{DARK}"/></linearGradient>
    <clipPath id="cB"><rect x="{CX-80}" y="{CY}" width="160" height="120"/></clipPath>
    <clipPath id="cK"><rect x="{CX-90}" y="{CY}" width="180" height="120"/></clipPath>
  </defs>
  {ln(right,"gR",TW)}
  {ln(left,"gL",TW)}
  <g clip-path="url(#cB)">{ln(right,"gR",TW)}</g>
  <g transform="rotate(45 {CX} {CY})">
    {ln(kA,"gL",KW)}{ln(kB,"gR",KW)}
    <g clip-path="url(#cK)">{ln(kA,"gL",KW)}</g>
    <rect x="{CX-26}" y="{CY-26}" width="52" height="52" rx="9" fill="{DARK}"/>
    <rect x="{CX-19}" y="{CY-19}" width="38" height="38" rx="7" fill="{BRIGHT}"/>
  </g>
</svg>'''
open("/tmp/odin/odin-infinity-glyph.svg","w").write(svg)
print("wrote glyph", len(svg))
