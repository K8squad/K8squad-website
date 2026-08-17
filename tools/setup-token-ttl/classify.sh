#!/usr/bin/env bash
# classify.sh — the ONE source of truth for probe classification (ISI-2293).
#
# Sourced by probe.sh and exercised by classify.test.sh so the unattended canary and
# its self-check can never drift. A rate/usage limit is NOT expiry: mis-reading a 429
# as a 401 would fabricate a short TTL, so ordering is deliberate.
#
#   classify_status "<combined stdout+stderr of the probe>" <exit_code>  -> echoes:
#     OK        healthy (exit 0 + a JSON-shaped result)
#     RATELIMIT 429 / rate_limit_error / usage cap / quota  -> throttled, has a reset
#     OVERLOAD  529 / overloaded_error                      -> transient server load
#     AUTHFAIL  401 / expired / revoked / invalid token     -> the TTL signal
#     ERR       other nonzero (network/unknown)             -> proves nothing
#     UNKNOWN   exit 0 but no recognizable JSON              -> keep probing
classify_status() {
  local out="$1" code="$2"
  if [[ "$code" -eq 0 ]] && printf '%s' "$out" | grep -qiE '"(result|type|role|content)"'; then
    echo OK
  elif printf '%s' "$out" | grep -qiE '529|overloaded_error|"type"[^}]*overloaded'; then
    echo OVERLOAD
  elif printf '%s' "$out" | grep -qiE '429|rate.?limit|rate_limit_error|usage.?limit|quota|too.?many.?requests|limit.*reset|reset.*limit'; then
    echo RATELIMIT
  elif printf '%s' "$out" | grep -qiE '401|unauthor|invalid.?(api.?key|token|credential)|authentication_error|oauth.*(expired|revoked)|expired.*token'; then
    echo AUTHFAIL
  elif [[ "$code" -ne 0 ]]; then
    echo ERR
  else
    echo UNKNOWN
  fi
}
