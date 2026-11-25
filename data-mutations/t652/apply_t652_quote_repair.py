#!/usr/bin/env python3
"""t/652: stored key-point quotes that copied a snapshot's damaged '?' get the character back.

99 snapshots in ai-triad-sources had characters replaced by '?' by an old PDF conversion; t/652 put them
back (ai-triad-sources 3d0d819f). Some summaries quote those snapshots, and the model copied the '?'.
This is the narrow exception to "a quote is stored as the model wrote it" (Tech Lead ruling t/652#16,
accepted by the Comp-Linguist on t/389): class 'model-copied damage restored, t/652'.

Reads ONLY frozen_t652_quote_repair.json, beside this file (/data-mutation element 1). Each frozen
quote is (file, JSON path, old text, new text). The new text was produced only by t/652's frozen
character map, and is in the freeze only because #5419's matcher decides it 'exact' against the
repaired snapshot. The old text stays in the freeze, so every change is traceable and reversible.

For each frozen file:
  - its bytes must hash to the frozen pre_sha256, and the serializer must round-trip it;
  - at every frozen JSON path the value must be exactly the frozen old text; one mismatch anywhere
    stops the whole run before anything is written;
  - only those values change: every other value of the document is equal and in place;
  - the result must round-trip and hash to the frozen post_sha256.

  --mode dry-run (default)  Every check runs for every file; writes nothing.
  --mode apply              The same checks for all files first; then writes them and re-reads each
                            against post_sha256. Requires --frozen-sha.

Hashes are sha256 of the bytes with CRLF turned into LF. Revert: `git revert` the one commit.
"""

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

FROZEN = Path(__file__).resolve().parent / "frozen_t652_quote_repair.json"
CR, LF = bytes([13]), bytes([10])


def _fail(goal, problem, next_steps):
    raise SystemExit(f"ERROR\n  Goal: {goal}\n  Problem: {problem}\n  Location: apply_t652_quote_repair.py\n  Next Steps: {next_steps}")


def lf_sha256(data):
    return hashlib.sha256(data.replace(CR + LF, LF)).hexdigest()


def serialize(doc, crlf):
    data = (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return data.replace(LF, CR + LF) if crlf else data


def get_at(doc, path):
    node = doc
    for key in path:
        node = node[key]
    return node


def set_at(doc, path, value):
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def transform(doc, quotes):
    """Returns (new doc, problems)."""
    out = copy.deepcopy(doc)
    problems, seen = [], set()
    for q in quotes:
        key = json.dumps(q["path"])
        if key in seen:
            problems.append(f"path listed twice: {q['path']}")
            continue
        seen.add(key)
        try:
            have = get_at(out, q["path"])
        except (KeyError, IndexError, TypeError):
            problems.append(f"no value at {q['path']}")
            continue
        if have != q["old"]:
            problems.append(f"{q['path']}: the stored text is not the frozen old text")
            continue
        set_at(out, q["path"], q["new"])
    # Nothing else changed: putting the old texts back gives the original document.
    back = copy.deepcopy(out)
    if not problems:
        for q in quotes:
            set_at(back, q["path"], q["old"])
        if back != doc:
            problems.append("a value outside the frozen paths changed")
    return out, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    ap.add_argument("--frozen-sha", help="sha256-lf (or a 16+ character prefix) of the frozen file; required for apply")
    a = ap.parse_args(argv)

    frozen_bytes = FROZEN.read_bytes()
    actual = lf_sha256(frozen_bytes)
    if a.mode == "apply" and (not a.frozen_sha or len(a.frozen_sha) < 16 or not actual.startswith(a.frozen_sha)):
        _fail("Apply only the authorized frozen change", f"--frozen-sha {a.frozen_sha!r} does not match the frozen file ({actual[:16]}...)",
              "Pass the sha256-lf recorded on t/652.")
    frozen = json.loads(frozen_bytes)

    root = Path(a.data_root)
    problems, plan, total = [], [], 0
    for rel, spec in sorted(frozen["files"].items()):
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: not found")
            continue
        raw = path.read_bytes()
        crlf = CR + LF in raw
        if lf_sha256(raw) != spec["pre_sha256"]:
            problems.append(f"{rel}: bytes differ from pre_sha256 (changed since the freeze)")
            continue
        doc = json.loads(raw)
        if serialize(doc, crlf) != raw:
            problems.append(f"{rel}: the serializer does not round-trip the file as it is")
            continue
        new, more = transform(doc, spec["quotes"])
        problems += [f"{rel}: {m}" for m in more]
        new_raw = serialize(new, crlf)
        if serialize(json.loads(new_raw), crlf) != new_raw:
            problems.append(f"{rel}: the serializer does not round-trip the result")
        if not more and lf_sha256(new_raw) != spec["post_sha256"]:
            problems.append(f"{rel}: the result hashes to {lf_sha256(new_raw)}, not post_sha256")
        plan.append((path, rel, new_raw))
        total += len(spec["quotes"])

    print(f"files {len(frozen['files'])}; quotes {total}; problems {len(problems)}", file=sys.stderr)
    if problems:
        _fail("Restore only the frozen quotes", "; ".join(problems[:20]) + (f"; and {len(problems) - 20} more" if len(problems) > 20 else ""),
              "Nothing was written. Fix the cause; do not edit the freeze (a correction is a new record).")
    if a.mode == "dry-run":
        print("dry-run: all checks passed; nothing written", file=sys.stderr)
        return 0
    for path, _rel, new_raw in plan:
        path.write_bytes(new_raw)
    bad = [rel for path, rel, _n in plan if lf_sha256(path.read_bytes()) != frozen["files"][rel]["post_sha256"]]
    if bad:
        _fail("Verify the written files", f"post_sha256 mismatch after write: {bad[:10]}", "Revert with git checkout -- summaries and investigate.")
    print(f"wrote {len(plan)} files; all match post_sha256", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
