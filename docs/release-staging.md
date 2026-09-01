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
