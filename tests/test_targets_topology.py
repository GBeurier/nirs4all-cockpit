from __future__ import annotations

import re
from pathlib import Path

from cockpit.manual_actions import ManualAction, evaluate, load_actions
from cockpit.model import PackageSource, PackageStatus, Snapshot, TargetStatus
from cockpit.reconcile import load_targets

ROOT = Path(__file__).resolve().parents[1]


def _targets():
    return load_targets(ROOT / "ops" / "targets.yaml")


def _package(package_id: str):
    targets = _targets()
    for package in targets.packages:
        if package.id == package_id:
            return package
    raise AssertionError(f"missing package {package_id}")


def test_rc_core_uses_canonical_repo_and_keeps_legacy_lite_alias_visible() -> None:
    package = _package("nirs4all-core")

    assert package.channel == "rc"
    assert package.repo == "nirs4all-core"
    assert package.issues_repo == "nirs4all-core"
    assert package.source_of_truth is not None
    assert package.source_of_truth.strategy == "cargo_package"

    targets = {(target.registry, target.name): target for target in package.targets}
    assert targets[("pypi", "nirs4all-lite")].state == "tracked"
    assert targets[("github-release", "nirs4all-core")].state == "tracked"
    assert targets[("pypi", "nirs4all-core")].state == "tracked"
    assert targets[("crates", "nirs4all")].state == "tracked"
    assert targets[("npm", "nirs4all")].state == "tracked"
    assert targets[("r-universe", "nirs4all")].state == "tracked"
    assert targets[("cran", "nirs4all")].state == "tracked"
    core_release_reason = targets[("github-release", "nirs4all-core")].reason or ""
    core_pypi_reason = targets[("pypi", "nirs4all-core")].reason or ""
    assert "MATLAB/Octave archive" in core_release_reason
    assert "Python wheel/sdist fallback assets" in core_release_reason
    assert "GitHub Release v0.2.13 carries Python wheel/sdist fallback assets" in core_pypi_reason


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
    for language in ("rust", "javascript_wasm", "r", "matlab_octave"):
        assert targets[language_surface_targets[language]].state == "tracked"


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
    web = _package("nirs4all-web")
    ui = _package("nirs4all-ui")

    assert oracle.channel == "production-held"
    assert any(target.registry == "pypi" and target.name == "nirs4all" for target in oracle.targets)
    assert web.channel == "production"
    assert web.source_of_truth is not None
    assert web.source_of_truth.strategy == "npm_package_json"
    assert web.source_of_truth.path == "studio-lite/package.json"
    assert [target.registry for target in web.targets] == ["github-release", "pages"]
    web_release_reason = next(target.reason or "" for target in web.targets if target.registry == "github-release")
    assert "client-side-only web app release" in web_release_reason

    assert ui.channel == "rc"
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


def test_v1_custom_app_host_bundle_is_machine_readable() -> None:
    targets = _targets()
    packages = {package.id: package for package in targets.packages}
    bundles = {bundle.id: bundle for bundle in targets.release_bundles}

    assert "v1-custom-app-host" in bundles
    bundle = bundles["v1-custom-app-host"]

    assert bundle.channel == "rc"
    assert bundle.included_packages == ["nirs4all-core", "nirs4all-ui", "nirs4all-web"]
    assert bundle.held_packages == ["nirs4all", "nirs4all-studio"]
    assert set(bundle.included_packages).isdisjoint(bundle.held_packages)
    assert set(bundle.included_packages) | set(bundle.held_packages) <= set(packages)

    assert packages["nirs4all-core"].channel == "rc"
    assert packages["nirs4all-ui"].channel == "rc"
    assert packages["nirs4all-web"].channel == "production"
    assert packages["nirs4all"].channel == "production-held"
    assert packages["nirs4all-studio"].channel == "production-held"
    assert "client-side-only web host" in (bundle.reason or "")


def test_python_provider_and_tools_surfaces_are_rc_packages() -> None:
    providers = _package("nirs4all-providers")
    tools = _package("nirs4all-tools")

    assert providers.channel == "rc"
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
    assert "carries wheel/sdist fallback assets" in github_reason
    assert "provider clients/read facade" in pypi_reason
    assert "neutral contracts remain canonical" in pypi_reason
    assert "docs/site page" in pages_reason

    assert tools.channel == "rc"
    assert tools.source_of_truth is not None
    assert tools.source_of_truth.strategy == "python_attr"
    assert tools.source_of_truth.path == "src/nirs4all_tools/__init__.py"
    assert [(target.registry, target.name, target.state) for target in tools.targets] == [
        ("pypi", "nirs4all-tools", "tracked"),
        ("github-release", "nirs4all-tools", "tracked"),
    ]
    tools_release_reason = next(target.reason or "" for target in tools.targets if target.registry == "github-release")
    assert "v0.0.4 release" in tools_release_reason
    assert "carries wheel/sdist fallback assets" in tools_release_reason


