---
title: K8squad Branding Guidelines — Logo System (v2)
owner: Architect (Winston)
status: active
date: 2026-08-12
issue: ISI-2324
source-of-truth: docs/bmad/branding/assets/ (built from docs/bmad/branding/src/build.py)
upstream: ISI-2137 (Graphic Designer — v2 asset production)
stepsCompleted:
  - logo-system-and-marks
  - color-tokens
  - variants-and-usage
  - sizing-clearspace-minimums
  - wordmark-logotype-rule
  - dos-and-donts
  - asset-manifest
  - console-application-and-enforcement
---

# K8squad Branding Guidelines — Logo System (v2)

CEO directive (2026-08-12): every console screen, nav-rail header, login screen,
and mobile mock must embed the **official** K8squad logo — the v2 **8-Crest**
mark. This document is the usage contract for that mark and its lockups.

All assets referenced here live in [`assets/`](./assets/) and are reproducible
from [`src/build.py`](./src/build.py) + [`src/render.js`](./src/render.js)
(no system libraries required beyond Node + `@resvg/resvg-js`).

---

## 1. The logo system

The brand ships **one primary mark** and two secondary/heritage marks. Use the
primary for everything unless you have a specific documented reason.

| Role | Name | File stem | When to use |
|------|------|-----------|-------------|
| **Primary** | **8-Crest** | `mark-8crest` | App icon, avatar, nav-rail lockup, login/mobile splash, favicon — **the default everywhere** |
| Secondary | Squad Formation | `mark-formation` | Wide banners / marketing where a horizontal "flying wedge" reads better than the crest |
| Heritage | Helm, Re-crewed | `mark-helm-recrewed` | Flagged heritage mark; do **not** use in the console without design sign-off |

### The 8-Crest (primary)

Two stacked rounded-**square** rings — two squads huddled, pinched at a shared
waist node (the coordinator, and the numeronym-**8** lineage hinge). Three nodes:
two lead-agent nodes on the front (top) squad, one rear node on the bottom squad.
It is **not** a racetrack/pill and **not** the number 8 in a typeface — the square
corners encode the CRD/Kubernetes-object lineage.

Artwork is authored in a **0–100 unit** space (rings span y13–y87, nodes
y9.5–y90.5). On a plate it sits on a 512×512 ground with a 96px (≈18.75%) corner
radius.

---

## 2. Color tokens

The mark is **azure-mono** — a single hue family, no status colors. Ring strokes
use vertical gradients so the crest reads with depth at any size.

| Token | Hex | Use |
|-------|-----|-----|
| Squad Azure (hero) | `#3D7DFF` | Numeral **8** in the logotype; mid nodes; gradient anchor |
| Lead / highlight | `#93B7FF` | Lead nodes; top of ring gradient |
| Interpolated mid-low | `#2E4E8C` | Rear node; bottom of ring gradient (depth) |
| On-dark canvas | `#0B1220` | Dark plate / dark console ground |
| On-dark ink | `#E8EEF9` | Wordmark & mono mark on dark |
| On-light ink | `#0B1220` | Wordmark & mono mark on light |

Ring gradients (required in any document that renders the color mark):

```
ringTop:  #93B7FF → #3D7DFF   (vertical)
ringBot:  #3D7DFF → #2E4E8C   (vertical)
```

These are injected as `<defs>` by the console kits (`svg_open`/`head`) and by the
enforcement pass — see §8.

---

## 3. Variants & when to use each

| Variant | File | Background it's built for |
|---------|------|---------------------------|
| On dark (color) | `mark-8crest-on-dark.svg` (+ `-256/-512.png`) | Dark UI (`#0B1220`), the console default |
| On light (color) | `mark-8crest-on-light.svg` | Light UI (`#FFFFFF`/`#F6F8FC`) |
| Reversed | `mark-8crest-reversed.svg` | White knockout on a solid Squad-Azure fill |
| Mono on dark | `mark-8crest-mono-dark.svg` | Single-ink (`#E8EEF9`) on dark — print, watermark, ≤16px |
| Mono on light | `mark-8crest-mono-light.svg` | Single-ink (`#0B1220`) on light |

**Inner geometry is identical** across on-dark and on-light — only the plate
background changes. The mark's node colors (`#93B7FF`, `#2E4E8C`) are tuned to
read on **both** grounds, so the same inner mark drops into a dark or light nav
rail unchanged. Below ~24px prefer a **mono** variant — gradients muddy at
favicon scale (the favicon is a simplified crest with the corner nodes dropped).

---

## 4. Sizing, clear-space & minimums

- **Clear space:** keep free space of at least **½ the mark's height** on all
  sides of the mark (and of the mark+logotype lockup). Nothing — text, rules,
  other glyphs — intrudes.
