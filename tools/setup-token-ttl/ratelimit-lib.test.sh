#!/usr/bin/env bash
# ratelimit-lib.test.sh — self-check for the rate-limit auto-resume core (ISI-2296).
# No framework: assert-based. Run: ./ratelimit-lib.test.sh  (exit 0 = all pass).
set -uo pipefail
. "$(cd "$(dirname "$0")" && pwd)/ratelimit-lib.sh"
fails=0
ok()  { echo "  ok: $1"; }
eq()  { if [[ "$2" == "$3" ]]; then ok "$1"; else echo "  FAIL: $1 — got '$2' want '$3'"; fails=$((fails+1)); fi; }
ge()  { if [[ "$2" -ge "$3" ]]; then ok "$1"; else echo "  FAIL: $1 — $2 < $3"; fails=$((fails+1)); fi; }
le()  { if [[ "$2" -le "$3" ]]; then ok "$1"; else echo "  FAIL: $1 — $2 > $3"; fails=$((fails+1)); fi; }
NOW=1000000000

echo "[classify]"
eq  "healthy JSON => OK"        "$(rl_classify '{"result":"hi","type":"text"}' 0)"                 OK
eq  "529 => OVERLOAD"           "$(rl_classify '{"type":"error","error":{"type":"overloaded_error"}}' 1)" OVERLOAD
eq  "429 => RATELIMIT"          "$(rl_classify 'HTTP 429 rate_limit_error usage limit reached' 1)"  RATELIMIT
eq  "401 => AUTHFAIL"           "$(rl_classify 'HTTP 401 authentication_error: token expired' 1)"   AUTHFAIL
# THE correctness case (AC1/AC4): a usage-limit body that also mentions "401" must NOT be read as auth-death.
eq  "429+stray 401 => RATELIMIT (not AUTHFAIL)" \
    "$(rl_classify 'rate_limit_error: usage limit reached (ref 401xx) retry later' 1)"             RATELIMIT
eq  "network nonzero => ERR"    "$(rl_classify 'curl: (6) could not resolve host' 7)"              ERR
# F2: an error envelope returned AT EXIT 0 matches on "type"/"content" — it must NOT classify OK,
# else OVERLOAD/RATELIMIT never fire and the guard no-ops with no resume scheduled.
eq  "overloaded_error @code0 => OVERLOAD (not OK)" \
    "$(rl_classify '{"type":"error","error":{"type":"overloaded_error","message":"overloaded"}}' 0)"  OVERLOAD
eq  "rate_limit_error @code0 => RATELIMIT (not OK)" \
    "$(rl_classify '{"type":"error","error":{"type":"rate_limit_error","message":"usage limit reached"}}' 0)" RATELIMIT

echo "[extract — headers beat message text (AC2)]"
# retry-after header present alongside a misleading "in 9 hours" message => header wins.
read -r e s <<<"$(rl_extract_reset 'retry-after: 120
error: rate limit, try again in 9 hours' "$NOW" RATELIMIT)"
eq  "retry-after header used"   "$s" "header:retry-after:120s"
eq  "retry-after epoch = now+120" "$e" "$((NOW+120))"
# anthropic-ratelimit-*-reset RFC3339 header.
read -r e s <<<"$(rl_extract_reset 'anthropic-ratelimit-unified-reset: 2001-09-09T02:46:40Z' "$NOW" RATELIMIT)"
eq  "ratelimit-reset header src" "$s" "header:ratelimit-reset"
ge  "ratelimit-reset parsed"     "$e" 1000000000
# F1: multiple *-reset headers at different times. Prefer `unified` even when a tokens-reset
# appears EARLIER in the body (head -1 would have wrongly picked the earlier, non-binding one).
read -r e s <<<"$(rl_extract_reset 'anthropic-ratelimit-tokens-reset: 1000000200
anthropic-ratelimit-unified-reset: 1000000500' "$NOW" RATELIMIT)"
eq  "unified reset preferred over earlier tokens reset" "$e" "$((NOW+500))"
# No unified header => take the MAX (latest = conservative), never the first-in-text.
read -r e s <<<"$(rl_extract_reset 'anthropic-ratelimit-requests-reset: 1000000200
anthropic-ratelimit-tokens-reset: 1000000900' "$NOW" RATELIMIT)"
eq  "max reset epoch chosen among non-unified headers" "$e" "$((NOW+900))"
echo "[extract — message fallback + conservative default]"
read -r e s <<<"$(rl_extract_reset 'rate limit, try again in 5 minutes' "$NOW" RATELIMIT)"
eq  "relative message"          "$s" "msg:relative:in 5 minutes"
eq  "relative epoch = now+300"  "$e" "$((NOW+300))"
read -r e s <<<"$(rl_extract_reset 'usage limit reached, no time given' "$NOW" RATELIMIT)"
eq  "usage default 5h src"      "$s" "default-usage-window-5h"
eq  "usage default epoch"       "$e" "$((NOW+5*3600))"
read -r e s <<<"$(rl_extract_reset 'overloaded, no time' "$NOW" OVERLOAD)"
eq  "overload default 2m"       "$s" "default-overload-2m"

echo "[jitter — deterministic, staggered, capped (AC5)]"
RESET=$((NOW+300))
a="$(rl_jittered_resume "$RESET" "$NOW" agent-A 0)"
a2="$(rl_jittered_resume "$RESET" "$NOW" agent-A 0)"
b="$(rl_jittered_resume "$RESET" "$NOW" agent-B 0)"
eq  "same agent => same wake (crash-safe, no double-schedule)" "$a" "$a2"
if [[ "$a" != "$b" ]]; then ok "distinct agents stagger (a=$a b=$b)"; else echo "  FAIL: agents A/B collided at $a"; fails=$((fails+1)); fi
ge  "wake >= reset"             "$a" "$RESET"
le  "wake <= reset+spread(300)" "$a" "$((RESET+300))"
# backoff floor on repeat trips: attempt 3 must wait >= now+120 even if reset is in the past.
w="$(rl_jittered_resume "$((NOW-10))" "$NOW" agent-A 3)"
ge  "attempt=3 backoff floor >= now+120" "$w" "$((NOW+120))"
# cap: a huge attempt is clamped to now+cap(1800)+spread.
w="$(rl_jittered_resume "$((NOW-10))" "$NOW" agent-A 20)"
le  "backoff capped <= now+cap+spread" "$w" "$((NOW+1800+300))"

echo
if [[ $fails -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "$fails FAILURE(S)"; exit 1; fi
