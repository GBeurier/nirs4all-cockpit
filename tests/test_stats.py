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

    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        return workflows if "actions/workflows" in url else runs

    monkeypatch.setattr(github, "get_json", _fake)
    out = github.actions_stats("GBeurier", "nirs4all")

    assert out["workflows"] == 5
    assert out["total_runs"] == 1234
    assert out["recent_success"] == 2
    assert out["recent_failure"] == 1
    assert out["success_rate"] == 66.7  # 2 / (2+1)
    assert out["last_conclusion"] == "success"
