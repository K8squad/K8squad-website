#!/usr/bin/env python3
"""agent-card-check.py — Story 5.2 falsification (Agent Card generated from the Agent CRD).

The §10.1 / FR-D4 / R3 / F15 load-bearing invariant: the Agent Card is the moat seam's
HONESTY contract. Runtime capability gaps (streaming / tool-calls / interactive /
byoModelEndpoint) are advertised as FIRST-CLASS `false` flags the core reads BEFORE it
dispatches — never omitted, never discovered as a mid-Run failure. Three cruxes make the
seam honest rather than leaky:

  1. NO-OMISSION (AC2, FR-D4/R3/F15). A gap is an explicit `false` flag, not an absent key.
     A naive card that omits unsupported capabilities lets the core read "absent → assume
     capable", dispatch an interactive task to a non-interactive runtime, and hit the gap as
     a mid-Run RuntimeFailure — the exact "leaky abstraction" R3 names. The honest card sets
     the flag `false`; the core routes around it pre-dispatch.
  2. NO-ESCALATION (AC3, §5.3.6 trust boundary on the card). `Agent.capabilityOverrides`
     INTERSECT the resolved AgentRuntime's real capability ceiling — an override can CLEAR a
     bit (operator narrows: "don't let this agent use docker") but can NEVER SET a bit the
     runtime lacks (forge `interactive:true` on a runtime that cannot). A forged flag is a
     dishonest card = the same self-declared-capability escalation §5.3.6 forbids for skills.
  3. NO-SECRET-MATERIAL (AC4, FR-G2/§11, §10.1 "the shim never logs credential material").
     The card carries credential *capability metadata* — {credentialType, credentialLifecycle}
     from the §11 story — NEVER the resolved Secret's bytes. The card flows south over A2A;
     embedding token material leaks it.

Differential falsification (same discipline as handoff-advisory-check.py / run-retry-backoff-check.py):
  (A) NAIVE omit-gaps card → the core's route decision reads an absent flag as capable →
      dispatches → mid-Run RuntimeFailure. MUST break (teeth), else the harness proves nothing.
  (B) §10.1 HONEST card → gaps are explicit `false` → the core routes around them pre-dispatch;
      no runtime is ever asked to do what it advertised it cannot.
  (F2) override NO-ESCALATION teeth (AC3): naive "override wins" forges interactive:true on a
      non-interactive runtime → dishonest card → dispatch → failure; honest intersect (AND)
      lets an override clear docker but never forge interactive. Mutation-proven.
  (F3) credential NO-MATERIAL teeth (AC4): the naive card embeds the resolved secret bytes →
      the token string appears in the serialized card (leak); the honest card carries only
      type+lifecycle. Mutation-proven.
  (C) skills from CRD refs (AC1): skills = sorted(union(Agent.skillRefs, Role.defaultSkills))
      resolved to the Skill CRDs' operator-authorized envelope — a runtime-self-declared skill
      never reaches the card; two generations are byte-identical.
  (D) credential-metadata mapping fidelity (AC4): the three §11 stories map to the right
      {type, lifecycle}; an unknown credential shape FAILS CLOSED (no blank credential block).
  (E) deterministic byte-stable card (AC5): canonical JSON — same resolved CRDs → same bytes
      (the CRD→card mapping conformance §10.1 pins). And byoModelEndpoint follows the honesty
      rule: modelEndpointRef on a runtime lacking the capability fails closed, never forges it.

stdlib-only; `python3 agent-card-check.py`. Exit non-zero if a gap is ever omitted, an override
forges a capability the runtime lacks, secret material reaches the card, a self-declared skill
lands on the card, the card is non-deterministic, or an unknown credential emits a blank block.
Models the Agent-reconciler CRD→card generation (§5.1 "publishes Agent Card") in-process;
real-runtime promotion rides the ISI-2114 conformance suite (§10.1, Story 5.6).
"""
import json


# The known capability keys — every one is a FIRST-CLASS flag on every card (AC2). The point of
# the honesty contract is that this set is FIXED: a runtime declares a value for each, never a
# subset. streaming/tool_calls/interactive are FR-D4's named three; byo_model_endpoint is §10.3;
# docker/github/package_install ride the resolved AgentRuntime.capabilities (§5.3).
CAP_KEYS = (
    "streaming", "tool_calls", "interactive", "byo_model_endpoint",
    "docker", "github", "package_install",
)

