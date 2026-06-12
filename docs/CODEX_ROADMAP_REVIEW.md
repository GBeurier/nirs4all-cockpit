# Codex — Review de la roadmap cockpit

Sources verifiees: `ROADMAP.md`, workflows/manifests des repos freres listes.
`docs/DESIGN.md` est absent dans ce checkout: impossible de verifier l'Annexe C.

## Corrections actionnables avant implementation

1. [BLOCKER] Ajouter/committer `docs/DESIGN.md` ou retirer sa dependance de la spec.
   Fix: sans ce fichier, l'inventaire des workflows en Annexe C n'est pas auditable.

2. [BLOCKER] Ne pas modeliser `release_trigger` seulement au niveau package.
   Fix: mettre trigger+inputs au niveau target/workflow; les repos melangent tag, dispatch,
   `release: published`, et workflows sans publish sur dispatch.

3. [BLOCKER] `nirs4all`: source de version fausse/incomplete.
   Fix: `source_of_truth = python_attr`, path `nirs4all/__init__.py`, attr `__version__`
   (`pyproject.toml` pointe vers cet attr), version locale `0.9.4`.

4. [IMPORTANT] `nirs4all`: trigger reel `publish.yml` = `release: published` + `workflow_dispatch`,
   sans input. Le dispatch publie reellement.
   Fix: admin doit classer ce workflow en `dangerous_dispatch_publish`, confirmation forte.

5. [BLOCKER] `nirs4all-methods`: source de version fausse.
   Fix: SoT = `cpp/include/n4m/n4m_version.h`, macro `N4M_PROJECT_VERSION_STRING`
   (`0.99.0`), pas le tag.

6. [IMPORTANT] `nirs4all-methods` PyPI `pls4all`: workflow exact `release-python.yml`.
   Fix: inputs `publish_to` choice `[none, testpypi]`; production PyPI par tag `v*.*.*`
   non prerelease seulement, pas par `publish=true`.

7. [IMPORTANT] `nirs4all-methods` PyPI `nirs4all-methods`: workflow exact `release-wheels.yml`.
   Fix: inputs `version_tag` required string + `publish` boolean; tag prod publie aussi.

8. [IMPORTANT] `nirs4all-methods` npm: `release-npm.yml`, input `publish` boolean.
   Fix: nom registre exact `@nirs4all/methods-wasm`.

9. [IMPORTANT] `nirs4all-methods` R: `release-r.yml` ne publie pas CRAN.
   Fix: `r-universe` targets `n4m`/`pls4all` read-only; `cran` targets doivent etre
   `manual`/`missing`, pas admin-run.

10. [IMPORTANT] `nirs4all-formats` PyPI: `release.yml`, input `dry_run`, mais dispatch ne publie pas.
    Fix: admin publish prod = creer/pousser tag; dispatch = build dry-run seulement.

11. [IMPORTANT] `nirs4all-formats` crates: `release-crates.yml`, input `dry_run`
    default `"true"`; `dry_run=false` publie sur dispatch.
    Fix: inputs strings, pas booleens YAML implicites.

12. [IMPORTANT] `nirs4all-formats` npm: `release-npm.yml`, input `publish` boolean.
    Fix: nom registre exact `@nirs4all/formats-wasm`.

13. [IMPORTANT] `nirs4all-formats` R names: `nirs4allformats` et `nirs4allformats.lite`.
    Fix: conserver le point dans `nirs4allformats.lite`; ne pas normaliser en tiret/underscore.

14. [IMPORTANT] `nirs4all-io` PyPI: `release.yml`, input `dry_run`, dispatch build only.
    Fix: SoT `Cargo.toml` `[workspace.package].version`; PyPI version dynamique via maturin.

15. [IMPORTANT] `nirs4all-io` crates: workflow publie seulement
    `nirs4all-io-core`, `nirs4all-io`, `nirs4all-io-capi`, `nirs4all-io-cli`.
    Fix: ne pas ajouter `nirs4all-io-dagml` aux targets crates.io.

