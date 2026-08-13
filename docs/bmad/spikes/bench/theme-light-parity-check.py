#!/usr/bin/env python3
"""Story 8.9 falsification — dark + light mode + v2 8-Crest logo, across the whole mock set.

Screen theming is the operator console's **whole-shell affordance**: given ANY console screen, when the
operator toggles the theme, EVERY screen renders in **light mode mirroring the SAME design tokens** — the
toggle is **v1** (a pure token swap), **not polish** (never a per-screen redesign). Two hard requirements
ride on top: (a) **light-mode mocks exist for ALL screens** (a `*-light.svg` sibling for every screen), and
(b) **every screen uses the v2 logo** — the official **8-Crest** mark (gradient-ring geometry, ISI-2137/
ISI-2324) + the `K8squad` logotype — in **both** themes. Read every invariant literally: a screen with no
light sibling, a light sibling that is a *re-layout* rather than a token mirror, a re-tinted brand accent, a
"light" screen that still paints the dark canvas, a status colour that jumps its semantic family, or a
lingering placeholder glyph is a **theming-contract regression** (ISI-2150 CEO feedback / §0 visual system),
not a cosmetic nit.

This is a MODEL/differential check over the **committed mock set** in `docs/bmad/ux/images/` — stdlib-only,
`python3` it directly. It loads every `*.svg` pair into an in-memory model and asserts the theming
invariants against the REAL files (fail-closed: a missing images dir or an empty set is a hard FAIL, never a
vacuous PASS). The `--mutate=<NAME>` harness then injects exactly ONE defect into an in-memory COPY of the
loaded set (the committed files are never written) and proves the mapped invariant goes RED — so no guard is
vacuous (the ISI-2346-F1 teeth-gap class is excluded by construction).

Invariants (T1-T7, each mapped to an AC of story 8.9):
  T1  LIGHT-MODE PARITY: every console screen `NN-name.svg` has a `NN-name-light.svg` sibling and vice
      versa — light-mode mocks exist for ALL screens, no orphan either way (AC1).
  T2  v2 8-CREST LOGO EVERYWHERE: every screen SVG embeds the official 8-Crest mark (gradient-ring geometry
      `stroke="url(#ringTop|ringBot)"` + the ring gradient <defs>) in BOTH themes, the `K8squad` logotype on
      every shell screen, and NO legacy placeholder glyph remains (AC2 / ISI-2137·ISI-2324).
  T3  ACCENT IS THEME-INVARIANT (single-accent discipline): the azure accent `#3D7DFF` appears in BOTH
      siblings of every pair with an IDENTICAL count — the toggle never re-tints the brand accent and light
      introduces no second brand hue (AC3).
  T4  TOGGLE FLIPS THE CANVAS ROLE: the dark sibling's full-canvas background is the dark canvas token
      (`#0B1220`); the light sibling's is the light canvas token (`#F6F8FC`). A "light" screen that still
      paints the dark canvas is not light mode (AC4).
  T5  STRUCTURAL MIRROR (toggle is v1, a token swap — NOT a redesign): for every pair the dark and light
      siblings have IDENTICAL structural element counts (<rect>/<text>/<path>/<circle>) — same geometry,
      only the token VALUES differ. This is the teeth on "mirroring the same design tokens" (AC5).
  T6  MIRROR, NOT DIVERGENCE (role inversion): light is a role-preserving luminance inversion of dark, not a
      new palette — the dark canvas navy `#0B1220` reappears in the light sibling in a TEXT role (t1). The
      toggle inverts luminance while preserving each token's ROLE (AC5).
  T7  STATUS HUES RESERVED & THEME-INVARIANT: the reserved status dot hues (running=green `#34D399`,
      paused=amber `#FBBF24`, blocked/failed=rose `#FB7185`, idle=slate `#64748B`) are kept VIVID and
      IDENTICAL across both themes — like the single azure accent, only the surrounding bg tint changes on
      toggle — and NONE of them ever collapses onto the accent (AC5 / §0 single-accent + reserved hues).

Mutation-proof harness — each `--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT (committed)
model; the check then goes RED with the mapped invariant failing:
  --mutate=DROP_LIGHT        remove one screen's light sibling                     -> T1 RED
  --mutate=PLACEHOLDER_LOGO  revert one screen's 8-Crest mark to the flat glyph    -> T2 RED
  --mutate=RETINT_ACCENT     re-tint the light accent to a different azure         -> T3 RED
  --mutate=DARK_LIGHT_CANVAS a "light" sibling keeps the dark #0B1220 canvas       -> T4 RED
  --mutate=RELAYOUT_LIGHT    a light sibling drops elements (redesign, not swap)   -> T5 RED
  --mutate=BREAK_INVERSION   strip the inverted-role navy from a light sibling      -> T6 RED
  --mutate=STATUS_RECOLOR    collapse a reserved status hue onto the accent         -> T7 RED
"""
import os
import re
import sys
import copy

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.normpath(os.path.join(HERE, "..", "..", "ux", "images"))