# The three §11 credential stories → their capability metadata (type + lifecycle). This is the
# ONLY credential info the card carries (AC4). Material never appears here.
CREDENTIAL_META = {
    "claude-oauth":  {"credentialType": "oauth",       "credentialLifecycle": "zero-touch-refresh"},
    "api-key":       {"credentialType": "api-key",     "credentialLifecycle": "static"},
    "byo-endpoint":  {"credentialType": "byo-endpoint", "credentialLifecycle": "static"},
}


class RuntimeFailure(Exception):
    """A capability gap discovered at dispatch time — the R3 leak the card exists to prevent."""


# ---- the resolved inputs (CRDs the Agent reconciler reads, §5.1) ----

class AgentRuntime:
    """The resolved runtime — its `capabilities` are the HONEST ceiling (§5.3/§10.1)."""

    def __init__(self, rtype, capabilities):
        self.type = rtype
        # every CAP_KEY present here is the runtime's real ability; absent → False (cannot).
        self.capabilities = {k: bool(capabilities.get(k, False)) for k in CAP_KEYS}


class Skill:
    def __init__(self, name, mcp_tool_refs, permissions):
        self.name = name
        self.mcpToolRefs = list(mcp_tool_refs)
        self.permissions = list(permissions)


class Role:
    def __init__(self, default_skills):
        self.defaultSkills = list(default_skills)  # skill names


class Agent:
    def __init__(self, runtime_ref, role_ref, skill_refs, credential_secret_ref,
                 model, capability_overrides=None, model_endpoint_ref=None):
        self.runtimeRef = runtime_ref
        self.roleRef = role_ref
        self.skillRefs = list(skill_refs)                 # skill names
        self.credentialSecretRef = credential_secret_ref  # Secret name
        self.model = model
        self.capabilityOverrides = dict(capability_overrides or {})  # partial {cap: bool}
        self.modelEndpointRef = model_endpoint_ref        # §10.3 BYO endpoint Secret, or None


# ---- the credential store (per-user Secret rows, §11) — MATERIAL never leaves it ----

class SecretStore:
    def __init__(self):
        # secret name → (credential kind key into CREDENTIAL_META, the actual token MATERIAL)
        self._rows = {}

    def put(self, name, kind, material):
        self._rows[name] = {"kind": kind, "material": material}
        return self

    def kind_of(self, name):
        return self._rows[name]["kind"] if name in self._rows else None

    def material_of(self, name):
        return self._rows[name]["material"] if name in self._rows else None


# ---- the Agent reconciler's CRD → Agent Card generation (§5.1 "publishes Agent Card") ----