16. [IMPORTANT] `nirs4all-io` npm/R: noms exacts `@nirs4all/io-wasm`, `nirs4allio`.
    Fix: workflows `release-npm.yml` input `publish`; `release-r.yml` dispatch/tag, pas CRAN publish.

17. [BLOCKER] `nirs4all-datasets` crates: inventaire roadmap faux.
    Fix: il n'existe pas de crate facade `nirs4all-datasets` publiee; `release-crates.yml`
    publie seulement `nirs4all-datasets-core`, `nirs4all-datasets-capi`, `nirs4all-datasets-cli`.

18. [IMPORTANT] `nirs4all-datasets` PyPI: `release-python.yml`, input `dry_run`,
    dispatch build only; prod par tag.
    Fix: ne pas cabler `--publish` sur dispatch.

19. [IMPORTANT] `nirs4all-datasets/publish.yml` n'est pas une release package.
    Fix: exclure du cockpit registry; c'est Dataverse avec inputs `dataset_id`,
    `collection`, `contact_email`.

20. [BLOCKER] `nirs4all-lite`: SoT faux dans la roadmap.
    Fix: pas de version dans root `[workspace.package]`; SoT =
    `bindings/rust/nirs4all/Cargo.toml` `[package].version` (`0.1.0`).

21. [BLOCKER] `nirs4all-lite`: garder le piege nom logique/registre.
    Fix targets exacts: PyPI `nirs4all-lite`, crates `nirs4all`, npm `nirs4all`,
    R-universe/CRAN `nirs4all`, GitHub repo `nirs4all-lite`.

22. [IMPORTANT] `nirs4all-lite` workflows: `release-python.yml` input `dry_run`
    build-only; `release-crates.yml` input `dry_run`; `release-npm.yml` input `publish`;
    `release-r.yml`/`release-source.yml`/`release-matlab.yml` dispatch sans inputs.
    Fix: generer les boutons admin par workflow, pas par registry generique.

23. [IMPORTANT] `nirs4all-aom`: PyPI exact `nirs4all-aom`, SoT `pyproject.toml`
    static `version = "0.1.1"`.
    Fix: `publish-pypi.yml` trigger `release: published` + `workflow_dispatch`, sans input.

24. [BLOCKER] `dag-ml`: aucun workflow release, seulement `ci.yml`.
    Fix: targets crates/npm/PyPI doivent etre `planned` ou `missing_readonly`; admin = "pas de bouton".

25. [IMPORTANT] `dag-ml`: noms reels sources: crates
    `dag-ml`, `dag-ml-core`, `dag-ml-arrow`, `dag-ml-capi`, `dag-ml-cli`, `dag-ml-py`,
    `dag-ml-wasm`; PyPI `dag-ml`. Le package npm source n'est pas fixe.
    Fix: ne pas inscrire `@nirs4all/dag-ml-wasm` comme nom exact avant workflow/package source.

26. [BLOCKER] `dag-ml-data`: aucun workflow release, seulement `ci.yml`.
    Fix: targets release = planned/read-only; pas d'admin run.

27. [IMPORTANT] `dag-ml-data`: noms reels sources: crates
    `dag-ml-data`, `dag-ml-data-core`, `dag-ml-data-arrow`, `dag-ml-data-capi`,
    `dag-ml-data-cli`, `dag-ml-data-provider`, `dag-ml-data-py`, `dag-ml-data-wasm`;
    PyPI `dag-ml-data`; R `dagmldata`.
    Fix: ajouter PyPI ou l'exclure explicitement; ne pas supposer un npm scoped.

28. [BLOCKER] `local_manifests` via raw GitHub: ne pas hardcoder une branche dans YAML.
    Fix: recuperer `default_branch` via GitHub API; les remotes actuels pointent tous sur
    `main`, mais les checkouts locaux `dag-ml*` sont sur branches de travail.

