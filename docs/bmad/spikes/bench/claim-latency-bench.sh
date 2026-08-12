#!/usr/bin/env bash
# ISI-2113 — warm-pool sandbox claim-latency field harness.
#
# Measures, per RuntimeClass, the three numbers arch §9/§21 and obs §5.3 gate on:
#   1. cold_start_s   : pod create -> Ready           (pool_hit=cold latency)
#   2. warm_claim_s   : time to grab a Ready pod + exec first cmd (~pool_hit=warm)
#   3. replenish_s    : delete one Ready pod -> a fresh one Ready (teardown-and-
#                       replace §9.3) -> feeds pool_sizing.py as R
#
# It is deliberately dependency-light: kubectl + bash + date. It prepulls the
# image first (warm-pool assumes node image-prepull, §9.2) so it measures the
# runtime's sandbox-creation cost, NOT image pull. RuntimeClasses that are absent
# on the cluster are SKIPPED with a notice (no silent truncation — ponytail).
#
# Usage:
#   ./claim-latency-bench.sh                 # bench all present of: runc gvisor kata
#   ./claim-latency-bench.sh gvisor kata     # bench a subset
#   ./claim-latency-bench.sh --validate      # no-cluster: check kubectl + tools only
#   ITERS=10 IMAGE=busybox:1.36 NS=isi2113 ./claim-latency-bench.sh
#
# Output: a table of p50/p95 per runtime, plus a `pool_sizing.py` invocation line
# with the measured replenish_s so the sizing follows straight from the evidence.
set -euo pipefail

NS="${NS:-isi2113-bench}"
IMAGE="${IMAGE:-busybox:1.36}"       # tiny; the runtime, not the app, is under test
ITERS="${ITERS:-5}"
# gvisor/kata are the conventional RuntimeClass handler names; override via env if
# your cluster names them differently (e.g. gvisor -> runsc).
DEFAULT_RUNTIMES=(runc gvisor kata)

log() { printf '%s\n' "$*" >&2; }
now_ms() { date +%s%3N; }            # epoch millis

require() { command -v "$1" >/dev/null 2>&1 || { log "FATAL: missing '$1'"; exit 2; }; }

validate() {
  require kubectl
  require date
  require python3
  # date +%N must work (GNU date); BusyBox date lacks it.
  [[ "$(date +%3N)" != "3N" ]] || { log "FATAL: 'date +%N' unsupported (need GNU date)"; exit 2; }
  log "validate: kubectl, GNU date, python3 present — harness is runnable."
  log "validate: run against a cluster with the target RuntimeClasses to collect numbers."
}

# runtime_present <name> -> 0 if a RuntimeClass of that name exists (runc always "present": it's the default, no runtimeClassName)
runtime_present() {
  local rt="$1"
  [[ "$rt" == "runc" ]] && return 0
  kubectl get runtimeclass "$rt" >/dev/null 2>&1
}

# pod_manifest <name> <runtime> -> stdout YAML. runc => no runtimeClassName.
pod_manifest() {
  local name="$1" rt="$2"
  local rc_line=""
  [[ "$rt" != "runc" ]] && rc_line="  runtimeClassName: ${rt}"
  cat <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: ${name}
  labels: { app: isi2113-bench, runtime: ${rt} }
spec:
${rc_line}
  terminationGracePeriodSeconds: 0
  containers:
  - name: c
    image: ${IMAGE}
    imagePullPolicy: IfNotPresent
    command: ["sh","-c","sleep 3600"]
    resources: { requests: { cpu: "50m", memory: "64Mi" } }
YAML
}

wait_ready() {  # <pod> -> echoes elapsed ms from now until Ready
  local pod="$1" start; start="$(now_ms)"
  kubectl -n "$NS" wait --for=condition=Ready "pod/$pod" --timeout=180s >/dev/null
  echo $(( $(now_ms) - start ))
}

