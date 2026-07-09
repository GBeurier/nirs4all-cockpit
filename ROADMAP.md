# nirs4all-cockpit — Implementation status and operating roadmap

> Objective: keep a public, static release cockpit for the NIRS4ALL ecosystem.
> The v1 cockpit is implemented as a vanilla static dashboard plus a CLI
> collector/admin surface. Non-negotiable principle: **the cockpit aggregates and
> orchestrates; it does not reimplement repository release logic.** Operational
> truth lives in `README.md`, `ops/targets.yaml`, `ops/manual-actions.yaml`, the
> generated `data/*.json` snapshots, and the offline test suite.

## Scope v1 (implemented)

- ✅ `ops/targets.yaml` — complete declarative inventory: package x registry x exact name x workflow x trigger x version-of-truth.
- ✅ `ops/manual-actions.yaml` — structured manual release queue with `after_done` and `auto_check`.
- ✅ Read-only public collectors: PyPI, npm, crates.io, R-universe, CRAN, GitHub releases/workflow runs/issues, and local manifests.
- ✅ `reconcile` — manifest / release tag / published version state model with `green`, `stale`, `pending`, `missing`, `broken`, `unknown`, `source-ahead`, and `excluded`.
- ✅ Generated public snapshots: `data/current.json`, `data/manual-actions.json`, and history snapshots.
- ✅ Vanilla static dashboard: `web/index.html`, `web/app.js`, and `web/style.css`, with manual blockers intentionally rendered at the bottom.
- ✅ CI workflows: `collect.yml` for scheduled/manual collection and commits; `pages.yml` for GitHub Pages deploy on pushes, successful collect completion, or manual dispatch.
- ✅ `n4a-cockpit` CLI: `collect`, `validate-targets`, `summarize`, `status`, `admin run`, `admin set-secret`, `admin actions`, and local-only `admin collect`.
- ✅ Local-only admin snapshot: traffic, open PRs, security alerts, and Sentry counters are collected into gitignored `data/admin/snapshot.admin.json`; they are never deployed to the public Pages site.
- ✅ Offline fixture tests for version parsing, collectors, reconciliation, topology, and dashboard DOM smoke.
- 🟡 Phase 2 remains intentionally out of v1: any local FastAPI/admin UI and richer long-term admin/history views. The v1 admin signals remain CLI-only and local-only.

## Layout

```
nirs4all-cockpit/
├── pyproject.toml                 # package python "nirs4all-cockpit", entrypoint n4a-cockpit
├── README.md
├── .gitignore                     # *_token, *.env, __pycache__, dist, .venv, node noise
├── ops/
│   ├── targets.yaml
│   └── manual-actions.yaml
├── cockpit/
│   ├── __init__.py
│   ├── model.py                   # pydantic v2 : Targets, Package, Target, Snapshot, PackageStatus, State
│   ├── version.py                 # normalisation SemVer/PEP440/R-devel + comparaison + aliases
│   ├── http.py                    # client httpx partagé: UA descriptif, timeout, retry/backoff, cache disque léger
│   ├── collect/
│   │   ├── __init__.py
│   │   ├── base.py                # Fetched{value,endpoint,http_status,fetched_at,error}
│   │   ├── pypi.py  npm.py  crates.py  runiverse.py  cran.py
│   │   ├── github.py              # releases + workflow runs + issues (GITHUB_TOKEN ambiant)
│   │   ├── local_manifests.py     # lit la version-de-vérité depuis les manifests des repos frères (../<repo>)
│   │   ├── sentry.py              # admin-only local Sentry aggregate counters
│   │   ├── github_prs.py          # admin-only local open-PR counts
│   │   └── github_security.py     # admin-only local security alert counts
│   ├── reconcile.py               # snapshot(faits) -> current.json (états)
│   ├── snapshot.py                # écrit current.json + history/, compaction mensuelle
│   ├── admin.py                   # wrappers `gh` : workflow run / secret set ; jamais de publish direct
│   ├── manual_actions.py          # charge manual-actions.yaml + auto_check vs current.json
│   └── cli.py                     # Typer
├── web/
│   ├── index.html  app.js  style.css
├── data/
│   ├── current.json               # généré (sample committé)
│   └── history/
├── tests/
│   ├── fixtures/*.json
│   ├── test_version.py  test_reconcile.py  test_collect_parsing.py
└── .github/workflows/
    ├── collect.yml
    └── pages.yml
```

## Data contracts