29. [IMPORTANT] `local_manifests` doit connaitre les chemins exacts par strategie.
    Fix minimal:
    `nirs4all/nirs4all/__init__.py`, `nirs4all-aom/pyproject.toml`,
    `nirs4all-methods/cpp/include/n4m/n4m_version.h`,
    `<formats|io|datasets>/Cargo.toml`, `nirs4all-lite/bindings/rust/nirs4all/Cargo.toml`,
    `dag-ml/Cargo.toml`, `dag-ml-data/Cargo.toml`.

30. [BLOCKER] Machine a etats: `expected_version = release_tag sinon manifest` est trop naive.
    Fix: stocker `manifest_version`, `latest_prod_tag`, `latest_any_tag`, `published_version`,
    puis deriver `expected_prod_version`; prerelease/source-ahead ne doit pas rougir les prod targets.

31. [IMPORTANT] `source-ahead` doit etre un flag package/source, pas un status de target.
    Fix: garder statuses target `green/stale/missing/broken/unknown/excluded`; ajouter
    `flags: ["source_ahead"]` et un roll-up separe.

32. [IMPORTANT] `excluded` doit etre par target avec raison obligatoire et evidence.
    Fix: exclure du roll-up, mais compter dans summary; ne jamais le transformer en green.

33. [IMPORTANT] Ne pas melanger sante CI et etat registry.
    Fix: un dernier workflow release en echec = `workflow_health=failed`; le target registry
    reste `green` si la version publiee attendue est disponible.

34. [IMPORTANT] Tags vs GitHub Releases: plusieurs workflows publient sur tag et attachent via
    `softprops/action-gh-release`, mais le tag est la source de depart.
    Fix: collecter tags ET releases; `nirs4all`/`nirs4all-aom` sont les vrais cas
    `release: published`.

35. [IMPORTANT] API npm: la roadmap cite le piege, il faut le contractualiser en tests.
    Fix: fixture scoped `%2F` + fixture HTTP 200 avec body erreur; traiter comme `missing/unknown`
    selon code erreur body.

36. [IMPORTANT] API downloads: ne pas utiliser absence de stats comme absence de paquet.
    Fix: pypistats `429`/fenetre ~180j => downloads `unknown`; cranlogs `0` HTTP 200
    => zero download, pas `missing`.

37. [IMPORTANT] API GitHub: eviter Search Issues pour le MVP.
    Fix: utiliser `/repos/{owner}/{repo}/issues?state=open&labels=...` ou GraphQL groupe,
    cache 6h; Search est limite a 30/min.

38. [IMPORTANT] API crates.io: User-Agent descriptif obligatoire.
    Fix: tests sur 403 sans UA; backoff+cache disque partage.

39. [IMPORTANT] Admin CLI: inputs heterogenes.
    Fix: `targets.yaml` doit contenir schema exact par workflow: input name, type, default,
    danger level, et si dispatch peut publier. Refuser tout input non declare.

40. [IMPORTANT] Admin secrets: le cockpit ne doit jamais manipuler tokens npm/pypi/cargo hors
    `gh secret set`.
    Fix: `admin set-secret` accepte seulement `--from-file`; jamais `--body`, jamais echo,
    jamais stockage dans `data/`.

41. [NICE] Scope lean: couper/stubber downloads historiques riches, Sentry, PR/security,
    FastAPI, compaction mensuelle et dashboards deploy pages-only.
    Fix MVP: `collect`, `validate-targets`, `current.json`, UI matrice, tests offline.

42. [NICE] Mode `--no-network`: le contrat est flou.
    Fix: en MVP, `--no-network` lit uniquement fixtures/cache et doit marquer tout non-cache
    `unknown`, pas echouer le collect complet.

## Verdict

GO avec ces 42 corrections.
