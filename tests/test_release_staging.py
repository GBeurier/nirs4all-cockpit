from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cockpit.release_staging import (
    PHASE,
    STATUS,
    StagingError,
    build_projection,
    digest,
    load_json,
    render,
    validate_projection,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "release_staging"


def inputs() -> tuple[dict, dict]:
    manifest = load_json(FIXTURES / "manifest.json")
    lock = load_json(FIXTURES / "lock.json")
    assert lock["manifest_digest"] == digest(manifest)
    return manifest, lock


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_projection_is_deterministic_public_and_non_publishing() -> None:
    manifest, lock = inputs()

    first = build_projection(manifest, lock)
    second = build_projection(copy.deepcopy(manifest), copy.deepcopy(lock))

    assert render(first) == render(second)
    assert first.phase == PHASE == "R2"
    assert first.status == STATUS == "in_progress"
    assert first.members[0].repository_url == "https://github.com/GBeurier/nirs4all-core"
    assert first.members[0].commit_url.endswith("/commit/0123456789abcdef0123456789abcdef01234567")
    serialized = render(first)
    for forbidden in ('"artifacts":', '"downloads":', "selected_workspace_path", "branch", "/dev/shm", "_worktrees"):
        assert forbidden not in serialized.lower()


def test_projection_refuses_incomplete_or_extra_lock_members() -> None:
    manifest, lock = inputs()
    lock["members"] = {}
    with pytest.raises(StagingError, match="incomplete or divergent"):
        build_projection(manifest, lock)

    manifest, lock = inputs()
    lock["members"]["unexpected"] = copy.deepcopy(lock["members"]["core"])
    with pytest.raises(StagingError, match="incomplete or divergent"):
        build_projection(manifest, lock)


def test_projection_refuses_manifest_and_release_metadata_divergence() -> None:
    manifest, lock = inputs()
    manifest["release_train"] = "different"
    with pytest.raises(StagingError, match="manifest_digest diverges"):
        build_projection(manifest, lock)

    manifest, lock = inputs()
    lock["status"] = "different"
    with pytest.raises(StagingError, match="release metadata diverges"):
        build_projection(manifest, lock)

    manifest, lock = inputs()
    manifest["status"] = "released"
    lock["manifest_digest"] = digest(manifest)
    lock["status"] = "released"
    with pytest.raises(StagingError, match="candidate/in_progress"):
        build_projection(manifest, lock)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repo_url", "file:///home/user/private.git", "public GitHub"),
        ("repo_url", "https://token@github.com/GBeurier/nirs4all-core", "public GitHub"),
        ("repo_url", "https://git.example.internal/GBeurier/nirs4all-core", "public GitHub"),
        ("repo_path", "/home/user/nirs4all-core", "local path or worktree"),
        ("repo_path", "../nirs4all-core", "local path or worktree"),
        ("selected_workspace_path", "_worktrees/RC-v1-core", "local path or worktree"),
    ],
)
def test_projection_refuses_private_urls_and_local_paths(field: str, value: str, message: str) -> None:
    manifest, lock = inputs()
    manifest["components"][0][field] = value
    lock["manifest_digest"] = digest(manifest)
    with pytest.raises(StagingError, match=message):
        build_projection(manifest, lock)


def test_projection_refuses_private_flags_and_divergent_lock_url() -> None:
    manifest, lock = inputs()
    manifest["components"][0]["private"] = True
    lock["manifest_digest"] = digest(manifest)
    with pytest.raises(StagingError, match="not explicitly public"):
        build_projection(manifest, lock)

    manifest, lock = inputs()
    lock["members"]["core"]["repo_url"] = "GBeurier/different-repo"
    with pytest.raises(StagingError, match="repo_url diverges"):
        build_projection(manifest, lock)


def test_projection_refuses_dirty_invalid_or_version_divergent_member() -> None:
    manifest, lock = inputs()
    lock["members"]["core"]["state"]["dirty"] = True
    with pytest.raises(StagingError, match="dirty"):
        build_projection(manifest, lock)

    manifest, lock = inputs()
    lock["members"]["core"]["state"]["commit"] = "0123456"
    with pytest.raises(StagingError, match="full lowercase commit SHA"):
        build_projection(manifest, lock)

    manifest, lock = inputs()
    lock["members"]["core"]["versions"]["rust"]["value"] = "1.0.1"
    with pytest.raises(StagingError, match="divergent public versions"):
        build_projection(manifest, lock)


def test_projection_refuses_local_version_source() -> None:
    manifest, lock = inputs()
    lock["members"]["core"]["versions"]["python"]["source"] = "/tmp/pyproject.toml"
    with pytest.raises(StagingError, match="local path or worktree"):
        build_projection(manifest, lock)


def test_validator_requires_exact_deterministic_projection(tmp_path: Path) -> None:
    manifest, lock = inputs()
    manifest_path = tmp_path / "manifest.json"
    lock_path = tmp_path / "lock.json"
    projection_path = tmp_path / "projection.json"
    write_json(manifest_path, manifest)
    write_json(lock_path, lock)
    projection_path.write_text(render(build_projection(manifest, lock)), encoding="utf-8")

    validate_projection(manifest_path, lock_path, projection_path)

    noncanonical = projection_path.read_text(encoding="utf-8").replace('  "phase"', '    "phase"')
    projection_path.write_text(noncanonical, encoding="utf-8")
    with pytest.raises(StagingError, match="canonical form"):
        validate_projection(manifest_path, lock_path, projection_path)


def test_cli_build_and_validate_require_explicit_inputs(tmp_path: Path) -> None:
    projection_path = tmp_path / "projection.json"
    command = [sys.executable, str(ROOT / "scripts" / "release_staging.py")]
    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "",
    }
    built = subprocess.run(
        [
            *command,
            "build",
            "--manifest",
            str(FIXTURES / "manifest.json"),
            "--lock",
            str(FIXTURES / "lock.json"),
            "--out",
            str(projection_path),
        ],
        cwd=tmp_path,
        env=clean_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    assert projection_path.is_file()

    validated = subprocess.run(
        [
            *command,
            "validate",
            "--manifest",
            str(FIXTURES / "manifest.json"),
            "--lock",
            str(FIXTURES / "lock.json"),
            "--projection",
            str(projection_path),
        ],
        cwd=tmp_path,
        env=clean_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr

    missing = subprocess.run(
        [*command, "build"],
        cwd=tmp_path,
        env=clean_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode != 0


def test_committed_public_projection_matches_staging_inputs() -> None:
    validate_projection(
        ROOT / "ops" / "release-staging" / "public-manifest.json",
        ROOT / "ops" / "release-staging" / "public-lock.json",
        ROOT / "data" / "release-staging.json",
    )


def test_direct_cli_ignores_stale_package_outside_checkout(tmp_path: Path) -> None:
    stale = tmp_path / "stale-site"
    stale_package = stale / "cockpit"
    stale_package.mkdir(parents=True)
    (stale_package / "__init__.py").write_text("", encoding="utf-8")
    (stale_package / "release_staging.py").write_text(
        'raise RuntimeError("stale cockpit package imported")\n',
        encoding="utf-8",
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(stale),
    }

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "release_staging.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "stale cockpit package imported" not in result.stderr


def test_json_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version": 1, "schema_version": 2}\n', encoding="utf-8")
    with pytest.raises(StagingError, match="duplicate JSON key"):
        load_json(path)
