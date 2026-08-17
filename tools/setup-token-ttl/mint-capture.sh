#!/usr/bin/env bash
# mint-capture.sh — Tier 0 of the setup-token TTL measurement (ISI-2293).
#
# Run this ONCE, immediately after `claude setup-token`, on the real Pro/Max seat.
# It records the mint timestamp and tries every *declared-expiry* source before we
# fall back to the (potentially months-long) 401 canary.
#
# It NEVER logs the full token. It prints a redacted prefix only.
#
# Usage:
#   claude setup-token          # copy the printed sk-ant-oat01-... token
#   export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-...'
#   ./mint-capture.sh
#
set -euo pipefail

OUTDIR="${OUTDIR:-$HOME/.setup-token-ttl}"
mkdir -p "$OUTDIR"
STATE="$OUTDIR/mint.json"
LOG="$OUTDIR/canary.log"

tok="${CLAUDE_CODE_OAUTH_TOKEN:-}"
if [[ -z "$tok" ]]; then
  echo "ERROR: CLAUDE_CODE_OAUTH_TOKEN is not set. Export the token from 'claude setup-token' first." >&2
  exit 1
fi

now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
now_epoch="$(date -u +%s)"
prefix="${tok:0:16}"        # e.g. sk-ant-oat01-xxx — safe to record
suffix="${tok: -4}"         # last 4 for identification
tok_len="${#tok}"

declared_expiry=""
declared_source=""

# --- Source A: JWT? (opaque sk-ant-oat01 tokens are NOT JWTs, but check anyway) ---
b64url_decode() { local s="${1//-/+}"; s="${s//_//}"; local m=$(( ${#s} % 4 )); [[ $m -ne 0 ]] && s="$s$(printf '=%.0s' $(seq $((4-m))))"; printf '%s' "$s" | base64 -d 2>/dev/null || true; }
if [[ "$tok" == *.*.* ]]; then
  payload="$(b64url_decode "$(printf '%s' "$tok" | cut -d. -f2)")"
  exp="$(printf '%s' "$payload" | grep -oE '"exp"[[:space:]]*:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' || true)"
  if [[ -n "$exp" ]]; then
    declared_expiry="$(date -u -d "@$exp" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "epoch:$exp")"
    declared_source="jwt.exp"
  fi
fi

# --- Source B: does `claude setup-token` persist an expiry to the config? ---
for cand in "$HOME/.claude/.credentials.json" "$HOME/.config/claude/.credentials.json"; do
  [[ -f "$cand" ]] || continue
  # look for any *expiresAt-like key that is NOT the interactive-login access token
  e="$(grep -oE '"[a-zA-Z]*[Ee]xpires?At"[[:space:]]*:[[:space:]]*"[^"]+"' "$cand" || true)"
  if [[ -n "$e" && -z "$declared_expiry" ]]; then
    declared_expiry="$(printf '%s' "$e" | head -1 | grep -oE '"[0-9T:.Z+-]+"$' | tr -d '"' || true)"
    declared_source="config:$cand"
  fi
done

cat > "$STATE" <<EOF
{
  "mint_utc": "$now_utc",
  "mint_epoch": $now_epoch,
  "token_prefix": "$prefix",
  "token_suffix": "$suffix",
  "token_len": $tok_len,
  "declared_expiry": "${declared_expiry}",
  "declared_expiry_source": "${declared_source}",
  "seat": "${SEAT_LABEL:-unknown-Pro-or-Max-seat}"
}
EOF

{
  echo "$now_utc  MINT     token=${prefix}…${suffix} len=${tok_len}"
  if [[ -n "$declared_expiry" ]]; then
    echo "$now_utc  DECLARED expiry=${declared_expiry} source=${declared_source}"
  else
    echo "$now_utc  DECLARED none-found — declared expiry not exposed; canary required"
  fi
} | tee -a "$LOG"

echo
echo "State written: $STATE"
if [[ -n "$declared_expiry" ]]; then
  echo
  echo ">>> DECLARED TTL FOUND. You may be done: report mint=$now_utc, expiry=$declared_expiry (source=$declared_source)."
  echo ">>> Still start the canary (probe.sh) as confirmation, but you likely don't need to wait."
else
  echo
  echo ">>> No declared expiry exposed (expected for opaque sk-ant-oat01 tokens)."
  echo ">>> Start the canary: schedule probe.sh (see runbook). First 401 = observed TTL."
fi
