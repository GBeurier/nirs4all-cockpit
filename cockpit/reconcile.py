"""Reconcile observed registry/CI/issue facts into a :class:`Snapshot`.

The collectors report *facts*; this module turns them into *states* using the
pure engine in :mod:`cockpit.version`, then rolls each package up to a single
worst-cell verdict. The rules it enforces (from the Codex review):

* The registry status of a target is kept **separate** from its release
  workflow's health: a failed release run does not redden a target whose
  expected version is published.
* Download counts that come back ``unknown`` never degrade the version verdict.
* A ``planned`` target reconciles as ``missing`` and carries a ``planned`` flag;
  it gets no admin button (that is the admin layer's concern).
* ``excluded`` targets are counted in the summary but kept **out** of the
  package roll-up and never turned green.
* The package roll-up is the worst cell, ordered
  ``broken > missing > stale > unknown > green`` (excluded ignored).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

from . import version as ver
from .collect import cran, crates, github, local_manifests, npm, pypi, runiverse
from .collect.base import now_iso
from .model import (
    Downloads,
    Evidence,
    Issues,
    Package,
    PackageSource,
    PackageStatus,
    RepoStats,
    Snapshot,
    Target,
    Targets,
    TargetStatus,
    WorkflowHealth,
)

# Worst-cell ordering for the package roll-up (excluded is out of band).
_RANK = {"broken": 5, "missing": 4, "stale": 3, "unknown": 2, "green": 1}

# registry → collector entry function (each returns the fact dict).
_COLLECTORS = {
    "pypi": pypi.collect,
    "npm": npm.collect,
    "crates": crates.collect,
    "r-universe": runiverse.collect,
    "cran": cran.collect,
}

# Version-tag prefix considered a production tag (vX.Y.Z, non-prerelease).
_PROD_TAG = "v"


def load_targets(path: str | Path) -> Targets:
    """Parse ``ops/targets.yaml`` into the :class:`Targets` inventory model."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Targets.model_validate(data)


def reconcile(
    targets: Targets,
    *,
    only: set[str] | None = None,
    no_network: bool = False,
    with_traffic: bool = False,
    run_id: str | None = None,
    generated_at: str | None = None,
) -> Snapshot:
    """Reconcile the inventory against live registry/CI state into a snapshot.

    Args:
        targets: Parsed inventory.
        only: Optional set of package ids to limit the collect to.
        no_network: When ``True``, skip all network calls; every non-cached fact
            is reported as ``unknown`` rather than failing the collect.
        run_id: Optional CI run id, stored in the snapshot ``generator`` block.
        generated_at: UTC ISO-8601 stamp to embed in the snapshot. The CLI is the
            single place wall-clock time enters the pipeline and passes it here;
            when omitted (library use) it falls back to ``now_iso()``.

    Returns:
        A fully populated :class:`Snapshot`.
    """
    packages: list[PackageStatus] = []
    summary = {"green": 0, "stale": 0, "missing": 0, "broken": 0, "unknown": 0, "excluded": 0}

    for pkg in targets.packages:
        if only and pkg.id not in only:
            continue
        status = _reconcile_package(targets.owner, pkg, no_network=no_network, with_traffic=with_traffic)
        packages.append(status)
        for tgt in status.targets:
            summary[tgt.status] = summary.get(tgt.status, 0) + 1

    return Snapshot(
        schema_version=1,
        generated_at=generated_at or now_iso(),
        generator={
            "repo": f"{targets.owner}/nirs4all-cockpit",
            "workflow": "collect.yml",
            "run_id": run_id,
        },
        packages=packages,
        summary=summary,
    )


def build_snapshot(
    targets: Targets,
    *,
    only: Iterable[str] | None = None,
    offline: bool = False,
    with_traffic: bool = False,
    generated_at: str | None = None,
    run_id: str | None = None,
) -> Snapshot:
    """CLI-facing entry point: reconcile an already-parsed inventory into a snapshot.

    Thin adapter over :func:`reconcile` matching the ``n4a-cockpit collect`` call
    shape: ``only`` is any iterable of package ids (not just a set), ``offline``
    maps to ``no_network``, and ``generated_at`` is the single wall-clock stamp
    the CLI injects.

    Args:
        targets: Parsed inventory (:class:`Targets`).
        only: Optional iterable of package ids to limit the collect to.
        offline: When ``True``, skip all network calls (non-cached facts become
            ``unknown``).
        generated_at: UTC ISO-8601 stamp from the CLI.
        run_id: Optional CI run id for the ``generator`` block.

    Returns:
        A fully populated :class:`Snapshot`.
    """
    return reconcile(
        targets,
        only=set(only) if only is not None else None,
        no_network=offline,
        with_traffic=with_traffic,
        run_id=run_id,
        generated_at=generated_at,
    )