# p50/p95 of space-separated ints via python (already required).
pctl() { python3 -c "
import sys
xs=sorted(int(x) for x in sys.argv[1:])
def p(q):
    if not xs: return 0
    i=min(len(xs)-1, int(q*(len(xs)-1)+0.5)); return xs[i]
print(f'{p(0.5)} {p(0.95)}')" "$@"; }

prepull() {  # DaemonSet-free prepull: one pod per runtime forces the image onto its scheduled node
  local rt="$1" p="prepull-$rt"
  pod_manifest "$p" "$rt" | kubectl -n "$NS" apply -f - >/dev/null
  kubectl -n "$NS" wait --for=condition=Ready "pod/$p" --timeout=300s >/dev/null
  kubectl -n "$NS" delete pod "$p" --wait=true >/dev/null 2>&1 || true
}

bench_runtime() {  # <runtime> -> "runtime cold_p50 cold_p95 warm_p50 warm_p95 repl_p50 repl_p95"
  local rt="$1" i cold=() warm=() repl=()
  log "  prepulling $IMAGE for $rt ..."; prepull "$rt"

  for ((i=0;i<ITERS;i++)); do
    local pod="cold-$rt-$i"
    pod_manifest "$pod" "$rt" | kubectl -n "$NS" apply -f - >/dev/null
    cold+=( "$(wait_ready "$pod")" )
    # warm-claim proxy: pod is already Ready; time an exec round-trip (the "grab").
    local w0 w1; w0="$(now_ms)"
    kubectl -n "$NS" exec "$pod" -- true >/dev/null 2>&1 || true
    w1="$(now_ms)"; warm+=( $(( w1 - w0 )) )
    # replenish: delete then create a fresh one and time to Ready (teardown-and-replace).
    kubectl -n "$NS" delete pod "$pod" --wait=true >/dev/null 2>&1 || true
    local rpod="repl-$rt-$i"
    pod_manifest "$rpod" "$rt" | kubectl -n "$NS" apply -f - >/dev/null
    repl+=( "$(wait_ready "$rpod")" )
    kubectl -n "$NS" delete pod "$rpod" --wait=false >/dev/null 2>&1 || true
  done

  read -r cp50 cp95 < <(pctl "${cold[@]}")
  read -r wp50 wp95 < <(pctl "${warm[@]}")
  read -r rp50 rp95 < <(pctl "${repl[@]}")
  echo "$rt $cp50 $cp95 $wp50 $wp95 $rp50 $rp95"
}

main() {
  [[ "${1:-}" == "--validate" ]] && { validate; exit 0; }
  require kubectl; require python3
  local -a want=("$@"); [[ ${#want[@]} -eq 0 ]] && want=("${DEFAULT_RUNTIMES[@]}")

  kubectl create namespace "$NS" >/dev/null 2>&1 || true
  trap 'kubectl delete namespace "$NS" --wait=false >/dev/null 2>&1 || true' EXIT

  local results=() skipped=()
  for rt in "${want[@]}"; do
    if runtime_present "$rt"; then
      log "benchmarking runtime=$rt (iters=$ITERS) ..."
      results+=( "$(bench_runtime "$rt")" )
    else
      log "SKIP runtime=$rt — no RuntimeClass '$rt' on this cluster"
      skipped+=( "$rt" )
    fi
  done

  printf '\n%-8s %10s %10s %10s %10s %10s %10s\n' \
    runtime cold_p50 cold_p95 warm_p50 warm_p95 repl_p50 repl_p95
  printf '%s\n' "-------- (all values in milliseconds) ------------------------------------------"
  for r in "${results[@]}"; do
    # shellcheck disable=SC2086
    set -- $r
    printf '%-8s %10s %10s %10s %10s %10s %10s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7"
  done
  [[ ${#skipped[@]} -gt 0 ]] && log "NOTE: skipped (RuntimeClass absent): ${skipped[*]}"

  log ""
  log "Next: feed measured repl_p95 (seconds) into the sizing model, e.g."
  log "  python3 -c \"from pool_sizing import table; \\"
  log "    print(table({'gvisor':<repl_p95_s>,'kata':<repl_p95_s>}, \\"
  log "                {'medium':0.2,'heavy':0.5}, 0.95))\""
}

main "$@"
