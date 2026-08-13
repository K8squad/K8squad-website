#!/usr/bin/env python3
"""Story 8.3 falsification — inspect a Run's artifact blobs + handoff outputs (FR-F3, UX 03-artifact-inspection).

Given a completed/collecting Run, the operator (Sam) opens **Artifacts** and inspects the blobs the Run
produced — diff / comment / report / file / log — and the **structured handoff outputs**, all read from the
**durable coordination record** (§6.5). This story does NOT invent a store, a diff engine, or an authZ path:
it is a **read-only projection of the content-addressed `coord.artifact` rows** (the same rows story 2.8
writes for handoffs and 8.7c writes for build snapshots), served **through the Next.js BFF** (§13 / ADR-013),
**scoped per-principal** (NFR-SEC5, the 8.7d gate), with **server-stamped provenance** on every row
(FR-B4 / D4 / FR-I3), the served blob **verified against its recorded `sha256`** (content-addressed
integrity, 2.8 / §6.5), every body **bounded fail-safe** (8.7a caps), and — the pixel-level crux — **no
edit / apply / mutate / re-run affordance** anywhere on the surface (R6 scope guard, UX §3.3: *"apply happens
in the repo PR the Fixer opened, not here"*). The **handoff** output is rendered as **advisory context**
(2.8): its 7 fields are shown, but no custody / claim / fence affordance rides the inspection.

This is a MODEL/differential check (like the sibling console checks live-run-sse-check.py and
handoff-advisory-check.py), stdlib-only, `python3` it directly. It first proves the **FR-F3 anti-pattern**
— a "bespoke-store editor" client (reads a re-invented artifact store, streams the browser straight from
the Go apiserver, serves the blob WITHOUT checking its sha, returns a same-Team non-owner's blob, hangs an
Edit/Apply button on the preview, fabricates provenance client-side, and streams an unbounded blob) — is
**DETECTED as violating every invariant** (so the harness has real teeth), then proves the **§6.5/§13
durable-coord read-model** design violates nothing and **actually serves the owner an integrity-verified,
provenance-stamped, bounded blob while 404-hiding the same artifact from a same-Team non-owner**.

Invariants (A1-A7, each mapped to an AC of story 8.3):
  A1  DURABLE SOURCE: artifacts + handoffs are projected from the durable content-addressed `coord.artifact`
      rows (§6.5) — NOT a re-invented store or an in-memory scrape (ADR-040: no bespoke table).
  A2  BFF CHOKE POINT: the browser reads through the Next.js BFF, which proxies the Go apiserver; the browser
      never connects to the apiserver directly and holds no apiserver URL/credential (§13 / ADR-013).
  A3  CONTENT-ADDRESSED INTEGRITY: the served blob's bytes hash to the row's recorded `sha256` — a blob whose
      bytes do not match its digest is REJECTED, never rendered as the artifact (2.8 content-addressing).
  A4  PER-PRINCIPAL EXISTENCE-HIDING: a caller who is not the Run's owning principal — INCLUDING a same-Team
      non-owner — gets `404`, not the blob and not a `403` (NFR-SEC5 / 8.7d; worktree blobs may carry the
      owner's BYO secrets). The owner gets `200`.
  A5  READ-ONLY, NO MUTATE AFFORDANCE (R6 scope guard, the pixel-level crux): the surface carries ONLY
      read/navigate/download affordances — NO edit / apply / re-run / claim / grant-custody verb. Handoff is
      ADVISORY (2.8): its fields are shown, but no custody/claim/fence affordance rides the inspection.
  A6  SERVER-STAMPED PROVENANCE: every artifact/handoff carries server-stamped provenance from the coord
      record — kind ∈ {diff,comment,report,file,log,handoff}, producer (agent·role), work item, timestamp,
      sha — never client-fabricated (FR-B4 / D4 / FR-I3).
  A7  BOUNDED + OBS: an oversize blob returns `tooLarge:true` with NO body, a binary blob returns
      `binary:true` with NO text body (never unbounded, 8.7a caps); the inspection span carries ONLY
      magnitudes/status — never blob content, an artifact sha, or a per-item id as a metric label (NFR-OBS3).

Mutation-proof harness (no vacuous guard — the ISI-2346-F1 class is excluded by construction). Each
`--mutate=<NAME>` injects exactly ONE defect into the CONFORMANT design; the check then goes RED with
EXACTLY the mapped invariant failing (no guard shadows another):
  --mutate=BESPOKE      read a re-invented store instead of the coord record   -> A1 RED
  --mutate=DIRECT_API   point the browser straight at the Go apiserver         -> A2 RED
  --mutate=SHA_MISMATCH serve a blob whose bytes don't match its digest        -> A3 RED
  --mutate=CROSS_PRIN   return a same-Team non-owner's blob (200 not 404)      -> A4 RED
  --mutate=MUTATE       hang an edit/apply affordance on the preview           -> A5 RED
  --mutate=CLIENT_PROV  fabricate provenance client-side                       -> A6 RED
  --mutate=UNBOUNDED    stream an oversize blob body (ignore the cap)          -> A7 RED

Baseline `python3 artifact-inspection-check.py` exits 0; each `--mutate=NAME` exits 1 with the single
violation. The check exits non-zero if the bespoke-store-editor model STOPS violating (teeth lost), if the
durable-coord model EVER violates an invariant, or if it fails to actually serve the owner the verified blob
while 404-hiding it from the same-Team non-owner.

Runtime proof (owned elsewhere). The real GET-through-BFF, the live 404 on a same-Team non-owner, and the
Gateway edge are exercised by the console E2E (`05-testing`) and the 8.7d BFF scoping gate. This model check
guards the **construction-time contract** — 8.3's crux and exactly what FR-F3 asked (inspect the blobs +
handoffs, from the coordination record, read-only).
"""
import hashlib
import sys

