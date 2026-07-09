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

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from . import version as ver
from .collect import (
    code_stats,
    cran,
    crates,
    github,
    local_manifests,
    npm,
    pypi,
    readthedocs,
    runiverse,
    search_console,
    sentry,
    visits,
)
from .collect.base import now_iso
from .model import (
    ActionsStats,
    CodeStats,
    Downloads,
    Evidence,
    Issues,
    Package,
    PackageSource,
    PackageStatus,
    RepoStats,
    SearchConsoleStats,
    SentryStatus,
    Snapshot,
    Target,
    Targets,
    TargetStatus,
    Totals,
    Visits,
    WorkflowHealth,
    WorkflowRef,
)

# registry → collector entry function (each returns the fact dict).
_COLLECTORS = {
    "pypi": pypi.collect,
    "npm": npm.collect,
    "crates": crates.collect,
    "r-universe": runiverse.collect,
    "cran": cran.collect,
    "readthedocs": readthedocs.collect,
}


_CANONICAL_PAGES_URLS = {
    "nirs4all-org": "https://nirs4all.org/",
    "nirs4all-datasets": "https://datasets.nirs4all.org/",
    "nirs4all-formats": "https://formats.nirs4all.org/",
    "nirs4all-io": "https://io.nirs4all.org/",
    "nirs4all-methods": "https://methods.nirs4all.org/",
    "nirs4all-cockpit": "https://cockpit.nirs4all.org/",
    "nirs4all-web": "https://web.nirs4all.org/",
    "nirs4all-quality": "https://quali.nirs4all.org/",
    "nirs4all-repository": "https://repository.nirs4all.org/",
    "nirs4all-papers": "https://papers.nirs4all.org/",
    "nirs4all-benchmarks": "https://benchmarks.nirs4all.org/",
    "nirs4all-providers": "https://gbeurier.github.io/nirs4all-providers/",
    "nirs4all-ui": "https://gbeurier.github.io/nirs4all-ui/",
}


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
    summary = {"green": 0, "stale": 0, "pending": 0, "missing": 0, "broken": 0, "unknown": 0, "excluded": 0}

    for pkg in targets.packages:
        if only and pkg.id not in only:
            continue
        status = _reconcile_package(targets.owner, pkg, no_network=no_network, with_traffic=with_traffic)
        packages.append(status)
        for tgt in status.targets:
            summary[tgt.status] = summary.get(tgt.status, 0) + 1

    stamp = generated_at or now_iso()
    if no_network:
        visits_status, search_console_status, sentry_status = Visits(), SearchConsoleStats(), SentryStatus()
    else:
        visits_status = Visits.model_validate(visits.collect(ref_date=stamp[:10], include_pages=True))
        search_console_status = SearchConsoleStats.model_validate(search_console.collect(ref_date=stamp[:10]))
        sentry_status = SentryStatus.model_validate(sentry.collect(include_issues=False))

    return Snapshot(
        schema_version=1,
        generated_at=stamp,
        generator={
            "repo": f"{targets.owner}/nirs4all-cockpit",
            "workflow": "collect.yml",
            "run_id": run_id,
        },
        packages=packages,
        summary=summary,
        totals=_compute_totals(packages),
        visits=visits_status,
        search_console=search_console_status,
        sentry=sentry_status,
    )