- **Minimum size (color/gradient mark):** **24px** tall. Below this, switch to a
  mono variant.
- **Minimum size (mono mark):** **16px** (favicon-proven).
- **Do not** re-space the three nodes or change ring stroke weight (9 units in
  the 0–100 space) to "fix" small sizes — use the mono variant instead.
- Console rail lockup renders the mark at ~34px with the logotype at 17px; the
  login/mobile splash renders it larger (scale 0.9–0.95) with a 26–30px logotype.

---

## 5. Wordmark / logotype rule

There are **two** correct written forms, and they are not interchangeable:

- **Logotype (stylized):** **K8squad** — the letter **8** is set in Squad Azure
  (`#3D7DFF`); **K** and **squad** take the surrounding ink color. This is the
  lockup wordmark that sits beside the mark. It is a k8s numeronym pun.
- **Prose (running copy):** write **"KSquad"** — like *K8s ↔ Kubernetes*, running
  sentences use the readable spelling. Body copy in the mocks (e.g. "KSquad never
  stores a shared master credential") is intentionally left as "KSquad".

In markup the logotype is one text run with a `<tspan fill="#3D7DFF">8</tspan>`;
in the kits it is emitted by `logotype()`. Never hand-render the lockup wordmark
as flat "KSquad" or "K8SQUAD".

The optional descriptor line under the lockup is **"operator console"**
(lowercase, wide tracking), in the tertiary text color.

---

## 6. Do / Don't

**Do**
- Use the on-dark color mark on the console; the on-light mark on light surfaces.
- Keep the mark's aspect ratio and internal proportions locked.
- Use a mono variant under 24px or on busy/photographic backgrounds.

**Don't**
- Recolor the mark outside the azure family or apply status hues to it.
- Redraw the rings as pills/racetracks or the nodes as circles.
- Add drop shadows, outer glows, or a bounding stroke.
- Rotate, shear, or stretch the mark; don't detach a node.
- Type the lockup wordmark as "KSquad" (that's the prose form) or all-caps.

---

## 7. Asset manifest

Committed under [`assets/`](./assets/) (SVG + rasterized PNG, built by
`src/build.py` → `src/render.js`):

- **Marks:** `mark-8crest-{on-dark,on-light,reversed,mono-dark,mono-light}` ·
  `mark-formation-{on-dark,on-light,mono-dark}` · `mark-helm-recrewed-on-dark`
- **Favicons:** `favicon.svg` · `favicon-mono.svg` · `favicon-{16,32,48,64}.png`
- **Banners:** `banner-{on-dark,on-light,mono-dark,terminal-mono}` ·
  `readme-banner` (taglines: *"Your agents, in formation."* /
  *"Kubernetes-native agent squads."*)

To rebuild: `cd src && python3 build.py && node render.js` (writes to `out/`;
copy the marks/banners/favicons back into `assets/`).

---

## 8. Console application & enforcement

The operator-console mocks live in `docs/bmad/ux/images/` and are generated by
`gen-*.py` on top of shared kits (`console_kit.py`, `console_kit_ia.py`,
`console_kit_rbac.py`). The mark is embedded through three shared entry points —
`build_logo` (rail lockup), the inline flat rail, and `big_logo` (login/mobile
splash) — all of which now emit the official 8-Crest via `mark_8crest()` +
`logotype()`, with `LOGO_DEFS` injected by `svg_open`/`head`.

**Enforcement pass (single source of branding truth for outputs):**
[`docs/bmad/ux/apply-official-8crest.py`](../ux/apply-official-8crest.py) is an
**idempotent, generator-agnostic** post-render step. It swaps any remaining
placeholder glyph for the official mark, upgrades the lockup wordmark to the
azure-8 logotype, and injects the gradient `<defs>`. It exists because the early
screens (00–07) have no surviving generator, and a few older gens (09/11/12)
still duplicate the lockup inline.

> **Run `python3 apply-official-8crest.py` after any re-render of the mock set.**
> It is a no-op on already-official files. (ponytail: some older gens still
> carry the placeholder in source — the enforcement pass is the mandatory
> final step until those inline lockups are migrated to the shared helpers.)

**Verification** (how "all mocks use the logo" was checked for ISI-2324):

```
# every mock references the official gradient mark, none carries the placeholder
grep -l 'url(#ringTop)' images/*.svg | wc -l     # → 44 / 44
grep -l 'rx="2.8"'      images/*.svg | wc -l     # → 0   (old node signature)
grep -l 'id="ringTop"'  images/*.svg | wc -l     # → 44 / 44 (defs present)
```

Screens 00–21 (dark + light, SVG + 1.5× PNG) all pass.
