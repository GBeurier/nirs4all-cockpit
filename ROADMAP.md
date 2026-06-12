# nirs4all-cockpit — Roadmap d'implémentation (spec one-shot, lean)

> Objectif : implémenter en **un one-shot rushé mais complet** le cœur du cockpit. Front **vanilla statique**
> (zéro build), admin = **CLI** (`gh`-wrapping). Sentry/PR/sécurité + UI FastAPI = **stubs/phase 2** clairement
> marqués. Principe non négociable : **le cockpit agrège & orchestre, il ne réimplémente aucune logique de repo.**
> Spec détaillée du design : `docs/DESIGN.md`.

## Scope v1 (ce qu'on construit MAINTENANT)

- ✅ `ops/targets.yaml` — inventaire déclaratif complet (paquet × registre × nom exact × workflow × trigger × version-de-vérité).
- ✅ `ops/manual-actions.yaml` — migration structurée de `RELEASE_ACTIONS.md` (avec `after_done` + `auto_check`).
- ✅ Collecteurs **read-only publics** : pypi, npm, crates, r-universe, cran, github (releases + workflow runs + issues), local_manifests (version-de-vérité).
- ✅ `reconcile` — modèle **3 versions** (manifest / release_tag / published) → `green/stale/missing/broken/unknown` (+`source-ahead`, +`excluded`).
- ✅ `current.json` (+ `history/YYYY-MM-DD.json`) committés dans `data/`.
- ✅ Front **vanilla** `web/index.html` + `app.js` + `style.css` lisant `../data/current.json` → matrice paquet×registre + downloads + issues + CI.
- ✅ CI : `.github/workflows/collect.yml` (cron 6 h → collect → commit) + `pages.yml` (déploie `web/` + `data/`).
- ✅ CLI `n4a-cockpit` : `collect`, `validate-targets`, `summarize`, `status`, `admin run`, `admin set-secret`, `admin actions`.
- ✅ Tests à fixtures (offline) pour reconcile + parsing collecteurs.
- 🟡 **Phase 2 (stubs marqués TODO)** : collecteurs `sentry`, `github_prs`, `github_security`, store `snapshot.admin.json`, UI FastAPI 127.0.0.1.

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

## Contrats de données

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

## Machine à états (reconcile)
- `expected_version` = `release_tag_version` si un tag prod existe, sinon `manifest_version`.
- `manifest_version > release_tag_version` ⇒ badge **`source-ahead`** (pas un faux rouge).
- `published == expected` ⇒ **green** · `published < expected` ⇒ **stale** · 404/absent ⇒ **missing**
  · `Version:null`/build failed/last release-run failed ⇒ **broken** · timeout/429/5xx ⇒ **unknown** · `state:excluded` ⇒ **excluded**.
- Comparaison **SemVer/PEP440-aware** (jamais lexicale), prereleases via `version_aliases`.
- Roll-up paquet = pire cellule (broken>missing>stale>unknown>source-ahead>green ; excluded ignoré).

## APIs (endpoints, pièges) — résumé (détail dans docs/DESIGN.md §4 et Annexe C §4)
- PyPI `https://pypi.org/pypi/{pkg}/json` → `info.version` (pas de vrais downloads ici). 404=missing.
- pypistats `…/api/packages/{pkg}/recent` (**429 possible** → cache+backoff, `unknown`). overall ~180 j.
- npm `https://registry.npmjs.org/{pkg}` (scoped `%2F`) ; downloads `api.npmjs.org/downloads/point/last-month/{pkg}` (**scoped 404 + erreur en HTTP 200** → parser le corps).
- crates `https://crates.io/api/v1/crates/{crate}` (**User-Agent obligatoire**, sinon 403). 404=missing.
- R-universe `https://gbeurier.r-universe.dev/api/packages` (`Version:null`=broken).
- CRAN `https://crandb.r-pkg.org/{pkg}` (404 tant que non accepté) ; cranlogs `…/downloads/total/last-month/{pkg}` (**0 en 200** ≠ missing).
- GitHub releases/runs/issues : `GITHUB_TOKEN` ambiant (5000/h) ; Search issues 30/min ; `download_count` par asset.

