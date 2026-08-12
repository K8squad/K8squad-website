#!/usr/bin/env bash
# ratelimit-guard.sh — the fleet-runtime hook for rate-limit-aware auto-resume (ISI-2296).
#
# Call this ONCE right after a `claude -p` invocation in an agent's runtime, with the
# invocation's combined output + exit code. It decides the fate of the throttled agent
# WITHOUT burning retries or dying through the limit window:
#
#   OK / UNKNOWN -> exit 0, nothing to do (agent proceeds normally).
#   ERR          -> exit 0, normal retry path (network blip, not a throttle — not ours).
#   OVERLOAD     -> schedule ONE monitor wake at reset+jitter (transient 529, short backoff).
#   RATELIMIT    -> schedule EXACTLY ONE monitor wake at reset+jitter; persist RESUME_AT;
#                   NO busy-poll through the window (AC3).
#   AUTHFAIL     -> do NOT auto-resume; PAGE for token re-issue (spike-isi2112 §3). No silent
#                   death: mark the issue blocked + drop a durable page marker (AC4).
#
# Idempotency (AC3 "exactly one"): a per-issue guard file + a skip when the issue already has
# monitorNextCheckAt in the future ensure repeat calls in the same window don't stack wakes.
#
# Inputs (env, all overridable):
#   CLAUDE_OUT / CLAUDE_OUT_FILE   combined stdout+stderr of the claude -p call (headers too, if captured)
#   CLAUDE_CODE                    its exit code (default: $?)
#   RL_AGENT_ID                    stable agent identity (drives per-agent jitter)
#   RESUME_ISSUE_ID                Paperclip issue to wake / block
#   PAPERCLIP_API_BASE             default http://127.0.0.1:3100
#   PAPERCLIP_API_KEY              bearer for the PATCH (optional in --print/dry-run)
#   PAPERCLIP_RUN_ID               optional run-id header
#   RL_ATTEMPT                     repeat-trip counter for backoff floor (default 0)
#   OUTDIR                         state dir (default ~/.setup-token-ttl)
#   RL_SPREAD / RL_BACKOFF_CAP     jitter window / backoff cap (see ratelimit-lib.sh)
#
# --print => classify + plan only, no PATCH (dry run). Exit code encodes the class so a
# caller can branch: 0=proceed/scheduled, 3=paged(authfail).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=ratelimit-lib.sh
. "$HERE/ratelimit-lib.sh"

OUTDIR="${OUTDIR:-$HOME/.setup-token-ttl}"; mkdir -p "$OUTDIR"
LOG="$OUTDIR/guard.log"
now_epoch="$(date -u +%s)"; now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DRY=0; [[ "${1:-}" == "--print" ]] && DRY=1

out="${CLAUDE_OUT:-}"
[[ -z "$out" && -n "${CLAUDE_OUT_FILE:-}" && -f "${CLAUDE_OUT_FILE}" ]] && out="$(cat "$CLAUDE_OUT_FILE")"
code="${CLAUDE_CODE:-0}"
agent="${RL_AGENT_ID:-$(hostname 2>/dev/null || echo agent)}"
attempt="${RL_ATTEMPT:-0}"

status="$(rl_classify "$out" "$code")"
echo "$now_utc  GUARD    status=$status code=$code agent=$agent attempt=$attempt" >> "$LOG"

case "$status" in
  OK|UNKNOWN) echo "status=$status — proceed"; exit 0 ;;
  ERR)        echo "status=ERR — normal retry (not a throttle)"; exit 0 ;;
esac

