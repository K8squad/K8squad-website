#!/usr/bin/env bash
# ISI-2295 — sequential build-falsification matrix runner.
# Runs one timed pod at a time on a SINGLE worker (no cross-pod CPU contention,
# identical node for every cell) and collects TIMING lines. Assumes the
# `buildbench` ConfigMap + `rt-buildbench` namespace already applied.
set -euo pipefail
: "${KUBECONFIG:=/home/hrexed/.config/capmox/observable-agentsandbox.kubeconfig}"
export KUBECONFIG
NS=rt-buildbench
NODE="${NODE:-observable-agentsandbox-workers-4jjsr-stfbr}"
OUT="${OUT:-/mnt/nas/project/ksquad/docs/bmad/spikes/bench/results-isi2295.txt}"

run_cell() {
  local name="$1" rt="$2" workload="$3" storage="$4" rootless="$5" iters="$6"
  local image rcline secblock datamount datavol
  if [ "$rootless" = 1 ]; then
    image="docker:27-dind-rootless"
    secblock=$'        runAsUser: 1000\n        runAsGroup: 1000\n        seccompProfile: { type: Unconfined }'
    datamount=""   # rootless: no root-owned emptyDir (chmod EPERM); use ephemeral layer
    datavol=""
  else
    image="docker:27-dind"
    secblock='        privileged: true'
    datamount='        - { name: dockerdata, mountPath: /var/lib/docker }'
    datavol='    - { name: dockerdata, emptyDir: { sizeLimit: 6Gi } }'
  fi
  local rcn=""
  [ "$rt" = "gvisor" ] && rcn="  runtimeClassName: gvisor"

  kubectl -n "$NS" delete pod "$name" --ignore-not-found --wait=true >/dev/null 2>&1 || true
  cat <<YAML | kubectl apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: $name
  namespace: $NS
  annotations: { dynatrace.com/inject: "false" }
  labels: { app: buildbench, cell: "$name" }
spec:
  nodeName: $NODE
$rcn
  restartPolicy: Never
  securityContext: {}
  containers:
    - name: dind
      image: $image
      command: ["/bin/sh", "/etc/buildbench/run.sh"]
      env:
        - { name: RT_LABEL, value: "$name" }
        - { name: ITERS, value: "$iters" }
        - { name: ROOTLESS, value: "$rootless" }
        - { name: STORAGE, value: "$storage" }
        - { name: WORKLOAD, value: "$workload" }
      securityContext:
$secblock
      resources:
        requests: { cpu: "1", memory: 1Gi }
        limits: { cpu: "3", memory: 3Gi }
      volumeMounts:
        - { name: cfg, mountPath: /etc/buildbench }
$datamount
        - { name: tmp, mountPath: /tmp }
  volumes:
    - { name: cfg, configMap: { name: buildbench } }
$datavol
    - { name: tmp, emptyDir: { sizeLimit: 2Gi } }
YAML

  echo ">>> $name (rt=$rt workload=$workload storage=$storage rootless=$rootless iters=$iters)" | tee -a "$OUT"
  # wait for terminal phase
  for _ in $(seq 1 120); do
    ph=$(kubectl -n "$NS" get pod "$name" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
    [ "$ph" = "Succeeded" ] && break
    [ "$ph" = "Failed" ] && break
    sleep 5
  done
  { kubectl -n "$NS" logs "$name" 2>&1 | grep -E 'BENCH_START|DOCKERD_READY|BASE_READY|WARMUP|TIMING|BUILD_FAILED|DOCKERD_FAILED|PULL_FAILED|BENCH_DONE' || true; } | tee -a "$OUT"
  echo "" | tee -a "$OUT"
}

: > "$OUT"
echo "# ISI-2295 build-falsification matrix — node=$NODE" | tee -a "$OUT"
# primary: compile on overlay2
run_cell compile-runc-overlay2   runc   compile overlay2 0 10
run_cell compile-gvisor-overlay2 gvisor compile overlay2 0 10
# secondary stressor: churn on overlay2
run_cell churn-runc-overlay2     runc   churn   overlay2 0 10
run_cell churn-gvisor-overlay2   gvisor churn   overlay2 0 10
# §5.3.3 capability: rootless dockerd under gVisor completes a build (vfs, small)
run_cell rootless-gvisor-vfs     gvisor churn   vfs      1 2
echo "# matrix done" | tee -a "$OUT"
