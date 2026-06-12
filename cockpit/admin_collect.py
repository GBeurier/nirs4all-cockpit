"""Build the LOCAL-ONLY admin snapshot (traffic, PRs, security, Sentry).

These signals are push-scoped or semi-private, so they live in a separate
``data/admin/snapshot.admin.json`` that is gitignored and never deployed to the
public Pages site. The public ``data/current.json`` (built by
:mod:`cockpit.reconcile`) stays free of them.

Like the rest of the cockpit, this only *aggregates* read-only API signals — it
never mutates a repo or reimplements any logic.
"""

from __future__ import annotations

from collections.abc import Iterable

from .collect import github, github_prs, github_security, sentry
from .collect.base import now_iso
from .model import (
    AdminSnapshot,
    PullRequests,
    RepoAdmin,
    Security,
    SentryStatus,
    Targets,
    Traffic,
)


def build_admin_snapshot(
    targets: Targets,
    *,
    only: Iterable[str] | None = None,
    generated_at: str | None = None,
) -> AdminSnapshot:
    """Collect admin-only signals for each repo in the inventory.

    Args:
        targets: Parsed inventory (:class:`~cockpit.model.Targets`).
        only: Optional iterable of package ids to limit the collect to.
        generated_at: UTC ISO-8601 stamp (the CLI injects it; falls back to now).

    Returns:
        A populated :class:`~cockpit.model.AdminSnapshot`.
    """
    only_set = set(only) if only is not None else None
    owner = targets.owner

    repos: list[RepoAdmin] = []
    seen: set[str] = set()
    for pkg in targets.packages:
        if only_set is not None and pkg.id not in only_set:
            continue
        if pkg.repo in seen:
            continue
        seen.add(pkg.repo)

        stats = github.repo_stats(owner, pkg.repo, with_traffic=True)
        traffic = Traffic(
            views_14d=stats["traffic_views_14d"],
            views_uniques=stats["traffic_views_uniques"],
            clones_14d=stats["traffic_clones_14d"],
            clones_uniques=stats["traffic_clones_uniques"],
            available=stats["traffic_available"],
        )
        pulls = PullRequests.model_validate(github_prs.collect(owner, pkg.repo))
        security = Security.model_validate(github_security.collect(owner, pkg.repo))
        repos.append(
            RepoAdmin(repo=f"{owner}/{pkg.repo}", traffic=traffic, pulls=pulls, security=security)
        )

    stamp = generated_at or now_iso()
    sentry_status = SentryStatus.model_validate(sentry.collect())

    return AdminSnapshot(
        schema_version=1,
        generated_at=stamp,
        sentry=sentry_status,
        repos=repos,
    )
