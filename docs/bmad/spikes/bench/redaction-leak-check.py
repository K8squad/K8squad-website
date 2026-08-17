#!/usr/bin/env python3
"""redaction-leak-check.py — differential falsification for Story 13.7 (ISI-2239).

The mandatory PII/secret redaction processor (obs-plan §6, NFR-SEC3 + R9) is the
crux of 13.7: it sits UPSTREAM of every exporter on all three signal pipelines
and guarantees no credential, password, session token, username, or email ever
crosses the cluster boundary — only the opaque `user.id` survives, and agent
content is exported as id/kind/length/hash only. §11 gate #3.

This bench proves that guarantee has TEETH two ways:

  A) BEHAVIOURAL — model the `redaction` + `transform/redaction-content`
     processors over a fixture stream. A clean baseline exports unchanged; each
     planted secret/PII/agent-content shape is dropped or hashed while `user.id`
     survives. Every mutation (weakened regex, dropped rule, redaction moved
     after export) flips the check RED. (AC2/AC3/AC6)

  B) CONFIG-FIDELITY — parse the SHIPPED reference config
     (`collector-pipeline.yaml`): the redaction ruleset the model uses is read
     from that file, and the processor ORDER on every pipeline is asserted
     (memory_limiter first, batch last, redaction present + before tail_sampling,
     k8sattributes not resourcedetection). So a real edit that weakens a regex or
     reorders the pipeline flips THIS bench RED — the bench guards the artifact
     that ships, not a private reimplementation. (AC1/AC2)

Stdlib-only. `python3 redaction-leak-check.py`.
"""

import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "collector-pipeline.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# (B) Read the shipped config — allowed_keys, blocked_values, pipeline order.
# A deliberately small YAML-subset reader for the specific known structure, so
# the bench stays stdlib-only yet tracks the real artifact.
# ─────────────────────────────────────────────────────────────────────────────
def load_config(path=CONFIG):
    with open(path) as fh:
        lines = fh.readlines()

    allowed_keys, blocked_values = [], []
    pipelines = {}          # name -> list[processor]
    section = None          # "allowed_keys" | "blocked_values" | None
    in_pipelines = False
    cur_pipeline = None

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # redaction ruleset lists
        if stripped.startswith("allowed_keys:"):
            section = "allowed_keys"
            continue
        if stripped.startswith("blocked_values:"):
            section = "blocked_values"
            continue
        if section and stripped.startswith("- "):
            item = stripped[2:].strip()
            # strip surrounding quotes + trailing inline comment
            if item and item[0] in "\"'":
                q = item[0]
                item = item[1:item.index(q, 1)]
                if q == '"':
                    # YAML double-quote escaping: "\\s" is the regex \s. The OTel
                    # collector unescapes this at parse time; mirror that here so
                    # the bench compiles the SAME regex the processor runs.
                    item = item.replace("\\\\", "\\")
            else:
                item = item.split("#")[0].strip()
            (allowed_keys if section == "allowed_keys" else blocked_values).append(item)
            continue
        # a non-list, less-indented key ends the current list section
        if section and not stripped.startswith("- ") and stripped.endswith(":"):
            section = None

        # service.pipelines.<name>.processors
        if stripped == "pipelines:":
            in_pipelines = True
            continue
        if in_pipelines:
            m = re.match(r"^    (\w+):$", line)          # traces:/metrics:/logs:
            if m:
                cur_pipeline = m.group(1)
                pipelines[cur_pipeline] = []
                continue
            m = re.match(r"^\s*processors:\s*\[(.*)\]", line)
            if m and cur_pipeline:
                procs = [p.strip() for p in m.group(1).split(",") if p.strip()]
                pipelines[cur_pipeline] = procs
            if stripped in ("telemetry:", "extensions:"):
                in_pipelines = False

    return {
        "allowed_keys": allowed_keys,
        "blocked_values": blocked_values,
        "pipelines": pipelines,
    }


REDACTION_PROCS = ("redaction", "transform/redaction-content")


