#!/usr/bin/env python3
"""Story 9.2 (ISI-2251) falsification — EVERY PVC's StorageClass comes from values,
never the cluster default: the CNPG Postgres `Cluster` PVC (and optional WAL PVC), the
per-Project workspace PVCs the operator stamps, and the NATS/JetStream file store all
take their StorageClass from `storage.*`, per-family override falling back to a global
`storage.storageClassName`; an unset class FAILS THE INSTALL FAST (arch §16.2 / §9.4,
Theme L / FR-L2; chart impl = ISI-2149, `feat(helm): parameterized Gateway API exposure
+ explicit StorageClass`, snapshot k8squad@5e6442d).

WHY THIS BENCH EXISTS
---------------------
On a cluster whose *default* StorageClass is unsuitable — wrong provisioner, wrong
performance tier, no `allowVolumeExpansion`, no RWX, or simply not marked default at all —
a chart that silently relies on the cluster default binds KSquad's data-of-record (the
CNPG Postgres store, ADR-001/§4) and every Project workspace to storage the operator never
chose. `kubectl get pvc` is green; the PVCs are Bound; and the store is on the wrong disk
(or Pending forever with no default class). Four ways a plausible-but-wrong chart breaks
the acceptance, NONE caught by "it renders / the PVC is Bound":

  1. OMITTED-CLASS — the CNPG `Cluster` (or a workspace/NATS PVC) omits `storageClass`
     entirely, so Kubernetes falls back to the cluster-default StorageClass. §16.2: the
     class is a REQUIRED values input, stamped on every PVC, never omitted.

  2. HARDCODED-CLASS — `storageClass` frozen to a literal ("standard", "gp2"). It renders,
     but only the author's class; the operator's `storage.postgres.storageClassName=ceph-rbd`
     is ignored. §16.2: sourced from values, never a hardcode.

  3. NO-OVERRIDE / NO-FALLBACK — the per-family override (`storage.postgres.storageClassName`)
     is ignored and only the global is used, OR the global fallback is dropped so a family
     left empty resolves empty and a legitimate global-only install fails. §16.2: resolution
     is `family || global`, both directions.

  4. SILENT-DEFAULT — an unset class does NOT fail the install; the chart defaults it to a
     literal or omits it and lets Kubernetes pick. §16.2: unset MUST fail fast with a clear
     "never relies on the cluster-default StorageClass" error, for EACH PVC family.

Two falsification layers, both stdlib-only (`python3 storage-class-check.py`):

  LAYER A — model-based mutation battery. A faithful mini-renderer of the chart's storage
  templates + `ksquad.validate` fail-fast (mirrors postgres-cluster.yaml, operator-config.yaml,
  _helpers.tpl storageClass.* + validate). Six checks C1–C6 ↔ the acceptance. A battery of
  broken-chart mutations; EACH must be caught by a designated check going RED, and the
  §16.2-conformant baseline is GREEN on all six. Differential checks render two distinct
  value profiles (A: per-family overrides + WAL on; B: global-only fallback + WAL off) and
  assert the rendered class TRACKS the input — the teeth against hardcoding/omission that
  "it renders once" cannot give.

  LAYER B — file-grounded pass over the PINNED real chart snapshot
  (`helm-chart-isi2149/`, k8squad@5e6442d). Asserts the SHIPPED templates satisfy each
  invariant, and text-mutates each real template and asserts the detector flips RED, so the
  file-grounded checks have teeth on the real artifact, not just the model.

Exit non-zero if any mutation survives (Layer A), any real-chart invariant is violated, or
any file-grounded detector fails to flip (Layer B).
"""
import copy
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "helm-chart-isi2149")


# ══════════════════════════════════════════════════════════════════════════════════════
#  Value profiles — two distinct installs. Differential checks assert output tracks input.
#  Profile A exercises per-family OVERRIDES (each family a distinct class ≠ the global) plus
#  the optional WAL volume; profile B exercises the GLOBAL FALLBACK (families empty → global)
#  with WAL off. Between them every storage field a mutation might freeze/omit differs.
# ══════════════════════════════════════════════════════════════════════════════════════

