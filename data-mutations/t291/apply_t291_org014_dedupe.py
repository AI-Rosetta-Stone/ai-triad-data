#!/usr/bin/env python3
"""t/291: org-014 (NIST) stance claims and edges that sit on marked copies of two documents.

PI approval relayed by the TL (p/37#189). Reads ONLY frozen_t291_org014_dedupe.json, beside this
file, for what to change (/data-mutation element 1).

  organization_stance_claims.json
      - the frozen `remove` claims are removed: each has the same text as a claim org-014 already
        holds on the copy's canonical document (or as another copy claim that is moved there);
      - the frozen `move` claims get `source_id` = the canonical document. Nothing else on them changes;
      - `claim_count` follows; `last_modified` := the frozen date.
  organization_edges.json
      - the frozen `edges_set` edges (org-014 PUBLISHED -> a copy) get the frozen fields. They are not
        re-pointed, because the PUBLISHED edge to each canonical already exists, and not deleted,
        because Invoke-OrgPublishedSeeding skips any existing edge, so a rejected edge is never
        re-proposed (/data-mutation check B; the t/293 precedent);
      - the frozen `source_refs` edges get the frozen list (copy ids replaced by their canonicals,
        repeats removed, order kept);
      - `last_modified` := the frozen date.

  --mode dry-run (default)  Every check runs; writes nothing.
  --mode apply              The same checks; refuses if any fails; writes both files and re-reads them
                            against post_sha256. Requires --frozen-sha.

Hashes are sha256 of the bytes with CRLF turned into LF. Revert: `git revert` the one commit.
"""

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

FROZEN = Path(__file__).resolve().parent / "frozen_t291_org014_dedupe.json"
CLAIMS = "taxonomy/Origin/organization_stance_claims.json"
EDGES = "taxonomy/Origin/organization_edges.json"


def _fail(goal, problem, next_steps):
    raise SystemExit(f"ERROR\n  Goal: {goal}\n  Problem: {problem}\n  Location: apply_t291_org014_dedupe.py\n  Next Steps: {next_steps}")


