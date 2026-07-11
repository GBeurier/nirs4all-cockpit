from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from cockpit import snapshot as snapshot_io
from cockpit.manual_actions import ManualAction, evaluate, load_actions, public_payload
from cockpit.model import PackageSource, PackageStatus, Snapshot, TargetStatus
from cockpit.reconcile import _CANONICAL_PAGES_URLS, load_targets, reconcile

ROOT = Path(__file__).resolve().parents[1]


def _targets():
    return load_targets(ROOT / "ops" / "targets.yaml")


def _package(package_id: str):
    targets = _targets()
    for package in targets.packages:
        if package.id == package_id:
            return package
    raise AssertionError(f"missing package {package_id}")


def test_rc_core_uses_canonical_repo_without_legacy_lite_alias() -> None:
    package = _package("nirs4all-core")

    assert package.repo == "nirs4all-core"
    assert package.issues_repo == "nirs4all-core"
    assert package.coordination_tag == "n4a-v1-rc17-2026.07-refactor"
    assert package.source_of_truth is not None
    assert package.source_of_truth.strategy == "cargo_package"

    assert [(workflow.file, workflow.trigger, workflow.danger) for workflow in package.workflows] == [
        ("release-source.yml", "tag", "safe"),
        ("release-matlab.yml", "tag", "safe"),
    ]

    targets = {(target.registry, target.name): target for target in package.targets}
    assert ("pypi", "nirs4all-lite") not in targets
    assert targets[("github-release", "nirs4all-core")].state == "tracked"
    assert targets[("pypi", "nirs4all-core")].state == "tracked"
    assert targets[("crates", "nirs4all")].state == "tracked"
    assert targets[("npm", "nirs4all")].state == "tracked"
    assert targets[("r-universe", "nirs4all")].state == "manual"
    assert targets[("cran", "nirs4all")].state == "manual"
    core_release_reason = targets[("github-release", "nirs4all-core")].reason or ""
    core_pypi_reason = targets[("pypi", "nirs4all-core")].reason or ""
    assert "MATLAB/Octave archive" in core_release_reason
    assert "R tarball" in core_release_reason
    assert "SHA256SUMS" in core_release_reason
    assert "Python wheel/sdist fallback assets" not in core_release_reason
    assert "PyPI package targets v0.3.11" in core_pypi_reason


def test_inventory_tracks_no_live_nirs4all_lite_release_alias() -> None:
    targets = _targets()

    live_alias_targets = [
        (package.id, target.registry, target.name)
        for package in targets.packages
        for target in package.targets
        if target.name == "nirs4all-lite"
    ]

    assert live_alias_targets == []


def test_rc_core_targets_account_for_all_v1_language_surfaces() -> None:
    package = _package("nirs4all-core")

    targets = {(target.registry, target.name): target for target in package.targets}
    language_surface_targets = {
        "python": ("pypi", "nirs4all-core"),
        "rust": ("crates", "nirs4all"),
        "javascript_wasm": ("npm", "nirs4all"),
        "r": ("r-universe", "nirs4all"),
        "matlab_octave": ("github-release", "nirs4all-core"),
    }

    assert set(language_surface_targets) == {"python", "rust", "javascript_wasm", "r", "matlab_octave"}
    for key in language_surface_targets.values():
        assert key in targets
    assert targets[language_surface_targets["python"]].state == "tracked"
    for language in ("rust", "javascript_wasm", "matlab_octave"):
        assert targets[language_surface_targets[language]].state == "tracked"
    assert targets[language_surface_targets["r"]].state == "manual"


def test_dag_python_binding_surfaces_have_publish_workflows() -> None:
    expected = {
        "dag-ml": "dag-ml",
        "dag-ml-data": "dag-ml-data",
    }

    for package_id, pypi_name in expected.items():
        package = _package(package_id)
        target = next(
            target
            for target in package.targets
            if target.registry == "pypi" and target.name == pypi_name
        )

        assert target.state == "tracked"
        assert "Python binding" in (target.reason or "")
        assert target.workflow is not None
        assert target.workflow.file == "release-python.yml"
        assert target.workflow.trigger == "workflow_dispatch"
        assert target.workflow.danger == "publish"
        assert target.workflow.publishes_on_dispatch is True
        assert [(item["name"], item["type"], item["default"]) for item in target.workflow.inputs] == [
            ("publish", "boolean", False)
        ]


