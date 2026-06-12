"""R-universe collector (gbeurier.r-universe.dev).

The whole universe's package list is fetched once and indexed by name. A package
present in the list but with ``Version: null`` has failed its build on
r-universe — that is reported as a ``broken`` signal (``published_version`` is
``None`` while ``http_status`` is ``200``, which :mod:`cockpit.reconcile` reads
as broken rather than missing). A name absent from the list is missing.

Endpoint:
    * ``https://gbeurier.r-universe.dev/api/packages`` → array of
      ``{Package, Version, ...}`` objects.
"""

from __future__ import annotations

from typing import Any

from ..http import get_json

PACKAGES_URL = "https://gbeurier.r-universe.dev/api/packages"

# The universe listing changes rarely; cache it for the whole collect run.
_INDEX: dict[str, dict[str, Any]] | None = None
_INDEX_STATUS: int = 0
_INDEX_ERROR: str | None = None


def _load_index() -> tuple[dict[str, dict[str, Any]] | None, int, str | None]:
    global _INDEX, _INDEX_STATUS, _INDEX_ERROR
    if _INDEX is not None or _INDEX_STATUS != 0:
        return _INDEX, _INDEX_STATUS, _INDEX_ERROR
    status, body, error = get_json(PACKAGES_URL)
    _INDEX_STATUS = status
    _INDEX_ERROR = error
    if status == 200 and isinstance(body, list):
        _INDEX = {pkg.get("Package"): pkg for pkg in body if isinstance(pkg, dict) and pkg.get("Package")}
    return _INDEX, _INDEX_STATUS, _INDEX_ERROR


def collect(name: str) -> dict[str, Any]:
    """Collect the published version of one r-universe package."""
    index, status, error = _load_index()

    published_version: str | None = None
    broken = False
    if index is not None:
        entry = index.get(name)
        if entry is not None:
            version = entry.get("Version")
            if version is None:
                broken = True  # present but failed build → broken, not missing
            else:
                published_version = version
        else:
            status = 404  # absent from the universe → missing

    return {
        "published_version": published_version,
        "downloads": {
            "last_day": None,
            "last_week": None,
            "last_month": None,
            "total": None,
            "source": None,
        },
        "evidence": {
            "version_endpoint": PACKAGES_URL,
            "downloads_endpoint": None,
        },
        "http_status": status,
        "error": error,
        "broken": broken,
    }