def generate_card(agent, runtime, role, skills_by_name, secrets, *,
                  omit_gaps=False, override_wins=False, leak_secret=False):
    """Deterministically project the resolved CRDs into an Agent Card.

    Default (all flags False) is the §10.1 HONEST generator. The three toggles simulate the
    exact mutations the falsification arms prove fatal — each corresponds to deleting one
    load-bearing line:
      omit_gaps=True     → drops the "fill every CAP_KEY with an explicit bool" step (AC2 teeth).
      override_wins=True → replaces the intersect (AND) with "override wins" (AC3 teeth).
      leak_secret=True   → embeds the resolved Secret material on the card (AC4 teeth).
    """
    # --- capabilities: the honesty crux (AC2 no-omission + AC3 no-escalation) ---
    capabilities = {}
    for k in CAP_KEYS:
        runtime_cap = runtime.capabilities[k]              # the HONEST ceiling (§5.3/§10.1)
        override = agent.capabilityOverrides.get(k)        # None | True | False
        if override_wins:
            # WRONG (AC3): an override forges a capability the runtime lacks — a dishonest card.
            card_cap = override if override is not None else runtime_cap
        else:
            # §5.3.6 on the card: override INTERSECTS the ceiling — can clear, never forge.
            card_cap = runtime_cap and (override if override is not None else True)
        if omit_gaps and not card_cap:
            # WRONG (AC2): omit the gap → the core reads "absent → assume capable" downstream.
            continue
        capabilities[k] = card_cap
    # LOAD-BEARING (AC2): every known key carries an explicit bool. Deleting this defaulting IS
    # the omit_gaps mutation. (When omit_gaps=True the loop above already skipped the False ones.)
    if not omit_gaps:
        for k in CAP_KEYS:
            capabilities.setdefault(k, False)

    # byoModelEndpoint honesty (AC5 / §10.3): an Agent that sets modelEndpointRef on a runtime
    # WITHOUT the byo_model_endpoint capability must FAIL CLOSED — the card never forges it.
    if agent.modelEndpointRef is not None and not runtime.capabilities["byo_model_endpoint"]:
        raise ValueError(
            "modelEndpointRef set but resolved runtime lacks byo_model_endpoint — fail closed, "
            "never advertise a capability the runtime cannot honor (AC5/§10.3)")

    # --- skills: resolved from CRD refs ONLY (AC1, operator-authorized §5.3.6) ---
    # union of the Agent's skillRefs and the Role's defaultSkills, resolved to the Skill CRDs'
    # declared envelope. A runtime cannot self-declare a skill: nothing here reads the runtime.
    skill_names = sorted(set(agent.skillRefs) | set(role.defaultSkills))  # canonical order
    card_skills = []
    for name in skill_names:
        sk = skills_by_name[name]  # KeyError = an unresolved ref → the reconciler would reject
        card_skills.append({
            "name": sk.name,
            "mcpToolRefs": sorted(sk.mcpToolRefs),
            "permissions": sorted(sk.permissions),
        })

    # --- credential capability metadata (AC4, FR-G2/§11) — type + lifecycle, NEVER material ---
    kind = secrets.kind_of(agent.credentialSecretRef)
    meta = CREDENTIAL_META.get(kind)
    if meta is None:
        # fail closed: an unknown credential shape does NOT emit a blank/optimistic block.
        raise ValueError(f"unknown credential kind {kind!r} — fail closed (AC4)")
    credential = dict(meta)
    if leak_secret:
        # WRONG (AC4): resolve and embed the token bytes — leaks credential material south.
        credential["material"] = secrets.material_of(agent.credentialSecretRef)

    card = {
        "runtimeType": runtime.type,
        "model": agent.model,
        "capabilities": capabilities,
        "skills": card_skills,
        "credential": credential,
    }
    return card


def serialize(card):
    """The wire form the conformance suite pins (§10.1) — canonical, byte-stable."""
    return json.dumps(card, sort_keys=True, separators=(",", ":"))


# ---- the CORE's consumers — what gives the honesty arms real teeth ----

def core_can_dispatch(card, task_needs):
    """The core's route decision (§10.1 'the core routes around' a declared gap). It reads the
    capability FLAGS. An ABSENT flag is read as capable — the naive optimism a first-class
    `false` exists to prevent. So an omitted gap makes the core say 'yes' and then fail."""
    caps = card["capabilities"]
    return all(caps.get(cap, True) for cap in task_needs)  # absent → True (the hazard)


def dispatch_and_run(runtime, task_needs):
    """Actually invoke the runtime. If the card lied (advertised a capability the runtime lacks),
    the gap surfaces HERE as a mid-Run RuntimeFailure — the R3 leak."""
    for cap in task_needs:
        if not runtime.capabilities[cap]:
            raise RuntimeFailure(f"runtime {runtime.type} cannot {cap}")
    return "ok"


# ---- fixtures ----

def _skills():
    return {
        "git":   Skill("git",   ["mcp:git"],   ["repo:rw"]),
        "web":   Skill("web",   ["mcp:fetch"], ["net:egress"]),
        "shell": Skill("shell", ["mcp:exec"],  ["exec"]),
    }


def _weak_runtime():
    """A limited runtime: streams + tool-calls, but NO interactive-prompt, NO byo endpoint."""
    return AgentRuntime("hermes-lite", {
        "streaming": True, "tool_calls": True, "interactive": False,
        "byo_model_endpoint": False, "docker": True, "github": True, "package_install": False,
    })


def _full_runtime():
    return AgentRuntime("openclaw", {
        "streaming": True, "tool_calls": True, "interactive": True,
        "byo_model_endpoint": True, "docker": True, "github": True, "package_install": True,
    })


# ---- scenarios ----

