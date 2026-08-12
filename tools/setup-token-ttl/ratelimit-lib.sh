# ratelimit-lib.sh — canonical classify + reset-extraction + resume-jitter for the fleet.
#
# The reusable core behind rate-limit-aware auto-resume (ISI-2296). The classifier and
# the message-text reset ladder are lifted verbatim from the probe.sh seed (ISI-2293);
# this lib ADDS the two things the standalone canary can't do but the runtime can:
#   (a) header-based reset sources (anthropic-ratelimit-*-reset / retry-after), and
#   (b) per-agent jitter so N agents sharing ONE seat's throttle pool don't all relaunch
#       at the exact same instant and immediately re-trip the limit (spike-isi2112:
#       concurrency is throttle-bound, not seat-licensed).
#
# Pure functions, no side effects — source it, call it, unit-test it. Bash 4+.
#
# Contract:
#   rl_classify        "<combined output>" <exit_code>        -> OK|RATELIMIT|OVERLOAD|AUTHFAIL|ERR
#   rl_extract_reset   "<text+headers>" <now_epoch> <status>  -> "<resume_epoch> <source>"
#   rl_jittered_resume <reset_epoch> <now_epoch> <agent_id> <attempt> -> <wake_epoch>

# --- (1) Classify, in priority order. A rate/usage limit is NOT expiry: it must never be
# mistaken for a 401, and it carries a reset time we can resume on. Same order as probe.sh
# (529 > 429 > 401 > ERR) — that ordering is what satisfies AC1/AC4: a 429 body that also
# happens to mention "401"/"unauthorized" still classifies RATELIMIT, never AUTHFAIL.
rl_classify() {
  local out="$1" code="$2"
  # F2: keep ONLY markers an error envelope can't carry. {"type":"error",...} matches on
  # "type"/"content", so those would classify an overloaded_error/rate_limit_error body as OK
  # at exit 0 and short-circuit before OVERLOAD/RATELIMIT. "result"/"role" are success-only.
  if [[ "$code" -eq 0 ]] && printf '%s' "$out" | grep -qiE '"(result|role)"'; then
    echo OK; return
  fi
  if printf '%s' "$out" | grep -qiE '529|overloaded_error|"type"[^}]*overloaded'; then
    echo OVERLOAD; return
  fi
  if printf '%s' "$out" | grep -qiE '429|rate.?limit|rate_limit_error|usage.?limit|quota|too.?many.?requests|limit.*reset|reset.*limit'; then
    echo RATELIMIT; return
  fi
  if printf '%s' "$out" | grep -qiE '401|unauthor|invalid.?(api.?key|token|credential)|authentication_error|oauth.*(expired|revoked)|expired.*token'; then
    echo AUTHFAIL; return
  fi
  if [[ "$code" -ne 0 ]]; then echo ERR; return; fi   # network/other — proves nothing
  echo UNKNOWN
}

# Turn an RFC3339 stamp (or bare epoch) into epoch seconds; empty on failure.
_rl_to_epoch() {
  local v="$1"
  if [[ "$v" =~ ^[0-9]{10}$ ]]; then echo "$v"; return; fi
  date -u -d "$(printf '%s' "$v" | tr 'tT' ' ' | tr -d 'zZ') UTC" +%s 2>/dev/null || true
}