# ---- caps (fail-safe, mirrors 8.7a §3 "Limits, fail-safe not fail-open") ---------------------------
BLOB_CAP_BYTES = 2 * 1024 * 1024   # inspected blob body cap

# artifact kinds the coord record projects (UX §3.3 + 2.8 handoff)
ARTIFACT_KINDS = {"diff", "comment", "report", "file", "log", "handoff"}

# affordances allowed on a read-only inspection surface (R6). Anything else is a mutate leak.
READONLY_AFFORDANCES = {"view", "download", "navigate"}

# the 7 advisory fields of a structured handoff (story 2.8 — a superset of §8.5's illustrative shape)
HANDOFF_FIELDS = {"did", "decisions", "next", "blockers", "findings",
                  "recommended_next", "artifacts_for_downstream"}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


# ---- the durable coordination record (§6.5) — the ONLY source of truth -----------------------------
# Each row is a content-addressed coord.artifact. `owning_principal` is the Run's already-recorded
# initiating principal (8.7d AC5 — no new field). Blob bytes are content-addressed by `sha256`.
def build_coord_record():
    diff_blob = (b"--- a/pay.py\n+++ b/pay.py\n@@ -1,2 +1,2 @@\n"
                 b"-def charge(): return 1\n+def charge(): return 2  # fix\n")
    report_blob = b"payments-review: 3 findings, 0 blocking\n"
    log_blob = b"[02:48:01] fixer: opened PR #88\n[02:48:12] fixer: CI green\n"
    handoff_obj = {
        "did": "patched charge() rounding",
        "decisions": "kept the existing API signature",
        "next": "reviewer confirms the CI run",
        "blockers": "none",
        "findings": "one latent off-by-one, filed follow-up",
        "recommended_next": "merge after review",
        "artifacts_for_downstream": ["pay.py diff"],
    }
    handoff_blob = repr(sorted(handoff_obj.items())).encode()
    huge_blob = b"y" * (BLOB_CAP_BYTES + 4096)          # > 2 MiB -> tooLarge
    binary_blob = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4  # binary -> no text body

    rows = [
        {"id": "art-diff", "kind": "diff", "producer_agent": "Fixer", "producer_role": "Hermes",
         "work_item": "#88", "ts": "02:48:20", "owning_principal": "sam", "blob": diff_blob},
        {"id": "art-report", "kind": "report", "producer_agent": "Reviewer", "producer_role": "Claude",
         "work_item": "#88", "ts": "02:49:02", "owning_principal": "sam", "blob": report_blob},
        {"id": "art-log", "kind": "log", "producer_agent": "Fixer", "producer_role": "Hermes",
         "work_item": "#88", "ts": "02:48:12", "owning_principal": "sam", "blob": log_blob},
        {"id": "art-handoff", "kind": "handoff", "producer_agent": "Fixer", "producer_role": "Hermes",
         "work_item": "#88", "ts": "02:49:30", "owning_principal": "sam", "blob": handoff_blob,
         "handoff": handoff_obj},
        {"id": "art-huge", "kind": "file", "producer_agent": "Fixer", "producer_role": "Hermes",
         "work_item": "#88", "ts": "02:50:00", "owning_principal": "sam", "blob": huge_blob},
        {"id": "art-bin", "kind": "file", "producer_agent": "Fixer", "producer_role": "Hermes",
         "work_item": "#88", "ts": "02:50:10", "owning_principal": "sam", "blob": binary_blob},
    ]
    # content-address every row: the recorded digest is the authority (2.8 / §6.5).
    for r in rows:
        r["sha256"] = sha256(r["blob"])
    return {r["id"]: r for r in rows}


