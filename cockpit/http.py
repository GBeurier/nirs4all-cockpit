"""Shared HTTP client for cockpit collectors.

A single :func:`get_json` helper is the only network primitive the collectors
use. It is deliberately *boundary-defensive*: it never raises on an HTTP error
status, a timeout, a connection drop, or a malformed body. Instead it returns a
``(status, body, error)`` tuple so each collector can decide what an error
*means* for its registry (a 404 on crates.io is ``missing``; a 429 on pypistats
is ``unknown``).

Cross-cutting concerns handled here, once, for every registry:

* a descriptive ``User-Agent`` (crates.io returns 403 without one);
* a 20 s timeout, overridable through ``COCKPIT_HTTP_TIMEOUT``;
* bounded retry with exponential backoff on 429 and 5xx (and transport errors);
* an optional light on-disk cache under ``.cache/`` keyed by URL+headers.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "nirs4all-cockpit (gregory.beurier@cirad.fr)"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


TIMEOUT_S = _env_float("COCKPIT_HTTP_TIMEOUT", 20.0)
MAX_RETRIES = _env_int("COCKPIT_HTTP_MAX_RETRIES", 3)
BACKOFF_BASE_S = _env_float("COCKPIT_HTTP_BACKOFF_BASE", 1.0)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

_CACHE_DIR = Path(os.environ.get("COCKPIT_CACHE_DIR", ".cache"))
_CACHE_TTL_S = float(os.environ.get("COCKPIT_CACHE_TTL", "0"))  # 0 disables caching


def _cache_path(url: str, headers: dict[str, str] | None) -> Path:
    key = url + "\x00" + json.dumps(headers or {}, sort_keys=True)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / f"{digest}.json"


def _cache_read(path: Path) -> tuple[int, Any] | None:
    if _CACHE_TTL_S <= 0 or not path.exists():
        return None
    if time.time() - path.stat().st_mtime > _CACHE_TTL_S:
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        return int(blob["status"]), blob["body"]
    except (OSError, ValueError, KeyError):
        return None


def _cache_write(path: Path, status: int, body: Any) -> None:
    if _CACHE_TTL_S <= 0:
        return
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": status, "body": body}), encoding="utf-8")
    except (OSError, TypeError):
        pass  # cache is best-effort; never let it break a collect


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    accept: str = "application/json",
    max_retries: int = MAX_RETRIES,
) -> tuple[int, Any | None, str | None]:
    """Fetch ``url`` and parse the body as JSON, never raising on network error.

    Args:
        url: Absolute URL to GET.
        headers: Extra request headers, merged over the descriptive defaults.
        accept: ``Accept`` header value (some registries vary their response).
        max_retries: Number of retries for 429/5xx or transport failures.

    Returns:
        A ``(status, body, error)`` tuple.

        * On a successful JSON response: ``(status, parsed_json, None)``.
        * On a non-2xx status with a parseable JSON body: ``(status, body,
          None)`` — the caller inspects ``status``/``body`` (e.g. npm returns a
          ``200`` with ``{"error": ...}``).
        * On a non-2xx status with a non-JSON body: ``(status, None, "http
          <status>")``.
        * On a timeout / transport failure / exhausted retries: ``(0, None,
          "<reason>")`` so the caller can map it to ``unknown``.
    """
    return _json_request("GET", url, headers=headers, accept=accept, max_retries=max_retries)


def post_json(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    *,
    accept: str = "application/json",
    max_retries: int = MAX_RETRIES,
) -> tuple[int, Any | None, str | None]:
    """POST a JSON payload and parse a JSON response, never raising on network error."""
    return _json_request("POST", url, headers=headers, accept=accept, max_retries=max_retries, payload=payload)


def _json_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    *,
    accept: str,
    max_retries: int,
    payload: dict | None = None,
) -> tuple[int, Any | None, str | None]:
    merged = {"User-Agent": USER_AGENT, "Accept": accept}
    if headers:
        merged.update(headers)

    cache_file = _cache_path(url, merged) if method == "GET" else None
    if cache_file is not None:
        cached = _cache_read(cache_file)
        if cached is not None:
            return cached[0], cached[1], None

    last_error: str | None = None
    last_status = 0

    for attempt in range(max_retries + 1):
        try:
            if method == "POST":
                resp = httpx.post(url, headers=merged, json=payload, timeout=TIMEOUT_S, follow_redirects=True)
            else:
                resp = httpx.get(url, headers=merged, timeout=TIMEOUT_S, follow_redirects=True)
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            last_status = 0
        else:
            last_status = resp.status_code
            if resp.status_code in RETRY_STATUSES and attempt < max_retries:
                time.sleep(_retry_delay(resp, attempt))
                continue
            try:
                body = resp.json()
            except ValueError:
                if resp.is_success:
                    return resp.status_code, None, "invalid json body"
                return resp.status_code, None, f"http {resp.status_code}"
            if cache_file is not None:
                _cache_write(cache_file, resp.status_code, body)
            return resp.status_code, body, None

        if attempt < max_retries:
            time.sleep(_retry_delay(None, attempt))

    return last_status, None, last_error or f"http {last_status}"


def _retry_delay(resp: httpx.Response | None, attempt: int) -> float:
    """Backoff delay, honouring a ``Retry-After`` header when the server sends one."""
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
    return BACKOFF_BASE_S * (2**attempt)
