from __future__ import annotations

from cockpit.cli import _carry_forward_public_signals
from cockpit.model import SentryStatus, Snapshot, Visits


def test_collect_carries_forward_token_backed_public_signals() -> None:
    snap = Snapshot(
        schema_version=1,
        generated_at="2026-06-13T00:00:00+00:00",
        generator={},
        packages=[],
        summary={},
        visits=Visits(error="no GOATCOUNTER_TOKEN in env"),
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
    }

    _carry_forward_public_signals(snap, prior)

    assert snap.visits.available is True
    assert snap.visits.windows["30d"] == 23
    assert snap.sentry.available is True
    assert snap.sentry.unresolved == 9


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
