#!/usr/bin/env bash
# Story X.2 runtime driver — residue/reuse test across Runs and principals, ON A REAL CLUSTER.
# (arch §9.3 teardown-and-replace / ADR-006, §9.4 per-principal scoping, §12.1; FR-C6, NFR-SEC5,
#  R12; testing §6.5 S4 reuse-residue case; absorbed into L4 §14.4 — ISI-2245.)
#
# The VERDICT is `residue-reuse-check.py` (the offline-proven oracle). This driver is the kind
# binding: it plants POISON-TOKEN-run1 into every residue channel inside a REAL sandbox pod
# (Run 1 / principal p1), applies the hygiene policy under test, then probes every channel from a
# successor Run by a DIFFERENT principal (p2) and feeds the observations to the oracle's
# `--observed` judge. A green run therefore uses the same `violations()` the mutation contract
# gave teeth to — not a second, weaker check (retro F2 bar from ISI-2237/ISI-2539).
#
# Policies (C1/C2/C5/C6):
#   teardown+per-principal  — §9.3/§9.4 shipped posture. Pod destroyed + fresh pod; Project-PVC
#                             cache mounted at the per-principal subPath. EXPECT judge PASS and
#                             pod UID change (C2).
#   reset-partial           — reset-in-place candidate: SAME pod reused after a scrub that covers
#                             scratch-fs + git-worktree but misses in-mem-secret / build-cache-pod
#                             / cred-env (ADR-006's losing game). EXPECT judge FAIL on exactly the
#                             3 unscrubbed channels (C6a).
#   reset-shared-pvc        — fresh pod + perfect pod scrub, but the Project-PVC cache is mounted
#                             at ONE shared per-Project subPath. EXPECT judge FAIL on
#                             pvc-cross-principal (C6b — §9.4 is independently load-bearing).
#
# Usage (S4 kind lane / any cluster with kubectl):
#   ./residue-reuse-kind.sh                          # full matrix: all 3 policies + C2 + C5 control
#   ./residue-reuse-kind.sh --policy teardown+per-principal
#   ./residue-reuse-kind.sh --namespace ksquad-x2-s4 --runtime-class gvisor
#   ./residue-reuse-kind.sh --volume-mode pvc         # force Project-PVC workspace (default: auto)
#   ./residue-reuse-kind.sh --self-check              # NO cluster: prove judge wiring + failure modes
#
# Preconditions (fail-fast, honest): kubectl + a reachable cluster; namespace creatable; image
# default alpine/git (git present for the git-worktree channel). Volume mode auto: Project-PVC
# (ReadWriteMany, default StorageClass) when one exists — the lane posture; else hostPath
# ($HOSTPATH_DIR, node-pinned, durable across pods) so clusters without dynamic provisioning
# still exercise every channel including the durable cross-principal one. RuntimeClass auto:
# gvisor when present (Story 4.2 posture), else the lane default.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORACLE="$HERE/residue-reuse-check.py"
NS="ksquad-x2-s4"
RUNTIME_CLASS="${X2_RUNTIME_CLASS:-auto}"     # auto = use gvisor RuntimeClass when present (4.2)
IMAGE="${X2_IMAGE:-alpine/git:latest}"
VOLUME_MODE="${X2_VOLUME_MODE:-auto}"         # auto|pvc|hostpath (hostpath: node-pinned, durable)
PROJECT="proj"
PVC="x2-project-ws"
HOSTPATH_DIR="/var/tmp/ksquad-x2-s4"
POISON="POISON-TOKEN-run1"
POLICY="ALL"
SELFCHECK=0
NODE_PIN=""

while [ $# -gt 0 ]; do
  case "$1" in
    --policy) POLICY="$2"; shift 2 ;;
    --namespace) NS="$2"; shift 2 ;;
    --runtime-class) RUNTIME_CLASS="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --volume-mode) VOLUME_MODE="$2"; shift 2 ;;
    --self-check) SELFCHECK=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

# per-principal PVC subPath — MUST match principal_subpath() in residue-reuse-check.py and
# teardown-scoping-check.py (boundary agreement with Story 4.5): proj/cache/<p>-<sha12>.
subpath() { # project principal
  local h
  h="$(printf '%s' "$2" | sha256sum | cut -c1-12)"
  printf '%s/cache/%s-%s' "$1" "$2" "$h"
}
SP1="$(subpath "$PROJECT" p1)"
SP2="$(subpath "$PROJECT" p2)"
SPS="$PROJECT/cache-shared"