def test_python_oracle_web_client_and_shared_ui_are_separate() -> None:
    oracle = _package("nirs4all")
    studio = _package("nirs4all-studio")
    web = _package("nirs4all-web")
    ui = _package("nirs4all-ui")

    assert any(target.registry == "pypi" and target.name == "nirs4all" for target in oracle.targets)
    studio_release_target = next(
        target
        for target in studio.targets
        if target.registry == "github-release"
    )
    studio_release_reason = studio_release_target.reason or ""
    assert "Studio transition release 0.10.0" in studio_release_reason
    assert "n4a-v1-rc8-2026.07-refactor" not in studio_release_reason
    assert studio_release_target.workflow is not None
    assert studio_release_target.workflow.file == "release-unified.yml"
    assert studio_release_target.workflow.publishes_on_dispatch is False
    assert web.coordination_tag == "n4a-v1-rc14-2026.07-refactor"
    assert web.source_of_truth is not None
    assert web.source_of_truth.strategy == "npm_package_json"
    assert web.source_of_truth.path == "web-app/package.json"
    assert [target.registry for target in web.targets] == ["github-release", "pages"]
    web_release_reason = next(target.reason or "" for target in web.targets if target.registry == "github-release")
    web_pages_reason = next(target.reason or "" for target in web.targets if target.registry == "pages")
    assert "client-side-only web app release" in web_release_reason
    assert "n4a-v1-rc14-2026.07-refactor" in web_pages_reason

    assert ui.coordination_tag == "n4a-v1-rc14-2026.07-refactor"
    assert ui.source_of_truth is not None
    assert ui.source_of_truth.strategy == "npm_package_json"
    assert [(target.registry, target.name, target.state) for target in ui.targets] == [
        ("github-release", "nirs4all-ui", "tracked"),
        ("npm", "nirs4all-ui", "tracked"),
        ("pages", "nirs4all-ui", "tracked"),
    ]
    npm_reason = next(target.reason or "" for target in ui.targets if target.registry == "npm")
    pages_reason = next(target.reason or "" for target in ui.targets if target.registry == "pages")
    assert "reusable components" in npm_reason
    assert "brand assets" in npm_reason
    assert "components/assets showcase" in pages_reason
    ui_pages = next(target for target in ui.targets if target.registry == "pages")
    assert ui_pages.workflow is not None
    assert ui_pages.workflow.file == "pages.yml"
    assert ui_pages.workflow.danger == "safe"


def test_inventory_has_no_release_bundles_or_display_channels() -> None:
    raw = yaml.safe_load((ROOT / "ops" / "targets.yaml").read_text(encoding="utf-8"))

    assert "release_bundles" not in raw
    for package in raw["packages"]:
        assert "channel" not in package


def test_public_snapshot_has_no_channel_display_metadata() -> None:
    snapshot = reconcile(_targets(), no_network=True)
    payload = json.loads(snapshot_io._dump(snapshot))
    raw_payload = json.dumps(payload)

    assert "release_bundles" not in payload
    assert "Release bundles" not in raw_payload
    assert "production held" not in raw_payload
    assert "held outside" not in raw_payload
    assert "production app release remains held" not in raw_payload
    for package in payload["packages"]:
        assert "channel" not in package
        for target in package["targets"]:
            assert "channel" not in target


