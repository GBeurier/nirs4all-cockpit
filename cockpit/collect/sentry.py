"""Sentry collector: unresolved + recently-resolved issues for the studio project.

Reads the ``nirs4all-studio`` Sentry project so the cockpit can show a runtime-
health panel: how many issues are unresolved vs resolved, how many events and
users they hit, and the issues themselves (current unresolved + recently closed).

Coordinates (verified): org ``wwwciradfr`` on region ``https://de.sentry.io``,
project ``nirs4all-studio``. All overridable via ``SENTRY_ORG`` / ``SENTRY_PROJECT``
/ ``SENTRY_REGION_URL``.

Auth: a Sentry **auth token** in ``SENTRY_AUTH_TOKEN`` (``Authorization: Bearer``)
— distinct from the ingest DSN. Without it the collector degrades gracefully
(``available=False`` + an explanatory ``error``) and never raises.

Only aggregate counts + issue metadata enter the snapshot — never the token.
"""

from __future__ import annotations

import os
from typing import Any

from ..http import get_json

ORG = "wwwciradfr"
REGION = "https://de.sentry.io"
PROJECT = "nirs4all-studio"


def _to_int(x: Any) -> int | None:
    """Coerce Sentry's stringy counts to ``int`` (``None`` if unparseable)."""
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _issue(it: dict) -> dict:
    """Project one Sentry issue down to the public-safe fields the panel shows."""
    return {
        "title": it.get("title"),
        "culprit": it.get("culprit"),
        "level": it.get("level"),
        "count": _to_int(it.get("count")),
        "userCount": _to_int(it.get("userCount")),
        "firstSeen": it.get("firstSeen"),
        "lastSeen": it.get("lastSeen"),
        "permalink": it.get("permalink"),
    }


def collect(
    org: str | None = None,
    project: str | None = None,
    region_url: str | None = None,
    token: str | None = None,
    stats_period: str = "14d",
    limit: int = 25,
) -> dict[str, Any]:
    """Collect unresolved + recently-resolved Sentry issues for a project.

    Returns ``{"available", "org", "project", "unresolved", "resolved", "events",
    "users_affected", "issues": [...], "resolved_issues": [...], "error"}``. Each
    issue carries ``title/culprit/level/count/userCount/firstSeen/lastSeen/
    permalink``. Never raises: any auth/transport failure sets ``available=False``.
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
        "resolved": None,
        "events": None,
        "users_affected": None,
        "issues": [],
        "resolved_issues": [],
        "error": None,
    }
    if not token:
        out["error"] = "no SENTRY_AUTH_TOKEN in env (set it to enable Sentry)"
        return out

    headers = {"Authorization": f"Bearer {token}"}
    base = f"{region_url}/api/0/projects/{org}/{project}/issues/"

    def _fetch(query: str, lim: int) -> tuple[list | None, str | None]:
        url = f"{base}?query={query}&statsPeriod={stats_period}&limit={lim}"
        status, body, error = get_json(url, headers=headers)
        if status != 200 or not isinstance(body, list):
            return None, (error or f"http {status}")
        return body, None

    raw, err = _fetch("is:unresolved", limit)
    if raw is None:
        out["error"] = err
        return out
    issues = [_issue(it) for it in raw if isinstance(it, dict)]

    # Recently closed issues — for the "resolved" tally and the closed list. A
    # failure here is non-fatal: the unresolved view still renders.
    resolved_raw, _ = _fetch("is:resolved", 100)
    resolved_issues = [_issue(it) for it in (resolved_raw or []) if isinstance(it, dict)]

    out.update(
        available=True,
        unresolved=len(issues),
        resolved=len(resolved_issues) if resolved_raw is not None else None,
        events=sum(i["count"] or 0 for i in issues),
        users_affected=sum(i["userCount"] or 0 for i in issues),
        issues=issues,
        resolved_issues=resolved_issues[:12],
    )
    return out
