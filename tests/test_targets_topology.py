from __future__ import annotations

from pathlib import Path

from cockpit.reconcile import load_targets

ROOT = Path(__file__).resolve().parents[1]


def _package(package_id: str):
    targets = load_targets(ROOT / "ops" / "targets.yaml")
    for package in targets.packages:
        if package.id == package_id:
            return package
    raise AssertionError(f"missing package {package_id}")


def test_rc_core_keeps_legacy_lite_prod_targets_visible() -> None:
    package = _package("nirs4all-core")

    assert package.repo == "nirs4all-lite"
    assert package.issues_repo == "nirs4all-lite"
    assert package.source_of_truth is not None
    assert package.source_of_truth.strategy == "cargo_package"

    targets = {(target.registry, target.name): target for target in package.targets}
    assert targets[("pypi", "nirs4all-lite")].state == "tracked"
    assert targets[("github-release", "nirs4all-lite")].state == "tracked"
    assert targets[("pypi", "nirs4all-core")].state == "planned"
    assert targets[("crates", "nirs4all")].state == "tracked"
    assert targets[("npm", "nirs4all")].state == "tracked"
    assert targets[("r-universe", "nirs4all")].state == "tracked"


def test_python_oracle_web_client_and_shared_ui_are_separate() -> None:
    oracle = _package("nirs4all")
    web = _package("nirs4all-web")
    ui = _package("nirs4all-ui")

    assert any(target.registry == "pypi" and target.name == "nirs4all" for target in oracle.targets)
    assert [target.registry for target in web.targets] == ["pages"]

    assert ui.channel == "rc"
    assert ui.source_of_truth is not None
    assert ui.source_of_truth.strategy == "npm_package_json"
    assert [(target.registry, target.name, target.state) for target in ui.targets] == [
        ("npm", "nirs4all-ui", "planned")
    ]
