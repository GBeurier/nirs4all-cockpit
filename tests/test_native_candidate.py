from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cockpit.native_candidate import CandidateError, render, validate_projection

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "native-candidate-staging.json"
CURRENT = ROOT / "data" / "current.json"


def candidate() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_committed_candidate_is_canonical_unpublished_and_precise() -> None:
    value = candidate()
    validate_projection(value)
    assert SNAPSHOT.read_text(encoding="utf-8") == render(value)
    assert value["source"]["commit"] == "8edd28e7428f9492387e537329fe3167eb6babbf"
    assert value["architecture"]["studio_control_plane"] == "rust_only"
    assert [item["code"] for item in value["migration"]["exit_codes"]] == [0, 10, 20]
    assert value["methods_documentation"]["mapped_pages"] == "209/209"
    assert {row["status"] for row in value["capabilities"]} >= {
        "qualified_local",
        "qualified_bounded",
        "bounded_current_not_release_evidence",
    }
    assert value["release_train"]["milestones"]["r1"]["default_engine"] == "legacy"
    assert value["release_train"]["milestones"]["r3"]["studio_commit"] == (
        "1c905e4c51a146dcc85e017454557a7eace7209b"
    )
    assert value["release_train"]["milestones"]["r2"]["python_commit"] == (
        "d351785dbc17290cdc85a797ead299ffce58f257"
    )
    assert value["release_train"]["milestones"]["r3"]["python_commit"] == (
        "3567bd4abcaa64443a1946748a579f0803e91889"
    )
    assert value["release_train"]["milestones"]["r2"]["publication_workflow_run"] == 33868949671
    assert value["release_train"]["milestones"]["r3"]["publication_workflow_run"] == 33873060692
    assert value["release_train"]["milestones"]["r4"] == {
        "documentation_commit": "ef39f1a53dd120b9ce28907dc372d755dd621430",
        "documentation_tree": "126dfe87557a265d2a6c7894885c7772604d5311",
        "python_commit": "a5e5f93b8b1336bc58c0a23814066e5e14678d12",
        "python_tree": "1f566f81f5309ed0b73872fbc01db00a40d4e3e2",
        "python_version": "1.0.0",
        "status": "unpublished_candidate_no_public_receipt",
    }
    assert value["governance"]["ownership"]["commit"] == "fe17a3f939f9fb95c8ed1e068138c72ceac92890"
    assert value["governance"]["capability_inventory"]["commit"] == "cf6cd1d96c12d7043134ab0a7b4f593e19ec553b"
    assert value["cutover_observability"]["implicit_fallback"] is False
    assert value["cutover_observability"]["counter_scope"] == "opt_in_process_local_non_persistent_intentional"
    assert value["performance"] == {
        "budgets_frozen": False,
        "contract": "archive_v2_same_matrix_four_surfaces",
        "evidence_mode": "current_heads_bounded_synthetic_not_release_evidence",
        "release_eligible": False,
        "report_scope": "current_selected_heads_local_four_surface_replay",
        "representative_soak_required": True,
        "timings_ms": None,
    }
    assert value["functional_non_crash"] == {
        "release_gate": False,
        "scope": "ordinary_component_suites_supported_invalid_inputs",
        "status": "complete_local_functional_non_crash_non_blocking",
        "work_item": "ROB-001",
    }
    components = {item["key"]: item for item in value["components"]}
    assert components["studio"]["commit"] == "1c905e4c51a146dcc85e017454557a7eace7209b"
    assert components["repository"]["commit"] == "dbd9dae1205e1905692decd9fc7243f4fbda3068"
    assert components["providers"]["commit"] == "b2210ec717c0de0055fc8b9424b115a933efdb4e"
    assert components["repository"]["publication"] == "published"
    assert components["providers"]["publication"] == "published"
    assert {artifact["id"] for artifact in components["repository"]["artifacts"]} == {"wheel", "sdist"}
    assert {artifact["id"] for artifact in components["providers"]["artifacts"]} == {"wheel", "sdist"}
    assert components["web"]["commit"] == "051bf636d7c1729087e5d40061b18bd690cd33b7"
    assert components["benchmarks"]["commit"] == "17f8196b26457fbd300a46d6520c3d1845d0de05"
    assert components["ui"] == {
        "artifacts": [],
        "commit": "406d94d70004f27459ef12347af1e6f0079ab6ac",
        "detail_versions": {"registry_latest_observed": "0.1.13"},
        "key": "ui",
        "name": "nirs4all-ui",
        "publication": "unavailable",
        "qualification": "published_0_1_13_downstream_product_release_hold",
        "registry_urls": [],
        "repository_url": "https://github.com/GBeurier/nirs4all-ui",
        "tree": "377722160bbf188c474aacfecc8a6825095be2ca",
        "version": "0.1.13",
    }
    assert value["work_item_states"] == {
        "API-001": "complete_local_code_release_hold",
        "API-004": "complete_local_native_full_transfer_plugin_finetune_refused",
        "API-005": "complete_local_by_executable_preflight_refusal",
        "CAP-001": "complete",
        "DAG-001": "complete_local_code_release_hold",
        "DOC-001": "complete_local_docs_release_hold",
        "GATE-001": "complete_local_linux_functional_release_hold",
        "INST-001": "advanced_local_linux_appimage_lifecycle_complete_macos_windows_hold",
        "PERF-002": "advanced_local_evidence_not_closed",
        "RC-001": "prepared_local_triage_external_evidence_hold",
        "REL-003": "complete_local_code_release_hold",
        "ROB-001": "complete_local_functional_non_crash_non_blocking",
        "SOAK-001": "advanced_local_evidence_not_closed",
        "STU-006": "complete_local_code_external_release_hold",
        "UI-001": "complete_registry_publication_downstream_product_hold",
        "WEB-001": "complete_local_code_release_hold",
        "WEBREL-001": "complete_local_staging_publication_hold",
    }


