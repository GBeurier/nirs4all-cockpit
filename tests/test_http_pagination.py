"""Pagination observes real response headers instead of legacy body-only caches."""

import httpx

from cockpit import http


def test_paginated_json_exposes_link_headers_and_bypasses_headerless_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "_CACHE_TTL_S", 3600)
    monkeypatch.setattr(http, "_CACHE_DIR", tmp_path)
    url = "https://example.org/issues/"
    http._cache_write(http._cache_path(url, {"User-Agent": http.USER_AGENT, "Accept": "application/json"}),
                      200, [{"id": "stale"}])
    calls = []

    def fake_get(request_url, **kwargs):
        calls.append(request_url)
        return httpx.Response(200, json=[{"id": "current"}], headers={
            "Link": '<https://example.org/issues/>; rel="next"; results="true"; cursor="1:0:0"',
        })

    monkeypatch.setattr(http.httpx, "get", fake_get)
    response_headers = {}
    status, body, error = http.get_json(url, response_headers=response_headers)
    assert (status, body, error) == (200, [{"id": "current"}], None)
    assert calls == [url]
    assert 'cursor="1:0:0"' in response_headers["link"]
