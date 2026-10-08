# nirs4all-cockpit

A read-only **release & health cockpit** for the nirs4all ecosystem. It
aggregates the public state of every published package — which version is on
which registry, recent downloads, open issues, and the health of release
workflows — into a single `data/current.json` snapshot and renders it as a
vanilla (zero-build) dashboard.

Part of the [open-source NIRS tools](https://nirs4all.org/open-source-nirs-tools.html)
ecosystem: file readers, datasets, methods, browser modelling, reproducible pipelines,
papers, benchmarks, and release dashboards for near-infrared spectroscopy.

**The cockpit aggregates and orchestrates; it never reimplements any repo's
logic.** Every verdict is derived from public, read-only registry/CI/issue
signals declared in `ops/targets.yaml`.

Public delivery status on **8 October 2026**:

| Product | Published version and delivery | Release source | Current main source |
| --- | --- | --- | --- |
| Python SDK | [1.4.7](https://github.com/GBeurier/nirs4all/releases/tag/1.4.7): [PyPI](https://pypi.org/project/nirs4all/1.4.7/), Docker and the [common/Legacy guide](https://gbeurier.github.io/nirs4all/) are published. | [1a828c3c](https://github.com/GBeurier/nirs4all/commit/1a828c3cad6b6571cbe14b9bd7da2f9f1db767cc) | [1aa5f7ed](https://github.com/GBeurier/nirs4all/commit/1aa5f7ed03fd2775284f822d7158450fcc8bd76c), including the current documentation |
| Core | [0.4.5](https://github.com/GBeurier/nirs4all-core/releases/tag/v0.4.5): [PyPI](https://pypi.org/project/nirs4all-core/0.4.5/), [crates.io](https://crates.io/crates/nirs4all/0.4.5), [npm](https://www.npmjs.com/package/nirs4all/v/0.4.5), source/SBOM and MATLAB/Octave assets are published. | [5668796a](https://github.com/GBeurier/nirs4all-core/commit/5668796aaac9a02d8d0146ec05ead04f9c76657c) | same release source |
| DAG-ML | [0.3.41](https://github.com/GBeurier/dag-ml/releases/tag/v0.3.41): [PyPI](https://pypi.org/project/dag-ml/0.3.41/), [npm](https://www.npmjs.com/package/dag-ml-wasm/v/0.3.41), [Rust crates](https://crates.io/crates/dag-ml/0.3.41) and [R-universe](https://gbeurier.r-universe.dev/dagml) are published. | [6f4044b4](https://github.com/GBeurier/dag-ml/commit/6f4044b45028a90a92d3f29287e67779bb5fd0b9) | [c6b52979](https://github.com/GBeurier/dag-ml/commit/c6b52979745397ae4e8662580df79341f0378d28), including subsequent CI/docs metadata changes |
| R product | [0.7.2](https://github.com/GBeurier/nirs4all-r/releases/tag/v0.7.2): [R-universe source and binaries](https://gbeurier.r-universe.dev/nirs4all) are published; CRAN submission remains separate. | [1c6f4a7f](https://github.com/GBeurier/nirs4all-r/commit/1c6f4a7f1b42a5d550cabc4809e957680630a4d7) | same release source |
| Quality | [0.0.3](https://github.com/GBeurier/nirs4all-quality/releases/tag/v0.0.3): the static ZIP and [quali.nirs4all.org](https://quali.nirs4all.org/) are published. | [6d68810b](https://github.com/GBeurier/nirs4all-quality/commit/6d68810b4b5961eb6a77f881f35f8cf7e33480a2) | same release source |
| Device | [0.1.1](https://github.com/GBeurier/nirs4all-device/releases/tag/v0.1.1): [device.nirs4all.org](https://device.nirs4all.org/) and the Android debug APK are published. Hardware, app-store and signed iOS delivery are outside this evidence. | [87bc8311](https://github.com/GBeurier/nirs4all-device/commit/87bc83118b1508d5eddadcf888db646568ce58a4) | same release source |
| Web | [0.4.1](https://github.com/GBeurier/nirs4all-web/releases/tag/v0.4.1) is published and deployed at [web.nirs4all.org](https://web.nirs4all.org/). Served files match the official Pages artifact and the public UI startup is verified. | [0ec8790b](https://github.com/GBeurier/nirs4all-web/commit/0ec8790b4afc896a01c0f85ef59f9e347a83c3a2) | same release source |
| Studio | [0.15.2](https://github.com/GBeurier/nirs4all-studio/releases/tag/0.15.2): Linux, Windows and macOS ARM installers, checksums and Docker are published. Native identity matches the embedded Python SDK 1.4.7; all three platform UI startups passed. 0.15.1 was never published. | [434d8221](https://github.com/GBeurier/nirs4all-studio/commit/434d8221bc72a3fbb65dcc62b74cfc77e565d34b) | application release source; subsequent publication-workflow changes preserve these artifacts |

Source tags, registry publication and deployed applications are separate facts.
The daily snapshot has its own collection timestamp and can lag these deliveries.
The existing Read the Docs routes redirect to the current common/Legacy guide;
this does not establish a new successful native Read the Docs build.
Hosted product jobs build/package and run a short UI startup smoke; full scientific
E2E and performance qualification run locally. Studio installers remain unsigned
and non-notarized. The earlier `v0.1.8` and
`n4a-v1-2026.09-native-release` Cockpit tags describe the historical projection;
this status update does not create a new Cockpit package release.

---

## Quickstart

### 1. Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .          # add [collect] for the rich CLI table, [dev] for tests
```

### 2. Collect a snapshot

```bash
n4a-cockpit collect                          # all packages → data/current.json
n4a-cockpit collect --only nirs4all,dag-ml --out /tmp/n4a-current.partial.json
n4a-cockpit collect --offline                # fixtures/cache only; non-cached → unknown
```

`collect` reads the inventory (`ops/targets.yaml`), probes each registry with a
shared, rate-limit-aware HTTP client, reconciles the four version facts
(`manifest` / `latest_prod_tag` / `latest_any_tag` / `published`) into a status,
and writes `data/current.json`. In CI an ambient `GITHUB_TOKEN` raises the
GitHub rate limit.

CRAN also has a lifecycle probe against its canonical package page. `crandb`
keeps an old version record after CRAN archives a package, so an archived target
carries `lifecycle="archived"`, its archival reason and former version
separately. Its release status remains `missing` or `pending`: an archive is not
a publication and can coexist with a replacement tarball awaiting manual review.

Subset collection is intentionally scratch-only: `--only` refuses to write the
public `data/current.json` unless you provide an explicit `--out` path.

Optional public analytics are enabled by secrets:

- `GOATCOUNTER_TOKEN` for aggregate Pages visits.
- `SENTRY_AUTH_TOKEN` for aggregate runtime-error counters.
- `GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON` for aggregate Google Search
  clicks, impressions, CTR, average position, and top pages. The service
  account must first be added as a user on the Search Console property; the
  default property is `sc-domain:nirs4all.org` and can be overridden with
  `GOOGLE_SEARCH_CONSOLE_SITE`.

Validate the inventory itself at any time:

```bash
n4a-cockpit validate-targets ops/targets.yaml
n4a-cockpit summarize data/current.json
n4a-cockpit status                 # coloured table read from the snapshot
```

### 3. Open the dashboard

The front-end is plain HTML/CSS/JS — no build step, no dependencies. It reads
`data/current.json` and, when present, `data/manual-actions.json` for the public
manual-blocker panel. Because browsers block `fetch` over `file://`, serve the
**repo root** over HTTP so `web/index.html` can reach `../data/current.json`:

```bash
python -m http.server 8000      # then open http://localhost:8000/web/index.html
```

`app.js` tries `../data/current.json`, then `./current.json`, then
`./data/current.json`, so it works both when the repo root is served and when
`data/` is copied next to `web/` (see *Deployment* below).

### 4. Manual release actions

Some release steps are human-only (account web forms, registry tokens). They
live in `ops/manual-actions.yaml`; the cockpit surfaces them with an auto-check
against the latest snapshot:

```bash
n4a-cockpit admin actions            # checklist + auto-checks vs current.json
n4a-cockpit admin actions --md       # Markdown rendering
n4a-cockpit admin actions --json-out data/manual-actions.json
```

The admin layer wraps `gh` only; it never publishes directly and never reads or
echoes a token:

```bash
n4a-cockpit admin run <pkg> <registry>            # preview (dry-run default)
n4a-cockpit admin run <pkg> <registry> --publish --no-dry-run   # guarded dispatch
n4a-cockpit admin set-secret <repo> <NAME> --from-file <path>   # gh secret set
```

### 5. Local admin signals (traffic, PRs, security, Sentry)

`admin collect` gathers **push-scoped / semi-private** signals into a
**gitignored** `data/admin/snapshot.admin.json` — never the public snapshot,
never deployed:

```bash
n4a-cockpit admin collect            # traffic + open PRs + security alerts + Sentry
```

- **GitHub traffic** (views/clones, 14 d) needs a push-scoped token.
- **Open PRs** and **Dependabot / code-scanning** alerts per repo.
- **Sentry** aggregate counters for `nirs4all-studio` (org `wwwciradfr`,
  `de.sentry.io`) — set `SENTRY_AUTH_TOKEN` to enable; it degrades gracefully
  (`available=false`) otherwise.
  Counters use the [organization issue search](https://docs.sentry.io/api/events/list-an-organizations-issues/),
  scoped to the project and the last 14 days of event activity. The dashboard
  displays that period and links to the same search. Unlike the deprecated
  project endpoint, this excludes orphaned issue groups without searchable
  events. It does not resolve or ignore any issue in Sentry.

The dashboard renders these in an **Admin** section *only* when that local file
is present, so the public site never shows them.

---

## Topology notes

- **`nirs4all`** remains the Python oracle: its PyPI/docs/release state is tracked
  independently and is not folded into the aggregate packages.
- **`nirs4all-core`** owns the portable Python, Rust, JavaScript/WASM and
  MATLAB/Octave aggregate artifacts. No legacy aggregate alias is tracked.
- **`nirs4all-r`** owns the R package named `nirs4all`, tracked once on R-universe
  and CRAN from its `DESCRIPTION`. Core's former `bindings/r` is retired.
- **`n4m`** is the independently versioned Rust binding in `nirs4all-methods`.
  Its Cargo manifest and `n4m-v` tags define the crates.io expectation separately
  from the Methods product version. Shared repository statistics count once.
- **`nirs4all-web`** is client-side-only; the deployed runtime is tracked as a
  Pages target, and the shipped source/app version is tracked with a GitHub
  Release. It is not a package-registry aggregate.
- **`nirs4all-ui`** is a shared React/TypeScript package of reusable
  components, status helpers, and brand assets outside the
  `nirs4all-core` aggregation lock; it is tracked separately with npm,
  GitHub Release and GitHub Pages showcase targets.
- **`nirs4all-providers`** is an optional Python provider-client layer for
  datasets and repository metadata/contracts. Benchmarks and papers keep their
  public APIs in their owning repositories. It stays outside core: neutral
  contracts remain the cross-language source of truth.
- **`nirs4all-tools`** is the Python migration/converter toolkit for legacy
  workspaces, pipelines and predictions. It is tracked separately because it is
  an operational cutover surface, not runtime core.
- **`nirs4all-device`** is tracked as a public Pages app surface for the
  phone/tablet spectrometer workbench. Its Android debug APK remains a CI
  artifact, not a registry or production-store release target.

---

## Status model

Each target (one exact name on one registry) gets exactly one status. Colour and
a glyph both encode it (never colour alone) so the matrix is readable without
colour perception.

| Status     | Glyph | Meaning |
|------------|:-----:|---------|
| `green`    |  ●    | Published version matches the expected production version. |
| `stale`    |  ◐    | Published, but behind the expected version. |
| `pending`  |  ●    | Built or submitted, but not live on the registry yet (for example a CRAN review queue). |
| `missing`  |  ○    | Not found (404) where a release is expected; also `planned` targets with nothing published yet. |
| `broken`   |  ✕    | Present but failed to build/publish (e.g. R-universe `Version: null`, or a failed release run with no published version). |
| `unknown`  |  ?    | Inconclusive probe — timeout, `429`, or `5xx`. Never a red verdict. |
| `excluded` |  —    | Intentionally not on this registry (mandatory `reason`). Counted in the summary, kept out of the package roll-up, never turned green. |

Two signals are deliberately **not** statuses:

- **`source_ahead`** — a *package flag* shown as a badge when the repo manifest
  is ahead of the latest production tag (an unreleased bump). It never reddens a
  target.
- **`planned`** — a per-target flag (no release workflow yet). It reconciles as
  `missing` and gets no admin button.
- **`lifecycle="archived"`** — a registry-specific historical fact. CRAN sets
  it when its canonical package page says the package was removed. The matrix
  renders an amber archive glyph while the release status remains `pending` or
  `missing`; the former version and official reason stay in the target record.

The package **roll-up** is the worst tracked cell
(`broken` > `missing` > `stale` > `pending` > `unknown` > `green`); `excluded`
and manual targets are ignored in the roll-up but still counted in the summary.

Download counts use `n/a` for `null`/unknown; `0` is a real zero (e.g. cranlogs
returns `0` for a package nobody has downloaded — that is not "missing").

---

## Deployment (GitHub Pages)

Two workflows drive the live site:

- **`.github/workflows/collect.yml`** — cron `17 0 * * *` + manual dispatch;
  installs the package, shallow-clones public sibling repos under `_siblings/`
  for code stats and manifest reads, runs `n4a-cockpit collect`, and commits
  refreshed `data/*.json` with plain git commands.
- **`.github/workflows/pages.yml`** — on push to `main`, successful `collect`
  workflow completion, and manual dispatch, assembles `_site/` from `web/*` with
  `data/` copied to `_site/data/`, then publishes it with
  `actions/upload-pages-artifact` + `actions/deploy-pages`.

**Pages layout choice:** the build copies `web/` to the **site root** and `data/`
to `_site/data/`, so the dashboard *is* the site root and reads
`./data/current.json`. This is simpler than serving the repo root (which would
expose a directory listing at `/`) and needs no path rewrite — `app.js` already
falls back across `../data`, `./`, and `./data`.

### Native V1 release receipt

The dashboard also reads `data/native-candidate-staging.json`, the machine-readable
V1 release receipt shared with `nirs4all-org`. Despite its historical filename,
it describes the published train. It contains public Git object IDs and artifact
checksums—not machine paths or private local data—so the exact release can be
audited. Those identities remain in the receipt but are intentionally not shown
in the public UI: the page uses the file only for concise release news.

This receipt is deliberately separate from registry health. The release matrix
comes from `data/current.json`, which is produced by the daily collector. A new
publication can therefore appear in the release receipt before it reaches the
matrix; the matrix's displayed `updated` timestamp identifies the snapshot in
use, and the next successful collection reconciles the versions.

---

## Public vs admin signals

- **Public** (`data/current.json`, deployed to Pages): registry versions &
  status, downloads (only the metrics each registry truly reports, plus
  **per-version detail for crates**; GitHub Release asset counts are **excluded**
  as they conflate CI/test/deploy pulls with installs), open issues, release-
  workflow health, **public GitHub stats** (stars / forks / watchers / license /
  PRs open·merged·closed), **code stats** (effective LOC, comments, tests,
  coverage, per-language — scanned from the local checkout), **GitHub Actions
  stats** (workflow count, total runs, recent success rate), aggregate
  **GoatCounter visits**, aggregate **Google Search Console performance**,
  aggregate **Sentry counters**, and an ecosystem-wide **`totals`** aggregate.
  Built by `collect`.
- **Admin** (`data/admin/snapshot.admin.json`, gitignored, local only): GitHub
  **traffic** (views/clones), **open PRs**, **Dependabot / code-scanning**
  alerts, and **Sentry** aggregate counters. Built by `admin collect`. These are
  push-scoped or semi-private and never enter the public snapshot.

### Still ahead

- A **FastAPI** local admin UI (admin is CLI + local dashboard section for now). - **Rich download history** and monthly history compaction.

---

## Tests

Offline only — no network. JSON collectors reach the network through
`cockpit.http.get_json`; the CRAN archive probe uses `get_text`. Tests monkeypatch
both seams with captured fixtures under `tests/fixtures/`.

```bash
pip install -e .[dev]
pytest -q
```

- `tests/test_version.py` — the pure version engine (SemVer/PEP 440-aware
  compare, `derive_expected`, `source_ahead`, `is_prerelease`, and every
  `classify` state).
- `tests/test_collect_parsing.py` — each registry parser against its fixture
  (PyPI `info.version`, crates `max_version`/404, npm `dist-tags` + the
  error-at-HTTP-200 trap, R-universe `Version: null` → broken, cranlogs `0`).
- `tests/test_reconcile.py` — the four reconcile scenarios: planned crate →
  missing, npm scoped error-200 → version OK + downloads unknown, cranlogs `0`
  ≠ missing, R-universe null → broken.
- `tests/test_admin.py` — the admin collectors: Sentry token-less degradation
  and aggregate counter shaping, PR draft/ready counts, security 403 → unavailable and the
  Dependabot severity breakdown.
- `tests/test_stats.py` — the local code scanner (code/comment/blank/test counts,
  vendored-dir skipping, missing-checkout → None) and the Actions success-rate.

> **Note on code stats:** LOC/tests are a raw scan of sibling checkouts, so they
> include tests/examples and need source trees present. The public CI cron
> shallow-clones public siblings into `_siblings/`; local runs can point
> `N4A_SIBLINGS_ROOT` at any equivalent workspace. Coverage is read from a
> Cobertura `coverage.xml` when present.

## License

`nirs4all-cockpit` is dual-licensed open-source — **`CeCILL-2.1 OR AGPL-3.0-or-later`** (your choice) —
with an optional **commercial license** for closed-source / SaaS use. For any commercial use, contact
<nirs4all-admin@cirad.fr>. See [`LICENSING.md`](LICENSING.md), the texts under [`LICENSES/`](LICENSES/),
and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