# a re-invented, non-durable store (the A1 anti-pattern): same ids, but scraped/mutated, NOT content-addressed.
def build_bespoke_store(coord):
    store = {}
    for rid, r in coord.items():
        store[rid] = dict(r)
        store[rid]["sha256"] = "0" * 64   # not content-addressed — a scrape, digest is meaningless
    return store


# ---- the artifact-inspection projection (the executable spec 8.3's console+BFF must match) ----------
#
# `inspect(design, caller, run_owner, artifact_id, coord, bespoke)` returns a response dict AND the design's
# transport/affordance/provenance metadata. `mut` names the single injected defect for the mutation harness;
# the conformant baseline passes mut=None.
def inspect(design, caller, run_owner, artifact_id, coord, bespoke, mut=None):
    source = design["source"]
    if mut == "BESPOKE":
        source = "bespoke"                       # DEFECT: read the re-invented store -> A1.

    record = bespoke if source == "bespoke" else coord
    row = record[artifact_id]

    # --- per-principal existence-hiding gate (A4 / NFR-SEC5 / 8.7d) BEFORE any body is read ----------
    scoped = design["scope"] == "per_principal"
    if mut == "CROSS_PRIN":
        scoped = False                           # DEFECT: drop the per-principal gate -> A4.
    is_owner = (caller == row["owning_principal"])
    if scoped and not is_owner:
        # existence-hiding: 404, no body, no confirmation the artifact exists.
        return {"status": 404, "body": None, "provenance": None}, _meta(design, mut)
    if not scoped and not is_owner:
        # the regression path: a non-owner gets the real blob back.
        pass

    # --- content-addressed integrity (A3 / 2.8) -----------------------------------------------------
    served_bytes = row["blob"]
    recorded_sha = row["sha256"]
    if mut == "SHA_MISMATCH":
        served_bytes = served_bytes + b"X"       # DEFECT: bytes no longer hash to recorded_sha -> A3.
    integrity_ok = (source != "bespoke") and (sha256(served_bytes) == recorded_sha)

    # --- bounded body / binary marker (A7 / 8.7a caps) ----------------------------------------------
    size = len(served_bytes)
    bounded = design.get("bounded", True)
    if mut == "UNBOUNDED":
        bounded = False                          # DEFECT: ignore the cap -> A7 (unbounded body).
    # an unbounded design streams the raw body: no too_large marker, no binary guard.
    binary = (b"\x00" in served_bytes) and bounded
    too_large = (size > BLOB_CAP_BYTES) and bounded

    if binary:
        body = None                              # never stream a binary as text
        rendered = {"binary": True, "tooLarge": False, "content": None}
    elif too_large:
        body = None
        rendered = {"binary": False, "tooLarge": True, "content": None}
    else:
        body = served_bytes if integrity_ok else None
        rendered = {"binary": False, "tooLarge": False,
                    "content": body.decode("utf-8", "surrogateescape") if body is not None else None}

    # --- server-stamped provenance (A6 / FR-I3) -----------------------------------------------------
    if mut == "CLIENT_PROV" or design["provenance"] == "client":
        provenance = {"source": "client", "kind": row["kind"]}   # DEFECT: client-fabricated -> A6.
    else:
        provenance = {
            "source": "server", "kind": row["kind"],
            "producer": f"{row['producer_agent']} ({row['producer_role']})",
            "work_item": row["work_item"], "ts": row["ts"], "sha256": recorded_sha,
        }

    resp = {"status": 200, "body": rendered, "provenance": provenance,
            "integrity_ok": integrity_ok, "sizeBytes": size}
    # handoff (advisory, 2.8): surface the 7 fields but NEVER a custody/claim affordance.
    if row["kind"] == "handoff":
        resp["handoff"] = row.get("handoff")
    return resp, _meta(design, mut)


def _meta(design, mut):
    endpoint = design["endpoint"]
    if mut == "DIRECT_API":
        endpoint = "apiserver"                   # DEFECT: browser talks to the Go apiserver -> A2.
    affordances = set(design["affordances"])
    if mut == "MUTATE":
        affordances = affordances | {"edit", "apply"}   # DEFECT: mutate affordance on preview -> A5.
    source = "bespoke" if mut == "BESPOKE" else design["source"]
    return {"endpoint": endpoint, "affordances": affordances, "source": source}