def profile(name):
    if name == "A":
        return {
            "release": "ksq",
            "storage": {
                "storageClassName": "glob-a",                       # global fallback
                "postgres": {"storageClassName": "pg-a",            # per-family OVERRIDE
                             "size": "10Gi", "instances": 1,
                             "walStorage": {"enabled": True, "size": "2Gi"}},
                "workspace": {"storageClassName": "ws-a",           # per-family OVERRIDE
                              "accessMode": "ReadWriteOnce", "size": "20Gi"},
                "nats": {"storageClassName": "nats-a", "size": "5Gi"},
            },
        }
    # profile B — families empty → resolve to the (distinct) global; WAL off
    return {
        "release": "ksq",
        "storage": {
            "storageClassName": "glob-b",                           # global fallback
            "postgres": {"storageClassName": "",                    # empty → glob-b
                         "size": "20Gi", "instances": 3,
                         "walStorage": {"enabled": False, "size": "4Gi"}},
            "workspace": {"storageClassName": "",                   # empty → glob-b
                          "accessMode": "ReadWriteMany", "size": "40Gi"},
            "nats": {"storageClassName": "nats-b", "size": "8Gi"},
        },
    }


# Expected resolved class per family, per profile (family || global).
EXPECT = {
    "A": {"postgres": "pg-a",  "workspace": "ws-a",  "nats": "nats-a"},
    "B": {"postgres": "glob-b", "workspace": "glob-b", "nats": "nats-b"},
}


class FailFast(Exception):
    """Models a Helm `{{ fail }}` — install aborts before any object is applied."""


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER A — faithful mini-renderer of the chart's storage templates + validate.
#  Mirrors deploy/helm/ksquad/templates/{postgres-cluster,operator-config}.yaml +
#  _helpers.tpl (ksquad.storageClass.* + the storage half of ksquad.validate).
# ══════════════════════════════════════════════════════════════════════════════════════

class Chart:
    """Baseline §16.2-conformant renderer. render() -> list of k8s objects (dicts)."""

    def fullname(self, v):
        return v["release"]

    # --- ksquad.storageClass.<family>: per-family override, else the global value ---
    def storage_class(self, v, family):
        return v["storage"][family]["storageClassName"] or v["storage"]["storageClassName"]

    # --- storage half of ksquad.validate (fail-fast; runs on every render) ---
    def validate(self, v):
        for fam in ("postgres", "workspace", "nats"):
            if not self.storage_class(v, fam):
                raise FailFast(
                    f"storage.storageClassName (or storage.{fam}.storageClassName) is REQUIRED "
                    f"— KSquad never relies on the cluster-default StorageClass (§16.2)")

    # --- render ---
    def render(self, v):
        self.validate(v)
        return [self.render_postgres(v), self.render_operator_config(v)]

    def render_postgres(self, v):
        sc = self.storage_class(v, "postgres")
        pg = v["storage"]["postgres"]
        obj = {
            "kind": "Cluster", "apiVersion": "postgresql.cnpg.io/v1",
            "name": self.fullname(v) + "-pg",
            "instances": pg["instances"],
            "storage": {"size": pg["size"], "storageClass": sc},
        }
        if pg["walStorage"]["enabled"]:
            # WAL PVC uses the SAME resolved postgres class — never omitted, never a
            # second uncontrolled default-class PVC.
            obj["walStorage"] = {"size": pg["walStorage"]["size"], "storageClass": sc}
        return obj

    def render_operator_config(self, v):
        # ConfigMap the operator reads to stamp every per-Project workspace PVC (§9.4),
        # plus reference values for the Postgres/NATS PVCs.
        return {
            "kind": "ConfigMap", "name": self.fullname(v) + "-storage",
            "data": {
                "workspace.storageClassName": self.storage_class(v, "workspace"),
                "workspace.accessMode": v["storage"]["workspace"]["accessMode"],
                "workspace.size": v["storage"]["workspace"]["size"],
                "postgres.storageClassName": self.storage_class(v, "postgres"),
                "nats.storageClassName": self.storage_class(v, "nats"),
                "nats.size": v["storage"]["nats"]["size"],
            },
        }


