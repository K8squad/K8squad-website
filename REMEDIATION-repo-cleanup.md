# Remediation: purge BMAD / Paperclip artifacts from the K8squad GitHub repo

**Owner:** CTO (delegated by BigBoss/CEO)
**Trigger:** Board constraint from Henrik (2026-08-10): the GitHub repo `K8squad/K8squad`
must contain **only actual project source code** — no `bmad/` / `docs/bmad/` artifacts,
no Paperclip issue identifiers (`ISI-xxxx`) in files or commit messages.

## Current state (verified 2026-08-10)

- Repo: `/mnt/nas/project/k8squad` → remote `https://github.com/K8squad/K8squad.git`.
- Branches present: `master`, `bmad/architecture-isi2119` (branch name itself references an issue).
- **Nothing is pushed** — no upstream on any branch, `git ls-remote --heads origin` is empty.
  So there is currently **zero exposure on GitHub**; contamination is entirely local.
- **The entire history is BMAD content.** `git ls-tree -r master` shows only `docs/bmad/**`.
  There is no real source code committed yet.
- **Every commit message** on both branches references `ISI-xxxx` (e.g. `docs(bmad): ... (ISI-2115)`).
- `.gitignore` already excludes `bmad/`, `.bmad/`, `**/bmad/`, `docs/bmad/`, `.paperclip/`,
  `paperclip/` — but the BMAD files are **already tracked**, so `.gitignore` does not untrack them.

## Artifacts preserved

All 21 BMAD artifacts (kickoff brief, brainstorming, PRD, architecture, architecture review,
observability plan, epics, UX README + images, branding) have been copied to the Paperclip
workspace at `/mnt/nas/project/ksquad/docs/bmad/`. These are the authoritative deliverables
going forward and must **not** re-enter the git repo.

## Required remediation (CTO)

Because the repo's *entire* history is BMAD docs and nothing is pushed, the clean fix is a
**fresh repo history**, not a single removal commit (a removal commit would leave every
BMAD file + ISI reference in history, which still reaches GitHub on first push).

1. Confirm artifacts are safe in `/mnt/nas/project/ksquad/docs/bmad/` (done — 21 files).
2. Re-initialize repo history to a pristine state:
   - New root commit containing only genuine repo content: `README.md`, `LICENSE`,
     `.gitignore` (keep the existing ignore rules), and any real source scaffolding
     (Go backend, Node.js frontend, CRD definitions, infra manifests) as it gets created.
   - Commit messages must contain **no** `ISI-xxxx` references.
   - Do not carry over the `docs/bmad/**` tree.
3. Rename/replace the `bmad/architecture-isi2119` branch — the branch name references an issue.
   Use a neutral default branch (`main`).
4. Verify before any push:
   - `git ls-files | grep -iE 'bmad|paperclip'` → empty
   - `git log --all --oneline | grep -iE 'ISI-[0-9]'` → empty
   - `git ls-tree -r --name-only <default-branch> | grep -i bmad` → empty
5. Only then configure the remote default branch and push.

## Guardrail

Until this is done, **do not push any branch** to `github.com/K8squad/K8squad`. Pushing now
would publish the full BMAD history and violate the board constraint.
