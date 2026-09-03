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
    assert value["source"]["commit"] == "091b8a0f3069e7a90167f78c81bb9d414c50ade5"
    assert value["architecture"]["studio_control_plane"] == "rust_only"
    assert [item["code"] for item in value["migration"]["exit_codes"]] == [0, 10, 20]
    assert value["methods_documentation"]["mapped_pages"] == "209/209"
    assert {row["status"] for row in value["capabilities"]} >= {
        "qualified_local",
        "qualified_bounded",
        "not_qualified",
        "stale_not_current_evidence",
    }
    assert value["release_train"]["milestones"]["r1"]["default_engine"] == "legacy"
    assert value["release_train"]["milestones"]["r3"]["studio_commit"] == (
        "ca4ee2afbb7596b2e4ba4b00f6d5797e553dfa39"
    )
    assert value["governance"]["ownership"]["commit"] == "fe17a3f939f9fb95c8ed1e068138c72ceac92890"
    assert value["governance"]["capability_inventory"]["commit"] == "cf6cd1d96c12d7043134ab0a7b4f593e19ec553b"
    assert value["cutover_observability"]["implicit_fallback"] is False
    assert value["cutover_observability"]["counter_scope"] == "opt_in_process_local_non_persistent_intentional"
    assert value["performance"] == {
        "budgets_frozen": False,
        "contract": "archive_v2_same_matrix_four_surfaces",
        "evidence_mode": "stale_not_current_evidence",
        "refresh_required": True,
        "release_eligible": False,
        "report_scope": "predates_distinct_r1_r2_r3_candidates",
        "timings_ms": None,
    }
    assert value["security_harnesses"]["evidence_status"] == "four_native_targets_prepared_campaign_not_run"
    assert [item["surface"] for item in value["security_harnesses"]["harnesses"]] == [
        "formats",
        "core",
        "methods",
        "studio_store",
    ]
    assert "no fuzz campaign has run" in value["security_harnesses"]["release_limit"]
    components = {item["key"]: item for item in value["components"]}
    assert components["studio"]["commit"] == "ca4ee2afbb7596b2e4ba4b00f6d5797e553dfa39"
    assert components["web"]["commit"] == "051bf636d7c1729087e5d40061b18bd690cd33b7"
    assert components["benchmarks"]["commit"] == "9ff889a5be1bbc48a16d69a27ab743c23598f7da"
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


def test_public_surfaces_match_the_published_r1_and_web_receipts() -> None:
    value = candidate()
    r1_version = value["release_train"]["milestones"]["r1"]["python_version"]
    web_version = next(item["version"] for item in value["components"] if item["key"] == "web")
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    packages = {item["id"]: item for item in current["packages"]}

    assert value["release_train"]["publication"] == "r1_published_r2_r3_unpublished"
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
    assert f"R1 {r1_version} and Web {web_version} are published" in readme
    assert f"R1 {r1_version} and nirs4all-web {web_version} are published" in index
    assert 'releaseTrain.publication !== "r1_published_r2_r3_unpublished"' in browser_validator
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
        (("performance", "evidence_mode"), "qualified", "stale"),
        (("performance", "refresh_required"), False, "stale"),
        (("work_item_states", "SEC-001"), "complete", "work-item states"),
        (("security_harnesses", "evidence_status"), "qualified", "SEC-001"),
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
