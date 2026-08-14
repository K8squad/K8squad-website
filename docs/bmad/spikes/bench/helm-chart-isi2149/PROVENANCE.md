# Pinned chart snapshot — read-only fixture

This directory is a **verbatim, read-only snapshot** of the shipped KSquad Helm
chart, vendored into the BMAD workspace so the Epic-9 falsification benches have
**file-grounded teeth** without requiring a `helm` binary or a live checkout of
the `k8squad` source repo. It backs both the Story 9.1 bench
(`../gateway-httproute-check.py`) and the Story 9.4 bench
(`../nats-jetstream-check.py`).

- **Source repo:** `k8squad` (GitHub `K8squad/K8squad`)
- **Path:** `deploy/helm/ksquad/`
- **Commit:** `598f3f5` — `feat(helm): NATS/JetStream event bus + apiserver
  outbox relay (ISI-2253)`, on `feature/isi-2253-nats-jetstream` (PR #18),
  branched off `5e6442d` (`feature/helm-exposure-storage`, ISI-2149 + ISI-2286).
- **Story tickets:** ISI-2250 (9.1 Gateway+HTTPRoute), ISI-2253 (9.4 NATS/
  JetStream event bus). Chart impl: ISI-2149 (exposure+storage) + ISI-2253
  (event bus).

**What changed vs the prior 5e6442d snapshot:** added `templates/nats.yaml`
(parent-rendered JetStream StatefulSet), `templates/event-relay.yaml` (apiserver
outbox→NATS relay ConfigMap), the `nats:`/`events:` values blocks, the NATS
helpers + `ksquad.validate` guards, and the NATS README/NOTES/ci-test additions.
The prior snapshot also omitted `postgres-cluster.yaml` + `operator-config.yaml`
that already shipped at 5e6442d; this re-vendor captures the full chart.

**Do not edit these files by hand.** They are the authoritative render source the
benches read for their file-grounded pass. To refresh, re-vendor from the
k8squad branch and bump the commit above. The `k8squad` repo stays BMAD-free;
the artifact lives here.

The Epic-9 stories pin the *construction-time contract* these templates must
satisfy; the chart code lives and is CI-tested (`ci/test.sh`, needs `helm`) in
`k8squad`.
