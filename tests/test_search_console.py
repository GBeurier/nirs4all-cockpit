from __future__ import annotations

import sys
from types import SimpleNamespace

from google.oauth2 import service_account

from cockpit.collect import search_console


def test_search_console_no_credentials_degrades(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GSC_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GSC_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    out = search_console.collect(ref_date="2026-07-02")

    assert out["available"] is False
    assert "GOOGLE_SEARCH_CONSOLE" in out["error"]


def test_search_console_collects_windows_and_pages(monkeypatch) -> None:
    seen = []

    def _fake_post(url, payload, headers=None, *, accept="application/json", max_retries=None):  # noqa: ARG001
        seen.append((url, payload, headers))
        dims = payload.get("dimensions") or []
        if dims == ["page"]:
            return (
                200,
                {
                    "rows": [
                        {
                            "keys": ["https://web.nirs4all.org/"],
                            "clicks": 4.0,
                            "impressions": 40.0,
                            "ctr": 0.1,
                            "position": 6.2,
                        }
                    ]
                },
                None,
            )
        if dims == ["query"]:
            return (
                200,
                {
                    "rows": [
                        {
                            "keys": ["nirs tools"],
                            "clicks": 2.0,
                            "impressions": 20.0,
                            "ctr": 0.1,
                            "position": 3.4,
                        }
                    ]
                },
                None,
            )
        return (
            200,
            {"rows": [{"clicks": 7.0, "impressions": 70.0, "ctr": 0.1, "position": 5.6}]},
            None,
        )

    monkeypatch.setattr(search_console, "post_json", _fake_post)

    out = search_console.collect(
        site_url="sc-domain:nirs4all.org",
        token="tok",
        ref_date="2026-07-02",
        include_queries=True,
    )

    assert out["available"] is True
    assert out["start_date"] == "2026-04-01"
    assert out["end_date"] == "2026-06-29"
    assert out["windows"]["28d"]["clicks"] == 7
    assert out["pages"][0]["url"] == "https://web.nirs4all.org/"
    assert out["pages"][0]["position"] == 6.2
    assert out["queries"][0]["query"] == "nirs tools"
    assert seen
    assert seen[0][0].endswith("/sites/sc-domain%3Anirs4all.org/searchAnalytics/query")
    assert seen[0][2]["Authorization"] == "Bearer tok"


def test_search_console_service_account_refresh_uses_bounded_timeout(monkeypatch) -> None:
    calls = []

    class FakeCreds:
        token = "service-token"

        def refresh(self, request):
            request("https://oauth.example/token")

    class FakeRequest:
        def __call__(self, url, method="GET", body=None, headers=None, timeout=120, **kwargs):  # noqa: ARG001
            calls.append(timeout)

    monkeypatch.setenv("GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON", "{}")
    monkeypatch.setenv("GOOGLE_AUTH_TIMEOUT", "4.5")
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", SimpleNamespace(Request=lambda: FakeRequest()))
    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_info",
        lambda info, scopes: FakeCreds(),  # noqa: ARG005
    )

    token, error = search_console._bearer_token(None)

    assert token == "service-token"
    assert error is None
    assert calls == [4.5]
