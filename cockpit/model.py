"""Pydantic v2 contracts for nirs4all-cockpit.

Two families of models live here, both with a frozen schema:

* The **snapshot** family (``Snapshot`` and friends) is the shape the collector
  emits to ``data/current.json``: per-package rollups, per-target registry
  status, download counts, CI workflow health, and issue counts.
* The **targets** family (``Targets`` and friends) is the declarative inventory
  parsed from ``ops/targets.yaml``: package × registry × exact name × release
  workflow × source-of-truth version strategy.

The two families never overlap: the inventory describes *what should exist*; the
snapshot describes *what was observed*. Reconciliation between them lives in
``cockpit.reconcile`` and ``cockpit.version`` — never here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

State = Literal["green", "stale", "pending", "missing", "broken", "unknown", "excluded"]
"""Registry status of a single target. ``pending`` = built & submitted but not yet
live (e.g. the R source tarball is attached to a GitHub Release but the package
is not on CRAN yet — awaiting manual review); it is distinct from ``stale`` (an
*older* version IS published) and from ``missing`` (nothing built/submitted).
``source_ahead`` is a package flag, not a status; ``planned`` is carried
separately on ``TargetStatus``."""


# --------------------------------------------------------------------------- #
# Snapshot family (data/current.json)
# --------------------------------------------------------------------------- #


class Downloads(BaseModel):
    """Download counts for a target, as reported by its registry's stats API.

    All counts are ``None`` when the registry exposes no stats or the stats
    fetch was inconclusive (429/timeout); ``0`` is a real zero, not absence.
    """

    last_day: int | None = None
    last_week: int | None = None
    last_month: int | None = None
    total: int | None = None
    source: str | None = None
    by_version: list[dict] = Field(default_factory=list)
    # Window → count, for the UI period selector. Keys: "7d"/"30d"/"90d"/"total".
    # Each registry fills only the windows its API reports (None elsewhere).
    windows: dict = Field(default_factory=dict)


class Evidence(BaseModel):
    """Endpoints consulted to reach a target's verdict (for auditability)."""

    version_endpoint: str | None = None
    downloads_endpoint: str | None = None


class TargetStatus(BaseModel):
    """Observed state of one published target (one registry × one exact name)."""

    registry: str
    name: str
    published_version: str | None = None
    status: State
    planned: bool = False
    downloads: Downloads = Field(default_factory=Downloads)
    evidence: Evidence = Field(default_factory=Evidence)
    error: str | None = None


class WorkflowHealth(BaseModel):
    """Last observed run of a release workflow, kept separate from registry state.

    A failed release run sets ``conclusion="failure"`` but does not by itself
    turn a target red: the target stays ``green`` if the expected version is
    published.
    """

    file: str
    conclusion: str | None = None
    created_at: str | None = None
    head_sha: str | None = None


class PackageSource(BaseModel):
    """Resolved version facts for a package (the four-version reconcile model).

    ``manifest_version`` is the source-of-truth in the repo; ``latest_prod_tag``
    is the newest ``v*.*.*`` non-prerelease tag; ``latest_any_tag`` includes
    prereleases; ``expected_prod_version`` is derived (prod tag, else manifest).
    """

    manifest_version: str | None = None
    latest_prod_tag: str | None = None
    latest_any_tag: str | None = None
    expected_prod_version: str | None = None
    commit: str | None = None


class Issues(BaseModel):
    """Open-issue counts for a package's tracker."""

    open: int = 0
    bugs: int = 0


class RepoStats(BaseModel):
    """GitHub repository stats for a package's repo.

    The public block (stars/forks/watchers/size/license/pushed_at) needs no auth.
    The ``traffic_*`` block (14-day views/clones) requires a **push-scoped** token
    and is therefore only populated on a local maintainer run, not in the public
    Pages cron; it stays ``None`` (``traffic_available=False``) otherwise.
    """

    stars: int | None = None
    forks: int | None = None
    watchers: int | None = None
    open_prs: int | None = None
    closed_prs: int | None = None
    merged_prs: int | None = None
    size_kb: int | None = None
    license: str | None = None
    pushed_at: str | None = None
    default_branch: str | None = None
    traffic_views_14d: int | None = None
    traffic_views_uniques: int | None = None
    traffic_clones_14d: int | None = None
    traffic_clones_uniques: int | None = None
    traffic_available: bool = False


class CodeStats(BaseModel):
    """Source-code statistics for a repo (computed from the local checkout).

    ``loc_code`` is *effective* lines of code (non-blank, non-comment); comments
    and blanks are tallied separately. ``tests`` and ``coverage_pct`` are
    best-effort heuristics. ``source`` records how it was obtained (``local-scan``)
    or is ``None`` when no local checkout was available.
    """

    loc_code: int = 0
    loc_comment: int = 0
    loc_blank: int = 0
    loc_total: int = 0
    files: int = 0
    tests: int = 0
    by_language: dict = Field(default_factory=dict)
    coverage_pct: float | None = None
    source: str | None = None


class ActionsStats(BaseModel):
    """GitHub Actions activity for a repo (over the most recent runs)."""

    workflows: int | None = None
    total_runs: int | None = None
    recent_total: int = 0
    recent_success: int = 0
    recent_failure: int = 0
    success_rate: float | None = None
    last_conclusion: str | None = None
    last_created_at: str | None = None


class Totals(BaseModel):
    """Ecosystem-wide aggregates summed across all packages in the snapshot."""

    packages: int = 0
    repos: int = 0
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    loc_code: int = 0
    loc_total: int = 0
    tests: int = 0
    files: int = 0
    workflow_runs: int = 0
    downloads_last_month: int = 0