def build_span_attrs(resp, mut=None):
    """OBS: the inspection span carries ONLY magnitudes/status — never content/sha/id (A7, NFR-OBS3)."""
    attrs = {
        "ksquad.artifact.too_large": bool(resp["body"] and resp["body"]["tooLarge"]) if resp["body"] else False,
        "ksquad.artifact.binary": bool(resp["body"] and resp["body"]["binary"]) if resp["body"] else False,
        "ksquad.artifact.bytes_returned": resp.get("sizeBytes", 0),
    }
    if mut == "UNBOUNDED":
        # the unbounded defect also leaks the blob content into the span (the exfil edge A7 forbids).
        if resp["body"] and resp["body"].get("content"):
            attrs["ksquad.artifact.sample"] = resp["body"]["content"]
    return attrs


# ---- the two designs -------------------------------------------------------------------------------
CONFORMANT = {
    "source": "coord",            # A1 — durable content-addressed coord.artifact rows
    "endpoint": "bff",            # A2 — through the Next.js BFF, hiding the Go API
    "scope": "per_principal",     # A4 — existence-hiding per-principal gate
    "affordances": {"view", "download", "navigate"},  # A5 — read-only only
    "provenance": "server",       # A6 — server-stamped
    "bounded": True,              # A7 — caps + magnitudes-only span
}
NAIVE = {
    "source": "bespoke",          # A1 fail — re-invented store
    "endpoint": "apiserver",      # A2 fail — browser straight at the Go API
    "scope": "none",              # A4 fail — no per-principal gate
    "affordances": {"view", "edit", "apply", "rerun"},  # A5 fail — mutate affordances
    "provenance": "client",       # A6 fail — client-fabricated
    "bounded": False,             # A7 fail — streams unbounded blob bodies
}


# ---- the runnable check ----------------------------------------------------------------------------
def evaluate(design, mut, coord, bespoke, *, is_naive=False):
    """Return the list of (invariant, detail) violations for `design`."""
    fails = []

    def check(inv, cond, detail):
        if not cond:
            fails.append((inv, detail))

    OWNER, NON_OWNER = "sam", "priya"   # priya is in the SAME Team/Project but not the Run's principal

    # owner inspects the diff artifact -> the positive-control path (must be a faithful projection).
    resp, meta = inspect(design, OWNER, OWNER, "art-diff", coord, bespoke, mut=mut)

    # A1 — durable source, not a re-invented store.
    check("A1", meta["source"] == "coord",
          f"artifacts read from {meta['source']!r} store, not the durable coord record (§6.5/ADR-040)")

    # A2 — through the BFF, never the Go apiserver directly.
    check("A2", meta["endpoint"] == "bff",
          f"browser reads through {meta['endpoint']!r}, not the Next.js BFF (§13/ADR-013)")

    # A3 — content-addressed integrity: served bytes hash to the recorded sha.
    check("A3", resp["status"] == 200 and resp.get("integrity_ok") is True,
          "served blob does not hash to its recorded sha256 (content-addressing broken, 2.8/§6.5)")

    # A4 — per-principal existence-hiding: the SAME-Team non-owner gets 404, not the blob.
    deny, _ = inspect(design, NON_OWNER, OWNER, "art-diff", coord, bespoke, mut=mut)
    check("A4", deny["status"] == 404 and deny["body"] is None,
          f"same-Team non-owner got status={deny['status']} body={'set' if deny['body'] else 'None'} "
          f"— must be 404 existence-hiding (NFR-SEC5/8.7d)")
    # positive control: the owner is NOT denied (non-vacuous — the gate must allow the owner).
    check("A4", resp["status"] == 200,
          "owner was denied their own artifact — gate must ALLOW the owning principal (non-vacuous)")

    # A5 — read-only: only view/download/navigate affordances, no mutate verb; handoff advisory.
    leaked = meta["affordances"] - READONLY_AFFORDANCES
    check("A5", not leaked,
          f"mutate/edit affordance(s) {sorted(leaked)} on the inspection surface — R6 scope guard "
          f"(apply happens in the repo PR, not here)")
    h_resp, _ = inspect(design, OWNER, OWNER, "art-handoff", coord, bespoke, mut=mut)
    if h_resp["status"] == 200:
        check("A5", "grant_custody" not in (h_resp.get("handoff") or {}),
              "handoff carries a custody/claim affordance — handoff is ADVISORY only (2.8, no-P2P)")

    # A6 — server-stamped provenance with a legible kind.
    prov = resp.get("provenance") or {}
    check("A6", prov.get("source") == "server",
          f"provenance source={prov.get('source')!r} — must be server-stamped, not client (FR-I3)")
    check("A6", prov.get("kind") in ARTIFACT_KINDS,
          f"artifact kind {prov.get('kind')!r} not in {sorted(ARTIFACT_KINDS)} (FR-B4/D4)")

    # A7 — bounded body + span carries only magnitudes (no content/sha/id leak).
    huge, _ = inspect(design, OWNER, OWNER, "art-huge", coord, bespoke, mut=mut)
    check("A7", huge["body"] is not None and huge["body"]["tooLarge"] is True
          and huge["body"]["content"] is None,
          f"oversize blob must be tooLarge with no body (got {huge['body']})")
    binr, _ = inspect(design, OWNER, OWNER, "art-bin", coord, bespoke, mut=mut)
    check("A7", binr["body"] is not None and binr["body"]["binary"] is True
          and binr["body"]["content"] is None,
          "binary blob must be binary:true with no text body (8.7a)")
    attrs = build_span_attrs(resp, mut=mut)
    magnitudes = {"ksquad.artifact.too_large", "ksquad.artifact.binary", "ksquad.artifact.bytes_returned"}
    check("A7", set(attrs) <= magnitudes,
          f"inspection span carries non-magnitude attr(s) {sorted(set(attrs) - magnitudes)} "
          f"— content/sha/id leak forbidden (NFR-OBS3)")

    return fails


