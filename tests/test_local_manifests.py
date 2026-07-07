from __future__ import annotations

from pathlib import Path

from cockpit.collect import local_manifests


def test_manifest_reader_prefers_public_default_branch_over_stale_local(
    monkeypatch,
    tmp_path: Path,
) -> None:
    local_repo = tmp_path / "nirs4all-ui"
    local_repo.mkdir()
    (local_repo / "package.json").write_text('{"version":"0.1.4"}\n', encoding="utf-8")

    monkeypatch.setattr(local_manifests, "SIBLINGS_ROOT", tmp_path)
    monkeypatch.setattr(local_manifests.github, "default_branch", lambda owner, repo: "main")  # noqa: ARG005
    monkeypatch.setattr(
        local_manifests,
        "_read_raw_text",
        lambda url: '{"version":"0.1.7"}\n',
    )

    version = local_manifests.read_manifest_version(
        owner="GBeurier",
        repo="nirs4all-ui",
        strategy="npm_package_json",
        path="package.json",
    )

    assert version == "0.1.7"


def test_manifest_reader_falls_back_to_local_checkout_when_public_raw_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    local_repo = tmp_path / "nirs4all-ui"
    local_repo.mkdir()
    (local_repo / "package.json").write_text('{"version":"0.1.7"}\n', encoding="utf-8")

    monkeypatch.setattr(local_manifests, "SIBLINGS_ROOT", tmp_path)
    monkeypatch.setattr(local_manifests.github, "default_branch", lambda owner, repo: "main")  # noqa: ARG005
    monkeypatch.setattr(local_manifests, "_read_raw_text", lambda url: None)

    version = local_manifests.read_manifest_version(
        owner="GBeurier",
        repo="nirs4all-ui",
        strategy="npm_package_json",
        path="package.json",
    )

    assert version == "0.1.7"