## Inventaire des paquets (à VERROUILLER dans targets.yaml — vérifier noms/inputs contre les vrais workflows)
- **nirs4all** (repo nirs4all, python_pyproject) — pypi `nirs4all` ; github-release. trigger `github_release_published` (`publish.yml`).
- **nirs4all-methods** (tag) — pypi `nirs4all-methods` (release-wheels.yml) **+** pypi `pls4all` (release-python.yml) ; npm `@nirs4all/methods-wasm` (release-npm.yml) ; r-universe `n4m` + `pls4all` (release-r.yml) ; cran `n4m`+`pls4all` ; github-release.
- **nirs4all-formats** (cargo_workspace) — pypi `nirs4all-formats` (release.yml) ; crates `nirs4all-formats{,-core,-capi,-cli}` (release-crates.yml, input dry_run) ; npm `@nirs4all/formats-wasm` (release-npm.yml, input publish) ; r-universe `nirs4allformats`+`nirs4allformats.lite` (release-r.yml) ; cran **excluded** (>5Mo) ; github-release.
- **nirs4all-io** (cargo_workspace) — pypi `nirs4all-io` (release.yml) ; crates `nirs4all-io{,-core,-capi,-cli}` ; npm `@nirs4all/io-wasm` ; r-universe `nirs4allio` ; github-release.
- **nirs4all-datasets** (cargo_workspace ou python) — pypi `nirs4all-datasets` (release-python.yml) ; crates `nirs4all-datasets{,-core,-capi,-cli}` ; npm `@nirs4all/datasets-wasm` ; r-universe `nirs4alldatasets` ; github-release.
- **nirs4all-lite** (cargo_workspace) — pypi **`nirs4all-lite`** ; crates **`nirs4all`** ; npm **`nirs4all`** ; r-universe **`nirs4all`** (⚠ nom logique ≠ nom registre).
- **nirs4all-aom** (python) — pypi `nirs4all-aom` (publish-pypi.yml).
- **dag-ml** (cargo_workspace) — crates `dag-ml{,-core,-arrow,-capi,-cli,-py,-wasm}` (aujourd'hui **missing**) ; npm `@nirs4all/dag-ml-wasm`. release-trigger: pas encore de workflow → admin signale « pas de bouton ».
- **dag-ml-data** (cargo_workspace) — crates `dag-ml-data{,-core,-arrow,-capi,-cli,-provider,-py,-wasm}` ; r-universe `dagmldata`.
- (Pages-only, pas de paquet : nirs4all-web, nirs4all-org, formats demo-pages, methods docs → suivis en `deploy` côté CI.)

## CLI
```
n4a-cockpit collect [--targets ops/targets.yaml] [--out data/current.json] [--only pkg,...] [--no-network]
n4a-cockpit validate-targets ops/targets.yaml
n4a-cockpit summarize data/current.json
n4a-cockpit status [pkg]                         # table colorée lue depuis current.json
n4a-cockpit admin run <pkg> <registry> [--publish] [--dry-run/--no-dry-run]   # gh workflow run, dry-run défaut
n4a-cockpit admin set-secret <repo> <NAME> --from-file <path>                 # gh secret set, jamais affiché
n4a-cockpit admin actions [--md]                 # manual-actions.yaml + auto_check vs current.json
```
Garde-fous admin : refuse si `gh auth status` échoue ; `--dry-run` défaut ; confirmation pour publish/secret/tag ; tokens référencés par chemin, jamais lus sauf `gh secret set` ; refuse trigger ≠ déclarable (tag-only → propose la commande tag, ne la lance pas).

## CI
- `collect.yml` : `schedule cron "17 */6 * * *"` + `workflow_dispatch` ; permissions `contents: write, actions: read, issues: read` ; pip install -e .[collect] ; `n4a-cockpit collect` ; commit `data/*.json` via git-auto-commit ; `GITHUB_TOKEN` ambiant. **MVP : collecter les repos frères absents → le collect tourne sur l'API publique seulement (local_manifests via GitHub raw quand le repo n'est pas un sibling local).**
- `pages.yml` : déploie `web/` + `data/` sur GitHub Pages (actions/upload-pages-artifact + deploy-pages).

## Décisions « lean » assumées
- Front **vanilla** (pas Vite/React) : Pages immédiat, zéro node_modules, zéro build CI. Upgrade React possible plus tard.
- Admin = **CLI** seulement (pas de FastAPI UI en v1).
- Store public seulement (`current.json`) ; `snapshot.admin.json` + Sentry/PR/sécurité = phase 2 stubbée.
- `local_manifests` : en CI (pas de siblings) → lit la version-de-vérité via **GitHub raw** (`raw.githubusercontent.com/GBeurier/{repo}/{default}/…`) ; en local → lit `../<repo>`.

## Définition de « terminé » (gate one-shot)
1. `python -m compileall cockpit` OK ; `ruff check` propre si dispo.
2. `n4a-cockpit validate-targets ops/targets.yaml` OK.
3. `n4a-cockpit collect --only nirs4all,nirs4all-formats,dag-ml` produit un `data/current.json` réel (réseau) avec au moins : nirs4all green PyPI, formats green crates/npm, dag-ml missing crates.
4. `tests/` passent (offline, fixtures).
5. `web/index.html` ouvre et rend la matrice depuis `data/current.json`.
6. README explique collect/serve/admin + le statut phase 2.
