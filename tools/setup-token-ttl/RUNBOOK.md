# Setup-token TTL measurement runbook (ISI-2293)

Goal: replace the **assumed** setup-token TTL that keys the ~75 % rotation alert in
`spike-isi2112` §4 with a **measured** one.

## Automated process (default — Henrik's ask on ISI-2293)
Deploy `canary-cronjob.yaml`: a k8s CronJob probes on a schedule, classifies each probe,
and on the first real 401 computes the observed TTL and **auto-reports it to ISI-2293**
via `report.sh` — no human reads a log or pastes a number. The **only** manual atom is the
one-time `claude setup-token` mint (OAuth browser consent is a deliberate human-in-the-loop
control and is intentionally not automated); the human just drops the token into a Secret:

```bash
claude setup-token                                   # one-time browser consent
kubectl create secret generic setup-token-canary \
  --from-literal=CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-...'
kubectl create configmap setup-token-ttl-scripts --from-file=.   # or bake into the image
kubectl apply -f canary-cronjob.yaml
```

This same canary is the reusable core of the credential-controller's token-health /
rotation alert — the alert should be **canary-driven** off live probes + any declared
expiry, not a fixed 75 %-of-assumption threshold (spike §4 → ADR-032 / Epic 7 Story 7.7).
The steps below are the **manual fallback** when you can't run the CronJob (e.g. measuring
on a laptop seat).

## Key insight — why "probe until 401" alone is a trap
`claude setup-token` mints an **opaque** `sk-ant-oat01-…` bearer whose TTL is widely
reported at **~1 year**. Waiting for a natural 401 is therefore a *months-to-a-year*
canary, not a 15-min task. So we measure in two tiers and take whichever answers first:

- **Tier 0 (instant):** capture any *declared* expiry at mint time. If exposed, that's
  the number — done in minutes.
- **Tier 1 (passive):** a cron canary that catches the real 401 if no declared expiry
  exists. Confirms Tier 0; runs in the background for as long as it takes.

## Steps (human, on a real Pro/Max seat, ~15 min hands-on)

1. **Mint + capture** (one-shot):
   ```bash
   claude setup-token                       # complete browser consent
   export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-...'   # paste the printed token
   export SEAT_LABEL='max-seat-<name>'      # optional, for the record
   ./mint-capture.sh
   ```
   Read the output:
   - **If it prints `DECLARED TTL FOUND`** → report `mint_utc`, `declared_expiry`,
     `source` back on ISI-2293. You are essentially done (still start the canary as
     confirmation, but you don't have to wait).
   - **If `none-found`** → continue to step 2 (expected for opaque tokens).

2. **Schedule the canary** (probe every 6 h; interval = your measurement precision):
   ```bash
   crontab -e
   # 0 */6 * * *  CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-...' OUTDIR="$HOME/.setup-token-ttl" /abs/path/probe.sh
   ```
   Do NOT put the token in git or a world-readable file. A user crontab line or a
   root-owned `/etc/…` env file is fine; it grants full inference on your paid seat.

3. **Wait.** The canary logs one line per probe to `~/.setup-token-ttl/canary.log`.
   On the first auth failure it writes `~/.setup-token-ttl/RESULT.txt` with the observed
   TTL and stops changing. Nothing else to babysit.

4. **Report** the contents of `RESULT.txt` (or the declared expiry from step 1) on
   ISI-2293. The Research Engineer resumes to fold the number into the spike doc and
   re-key the rotation alert.

## What "done" looks like
One of:
- a **declared expiry** captured at mint (best — instant, exact), or
- an **observed 401** with elapsed days (upper bound, precision = probe interval).

Either replaces the assumption. If the number lands near ~1 year, also flag whether the
alert cadence in the spike should be expiry-derived (recommended) rather than a fixed
75 %-of-assumption threshold.

## Rate-limit vs expiry (do not confuse them)
A `429`/usage-cap is **not** token death — mis-reading it as a 401 would fabricate a
short TTL. `probe.sh` classifies every probe in priority order:

| status | trigger | meaning | action |
|---|---|---|---|
| `OK` | exit 0 + JSON | healthy | keep probing |
| `RATELIMIT` | 429 / rate_limit_error / usage limit / quota | throttled, has a **reset time** | back off to reset, then resume |
| `OVERLOAD` | 529 / overloaded_error | transient server load | short backoff |
| `AUTHFAIL` | 401 / expired / revoked / invalid | **this is the TTL signal** | write `RESULT.txt`, stop |
| `ERR` | other nonzero | network/unknown | keep probing, proves nothing |

On `RATELIMIT`/`OVERLOAD` the probe extracts the reset time (epoch → RFC3339 →
`retry-after` → "in N min/hours"; else a conservative default: 5 h for a usage window,
2 min for an overload) and writes `~/.setup-token-ttl/RESUME_AT.txt`:
```json
{"status":"RATELIMIT","resume_utc":"...","resume_epoch":...,"wait_seconds":...,"reset_source":"..."}
```
The seat canary is **self-healing** (its own cron re-probes after the window), so a
rate limit never corrupts the TTL measurement. For the **agent fleet**, feed that file
to `resume-planner.sh`, which schedules exactly one heartbeat at the reset time
(Paperclip monitor wake if `RESUME_ISSUE_ID` is set, else `at(1)`) instead of hammering
the API through the window. Fleet wiring is delegated — see the child issue on ISI-2293.

## Files
- `mint-capture.sh` — Tier 0, run once right after minting.
- `probe.sh` — Tier 1 cron canary; isolated HOME, unsets `ANTHROPIC_API_KEY`, idempotent;
  classifies rate-limit/overload/auth and emits `RESUME_AT.txt`.
- `resume-planner.sh` — fleet side: schedule one resume heartbeat from `RESUME_AT.txt`.
- Output dir: `~/.setup-token-ttl/` (`mint.json`, `canary.log`, `RESULT.txt`, `RESUME_AT.txt`).

## Safety
- Scripts log only a **redacted** token prefix/suffix, never the full token.
- The canary runs in a throwaway `HOME` so it authenticates with the setup-token under
  test and not with any interactive `~/.claude/.credentials.json` login.
- `ANTHROPIC_API_KEY` is blanked during probes so a stray API key can't mask a dead
  OAuth token and give a false OK.
