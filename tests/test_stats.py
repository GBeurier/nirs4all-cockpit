"""Phase-3 stats — local code scanner and GitHub Actions stats (offline)."""

from __future__ import annotations

import zipfile
from io import BytesIO

from cockpit.collect import code_stats, github


def test_code_stats_counts_and_skips_vendored(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "mod.py").write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "def foo():",
                "    return 1",
                '"""',
                "block doc",
                '"""',
                "def test_foo():",
                "    assert foo() == 1",
            ]
        ),
        encoding="utf-8",
    )
    # vendored dir must be skipped entirely
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "junk.py").write_text("x = 1\n" * 100, encoding="utf-8")

    monkeypatch.setattr(code_stats, "SIBLINGS_ROOT", tmp_path)
    out = code_stats.scan("myrepo")

    assert out is not None
    assert out["source"] == "local-scan"
    assert out["files"] == 1  # node_modules skipped
    assert out["loc_blank"] == 1
    assert out["loc_comment"] == 4  # '#' line + the three triple-quote lines
    assert out["loc_code"] == 4  # def foo, return, def test_foo, assert
    assert out["tests"] == 1
    assert out["by_language"]["Python"] == 4


def test_code_stats_skips_nested_git_checkouts(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "mod.py").write_text("x = 1\n", encoding="utf-8")
    nested = repo / "nested-checkout"
    nested.mkdir()
    (nested / ".git").write_text("gitdir: ../.git/modules/nested-checkout\n", encoding="utf-8")
    (nested / "inflated.py").write_text("x = 1\n" * 100, encoding="utf-8")

    monkeypatch.setattr(code_stats, "SIBLINGS_ROOT", tmp_path)
    out = code_stats.scan("myrepo")

    assert out is not None
    assert out["files"] == 1
    assert out["loc_code"] == 1


