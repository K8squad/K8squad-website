# Story 8.7g: [with Epic 11] PR/CI header strip in build browser

Status: in-review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **This is a flagged fast-follow of Epic 8.7** (deps `8.7e` + `Epic 11.4`). Epic 8.7 already **closed**
> at 8.7e (`6fe7287`) — the strictly read-only three-pane build browser. 8.7g adds exactly ONE thing on
> top of that composition: a **PR/CI header strip** that renders `meta.prUrl` / `meta.ciStatus` when
> **SCM sync (Epic 11.4, design §5.4)** has mirrored them into the Run's `meta`, and links the CI
> artifacts that SCM sync published into the browser. It adds **no new read path, no new backend, no new
> store, no new endpoint** — it is a **pure additive read** over the SAME 8.7d `meta` payload the
> three-pane browser already fetches. The load-bearing constraint is the one a "I opened a Run that had a
> PR and saw a link" demo does not prove: **the build browser does NOT hard-depend on Epic 11 — it
> degrades to git-only.**

## Story

As an **operator using the console build browser**,
I want **a PR/CI header strip that renders `meta.prUrl` / `meta.ciStatus` (and links published CI
artifacts) when SCM sync has mirrored a Run's PR/CI state — and is simply absent otherwise**,
so that **I can jump from a Run's changed files to its pull request and CI outcome without leaving the
browser, while the browser still works exactly as before for Runs whose PR/CI was never mirrored (Epic 11
not landed, or SCM sync hasn't run) — never blocked on, and never broken by, a missing PR.**

## Context & prerequisites (read first)

- **Design contract:** `docs/bmad/design/build-browser-component-design.md` — §6 (console surface, the
  **PR/CI linkage** bullet: `meta.prUrl`/`meta.ciStatus` render as a header strip when SCM sync has
  mirrored them, **absent otherwise; build browser does not depend on Epic 11 to ship — degrades to
  git-only**), §5.4 (SCM sync — the mirror that populates `prUrl`/`ciStatus`/published artifacts), §3
  (the `meta` endpoint whose response already carries `prUrl?`/`ciStatus?`/`artifacts`), §5 (the
  per-principal gate the strip inherits by reading through `meta`), §1 (scope guard **R6** — read-only,
  not an IDE), §9 (story slicing — this is the flagged **8.7g** fast-follow).
- **Mock:** `docs/bmad/ux/images/06-build-browser-{light,dark}.svg|png` — FR-F7 (light + dark parity);
  the header strip sits above the three panes.
- **Architecture:** `03-architecture.md` §13 (Next.js BFF → Go apiserver, **one authorization choke
  point** — the console never touches kube/Postgres/git/**GitHub** directly), §5/NFR-SEC5 (per-principal
  scoping), R6 (read-only console).
- **Depends on (must be landable/mergeable before this story is done):**
  - **8.7e** (`6fe7287`) — the three-pane composition this strip sits atop; unchanged by this story.
  - **8.7d** (`99f0f05`) — the `meta` endpoint + the per-principal `404` gate the strip **inherits** by
    reading `prUrl`/`ciStatus` from the gated `meta` payload (no new read).
  - **Epic 11.4 (SCM sync)** — the mirror that **populates** `meta.prUrl`/`meta.ciStatus` and publishes
    CI artifacts into `meta.artifacts`. **This story does not implement 11.4** — it *renders* what 11.4
    mirrors. Until 11.4 lands, every Run is git-only and the strip is (correctly) absent; the
    composition invariants **do not depend on 11.4 being present** (the `run-git-only` fixture is exactly
    the pre-Epic-11 world, and it must render an unchanged browser).
- **Blocks:** nothing (flagged fast-follow; Epic 8.7 already closed at 8.7e).

## Acceptance Criteria

**AC1 — strip when mirrored (§5.4/§6).**
Given a Run whose `meta` carries `prUrl` and/or `ciStatus` (SCM sync has mirrored them), When I open the
build browser, Then a **header strip renders above the three panes** whose **PR link is exactly
`meta.prUrl`** and **CI badge is exactly `meta.ciStatus`** — the mirrored values, never a live-fetched or
invented one.

**AC2 — degrade to git-only (THE crux).**
Given a Run with **no** mirrored `prUrl`/`ciStatus` (Epic 11 not landed, or SCM sync hasn't run for this
Run), When I open the build browser, Then I see the **unchanged three-pane browser** with **no strip**
and **no error / no perpetual "loading PR…" state** — the build browser **does not hard-depend on Epic
11**; the strip's absence **is** the normal git-only view, not a degraded one.

**AC3 — additive, read-only, over `meta` only (§13/R6).**
Given the strip, When it fetches its data, Then it reads `prUrl`/`ciStatus`/CI-artifact links **only from
the gated 8.7d `meta` payload** — **never** a direct GitHub / CI-provider call and **never** a second
ungated channel — and it exposes **no** mutating affordance (no merge-PR / re-run-CI / approve / close)
and issues **only** `GET`. The PR link is an **external link** to the SCM; the CI badge is a read-only
status.

**AC4 — faithful badge, never fabricated.**
Given a **partial** mirror (`prUrl` present, `ciStatus` absent — PR opened, CI not reported yet), When
the strip renders, Then it shows the **PR link** and shows **no CI status** — it **never invents** a
status, and in particular never defaults an unknown CI outcome to "success"/"passing". `ciStatus` is
always the mirrored value verbatim.

**AC5 — published CI artifacts link in, not rebuilt.**
Given a Run whose CI artifacts SCM sync **published** into `meta.artifacts`, When the strip renders, Then
those artifacts **link into the browser from the mirror** — the browser **never re-fetches** them from
the CI provider or rebuilds them, and **never silently drops** the links.

**AC6 — the strip inherits the per-principal gate (§5/NFR-SEC5).**
Given a **per-principal deny** (gate `404`) or a **genuinely-missing** Run, When the browser renders,
Then it shows the neutral **"no build view"** with **no strip** and **leaks no `prUrl`** — because the
strip rides the **same gated `meta` read**, it can **never** be a side-channel that reveals a Run (or its
PR) the caller may not even learn exists (existence-hiding, inherited from 8.7d).

**AC7 — light + dark parity (FR-F7).**
Given the strip, When it renders in **light** and in **dark** (mock 06 both themes), Then it is
**present/absent identically** and its **control set is the same** — and the CI badge hue is
**theme-invariant** (like the status dots, ISI-2279).

## Runnable falsification check (ships with this story)

`docs/bmad/spikes/bench/build-browser-prci-strip-check.py` — a self-contained, no-cluster/no-browser
differential check over the **PR/CI strip composition**. It (i) proves the naive *"call GitHub directly,
slap a merge button on, and hard-fail when there's no PR"* anti-pattern is **DETECTED** violating
**every** invariant G1–G7 (real teeth), then (ii) proves the §5.4/§6/R6/FR-F7 conformant strip violates
nothing — driving **real renders** (PR+CI mirrored / git-only-no-mirror / PR-without-status partial /
CI-artifacts-published / per-principal-deny / missing Run; light + dark) through an executable `render()`
with a spy that records the **transport + verb** of every backend fetch (`meta` = the gated 8.7d payload;
`scm-api` = a forbidden direct call to GitHub/the CI provider).

Invariants **G1–G7 == AC1–AC7**. Mutation harness (each injects exactly one defect; mapped invariant
goes RED):

| mutation | → | mutation | → |
|---|---|---|---|
| `STRIP_SUPPRESSED` | **G1** | `ARTIFACTS_REBUILT`, `ARTIFACTS_DROPPED` | **G5** |
| `STRIP_HARD_DEP` | **G2** | `STRIP_LEAKS_DENY` | **G6** |
| `SCM_DIRECT`, `STRIP_MUTATES` | **G3** | `THEME_ASYMMETRY` | **G7** |
| `FABRICATE_STATUS` | **G4** | | |

**Verified:** baseline `python3 build-browser-prci-strip-check.py` exits `0`; the naive anti-pattern
trips **12 violations across all 7 invariants**; each of the **9 mutations** exits `1` with its mapped
tooth RED, **0 survivors**. The React/Next.js strip is still greenfield in the source repo — this bench
is the **executable spec** it must match (the 8.7a–e pattern). The `run-git-only` fixture **is** the
pre-Epic-11 world: it must render an unchanged three-pane browser, proving the no-hard-dependency
guarantee without Epic 11 present.

## Tasks / Subtasks

- [ ] **Task 1 — Strip when mirrored (AC1).** When `meta.prUrl`/`meta.ciStatus` are present, render a
  header strip above the three panes; PR link = `meta.prUrl`, CI badge = `meta.ciStatus`, verbatim.
- [ ] **Task 2 — Degrade to git-only (AC2).** When `meta` carries no `prUrl`/`ciStatus`, render the
  unchanged three-pane browser with **no strip** and **no error / no loading state**. Assert (a component
  test with a no-mirror `meta`) that the browser renders fully and the strip is structurally absent —
  the build browser must not hard-depend on Epic 11.
- [ ] **Task 3 — Additive read-only over `meta` only (AC3).** Source `prUrl`/`ciStatus`/CI-artifact links
  from the already-fetched gated `meta`; **no** GitHub/CI-provider call, **no** second channel. No
  merge/re-run/approve control; issue only `GET`. The PR link is an external `<a href>` to the SCM.
- [ ] **Task 4 — Faithful badge (AC4).** Render `ciStatus` verbatim; when it is absent show the PR link
  with **no** status — never default to "success"/"passing".
- [ ] **Task 5 — Link published CI artifacts (AC5).** Link `meta.artifacts` entries of kind
  `ci-published` into the browser; never re-fetch/rebuild them, never drop them.
- [ ] **Task 6 — Inherit the gate (AC6).** The strip renders only after a `meta` `200`; a `404`
  (deny/missing) shows "no build view" with no strip and no `prUrl`. Assert a deny/missing render leaks
  no PR URL.
- [ ] **Task 7 — Light + dark parity (AC7).** Strip present/absent identically in both themes; identical
  control set; CI badge hue theme-invariant (mock 06). 
- [ ] **Task 8 — Keep the runnable check green.** Wire the bench into CI alongside the 8.7a–e checks;
  baseline exits 0, every mutation exits 1 with its mapped tooth RED.

## Dev Notes

- **The strip is additive — it does not touch the three-pane composition.** 8.7e (`6fe7287`) owns the
  tree→diff→code panes and is unchanged by this story. 8.7g only adds a header strip that reads two extra
  fields (`prUrl`, `ciStatus`) and a filtered slice of `meta.artifacts` (`ci-published`) that the 8.7d
  `meta` endpoint **already returns** (design §3). If you find yourself editing a pane, a store, or the
  `meta` endpoint, stop — that is another slice's job.
- **The crux is "no hard dependency on Epic 11" (AC2/G2).** SCM sync (Epic 11.4) is what mirrors PR/CI
  into `meta`; until it lands, **every Run is git-only** and the strip must simply not be there. The
  common failure is to treat a missing PR as an error state (a red banner, a spinner that never
  resolves, or a hard-fail that blanks the browser). The `run-git-only` fixture in the bench is exactly
  the pre-Epic-11 world and it **must render an unchanged three-pane browser** — that is how this story
  ships and merges **before** Epic 11 does.
- **Read through `meta`, never call GitHub (AC3/G3, §13).** The whole point of the one-choke-point BFF is
  that the console never grows a direct dependency on an external service, and never opens a channel that
  bypasses the per-principal gate. Reading `prUrl`/`ciStatus` from the gated `meta` payload gets the
  gate, the existence-hiding, and the "no new dependency" for free. A direct GitHub/CI call would be
  both a new external coupling **and** an ungated side-channel that leaks a Run's PR to a principal who
  was `404`'d on the Run itself (the `STRIP_LEAKS_DENY`/`SCM_DIRECT` teeth).
- **Team-legibility of *outcomes* lives here, deliberately (design §5).** The raw-content panes are
  strictly per-principal (a same-Team peer is `404`'d). PR/CI state is a Team-legible *outcome* — but it
  is surfaced **only** through the gated `meta` for a Run the caller can already see; the strip never
  makes PR/CI legible for a Run the caller was denied. The gate is inherited, not reopened.
- **R6 still holds — this is legibility, not an SCM control panel.** The strip links out to the PR and
  shows the CI badge; it does **not** merge, re-run, approve, or close. Mutating SCM actions are a
  different surface with their own RBAC — never this read-only browser.
- **Badge hue is theme-invariant (AC7, ISI-2279).** Like the status dots in the 8.9 theming contract, the
  CI badge's semantic color (success/failure/pending) does not swap between light and dark — only the
  chrome around it does. Present/absent and the control set must match across themes (mock 06).
