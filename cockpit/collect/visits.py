"""GoatCounter visits collector (public signal).

Reads pageview totals for the ecosystem's GoatCounter site over a few windows
(7 d / 30 d / 365 d / all-time), so the dashboard can show aggregate Pages-site
visits — something GitHub itself does not expose.

Auth: a GoatCounter **API token** in ``GOATCOUNTER_TOKEN`` (created under the
site's Settings → API), sent as ``Authorization: Bearer``. The site URL defaults
to ``https://nirs4all.goatcounter.com`` (override with ``GOATCOUNTER_SITE``).
Without a token the collector degrades gracefully (``available=False``) and never
raises, so a collect without analytics configured still succeeds.

Only count data enters the public snapshot — never the token. Per-page details
are path/title/count aggregates only.
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


def collect(
    site: str | None = None,
    token: str | None = None,
    ref_date: str | None = None,
    include_pages: bool = False,
) -> dict[str, Any]:
    """Collect GoatCounter pageview totals per window.

    Returns ``{"available", "site", "windows": {"7d","30d","365d","total"},
    "pages": [], "error"}``. Per-page details are returned only when
    ``include_pages=True``.
    """
    site = (site or os.environ.get("GOATCOUNTER_SITE", DEFAULT_SITE)).rstrip("/")
    token = token or os.environ.get("GOATCOUNTER_TOKEN")

    out: dict[str, Any] = {"available": False, "site": site, "windows": {}, "since": None, "pages": [], "error": None}
    if not token:
        out["error"] = "no GOATCOUNTER_TOKEN in env (create one in GoatCounter → Settings → API)"
        return out

    today = _ref_date(ref_date)
    end = today.isoformat()
    headers = {"Authorization": f"Bearer {token}"}

    def _total_body(start: str) -> dict[str, Any] | None:
        status, body, _error = get_json(f"{site}/api/v0/stats/total?start={start}&end={end}", headers=headers)
        return body if status == 200 and isinstance(body, dict) else None

    def _total(start: str) -> int | None:
        body = _total_body(start)
        v = body.get("total") if body else None
        return v if isinstance(v, int) else None

    windows: dict[str, int | None] = {
        key: _total((today - timedelta(days=days)).isoformat()) for key, days in _WINDOWS.items()
    }
    # The all-time call carries a per-day ``stats`` array (HitListStat); the first
    # day with traffic is when this GoatCounter site began recording — surfaced as
    # ``since`` so the dashboard can show "all-time · since <date>".
    alltime = _total_body(_EPOCH) or {}
    total = alltime.get("total")
    windows["total"] = total if isinstance(total, int) else None
    for s in alltime.get("stats") or []:
        if isinstance(s, dict) and (s.get("daily") or 0) > 0 and s.get("day"):
            out["since"] = s["day"]
            break
    out["windows"] = windows

    if include_pages:
        # Per-page breakdown (all-time), highest-traffic first.
        status, body, _error = get_json(
            f"{site}/api/v0/stats/hits?start={_EPOCH}&end={end}&limit={_MAX_PAGES}", headers=headers
        )
        if status == 200 and isinstance(body, dict):
            # Every ecosystem page sets an explicit per-site path via
            # ``data-goatcounter-settings`` (e.g. ``/formats``, ``/io``, ``/methods``),
            # so the per-page breakdown is keyed by site. The bare ``/`` bucket is
            # only the legacy traffic recorded before those path overrides existed;
            # drop it so it does not masquerade as one ecosystem page.
            pages = [
                {
                    "path": h.get("path") or "/",
                    "title": (h.get("title") or "").strip() or None,
                    "count": h.get("count") if isinstance(h.get("count"), int) else 0,
                }
                for h in body.get("hits", [])
                if (h.get("path") or "/") != "/"
            ]
            pages.sort(key=lambda p: p["count"], reverse=True)
            out["pages"] = pages

    out["available"] = any(v is not None for v in windows.values()) or bool(out["pages"])
    return out