def _compute_totals(packages: list[PackageStatus]) -> Totals:
    """Sum public, ecosystem-wide aggregates across the reconciled packages."""
    totals = Totals(packages=len(packages), repos=len({p.repo for p in packages}))
    for p in packages:
        totals.open_issues += p.issues.open
        if p.repo_stats:
            totals.stars += p.repo_stats.stars or 0
            totals.forks += p.repo_stats.forks or 0
            totals.watchers += p.repo_stats.watchers or 0
        if p.code_stats:
            totals.loc_code += p.code_stats.loc_code
            totals.loc_total += p.code_stats.loc_total
            totals.tests += p.code_stats.tests
            totals.files += p.code_stats.files
        if p.actions_stats and p.actions_stats.total_runs:
            totals.workflow_runs += p.actions_stats.total_runs
        for t in p.targets:
            if t.downloads.last_month:
                totals.downloads_last_month += t.downloads.last_month
    return totals


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
    source_facts = _source_versions(owner, pkg, no_network=no_network)
    manifest = source_facts.get("manifest_version")
    latest_prod = source_facts.get("latest_prod_tag")
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

    if not no_network:
        for workflow in _declared_workflow_refs(pkg):
            if workflow.file in seen_workflows:
                continue
            seen_workflows.add(workflow.file)
            wf = github.workflow_last_run(owner, pkg.repo, workflow.file)
            if wf is not None:
                workflows.append(WorkflowHealth.model_validate(wf))

    issues = Issues()
    repo_stats: RepoStats | None = None
    actions_stats: ActionsStats | None = None
    if not no_network:
        issues_repo = pkg.issues_repo or pkg.repo
        issues = Issues.model_validate(github.open_issues(owner, issues_repo))
        stats_dict = github.repo_stats(owner, pkg.repo, with_traffic=with_traffic)
        raw_open = stats_dict.pop("_open_issues_count", None)
        if pkg.primary_language:
            stats_dict["language"] = pkg.primary_language
        repo_stats = RepoStats.model_validate(stats_dict)
        if raw_open is not None:
            repo_stats.open_prs = max(0, raw_open - issues.open)
        prc = github.pr_counts(owner, pkg.repo)
        repo_stats.closed_prs = prc.get("closed")
        repo_stats.merged_prs = prc.get("merged")
        actions_stats = ActionsStats.model_validate(github.actions_stats(owner, pkg.repo))

    # Code stats are computed from the local checkout; coverage may be completed
    # from CI artifacts only during online collection.
    code = code_stats.scan(pkg.repo, allow_artifact_coverage=not no_network)
    code_model = CodeStats.model_validate(code) if code is not None else None

    rollup = _rollup(target_statuses)

    return PackageStatus(
        id=pkg.id,
        repo=pkg.repo,
        channel=pkg.channel,
        source=PackageSource.model_validate({**source_facts, "expected_prod_version": expected}),
        rollup=rollup,
        flags=flags,
        targets=target_statuses,
        workflows=workflows,
        issues=issues,
        repo_stats=repo_stats,
        code_stats=code_model,
        actions_stats=actions_stats,
    )


def _declared_workflow_refs(pkg: Package) -> Iterable[WorkflowRef]:
    """Return package-level and target-level workflow declarations, in stable order."""
    yield from pkg.workflows
    for tgt in pkg.targets:
        if tgt.workflow is not None:
            yield tgt.workflow


