"""GitHub security collector — PHASE 2 STUB (not implemented).

Planned scope: surface Dependabot / code-scanning / secret-scanning alert counts
per repo so the cockpit shows a security column alongside CI and registry state.

Likely endpoints (to confirm in phase 2; all require a token with the right
scope and the feature enabled on the repo):
    * Dependabot   : ``GET /repos/{owner}/{repo}/dependabot/alerts?state=open``
    * code scanning: ``GET /repos/{owner}/{repo}/code-scanning/alerts?state=open``
    * secret scan  : ``GET /repos/{owner}/{repo}/secret-scanning/alerts?state=open``

Auth: ambient ``GITHUB_TOKEN`` via ``Authorization: Bearer``.
"""

from __future__ import annotations

from typing import Any


def collect(owner: str, repo: str) -> dict[str, Any]:
    """Collect open security-alert counts for a repo. Not implemented (phase 2)."""
    raise NotImplementedError("phase 2")
