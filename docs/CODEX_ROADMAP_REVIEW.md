# Codex — Review of the cockpit roadmap

Verified sources:`ROADMAP.md`, workflows/manifests from sister repos lists.`docs/DESIGN.md`is missing in this checkout: impossible to check Appendix C.

## Corrections actionnables avant implementation

1. [BLOCK] Add/commit`docs/DESIGN.md`or remove its dependency on the spec.
   Fix: without this file, the workflow inventory in Appendix C is not auditable.

2. [BLOCK] Do not model`release_trigger`only at the package level.
   Fix: mettre trigger+inputs au niveau target/workflow; les repos melangent tag, dispatch,
`release: published`, and workflows without publish on dispatch.

3. [BLOCKER]`nirs4all`: wrong/incomplete version source.
   Fix: `source_of_truth = python_attr`, path `nirs4all/__init__.py`, attr `__version__`
   (`pyproject.toml` pointe vers cet attr), version locale `0.9.4`.

4. [IMPORTANT]`nirs4all`: real trigger`publish.yml`=`release: published`+`workflow_dispatch`,
   without input. Dispatch actually publishes.
   Fix: admin must classify this workflow as `dangerous_dispatch_publish` and require strong confirmation.

5. [BLOCKER]`nirs4all-methods`: wrong version source.
   Fix: SoT = `cpp/include/n4m/n4m_version.h`, macro `N4M_PROJECT_VERSION_STRING`
   (`0.99.0`), not the tag.

6. [IMPORTANT] `nirs4all-methods` PyPI `pls4all`: exact workflow `release-python.yml`.
   Fix: `publish_to` input choice `[none, testpypi]`; production PyPI by tag `v*.*.*`
not prerelease only, not by`publish=true`.

7. [IMPORTANT] `nirs4all-methods` PyPI `nirs4all-methods`: workflow exact `release-wheels.yml`.
   Fix: `version_tag` input must be a required string + `publish` boolean; prod tags also publish.

8. [IMPORTANT] `nirs4all-methods` npm: `release-npm.yml`, input `publish` boolean.
   Fix: nom registre exact `@nirs4all/methods-wasm`.

9. [IMPORTANT] `nirs4all-methods` R: `release-r.yml` does not publish to CRAN.
   Fix: `r-universe` targets `n4m`/`pls4all` are read-only; `cran` targets must be
   `manual`/`missing`, not admin-run.

10. [IMPORTANT]`nirs4all-formats`PyPI:`release.yml`, input`dry_run`, but dispatch does not publish.
    Fix: admin publish prod = creer/pousser tag; dispatch = build dry-run seulement.

11. [IMPORTANT] `nirs4all-formats` crates: `release-crates.yml`, input `dry_run`
    default `"true"`; `dry_run=false` publishes on dispatch.
    Fix: inputs must be strings, not implicit YAML booleans.

12. [IMPORTANT] `nirs4all-formats` npm: `release-npm.yml`, input `publish` boolean.
    Fix: nom registre exact `@nirs4all/formats-wasm`.

13. [IMPORTANT] `nirs4all-formats` R names: `nirs4allformats` et `nirs4allformats.lite`.
    Fix: keep the dot in `nirs4allformats.lite`; do not normalize it to a dash/underscore.

14. [IMPORTANT] `nirs4all-io` PyPI: `release.yml`, input `dry_run`, dispatch build only.
    Fix: SoT `Cargo.toml` `[workspace.package].version`; PyPI version dynamique via maturin.

15. [IMPORTANT]`nirs4all-io`crates: workflow publishes only
    `nirs4all-io-core`, `nirs4all-io`, `nirs4all-io-capi`, `nirs4all-io-cli`.
    Fix: do not add `nirs4all-io-dagml` to crates.io targets.

16. [IMPORTANT] `nirs4all-io` npm/R: noms exacts `@nirs4all/io-wasm`, `nirs4allio`.
    Fix: workflows `release-npm.yml` input `publish`; `release-r.yml` dispatch/tag, not CRAN publish.

17. [BLOCKER] `nirs4all-datasets` crates: roadmap inventory is wrong.
    Fix: there is no published facade crate `nirs4all-datasets`; `release-crates.yml`
    publishes only `nirs4all-datasets-core`, `nirs4all-datasets-capi`, and `nirs4all-datasets-cli`.

18. [IMPORTANT] `nirs4all-datasets` PyPI: `release-python.yml`, input `dry_run`,
    dispatch build only; prod par tag.
    Fix: do not wire `--publish` to dispatch.

19. [IMPORTANT]`nirs4all-datasets/publish.yml`is not a release package.
    Fix: exclude it from the cockpit registry; it is Dataverse with inputs `dataset_id`,
    `collection`, `contact_email`.

20. [BLOCKER]`nirs4all-lite`: wrong SoT in the roadmap.
    Fix: no version in root `[workspace.package]`; SoT =
    `bindings/rust/nirs4all/Cargo.toml` `[package].version` (`0.1.0`).

21. [BLOCKER]`nirs4all-lite`: keep the logical name/register trap.
    Fix exact targets: PyPI `nirs4all-lite`, crates `nirs4all`, npm `nirs4all`,
    R-universe/CRAN `nirs4all`, GitHub repo `nirs4all-lite`.

22. [IMPORTANT] `nirs4all-lite` workflows: `release-python.yml` input `dry_run`
    build-only; `release-crates.yml` input `dry_run`; `release-npm.yml` input `publish`;
    `release-r.yml`/`release-source.yml`/`release-matlab.yml` dispatch sans inputs.
    Fix: generate admin buttons per workflow, not per generic registry.

