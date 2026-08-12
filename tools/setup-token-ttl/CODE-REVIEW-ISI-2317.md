# Code review — rate-limit auto-resume runtime hook (ISI-2317 → ISI-2296)

**Reviewer:** Amelia (Code Reviewer) · **Date:** 2026-08-12
**Under review:** `ratelimit-lib.sh`, `ratelimit-guard.sh`, `ratelimit-lib.test.sh` @ `dd5855b`, branch `runtime/isi2296-ratelimit-autoresume` (ksquad, local/NAS, no remote).
**Self-check:** `./ratelimit-lib.test.sh` → **ALL PASS (22/22)**, reproduced locally.

## Verdict: APPROVE WITH FINDINGS — no blockers, 2 medium gaps worth fixing before this fronts real traffic.

The spine is sound and the documented AC cases are correct and tested:
- Classifier precedence `529 > 429 > 401 > ERR` holds; the marquee case ("429 body that also
  mentions 401 → RATELIMIT, never AUTHFAIL") passes (`ratelimit-lib.test.sh:19`).
- Header-beats-message reset ladder + always-emits-a-target default: correct (`:47-93`).
- Idempotent single monitor wake with future-wake skip: sound, no busy-poll (`ratelimit-guard.sh:93-101`).
- 401 ⇒ page + `blocked`, never auto-resume: correct (`ratelimit-guard.sh:57-73`).
- Deterministic per-agent jitter + capped exponential backoff: verified crash-safe (same agent ⇒ same wake).

## Findings

### F1 — MEDIUM — multi-`*-reset` header selection is not conservative (NEW code)
`ratelimit-lib.sh:58-59`. The header ladder greps **all** `anthropic-ratelimit-*-reset`
headers and takes `head -1` — i.e. whichever appears *first in the response text*, not the
governing limit. Real 429 responses carry several with **different** reset times
(`requests` / `tokens` / `input-tokens` / `output-tokens` / `unified`). Reproduced: with
`tokens-reset` earlier in the body than `unified-reset`, the guard picks the **earlier**
(`tokens`) reset.
- **Failure:** resume fires before the binding limit clears → the agent relaunches, immediately
  re-trips the shared throttle pool, and only then climbs the backoff floor. That is precisely
  the stampede AC5's jitter exists to prevent — F1 lets it back in through the reset value.
- **Fix:** among matched reset headers, prefer `unified`, else take the **max** epoch (latest
  reset is the conservative choice). One extra `sort -n | tail -1` over the matches, or a
  `unified`-first grep pass.

### F2 — MEDIUM — OK-gate can swallow an error body returned at exit 0 (inherited from probe.sh)
`ratelimit-lib.sh:24`. `rl_classify` returns `OK` when `code==0` **and** the body matches
`"(result|type|role|content)"`. An Anthropic error JSON is `{"type":"error","error":{...}}` —
it matches on `"type"`. Reproduced: both `overloaded_error` and `rate_limit_error` bodies
classify as **OK** when the exit code is 0, short-circuiting before the OVERLOAD/RATELIMIT
branches ever run.
- **Failure:** if `claude -p --output-format json` ever emits an API error object while exiting
  `0` (a contract this hook cannot assume holds — streaming/json modes often exit 0 on a
  well-formed error envelope), the guard no-ops, the agent proceeds as if healthy, no resume is
  scheduled, and it burns straight through the window — defeating AC1/AC2/AC3 for that path.
- **Context:** lifted verbatim from `probe.sh:60`, where a false-OK only means "canary saw a
  healthy token" — low stakes. The runtime hook raises the stakes; the assumption should not
  ride along unexamined.
- **Fix (minimal):** drop `type|content` from the OK marker set — keep `"(result|role)"`.
  Success bodies still match (`result` = final claude -p result, `role` = assistant message);
  an error envelope no longer can. Then OVERLOAD/RATELIMIT/AUTHFAIL classify correctly at exit 0.

### F3 — LOW — bare status-code substrings match inside larger numbers (inherited)
`ratelimit-lib.sh:27,30,33`. `429`/`401`/`529` are matched without delimiters, so `4290`,
`req_401xx`, a line number, or a token count containing those digits will match. On a
non-throttle **nonzero-exit** body that incidentally contains such digits, the guard schedules a
bogus resume (or page) instead of a normal retry. Reproduced: `'build failed at line 4290'`
(code 1) → `RATELIMIT`. Low real-world hit rate; all AC cases pass. Optional hardening: anchor
the codes (`\b429\b`, or require adjacency to `rate`/`http`/`status`). Note only — not for this pass.

## Handoff
F1 + F2 delegated to the ISI-2296 owner (agent 216ef42c) as a child fix issue with both as
blockers. F3 recorded, non-blocking. Review complete; ISI-2317 → done.
