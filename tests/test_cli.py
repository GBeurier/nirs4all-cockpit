from __future__ import annotations

from cockpit.cli import _carry_forward_public_signals, _print_summary
from cockpit.model import SearchConsoleStats, SentryStatus, Snapshot, Visits


def test_collect_carries_forward_token_backed_public_signals() -> None:
    snap = Snapshot(
        schema_version=1,
        generated_at="2026-06-13T00:00:00+00:00",
        generator={},
        packages=[],
        summary={},
        visits=Visits(error="no GOATCOUNTER_TOKEN in env"),
        search_console=SearchConsoleStats(error="no GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON in env"),
        sentry=SentryStatus(error="no SENTRY_AUTH_TOKEN in env"),
    )
    prior = {
        "visits": {
            "available": True,
            "site": "https://nirs4all.goatcounter.com",
            "windows": {"30d": 23, "total": 23},
            "pages": [],
            "error": None,
        },
        "sentry": {
            "available": True,
            "org": "wwwciradfr",
            "project": "nirs4all-studio",
            "unresolved": 9,
            "resolved": 25,
            "events": 416,
            "users_affected": 0,
            "issues": [],
            "resolved_issues": [],
            "error": None,
        },
        "search_console": {
            "available": True,
            "site_url": "sc-domain:nirs4all.org",
            "start_date": "2026-04-01",
            "end_date": "2026-06-29",
            "windows": {"28d": {"clicks": 12, "impressions": 120, "ctr": 0.1, "position": 7.1}},
            "pages": [],
            "queries": [],
            "error": None,
        },
    }

    _carry_forward_public_signals(snap, prior)

    assert snap.visits.available is True
    assert snap.visits.windows["30d"] == 23
    assert snap.sentry.available is True
    assert snap.sentry.unresolved == 9
    assert snap.search_console.available is True
    assert snap.search_console.windows["28d"].clicks == 12


def test_collect_carries_forward_downloads_for_unchanged_targets() -> None:
    snap = Snapshot(
        schema_version=1,
        generated_at="2026-06-13T00:00:00+00:00",
        generator={},
        packages=[
            {
                "id": "pkg",
                "repo": "pkg",
                "source": {},
                "rollup": "green",
                "targets": [
                    {
                        "registry": "pypi",
                        "name": "pkg",
                        "published_version": "1.1.0",
                        "status": "green",
                        "downloads": {"source": "pypistats", "windows": {"30d": None}},
                    }
                ],
            }
        ],
        summary={},
        visits=Visits(),
        sentry=SentryStatus(),
    )
    prior = {
        "packages": [
            {
                "id": "pkg",
                "targets": [
                    {
                        "registry": "pypi",
                        "name": "pkg",
                        "published_version": "1.0.0",
                        "downloads": {
                            "last_day": 2,
                            "last_week": 7,
                            "last_month": 30,
                            "source": "pypistats",
                            "windows": {"7d": 7, "30d": 30},
                        },
                    }
                ],
            }
        ]
    }

    _carry_forward_public_signals(snap, prior)

    target = snap.packages[0].targets[0]
    assert target.downloads.last_month == 30
    assert target.downloads.windows["30d"] == 30
    assert snap.totals.downloads_last_month == 30


def test_print_summary_includes_pending(capsys) -> None:
    snap = Snapshot(
        schema_version=1,
        generated_at="2026-06-13T00:00:00+00:00",
        generator={},
        packages=[],
        summary={"green": 1, "stale": 0, "pending": 2, "missing": 3, "broken": 0, "unknown": 0, "excluded": 0},
        visits=Visits(),
        sentry=SentryStatus(),
    )

    _print_summary(snap)

    out = capsys.readouterr().out
    assert "pending=2" in out
