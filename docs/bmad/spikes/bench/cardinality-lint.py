#!/usr/bin/env python3
"""
cardinality-lint — the CI cardinality-budget gate (Story 13.6 / ISI-2238).

obs-plan §5.6 / §11 gate #1: "A CI check greps the instrumentation for metric
label keys outside the allowlist and fails the build." High-cardinality dims
(`run.id`/`work_item.id`/`principal.id`/`user.id`, scope names, PII) ride as
resource attributes / exemplars / span+log attributes only — NEVER as a metric
label. This tool is that gate. Story 13.6 delivers it; Story 14.7 wires it into
`ci.yml` as a required check.

WHAT IT SCANS (and, crucially, what it does NOT). The load-bearing distinction is
metric label vs span/log/resource attribute:

  * Go, idiomatic OTel: metric labels are the `attribute.*` keys wrapped in the
    METRIC package's option `metric.WithAttributes(...)` passed to an instrument
    emit (`.Add(` / `.Record(` / observer `.Observe*(`). This tool flags keys in
    those, and ONLY those. `span.SetAttributes(...)` (trace) and
    `resource.WithAttributes(...)` / `resource.NewWithAttributes(...)` (resource
    attrs — where scope names legitimately live) are deliberately NOT metric
    labels, so an id/name/user.id there is fine and is NOT flagged. This is the
    whole point: the budget constrains the label axis, not the correlation axis.

  * TS/JS, OTel-JS metrics: metric labels are the keys of the attributes object
    literal (2nd arg) to `.add(v, {..})` / `.record(v, {..})` / `.observe(v, {..})`.
    `span.setAttributes({..})` / `.setAttribute(k, v)` are span attrs — NOT flagged.

CLASSIFICATION (allowlist = cardinality-allowlist.txt, the machine mirror of §5.6):
  * a leading `ksquad.` namespace is stripped before matching; the final dotted
    segment and the `_`-joined form are also tested, so `ksquad.runtime`->`runtime`
    (ALLOW) and `ksquad.user.id`->`user.id` (DENY).
  * DENY (explicit forbidden key) wins over ALLOW and yields its specific code
    (OBS-9 per-actor id / PII, OBS-11 privacy/fingerprint) for a legible message.
  * a bounded-enum ALLOW token (bare or as a final segment) passes.
  * anything else fails as "out-of-allowlist" (catches novel id labels too, e.g.
    a fresh `agent.id`).

This is a source lint — a heuristic over idiomatic emit sites, not a Go/TS AST.
Its detection is proven with teeth by cardinality-budget-check.py (the §13.6
falsification bench): planted violations MUST turn it RED; legal exemplar/span/
resource placements of the very same ids MUST stay GREEN.

Usage:
    cardinality-lint.py [PATH ...]            # scan given files/dirs (default: .)
    cardinality-lint.py --allowlist FILE ...  # override allowlist location
    cardinality-lint.py --self-test           # scan the built-in fixtures only

Exit 0 = clean (no metric label outside the budget). Exit 1 = at least one
violation (printed file:line: key: reason). Exit 2 = usage / config error.
stdlib only.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ALLOWLIST = os.path.join(HERE, "cardinality-allowlist.txt")

# Aliases under which the OTel *metric* package is imported. Idiomatic default is
# `metric`; a repo may alias it. `resource.WithAttributes` is intentionally absent
# — resource attributes are NOT metric labels and legitimately carry scope names.
METRIC_ALIASES = ("metric", "otelmetric", "apimetric", "metricapi", "meterapi")

GO_EXT = (".go",)
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs")
SKIP_DIRS = {"vendor", "node_modules", ".git", "bin", "dist", "build", "__pycache__", "testdata"}


# --------------------------------------------------------------------------- #
# Allowlist loading                                                           #
# --------------------------------------------------------------------------- #
def load_allowlist(path):
    """Parse cardinality-allowlist.txt -> (allow:set[str], deny:dict[str,(code,reason)])."""
    allow, deny = set(), {}
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            verb = parts[0].upper()
            if verb == "ALLOW" and len(parts) == 2:
                allow.add(parts[1].strip())
            elif verb == "DENY" and len(parts) == 2:
                rest = parts[1].split(None, 2)
                key = rest[0]
                code = rest[1] if len(rest) > 1 else "OBS-9"
                reason = rest[2] if len(rest) > 2 else "forbidden as a metric label (§5.6)"
                deny[key] = (code, reason)
            else:
                raise ValueError("cardinality-allowlist.txt: unparseable line: %r" % raw)
    if not allow:
        raise ValueError("cardinality-allowlist.txt: no ALLOW tokens loaded")
    return allow, deny


def classify(key, allow, deny):
    """Return None if the key is a legal metric label, else (code, reason)."""
    k = key.strip()
    stripped = k[len("ksquad."):] if k.startswith("ksquad.") else k
    exact = {k, stripped, stripped.replace(".", "_")}
    # DENY wins, matched on the exact/stripped key (not the final segment, to
    # avoid over-matching a bounded label that merely ends in a denied word).
    for cand in exact:
        if cand in deny:
            return deny[cand]
    # ALLOW: bare token, stripped key, final dotted segment, or `_`-joined form.
    segments = {stripped, stripped.split(".")[-1], stripped.replace(".", "_")}
    if segments & allow:
        return None
    return ("OBS-CARD", "out-of-allowlist metric label (not in §5.6 budget)")


# --------------------------------------------------------------------------- #
# Extraction — find metric label keys in source text                          #
# --------------------------------------------------------------------------- #
def _balanced(text, open_idx, opener="(", closer=")"):
    """Given index of an opener in text, return the substring inside its match."""
    depth, i, n = 0, open_idx, len(text)
    while i < n:
        c = text[i]
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
        i += 1
    return text[open_idx + 1:]  # unbalanced; scan to EOF


def _lineno(text, idx):
    return text.count("\n", 0, idx) + 1


_GO_METRIC_OPT = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in METRIC_ALIASES) + r")\.WithAttributes\("
)
# attribute.String("k", ..) / attribute.Int64("k", ..) / attribute.Key("k")...
_GO_ATTR_KEY = re.compile(r'attribute\.(?:Key|String|StringSlice|Bool|Int|Int64|Float64)\(\s*"([^"]+)"')

_JS_EMIT = re.compile(r"\.(?:add|record|observe)\s*\(")
_JS_KEY = re.compile(r"""(?:^|[,{])\s*(?:'([^']+)'|"([^"]+)"|([A-Za-z_$][\w$.-]*))\s*:""")


