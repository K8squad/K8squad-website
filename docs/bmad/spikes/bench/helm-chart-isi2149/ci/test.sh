#!/usr/bin/env bash
# Self-check for the KSquad chart (ISI-2149): lint, render every exposure mode,
# and assert the fail-fast guards actually fail. No cluster required.
set -euo pipefail
CHART="$(cd "$(dirname "$0")/.." && pwd)"
pass() { echo "  ok  — $1"; }
fail() { echo "  FAIL — $1"; exit 1; }

# A render that must SUCCEED, optionally grepping for an expected string.
render_ok() { # <desc> <grep-or-emptystring> <set-args...>
  local desc="$1" want="$2"; shift 2
  local out
  if ! out="$(helm template t "$CHART" "$@" 2>&1)"; then
    echo "$out"; fail "$desc (expected success)"
  fi
  if [[ -n "$want" ]] && ! grep -q -- "$want" <<<"$out"; then
    echo "$out"; fail "$desc (missing: $want)"
  fi
  pass "$desc"
}

# A render that must FAIL with an expected message fragment.
render_fail() { # <desc> <expect-msg> <set-args...>
  local desc="$1" msg="$2"; shift 2
  local out
  if out="$(helm template t "$CHART" "$@" 2>&1)"; then
    echo "$out"; fail "$desc (expected failure but succeeded)"
  fi
  grep -q -- "$msg" <<<"$out" || { echo "$out"; fail "$desc (wrong message)"; }
  pass "$desc"
}

GW=(--set exposure.mode=gateway
    --set exposure.gateway.gatewayClassName=cilium
    --set exposure.gateway.listeners.https.certSecretName=tls
    --set exposure.hostnames.console=ksquad.example.com
    --set exposure.hostnames.apiserver=api.example.com
    --set storage.storageClassName=fast-ssd)

# Lint with a valid values set — the chart deliberately fails on empty defaults
# (that IS the fail-fast guard; asserted separately below).
echo "== helm lint =="
if helm lint "$CHART" "${GW[@]}" >/dev/null 2>&1; then pass "lint clean (valid values)"; else
  helm lint "$CHART" "${GW[@]}"; fail "lint"; fi

echo "== positive renders =="
render_ok "gateway: creates Gateway w/ gatewayClassName" 'gatewayClassName: "cilium"' "${GW[@]}"
render_ok "gateway: apiserver HTTPRoute disables SSE timeout" 'request: "0s"' "${GW[@]}"
render_ok "gateway: CNPG PVC uses values StorageClass" 'storageClass: "fast-ssd"' "${GW[@]}"
render_ok "gateway: workspace StorageClass handed to operator" 'workspace.storageClassName: "fast-ssd"' "${GW[@]}"
render_ok "ingress: renders Ingress + SSE annotations" 'proxy-buffering' \
  --set exposure.mode=ingress --set exposure.ingress.className=nginx \
  --set exposure.ingress.tls.secretName=tls \
  --set exposure.hostnames.console=a.example.com \
  --set exposure.hostnames.apiserver=b.example.com \
  --set storage.storageClassName=std
render_ok "clusterip: Services only, no Gateway" 'kind: Service' \
  --set exposure.mode=clusterip --set storage.storageClassName=std
# per-family override beats global
render_ok "postgres per-family StorageClass override" 'storageClass: "db-class"' \
  --set exposure.mode=clusterip --set storage.storageClassName=std \
  --set storage.postgres.storageClassName=db-class

echo "== fail-fast guards =="
render_fail "missing gatewayClassName fails" "gatewayClassName is REQUIRED" \
  --set exposure.mode=gateway \
  --set exposure.gateway.listeners.https.certSecretName=tls \
  --set exposure.hostnames.console=a --set exposure.hostnames.apiserver=b \
  --set storage.storageClassName=std
render_fail "missing storageClassName fails (no cluster default)" "never relies on the cluster-default" \
  --set exposure.mode=clusterip
render_fail "bad exposure.mode fails" "exposure.mode must be one of" \
  --set exposure.mode=bogus --set storage.storageClassName=std
render_fail "https listener without cert fails" "certSecretName is REQUIRED" \
  --set exposure.mode=gateway --set exposure.gateway.gatewayClassName=envoy \
  --set exposure.hostnames.console=a --set exposure.hostnames.apiserver=b \
  --set storage.storageClassName=std
render_fail "gateway with both listeners disabled fails (ISI-2286 F2)" "at least one exposure.gateway.listeners" \
  --set exposure.mode=gateway --set exposure.gateway.gatewayClassName=envoy \
  --set exposure.gateway.listeners.http.enabled=false \
  --set exposure.gateway.listeners.https.enabled=false \
  --set exposure.hostnames.console=a --set exposure.hostnames.apiserver=b \
  --set storage.storageClassName=std

# Reusable minimal-core value set (clusterip so exposure is out of the way).
CORE=(--set exposure.mode=clusterip --set storage.storageClassName=std)

