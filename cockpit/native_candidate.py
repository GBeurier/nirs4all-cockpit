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
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+|[-+][0-9A-Za-z.-]+)?")
PROJECTED_WORK_ITEM_STATES = {
    "API-001": "complete_local_code_release_hold",
    "API-004": "complete_local_native_full_transfer_plugin_finetune_refused",
    "API-005": "complete_local_by_executable_preflight_refusal",
    "CAP-001": "complete",
    "DAG-001": "complete_local_code_release_hold",
    "DOC-001": "complete_local_docs_release_hold",
    "GATE-001": "complete_local_linux_functional_release_hold",
    "INST-001": "prepared_local_linux_harness_external_matrix_hold",
    "PERF-002": "advanced_local_evidence_not_closed",
    "RC-001": "prepared_local_triage_external_evidence_hold",
    "REL-003": "complete_local_code_release_hold",
    "SEC-001": "prepared_local_native_fuzz_harnesses_campaign_not_closed",
    "SOAK-001": "advanced_local_evidence_not_closed",
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


def _project_security_harnesses(evidence: dict[str, Any]) -> dict[str, Any]:
    """Project bounded SEC-001 harness metadata without implying qualification."""
    security = evidence.get("security_harnesses")
    if not isinstance(security, dict):
        raise CandidateError("SEC-001 harness evidence is missing")
    if security.get("evidence_status") != "four_native_targets_prepared_campaign_not_run":
        raise CandidateError("SEC-001 must remain prepared with no fuzz campaign")

    harnesses: list[dict[str, Any]] = []
    for surface in ("formats", "core", "methods", "studio_store"):
        raw = security.get(surface)
        if not isinstance(raw, dict):
            raise CandidateError(f"SEC-001 {surface} harness is missing")
        commit = raw.get("commit")
        tree = raw.get("tree")
        target = raw.get("target")
        input_limit = raw.get("input_limit_bytes")
        entrypoint = raw.get("canonical_entrypoint")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise CandidateError(f"SEC-001 {surface} harness commit is invalid")
        if not isinstance(tree, str) or not TREE_RE.fullmatch(tree):
            raise CandidateError(f"SEC-001 {surface} harness tree is invalid")
        if not isinstance(target, str) or not target:
            raise CandidateError(f"SEC-001 {surface} harness target is invalid")
        if not isinstance(input_limit, int) or input_limit <= 0 or input_limit > 2 * 1024 * 1024:
            raise CandidateError(f"SEC-001 {surface} harness input bound is invalid")
        if not isinstance(entrypoint, str) or not entrypoint:
            raise CandidateError(f"SEC-001 {surface} canonical entrypoint is invalid")
        harnesses.append(
            {
                "surface": surface,
                "commit": commit,
                "tree": tree,
                "target": target,
                "input_limit_bytes": input_limit,
                "canonical_entrypoint": entrypoint,
            }
        )

    release_limit = security.get("release_limit")
    if not isinstance(release_limit, str) or not release_limit:
        raise CandidateError("SEC-001 release limit is missing")
    return {
        "work_item": "SEC-001",
        "evidence_status": security["evidence_status"],
        "harnesses": harnesses,
        "release_limit": release_limit,
    }


def _project_release_train(evidence: dict[str, Any]) -> dict[str, Any]:
    """Project the distinct product candidates without implying a stable release."""
    sequence = evidence.get("product_release_sequence")
    if not isinstance(sequence, dict):
        raise CandidateError("product release sequence is missing")
    if sequence.get("status") != "r1_r2_r3_distinct_remote_candidates_r4_held":
        raise CandidateError("product release sequence is not the held R1/R2/R3 train")
    if sequence.get("required_order") != (
        "r1_0_13_0_then_r2_1_0_0_rc_1_then_r3_1_0_0_rc_2_then_r4_1_0_0"
    ):
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
    r4 = raw_milestones["r4"]
    if r4 != {"version": "1.0.0", "status": "not_created_until_all_stable_gates_are_green"}:
        raise CandidateError("R4 must remain absent until all stable gates are green")
    milestones["r4"] = {
        "python_version": "1.0.0",
        "status": "not_created_until_stable_gates_are_green",
    }
    return {
        "status": "r1_r2_r3_distinct_candidates_r4_held",
        "publication": "r1_published_r2_r3_unpublished",
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
    if (
        evidence.get("promotion_status") != "no_go"
        or evidence.get("publication_status") != "component_train_published_product_train_incomplete_no_go"
        or evidence.get("release_gate_status") != "no_go"
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
    ui = evidence["ui"]
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
    ui_version = _version_at(
        workspace_root / "nirs4all-ui",
        ui["commit"],
        "package.json",
        r'^\s*"version"\s*:\s*"([^"]+)"',
    )
    if ui_version != ui.get("version"):
        raise CandidateError("ui: ledger version differs from the selected source")
    if ui.get("studio_consumer_commit") != studio.get("candidate_commit"):
        raise CandidateError("ui: Studio consumer does not match the selected candidate")
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
                "matrice unsigned Linux/Windows/macOS verte; publication, signatures, "
                "soak hostile et verrou canonique restent en attente."
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
            "label": "Matrice complète API Python R2",
            "status": "not_qualified",
            "surfaces": ["python"],
            "limits": (
                "run/predict/session/cache/conformal/robustness et les chemins dual-Methods "
                "restent incomplets comme ensemble; les dispositions retrain/explain/generate "
                "bornées sont listées séparément."
            ),
        },
        {
            "key": "four_surface_performance",
            "label": "Performance sur le train courant",
            "status": "stale_not_current_evidence",
            "surfaces": ["benchmarks"],
            "limits": (
                "Le rapport Bench disponible précède les candidats R1/R2/R3 distincts. Il reste historique "
                "et ne constitue pas une preuve courante; nouvelle mesure et soak requis."
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
                "Candidat produit strictement NO-GO; les composants natifs, R1 0.13.0 et Web 0.1.10 "
                "sont publiés, mais R2, R3 et Studio restent non publiés et aucune V1 stable n’est annoncée."
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
            "evidence_mode": "stale_not_current_evidence",
            "contract": benchmarks["performance_contract"],
            "report_scope": "predates_distinct_r1_r2_r3_candidates",
            "refresh_required": True,
            "timings_ms": None,
            "budgets_frozen": False,
            "release_eligible": benchmarks["release_eligible"],
        },
        "security_harnesses": _project_security_harnesses(evidence),
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
        "notice": (
            "Candidat produit strictement NO-GO; les composants natifs, R1 0.13.0 et Web 0.1.10 "
            "sont publiés, mais R2, R3 et Studio restent non publiés et aucune V1 stable n’est annoncée."
        ),
    }
    if release != expected_release:
        raise CandidateError("candidate projection must remain unpublished and NO-GO")
    release_train = projection.get("release_train")
    if not isinstance(release_train, dict) or release_train.get("status") != (
        "r1_r2_r3_distinct_candidates_r4_held"
    ) or release_train.get("publication") != "r1_published_r2_r3_unpublished":
        raise CandidateError("candidate release train must retain only the published R1 receipt")
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
        if any(not COMMIT_RE.fullmatch(milestone.get(field, "")) for field in (
            "python_commit", "python_tree", "studio_commit", "studio_tree"
        )) or any(not VERSION_RE.fullmatch(milestone.get(field, "")) for field in (
            "python_version", "studio_version"
        )):
            raise CandidateError(f"{key}: candidate release identity is malformed")
    r1 = milestones["r1"]
    if (
        r1.get("publication") != "pypi_and_ghcr"
        or not COMMIT_RE.fullmatch(r1.get("publication_repair_commit", ""))
        or not TREE_RE.fullmatch(r1.get("publication_repair_tree", ""))
        or r1.get("publication_workflow_run") != 33753479548
    ):
        raise CandidateError("R1 candidate publication receipt diverges")
    if milestones.get("r4") != {
        "python_version": "1.0.0",
        "status": "not_created_until_stable_gates_are_green",
    }:
        raise CandidateError("R4 must remain absent until stable gates are green")
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
        performance.get("evidence_mode") != "stale_not_current_evidence"
        or performance.get("contract") != "archive_v2_same_matrix_four_surfaces"
        or performance.get("report_scope") != "predates_distinct_r1_r2_r3_candidates"
        or performance.get("refresh_required") is not True
        or performance.get("timings_ms") is not None
        or performance.get("budgets_frozen") is not False
        or performance.get("release_eligible") is not False
    ):
        raise CandidateError("performance evidence must remain stale, refresh-required and release-ineligible")
    if projection.get("work_item_states") != PROJECTED_WORK_ITEM_STATES:
        raise CandidateError("selected work-item states are incomplete or overclaimed")
    security = projection.get("security_harnesses")
    if (
        not isinstance(security, dict)
        or security.get("work_item") != "SEC-001"
        or security.get("evidence_status") != "four_native_targets_prepared_campaign_not_run"
        or not isinstance(security.get("release_limit"), str)
        or "no fuzz campaign has run" not in security["release_limit"]
    ):
        raise CandidateError("SEC-001 harness evidence is incomplete or overclaimed")
    harnesses = security.get("harnesses")
    if not isinstance(harnesses, list) or [item.get("surface") for item in harnesses if isinstance(item, dict)] != [
        "formats",
        "core",
        "methods",
        "studio_store",
    ]:
        raise CandidateError("SEC-001 must expose exactly four prepared native harnesses")
    for harness in harnesses:
        if (
            not COMMIT_RE.fullmatch(harness.get("commit", ""))
            or not TREE_RE.fullmatch(harness.get("tree", ""))
            or not isinstance(harness.get("target"), str)
            or not harness["target"]
            or not isinstance(harness.get("canonical_entrypoint"), str)
            or not harness["canonical_entrypoint"]
            or not isinstance(harness.get("input_limit_bytes"), int)
            or harness["input_limit_bytes"] <= 0
            or harness["input_limit_bytes"] > 2 * 1024 * 1024
        ):
            raise CandidateError("SEC-001 harness metadata is malformed")
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
    if keys != PROJECTED_COMPONENT_KEYS:
        raise CandidateError("candidate component membership is incomplete")
    capabilities = projection.get("capabilities")
    performance_capabilities = [
        capability
        for capability in capabilities or []
        if isinstance(capability, dict) and capability.get("key") == "four_surface_performance"
    ]
    if len(performance_capabilities) != 1 or performance_capabilities[0].get("status") != (
        "stale_not_current_evidence"
    ):
        raise CandidateError("performance capability must remain stale and non-current")
    serialized = render(projection).lower()
    for fragment in ("/home/", "/dev/shm/", "_worktrees", "localhost", "browser_download_url"):
        if fragment in serialized:
            raise CandidateError(f"candidate projection leaks forbidden fragment: {fragment}")
