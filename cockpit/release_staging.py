"""Deterministic public R2 staging projection from an aggregation release lock.

The aggregation manifest and lock remain owned by nirs4all-ecosystem.  Cockpit
only validates their public identity fields and projects a deliberately small,
stable document.  In particular, local checkout metadata, branches, gates,
artifacts and download URLs are never copied into the public projection.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

MANIFEST_SCHEMA = "n4a.aggregation-manifest/v1"
LOCK_SCHEMA = "n4a.aggregation-lock/v1"
PROJECTION_SCHEMA = "n4a.cockpit-release-staging/v1"
PHASE = "R2"
STATUS = "in_progress"
MAX_INPUT_BYTES = 5 * 1024 * 1024

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_KEY_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_REPO_PART_RE = re.compile(r"[A-Za-z0-9_.-]+")
_TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+/-]{0,127}")
_TRAIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_VERSION_RE = re.compile(r"[0-9][A-Za-z0-9._+!-]{0,127}")


class StagingError(RuntimeError):
    """A release input or projection failed the public staging contract."""


class StagingSource(BaseModel):
    """Content identities of the two explicit release inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_sha256: str
    lock_sha256: str


class StagingMember(BaseModel):
    """Public identity of one complete locked component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    repository_url: str
    commit: str
    commit_url: str
    version: str
    version_sources: dict[str, str]
    exact_tag: str | None = None


class ReleaseStaging(BaseModel):
    """Public, non-publishing view of the R2 release train."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    phase: str
    status: str
    release_train: str
    notice: str
    source: StagingSource
    members: list[StagingMember]


