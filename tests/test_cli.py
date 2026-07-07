from __future__ import annotations

from typer.testing import CliRunner

from cockpit import cli
from cockpit.cli import _carry_forward_public_signals, _print_summary
from cockpit.model import SearchConsoleStats, SentryStatus, Snapshot, Visits


def test_collect_only_refuses_default_public_snapshot_path() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["collect", "--only", "nirs4all-cockpit", "--offline"])

    assert result.exit_code == 2
    assert "refusing to write a partial --only snapshot to data/current.json" in result.stderr


def test_collect_only_allows_explicit_scratch_output(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    out = tmp_path / "partial-current.json"

    def build_snapshot(*_args, **_kwargs):
        return Snapshot(
            schema_version=1,
            generated_at="2026-07-07T00:00:00+00:00",
            generator={},
            packages=[],
            summary={},
            visits=Visits(),
            sentry=SentryStatus(),
        )

    monkeypatch.setattr(cli.reconcile, "build_snapshot", build_snapshot)

    result = runner.invoke(
        cli.app,
        [
            "collect",
            "--only",
            "nirs4all-cockpit",
            "--offline",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    assert out.is_file()
    assert "wrote" in result.stdout


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


def test_collect_carries_forward_public_github_facts_when_collect_loses_api_data() -> None:
    snap = Snapshot(
        schema_version=1,
        generated_at="2026-06-13T00:00:00+00:00",
        generator={},
        packages=[
            {
                "id": "pkg",
                "repo": "pkg",
                "source": {
                    "manifest_version": "1.0.0",
                    "expected_prod_version": "1.0.0",
                },
                "rollup": "green",
                "targets": [
                    {
                        "registry": "github-pages",
                        "name": "pkg",
                        "published_version": "1.0.0",
                        "status": "green",
                    }
                ],
                "workflows": [{"file": "publish.yml"}],
                "issues": {"open": 0, "bugs": 0},
                "repo_stats": {"language": "Python"},
                "actions_stats": {},
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
                "source": {
                    "manifest_version": "1.0.0",
                    "latest_prod_tag": "v1.0.0",
                    "latest_any_tag": "v1.0.0",
                    "expected_prod_version": "v1.0.0",
                    "commit": "abc123",
                    "latest_prod_tag_at": "2026-06-01T00:00:00Z",
                    "latest_release_at": "2026-06-01T00:01:00Z",
                    "latest_version_at": "2026-06-01T00:01:00Z",
                    "latest_version_source": "release",
                    "last_commit_at": "2026-06-01T00:02:00Z",
                    "commits_ahead_of_latest_prod_tag": 0,
                },
                "targets": [
                    {
                        "registry": "github-pages",
                        "name": "pkg",
                        "downloads": {"last_month": 4},
                    }
                ],
                "workflows": [{"file": "publish.yml", "conclusion": "success"}],
                "issues": {"open": 2, "bugs": 1},
                "repo_stats": {
                    "stars": 8,
                    "forks": 1,
                    "watchers": 3,
                    "open_prs": 4,
                    "closed_prs": 5,
                    "merged_prs": 6,
                    "size_kb": 700,
                    "language": "Python",
                    "license": "AGPL-3.0",
                    "pushed_at": "2026-06-02T00:00:00Z",
                    "default_branch": "main",
                },
                "actions_stats": {
                    "workflows": 3,
                    "total_runs": 12,
                    "recent_total": 10,
                    "recent_success": 9,
                    "recent_failure": 1,
                    "success_rate": 90.0,
                    "last_conclusion": "success",
                    "last_created_at": "2026-06-02T00:00:00Z",
                },
            }
        ]
    }

    _carry_forward_public_signals(snap, prior)

    package = snap.packages[0]
    assert package.source.latest_prod_tag == "v1.0.0"
    assert package.source.commit == "abc123"
    assert package.repo_stats is not None
    assert package.repo_stats.stars == 8
    assert package.repo_stats.closed_prs == 5
    assert package.actions_stats is not None
    assert package.actions_stats.total_runs == 12
    assert package.workflows[0].file == "publish.yml"
    assert package.issues.open == 2
    assert snap.totals.stars == 8
    assert snap.totals.workflow_runs == 12
    assert snap.totals.downloads_last_month == 4


def test_collect_does_not_carry_forward_source_tag_when_manifest_changed() -> None:
    snap = Snapshot(
        schema_version=1,
        generated_at="2026-06-13T00:00:00+00:00",
        generator={},
        packages=[
            {
                "id": "pkg",
                "repo": "pkg",
                "source": {
                    "manifest_version": "1.0.1",
                    "expected_prod_version": "1.0.1",
                },
                "rollup": "green",
                "targets": [{"registry": "pypi", "name": "pkg", "status": "green"}],
                "repo_stats": {"stars": 1},
                "actions_stats": {"total_runs": 1},
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
                "source": {
                    "manifest_version": "1.0.0",
                    "latest_prod_tag": "v1.0.0",
                    "commit": "old",
                },
            }
        ]
    }

    _carry_forward_public_signals(snap, prior)

    assert snap.packages[0].source.latest_prod_tag is None
    assert snap.packages[0].source.commit is None


def test_collect_uses_local_git_source_when_manifest_changed_and_github_missing(monkeypatch) -> None:
    snap = Snapshot(
        schema_version=1,
        generated_at="2026-06-13T00:00:00+00:00",
        generator={},
        packages=[
            {
                "id": "pkg",
                "repo": "pkg",
                "source": {
                    "manifest_version": "1.0.1",
                    "expected_prod_version": "1.0.1",
                },
                "rollup": "green",
                "targets": [{"registry": "pypi", "name": "pkg", "status": "green"}],
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
                "source": {
                    "manifest_version": "1.0.0",
                    "latest_prod_tag": "v1.0.0",
                    "commit": "old",
                },
            }
        ]
    }

    monkeypatch.setattr(
        cli,
        "_local_git_source_facts",
        lambda repo, manifest: {
            "latest_prod_tag": "v1.0.1",
            "latest_any_tag": "v1.0.1",
            "expected_prod_version": "v1.0.1",
            "commit": "new",
            "latest_prod_tag_at": "2026-06-14T00:00:00+00:00",
            "latest_version_at": "2026-06-14T00:00:00+00:00",
            "latest_version_source": "tag",
            "last_commit_at": "2026-06-14T00:00:00+00:00",
            "commits_ahead_of_latest_prod_tag": 0,
        },
    )

    _carry_forward_public_signals(snap, prior)

    assert snap.packages[0].source.latest_prod_tag == "v1.0.1"
    assert snap.packages[0].source.expected_prod_version == "v1.0.1"
    assert snap.packages[0].source.commit == "new"


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