rc_block() {
  if [ "$RUNTIME_CLASS" = "auto" ]; then
    kubectl get runtimeclass gvisor >/dev/null 2>&1 && RUNTIME_CLASS="gvisor" || RUNTIME_CLASS=""
  fi
  [ -n "$RUNTIME_CLASS" ] && printf '  runtimeClassName: %s\n' "$RUNTIME_CLASS" || true
}

# --- payloads ---------------------------------------------------------------
# PLANT (Run 1 / p1): write POISON into every channel §9.3/§9.4 names.
PLANT='set -eu
T=POISON-TOKEN-run1
mkdir -p /tmp/ksquad-x2 /workspace/.scratch ~/.cache/ksquad-build ~/.ksquad-creds
printf "%s scratch-fs\n" "$T"            > /tmp/ksquad-x2/scratch.txt        # scratch-fs (/tmp)
printf "%s scratch-ws\n" "$T"            > /workspace/.scratch/ws-poison    # scratch-fs (ws)
printf "%s in-mem-secret\n" "$T"         > /dev/shm/x2-secret               # tmpfs secret
git config --global user.email p1@x2.local; git config --global user.name p1
rm -rf /workspace/repo; git init -q /workspace/repo                        # git-worktree state
cd /workspace/repo; printf "%s git-worktree\n" "$T" > staged.txt
git add staged.txt; git checkout -q -b poison-branch                       # staged index + branch
printf "%s build-cache-pod\n" "$T"       > ~/.cache/ksquad-build/entry      # poisoned build cache
printf "CREDS %s cred-env\n" "$T"        > ~/.ksquad-creds/cred.env         # mounted-secret file
mkdir -p /workspace/cache                                                 # own PVC subpath (legit, FR-C2)
printf "%s pvc-cache\n" "$T"             > /workspace/cache/p1-poison.marker
echo PLANT-OK'

# PROBE (successor Run): enumerate every channel, emit JSONL of POISON it can observe that it did
# not author. Fields: {channel, token, author_run, author_principal} — exactly what the oracle
# judge consumes. ALSO records own-author cache (C5 positive control line).
PROBE='set -eu
T=POISON-TOKEN-run1
emit() { printf "{\"channel\":\"%s\",\"token\":\"%s\",\"author_run\":\"%s\",\"author_principal\":\"%s\"}\n" "$1" "$2" "$3" "$4"; }
grep -rq "$T" /tmp/ksquad-x2 2>/dev/null            && emit scratch-fs       "$T scratch-fs"       run1 p1
[ -e /workspace/.scratch/ws-poison ]                && emit scratch-fs       "$T scratch-ws"       run1 p1
[ -e /dev/shm/x2-secret ]                           && emit in-mem-secret    "$T in-mem-secret"    run1 p1
if [ -d /workspace/repo/.git ]; then                                                # git-worktree residue
  # residue = staged index, dirty tree, or the poison branch (C3: staged/branch/dirty).
  # NOTE: git diff --quiet exits 0 when CLEAN, so the residue test is the NEGATION.
  (cd /workspace/repo && { ! git diff --cached --quiet 2>/dev/null || ! git diff --quiet 2>/dev/null || git symbolic-ref -q --short HEAD | grep -q poison-branch; }) \
    && emit git-worktree "$T git-worktree" run1 p1
fi
[ -e ~/.cache/ksquad-build/entry ]                  && emit build-cache-pod  "$T build-cache-pod"  run1 p1
[ -e ~/.ksquad-creds/cred.env ]                     && emit cred-env        "$T cred-env"         run1 p1
env | grep -q "X2_POISON=$T"                        && emit cred-env        "$T cred-env-env"     run1 p1
for m in $(find /workspace -maxdepth 4 -name "*poison.marker" 2>/dev/null); do  # PVC visibility
  emit pvc-cross-principal "$T pvc-cache" run1 p1
done
[ -e /workspace/cache/p1-self.marker ]              && emit pvc-cross-principal "CACHE-p1" run3 p1  # C5 control line
echo PROBE-OK'

mkpod() { # name principal subpath|none poison_env
  local sub="$3" envblock="" vol pin=""
  [ "$4" = "yes" ] && envblock=$'      env:\n        - { name: X2_POISON, value: POISON-TOKEN-run1 }'
  if [ "$VOLUME_MODE" = "hostpath" ]; then
    vol="    - { name: ws, hostPath: { path: $HOSTPATH_DIR, type: DirectoryOrCreate } }"
  else
    vol="    - { name: ws, persistentVolumeClaim: { claimName: $PVC } }"
  fi
  [ -n "$NODE_PIN" ] && pin="  nodeName: $NODE_PIN"
  local spblock=""
  if [ "$sub" = "none" ]; then
    spblock=$'        - { name: ws, mountPath: /workspace }'
  else
    spblock=$'        - { name: ws, mountPath: /workspace, subPath: '"$sub"' }'
  fi
  cat <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: $1
  namespace: $NS
  labels: { story: x2, run: "$1", principal: "$2" }
spec:
$(rc_block)
$pin
  restartPolicy: Never
  containers:
    - name: main
      image: $IMAGE
      command: ["/bin/sh", "-c", "sleep 600"]
      volumeMounts:
$spblock
$envblock
  volumes:
$vol
YAML
}

