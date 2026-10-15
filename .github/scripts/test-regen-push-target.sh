#!/usr/bin/env bash
# Copyright (c) 2026 Jeffrey Snover. All rights reserved.
# Licensed under the MIT License. See LICENSE file in the project root.
#
# t/4226: both-arms test of regen-push-target.sh's fail-closed predicate (Guard Testability
# rule -- PR CI can't exercise a main-only predicate against a real non-main ref, so this
# exercises it directly, no CI run needed). Run with: bash .github/scripts/test-regen-push-target.sh
set -uo pipefail

SCRIPT="$(dirname "$0")/regen-push-target.sh"
PASS=0
FAIL=0

check_pass() {
  local ref="$1" expected="$2"
  local out
  out="$(GITHUB_REF="$ref" bash "$SCRIPT" 2>/dev/null)"
  local code=$?
  if [ "$code" -eq 0 ] && [ "$out" = "$expected" ]; then
    echo "PASS: GITHUB_REF='$ref' -> '$out'"
    PASS=$((PASS + 1))
  else
    echo "FAIL: GITHUB_REF='$ref' -> exit=$code out='$out' (expected exit=0 out='$expected')"
    FAIL=$((FAIL + 1))
  fi
}

check_fault() {
  local ref="$1" label="$2"
  local out
  out="$(GITHUB_REF="$ref" bash "$SCRIPT" 2>/dev/null)"
  local code=$?
  if [ "$code" -ne 0 ] && [ -z "$out" ]; then
    echo "PASS (fault-arm, $label): GITHUB_REF='$ref' -> exit=$code, no stdout"
    PASS=$((PASS + 1))
  else
    echo "FAIL (fault-arm, $label): GITHUB_REF='$ref' -> exit=$code out='$out' (expected nonzero exit, empty stdout)"
    FAIL=$((FAIL + 1))
  fi
}

# Success arms
check_pass "refs/heads/main" "HEAD:main"
check_pass "refs/heads/t4226-safe-commit-back" "HEAD:t4226-safe-commit-back"
check_pass "refs/heads/some/nested-branch" "HEAD:some/nested-branch"

# Fault arms (t/4226 condition 1) -- every one of these must fail closed, never default to main
check_fault "" "empty ref"
check_fault "refs/tags/v1.0" "tag ref"
check_fault "refs/pull/123/merge" "pull ref"
check_fault "main" "bare name, no refs/heads/ prefix"

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  exit 1
fi