def _source_versions(owner: str, pkg: Package, *, no_network: bool) -> dict[str, Any]:
    """Resolve source-version facts, tag/release dates, latest commit date, and ahead count."""
    empty = {
        "manifest_version": None,
        "latest_prod_tag": None,
        "latest_any_tag": None,
        "commit": None,
        "latest_prod_tag_at": None,
        "latest_release_at": None,
        "latest_version_at": None,
        "latest_version_source": None,
        "last_commit_at": None,
        "commits_ahead_of_latest_prod_tag": None,
    }
    if no_network:
        return empty

    sot = pkg.source_of_truth
    manifest = None
    if sot is not None:
        manifest = local_manifests.read_manifest_version(
            owner=owner,
            repo=pkg.repo,
            strategy=sot.strategy,
            path=sot.path,
            attr=sot.attr,
        )

    tag_names = github.tags(owner, pkg.repo)
    latest_prod = _latest_prod_tag(tag_names, pkg.tag_prefix)
    latest_any = _latest_any_tag(tag_names, pkg.tag_prefix)
    coordination_commit = None
    coordination_tag_at = None
    release_tag_covers_manifest = bool(
        manifest is not None and latest_prod is not None and ver.compare(latest_prod, manifest) >= 0
    )
    if pkg.coordination_tag and pkg.coordination_tag in tag_names and not release_tag_covers_manifest:
        latest_any = pkg.coordination_tag
        coordination_meta = github.tag_fact(owner, pkg.repo, pkg.coordination_tag)
        coordination_tag_at = coordination_meta.get("tagged_at") if coordination_meta else None
        coordination_commit = github.commit_fact(owner, pkg.repo, pkg.coordination_tag)
    latest_release = github.latest_release(owner, pkg.repo)
    latest_release_tag = latest_release.get("tag_name") if latest_release else None
    latest_release_at = latest_release.get("published_at") if latest_release else None
    tag_meta = github.tag_fact(owner, pkg.repo, latest_prod) if latest_prod else None
    latest_prod_tag_at = tag_meta.get("tagged_at") if tag_meta else None
    head = github.default_branch_commit(owner, pkg.repo)
    branch = head.get("branch") if head else None
    latest_version_at = latest_prod_tag_at
    latest_version_source = "tag" if latest_prod_tag_at else None
    if latest_release_tag == latest_prod and latest_release_at:
        latest_version_at = latest_release_at
        latest_version_source = "release"
    source_commit = coordination_commit or head
    if coordination_commit is not None:
        latest_version_at = coordination_tag_at or coordination_commit.get("committed_at")
        latest_version_source = "coordination-tag"
        branch = pkg.coordination_tag
    return {
        "manifest_version": manifest,
        "latest_prod_tag": latest_prod,
        "latest_any_tag": latest_any,
        "commit": source_commit.get("sha") if source_commit else None,
        "latest_prod_tag_at": latest_prod_tag_at,
        "latest_release_at": latest_release_at,
        "latest_version_at": latest_version_at,
        "latest_version_source": latest_version_source,
        "last_commit_at": source_commit.get("committed_at") if source_commit else None,
        "commits_ahead_of_latest_prod_tag": (
            github.commits_ahead(owner, pkg.repo, latest_prod, branch) if latest_prod else None
        ),
    }


def _latest_prod_tag(tag_names: list[str], tag_prefix: str = "v") -> str | None:
    """Newest non-prerelease production tag, version-sorted (not list order)."""
    candidates = [t for t in tag_names if _matches_tag_prefix(t, tag_prefix) and not ver.is_prerelease(t)]
    return _max_version(candidates)


def _latest_any_tag(tag_names: list[str], tag_prefix: str = "v") -> str | None:
    """Newest production-style tag including prereleases, version-sorted."""
    candidates = [t for t in tag_names if _matches_tag_prefix(t, tag_prefix)]
    return _max_version(candidates)


