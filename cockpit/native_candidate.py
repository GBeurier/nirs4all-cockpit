"""Deterministic public-safe projection of the local native-backend candidate.

Unlike the canonical aggregation lock, this document is explicitly not release
authority.  It exposes exact candidate identities, qualified capability
evidence and narrowly scoped immutable publication receipts recorded by the
migration ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "n4a.native-candidate-staging/v1"
LEDGER_SCHEMA = "n4a.migration-work-ledger/v1"
LEDGER_PATH = "docs/contracts/release/migration-work-ledger.yaml"
GOVERNANCE_REPOSITORY_URL = "https://github.com/GBeurier/nirs4all-ecosystem"
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
TREE_RE = COMMIT_RE
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+|[-+][0-9A-Za-z.-]+)?")
PROJECTED_WORK_ITEM_STATES = {
    "API-001": "complete_local_code_release_hold",
    "API-004": "complete_local_native_full_transfer_plugin_finetune_refused",
    "API-005": "complete_local_by_executable_preflight_refusal",
    "CAP-001": "complete",
    "DAG-001": "complete_local_code_release_hold",
    "DOC-001": "complete_local_docs_release_hold",
    "GATE-001": "complete_local_linux_functional_release_hold",
    "INST-001": "complete_with_bounded_windows_installed_path_waiver",
    "PERF-002": "complete_v1_bounded_measurement_sustained_budgets_deferred_post_v1",
    "RC-001": "complete_existing_evidence_reconciled",
    "REL-003": "complete_local_code_release_hold",
    "ROB-001": "complete_local_functional_non_crash_non_blocking",
    "SOAK-001": "complete_functional_campaign_passed",
    "STU-006": "complete_local_code_external_release_hold",
    "UI-001": "complete_registry_publication_downstream_product_hold",
    "WEB-001": "complete_local_code_release_hold",
    "WEBREL-001": "complete_local_staging_publication_hold",
}
PROJECTED_COMPONENT_KEYS = {
    "benchmarks",
    "core",
    "dag_ml",
    "dag_ml_data",
    "datasets",
    "formats",
    "io",
    "methods",
    "python",
    "providers",
    "repository",
    "studio",
    "tools",
    "ui",
    "web",
}


class CandidateError(RuntimeError):
    """The candidate ledger or public projection is incomplete or unsafe."""


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise CandidateError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def _text_at(repo: Path, commit: str, path: str) -> str:
    return _git(repo, "show", f"{commit}:{path}").decode("utf-8")


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _version_at(repo: Path, commit: str, path: str, pattern: str) -> str:
    match = re.search(pattern, _text_at(repo, commit, path), flags=re.MULTILINE)
    if match is None or not VERSION_RE.fullmatch(match.group(1)):
        raise CandidateError(f"cannot resolve a public version from {repo.name}@{commit}:{path}")
    return match.group(1)


def _identity(
    evidence: dict[str, Any],
    *,
    key: str,
    name: str,
    repository: str,
    commit_field: str = "commit",
    tree_field: str = "tree",
    version: str,
    detail_versions: dict[str, str] | None = None,
    publication: str = "published",
    artifacts: list[dict[str, Any]] | None = None,
    registry_urls: list[str] | None = None,
) -> dict[str, Any]:
    commit = evidence.get(commit_field)
    tree = evidence.get(tree_field)
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise CandidateError(f"{key}: missing exact candidate commit")
    if not isinstance(tree, str) or not TREE_RE.fullmatch(tree):
        raise CandidateError(f"{key}: missing exact candidate tree")
    if not VERSION_RE.fullmatch(version):
        raise CandidateError(f"{key}: invalid candidate version")
    return {
        "key": key,
        "name": name,
        "repository_url": f"https://github.com/GBeurier/{repository}",
        "commit": commit,
        "tree": tree,
        "version": version,
        "detail_versions": detail_versions or {},
        "qualification": evidence.get("evidence_status"),
        "publication": publication,
        "artifacts": artifacts or [],
        "registry_urls": registry_urls or [],
    }


def _governance_identity(evidence: dict[str, Any], *, key: str) -> dict[str, str]:
    """Project one local governance witness without implying publication."""
    commit = evidence.get("commit")
    tree = evidence.get("tree")
    status = evidence.get("evidence_status")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise CandidateError(f"{key}: missing exact governance commit")
    if not isinstance(tree, str) or not TREE_RE.fullmatch(tree):
        raise CandidateError(f"{key}: missing exact governance tree")
    if not isinstance(status, str) or not status:
        raise CandidateError(f"{key}: missing governance evidence status")
    return {"commit": commit, "tree": tree, "status": status}


def _project_work_item_states(ledger: dict[str, Any]) -> dict[str, str]:
    """Expose only selected final states, without leaking local ledger details."""
    work_items = ledger.get("work_items")
    if not isinstance(work_items, list):
        raise CandidateError("migration work items are missing")
    observed = {
        item.get("id"): item.get("state")
        for item in work_items
        if isinstance(item, dict) and item.get("id") in PROJECTED_WORK_ITEM_STATES
    }
    if observed != PROJECTED_WORK_ITEM_STATES:
        raise CandidateError("selected final work-item states diverge")
    return dict(sorted(observed.items()))


def _project_release_train(evidence: dict[str, Any]) -> dict[str, Any]:
    """Project the distinct product candidates without implying a stable release."""
    sequence = evidence.get("product_release_sequence")
    if not isinstance(sequence, dict):
        raise CandidateError("product release sequence is missing")
    if sequence.get("status") not in {
        "r1_r2_r3_distinct_published_releases_r4_candidate_held",
        "r1_r2_r3_r4_distinct_published_releases",
    }:
        raise CandidateError("product release sequence does not record the published Python train")
    if sequence.get("required_order") != ("r1_0_13_0_then_r2_1_0_0_rc_1_then_r3_1_0_0_rc_2_then_r4_1_0_0"):
        raise CandidateError("product release order diverges")

    raw_milestones = sequence.get("milestones")
    if not isinstance(raw_milestones, dict) or set(raw_milestones) != {"r1", "r2", "r3", "r4"}:
        raise CandidateError("product release milestones are incomplete")
    engine_profiles = {
        "r1": ("legacy", "fastapi_desktop_with_explicit_rust_sidecar_qualification", "legacy"),
        "r2": (
            "native",
            "dag_ml_default_explicit_opt_in_legacy_fallback_packaged",
            "native_with_explicit_legacy_opt_in",
        ),
        "r3": (
            "native_fail_closed",
            "rust_only_fail_closed_cpython_plugin_host_only",
            "native_fail_closed_rust_only",
        ),
    }
    milestones: dict[str, Any] = {}
    for key, (default_engine, control_plane, public_engine) in engine_profiles.items():
        raw = raw_milestones.get(key)
        if not isinstance(raw, dict):
            raise CandidateError(f"{key}: product milestone is missing")
        if raw.get("default_engine") != default_engine or raw.get("studio_control_plane") != control_plane:
            raise CandidateError(f"{key}: product runtime profile diverges")
        for field in ("commit", "tree", "studio_commit", "studio_tree"):
            if not COMMIT_RE.fullmatch(raw.get(field, "")):
                raise CandidateError(f"{key}: malformed {field}")
        for field in ("version", "studio_version"):
            if not VERSION_RE.fullmatch(raw.get(field, "")):
                raise CandidateError(f"{key}: malformed {field}")
        milestones[key] = {
            "python_version": raw["version"],
            "python_commit": raw["commit"],
            "python_tree": raw["tree"],
            "studio_version": raw["studio_version"],
            "studio_commit": raw["studio_commit"],
            "studio_tree": raw["studio_tree"],
            "default_engine": public_engine,
        }

    r1 = raw_milestones["r1"]
    if r1.get("publication_status") != "published_pypi_and_ghcr_release_workflow_green":
        raise CandidateError("R1 publication receipt is incomplete")
    if not COMMIT_RE.fullmatch(r1.get("publication_repair_commit", "")) or not TREE_RE.fullmatch(
        r1.get("publication_repair_tree", "")
    ):
        raise CandidateError("R1 publication repair identity is incomplete")
    if (
        r1.get("publication_run") != 33753479548
        or r1.get("pypi_published") is not True
        or r1.get("ghcr_published") is not True
    ):
        raise CandidateError("R1 PyPI/GHCR publication receipt is incomplete")
    milestones["r1"].update(
        {
            "publication": "pypi_and_ghcr",
            "publication_repair_commit": r1["publication_repair_commit"],
            "publication_repair_tree": r1["publication_repair_tree"],
            "publication_workflow_run": r1["publication_run"],
        }
    )
    expected_runs = {"r2": 33868949671, "r3": 33873060692}
    for key, expected_run in expected_runs.items():
        raw = raw_milestones[key]
        required = {
            "publication_workflow_run": raw.get("publication_run"),
            "release_id": raw.get("release_id"),
            "release_url": raw.get("release_url"),
            "tag_object": raw.get("release_tag_object"),
            "wheel_sha256": raw.get("wheel_sha256"),
            "sdist_sha256": raw.get("sdist_sha256"),
            "record_sha256": raw.get("record_sha256"),
            "installed_manifest_sha256": raw.get("installed_manifest_sha256"),
            "ghcr_oci_index": raw.get("ghcr_oci_index"),
        }
        if (
            raw.get("artifact_status") != "published_pypi_and_ghcr_release_workflow_green"
            or raw.get("publication_run") != expected_run
            or raw.get("pypi_published") is not True
            or raw.get("ghcr_published") is not True
            or not isinstance(required["release_id"], int)
            or not re.fullmatch(
                r"https://github\.com/GBeurier/nirs4all/releases/tag/[0-9A-Za-z.-]+",
                required["release_url"] or "",
            )
            or not COMMIT_RE.fullmatch(required["tag_object"] or "")
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", required[field] or "")
                for field in ("wheel_sha256", "sdist_sha256", "record_sha256", "installed_manifest_sha256")
            )
            or not SHA256_RE.fullmatch(required["ghcr_oci_index"] or "")
        ):
            raise CandidateError(f"{key.upper()} PyPI/GHCR publication receipt is incomplete")
        milestones[key].update({"publication": "pypi_and_ghcr", **required})
    r4 = raw_milestones["r4"]
    python = evidence.get("python_strict_profile")
    expected_r4_statuses = {
        "unpublished_candidate_no_public_receipt",
        "published_pypi_and_ghcr_release_workflow_green",
    }
    for field in ("commit", "tree", "direct_parent_documentation_commit"):
        if not COMMIT_RE.fullmatch(r4.get(field, "")):
            raise CandidateError(f"r4: malformed {field}")
    r4_status = r4.get("status")
    if r4.get("version") != "1.0.0" or r4_status not in expected_r4_statuses:
        raise CandidateError("R4 must be an exact candidate or published release")
    if (
        not isinstance(python, dict)
        or python.get("r4_documentation_commit") != r4["direct_parent_documentation_commit"]
        or not TREE_RE.fullmatch(python.get("r4_documentation_tree", ""))
    ):
        raise CandidateError("R4 documentation identity diverges")
    milestones["r4"] = {
        "python_version": "1.0.0",
        "python_commit": r4["commit"],
        "python_tree": r4["tree"],
        "documentation_commit": r4["direct_parent_documentation_commit"],
        "documentation_tree": python["r4_documentation_tree"],
        "status": r4_status,
    }
    if r4_status == "published_pypi_and_ghcr_release_workflow_green":
        required = {
            "publication_workflow_run": r4.get("publication_run"),
            "release_id": r4.get("release_id"),
            "release_url": r4.get("release_url"),
            "tag_object": r4.get("release_tag_object"),
            "wheel_sha256": r4.get("wheel_sha256"),
            "sdist_sha256": r4.get("sdist_sha256"),
            "record_sha256": r4.get("record_sha256"),
            "installed_manifest_sha256": r4.get("installed_manifest_sha256"),
            "ghcr_oci_index": r4.get("ghcr_oci_index"),
        }
        if (
            not isinstance(required["publication_workflow_run"], int)
            or not isinstance(required["release_id"], int)
            or not COMMIT_RE.fullmatch(required["tag_object"] or "")
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", required[field] or "")
                for field in ("wheel_sha256", "sdist_sha256", "record_sha256", "installed_manifest_sha256")
            )
            or not SHA256_RE.fullmatch(required["ghcr_oci_index"] or "")
        ):
            raise CandidateError("R4 publication receipt is incomplete")
        milestones["r4"].update({"publication": "pypi_and_ghcr", **required})
    train_published = r4_status == "published_pypi_and_ghcr_release_workflow_green"
    return {
        "status": (
            "r1_r2_r3_r4_distinct_published_releases"
            if train_published
            else "r1_r2_r3_distinct_published_releases_r4_candidate_held"
        ),
        "publication": (
            "python_r1_r2_r3_r4_and_studio_published"
            if train_published
            else "python_r1_r2_r3_and_studio_published_r4_held"
        ),
        "milestones": milestones,
    }


def build_projection(governance_repo: Path, governance_commit: str, workspace_root: Path) -> dict[str, Any]:
    """Build a deterministic staging projection from one exact ledger commit."""
    if not COMMIT_RE.fullmatch(governance_commit):
        raise CandidateError("governance commit must be a full lowercase SHA")
    raw_ledger = _git(governance_repo, "show", f"{governance_commit}:{LEDGER_PATH}")
    try:
        ledger = yaml.safe_load(raw_ledger)
    except yaml.YAMLError as exc:
        raise CandidateError("invalid migration ledger YAML") from exc
    if not isinstance(ledger, dict) or ledger.get("schema_version") != LEDGER_SCHEMA:
        raise CandidateError("unexpected migration ledger schema")
    evidence = ledger.get("current_candidate_evidence")
    if not isinstance(evidence, dict):
        raise CandidateError("candidate evidence block is missing")
    allowed_release_states = {
        (
            "no_go",
            "studio_0_11_0_repository_0_1_12_providers_0_2_11_r1_r2_r3_published_r4_pending_no_go",
            "no_go",
        ),
        (
            "go",
            "native_v1_r1_r2_r3_r4_studio_web_repository_providers_published",
            "go",
        ),
    }
    release_state = (
        evidence.get("promotion_status"),
        evidence.get("publication_status"),
        evidence.get("release_gate_status"),
    )
    if release_state not in allowed_release_states:
        raise CandidateError("release evidence has an unsupported promotion state")
    canonical_lock = evidence.get("canonical_release_lock")
    if not isinstance(canonical_lock, dict) or not isinstance(canonical_lock.get("updated"), bool):
        raise CandidateError("canonical release lock state is missing")

    methods = evidence["methods"]
    dag_data = evidence["dag_ml_data"]
    dag_ml = evidence["dag_ml"]
    core = evidence["core"]
    formats = evidence["formats"]
    io = evidence["io"]
    datasets = evidence["datasets"]
    tools = evidence["tools"]
    python = evidence["python_strict_profile"]
    studio = evidence["studio"]
    web = evidence["web"]
    ui = evidence["ui"]
    benchmarks = evidence["benchmarks"]
    providers = evidence["providers"]
    repository = evidence["repository"]
    capability_governance = evidence["capability_governance"]
    ownership_governance = evidence["ownership_governance"]
    final_release = evidence.get("promotion_status") == "go"

    python_version = _version_at(
        workspace_root / "nirs4all",
        python["commit"],
        "nirs4all/__init__.py",
        r'^__version__\s*=\s*"([^"]+)"',
    )
    studio_version = _version_at(
        workspace_root / "nirs4all-studio",
        studio["candidate_commit"],
        "package.json",
        r'^\s*"version"\s*:\s*"([^"]+)"',
    )
    web_version = _version_at(
        workspace_root / "nirs4all-web",
        web["candidate_commit"],
        "web-app/package.json",
        r'^\s*"version"\s*:\s*"([^"]+)"',
    )
    ui_version = _version_at(
        workspace_root / "nirs4all-ui",
        ui["commit"],
        "package.json",
        r'^\s*"version"\s*:\s*"([^"]+)"',
    )
    if ui_version != ui.get("version"):
        raise CandidateError("ui: ledger version differs from the selected source")
    if not _is_ancestor(
        workspace_root / "nirs4all-studio",
        ui.get("studio_consumer_commit", ""),
        studio.get("candidate_commit", ""),
    ):
        raise CandidateError("ui: Studio candidate does not descend from the qualified UI consumer")
    if ui.get("web_consumer_commit") != web.get("candidate_commit"):
        raise CandidateError("ui: Web consumer does not match the selected candidate")
    if not re.fullmatch(r"[0-9a-f]{64}", ui.get("tarball_sha256", "")):
        raise CandidateError("ui: local tarball evidence is incomplete")
    registry_ui_version = ui.get("registry_latest_version")
    if not isinstance(registry_ui_version, str) or not VERSION_RE.fullmatch(registry_ui_version):
        raise CandidateError("ui: observed registry version is invalid")
    benchmarks_version = _version_at(
        workspace_root / "nirs4all-benchmarks",
        benchmarks["commit"],
        "src/nirs4all_benchmarks/version.py",
        r'^__version__\s*=\s*"([^"]+)"',
    )
    providers_version = _version_at(
        workspace_root / "nirs4all-providers",
        providers["qualification_commit"],
        "src/nirs4all_providers/__init__.py",
        r'^__version__\s*=\s*"([^"]+)"',
    )
    repository_version = _version_at(
        workspace_root / "nirs4all-repository",
        repository["qualification_commit"],
        "src/nirs4all_repository/_version.py",
        r'^__version__\s*=\s*"([^"]+)"',
    )

    components = [
        _identity(
            methods,
            key="methods",
            name="nirs4all-methods",
            repository="nirs4all-methods",
            version=methods["version"],
            detail_versions={"c_abi": methods["c_abi_version"], "rust_binding": methods["rust_binding_version"]},
            artifacts=[
                {
                    "id": "source_tarball",
                    "filename": "nirs4all-methods-1.0.16-src.tar.gz",
                    "size": 22282689,
                    "sha256": "f8bb9259bdfcaac8b071d93ec6b1abebf75e5015d7f6d25fa605c0da24585d08",
                },
                {
                    "id": "sbom",
                    "filename": "nirs4all-methods-1.0.16.cdx.json",
                    "size": 105658,
                    "sha256": "8a580c8a78fbdcac70a01bc39b4679750e8e626d2f5de93220d081adfaf74bed",
                },
                {
                    "id": "matlab_octave",
                    "filename": "nirs4all-methods-matlab-octave-1.0.16.zip",
                    "size": 91143,
                    "sha256": "ca60c80b574663fc104dfac56bb0a680e6aac4111c037fbdc6a950b17e3f7934",
                },
                {
                    "id": "r_n4m",
                    "filename": "n4m_1.0.16.tar.gz",
                    "size": 859946,
                    "sha256": "29d8b7dc63d47fb8c9617a2b39d44bb43d71b68811ad4b14fc5d61bc98348c2d",
                },
                {
                    "id": "r_pls4all",
                    "filename": "pls4all_1.0.16.tar.gz",
                    "size": 856136,
                    "sha256": "e90005fdc656119de7b9c7404d2d3d2e6286a385a16494a481463bffd3a27ac6",
                },
            ],
            registry_urls=[
                methods["methods_release_url"],
                methods["methods_registries"]["npm"],
                methods["methods_registries"]["pypi_pls4all"],
                methods["methods_registries"]["pypi_nirs4all_methods"],
            ],
        ),
        _identity(
            dag_data, key="dag_ml_data", name="dag-ml-data", repository="dag-ml-data", version=dag_data["version"]
        ),
        _identity(dag_ml, key="dag_ml", name="dag-ml", repository="dag-ml", version=dag_ml["version"]),
        _identity(core, key="core", name="nirs4all-core", repository="nirs4all-core", version=core["version"]),
        _identity(
            formats, key="formats", name="nirs4all-formats", repository="nirs4all-formats", version=formats["version"]
        ),
        _identity(io, key="io", name="nirs4all-io", repository="nirs4all-io", version=io["version"]),
        _identity(
            datasets,
            key="datasets",
            name="nirs4all-datasets",
            repository="nirs4all-datasets",
            version=datasets["version"],
        ),
        _identity(tools, key="tools", name="nirs4all-tools", repository="nirs4all-tools", version=tools["version"]),
        _identity(python, key="python", name="nirs4all", repository="nirs4all", version=python_version),
        _identity(
            providers,
            key="providers",
            name="nirs4all-providers",
            repository="nirs4all-providers",
            commit_field="qualification_commit",
            tree_field="qualification_tree",
            version=providers_version,
            publication="published",
            artifacts=[
                {
                    "id": "wheel",
                    "filename": "nirs4all_providers-0.2.11-py3-none-any.whl",
                    "sha256": providers["wheel_sha256"],
                    "size": providers["wheel_size"],
                },
                {
                    "id": "sdist",
                    "filename": "nirs4all_providers-0.2.11.tar.gz",
                    "sha256": providers["sdist_sha256"],
                    "size": providers["sdist_size"],
                },
            ],
            registry_urls=[providers["release_url"], providers["pypi_url"]],
        ),
        _identity(
            repository,
            key="repository",
            name="nirs4all-repository",
            repository="nirs4all-repository",
            commit_field="qualification_commit",
            tree_field="qualification_tree",
            version=repository_version,
            publication="published",
            artifacts=[
                {
                    "id": "wheel",
                    "filename": "nirs4all_repository-0.1.12-py3-none-any.whl",
                    "sha256": repository["wheel_sha256"],
                    "size": repository["wheel_size"],
                },
                {
                    "id": "sdist",
                    "filename": "nirs4all_repository-0.1.12.tar.gz",
                    "sha256": repository["sdist_sha256"],
                    "size": repository["sdist_size"],
                },
            ],
            registry_urls=[repository["release_url"], repository["pypi_url"]],
        ),
        _identity(
            studio,
            key="studio",
            name="nirs4all-studio",
            repository="nirs4all-studio",
            commit_field="candidate_commit",
            tree_field="candidate_tree",
            version=studio_version,
            artifacts=[
                {
                    "id": "all_in_one_linux_x64",
                    "sha256": "f415acd2b05cce6d26b49a3fd59b506c53a57e037473171d86df8210062e6f0a",
                },
                {
                    "id": "all_in_one_macos_arm64",
                    "sha256": "e042b06bece4d118b6c5108f791185535ea67a91c5ca239c540bf843238b388a",
                },
                {
                    "id": "all_in_one_macos_x64",
                    "sha256": "13fe38ba625e9288adedb6bb8e058b03ff14ebf09a8b904b929251f3997f0f64",
                },
                {
                    "id": "all_in_one_windows_x64",
                    "sha256": "8091ca079236581a0fa8620ee24e43059094cffd85bc5b6f87e43de9de22159d",
                },
                {"id": "windows_nsis", "sha256": "e1810f3b2b4db329e9043f0d6fe346d8d78cca4609b39fccba7624e9b6288cf6"},
                {"id": "ghcr_image", "sha256": "06db667567fcc8d3a0cc728024b28ddb2d82cdb988c2204a7c6c448f95fb6489"},
            ],
            registry_urls=[studio["publication_release_url"]],
        ),
        _identity(
            web,
            key="web",
            name="nirs4all-web",
            repository="nirs4all-web",
            commit_field="candidate_commit",
            tree_field="candidate_tree",
            version=web_version,
        ),
        _identity(
            ui,
            key="ui",
            name="nirs4all-ui",
            repository="nirs4all-ui",
            version=ui_version,
            detail_versions={"registry_latest_observed": registry_ui_version},
        ),
        _identity(
            benchmarks,
            key="benchmarks",
            name="nirs4all-benchmarks",
            repository="nirs4all-benchmarks",
            version=benchmarks_version,
        ),
    ]

    docs = evidence["methods_documentation"]
    capabilities = [
        {
            "key": "native_pipeline_v2",
            "label": "SNV → Savitzky–Golay → PLS, Archive V2 et predict",
            "status": "qualified_local",
            "surfaces": ["methods", "dag_ml", "core", "python", "studio", "web"],
            "limits": (
                "Profil borné SNV ddof=0, SG interp fenêtre 11/polynôme 3, PLS; aucune généralisation à toute l’API."
            ),
        },
        {
            "key": "archive_v1_replay",
            "label": "Relecture Archive V1 historique",
            "status": "qualified_local",
            "surfaces": ["dag_ml", "core", "studio", "web"],
            "limits": "Compatibilité de lecture/rejeu; aucune réécriture en place.",
        },
        {
            "key": "native_hpo_resume",
            "label": "HPO Methods natif, reprise et export/rejeu",
            "status": "qualified_bounded",
            "surfaces": ["methods", "dag_ml", "python"],
            "limits": "Témoin Python PLS random 2→4 essais; l’API publique N4MOPT de reprise n’est pas annoncée.",
        },
        {
            "key": "dataset_package_handoff",
            "label": "DatasetPackage Rust vers plan de données",
            "status": "qualified_local",
            "surfaces": ["io"],
            "limits": "IO 0.1.14 et dag-ml-data 0.2.10 sont publiés; les matrices externes restent requises.",
        },
        {
            "key": "conformal",
            "label": "Conformal natif multi-cible et Archive V2",
            "status": "qualified_local",
            "surfaces": ["dag_ml", "core", "studio"],
            "limits": (
                "Flux local DAG/Core/Studio qualifié; aucune promesse Web ni "
                "matrice conformal générale de l’API Python."
            ),
        },
        {
            "key": "studio_control_plane",
            "label": "Plan de contrôle Studio",
            "status": "qualified_local",
            "surfaces": ["studio"],
            "limits": (
                "HTTP, contrôle, store, jobs, scheduler et WebSocket en Rust; "
                "Studio 0.11.0 est publié sur Python R3 et Methods 1.0.16; "
                "les signatures restent explicitement waived."
            ),
        },
        {
            "key": "embedded_cpython_plugins",
            "label": "Interopérabilité bibliothèques Python",
            "status": "qualified_bounded",
            "surfaces": ["studio", "python"],
            "limits": (
                "CPython embarqué limité à un host bibliothèque/plugin stdio "
                "attesté; aucun serveur HTTP, scheduler, store ou fallback Python."
            ),
        },
        {
            "key": "web_wasm",
            "label": "Web client-side WASM",
            "status": "qualified_local",
            "surfaces": ["web", "core", "methods"],
            "limits": "Rejeu Archive V1/V2 qualifié sur les WASM finaux; aucune UI conformal n’est annoncée.",
        },
        {
            "key": "python_retrain_modes",
            "label": "Retrain Python R2",
            "status": "qualified_bounded",
            "surfaces": ["python"],
            "limits": (
                "Full omis route vers DAG-ML natif; transfer exige le plugin Python déclaré; "
                "finetune et options inconnues sont refusés avant accès aux données."
            ),
        },
        {
            "key": "python_explain_generate",
            "label": "Explain et generate Python",
            "status": "qualified_bounded",
            "surfaces": ["python"],
            "limits": (
                "Préflight exécutable qualifié: native et plugin non installé refusent sans effet; "
                "implémentations historiques accessibles seulement par engine=legacy explicite."
            ),
        },
        {
            "key": "full_python_api",
            "label": "Matrice API Python bornée",
            "status": "qualified_bounded",
            "surfaces": ["python"],
            "limits": (
                "Les surfaces promises run/predict/session/cache/conformal/robustness et orchestration "
                "sont qualifiées localement; transfer reste lié au plugin, et les capacités absentes refusent."
            ),
        },
        {
            "key": "four_surface_performance",
            "label": "Performance sur le train courant",
            "status": "bounded_v1_functional_soak_passed",
            "surfaces": ["benchmarks"],
            "limits": (
                "Le soak fonctionnel V1 passe sans crash ni fuite observée; la campagne soutenue, "
                "les budgets figés et les métriques multi-plateformes sont différés post-V1."
            ),
        },
    ]

    projection: dict[str, Any] = {
        "schema_version": SCHEMA,
        "source": {
            "repository_url": GOVERNANCE_REPOSITORY_URL,
            "commit": governance_commit,
            "tree": _git(governance_repo, "rev-parse", f"{governance_commit}^{{tree}}").decode().strip(),
            "ledger_path": LEDGER_PATH,
            "ledger_sha256": "sha256:" + hashlib.sha256(raw_ledger).hexdigest(),
        },
        "release": {
            "label": "nirs4all V1 native product train",
            "status": "go" if final_release else "no_go",
            "publication": "published" if final_release else "release_finalization_pending",
            "canonical_lock_updated": canonical_lock["updated"],
            "downloads_enabled": final_release,
            "registry_links_enabled": True,
            "notice": (
                "Train V1 natif publié; Python R1/R2/R3/R4, Studio 0.11.0, Web 0.1.10, "
                "Repository 0.1.12 et Providers 0.2.11 disposent de reçus publics. Les installateurs "
                "Studio restent non signés/non notarized et le chemin Windows NSIS installé est couvert "
                "par des waivers bornés, pas par de faux reçus de réussite."
                if final_release
                else "Publication produit achevée sauf Python R4; la promotion V1 reste NO-GO."
            ),
        },
        "release_train": _project_release_train(evidence),
        "architecture": {
            "studio_control_plane": "rust_only",
            "embedded_cpython": "bounded_attested_stdio_library_plugin_host",
            "python_forbidden_roles": ["http_server", "scheduler", "store", "listener", "fallback"],
            "web_runtime": "client_side_wasm_only",
            "legacy_profile": "explicit_engine_legacy_through_r4_unreachable_from_strict_product_paths",
        },
        "cutover_observability": {
            "work_item": "CUT-002",
            "legacy_activation": "explicit_legacy_or_dual_only",
            "warning_format": "stable_structured_json",
            "counter_scope": python["legacy_usage_counter_scope"],
            "counter_opt_in": True,
            "strict_paths_silent": True,
            "implicit_fallback": False,
            "evidence_commit": python["legacy_usage_observability_commit"],
        },
        "governance": {
            "capability_inventory": _governance_identity(capability_governance, key="capability_governance"),
            "ownership": _governance_identity(ownership_governance, key="ownership_governance"),
        },
        "performance": {
            "evidence_mode": "v1_bounded_functional_soak_passed_sustained_budgets_deferred",
            "contract": benchmarks["performance_contract"],
            "report_scope": "python_3_cycles_and_studio_30_readiness_repetitions",
            "representative_soak_required": False,
            "duration_seconds": benchmarks["soak_duration_seconds"],
            "python_checks": benchmarks["soak_python_checks_passed"],
            "studio_checks": benchmarks["soak_studio_checks_passed"],
            "report_sha256": benchmarks["soak_report_sha256"],
            "budgets_frozen": False,
            "sustained_campaign_deferred_post_v1": True,
            "release_eligible": True,
        },
        "functional_non_crash": {
            "work_item": "SOAK-001",
            "status": "complete_functional_campaign_passed",
            "scope": "python_21_of_21_and_studio_90_of_90_checks",
            "release_gate": True,
        },
        "work_item_states": _project_work_item_states(ledger),
        "migration": {
            "tool": "nirs4all-tools",
            "version": tools["version"],
            "policy": "copy_on_write_dry_run_resume_and_verify",
            "exit_codes": [
                {"code": 0, "meaning": "migration complète sans avertissement"},
                {"code": 10, "meaning": "migration avec avertissements ou éléments opaques préservés"},
                {"code": 20, "meaning": "entrée non prise en charge; aucune fausse réussite"},
            ],
        },
        "methods_documentation": {
            "status": "published_with_v1_train",
            "commit": docs["commit"],
            "tree": docs["tree"],
            "mapped_pages": docs["mapped_documentation_pages"],
            "bibliography_entries": docs["bibliography_entries"],
            "historical_entries_preserved": 73,
            "reviewed_entries_added": 15,
        },
        "components": sorted(components, key=lambda item: item["key"]),
        "capabilities": capabilities,
        "holds": [
            (
                "Waiver: Studio 0.11.0 installers are unsigned and non-notarized; SHA-256 receipts compensate "
                "but do not suppress SmartScreen or Gatekeeper warnings."
            ),
            (
                "Waiver: Windows all-in-one self-update passed, while installed NSIS update/uninstall and "
                "independent manual desktop smoke remain unclaimed."
            ),
            "Post-V1: sustained performance budgets and a longer cross-platform soak campaign remain deferred.",
        ],
    }
    validate_projection(projection)
    return projection


def render(projection: dict[str, Any]) -> str:
    """Render a stable byte representation shared by Org and Cockpit."""
    return json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def validate_projection(projection: Any) -> None:
    """Fail closed on publication claims, unsafe URLs or malformed identities."""
    if not isinstance(projection, dict) or projection.get("schema_version") != SCHEMA:
        raise CandidateError("unexpected candidate projection schema")
    source = projection.get("source")
    release = projection.get("release")
    if not isinstance(source, dict) or not COMMIT_RE.fullmatch(source.get("commit", "")):
        raise CandidateError("candidate source commit is invalid")
    if not TREE_RE.fullmatch(source.get("tree", "")) or not SHA256_RE.fullmatch(source.get("ledger_sha256", "")):
        raise CandidateError("candidate source identity is incomplete")
    if source.get("repository_url") != GOVERNANCE_REPOSITORY_URL or source.get("ledger_path") != LEDGER_PATH:
        raise CandidateError("candidate source is not the public governance ledger")
    if not isinstance(release, dict) or set(release) != {
        "label",
        "status",
        "publication",
        "canonical_lock_updated",
        "downloads_enabled",
        "registry_links_enabled",
        "notice",
    }:
        raise CandidateError("release projection is malformed")
    final_release = release.get("status") == "go"
    if (
        release.get("label") != "nirs4all V1 native product train"
        or release.get("publication") != ("published" if final_release else "release_finalization_pending")
        or release.get("downloads_enabled") is not final_release
        or release.get("registry_links_enabled") is not True
        or not isinstance(release.get("canonical_lock_updated"), bool)
        or not isinstance(release.get("notice"), str)
        or not release["notice"]
    ):
        raise CandidateError("release projection status diverges")
    release_train = projection.get("release_train")
    expected_train = (
        ("r1_r2_r3_r4_distinct_published_releases", "python_r1_r2_r3_r4_and_studio_published")
        if final_release
        else ("r1_r2_r3_distinct_published_releases_r4_candidate_held", "python_r1_r2_r3_and_studio_published_r4_held")
    )
    if (
        not isinstance(release_train, dict)
        or (release_train.get("status"), release_train.get("publication")) != expected_train
    ):
        raise CandidateError("release train publication state diverges")
    milestones = release_train.get("milestones")
    if not isinstance(milestones, dict) or set(milestones) != {"r1", "r2", "r3", "r4"}:
        raise CandidateError("candidate release milestones are incomplete")
    expected_engines = {
        "r1": "legacy",
        "r2": "native_with_explicit_legacy_opt_in",
        "r3": "native_fail_closed_rust_only",
    }
    for key, expected_engine in expected_engines.items():
        milestone = milestones.get(key)
        if not isinstance(milestone, dict) or milestone.get("default_engine") != expected_engine:
            raise CandidateError(f"{key}: candidate runtime profile diverges")
        if any(
            not COMMIT_RE.fullmatch(milestone.get(field, ""))
            for field in ("python_commit", "python_tree", "studio_commit", "studio_tree")
        ) or any(not VERSION_RE.fullmatch(milestone.get(field, "")) for field in ("python_version", "studio_version")):
            raise CandidateError(f"{key}: candidate release identity is malformed")
    r1 = milestones["r1"]
    if (
        r1.get("publication") != "pypi_and_ghcr"
        or not COMMIT_RE.fullmatch(r1.get("publication_repair_commit", ""))
        or not TREE_RE.fullmatch(r1.get("publication_repair_tree", ""))
        or r1.get("publication_workflow_run") != 33753479548
    ):
        raise CandidateError("R1 candidate publication receipt diverges")
    expected_runs = {"r2": 33868949671, "r3": 33873060692}
    for key, expected_run in expected_runs.items():
        milestone = milestones[key]
        if (
            milestone.get("publication") != "pypi_and_ghcr"
            or milestone.get("publication_workflow_run") != expected_run
            or not isinstance(milestone.get("release_id"), int)
            or not COMMIT_RE.fullmatch(milestone.get("tag_object", ""))
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", milestone.get(field, ""))
                for field in ("wheel_sha256", "sdist_sha256", "record_sha256", "installed_manifest_sha256")
            )
            or not SHA256_RE.fullmatch(milestone.get("ghcr_oci_index", ""))
        ):
            raise CandidateError(f"{key.upper()} publication receipt diverges")
    r4 = milestones.get("r4")
    expected_r4_status = (
        "published_pypi_and_ghcr_release_workflow_green" if final_release else "unpublished_candidate_no_public_receipt"
    )
    if (
        not isinstance(r4, dict)
        or r4.get("python_version") != "1.0.0"
        or r4.get("status") != expected_r4_status
        or any(
            not COMMIT_RE.fullmatch(r4.get(field, ""))
            for field in ("python_commit", "python_tree", "documentation_commit", "documentation_tree")
        )
    ):
        raise CandidateError("R4 release identity diverges")
    if final_release and (
        r4.get("publication") != "pypi_and_ghcr"
        or not isinstance(r4.get("publication_workflow_run"), int)
        or not COMMIT_RE.fullmatch(r4.get("tag_object", ""))
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", r4.get(field, ""))
            for field in ("wheel_sha256", "sdist_sha256", "record_sha256", "installed_manifest_sha256")
        )
        or not SHA256_RE.fullmatch(r4.get("ghcr_oci_index", ""))
    ):
        raise CandidateError("R4 publication receipt diverges")
    governance = projection.get("governance")
    expected_governance_statuses = {
        "capability_inventory": "exhaustive_candidate_inventory_complete_no_go",
        "ownership": "lanes_and_handoffs_complete_local",
    }
    if not isinstance(governance, dict) or set(governance) != set(expected_governance_statuses):
        raise CandidateError("candidate governance evidence is incomplete")
    for key, witness in governance.items():
        if not isinstance(witness, dict):
            raise CandidateError(f"{key}: malformed governance evidence")
        if not COMMIT_RE.fullmatch(witness.get("commit", "")) or not TREE_RE.fullmatch(witness.get("tree", "")):
            raise CandidateError(f"{key}: malformed governance identity")
        if witness.get("status") != expected_governance_statuses[key]:
            raise CandidateError(f"{key}: unsafe governance status")
    expected_cutover = {
        "work_item": "CUT-002",
        "legacy_activation": "explicit_legacy_or_dual_only",
        "warning_format": "stable_structured_json",
        "counter_scope": "opt_in_process_local_non_persistent_intentional",
        "counter_opt_in": True,
        "strict_paths_silent": True,
        "implicit_fallback": False,
    }
    cutover = projection.get("cutover_observability")
    if (
        not isinstance(cutover, dict)
        or {key: cutover.get(key) for key in expected_cutover} != expected_cutover
        or not COMMIT_RE.fullmatch(cutover.get("evidence_commit", ""))
    ):
        raise CandidateError("CUT-002 observability evidence is incomplete or unsafe")
    performance = projection.get("performance")
    if not isinstance(performance, dict):
        raise CandidateError("performance evidence is missing")
    if (
        performance.get("evidence_mode") != "v1_bounded_functional_soak_passed_sustained_budgets_deferred"
        or performance.get("contract") != "archive_v2_same_matrix_four_surfaces"
        or performance.get("report_scope") != "python_3_cycles_and_studio_30_readiness_repetitions"
        or performance.get("representative_soak_required") is not False
        or performance.get("duration_seconds") != 147.512
        or performance.get("python_checks") != "21/21"
        or performance.get("studio_checks") != "90/90"
        or not re.fullmatch(r"[0-9a-f]{64}", performance.get("report_sha256", ""))
        or performance.get("budgets_frozen") is not False
        or performance.get("sustained_campaign_deferred_post_v1") is not True
        or performance.get("release_eligible") is not True
    ):
        raise CandidateError("performance evidence must preserve the bounded V1 soak and post-V1 deferral")
    if projection.get("work_item_states") != PROJECTED_WORK_ITEM_STATES:
        raise CandidateError("selected work-item states are incomplete or overclaimed")
    functional = projection.get("functional_non_crash")
    if functional != {
        "work_item": "SOAK-001",
        "status": "complete_functional_campaign_passed",
        "scope": "python_21_of_21_and_studio_90_of_90_checks",
        "release_gate": True,
    }:
        raise CandidateError("SOAK-001 functional non-crash scope diverges")
    components = projection.get("components")
    if not isinstance(components, list) or not components:
        raise CandidateError("candidate projection has no components")
    keys: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise CandidateError("candidate component must be an object")
        component_key = component.get("key")
        if not isinstance(component_key, str) or component_key in keys:
            raise CandidateError("candidate component keys must be unique")
        keys.add(component_key)
        if not COMMIT_RE.fullmatch(component.get("commit", "")) or not TREE_RE.fullmatch(component.get("tree", "")):
            raise CandidateError(f"{component_key}: malformed source identity")
        if not VERSION_RE.fullmatch(component.get("version", "")):
            raise CandidateError(f"{component_key}: malformed version")
        if component_key == "methods":
            expected_artifact_ids = {"source_tarball", "sbom", "matlab_octave", "r_n4m", "r_pls4all"}
            if (
                component.get("publication") != "published"
                or {artifact.get("id") for artifact in component.get("artifacts", [])} != expected_artifact_ids
                or len(component.get("registry_urls", [])) != 4
            ):
                raise CandidateError("methods: published multi-registry receipt is incomplete")
            for artifact in component["artifacts"]:
                if (
                    not isinstance(artifact.get("filename"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", ""))
                    or not isinstance(artifact.get("size"), int)
                    or artifact["size"] <= 0
                ):
                    raise CandidateError("methods: malformed artifact receipt")
            if any(not registry_url.startswith("https://") for registry_url in component["registry_urls"]):
                raise CandidateError("methods: malformed registry receipt URL")
        elif component_key in {"providers", "repository"}:
            if component.get("publication") != "published" or len(component.get("artifacts", [])) != 2:
                raise CandidateError(f"{component_key}: published receipt is incomplete")
            for artifact in component["artifacts"]:
                if (
                    artifact.get("id") not in {"wheel", "sdist"}
                    or not isinstance(artifact.get("filename"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", ""))
                    or not isinstance(artifact.get("size"), int)
                    or artifact["size"] <= 0
                ):
                    raise CandidateError(f"{component_key}: malformed artifact receipt")
            if len(component.get("registry_urls", [])) != 2 or any(
                not re.fullmatch(
                    r"https://(?:github\.com/GBeurier/[A-Za-z0-9_.-]+/releases/tag/[A-Za-z0-9_.-]+|pypi\.org/project/[A-Za-z0-9_.-]+/[0-9A-Za-z.-]+/)",
                    registry_url,
                )
                for registry_url in component["registry_urls"]
            ):
                raise CandidateError(f"{component_key}: malformed registry receipt URL")
        elif component.get("publication") != "published":
            raise CandidateError(f"{component_key}: selected release component must be published")
        url = component.get("repository_url", "")
        if not re.fullmatch(r"https://github\.com/GBeurier/[A-Za-z0-9_.-]+", url):
            raise CandidateError(f"{component_key}: unsafe repository URL")
    if keys != PROJECTED_COMPONENT_KEYS:
        raise CandidateError("candidate component membership is incomplete")
    capabilities = projection.get("capabilities")
    performance_capabilities = [
        capability
        for capability in capabilities or []
        if isinstance(capability, dict) and capability.get("key") == "four_surface_performance"
    ]
    if len(performance_capabilities) != 1 or performance_capabilities[0].get("status") != (
        "bounded_v1_functional_soak_passed"
    ):
        raise CandidateError("performance capability must preserve the bounded V1 evidence scope")
    serialized = render(projection).lower()
    for fragment in ("/home/", "/dev/shm/", "_worktrees", "localhost", "browser_download_url"):
        if fragment in serialized:
            raise CandidateError(f"candidate projection leaks forbidden fragment: {fragment}")