# small render helpers used by checks -----------------------------------------------------

def try_render(chart, v):
    """Return (objs, failfast_msg_or_None)."""
    try:
        return chart.render(copy.deepcopy(v)), None
    except FailFast as e:
        return None, str(e)


def find(objs, kind):
    for o in objs or []:
        if o["kind"] == kind:
            return o
    return None


# a StorageClass value is only "real" if it is a non-empty string that is NOT the k8s
# cluster-default sentinel (None/"" both mean "let Kubernetes pick the default class").
def is_real_class(sc):
    return isinstance(sc, str) and sc != ""


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER A — checks C1–C6 (each returns (ok: bool, detail: str)). Differential where an
#  omission/hardcode would otherwise slip through.
# ══════════════════════════════════════════════════════════════════════════════════════

def C1_postgres_pvc_class_from_values(chart):
    """CNPG `Cluster` PVC StorageClass is set FROM VALUES (never omitted → never the
    cluster default; never a hardcoded literal). Differential: A=pg-a (override),
    B=glob-b (fallback)."""
    for prof in ("A", "B"):
        objs, e = try_render(chart, profile(prof))
        if e:
            return False, f"[{prof}] render failed: {e}"
        cl = find(objs, "Cluster")
        if not cl:
            return False, f"[{prof}] no CNPG Cluster rendered"
        sc = cl["storage"].get("storageClass")
        if not is_real_class(sc):
            return False, f"[{prof}] CNPG Cluster storageClass omitted/empty ({sc!r}) — falls back to the cluster default"
        if sc != EXPECT[prof]["postgres"]:
            return False, f"[{prof}] CNPG storageClass {sc!r} does not track values (want {EXPECT[prof]['postgres']!r}) — hardcoded/frozen"
    return True, "CNPG Cluster PVC storageClass tracks values (A=pg-a override, B=glob-b fallback)"


def C2_workspace_class_to_operator(chart):
    """The workspace StorageClass (for the operator-stamped per-Project PVCs, §9.4) is
    handed to the operator via the ConfigMap FROM VALUES, alongside accessMode + size.
    Differential: A=ws-a, B=glob-b."""
    for prof in ("A", "B"):
        objs, e = try_render(chart, profile(prof))
        if e:
            return False, f"[{prof}] render failed: {e}"
        cm = find(objs, "ConfigMap")
        if not cm:
            return False, f"[{prof}] no operator storage ConfigMap rendered"
        sc = cm["data"].get("workspace.storageClassName")
        if not is_real_class(sc):
            return False, f"[{prof}] workspace.storageClassName omitted/empty ({sc!r}) — operator would stamp the cluster default onto every Project PVC"
        if sc != EXPECT[prof]["workspace"]:
            return False, f"[{prof}] workspace.storageClassName {sc!r} does not track values (want {EXPECT[prof]['workspace']!r})"
        # accessMode + size must ride along so the operator can build a complete PVC spec
        if not cm["data"].get("workspace.accessMode") or not cm["data"].get("workspace.size"):
            return False, f"[{prof}] operator ConfigMap missing workspace.accessMode/size"
    # accessMode is itself values-driven (A=RWO, B=RWX) — not frozen
    a = find(try_render(chart, profile("A"))[0], "ConfigMap")["data"]["workspace.accessMode"]
    b = find(try_render(chart, profile("B"))[0], "ConfigMap")["data"]["workspace.accessMode"]
    if a != "ReadWriteOnce" or b != "ReadWriteMany":
        return False, f"workspace.accessMode not values-driven (A={a}, B={b})"
    return True, "workspace class+accessMode+size handed to operator, track values (A=ws-a/RWO, B=glob-b/RWX)"


