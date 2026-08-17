# Story 11.4: CI check results + published artifacts → build browser (per-PR / per-Run)

Status: ready-for-dev (spec) — build gated on Epic-11 build wave (Wave-1 substrate)

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **The CI-mirror story — it fills `scm_check_run` (check conclusions per PR/ref) and
> `scm_artifact_ref` (published-artifact references) on the 11.1 loop, surfaces check results
> per-PR and per-Run, and links published CI artifacts into the build browser (8.7e) as
> references.** It rides 11.3's PR correlation (`head_sha → run.commit_sha`) to attribute checks
> to a Run, through the frozen `SourceControlProvider.Checks`/`.Artifacts` seam (11.5). The mirror
> is **UNTRUSTED-EXTERNAL, provenanced** — check conclusions + artifact refs written **only** by the
> inbound reconciler. **`scm_artifact_ref` is a REFERENCE, never bytes** — the reconciler stores a
> stable id + fetch descriptor (URL/digest/size), and the build browser resolves it **on demand**
> through the same per-principal RO reader discipline as 8.7f; **CI artifact bytes never stream
> through coord and are never trusted as build input to a Run.** A check result treated as a
> **trusted gate** on coord (auto-acting on a green check), an artifact **mirrored as bytes into
> coord** or **executed/trusted** by a Run, a **missing `external_origin`**, or a check attributed to
> a Run by anything **other than the 11.3 sha correlation** is a **regression**. Read AC1, AC3, AC4
> literally. Deps: **11.3 (PR + sha correlation) + 8.7e (build browser) + 11.5 seam + 11.1 loop.**

## Story

As **an operator**,
I want **CI check results per PR and per Run**, with **published build/CI artifacts linked into the
build browser (8.7e) as on-demand references**,
so that **I see whether an agent's build passed CI and can open its published artifacts without
leaving the console — with CI state and artifacts staying untrusted-external references, never a
trusted coord gate and never bytes streamed through or executed by a Run.**

## Context & prerequisites (read first)

- **PRD / epic:** `docs/bmad/04-epics-and-stories.md` Epic 11 row **11.4** — *CI check results per PR
  and per Run, with build/CI artifacts linked into the build browser (8.7); when checks complete,
  results surface per PR and per Run, and published artifacts link into the Run's build browser.
  **Feeds dashboard PR/CI tiles (8.8).***
- **The loop + PR correlation + seam this rides:** `docs/bmad/stories/11-1-repo-sync-reconciler.md`
  (loop; `scm_check_run` + `scm_artifact_ref` are pinned tables filled here),
  `docs/bmad/stories/11-3-pr-status-run-branch.md` (the `head_sha → run.commit_sha` correlation that
  attributes a check to a Run), and **11.5** (`SourceControlProvider.Checks` + `.Artifacts`).
- **Build browser (the surface):** `docs/bmad/stories/8-7e-console-three-pane-build-browser.md`
  (read-only tree→diff→code; pure consumer) + `docs/bmad/stories/8-7g-prci-header-strip.md`
  (*"published CI artifacts link into the browser (Epic 11.4)"* — 11.4 is the data source of 8.7g's
  artifact links) + `docs/bmad/stories/8-7f-on-demand-ro-reader-pod-full-tree-reads.md` (the
  **on-demand, per-principal, revoked-at-teardown RO reader** discipline artifact resolution reuses).
- **Architecture:** `docs/bmad/03-architecture.md` **§5.4** (reconciler & mirror — read whole),
  **§7.3.2** (untrusted-external provenance), **§6** (fenced claim / no-P2P — CI is never a coord
  gate; custody never crosses the seam), **§9.4** (worktree/`commit_sha` correlation basis).
  **ADR-001** (`scm` schema), **ADR-018** (field-ownership + echo-suppression).
- **Mirror schema (11.1 pinned the tables; 11.4 fills them):**
  - `scm_check_run` — external-owned **`external_id`, `pr_external_id`/`ref`, `head_sha`, `name`,
    `status ∈ {queued, in_progress, completed}`, `conclusion ∈ {success, failure, neutral, cancelled,
    timed_out, action_required, skipped}`, `details_url`, `actor`, `external_origin`, `synced_at`**;
    upsert key `(project_id, provider, external_id)`, idempotent.
  - `scm_artifact_ref` — external-owned **`external_id`, `check_external_id`/`pr_external_id`,
    `head_sha`, `name`, `fetch{url, digest, size_bytes, expires_at}`, `external_origin`, `synced_at`**.
    **A reference only — no bytes stored, no bytes in coord.**
