# Console mock conformance checklist — logo v12 + UI-follows-mocks

**Owner:** Graphic Designer · **Issue:** ISI-2749 (board directive on ISI-2170) · **Date:** 2026-08-17

Board directive (ISI-2170): *"make sure our UI follows the mocks build and shared on our
website using our logo v12."* This doc is the **authoritative conformance spec** the console
build must match. The committed mock set in `docs/bmad/ux/images/*.svg` is the **source of
truth for the intended look**; the k8squad.io website is rendered from the same set.

Two things are locked here:
1. **Logo v12 (Odin Infinity)** is the only brand mark. The v2 8-Crest is retired.
2. **Every in-flight console surface** below has a named authoritative mock + a per-screen
   checklist. "UI follows mocks" = the built screen reproduces the mock's chrome, tokens,
   mark, and status semantics — not a re-layout.

---

## 0. Automated conformance gate (run this)

`docs/bmad/spikes/bench/theme-light-parity-check.py` is the runnable regression gate over the
committed mock set. Migrated to **logo v12** in ISI-2749:

```
python3 docs/bmad/spikes/bench/theme-light-parity-check.py            # T1–T7 green, exit 0
python3 docs/bmad/spikes/bench/theme-light-parity-check.py --mutate=PLACEHOLDER_LOGO  # T2 RED
```

| Invariant | Asserts |
|-----------|---------|
| **T1** | every screen has a mirrored `*-light.svg` sibling (no orphan either way) |
| **T2** | every screen embeds the **v12 Odin Infinity** mark (`stroke="url(#odinL\|odinR)"` + blue `<defs>`) in **both** themes, `K8squad` logotype on every shell screen, **no legacy 8-Crest ring** or placeholder glyph |
| **T3** | azure accent `#3D7DFF` is theme-invariant (single-accent discipline) |
| **T4** | toggle flips the canvas: dark `#0B1220` ↔ light `#F6F8FC` |
| **T5** | light is a structural mirror (token swap, not a redesign) |
| **T6** | role-preserving luminance inversion (dark canvas navy reappears as light text) |
| **T7** | reserved status hues are on-token and theme-invariant, none collapses onto the accent |

Baseline is **green** and all 7 single-defect mutations go **RED** (no vacuous guard). Re-run
after any re-render or `apply-odin-infinity.py` pass.

---

## 1. Logo v12 — Odin Infinity (non-negotiable)

Source of truth: `docs/bmad/branding/assets/logo-v12/` · spec: `logo-v12/LOGO-SPEC.md`.

| Context | Asset | Rule |
|---------|-------|------|
| Console header / rail lockup (~30px) | `odin-infinity-glyph.svg` | **Compact glyph** (links + Valknut knot, no chain) + `K8squad` logotype beside it |
| Docs / hero / marketing | `odin-infinity-mark.svg` | Full horizontal mark (links + knot + task chain) |
| Favicon / app icon / avatar (<48px) | `favicon-*.png`, `glyph-*-512.png` | Glyph only |
| Raster fallback | `odin-infinity-{transparent,dark,white}-2048.png` | Where SVG can't be used |

**Palette — blue only, no other hues in the mark:**

| Token | Hex | Role |
|-------|-----|------|
| Light | `#93B7FF` | left link, knot highlight (`odinL` gradient start) |
| Primary | `#3D7DFF` | dominant blue, active task boxes (also the console accent) |
| Dark | `#2E4E8C` | right link, "done" box, depth (`odinR` gradient end) |
| Bright | `#4D8BFF` | active centre diamond |

Ring links carry a light→dark diagonal gradient (`odinL` top-left→primary, `odinR`
primary→dark). Do **not** re-tint, mono-fill, or drop the gradient. The logotype is
`K` `8`(azure `#3D7DFF`) `squad` — never plain "KSquad" for the lockup.

**Retirement:** no v2 8-Crest ring geometry (`ringTop`/`ringBot`) may ship. T2 fails closed on
any survivor.

---

## 2. Theming contract — dark + light tokens (T1–T7)

Light is the dark shell with token **roles luminance-inverted**, single azure accent invariant.
Full token maps live in `docs/bmad/ux/console_kit.py` (`DARK` / `LIGHT`). Key tokens:

