"""Sentry collector (admin-only signal): unresolved issues for the studio project.

Reads recent unresolved issues for the ``nirs4all-studio`` Sentry project so the
local admin view can show a runtime-health panel beside the release/CI matrix.

Coordinates (verified): org ``wwwciradfr`` on region ``https://de.sentry.io``,
project ``nirs4all-studio``. All overridable via ``SENTRY_ORG`` /
``SENTRY_PROJECT`` / ``SENTRY_REGION_URL``.

Auth: a Sentry **auth token** in ``SENTRY_AUTH_TOKEN`` (``Authorization: Bearer``)
— distinct from the ingest DSN. Without it the collector degrades gracefully
(``available=False`` + an explanatory ``error``) and never raises, so an admin
collect without Sentry configured still succeeds.

This is **admin-only**: written to the local ``snapshot.admin.json``, never to
the public ``data/current.json``.
"""

from __future__ import annotations

import os
from typing import Any

from ..http import get_json

ORG = "wwwciradfr"
REGION = "https://de.sentry.io"
PROJECT = "nirs4all-studio"


def collect(
    org: str | None = None,
    project: str | None = None,
    region_url: str | None = None,
    token: str | None = None,
    stats_period: str = "14d",
    limit: int = 25,
) -> dict[str, Any]:
    """Collect unresolved Sentry issues for a project.

    Returns ``{"available", "org", "project", "unresolved", "issues": [...],
    "error"}``. ``issues`` items carry ``title/level/count/userCount/permalink/
    lastSeen``. Never raises: any auth/transport failure sets ``available=False``
    and records ``error``.
    """
    org = org or os.environ.get("SENTRY_ORG", ORG)
    project = project or os.environ.get("SENTRY_PROJECT", PROJECT)
    region_url = (region_url or os.environ.get("SENTRY_REGION_URL", REGION)).rstrip("/")
    token = token or os.environ.get("SENTRY_AUTH_TOKEN")

    out: dict[str, Any] = {
        "available": False,
        "org": org,
        "project": project,
        "unresolved": None,
        "issues": [],
        "error": None,
    }
    if not token:
        out["error"] = "no SENTRY_AUTH_TOKEN in env (admin-only; set it to enable Sentry)"
        return out

    url = (
        f"{region_url}/api/0/projects/{org}/{project}/issues/"
        f"?query=is:unresolved&statsPeriod={stats_period}&limit={limit}"
    )
    status, body, error = get_json(url, headers={"Authorization": f"Bearer {token}"})
    if status != 200 or not isinstance(body, list):
        out["error"] = error or f"http {status}"
        return out

    issues = [
        {
            "title": it.get("title"),
            "level": it.get("level"),
            "count": it.get("count"),
            "userCount": it.get("userCount"),
            "permalink": it.get("permalink"),
            "lastSeen": it.get("lastSeen"),
        }
        for it in body
        if isinstance(it, dict)
    ]
    out.update(available=True, unresolved=len(issues), issues=issues)
    return out