- **Per-PR / per-Run attribution:** checks correlate to a PR by `pr_external_id`, and to a Run by
  **11.3's `head_sha = run.commit_sha`** read-side JOIN — the **same** correlation, extended to
  checks. A check with no matching Run renders per-PR-only; the correlation **never mutates the Run**.
- **Artifact resolution (the bytes crux):** `scm_artifact_ref` is a **pointer**. When an operator
  opens an artifact from the build browser, resolution goes through the **on-demand, per-principal RO
  path** (8.7f discipline) using the **BYO mirror-read token** (Epic 7, never shared/logged) — bytes
  are fetched to the console/reader on demand, **never** mirrored into coord, **never** injected into
  or executed by an agent Run (an untrusted external artifact is not build input).
- **Trust (D8, §7.3.2):** check conclusions + artifact refs are **untrusted-external** with
  `external_origin`; a green/red check is **displayed, never an automatic coord action** — the
  CI-failure **auto-post** to the Project room is **11.6** (an observer notification, still no coord
  gate).
- **Scope guard:** 11.4 is **checks + artifact references + build-browser linkage only.** The
  dashboard PR/CI **tiles** and the CI-failure **auto-post** are **11.6**. No coordination path; no
  CI-as-gate; no artifact bytes in coord. **Runtime Go deferred to the Epic-11 build wave.**

## Acceptance Criteria

