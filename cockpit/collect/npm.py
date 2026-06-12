"""npm collector.

Two scoped-package traps are handled here:

* the package endpoint path must percent-encode the ``/`` of a scope
  (``@nirs4all/formats-wasm`` → ``@nirs4all%2Fformats-wasm``);
* the downloads endpoint, for scoped packages, returns *either* a ``404`` *or* an
  HTTP ``200`` whose body is ``{"error": ...}``. The body is parsed in both
  cases, downloads degrade to ``None`` ("unknown"), and the version verdict is
  never reddened.

Endpoints:
    * version:   ``https://registry.npmjs.org/{pkg}`` → ``dist-tags.latest``.
    * downloads: ``https://api.npmjs.org/downloads/point/last-month/{pkg}`` →
      ``downloads`` (an int) on success.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..http import get_json

VERSION_URL = "https://registry.npmjs.org/{pkg}"
DOWNLOADS_URL = "https://api.npmjs.org/downloads/point/last-month/{pkg}"


def _encode(name: str) -> str:
    """Percent-encode a package name so a scope's ``/`` survives the path."""
    return quote(name, safe="@")


def collect(name: str) -> dict[str, Any]:
    """Collect published version and last-month downloads for an npm package."""
    encoded = _encode(name)
    version_endpoint = VERSION_URL.format(pkg=encoded)
    downloads_endpoint = DOWNLOADS_URL.format(pkg=encoded)

    status, body, error = get_json(version_endpoint)
    published_version: str | None = None
    if status == 200 and isinstance(body, dict):
        dist_tags = body.get("dist-tags") or {}
        published_version = dist_tags.get("latest")

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
    """Fetch last-month downloads; a 404 or an in-body ``error`` leaves ``None``."""
    out: dict[str, Any] = {
        "last_day": None,
        "last_week": None,
        "last_month": None,
        "total": None,
        "source": "npm",
    }
    status, body, _error = get_json(endpoint)
    # Scoped packages can return 200 with {"error": "..."}; parse the body, never
    # treat a download gap as the package being absent.
    if status == 200 and isinstance(body, dict) and "error" not in body:
        count = body.get("downloads")
        if isinstance(count, int):
            out["last_month"] = count
    out["windows"] = {"7d": None, "30d": out["last_month"], "90d": None, "total": None}
    return out
