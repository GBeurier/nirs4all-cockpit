"""crates.io collector.

crates.io rejects requests without a descriptive ``User-Agent`` with a ``403`` —
that header is set globally in :mod:`cockpit.http`, so no special handling is
needed here. A ``404`` means the crate has never been published (missing).

Endpoint:
    * ``https://crates.io/api/v1/crates/{crate}`` →
      ``crate.newest_version`` / ``crate.max_version`` (published version),
      ``crate.downloads`` (total) and ``crate.recent_downloads`` (~90 days).
"""

from __future__ import annotations

from typing import Any

from ..http import get_json

VERSION_URL = "https://crates.io/api/v1/crates/{crate}"


def collect(name: str) -> dict[str, Any]:
    """Collect published version and download totals for a crate."""
    endpoint = VERSION_URL.format(crate=name)

    status, body, error = get_json(endpoint)

    published_version: str | None = None
    total: int | None = None
    recent: int | None = None
    if status == 200 and isinstance(body, dict):
        crate = body.get("crate") or {}
        # max_version is the highest non-yanked release; fall back to newest.
        published_version = crate.get("max_version") or crate.get("newest_version")
        dl = crate.get("downloads")
        total = dl if isinstance(dl, int) else None
        rd = crate.get("recent_downloads")
        recent = rd if isinstance(rd, int) else None

    return {
        "published_version": published_version,
        "downloads": {
            "last_day": None,
            "last_week": None,
            "last_month": recent,
            "total": total,
            "source": "crates.io",
        },
        "evidence": {
            "version_endpoint": endpoint,
            "downloads_endpoint": endpoint,
        },
        "http_status": status,
        "error": error,
    }
