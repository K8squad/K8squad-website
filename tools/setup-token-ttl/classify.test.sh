#!/usr/bin/env bash
# classify.test.sh — self-check for the canary's ONE piece of non-trivial logic (ISI-2293).
# No frameworks: feed canned `claude -p` outputs through classify_status and assert.
# The whole point is that an UNATTENDED canary must never mistake a 429 for a 401 (which
# would fabricate a short TTL) or let a network blip look like expiry.
set -uo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/classify.sh"

fail=0
check() { # want  out  code
  local want="$1" got; got="$(classify_status "$2" "$3")"
  if [[ "$got" == "$want" ]]; then echo "ok   $want"; else echo "FAIL want=$want got=$got :: ${2:0:60}"; fail=1; fi
}

# healthy
check OK        '{"type":"result","result":"ok"}'                         0
check UNKNOWN   'ok'                                                       0     # exit 0 but no JSON shape
# the dangerous confusions — a usage/rate cap must NOT read as expiry
check RATELIMIT '{"type":"error","error":{"type":"rate_limit_error"}}'    1
check RATELIMIT 'HTTP 429 Too Many Requests'                              1
check RATELIMIT 'You have hit your usage limit; resets at 5pm'            1
check OVERLOAD  '{"type":"error","error":{"type":"overloaded_error"}}'    1
check OVERLOAD  'HTTP 529'                                                 1
# the signal we actually measure
check AUTHFAIL  '{"type":"error","error":{"type":"authentication_error"}}' 1
check AUTHFAIL  'HTTP 401 Unauthorized'                                    1
check AUTHFAIL  'OAuth token expired'                                      1
check AUTHFAIL  'invalid token'                                            1
# noise that proves nothing — must keep probing, never resolve
check ERR       'curl: (6) Could not resolve host: api.anthropic.com'      6

# precedence: an overloaded error that also happens to contain "401" text must stay
# OVERLOAD (529 is checked first) — guards against a body that mentions both.
check OVERLOAD  'overloaded_error (was 401 earlier)'                       1

if [[ $fail -eq 0 ]]; then echo "PASS — classify_status all green"; else echo "SOME TESTS FAILED"; fi
exit $fail