class PackageStatus(BaseModel):
    """Reconciled snapshot for one package: source, rollup, targets, CI, issues, stats."""

    id: str
    repo: str
    source: PackageSource
    rollup: State
    flags: list[str] = Field(default_factory=list)
    targets: list[TargetStatus]
    workflows: list[WorkflowHealth] = Field(default_factory=list)
    issues: Issues = Field(default_factory=Issues)
    repo_stats: RepoStats | None = None
    code_stats: CodeStats | None = None
    actions_stats: ActionsStats | None = None


class VisitPage(BaseModel):
    """One page's all-time pageview count (a GoatCounter path)."""

    path: str
    title: str | None = None
    count: int = 0


class Visits(BaseModel):
    """GoatCounter Pages-site visits: aggregate windows + per-page breakdown.

    Public, count-only signal (the API token never enters the snapshot).
    ``windows`` holds ecosystem-wide totals (7d/30d/365d/all-time); ``pages``
    is the per-page breakdown, highest-traffic first.
    """

    available: bool = False
    site: str | None = None
    windows: dict = Field(default_factory=dict)
    pages: list[VisitPage] = Field(default_factory=list)
    error: str | None = None


class SentryStatus(BaseModel):
    """Unresolved Sentry issues for the studio project.

    The public snapshot carries the count only (``unresolved``); the per-issue
    ``issues`` list is populated solely in the local admin snapshot, never on the
    public site (titles can leak context).
    """

    available: bool = False
    org: str | None = None
    project: str | None = None
    unresolved: int | None = None
    issues: list[dict] = Field(default_factory=list)
    error: str | None = None


class Snapshot(BaseModel):
    """Top-level document written to ``data/current.json``."""

    schema_version: int = 1
    generated_at: str
    generator: dict
    packages: list[PackageStatus]
    summary: dict[str, int]
    totals: Totals = Field(default_factory=Totals)
    visits: Visits = Field(default_factory=Visits)
    sentry: SentryStatus = Field(default_factory=SentryStatus)


# --------------------------------------------------------------------------- #
# Admin snapshot family (data/admin/snapshot.admin.json — LOCAL ONLY)
# --------------------------------------------------------------------------- #
# These carry push-scoped / semi-private signals (traffic, PRs, security alerts,
# Sentry). They are written to a gitignored local file by `n4a-cockpit admin
# collect` and never enter the public snapshot or GitHub Pages.


class Traffic(BaseModel):
    """14-day GitHub traffic for a repo (push-scoped; local admin only)."""

    views_14d: int | None = None
    views_uniques: int | None = None
    clones_14d: int | None = None
    clones_uniques: int | None = None
    available: bool = False


class PullRequests(BaseModel):
    """Open pull-request counts for a repo, with a light per-PR list."""

    open: int = 0
    draft: int = 0
    ready: int = 0
    items: list[dict] = Field(default_factory=list)


class Security(BaseModel):
    """Open security-alert counts for a repo (Dependabot + code scanning)."""

    available: bool = False
    dependabot_open: int | None = None
    dependabot_by_severity: dict = Field(default_factory=dict)
    code_scanning_open: int | None = None
    error: str | None = None


class RepoAdmin(BaseModel):
    """Admin-only signals for one repo: traffic, open PRs, security alerts."""

    repo: str
    traffic: Traffic = Field(default_factory=Traffic)
    pulls: PullRequests = Field(default_factory=PullRequests)
    security: Security = Field(default_factory=Security)


class AdminSnapshot(BaseModel):
    """Top-level local-only document written to ``data/admin/snapshot.admin.json``."""

    schema_version: int = 1
    generated_at: str
    sentry: SentryStatus = Field(default_factory=SentryStatus)
    repos: list[RepoAdmin] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Targets family (ops/targets.yaml)
# --------------------------------------------------------------------------- #


class SourceOfTruth(BaseModel):
    """How to read ``manifest_version`` for a package from its repo."""

    strategy: str
    path: str
    attr: str | None = None


class WorkflowRef(BaseModel):
    """Reference to a release workflow, with its trigger and danger classing.

    ``danger`` reflects what a ``workflow_dispatch`` does: ``safe`` (no publish),
    ``publish`` (publishes only with the right input/tag), or ``dangerous`` (the
    dispatch publishes outright). ``publishes_on_dispatch`` makes that explicit.
    ``inputs`` declares each accepted dispatch input (name/type/default/...); the
    admin layer refuses any input not declared here.
    """

    file: str
    trigger: Literal["tag", "workflow_dispatch", "release_published"]
    danger: Literal["safe", "publish", "dangerous"] = "publish"
    publishes_on_dispatch: bool = False
    inputs: list[dict] = Field(default_factory=list)


class Target(BaseModel):
    """One inventory target: an exact package name on a given registry."""

    registry: str
    name: str
    state: Literal["tracked", "excluded", "planned"] = "tracked"
    reason: str | None = None
    workflow: WorkflowRef | None = None


class Package(BaseModel):
    """One ecosystem package: its repo, channel, source-of-truth, and targets."""

    id: str
    repo: str
    channel: str = "production"
    issues_repo: str | None = None
    source_of_truth: SourceOfTruth | None = None
    targets: list[Target]
    version_aliases: dict = Field(default_factory=dict)


class Targets(BaseModel):
    """Top-level inventory document parsed from ``ops/targets.yaml``."""

    schema_version: int = 1
    owner: str
    packages: list[Package]
