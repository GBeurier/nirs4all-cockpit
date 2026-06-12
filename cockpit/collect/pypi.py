"""PyPI collector.

Version comes from the JSON metadata endpoint; PyPI itself exposes no real
download counts, so those are fetched from pypistats (a separate, rate-limited
service) and degrade to ``unknown`` rather than blocking the version verdict.

Endpoints:
    * version:   ``https://pypi.org/pypi/{pkg}/json`` → ``info.version``;
      ``404`` means the project does not exist (missing).
    * downloads: ``https://pypistats.org/api/packages/{pkg}/recent`` → recent
      day/week/month; ~180 days of history, frequently ``429`` → ``unknown``.
"""

from __future__ import annotations

from typing import Any

from ..http import get_json

VERSION_URL = "https://pypi.org/pypi/{pkg}/json"
DOWNLOADS_URL = "https://pypistats.org/api/packages/{pkg}/recent"


def collect(name: str) -> dict[str, Any]:
    """Collect published version and recent downloads for a PyPI project."""
    version_endpoint = VERSION_URL.format(pkg=name)
    downloads_endpoint = DOWNLOADS_URL.format(pkg=name.lower())

    status, body, error = get_json(version_endpoint)
    published_version: str | None = None
    if status == 200 and isinstance(body, dict):
        info = body.get("info") or {}
        published_version = info.get("version")

    downloads = _downloads(downloads_endpoint)

    return {
        "published_version": published_version,
        "downloads": downloads,
        "evidence": {
            "version_endpoint": version_endpoint,
            "downloads_endpoint": downloads_endpoint,
        },
        "http_status": status,
        "error": error,
    }


def _downloads(endpoint: str) -> dict[str, Any]:
    """Fetch pypistats recent downloads; a 429/timeout leaves all counts ``None``."""
    out: dict[str, Any] = {
        "last_day": None,
        "last_week": None,
        "last_month": None,
        "total": None,
        "source": "pypistats",
    }
    status, body, _error = get_json(endpoint)
    if status == 200 and isinstance(body, dict):
        data = body.get("data") or {}
        out["last_day"] = data.get("last_day")
        out["last_week"] = data.get("last_week")
        out["last_month"] = data.get("last_month")
    # 429 / timeout / 404 → counts stay None ("unknown"); never reddens version.
    return out