def test_python_provider_and_tools_surfaces_are_rc_packages() -> None:
    providers = _package("nirs4all-providers")
    tools = _package("nirs4all-tools")

    assert providers.source_of_truth is not None
    assert providers.source_of_truth.strategy == "python_attr"
    assert providers.source_of_truth.path == "src/nirs4all_providers/__init__.py"
    assert [(target.registry, target.name, target.state) for target in providers.targets] == [
        ("github-release", "nirs4all-providers", "tracked"),
        ("pypi", "nirs4all-providers", "tracked"),
        ("pages", "nirs4all-providers", "tracked"),
    ]
    github_reason = next(target.reason or "" for target in providers.targets if target.registry == "github-release")
    pypi_reason = next(target.reason or "" for target in providers.targets if target.registry == "pypi")
    pages_reason = next(target.reason or "" for target in providers.targets if target.registry == "pages")
    assert "provider-client release" in github_reason
    assert "PyPI distribution is published" in github_reason
    assert "provider clients/read facade" in pypi_reason
    assert "neutral contracts remain canonical" in pypi_reason
    assert "docs/site page" in pages_reason
    provider_pages = next(target for target in providers.targets if target.registry == "pages")
    assert provider_pages.workflow is not None
    assert provider_pages.workflow.file == "pages.yml"
    assert provider_pages.workflow.danger == "safe"

    assert tools.source_of_truth is not None
    assert tools.source_of_truth.strategy == "python_attr"
    assert tools.source_of_truth.path == "src/nirs4all_tools/__init__.py"
    assert [(target.registry, target.name, target.state) for target in tools.targets] == [
        ("pypi", "nirs4all-tools", "tracked"),
        ("github-release", "nirs4all-tools", "tracked"),
    ]
    tools_release_reason = next(target.reason or "" for target in tools.targets if target.registry == "github-release")
    assert "v0.0.5 release" in tools_release_reason
    assert "carries wheel/sdist fallback assets" in tools_release_reason


def test_pages_targets_declare_repo_local_deploy_workflows_when_available() -> None:
    expected = {
        "nirs4all-web": "deploy-pages.yml",
        "nirs4all-ui": "pages.yml",
        "nirs4all-providers": "pages.yml",
        "nirs4all-device": "pages.yml",
        "nirs4all-cockpit": "pages.yml",
        "nirs4all-benchmarks": "pages.yml",
        "nirs4all-repository": "deploy-pages.yml",
    }

    for package_id, workflow_file in expected.items():
        package = _package(package_id)
        page_target = next(target for target in package.targets if target.registry == "pages")
        assert page_target.workflow is not None
        assert page_target.workflow.file == workflow_file
        assert page_target.workflow.trigger == "workflow_dispatch"
        assert page_target.workflow.danger == "safe"
        assert page_target.workflow.publishes_on_dispatch is False


def test_device_is_tracked_as_pages_only_public_surface() -> None:
    device = _package("nirs4all-device")

    assert device.source_of_truth is not None
    assert device.source_of_truth.strategy == "npm_package_json"
    assert device.source_of_truth.path == "package.json"
    assert [(target.registry, target.name, target.state) for target in device.targets] == [
        ("pages", "nirs4all-device", "tracked"),
    ]
    pages = device.targets[0]
    assert pages.workflow is not None
    assert pages.workflow.file == "pages.yml"
    assert "Android debug APK remains a CI artifact" in (pages.reason or "")


def test_dashboard_pages_urls_cover_current_rc_pages_roster() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    pages_targets = {
        package.repo
        for package in _targets().packages
        for target in package.targets
        if target.registry == "pages"
    }
    assert pages_targets == set(_CANONICAL_PAGES_URLS)

    for repo, url in _CANONICAL_PAGES_URLS.items():
        assert f'"{repo}": "{url}"' in app_js
        path = f'/{repo.removeprefix("nirs4all-")}'
        host = url.removeprefix("https://").removesuffix("/")
        assert f'["{path}", "{host}", "{repo}"]' in app_js
    assert (
        'const href = (reg === "readthedocs" || reg === "pages") && rep.evidence && rep.evidence.version_endpoint'
        in app_js
    )


def test_dashboard_surfaces_public_manual_blockers() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert "manual-actions.json" in app_js
    assert "renderManualActions" in app_js
    assert "manual-actions-block" in index


def test_dashboard_manual_blockers_are_bottom_section() -> None:
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    blockers_at = index.index('id="manual-actions-block"')

    for section_id in (
        'id="matrix"',
        'id="downloads"',
        'id="repostats"',
        'id="codestats"',
        'id="admin"',
        'id="visits-block"',
        'id="search-console-block"',
        'id="sentry-block"',
    ):
        assert index.index(section_id) < blockers_at
    assert blockers_at < index.index('<footer class="foot">')


