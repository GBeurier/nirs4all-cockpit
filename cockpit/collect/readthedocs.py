"""Read the Docs collector.

Read the Docs is treated as a documentation registry: a target is healthy when
the project exists and its default version is active and built. It exposes no
download counts relevant to package releases, so downloads remain empty.

Endpoints:
    * project: ``https://readthedocs.org/api/v3/projects/{slug}/`` → project
      metadata, including ``default_version`` and documentation URL.
    * version: ``https://readthedocs.org/api/v3/projects/{slug}/versions/{ver}/``
      → ``active`` / ``built`` for the default version.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..http import TIMEOUT_S, USER_AGENT

PROJECT_URL = "https://readthedocs.org/api/v3/projects/{slug}/"
VERSION_URL = "https://readthedocs.org/api/v3/projects/{slug}/versions/{version}/"


def get_json(url: str) -> tuple[int, Any | None, str | None]:
    """Fetch RTD JSON once.

    The shared HTTP helper retries 429s with backoff, which is useful for package
    registries but makes an ecosystem-wide collect crawl when RTD throttles us.
    For docs status, a rate limit should degrade to ``unknown`` quickly.
    """
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=min(TIMEOUT_S, 8.0)) as resp:
            status = resp.status
            raw = resp.read()
    except HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except URLError as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"

    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        if 200 <= status < 300:
            return status, None, "invalid json body"
        return status, None, f"http {status}"
    return status, body, None


def collect(name: str) -> dict[str, Any]:
    """Collect Read the Docs project/default-version availability for ``name``."""
    project_endpoint = PROJECT_URL.format(slug=name)
    status, body, error = get_json(project_endpoint)

    published_version: str | None = None
    version_status = status
    version_error = error
    broken = False
    documentation_url: str | None = None

    if status == 200 and isinstance(body, dict):
        published_version = body.get("default_version") or "latest"
        urls = body.get("urls") or {}
        documentation_url = urls.get("documentation")
        version_endpoint = VERSION_URL.format(slug=name, version=published_version)
        version_status, version_body, version_error = get_json(version_endpoint)
        if version_status == 200 and isinstance(version_body, dict):
            if not version_body.get("active", False) or not version_body.get("built", False):
                broken = True
            version_urls = version_body.get("urls") or {}
            documentation_url = version_urls.get("documentation") or documentation_url
        elif version_status == 404:
            broken = True
    else:
        version_endpoint = VERSION_URL.format(slug=name, version="latest")

    return {
        "published_version": published_version,
        "downloads": {
            "last_day": None,
            "last_week": None,
            "last_month": None,
            "total": None,
            "source": None,
            "by_version": [],
            "windows": {},
        },
        "evidence": {
            "version_endpoint": documentation_url or project_endpoint,
            "downloads_endpoint": None,
        },
        "http_status": version_status,
        "error": version_error,
        "broken": broken,
    }
