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

State = Literal["green", "stale", "missing", "broken", "unknown", "excluded"]
"""Registry status of a single target. ``source_ahead`` is a package flag, not a
status; ``planned`` is carried separately on ``TargetStatus`` (a planned target
reconciles as ``missing`` but is flagged and given no admin button)."""


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
    size_kb: int | None = None
    license: str | None = None
    pushed_at: str | None = None
    default_branch: str | None = None
    traffic_views_14d: int | None = None
    traffic_views_uniques: int | None = None
    traffic_clones_14d: int | None = None
    traffic_clones_uniques: int | None = None
    traffic_available: bool = False


class PackageStatus(BaseModel):
    """Reconciled snapshot for one package: source, rollup, targets, CI, issues, repo stats."""

    id: str
    repo: str
    source: PackageSource
    rollup: State
    flags: list[str] = Field(default_factory=list)
    targets: list[TargetStatus]
    workflows: list[WorkflowHealth] = Field(default_factory=list)
    issues: Issues = Field(default_factory=Issues)
    repo_stats: RepoStats | None = None


class Snapshot(BaseModel):
    """Top-level document written to ``data/current.json``."""

    schema_version: int = 1
    generated_at: str
    generator: dict
    packages: list[PackageStatus]
    summary: dict[str, int]


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
    source_of_truth: SourceOfTruth
    targets: list[Target]
    version_aliases: dict = Field(default_factory=dict)


class Targets(BaseModel):
    """Top-level inventory document parsed from ``ops/targets.yaml``."""

    schema_version: int = 1
    owner: str
    packages: list[Package]
