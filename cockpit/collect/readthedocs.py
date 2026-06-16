"""Read the Docs collector.

Read the Docs is treated as a documentation registry: a target is healthy when
its rendered default version is served.

We probe the **public docs site** (``https://{slug}.readthedocs.io/en/latest/``)
rather than the JSON API. The API (``readthedocs.org/api/v3/projects/{slug}/``)
now 302-redirects anonymous requests in a loop — without a stored RTD token the
cockpit can never reach it, which made every RTD target spuriously ``missing``.
The public docs host needs no auth: it returns 200 when the default version is
built and 404 when the project/version does not exist, which is exactly the
healthy/missing signal we want. RTD exposes no release-relevant download counts,
so downloads remain empty.
"""

from __future__ import annotations

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..http import TIMEOUT_S, USER_AGENT

DOCS_URL = "https://{slug}.readthedocs.io/en/latest/"


def probe(url: str) -> tuple[int, str | None]:
    """Return the HTTP status of ``url`` (following redirects), or (0, error).

    A built RTD version answers 200; an unknown project/version answers 404.
    urlopen follows the docs host's ``/`` → ``/en/latest/`` redirect, and unlike
    the API host it does not loop.
    """
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=min(TIMEOUT_S, 8.0)) as resp:
            return resp.status, None
    except HTTPError as exc:
        return exc.code, None
    except URLError as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def collect(name: str) -> dict[str, Any]:
    """Collect Read the Docs default-version availability for ``name``."""
    docs_url = DOCS_URL.format(slug=name)
    status, error = probe(docs_url)
    healthy = 200 <= status < 300

    return {
        # A served default version reconciles as green (expected=None for RTD);
        # None -> missing. The slug-derived host IS the version identity here.
        "published_version": "latest" if healthy else None,
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
            "version_endpoint": docs_url,
            "downloads_endpoint": None,
        },
        "http_status": status,
        "error": None if healthy else (error or (f"http {status}" if status else None)),
        "broken": False,
    }
