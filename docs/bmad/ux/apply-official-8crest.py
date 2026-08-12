#!/usr/bin/env python3
"""Branding enforcement pass for KSquad operator-console mocks (ISI-2324).

CEO directive 2026-08-12: every console mock must embed the *official* K8squad
logo — the v2 8-Crest mark (`mark-8crest`, from the Graphic Designer's asset set,
ISI-2137) — instead of the earlier hand-drawn placeholder glyph.

This is an **idempotent, generator-agnostic** post-render step. It rewrites the
committed SVG mocks in place so the fix applies uniformly to *all* screens,
including the early screens (00–07) whose original generators no longer exist.
Run it after any re-render of the mock set:

    python3 apply-official-8crest.py            # default: images/*.svg
    python3 apply-official-8crest.py FILE ...   # explicit files

Two edits per file, each guarded so re-runs are no-ops:
  1. MARK  — the 5-rect placeholder glyph (two flat rings + three flat nodes) is
     swapped for the official 8-Crest inner geometry (gradient rings + crest
     nodes). The placeholder and official rings share the exact same rects, so
     the swap preserves each screen's own translate/scale wrapper — the lockup
     does not shift.
  2. LOGOTYPE — the standalone lockup wordmark `>KSquad<` becomes the official
     logotype `K8squad` with an azure numeral 8 (a k8s pun), via a <tspan>.
     Prose that merely contains "KSquad" (e.g. "KSquad never stores …") is left
     untouched — in running copy the product is written "KSquad", like
     K8s ↔ Kubernetes.
Gradient <defs> (ringTop/ringBot) are injected once per document.

Official geometry source of truth: docs/bmad/branding/assets/mark-8crest-on-dark.svg
"""
import re
import sys
import glob
import os

# Gradient defs the official mark's ring strokes reference. Injected once per doc.
LOGO_DEFS = (
    '<defs>'
    '<linearGradient id="ringTop" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#93B7FF"/><stop offset="1" stop-color="#3D7DFF"/>'
    '</linearGradient>'
    '<linearGradient id="ringBot" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#3D7DFF"/><stop offset="1" stop-color="#2E4E8C"/>'
    '</linearGradient>'
    '</defs>'
)

# Official 8-Crest inner geometry (0..100 artwork space — same bounds as the
# placeholder rings, so the wrapping transform is preserved). Verbatim from the
# Graphic Designer's mark-8crest-on-dark.svg inner <g>, minus the 512px plate.
OFFICIAL_MARK = (
    '<rect x="29" y="45" width="42" height="42" rx="13" fill="none" stroke="url(#ringBot)" stroke-width="9"/>'
    '<rect x="29" y="13" width="42" height="42" rx="13" fill="none" stroke="url(#ringTop)" stroke-width="9"/>'
    '<rect x="41" y="41" width="18" height="18" rx="5" fill="#93B7FF"/>'
    '<rect x="44.5" y="9.5" width="11" height="11" rx="3" fill="#93B7FF"/>'
    '<rect x="44.5" y="79.5" width="11" height="11" rx="3" fill="#2E4E8C"/>'
)

# The placeholder glyph: two flat rings (any stroke colour) + three flat nodes
# (any fill). Byte-identical across every screen except for the colour values.
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
    marks = wordmarks = 0

    # 1. mark geometry
    src, marks = PLACEHOLDER_RE.subn(OFFICIAL_MARK, src)

    # 2. lockup logotype (leaves prose untouched)
    if WORDMARK_OLD in src:
        wordmarks = src.count(WORDMARK_OLD)
        src = src.replace(WORDMARK_OLD, WORDMARK_NEW)

    # 3. inject gradient defs once (only meaningful if a gradient is now referenced)
    injected = False
    if 'url(#ringTop)' in src and 'id="ringTop"' not in src:
        src = re.sub(r'(<svg\b[^>]*>)', r'\1' + LOGO_DEFS, src, count=1)
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
            print(f"  {os.path.basename(f):42s} (already official / no logo)")
    print(f"\nUpdated {tot_files} file(s): {tot_m} mark(s), {tot_w} logotype(s).")


if __name__ == "__main__":
    main(sys.argv[1:])