def test_dashboard_manual_blockers_sort_after_other_manual_actions() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "const severityRank = { important: 0, info: 1, blocker: 2 };" in app_js


def test_dashboard_keeps_release_matrix_without_bundle_or_channel_chips() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert 'id="release-bundles-block"' not in index
    assert "Release bundles" not in index
    assert "RC scopes" not in index
    assert "held production lines" not in index
    assert "renderReleaseBundles" not in app_js
    assert "snap.release_bundles" not in app_js
    assert "bundle.channel" not in app_js
    assert "bundle-status" not in app_js
    assert "bundle-status" not in style
    assert "bundle-chip" not in style
    assert "pkg-channel" not in app_js
    assert ".pkg-channel" not in style
    assert "production held" not in app_js
    assert "production held" not in index
    assert "tt-reason" not in app_js
    assert "app.js?v=20260710-current-only" in index
    assert "style.css?v=20260710-current-only" in index


def test_dashboard_marks_missing_visit_rows_untracked() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'text: r.count == null ? "untracked" : fmtInt(r.count)' in app_js
    assert "counts.has(path) ? counts.get(path) : null" in app_js


def test_rc_python_facade_publish_state_is_explicit() -> None:
    core = _package("nirs4all-core")
    providers = _package("nirs4all-providers")
    tools = _package("nirs4all-tools")
    benchmarks = _package("nirs4all-benchmarks")
    repository = _package("nirs4all-repository")

    blockers = {
        "core": next(
            target.reason or ""
            for target in core.targets
            if target.registry == "pypi" and target.name == "nirs4all-core"
        ),
        "providers": next(
            target.reason or ""
            for target in providers.targets
            if target.registry == "pypi" and target.name == "nirs4all-providers"
        ),
        "tools": tools.targets[0].reason or "",
        "benchmarks": next(
            target.reason or ""
            for target in benchmarks.targets
            if target.registry == "pypi" and target.name == "nirs4all-benchmarks"
        ),
        "repository": next(
            target.reason or ""
            for target in repository.targets
            if target.registry == "pypi" and target.name == "nirs4all-repository"
        ),
    }

    assert "PyPI package targets v0.3.11" in blockers["core"]
    assert "PyPI package is published at v0.2.10" in blockers["providers"]
    assert "PyPI package is published at v0.0.5" in blockers["tools"]
    assert "GitHub Release v0.0.5 also carries wheel/sdist assets" in blockers["tools"]
    assert "PyPI package is published at v0.1.6" in blockers["benchmarks"]
    assert "PyPI package is published at v0.1.10" in blockers["repository"]
    assert "GitHub Release v0.1.10 also carries wheel/sdist assets" in blockers["repository"]


def test_current_pypi_manual_actions_track_resolved_publishers() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    expected = {
        "pypi-publisher-core": ("nirs4all-core", "v0.3.11"),
        "pypi-publisher-providers": ("nirs4all-providers", "v0.2.10"),
        "pypi-publisher-tools": ("nirs4all-tools", "v0.0.5"),
        "pypi-publisher-benchmarks": ("nirs4all-benchmarks", "v0.1.6"),
        "pypi-publisher-repository": ("nirs4all-repository", "v0.1.10"),
        "pypi-publisher-dag-ml": ("dag-ml", "v0.2.7"),
        "pypi-publisher-dag-ml-data": ("dag-ml-data", "v0.2.9"),
    }

    for action_id, (project, published_version) in expected.items():
        action = actions[action_id]
        assert action.status == "done"
        assert action.severity == "blocker"
        assert project in action.title
        assert published_version in action.title
        assert "published" in action.title
        assert action.auto_check == {"registry": "pypi", "name": project, "expect": "published"}


def test_studio_windows_rc_smoke_is_tracked_as_manual_blocker() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    action = actions["studio-windows-rc-smoke"]

    assert action.status == "todo"
    assert action.severity == "blocker"
    assert "Windows 0.10.0 transition installer" in action.title
    assert action.manual_url == "https://github.com/GBeurier/nirs4all-studio/releases/tag/0.10.0"
    assert "nirs4all-studio:release-unified.yml" in action.affects
    assert "nirs4all-studio:github-release" in action.affects


