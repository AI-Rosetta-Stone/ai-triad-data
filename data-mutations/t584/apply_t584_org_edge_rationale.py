#!/usr/bin/env python3
"""t/584: organization edges whose `rationale` is a pipeline diagnostic get a plain sentence.

PI approval recorded on t/584#22 (relayed by the TL, p/37#227). Reads ONLY
frozen_t584_org_edge_rationale.json, beside this file, for what to change (/data-mutation element 1).

  taxonomy/Origin/organization_edges.json
      - each frozen `edges_set` edge (found by source, target, type; exactly one match) must still
        hold the frozen `require` values (its old rationale and status), and gets the frozen `set`
        fields: `rationale`, `match_meta` (the diagnostics the old rationale carried), and for the
        five claimless proposed edges `status`, `reviewed_by`, `reviewed_at`, `review_note`;
      - a key the edge already has keeps its place; a new key is appended, `match_meta` last (where
        Import-OrganizationEdge puts it);
      - `last_modified` := the frozen date. No edge is added, removed or reordered.

  --mode dry-run (default)  Every check runs; writes nothing.
  --mode apply              The same checks; refuses if any fails; writes the file and re-reads it
                            against post_sha256. Requires --frozen-sha.

Hashes are sha256 of the bytes with CRLF turned into LF. Revert: `git revert` the one commit.
"""

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

FROZEN = Path(__file__).resolve().parent / "frozen_t584_org_edge_rationale.json"
EDGES = "taxonomy/Origin/organization_edges.json"
SET_ORDER = ["rationale", "status", "reviewed_by", "reviewed_at", "review_note", "match_meta"]


def _fail(goal, problem, next_steps):
    raise SystemExit(f"ERROR\n  Goal: {goal}\n  Problem: {problem}\n  Location: apply_t584_org_edge_rationale.py\n  Next Steps: {next_steps}")


def lf_sha256(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def serialize(doc, crlf):
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")


def edge_key(e):
    return (e.get("source"), e.get("target"), e.get("type"))


def transform(doc, frozen):
    """Returns (new doc, problems)."""
    out = copy.deepcopy(doc)
    problems = []
    keys = [edge_key(e) for e in out["edges"]]
    seen = set()
    for item in frozen["edges_set"]:
        k = tuple(item["key"])
        if k in seen:
            problems.append(f"frozen key listed twice: {k}")
            continue
        seen.add(k)
        if keys.count(k) != 1:
            problems.append(f"frozen key matches {keys.count(k)} edges, expected 1: {k}")
            continue
        e = out["edges"][keys.index(k)]
        for field, want in item["require"].items():
            if e.get(field) != want:
                problems.append(f"{k}: {field} is {e.get(field)!r}, the freeze requires {want!r}")
        if "match_meta" in e:
            problems.append(f"{k}: already has match_meta")
        unknown = [f for f in item["set"] if f not in SET_ORDER]
        if unknown:
            problems.append(f"{k}: the freeze sets fields this script does not know: {unknown}")
        for field in SET_ORDER:
            if field in item["set"]:
                e[field] = copy.deepcopy(item["set"][field])
    out["last_modified"] = frozen["last_modified"]
    return out, problems


def collateral(old, new, frozen):
    """Everything the freeze does not name must be equal and in place."""
    problems = []
    if [k for k in old if k != "edges"] != [k for k in new if k != "edges"]:
        problems.append("file-level keys changed")
    for k in old:
        if k not in ("edges", "last_modified") and old[k] != new[k]:
            problems.append(f"file-level field {k} changed")
    if len(old["edges"]) != len(new["edges"]):
        problems.append(f"edge count {len(old['edges'])} -> {len(new['edges'])}")
        return problems
    plan = {tuple(i["key"]): i for i in frozen["edges_set"]}
    changed = 0
    for a, b in zip(old["edges"], new["edges"]):
        if edge_key(a) != edge_key(b):
            problems.append(f"edge order or identity changed at {edge_key(a)}")
            continue
        item = plan.get(edge_key(a))
        if item is None:
            if a != b or list(a) != list(b):
                problems.append(f"an edge outside the freeze changed: {edge_key(a)}")
            continue
        changed += 1
        allowed = set(item["set"])
        for field in set(a) | set(b):
            if field not in allowed and a.get(field) != b.get(field):
                problems.append(f"{edge_key(a)}: field {field} changed and is not in the freeze")
        if [f for f in b if f in a] != list(a):
            problems.append(f"{edge_key(a)}: existing keys moved")
        if {f: b[f] for f in allowed} != item["set"]:
            problems.append(f"{edge_key(a)}: the result does not hold the frozen values")
    if changed != len(plan):
        problems.append(f"{changed} frozen edges found in place, expected {len(plan)}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    ap.add_argument("--frozen-sha", help="sha256-lf (or a 16+ character prefix) of the frozen file; required for apply")
    ap.add_argument("--out-dir", help="dry-run only: also write the candidate file here")
    a = ap.parse_args(argv)

    frozen_bytes = FROZEN.read_bytes()
    actual = lf_sha256(frozen_bytes)
    if a.mode == "apply" and (not a.frozen_sha or len(a.frozen_sha) < 16 or not actual.startswith(a.frozen_sha)):
        _fail("Apply only the authorized frozen change", f"--frozen-sha {a.frozen_sha!r} does not match the frozen file ({actual[:16]}...)",
              "Pass the sha256-lf recorded on t/584.")
    frozen = json.loads(frozen_bytes)
    spec = frozen["files"][EDGES]

    path = Path(a.data_root) / EDGES
    raw = path.read_bytes()
    problems = []
    if lf_sha256(raw) != spec["pre_sha256"]:
        problems.append(f"{EDGES}: bytes differ from pre_sha256 (changed since the freeze)")
    crlf = b"\r\n" in raw
    old = json.loads(raw)
    if serialize(old, crlf) != raw:
        problems.append(f"{EDGES}: the serializer does not round-trip the file as it is")
    new, more = transform(old, frozen)
    problems += more
    problems += collateral(old, new, frozen)
    new_raw = serialize(new, crlf)
    if serialize(json.loads(new_raw), crlf) != new_raw:
        problems.append(f"{EDGES}: the serializer does not round-trip the result")
    post = lf_sha256(new_raw)
    if spec.get("post_sha256") and post != spec["post_sha256"]:
        problems.append(f"{EDGES}: transformed bytes hash to {post}, not post_sha256")

    print(f"{EDGES}: edges {len(old['edges'])} -> {len(new['edges'])}; frozen edges {len(frozen['edges_set'])}; candidate post sha256-lf {post}", file=sys.stderr)
    if problems:
        _fail("Rewrite only the frozen organization-edge rationales", "; ".join(problems), "Fix the cause; do not edit the freeze (a correction is a new record).")
    if a.mode == "dry-run":
        if a.out_dir:
            out = Path(a.out_dir) / EDGES
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(new_raw)
        print("dry-run: all checks passed; nothing written", file=sys.stderr)
        return 0
    if not spec.get("post_sha256"):
        _fail("Apply only a fully frozen change", "the freeze has no post_sha256", "Record the dry-run post hash in the freeze first.")
    path.write_bytes(new_raw)
    if lf_sha256(path.read_bytes()) != spec["post_sha256"]:
        _fail("Verify the written file", "post_sha256 mismatch after write", f"Revert with git checkout -- {EDGES} and investigate.")
    print("wrote 1 file; it matches post_sha256", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
