"""Sentry collector: aggregate runtime-error counters for the studio project.

Reads the ``nirs4all-studio`` Sentry project so the cockpit can show a runtime-
health panel: how many issues are unresolved vs resolved, how many events and
users they hit, for issues with searchable events in the requested period.

Use the organization issue search, scoped to the project, just like Sentry's
issue stream. The deprecated project endpoint can return orphaned groups with
no retrievable events, and its ``statsPeriod`` only selects graph statistics;
it does not filter the issue list by event activity.

Coordinates (verified): org ``wwwciradfr`` on region ``https://de.sentry.io``,
project ``nirs4all-studio``. All overridable via ``SENTRY_ORG`` / ``SENTRY_PROJECT``
/ ``SENTRY_REGION_URL``.

Auth: a Sentry **auth token** in ``SENTRY_AUTH_TOKEN`` (``Authorization: Bearer``)
— distinct from the ingest DSN. Without it the collector degrades gracefully
(``available=False`` + an explanatory ``error``) and never raises.

Only aggregate counts enter the public snapshot — never the token, issue titles,
culprits, permalinks, or user-identifying details.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote, urlencode

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
    """Project one Sentry issue down to local-only fields when explicitly requested."""
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
    include_issues: bool = False,
) -> dict[str, Any]:
    """Collect aggregate Sentry issue counters for a project.

    Returns ``{"available", "org", "project", "unresolved", "resolved", "events",
    "users_affected", "issues": [], "resolved_issues": [], "error"}``. Detailed
    issue lists are returned only when ``include_issues=True`` for local use.
    Never raises: any auth/transport failure sets ``available=False``.
    """
    org = org or os.environ.get("SENTRY_ORG", ORG)
    project = project or os.environ.get("SENTRY_PROJECT", PROJECT)
    region_url = (region_url or os.environ.get("SENTRY_REGION_URL", REGION)).rstrip("/")
    token = token or os.environ.get("SENTRY_AUTH_TOKEN")

    out: dict[str, Any] = {
        "available": False,
        "org": org,
        "project": project,
        "stats_period": stats_period,
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
    base = f"{region_url}/api/0/organizations/{quote(org, safe='')}/issues/"

    def _fetch(query: str, lim: int) -> tuple[list | None, str | None]:
        """Follow Sentry cursors; never publish a truncated issue count."""
        params = {"project": project, "query": query, "statsPeriod": stats_period, "limit": max(1, min(lim, 100))}
        collected = []
        cursors: set[str] = set()
        for _ in range(100):
            response_headers: dict[str, str] = {}
            status, body, error = get_json(
                f"{base}?{urlencode(params)}", headers=headers, response_headers=response_headers,
            )
            if status != 200 or not isinstance(body, list):
                return None, (error or f"http {status}")
            collected.extend(it for it in body if isinstance(it, dict))
            next_link = next(
                (link for link in response_headers.get("link", "").split(",") if 'rel="next"' in link), "",
            )
            if 'results="true"' not in next_link:
                if not next_link and len(body) >= params["limit"]:
                    return None, "Sentry pagination metadata missing; issue count is unknown"
                return collected, None
            match = re.search(r'cursor="([^"]+)"', next_link)
            if match is None or match[1] in cursors:
                return None, "invalid or repeated Sentry pagination cursor"
            cursors.add(match[1])
            params["cursor"] = match[1]
        return None, "Sentry pagination limit exceeded; issue count is unknown"

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
        events=sum(i["count"] for i in issues) if all(i["count"] is not None for i in issues) else None,
        users_affected=0 if not issues else _unique_users(raw, region_url, org, stats_period, headers),
    )
    if include_issues:
        out.update(issues=issues, resolved_issues=resolved_issues[:12])
    return out


def _unique_users(issues: list[dict], region: str, org: str, period: str, headers: dict[str, str]) -> int | None:
    """Count distinct users across the selected groups, not user/group pairs.

    Organization issue search's top-level ``count`` and ``userCount`` are scoped
    to statsPeriod; ``lifetime`` is separate. Summing event counts is valid, but
    a user shared by several groups must be deduplicated by the events backend.
    """
    ids = [str(it.get("id", "")) for it in issues]
    project_ids = {
        str(it["project"].get("id", "")) if isinstance(it.get("project"), dict) else ""
        for it in issues
    }
    if not all(value.isdigit() for value in ids) or len(project_ids) != 1:
        return None
    project_id = project_ids.pop()
    if not project_id.isdigit():
        return None
    params = urlencode({
        "project": project_id, "statsPeriod": period,
        "query": f"issue.id:[{','.join(ids)}]", "field": "count_unique(user)",
    })
    url = f"{region}/api/0/organizations/{quote(org, safe='')}/events/?{params}"
    if len(url) > 8000:
        return None  # Do not invent a unique-user count by adding batch counts.
    status, body, _ = get_json(url, headers=headers)
    rows = body.get("data") if isinstance(body, dict) else None
    if status == 200 and isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return _to_int(rows[0].get("count_unique(user)"))
    return None
