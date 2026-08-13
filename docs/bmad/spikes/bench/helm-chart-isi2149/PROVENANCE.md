# Pinned chart snapshot — read-only fixture

This directory is a **verbatim, read-only snapshot** of the shipped KSquad Helm
chart, vendored into the BMAD workspace so the Story 9.1 falsification bench has
**file-grounded teeth** without requiring a `helm` binary or a live checkout of
the `k8squad` source repo.

- **Source repo:** `k8squad` (GitHub `K8squad/K8squad`)
- **Path:** `deploy/helm/ksquad/`
- **Commit:** `5e6442d417244f9e9ddbec0f1805e68fcaa15a07`
  (`fix(helm): honest SSE-timeout conformance docs + guard empty Gateway (ISI-2286)`)
- **Branch:** `feature/helm-exposure-storage`
- **Chart implementation ticket:** ISI-2149 (feat: parameterized Gateway API
  exposure + explicit StorageClass), hardened by ISI-2286.

**Do not edit these files by hand.** They are the authoritative render source the
bench (`../gateway-httproute-check.py`) reads for its file-grounded pass. To
refresh, re-vendor from the k8squad branch and bump the commit above. The
`k8squad` repo stays BMAD-free; the artifact lives here.

Story 9.1 (ISI-2250) pins the *construction-time contract* these templates must
satisfy; the chart code lives and is CI-tested (`ci/test.sh`, needs `helm`) in
`k8squad`.
