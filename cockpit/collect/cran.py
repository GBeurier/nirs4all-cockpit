"""CRAN collector (crandb + canonical CRAN page + cranlogs).

Until a package is accepted on CRAN its crandb entry ``404``s — that is a true
``missing``. cranlogs is separate and answers HTTP ``200`` with ``downloads: 0``
for an unknown/empty package; a zero count is a *real zero*, never reinterpreted
as the package being missing.

The crandb record is intentionally not enough to identify a removal: it keeps
the last published metadata after CRAN archives a package.  The canonical CRAN
HTML page is therefore probed as well and is the authoritative archive signal.

Endpoints:
    * version:   ``https://crandb.r-pkg.org/{pkg}`` → ``Version``;
      ``404`` = not (yet) on CRAN.
    * archive:   ``https://CRAN.R-project.org/package={pkg}`` → canonical
      removal notice and archive date, when applicable.
    * downloads: ``https://cranlogs.r-pkg.org/downloads/total/last-month/{pkg}``
      → array with ``downloads`` (an int, ``0`` for unknown packages).
"""

from __future__ import annotations

import re
from typing import Any

from ..http import get_json, get_text

VERSION_URL = "https://crandb.r-pkg.org/{pkg}"
ARCHIVE_URL = "https://CRAN.R-project.org/package={pkg}"
DOWNLOADS_URL = "https://cranlogs.r-pkg.org/downloads/total/last-month/{pkg}"

_REMOVED_RE = re.compile(r"Package\s+.{0,200}?\s+was removed from the CRAN repository\.", re.IGNORECASE | re.DOTALL)
_ARCHIVED_RE = re.compile(r"Archived on\s+(\d{4}-\d{2}-\d{2})(?:\s+as\s+(.+?))?\.", re.IGNORECASE | re.DOTALL)


def collect(name: str) -> dict[str, Any]:
    """Collect published version and last-month downloads for a CRAN package."""
    version_endpoint = VERSION_URL.format(pkg=name)
    downloads_endpoint = DOWNLOADS_URL.format(pkg=name)

    status, body, error = get_json(version_endpoint)
    published_version: str | None = None
    if status == 200 and isinstance(body, dict):
        published_version = body.get("Version")

    archive_endpoint = ARCHIVE_URL.format(pkg=name)
    archive_status, archive_page, _archive_error = get_text(archive_endpoint)
    archived = archive_status == 200 and isinstance(archive_page, str) and bool(_REMOVED_RE.search(archive_page))
    archive_reason: str | None = None
    if archived:
        archived_match = _ARCHIVED_RE.search(archive_page)
        if archived_match:
            archived_on, detail = archived_match.groups()
            archive_reason = f"CRAN archived on {archived_on}"
            if detail:
                normalized_detail = re.sub(r"\s+", " ", detail).strip()
                archive_reason += f": {normalized_detail}"
        else:
            archive_reason = "CRAN reports that this package was removed from the repository"

    downloads = _downloads(downloads_endpoint)

    return {
        "published_version": published_version,
        "downloads": downloads,
        "evidence": {
            "version_endpoint": version_endpoint,
            "archive_endpoint": archive_endpoint,
            "downloads_endpoint": downloads_endpoint,
        },
        "http_status": status,
        "error": error,
        "lifecycle": "archived" if archived else None,
        "lifecycle_reason": archive_reason,
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