def test_active_readthedocs_targets_are_tracked_without_manual_activation_actions() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}

    for package_id in ("nirs4all-benchmarks", "nirs4all-papers", "nirs4all-repository"):
        package = _package(package_id)
        readthedocs = next(target for target in package.targets if target.registry == "readthedocs")
        assert readthedocs.state == "tracked"
        assert "active" in (readthedocs.reason or "")
    assert not any(action_id.startswith("rtd-activate-") for action_id in actions)


def test_current_runiverse_manual_action_tracks_core_rebuild_done() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    action = actions["runiverse-core-rebuild"]

    assert action.status == "done"
    assert action.severity == "important"
    assert "nirs4all-core" in action.title
    assert "published" in action.title
    assert action.manual_url == "https://gbeurier.r-universe.dev/nirs4all"
    assert "nirs4all-core:r-universe" in action.affects
    assert "nirs4all-core@59d54c97399a43eb53665d236f5ab01b5972fe16" in action.affects
    assert "GBeurier/GBeurier.r-universe.dev@b4788189c992d3e1d9edd7fdd2c92b6c801160cc" in action.affects
    assert "r-universe/gbeurier:nirs4all rebuild" in action.affects
    assert action.auto_check == {"registry": "r-universe", "name": "nirs4all", "expect": "green"}


def test_current_runiverse_manual_actions_cover_release_rebuilds() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    expected = {
        "runiverse-core-rebuild": ("nirs4all-core", "nirs4all", "v0.3.11", "done"),
        "runiverse-methods-n4m-rebuild": ("nirs4all-methods", "n4m", "v1.0.9", "done"),
        "runiverse-methods-pls4all-rebuild": ("nirs4all-methods", "pls4all", "v1.0.9", "done"),
        "runiverse-formats-rebuild": ("nirs4all-formats", "nirs4allformats", "v0.2.7", "done"),
        "runiverse-io-rebuild": ("nirs4all-io", "nirs4allio", "v0.1.11", "done"),
        "runiverse-dagml-data-rebuild": ("dag-ml-data", "dagmldata", "v0.2.9", "done"),
        "runiverse-datasets-rebuild": ("nirs4all-datasets", "nirs4alldatasets", "v0.3.8", "done"),
    }

    for action_id, (repo, package_name, version, status) in expected.items():
        action = actions[action_id]
        assert action.status == status
        assert action.severity == "important"
        assert "R-universe" in action.title
        assert any(repo in item for item in action.affects)
        assert "GBeurier.r-universe.dev:packages.json" not in action.affects
        assert package_name in action.title
        assert version in action.title
        assert action.auto_check == {
            "registry": "r-universe",
            "name": package_name,
            "expect": "green",
        }


def test_formats_cran_target_is_explicitly_excluded_to_match_manual_policy() -> None:
    package = _package("nirs4all-formats")
    targets = {(target.registry, target.name): target for target in package.targets}
    assert ("r-universe", "nirs4allformats.lite") not in targets
    cran = targets[("cran", "nirs4allformats")]
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}

    assert cran.state == "excluded"
    assert "do NOT submit nirs4allformats to CRAN" in (cran.reason or "")
    assert "R-universe only" in (cran.reason or "")
    assert "do NOT submit nirs4allformats" in actions["cran-resubmit-n4m-pls4all"].title
    assert "do NOT submit nirs4allformats" in actions["cran-resubmit-pls4all"].title


def test_cran_manual_actions_cover_n4m_and_pls4all_separately() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}

    assert actions["cran-resubmit-n4m-pls4all"].auto_check == {
        "registry": "cran",
        "name": "n4m",
        "expect": "published",
    }
    assert actions["cran-resubmit-pls4all"].auto_check == {
        "registry": "cran",
        "name": "pls4all",
        "expect": "published",
    }
    assert "n4m only" in actions["cran-resubmit-n4m-pls4all"].title
    assert "pls4all only" in actions["cran-resubmit-pls4all"].title