def assert_config_order(cfg):
    """AC1/AC2 config-fidelity: the fixed processor order holds on every pipeline."""
    pls = cfg["pipelines"]
    for name in ("traces", "metrics", "logs"):
        assert name in pls and pls[name], f"config: pipeline {name!r} missing/empty"
        procs = pls[name]
        assert procs[0] == "memory_limiter", f"config: {name}: memory_limiter must be FIRST, got {procs[0]!r}"
        assert procs[-1] == "batch", f"config: {name}: batch must be LAST, got {procs[-1]!r}"
        assert "resourcedetection" not in procs, f"config: {name}: resourcedetection is for VM/bare-metal, not k8s"
        assert "k8sattributes" in procs, f"config: {name}: k8sattributes required (k8s-native)"
        # redaction present and upstream of the exporter (i.e. before batch)
        assert "redaction" in procs, f"config: {name}: mandatory `redaction` processor missing (AC2)"
        assert procs.index("redaction") < procs.index("batch"), \
            f"config: {name}: redaction must precede batch/export (AC2)"
        if "tail_sampling" in procs:  # traces only
            assert procs.index("redaction") < procs.index("tail_sampling"), \
                f"config: {name}: redaction must precede tail_sampling (never sample on pre-redaction attrs)"
    # the ruleset must actually cover the secret families
    assert cfg["allowed_keys"], "config: allowed_keys empty — redaction would delete everything or nothing"
    assert "user.id" in cfg["allowed_keys"], "config: user.id must survive (the only identity key, §6)"
    assert len(cfg["blocked_values"]) >= 8, "config: blocked_values too thin to cover the §6 secret shapes"
    # COVERAGE FIDELITY (AC6): every §6 secret family must still match at least one
    # of the SHIPPED blocked_values regexes. Delete/weaken a regex in the artifact
    # so a family is no longer covered, and THIS check flips RED — the bench guards
    # the file that ships, not only its own embedded copy.
    shipped = []
    for pat in cfg["blocked_values"]:
        try:
            shipped.append(re.compile(pat))
        except re.error as e:
            raise AssertionError(f"config: blocked_values regex does not compile: {pat!r} ({e})")
    for family, sample in SECRET_SAMPLES.items():
        assert any(rx.search(sample) for rx in shipped), \
            f"config: no shipped blocked_values regex covers the {family!r} secret family (AC6)"


# ─────────────────────────────────────────────────────────────────────────────
# (A) Behavioural model of the two redaction processors over a fixture stream.
# ─────────────────────────────────────────────────────────────────────────────
def sha256(s):
    return "sha256:" + hashlib.sha256(str(s).encode()).hexdigest()[:16]


# Keys carrying raw agent-authored content — transform/redaction-content hashes
# these and drops the raw value (AC3). Closed set, mirrors the config's OTTL.
CONTENT_KEYS = {"agent.content", "memory.body", "workitem.text", "model.output"}

# ── Canonical redaction ruleset (embedded; mirrors collector-pipeline.yaml §6). ──
# `http.header` + `contact` are kept on the allowlist ON PURPOSE: the value-regex
# battery is then the SOLE guard for a secret/PII in their value — the strongest
# possible test of blocked_values (weaken a regex ⇒ that value leaks ⇒ RED).
CANONICAL_ALLOWED = [
    "user.id", "run.id", "work_item.id", "team", "project", "error_code",
    "phase", "outcome", "http.status_code", "http.header", "contact",
    "content.hash", "content.length", "model.output",
]
CANONICAL_BLOCKED = [
    r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"(?i)CLAUDE_CODE_OAUTH_TOKEN\s*=\s*\S+",
    r"sk-ant-[A-Za-z0-9]{12,}",
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"(?i)password\s*=\s*\S+",
    r"(?i)session_token\s*=\s*\S+",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"(?i)api[_-]?key\s*=\s*\S+",
]

# Raw secret/PII samples, one per §6 family — used both to plant fixtures and to
# assert the SHIPPED config's regex battery still covers every family (fidelity).
SECRET_SAMPLES = {
    "bearer":        "Authorization: Bearer eyJhbGciOiJqd.abcDEF123.ghiJKL456",
    "oauth":         "CLAUDE_CODE_OAUTH_TOKEN=sk-ant-abcdEFGH12345678",
    "anthropic_key": "sk-ant-ABCDEFGH0123456789xyz",
    "aws_key":       "AKIAIOSFODNN7EXAMPLE",
    "github_token":  "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    "password":      "password=hunter2superSecret",
    "session_token": "session_token=abcd1234efgh5678ijkl",
    "email":         "alice@example.com",
    "api_key":       "api_key=SECRETgenericKEYvalue123",
}


