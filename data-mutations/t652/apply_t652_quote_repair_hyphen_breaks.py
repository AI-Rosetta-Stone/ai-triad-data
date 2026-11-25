#!/usr/bin/env python3
"""t/652, second quote-repair freeze: the same change as apply_t652_quote_repair.py, for the quotes whose
repaired text the guard keeps as one passage at coverage 1.0 but does not call 'exact', because the source
breaks a word over a line end (Tech Lead t/652#26; the Comp-Linguist's amended exception (b) on t/389).

Reads ONLY frozen_t652_quote_repair_hyphen_breaks.json, beside this file. It runs the first script's own
checks and writer, unchanged, on that freeze. It must be applied AFTER the first freeze: where both touch
a file, this freeze's pre_sha256 is the first freeze's post_sha256, so applying them in the wrong order
is refused.

  python apply_t652_quote_repair_hyphen_breaks.py --data-root . [--mode apply --frozen-sha <sha256-lf>]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import apply_t652_quote_repair as first  # noqa: E402

first.FROZEN = HERE / "frozen_t652_quote_repair_hyphen_breaks.json"

if __name__ == "__main__":
    sys.exit(first.main())