### `ops/targets.yaml`
```yaml
schema_version: 1
owner: GBeurier
packages:
  - id: <logique>
    repo: <repo-name>                  # dossier frère ../<repo> + GitHub GBeurier/<repo>
    source_of_truth:                   # comment lire manifest_version
      strategy: cargo_workspace|python_pyproject|python_attr|r_description|tag
      path: <fichier>
      attr: <optionnel, pour python_attr>
    release_trigger:                   # comment une release part (admin)
      kind: tag|workflow_dispatch|github_release_published
    channel: production|prerelease
    issues_repo: <repo>
    targets:
      - registry: pypi|npm|crates|r-universe|cran|github-release
        name: <nom EXACT par registre>
        workflow: { file: <release-*.yml>, inputs: {k: v} }   # optionnel (admin)
        state: tracked|excluded
        reason: <si excluded>          # ex CRAN size exception or intentionally R-universe-only
    version_aliases: { "0.2.0-alpha.1": { pep440: "0.2.0a1", r_devel: "0.2.0.9000" } }
```

### `data/current.json`
```json
{ "schema_version": 1, "generated_at": "...Z",
  "generator": {"repo":"GBeurier/nirs4all-cockpit","workflow":"collect.yml","run_id":null},
  "packages": [ { "id":"...","repo":"...",
    "source": {"manifest_version":"...","release_tag_version":"...","expected_version":"...","commit":"..."},
    "targets": [ {"registry":"...","name":"...","published_version":"...","status":"green",
                  "downloads":{"last_day":null,"last_week":null,"last_month":null,"total":null,"source":"..."},
                  "evidence":{"version_endpoint":"...","downloads_endpoint":"..."},
                  "error":null } ],
    "workflows":[{"file":"release.yml","last_run":{"conclusion":"success","created_at":"...","head_sha":"..."}}],
    "issues":{"open":0,"bugs":0} } ],
  "summary": {"green":0,"stale":0,"missing":0,"broken":0,"unknown":0,"excluded":0} }
```

## State machine (reconcile)
- `expected_version` = `release_tag_version` if a prod tag exists, otherwise `manifest_version`.
- `manifest_version > release_tag_version` ⇒ badge **`source-ahead`** (not a fake red).
- `published == expected` ⇒ **green**.
- `published < expected` ⇒ **stale**.
- Submitted or intentionally waiting on an external review queue ⇒ **pending**.
- 404/absent ⇒ **missing**.
- `Version:null`, build failed, or last release-run failed ⇒ **broken**.
- timeout/429/5xx ⇒ **unknown**.
- `state:excluded` ⇒ **excluded**.
- Comparison is SemVer/PEP440-aware, never lexical; prereleases use `version_aliases`.
- Roll-up packet = worst cell (`broken` > `missing` > `stale` > `pending` > `unknown` > `source-ahead` > `green`; `excluded` ignored).

## APIs (endpoints, traps) — summary
- PyPI`https://pypi.org/pypi/{pkg}/json`→`info.version`(no real downloads here). 404=missing. - pypistats`…/api/packages/{pkg}/recent`(**429 possible** → cache+backoff,`unknown`). overall ~180 days. - npm`https://registry.npmjs.org/{pkg}`(scoped`%2F`); downloads`api.npmjs.org/downloads/point/last-month/{pkg}`(**scoped 404 + error in HTTP 200** → parse the body). -`https://crates.io/api/v1/crates/{crate}`crates (**User-Agent required**, otherwise 403). 404=missing. - R-universe`https://gbeurier.r-universe.dev/api/packages`(`Version:null`=broken). - CRAN`https://crandb.r-pkg.org/{pkg}`(404 as long as not accepted); cranlogs`…/downloads/total/last-month/{pkg}`(**0 in 200** ≠ missing). - GitHub releases/runs/issues:`GITHUB_TOKEN`ambient (5000/h); Search issues 30/min;`download_count`per asset.

