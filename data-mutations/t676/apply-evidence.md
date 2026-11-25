# t/676 apply evidence

**Change:** `taxonomy/Origin/org-edge.json` is removed. It was a stale copy of the organization edges (97 edges, last changed 2026-07-20 by `67bde194`), with 19 rationales that are pipeline diagnostics (`match_basis=...`). The live file is `taxonomy/Origin/organization_edges.json` (126 edges), which t/584 rewrote; it is not touched here.

**Authorization:** PI decision, recorded by the Tech Lead on t/676#5. The Comp-Linguist confirmed the file is not needed (t/676#3).

**The removed file** (data `e66f2822`): sha256-lf `7a9d0df1ad0af88495817215f92af3394673701ca895ef063f97ed5b1fa55213`, 33,620 bytes. It stays in history: `git show 67bde194:taxonomy/Origin/org-edge.json`.

**Who read it (checked on research `origin/main` d4df3f396 and data `origin/main` e66f2822):** no product code, cmdlet, server or renderer file names it. Two mentions remain in the research repo, neither of which reads it: `research/comp-linguist/analyses/p0-t1767/_p0_score.py` line 35 lists the name among files a directory scan skips (harmless when the file is absent; the Comp-Linguist asked for no change, t/676#3), and a design note.

**Check B (will a producer recreate it):** nothing in the research repo writes a file of this name. The organization-edge writers (`Import-OrganizationEdge`, `Invoke-OrgClaimMatching`, `Invoke-OrgPublishedSeeding`) write `organization_edges.json`.

**Apply:** `git rm taxonomy/Origin/org-edge.json` in a clean worktree at `9f5a96b7` (the freeze commit, on `e66f2822`).

**Revert:** `git revert` the commit.