23. [IMPORTANT] `nirs4all-aom`: PyPI exact `nirs4all-aom`, SoT `pyproject.toml`
    static `version = "0.1.1"`.
    Fix: `publish-pypi.yml` trigger `release: published` + `workflow_dispatch`, sans input.

24. [BLOCKER]`dag-ml`: no release workflow, only`ci.yml`.
    Fix: crates/npm/PyPI targets must be `planned` or `missing_readonly`; admin = "no button".

25. [IMPORTANT] `dag-ml`: noms reels sources: crates
    `dag-ml`, `dag-ml-core`, `dag-ml-arrow`, `dag-ml-capi`, `dag-ml-cli`, `dag-ml-py`,
    `dag-ml-wasm`; PyPI `dag-ml`. The npm source package name is not fixed.
    Fix: do not register `@nirs4all/dag-ml-wasm` as the exact name before the workflow/package source exists.

26. [BLOCKER]`dag-ml-data`: no workflow release, only`ci.yml`.
    Fix: release targets = planned/read-only; no admin run.

27. [IMPORTANT] `dag-ml-data`: noms reels sources: crates
    `dag-ml-data`, `dag-ml-data-core`, `dag-ml-data-arrow`, `dag-ml-data-capi`,
    `dag-ml-data-cli`, `dag-ml-data-provider`, `dag-ml-data-py`, `dag-ml-data-wasm`;
    PyPI `dag-ml-data`; R `dagmldata`.
    Fix: add PyPI or exclude it explicitly; do not assume an npm scoped package.

28. [BLOCKER]`local_manifests`via raw GitHub: do not hardcode a branch in YAML.
    Fix: fetch `default_branch` via the GitHub API; current remotes all point to
    `main`, but the local `dag-ml*` checkouts are on work branches.

29. [IMPORTANT]`local_manifests`must know the exact paths by strategy.
    Fix minimal:
    `nirs4all/nirs4all/__init__.py`, `nirs4all-aom/pyproject.toml`,
    `nirs4all-methods/cpp/include/n4m/n4m_version.h`,
    `<formats|io|datasets>/Cargo.toml`, `nirs4all-lite/bindings/rust/nirs4all/Cargo.toml`,
    `dag-ml/Cargo.toml`, `dag-ml-data/Cargo.toml`.

30. [BLOCKER] State machine: `expected_version = release_tag else manifest` is too naive.
    Fix: store `manifest_version`, `latest_prod_tag`, `latest_any_tag`, and `published_version`,
    then derive `expected_prod_version`; prerelease/source-ahead must not redden production targets.

31. [IMPORTANT]`source-ahead`must be a package/source flag, not a target status.
    Fix: keep target statuses `green/stale/missing/broken/unknown/excluded`; add
    `flags: ["source_ahead"]` and a separate roll-up.

32. [IMPORTANT]`excluded`must be per target with a mandatory, obvious reason.
    Fix: exclude it from the roll-up, but count it in the summary; never turn it green.

33. [IMPORTANT] Do not mix CI health and registry status.
    Fix: un dernier workflow release en echec = `workflow_health=failed`; le target registry
    reste `green` si la version publiee attendue est disponible.

34. [IMPORTANT] Tags vs GitHub Releases: Multiple workflows release to tag and attach via
    `softprops/action-gh-release`, mais le tag est la source de depart.
    Fix: collecter tags ET releases; `nirs4all`/`nirs4all-aom` sont les vrais cas
    `release: published`.

35. [IMPORTANT] npm API: the roadmap mentions the pitfall, it must be contractualized in tests.
    Fix: fixture scoped `%2F` + fixture HTTP 200 avec body erreur; traiter comme `missing/unknown`
    selon code erreur body.

36. [IMPORTANT] API downloads: do not use absence of stats as absence of package.
    Fix: pypistats `429`/fenetre ~180j => downloads `unknown`; cranlogs `0` HTTP 200
    => zero download, not `missing`.

37. [IMPORTANT] GitHub API: avoid Search Issues for the MVP.
    Fix: utiliser `/repos/{owner}/{repo}/issues?state=open&labels=...` ou GraphQL groupe,
    cache 6h; Search is limited to 30/min.

38. [IMPORTANT] API crates.io: User-Agent descriptif obligatoire.
    Fix: tests for 403 without UA; backoff + shared disk cache.

39. [IMPORTANT] Admin CLI: heterogeneous inputs.
    Fix: `targets.yaml` must contain the exact schema per workflow: input name, type, default,
    danger level, and whether dispatch can publish. Reject any undeclared input.

40. [IMPORTANT] Admin secrets: the cockpit must never handle npm/pypi/cargo tokens outside
    `gh secret set`.
    Fix: `admin set-secret` accepte seulement `--from-file`; jamais `--body`, jamais echo,
    jamais stockage dans `data/`.

41. [NICE] Scope lean: couper/stubber downloads historiques riches, Sentry, PR/security,
    FastAPI, compaction mensuelle et dashboards deploy pages-only.
    Fix MVP: `collect`, `validate-targets`, `current.json`, UI matrice, tests offline.

42. [NICE]`--no-network`mode: the contract is vague.
    Fix: in the MVP, `--no-network` reads only fixtures/cache and must mark every non-cached
    value `unknown`, not fail the full collect.

## Verdict

GO avec ces 42 corrections.
