"""Sentry issue-stream parity, using synthetic offline API responses."""

from urllib.parse import parse_qs, urlsplit

import pytest

from cockpit.collect import sentry
from cockpit.model import SentryStatus


def test_orphaned_legacy_group_does_not_create_a_phantom_alert(monkeypatch):
    """A legacy group can survive after its event disappears from issue search."""
    orphan = {"title": "Native report", "count": "1", "userCount": 0, "status": "unresolved"}
    queries = []

    def fake_get(url, headers=None):
        parsed = urlsplit(url)
        if "/projects/" in parsed.path:
            return 200, [orphan], None
        assert parsed.path == "/api/0/organizations/wwwciradfr/issues/"
        params = parse_qs(parsed.query)
        assert params["project"] == ["nirs4all-studio"]
        assert params["statsPeriod"] == ["14d"]
        queries.append(params["query"][0])
        return 200, [], None

    monkeypatch.setattr(sentry, "get_json", fake_get)
    out = sentry.collect(token="test-token")
    assert out["available"] is True
    assert out["unresolved"] == out["resolved"] == out["events"] == out["users_affected"] == 0
    assert queries == ["is:unresolved", "is:resolved"]
    assert SentryStatus.model_validate(out).stats_period == "14d"


def test_searchable_native_error_is_still_counted_with_requested_scope(monkeypatch):
    """Switching endpoints must not filter out genuine native errors."""
    issue = {"title": "Native error", "platform": "native", "count": "2", "userCount": 1}

    def fake_get(url, headers=None):
        parsed = urlsplit(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "sentry.example.com"
        assert parsed.path == "/api/0/organizations/test-org/issues/"
        params = parse_qs(parsed.query)
        assert params["project"] == ["custom-project"]
        assert params["statsPeriod"] == ["7d"]
        assert headers == {"Authorization": "Bearer test-token"}
        return 200, [issue] if params["query"] == ["is:unresolved"] else [], None

    monkeypatch.setattr(sentry, "get_json", fake_get)
    out = sentry.collect(
        org="test-org", project="custom-project", region_url="https://sentry.example.com/",
        token="test-token", stats_period="7d",
    )
    assert (out["unresolved"], out["events"], out["users_affected"]) == (1, 2, 1)
    assert out["resolved"] == 0
    assert out["stats_period"] == "7d"
    assert out["issues"] == out["resolved_issues"] == []


@pytest.mark.parametrize("response", [(403, None, "forbidden"), (0, None, "timeout"), (200, {"detail": "error"}, None)])
def test_failed_search_remains_unknown_without_legacy_fallback(monkeypatch, response):
    calls = []

    def fake_get(url, headers=None):
        calls.append(url)
        return response

    monkeypatch.setattr(sentry, "get_json", fake_get)
    out = sentry.collect(token="test-token")
    assert len(calls) == 1
    assert out["available"] is False
    assert out["unresolved"] is None
    assert out["events"] is None
    assert out["error"]


def test_resolved_search_failure_preserves_unresolved_count(monkeypatch):
    def fake_get(url, headers=None):
        query = parse_qs(urlsplit(url).query)["query"]
        if query == ["is:resolved"]:
            return 503, None, "http 503"
        return 200, [{"count": "3", "userCount": 1}], None

    monkeypatch.setattr(sentry, "get_json", fake_get)
    out = sentry.collect(token="test-token")
    assert out["available"] is True
    assert out["unresolved"] == 1
    assert out["resolved"] is None


def test_legacy_snapshot_has_no_claimed_activity_window():
    assert SentryStatus.model_validate({"available": True, "unresolved": 1}).stats_period is None
