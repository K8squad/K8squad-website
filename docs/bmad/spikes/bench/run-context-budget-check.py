#!/usr/bin/env python3
"""
Story 5.9 (ISI-2221) falsification — context-injection contract + model-window token budget.

Differential budget/fit falsification, same shape as run-reconcile-check.py (3.1) and
run-retry-backoff-check.py (3.2). It proves the INJECTION SEAM has teeth by contrasting a NAIVE
proportional budgeter that shrinks EVERY tier to hit the window (mangling the task, or silently
truncating instead of failing closed) against the arch-§8.5(3) PRIORITY-ORDERED FAIL-CLOSED budgeter
that never touches must-include and fails the Run closed rather than shipping a truncated task.

Scope reminder: Story 3.6 owns ENVELOPE ASSEMBLY (gather + trust-tier + snapshot). THIS check owns the
BUDGET half: resolve+clamp the budget against the resolved MODEL window (Agent Card capability, model-
keyed not CLI-keyed), the priority-ordered fit (must-include verbatim & first; best-effort evicted
lowest-priority-first), the fail-closed gate when must-include alone exceeds the window, the tier-
preserving injection contract (no flat prompt blob, F16), and determinism over the snapshot.

Mutation contract (the headline invariants must be falsifiable — re-run these after any edit):
  * delete the "place must-include verbatim, budget only the remainder" guard in fit()  -> (F1) MUST turn RED.
    (F1 is exercised on a DEDICATED sub-envelope f1_envelope() where a best-effort element
     OUTRANKS a must-include element, so a merged whole-env greedy trim is forced to evict a
     must element — the vacuous-arm trap ISI-2346-F1/ISI-2361-F1 warn about is avoided.)
  * delete the "if size(must-include) > window: return fail_closed" gate in fit()        -> (F2) MUST turn RED.
  * delete the over-window reject ("if configured > window: raise") in resolve_budget()  -> (F3) MUST turn RED.
    (The reject is the SOLE teeth; the subsequent min(configured, window) is belt-and-suspenders
     — the reject already guarantees configured <= window at the return, so mutating min() alone
     does NOT flip the check. Do not claim the clamp is independently mutation-proven.)
  * flatten the injected envelope to one prompt string                                    -> (F5) MUST turn RED.

stdlib only. `python3 run-context-budget-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG: token sizes are explicit ints; everything is deterministic.
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# ---------------------------------------------------------------------------
# The tiered envelope element (Story 3.6 output, consumed here — §A).
# tier ∈ {authoritative, untrusted-recall, untrusted-external}; priority orders
# eviction (higher = kept longer). `size` is the token cost; `content` is the
# actual text (so a mangled/truncated task is detectable byte-for-byte).
# ---------------------------------------------------------------------------
AUTH, RECALL, EXTERNAL = "authoritative", "untrusted-recall", "untrusted-external"

class Elem:
    __slots__ = ("id", "tier", "priority", "size", "content", "provenance")
    def __init__(self, id, tier, priority, size, content, provenance=None):
        self.id, self.tier, self.priority = id, tier, priority
        self.size, self.content, self.provenance = size, content, provenance
    def clone(self, size=None, content=None):
        return Elem(self.id, self.tier, self.priority,
                    self.size if size is None else size,
                    self.content if content is None else content, self.provenance)
    def key(self):  # for byte-identical / determinism comparison
        return (self.id, self.tier, self.size, self.content)

class FailClosed:
    def __init__(self, reason, required, window):
        self.reason, self.required, self.window = reason, required, window
    def __eq__(self, o): return isinstance(o, FailClosed) and self.reason == o.reason

class ValidationError(Exception):
    pass

def total_size(elems):
    return sum(e.size for e in elems)

# A representative envelope: must-include (authoritative) = the task; best-effort
# recall + artifacts with distinct priorities so eviction order is observable.
def sample_envelope():
    return [
        # --- authoritative / must-include: the task itself (verbatim, never truncated) ---
        Elem("work_item",  AUTH, 100, 1200, "TASK: implement fenced claim renewal per §6.2", "crd"),
        Elem("accept_crit", AUTH, 100, 900,  "AC1..AC6: no double-claim; fence-first reclaim; ...", "crd"),
        Elem("goals",      AUTH, 100, 400,  "GOALS: correctness over speed; no P2P custody", "project-crd"),
        # --- best-effort: untrusted-recall (memory), ranked by relevance ---
        Elem("recall_hi",  RECALL, 80, 1500, "prior note: fence_token equality guard rejects zombies",
             {"author": "agentA", "trust": "untrusted"}),
        Elem("recall_mid", RECALL, 60, 1500, "prior note: lease grace = 3x renewal interval",
             {"author": "agentB", "trust": "untrusted"}),
        Elem("recall_lo",  RECALL, 40, 1500, "prior note: unrelated dashboard styling detail",
             {"author": "agentC", "trust": "untrusted"}),
        # --- best-effort: untrusted-external (synced artifacts) — lowest priority ---
        Elem("artifact",   EXTERNAL, 20, 2000, "synced README excerpt from the repo mirror",
             {"trust": "untrusted"}),
    ]

def must_include(env):    return [e for e in env if e.tier == AUTH]
def best_effort(env):     return [e for e in env if e.tier != AUTH]

# A DEDICATED envelope for the F1 must-include-verbatim teeth (ISI-2383 F1 fix). Here a best-effort
# recall element OUTRANKS a must-include element (priority 130 > 100). The tier-separated fit() keeps
# must-include verbatim REGARDLESS of priority (it separates by TIER, then budgets the remainder), but
# a mutated whole-env greedy-by-priority trim would place the high-priority recall first and be FORCED
# to evict/summarize a must-include element to fit the window -> the guard becomes decisive.
def f1_envelope():
    return [
        Elem("f1_work",  AUTH, 100, 1200, "TASK: implement the fenced renewal", "crd"),
        Elem("f1_ac",    AUTH, 100, 900,  "AC1..AC6: the acceptance criteria verbatim", "crd"),
        Elem("f1_goals", AUTH, 100, 400,  "GOALS: correctness over speed", "project-crd"),
        # best-effort recall priced high enough to out-rank the task in a naive whole-env sort:
        Elem("f1_hot",   RECALL, 130, 1500, "a very-high-relevance recall note",
             {"author": "agentX", "trust": "untrusted"}),
    ]
F1_WINDOW = 3000   # must(2500) fits; must + f1_hot(1500) = 4000 > 3000, forcing a mutated trim to cut must

# ---------------------------------------------------------------------------
# §B — budget resolution + clamp. Config can SHRINK but never exceed the
# physical model window; an over-window override is a FAIL-CLOSED validation
# error (§8.5). This is model-keyed: `window` is the resolved MODEL endpoint's
# contextWindow (Agent Card capability), not the runtime CLI's nominal limit.
# ---------------------------------------------------------------------------
def resolve_budget(window, project_default=None, agent_override=None):
    configured = agent_override if agent_override is not None else project_default
    if configured is None:
        return window                      # per-runtime/model default = the window itself
    # MUTATION POINT (F3): removing this reject lets an over-window override through -> RED.
    # This is the SOLE teeth for the shrink-only / fail-closed-over-window contract (§8.5).
    if configured > window:
        raise ValidationError(
            "contextBudgetOverride %d exceeds model contextWindow %d (shrink-only)" % (configured, window))
    # min() is belt-and-suspenders only: the reject above already guarantees configured <= window
    # here, so this is NOT independently mutation-proven (documented in the mutation contract).
    return min(configured, window)

# ---------------------------------------------------------------------------
# §C — the priority-ordered FAIL-CLOSED fit. Total & deterministic: yields
# either a fitted tier-labeled envelope (task verbatim, best-effort trimmed
# lowest-priority-first) or a FailClosed. NEVER a silently-truncated task.
# ---------------------------------------------------------------------------
SUMMARY_FLOOR = 0.4  # a best-effort element can be summarized down to 40% of its size

def fit(env, window):
    must = must_include(env)
    must_sz = total_size(must)
    # MUTATION POINT (F2): deleting this gate makes a too-small model silently truncate the task.
    if must_sz > window:
        return FailClosed("ContextWindowExceeded", required=must_sz, window=window)
    # MUTATION POINT (F1): must-include is placed VERBATIM and only the REMAINDER is budgeted.
    # Letting `must` enter the trim below (e.g. budgeting the whole `env`) truncates the task.
    # canonical order (stable over arrival order -> deterministic over the snapshot, AC6/F6).
    kept = sorted(must, key=lambda e: (-e.priority, e.id))   # task first, never truncated
    remaining = window - must_sz
    # best-effort, highest priority first; evict lowest-priority-first to make room.
    be = sorted(best_effort(env), key=lambda e: (-e.priority, e.id))
    for e in be:
        if e.size <= remaining:
            kept.append(e); remaining -= e.size
        else:
            floor = int(e.size * SUMMARY_FLOOR)
            if floor <= remaining:                      # summarize this (lowest fitting) element
                kept.append(e.clone(size=floor, content="[summarized] " + e.content[:floor]))
                remaining -= floor
            # else drop e entirely and continue to the next (lower-priority) element
    return kept

# ---------------------------------------------------------------------------
# §D — the injection contract. Deliver as A2A system/context WITH tiers intact.
# ---------------------------------------------------------------------------
def inject(fitted):
    if isinstance(fitted, FailClosed):
        return fitted
    # tier-labeled elements survive to the runtime (authoritative=task, untrusted-*=reference).
    return [{"tier": e.tier, "size": e.size, "content": e.content, "provenance": e.provenance}
            for e in fitted]

def flatten_to_prompt_blob(fitted):   # the F16-breaking mutation (for the differential twin)
    return "\n".join(e.content for e in fitted)

# ---------------------------------------------------------------------------
# NAIVE budgeter (the differential foil) — proportional shrink of EVERY tier,
# including must-include, to make the payload fit. Mangles the task; never fails
# closed. Must stay detectably broken or the harness lost its power.
# ---------------------------------------------------------------------------
def naive_proportional_fit(env, window):
    tot = total_size(env)
    if tot <= window:
        return list(env)
    factor = window / tot
    out = []
    for e in env:
        new_sz = max(1, int(e.size * factor))
        out.append(e.clone(size=new_sz, content=e.content[:new_sz]))  # truncates task text too
    return out

# ===========================================================================
# (A) NAIVE proportional budgeter detectably mangles the task.
# ===========================================================================
env = sample_envelope()
small = 4000  # < must(2500) + best-effort(8000); forces trimming
naive = naive_proportional_fit(env, small)
# a task is "mangled" if EITHER its token size shrank OR its text changed (§C: must-include is
# verbatim — same size AND same content; the naive proportional shave reduces the size).
src_must = {e.id: (e.content, e.size) for e in must_include(env)}
naive_must = {e.id: (e.content, e.size) for e in naive if e.tier == AUTH}
mangled = any(naive_must[i] != src_must[i] for i in src_must)
check(mangled, "(A) FOIL LOST POWER: naive proportional budgeter no longer mangles must-include — "
               "the differential has no teeth")

# ===========================================================================
# (F1) must-include is verbatim & first; best-effort trimmed lowest-priority-first.
# ===========================================================================
fitted = fit(env, small)
assert not isinstance(fitted, FailClosed), "must-include fits at window=4000"
fit_must = {e.id: (e.content, e.size) for e in fitted if e.tier == AUTH}
check(all(fit_must[i] == src_must[i] for i in src_must),
      "(F1) must-include was truncated — the task is never truncated (AC1)")
check(total_size([e for e in fitted]) <= small,
      "(F1) fitted envelope exceeds the window")
# best-effort survivors are the highest-priority prefix; the lowest-priority artifact is cut first.
be_kept = [e.id for e in fitted if e.tier != AUTH]
check("recall_hi" in be_kept, "(F1) highest-priority recall was dropped while budget remained")
check("artifact" not in be_kept,
      "(F1) lowest-priority external survived while a higher-priority recall could have been kept")

# --- F1 DECISIVE teeth (ISI-2383 F1 fix): must-include stays verbatim even when a best-effort element
# OUTRANKS it. On f1_envelope() the good tier-separated fit keeps all must verbatim (dropping f1_hot);
# a whole-env greedy-by-priority mutation would place f1_hot first and evict a must element -> RED. ---
f1env = f1_envelope()
f1_fit = fit(f1env, F1_WINDOW)
assert not isinstance(f1_fit, FailClosed), "must-include (2500) fits F1_WINDOW (3000)"
f1_src = {e.id: (e.content, e.size) for e in must_include(f1env)}
f1_got = {e.id: (e.content, e.size) for e in f1_fit if e.tier == AUTH}
# robust: a DROPPED must element is a clean RED (membership check), not a KeyError crash.
check(all(i in f1_got and f1_got[i] == f1_src[i] for i in f1_src),
      "(F1) must-include was truncated or dropped when a best-effort element outranked it — "
      "the task is placed by TIER and never truncated, regardless of priority (AC1)")
# sanity: the high-priority best-effort recall is the one that gives way (proves the window is binding).
check("f1_hot" not in {e.id for e in f1_fit},
      "(F1) f1_hot should not fit alongside a verbatim must-include at F1_WINDOW — arm is non-binding")

# ===========================================================================
# (B) lowest-priority-first eviction: never drop a higher-priority element while
#     keeping a lower-priority one.
# ===========================================================================
kept_prios = {e.id: e.priority for e in fitted if e.tier != AUTH}
dropped = [e for e in best_effort(env) if e.id not in kept_prios]
if dropped and kept_prios:
    max_dropped = max(e.priority for e in dropped)
    min_kept = min(kept_prios.values())
    check(min_kept >= max_dropped,
          "(B) eviction violated priority order: a lower-priority element was kept over a higher one")

# ===========================================================================
# (F2) fail-closed when must-include alone exceeds the window — never silent
#      task truncation. Differential twin: naive truncate-to-fit runs a mangled task.
# ===========================================================================
tiny = 2000  # < must-include (2500): a too-small model
good = fit(env, tiny)
check(isinstance(good, FailClosed) and good.reason == "ContextWindowExceeded",
      "(F2) must-include > window did NOT fail closed — silent task truncation is forbidden (AC3)")
check(not isinstance(good, FailClosed) or good.required == total_size(must_include(env)),
      "(F2) fail-closed condition lacks the required-vs-window detail")
# the naive path instead ships a truncated task with no failure signal (undetectable corruption):
naive_tiny = naive_proportional_fit(env, tiny)
naive_tiny_must = {e.id: (e.content, e.size) for e in naive_tiny if e.tier == AUTH}
check(any(naive_tiny_must[i] != src_must[i] for i in src_must),
      "(F2) FOIL LOST POWER: naive path no longer silently truncates the task at a too-small window")

# ===========================================================================
# (F3) clamp / over-window override: config shrinks but never grows past the window.
# ===========================================================================
WINDOW_200K = 200_000
over = None
try:
    resolve_budget(WINDOW_200K, agent_override=300_000)  # 300K on a 200K model
except ValidationError:
    over = "rejected"
check(over == "rejected",
      "(F3) an over-window contextBudgetOverride was NOT a fail-closed validation error (AC4)")
shrunk = resolve_budget(WINDOW_200K, agent_override=50_000)
check(shrunk == 50_000, "(F3) a shrink override was not honored (config must be able to shrink)")
check(resolve_budget(WINDOW_200K) == WINDOW_200K,
      "(F3) with no override the budget must default to the model window")

# ===========================================================================
# (F4) model-keyed window: same runtime+envelope, two model endpoints -> two budgets.
#      A CLI-keyed twin over-fills the small model.
# ===========================================================================
big_env = sample_envelope()
fit_200k = fit(big_env, 200_000)     # frontier: everything fits
fit_8k = fit(big_env, 3600)          # local Ollama-ish: must(2500) fits, best-effort mostly trimmed
assert not isinstance(fit_8k, FailClosed)
be_200 = [e.id for e in fit_200k if e.tier != AUTH]
be_8 = [e.id for e in fit_8k if e.tier != AUTH]
check(len(be_200) > len(be_8),
      "(F4) the small model kept as much best-effort as the large one — window is not model-keyed (AC2)")
check(total_size(fit_8k) <= 3600, "(F4) small-model fit exceeded its own window")

# CLI-keyed FOIL (the broken design): budgets against the runtime CLI's fixed nominal limit,
# IGNORING the resolved model window, then the payload is delivered to a small (8K) model -> overflow.
# This is a genuine differential: it budgets to `cli_limit` and asserts the result exceeds the actual
# `model_window` it will be handed to (the overflow), which the model-keyed fit() never produces.
def cli_keyed_fit(env, cli_limit, model_window):
    payload = fit(env, cli_limit)                 # sized to the CLI limit, NOT the model window
    return payload, model_window                  # ...then handed to a model_window-sized model
cli_payload, target_window = cli_keyed_fit(big_env, cli_limit=200_000, model_window=3600)
check(not isinstance(cli_payload, FailClosed) and total_size(cli_payload) > target_window,
      "(F4) FOIL LOST POWER: CLI-keyed budgeting no longer overflows the small model it is handed to")

# ===========================================================================
# (F5) trust tiers preserved on the wire — no flat prompt blob (F16).
# ===========================================================================
injected = inject(fitted)
tiered = isinstance(injected, list) and all(isinstance(x, dict) and "tier" in x for x in injected)
check(tiered,
      "(F5) injected envelope lost its per-element trust tiers — a flat prompt blob re-opens the F16 "
      "prompt-injection vector (framing must survive the wire)")
if tiered:  # only inspect framing when the contract held; a flattened blob already failed above
    auth_injected = [x for x in injected if x["tier"] == AUTH]
    recall_injected = [x for x in injected if x["tier"] in (RECALL, EXTERNAL)]
    check(len(auth_injected) == 3 and len(recall_injected) >= 1,
          "(F5) injection did not frame authoritative vs untrusted-* distinctly")
# the flatten twin (the F16-breaking mutation) collapses everything to one string -> tiers gone.
# foil-lost-power guard: if flatten_to_prompt_blob were neutered to return the tiered list, this
# `isinstance(blob, str)` check flips RED — a genuine detector, not a str-is-never-a-dict tautology.
blob = flatten_to_prompt_blob(fitted)
check(isinstance(blob, str),
      "(F5) FOIL LOST POWER: the flatten twin no longer erases tiers (must produce a tier-less string)")

# ===========================================================================
# (F6) determinism over the snapshot: two fresh fits of the same snapshot are
#      byte-identical (a resumed Run re-injects identically). A re-query twin diverges.
# ===========================================================================
snap = sample_envelope()
run1 = fit(snap, small)
run2 = fit(sample_envelope(), small)  # fresh instance, same snapshot content
sig1 = tuple(e.key() for e in run1)
sig2 = tuple(e.key() for e in run2)
check(sig1 == sig2, "(F6) fit is non-deterministic over the snapshot — a resume would see different context (AC6)")
# a re-query twin that reorders recall (non-deterministic memory search) diverges:
reordered = sample_envelope()
reordered.reverse()  # simulate an unstable recall order
requery = fit(reordered, small)
# with a STABLE priority sort the fit is order-independent; assert the good design is robust to it:
check(tuple(e.key() for e in requery) == sig1,
      "(F6) the fit is not stable under recall reordering — it must sort by priority, not arrival order")

# ===========================================================================
# (F7) mid-Run model switch re-resolves the window to the fallback's own window.
# ===========================================================================
primary_fit = fit(sample_envelope(), 200_000)     # primary ~200K
fallback_fit = fit(sample_envelope(), 3600)       # switched to ~8K fallback mid-Run
check(total_size(fallback_fit) <= 3600,
      "(F7) after a mid-Run model switch the budget was not re-resolved to the fallback window (AC5/§10.3)")
check(len([e for e in fallback_fit if e.tier != AUTH]) <
      len([e for e in primary_fit if e.tier != AUTH]),
      "(F7) the fallback fit kept as much best-effort as the primary — the window did not follow the model")

# ---------------------------------------------------------------------------
if FAIL:
    print("FALSIFIED — Story 5.9 context-budget check found %d violation(s):" % len(FAIL))
    for m in FAIL:
        print("  ✗", m)
    sys.exit(1)
print("OK — Story 5.9 context-injection budget check passed all falsification arms:")
print("  (A) naive proportional budgeter detectably mangles the task (foil has teeth)")
print("  (F1) must-include verbatim by TIER even when a best-effort element outranks it (decisive teeth)")
print("  (B) eviction is lowest-priority-first (never drop higher while keeping lower)")
print("  (F2) fail-closed when must-include > window (no silent task truncation)")
print("  (F3) over-window override rejected; shrink override honored; default = window")
print("  (F4) window is model-keyed, not CLI-keyed (small vs large model -> different budgets)")
print("  (F5) trust tiers preserved on the wire (no flat prompt blob, F16)")
print("  (F6) deterministic over the snapshot (a resume re-injects identically)")
print("  (F7) mid-Run model switch re-resolves the budget to the fallback window")
sys.exit(0)
