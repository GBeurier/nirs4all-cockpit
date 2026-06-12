# nirs4all-cockpit

A read-only **release & health cockpit** for the nirs4all ecosystem. It
aggregates the public state of every published package — which version is on
which registry, recent downloads, open issues, and the health of release
workflows — into a single `data/current.json` snapshot and renders it as a
vanilla (zero-build) dashboard.

**The cockpit aggregates and orchestrates; it never reimplements any repo's
logic.** Every verdict is derived from public, read-only registry/CI/issue
signals declared in `ops/targets.yaml`.

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
n4a-cockpit collect --only nirs4all,dag-ml   # a subset
n4a-cockpit collect --offline                # fixtures/cache only; non-cached → unknown
```

`collect` reads the inventory (`ops/targets.yaml`), probes each registry with a
shared, rate-limit-aware HTTP client, reconciles the four version facts
(`manifest` / `latest_prod_tag` / `latest_any_tag` / `published`) into a status,
and writes `data/current.json`. In CI an ambient `GITHUB_TOKEN` raises the
GitHub rate limit.

Validate the inventory itself at any time:

```bash
n4a-cockpit validate-targets ops/targets.yaml
n4a-cockpit summarize data/current.json
n4a-cockpit status                 # coloured table read from the snapshot
```

### 3. Open the dashboard

The front-end is plain HTML/CSS/JS — no build step, no dependencies. It reads
`data/current.json`. Because browsers block `fetch` over `file://`, serve the
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
```

The admin layer wraps `gh` only; it never publishes directly and never reads or
echoes a token:

```bash
n4a-cockpit admin run <pkg> <registry>            # preview (dry-run default)
n4a-cockpit admin run <pkg> <registry> --publish --no-dry-run   # guarded dispatch
n4a-cockpit admin set-secret <repo> <NAME> --from-file <path>   # gh secret set
```

---

## Status model

Each target (one exact name on one registry) gets exactly one status. Colour and
a glyph both encode it (never colour alone) so the matrix is readable without
colour perception.

| Status     | Glyph | Meaning |
|------------|:-----:|---------|
| `green`    |  ●    | Published version matches the expected production version. |
| `stale`    |  ◐    | Published, but behind the expected version. |
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

The package **roll-up** is the worst tracked cell
(`broken` > `missing` > `stale` > `unknown` > `green`); `excluded` is ignored in
the roll-up but still counted in the summary.

Download counts use `n/a` for `null`/unknown; `0` is a real zero (e.g. cranlogs
returns `0` for a package nobody has downloaded — that is not "missing").

---

## Deployment (GitHub Pages)

Two workflows drive the live site:

- **`.github/workflows/collect.yml`** — cron `17 */6 * * *` + manual dispatch;
  installs the package, runs `n4a-cockpit collect`, and commits the refreshed
  `data/*.json` via `git-auto-commit-action`.
- **`.github/workflows/pages.yml`** — on push to `main` (and manual dispatch),
  assembles `_site/` from `web/*` with `data/` copied to `_site/data/`, then
  publishes it with `actions/upload-pages-artifact` + `actions/deploy-pages`.

**Pages layout choice:** the build copies `web/` to the **site root** and `data/`
to `_site/data/`, so the dashboard *is* the site root and reads
`./data/current.json`. This is simpler than serving the repo root (which would
expose a directory listing at `/`) and needs no path rewrite — `app.js` already
falls back across `../data`, `./`, and `./data`.

---

## Phase 2 (stubbed)

The following are intentionally **out of scope for v1** and shipped as marked
TODO stubs only:

- **Sentry** error/issue ingestion.
- **GitHub PRs** and **security advisories** collectors.
- The private **admin snapshot** store (`snapshot.admin.json`).
- A **FastAPI** local UI (v1 admin is CLI-only).
- **Rich download history** and monthly history compaction.

v1 is exactly: `collect`, `validate-targets`, `current.json`, the matrix UI, and
offline fixture tests.

---

## Tests

Offline only — no network. The collectors reach the network through a single
`cockpit.http.get_json` seam, which the tests monkeypatch with captured fixtures
under `tests/fixtures/`.

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
