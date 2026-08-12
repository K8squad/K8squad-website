# Rate-limit-aware auto-resume for the agent fleet (ISI-2296)

Wires the probe classifier + monitor-wake scheduler into the fleet runtime so a throttled
agent **backs off to the reset time and is relaunched by a single scheduled heartbeat**,
instead of burning retries or dying through the window. Spun out of ISI-2293; the
architecture policy is arch §8 (ADR-030/031). This is the concrete runtime hook.

## Where it wires in

Call `ratelimit-guard.sh` **once, right after each `claude -p` invocation** in the agent
runtime, passing the invocation's combined output + exit code:

```sh
out="$(claude -p "$prompt" --output-format json 2>&1)"; code=$?
CLAUDE_OUT="$out" CLAUDE_CODE=$code \
  RL_AGENT_ID="$AGENT_ID" RESUME_ISSUE_ID="$ISSUE_ID" RL_ATTEMPT="$attempt" \
  ratelimit-guard.sh
case $? in
  0) : ;;          # proceed / resume scheduled — end this heartbeat, wake fires at reset
  3) exit ;;       # AUTHFAIL — paged for re-issue, do NOT retry
esac
```

The guard never sleeps through the window: on a throttle it persists a resume target and
sets **one** Paperclip monitor wake (`monitorNextCheckAt`), then the heartbeat ends. The
control plane relaunches the agent when the wake fires — zero API calls wasted waiting.

## Files

| File | Role |
|------|------|
| `ratelimit-lib.sh`  | Pure reusable core: `rl_classify`, `rl_extract_reset`, `rl_jittered_resume`. Classifier + message ladder lifted from the `probe.sh` seed; **adds** header sources + jitter. |
| `ratelimit-guard.sh`| Runtime hook: classify → on throttle schedule ONE monitor wake; on 401 page. Idempotent. |
| `ratelimit-lib.test.sh` | Assert-based self-check (22 cases). `./ratelimit-lib.test.sh` → `ALL PASS`. |
| `probe.sh`, `resume-planner.sh` | The ISI-2293 **reference** seed (untouched). |

## Acceptance criteria → implementation

1. **Distinguish 429/529 from 401.** `rl_classify` — precedence `529 > 429 > 401 > ERR`
   (reused from `probe.sh`). A 429 body that also mentions "401" still classifies
   `RATELIMIT`, never `AUTHFAIL` (self-check `429+stray 401 => RATELIMIT`). This ordering is
   the whole point: a usage cap must never be mistaken for auth-death.
2. **Parse reset from headers, fall back to message text, persist a target.**
   `rl_extract_reset` ladder — **headers first** (`anthropic-ratelimit-*-reset` [RFC3339 or
   epoch], `retry-after` [seconds]), then message text (epoch → RFC3339 → `retry_after` →
   "in N min/hours"), then a conservative default (overload 2m / usage window 5h) so a
   target is *always* emitted. Written to `RESUME_AT.txt`.
3. **Exactly one wake at reset — no busy-poll.** Guard sets `monitorNextCheckAt` once and
   returns. Idempotency: it re-reads the issue and **skips** if a future `monitorNextCheckAt`
   already exists, so repeat calls in the same window never stack wakes.
4. **On 401, page — do NOT auto-resume.** `AUTHFAIL` path writes `PAGE_AUTHFAIL.txt`, PATCHes
   the issue to `blocked` with a re-issue note (spike-isi2112 §3 item 3: "page for re-issue,
   no silent death"), and exits `3`. It never schedules a resume — an expired token won't fix
   itself by waiting.
5. **Jittered backoff + cap, safe under N agents sharing one seat's throttle.**
   `rl_jittered_resume`: **deterministic** per-agent spread (`0..RL_SPREAD`, default 300s,
   hashed from the agent id) so the N agents that all got 429 at once wake **staggered**
   instead of stampeding the reset instant and re-tripping the shared limit
   (spike-isi2112: concurrency is *throttle-bound, not seat-licensed*). Plus an exponential
   backoff floor on repeat trips (`RL_ATTEMPT`), capped at `RL_BACKOFF_CAP` (1800s). Being
   deterministic makes it crash-safe: a restarted agent recomputes the same wake and never
   double-schedules.

## Observability

Emits `guard.log` lines (`GUARD`/`RESUME`/`PAGE`) per event. Maps onto the arch §17.2 metric
taxonomy — `ksquad.ratelimit.hits{project,agent,role,provider,model}` and
`ksquad.ratelimit.duration_seconds` (time in `Paused(rate_limited)`). Observability wiring is
delegated (see ISI-2296 subtasks).
