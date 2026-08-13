#!/usr/bin/env python3
"""
Story 5.4 (ISI-2216) falsification — the credential-injection contract.

Differential secret-hygiene falsification, same house shape as run-retry-backoff-check.py (3.2) and
runtimeclass-selection-check.py (4.2). It proves the two load-bearing invariants of the shim §7 /
arch §11 credential contract have TEETH by contrasting a NAIVE injector (inlines the token literal into
the pod spec, lets the shim read+log the raw value, echoes the raw runtime error into the auth-required
event, mounts a cross-squad Secret, and hardcodes a vendor env switch in core) against the §7/§11
CONTRACT injector (env/volume FROM a Secret ref only, shim knows the *shape* not the value, auth-required
carries ref-not-value, per-namespace scope, runtime-native mapping via Agent-Card metadata not core code).

The crux (NFR-SEC3 / FR-G1): the credential VALUE must NEVER appear in any observable/durable sink —
pod spec/manifest (etcd), Run logs, shim logs, the SSE event stream, coord artifacts, the audit_log, or
OTel attributes. Only the *reference* (secretRef name) and the *shape* (Agent-Card auth.type) are ever
handled outside the Secret object and the kubelet-materialized runtime container env.

Mutation contract (the two headline invariants must be falsifiable — re-run these after any edit):
  * delete `scrub(...)` in auth_required_event_contract (echo the raw runtime error) -> (F1) MUST go RED.
  * make assemble_pod_contract inline the literal instead of a secretRef mount     -> (F2) MUST go RED.

stdlib only. `python3 credential-injection-check.py`. Exits non-zero on any falsification.
No wall-clock, no RNG: everything is a pure function of fixed inputs so the gate is reproducible.
"""
import sys

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)

# The sentinel credential value. If this substring EVER reaches a sink, the contract is breached.
SECRET_VALUE = "oauth-tok-SENSITIVE-DEADBEEF0000"

# ---------------------------------------------------------------------------
# Runtime-native mapping is Agent-Card metadata (FR-G2), NOT a core vendor switch.
# The Run reconciler resolves the env var name + secret key by DATA lookup on the
# runtime's advertised auth.type — adding a runtime family is a metadata row, not a
# code branch (conformance C10 zero-core-change; §7 "runtime metadata, not core-hardcoded").
# ---------------------------------------------------------------------------
RUNTIME_AUTH_METADATA = {
    "oauth-subscription": {"env": "CLAUDE_CODE_OAUTH_TOKEN", "secret_key": "token"},   # (a) Claude-family
    "api-key":            {"env": "ANTHROPIC_API_KEY",       "secret_key": "api_key"}, # (b) non-Claude key
    "byo-endpoint":       {"env": "OPENAI_BASE_URL",         "secret_key": "endpoint"},# (c) BYO endpoint §10.3
    "hermes-key":         {"env": "HERMES_API_TOKEN",        "secret_key": "api_key"}, # a LATER family: pure
    #                                                                                    metadata, no core edit
}

def resolve_env_mapping_contract(auth_type):
    """Pure data lookup — core carries no `if vendor == ...`. A new family drops in as a metadata row."""
    return RUNTIME_AUTH_METADATA[auth_type]

def resolve_env_mapping_naive(auth_type):
    """The seam-leaking anti-pattern: a hardcoded vendor switch in core. It cannot resolve a runtime
    family it wasn't compiled to know about -> every new runtime forces a core change (breaks C10)."""
    if auth_type == "oauth-subscription":
        return {"env": "CLAUDE_CODE_OAUTH_TOKEN", "secret_key": "token"}
    if auth_type == "api-key":
        return {"env": "ANTHROPIC_API_KEY", "secret_key": "api_key"}
    raise KeyError(f"core has no branch for auth.type={auth_type!r} (add a case & recompile)")


# ---------------------------------------------------------------------------
# Simulated k8s Secret store. The credential VALUE lives here (and, at runtime,
# only in the kubelet-materialized runtime-container env) — nowhere else, ever.
# ---------------------------------------------------------------------------
class SecretStore:
    def __init__(self):
        self.data = {}
    def put(self, ns, name, kv):
        self.data[(ns, name)] = dict(kv)
    def get(self, ns, name):
        return self.data[(ns, name)]