def C3_nats_class_from_values(chart):
    """The NATS/JetStream file-store StorageClass is surfaced FROM VALUES (never the
    cluster default). Differential: A=nats-a, B=nats-b."""
    for prof in ("A", "B"):
        objs, e = try_render(chart, profile(prof))
        if e:
            return False, f"[{prof}] render failed: {e}"
        cm = find(objs, "ConfigMap")
        sc = cm["data"].get("nats.storageClassName")
        if not is_real_class(sc):
            return False, f"[{prof}] nats.storageClassName omitted/empty ({sc!r})"
        if sc != EXPECT[prof]["nats"]:
            return False, f"[{prof}] nats.storageClassName {sc!r} does not track values (want {EXPECT[prof]['nats']!r})"
    return True, "NATS storageClass tracks values (A=nats-a, B=nats-b)"


def C4_override_and_fallback(chart):
    """Resolution is `family || global`, BOTH directions: a per-family override BEATS the
    global (profile A: postgres=pg-a ≠ global glob-a), and an empty family FALLS BACK to
    the global (profile B: postgres empty → glob-b). Neither hardcodes the family to the
    global nor drops the global fallback."""
    a, ea = try_render(chart, profile("A"))
    if ea:
        return False, f"[A] render failed: {ea}"
    # override wins: postgres/workspace use their family value, not the global glob-a
    pg_a = find(a, "Cluster")["storage"]["storageClass"]
    ws_a = find(a, "ConfigMap")["data"]["workspace.storageClassName"]
    if pg_a == "glob-a" or ws_a == "glob-a":
        return False, f"per-family override IGNORED — postgres={pg_a!r}, workspace={ws_a!r} fell through to the global (glob-a)"
    if pg_a != "pg-a" or ws_a != "ws-a":
        return False, f"per-family override not applied (postgres={pg_a!r}, workspace={ws_a!r})"
    # fallback works: profile B families empty → resolve to the global glob-b
    b, eb = try_render(chart, profile("B"))
    if eb:
        return False, f"[B] global-only install failed — global fallback dropped: {eb}"
    pg_b = find(b, "Cluster")["storage"]["storageClass"]
    ws_b = find(b, "ConfigMap")["data"]["workspace.storageClassName"]
    if pg_b != "glob-b" or ws_b != "glob-b":
        return False, f"global fallback broken — postgres={pg_b!r}, workspace={ws_b!r}, want glob-b"
    return True, "override beats global (A→pg-a/ws-a) and empty family falls back to global (B→glob-b)"


def C5_fail_fast_when_class_unset(chart):
    """An unset StorageClass FAILS THE INSTALL FAST — never a silent default — and the
    guard is PER FAMILY: leaving any one of postgres/workspace/nats with no class (and no
    global) aborts the render with the cluster-default error, rendering nothing."""
    # (a) nothing set at all → fail fast, render nothing
    v = profile("A")
    v["storage"]["storageClassName"] = ""
    for fam in ("postgres", "workspace", "nats"):
        v["storage"][fam]["storageClassName"] = ""
    objs, e = try_render(chart, v)
    if objs is not None:
        return False, "all-unset storage did NOT fail — chart rendered PVCs against the cluster default"
    if "cluster-default" not in e:
        return False, f"failed, but not on the cluster-default guard: {e}"
    # (b) per-family teeth: global empty, only ONE family left empty → must fail on THAT family
    for empty in ("postgres", "workspace", "nats"):
        v = profile("A")
        v["storage"]["storageClassName"] = ""        # kill the global fallback
        for fam in ("postgres", "workspace", "nats"):
            v["storage"][fam]["storageClassName"] = "set-" + fam
        v["storage"][empty]["storageClassName"] = ""  # ...except this one
        objs, e = try_render(chart, v)
        if objs is not None:
            return False, f"{empty} left classless did NOT fail fast — silent cluster-default for {empty} PVC(s)"
        if empty not in e:
            return False, f"unset {empty} failed, but the error names the wrong family: {e}"
    return True, "unset class fails fast per family (postgres/workspace/nats), no silent cluster-default"


