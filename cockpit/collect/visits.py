"""GoatCounter visits collector (public signal).

Reads pageview totals for the ecosystem's GoatCounter site over a few windows
(7 d / 30 d / 365 d / all-time) **and** a per-page breakdown, so the dashboard
can show real Pages-site visits — aggregated across every nirs4all page and page
by page — something GitHub itself does not expose.

Auth: a GoatCounter **API token** in ``GOATCOUNTER_TOKEN`` (created under the
site's Settings → API), sent as ``Authorization: Bearer``. The site URL defaults
to ``https://nirs4all.goatcounter.com`` (override with ``GOATCOUNTER_SITE``).
Without a token the collector degrades gracefully (``available=False``) and never
raises, so a collect without analytics configured still succeeds.

Only aggregate counts and per-path totals enter the snapshot — never the token.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from ..http import get_json

DEFAULT_SITE = "https://nirs4all.goatcounter.com"
_WINDOWS = {"7d": 7, "30d": 30, "365d": 365}
_EPOCH = "2020-01-01"
_MAX_PAGES = 100


def _ref_date(ref_date: str | None) -> date:
    """Parse an ISO ``YYYY-MM-DD`` reference, falling back to today."""
    if ref_date:
        try:
            return date.fromisoformat(ref_date[:10])
        except ValueError:
            pass
    return date.today()


def collect(site: str | None = None, token: str | None = None, ref_date: str | None = None) -> dict[str, Any]:
    """Collect GoatCounter pageview totals per window plus a per-page breakdown.

    Returns ``{"available", "site", "windows": {"7d","30d","365d","total"},
    "pages": [{"path","title","count"}], "error"}``.
    """
    site = (site or os.environ.get("GOATCOUNTER_SITE", DEFAULT_SITE)).rstrip("/")
    token = token or os.environ.get("GOATCOUNTER_TOKEN")

    out: dict[str, Any] = {"available": False, "site": site, "windows": {}, "pages": [], "error": None}
    if not token:
        out["error"] = "no GOATCOUNTER_TOKEN in env (create one in GoatCounter → Settings → API)"
        return out

    today = _ref_date(ref_date)
    end = today.isoformat()
    headers = {"Authorization": f"Bearer {token}"}

    def _total(start: str) -> int | None:
        status, body, _error = get_json(f"{site}/api/v0/stats/total?start={start}&end={end}", headers=headers)
        if status == 200 and isinstance(body, dict):
            v = body.get("total")
            return v if isinstance(v, int) else None
        return None

    windows: dict[str, int | None] = {
        key: _total((today - timedelta(days=days)).isoformat()) for key, days in _WINDOWS.items()
    }
    windows["total"] = _total(_EPOCH)
    out["windows"] = windows

    # Per-page breakdown (all-time), highest-traffic first. Each nirs4all Pages
    # site lands under its own path prefix (/nirs4all-methods/, …), so the path
    # is a faithful per-page key; nirs4all.org sits at the root path.
    status, body, _error = get_json(
        f"{site}/api/v0/stats/hits?start={_EPOCH}&end={end}&limit={_MAX_PAGES}", headers=headers
    )
    if status == 200 and isinstance(body, dict):
        pages = [
            {
                "path": h.get("path") or "/",
                "title": (h.get("title") or "").strip() or None,
                "count": h.get("count") if isinstance(h.get("count"), int) else 0,
            }
            for h in body.get("hits", [])
        ]
        pages.sort(key=lambda p: p["count"], reverse=True)
        out["pages"] = pages

    out["available"] = any(v is not None for v in windows.values()) or bool(out["pages"])
    return out
