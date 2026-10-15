"""Detect data `main` ref-updates that never ran CI (t/4227, prevention follow-up for t/4064#10).

WHY THIS EXISTS
  t/4064#10: a regen workflow's commit-back pushed with a hardcoded `git push origin
  HEAD:main` (fixed in t/4226), so a probe run on another branch fast-forwarded `main`
  through a `GITHUB_TOKEN` push. Such a push starts NO workflow run — nothing noticed.
  The TL found it only by reading `main`'s log during a GV. This script restores that
  visibility on a schedule, without a human having to read the log by hand.

WHY REF UPDATES, NOT COMMITS (TL review, t/4227#2)
  An earlier draft judged each commit by whether ITS OWN SHA had a run. That both missed
  the incident and false-positived on ordinary pushes:
    - a normal N-commit push gets ONE run, at the tip — every intermediate commit has no
      run of its own, so a per-commit check flags every multi-commit push;
    - "covered by a later run" is equally wrong the other direction: the incident's
      `99ecc405`/`219a20ee` were "covered" by PR #63's later run, but #63's run had
      `before = 6115aa80` — its CI never looked at the earlier commits at all.
  The repository Activity API (`GET /repos/{o}/{r}/activity?ref=refs/heads/main`) gives
  one entry per REF UPDATE — before, after, actor, activity_type — which is the right
  unit: it is exactly what moved `main`, in one step, by one actor.

CLASSIFICATION (one of three arms per update)
  (a) actor is a bot (`github-actions[bot]`): every commit in `before..after` must be a
      bot-authored regen commit (author name `github-actions[bot]` AND the regen commit
      message). Anything else in that range is unexpected and flagged — this is the
      incident's exact shape (a bot ref-update smuggling non-bot commits through).
  (b) any other actor (human, app, other bot): a `push`-event workflow run with
      `headSha == after` must exist. No such run -> flagged ("CI never evaluated this").
  (c) `activity_type == force_push`: always flagged, regardless of (a)/(b) — a force-push
      rewrites the history this script reasons about, and deserves a human look regardless
      of who or what did it.

ACKNOWLEDGEMENT
  `.github/main-without-ci-ack.txt`: one `after` SHA per line (blank lines and `#`-comment
  lines ignored), each with a free-text reason. Edited only through a PR — this is a
  record of "a human looked at this and it's fine," not something the watchdog itself
  can write. An acked update's SHA is excluded from findings for the rest of its life in
  the lookback window (and forever after, since the ack file is permanent once merged).

STATELESS LOOKBACK
  No separate checkpoint file — the window is simply "every `main` ref-update in the last
  N days" (default 7). A flagged update stays flagged for its whole time in that window;
  it drops out on its own once it ages past the window, or immediately once acked.

Usage:
  python3 .github/scripts/main_without_ci_check.py --repo <owner/repo> [--lookback-days 7]
                                                     [--ack-file <path>]
Exit: 0 = no (unacked) findings; 1 = findings; 2 = usage/API error.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

REGEN_COMMIT_MESSAGE_PREFIX = "chore: regenerate source_index.json"
BOT_AUTHOR_NAME = "github-actions[bot]"


def run_gh(args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {args}: {r.stderr.strip()}")
    return r.stdout


def run_git(args, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {args}: {r.stderr.strip()}")
    return r.stdout


def fetch_activity(repo, since_iso):
    """One entry per main ref-update since `since_iso`. Paginates; the Activity API has
    no server-side time filter, so this fetches pages until timestamps age out of the
    window (activity is returned newest-first)."""
    entries = []
    page = 1
    while True:
        raw = run_gh([
            # --method GET is NOT optional here: gh api defaults to POST the moment any
            # -f/-F field is present, which 404s against this GET-only endpoint.
            "api", "--method", "GET", f"repos/{repo}/activity",
            "-f", "ref=refs/heads/main",
            "-f", f"page={page}", "-f", "per_page=100",
        ])
        batch = json.loads(raw)
        if not batch:
            break
        done = False
        for e in batch:
            if e.get("timestamp", "") < since_iso:
                done = True
                break
            # Normalize actor to its login string here, at the one place the raw API
            # shape is read -- the Activity API nests it as {"login": ..., ...}; the
            # pure classify_update() contract is a flat string, matched against
            # BOT_AUTHOR_NAME, so this is where that gets flattened, once.
            actor = e.get("actor") or {}
            entries.append({
                "before": e["before"],
                "after": e["after"],
                "actor": actor.get("login", "<unknown>"),
                "activity_type": e.get("activity_type"),
            })
        if done or len(batch) < 100:
            break
        page += 1
    return entries


def fetch_push_run_shas(repo, limit=300):
    """SHAs with at least one push-event workflow run on main, any conclusion — a run
    that evaluated the commit and failed still means CI looked at it; a MISSING run is
    the finding, not a failing one (that's a different alert's job)."""
    raw = run_gh([
        "run", "list", "-R", repo, "--branch", "main", "--event", "push",
        "--limit", str(limit), "--json", "headSha",
    ])
    return {row["headSha"] for row in json.loads(raw)}


def commits_in_range(before, after, cwd=None):
    """Commits strictly after `before` up to and including `after`, oldest first. Each as
    {sha, author_name, message}. Requires a local checkout with full history
    (fetch-depth: 0) — this walks real git ancestry, not the GitHub API, to keep the
    bot-regen classification exact (author name is set verbatim by the commit-back step,
    not inferred from a GitHub-side identity mapping)."""
    sep = "\x1f"  # unit separator -- never appears in a commit subject
    out = run_git(
        ["log", "--format=%H" + sep + "%an" + sep + "%s", f"{before}..{after}"],
        cwd=cwd,
    )
    commits = []
    for line in out.splitlines():
        if not line:
            continue
        sha, author_name, message = line.split(sep, 2)
        commits.append({"sha": sha, "author_name": author_name, "message": message})
    commits.reverse()  # git log is newest-first; we want oldest-first
    return commits


def is_bot_regen_commit(commit):
    return (
        commit["author_name"] == BOT_AUTHOR_NAME
        and commit["message"].startswith(REGEN_COMMIT_MESSAGE_PREFIX)
    )


def load_ack_file(path):
    acked = set()
    if not path or not os.path.isfile(path):
        return acked
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sha = line.split()[0]
            acked.add(sha)
    return acked


def classify_update(update, commits, has_ci_run, acked_shas):
    """Pure. Returns a finding reason string, or None if the update is fine.

    update: {"before": str, "after": str, "actor": str, "activity_type": str}
    commits: commits_in_range(before, after) -- only consulted for a bot actor.
    has_ci_run: whether a push-event run exists with headSha == update["after"].
    acked_shas: set of acknowledged `after` SHAs (ack always wins, checked first).
    """
    after = update["after"]
    if after in acked_shas:
        return None

    if update.get("activity_type") == "force_push":
        return f"force-push to main (before={update['before'][:8]} after={after[:8]}) by {update['actor']} -- history rewrite, always flagged"

    if update["actor"] == BOT_AUTHOR_NAME:
        offenders = [c for c in commits if not is_bot_regen_commit(c)]
        if offenders:
            shas = ", ".join(c["sha"][:8] for c in offenders)
            return (
                f"bot ref-update (before={update['before'][:8]} after={after[:8]}) carries "
                f"non-bot-regen commit(s): {shas} -- this is the t/4064 incident's shape"
            )
        return None

    if not has_ci_run:
        return f"no push-event CI run for {after[:8]} (actor: {update['actor']})"

    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--lookback-days", type=int, default=7)
    p.add_argument("--ack-file", default=None)
    p.add_argument("--git-cwd", default=None, help="checkout to run `git log` in (default: cwd)")
    args = p.parse_args()

    try:
        since = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        activity = fetch_activity(args.repo, since_iso)
        run_shas = fetch_push_run_shas(args.repo)
        acked = load_ack_file(args.ack_file)

        findings = []
        for update in activity:
            if update.get("activity_type") == "force_push":
                commits = []
            elif update["actor"] == BOT_AUTHOR_NAME:
                commits = commits_in_range(update["before"], update["after"], cwd=args.git_cwd)
            else:
                commits = []
            has_run = update["after"] in run_shas
            reason = classify_update(update, commits, has_run, acked)
            if reason:
                findings.append({"before": update["before"], "after": update["after"], "reason": reason})

        if findings:
            for f in findings:
                print(f"::error::main-without-ci: {f['reason']}")
            print(json.dumps(findings))
            return 1

        print("main-without-ci: no unacked findings in the lookback window")
        return 0

    except Exception as exc:  # noqa: BLE001 -- "could not check" must be its own loud failure
        print(f"::error::main-without-ci check failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