## Package inventory (LOCK in targets.yaml — check names/inputs against real workflows)
- **nirs4all** (production Python oracle, held) — pypi`nirs4all`; github-release via `publish.yml`.
- **nirs4all-methods** — pypi`nirs4all-methods` + `pls4all`; npm`@nirs4all/methods`; r-universe`n4m` + `pls4all`; github-release.
- **nirs4all-formats** (`0.2.6` train) — pypi`nirs4all-formats`; crates`nirs4all-formats{,-core,-capi,-cli}`; npm`@nirs4all/formats-wasm`; r-universe`nirs4allformats`; CRAN explicitly excluded / R-universe-only for `nirs4allformats`.
- **nirs4all-io** — pypi`nirs4all-io`; crates`nirs4all-io{,-core,-capi,-cli}`; npm`@nirs4all/io-wasm`; r-universe`nirs4allio`; github-release.
- **nirs4all-datasets** — pypi`nirs4all-datasets`; crates`nirs4all-datasets{,-core,-capi,-cli}`; npm`@nirs4all/datasets-wasm`; r-universe`nirs4alldatasets`; CRAN manual resubmission is tracked and needs the 24 MB size-exception comment; github-release.
- **nirs4all-core** (`0.3.7` train) — pypi`nirs4all-core`; github-release`nirs4all-core`; crates/npm/r-universe logical package name `nirs4all`.
- **nirs4all-ui** (`0.1.9` train) — tracked npm`nirs4all-ui` + Pages showcase; outside core aggregation lock.
- **dag-ml** (`0.2.7` train) — pypi`dag-ml`; npm`dag-ml-wasm`; crates`dag-ml{,-core,-arrow,-capi,-cli}`.
- **dag-ml-data** (`0.2.8` train) — pypi`dag-ml-data`; npm`dag-ml-data-wasm`; crates`dag-ml-data{,-core,-arrow,-capi,-cli,-provider}`; r-universe`dagmldata` may lag until rebuild.
- **nirs4all-providers** (`0.2.9` train) — tracked pypi`nirs4all-providers`; read-side bridge over datasets/repository neutral contracts only.
- **nirs4all-tools** (`0.0.5` train) — tracked pypi`nirs4all-tools`; migration/converter toolkit outside runtime core.
- **nirs4all-aom**, **nirs4all-web**, **nirs4all-org**, demo pages and docs deployments are followed through their explicit targets in `ops/targets.yaml`.

## CLI
```
n4a-cockpit collect [--targets ops/targets.yaml] [--out data/current.json] [--only pkg,...] [--offline]
n4a-cockpit validate-targets ops/targets.yaml
n4a-cockpit summarize data/current.json
n4a-cockpit status [pkg]                         # table colorée lue depuis current.json
n4a-cockpit admin run <pkg> <registry> [--publish] [--dry-run/--no-dry-run]   # gh workflow run, dry-run défaut
n4a-cockpit admin set-secret <repo> <NAME> --from-file <path>                 # gh secret set, jamais affiché
n4a-cockpit admin collect [--only pkg,...] [--out data/admin/snapshot.admin.json] # local-only admin snapshot
n4a-cockpit admin actions [--md]                 # manual-actions.yaml + auto_check vs current.json
```
Admin guardrails: refuse if`gh auth status`fails;`--dry-run`default; confirmation for publish/secret/tag; tokens referenced by path, never read except`gh secret set`; refuse trigger ≠ declarable (tag-only → offers the tag command, does not run it).

## CI
-`collect.yml`:`schedule cron "17 0 * * *"`+`workflow_dispatch`;`contents: write, actions: read, issues: read`permissions; pip install -e .; shallow-clone public sibling repos under `_siblings/`;`n4a-cockpit collect`; commit`data/*.json`with plain git commands;`GITHUB_TOKEN`ambient.
-`pages.yml`: deploys`web/`+`data/`on GitHub Pages (actions/upload-pages-artifact + deploy-pages) on push, successful `collect` workflow completion, or manual dispatch.

## “Lean” decisions kept

- Frontend remains **vanilla static**: immediate Pages deploy, no Node build, no app server.
- Admin remains **CLI-only** in v1; no FastAPI/admin UI is shipped.
- Public store remains `current.json` plus `manual-actions.json`; private `data/admin/snapshot.admin.json` is local-only, gitignored, and built only by `admin collect`.
- Sentry/PR/security collectors are admin-only local signals and must not block or redden the public release cockpit.
- `local_manifests`: in CI, truth versions are read via GitHub raw URLs; locally, sibling checkouts under `../<repo>` are preferred.

## Definition of “finished” (gate one-shot)
1.`python -m compileall cockpit`OK;`ruff check`clean if available. 2.`n4a-cockpit validate-targets ops/targets.yaml`OK. 3.`n4a-cockpit collect`produces a full public`data/current.json`; any `--only` probe must write to an explicit scratch `--out` path. 4.`tests/`pass (offline, fixtures). 5.`web/index.html`opens and renders the matrix from`data/current.json`. 6. README/ROADMAP explain collect/serve/admin, the local-only admin snapshot, and remaining phase 2 UI scope.