**AC1 — check results reconcile through the seam into a provenanced mirror, per PR and per Run (the mirror crux).**
Given a linked PR/branch with CI, When checks complete (webhook `check_run`/`check_suite` / poll),
Then the reconciler **idempotent-upserts** `scm_check_run` via **`SourceControlProvider.Checks`**
(11.5) with normalized `status`/`conclusion`, keyed `(project_id, provider, external_id)`; the row is
**untrusted-external** with **`external_origin`**; and it is attributable **per PR** (`pr_external_id`)
and **per Run** (via 11.3's `head_sha = run.commit_sha` JOIN). A redelivered webhook is a **no-op**. A
row **missing `external_origin`**, a **non-idempotent** upsert, or a **direct GitHub call** outside
the seam is a **regression**.

**AC2 — published artifacts are REFERENCES linked into the build browser, resolved on demand (the artifact-reference crux).**
Given completed CI with published artifacts, When the reconciler records them, Then each
`scm_artifact_ref` stores a **stable id + fetch descriptor** (url/digest/size/expiry) — **no bytes** —
and the **8.7e build browser** links them onto the producing Run (via the sha correlation), resolving
bytes **on demand** through the **per-principal RO path** (8.7f) using the **BYO mirror-read token**.
An artifact **mirrored as bytes**, bytes **stored in coord**, or resolution using a **shared/logged
token** is a **regression**.

**AC3 — CI is displayed, never a trusted coord gate; artifacts are never Run build input (the trust crux, §6).**
Given a check conclusion or a published artifact, When it lands, Then it is **untrusted-external,
displayed** — a green check triggers **no automatic coord action** (no claim/merge/state transition),
and an artifact is **never injected into or executed by an agent Run** as build input. CI conclusions
inform humans + downstream **observers** (11.6 auto-post); they **never** gate the fenced coordination
record (§6). A check that **auto-acts on coord**, or an artifact **trusted/executed by a Run**, is a
**regression**.

**AC4 — check-to-Run attribution reuses the 11.3 sha correlation and never mutates the Run (the correlation crux).**
Given a check with a `head_sha`, When it is attributed to a Run, Then it uses **11.3's read-side
`scm_check_run.head_sha = run.commit_sha` JOIN** — the **same** correlation as PRs — and **never
writes CI state onto the Run** as authoritative. A check with no matching Run renders **per-PR only**.
Attributing by anything **other than the sha correlation**, or an attribution that **mutates the
Run**, is a **regression**.

## Tasks / Subtasks

- [ ] **(Epic 11 build)** `scm_check_run` + `scm_artifact_ref` migrations (external-owned fields +
  `external_origin`; artifact = fetch descriptor, **no bytes column**); idempotent upserts keyed
  `(project_id, provider, external_id)`.
- [ ] **(Epic 11 build)** Inbound check/artifact reconcile off 11.1's loop via
  `SourceControlProvider.Checks`/`.Artifacts` (11.5), subscribing `check_run`/`check_suite` + poll.
- [ ] **(Epic 11 build)** Per-PR + per-Run attribution via 11.3's `head_sha = run.commit_sha` JOIN
  (extended to checks); expose check results on Run detail (8.11) + per-PR.
- [ ] **(Epic 11 build)** Build-browser artifact linkage (8.7e/8.7g): render `scm_artifact_ref` links
  on the producing Run; resolve bytes on demand through the per-principal RO path (8.7f) + BYO token.
- [ ] **Pin the construction-time contract** as a runnable falsification check
  (`docs/bmad/spikes/bench/scm-checks-artifacts-check.py`) in 11.1's model-check style: model the
  check/artifact upsert, the reference-not-bytes invariant, the CI-not-a-gate invariant, and the
  sha-correlation attribution.
- [ ] **Four checks C1–C4 ↔ AC1–AC4**, GREEN on the §5.4/§7.3.2/§6-conformant baseline.
- [ ] **Mutation battery** (≥10), each flipping its designated check RED, no vacuous survivors:
  drop-provenance / non-idempotent → C1 RED; artifact-stores-bytes / bytes-in-coord / shared-token →
  C2 RED; check-auto-acts-on-coord / artifact-executed-by-Run → C3 RED; attribute-by-non-sha /
  attribution-mutates-Run → C4 RED.
- [ ] `python3 scm-checks-artifacts-check.py` → **exit 0** (baseline GREEN; all mutations CAUGHT).

## Dev Notes

- **Reference-not-bytes is the load-bearing artifact discipline.** A build-artifact mirror that pulls
  bytes into Postgres/coord bloats the datastore and — worse — turns an untrusted external blob into
  something adjacent to trusted state. `scm_artifact_ref` is a pointer; the build browser resolves it
  on demand exactly like 8.7f resolves workspace blobs (per-principal RO, revoked at teardown, BYO
  token). This keeps coord small and the trust boundary intact.
- **CI is never a gate — this is the §6 no-P2P line applied to CI.** It is tempting to "auto-merge on
  green" or "auto-claim next on pass." That is a coordination action driven by untrusted-external
  state — exactly what §6 forbids. 11.4 **displays** CI; any action on it is a **human** decision or a
  downstream **observer** (11.6 auto-post is a notification, not a coord write). The check hunts a
  conclusion that fires a coord mutation.
- **One correlation, reused:** checks attribute to Runs by the **same** `head_sha = run.commit_sha`
  JOIN 11.3 established for PRs — no second correlation mechanism, no title/branch guesswork. This is
  why 11.4 depends on 11.3: the correlation must exist first.
- **Normalized conclusions (11.5 AC4):** `status`/`conclusion` are provider-neutral; the GitHub
  adapter maps GitHub Checks API onto them, a GitLab adapter maps pipeline/job status onto them —
  the build browser + 11.6 tiles read the normalized vocabulary, never raw GitHub.
- **8.7g is the strip, 11.4 is the data:** 8.7g renders `meta.ciStatus` + artifact links in the
  build-browser header and degrades to git-only without sync; 11.4 supplies `scm_check_run` +
  `scm_artifact_ref`. Neither blocks the other from shipping.

## Testing

- **Runnable check:** `python3 docs/bmad/spikes/bench/scm-checks-artifacts-check.py` → **exit 0** —
  baseline GREEN on C1–C4; mutation battery all CAUGHT, no vacuous survivors.
- **Deferred to Epic 11 build (integration):** the real `scm_check_run`/`scm_artifact_ref` upserts +
  the on-demand artifact resolution (per-principal RO, BYO token) + build-browser linkage, proven
  against live CI by the operator/apiserver integration suite (CI completes → check rows + artifact
  refs → surface per-PR + per-Run → open artifact resolves on demand; green check triggers no coord
  action).

## References

- [Source: docs/bmad/04-epics-and-stories.md] — Epic 11 row 11.4 (CI checks + artifacts → build
  browser; feeds 8.8 tiles).
- [Source: docs/bmad/stories/11-1-repo-sync-reconciler.md] — the loop; `scm_check_run` +
  `scm_artifact_ref` pinned tables.
- [Source: docs/bmad/stories/11-3-pr-status-run-branch.md] — the `head_sha=run.commit_sha` correlation
  reused for check-to-Run attribution.
- [Source: docs/bmad/stories/11-5-provider-seam-explicit.md] — `SourceControlProvider.Checks` +
  `.Artifacts` seam + normalized conclusions.
- [Source: docs/bmad/stories/8-7e-console-three-pane-build-browser.md] + 8-7g (PR/CI header strip,
  artifact links) + 8-7f-on-demand-ro-reader-pod-full-tree-reads (per-principal RO reader discipline
  reused for artifact resolution).
- [Source: docs/bmad/03-architecture.md#5.4] — reconciler & mirror; §7.3.2 (untrusted-external), §6
  (no-P2P / CI-not-a-gate), §9.4 (sha correlation). ADR-001, ADR-018.

## Dev Agent Record

_(empty — spec authored by the Story Writer; the build wave fills this in.)_