| Token | Dark | Light | Role |
|-------|------|-------|------|
| `bg` (canvas) | `#0B1220` | `#F6F8FC` | shell background |
| `rail` | `#0D1728` | `#EEF2F8` | nav rail |
| `card` | `#131D31` | `#FFFFFF` | cards/panels |
| `t1` (primary text) | `#E8EEF9` | `#0B1220` | headings — note dark canvas navy → light text |
| `accent` | `#3D7DFF` | `#3D7DFF` | **theme-invariant** brand azure |
| status running | `#34D399` | `#059669` | reserved — never collapses onto accent |
| status paused | `#FBBF24` | `#B45309` | reserved |
| status blocked/failed | `#FB7185` | `#E11D48` | reserved |
| memory | `#A78BFA` | `#7C3AED` | reserved |

Every screen ships a dark + `*-light` pair. A light sibling that drops/adds elements or repaints
the dark canvas is a contract regression (T4/T5/T6), not polish.

---

## 3. Per-surface conformance — in-flight console screens

### E8 — console shell · ISI-2180 (Next.js App Router, PR#61)

The shell chrome + read surfaces. Authoritative mocks (dark + light each):

| Mock screen | Governs |
|-------------|---------|
| `00-visual-system` | token/status reference sheet — the palette the shell must resolve to |
| `01-squad-overview` | landing: Team→Project→Run-status cards from informer cache |
| `02-run-stream-sse` | live Run progress via the single SSE EventSource (8.2) |
| `03-artifact-inspection` | read-only artifact projection |
| `05-credential-auth-state` | per-agent credential/health derived state |
| `06-build-browser` | tree→diff→code read-only build browser |
| `08-fleet-dashboard` | dashboard tiles (8.8) |
| `09/20/21 team-org` | Team→Agent→Role read-only org projection |
| `10-agent-runs` | agent detail: Run CRDs + run_events + SSE tail |
| `13-nav-ia` | nav rail + breadcrumb IA (Project-rooted hierarchy) |
| `14-project-tickets` | tickets tree |
| `17-login` / `18-mobile-rbac` | auth + responsive RBAC |
| `19-project-dashboard` | project dashboard |

**Shell checklist (every E8 screen):**
- [ ] Header/rail lockup = Odin Infinity **glyph** + `K8squad` logotype (§1), not v2 8-Crest.
- [ ] Dark + light both implemented; theme toggle is a token swap (matches `*-light` sibling 1:1).
- [ ] Canvas `#0B1220` / `#F6F8FC`; single accent `#3D7DFF`; no second brand hue introduced.
- [ ] Status pills use reserved hues (running/paused/blocked/idle/memory) — never the accent.
- [ ] Nav rail + breadcrumb match `13-nav-ia` (Project-rooted, not flat).
- [ ] Favicon set = `logo-v12/favicon-*`.

### E10.3 — discussion room in console · ISI-2704

Authoritative mock: **`07-discussion-room.svg` / `07-discussion-room-light.svg`**.

- [ ] Room layout, thread/message affordances, and participant chrome match screen 07.
- [ ] Header lockup = Odin glyph (§1); dark + light per the pair.
- [ ] Reuses the shell tokens (card `#131D31`/`#FFFFFF`, dividers, `t1`–`t4` text ramp).
- [ ] Discussion room is presented as a **read/coordinate surface**, consistent with the
      "not a coordination back-channel" guardrail (ISI-2705) — no controls the mock doesn't show.
- [ ] Memory/reference chips use the reserved `mem` hue, not the accent.

### E11.6 — synced-state console + CI-failure auto-post · ISI-2741

Authoritative mock: **`22-scm-synced-state.svg` / `22-scm-synced-state-light.svg`** (added this cycle).

- [ ] SCM sync-state surface (branch/PR/CI status) matches screen 22's layout.
- [ ] CI-failure state uses the reserved **failed/blocked** hue (`#FB7185` dark / `#E11D48` light),
      success uses **running/succeeded** green — never the accent azure.
- [ ] Auto-post/annotation affordance rendered exactly where the mock places it.
- [ ] Header lockup = Odin glyph (§1); dark + light per the pair.

---

## 4. Sign-off

- [ ] `theme-light-parity-check.py` green (T1–T7) — automated logo-v12 + theming proof.
- [ ] Each surface above visually reconciled against its named mock (dark **and** light).
- [ ] No v2 8-Crest, no placeholder glyph, no off-palette hue in any shipped screen.

Questions on intended look → Graphic Designer (this issue). Spec/implementation-readiness for
the console surfaces is tracked with the Architect (ISI-2748).