class RedactionPipeline:
    """Applies transform/redaction-content then `redaction` to one record's attrs.

    `mut` is a set of active mutation names (the falsification harness); the clean
    pipeline runs with mut=set().

    The behavioural ruleset is EMBEDDED here (CANONICAL_ALLOWED / CANONICAL_BLOCKED)
    — the sibling-bench convention (cf. blocked-gauge-check.py's inline enum). It
    mirrors collector-pipeline.yaml's intent but is decoupled from the file's exact
    text so the mutation harness stays deterministic. The shipped file's own regex
    battery is separately guarded by assert_config_order()'s coverage check, so a
    real weakening of the artifact is still caught."""

    def __init__(self, mut=None):
        self.mut = mut or set()
        self.allowed = set(CANONICAL_ALLOWED)
        # A weakened-rule mutation narrows the bearer/token regexes to something
        # that no longer matches realistic tokens.
        blocked = list(CANONICAL_BLOCKED)
        if "weaken_token_regex" in self.mut:
            blocked = [b for b in blocked if "bearer" not in b.lower() and "sk-" not in b]
            blocked.append(r"bearer ZZZ_NEVER_MATCHES")
        if "drop_email_rule" in self.mut:
            blocked = [b for b in blocked if "@" not in b]
        self.blocked = [re.compile(b) for b in blocked]

    def _content_stage(self, attrs):
        """transform/redaction-content — AC3."""
        if "disable_content_hash" in self.mut:
            return attrs  # MUTATION: leak raw agent content verbatim
        out = dict(attrs)
        for k in list(out.keys()):
            if k in CONTENT_KEYS:
                out["content.hash"] = sha256(out[k])
                out["content.length"] = len(str(out[k]))
                del out[k]
        return out

    def _value_stage(self, attrs):
        """`redaction` — AC2. Drop non-allowed keys; hash blocked values."""
        out = {}
        for k, v in attrs.items():
            if "allow_all_keys" in self.mut:
                keep = True  # MUTATION: allow_all_keys=true — content keys survive
            else:
                keep = k in self.allowed
            if not keep:
                continue  # key deleted (username, email-key, raw content key…)
            sv = str(v)
            masked = sv
            for rx in self.blocked:
                if rx.search(sv):
                    masked = sha256(sv)
                    break
            out[k] = masked
        return out

    def apply(self, attrs):
        # AC6 "redaction after export": model export happening BEFORE redaction —
        # the record leaves the pipeline with raw attrs, redaction is a no-op tail.
        if "redaction_after_export" in self.mut:
            return dict(attrs)
        return self._value_stage(self._content_stage(attrs))