def test_cran_manual_actions_cover_manual_rc_r_surfaces() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    packages = _targets().packages
    targets = {
        (target.registry, target.name): target
        for package in packages
        for target in package.targets
    }
    expected = {
        "cran-submit-nirs4allio": "nirs4allio",
        "cran-submit-nirs4alldatasets": "nirs4alldatasets",
        "cran-submit-nirs4all-core-aggregate": "nirs4all",
    }

    for action_id, package_name in expected.items():
        action = actions[action_id]
        assert action.status == "todo"
        assert action.severity == "important"
        assert "CRAN" in action.title
        assert package_name in action.title
        assert action.auto_check == {
            "registry": "cran",
            "name": package_name,
            "expect": "green",
        }
        assert targets[("cran", package_name)].state == "manual"
        assert targets[("cran", package_name)].workflow is None


def test_cran_rc_manual_actions_do_not_resolve_on_stale_publication() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    action = actions["cran-submit-nirs4alldatasets"]
    snapshot = Snapshot(
        generated_at="2026-07-07T00:00:00+00:00",
        generator={},
        summary={},
        packages=[
            PackageStatus(
                id="nirs4all-datasets",
                repo="nirs4all-datasets",
                source=PackageSource(expected_prod_version="0.3.5"),
                rollup="stale",
                targets=[
                    TargetStatus(
                        registry="cran",
                        name="nirs4alldatasets",
                        status="stale",
                        published_version="0.2.0",
                    )
                ],
            )
        ],
    )

    evaluate(action, snapshot)

    assert action.resolved is False
    assert "status=stale" in (action.check_note or "")


def test_cran_optional_comments_flag_datasets_size_exception() -> None:
    script = (ROOT / "scripts" / "fetch-cran-tarballs.sh").read_text(encoding="utf-8")
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    package = _package("nirs4all-datasets")
    targets = {(target.registry, target.name): target for target in package.targets}

    assert "CRAN-ready now (≤10 MB, clean): `n4m`, `pls4all`, `nirs4allio`." in script
    assert "R-universe-only: `nirs4allformats`; do not submit it to CRAN" in script
    assert "nirs4all-formats" not in script.split("REPOS=", 1)[1].split(")", 1)[0]
    assert "nirs4allformats.lite" not in script
    assert "nirs4allformats|nirs4allformats\\.lite" not in script
    assert "`nirs4alldatasets` (~24 MB)" in script
    assert "24,664,283 bytes" in script
    assert "ships no dataset\npayloads" in script
    assert "sha256sum or shasum is required" in script
    assert 'mv "$SUMS_TMP" "$OUTDIR/SHA256SUMS"' in script
    assert "this script verifies the local file against it" in script
    assert '[ "$expected_sha" = "null" ] && expected_sha=""' in script
    assert "Source tarball ~9.3 MB" not in script
    assert "shipped-in-tarball `cran-comments.md`" not in script
    assert "License: CeCILL-2.1 | AGPL (>= 3)." in script
    assert "24 MB size-exception" in actions["cran-submit-nirs4alldatasets"].title
    assert "size-exception comment" in (targets[("cran", "nirs4alldatasets")].reason or "")


def test_resolved_manual_actions_are_marked_done() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    done_actions = {
        "npm-automation-token",
        "pypi-publisher-pls4all",
        "pypi-publisher-io",
        "crates-verify-email",
    }

    for action_id in done_actions:
        assert actions[action_id].status == "done"


def test_manual_action_expect_green_requires_current_target() -> None:
    action = ManualAction(
        id="runiverse-core-rebuild",
        status="todo",
        severity="important",
        title="R-universe rebuild",
        auto_check={"registry": "r-universe", "name": "nirs4all", "expect": "green"},
    )
    snapshot = Snapshot(
        generated_at="2026-07-04T00:00:00+00:00",
        generator={},
        summary={},
        packages=[
            PackageStatus(
                id="nirs4all-core",
                repo="nirs4all-core",
                source=PackageSource(expected_prod_version="0.2.4"),
                rollup="stale",
                targets=[
                    TargetStatus(
                        registry="r-universe",
                        name="nirs4all",
                        status="stale",
                        published_version="0.2.0",
                    )
                ],
            )
        ],
    )

    evaluate(action, snapshot)
    assert action.resolved is False
    assert "status=stale" in (action.check_note or "")

    snapshot.packages[0].targets[0].status = "green"
    snapshot.packages[0].targets[0].published_version = "0.2.4"
    evaluate(action, snapshot)
    assert action.resolved is True