def _matches_tag_prefix(tag: str, tag_prefix: str) -> bool:
    if tag_prefix:
        if not tag.startswith(tag_prefix):
            return False
        tag = tag[len(tag_prefix):]
    elif tag.startswith(("v", "V")):
        return False
    return ver.is_version(tag)


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
            channel=pkg.channel,
            reason=tgt.reason,
            published_version=None,
            status="excluded",
            planned=False,
            downloads=Downloads(),
            evidence=Evidence(),
            error=tgt.reason,
        )

    if tgt.registry == "github-release":
        return _reconcile_github_release(owner, pkg, tgt, expected, no_network=no_network)

    if tgt.registry == "pages":
        return _reconcile_pages(owner, pkg, tgt, no_network=no_network)

    if planned:
        # No release workflow yet → missing, flagged planned, no probe needed.
        return TargetStatus(
            registry=tgt.registry,
            name=tgt.name,
            channel=pkg.channel,
            reason=tgt.reason,
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
            channel=pkg.channel,
            reason=tgt.reason,
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
    elif tgt.registry == "readthedocs":
        state = ver.classify(
            None,
            published,
            http_status=http_status,
            transient_error=transient,
            excluded=False,
            planned=False,
        )
    else:
        state = ver.classify(
            expected,
            published,
            http_status=http_status,
            transient_error=transient,
            excluded=False,
            planned=False,
        )

    # CRAN submissions awaiting manual review: not on CRAN yet (missing) but the R
    # source tarball is already built and attached to a GitHub Release → pending.
    if state == "missing" and tgt.registry == "cran" and not no_network:
        if github.release_asset_matches(owner, pkg.repo, rf"^{re.escape(tgt.name)}_.*\.tar\.gz$"):
            state = "pending"

    return TargetStatus(
        registry=tgt.registry,
        name=tgt.name,
        channel=pkg.channel,
        reason=tgt.reason,
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
            channel=pkg.channel, reason=tgt.reason,
            status="unknown", planned=False, downloads=Downloads(),
            evidence=evidence, error="no-network",
        )

    fact = github.latest_release_fact(owner, pkg.repo)
    raw = fact.get("published_version")
    # Normalise the tag (e.g. "v0.5.3" -> "0.5.3") so it matches the other
    # registries' clean versions and the UI doesn't render a double "v".
    published = ver.normalize(raw) if raw else None
    http_status = fact.get("http_status")
    error = fact.get("error")
    transient = _is_transient(http_status, error)
    state = ver.classify(
        expected, published, http_status=http_status, transient_error=transient,
        excluded=False, planned=False,
    )
    asset_downloads = fact.get("asset_downloads")
    downloads = Downloads(source="github-release-assets")
    if isinstance(asset_downloads, int):
        downloads.total = asset_downloads
        downloads.windows["total"] = asset_downloads

    return TargetStatus(
        registry=tgt.registry, name=tgt.name, published_version=published,
        channel=pkg.channel, reason=tgt.reason,
        status=state, planned=False, downloads=downloads, evidence=evidence, error=error,
    )


def _reconcile_pages(owner: str, pkg: Package, tgt: Target, *, no_network: bool) -> TargetStatus:
    """Reconcile a GitHub Pages 'gh.io' target: is the site published & healthy?"""
    endpoint = f"https://api.github.com/repos/{owner}/{pkg.repo}/pages"
    if no_network:
        return TargetStatus(
            registry="pages", name=tgt.name, published_version=None, status="unknown",
            channel=pkg.channel, reason=tgt.reason,
            planned=False, downloads=Downloads(), evidence=Evidence(version_endpoint=endpoint), error="no-network",
        )
    info = github.pages_status(owner, pkg.repo)
    if not info["available"]:
        state = "missing"
    elif info["build_status"] == "errored":
        state = "broken"
    else:
        # built, null (Actions deploys), or building — a rebuild keeps serving the
        # previous deploy, so the site is live; don't flap it to "unknown".
        state = "green"
    return TargetStatus(
        registry="pages", name=tgt.name, published_version=None, status=state, planned=False,
        channel=pkg.channel, reason=tgt.reason,
        downloads=Downloads(), evidence=Evidence(version_endpoint=_pages_url(pkg.repo, info)), error=None,
    )


def _pages_url(repo: str, info: dict[str, Any]) -> str | None:
    """Return the public Pages URL used by the dashboard for this repo."""
    return _CANONICAL_PAGES_URLS.get(repo) or info.get("html_url")


def _is_transient(http_status: int | None, error: str | None) -> bool:
    """A timeout / transport failure (status 0 with an error) is transient → unknown."""
    return http_status in (None, 0) and error is not None


def _rollup(targets: list[TargetStatus]) -> str:
    """Package roll-up. ``excluded`` cells are ignored, all-excluded → green.

    The package roll-up is the worst tracked target, matching the dashboard rank.
    This keeps blockers such as a missing PyPI project visible even when the same
    package is already green on GitHub Pages or another registry.
    """
    states = {ts.status for ts in targets if ts.status != "excluded"}
    for s in ("broken", "missing", "stale", "pending", "unknown", "green"):
        if s in states:
            return s
    return "green"


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
