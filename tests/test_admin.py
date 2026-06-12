"""Phase-2 admin collectors — Sentry, PRs, security (offline, network stubbed).

Same single-seam approach as the rest of the suite: the collectors reach the
network only through ``get_json`` in their module namespace, patched here.
"""

from __future__ import annotations

from cockpit.collect import github, github_prs, github_security, sentry


def _patch_seq(monkeypatch, module, replies):
    """Replay ``get_json`` with one reply, or a sequence across successive calls."""
    if isinstance(replies, tuple):
        replies = [replies]
    calls = {"i": 0}

    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        i = min(calls["i"], len(replies) - 1)
        calls["i"] += 1
        return replies[i]

    monkeypatch.setattr(module, "get_json", _fake)


def test_sentry_no_token_degrades(monkeypatch) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    out = sentry.collect(token=None)
    assert out["available"] is False
    assert out["unresolved"] is None
    assert "SENTRY_AUTH_TOKEN" in out["error"]


def test_sentry_with_token_shapes_stats_only_by_default(monkeypatch) -> None:
    body = [
        {
            "title": "TypeError: x is undefined",
            "level": "error",
            "count": "42",
            "userCount": 5,
            "permalink": "https://de.sentry.io/issues/1/",
            "lastSeen": "2026-06-12T00:00:00Z",
        },
        {"title": "Timeout", "level": "warning", "count": "3", "userCount": 1},
    ]
    _patch_seq(monkeypatch, sentry, (200, body, None))
    out = sentry.collect(token="tok")
    assert out["available"] is True
    assert out["unresolved"] == 2
    assert out["events"] == 45
    assert out["users_affected"] == 6
    assert out["issues"] == []
    assert out["resolved_issues"] == []

    _patch_seq(monkeypatch, sentry, (200, body, None))
    out = sentry.collect(token="tok", include_issues=True)
    assert out["issues"][0]["title"] == "TypeError: x is undefined"


def test_github_prs_counts_drafts(monkeypatch) -> None:
    body = [
        {"number": 1, "title": "feat", "draft": False, "user": {"login": "a"}, "labels": []},
        {"number": 2, "title": "wip", "draft": True, "user": {"login": "b"}, "labels": [{"name": "wip"}]},
    ]
    _patch_seq(monkeypatch, github, (200, body, None))
    out = github_prs.collect("GBeurier", "nirs4all")
    assert out["open"] == 2
    assert out["draft"] == 1
    assert out["ready"] == 1


def test_github_security_unavailable_on_403(monkeypatch) -> None:
    _patch_seq(monkeypatch, github, (403, None, "forbidden"))
    out = github_security.collect("GBeurier", "nirs4all")
    assert out["available"] is False
    assert out["dependabot_open"] is None


def test_github_security_counts_and_severity(monkeypatch) -> None:
    dependabot = [
        {"security_advisory": {"severity": "high"}},
        {"security_advisory": {"severity": "low"}},
    ]
    code_scanning = [{"number": 1}]
    _patch_seq(monkeypatch, github, [(200, dependabot, None), (200, code_scanning, None)])
    out = github_security.collect("GBeurier", "nirs4all")
    assert out["available"] is True
    assert out["dependabot_open"] == 2
    assert out["code_scanning_open"] == 1
    assert out["dependabot_by_severity"]["high"] == 1
