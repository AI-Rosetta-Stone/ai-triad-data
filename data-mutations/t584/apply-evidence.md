# t/584 apply evidence

**Change:** 48 edges of `taxonomy/Origin/organization_edges.json` whose `rationale` was a pipeline diagnostic (`match_basis=...`) get a plain sentence; the diagnostics move to a new optional field `match_meta`. 5 proposed edges of org-014 with no supporting claim left are rejected in the same write.

**Authorization:** PI decision recorded on t/584#22 (sentences listed on t/584#11 as amended by #21); the freeze confirmed by the TL as within it (t/584#31, p/37#257). Frozen list checked by Quality before the write (p/43#143).

**Inputs** (data `1b40d9cb`, sources `39d8573`; the file was last changed by `f9d5aff7`):

| File | pre sha256-lf | post sha256-lf |
|---|---|---|
| `taxonomy/Origin/organization_edges.json` | `51fe66837662fb8b4ab00ab113b4977b22f3469dea14e3132f186d4b5b29b107` | `107aa550d1c38ee6ac662b48f5159d887da923fddb448c686e5b6dda719c2715` |

**What changed**

- 48 edges: `rationale` replaced; `match_meta` added as the edge's last key (stage, basis, and for claim-matched edges families, best cosine, NLI fields, and the representative claim's source id and text hash).
- 5 of them (org-014 ADVOCATES_FOR `saf-desires-012`, `acc-intentions-103`, `saf-intentions-016`, `saf-intentions-201`, `skp-intentions-094`): `status` proposed to rejected, with `reviewed_by`, `reviewed_at` and `review_note`.
- `last_modified` is `2026-11-25`. 126 edges before and after, in the same order. No other edge and no other field changes.

**Checks run by `apply_t584_org_edge_rationale.py` before writing:** the file hashes to the frozen pre hash; each frozen key matches exactly one edge, which still holds the frozen old rationale and status and has no `match_meta`; every edge outside the freeze is equal and in place; in a frozen edge only frozen fields differ and existing keys keep their order; the serializer round-trips the file before and after; the result hashes to the frozen post hash.

**Apply:** `python data-mutations/t584/apply_t584_org_edge_rationale.py --data-root . --mode apply --frozen-sha 47fc302e65a497e1`, in a clean worktree at `e149d3b9` (the freeze commit, on `1b40d9cb`). Output: `wrote 1 file; it matches post_sha256`.

**Revert:** `git revert` the commit.