def run_naive_omit_gaps():
    """(A) NAIVE: the card OMITS the interactive gap. The core reads absent→capable, dispatches an
    interactive task to a runtime that cannot → mid-Run RuntimeFailure. MUST break (teeth)."""
    rt = _weak_runtime()
    role = Role(default_skills=["git"])
    agent = Agent("hermes-lite", "coder", ["web"], "sec-key", "gpt-x")
    secrets = SecretStore().put("sec-key", "api-key", "sk-DEADBEEF-secret")
    card = generate_card(agent, rt, role, _skills(), secrets, omit_gaps=True)
    task_needs = ["interactive"]                       # a task requiring interactive prompts
    interactive_on_card = "interactive" in card["capabilities"]
    core_said_yes = core_can_dispatch(card, task_needs)
    failed_mid_run = False
    try:
        if core_said_yes:
            dispatch_and_run(rt, task_needs)
    except RuntimeFailure:
        failed_mid_run = True
    return {"interactive_key_present": interactive_on_card,
            "core_dispatched": core_said_yes, "failed_mid_run": failed_mid_run}


def run_honest_card():
    """(B) §10.1 HONEST: the interactive gap is an explicit `false`. The core routes around it
    BEFORE dispatch — the runtime is never asked to do what it advertised it cannot."""
    rt = _weak_runtime()
    role = Role(default_skills=["git"])
    agent = Agent("hermes-lite", "coder", ["web"], "sec-key", "gpt-x")
    secrets = SecretStore().put("sec-key", "api-key", "sk-DEADBEEF-secret")
    card = generate_card(agent, rt, role, _skills(), secrets)
    task_needs = ["interactive"]
    core_said_yes = core_can_dispatch(card, task_needs)
    dispatched = False
    if core_said_yes:
        dispatch_and_run(rt, task_needs)
        dispatched = True
    # and a task the runtime CAN do (streaming+tool_calls) still routes + runs fine.
    ok_needs = ["streaming", "tool_calls"]
    ok_dispatched = core_can_dispatch(card, ok_needs) and dispatch_and_run(rt, ok_needs) == "ok"
    return {"interactive_flag": card["capabilities"]["interactive"],
            "core_routed_around": core_said_yes is False, "dispatched_bad_task": dispatched,
            "capable_task_ran": ok_dispatched,
            "all_keys_present": set(card["capabilities"].keys()) == set(CAP_KEYS)}


def run_override_escalation():
    """(F2) AC3: capabilityOverrides intersect the runtime ceiling. An override CANNOT forge a
    capability the runtime lacks; it CAN clear one the runtime has."""
    rt = _weak_runtime()  # interactive=False, docker=True
    role = Role(default_skills=["git"])
    secrets = SecretStore().put("sec-key", "api-key", "sk-x")

    # (i) forge attempt: override interactive True on a runtime that cannot.
    forge = Agent("hermes-lite", "coder", ["web"], "sec-key", "gpt-x",
                  capability_overrides={"interactive": True})
    honest = generate_card(forge, rt, role, _skills(), secrets)                  # intersect
    naive = generate_card(forge, rt, role, _skills(), secrets, override_wins=True)  # override wins

    # naive forged card → core dispatches → mid-Run failure (teeth).
    naive_failed = False
    try:
        if core_can_dispatch(naive, ["interactive"]):
            dispatch_and_run(rt, ["interactive"])
    except RuntimeFailure:
        naive_failed = True

    # (ii) narrow: override docker False on a runtime that HAS docker → honestly cleared.
    narrow = Agent("hermes-lite", "coder", ["web"], "sec-key", "gpt-x",
                   capability_overrides={"docker": False})
    narrowed = generate_card(narrow, rt, role, _skills(), secrets)

    return {"honest_interactive_forged": honest["capabilities"]["interactive"],  # must be False
            "naive_interactive_forged": naive["capabilities"]["interactive"],    # True (the lie)
            "naive_failed_mid_run": naive_failed,
            "narrow_cleared_docker": narrowed["capabilities"]["docker"] is False,
            "narrow_kept_streaming": narrowed["capabilities"]["streaming"] is True}


def run_credential_no_material():
    """(F3) AC4: the card carries {credentialType, credentialLifecycle} only. The naive card
    embeds the token bytes — the material appears in the serialized wire form (leak)."""
    rt = _full_runtime()
    role = Role(default_skills=["git"])
    agent = Agent("openclaw", "coder", ["web"], "claude-cred", "claude-sonnet-x")
    material = "CLAUDE_CODE_OAUTH_TOKEN=oat-SUPER-SECRET-abc123"
    secrets = SecretStore().put("claude-cred", "claude-oauth", material)

    honest = generate_card(agent, rt, role, _skills(), secrets)
    leaky = generate_card(agent, rt, role, _skills(), secrets, leak_secret=True)

    return {"honest_wire": serialize(honest), "leaky_wire": serialize(leaky),
            "honest_type": honest["credential"]["credentialType"],
            "honest_lifecycle": honest["credential"]["credentialLifecycle"],
            "material": material}


