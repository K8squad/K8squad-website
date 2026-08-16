#!/usr/bin/env python3
"""Branding-asset pass: swap the v2 8-Crest mark for the Odin Infinity glyph.

Sibling to docs/bmad/ux/apply-odin-infinity.py (ISI-2515/ISI-2662). That pass
targets the ux/website mocks, whose 8-Crest uses integer coords (x="29"). The
branding *source* assets emitted by src/build.py use fixed-decimal coords
(x="29.00") and a trailing space before self-closing fill rects (fill="..." />),
plus a reduced 3-rect favicon variant — so the ux regexes miss them. This pass
matches the build.py `mark_B` output exactly and is likewise **idempotent** and
**generator-agnostic**: it rewrites committed assets/*.svg in place, preserving
each file's own mark-positioning wrapper AND its outlined-Geist wordmark paths
(which cannot be re-outlined here — the Geist .ttf sources are not vendored).

  python3 apply-odin-infinity-branding.py            # default: the mark_B assets
  python3 apply-odin-infinity-branding.py FILE ...   # explicit files

Colour marks (stroke="url(#ringTop)") -> blue Odin glyph. Mono marks
(stroke="#E8EEF9" etc.) -> single-colour Odin in that same ink. mark-formation-*
and mark-helm-* are DISTINCT exploratory marks (not the 8-Crest) and are left
untouched. Odin geometry source of truth: assets/logo-v12/odin-infinity-glyph.svg
"""
import re
import sys
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

# Odin defs: blue gradients + interlace clip paths. clipPath rects are in the
# 512-space of the glyph (referenced from inside scale(0.195313) -> resolve there).
ODIN_DEFS = (
    '<defs>'
    '<linearGradient id="odinL" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#93B7FF"/><stop offset="1" stop-color="#3D7DFF"/></linearGradient>'
    '<linearGradient id="odinR" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#3D7DFF"/><stop offset="1" stop-color="#2E4E8C"/></linearGradient>'
    '<clipPath id="odinCB"><rect x="176" y="256" width="160" height="120"/></clipPath>'
    '<clipPath id="odinCK"><rect x="166" y="256" width="180" height="120"/></clipPath>'
    '</defs>'
)


def odin_mark(sL, sR, nodeOut, nodeIn):
    """Odin Infinity glyph in the 0..100 mark box (scale 100/512 = 0.195313),
    verbatim geometry from odin-infinity-glyph.svg. Stroke/fill values are
    parameterised so colour and mono emissions share one geometry."""
    return (
        '<g transform="scale(0.195313)">'
        f'<path d="M300,148 h96 a60,60 0 0 1 60,60 v96 a60,60 0 0 1 -60,60 h-96 a60,60 0 0 1 -60,-60 v-96 a60,60 0 0 1 60,-60 z" fill="none" stroke="{sR}" stroke-width="40" stroke-linejoin="round"/>'
        f'<path d="M116,148 h96 a60,60 0 0 1 60,60 v96 a60,60 0 0 1 -60,60 h-96 a60,60 0 0 1 -60,-60 v-96 a60,60 0 0 1 60,-60 z" fill="none" stroke="{sL}" stroke-width="40" stroke-linejoin="round"/>'
        f'<g clip-path="url(#odinCB)"><path d="M300,148 h96 a60,60 0 0 1 60,60 v96 a60,60 0 0 1 -60,60 h-96 a60,60 0 0 1 -60,-60 v-96 a60,60 0 0 1 60,-60 z" fill="none" stroke="{sR}" stroke-width="40" stroke-linejoin="round"/></g>'
        '<g transform="rotate(45 256 256)">'
        f'<path d="M196,206 h64 a18,18 0 0 1 18,18 v64 a18,18 0 0 1 -18,18 h-64 a18,18 0 0 1 -18,-18 v-64 a18,18 0 0 1 18,-18 z" fill="none" stroke="{sL}" stroke-width="26" stroke-linejoin="round"/>'
        f'<path d="M252,206 h64 a18,18 0 0 1 18,18 v64 a18,18 0 0 1 -18,18 h-64 a18,18 0 0 1 -18,-18 v-64 a18,18 0 0 1 18,-18 z" fill="none" stroke="{sR}" stroke-width="26" stroke-linejoin="round"/>'
        f'<g clip-path="url(#odinCK)"><path d="M196,206 h64 a18,18 0 0 1 18,18 v64 a18,18 0 0 1 -18,18 h-64 a18,18 0 0 1 -18,-18 v-64 a18,18 0 0 1 18,-18 z" fill="none" stroke="{sL}" stroke-width="26" stroke-linejoin="round"/></g>'
        f'<rect x="230" y="230" width="52" height="52" rx="9" fill="{nodeOut}"/>'
        f'<rect x="237" y="237" width="38" height="38" rx="7" fill="{nodeIn}"/>'
        '</g>'
        '</g>'
    )