# ---------------------------------------------------------------------------
# The set of observable/durable sinks. NFR-SEC3: the credential value must be
# absent from every one of them. `leaked()` is the falsifier.
# ---------------------------------------------------------------------------
class Sinks:
    def __init__(self):
        self.run_log = []     # Run logs (§13)
        self.shim_log = []    # shim sidecar logs
        self.sse = []         # the SSE event stream (§4)
        self.artifacts = []   # coord.artifact blobs (§6.5)
        self.audit = []       # audit_log rows (§6)
        self.otel = []        # OTel span/metric attributes (§17.2)
    def _scan(self, bucket):
        hits = []
        for entry in bucket:
            if SECRET_VALUE in _stringify(entry):
                hits.append(entry)
        return hits
    def leaked(self):
        out = {}
        for name in ("run_log", "shim_log", "sse", "artifacts", "audit", "otel"):
            hits = self._scan(getattr(self, name))
            if hits:
                out[name] = hits
        return out  # {} == clean

def _stringify(x):
    if isinstance(x, dict):
        return " ".join(_stringify(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return " ".join(_stringify(v) for v in x)
    return str(x)


# ---------------------------------------------------------------------------
# Pod assembly. CONTRACT: env/volume FROM a secretRef — the pod SPEC (what the
# reconciler writes to etcd) carries only a REFERENCE; the value is materialized
# by kubelet into the runtime container at run time, never written into the manifest.
# ---------------------------------------------------------------------------
def assemble_pod_contract(agent, meta):
    ref = agent["credentialSecretRef"]
    return {
        "namespace": agent["namespace"],
        # env-from-secret-ref: a reference, not a literal (§7 "envFrom: secretRef / valueFrom.secretKeyRef")
        "containers": {
            "runtime": {
                "envFrom": [{"secretRef": {"name": ref}}],
                "env": [{"name": meta["env"],
                         "valueFrom": {"secretKeyRef": {"name": ref, "key": meta["secret_key"]}}}],
            },
            # the shim is a SEPARATE sidecar: it never receives the credential env at all (§7 trust surface)
            "shim": {"env": [{"name": "KSQUAD_AUTH_TYPE", "value": agent["auth_type"]},
                             {"name": "KSQUAD_SECRET_REF", "value": ref}]},
        },
    }

def assemble_pod_naive(agent, store, meta):
    """The hole §7 closes: read the Secret value and INLINE it into the pod spec (and hand it to the
    shim container). The literal now lives in etcd, in every `kubectl get pod -o yaml`, in reconciler
    logs, and in the shim's env — i.e. persisted and echoable. (F2 mutation = making the contract do this.)"""
    val = store.get(agent["namespace"], agent["credentialSecretRef"])[meta["secret_key"]]
    return {
        "namespace": agent["namespace"],
        "containers": {
            "runtime": {"env": [{"name": meta["env"], "value": val}]},           # INLINE literal
            "shim":    {"env": [{"name": meta["env"], "value": val}]},           # shim can now read+log it
        },
    }

def pod_contains_secret_literal(pod):
    return SECRET_VALUE in _stringify(pod)


# ---------------------------------------------------------------------------
# Per-namespace scope (NFR-SEC3: credentials never mounted cross-squad).
# A Run may bind only a Secret in its OWN Team namespace (Story 4.1 boundary).
# ---------------------------------------------------------------------------
def bind_secret_contract(pod_ns, secret_ns, name):
    if secret_ns != pod_ns:
        return ("rejected", "CrossSquadCredentialDenied")   # fail-closed
    return ("bound", name)

def bind_secret_naive(pod_ns, secret_ns, name):
    return ("bound", name)  # naive: mounts whatever ref is named, even another team's Secret


# ---------------------------------------------------------------------------
# Auth-failure -> Paused(auth-required). The event carries {provider, secretRef, detail};
# the runtime's raw error text may embed the token, so the shim SCRUBS it to ref-not-value.
# (F1 mutation = deleting scrub.)  C7: never generic `failed`.
# ---------------------------------------------------------------------------
def scrub(text):
    """The shim's no-echo discipline (§7/§17.1): strip any credential material before it can leave the
    shim's trust surface. Modeled as replacing the known sentinel; a real shim never has the raw value in
    hand (it isn't injected into the sidecar) — this guards the one path where a runtime error string can
    carry it through."""
    return text.replace(SECRET_VALUE, "«redacted»")

def auth_required_event_contract(provider, secret_ref, runtime_error_text):
    return {"type": "auth-required", "provider": provider, "secretRef": secret_ref,
            "detail": scrub(runtime_error_text)}   # <-- F1 mutation target (delete scrub -> RED)

def auth_required_event_naive(provider, secret_ref, runtime_error_text):
    return {"type": "auth-required", "provider": provider, "secretRef": secret_ref,
            "detail": runtime_error_text}          # raw error -> embeds the token -> leak

def run_reconcile_on_auth_failure(event):
    """C7 / FR-G3: an auth-required event -> Paused with a legible condition, NOT generic `failed`."""
    if event["type"] == "auth-required":
        return {"phase": "Paused", "condition": f"AuthRequired(provider={event['provider']},"
                                                f"secretRef={event['secretRef']})",
                "resume_on": ("secret_update", event["secretRef"])}
    return {"phase": "Failed"}


# ===========================================================================
# Scenarios
# ===========================================================================
def scenario_naive_inline_pod_leaks(store):
    """(A) NAIVE inline injector: token literal lands in the pod spec AND the shim env; the shim reads it
    and logs it. Both the manifest scan and the sink scan MUST catch it (harness has teeth)."""
    sinks = Sinks()
    agent = {"namespace": "team-acme", "credentialSecretRef": "acme-claude-creds",
             "auth_type": "oauth-subscription"}
    meta = resolve_env_mapping_naive(agent["auth_type"])
    pod = assemble_pod_naive(agent, store, meta)
    # naive shim can read the injected env value -> "helpfully" logs the container env on start
    shim_env_val = pod["containers"]["shim"]["env"][0]["value"]
    sinks.shim_log.append(f"starting runtime with env {meta['env']}={shim_env_val}")
    return pod_contains_secret_literal(pod), sinks.leaked()

def scenario_contract_pod_clean(store):
    """(B) CONTRACT injector: pod spec carries only a secretRef; the shim env carries only the SHAPE +
    the ref name; the shim logs the shape, never a value. Manifest scan and every sink stay clean."""
    sinks = Sinks()
    agent = {"namespace": "team-acme", "credentialSecretRef": "acme-claude-creds",
             "auth_type": "oauth-subscription"}
    meta = resolve_env_mapping_contract(agent["auth_type"])
    pod = assemble_pod_contract(agent, meta)
    # contract shim only knows the shape; it has no raw value to log
    auth_type = pod["containers"]["shim"]["env"][0]["value"]
    ref = pod["containers"]["shim"]["env"][1]["value"]
    sinks.run_log.append(f"Run start: auth shape={auth_type} via secretRef={ref}")
    sinks.shim_log.append(f"shim up; injecting {meta['env']} from secretRef (value not handled by shim)")
    return pod_contains_secret_literal(pod), sinks.leaked()

def scenario_mapping_metadata_vs_core(store):
    """(M) runtime-native mapping across the three §11 shapes resolves by METADATA; a LATER family
    (hermes-key) resolves with the SAME resolver, no core change (C10). The naive core switch can't."""
    for at in ("oauth-subscription", "api-key", "byo-endpoint"):
        m = resolve_env_mapping_contract(at)
        check("env" in m and "secret_key" in m, f"mapping metadata missing for {at}")
    check(resolve_env_mapping_contract("oauth-subscription")["env"] == "CLAUDE_CODE_OAUTH_TOKEN",
          "oauth family must map to CLAUDE_CODE_OAUTH_TOKEN")
    # zero-core-change: a runtime family core was never compiled for still resolves via metadata.
    contract_ok = resolve_env_mapping_contract("hermes-key")["env"] == "HERMES_API_TOKEN"
    naive_needs_core_edit = False
    try:
        resolve_env_mapping_naive("hermes-key")
    except KeyError:
        naive_needs_core_edit = True
    return contract_ok, naive_needs_core_edit

def scenario_cross_squad_scope(store):
    """(S) NFR-SEC3 cross-squad: a Run in team-acme naming team-globex's Secret is fail-closed by the
    contract; the naive binder mounts it (a cross-squad credential leak)."""
    contract = bind_secret_contract("team-acme", "team-globex", "globex-creds")
    naive = bind_secret_naive("team-acme", "team-globex", "globex-creds")
    return contract, naive

def scenario_auth_failure_pause(store):
    """(P) auth-failure -> Paused(auth-required) with ref-not-value; resume on Secret update; NOT failed.
    The raw runtime error embeds the token; the contract event scrubs it, naive echoes it (sink leak)."""
    sinks_c, sinks_n = Sinks(), Sinks()
    raw_err = f"401 from provider: token {SECRET_VALUE} rejected"
    ev_c = auth_required_event_contract("anthropic", "acme-claude-creds", raw_err)
    ev_n = auth_required_event_naive("anthropic", "acme-claude-creds", raw_err)
    sinks_c.sse.append(ev_c); sinks_c.run_log.append(ev_c["detail"])
    sinks_n.sse.append(ev_n); sinks_n.run_log.append(ev_n["detail"])
    state = run_reconcile_on_auth_failure(ev_c)
    return state, sinks_c.leaked(), sinks_n.leaked()

def scenario_no_persist(store):
    """(N) never PERSISTS: the metering/audit path anchors {principal, agent, run, secretRef} but never
    the value (FR-I2 attribution is by principal, not by echoing the credential). A naive 'log the token
    to audit for debugging' is the exact NFR-SEC3 breach; the contract audit/artifact/otel rows stay clean."""
    sinks = Sinks()
    # contract: attribution by reference + principal, value-free
    sinks.audit.append({"event": "run.start", "principal": "user:acme-alice",
                        "agent": "agent-x", "run": "run-1", "secretRef": "acme-claude-creds"})
    sinks.otel.append({"ksquad.principal": "user:acme-alice", "ksquad.agent": "agent-x",
                       "ksquad.run": "run-1"})  # labels, never the token (§17.2)
    sinks.artifacts.append({"kind": "diff", "run": "run-1", "sha256": "abc123"})  # workspace diff, no creds
    return sinks.leaked()

def scenario_f1_scrub_teeth(store):
    """(F1) ISOLATED scrub teeth: feed a runtime error embedding the token through the CONTRACT event
    builder. detail MUST NOT contain the value. Deleting scrub() makes this RED."""
    raw_err = f"provider auth error: Authorization: Bearer {SECRET_VALUE}"
    ev = auth_required_event_contract("anthropic", "acme-claude-creds", raw_err)
    return SECRET_VALUE not in _stringify(ev)  # must be True

def scenario_f2_inline_teeth(store):
    """(F2) ISOLATED inline-rejection teeth: the CONTRACT pod spec MUST carry no credential literal —
    only a secretRef. Making assemble_pod_contract inline the value makes this RED."""
    agent = {"namespace": "team-acme", "credentialSecretRef": "acme-claude-creds",
             "auth_type": "oauth-subscription"}
    meta = resolve_env_mapping_contract(agent["auth_type"])
    pod = assemble_pod_contract(agent, meta)
    # the pod references the Secret by name, and that ref actually resolves in the store (real binding),
    # yet the VALUE is nowhere in the spec.
    ref_used = pod["containers"]["runtime"]["envFrom"][0]["secretRef"]["name"]
    store.get(agent["namespace"], ref_used)  # raises if the ref is dangling -> real, not a fake pass
    return (not pod_contains_secret_literal(pod)), ref_used == agent["credentialSecretRef"]


# ===========================================================================
def main():
    store = SecretStore()
    store.put("team-acme", "acme-claude-creds", {"token": SECRET_VALUE})
    store.put("team-globex", "globex-creds", {"token": "globex-other-value"})

    # (A) naive inline injector MUST leak — both the manifest and a sink (harness keeps its teeth)
    naive_inline, naive_sinks = scenario_naive_inline_pod_leaks(store)
    check(naive_inline is True,
          "HARNESS LOST TEETH: naive inline injector no longer writes the token literal into the pod spec")
    check("shim_log" in naive_sinks,
          "HARNESS LOST TEETH: naive shim no longer leaks the injected credential into its log")

    # (B) contract injector: no literal in the manifest, no leak in ANY sink
    c_inline, c_sinks = scenario_contract_pod_clean(store)
    check(c_inline is False,
          "AC1 FAILED: contract pod spec contains a credential literal (must be a secretRef, not inline)")
    check(c_sinks == {},
          f"NFR-SEC3 FAILED: contract path leaked the credential into a sink: {c_sinks}")

    # (M) runtime-native mapping via metadata; zero-core-change for a later family (C10)
    contract_ok, naive_needs_edit = scenario_mapping_metadata_vs_core(store)
    check(contract_ok,
          "AC2 FAILED: a later runtime family did not resolve via Agent-Card metadata (needs core edit)")
    check(naive_needs_edit,
          "HARNESS LOST TEETH: the naive core switch resolved a new family without a code branch")

    # (S) cross-squad scope fail-closed; naive mounts another team's Secret
    contract_scope, naive_scope = scenario_cross_squad_scope(store)
    check(contract_scope[0] == "rejected",
          "AC5 FAILED: a cross-squad Secret mount was not fail-closed (NFR-SEC3 cross-squad breach)")
    check(naive_scope[0] == "bound",
          "HARNESS LOST TEETH: naive cross-squad mount no longer succeeds")

    # (P) auth-failure -> Paused (not failed); ref-not-value; contract sink clean, naive sink leaks
    state, sinks_c, sinks_n = scenario_auth_failure_pause(store)
    check(state["phase"] == "Paused" and "AuthRequired" in state["condition"],
          "AC6/C7 FAILED: auth-failure did not route to Paused(auth-required)")
    check(state["resume_on"][0] == "secret_update",
          "AC6 FAILED: Paused Run must resume on the referenced Secret updating")
    check(sinks_c == {},
          f"AC4 FAILED: contract auth-required event leaked the token into a sink: {sinks_c}")
    check("sse" in sinks_n or "run_log" in sinks_n,
          "HARNESS LOST TEETH: naive raw-error echo no longer leaks the token")

    # (N) never persists to audit/artifact/otel
    check(scenario_no_persist(store) == {},
          "AC4 FAILED: the credential value was persisted to an audit/artifact/otel sink")

    # (F1) scrub teeth isolated
    check(scenario_f1_scrub_teeth(store) is True,
          "AC4 scrub teeth FAILED: auth-required detail carried the raw token "
          "(delete scrub() in auth_required_event_contract to see this go RED)")

    # (F2) inline-rejection teeth isolated
    f2_clean, f2_ref_ok = scenario_f2_inline_teeth(store)
    check(f2_clean is True and f2_ref_ok is True,
          "AC1 inline-rejection teeth FAILED: contract pod carried a literal instead of a live secretRef "
          "(make assemble_pod_contract inline the value to see this go RED)")

    if FAIL:
        print("FALSIFIED — Story 5.4 credential-injection check FAILED:")
        for m in FAIL:
            print("  ✗", m)
        sys.exit(1)
    print("OK — Story 5.4 credential-injection contract holds:")
    print("  (A)  naive inline injector writes the token into the pod spec AND leaks it via shim log (teeth)")
    print("  (B)  contract injector: secretRef-only pod spec; no leak in run_log/shim_log/sse/artifact/audit/otel (AC1/AC3/AC4)")
    print("  (M)  runtime-native env mapping resolves by Agent-Card metadata; a later family needs NO core edit (AC2/C10)")
    print("  (S)  a cross-squad Secret mount is fail-closed; naive binder leaks it (AC5/NFR-SEC3)")
    print("  (P)  auth-failure -> Paused(auth-required), resume-on-Secret-update, ref-not-value; naive echo leaks (AC6/C7)")
    print("  (N)  audit/artifact/otel carry {principal,agent,run,secretRef} but never the value (AC4)")
    print("  (F1) auth-required detail is scrubbed of the raw token (delete scrub -> RED)")
    print("  (F2) contract pod carries a LIVE secretRef, zero literal (inline the value -> RED)")

if __name__ == "__main__":
    main()