def run_skills_from_crd():
    """(C) AC1: skills = sorted(union(Agent.skillRefs, Role.defaultSkills)), resolved from the
    Skill CRDs. A runtime-self-declared skill never reaches the card; the list is deterministic."""
    rt = _full_runtime()
    role = Role(default_skills=["git", "web"])
    agent = Agent("openclaw", "coder", ["web", "shell"], "sec-key", "m")  # web overlaps role
    secrets = SecretStore().put("sec-key", "api-key", "sk-x")
    card1 = generate_card(agent, rt, role, _skills(), secrets)
    card2 = generate_card(agent, rt, role, _skills(), secrets)
    names = [s["name"] for s in card1["skills"]]
    # a runtime that tried to self-declare an 'exfil' skill: generate_card reads no runtime skill
    # source, so it cannot appear. Confirm the card is exactly the CRD-authorized union.
    return {"skill_names": names,
            "expected_union": sorted({"git", "web", "shell"}),
            "no_self_declared": "exfil" not in names,
            "deterministic": serialize(card1) == serialize(card2),
            "envelope_present": all("mcpToolRefs" in s and "permissions" in s for s in card1["skills"])}


def run_credential_mapping_and_failclosed():
    """(D)/(E) AC4/AC5: the three §11 stories map to the right {type, lifecycle}; an unknown
    credential FAILS CLOSED; a byo endpoint on a capable runtime is honestly advertised; and the
    card is byte-stable."""
    rt = _full_runtime()
    role = Role(default_skills=["git"])
    skills = _skills()
    out = {}
    for secret_kind, model, cred in [
        ("claude-oauth", "claude-sonnet-x", "cred-a"),
        ("api-key",      "gpt-x",           "cred-b"),
        ("byo-endpoint", "llama-local",     "cred-c"),
    ]:
        agent = Agent(rt.type, "coder", ["web"], cred, model,
                      model_endpoint_ref=("ep" if secret_kind == "byo-endpoint" else None))
        secrets = SecretStore().put(cred, secret_kind, "MATERIAL-" + secret_kind)
        card = generate_card(agent, rt, role, skills, secrets)
        out[secret_kind] = (card["credential"]["credentialType"],
                            card["credential"]["credentialLifecycle"])

    # fail-closed: an unknown credential kind must raise, not emit a blank block.
    fail_closed = False
    try:
        bad = Agent(rt.type, "coder", ["web"], "mystery", "m")
        generate_card(bad, rt, role, skills, SecretStore().put("mystery", "totally-unknown", "x"))
    except ValueError:
        fail_closed = True

    # byoModelEndpoint fail-closed: modelEndpointRef on a runtime lacking the capability must raise.
    byo_failclosed = False
    weak = _weak_runtime()  # byo_model_endpoint=False
    try:
        a = Agent(weak.type, "coder", ["web"], "sec", "m", model_endpoint_ref="ep")
        generate_card(a, weak, role, skills, SecretStore().put("sec", "byo-endpoint", "x"))
    except ValueError:
        byo_failclosed = True

    return {"mapping": out, "unknown_failclosed": fail_closed, "byo_failclosed": byo_failclosed}


