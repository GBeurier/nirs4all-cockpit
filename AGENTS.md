# Cockpit contributor instructions

## Read-only health and data

Cockpit collects public registry/CI/issues/stats, never owner release logic.
Tests stay offline through both cockpit.http.get_json and get_text seams; retain registry error-200/404/null-version/zero-download fixtures and tests/test_<area>.py/test_<behavior>. Unknown is not zero; preserve original observation/carried-forward dates and [status semantics](README.md#status-model), separately from platform/delivery evidence.
Public data/current.json is distinct from ignored local data/admin/snapshot.admin.json; push-scoped/semi-private signals never enter public/deployed data. Never commit/print/store tokens or admin snapshots. GITHUB_TOKEN/GOATCOUNTER_TOKEN/SENTRY_AUTH_TOKEN retain their [public/admin conditions](README.md#public-vs-admin-signals).
`--only` needs explicit scratch `--out`, never the public snapshot. Refresh Cockpit LAST; existing cron and guarded admin examples grant no agent refresh, dispatch, secret-setting or deployment authority. Keep [Quickstart prerequisites](README.md#quickstart).

## Commands and conventions

From this checkout/package environment retain:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
n4a-cockpit validate-targets ops/targets.yaml
n4a-cockpit collect --offline
n4a-cockpit status
python -m http.server 8000
pytest -q
ruff check .
```

Serve repo root at http://localhost:8000/web/index.html; fetches fail over file://. Keep Python 3.11/Ruff 120/py311 E/F/I/UP/B, four spaces, snake_case modules/functions, PascalCase/Pydantic and registry-specific names, dependency-free vanilla frontend. Focus Conventional Commits; PRs need context/issue/checks and UI screenshots when relevant.
The [staging build/validate recipe](docs/release-staging.md#public-release-staging-projection) requires explicitly selected sanitized inputs and fail-closed validation; it proves no registry publication/artifact availability and grants no UI/deploy. Its [native-candidate profile](docs/release-staging.md#local-native-r4v1-candidate) retains governance/cwd/limits and the byte-identical Org mirror; staging is no V1 announcement. Historical receipts are not current support.
Follow [LICENSING](LICENSING.md) and [notices](THIRD_PARTY_NOTICES.md): `CeCILL-2.1 OR AGPL-3.0-or-later`, optional commercial contact and authoritative upstream component terms.

## Working rules

Read applicable instructions first and preserve dirty work. If `../AGENTS.md` exists, read it within the current user scope; this file also works alone.
Use CodeGraph FIRST only with this checkout's own `.codegraph/` (exact projectPath or local CLI); never auto-index or use an ancestor index. Source, tests and builds are final authority.
Record actual commands, exits and skips. Keep secrets, private data and build output out of Git. Examples grant no install, network, science, publication, hosting, frontend or Git authority.
All project content, including UI text, docs, tests, reports, PRs and commits, is English; conversation may be French. Preserve names, identifiers, quotations and provenance.
