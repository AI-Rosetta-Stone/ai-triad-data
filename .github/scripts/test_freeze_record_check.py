"""Arms for freeze_record_check.py (t/399).

Each arm builds a throwaway git repo and drives check_pr()/check_push() end to end, so the
git-reading half runs, not only the pure functions. Every decision site has its PASS, FAIL
and GATE-UNREADABLE arms (t/399#6): record parse, required keys, hash, target present, removal
absent, record-without-write, record-modified, and the commit-to-PR lookup failing.

Run: python3 .github/scripts/test_freeze_record_check.py -v
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import freeze_record_check as m  # noqa: E402

ACC = "taxonomy/Origin/accelerationist.json"
REC = "data-mutations/t999/frozen_targets.json"


class Repo:
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="t399-")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t399@example.invalid")
        self.git("config", "user.name", "t399")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", os.devnull)
        self.git("config", "core.autocrlf", "false")

    def git(self, *args):
        r = subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"git {args}: {r.stderr}")
        return r.stdout.strip()

    def write(self, path, content):
        full = os.path.join(self.path, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))

    def rm(self, path):
        os.remove(os.path.join(self.path, path))

    def commit(self, msg, files=None, remove=()):
        for p, c in (files or {}).items():
            self.write(p, c)
        for p in remove:
            self.rm(p)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


def nodes(*ids):
    return {"nodes": [{"id": i, "label": i} for i in ids]}


def record(targets, removals=None, **over):
    rec = {"ticket": "t/999", "go": "t/999#3", "targets": targets}
    if removals is not None:
        rec["removals"] = removals
    rec["sha256"] = m.record_hash(targets, removals or [])
    rec.update(over)
    return rec


class Base(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.git = m.Git(self.r.path)
        self.base = self.r.commit("seed", {ACC: nodes("acc-1", "acc-2"), "README.md": "x"})

    def tearDown(self):
        self.r.cleanup()

    def pr(self, head):
        findings, n = m.check_pr(self.git, self.base, head)
        return m.verdict(findings, n), findings

    def assertVerdict(self, head, want, pattern=None):
        (v, reason), findings = self.pr(head)
        self.assertEqual(v, want, f"{reason}\n{findings}")
        if pattern:
            self.assertRegex("\n".join(msg for _, msg in findings) or reason, pattern)
        return findings


class TestHash(unittest.TestCase):
    def test_hash_is_order_independent_and_covers_removals(self):
        a = [{"file": "b.json", "id": "2"}, {"file": "a.json"}]
        self.assertEqual(m.record_hash(a), m.record_hash(list(reversed(a))))
        self.assertNotEqual(m.record_hash(a), m.record_hash(a, [{"file": "c.json"}]))
        self.assertEqual(m.record_hash(a, []), m.record_hash(a, None))

    def test_hash_is_pinned(self):
        # The exact bytes: no trailing newline, compact separators, sorted keys.
        text = '{"removals":[],"targets":[{"file":"a.json","id":"x"}]}'
        import hashlib
        self.assertEqual(m.record_hash([{"id": "x", "file": "a.json"}]), hashlib.sha256(text.encode()).hexdigest())

    def test_hash_cli_matches(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "r.json")
            rec = record([{"file": ACC, "id": "acc-1"}])
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(rec, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(m.main(["hash", p]), 0)
            self.assertEqual(buf.getvalue().strip(), rec["sha256"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestRecord(Base):
    def test_pass_no_records(self):
        head = self.r.commit("unrelated", {ACC: nodes("acc-1", "acc-2", "acc-3")})
        (v, reason), _ = self.pr(head)
        self.assertEqual((v, reason), (m.PASS, "no freeze record changes in range"))

    def test_pass_record_with_its_write(self):
        head = self.r.commit("write + record", {
            ACC: nodes("acc-1", "acc-2", "acc-3"),
            REC: record([{"file": ACC, "id": "acc-3"}]),
        })
        self.assertVerdict(head, m.PASS)

    def test_parse_fail(self):
        head = self.r.commit("bad json", {ACC: nodes("acc-1"), REC: "{not json"})
        self.assertVerdict(head, m.FAIL, r"record is not valid JSON")

    def test_parse_unreadable(self):
        head = self.r.commit("write + record", {ACC: nodes("acc-1", "acc-3"), REC: record([{"file": ACC, "id": "acc-3"}])})
        real = self.git.show
        self.git.show = lambda rev, path: (_ for _ in ()).throw(m.Unreadable("git show: boom")) if path == REC else real(rev, path)
        self.assertVerdict(head, m.UNREADABLE, r"git show: boom")

    def test_required_keys_fail(self):
        rec = record([{"file": ACC, "id": "acc-1"}])
        del rec["go"]
        rec["ticket"] = "999"
        head = self.r.commit("keys", {ACC: nodes("acc-1", "acc-9"), REC: rec})
        f = self.assertVerdict(head, m.FAIL, r"`go` must be")
        self.assertTrue(any("`ticket` must be" in msg for _, msg in f))

    def test_target_shape_fail(self):
        rec = record([{"file": ACC, "id": ""}])
        head = self.r.commit("shape", {ACC: nodes("acc-1", "acc-9"), REC: rec})
        self.assertVerdict(head, m.FAIL, r"every target must be")

    def test_hash_fail(self):
        rec = record([{"file": ACC, "id": "acc-1"}])
        rec["targets"].append({"file": ACC, "id": "acc-2"})  # list changed after hashing
        head = self.r.commit("hash", {ACC: nodes("acc-1", "acc-2", "x"), REC: rec})
        self.assertVerdict(head, m.FAIL, r"does not match its targets/removals")

    def test_target_file_missing_fail(self):
        head = self.r.commit("missing", {ACC: nodes("acc-1", "z"), REC: record([{"file": ACC}, {"file": "nope.json"}])})
        self.assertVerdict(head, m.FAIL, r"target nope\.json does not exist")

    def test_target_id_missing_fail(self):
        head = self.r.commit("id", {ACC: nodes("acc-1", "z"), REC: record([{"file": ACC, "id": "acc-404"}])})
        self.assertVerdict(head, m.FAIL, r"target id acc-404 not found")

    def test_whole_file_target_pass(self):
        head = self.r.commit("new file", {"sources/new.json": {"a": 1}, REC: record([{"file": "sources/new.json"}])})
        self.assertVerdict(head, m.PASS)

    def test_target_not_json_unreadable(self):
        head = self.r.commit("txt", {"notes/a.json": "not json", REC: record([{"file": "notes/a.json", "id": "x"}])})
        self.assertVerdict(head, m.UNREADABLE, r"is not readable JSON")

    def test_removal_pass_file_and_id(self):
        self.base = self.r.commit("seed2", {"old/gone.json": {"x": 1}})
        head = self.r.commit("remove", {
            ACC: nodes("acc-1"),
            REC: record([{"file": ACC, "id": "acc-1"}], removals=[{"file": ACC, "id": "acc-2"}, {"file": "old/gone.json"}]),
        }, remove=["old/gone.json"])
        self.assertVerdict(head, m.PASS)

    def test_removal_still_present_fail(self):
        head = self.r.commit("not removed", {
            ACC: nodes("acc-1", "acc-2", "acc-3"),
            REC: record([{"file": ACC, "id": "acc-3"}], removals=[{"file": ACC, "id": "acc-2"}]),
        })
        self.assertVerdict(head, m.FAIL, r"removal id acc-2 still in")

    def test_removal_never_present_fail(self):
        head = self.r.commit("phantom", {
            ACC: nodes("acc-1", "acc-3"),
            REC: record([{"file": ACC, "id": "acc-3"}], removals=[{"file": ACC, "id": "acc-77"}]),
        })
        self.assertVerdict(head, m.FAIL, r"removal id acc-77 was not in")

    def test_removal_base_not_json_unreadable(self):
        self.base = self.r.commit("seed2", {"old/bad.json": "not json"})
        head = self.r.commit("rm", {"old/bad.json": "still not json", REC: record([{"file": "old/bad.json"}], removals=[{"file": "old/bad.json", "id": "x"}])})
        self.assertVerdict(head, m.UNREADABLE, r"old/bad\.json at .* is not readable JSON")

    def test_record_without_write_fail(self):
        head = self.r.commit("record only", {REC: record([{"file": ACC, "id": "acc-1"}])})
        self.assertVerdict(head, m.FAIL, r"record without its write; this unit does not change taxonomy/Origin/accelerationist\.json")

    def test_record_modified_later_fail(self):
        self.base = self.r.commit("freeze", {ACC: nodes("acc-1", "acc-3"), REC: record([{"file": ACC, "id": "acc-3"}])})
        head = self.r.commit("edit freeze", {REC: record([{"file": ACC, "id": "acc-1"}])})
        self.assertVerdict(head, m.FAIL, r"frozen record changed after it was committed")

    def test_record_deleted_later_fail(self):
        self.base = self.r.commit("freeze", {ACC: nodes("acc-1", "acc-3"), REC: record([{"file": ACC, "id": "acc-3"}])})
        head = self.r.commit("drop freeze", remove=[REC])
        self.assertVerdict(head, m.FAIL, r"frozen record deleted after it was committed")

    def test_later_unrelated_edit_of_target_file_passes(self):
        # One direction only (t/399#6 b): editing a frozen target file later is honest work.
        self.base = self.r.commit("freeze", {ACC: nodes("acc-1", "acc-3"), REC: record([{"file": ACC, "id": "acc-3"}])})
        head = self.r.commit("unrelated edit", {ACC: nodes("acc-1", "acc-3", "acc-4")})
        self.assertVerdict(head, m.PASS)

    def test_non_record_paths_ignored(self):
        head = self.r.commit("notes", {"data-mutations/t999/apply-evidence.md": "counts", "data-mutations/t999/sub/frozen_x.json": "nope"})
        self.assertVerdict(head, m.PASS)

    def test_bad_pr_range_unreadable(self):
        findings, n = m.check_pr(self.git, "0" * 40, self.base)
        self.assertEqual(m.verdict(findings, n)[0], m.UNREADABLE)


class TestPush(Base):
    def test_same_pr_two_commits_pass(self):
        c1 = self.r.commit("record", {REC: record([{"file": ACC, "id": "acc-3"}])})
        c2 = self.r.commit("write", {ACC: nodes("acc-1", "acc-2", "acc-3")})
        findings, n = m.check_push(self.git, self.base, c2, lambda sha: [42])
        self.assertEqual(m.verdict(findings, n)[0], m.PASS, findings)
        self.assertNotEqual(c1, c2)

    def test_two_direct_commits_fail(self):
        self.r.commit("record", {REC: record([{"file": ACC, "id": "acc-3"}])})
        c2 = self.r.commit("write", {ACC: nodes("acc-1", "acc-2", "acc-3")})
        findings, n = m.check_push(self.git, self.base, c2, lambda sha: [])
        v, _ = m.verdict(findings, n)
        self.assertEqual(v, m.FAIL)
        # The record's own commit is the unit: it lacks the write, and (at that head) the id too.
        self.assertTrue(any(__import__("re").match(r"^commit [0-9a-f]{9}: .*record without its write", msg) for _, msg in findings), findings)

    def test_lookup_failure_unreadable(self):
        c = self.r.commit("write + record", {ACC: nodes("acc-1", "acc-3"), REC: record([{"file": ACC, "id": "acc-3"}])})

        def boom(sha):
            raise m.Unreadable(f"commit-to-PR lookup for {sha[:9]} failed: HTTP 502")
        findings, n = m.check_push(self.git, self.base, c, boom)
        v, reason = m.verdict(findings, n)
        self.assertEqual(v, m.UNREADABLE)
        self.assertRegex(findings[0][1], r"lookup .* failed")

    def test_no_record_in_range_spends_no_lookups(self):
        c = self.r.commit("unrelated", {ACC: nodes("acc-1", "acc-2", "acc-5")})
        calls = []
        findings, n = m.check_push(self.git, self.base, c, lambda sha: calls.append(sha) or [])
        self.assertEqual(m.verdict(findings, n)[0], m.PASS)
        self.assertEqual(calls, [])

    def test_zero_before_unreadable(self):
        findings, n = m.check_push(self.git, m.ZERO_SHA, self.base, lambda sha: [])
        self.assertEqual(m.verdict(findings, n)[0], m.UNREADABLE)

    def test_modified_in_later_push_fail(self):
        frozen = self.r.commit("freeze", {ACC: nodes("acc-1", "acc-3"), REC: record([{"file": ACC, "id": "acc-3"}])})
        c = self.r.commit("edit", {REC: record([{"file": ACC, "id": "acc-1"}])})
        findings, n = m.check_push(self.git, frozen, c, lambda sha: [])
        self.assertEqual(m.verdict(findings, n)[0], m.FAIL)


class TestEmit(unittest.TestCase):
    def run_emit(self, v, findings):
        d = tempfile.mkdtemp()
        try:
            env = {"GITHUB_OUTPUT": os.path.join(d, "o"), "GITHUB_STEP_SUMMARY": os.path.join(d, "s")}
            lines = []
            code = m.emit(v, "why", findings, env=env, out=lines.append)
            with open(env["GITHUB_OUTPUT"], encoding="utf-8") as fh:
                outputs = fh.read()
            with open(env["GITHUB_STEP_SUMMARY"], encoding="utf-8") as fh:
                summary = fh.read()
            return code, lines, outputs, summary
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_exit_codes_outputs_and_error_annotation(self):
        for v, code_want in ((m.PASS, 0), (m.FAIL, 1), (m.UNREADABLE, 2)):
            code, lines, outputs, summary = self.run_emit(v, [] if v == m.PASS else [(v, "x")])
            self.assertEqual(code, code_want)
            self.assertEqual(outputs, f"gate={m.GATE}\nverdict={v}\nreason=why\n")
            self.assertIn(f"**{v}**", summary)
            self.assertEqual(any(l.startswith("::error") for l in lines), v != m.PASS)

    def test_unreadable_outranks_fail(self):
        v, _ = m.verdict([(m.FAIL, "a"), (m.UNREADABLE, "b")], 2)
        self.assertEqual(v, m.UNREADABLE)


if __name__ == "__main__":
    unittest.main()