def main():
    print("[model] Story 5.2 Agent Card from Agent CRD — honesty-contract falsification\n")

    # (A) teeth: the naive omit-gaps card MUST leak the gap as a mid-Run failure.
    a = run_naive_omit_gaps()
    print(f"[model] (A) NAIVE  (omit capability gaps): {a}")
    assert a["interactive_key_present"] is False, "naive card should OMIT the unsupported flag"
    assert a["core_dispatched"] is True, "TEETH LOST: the core should read absent→capable and dispatch"
    assert a["failed_mid_run"] is True, \
        "TEETH LOST: an omitted gap must surface as a mid-Run RuntimeFailure (the R3 leak)"
    print("[model]        → omitted gap ⇒ core dispatched an interactive task to a runtime that "
          "cannot ⇒ mid-Run failure (hazard is real)\n")

    # (B) §10.1 honest: gaps are explicit false; the core routes around pre-dispatch.
    b = run_honest_card()
    print(f"[model] (B) §10.1 (honest first-class flags): {b}")
    assert b["interactive_flag"] is False, "the interactive gap must be an explicit `false` flag (AC2)"
    assert b["all_keys_present"], "every known capability key is first-class on the card (AC2)"
    assert b["core_routed_around"] and not b["dispatched_bad_task"], \
        "the core must route AROUND a declared gap — never dispatch it (FR-D4/R3)"
    assert b["capable_task_ran"], "a task the runtime CAN do still routes and runs"
    print("[model]        → declared gap ⇒ core routed around it pre-dispatch; no runtime asked "
          "to do what it cannot\n")

    # (F2) override no-escalation: intersect, never forge.
    f2 = run_override_escalation()
    print(f"[model] (F2) AC3  (override intersects the ceiling): {f2}")
    assert f2["honest_interactive_forged"] is False, \
        "an override must NOT forge a capability the runtime lacks (intersect, not union)"
    assert f2["naive_interactive_forged"] is True and f2["naive_failed_mid_run"], \
        "TEETH LOST: 'override wins' should forge a dishonest flag that fails mid-Run"
    assert f2["narrow_cleared_docker"] and f2["narrow_kept_streaming"], \
        "an override CAN clear a capability the runtime has (operator narrows), leaving others"
    print("[model]        → override clears (docker↓) but cannot forge (interactive stays false); "
          "the forge attempt fails mid-Run\n")

    # (F3) credential no-material: type+lifecycle only, never the token bytes.
    f3 = run_credential_no_material()
    print(f"[model] (F3) AC4  (credential metadata, no material): type={f3['honest_type']} "
          f"lifecycle={f3['honest_lifecycle']}")
    assert f3["material"] not in f3["honest_wire"], \
        "the honest card must carry NO secret material (FR-G2/§11/§10.1)"
    assert f3["material"] in f3["leaky_wire"], \
        "TEETH LOST: the naive card should embed the token bytes (the leak this arm proves)"
    assert f3["honest_type"] == "oauth" and f3["honest_lifecycle"] == "zero-touch-refresh", \
        "credential capability metadata = {type, lifecycle} from the §11 story"
    print("[model]        → honest card = type+lifecycle only; naive card leaks the token string\n")

    # (C) skills from CRD refs, deterministic, operator-authorized.
    c = run_skills_from_crd()
    print(f"[model] (C) AC1  (skills from CRD refs): {c['skill_names']}")
    assert c["skill_names"] == c["expected_union"], \
        "skills = sorted union of Agent.skillRefs and Role.defaultSkills, resolved from CRDs"
    assert c["no_self_declared"], "a runtime cannot self-declare a skill onto the card (§5.3.6)"
    assert c["deterministic"], "same resolved CRDs → byte-identical card (AC5/conformance)"
    assert c["envelope_present"], "each skill carries its operator-authorized envelope"
    print("[model]        → skills are the CRD-authorized union, canonical order, byte-stable\n")

    # (D)/(E) mapping fidelity + fail-closed.
    d = run_credential_mapping_and_failclosed()
    print(f"[model] (D) AC4  (credential mapping + fail-closed): {d}")
    assert d["mapping"]["claude-oauth"] == ("oauth", "zero-touch-refresh")
    assert d["mapping"]["api-key"] == ("api-key", "static")
    assert d["mapping"]["byo-endpoint"] == ("byo-endpoint", "static"), \
        "each of the three §11 stories maps to its own {type, lifecycle}"
    assert d["unknown_failclosed"], "an unknown credential shape must fail closed, not emit a blank block"
    assert d["byo_failclosed"], \
        "modelEndpointRef on a runtime lacking byo_model_endpoint must fail closed, never forge it (AC5/§10.3)"
    print("[model]        → three credential stories map cleanly; unknown cred + un-backed byo "
          "endpoint both fail closed\n")

    print("[model] PASS — the naive card detectably leaks its gaps (omission A, override-forge F2, "
          "secret-material F3); the §10.1 honest card advertises first-class flags the core routes "
          "on, forges nothing, leaks no material, and maps credentials fail-closed.")


if __name__ == "__main__":
    main()
