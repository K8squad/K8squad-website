#!/usr/bin/env python3
"""Falsification bench for Story 9.3 / ISI-2252 — access-mode behavior documented
and schema-validated per StorageClass (arch §9.4).

helm-free, stdlib only. Reads the PINNED chart snapshot
(docs/bmad/spikes/bench/helm-chart-isi2149/, k8squad chart) and proves the three
teeth of the story hold on the SHIPPED artifact, then mutates each to prove the
detector flips RED:

  C1  values.schema.json validates storage.workspace.accessMode against the enum
      {ReadWriteOnce, ReadWriteMany, ReadWriteOncePod} — RWO/RWX/RWOP pass, a typo
      or an off-list mode (ReadWriteMnay / rwx / ReadOnlyMany) FAILS the schema.
  C2  The chart WARNS on RWX (does not reject it): NOTES.txt renders a WARNING
      only when accessMode=ReadWriteMany, and RWX still passes the schema (valid
      enum member — warned, never failed). RWO renders no warning.
  C3  README documents access-mode behavior per §9.4: RWO is the default, RWX is
      optional and honored ONLY when the class supports it, and volume expansion +
      snapshots are class-dependent.

Run: python3 docs/bmad/spikes/bench/access-mode-check.py   (exit 0 = all teeth hold)
"""
import json
import re
import sys
from pathlib import Path

CHART = Path(__file__).resolve().parent / "helm-chart-isi2149"
SCHEMA = CHART / "values.schema.json"
NOTES = CHART / "templates" / "NOTES.txt"
README = CHART / "README.md"

EXPECTED_ENUM = {"ReadWriteOnce", "ReadWriteMany", "ReadWriteOncePod"}


# ── tiny faithful models of the two render seams (no helm needed) ──────────────

def schema_accessmode_enum(schema_text):
    """Return the accessMode enum list from a values.schema.json string, or None
    if the field is unconstrained (no enum) — that None is exactly the regression
    (freeform mode) C1 must catch."""
    schema = json.loads(schema_text)
    node = (schema.get("properties", {})
                  .get("storage", {}).get("properties", {})
                  .get("workspace", {}).get("properties", {})
                  .get("accessMode", {}))
    return node.get("enum")  # None when unconstrained


def schema_accepts(schema_text, mode):
    """Model helm's values.schema.json enum validation for accessMode."""
    enum = schema_accessmode_enum(schema_text)
    if enum is None:
        return True  # unconstrained → helm accepts anything (the M2 regression)
    return mode in enum


_COND = re.compile(
    r'\{\{-?\s*if\s+eq\s+\.Values\.storage\.workspace\.accessMode\s+"([^"]+)"\s*-?\}\}'
    r'(.*?)\{\{-?\s*end\s*-?\}\}',
    re.DOTALL,
)


def render_notes(notes_text, mode):
    """Faithfully model the Go-template conditional for the workspace access mode:
    a block guarded on `eq .accessMode "X"` is included iff mode == X. Text outside
    such blocks is always included. Keys on the guard's ACTUAL mode string so a
    mutation that re-points the guard (M4) is caught, not papered over."""
    out = []
    idx = 0
    for m in _COND.finditer(notes_text):
        out.append(notes_text[idx:m.start()])  # always-on text before the block
        if m.group(1) == mode:
            out.append(m.group(2))             # guarded body, only for matching mode
        idx = m.end()
    out.append(notes_text[idx:])
    return "".join(out)


def notes_warns(notes_text, mode):
    return "WARNING" in render_notes(notes_text, mode)


# ── checks (return list of failure strings; empty = GREEN) ────────────────────

def C1(schema_text):
    fails = []
    enum = schema_accessmode_enum(schema_text)
    if enum is None or set(enum) != EXPECTED_ENUM:
        fails.append(f"C1: accessMode enum is {enum!r}, expected {sorted(EXPECTED_ENUM)}")
    for good in EXPECTED_ENUM:
        if not schema_accepts(schema_text, good):
            fails.append(f"C1: valid mode {good!r} rejected by schema")
    for bad in ("ReadWriteMnay", "rwx", "ReadOnlyMany", ""):
        if schema_accepts(schema_text, bad):
            fails.append(f"C1: invalid mode {bad!r} wrongly accepted by schema")
    return fails