def keys_in_go(text):
    """Yield (key, lineno) for every metric label key emitted in Go source."""
    for m in _GO_METRIC_OPT.finditer(text):
        inner = _balanced(text, m.end() - 1)  # start at the '('
        base = m.end() - 1
        for km in _GO_ATTR_KEY.finditer(inner):
            yield km.group(1), _lineno(text, base + km.start())


def keys_in_js(text):
    """Yield (key, lineno) for every metric label key emitted in TS/JS source."""
    for m in _JS_EMIT.finditer(text):
        # locate the attributes object literal: the first '{' after the value arg,
        # bounded by the emit call's own paren group.
        call_args = _balanced(text, m.end() - 1)
        brace = call_args.find("{")
        if brace == -1:
            continue
        obj = _balanced(call_args, brace, "{", "}")
        base = m.end() - 1 + 1 + brace  # +1 to step past '(' consumed by _balanced
        for km in _JS_KEY.finditer(obj):
            key = km.group(1) or km.group(2) or km.group(3)
            if key is None:
                continue
            yield key, _lineno(text, m.start())  # emit-site line (obj may span lines)


def scan_text(path, text, allow, deny):
    ext = os.path.splitext(path)[1].lower()
    extractor = keys_in_go if ext in GO_EXT else keys_in_js if ext in JS_EXT else None
    if extractor is None:
        return []
    findings = []
    for key, ln in extractor(text):
        verdict = classify(key, allow, deny)
        if verdict is not None:
            code, reason = verdict
            findings.append((path, ln, key, code, reason))
    return findings


# --------------------------------------------------------------------------- #
# File walking + CLI                                                           #
# --------------------------------------------------------------------------- #
def iter_source_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if os.path.splitext(f)[1].lower() in GO_EXT + JS_EXT:
                    yield os.path.join(root, f)


def scan_paths(paths, allow, deny):
    findings = []
    for fp in iter_source_files(paths):
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        findings.extend(scan_text(fp, text, allow, deny))
    return findings


def main(argv):
    allowlist_path = DEFAULT_ALLOWLIST
    paths, i, self_test = [], 0, False
    while i < len(argv):
        a = argv[i]
        if a == "--allowlist":
            i += 1
            allowlist_path = argv[i]
        elif a == "--self-test":
            self_test = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            paths.append(a)
        i += 1
    if self_test:
        print("cardinality-lint: --self-test is handled by cardinality-budget-check.py", file=sys.stderr)
        return 2
    if not paths:
        paths = ["."]
    try:
        allow, deny = load_allowlist(allowlist_path)
    except (OSError, ValueError) as e:
        print("cardinality-lint: %s" % e, file=sys.stderr)
        return 2

    findings = scan_paths(paths, allow, deny)
    for path, ln, key, code, reason in sorted(findings):
        print("%s:%d: [%s] metric label %r: %s" % (path, ln, code, key, reason), file=sys.stderr)
    if findings:
        print("\ncardinality-lint: FAIL — %d metric label(s) outside the §5.6 budget" % len(findings),
              file=sys.stderr)
        return 1
    print("cardinality-lint: OK — every metric label is within the §5.6 budget")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
