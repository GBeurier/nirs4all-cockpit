"""GitHub pull-requests collector (admin-only signal).

Counts open PRs per repo (total / drafts / ready) plus a light per-PR list, so
the local admin view can sit it beside the open-issue count. Pure delegation to
:func:`cockpit.collect.github.open_pull_requests` — no API logic of its own.

This is an **admin-only** signal: it is written to the local
``snapshot.admin.json`` (built by ``n4a-cockpit admin collect``), never to the
public ``data/current.json``.
"""

from __future__ import annotations

from typing import Any

from . import github


def collect(owner: str, repo: str) -> dict[str, Any]:
    """Return ``{"open", "draft", "ready", "items": [...]}`` for a repo's open PRs."""
    return github.open_pull_requests(owner, repo)
