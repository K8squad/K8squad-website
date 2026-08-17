#!/usr/bin/env bash
# resume-planner.sh — turn a detected rate/usage limit into a scheduled resume.
#
# Consumes the RESUME_AT.txt written by probe.sh and schedules ONE heartbeat at the
# reset time to relaunch work, instead of hammering the API through the limit window.
# This is the fleet-runtime side of Henrik's ask on ISI-2293; the seat canary is
# self-healing (its own cron re-probes), so this matters for the agent runtime.
#
# Two backends, auto-selected:
#   1. Paperclip  — if PAPERCLIP_API_URL + PAPERCLIP_API_KEY + RESUME_ISSUE_ID are set,
#                   POST a monitor/wake on the issue at resume_epoch (relaunch the agent).
#   2. at(1)      — otherwise schedule a local one-shot that runs $RESUME_CMD.
# With --print it only emits the plan (dry run).
#
set -euo pipefail
OUTDIR="${OUTDIR:-$HOME/.setup-token-ttl}"
F="$OUTDIR/RESUME_AT.txt"
[[ -f "$F" ]] || { echo "no $F — nothing to schedule (no rate limit detected)"; exit 0; }

get() { grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"?[^,\"}]+" "$F" | sed -E "s/.*:[[:space:]]*\"?//"; }
resume_epoch="$(get resume_epoch)"
resume_utc="$(get resume_utc)"
wait_s="$(get wait_seconds)"
status="$(get status)"
echo "plan: status=$status resume_utc=$resume_utc (in ${wait_s}s)"

if [[ "${1:-}" == "--print" ]]; then exit 0; fi

# Backend 1: Paperclip monitor wake (relaunch the agent on the issue at reset time).
if [[ -n "${PAPERCLIP_API_URL:-}" && -n "${PAPERCLIP_API_KEY:-}" && -n "${RESUME_ISSUE_ID:-}" ]]; then
  base="${PAPERCLIP_API_BASE:-http://127.0.0.1:3100}"
  # RFC3339 resume time; schedule a monitor check that wakes the assignee.
  body="$(printf '{"monitorNextCheckAt":"%s","monitorNotes":"rate-limit resume (%s), auto-scheduled by resume-planner"}' "$resume_utc" "$status")"
  code="$(curl -s -o /dev/null -w '%{http_code}' -X PATCH \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    ${PAPERCLIP_RUN_ID:+-H "X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID"} \
    -H 'Content-Type: application/json' \
    -d "$body" "$base/api/issues/$RESUME_ISSUE_ID" || echo 000)"
  echo "paperclip monitor PATCH -> HTTP $code (wake issue $RESUME_ISSUE_ID at $resume_utc)"
  [[ "$code" == 2* ]] && exit 0
  echo "paperclip path failed; falling through to at(1)"
fi

# Backend 2: local one-shot at the reset time.
cmd="${RESUME_CMD:-$(cd "$(dirname "$0")" && pwd)/probe.sh}"
if command -v at >/dev/null 2>&1; then
  echo "$cmd" | at -t "$(date -u -d "@$resume_epoch" +%Y%m%d%H%M.%S)" 2>&1 | sed 's/^/at: /'
  echo "scheduled '$cmd' via at(1) for $resume_utc"
else
  echo "at(1) unavailable. Sleep-and-run fallback (keep this process alive):"
  echo "  ( sleep $wait_s && $cmd ) &"
fi
