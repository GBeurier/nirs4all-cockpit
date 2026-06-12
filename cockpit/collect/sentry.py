"""Sentry collector — PHASE 2 STUB (not implemented).

Planned scope: pull recent issue/error counts for the ``nirs4all-studio``
project so the cockpit can surface a runtime-health column next to the
release/CI matrix.

Coordinates (documented now so phase 2 needs no rediscovery):
    * org region : ``https://de.sentry.io``
    * org slug   : ``wwwciradfr``
    * project    : ``nirs4all-studio``

Likely endpoints (to confirm in phase 2):
    * issues : ``GET https://de.sentry.io/api/0/projects/wwwciradfr/nirs4all-studio/issues/``
      (``query=is:unresolved``, ``statsPeriod=14d``)
    * stats  : ``GET https://de.sentry.io/api/0/projects/wwwciradfr/nirs4all-studio/stats_v2/``

Auth: a Sentry auth token (``SENTRY_AUTH_TOKEN``) via ``Authorization: Bearer``.
"""

from __future__ import annotations

from typing import Any

ORG = "wwwciradfr"
REGION = "https://de.sentry.io"
PROJECT = "nirs4all-studio"


def collect(project: str = PROJECT) -> dict[str, Any]:
    """Collect Sentry health for a project. Not implemented (phase 2)."""
    raise NotImplementedError("phase 2")
