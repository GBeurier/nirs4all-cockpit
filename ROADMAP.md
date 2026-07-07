# nirs4all-cockpit — Implementation roadmap (one-shot spec, lean)

> Objective: implement the heart of the cockpit in **a rushed but complete one-shot**. Forehead **vanilla static**
> (zero build), admin = **CLI** (`gh`-wrapping). Sentry/PR/security + UI FastAPI = **stubs/phase 2** clearly
> marked. Non-negotiable principle: **the cockpit aggregates & orchestrates, it does not reimplement any repository logic.**
> Detailed design spec:`docs/DESIGN.md`.

## Scope v1 (what we're building NOW)

- ✅`ops/targets.yaml`— complete declarative inventory (package × registry × exact name × workflow × trigger × version-of-truth). - ✅`ops/manual-actions.yaml`— structured migration of`RELEASE_ACTIONS.md`(with`after_done`+`auto_check`). - ✅ **read-only public** collectors: pypi, npm, crates, r-universe, cran, github (releases + workflow runs + issues), local_manifests (version-of-truth). - ✅`reconcile`— model **3 versions** (manifest / release_tag / published) →`green/stale/missing/broken/unknown`(+`source-ahead`, +`excluded`). - ✅`current.json`(+`history/YYYY-MM-DD.json`) committed in`data/`. - ✅ Front **vanilla**`web/index.html`+`app.js`+`style.css`reading`../data/current.json`→ packet × register matrix + downloads + issues + CI. - ✅ CI:`.github/workflows/collect.yml`(cron 6 h → collect → commit) +`pages.yml`(deploy`web/`+`data/`). - ✅`n4a-cockpit`CLI:`collect`,`validate-targets`,`summarize`,`status`,`admin run`,`admin set-secret`,`admin actions`. - ✅ Fixture tests (offline) to reconcile + collector analysis. - 🟡 **Phase 2 (stubs marked TODO)**: collectors`sentry`,`github_prs`,`github_security`, store`snapshot.admin.json`, UI FastAPI 127.0.0.1.

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
│   │   ├── sentry.py              # TODO phase 2 (org wwwciradfr / de.sentry.io / projet nirs4all-studio)
│   │   ├── github_prs.py          # TODO phase 2
│   │   └── github_security.py     # TODO phase 2
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
        reason: <si excluded>          # ex CRAN >5Mo
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
-`expected_version`=`release_tag_version`if a prod tag exists, otherwise`manifest_version`. -`manifest_version > release_tag_version`⇒ badge **`source-ahead`** (not a fake red). -`published == expected`⇒ **green** ·`published < expected`⇒ **stale** · 404/absent ⇒ **missing**
  ·`Version:null`/build failed/last release-run failed ⇒ **broken** · timeout/429/5xx ⇒ **unknown** ·`state:excluded`⇒ **excluded**. - Comparison **SemVer/PEP440-aware** (never lexical), prereleases via`version_aliases`. - Roll-up packet = worst cell (broken>missing>stale>unknown>source-ahead>green; excluded ignored).

## APIs (endpoints, traps) — summary (details in docs/DESIGN.md §4 and Appendix C §4)
- PyPI`https://pypi.org/pypi/{pkg}/json`→`info.version`(no real downloads here). 404=missing. - pypistats`…/api/packages/{pkg}/recent`(**429 possible** → cache+backoff,`unknown`). overall ~180 days. - npm`https://registry.npmjs.org/{pkg}`(scoped`%2F`); downloads`api.npmjs.org/downloads/point/last-month/{pkg}`(**scoped 404 + error in HTTP 200** → parse the body). -`https://crates.io/api/v1/crates/{crate}`crates (**User-Agent required**, otherwise 403). 404=missing. - R-universe`https://gbeurier.r-universe.dev/api/packages`(`Version:null`=broken). - CRAN`https://crandb.r-pkg.org/{pkg}`(404 as long as not accepted); cranlogs`…/downloads/total/last-month/{pkg}`(**0 in 200** ≠ missing). - GitHub releases/runs/issues:`GITHUB_TOKEN`ambient (5000/h); Search issues 30/min;`download_count`per asset.

