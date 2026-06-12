"""GoatCounter visits collector (admin-only signal).

Reads pageview totals for the ecosystem's GoatCounter site over a few windows
(7 d / 30 d / 365 d / all-time) so the local admin view can show real Pages-site
visits with history — something GitHub itself does not expose.

Auth: a GoatCounter **API token** in ``GOATCOUNTER_TOKEN`` (created under the
site's Settings → API), sent as ``Authorization: Bearer``. The site URL defaults
to ``https://nirs4all.goatcounter.com`` (override with ``GOATCOUNTER_SITE``).
Without a token the collector degrades gracefully (``available=False``) and never
raises, so an admin collect without analytics configured still succeeds.

This is **admin-only**: written to the local ``snapshot.admin.json``, never to
the public ``data/current.json``.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from ..http import get_json

DEFAULT_SITE = "https://nirs4all.goatcounter.com"
_WINDOWS = {"7d": 7, "30d": 30, "365d": 365}


def _ref_date(ref_date: str | None) -> date:
    """Parse an ISO ``YYYY-MM-DD`` reference, falling back to today."""
    if ref_date:
        try:
            return date.fromisoformat(ref_date[:10])
        except ValueError:
            pass
    return date.today()


def collect(site: str | None = None, token: str | None = None, ref_date: str | None = None) -> dict[str, Any]:
    """Collect GoatCounter pageview totals per window.

    Returns ``{"available", "site", "windows": {"7d","30d","365d","total"}, "error"}``.
    """
    site = (site or os.environ.get("GOATCOUNTER_SITE", DEFAULT_SITE)).rstrip("/")
    token = token or os.environ.get("GOATCOUNTER_TOKEN")

    out: dict[str, Any] = {"available": False, "site": site, "windows": {}, "error": None}
    if not token:
        out["error"] = "no GOATCOUNTER_TOKEN in env (admin-only; create one in GoatCounter → Settings → API)"
        return out

    today = _ref_date(ref_date)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"{site}/api/v0/stats/total"
    windows: dict[str, int | None] = {}

    def _total(start: str) -> int | None:
        status, body, _error = get_json(f"{base}?start={start}&end={today.isoformat()}", headers=headers)
        if status == 200 and isinstance(body, dict):
            v = body.get("total")
            return v if isinstance(v, int) else None
        return None

    for key, days in _WINDOWS.items():
        windows[key] = _total((today - timedelta(days=days)).isoformat())
    windows["total"] = _total("2020-01-01")

    out["windows"] = windows
    out["available"] = any(v is not None for v in windows.values())
    return out
