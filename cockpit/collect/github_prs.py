"""GitHub pull-requests collector — PHASE 2 STUB (not implemented).

Planned scope: count open PRs per repo (and how many are drafts / awaiting
review) to sit beside the open-issue count in the package roll-up.

Likely endpoint (to confirm in phase 2):
    * ``GET https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=100``
      (paginate; the issues endpoint already excludes PRs, so they are counted
      here separately rather than mixed into :func:`github.open_issues`).

Auth: ambient ``GITHUB_TOKEN`` via ``Authorization: Bearer``, same as
:mod:`cockpit.collect.github`.
"""

from __future__ import annotations

from typing import Any


def collect(owner: str, repo: str) -> dict[str, Any]:
    """Collect open-PR counts for a repo. Not implemented (phase 2)."""
    raise NotImplementedError("phase 2")