## Package inventory (LOCK in targets.yaml — check names/inputs against real workflows)
- **nirs4all** (nirs4all repo, python_pyproject) — pypi`nirs4all`; github-release. trigger`github_release_published`(`publish.yml`). - **nirs4all-methods** (tag) — pypi`nirs4all-methods`(release-wheels.yml) **+** pypi`pls4all`(release-python.yml); npm`@nirs4all/methods`(release-npm.yml); r-universe`n4m`+`pls4all`(release-r.yml); notch`n4m`+`pls4all`; github-release. - **nirs4all-formats** (cargo_workspace) — pypi`nirs4all-formats`(release.yml); crates`nirs4all-formats{,-core,-capi,-cli}`(release-crates.yml, input dry_run); npm`@nirs4all/formats-wasm`(release-npm.yml, input publish); r-universe`nirs4allformats`+`nirs4allformats.lite`(release-r.yml); cran`nirs4allformats` **excluded** (manual policy: do NOT submit); screen **excluded** (>5MB); github-release. - **nirs4all-io** (cargo_workspace) — pypi`nirs4all-io`(release.yml); crates`nirs4all-io{,-core,-capi,-cli}`; npm`@nirs4all/io-wasm`; r-universe`nirs4allio`; github-release. - **nirs4all-datasets** (cargo_workspace or python) — pypi`nirs4all-datasets`(release-python.yml); crates`nirs4all-datasets{,-core,-capi,-cli}`; npm`@nirs4all/datasets-wasm`; r-universe`nirs4alldatasets`; github-release. - **nirs4all-core** (canonical RC aggregate) — github-release **`nirs4all-core`**; tracked pypi **`nirs4all-core`** (PyPI published at `0.3.0`; product version `0.3.0` is live on crates.io/npm/GitHub Release assets); crates/npm/r-universe logical package name **`nirs4all`**. - **nirs4all-ui** (React/TS shared reusable components/assets package, outside core aggregation lock) — tracked npm`nirs4all-ui` + Pages showcase. - **nirs4all-aom** (python) — pypi`nirs4all-aom`(publish-pypi.yml). - **dag-ml** (cargo_workspace) — crates`dag-ml{,-core,-arrow,-capi,-cli,-py,-wasm}` are tracked as published RC surfaces at `0.2.5`; npm`dag-ml-wasm` is published at `0.2.5`; PyPI`dag-ml` remains blocked by Trusted Publisher. - **dag-ml-data** (cargo_workspace) — crates`dag-ml-data{,-core,-arrow,-capi,-cli,-provider,-py,-wasm}` are tracked as published RC surfaces at `0.2.5`; r-universe`dagmldata` may lag until rebuild; PyPI`dag-ml-data` remains blocked by Trusted Publisher. - (Client-side-only / Pages-only: nirs4all-web, nirs4all-org, demo-pages formats, methods docs → followed in`deploy`on the CI side.)
- **nirs4all-providers** (Python optional provider clients, outside core aggregation lock) — tracked pypi`nirs4all-providers` (current blocker: Trusted Publisher / `invalid-publisher` on v0.2.7; tagged GitHub Release carries fallback wheel/sdist assets); read-side bridge over datasets/repository neutral contracts only. - **nirs4all-tools** (Python migration/converter toolkit, outside runtime core) — tracked pypi`nirs4all-tools` (current blocker: Trusted Publisher / `invalid-publisher` on v0.0.4).

## CLI
```
n4a-cockpit collect [--targets ops/targets.yaml] [--out data/current.json] [--only pkg,...] [--offline]
n4a-cockpit validate-targets ops/targets.yaml
n4a-cockpit summarize data/current.json
n4a-cockpit status [pkg]                         # table colorée lue depuis current.json
n4a-cockpit admin run <pkg> <registry> [--publish] [--dry-run/--no-dry-run]   # gh workflow run, dry-run défaut
n4a-cockpit admin set-secret <repo> <NAME> --from-file <path>                 # gh secret set, jamais affiché
n4a-cockpit admin actions [--md]                 # manual-actions.yaml + auto_check vs current.json
```
Admin guardrails: refuse if`gh auth status`fails;`--dry-run`default; confirmation for publish/secret/tag; tokens referenced by path, never read except`gh secret set`; refuse trigger ≠ declarable (tag-only → offers the tag command, does not run it).

## CI
-`collect.yml`:`schedule cron "17 */6 * * *"`+`workflow_dispatch`;`contents: write, actions: read, issues: read`permissions; pip install -e .[collect];`n4a-cockpit collect`; commit`data/*.json`via git-auto-commit;`GITHUB_TOKEN`ambient. **MVP: collect absent sibling repos → collect runs on the public API only (local_manifests via GitHub raw when the repo is not a local sibling).**
-`pages.yml`: deploys`web/`+`data/`on GitHub Pages (actions/upload-pages-artifact + deploy-pages).

## “Lean” decisions assumed
- Front **vanilla** (not Vite/React): Immediate pages, zero node_modules, zero CI build. Upgrade React possible later. - Admin = **CLI** only (no FastAPI UI in v1). - Public store only (`current.json`);`snapshot.admin.json`+ Sentry/PR/security = phase 2 stubbed. -`local_manifests`: in CI (no siblings) → reads the truth-version via **GitHub raw** (`raw.githubusercontent.com/GBeurier/{repo}/{default}/…`); locally → reads`../<repo>`.

## Definition of “finished” (gate one-shot)
1.`python -m compileall cockpit`OK;`ruff check`clean if available. 2.`n4a-cockpit validate-targets ops/targets.yaml`OK. 3.`n4a-cockpit collect`produces a full public`data/current.json`; any `--only` probe must write to an explicit scratch `--out` path. 4.`tests/`pass (offline, fixtures). 5.`web/index.html`opens and renders the matrix from`data/current.json`. 6. README explains collect/serve/admin + phase 2 status.