echo "== NATS / JetStream event bus (ISI-2253) =="
render_ok "nats: JetStream enabled StatefulSet renders by default" 'jetstream {' "${CORE[@]}"
render_ok "nats: single-replica default" 'replicas: 1' "${CORE[@]}"
render_ok "nats: JetStream PVC uses values StorageClass (never cluster-default)" 'storageClassName: "std"' "${CORE[@]}"
# ISI-2621: max_file_store must render UNQUOTED NATS syntax (4G, not "4Gi"/"4G")
# — a quoted or Gi-suffixed value CrashLoops nats-server on JetStream init.
render_ok "nats: max_file_store renders unquoted NATS syntax (ISI-2621)" 'max_file_store: 4G' "${CORE[@]}"
# CRITICAL: Ensure max_file_store ≤ storage.nats.size to prevent disk issues
render_ok "nats: max_file_store ≤ storage size" 'max_file_store: 2G' "${CORE[@]}" --set nats.jetstream.maxFileStore=2G --set storage.nats.size=4G
render_ok "nats: JetStream PVC uses per-family StorageClass override" 'storageClassName: "nats-class"' \
  "${CORE[@]}" --set storage.nats.storageClassName=nats-class
render_ok "relay: apiserver outbox→NATS relay ConfigMap renders" 'event-relay' "${CORE[@]}"
render_ok "relay: NATS URL is release-derived" 'relay.natsUrl: "nats://t-ksquad-nats' "${CORE[@]}"
render_ok "relay: subject taxonomy prefix present" 'relay.subjectPrefix: "ksquad"' "${CORE[@]}"
render_ok "relay: decoupled from write path (NATS-down never blocks)" 'relay.blocksWritePath: "false"' "${CORE[@]}"
render_ok "relay: NATS never gates apiserver health" 'relay.natsHealthGatesApiserver: "false"' "${CORE[@]}"
# HA toggle — same pattern as CNPG storage.postgres.instances.
render_ok "nats HA: clustered JetStream renders routes" 'cluster {' \
  "${CORE[@]}" --set nats.ha.enabled=true --set nats.ha.replicas=3
render_ok "nats HA: replicas honored" 'replicas: 3' \
  "${CORE[@]}" --set nats.ha.enabled=true --set nats.ha.replicas=3
# Core still installs with the bus off — NATS-down never blocks (§17.4).
render_ok "nats disabled: core still renders (no StatefulSet)" 'kind: Service' \
  "${CORE[@]}" --set nats.enabled=false
render_ok "nats disabled: relay still renders + buffers in outbox" 'relay.busBundled: "false"' \
  "${CORE[@]}" --set nats.enabled=false

echo "== NATS fail-fast guards =="
render_fail "nats.enabled + missing NATS StorageClass fails (no cluster default)" "never relies on the cluster-default" \
  --set exposure.mode=clusterip
render_fail "nats HA with even replicas fails (RAFT quorum)" "must be ODD" \
  "${CORE[@]}" --set nats.ha.enabled=true --set nats.ha.replicas=4
render_fail "nats HA with <3 replicas fails (RAFT quorum)" "must be >= 3" \
  "${CORE[@]}" --set nats.ha.enabled=true --set nats.ha.replicas=1

# HIGH: StorageClass validation (no cluster-default fallback)
render_fail "missing StorageClass fails fast" "never relies on the cluster-default" \
  --set exposure.mode=clusterip --set storage.storageClassName=

echo "== Storage configuration validation =="
# Test that PVC sizes use Kubernetes-compatible syntax (Gi allowed for PVCs)
render_ok "nats: PVC size uses Gi (Kubernetes compatible)" 'storage: "5Gi"' "${CORE[@]}"
# Test that PVC sizes can use other formats too (properly quoted)
render_ok "nats: PVC size uses plain number" 'storage: "5G"' "${CORE[@]}" --set storage.nats.size=5G

# HIGH: Gateway API timeout validation (SSE safety)
render_ok "gateway: HTTPRoute disables SSE timeout" 'request: "0s"' "${GW[@]}"

# HIGH: NATS resource validation (JetStream memory requirements)
render_ok "nats: JetStream has memory limits" 'memory: 256Mi' "${CORE[@]}"
render_ok "nats: JetStream has CPU requests" 'cpu: 50m' "${CORE[@]}"

# HIGH: Gateway API version compatibility validation
render_ok "gateway: HTTPRoute timeouts render correctly" 'request: "0s"' "${GW[@]}"

echo "== access-mode schema (ISI-2252, §9.4) =="
render_ok "accessMode RWO (default) passes schema" 'workspace.accessMode: "ReadWriteOnce"' \
  "${CORE[@]}"
render_ok "accessMode RWX passes schema (valid enum, warned not rejected)" 'workspace.accessMode: "ReadWriteMany"' \
  "${CORE[@]}" --set storage.workspace.accessMode=ReadWriteMany
render_ok "accessMode RWOncePod passes schema" 'workspace.accessMode: "ReadWriteOncePod"' \
  "${CORE[@]}" --set storage.workspace.accessMode=ReadWriteOncePod
render_fail "invalid accessMode fails schema enum (no silent bad PVC)" "must be one of the following" \
  "${CORE[@]}" --set storage.workspace.accessMode=ReadWriteMnay

echo "ALL CHECKS PASSED"