def lf_sha256(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def serialize(doc, crlf):
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")


def claim_key(c):
    return (c.get("org_id"), c.get("source_id"), c.get("text"))


def edge_key(e):
    return (e.get("source"), e.get("target"), e.get("type"))


def transform_claims(doc, plan):
    """Returns (new doc, problems)."""
    out = copy.deepcopy(doc)
    problems = []
    remove = [tuple(k) for k in plan["remove"]]
    move = {tuple(m["key"]): m["to"] for m in plan["move"]}
    keys = [claim_key(c) for c in out["claims"]]
    for k in remove + list(move):
        if keys.count(k) != 1:
            problems.append(f"claims: frozen key matches {keys.count(k)} claims, expected 1: {k[1]} | {k[2][:60]}")
    if set(remove) & set(move):
        problems.append("claims: a key is in both remove and move")
    kept = []
    for c in out["claims"]:
        k = claim_key(c)
        if k in remove:
            continue
        if k in move:
            c["source_id"] = move[k]
        kept.append(c)
    out["claims"] = kept
    out["claim_count"] = len(kept)
    out["last_modified"] = plan["last_modified"]
    after = [claim_key(c) for c in kept]
    if len(after) != len(set(after)):
        problems.append("claims: a (org, source, text) key is duplicated after the change")
    return out, problems


def transform_edges(doc, plan):
    out = copy.deepcopy(doc)
    problems = []
    keys = [edge_key(e) for e in out["edges"]]
    for spec in plan["edges_set"]:
        k = tuple(spec["key"])
        if keys.count(k) != 1:
            problems.append(f"edges: frozen key matches {keys.count(k)} edges: {k}")
            continue
        e = out["edges"][keys.index(k)]
        for f, v in spec["require"].items():
            if e.get(f) != v:
                problems.append(f"edges: {k} has {f}={e.get(f)!r}, the freeze requires {v!r}")
        e.update(spec["set"])
    for spec in plan["source_refs"]:
        k = tuple(spec["key"])
        if keys.count(k) != 1:
            problems.append(f"edges: frozen key matches {keys.count(k)} edges: {k}")
            continue
        e = out["edges"][keys.index(k)]
        if e.get("source_refs") != spec["from"]:
            problems.append(f"edges: {k} source_refs are {e.get('source_refs')!r}, the freeze expects {spec['from']!r}")
        e["source_refs"] = list(spec["to"])
    out["last_modified"] = plan["last_modified"]
    return out, problems


def collateral_claims(old, new, plan):
    problems = []
    for k in set(old) | set(new):
        if k not in ("claims", "claim_count", "last_modified") and old.get(k) != new.get(k):
            problems.append(f"claims: top-level {k} changed")
    remove = {tuple(k) for k in plan["remove"]}
    move = {tuple(m["key"]): m["to"] for m in plan["move"]}
    expect = []
    for c in old["claims"]:
        k = claim_key(c)
        if k in remove:
            continue
        expect.append(dict(c, source_id=move[k]) if k in move else c)
    if expect != new["claims"]:
        problems.append("claims: something other than the frozen removals and moves changed, or the order changed")
    for a, b in zip(expect, new["claims"]):
        if list(a) != list(b):
            problems.append("claims: a claim's key order changed")
            break
    return problems


def collateral_edges(old, new, plan):
    problems = []
    for k in set(old) | set(new):
        if k not in ("edges", "last_modified") and old.get(k) != new.get(k):
            problems.append(f"edges: top-level {k} changed")
    if len(old["edges"]) != len(new["edges"]):
        return problems + ["edges: the number of edges changed"]
    allowed = {tuple(s["key"]): set(s["set"]) for s in plan["edges_set"]}
    allowed.update({tuple(s["key"]): {"source_refs"} for s in plan["source_refs"]})
    for a, b in zip(old["edges"], new["edges"]):
        diff = {f for f in set(a) | set(b) if a.get(f) != b.get(f)}
        if diff - allowed.get(edge_key(a), set()):
            problems.append(f"edges: {edge_key(a)} changed {sorted(diff)}")
        if [f for f in a] != [f for f in b if f in a]:
            problems.append(f"edges: {edge_key(a)} key order changed")
    return problems


def plan_files(data_root, frozen):
    steps, problems = [], []
    for rel, transform, collateral in ((CLAIMS, transform_claims, collateral_claims), (EDGES, transform_edges, collateral_edges)):
        spec = frozen["files"][rel]
        path = data_root / rel
        raw = path.read_bytes()
        if lf_sha256(raw) != spec["pre_sha256"]:
            problems.append(f"{rel}: bytes differ from pre_sha256 (changed since the freeze)")
            continue
        crlf = b"\r\n" in raw
        doc = json.loads(raw.decode("utf-8"))
        if serialize(doc, crlf) != raw:
            problems.append(f"{rel}: serializer does not round-trip the file")
            continue
        new_doc, errs = transform(doc, frozen)
        problems += [f"{rel}: {e}" for e in errs]
        problems += [f"{rel}: {e}" for e in collateral(doc, new_doc, frozen)]
        new_raw = serialize(new_doc, crlf)
        if serialize(json.loads(new_raw.decode("utf-8")), crlf) != new_raw:
            problems.append(f"{rel}: output is not canonical")
        post = lf_sha256(new_raw)
        if spec.get("post_sha256") and post != spec["post_sha256"]:
            problems.append(f"{rel}: transformed bytes hash to {post}, not post_sha256")
        steps.append((path, new_raw, rel, post))
    if problems:
        _fail("Apply the frozen t/291 change with zero collateral", "\n    ".join(problems),
              "Nothing was written. Re-freeze against the current tree and get the new hash authorized.")
    return steps


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--mode", choices=("dry-run", "apply"), default="dry-run")
    ap.add_argument("--frozen-sha", help="sha256-lf (or a 16+ character prefix) of the frozen file; required for apply")
    ap.add_argument("--out-dir", help="dry-run only: also write the candidate files here")
    a = ap.parse_args(argv)
    frozen_bytes = FROZEN.read_bytes()
    actual = lf_sha256(frozen_bytes)
    if a.mode == "apply" and (not a.frozen_sha or len(a.frozen_sha) < 16 or not actual.startswith(a.frozen_sha)):
        _fail("Apply only the authorized frozen change", f"--frozen-sha {a.frozen_sha!r} does not match the frozen file ({actual[:16]}...)",
              "Pass the sha256-lf recorded on t/291.")
    frozen = json.loads(frozen_bytes)
    steps = plan_files(Path(a.data_root), frozen)
    for _path, _raw, rel, post in steps:
        print(f"{rel}: candidate post sha256-lf {post}", file=sys.stderr)
    print(f"frozen {actual[:16]}: {len(frozen['remove'])} claims removed, {len(frozen['move'])} moved, "
          f"{len(frozen['edges_set'])} edges set, {len(frozen['source_refs'])} source_refs rewritten; every check passes", file=sys.stderr)
    if a.mode == "dry-run":
        if a.out_dir:
            for _path, raw, rel, _post in steps:
                out = Path(a.out_dir) / Path(rel).name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(raw)
        return 0
    if not all(frozen["files"][rel].get("post_sha256") for _p, _r, rel, _s in steps):
        _fail("Apply only a fully frozen change", "the freeze has no post_sha256", "Record the dry-run post hashes in the freeze first.")
    for path, raw, _rel, _post in steps:
        path.write_bytes(raw)
    bad = [rel for path, _raw, rel, post in steps if lf_sha256(path.read_bytes()) != frozen["files"][rel]["post_sha256"]]
    if bad:
        _fail("Verify the written files", f"post_sha256 mismatch after write: {bad}", "Revert with git checkout -- <files> and investigate.")
    print(f"wrote {len(steps)} files; all match post_sha256", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
