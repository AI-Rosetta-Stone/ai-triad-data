"""Fixtures for main_without_ci_check.py (t/4227).

Each arm builds a throwaway git repo so commits_in_range() is exercised against real git
history (not a stub), and drives classify_update() -- the pure decision -- with the
corresponding update/has_ci_run/acked_shas inputs. "Tested code == running code" (same
property test_node_removal_push_check.py states for its own fixtures).

Run: python3 .github/scripts/test_main_without_ci_check.py -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main_without_ci_check as m  # noqa: E402

BOT = m.BOT_AUTHOR_NAME
REGEN_MSG = "chore: regenerate source_index.json (t/3788)"


class Repo:
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="t4227-")
        self.git("init", "-q", "-b", "main")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args):
        r = subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"git {args}: {r.stderr}")
        return r.stdout.strip()

    def commit(self, author_name, message, filename="f.txt", content="x"):
        full = os.path.join(self.path, filename)
        with open(full, "a", encoding="utf-8") as fh:
            fh.write(content + "\n")
        self.git("add", filename)
        self.git(
            "-c", f"user.name={author_name}", "-c", "user.email=x@example.invalid",
            "commit", "-q", "-m", message,
        )
        return self.git("rev-parse", "HEAD")

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


class TestMainWithoutCi(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.cleanup()

    def test_1_bot_update_carries_non_bot_commit_flags(self):
        """Fixture 1: a bot ref-update whose range holds a non-bot commit -- the
        incident's exact shape (t/4064#10: 5debb042 -> 6115aa80 by the bot, carrying
        dd25058a/99ecc405/219a20ee, none of them bot-regen commits)."""
        before = self.repo.commit(BOT, REGEN_MSG)
        self.repo.commit("Jeffrey Snover", "feat(ci): single shared REGEN_INPUTS source")
        self.repo.commit(BOT, "ci-probe(t/4064): stray probe commit")
        after = self.repo.commit(BOT, REGEN_MSG)
        update = {"before": before, "after": after, "actor": BOT, "activity_type": "push"}
        commits = m.commits_in_range(before, after, cwd=self.repo.path)
        self.assertEqual(len(commits), 3)  # sanity: the fixture built what it meant to
        reason = m.classify_update(update, commits, has_ci_run=False, acked_shas=set())
        self.assertIsNotNone(reason)
        self.assertIn("non-bot-regen", reason)

    def test_2_bot_update_only_regen_commits_silent(self):
        """Fixture 2: a bot ref-update with only bot regen commits -- the ordinary,
        expected case -- stays silent."""
        before = self.repo.commit(BOT, REGEN_MSG)
        after = self.repo.commit(BOT, REGEN_MSG)
        update = {"before": before, "after": after, "actor": BOT, "activity_type": "push"}
        commits = m.commits_in_range(before, after, cwd=self.repo.path)
        self.assertEqual(len(commits), 1)
        reason = m.classify_update(update, commits, has_ci_run=False, acked_shas=set())
        self.assertIsNone(reason)

    def test_3_human_push_multi_commit_one_run_at_tip_silent(self):
        """Fixture 3 (Problem 1 from the TL review): a normal 3-commit human push that
        got one run at the tip must NOT be flagged -- this is what a per-commit
        headSha check got wrong in the first design."""
        before = self.repo.commit(BOT, REGEN_MSG)
        self.repo.commit("Jeffrey Snover", "feat: a")
        self.repo.commit("Jeffrey Snover", "feat: b")
        after = self.repo.commit("Jeffrey Snover", "feat: c")
        update = {"before": before, "after": after, "actor": "Jeffrey Snover", "activity_type": "push"}
        # Human actor: commits_in_range is not consulted by classify_update at all.
        reason = m.classify_update(update, commits=[], has_ci_run=True, acked_shas=set())
        self.assertIsNone(reason)

    def test_4_human_update_no_run_for_after_flags(self):
        """Fixture 4: a human ref-update with no push-event run for `after` -- CI never
        evaluated it."""
        before = self.repo.commit(BOT, REGEN_MSG)
        after = self.repo.commit("Jeffrey Snover", "feat: direct push, no CI run")
        update = {"before": before, "after": after, "actor": "Jeffrey Snover", "activity_type": "push"}
        reason = m.classify_update(update, commits=[], has_ci_run=False, acked_shas=set())
        self.assertIsNotNone(reason)
        self.assertIn("no push-event CI run", reason)

    def test_5_force_push_always_flags(self):
        """Fixture 5: activity_type force_push always flags, regardless of actor or
        whether a run exists for `after` -- it rewrites the history this script reasons
        about."""
        before = self.repo.commit(BOT, REGEN_MSG)
        after = self.repo.commit(BOT, REGEN_MSG)  # even an all-bot-regen range
        update = {"before": before, "after": after, "actor": BOT, "activity_type": "force_push"}
        reason = m.classify_update(update, commits=[], has_ci_run=True, acked_shas=set())
        self.assertIsNotNone(reason)
        self.assertIn("force-push", reason)

    def test_6_flagged_update_in_ack_file_silent(self):
        """Fixture 6: an update that would otherwise flag is silenced once its `after`
        SHA is in the ack file."""
        before = self.repo.commit(BOT, REGEN_MSG)
        after = self.repo.commit("Jeffrey Snover", "feat: direct push, acked after the fact")
        update = {"before": before, "after": after, "actor": "Jeffrey Snover", "activity_type": "push"}
        reason_unacked = m.classify_update(update, commits=[], has_ci_run=False, acked_shas=set())
        self.assertIsNotNone(reason_unacked)
        reason_acked = m.classify_update(update, commits=[], has_ci_run=False, acked_shas={after})
        self.assertIsNone(reason_acked)


if __name__ == "__main__":
    unittest.main()