def C6_wal_pvc_shares_class(chart):
    """The optional CNPG WAL volume is values-driven and, when enabled, its PVC uses the
    SAME resolved postgres class — never omitted (a second cluster-default PVC), never a
    different hardcoded class. Profile A (walStorage.enabled) renders it; B does not."""
    a, ea = try_render(chart, profile("A"))
    b, eb = try_render(chart, profile("B"))
    if ea or eb:
        return False, f"render failed: {ea or eb}"
    cla, clb = find(a, "Cluster"), find(b, "Cluster")
    if "walStorage" not in cla:
        return False, "profile A (walStorage.enabled) rendered NO walStorage — not values-driven"
    wal_sc = cla["walStorage"].get("storageClass")
    main_sc = cla["storage"]["storageClass"]
    if not is_real_class(wal_sc):
        return False, f"WAL PVC storageClass omitted/empty ({wal_sc!r}) — a second cluster-default PVC"
    if wal_sc != main_sc:
        return False, f"WAL PVC storageClass {wal_sc!r} != main postgres class {main_sc!r} (drifted/hardcoded)"
    if "walStorage" in clb:
        return False, "profile B (walStorage disabled) STILL rendered a WAL volume (not values-driven)"
    return True, "WAL PVC present iff enabled and shares the resolved postgres class (values-driven)"


CHECKS = [
    ("C1", "CNPG Postgres PVC class from values", C1_postgres_pvc_class_from_values),
    ("C2", "workspace class handed to operator",  C2_workspace_class_to_operator),
    ("C3", "NATS class from values",              C3_nats_class_from_values),
    ("C4", "override beats global, global fallback", C4_override_and_fallback),
    ("C5", "fail-fast on unset (per family)",     C5_fail_fast_when_class_unset),
    ("C6", "WAL PVC shares postgres class",       C6_wal_pvc_shares_class),
]


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER A — mutations. Each is a broken Chart; the `caught_by` check(s) MUST go RED and
#  the baseline MUST be GREEN on all. A mutation no check catches = a hole in the bench.
# ══════════════════════════════════════════════════════════════════════════════════════

class M_HardcodePostgresClass(Chart):
    """CNPG storageClass frozen to a literal, ignoring values → C1."""
    def render_postgres(self, v):
        obj = Chart.render_postgres(self, v)
        obj["storage"]["storageClass"] = "standard"
        if "walStorage" in obj:
            obj["walStorage"]["storageClass"] = "standard"
        return obj

class M_OmitPostgresClass(Chart):
    """CNPG omits storageClass entirely → Kubernetes uses the cluster default → C1."""
    def render_postgres(self, v):
        obj = Chart.render_postgres(self, v)
        obj["storage"].pop("storageClass", None)
        obj["storage"]["storageClass"] = None
        return obj

class M_IgnoreOverride(Chart):
    """Per-family override ignored — always the global value → C4."""
    def storage_class(self, v, family):
        return v["storage"]["storageClassName"]     # global only, override dropped

class M_SilentDefaultOnUnset(Chart):
    """Unset class silently defaults to a literal instead of failing → C5."""
    def storage_class(self, v, family):
        return (v["storage"][family]["storageClassName"]
                or v["storage"]["storageClassName"]
                or "standard")                       # silent cluster-default stand-in

class M_SkipStorageValidate(Chart):
    """validate no longer guards storage; unset renders an omitted-class PVC anyway → C5."""
    def validate(self, v):
        return                                        # storage fail-fast REMOVED
    def render_postgres(self, v):
        sc = self.storage_class(v, "postgres")
        pg = v["storage"]["postgres"]
        return {"kind": "Cluster", "apiVersion": "postgresql.cnpg.io/v1",
                "name": self.fullname(v) + "-pg", "instances": pg["instances"],
                "storage": {"size": pg["size"], "storageClass": (sc or None)}}