def test_public_surfaces_match_the_published_train_and_web_receipts() -> None:
    value = candidate()
    r1_version = value["release_train"]["milestones"]["r1"]["python_version"]
    web_version = next(item["version"] for item in value["components"] if item["key"] == "web")
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    packages = {item["id"]: item for item in current["packages"]}

    assert value["release_train"]["publication"] == "python_r1_r2_r3_published_r4_and_studio_unpublished"
    assert current["generator"]["snapshot_status"] == "historical_obsolete"
    assert packages["nirs4all"]["source"]["expected_prod_version"] == r1_version
    assert {
        target["published_version"]
        for target in packages["nirs4all"]["targets"]
        if target["registry"] in {"pypi", "github-release"}
    } == {r1_version}
    assert packages["nirs4all-web"]["source"]["expected_prod_version"] == f"v{web_version}"
    web_targets = {target["registry"]: target for target in packages["nirs4all-web"]["targets"]}
    assert web_targets["pages"]["status"] == "green"
    assert web_targets["github-release"]["published_version"] == "0.1.8"
    assert web_targets["github-release"]["status"] == "stale"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    browser_validator = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert f"Python R1 {r1_version}, R2 and R3 plus Web {web_version}" in readme
    assert f"Python R1 {r1_version}, R2 and R3 plus nirs4all-web {web_version}" in index
    assert 'releaseTrain.publication !== "python_r1_r2_r3_published_r4_and_studio_unpublished"' in browser_validator
    assert "Web 0.1.9" not in readme
    assert "nirs4all-web 0.1.9" not in index


def test_candidate_refuses_publication_or_fabricated_artifacts() -> None:
    value = candidate()
    value["release"]["status"] = "go"
    with pytest.raises(CandidateError, match="unpublished and NO-GO"):
        validate_projection(value)

    value = copy.deepcopy(candidate())
    value["components"][0]["artifacts"] = [{"url": "https://example.invalid/fake.zip"}]
    with pytest.raises(CandidateError, match="cannot expose"):
        validate_projection(value)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("governance", "ownership", "commit"), "unknown", "governance identity"),
        (("cutover_observability", "implicit_fallback"), True, "CUT-002"),
        (("performance", "evidence_mode"), "qualified", "bounded"),
        (("performance", "representative_soak_required"), False, "bounded"),
        (("work_item_states", "ROB-001"), "pending", "work-item states"),
        (("functional_non_crash", "release_gate"), True, "ROB-001"),
    ],
)
def test_candidate_refuses_incomplete_or_overclaimed_final_evidence(
    path: tuple[str, ...], replacement: object, message: str
) -> None:
    value = copy.deepcopy(candidate())
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(CandidateError, match=message):
        validate_projection(value)