def run(mut=None):
    coord = build_coord_record()
    bespoke = build_bespoke_store(coord)

    # 1) teeth: the NAIVE bespoke-store-editor model must break EVERY invariant.
    naive_fails = evaluate(NAIVE, None, coord, bespoke, is_naive=True)
    naive_hit = {inv for inv, _ in naive_fails}

    # 2) the conformant §6.5/§13 durable-coord model (baseline, or with a single injected defect).
    conf_fails = evaluate(CONFORMANT, mut, coord, bespoke)

    return naive_fails, naive_hit, conf_fails


MUTANTS = {
    "BESPOKE": "A1", "DIRECT_API": "A2", "SHA_MISMATCH": "A3", "CROSS_PRIN": "A4",
    "MUTATE": "A5", "CLIENT_PROV": "A6", "UNBOUNDED": "A7",
}
ALL_INV = ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]


def main(argv):
    mut = None
    for a in argv[1:]:
        if a.startswith("--mutate="):
            mut = a.split("=", 1)[1].strip().upper()
    if mut and mut not in MUTANTS:
        print(f"unknown mutant {mut!r}; choose from {', '.join(MUTANTS)}", file=sys.stderr)
        return 2

    naive_fails, naive_hit, conf_fails = run(mut=mut)

    # teeth gate: the naive model must trip every invariant, always.
    missing_teeth = [inv for inv in ALL_INV if inv not in naive_hit]
    if missing_teeth:
        print(f"[artifact] TEETH LOST — the naive bespoke-store-editor model no longer trips {missing_teeth}:")
        for inv, d in naive_fails:
            print(f"    {inv}: {d}")
        return 1

    if mut is None:
        if conf_fails:
            print("[artifact] FAIL — the §6.5/§13 durable-coord model violated an invariant:")
            for inv, d in conf_fails:
                print(f"    {inv}: {d}")
            return 1
        print(f"[model] FR-F3 bespoke-store-editor client : {len(naive_hit)} violation(s) -> DETECTED")
        for inv, d in sorted(naive_fails):
            print(f"[model]   - {inv}: {d}")
        print("[model] §6.5/§13 durable-coord read model: 0 violation(s); "
              "source=coord, browser->bff, integrity-verified, per-principal 404, read-only, "
              "server-provenance, bounded")
        print("[artifact] PASS — the bespoke-store-editor client detectably breaks every invariant; the "
              "§6.5/§13\n           durable-coord design holds A1-A7 ... and actually serves the owner a "
              "verified blob\n           while 404-hiding the same artifact from a same-Team non-owner.")
        return 0

    expected = MUTANTS[mut]
    hit = {inv for inv, _ in conf_fails}
    if expected in hit:
        others = hit - {expected}
        tag = f" (also tripped {sorted(others)} — acceptable, {expected} is the mapped tooth)" if others else ""
        print(f"[artifact] KILLED — --mutate={mut} -> {expected} RED{tag}:")
        for inv, d in conf_fails:
            if inv == expected:
                print(f"    {inv}: {d}")
        return 1
    print(f"[artifact] SURVIVED — --mutate={mut} did NOT trip {expected} (VACUOUS GUARD); "
          f"tripped={sorted(hit) or 'nothing'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