def test_public_manual_action_payload_marks_auto_resolved_todo_as_done() -> None:
    action = ManualAction(
        id="runiverse-core-rebuild",
        status="todo",
        severity="important",
        title="R-universe rebuild",
        auto_check={"registry": "r-universe", "name": "nirs4all", "expect": "green"},
    )
    snapshot = Snapshot(
        generated_at="2026-07-07T00:00:00+00:00",
        generator={},
        summary={},
        packages=[
            PackageStatus(
                id="nirs4all-core",
                repo="nirs4all-core",
                source=PackageSource(expected_prod_version="0.3.4"),
                rollup="green",
                targets=[
                    TargetStatus(
                        registry="r-universe",
                        name="nirs4all",
                        status="green",
                        published_version="0.3.4",
                    )
                ],
            )
        ],
    )

    evaluate(action, snapshot)
    payload = public_payload([action], snapshot)
    exported = payload["actions"][0]

    assert exported["status"] == "done"
    assert exported["declared_status"] == "todo"
    assert exported["resolved"] is True
    assert payload["counts"]["pending"] == 0
    assert payload["counts"]["resolved"] == 1


def test_public_manual_action_payload_counts_declared_done_until_auto_check_resolves() -> None:
    action = ManualAction(
        id="runiverse-core-rebuild",
        status="done",
        severity="important",
        title="R-universe rebuild",
        auto_check={"registry": "r-universe", "name": "nirs4all", "expect": "green"},
    )
    snapshot = Snapshot(
        generated_at="2026-07-09T00:00:00+00:00",
        generator={},
        summary={},
        packages=[
            PackageStatus(
                id="nirs4all-core",
                repo="nirs4all-core",
                source=PackageSource(expected_prod_version="0.3.11"),
                rollup="stale",
                targets=[
                    TargetStatus(
                        registry="r-universe",
                        name="nirs4all",
                        status="stale",
                        published_version="0.3.7",
                    )
                ],
            )
        ],
    )

    evaluate(action, snapshot)
    payload = public_payload([action], snapshot)
    exported = payload["actions"][0]

    assert exported["status"] == "done"
    assert exported["declared_status"] == "done"
    assert exported["resolved"] is False
    assert payload["counts"]["pending"] == 1
    assert payload["counts"]["important"] == 1
    assert payload["counts"]["resolved"] == 0


def test_current_pypi_manual_actions_match_targets_reasons_and_workflow_inputs() -> None:
    actions = {
        action.id: action
        for action in load_actions(ROOT / "ops" / "manual-actions.yaml")
        if action.id.startswith("pypi-publisher-")
    }
    packages = load_targets(ROOT / "ops" / "targets.yaml").packages
    targets = {
        (target.registry, target.name): target
        for package in packages
        for target in package.targets
    }

    for action in actions.values():
        if not action.auto_check:
            continue
        key = (action.auto_check["registry"], action.auto_check["name"])
        target = targets[key]
        version = re.search(r"v\d+\.\d+\.\d+", action.title)
        if version:
            assert version.group(0) in (target.reason or "")

        for step in action.after_done:
            run_workflow = step["run_workflow"]
            assert run_workflow["workflow"] == target.workflow.file
            declared_inputs = {item["name"] for item in target.workflow.inputs}
            assert set(run_workflow.get("inputs", {})) <= declared_inputs

            if action.id == "pypi-publisher-repository":
                assert target.workflow.danger == "publish"
                assert run_workflow.get("inputs") == {"dry_run": "false"}

    core = actions["pypi-publisher-core"]
    assert core.after_done == []
    assert "published from release-python.yml" in core.title