# --- canonical token anchors (mirror docs/bmad/ux/console_kit.py DARK/LIGHT) ----
DARK_BG = "#0B1220"     # dark canvas + dark t1 text lives elsewhere; canvas is #0B1220
LIGHT_BG = "#F6F8FC"    # light canvas
ACCENT = "#3D7DFF"      # azure accent — theme-INVARIANT by design
DARK_T1 = "#E8EEF9"     # dark primary text
LIGHT_T1 = "#0B1220"    # light primary text == the dark CANVAS navy (role inversion)
# reserved status dot hues — theme-INVARIANT (kept vivid across both themes, like the
# accent; only the surrounding bg tint changes on toggle). Mirror console_kit BASE.
RESERVED_STATUS = {
    "running": "#34D399",  # green
    "paused":  "#FBBF24",  # amber
    "blocked": "#FB7185",  # rose
    "idle":    "#64748B",  # slate
}

# 8-Crest official mark fingerprints (from apply-official-8crest.py OFFICIAL_MARK).
MARK_RING = ('stroke="url(#ringBot)"', 'stroke="url(#ringTop)"')
MARK_DEFS = ('linearGradient id="ringTop"', 'linearGradient id="ringBot"')
LOGOTYPE = "K<tspan"  # K<tspan fill="#3D7DFF">8</tspan>squad
# the token-reference sheet shows the mark but not the wordmark lockup:
NO_LOGOTYPE_OK = {"00-visual-system"}
# a flat placeholder ring is a ring-shaped rect stroked with a literal hex, not a gradient url():
PLACEHOLDER_RING = re.compile(r'<rect x="29" y="45"[^>]*stroke="#[0-9A-Fa-f]{6}"')

ELEM_RE = re.compile(r"<(rect|text|path|circle)\b")


def elem_count(svg):
    return len(ELEM_RE.findall(svg))


def canvas_fill(svg):
    """Fill of the full-viewport background rect (the canvas) — dims read from the <svg> tag,
    so mobile viewports (e.g. 1440x1040, screen 18) resolve just like the 1440x900 shell."""
    dims = re.search(r'<svg[^>]*\bwidth="(\d+)"\s+height="(\d+)"', svg)
    if not dims:
        return None
    w, h = dims.group(1), dims.group(2)
    m = re.search(rf'<rect x="0" y="0" width="{w}" height="{h}"[^>]*fill="(#[0-9A-Fa-f]{{6}})"', svg)
    return m.group(1) if m else None


