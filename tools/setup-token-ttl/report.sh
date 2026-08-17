#!/usr/bin/env bash
# report.sh — close the measurement loop with NO human (ISI-2293).
#
# The runbook version had a human read RESULT.txt and paste it back. Henrik's redirect
# on ISI-2293 was "it needs to be an automated process", so this posts the observed TTL
# (or the declared expiry from mint-capture) straight to the Paperclip issue and never
# reports the same result twice. Called automatically by probe.sh on the first AUTHFAIL;
# also runnable standalone once a declared expiry is captured at mint time.
#
# Wiring (env; all optional — with none set it just prints and no-ops the POST):
#   PAPERCLIP_API_BASE   default http://127.0.0.1:3100
#   RESUME_ISSUE_ID      the ISI-2293 issue UUID to comment on   (required to POST)
#   PAPERCLIP_API_KEY    bearer token                            (if the API needs it)
#   PAPERCLIP_RUN_ID     forwarded as X-Paperclip-Run-Id         (optional)
#
# It NEVER posts the token — RESULT.txt / mint.json hold only a redacted prefix/suffix.
set -uo pipefail

OUTDIR="${OUTDIR:-$HOME/.setup-token-ttl}"
RESULT="$OUTDIR/RESULT.txt"
STATE="$OUTDIR/mint.json"
SENT="$OUTDIR/.reported"          # idempotency sentinel — report exactly once

# Build the body from whichever tier resolved first.
if [[ -f "$RESULT" ]]; then
  body="$(cat "$RESULT")"
  kind="observed-401"
elif [[ -f "$STATE" ]] && grep -qE '"declared_expiry"[[:space:]]*:[[:space:]]*"[^"]+"' "$STATE" \
     && ! grep -qE '"declared_expiry"[[:space:]]*:[[:space:]]*""' "$STATE"; then
  exp="$(grep -oE '"declared_expiry"[[:space:]]*:[[:space:]]*"[^"]*"' "$STATE" | sed -E 's/.*"declared_expiry"[[:space:]]*:[[:space:]]*"([^"]*)"/\1/')"
  src="$(grep -oE '"declared_expiry_source"[[:space:]]*:[[:space:]]*"[^"]*"' "$STATE" | sed -E 's/.*"([^"]*)"$/\1/')"
  mint="$(grep -oE '"mint_utc"[[:space:]]*:[[:space:]]*"[^"]*"' "$STATE" | sed -E 's/.*"([^"]*)"$/\1/')"
  body=$'SETUP-TOKEN TTL — DECLARED at mint\nmint_utc:        '"$mint"$'\ndeclared_expiry: '"$exp"$'\nsource:          '"$src"
  kind="declared-$src"
else
  echo "report.sh: nothing resolved yet (no RESULT.txt, no declared expiry) — nothing to report."
  exit 0
fi

# Idempotency: never double-post the same result.
sig="$(printf '%s' "$body" | cksum | awk '{print $1}')"
if [[ -f "$SENT" ]] && grep -qx "$sig" "$SENT"; then
  echo "report.sh: result ($kind) already reported — skipping."
  exit 0
fi

echo "=== setup-token TTL result ($kind) ==="; echo "$body"

base="${PAPERCLIP_API_BASE:-http://127.0.0.1:3100}"
if [[ -z "${RESUME_ISSUE_ID:-}" ]]; then
  echo "report.sh: RESUME_ISSUE_ID unset — printed result but not posting. Set it to auto-report."
  exit 0
fi

comment="**Automated setup-token TTL measurement — result ($kind)**"$'\n\n```\n'"$body"$'\n```\n\nPosted automatically by the token-TTL canary (tools/setup-token-ttl/report.sh). This closes ISI-2293 with a measured number; fold it into the rotation alert (canary-driven, see spike §4).'
payload="$(RESUME_BODY="$comment" python3 -c 'import json,os; print(json.dumps({"body":os.environ["RESUME_BODY"]}))' 2>/dev/null \
           || printf '{"body":%s}' "$(printf '%s' "$comment" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")"

code="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  ${PAPERCLIP_API_KEY:+-H "Authorization: Bearer $PAPERCLIP_API_KEY"} \
  ${PAPERCLIP_RUN_ID:+-H "X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID"} \
  -H 'Content-Type: application/json' \
  -d "$payload" "$base/api/issues/$RESUME_ISSUE_ID/comments" || echo 000)"

echo "report.sh: Paperclip POST /issues/$RESUME_ISSUE_ID/comments -> HTTP $code"
if [[ "$code" == 2* ]]; then
  echo "$sig" >> "$SENT"     # mark reported only on success, so a failure retries next probe
else
  echo "report.sh: post failed (HTTP $code) — will retry on next canary run."
fi
