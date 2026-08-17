#!/usr/bin/env bash
# probe.sh — Tier 1 of the setup-token TTL measurement (ISI-2293).
#
# A cron-friendly canary. Each run probes the setup-token with a trivial prompt and
# appends one timestamped line to the canary log. On the FIRST transition from
# healthy -> auth-failure it records the observed TTL (elapsed since mint) and stops
# being noisy. Idempotent and safe to run every N hours forever.
#
# Isolation matters: we run with a clean HOME so the CLI authenticates with
# CLAUDE_CODE_OAUTH_TOKEN (the setup-token under test) and NOT with any interactive
# ~/.claude/.credentials.json login. We also unset ANTHROPIC_API_KEY so a stray API
# key can't mask a dead OAuth token.
#
# Setup:
#   export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-...'   # the token under test
#   crontab -e  ->  0 */6 * * *  CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-...' /path/probe.sh
#
set -uo pipefail

OUTDIR="${OUTDIR:-$HOME/.setup-token-ttl}"
mkdir -p "$OUTDIR"
STATE="$OUTDIR/mint.json"
LOG="$OUTDIR/canary.log"
RESULT="$OUTDIR/RESULT.txt"

now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
now_epoch="$(date -u +%s)"

tok="${CLAUDE_CODE_OAUTH_TOKEN:-}"
if [[ -z "$tok" ]]; then
  echo "$now_utc  ERROR    CLAUDE_CODE_OAUTH_TOKEN unset — cannot probe" | tee -a "$LOG" >&2
  exit 2
fi

# If already resolved, do nothing (cron can keep firing harmlessly).
if [[ -f "$RESULT" ]]; then
  exit 0
fi

# Isolated, token-only environment.
TMPHOME="$(mktemp -d)"
trap 'rm -rf "$TMPHOME"' EXIT

set +e
out="$(HOME="$TMPHOME" \
       CLAUDE_CODE_OAUTH_TOKEN="$tok" \
       ANTHROPIC_API_KEY="" \
       claude -p 'ok' --output-format json 2>&1)"
code=$?
set -e 2>/dev/null || true

# Classify via the shared source-of-truth (also exercised by classify.test.sh) so the
# unattended canary and its self-check can never drift. A rate/usage limit is NOT
# expiry — it must never be mistaken for a 401, and it carries a *reset time*.
# shellcheck source=classify.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/classify.sh"
status="$(classify_status "$out" "$code")"

reason="$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-200)"
echo "$now_utc  PROBE    status=$status code=$code :: $reason" >> "$LOG"

# --- Rate/usage limit: extract the reset time and write a resume plan ---------
# Sources, best-first: explicit epoch (unifiedReset / resetsAt / "reset":<epoch>),
# RFC3339 timestamp, retry-after seconds, "in N min/hours", "resets at H(:MM)(am|pm)".
# Fall back to a conservative default so we always emit a resume target.
if [[ "$status" == "RATELIMIT" || "$status" == "OVERLOAD" ]]; then
  resume_epoch=""; src=""
  epoch="$(printf '%s' "$out" | grep -oiE '(unified[_-]?reset|resets?[_-]?at|"reset")"?[[:space:]:]*"?[0-9]{10}' | grep -oE '[0-9]{10}' | head -1 || true)"
  rfc="$(printf '%s' "$out" | grep -oiE '20[0-9]{2}-[0-9]{2}-[0-9]{2}[tT ][0-9]{2}:[0-9]{2}:[0-9]{2}[zZ]?' | head -1 || true)"
  retry="$(printf '%s' "$out" | grep -oiE 'retry[_-]?after"?[[:space:]:]*"?[0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
  rel="$(printf '%s' "$out" | grep -oiE 'in [0-9]+ ?(second|minute|hour)s?' | head -1 || true)"
  if [[ -n "$epoch" ]]; then resume_epoch="$epoch"; src="epoch"
  elif [[ -n "$rfc" ]]; then resume_epoch="$(date -u -d "$(printf '%s' "$rfc" | tr 'tT' ' ' | tr -d 'zZ') UTC" +%s 2>/dev/null || true)"; src="rfc3339"
  elif [[ -n "$retry" ]]; then resume_epoch=$(( now_epoch + retry )); src="retry-after:${retry}s"
  elif [[ -n "$rel" ]]; then
    n="$(printf '%s' "$rel" | grep -oE '[0-9]+')"; unit="$(printf '%s' "$rel" | grep -oiE '(second|minute|hour)')"
    case "$unit" in second*) m=1;; minute*) m=60;; hour*) m=3600;; *) m=60;; esac
    resume_epoch=$(( now_epoch + n*m )); src="relative:${rel}"
  fi
  if [[ -z "$resume_epoch" ]]; then
    # Default: overloads clear fast; subscription usage windows are ~5h.
    if [[ "$status" == "OVERLOAD" ]]; then resume_epoch=$(( now_epoch + 120 )); src="default-overload-2m"
    else resume_epoch=$(( now_epoch + 5*3600 )); src="default-usage-window-5h"; fi
  fi
  resume_utc="$(date -u -d "@$resume_epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
  wait_s=$(( resume_epoch - now_epoch )); [[ $wait_s -lt 0 ]] && wait_s=0
  cat > "$OUTDIR/RESUME_AT.txt" <<EOF
{"status":"$status","detected_utc":"$now_utc","resume_utc":"$resume_utc","resume_epoch":$resume_epoch,"wait_seconds":$wait_s,"reset_source":"$src"}
EOF
  echo "$now_utc  RESUME   status=$status resume_utc=$resume_utc wait=${wait_s}s src=$src" >> "$LOG"
  # This canary keeps probing on its own cron cadence, so a RATELIMIT is self-healing
  # here. In the FLEET runtime, feed RESUME_AT.txt to the resume-planner to schedule a
  # heartbeat instead of hammering (see resume-planner.sh + child issue).
fi

if [[ "$status" == "AUTHFAIL" ]]; then
  mint_epoch="$(grep -oE '"mint_epoch"[[:space:]]*:[[:space:]]*[0-9]+' "$STATE" 2>/dev/null | grep -oE '[0-9]+' || echo 0)"
  mint_utc="$(grep -oE '"mint_utc"[[:space:]]*:[[:space:]]*"[^"]+"' "$STATE" 2>/dev/null | grep -oE '"[0-9T:.Z-]+"$' | tr -d '"' || echo unknown)"
  if [[ "$mint_epoch" -gt 0 ]]; then
    secs=$(( now_epoch - mint_epoch ))
    days=$(awk "BEGIN{printf \"%.2f\", $secs/86400}")
  else
    secs="unknown"; days="unknown"
  fi
  {
    echo "SETUP-TOKEN TTL — OBSERVED (upper bound)"
    echo "mint_utc:        $mint_utc"
    echo "first_401_utc:   $now_utc"
    echo "observed_ttl:    ${days} days  (${secs} s)"
    echo "note: this is an UPPER bound — true expiry lies between the last OK probe and this one;"
    echo "      tighten by probe interval. Report this back on ISI-2293."
  } | tee "$RESULT"

  # Close the loop with NO human: if wired to Paperclip, auto-report the result.
  # (This is what makes the canary an automated *process*, not a runbook — ISI-2293.)
  rep="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/report.sh"
  [[ -x "$rep" ]] && "$rep" || true
fi