uid_of() { kubectl -n "$NS" get pod "$1" -o jsonpath='{.metadata.uid}'; }
run_in() { # pod script
  kubectl -n "$NS" exec "$1" -- /bin/sh -c "$2"
}
new_pod() { # name principal subpath poison_env
  mkpod "$1" "$2" "$3" "$4" | kubectl apply -f - >/dev/null
  kubectl -n "$NS" wait --for=condition=Ready "pod/$1" --timeout=180s >/dev/null
}

setup_ns() {
  kubectl get namespace "$NS" >/dev/null 2>&1 || kubectl create namespace "$NS" >/dev/null
  if [ "$VOLUME_MODE" = "auto" ]; then
    if kubectl get storageclass -o json 2>/dev/null | grep -q 'storageclass.kubernetes.io/is-default-class":"true'; then
      VOLUME_MODE="pvc"
    else
      echo "[setup] no default StorageClass on this cluster -> volume-mode hostpath (node-pinned, durable across pods)"
      VOLUME_MODE="hostpath"
    fi
  fi
  if [ "$VOLUME_MODE" = "pvc" ] && ! kubectl -n "$NS" get pvc "$PVC" >/dev/null 2>&1; then
    kubectl -n "$NS" apply -f - >/dev/null <<YAML
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: $PVC, namespace: $NS }
spec:
  accessModes: [ReadWriteMany]
  resources: { requests: { storage: 1Gi } }
YAML
    kubectl -n "$NS" wait --for=condition=Bound pvc/"$PVC" --timeout=180s >/dev/null
  fi
  # Prime: mount the volume at root, wipe stale residue from prior runs, create the subPath tree
  # (a subPath must exist before it can be mounted), and capture the node to pin in hostpath mode.
  new_pod x2-prime p1 none no
  if [ "$VOLUME_MODE" = "hostpath" ]; then
    NODE_PIN="$(kubectl -n "$NS" get pod x2-prime -o jsonpath='{.spec.nodeName}')"
    echo "[setup] hostpath mode: pinning pods to node $NODE_PIN ($HOSTPATH_DIR)"
  fi
  run_in x2-prime "rm -rf /workspace/$PROJECT && mkdir -p /workspace/$SP1 /workspace/$SP2 /workspace/$SPS"
  kubectl -n "$NS" delete pod x2-prime --wait=true >/dev/null
}

# One full plant -> hygiene -> probe cycle for a given policy. Prints the JSONL observations to
# $1 (plus .uid sidecars), returns the p2 probe pod UID via global RUN2_UID.
cycle() { # out_jsonl policy
  local out="$1" pol="$2" sp1 sp2 probe_pod="x2-run2"
  case "$pol" in
    teardown+per-principal|reset-partial) sp1="$SP1"; sp2="$SP2" ;;
    reset-shared-pvc)                     sp1="$SPS"; sp2="$SPS" ;;
    *) echo "unknown policy: $pol" >&2; exit 64 ;;
  esac

  kubectl -n "$NS" delete pod x2-run1 x2-run2 x2-run3 --ignore-not-found --wait=true >/dev/null 2>&1 || true
  new_pod x2-run1 p1 "$sp1" yes
  run_in x2-run1 "$PLANT"
  uid_of x2-run1 > "${out}.run1.uid"

  case "$pol" in
    teardown+per-principal)
      kubectl -n "$NS" delete pod x2-run1 --wait=true >/dev/null      # §9.3: pod dies with its residue
      new_pod x2-run2 p2 "$sp2" no                                     # fresh pod = fresh pod-local state
      ;;
    reset-partial)
      run_in x2-run1 'rm -rf /tmp/ksquad-x2 /workspace/.scratch /workspace/repo'   # scrub the obvious fs channels ONLY
      probe_pod="x2-run1"                                             # Run 2 REUSES the same pod (the opt under test)
      ;;
    reset-shared-pvc)
      kubectl -n "$NS" delete pod x2-run1 --wait=true >/dev/null       # perfect pod scrub via replace...
      new_pod x2-run2 p2 "$sp2" no                                     # ...but ONE shared PVC subpath
      ;;
  esac
  RUN2_UID="$(uid_of "$probe_pod")"    # C2: must differ from run1 uid under every admissible policy
  run_in "$probe_pod" "$PROBE" > "$out"

  # C5 positive control: a LATER p1 Run must still see its OWN cache (FR-C2) and stay clean.
  if [ "$pol" = "teardown+per-principal" ]; then
    kubectl -n "$NS" delete pod x2-run2 --wait=true >/dev/null
    new_pod x2-run3 p1 "$sp1" no
    run_in x2-run3 'printf self > /workspace/cache/p1-self.marker'   # authored by p1 itself
    run_in x2-run3 "$PROBE" > "${out}.c5"
  fi
}