def _reconcile_package(owner: str, pkg: Package, *, no_network: bool, with_traffic: bool = False) -> PackageStatus:
    manifest, latest_prod, latest_any, commit = _source_versions(owner, pkg, no_network=no_network)
    expected = ver.derive_expected(manifest, latest_prod)

    flags: list[str] = []
    if ver.source_ahead(manifest, latest_prod):
        flags.append("source_ahead")

    target_statuses: list[TargetStatus] = []
    workflows: list[WorkflowHealth] = []
    seen_workflows: set[str] = set()

    for tgt in pkg.targets:
        ts = _reconcile_target(owner, pkg, tgt, expected, no_network=no_network)
        target_statuses.append(ts)
        if tgt.workflow and tgt.workflow.file not in seen_workflows and not no_network:
            seen_workflows.add(tgt.workflow.file)
            wf = github.workflow_last_run(owner, pkg.repo, tgt.workflow.file)
            if wf is not None:
                workflows.append(WorkflowHealth.model_validate(wf))

    issues = Issues()
    repo_stats: RepoStats | None = None
    if not no_network:
        issues_repo = pkg.issues_repo or pkg.repo
        issues = Issues.model_validate(github.open_issues(owner, issues_repo))
        stats_dict = github.repo_stats(owner, pkg.repo, with_traffic=with_traffic)
        raw_open = stats_dict.pop("_open_issues_count", None)
        repo_stats = RepoStats.model_validate(stats_dict)
        if raw_open is not None:
            repo_stats.open_prs = max(0, raw_open - issues.open)

    rollup = _rollup(target_statuses)

    return PackageStatus(
        id=pkg.id,
        repo=pkg.repo,
        source=PackageSource(
            manifest_version=manifest,
            latest_prod_tag=latest_prod,
            latest_any_tag=latest_any,
            expected_prod_version=expected,
            commit=commit,
        ),
        rollup=rollup,
        flags=flags,
        targets=target_statuses,
        workflows=workflows,
        issues=issues,
        repo_stats=repo_stats,
    )


def _source_versions(
    owner: str, pkg: Package, *, no_network: bool
) -> tuple[str | None, str | None, str | None, str | None]:
    """Resolve the four version facts: manifest, latest prod tag, latest any tag, commit."""
    if no_network:
        return None, None, None, None

    sot = pkg.source_of_truth
    manifest = local_manifests.read_manifest_version(
        owner=owner,
        repo=pkg.repo,
        strategy=sot.strategy,
        path=sot.path,
        attr=sot.attr,
    )

    tag_names = github.tags(owner, pkg.repo)
    latest_prod = _latest_prod_tag(tag_names)
    latest_any = _latest_any_tag(tag_names)
    return manifest, latest_prod, latest_any, None


def _latest_prod_tag(tag_names: list[str]) -> str | None:
    """Newest non-prerelease ``v*`` tag, version-sorted (not list order)."""
    candidates = [t for t in tag_names if t.startswith(_PROD_TAG) and not ver.is_prerelease(t)]
    return _max_version(candidates)


def _latest_any_tag(tag_names: list[str]) -> str | None:
    """Newest ``v*`` tag including prereleases, version-sorted."""
    candidates = [t for t in tag_names if t.startswith(_PROD_TAG)]
    return _max_version(candidates)


def _max_version(tags: list[str]) -> str | None:
    if not tags:
        return None
    best = tags[0]
    for t in tags[1:]:
        if ver.compare(t, best) > 0:
            best = t
    return best