def test_code_stats_missing_repo_returns_none(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(code_stats, "SIBLINGS_ROOT", tmp_path)
    assert code_stats.scan("does-not-exist") is None


def test_code_stats_can_skip_artifact_coverage(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "mod.py").write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(code_stats, "SIBLINGS_ROOT", tmp_path)
    monkeypatch.setattr(
        code_stats,
        "_coverage_from_github_artifact",
        lambda repo: (_ for _ in ()).throw(AssertionError("network fallback should be skipped")),  # noqa: ARG005
    )

    out = code_stats.scan("myrepo", allow_artifact_coverage=False)

    assert out is not None
    assert out["coverage_pct"] is None


def test_coverage_from_github_artifact_zip(monkeypatch) -> None:
    artifact = {"archive_download_url": "https://api.github.test/artifact.zip"}
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("coverage.xml", '<coverage line-rate="0.53"></coverage>')

    class _Resp:
        content = buf.getvalue()

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(code_stats.github, "_headers", lambda: {"Authorization": "Bearer tok"})
    monkeypatch.setattr(code_stats.httpx, "get", lambda *args, **kwargs: _Resp())  # noqa: ARG005

    assert code_stats._coverage_from_artifact_zip(artifact) == 53.0


def test_repo_stats_carries_github_primary_language(monkeypatch) -> None:
    repo = (
        200,
        {
            "stargazers_count": 1,
            "forks_count": 2,
            "subscribers_count": 3,
            "size": 123,
            "language": "C++",
            "license": {"spdx_id": "AGPL-3.0"},
            "pushed_at": "2026-06-13T00:00:00Z",
            "default_branch": "main",
            "open_issues_count": 4,
        },
        None,
    )

    monkeypatch.setattr(github, "get_json", lambda *args, **kwargs: repo)  # noqa: ARG005

    out = github.repo_stats("GBeurier", "nirs4all-methods")

    assert out["language"] == "C++"


def test_latest_release_fact_sums_all_release_asset_downloads(monkeypatch) -> None:
    def _fake_get(url):
        if url.endswith("/releases/latest"):
            return 200, {"tag_name": "0.8.0", "assets": [{"download_count": 15}]}, None
        if url.endswith("/releases?per_page=100"):
            return (
                200,
                [
                    {"tag_name": "0.8.0", "draft": False, "prerelease": False, "assets": [{"download_count": 15}]},
                    {"tag_name": "0.7.0", "draft": False, "prerelease": False, "assets": [{"download_count": 21}]},
                ],
                None,
            )
        raise AssertionError(url)

    monkeypatch.setattr(github, "_get", _fake_get)

    out = github.latest_release_fact("GBeurier", "nirs4all-studio")

    assert out["published_version"] == "0.8.0"
    assert out["asset_downloads"] == 36


def test_latest_release_fact_falls_back_to_gh_api_when_http_is_rate_limited(monkeypatch) -> None:
    monkeypatch.setattr(github, "_get", lambda url: (403, {"message": "rate limit"}, None))  # noqa: ARG005
    monkeypatch.setattr(
        github,
        "_gh_api_json",
        lambda endpoint: {"tag_name": "v0.1.1", "assets": [{"download_count": 3}]},
    )

    out = github.latest_release_fact("GBeurier", "nirs4all-ui")

    assert out == {
        "published_version": "v0.1.1",
        "http_status": 200,
        "error": None,
        "asset_downloads": 3,
    }


def test_github_get_retries_anonymously_when_env_token_is_rejected(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        calls.append(dict(headers or {}))
        if len(calls) == 1:
            assert "Authorization" in calls[-1]
            return 401, {"message": "Bad credentials"}, None
        assert "Authorization" not in calls[-1]
        return 200, {"tag_name": "v0.1.0"}, None

    monkeypatch.setenv("GITHUB_TOKEN", "stale-token")
    monkeypatch.setattr(github, "get_json", _fake)

    status, body, error = github._get("https://api.github.com/repos/GBeurier/nirs4all-ui/releases/latest")

    assert status == 200
    assert body == {"tag_name": "v0.1.0"}
    assert error is None
    assert len(calls) == 2


def test_pages_status_falls_back_to_gh_api_when_public_endpoint_is_hidden(monkeypatch) -> None:
    monkeypatch.setattr(github, "_get", lambda url: (404, {"message": "Not Found"}, None))  # noqa: ARG005
    monkeypatch.setattr(
        github,
        "_gh_api_json",
        lambda endpoint: {
            "html_url": "https://gbeurier.github.io/nirs4all-ui/",
            "status": None,
            "cname": None,
        },
    )

    out = github.pages_status("GBeurier", "nirs4all-ui")

    assert out == {
        "available": True,
        "html_url": "https://gbeurier.github.io/nirs4all-ui/",
        "build_status": None,
        "cname": None,
    }


def test_gh_api_json_ignores_invalid_token_env(monkeypatch) -> None:
    seen_env: dict | None = None

    class _Proc:
        returncode = 0
        stdout = '{"html_url":"https://gbeurier.github.io/nirs4all-ui/"}'

    def _fake_run(*args, **kwargs):  # noqa: ARG001
        nonlocal seen_env
        seen_env = kwargs["env"]
        return _Proc()

    monkeypatch.setenv("GITHUB_TOKEN", "stale-token")
    monkeypatch.setenv("GH_TOKEN", "stale-token")
    monkeypatch.setattr(github.subprocess, "run", _fake_run)

    out = github._gh_api_json("repos/GBeurier/nirs4all-ui/pages")

    assert out == {"html_url": "https://gbeurier.github.io/nirs4all-ui/"}
    assert seen_env is not None
    assert "GITHUB_TOKEN" not in seen_env
    assert "GH_TOKEN" not in seen_env


def test_actions_stats_success_rate(monkeypatch) -> None:
    workflows = (200, {"total_count": 5}, None)
    runs = (
        200,
        {
            "total_count": 1234,
            "workflow_runs": [
                {"conclusion": "success", "created_at": "2026-06-12T00:00:00Z"},
                {"conclusion": "failure"},
                {"conclusion": "success"},
                {"conclusion": None},  # in-progress → excluded from the rate
            ],
        },
        None,
    )

    repo = (200, {"default_branch": "main"}, None)
    seen_run_urls: list[str] = []

    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        if "actions/workflows" in url:
            return workflows
        if "actions/runs" in url:
            seen_run_urls.append(url)
            return runs
        return repo  # /repos/{owner}/{repo} → default branch lookup

    monkeypatch.setattr(github, "get_json", _fake)
    out = github.actions_stats("GBeurier", "nirs4all")

    assert out["workflows"] == 5
    assert out["total_runs"] == 1234
    assert out["recent_success"] == 2
    assert out["recent_failure"] == 1
    assert out["success_rate"] == 66.7  # 2 / (2+1)
    assert out["last_conclusion"] == "success"
    # Runs must be scoped to the default branch, not all branches.
    assert seen_run_urls and all("branch=main" in u for u in seen_run_urls)


def test_actions_stats_skips_in_progress_newest_run(monkeypatch) -> None:
    """The newest run on the branch can still be in progress — most visibly the
    cockpit's own ``collect`` run reading its run list while it is itself the
    newest run on ``main``. ``last_conclusion`` must fall back to the newest
    *concluded* run rather than reporting that transient null.
    """
    workflows = (200, {"total_count": 3}, None)
    runs = (
        200,
        {
            "total_count": 103,
            "workflow_runs": [
                {"conclusion": None, "created_at": "2026-06-16T23:20:56Z"},  # newest, in-progress (self)
                {"conclusion": "success", "created_at": "2026-06-16T23:12:22Z"},
                {"conclusion": "failure", "created_at": "2026-06-16T23:00:00Z"},
            ],
        },
        None,
    )
    repo = (200, {"default_branch": "main"}, None)

    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        if "actions/workflows" in url:
            return workflows
        if "actions/runs" in url:
            return runs
        return repo

    monkeypatch.setattr(github, "get_json", _fake)
    out = github.actions_stats("GBeurier", "nirs4all-cockpit")

    # Falls through the in-progress newest run to the last concluded one.
    assert out["last_conclusion"] == "success"
    assert out["last_created_at"] == "2026-06-16T23:12:22Z"
    # The in-progress run is still excluded from the success-rate accounting.
    assert out["recent_success"] == 1
    assert out["recent_failure"] == 1
    assert out["success_rate"] == 50.0


def test_workflow_last_run_uses_latest_concluded_run_across_refs(monkeypatch) -> None:
    seen_urls: list[str] = []

    def _fake_get(url):
        seen_urls.append(url)
        if "actions/workflows/publish.yml/runs" in url:
            return (
                200,
                {
                    "workflow_runs": [
                        {
                            "conclusion": None,
                            "created_at": "2026-06-26T06:40:00Z",
                            "head_sha": "running",
                        },
                        {
                            "conclusion": "success",
                            "created_at": "2026-06-26T06:37:35Z",
                            "head_sha": "abc123",
                        },
                        {
                            "conclusion": "failure",
                            "created_at": "2026-06-25T06:37:35Z",
                            "head_sha": "old456",
                        }
                    ]
                },
                None,
            )
        raise AssertionError(url)

    monkeypatch.setattr(github, "_get", _fake_get)
    out = github.workflow_last_run("GBeurier", "nirs4all", "publish.yml")

    assert out == {
        "file": "publish.yml",
        "conclusion": "success",
        "created_at": "2026-06-26T06:37:35Z",
        "head_sha": "abc123",
    }
    assert any("actions/workflows/publish.yml/runs?per_page=20" in url for url in seen_urls)
    assert not any("branch=" in url for url in seen_urls)