# ---- AUTHFAIL: page, do NOT auto-resume (AC4 + spike-isi2112 §3 item 3) ----
if [[ "$status" == "AUTHFAIL" ]]; then
  page="$OUTDIR/PAGE_AUTHFAIL.txt"
  printf '{"status":"AUTHFAIL","detected_utc":"%s","agent":"%s","action":"page-for-token-reissue","auto_resume":false}\n' \
    "$now_utc" "$agent" > "$page"
  echo "$now_utc  PAGE     AUTHFAIL agent=$agent -> re-issue setup-token (no auto-resume)" >> "$LOG"
  echo "AUTHFAIL — paging for token re-issue; NOT scheduling a resume."
  if [[ $DRY -eq 0 && -n "${PAPERCLIP_API_KEY:-}" && -n "${RESUME_ISSUE_ID:-}" ]]; then
    base="${PAPERCLIP_API_BASE:-http://127.0.0.1:3100}"
    body='{"status":"blocked","monitorNotes":"AUTHFAIL: setup-token expired/revoked — page for re-issue (spike-isi2112 §3). No auto-resume."}'
    curl -s -o /dev/null -w 'paperclip block PATCH -> HTTP %{http_code}\n' -X PATCH \
      -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
      ${PAPERCLIP_RUN_ID:+-H "X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID"} \
      -H 'Content-Type: application/json' -d "$body" "$base/api/issues/$RESUME_ISSUE_ID" || true
  fi
  exit 3
fi

# ---- RATELIMIT / OVERLOAD: extract reset, jitter, schedule ONE wake (AC2/AC3/AC5) ----
read -r reset src <<<"$(rl_extract_reset "$out" "$now_epoch" "$status")"
wake="$(rl_jittered_resume "$reset" "$now_epoch" "$agent" "$attempt")"
wake_utc="$(date -u -d "@$wake" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
wait_s=$(( wake - now_epoch )); [[ $wait_s -lt 0 ]] && wait_s=0

cat > "$OUTDIR/RESUME_AT.txt" <<EOF
{"status":"$status","detected_utc":"$now_utc","agent":"$agent","reset_epoch":$reset,"resume_epoch":$wake,"resume_utc":"$wake_utc","wait_seconds":$wait_s,"reset_source":"$src","attempt":$attempt}
EOF
echo "$now_utc  RESUME   status=$status wake_utc=$wake_utc wait=${wait_s}s src=$src" >> "$LOG"
echo "plan: status=$status resume_utc=$wake_utc (in ${wait_s}s) src=$src jitter+backoff(agent=$agent,attempt=$attempt)"
[[ $DRY -eq 1 ]] && exit 0

if [[ -z "${PAPERCLIP_API_KEY:-}" || -z "${RESUME_ISSUE_ID:-}" ]]; then
  echo "no PAPERCLIP_API_KEY/RESUME_ISSUE_ID — resume target persisted to RESUME_AT.txt only"; exit 0
fi
base="${PAPERCLIP_API_BASE:-http://127.0.0.1:3100}"

# Idempotency: skip if this issue already has a future monitor wake (another call this window).
existing="$(curl -s -H "Authorization: Bearer $PAPERCLIP_API_KEY" "$base/api/issues/$RESUME_ISSUE_ID" 2>/dev/null \
  | grep -oE '"monitorNextCheckAt":"[^"]+"' | grep -oE '20[0-9-]+T[0-9:.Z]+' | head -1 || true)"
if [[ -n "$existing" ]]; then
  existing_epoch="$(date -u -d "$existing" +%s 2>/dev/null || echo 0)"
  if [[ "$existing_epoch" -gt "$now_epoch" ]]; then
    echo "monitor wake already scheduled for $existing — not stacking a second (idempotent)"; exit 0
  fi
fi

body="$(printf '{"monitorNextCheckAt":"%s","monitorNotes":"rate-limit resume (%s, src=%s), auto-scheduled by ratelimit-guard for agent %s"}' \
  "$wake_utc" "$status" "$src" "$agent")"
curl -s -o /dev/null -w "paperclip monitor PATCH -> HTTP %{http_code} (wake $RESUME_ISSUE_ID at $wake_utc)\n" -X PATCH \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  ${PAPERCLIP_RUN_ID:+-H "X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID"} \
  -H 'Content-Type: application/json' -d "$body" "$base/api/issues/$RESUME_ISSUE_ID" || true
exit 0