COLOR_MARK = odin_mark("url(#odinL)", "url(#odinR)", "#2E4E8C", "#4D8BFF")

# mark_B output: <g> + two rings + (3 corner nodes | 0) + </g>. Fixed-decimal
# coords, trailing space before the self-closing fill rects. First ring stroke
# (group 1) decides colour vs mono.
RINGS = (
    r'<g><rect x="29\.00" y="45\.00" width="42\.00" height="42\.00" rx="13\.00" fill="none" stroke="([^"]*)" stroke-width="9"/>'
    r'<rect x="29\.00" y="13\.00" width="42\.00" height="42\.00" rx="13\.00" fill="none" stroke="[^"]*" stroke-width="9"/>'
)
NODE5 = (
    r'<rect x="41\.00" y="41\.00" width="18\.00" height="18\.00" rx="5\.00" fill="[^"]*" />'
    r'<rect x="44\.50" y="9\.50" width="11\.00" height="11\.00" rx="3\.00" fill="[^"]*" />'
    r'<rect x="44\.50" y="79\.50" width="11\.00" height="11\.00" rx="3\.00" fill="[^"]*" />'
)
NODE3 = r'<rect x="41\.00" y="41\.00" width="18\.00" height="18\.00" rx="5\.00" fill="[^"]*" />'

CREST5_RE = re.compile(RINGS + NODE5 + r'</g>')
CREST3_RE = re.compile(RINGS + NODE3 + r'</g>')


def _sub(m):
    stroke = m.group(1)
    if stroke.startswith("url("):
        return COLOR_MARK           # blue Odin
    return odin_mark(stroke, stroke, stroke, stroke)   # mono Odin in the mark's ink


def process(path):
    src = open(path, encoding="utf-8").read()
    src, n5 = CREST5_RE.subn(_sub, src)
    src, n3 = CREST3_RE.subn(_sub, src)
    marks = n5 + n3

    injected = False
    if 'url(#odinCB)' in src and 'id="odinCB"' not in src:
        src = re.sub(r'(<svg\b[^>]*>)', r'\1' + ODIN_DEFS, src, count=1)
        injected = True

    if marks or injected:
        open(path, "w", encoding="utf-8").write(src)
    return marks, injected


def main(argv):
    if argv:
        files = argv
    else:
        # the mark_B consumers only — NOT mark-formation-* / mark-helm-* (other marks)
        pats = ["mark-8crest-*.svg", "favicon*.svg", "banner-*.svg", "readme-banner.svg"]
        files = sorted({f for p in pats for f in glob.glob(os.path.join(ASSETS, p))})

    tot_m = tot_f = 0
    for f in files:
        m, inj = process(f)
        if m or inj:
            tot_f += 1
            tot_m += m
            print(f"  {os.path.basename(f):34s} marks={m} defs={'+' if inj else '-'}")
        else:
            print(f"  {os.path.basename(f):34s} (already Odin / no 8-Crest)")
    print(f"\nUpdated {tot_f} file(s): {tot_m} mark(s) -> Odin Infinity.")


if __name__ == "__main__":
    main(sys.argv[1:])
