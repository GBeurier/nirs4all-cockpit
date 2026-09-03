# Public release staging projection

`data/release-staging.json` is a deterministic, non-publishing projection of
the explicitly selected aggregation inputs in `ops/release-staging/`. It is
fixed to phase `R2` and status `in_progress`; it does not assert that R2, R3, or
V1 has been published.

The public input pair is a sanitized view of the upstream Ecosystem aggregation
manifest and lock. Its `derived_from` digests preserve that provenance while
local workspace selection, branches, validation commands, contract payloads,
artifacts, and downloads are deliberately absent. Updating the projection is an
explicit three-file review: update the public manifest and lock from a qualified
upstream lock, then run:

```console
python scripts/release_staging.py build \
  --manifest ops/release-staging/public-manifest.json \
  --lock ops/release-staging/public-lock.json \
  --out data/release-staging.json
python scripts/release_staging.py validate \
  --manifest ops/release-staging/public-manifest.json \
  --lock ops/release-staging/public-lock.json \
  --projection data/release-staging.json
```

The validator fails closed on incomplete or divergent membership, local or
worktree paths, private/non-GitHub repository URLs, dirty states, malformed
commits, inconsistent versions, invalid lockstep status, and non-canonical
output. It performs no network access and does not prove registry publication
or artifact availability.

UI integration is intentionally not part of this slice. The existing dashboard
continues to read the independently collected, timestamped health snapshot in
`data/current.json`; `data/release-staging.json` is staged as public data but is
not rendered until a separate UI contract is reviewed. GitHub Pages does not
deploy from this branch or CI gate, and this change adds no deployment step.

## Local native R4/V1 candidate

`data/native-candidate-staging.json` is a separate, deterministic view of the
local native-backend candidate recorded by governance commit
`0502c64cf4c562fa21bdcd326f89270f0d4ac505`. It is not derived from, and does
not modify, the canonical release lock. Its schema cannot carry download or
registry links: every component is `unavailable`, the train is `no_go`, and the
dashboard labels it staging-only.

From the ecosystem workspace, reproduce it with:

```console
python scripts/native_candidate_staging.py build \
  --governance-repo ../nirs4all-ecosystem \
  --governance-commit 0502c64cf4c562fa21bdcd326f89270f0d4ac505 \
  --workspace-root .. \
  --out data/native-candidate-staging.json
```

The projector reads the ledger from that exact Git object, resolves package
versions from each exact candidate commit, and records the ledger digest. The
same output bytes are staged in nirs4all-org; publication remains a separate,
lock-authorized operation.

The final projection records the exact ownership and capability-governance
witnesses, CUT-002's structured warning plus intentionally process-local opt-in
counter, and one real four-surface WSL performance campaign. Performance data
is explicitly record-only: the reference budgets are not frozen, no threshold
is claimed passed, and the evidence does not make the candidate release-eligible.
It also exposes the bounded local closures for API-001/004/005, CAP-001,
DAG-001, DOC-001, GATE-001, REL-003, STU-006, UI-001, WEB-001 and WEBREL-001.
INST-001 and RC-001 are explicitly prepared but not closed; SEC-001, SOAK-001
and PERF-002 remain advanced but open. UI 0.1.13 is represented only as an unavailable local source
identity; the observed public registry remains at 0.1.12 and no tarball or
registry URL is exposed by this snapshot.
