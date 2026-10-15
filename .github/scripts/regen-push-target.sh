#!/usr/bin/env bash
# Copyright (c) 2026 Jeffrey Snover. All rights reserved.
# Licensed under the MIT License. See LICENSE file in the project root.
#
# t/4226 (prevention for the t/4064 probe incident, t/4064#10): source-index-regen.yml's
# commit-back used to push with a hardcoded `git push origin HEAD:main`, regardless of which
# ref actually triggered the run. A probe run on a non-main branch therefore fast-forwarded
# data main with the probe's own commit -- a single-context assumption (the workflow only
# ever ran on `main` when this was written; it does not anymore).
#
# This script is the ONE place that decides the commit-back's push target, based on the
# triggering ref (GITHUB_REF, the FULL ref -- not GITHUB_REF_NAME, which can't tell a branch
# apart from a same-named tag or a `123/merge` PR ref). FAILS CLOSED: only `refs/heads/<name>`
# produces a target. Anything else (empty, a tag, a pull ref) is refused outright, never
# defaulted to `main` or silently skipped -- a caller that gets no target must stop, not guess.
#
# Output on success: `HEAD:<branch>` (the exact `git push origin <refspec>` argument).
# Output on failure: nothing to stdout; an `::error::` line to stderr; exit 1.
set -euo pipefail

ref="${GITHUB_REF:-}"

case "$ref" in
  refs/heads/*)
    branch="${ref#refs/heads/}"
    if [ -z "$branch" ]; then
      echo "::error::regen-push-target: empty branch name after stripping refs/heads/ (GITHUB_REF='$ref') -- refusing to compute a commit-back target" >&2
      exit 1
    fi
    echo "HEAD:${branch}"
    ;;
  *)
    echo "::error::regen-push-target: GITHUB_REF '$ref' is not refs/heads/* (tag, pull ref, or empty) -- refusing to compute a commit-back target (fail closed, t/4226)" >&2
    exit 1
    ;;
esac
