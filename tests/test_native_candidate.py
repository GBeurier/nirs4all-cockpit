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


def test_committed_release_projection_is_canonical_and_precise() -> None:
    value = candidate()
    validate_projection(value)
    assert SNAPSHOT.read_text(encoding="utf-8") == render(value)
    assert value["source"]["commit"] == "d7d62825e5aa5ab5554ec7d084fab29be66acd74"
    assert value["architecture"]["studio_control_plane"] == "rust_only"
    assert [item["code"] for item in value["migration"]["exit_codes"]] == [0, 10, 20]
    assert value["methods_documentation"]["mapped_pages"] == "209/209"
    assert {row["status"] for row in value["capabilities"]} >= {
        "qualified_local",
        "qualified_bounded",
        "bounded_v1_functional_soak_passed",
    }
    assert value["release_train"]["milestones"]["r1"]["default_engine"] == "legacy"
    assert value["release_train"]["milestones"]["r3"]["studio_commit"] == (
        "1c36b93f62cf560d8f4822c76cfe09fbb1d0e67b"
    )
    assert value["release_train"]["milestones"]["r2"]["python_commit"] == (
        "d351785dbc17290cdc85a797ead299ffce58f257"
    )
    assert value["release_train"]["milestones"]["r3"]["python_commit"] == (
        "3567bd4abcaa64443a1946748a579f0803e91889"
    )
    assert value["release_train"]["milestones"]["r2"]["publication_workflow_run"] == 33868949671
    assert value["release_train"]["milestones"]["r3"]["publication_workflow_run"] == 33873060692
    r4 = value["release_train"]["milestones"]["r4"]
    assert r4["python_commit"] == "a5e5f93b8b1336bc58c0a23814066e5e14678d12"
    assert r4["status"] == "published_pypi_and_ghcr_release_workflow_green"
    assert r4["publication_workflow_run"] == 33885659321
    assert r4["ghcr_oci_index"] == "sha256:c0a7420e1c63fc8bef403c673aefc46f62dc86cff45d28dff9b2e9c96f60ed9e"
    assert value["governance"]["ownership"]["commit"] == "fe17a3f939f9fb95c8ed1e068138c72ceac92890"
    assert value["governance"]["capability_inventory"]["commit"] == "cf6cd1d96c12d7043134ab0a7b4f593e19ec553b"
    assert value["cutover_observability"]["implicit_fallback"] is False
    assert value["cutover_observability"]["counter_scope"] == "opt_in_process_local_non_persistent_intentional"
    assert value["performance"] == {
        "budgets_frozen": False,
        "contract": "archive_v2_same_matrix_four_surfaces",
        "duration_seconds": 147.512,
        "evidence_mode": "v1_bounded_functional_soak_passed_sustained_budgets_deferred",
        "python_checks": "21/21",
        "release_eligible": True,
        "report_scope": "python_3_cycles_and_studio_30_readiness_repetitions",
        "report_sha256": "33a2d52cd60af8a03f2d092973a05c2b8442a775b5aa9a904f93603e70a1de91",
        "representative_soak_required": False,
        "studio_checks": "90/90",
        "sustained_campaign_deferred_post_v1": True,
    }
    assert value["functional_non_crash"] == {
        "release_gate": True,
        "scope": "python_21_of_21_and_studio_90_of_90_checks",
        "status": "complete_functional_campaign_passed",
        "work_item": "SOAK-001",
    }
    components = {item["key"]: item for item in value["components"]}
    assert components["studio"]["commit"] == "1c36b93f62cf560d8f4822c76cfe09fbb1d0e67b"
    assert components["repository"]["commit"] == "dbd9dae1205e1905692decd9fc7243f4fbda3068"
    assert components["providers"]["commit"] == "b2210ec717c0de0055fc8b9424b115a933efdb4e"
    assert components["repository"]["publication"] == "published"
    assert components["providers"]["publication"] == "published"
    assert components["methods"]["commit"] == "49aa40e90afef676f25809db1bd2a523e9582a49"
    assert components["methods"]["publication"] == "published"
    assert components["methods"]["version"] == "1.0.16"
    assert {artifact["id"] for artifact in components["repository"]["artifacts"]} == {"wheel", "sdist"}
    assert {artifact["id"] for artifact in components["providers"]["artifacts"]} == {"wheel", "sdist"}
    assert components["web"]["commit"] == "051bf636d7c1729087e5d40061b18bd690cd33b7"
    assert components["benchmarks"]["commit"] == "1649cdfb253a0eb0efec2c15b5e21a5c6219dc80"
    assert components["ui"] == {
        "artifacts": [],
        "commit": "406d94d70004f27459ef12347af1e6f0079ab6ac",
        "detail_versions": {"registry_latest_observed": "0.1.13"},
        "key": "ui",
        "name": "nirs4all-ui",
        "publication": "published",
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


def test_public_surfaces_match_the_published_train_and_web_receipts() -> None:
    value = candidate()
    r1_version = value["release_train"]["milestones"]["r1"]["python_version"]
    web_version = next(item["version"] for item in value["components"] if item["key"] == "web")
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    packages = {item["id"]: item for item in current["packages"]}

    assert value["release_train"]["publication"] == "python_r1_r2_r3_r4_and_studio_published"
    assert current["generator"]["run_id"] == "33823982288"
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
    assert f"Python R1 {r1_version}, R2, R3 and stable R4 1.0.0" in readme
    assert f"Python R1 {r1_version}, R2, R3 and stable R4 1.0.0" in index
    assert 'releaseTrain.publication !== "python_r1_r2_r3_r4_and_studio_published"' in browser_validator
    assert "Web 0.1.9" not in readme
    assert "nirs4all-web 0.1.9" not in index


def test_release_projection_refuses_state_downgrade_or_fabricated_artifacts() -> None:
    value = candidate()
    value["release"]["status"] = "no_go"
    with pytest.raises(CandidateError, match="status diverges"):
        validate_projection(value)

    value = copy.deepcopy(candidate())
    methods = next(item for item in value["components"] if item["key"] == "methods")
    methods["artifacts"][0]["sha256"] = "not-a-digest"
    with pytest.raises(CandidateError, match="methods: malformed artifact receipt"):
        validate_projection(value)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("governance", "ownership", "commit"), "unknown", "governance identity"),
        (("cutover_observability", "implicit_fallback"), True, "CUT-002"),
        (("performance", "evidence_mode"), "qualified", "bounded V1"),
        (("performance", "representative_soak_required"), True, "bounded V1"),
        (("work_item_states", "ROB-001"), "pending", "work-item states"),
        (("functional_non_crash", "release_gate"), False, "SOAK-001"),
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
