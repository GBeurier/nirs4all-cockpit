"""Independently versioned components retain registry and repository identities."""
from pathlib import Path

import pytest

from cockpit import cli, version
from cockpit import reconcile as rec
from cockpit.model import (
    ActionsStats,
    CodeStats,
    Downloads,
    Issues,
    PackageSource,
    PackageStatus,
    RepoStats,
    Snapshot,
    TargetStatus,
)

ROOT = Path(__file__).resolve().parents[1]


def component():
    return next(p for p in rec.load_targets(ROOT / "ops/targets.yaml").packages if p.id == "n4m")


def test_n4m_component_reads_its_actual_cargo_manifest_and_safe_workflow():
    package = component()
    assert package.repo == "nirs4all-methods"
    assert package.tag_prefix == "n4m-v"
    assert package.source_of_truth.strategy == "cargo_package"
    assert package.source_of_truth.path == "bindings/rust/n4m/Cargo.toml"
    target, = package.targets
    assert (target.registry, target.name, target.state) == ("crates", "n4m", "tracked")
    assert target.workflow.file == "release-n4m-crate.yml"
    assert target.workflow.trigger == "tag"
    assert target.workflow.danger == "safe"
    assert target.workflow.publishes_on_dispatch is False
    assert target.workflow.inputs == []


def test_namespaced_tags_sort_numerically_and_exclude_prereleases():
    tags = ["v9.9.9", "n4m-v0.9.0", "n4m-v0.10.0", "n4m-v0.11.0rc1", "n4m-notes"]
    assert rec._latest_prod_tag(tags, "n4m-v") == "n4m-v0.10.0"
    assert rec._latest_any_tag(tags, "n4m-v") == "n4m-v0.11.0rc1"
    assert rec._latest_prod_tag(tags) == "v9.9.9"


@pytest.mark.parametrize("manifest,flags", [("0.4.0", []), ("0.5.0", ["source_ahead"])])
def test_component_namespace_is_not_part_of_registry_version(monkeypatch, manifest, flags):
    monkeypatch.setattr(rec, "_source_versions", lambda *a, **kw: {
        "manifest_version": manifest, "latest_prod_tag": "n4m-v0.4.0", "latest_any_tag": "n4m-v0.4.0",
    })
    monkeypatch.setattr(rec.code_stats, "scan", lambda *a, **kw: None)

    def registry_result(owner, package, target, expected, *, no_network):
        assert expected == "0.4.0"
        state = version.classify(expected, "0.4.0", http_status=200, transient_error=False,
                                 excluded=False, planned=False)
        return TargetStatus(registry=target.registry, name=target.name, status=state, published_version="0.4.0")

    monkeypatch.setattr(rec, "_reconcile_target", registry_result)
    result = rec._reconcile_package("GBeurier", component(), no_network=True)
    assert result.rollup == "green"
    assert result.source.latest_prod_tag == "n4m-v0.4.0"
    assert result.source.expected_prod_version == "0.4.0"
    assert result.flags == flags


def test_components_count_shared_repository_stats_once_and_downloads_separately():
    packages = [PackageStatus(
        id=name, repo="nirs4all-methods", source=PackageSource(), rollup="green",
        issues=Issues(open=2), repo_stats=RepoStats(stars=3, forks=4, watchers=5, open_prs=7),
        code_stats=CodeStats(loc_code=6, loc_total=7, files=8, tests=9),
        actions_stats=ActionsStats(total_runs=10),
        targets=[TargetStatus(registry=registry, name=name, status="green", downloads=Downloads(last_month=11))],
    ) for name, registry in [("nirs4all-methods", "pypi"), ("n4m", "crates")]]
    totals = rec._compute_totals(packages)
    assert totals.model_dump() == {
        "packages": 2, "repos": 1, "stars": 3, "forks": 4, "watchers": 5, "open_issues": 2,
        "open_prs": 7, "loc_code": 6, "loc_total": 7, "tests": 9, "files": 8, "workflow_runs": 10,
        "downloads_last_month": 22,
    }


def test_cli_carry_forward_keeps_repository_totals_deduplicated():
    packages = [PackageStatus(
        id=name, repo="shared", source=PackageSource(), rollup="green", targets=[],
        issues=Issues(open=3), repo_stats=RepoStats(stars=8, open_prs=2),
        actions_stats=ActionsStats(total_runs=12),
    ) for name in ["product", "component"]]
    snap = Snapshot(generated_at="2026-10-29T00:00:00Z", generator={}, packages=packages, summary={})
    cli._carry_forward_public_signals(snap, {"packages": []})
    assert snap.totals.open_issues == 3
    assert snap.totals.open_prs == 2
    assert snap.totals.stars == 8
    assert snap.totals.workflow_runs == 12
    assert snap.totals == rec._compute_totals(packages)


def test_preflight_tracks_verified_publication_surfaces_and_domains_its_actual_owner():
    inventory = rec.load_targets(ROOT / "ops/targets.yaml")
    preflight = next(p for p in inventory.packages if p.id == "nirs4all-preflight")
    assert preflight.repo == preflight.issues_repo == "nirs4all-preflight"
    assert preflight.source_of_truth.strategy == "cargo_workspace"
    assert {(t.registry, t.name) for t in preflight.targets} == {
        ("npm", "@nirs4all/preflight"), ("crates", "nirs4all-preflight"),
        ("github-release", "nirs4all-preflight"), ("pages", "nirs4all-preflight"),
    }
    domains = next(p for p in inventory.packages if p.id == "nirs4all-domains")
    assert domains.owner == "dcornet"
    assert domains.targets == []
    assert rec._rollup([]) == "excluded"


def test_owner_override_reaches_source_collection_and_snapshot(monkeypatch):
    inventory = rec.load_targets(ROOT / "ops/targets.yaml")
    domains = next(p for p in inventory.packages if p.id == "nirs4all-domains")
    seen = []

    def source(owner, package, *, no_network):
        seen.append((owner, package.repo))
        return {"manifest_version": "0.1.0-alpha.16"}

    monkeypatch.setattr(rec, "_source_versions", source)
    monkeypatch.setattr(rec.code_stats, "scan", lambda *a, **kw: None)
    status = rec._reconcile_package("GBeurier", domains, no_network=True)
    assert seen == [("dcornet", "nirs4all-domains")]
    assert status.owner == "dcornet"
    assert status.rollup == "excluded"