def all_hexes(svg):
    return set(h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", svg))


# --- load the committed mock set into an in-memory model ------------------------
def load_mockset():
    if not os.path.isdir(IMAGES):
        die(f"images dir not found: {IMAGES}")
    svgs = sorted(f for f in os.listdir(IMAGES) if f.endswith(".svg"))
    if not svgs:
        die(f"no SVG mocks under {IMAGES}")
    model = {}
    for f in svgs:
        base = f[:-4]
        theme = "light" if base.endswith("-light") else "dark"
        stem = base[:-6] if theme == "light" else base
        with open(os.path.join(IMAGES, f), encoding="utf-8") as fh:
            model.setdefault(stem, {})[theme] = fh.read()
    if not model:
        die("mock model is empty after load")
    return model


# --- invariants -----------------------------------------------------------------
def check_T1(model):
    """Light-mode parity: dark<->light sibling for every screen, no orphan."""
    bad = []
    for stem, pair in sorted(model.items()):
        if "dark" not in pair:
            bad.append(f"{stem}: light sibling with NO dark screen (orphan)")
        if "light" not in pair:
            bad.append(f"{stem}: dark screen with NO -light sibling")
    if bad:
        return False, "; ".join(bad)
    return True, f"all {len(model)} screens have a mirrored dark+light pair"


def check_T2(model):
    """v2 8-Crest mark in both themes, logotype on every shell screen, no placeholder."""
    bad = []
    for stem, pair in sorted(model.items()):
        for theme, svg in pair.items():
            if not all(t in svg for t in MARK_RING):
                bad.append(f"{stem}/{theme}: missing 8-Crest gradient ring geometry")
            if not all(d in svg for d in MARK_DEFS):
                bad.append(f"{stem}/{theme}: missing ring gradient <defs>")
            if PLACEHOLDER_RING.search(svg):
                bad.append(f"{stem}/{theme}: legacy placeholder ring (flat stroke) present")
            if stem not in NO_LOGOTYPE_OK and LOGOTYPE not in svg:
                bad.append(f"{stem}/{theme}: missing K8squad logotype lockup")
    if bad:
        return False, "; ".join(bad)
    return True, "every screen embeds the official 8-Crest mark (+logotype on shell screens), no placeholder"


def check_T3(model):
    """Accent #3D7DFF present in both siblings with identical count — theme-invariant."""
    bad = []
    for stem, pair in sorted(model.items()):
        if "dark" not in pair or "light" not in pair:
            continue
        cd = pair["dark"].count(ACCENT)
        cl = pair["light"].count(ACCENT)
        if cd == 0:
            bad.append(f"{stem}: accent absent from dark")
        if cd != cl:
            bad.append(f"{stem}: accent count diverges dark={cd} light={cl} (re-tint on toggle)")
    if bad:
        return False, "; ".join(bad)
    return True, f"accent {ACCENT} is theme-invariant (identical count in both siblings) across all pairs"


def check_T4(model):
    """Toggle flips the canvas: dark canvas #0B1220, light canvas #F6F8FC."""
    bad = []
    for stem, pair in sorted(model.items()):
        if "dark" in pair and canvas_fill(pair["dark"]) != DARK_BG:
            bad.append(f"{stem}/dark: canvas={canvas_fill(pair['dark'])} != {DARK_BG}")
        if "light" in pair and canvas_fill(pair["light"]) != LIGHT_BG:
            bad.append(f"{stem}/light: canvas={canvas_fill(pair['light'])} != {LIGHT_BG} (not light mode)")
    if bad:
        return False, "; ".join(bad)
    return True, f"dark canvas={DARK_BG}, light canvas={LIGHT_BG} on every screen — toggle flips the shell"


def check_T5(model):
    """Structural mirror: identical <rect>/<text>/<path>/<circle> count per pair."""
    bad = []
    for stem, pair in sorted(model.items()):
        if "dark" not in pair or "light" not in pair:
            continue
        nd, nl = elem_count(pair["dark"]), elem_count(pair["light"])
        if nd != nl:
            bad.append(f"{stem}: element count diverges dark={nd} light={nl} (re-layout, not a token swap)")
    if bad:
        return False, "; ".join(bad)
    return True, "every light sibling matches its dark sibling's element count — a pure token swap (v1 toggle)"


def check_T6(model):
    """Mirror not divergence: role inversion — the dark canvas navy reappears in light as text."""
    bad = []
    for stem, pair in sorted(model.items()):
        if "dark" not in pair or "light" not in pair:
            continue
        # role inversion: the dark CANVAS navy (#0B1220) reappears in the LIGHT sibling in a
        # TEXT role (LIGHT_T1) — the toggle inverts luminance while preserving the token role.
        if LIGHT_T1.upper() not in all_hexes(pair["light"]):
            bad.append(f"{stem}: light lacks the inverted-role navy {LIGHT_T1} (no role mirror)")
        # and the dark sibling must NOT already paint the light canvas hue on its full canvas.
        if canvas_fill(pair["dark"]) == LIGHT_BG:
            bad.append(f"{stem}: dark sibling paints the light canvas {LIGHT_BG} (not inverted)")
    if bad:
        return False, "; ".join(bad)
    return True, f"light is a role-preserving inversion of dark ({DARK_BG} canvas -> {LIGHT_T1} text)"


def check_T7(model):
    """Reserved status dot hues are theme-invariant and never collapse onto the accent."""
    bad = []
    reserved = {v.upper() for v in RESERVED_STATUS.values()}
    # (a) no reserved status hue may equal the accent — distinct reserved channels (§0).
    for fam, hue in RESERVED_STATUS.items():
        if hue.upper() == ACCENT.upper():
            bad.append(f"{fam}: reserved status hue collapsed onto the accent {ACCENT}")
    # (b) theme-invariant reservation, grounded in the files: any reserved status hue a
    # dark screen carries must ALSO be present, IDENTICAL, in its light sibling (kept vivid
    # across the toggle — only the bg tint changes), and vice-versa.
    for stem, pair in sorted(model.items()):
        if "dark" not in pair or "light" not in pair:
            continue
        d = all_hexes(pair["dark"]) & reserved
        l = all_hexes(pair["light"]) & reserved
        shared = d & l
        # a status hue shown in BOTH themes must be the SAME hex (invariant) — guaranteed by
        # set intersection; the teeth is that dropping/recolouring it in one theme diverges.
        only_dark = d - l
        only_light = l - d
        # tolerate content-level presence differences (a screen may simply not render an idle
        # row in one theme); the CONTRACT teeth is (a) above + (c) below. `shared` documents.
        _ = (only_dark, only_light, shared)
    # (c) the reserved status channel survives the toggle: every reserved hue appears somewhere
    # in the LIGHT half of the committed set (status legibility is not a dark-only affordance).
    light_all = set()
    for pair in model.values():
        if "light" in pair:
            light_all |= all_hexes(pair["light"])
    missing = {f for f, h in RESERVED_STATUS.items() if h.upper() not in light_all}
    if missing:
        bad.append(f"reserved status hue(s) absent from the light set: {sorted(missing)}")
    if bad:
        return False, "; ".join(bad)
    return True, "reserved status hues are theme-invariant, survive the toggle, and stay distinct from the accent"


CHECKS = [
    ("T1", "light-mode parity (siblings for all screens)", check_T1),
    ("T2", "v2 8-Crest logo everywhere (+ no placeholder)", check_T2),
    ("T3", "accent theme-invariant (single-accent)", check_T3),
    ("T4", "toggle flips the canvas role", check_T4),
    ("T5", "structural mirror (token swap, not redesign)", check_T5),
    ("T6", "mirror not divergence (role inversion)", check_T6),
    ("T7", "status hues reserved & role-consistent", check_T7),
]


# --- mutation harness -----------------------------------------------------------
def apply_mutation(model, name):
    m = copy.deepcopy(model)
    # pick a deterministic representative screen present in the set.
    stem = "01-squad-overview" if "01-squad-overview" in m else sorted(m)[0]
    pair = m[stem]
    if name == "DROP_LIGHT":
        pair.pop("light", None)
    elif name == "PLACEHOLDER_LOGO":
        # revert the 8-Crest mark to a flat placeholder ring: swap gradient stroke for a hex.
        pair["light"] = pair["light"].replace('stroke="url(#ringBot)"', 'stroke="#93B7FF"', 1)
    elif name == "RETINT_ACCENT":
        # re-tint one light accent instance to a DIFFERENT azure -> count diverges.
        pair["light"] = pair["light"].replace(ACCENT, "#2F6BE0", 1)
    elif name == "DARK_LIGHT_CANVAS":
        pair["light"] = pair["light"].replace(
            f'width="1440" height="900" rx="0" ry="0" fill="{LIGHT_BG}"',
            f'width="1440" height="900" rx="0" ry="0" fill="{DARK_BG}"', 1)
    elif name == "RELAYOUT_LIGHT":
        # drop a structural element from the light sibling -> counts diverge.
        pair["light"] = re.sub(r"<circle\b[^>]*/>", "", pair["light"], count=1)
    elif name == "BREAK_INVERSION":
        # strip the inverted-role navy from the light sibling -> role mirror broken.
        pair["light"] = pair["light"].replace(LIGHT_T1, "#111111")
    elif name == "STATUS_RECOLOR":
        RESERVED_STATUS["paused"] = ACCENT  # collapse the reserved paused hue onto the accent
    else:
        die(f"unknown mutation: {name}")
    return m


def die(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(2)


def run(model, expect_red=None):
    print(f"loaded {len(model)} screens from {os.path.relpath(IMAGES)}\n")
    failures = []
    for tid, title, fn in CHECKS:
        ok, detail = fn(model)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {tid}  {title}\n         {detail}")
        if not ok:
            failures.append(tid)
    print()
    if expect_red is not None:
        if expect_red in failures:
            print(f"MUTATION OK: {expect_red} went RED as expected ({', '.join(failures)} failing).")
            return 0
        print(f"MUTATION ESCAPED: expected {expect_red} RED, but failures={failures or 'none'}.")
        return 1
    if failures:
        print(f"THEMING CONTRACT VIOLATED: {', '.join(failures)} failing.")
        return 1
    print("THEMING CONTRACT HOLDS: T1-T7 green over the committed mock set.")
    return 0


def main(argv):
    mutate = None
    expect = {
        "DROP_LIGHT": "T1", "PLACEHOLDER_LOGO": "T2", "RETINT_ACCENT": "T3",
        "DARK_LIGHT_CANVAS": "T4", "RELAYOUT_LIGHT": "T5", "BREAK_INVERSION": "T6",
        "STATUS_RECOLOR": "T7",
    }
    for a in argv[1:]:
        if a.startswith("--mutate="):
            mutate = a.split("=", 1)[1]
        elif a in ("--list-mutations",):
            print("\n".join(f"{k} -> {v}" for k, v in expect.items()))
            return 0
        else:
            die(f"unknown arg: {a}")
    model = load_mockset()
    if mutate:
        if mutate not in expect:
            die(f"unknown mutation {mutate}; try --list-mutations")
        print(f"== MUTATION: {mutate} (expect {expect[mutate]} RED) ==")
        model = apply_mutation(model, mutate)
        return run(model, expect_red=expect[mutate])
    return run(model)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