judge() { # jsonl observer_run observer_principal
  python3 "$ORACLE" --observed "$1" --observer-run "$2" --observer-principal "$3"
}

expect_pass() { # label jsonl obs_run obs_pri
  if judge "$2" "$3" "$4"; then echo "[$1] judge PASS (expected PASS) ✓"; return 0; fi
  echo "[$1] judge FAIL — expected PASS (CI RED)" >&2; return 1
}
expect_fail() { # label jsonl obs_run obs_pri want_channels_csv
  local out; out="$(judge "$2" "$3" "$4" || true)"
  echo "$out"
  local want got=1
  for want in ${5//,/ }; do echo "$out" | grep -q "\[$want\]" || got=0; done
  if [ "$got" = 1 ] && echo "$out" | grep -q "FAIL"; then echo "[$1] judge FAIL on expected channels ✓"; return 0; fi
  echo "[$1] expected FAIL on [$5] — gate did NOT fire (TEETH LOST)" >&2; return 1
}

self_check() {
  echo "== self-check (no cluster): judge wiring + both failure modes =="
  local tmp; tmp="$(mktemp)"
  printf '%s\n' \
    '{"channel":"cred-env","token":"POISON-TOKEN-run1 cred-env","author_run":"run1","author_principal":"p1"}' > "$tmp"
  judge "$tmp" run2 p2 >/dev/null && { echo "self-check: poison line must FAIL the judge"; exit 1; }
  echo "  poison observation -> judge FAIL ✓"
  printf '%s\n' \
    '{"channel":"pvc-cross-principal","token":"CACHE-p1","author_run":"run3","author_principal":"p1"}' > "$tmp"
  judge "$tmp" run3 p1 >/dev/null || { echo "self-check: same-principal cache must PASS"; exit 1; }
  echo "  same-principal cache (FR-C2) -> judge PASS ✓"
  python3 "$ORACLE" >/dev/null      || exit 1   # offline oracle + teeth still green
  python3 "$ORACLE" --mutate >/dev/null || exit 1
  echo "  offline oracle base+mutate -> PASS ✓"
  rm -f "$tmp"; echo "self-check PASS"
}

[ "$SELFCHECK" = 1 ] && { self_check; exit 0; }

command -v kubectl >/dev/null || { echo "kubectl required" >&2; exit 64; }
python3 "$ORACLE" >/dev/null && python3 "$ORACLE" --mutate >/dev/null   # precondition: teeth intact
setup_ns

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
rc=0
run_case() { # policy
  local pol="$1" f="$WORK/$1.jsonl"
  echo; echo "== policy: $1 =="
  cycle "$f" "$1"
  local u1; u1="$(cat "${f}.run1.uid")"
  case "$1" in
    teardown+per-principal)
      [ "$u1" != "$RUN2_UID" ] || { echo "C2 violated: Run2 reused Run1 pod UID ($u1)"; rc=1; }
      echo "C2 pod UID: run1=$u1 run2=$RUN2_UID distinct ✓"
      expect_pass "$1" "$f" run2 p2 || rc=1
      if [ -f "${f}.c5" ]; then
        grep -q "CACHE-p1" "${f}.c5" && echo "C5 same-principal cache VISIBLE to p1 ✓" || { echo "C5 control broken: p1 cannot see own cache"; rc=1; }
        expect_pass "$1-c5" "${f}.c5" run3 p1 || rc=1
      fi
      ;;
    reset-partial)      expect_fail "$1" "$f" run2 p2 in-mem-secret,build-cache-pod,cred-env || rc=1 ;;
    reset-shared-pvc)   expect_fail "$1" "$f" run2 p2 pvc-cross-principal || rc=1 ;;
  esac
}

if [ "$POLICY" = "ALL" ]; then
  run_case teardown+per-principal
  run_case reset-partial
  run_case reset-shared-pvc
else
  run_case "$POLICY"
fi

echo; if [ "$rc" = 0 ]; then echo "X.2 runtime residue suite: PASS — §9.3/§9.4 posture clean; deviations gated."; else echo "X.2 runtime residue suite: FAIL"; fi
exit "$rc"
