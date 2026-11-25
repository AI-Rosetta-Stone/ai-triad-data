# t/291 apply evidence

**Change:** org-014 (NIST) only. Stance claims and edges that sat on marked copies of two documents.

**Authorization:** PI decision recorded on t/291#6; the exact handling confirmed by the TL as within it (p/37#191).

**Inputs** (data `88892711`, sources `39d8573`):

| File | pre sha256-lf | post sha256-lf |
|---|---|---|
| `taxonomy/Origin/organization_stance_claims.json` | `faee6c679747c20fa7f812e16470436bf52033bff932c7502cc28e230ae725bb` | `371c2b347deafb96dfb4bd5bebeeea6eb79ad23d72eab76d1a7bf38ac26a9831` |
| `taxonomy/Origin/organization_edges.json` | `b7377bcc680557447a7f13b0fdd0c399c43fd8986967c05338e8c38cde53272c` | `51fe66837662fb8b4ab00ab113b4977b22f3469dea14e3132f186d4b5b29b107` |

**What changed**

- Claims 77 to 61. 16 removed: 13 whose text org-014 already holds on the canonical document, and 3 that repeat a moved claim. 6 moved to their canonical document (`source_id` only).
- 4 PUBLISHED edges from org-014 to copy documents are `rejected`, with `reviewed_by`, `reviewed_at` and a `review_note`. Each canonical already has its own approved PUBLISHED edge.
- 8 proposed ADVOCATES_FOR edges have copy ids in `source_refs` replaced by their canonicals.
- `claim_count` follows. `last_modified` is `2026-11-25` on both files.

**Checks run by `apply_t291_org014_dedupe.py` before writing:** each frozen key matches exactly one claim or edge; every other claim and edge is equal and in the same order; no duplicate (org, source, text) claim key afterwards; the serializer round-trips both files before and after; the result hashes to the frozen post hashes.

**Apply:** `python data-mutations/t291/apply_t291_org014_dedupe.py --data-root . --mode apply --frozen-sha 3dd7c47249aa0091`, in a clean worktree at `88892711`. Output: `wrote 2 files; all match post_sha256`.

**Revert:** `git revert` the commit.
