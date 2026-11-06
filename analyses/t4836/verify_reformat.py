#!/usr/bin/env python3
"""t/4836 format-only fix: prove the re-saved files are deep-equal to 902c800b (content, not bytes).
Per the TL's instruction, this uses Python's json module -- not PowerShell ConvertFrom-Json -- so
there is no risk of the same ISO-8601-string-to-DateTime reparse trap that caused the earlier
classified_at bug (t/4836#11, C1)."""
import json
import subprocess
import sys

FILES = [
    "taxonomy/Origin/accelerationist.json",
    "taxonomy/Origin/safetyist.json",
    "taxonomy/Origin/skeptic.json",
    "taxonomy/Origin/situations.json",
]
OLD_REF = "902c800be9d5713485f4c68d96fb9da3f44876eb"

all_ok = True
for f in FILES:
    old_bytes = subprocess.run(
        ["git", "show", f"{OLD_REF}:{f}"], capture_output=True, check=True
    ).stdout
    old = json.loads(old_bytes)
    with open(f, "rb") as fh:
        new = json.load(fh)
    ok = old == new
    all_ok = all_ok and ok
    print(f"{f}: deep-equal={ok}")

if not all_ok:
    print("FAIL: at least one file is not deep-equal to 902c800b", file=sys.stderr)
    sys.exit(1)
print("PASS: all 4 files are deep-equal to 902c800b (content identical, formatting only differs)")