class M_WorkspaceClassMissing(Chart):
    """Operator ConfigMap drops workspace.storageClassName → operator stamps the cluster
    default onto every Project PVC → C2."""
    def render_operator_config(self, v):
        cm = Chart.render_operator_config(self, v)
        cm["data"]["workspace.storageClassName"] = ""
        return cm

class M_HardcodeWorkspaceClass(Chart):
    """workspace.storageClassName frozen to a literal in the ConfigMap → C2."""
    def render_operator_config(self, v):
        cm = Chart.render_operator_config(self, v)
        cm["data"]["workspace.storageClassName"] = "gp2"
        return cm

class M_OmitNatsClass(Chart):
    """NATS class dropped from the ConfigMap → NATS file store on the cluster default → C3."""
    def render_operator_config(self, v):
        cm = Chart.render_operator_config(self, v)
        cm["data"]["nats.storageClassName"] = ""
        return cm

class M_WalOmitsClass(Chart):
    """WAL PVC omits storageClass while the main PVC sets it → second default-class PVC → C6."""
    def render_postgres(self, v):
        obj = Chart.render_postgres(self, v)
        if "walStorage" in obj:
            obj["walStorage"]["storageClass"] = None
        return obj

class M_WalDifferentClass(Chart):
    """WAL PVC uses a different hardcoded class, drifting from the main PVC → C6."""
    def render_postgres(self, v):
        obj = Chart.render_postgres(self, v)
        if "walStorage" in obj:
            obj["walStorage"]["storageClass"] = "slow-hdd"
        return obj

class M_DropGlobalFallback(Chart):
    """Resolution keeps only the family value, dropping the global fallback — a global-only
    install (profile B) then resolves empty and fails a legitimate config → C4."""
    def storage_class(self, v, family):
        return v["storage"][family]["storageClassName"]   # global fallback dropped


MUTATIONS = [
    ("M1  hardcode CNPG storageClass",      M_HardcodePostgresClass(), {"C1"}),
    ("M2  omit CNPG storageClass",          M_OmitPostgresClass(),     {"C1"}),
    ("M3  ignore per-family override",      M_IgnoreOverride(),        {"C4"}),
    ("M4  silent default on unset",         M_SilentDefaultOnUnset(),  {"C5"}),
    ("M5  skip storage validate",           M_SkipStorageValidate(),   {"C5"}),
    ("M6  workspace class missing (op cfg)",M_WorkspaceClassMissing(), {"C2"}),
    ("M7  hardcode workspace class",        M_HardcodeWorkspaceClass(),{"C2"}),
    ("M8  omit NATS class",                 M_OmitNatsClass(),         {"C3"}),
    ("M9  WAL omits storageClass",          M_WalOmitsClass(),         {"C6"}),
    ("M10 WAL different hardcoded class",   M_WalDifferentClass(),     {"C6"}),
    ("M11 drop global fallback",            M_DropGlobalFallback(),    {"C4"}),
]


def run_layer_a():
    print("=" * 92)
    print("LAYER A — model-based mutation battery (storage render + fail-fast validate)")
    print("=" * 92)
    baseline = Chart()
    print("\nBaseline (§16.2-conformant chart) — every check must be GREEN:")
    all_green = True
    for cid, desc, fn in CHECKS:
        ok, detail = fn(baseline)
        all_green &= ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid} {desc:<40} — {detail}")
    if not all_green:
        print("\n✗ BASELINE FAILED — the conformant chart model does not pass its own checks.")
        return False

    print("\nMutations — each must be CAUGHT (≥1 designated check flips RED):")
    print("  " + " ".join(f"{c:>4}" for c, _, _ in CHECKS))
    ok_all = True
    for label, chart, expect in MUTATIONS:
        row, caught = [], False
        for cid, _, fn in CHECKS:
            try:
                passed, _ = fn(chart)
            except Exception:                          # a mutation that crashes a check = caught
                passed = False
            red = not passed
            if red and cid in expect:
                caught = True
            row.append(" RED" if red else "  . ")
        status = "caught" if caught else "SURVIVED"
        ok_all &= caught
        print(f"  {' '.join(f'{c:>4}' for c in row)}   {label:<34} expect{sorted(expect)} -> {status}")
        if not caught:
            print(f"       ✗ mutation SURVIVED — no expected check {sorted(expect)} went RED")
    return ok_all


