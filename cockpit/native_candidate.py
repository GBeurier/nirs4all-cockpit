"""Deterministic public-safe projection of the local native-backend candidate.

Unlike the canonical aggregation lock, this document is explicitly not release
authority.  It exposes only the exact local candidate identities and qualified
capability evidence recorded by the migration ledger.  Publication URLs and
artifacts are intentionally impossible to represent in this schema.
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
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")


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
        "publication": "unavailable",
        "artifacts": [],
        "registry_urls": [],
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
    if any(
        evidence.get(field) != "no_go" for field in ("promotion_status", "publication_status", "release_gate_status")
    ):
        raise CandidateError("candidate must remain NO-GO in staging")
    canonical_lock = evidence.get("canonical_release_lock")
    if not isinstance(canonical_lock, dict) or canonical_lock.get("updated") is not False:
        raise CandidateError("canonical release lock must remain unchanged")

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
    benchmarks = evidence["benchmarks"]
    capability_governance = evidence["capability_governance"]
    ownership_governance = evidence["ownership_governance"]

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
    benchmarks_version = _version_at(
        workspace_root / "nirs4all-benchmarks",
        benchmarks["commit"],
        "src/nirs4all_benchmarks/version.py",
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
            studio,
            key="studio",
            name="nirs4all-studio",
            repository="nirs4all-studio",
            commit_field="candidate_commit",
            tree_field="candidate_tree",
            version=studio_version,
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
            "limits": "Candidat local résolu sur le patch dag-ml-data 0.2.10 encore publish=false.",
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
                "qualification externe Windows/Docker/installers en attente."
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
            "key": "full_python_api",
            "label": "Matrice complète API Python R2",
            "status": "not_qualified",
            "surfaces": ["python"],
            "limits": (
                "run/predict/session/cache/retrain/finetune/conformal/robustness/"
                "explain/generate et dual-Methods restent incomplets comme ensemble."
            ),
        },
        {
            "key": "four_surface_performance",
            "label": "Performance sur quatre surfaces",
            "status": "record_only",
            "surfaces": ["benchmarks"],
            "limits": (
                "Mesure local_real WSL 4/4 enregistrée sans seuil; budgets non gelés et aucune qualification release."
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
            "label": "R4/V1 native backend local candidate",
            "status": "no_go",
            "publication": "unpublished",
            "canonical_lock_updated": False,
            "downloads_enabled": False,
            "registry_links_enabled": False,
            "notice": (
                "Candidat local strictement NO-GO et non publié; "
                "aucune V1 stable ni aucun artefact n’est publié."
            ),
        },
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
            "evidence_mode": "local_real_record_only",
            "environment": "wsl_local",
            "contract": benchmarks["performance_contract"],
            "surfaces_passed": benchmarks["local_real_surfaces_passed"],
            "maximum_prediction_delta": benchmarks["maximum_prediction_delta"],
            "fallback_observed": benchmarks["fallback_observed"],
            "timings_ms": benchmarks["timings_ms"],
            "budgets_frozen": False,
            "threshold_passed": None,
            "release_eligible": benchmarks["release_eligible"],
        },
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
            "status": "qualified_local_publication_pending",
            "commit": docs["commit"],
            "tree": docs["tree"],
            "mapped_pages": docs["mapped_documentation_pages"],
            "bibliography_entries": docs["bibliography_entries"],
            "historical_entries_preserved": 73,
            "reviewed_entries_added": 15,
        },
        "components": sorted(components, key=lambda item: item["key"]),
        "capabilities": capabilities,
        "holds": list(evidence.get("blockers", [])),
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
    expected_release = {
        "label": "R4/V1 native backend local candidate",
        "status": "no_go",
        "publication": "unpublished",
        "canonical_lock_updated": False,
        "downloads_enabled": False,
        "registry_links_enabled": False,
        "notice": "Candidat local strictement NO-GO et non publié; aucune V1 stable ni aucun artefact n’est publié.",
    }
    if release != expected_release:
        raise CandidateError("candidate projection must remain unpublished and NO-GO")
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
    if not isinstance(cutover, dict) or {
        key: cutover.get(key) for key in expected_cutover
    } != expected_cutover or not COMMIT_RE.fullmatch(cutover.get("evidence_commit", "")):
        raise CandidateError("CUT-002 observability evidence is incomplete or unsafe")
    performance = projection.get("performance")
    if not isinstance(performance, dict):
        raise CandidateError("performance evidence is missing")
    if (
        performance.get("evidence_mode") != "local_real_record_only"
        or performance.get("environment") != "wsl_local"
        or performance.get("contract") != "archive_v2_same_matrix_four_surfaces"
        or performance.get("surfaces_passed") != "4/4"
        or performance.get("fallback_observed") is not False
        or performance.get("budgets_frozen") is not False
        or performance.get("threshold_passed") is not None
        or performance.get("release_eligible") is not False
    ):
        raise CandidateError("performance evidence must remain WSL-local, record-only and release-ineligible")
    delta = performance.get("maximum_prediction_delta")
    timings = performance.get("timings_ms")
    if not isinstance(delta, (int, float)) or delta < 0 or not isinstance(timings, dict) or set(timings) != {
        "python",
        "rust",
        "studio",
        "web",
    }:
        raise CandidateError("performance measurement is incomplete")
    for surface, values in timings.items():
        if not isinstance(values, dict) or set(values) != {"startup", "steady"} or any(
            not isinstance(value, (int, float)) or value < 0 for value in values.values()
        ):
            raise CandidateError(f"{surface}: malformed performance timings")
    components = projection.get("components")
    if not isinstance(components, list) or not components:
        raise CandidateError("candidate projection has no components")
    keys: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise CandidateError("candidate component must be an object")
        key = component.get("key")
        if not isinstance(key, str) or key in keys:
            raise CandidateError("candidate component keys must be unique")
        keys.add(key)
        if not COMMIT_RE.fullmatch(component.get("commit", "")) or not TREE_RE.fullmatch(component.get("tree", "")):
            raise CandidateError(f"{key}: malformed source identity")
        if not VERSION_RE.fullmatch(component.get("version", "")):
            raise CandidateError(f"{key}: malformed version")
        if (
            component.get("publication") != "unavailable"
            or component.get("artifacts") != []
            or component.get("registry_urls") != []
        ):
            raise CandidateError(f"{key}: unpublished candidate cannot expose artifacts or registries")
        url = component.get("repository_url", "")
        if not re.fullmatch(r"https://github\.com/GBeurier/[A-Za-z0-9_.-]+", url):
            raise CandidateError(f"{key}: unsafe repository URL")
    capabilities = projection.get("capabilities")
    performance_capabilities = [
        capability
        for capability in capabilities or []
        if isinstance(capability, dict) and capability.get("key") == "four_surface_performance"
    ]
    if len(performance_capabilities) != 1 or performance_capabilities[0].get("status") != "record_only":
        raise CandidateError("performance capability must remain record-only")
    serialized = render(projection).lower()
    for fragment in ("/home/", "/dev/shm/", "_worktrees", "localhost", "browser_download_url"):
        if fragment in serialized:
            raise CandidateError(f"candidate projection leaks forbidden fragment: {fragment}")
