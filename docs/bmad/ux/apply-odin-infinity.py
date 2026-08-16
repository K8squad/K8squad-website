#!/usr/bin/env python3
"""Branding pass: swap the v2 8-Crest mark for the Odin Infinity glyph (ISI-2515).

Henrik-approved 2026-08-14 (ISI-2514). The new primary mark is the **Odin
Infinity** logo — two rounded-square ring links forming an infinity (∞) with a
Valknut interlock knot and a claimed→in-progress→done task chain. Blue-only
palette (#93B7FF / #3D7DFF / #2E4E8C / #4D8BFF). Asset source of truth:
docs/bmad/branding/assets/logo-v12/odin-infinity-glyph.svg (compact glyph, the
correct lockup element for the ~30px console-header size).

This is the successor to `apply-official-8crest.py`. It is an **idempotent,
generator-agnostic** post-render step that rewrites the committed SVG mocks in
place, so the swap reaches *all* screens uniformly — including early screens
(00–07) whose original generators no longer exist. Run it after any re-render:

    python3 apply-odin-infinity.py            # default: images/*.svg
    python3 apply-odin-infinity.py FILE ...   # explicit files

Per file, each edit is guarded so re-runs are no-ops:
  1. MARK — the 8-Crest inner geometry (two stacked gradient rings + three crest
     nodes) OR the earlier 5-rect placeholder is swapped for the Odin Infinity
     glyph geometry, wrapped in scale(100/512) so it fits the exact same 0..100
     artwork box. Each screen's own translate/scale wrapper is preserved, so the
     header lockup does not shift.
  2. DEFS — the glyph's blue gradients + interlace clip paths (odin* ids) are
     injected once per document.

A standalone lockup wordmark `>KSquad<` is upgraded to the official `K8squad`
logotype (azure numeral 8, a k8s pun) — for the self-contained early generators
(09/11/12) that emit the pre-logotype wordmark and rely on this pass. Prose that
merely contains "KSquad" (e.g. "KSquad never stores …") is left untouched. The
now-unused ringTop/ringBot 8-Crest defs are left in place (harmless).

Odin geometry source of truth: docs/bmad/branding/assets/logo-v12/odin-infinity-glyph.svg
"""
import re
import sys
import glob
import os

# Blue gradients + interlace clip paths the Odin glyph strokes reference.
# Injected once per doc. clipPath rects are in the 512-space of the glyph (they
# are referenced from inside the scale group, so userSpaceOnUse resolves there).
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

# Odin Infinity glyph inner geometry, verbatim from odin-infinity-glyph.svg with
# ids namespaced (gL/gR/cB/cK -> odin*), wrapped in scale(100/512) = 0.195313 so
# the 512 artwork box maps onto the 0..100 box the mark wrappers already expect.
ODIN_MARK = (
    '<g transform="scale(0.195313)">'
    '<path d="M300,148 h96 a60,60 0 0 1 60,60 v96 a60,60 0 0 1 -60,60 h-96 a60,60 0 0 1 -60,-60 v-96 a60,60 0 0 1 60,-60 z" fill="none" stroke="url(#odinR)" stroke-width="40" stroke-linejoin="round"/>'
    '<path d="M116,148 h96 a60,60 0 0 1 60,60 v96 a60,60 0 0 1 -60,60 h-96 a60,60 0 0 1 -60,-60 v-96 a60,60 0 0 1 60,-60 z" fill="none" stroke="url(#odinL)" stroke-width="40" stroke-linejoin="round"/>'
    '<g clip-path="url(#odinCB)"><path d="M300,148 h96 a60,60 0 0 1 60,60 v96 a60,60 0 0 1 -60,60 h-96 a60,60 0 0 1 -60,-60 v-96 a60,60 0 0 1 60,-60 z" fill="none" stroke="url(#odinR)" stroke-width="40" stroke-linejoin="round"/></g>'
    '<g transform="rotate(45 256 256)">'
    '<path d="M196,206 h64 a18,18 0 0 1 18,18 v64 a18,18 0 0 1 -18,18 h-64 a18,18 0 0 1 -18,-18 v-64 a18,18 0 0 1 18,-18 z" fill="none" stroke="url(#odinL)" stroke-width="26" stroke-linejoin="round"/>'
    '<path d="M252,206 h64 a18,18 0 0 1 18,18 v64 a18,18 0 0 1 -18,18 h-64 a18,18 0 0 1 -18,-18 v-64 a18,18 0 0 1 18,-18 z" fill="none" stroke="url(#odinR)" stroke-width="26" stroke-linejoin="round"/>'
    '<g clip-path="url(#odinCK)"><path d="M196,206 h64 a18,18 0 0 1 18,18 v64 a18,18 0 0 1 -18,18 h-64 a18,18 0 0 1 -18,-18 v-64 a18,18 0 0 1 18,-18 z" fill="none" stroke="url(#odinL)" stroke-width="26" stroke-linejoin="round"/></g>'
    '<rect x="230" y="230" width="52" height="52" rx="9" fill="#2E4E8C"/>'
    '<rect x="237" y="237" width="38" height="38" rx="7" fill="#4D8BFF"/>'
    '</g>'
    '</g>'
)