def test_dashboard_pages_urls_cover_current_rc_pages_roster() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    pages_urls = {
        "nirs4all-methods": "https://methods.nirs4all.org/",
        "nirs4all-papers": "https://papers.nirs4all.org/",
        "nirs4all-repository": "https://repository.nirs4all.org/",
        "nirs4all-benchmarks": "https://benchmarks.nirs4all.org/",
        "nirs4all-providers": "https://gbeurier.github.io/nirs4all-providers/",
        "nirs4all-ui": "https://gbeurier.github.io/nirs4all-ui/",
    }
    pages_roster = [
        ("/methods", "methods.nirs4all.org", "nirs4all-methods"),
        ("/papers", "papers.nirs4all.org", "nirs4all-papers"),
        ("/repository", "repository.nirs4all.org", "nirs4all-repository"),
        ("/benchmarks", "benchmarks.nirs4all.org", "nirs4all-benchmarks"),
        ("/providers", "gbeurier.github.io/nirs4all-providers", "nirs4all-providers"),
        ("/ui", "gbeurier.github.io/nirs4all-ui", "nirs4all-ui"),
    ]

    for repo, url in pages_urls.items():
        assert f'"{repo}": "{url}"' in app_js
    for path, host, repo in pages_roster:
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


def test_rc_python_facade_publish_blockers_are_explicit() -> None:
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

    assert "invalid-publisher expected on release-python.yml" in blockers["core"]
    assert "invalid-publisher on v0.2.7 release" in blockers["providers"]
    assert "invalid-publisher on v0.0.4 release" in blockers["tools"]
    assert "GitHub Release v0.0.4 carries wheel/sdist fallback assets" in blockers["tools"]
    assert "invalid-publisher on v0.1.5 release" in blockers["benchmarks"]
    assert "invalid-publisher on v0.1.6 release" in blockers["repository"]
    assert "GitHub Release v0.1.6 carries wheel/sdist fallback assets" in blockers["repository"]


def test_current_pypi_manual_actions_cover_invalid_publisher_failures() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    expected = {
        "pypi-publisher-core": ("nirs4all-core", "v0.2.13"),
        "pypi-publisher-providers": ("nirs4all-providers", "v0.2.7"),
        "pypi-publisher-tools": ("nirs4all-tools", "v0.0.4"),
        "pypi-publisher-benchmarks": ("nirs4all-benchmarks", "v0.1.5"),
        "pypi-publisher-repository": ("nirs4all-repository", "v0.1.6"),
    }

    for action_id, (project, failed_version) in expected.items():
        action = actions[action_id]
        assert action.severity == "blocker"
        assert project in action.title
        assert failed_version in action.title
        assert action.auto_check == {"registry": "pypi", "name": project, "expect": "published"}


def test_active_readthedocs_targets_are_tracked_without_manual_activation_actions() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}

    for package_id in ("nirs4all-benchmarks", "nirs4all-papers", "nirs4all-repository"):
        package = _package(package_id)
        readthedocs = next(target for target in package.targets if target.registry == "readthedocs")
        assert readthedocs.state == "tracked"
        assert "active" in (readthedocs.reason or "")
    assert not any(action_id.startswith("rtd-activate-") for action_id in actions)


def test_current_runiverse_manual_action_tracks_core_rebuild_resolution() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    action = actions["runiverse-core-rebuild"]

    assert action.status == "done"
    assert action.severity == "important"
    assert "nirs4all-core" in action.title
    assert "nirs4all-lite" in action.title
    assert "nirs4all-core:r-universe" in action.affects
    assert action.auto_check == {"registry": "r-universe", "name": "nirs4all", "expect": "green"}


def test_current_runiverse_manual_actions_cover_stale_rc_rebuilds() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
    expected = {
        "runiverse-core-rebuild": ("nirs4all-core", "nirs4all", "v0.2.13", "done"),
        "runiverse-formats-rebuild": ("nirs4all-formats", "nirs4allformats", "v0.2.4", "done"),
        "runiverse-io-rebuild": ("nirs4all-io", "nirs4allio", "v0.1.9", "done"),
        "runiverse-dagml-data-rebuild": ("dag-ml-data", "dagmldata", "v0.2.5", "todo"),
    }

    for action_id, (repo, package_name, version, status) in expected.items():
        action = actions[action_id]
        assert action.status == status
        assert action.severity == "important"
        assert "R-universe" in action.title
        assert any(repo in item for item in action.affects)
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


def test_cran_manual_actions_cover_tracked_rc_r_surfaces() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops" / "manual-actions.yaml")}
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
    assert "tag-triggered workflow must be rerun manually" in core.title