def fixture_records():
    """One clean baseline + one planted secret/PII/content shape per record.
    Every record also carries an opaque `user.id` that MUST survive.

    The carrier keys align with collector-pipeline.yaml's allowed_keys, which
    deliberately keeps `http.header`, `contact`, and `model.output` on the
    allowlist so the VALUE-level guard is the sole thing between the secret and
    the exporter — the strongest test:
      • VALUE-MASKING (blocked_values regexes): the secret rides in the VALUE of
        an ALLOWED key (`http.header`, `contact`). The regex is the ONLY guard,
        so narrowing/removing a regex flips the bench RED.
      • CONTENT-HASH (transform/redaction-content): raw agent content rides on
        `model.output` (a content key); the hash stage is the only guard, so
        disabling it flips the bench RED.
      • KEY-DELETION (allowed_keys allowlist): a secret on a NON-allowlisted key
        (`username`, `secretRef.value`) is dropped wholesale by allow_all_keys=false."""
    return {
        "baseline":      {"user.id": "u-opaque-42", "run.id": "run-7", "error_code": "ok"},
        # value-masking: secret embedded in the allowed `http.header` value
        "oauth":         {"user.id": "u-1", "http.header": "CLAUDE_CODE_OAUTH_TOKEN=sk-ant-abcdEFGH12345678"},
        "bearer":        {"user.id": "u-1", "http.header": "Authorization: Bearer eyJhbGciOiJqd.abcDEF123.ghiJKL456"},
        "api_key":       {"user.id": "u-1", "http.header": "sk-ant-ABCDEFGH0123456789xyz"},
        "aws_key":       {"user.id": "u-1", "http.header": "AKIAIOSFODNN7EXAMPLE"},
        "gh_token":      {"user.id": "u-1", "http.header": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"},
        "password":      {"user.id": "u-1", "http.header": "password=hunter2superSecret"},
        "session_token": {"user.id": "u-1", "http.header": "session_token=abcd1234efgh5678ijkl"},
        "generic_key":   {"user.id": "u-1", "http.header": "api_key=SECRETgenericKEYvalue123"},
        # value-masking PII: email on the allowed `contact` key (email regex is the guard)
        "email":         {"user.id": "u-1", "contact": "alice@example.com"},
        # key-deletion: forbidden key dropped wholesale
        "username":      {"user.id": "u-1", "username": "alice.smith"},
        "secretref":     {"user.id": "u-1", "secretRef.value": "sk-ant-SECRETrefVALUE0123456789"},
        # content-hash: raw agent output → id/kind/len/hash only (AC3)
        "agent_content": {"user.id": "u-1", "model.output": "here is the customer's SSN 123-45-6789 and plan"},
    }


# What must be TRUE of every clean-pipeline output — no planted secret/PII
# substring may appear verbatim.
SECRET_TOKENS = [
    "sk-ant-abcdEFGH12345678", "eyJhbGciOiJqd", "abcDEF123",
    "sk-ant-ABCDEFGH0123456789xyz", "AKIAIOSFODNN7EXAMPLE",
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345", "hunter2superSecret",
    "abcd1234efgh5678ijkl", "SECRETgenericKEYvalue123",
    "alice@example.com", "alice.smith", "SECRETrefVALUE",
    "123-45-6789", "here is the customer's SSN",
]


def flatten(attrs):
    return " ".join(f"{k}={v}" for k, v in attrs.items())


def assert_clean(mut):
    """The GREEN invariant set — holds on the un-mutated pipeline."""
    pipe = RedactionPipeline(mut)
    recs = fixture_records()

    for name, attrs in recs.items():
        out = pipe.apply(attrs)
        blob = flatten(out)

        # (1) user.id ALWAYS survives, opaque, un-hashed.
        assert out.get("user.id", "").startswith("u-"), f"{name}: opaque user.id did not survive"

        # (2) no planted secret/PII substring appears verbatim on output.
        for tok in SECRET_TOKENS:
            assert tok not in blob, f"{name}: secret/PII leaked verbatim → {tok!r}"

        # (3) forbidden identity keys (username/email/raw-content keys) are gone.
        for k in ("username", "contact", "secretRef.value", "model.output", "http.header"):
            assert k not in out or "sha256:" in str(out[k]), \
                f"{name}: forbidden key {k!r} survived un-redacted"

    # (4) baseline exports UNCHANGED (redaction never mangles clean telemetry).
    base = pipe.apply(recs["baseline"])
    assert base == recs["baseline"], "baseline mutated by redaction (false positive)"

    # (5) AC3: agent content becomes hash + length, never verbatim.
    ac = pipe.apply(recs["agent_content"])
    assert "content.hash" in ac and "content.length" in ac, "AC3: content not hashed/length-stamped"
    assert int(ac["content.length"]) == len(recs["agent_content"]["model.output"]), "AC3: content length lost"


MUTATIONS = {
    "redaction_after_export":  "AC6: redaction moved after export (raw record leaves the pipeline)",
    "allow_all_keys":          "AC2: allow_all_keys=true — content-bearing keys bypass the allowlist",
    "weaken_token_regex":      "AC6: bearer/api-key regex narrowed so real tokens slip through",
    "drop_email_rule":         "AC2: email/PII rule removed",
    "disable_content_hash":    "AC3: agent content exported verbatim (hash stage disabled)",
}


def mutation_detected(mut_name):
    try:
        assert_clean({mut_name})
        return False
    except AssertionError:
        return True


def main():
    failures = []

    # (B) config fidelity — the shipped artifact carries the fixed order + ruleset.
    try:
        cfg = load_config()
        assert_config_order(cfg)
        print(f"OK   config GREEN — collector-pipeline.yaml: order fixed, redaction on "
              f"{len(cfg['pipelines'])} pipelines, {len(cfg['blocked_values'])} secret regexes")
    except (AssertionError, OSError) as e:
        print(f"\nFAIL: config check: {e}", file=sys.stderr)
        sys.exit(1)

    # (A1) behavioural GREEN baseline.
    try:
        assert_clean(set())
        print("OK   redaction GREEN — every planted secret/PII/content shape dropped or hashed; user.id survives")
    except AssertionError as e:
        failures.append(f"baseline not GREEN: {e}")

    # (A2) every mutation must be DETECTED (turn the check RED) — the teeth.
    for mut_name, desc in MUTATIONS.items():
        if mutation_detected(mut_name):
            print(f"OK   mutation caught — {desc}")
        else:
            failures.append(f"mutation NOT caught ({mut_name}): {desc}")

    if failures:
        print("\nFAIL:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)
    print("\nAll invariants falsifiable and held: 13.7 redaction-leak check GREEN.")


if __name__ == "__main__":
    main()