# The official 8-Crest inner geometry (two stacked gradient rings + three crest
# nodes). Colours are flexed so both dark/light emissions match.
CREST_RE = re.compile(
    r'<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="41" y="41" width="18" height="18" rx="5" fill="[^"]*"/>'
    r'<rect x="44\.5" y="9\.5" width="11" height="11" rx="3" fill="[^"]*"/>'
    r'<rect x="44\.5" y="79\.5" width="11" height="11" rx="3" fill="[^"]*"/>'
)

# The branding-source 8-Crest emission (docs/bmad/branding/assets/*.svg). Same
# geometry as CREST_RE but the branding generator writes 2-decimal coords and a
# space before the self-closing slash on the filled nodes. 5-rect variant covers
# mark-8crest-on-{dark,light}.svg and banner-on-light.svg.
CREST_DEC_RE = re.compile(
    r'<rect x="29\.00" y="45\.00" width="42\.00" height="42\.00" rx="13\.00" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="29\.00" y="13\.00" width="42\.00" height="42\.00" rx="13\.00" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="41\.00" y="41\.00" width="18\.00" height="18\.00" rx="5\.00" fill="[^"]*" />'
    r'<rect x="44\.50" y="9\.50" width="11\.00" height="11\.00" rx="3\.00" fill="[^"]*" />'
    r'<rect x="44\.50" y="79\.50" width="11\.00" height="11\.00" rx="3\.00" fill="[^"]*" />'
)

# The favicon subset (docs/bmad/branding/assets/favicon.svg): two rings + centre
# node only, no top/bottom crest pips. Must be tried AFTER CREST_DEC_RE so the
# 5-rect marks don't get partially matched (leaving two orphan pips).
FAVICON_DEC_RE = re.compile(
    r'<rect x="29\.00" y="45\.00" width="42\.00" height="42\.00" rx="13\.00" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="29\.00" y="13\.00" width="42\.00" height="42\.00" rx="13\.00" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="41\.00" y="41\.00" width="18\.00" height="18\.00" rx="5\.00" fill="[^"]*" />'
)

# The pre-8-Crest hand-drawn placeholder (defensive: covers any un-enforced doc).
PLACEHOLDER_RE = re.compile(
    r'<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="[^"]*" stroke-width="9"/>'
    r'<rect x="45" y="25\.5" width="10" height="10" rx="2\.8" fill="[^"]*"/>'
    r'<rect x="45" y="64\.5" width="10" height="10" rx="2\.8" fill="[^"]*"/>'
    r'<rect x="42\.5" y="42\.5" width="15" height="15" rx="4\.2" fill="[^"]*"/>'
)


# Standalone lockup wordmark only (exact token) — not prose containing "KSquad".
WORDMARK_OLD = '>KSquad</text>'
WORDMARK_NEW = '>K<tspan fill="#3D7DFF">8</tspan>squad</text>'


def process(path):
    src = open(path, encoding="utf-8").read()
    src, n_crest = CREST_RE.subn(ODIN_MARK, src)
    # 5-rect decimal MUST run before the 3-rect favicon subset (prefix overlap).
    src, n_dec = CREST_DEC_RE.subn(ODIN_MARK, src)
    src, n_fav = FAVICON_DEC_RE.subn(ODIN_MARK, src)
    src, n_ph = PLACEHOLDER_RE.subn(ODIN_MARK, src)
    marks = n_crest + n_dec + n_fav + n_ph

    wordmarks = src.count(WORDMARK_OLD)
    if wordmarks:
        src = src.replace(WORDMARK_OLD, WORDMARK_NEW)

    injected = False
    if 'url(#odinL)' in src and 'id="odinL"' not in src:
        src = re.sub(r'(<svg\b[^>]*>)', r'\1' + ODIN_DEFS, src, count=1)
        injected = True

    if marks or wordmarks or injected:
        open(path, "w", encoding="utf-8").write(src)
    return marks, wordmarks, injected


def main(argv):
    if argv:
        files = argv
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        files = sorted(glob.glob(os.path.join(here, "images", "*.svg")))

    tot_m = tot_w = tot_files = 0
    for f in files:
        m, w, inj = process(f)
        if m or w or inj:
            tot_files += 1
            tot_m += m
            tot_w += w
            print(f"  {os.path.basename(f):42s} marks={m} logotype={w} defs={'+' if inj else '-'}")
        else:
            print(f"  {os.path.basename(f):42s} (already Odin / no mark)")
    print(f"\nUpdated {tot_files} file(s): {tot_m} mark(s), {tot_w} logotype(s) → Odin Infinity / K8squad.")


if __name__ == "__main__":
    main(sys.argv[1:])
