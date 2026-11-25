# t/629: remove the remaining flight-recorder dumps from main

- Go: the PI, 2026-11-25 ~17:40Z, relayed by the TL (p/102#316); recorded at t/629#14.
- Base: origin/main e147874d. The DevOps Lead's e147874d already removed the two dumps holding the
  revoked Gemini key (t/650); this removes the remaining 8 (5 client, 3 server; all 2026-06-16),
  committed in June by the removed persistDumpToGitHub producer.
- Removals: the 8 files listed under `removals` in frozen_t629_flight_recorder.json. After the change,
  `git ls-files flight-recorder` is 0. `.gitignore` already ignores `flight-recorder/`.
- Second-agent re-count: TaxonomyServer, t/629 (p/93#90), at the first head 62dd343b; same removal set.
- History is not rewritten (PI decision; the key is revoked).