# ══════════════════════════════════════════════════════════════════════════════════════
#  LAYER B — file-grounded pass over the pinned real chart snapshot. Each detector must
#  (i) PASS on the shipped template text and (ii) FLIP when the template is text-mutated,
#  so the file-grounded checks have teeth on the real artifact, not just the model.
# ══════════════════════════════════════════════════════════════════════════════════════

def read(rel):
    with open(os.path.join(SNAP, rel), encoding="utf-8") as f:
        return f.read()


def det_postgres_class_from_values(texts):
    """postgres-cluster.yaml sources the CNPG PVC storageClass from the storageClass helper
    include (a $sc var), never a literal, never omitted."""
    t = texts["templates/postgres-cluster.yaml"]
    resolves = re.search(r'\$sc\s*:=\s*include "ksquad\.storageClass\.postgres"', t)
    stamps = re.search(r'storageClass:\s*\{\{\s*\$sc\s*\|\s*quote\s*\}\}', t)
    return bool(resolves and stamps)


def det_workspace_class_from_values(texts):
    """operator-config.yaml sources workspace.storageClassName from the helper include."""
    t = texts["templates/operator-config.yaml"]
    return bool(re.search(
        r'workspace\.storageClassName:\s*\{\{\s*include "ksquad\.storageClass\.workspace" \.\s*\|\s*quote\s*\}\}', t))


def det_nats_class_from_values(texts):
    """operator-config.yaml surfaces nats.storageClassName from the helper include."""
    t = texts["templates/operator-config.yaml"]
    return bool(re.search(
        r'nats\.storageClassName:\s*\{\{\s*include "ksquad\.storageClass\.nats" \.\s*\|\s*quote\s*\}\}', t))


def det_nats_pvc_class_from_values(texts):
    """nats.yaml — the SHIPPED JetStream StatefulSet — sources the real PVC storageClass
    from the helper include (a $sc var), never a literal, never omitted. FG3's operator-
    config assertion only covers the reference copy; this asserts the live PVC stamper so a
    regression on nats.yaml's volumeClaimTemplate can't leave FG3 GREEN (ISI-2648)."""
    t = texts["templates/nats.yaml"]
    resolves = re.search(r'\$sc\s*:=\s*include "ksquad\.storageClass\.nats" \.', t)
    stamps = re.search(r'storageClassName:\s*\{\{\s*\$sc\s*\|\s*quote\s*\}\}', t)
    return bool(resolves and stamps)


def det_resolution_family_or_global(texts):
    """_helpers.tpl resolves each family as `family | default global` — the override-then-
    fallback chain (checked on the postgres helper; workspace/nats mirror it)."""
    t = texts["templates/_helpers.tpl"]
    return bool(re.search(
        r'\.Values\.storage\.postgres\.storageClassName\s*\|\s*default\s+\.Values\.storage\.storageClassName', t))


def det_storage_failfast(texts):
    """ksquad.validate fails fast when a resolved family class is empty, with the
    never-cluster-default message — for the postgres family (workspace/nats mirror it)."""
    t = texts["templates/_helpers.tpl"]
    return bool(re.search(r'not \(include "ksquad\.storageClass\.postgres" \.\)', t)
                and re.search(r'never relies on the cluster-default StorageClass', t))