# --- (2) Extract the reset time. Best-first ladder; HEADERS win over message text (AC2).
# Header sources (present when the runtime captured the raw HTTP response):
#   anthropic-ratelimit-*-reset  — RFC3339 or epoch (unified/tokens/requests/...)
#   retry-after                  — integer seconds (delta from now)
# Message-text sources (the only thing `claude -p` surfaces): explicit epoch, RFC3339,
# "retry_after": N, "in N min/hours". Conservative default last so we always emit a target.
rl_extract_reset() {
  local text="$1" now="$2" status="$3"
  local resume="" src="" v

  # -- headers first --
  # F1: a 429 carries several *-reset headers (requests/tokens/input-tokens/output-tokens/
  # unified) at DIFFERENT times. head -1 = first-in-text, which can be an earlier non-binding
  # limit -> resume before the governing limit clears -> re-trip the shared pool. Instead:
  # prefer the `unified` reset, else the MAX epoch among matches (latest = conservative).
  local hdr unified_epoch="" max_epoch="" ep
  while IFS= read -r hdr; do
    [[ -z "$hdr" ]] && continue
    v="$(printf '%s' "$hdr" | grep -oiE '[0-9]{10}|20[0-9]{2}-[0-9]{2}-[0-9]{2}[tT ][0-9:]{5,8}[zZ]?' | head -1 || true)"
    ep="$(_rl_to_epoch "$v")"; [[ -z "$ep" ]] && continue
    printf '%s' "$hdr" | grep -qiE 'unified' && unified_epoch="$ep"
    { [[ -z "$max_epoch" ]] || [[ "$ep" -gt "$max_epoch" ]]; } && max_epoch="$ep"
  done <<<"$(printf '%s' "$text" | grep -oiE 'anthropic-ratelimit-[a-z-]*reset"?[[:space:]:=]+"?[0-9TZ:+-]{10,}' || true)"
  if [[ -n "$unified_epoch" ]]; then resume="$unified_epoch"; src="header:ratelimit-reset"
  elif [[ -n "$max_epoch" ]]; then resume="$max_epoch"; src="header:ratelimit-reset"; fi
  if [[ -z "$resume" ]]; then
    v="$(printf '%s' "$text" | grep -oiE 'retry-after"?[[:space:]:=]+"?[0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
    [[ -n "$v" ]] && { resume=$(( now + v )); src="header:retry-after:${v}s"; }
  fi

  # -- message text (probe.sh seed ladder) --
  if [[ -z "$resume" ]]; then
    v="$(printf '%s' "$text" | grep -oiE '(unified[_-]?reset|resets?[_-]?at|"reset")"?[[:space:]:]*"?[0-9]{10}' | grep -oE '[0-9]{10}' | head -1 || true)"
    [[ -n "$v" ]] && { resume="$v"; src="msg:epoch"; }
  fi
  if [[ -z "$resume" ]]; then
    v="$(printf '%s' "$text" | grep -oiE '20[0-9]{2}-[0-9]{2}-[0-9]{2}[tT ][0-9]{2}:[0-9]{2}:[0-9]{2}[zZ]?' | head -1 || true)"
    [[ -n "$v" ]] && { resume="$(_rl_to_epoch "$v")"; [[ -n "$resume" ]] && src="msg:rfc3339"; }
  fi
  if [[ -z "$resume" ]]; then
    v="$(printf '%s' "$text" | grep -oiE 'retry[_-]?after"?[[:space:]:]*"?[0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
    [[ -n "$v" ]] && { resume=$(( now + v )); src="msg:retry-after:${v}s"; }
  fi
  if [[ -z "$resume" ]]; then
    local rel; rel="$(printf '%s' "$text" | grep -oiE 'in [0-9]+ ?(second|minute|hour)s?' | head -1 || true)"
    if [[ -n "$rel" ]]; then
      local n unit m; n="$(printf '%s' "$rel" | grep -oE '[0-9]+')"; unit="$(printf '%s' "$rel" | grep -oiE '(second|minute|hour)')"
      case "$unit" in second*) m=1;; minute*) m=60;; hour*) m=3600;; *) m=60;; esac
      resume=$(( now + n*m )); src="msg:relative:${rel}"
    fi
  fi

  # -- conservative default: overloads clear fast; subscription usage windows are ~5h --
  if [[ -z "$resume" ]]; then
    if [[ "$status" == "OVERLOAD" ]]; then resume=$(( now + 120 )); src="default-overload-2m"
    else resume=$(( now + 5*3600 )); src="default-usage-window-5h"; fi
  fi
  echo "$resume $src"
}

# --- (3) Jittered resume. Two jobs, both required for a SHARED throttle pool:
#   * exponential backoff floor on repeat trips (attempt 0,1,2... -> 0,30,60,120s min wait,
#     capped) so a resume that immediately re-limits doesn't hot-loop;
#   * DETERMINISTIC per-agent spread (0..RL_SPREAD s, default 300) keyed on agent id, so the
#     N agents that all got 429 at once wake staggered instead of stampeding the reset
#     instant and re-tripping the limit for everyone. Deterministic (no rand) => crash-safe:
#     the same agent re-computes the same wake after a restart, so we never double-schedule.
rl_jittered_resume() {
  local reset="$1" now="$2" agent="$3" attempt="${4:-0}"
  local spread="${RL_SPREAD:-300}" cap="${RL_BACKOFF_CAP:-1800}"
  # deterministic offset in [0,spread) from a hash of the agent id
  local h; h="$(printf '%s' "$agent" | cksum | grep -oE '^[0-9]+')"
  local offset=$(( h % (spread + 1) ))
  # exponential backoff floor: 0,30,60,120,240... capped
  local floor=0
  if [[ "$attempt" -gt 0 ]]; then floor=$(( 30 * (1 << (attempt - 1)) )); [[ "$floor" -gt "$cap" ]] && floor="$cap"; fi
  local wake=$(( reset + offset ))
  local min=$(( now + floor ))
  [[ "$wake" -lt "$min" ]] && wake="$min"
  echo "$wake"
}