def _reject_constant(value: str) -> None:
    raise StagingError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StagingError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    """Load a bounded JSON object, rejecting duplicate keys and non-finite values."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise StagingError(f"cannot read JSON input: {path}") from exc
    if size > MAX_INPUT_BYTES:
        raise StagingError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes: {path}")
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StagingError(f"invalid JSON input: {path}") from exc
    if not isinstance(raw, dict):
        raise StagingError(f"top-level JSON object required: {path}")
    return raw


def canonical_json(data: Any) -> bytes:
    """Return the aggregation-lock canonical JSON representation."""
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(data: Any) -> str:
    """Return a content digest using the aggregation-lock spelling."""
    return "sha256:" + hashlib.sha256(canonical_json(data)).hexdigest()


def render(projection: ReleaseStaging) -> str:
    """Serialize the projection in one deterministic, reviewable representation."""
    return json.dumps(
        projection.model_dump(mode="json"),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _public_repository_url(raw_url: Any, label: str) -> str:
    if not isinstance(raw_url, str) or not raw_url:
        raise StagingError(f"{label} must name a public GitHub repository")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", raw_url):
        owner, repo = raw_url.split("/", 1)
    else:
        parsed = urlparse(raw_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise StagingError(f"{label} is not a public GitHub URL")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise StagingError(f"{label} must identify exactly one GitHub repository")
        owner, repo = parts
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not _REPO_PART_RE.fullmatch(owner) or not _REPO_PART_RE.fullmatch(repo):
        raise StagingError(f"{label} contains an invalid GitHub repository name")
    return f"https://github.com/{owner}/{repo}"


def _public_repo_path(raw_path: Any, label: str) -> str:
    if not isinstance(raw_path, str) or not raw_path:
        raise StagingError(f"{label} must be a public repository name")
    if "\\" in raw_path or re.match(r"^[A-Za-z]:", raw_path):
        raise StagingError(f"{label} must not be a local path")
    path = PurePosixPath(raw_path)
    lowered = {part.lower() for part in path.parts}
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or any(part in {"", ".", ".."} for part in path.parts)
        or lowered & {"_worktrees", "worktrees", ".worktrees", "tmp", "dev", "shm"}
        or not _REPO_PART_RE.fullmatch(raw_path)
    ):
        raise StagingError(f"{label} must not be a local path or worktree")
    return raw_path


def _repository_source_path(raw_path: Any, label: str) -> str:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path or re.match(r"^[A-Za-z]:", raw_path):
        raise StagingError(f"{label} must be repository-relative")
    path = PurePosixPath(raw_path)
    lowered = {part.lower() for part in path.parts}
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or lowered & {"_worktrees", "worktrees", ".worktrees", "tmp", "dev", "shm"}
    ):
        raise StagingError(f"{label} must not contain a local path or worktree")
    return path.as_posix()


def _public_version(entry: Any, label: str) -> str:
    if not isinstance(entry, dict):
        raise StagingError(f"{label} must be an object")
    _repository_source_path(entry.get("source"), f"{label}.source")
    if entry.get("read_from") != "tracked_worktree":
        raise StagingError(f"{label} must come from a tracked source")
    value = entry.get("value")
    if isinstance(value, dict):
        value = value.get("project_version")
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise StagingError(f"{label} has no public version string")
    return value


def _validated_component_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise StagingError(f"unexpected manifest schema_version: {manifest.get('schema_version')!r}")
    release_train = manifest.get("release_train")
    if not isinstance(release_train, str) or not _TRAIN_RE.fullmatch(release_train):
        raise StagingError("manifest release_train is missing or invalid")
    if manifest.get("status") not in {"candidate", "in_progress"}:
        raise StagingError("manifest status must remain candidate/in_progress during R2 staging")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise StagingError("manifest components must be a non-empty list")

    by_key: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise StagingError(f"manifest component {index} must be an object")
        key = component.get("key")
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise StagingError(f"manifest component {index} has an invalid key")
        if key in by_key:
            raise StagingError(f"duplicate manifest component key: {key}")
        if component.get("private") is not False:
            raise StagingError(f"manifest component {key} is not explicitly public")
        repo_path = _public_repo_path(component.get("repo_path"), f"manifest component {key}.repo_path")
        selected = component.get("selected_workspace_path", repo_path)
        selected_path = _public_repo_path(selected, f"manifest component {key}.selected_workspace_path")
        if selected_path != repo_path:
            raise StagingError(f"manifest component {key} selects a worktree instead of its public repo path")
        _public_repository_url(component.get("repo_url"), f"manifest component {key}.repo_url")
        by_key[key] = component
    return by_key


def build_projection(manifest: dict[str, Any], lock: dict[str, Any]) -> ReleaseStaging:
    """Validate a complete lock and create its deterministic public R2 projection."""
    components = _validated_component_map(manifest)
    if lock.get("schema_version") != LOCK_SCHEMA or lock.get("aggregation_lock_version") != 1:
        raise StagingError("unexpected aggregation lock schema/version")
    expected_manifest_digest = digest(manifest)
    if lock.get("manifest_digest") != expected_manifest_digest:
        raise StagingError("lock manifest_digest diverges from the supplied manifest")
    if lock.get("release_train") != manifest.get("release_train") or lock.get("status") != manifest.get("status"):
        raise StagingError("lock release metadata diverges from the supplied manifest")

    verification = lock.get("verification")
    if not isinstance(verification, dict):
        raise StagingError("lock verification block is missing")
    if verification.get("private_repos_present") is not False:
        raise StagingError("lock does not attest that every repository is public")
    if verification.get("all_lockstep_groups_valid") is not True:
        raise StagingError("lockstep verification is incomplete or invalid")

    locked_members = lock.get("members")
    if not isinstance(locked_members, dict) or set(locked_members) != set(components):
        missing = sorted(set(components) - set(locked_members or {}))
        extra = sorted(set(locked_members or {}) - set(components))
        raise StagingError(f"lock members are incomplete or divergent (missing={missing}, extra={extra})")

    projected: list[StagingMember] = []
    for key in sorted(components):
        component = components[key]
        member = locked_members[key]
        if not isinstance(member, dict):
            raise StagingError(f"lock member {key} must be an object")
        if member.get("private") is not False:
            raise StagingError(f"lock member {key} is not explicitly public")
        repo_path = _public_repo_path(member.get("repo_path"), f"lock member {key}.repo_path")
        if repo_path != component["repo_path"]:
            raise StagingError(f"lock member {key} repo_path diverges from manifest")
        selected = member.get("selected_workspace_path", repo_path)
        selected_path = _public_repo_path(selected, f"lock member {key}.selected_workspace_path")
        if selected_path != repo_path:
            raise StagingError(f"lock member {key} selects a worktree instead of its public repo path")
        if member.get("optional", False) != component.get("optional", False):
            raise StagingError(f"lock member {key} optional flag diverges from manifest")

        repository_url = _public_repository_url(component.get("repo_url"), f"manifest component {key}.repo_url")
        locked_repository_url = _public_repository_url(member.get("repo_url"), f"lock member {key}.repo_url")
        if locked_repository_url != repository_url:
            raise StagingError(f"lock member {key} repo_url diverges from manifest")
        state = member.get("state")
        if not isinstance(state, dict):
            raise StagingError(f"lock member {key} has no state")
        commit = state.get("commit")
        if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
            raise StagingError(f"lock member {key} has no full lowercase commit SHA")
        if state.get("dirty") is not False:
            raise StagingError(f"lock member {key} is dirty or lacks a clean attestation")
        tag = state.get("exact_tag")
        if tag is not None and (not isinstance(tag, str) or not _TAG_RE.fullmatch(tag) or ".." in tag):
            raise StagingError(f"lock member {key} has an invalid exact tag")

        versions = member.get("versions")
        if not isinstance(versions, dict) or not versions:
            raise StagingError(f"lock member {key} has no public versions")
        public_versions = {
            source_key: _public_version(entry, f"lock member {key}.versions.{source_key}")
            for source_key, entry in sorted(versions.items())
            if isinstance(source_key, str) and _KEY_RE.fullmatch(source_key)
        }
        if len(public_versions) != len(versions):
            raise StagingError(f"lock member {key} has an invalid version source key")
        unique_versions = set(public_versions.values())
        if len(unique_versions) != 1:
            raise StagingError(f"lock member {key} has divergent public versions: {sorted(unique_versions)}")
        version = next(iter(unique_versions))

        projected.append(
            StagingMember(
                key=key,
                repository_url=repository_url,
                commit=commit,
                commit_url=f"{repository_url}/commit/{commit}",
                version=version,
                version_sources=public_versions,
                exact_tag=tag,
            )
        )

    return ReleaseStaging(
        schema_version=PROJECTION_SCHEMA,
        phase=PHASE,
        status=STATUS,
        release_train=manifest["release_train"],
        notice="R2 staging is in progress; this document asserts no release, artifact, or download publication.",
        source=StagingSource(manifest_sha256=expected_manifest_digest, lock_sha256=digest(lock)),
        members=projected,
    )


def build_from_files(manifest_path: Path, lock_path: Path) -> ReleaseStaging:
    """Build a projection from two explicitly supplied input files."""
    return build_projection(load_json(manifest_path), load_json(lock_path))


def write_projection(projection: ReleaseStaging, out_path: Path) -> None:
    """Atomically write a deterministic projection."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{out_path.name}.", dir=out_path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render(projection))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, out_path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def validate_projection(manifest_path: Path, lock_path: Path, projection_path: Path) -> None:
    """Require a checked projection to exactly match the explicit release inputs."""
    expected = build_from_files(manifest_path, lock_path)
    actual_data = load_json(projection_path)
    try:
        actual = ReleaseStaging.model_validate(actual_data)
    except Exception as exc:
        raise StagingError(f"invalid staging projection: {projection_path}") from exc
    if actual != expected:
        raise StagingError("staging projection diverges from the supplied manifest/lock")
    try:
        actual_text = projection_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StagingError(f"cannot read staging projection: {projection_path}") from exc
    if actual_text != render(expected):
        raise StagingError("staging projection is not in deterministic canonical form")