def _reconcile_target(
    owner: str, pkg: Package, tgt: Target, expected: str | None, *, no_network: bool
) -> TargetStatus:
    excluded = tgt.state == "excluded"
    planned = tgt.state == "planned"

    if excluded:
        return TargetStatus(
            registry=tgt.registry,
            name=tgt.name,
            published_version=None,
            status="excluded",
            planned=False,
            downloads=Downloads(),
            evidence=Evidence(),
            error=tgt.reason,
        )

    if tgt.registry == "github-release":
        return _reconcile_github_release(owner, pkg, tgt, expected, no_network=no_network)

    if planned:
        # No release workflow yet → missing, flagged planned, no probe needed.
        return TargetStatus(
            registry=tgt.registry,
            name=tgt.name,
            published_version=None,
            status="missing",
            planned=True,
            downloads=Downloads(),
            evidence=Evidence(),
            error=None,
        )

    collector = _COLLECTORS.get(tgt.registry)
    if collector is None or no_network:
        # Any registry without an independent probe here, or an offline run:
        # report as unknown without a fabricated mismatch.
        return TargetStatus(
            registry=tgt.registry,
            name=tgt.name,
            published_version=None,
            status="unknown",
            planned=False,
            downloads=Downloads(),
            evidence=Evidence(),
            error="no-network" if no_network else None,
        )

    fact = collector(tgt.name)
    published = fact.get("published_version")
    http_status = fact.get("http_status")
    error = fact.get("error")
    broken = bool(fact.get("broken"))
    transient = _is_transient(http_status, error)

    if broken:
        state: str = "broken"
    else:
        state = ver.classify(
            expected,
            published,
            http_status=http_status,
            transient_error=transient,
            excluded=False,
            planned=False,
        )

    return TargetStatus(
        registry=tgt.registry,
        name=tgt.name,
        published_version=published,
        status=state,
        planned=False,
        downloads=Downloads.model_validate(fact.get("downloads") or {}),
        evidence=Evidence.model_validate(fact.get("evidence") or {}),
        error=error,
    )


def _reconcile_github_release(
    owner: str, pkg: Package, tgt: Target, expected: str | None, *, no_network: bool
) -> TargetStatus:
    """Reconcile the GitHub Releases 'registry' from the repo's latest release tag.

    The published version is the ``latest`` (non-draft, non-prerelease) release's
    ``tag_name``; per-asset download counts are summed into ``downloads.total``.
    """
    endpoint = f"https://api.github.com/repos/{owner}/{pkg.repo}/releases/latest"
    evidence = Evidence(version_endpoint=endpoint)
    if no_network:
        return TargetStatus(
            registry=tgt.registry, name=tgt.name, published_version=None,
            status="unknown", planned=False, downloads=Downloads(),
            evidence=evidence, error="no-network",
        )

    fact = github.latest_release_fact(owner, pkg.repo)
    published = fact.get("published_version")
    http_status = fact.get("http_status")
    error = fact.get("error")
    transient = _is_transient(http_status, error)
    state = ver.classify(
        expected, published, http_status=http_status, transient_error=transient,
        excluded=False, planned=False,
    )
    downloads = Downloads(total=fact.get("asset_downloads"), source="github-release-assets")
    return TargetStatus(
        registry=tgt.registry, name=tgt.name, published_version=published,
        status=state, planned=False, downloads=downloads, evidence=evidence, error=error,
    )


def _is_transient(http_status: int | None, error: str | None) -> bool:
    """A timeout / transport failure (status 0 with an error) is transient → unknown."""
    return http_status in (None, 0) and error is not None


def _rollup(targets: list[TargetStatus]) -> str:
    """Worst-cell roll-up; ``excluded`` cells are ignored, all-excluded → green."""
    worst = "green"
    worst_rank = _RANK["green"]
    for ts in targets:
        if ts.status == "excluded":
            continue
        rank = _RANK.get(ts.status, _RANK["green"])
        if rank > worst_rank:
            worst = ts.status
            worst_rank = rank
    return worst


def collect_snapshot(
    targets_path: str | Path,
    *,
    only: set[str] | None = None,
    no_network: bool = False,
    run_id: str | None = None,
) -> Snapshot:
    """Load the inventory and reconcile it into a :class:`Snapshot` in one call."""
    targets = load_targets(targets_path)
    return reconcile(targets, only=only, no_network=no_network, run_id=run_id)
