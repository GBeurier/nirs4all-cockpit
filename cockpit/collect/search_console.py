"""Google Search Console search-performance collector.

Reads aggregate Search Analytics metrics for the nirs4all domain property. The
collector accepts either a short-lived bearer token or a service-account JSON
credential from the environment, and writes only aggregate counts to the public
snapshot. Credentials never enter ``data/current.json``.

Auth environment:

* ``GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN``: already-minted OAuth bearer token.
* ``GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON``: service-account JSON text.
* ``GOOGLE_APPLICATION_CREDENTIALS``: path to a service-account JSON file.

The service account must be granted access to the Search Console property.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

from ..http import post_json

DEFAULT_SITE_URL = "sc-domain:nirs4all.org"
API_ROOT = "https://www.googleapis.com/webmasters/v3/sites"
READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
DEFAULT_DATA_LAG_DAYS = 3
WINDOWS = {"7d": 7, "28d": 28, "90d": 90}
PAGE_LIMIT = 25
QUERY_LIMIT = 12


def collect(
    site_url: str | None = None,
    token: str | None = None,
    ref_date: str | None = None,
    include_pages: bool = True,
    include_queries: bool | None = None,
) -> dict[str, Any]:
    """Collect Google Search Console aggregate search-performance metrics."""
    site_url = (site_url or os.environ.get("GOOGLE_SEARCH_CONSOLE_SITE") or DEFAULT_SITE_URL).strip()
    if include_queries is None:
        include_queries = _truthy(os.environ.get("GOOGLE_SEARCH_CONSOLE_INCLUDE_QUERIES"))
    end = _end_date(ref_date)
    start_90 = _start_date(end, WINDOWS["90d"])

    out: dict[str, Any] = {
        "available": False,
        "site_url": site_url,
        "start_date": start_90.isoformat(),
        "end_date": end.isoformat(),
        "windows": {},
        "pages": [],
        "queries": [],
        "error": None,
    }

    bearer, auth_error = _bearer_token(token)
    if not bearer:
        out["error"] = auth_error or (
            "no GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN, GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON, "
            "or GOOGLE_APPLICATION_CREDENTIALS in env"
        )
        return out

    headers = {"Authorization": f"Bearer {bearer}"}
    ok = False
    errors: list[str] = []

    for key, days in WINDOWS.items():
        body, error = _query(
            site_url,
            headers,
            {
                "startDate": _start_date(end, days).isoformat(),
                "endDate": end.isoformat(),
                "type": "web",
                "rowLimit": 1,
            },
        )
        if body is None:
            errors.append(f"{key}: {error}")
            continue
        ok = True
        out["windows"][key] = _summary_metric(body)

    if include_pages:
        body, error = _query(
            site_url,
            headers,
            {
                "startDate": start_90.isoformat(),
                "endDate": end.isoformat(),
                "type": "web",
                "dimensions": ["page"],
                "aggregationType": "byPage",
                "rowLimit": PAGE_LIMIT,
            },
        )
        if body is None:
            errors.append(f"pages: {error}")
        else:
            ok = True
            out["pages"] = _dimension_rows(body, "url")

    if include_queries:
        body, error = _query(
            site_url,
            headers,
            {
                "startDate": start_90.isoformat(),
                "endDate": end.isoformat(),
                "type": "web",
                "dimensions": ["query"],
                "rowLimit": QUERY_LIMIT,
            },
        )
        if body is None:
            errors.append(f"queries: {error}")
        else:
            ok = True
            out["queries"] = _dimension_rows(body, "query")

    out["available"] = ok
    out["error"] = "; ".join(errors) or None
    return out


def _query(site_url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    site_id = quote(site_url, safe="")
    url = f"{API_ROOT}/{site_id}/searchAnalytics/query"
    status, body, error = post_json(url, payload, headers=headers)
    if status == 200 and isinstance(body, dict):
        return body, None
    return None, _api_error(body) or error or f"http {status}"


def _summary_metric(body: dict[str, Any]) -> dict[str, Any]:
    rows = body.get("rows") if isinstance(body, dict) else None
    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": None, "position": None}
    return _metric(rows[0])


def _dimension_rows(body: dict[str, Any], key_name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in body.get("rows") or []:
        keys = row.get("keys") if isinstance(row, dict) else None
        if not keys:
            continue
        out.append({key_name: str(keys[0]), **_metric(row)})
    return out


def _metric(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "clicks": _int(row.get("clicks")),
        "impressions": _int(row.get("impressions")),
        "ctr": _float(row.get("ctr"), ndigits=4),
        "position": _float(row.get("position"), ndigits=1),
    }


def _int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _float(value: Any, *, ndigits: int) -> float | None:
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


def _api_error(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if message:
            return str(message)
    return None


def _ref_date(ref_date: str | None) -> date:
    if ref_date:
        try:
            return date.fromisoformat(ref_date[:10])
        except ValueError:
            pass
    return date.today()


def _end_date(ref_date: str | None) -> date:
    lag = _int_env("GOOGLE_SEARCH_CONSOLE_DATA_LAG_DAYS", DEFAULT_DATA_LAG_DAYS)
    return _ref_date(ref_date) - timedelta(days=max(0, lag))


def _start_date(end: date, days: int) -> date:
    return end - timedelta(days=max(1, days) - 1)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bearer_token(token: str | None) -> tuple[str | None, str | None]:
    if token:
        return token, None

    direct = os.environ.get("GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN") or os.environ.get("GSC_ACCESS_TOKEN")
    if direct:
        return direct, None

    service_json = (
        os.environ.get("GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    )
    service_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not service_json and not service_file:
        return None, (
            "no GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN, GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON, "
            "or GOOGLE_APPLICATION_CREDENTIALS in env"
        )

    try:
        from google.oauth2 import service_account
    except ImportError:
        return None, "google-auth is not installed; install nirs4all-cockpit with the current dependencies"

    try:
        if service_json:
            info = json.loads(service_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=[READONLY_SCOPE])
        else:
            creds = service_account.Credentials.from_service_account_file(service_file, scopes=[READONLY_SCOPE])
        creds.refresh(_google_auth_request())
    except Exception as exc:  # noqa: BLE001 - credential errors should degrade, not crash collect.
        return None, f"{type(exc).__name__}: {exc}"

    return creds.token, None


def _google_auth_request():
    """Google auth request wrapper using the cockpit HTTP timeout budget."""
    from google.auth.transport.requests import Request

    request = Request()
    auth_timeout = _float_env("GOOGLE_AUTH_TIMEOUT", _float_env("COCKPIT_HTTP_TIMEOUT", 20.0))

    def _request(url, method="GET", body=None, headers=None, timeout=None, **kwargs):  # noqa: ARG001
        return request(url, method=method, body=body, headers=headers, timeout=auth_timeout, **kwargs)

    return _request


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
