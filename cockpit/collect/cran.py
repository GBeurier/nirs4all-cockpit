"""CRAN collector (crandb + cranlogs).

Until a package is accepted on CRAN its crandb entry ``404``s — that is a true
``missing``. cranlogs is separate and answers HTTP ``200`` with ``downloads: 0``
for an unknown/empty package; a zero count is a *real zero*, never reinterpreted
as the package being missing.

Endpoints:
    * version:   ``https://crandb.r-pkg.org/{pkg}`` → ``Version``;
      ``404`` = not (yet) on CRAN.
    * downloads: ``https://cranlogs.r-pkg.org/downloads/total/last-month/{pkg}``
      → array with ``downloads`` (an int, ``0`` for unknown packages).
"""

from __future__ import annotations

from typing import Any

from ..http import get_json

VERSION_URL = "https://crandb.r-pkg.org/{pkg}"
DOWNLOADS_URL = "https://cranlogs.r-pkg.org/downloads/total/last-month/{pkg}"


def collect(name: str) -> dict[str, Any]:
    """Collect published version and last-month downloads for a CRAN package."""
    version_endpoint = VERSION_URL.format(pkg=name)
    downloads_endpoint = DOWNLOADS_URL.format(pkg=name)

    status, body, error = get_json(version_endpoint)
    published_version: str | None = None
    if status == 200 and isinstance(body, dict):
        published_version = body.get("Version")

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
    """Fetch cranlogs last-month total; ``0`` in a 200 body is a real zero."""
    out: dict[str, Any] = {
        "last_day": None,
        "last_week": None,
        "last_month": None,
        "total": None,
        "source": "cranlogs",
    }
    status, body, _error = get_json(endpoint)
    if status == 200 and isinstance(body, list) and body:
        count = body[0].get("downloads") if isinstance(body[0], dict) else None
        if isinstance(count, int):
            out["last_month"] = count  # 0 is a real zero, not "unknown"
    out["windows"] = {"7d": None, "30d": out["last_month"], "90d": None, "total": None}
    return out
