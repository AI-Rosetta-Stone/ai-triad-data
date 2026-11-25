# t/652 apply evidence: stored quotes that copied a snapshot's damaged '?'

**Change:** 112 key-point quotes (`pov_summaries.<camp>.key_points[].verbatim`) in 31 summaries have the `?` marks they copied from a damaged snapshot replaced by the character the snapshot now has. Class: **model-copied damage restored, t/652**. No field is added to any summary; each quote's old text is kept in the freeze records, so every change is traceable and reversible.

**Background:** an old PDF conversion replaced characters with `?` in 99 snapshots; t/652 put 8,089 of them back (ai-triad-sources `3d0d819f`). Summaries of those documents quote the damaged text, so after the repair the quote guard (ai-triad-research PR #5419) would have dropped quotes that are faithful to the source.

**Authorization:** Tech Lead ruling t/652#16 (a narrow exception to "a quote is stored as the model wrote it", accepted by the Comp-Linguist on t/389), go on the first freeze (p/37#275); gate for the second freeze t/652#26 with the Comp-Linguist's amended exception (b), go bound to `7e956562` (p/37#280). Quality checked both freezes in full before the write (p/43#155).

**Two freezes, applied in this order** (data `6e95f275`; matcher #5419 at `37728938d`):

| Freeze | Quotes | Files | Gate | sha256-lf of the freeze |
|---|---|---|---|---|
| `frozen_t652_quote_repair.json` | 107 | 30 | the repaired text is decided **exact** against the repaired snapshot | `261ac491c8c2f54d55b933826ecb089b5b68fb3d3efd54cdb121e5cc8d54ecfa` |
| `frozen_t652_quote_repair_hyphen_breaks.json` | 5 | 3 | the guard keeps the repaired text as one passage at coverage 1.0, stores exactly the repaired text, and the only difference from the source passage is a word broken over a line end | `a219f704d70c0fd2eceb40a95da10e212a04d5fcde22c654357bdfb2686d3aff` |

Two files are in both freezes; 31 files change in all. The second freeze's pre hash for a shared file is the first freeze's post hash, so applying them out of order is refused.

**How each new text was made:** the quote is found in the old snapshot by its letters, digits and marks in order; each `?` then stands on one byte of that snapshot, and becomes the text t/652's frozen character map (ai-triad-sources `data-mutations/t652/frozen_t652_lost_characters.json`) has for that byte. No other map is used and nothing else in the quote changes. 157 marks restored: ligatures as letters, and a few Greek letters and symbols.

**Left as they are, listed in the freezes with the reason:** 104 quotes with a `?`: 71 are not in the old snapshot in order (the model changed other words too); 32 have no mark in the map (real question marks, or marks t/652 left alone); 1 fails the second gate (an elided quote whose two segments are not one passage).

**Checks run by the apply scripts before writing:** each file hashes to its frozen pre hash and round-trips through the serializer; every frozen JSON path holds exactly the frozen old text, and one mismatch stops the run before anything is written; putting the old texts back gives the original document, so nothing else changed; the result hashes to the frozen post hash.

**Apply**, in a clean worktree at `7e956562` (the freeze commits, on `6e95f275`):
- `python data-mutations/t652/apply_t652_quote_repair.py --data-root . --mode apply --frozen-sha 261ac491c8c2f54d` : `files 30; quotes 107; problems 0`, `wrote 30 files; all match post_sha256`.
- `python data-mutations/t652/apply_t652_quote_repair_hyphen_breaks.py --data-root . --mode apply --frozen-sha a219f704d70c0fd2` : `files 3; quotes 5; problems 0`, `wrote 3 files; all match post_sha256`.

**Check B:** a summary is rewritten only by summarizing the document again, which now reads the repaired snapshot.

**Revert:** `git revert` the commit.