def C2(schema_text, notes_text):
    fails = []
    # warns on RWX, not on RWO
    if not notes_warns(notes_text, "ReadWriteMany"):
        fails.append("C2: NOTES does not WARN when accessMode=ReadWriteMany (RWX)")
    if notes_warns(notes_text, "ReadWriteOnce"):
        fails.append("C2: NOTES wrongly WARNs on the RWO default")
    # warned, not failed: RWX must still be a valid schema value
    if not schema_accepts(schema_text, "ReadWriteMany"):
        fails.append("C2: RWX rejected by schema (must be warned, not failed)")
    # the warning must be actionable (mention pre-flight the class)
    warn = render_notes(notes_text, "ReadWriteMany").lower()
    if "pre-flight" not in warn and "preflight" not in warn:
        fails.append("C2: RWX warning does not tell the operator to pre-flight the class")
    return fails


def C3(readme_text):
    fails = []
    low = readme_text.lower()
    # RWO is the default
    if not re.search(r"readwriteonce.*(default|the default)", low) and "rwo) — the default" not in low:
        if "default" not in low or "readwriteonce" not in low:
            fails.append("C3: README does not state ReadWriteOnce is the default")
    # RWX optional, honored ONLY when the class supports it — key on the canonical
    # conditional-support phrasings, not a loose "only"+"support" anywhere.
    RWX_QUALIFIERS = (
        "only where the class supports it",
        "only if supported",
        "gated on your class supporting it",
        "only when the class supports it",
    )
    if "readwritemany" not in low or not any(q in low for q in RWX_QUALIFIERS):
        fails.append("C3: README does not state RWX is optional/only when the class supports it")
    # expansion + snapshots are class-dependent
    if "allowvolumeexpansion" not in low and "volume expansion" not in low:
        fails.append("C3: README does not document volume expansion as class-dependent")
    if "volumesnapshotclass" not in low and "snapshot" not in low:
        fails.append("C3: README does not document snapshots as class-dependent")
    return fails


def run(schema_text, notes_text, readme_text):
    fails = []
    fails += C1(schema_text)
    fails += C2(schema_text, notes_text)
    fails += C3(readme_text)
    return fails


# ── mutation battery — each must be CAUGHT (baseline is GREEN) ─────────────────

MUTATIONS = [
    ("M1 drop RWX from enum (valid mode rejected)",
     lambda s, n, r: (s.replace(', "ReadWriteMany"', ""), n, r), "C1"),
    ("M2 schema freeform accessMode (typo slips through)",
     lambda s, n, r: (re.sub(r'"enum":\s*\[[^\]]*\]', '"minLength": 1', s), n, r), "C1"),
    ("M3 remove RWX warning block from NOTES",
     lambda s, n, r: (s, _COND.sub("", n), r), "C2"),
    ("M4 re-point warning guard to RWO instead of RWX",
     lambda s, n, r: (s, n.replace('"ReadWriteMany" }}', '"ReadWriteOnce" }}'), r), "C2"),
    ("M5 README drops the 'only if supported' RWX qualifier",
     lambda s, n, r: (s, n, r.replace("only where the class supports it", "always available")
                                .replace("only if supported", "always")
                                .replace("gated on your\nclass supporting it", "always available")
                                .replace("gated on your class supporting it", "always available")), "C3"),
    ("M6 README drops expansion+snapshot class-dependence",
     lambda s, n, r: (s, n, re.sub(r"(?is)volume expansion and snapshots.*?point it at\.", "", r)
                                .replace("allowVolumeExpansion", "")
                                .replace("VolumeSnapshotClass", "")
                                .replace("| Volume expansion |", "| |")
                                .replace("| Snapshots |", "| |")), "C3"),
]


def main():
    for p in (SCHEMA, NOTES, README):
        if not p.exists():
            print(f"MISSING artifact: {p}", file=sys.stderr)
            return 2
    schema_text = SCHEMA.read_text()
    notes_text = NOTES.read_text()
    readme_text = README.read_text()

    print("== baseline (shipped chart snapshot) ==")
    base = run(schema_text, notes_text, readme_text)
    if base:
        for f in base:
            print("  RED  ", f)
        print("BASELINE NOT GREEN — the shipped chart does not satisfy §9.4 access-mode teeth")
        return 1
    print("  GREEN — C1 (enum), C2 (warn-on-RWX), C3 (docs) all hold")

    print("== mutation battery (each must be caught) ==")
    ok = True
    for name, mutate, tag in MUTATIONS:
        s2, n2, r2 = mutate(schema_text, notes_text, readme_text)
        fails = run(s2, n2, r2)
        caught = any(f.startswith(tag) for f in fails)
        print(f"  {'caught' if caught else 'MISSED'} [{tag}] {name}")
        if not caught:
            ok = False
            for f in fails:
                print("       ->", f)
    if not ok:
        print("A MUTATION SLIPPED THROUGH — detector lacks teeth")
        return 1
    print("ALL TEETH HOLD (baseline GREEN, all mutations caught)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
