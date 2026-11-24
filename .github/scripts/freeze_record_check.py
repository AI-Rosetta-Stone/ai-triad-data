"""Freeze-record check for data mutations (t/399, PR-reduction plan D).

A data mutation's frozen record moves from the main repo into the ai-triad-data commit or PR
that performs the write. This check is what makes that safe. Records live at
`data-mutations/<ticket>/frozen_*.json` and look like:

    {"ticket": "t/N", "go": "t/N#M", "sha256": "<record_hash>",
     "targets":  [{"file": "<repo path>", "id": "<optional id>"}, ...],
     "removals": [{"file": "<repo path>", "id": "<optional id>"}, ...]}      # optional

Rules (design t/399#5 as amended by the DevOps Lead, t/399#6):
  - The record parses; `ticket` is t/N; `go` is a ticket comment ref t/N#M; `sha256` is 64 hex;
    `targets` is a non-empty list; each target or removal is {"file": str, "id"?: str}.
  - `sha256` equals record_hash(targets, removals): one definition, used by the CLI's `hash`
    command for authors and by this check.
  - Every target exists at the unit's head. With `id`, the file parses as JSON and holds that
    value under an `id` key at any depth. Every removal is present at the unit's base and absent
    at its head.
  - A record added in a unit (a PR, or on push the commits of one merged PR, or one commit with
    no PR) requires that unit to change every target and removal file: "record without its write".
  - A record that already existed before the unit is never changed or deleted: a freeze is
    immutable, and a correction is a new record.

Verdicts (three-state, the data-repo twin of the main repo's gate-verdict.mjs, t/4496):
  PASS             every record in range was read and satisfies the rules (or there were none).
  FAIL             a record breaks a rule.                                       exit 1
  GATE-UNREADABLE  something could not be read or evaluated (git error, a target file that is
                   not JSON, the commit-to-PR lookup failed). No verdict, never a pass.  exit 2
GATE-UNREADABLE outranks FAIL in the headline (an incomplete read has no verdict); every FAIL
found is still listed.

Run:
  python3 .github/scripts/freeze_record_check.py pr   --base <sha> --head <sha>
  python3 .github/scripts/freeze_record_check.py push --before <sha> --after <sha> --repo owner/name
  python3 .github/scripts/freeze_record_check.py hash <record.json>     # prints the sha256 to record
Self-test: python3 .github/scripts/test_freeze_record_check.py -v
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

GATE = "freeze-record-check"
PASS, FAIL, UNREADABLE = "PASS", "FAIL", "GATE-UNREADABLE"
EXIT = {PASS: 0, FAIL: 1, UNREADABLE: 2}
RECORD_RE = re.compile(r"^data-mutations/[^/]+/frozen_[^/]*\.json$")
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
ZERO_SHA = "0" * 40


class Unreadable(Exception):
    """Something the check needs could not be read or evaluated."""


# ── pure ─────────────────────────────────────────────────────────────────────────────────────────

def _sort_key(entry):
    return (entry.get("file", ""), entry.get("id") or "")


def record_hash(targets, removals=None):
    """THE hash of a record: sha256 hex of the UTF-8 bytes (no trailing newline) of
    json.dumps({"removals": R, "targets": T}, separators=(',', ':'), sort_keys=True,
    ensure_ascii=False), with R and T each sorted by (file, id or "")."""
    payload = {
        "removals": sorted(removals or [], key=_sort_key),
        "targets": sorted(targets, key=_sort_key),
    }
    text = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_record_path(path):
    return bool(RECORD_RE.match(path))


def _valid_entry(e):
    if not isinstance(e, dict) or set(e) - {"file", "id"}:
        return False
    f = e.get("file")
    if not isinstance(f, str) or not f or f.startswith("/") or ".." in f.split("/"):
        return False
    return "id" not in e or (isinstance(e["id"], str) and e["id"] != "")


def validate_shape(rec):
    """PURE. Problems with a parsed record's keys and shapes (empty list = fine)."""
    if not isinstance(rec, dict):
        return ["record is not a JSON object"]
    problems = []
    if not isinstance(rec.get("ticket"), str) or not re.fullmatch(r"t/\d+", rec["ticket"]):
        problems.append("`ticket` must be a ticket ref like t/123")
    if not isinstance(rec.get("go"), str) or not re.fullmatch(r"t/\d+#\d+", rec["go"]):
        problems.append("`go` must be a ticket comment ref like t/123#4")
    if not isinstance(rec.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", rec["sha256"]):
        problems.append("`sha256` must be 64 lowercase hex characters")
    targets = rec.get("targets")
    if not isinstance(targets, list) or not targets:
        problems.append("`targets` must be a non-empty list")
    elif not all(_valid_entry(t) for t in targets):
        problems.append('every target must be {"file": "<repo path>", "id"?: "<non-empty string>"}')
    removals = rec.get("removals", [])
    if not isinstance(removals, list) or not all(_valid_entry(r) for r in removals):
        problems.append('`removals` must be a list of {"file": "<repo path>", "id"?: "<non-empty string>"}')
    return problems


def folder_matches_ticket(path, ticket):
    """PURE. data-mutations/<folder>/... must be `t<N>` or `t<N>-<suffix>` for ticket `t/<N>`."""
    folder = path.split("/")[1]
    n = ticket.split("/", 1)[1]
    return folder == f"t{n}" or folder.startswith(f"t{n}-")


def escape_annotation(text):
    """PURE. GitHub workflow-command escaping for an annotation message."""
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def has_id(doc, wanted):
    """PURE. True when some object at any depth has "id" == wanted."""
    stack = [doc]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("id") == wanted:
                return True
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


# ── git ──────────────────────────────────────────────────────────────────────────────────────────

class Git:
    def __init__(self, cwd="."):
        self.cwd = cwd

    def run(self, *args, binary=False):
        r = subprocess.run(["git", "-C", self.cwd, *args], capture_output=True)
        if r.returncode != 0:
            raise Unreadable(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
        return r.stdout if binary else r.stdout.decode("utf-8", "replace")

    def exists(self, rev, path):
        return self.run("ls-tree", "--name-only", rev, "--", path).strip() == path

    def show(self, rev, path):
        return self.run("show", f"{rev}:{path}", binary=True)

    def changed(self, base, head):
        out = self.run("diff", "--name-only", "--no-renames", "-z", base, head)
        return {p for p in out.split("\0") if p}

    def first_parent(self, sha):
        parents = self.run("rev-list", "--parents", "-n", "1", sha).split()
        return parents[1] if len(parents) > 1 else EMPTY_TREE

    def merge_base(self, a, b):
        return self.run("merge-base", a, b).strip()

    def commits(self, before, after):
        return [c for c in self.run("rev-list", "--reverse", f"{before}..{after}").split() if c]


def _load_json(git, rev, path):
    try:
        return json.loads(git.show(rev, path).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Unreadable(f"{path} at {rev[:9]} is not readable JSON ({e})")


# ── one unit ─────────────────────────────────────────────────────────────────────────────────────

def check_unit(git, label, base, head, changed):
    """Checks every record touched in one unit. Returns [(FAIL|GATE-UNREADABLE, message)]."""
    findings = []
    for path in sorted(p for p in changed if is_record_path(p)):
        where = f"{label}: {path}"
        try:
            at_base = base != EMPTY_TREE and git.exists(base, path)
            at_head = git.exists(head, path)
            if at_base:
                verb = "changed" if at_head else "deleted"
                findings.append((FAIL, f"{where}: frozen record {verb} after it was committed (a freeze is immutable; a correction is a new record)"))
                continue
            if not at_head:
                continue  # added and removed again inside the unit: nothing landed
            raw = git.show(head, path)
            try:
                rec = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                findings.append((FAIL, f"{where}: record is not valid JSON ({e})"))
                continue
            problems = validate_shape(rec)
            if not problems and not folder_matches_ticket(path, rec["ticket"]):
                problems.append(f"record folder {path.split('/')[1]} does not match its ticket {rec['ticket']} (folder must be t<N> or t<N>-<suffix>)")
            if problems:
                findings.extend((FAIL, f"{where}: {p}") for p in problems)
                continue
            targets, removals = rec["targets"], rec.get("removals", [])
            want = record_hash(targets, removals)
            if rec["sha256"] != want:
                findings.append((FAIL, f"{where}: sha256 {rec['sha256'][:12]}... does not match its targets/removals ({want[:12]}...)"))
            for t in targets:
                if not git.exists(head, t["file"]):
                    findings.append((FAIL, f"{where}: target {t['file']} does not exist at {head[:9]}"))
                elif "id" in t and not has_id(_load_json(git, head, t["file"]), t["id"]):
                    findings.append((FAIL, f"{where}: target id {t['id']} not found in {t['file']} at {head[:9]}"))
            for r in removals:
                rid = r.get("id")
                if base == EMPTY_TREE or not git.exists(base, r["file"]):
                    findings.append((FAIL, f"{where}: removal {r['file']} was not present before the unit"))
                    continue
                if rid is not None and not has_id(_load_json(git, base, r["file"]), rid):
                    findings.append((FAIL, f"{where}: removal id {rid} was not in {r['file']} before the unit"))
                    continue
                if git.exists(head, r["file"]):
                    if rid is None:
                        findings.append((FAIL, f"{where}: removal {r['file']} still exists at {head[:9]}"))
                    elif has_id(_load_json(git, head, r["file"]), rid):
                        findings.append((FAIL, f"{where}: removal id {rid} still in {r['file']} at {head[:9]}"))
            missing = sorted({e["file"] for e in targets + removals} - changed)
            if missing:
                findings.append((FAIL, f"{where}: record without its write; this unit does not change {', '.join(missing)}"))
        except Unreadable as e:
            findings.append((UNREADABLE, f"{where}: {e}"))
    return findings


# ── ranges ───────────────────────────────────────────────────────────────────────────────────────

def check_pr(git, base, head):
    """pull_request: the whole PR (merge-base..head) is one unit."""
    try:
        mb = git.merge_base(base, head)
        changed = git.changed(mb, head)
    except Unreadable as e:
        return [(UNREADABLE, f"could not read the PR range: {e}")], 0
    n = sum(1 for p in changed if is_record_path(p))
    return check_unit(git, f"PR {mb[:9]}..{head[:9]}", mb, head, changed), n


def gh_pr_lookup(repo):
    """The merged PRs into main that contain a commit (`gh api`). Raises Unreadable on failure."""
    def lookup(sha):
        r = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{sha}/pulls",
             "--jq", '[.[] | select(.merged_at != null and .base.ref == "main") | .number]'],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise Unreadable(f"commit-to-PR lookup for {sha[:9]} failed: {r.stderr.strip()}")
        try:
            return json.loads(r.stdout or "[]")
        except ValueError as e:
            raise Unreadable(f"commit-to-PR lookup for {sha[:9]} returned non-JSON ({e})")
    return lookup


def check_push(git, before, after, pr_lookup):
    """push: commits in before..after, grouped into units by merged PR (no PR: its own unit).
    Each unit's change set is the union of its commits' own diffs; its base is the first
    parent of its earliest commit and its head its latest commit."""
    if not before or before == ZERO_SHA:
        return [(UNREADABLE, "no `before` commit (new branch or missing input): the range cannot be checked")], 0
    try:
        commits = git.commits(before, after)
    except Unreadable as e:
        return [(UNREADABLE, f"could not list {before[:9]}..{after[:9]}: {e}")], 0
    units = {}
    order = []
    try:
        per_commit = [(sha, git.changed(git.first_parent(sha), sha)) for sha in commits]
        if not any(is_record_path(p) for _, ch in per_commit for p in ch):
            return [], 0  # no record touched: no PR lookups spent (one REST call per commit)
        for sha, ch in per_commit:
            prs = pr_lookup(sha)
            key = f"PR #{min(prs)}" if prs else f"commit {sha[:9]}"
            if key not in units:
                units[key] = {"commits": [], "changed": set()}
                order.append(key)
            units[key]["commits"].append(sha)
            units[key]["changed"] |= ch
    except Unreadable as e:
        return [(UNREADABLE, str(e))], 0
    findings, n = [], 0
    for key in order:
        u = units[key]
        n += sum(1 for p in u["changed"] if is_record_path(p))
        try:
            base = git.first_parent(u["commits"][0])
        except Unreadable as e:
            findings.append((UNREADABLE, f"{key}: {e}"))
            continue
        findings.extend(check_unit(git, key, base, u["commits"][-1], u["changed"]))
    return findings, n


def verdict(findings, n_records):
    kinds = {k for k, _ in findings}
    if UNREADABLE in kinds:
        v = UNREADABLE
        reason = f"{sum(1 for k, _ in findings if k == UNREADABLE)} item(s) could not be read; no verdict"
    elif FAIL in kinds:
        v = FAIL
        reason = f"{len(findings)} problem(s) in freeze records; first: {findings[0][1]}"
    else:
        v = PASS
        reason = "no freeze record changes in range" if n_records == 0 else f"{n_records} freeze record change(s) checked; all valid"
    return v, reason


def emit(v, reason, findings, env=os.environ, out=print):
    out(f"GATE-VERDICT {GATE}: {v} - {reason}")
    for k, msg in findings:
        out(f"  [{k}] {msg}")
    if v != PASS:
        out(f"::error title={v}::{escape_annotation(f'{GATE}: {reason}')}")
    line = " ".join(reason.split())
    try:
        if env.get("GITHUB_OUTPUT"):
            with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
                fh.write(f"gate={GATE}\nverdict={v}\nreason={line}\n")
        if env.get("GITHUB_STEP_SUMMARY"):
            body = [f"### Gate verdict: {GATE}", "", f"**{v}**", "", f"Reason: {line}"]
            body += [f"- [{k}] {m}" for k, m in findings]
            with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write("\n".join(body) + "\n\n")
    except OSError as e:
        out(f"WARN: could not write the verdict to the step outputs/summary ({e}); this log carries it.")
    return EXIT[v]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pr")
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    q = sub.add_parser("push")
    q.add_argument("--before", required=True)
    q.add_argument("--after", required=True)
    q.add_argument("--repo", required=True)
    h = sub.add_parser("hash")
    h.add_argument("record")
    a = ap.parse_args(argv)

    if a.cmd == "hash":
        with open(a.record, encoding="utf-8") as fh:
            rec = json.load(fh)
        print(record_hash(rec["targets"], rec.get("removals", [])))
        return 0
    try:
        git = Git()
        if a.cmd == "pr":
            findings, n = check_pr(git, a.base, a.head)
        else:
            findings, n = check_push(git, a.before, a.after, gh_pr_lookup(a.repo))
        v, reason = verdict(findings, n)
    except Exception as e:  # noqa: BLE001 -- a crash is no verdict, never a pass (t/399#8 item 2)
        v, reason, findings = UNREADABLE, f"checker crashed: {type(e).__name__}: {e}", []
    return emit(v, reason, findings)


if __name__ == "__main__":
    sys.exit(main())