def det_wal_shares_class(texts):
    """postgres-cluster.yaml WAL block, when enabled, stamps the SAME $sc on the WAL PVC."""
    t = texts["templates/postgres-cluster.yaml"]
    m = re.search(
        r'if \.Values\.storage\.postgres\.walStorage\.enabled.*?walStorage:.*?'
        r'storageClass:\s*\{\{\s*\$sc\s*\|\s*quote\s*\}\}',
        t, re.S)
    return bool(m)


FG_DETECTORS = [
    ("FG1 CNPG PVC storageClass from values", "templates/postgres-cluster.yaml",
     det_postgres_class_from_values,
     ('$sc := include "ksquad.storageClass.postgres" .', '$sc := "standard"')),
    ("FG2 workspace class from values",       "templates/operator-config.yaml",
     det_workspace_class_from_values,
     ('workspace.storageClassName: {{ include "ksquad.storageClass.workspace" . | quote }}',
      'workspace.storageClassName: "gp2"')),
    ("FG3 NATS class from values",            "templates/operator-config.yaml",
     det_nats_class_from_values,
     ('nats.storageClassName: {{ include "ksquad.storageClass.nats" . | quote }}',
      'nats.storageClassName: "gp2"')),
    ("FG3b NATS PVC stamper from values",     "templates/nats.yaml",
     det_nats_pvc_class_from_values,
     ('storageClassName: {{ $sc | quote }}',
      'storageClassName: "gp2"')),
    ("FG4 resolution family|default global",  "templates/_helpers.tpl",
     det_resolution_family_or_global,
     ('.Values.storage.postgres.storageClassName | default .Values.storage.storageClassName',
      '.Values.storage.postgres.storageClassName')),
    ("FG5 fail-fast on unset storageClass",   "templates/_helpers.tpl",
     det_storage_failfast,
     ('not (include "ksquad.storageClass.postgres" .)',
      '(include "ksquad.storageClass.postgres" .)')),
    ("FG6 WAL PVC shares postgres class",     "templates/postgres-cluster.yaml",
     det_wal_shares_class,
     ('size: {{ .Values.storage.postgres.walStorage.size | quote }}\n    storageClass: {{ $sc | quote }}',
      'size: {{ .Values.storage.postgres.walStorage.size | quote }}\n    storageClass: "standard"')),
]


def run_layer_b():
    print("\n" + "=" * 92)
    print("LAYER B — file-grounded pass over pinned real chart (helm-chart-isi2149/, k8squad@5e6442d)")
    print("=" * 92)
    names = ["templates/postgres-cluster.yaml", "templates/operator-config.yaml",
             "templates/_helpers.tpl", "templates/nats.yaml"]
    try:
        texts = {n: read(n) for n in names}
    except FileNotFoundError as e:
        print(f"  ✗ pinned chart snapshot missing: {e}")
        return False

    ok_all = True
    for label, tgt, det, (find_s, repl_s) in FG_DETECTORS:
        shipped = det(texts)
        mutated = dict(texts)
        if find_s in mutated[tgt]:
            mutated[tgt] = mutated[tgt].replace(find_s, repl_s, 1)
            flipped = not det(mutated)
        else:
            flipped = False
            print(f"  (note) mutation anchor {find_s!r} not found in {tgt}")
        teeth = shipped and flipped
        ok_all &= teeth
        print(f"  [{'PASS' if teeth else 'FAIL'}] {label:<40} shipped={'ok' if shipped else 'VIOLATED'}  "
              f"detector-flips-on-mutation={'yes' if flipped else 'NO'}")
    return ok_all


# ══════════════════════════════════════════════════════════════════════════════════════

def main():
    a = run_layer_a()
    b = run_layer_b()
    print("\n" + "=" * 92)
    if a and b:
        print("✓ ALL GREEN — baseline passes C1–C6; all 11 mutations caught; 7 file-grounded "
              "detectors pass on the shipped chart and have teeth. Story 9.2 acceptance is falsifiable.")
        return 0
    print("✗ FAILURES ABOVE — see RED / SURVIVED / VIOLATED rows.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
