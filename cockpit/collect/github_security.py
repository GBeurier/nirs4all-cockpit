"""GitHub security collector (admin-only signal).

Surfaces open Dependabot and code-scanning alert counts per repo. Both require a
token with the right scope and the feature enabled; when unavailable the fields
degrade to ``None``/``available=False`` rather than erroring. Pure delegation to
:mod:`cockpit.collect.github`.

This is an **admin-only** signal: written to the local ``snapshot.admin.json``
(``n4a-cockpit admin collect``), never to the public ``data/current.json``.
"""

from __future__ import annotations

from typing import Any

from . import github


def collect(owner: str, repo: str) -> dict[str, Any]:
    """Return open Dependabot + code-scanning alert counts for a repo."""
    dependabot = github.dependabot_alerts(owner, repo)
    code_scanning = github.code_scanning_alerts(owner, repo)
    return {
        "available": bool(dependabot["available"] or code_scanning["available"]),
        "dependabot_open": dependabot["open"],
        "dependabot_by_severity": dependabot["by_severity"],
        "code_scanning_open": code_scanning["open"],
        "error": dependabot["error"] if not dependabot["available"] else code_scanning["error"],
    }
