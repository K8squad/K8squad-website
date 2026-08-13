# Story 8.9: Dark + light mode + v2 8-Crest logo (whole-shell theming)

Status: ready-for-review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This is the operator console's whole-shell theming contract, not a per-screen paint job.** Given ANY
> console screen, toggling the theme must render EVERY screen in light mode **mirroring the same design
> tokens** — the toggle is **v1, a pure token swap, not polish/redesign**. Read every AC literally: a screen
> with no light sibling, a light sibling that is a *re-layout* rather than a token mirror, a re-tinted brand
> accent, a "light" screen that still paints the dark canvas, or a lingering placeholder glyph is a
> **theming-contract regression** (ISI-2150 CEO feedback / §0 visual system), not a cosmetic nit.

## Story

As the **operator using the KSquad console**,
I want a **theme toggle that renders every screen in a light mode which mirrors the exact same design tokens as the dark shell, with the official v2 8-Crest logo on every screen in both themes**,
so that **I can work in whichever mode suits my environment without any screen looking different, off-brand, or half-migrated — the light mode is the dark shell with its token roles luminance-inverted, never a divergent second design.**

## Context & prerequisites (read first)

- **UX system of record:** `docs/bmad/ux/README.md` §0 ("Revision v2 — logo + light mode", ISI-2150) and §0j ("official v2 8-Crest branding", ISI-2324) — the locked visual system (dark canvas `#0B1220` + a **single** azure accent `#3D7DFF`; reserved status hues; v2 8-Crest rail lockup; **light mode mirrors token roles**). The dark→light token map is audited: the accent is **theme-invariant**; status **dot** hues stay vivid and identical across themes (only the surrounding bg tint changes).
- **Shared kit:** `docs/bmad/ux/console_kit.py` — the `DARK`/`LIGHT` token maps, `mark_8crest()` + `logotype()` (the v2 lockup), and `write_pair()` which emits every screen's `*.svg` **and** `*-light.svg` from one build function. `apply-official-8crest.py` is the idempotent, generator-agnostic branding pass that guarantees the 8-Crest mark on the early screens (00–07) whose original generators no longer exist.
- **Assets:** the v2 8-Crest mark geometry (`docs/bmad/branding/assets/mark-8crest-on-dark.svg`, ISI-2137) — the gradient-ring + crest-node lockup embedded via `LOGO_DEFS` + `mark_8crest()`.
- **Depends on:** **ISI-2137** (v2 8-Crest logo assets — *landed*, embedded via ISI-2324's enforcement pass) and **ISI-2150** (mock revision that shipped the light-mode siblings + swapped in the v2 lockup — *landed*). Both dependency deliverables are present in `docs/bmad/ux/images/`; this story **formalises and locks** the theming contract over that committed set.
- **Scope:** the toggle is **v1** — the mechanism is the audited token swap (`DARK` ⇄ `LIGHT`), proven by every screen shipping a byte-mirrored light sibling. Runtime toggle-persistence polish (localStorage, prefers-color-scheme, animated transition) is explicitly **out of scope** (§0 "Toggle is v1, not polish").

## Acceptance Criteria

**AC1 — light-mode mocks exist for ALL screens (parity).**
Given the committed mock set in `docs/bmad/ux/images/`, When it is enumerated, Then **every** console screen `NN-name.svg` has a `NN-name-light.svg` sibling and **vice-versa** — no dark screen without a light mirror, and no orphan light file. Light mode is available on every screen, not a subset.

**AC2 — the v2 8-Crest logo is on every screen, in both themes.**
Given any screen SVG (dark or light), When its brand lockup is inspected, Then it embeds the **official v2 8-Crest mark** — the gradient-ring geometry (`stroke="url(#ringTop)"` / `stroke="url(#ringBot)"`) plus the ring gradient `<defs>` — and the `K8squad` logotype lockup on every shell screen (the `00` token-reference sheet shows the mark without the wordmark, by design). And **no legacy placeholder glyph** (a flat-stroke ring rect) remains anywhere.

**AC3 — the brand accent is theme-invariant (single-accent discipline).**
Given a dark/light pair, When the azure accent `#3D7DFF` is counted, Then it appears in **both** siblings with an **identical count** — the toggle never re-tints the brand accent, and light mode introduces no second brand hue. One azure, both themes.

**AC4 — the toggle flips the canvas role.**
Given a pair, When each sibling's full-viewport background rect is read (dimensions taken from the `<svg>` tag, so mobile viewports resolve too), Then the **dark** sibling's canvas is the dark token `#0B1220` and the **light** sibling's canvas is the light token `#F6F8FC`. A "light" screen that still paints the dark canvas is not light mode.

**AC5 — structural mirror: the toggle is a token swap, not a redesign (the crux).**
Given a pair, When the structural element counts (`<rect>`/`<text>`/`<path>`/`<circle>`) of both siblings are compared, Then they are **identical** — same geometry, same layout, only the token **values** differ. This is the teeth on "mirroring the same design tokens": a light sibling with a different element count is a re-layout (polish/redesign), which violates the v1-toggle contract.

**AC6 — mirror, not divergence (role inversion).**
Given a pair, When the light sibling's hues are inspected, Then the toggle is a **role-preserving luminance inversion**: the dark **canvas** navy `#0B1220` reappears in the light sibling in a **text** role (light primary text `t1`), and the dark sibling never paints the light canvas hue. Light is dark with token roles inverted, not a new palette.

**AC7 — status hues reserved & theme-invariant.**
Given the reserved status dot hues — running=green `#34D399`, paused=amber `#FBBF24`, blocked/failed=rose `#FB7185`, idle=slate `#64748B` — When a screen renders status in either theme, Then those hues are kept **vivid and identical across both themes** (like the accent; only the surrounding bg tint changes on toggle), the reserved channel **survives the toggle** (every reserved hue is present in the light half of the set), and **none** of them ever collapses onto the accent `#3D7DFF`.

## Runnable falsification (the gate)

`docs/bmad/spikes/bench/theme-light-parity-check.py` — stdlib-only, `python3` it directly. It loads the
committed `docs/bmad/ux/images/*.svg` pairs into an in-memory model and asserts **T1–T7 ≡ AC1–AC7** against
the **real** files (fail-closed: a missing images dir or an empty set is a hard FAIL, never a vacuous PASS).

- **Baseline:** `python3 theme-light-parity-check.py` → **T1–T7 green** over all 22 screens, exit 0.
- **Mutation-proof (each injects ONE defect into an in-memory copy — committed files untouched — and the mapped invariant goes RED):**
  - `--mutate=DROP_LIGHT` → **T1** (a screen loses its light sibling)
  - `--mutate=PLACEHOLDER_LOGO` → **T2** (a screen's 8-Crest mark reverts to the flat placeholder)
  - `--mutate=RETINT_ACCENT` → **T3** (the light accent is re-tinted to a different azure)
  - `--mutate=DARK_LIGHT_CANVAS` → **T4** (a "light" sibling keeps the dark `#0B1220` canvas)
  - `--mutate=RELAYOUT_LIGHT` → **T5** (a light sibling drops an element — a redesign, not a swap)
  - `--mutate=BREAK_INVERSION` → **T6** (the inverted-role navy is stripped from a light sibling)
  - `--mutate=STATUS_RECOLOR` → **T7** (a reserved status hue collapses onto the accent)

No guard is vacuous — the ISI-2346-F1 teeth-gap class is excluded by construction (every invariant has a
mutation that flips it RED).

## Tasks / Subtasks

- [x] **Task 1 — Light-mode siblings for every screen (AC1).** All 22 screens (`00`–`21`) ship a `*-light.svg` + `*-light.png` sibling generated by the audited `DARK`→`LIGHT` token map (`console_kit.write_pair` / per-screen equivalents). Verified by T1.
- [x] **Task 2 — v2 8-Crest logo on every screen, both themes (AC2).** `mark_8crest()` + `logotype()` in the live generators; `apply-official-8crest.py` back-fills the early screens (00–07). No placeholder glyph remains. Verified by T2.
- [x] **Task 3 — Token-role mirror, not a redesign (AC3–AC7).** Light is the dark shell with token roles luminance-inverted: accent invariant (T3), canvas flipped (T4), structural element counts identical per pair (T5), role inversion (T6), reserved status hues theme-invariant (T7).
- [x] **Task 4 — Lock the contract with a runnable falsification gate.** `theme-light-parity-check.py` — baseline green, 7 mutations RED. This is the regression gate for any future re-render of the mock set (run it after `write_pair` / `apply-official-8crest.py`).

## Out of scope (v1 boundary)

- Runtime theme persistence (localStorage / cookie), `prefers-color-scheme` auto-detection, and animated
  cross-fade on toggle — these are **polish**, deferred past v1 (§0). The v1 deliverable is: the audited token
  swap exists, every screen has a mirrored light sibling, and the contract is falsifiably locked.
- The actual React/Next.js console implementation of the toggle switch — this story owns the **mock-set
  theming contract** the implementation must satisfy; the front-end toggle wiring rides the same `DARK`/`LIGHT`
  token maps when the console is built.
