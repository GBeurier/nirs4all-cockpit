from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cockpit.native_candidate import CandidateError, render, validate_projection

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "native-candidate-staging.json"


def candidate() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_committed_candidate_is_canonical_unpublished_and_precise() -> None:
    value = candidate()
    validate_projection(value)
    assert SNAPSHOT.read_text(encoding="utf-8") == render(value)
    assert value["source"]["commit"] == "0502c64cf4c562fa21bdcd326f89270f0d4ac505"
    assert value["architecture"]["studio_control_plane"] == "rust_only"
    assert [item["code"] for item in value["migration"]["exit_codes"]] == [0, 10, 20]
    assert value["methods_documentation"]["mapped_pages"] == "209/209"
    assert {row["status"] for row in value["capabilities"]} >= {
        "qualified_local",
        "qualified_bounded",
        "not_qualified",
        "record_only",
    }
    assert value["governance"]["ownership"]["commit"] == "fe17a3f939f9fb95c8ed1e068138c72ceac92890"
    assert value["governance"]["capability_inventory"]["commit"] == "cf6cd1d96c12d7043134ab0a7b4f593e19ec553b"
    assert value["cutover_observability"]["implicit_fallback"] is False
    assert value["cutover_observability"]["counter_scope"] == "opt_in_process_local_non_persistent_intentional"
    assert value["performance"] == {
        "budgets_frozen": False,
        "contract": "archive_v2_same_matrix_four_surfaces",
        "environment": "wsl_local",
        "evidence_mode": "local_real_record_only",
        "fallback_observed": False,
        "maximum_prediction_delta": 0,
        "release_eligible": False,
        "surfaces_passed": "4/4",
        "threshold_passed": None,
        "timings_ms": {
            "python": {"startup": 1067.573, "steady": 28.026},
            "rust": {"startup": 38.148, "steady": 18.244},
            "studio": {"startup": 75.621, "steady": 24.771},
            "web": {"startup": 97.81, "steady": 4.713},
        },
    }
    components = {item["key"]: item for item in value["components"]}
    assert components["studio"]["commit"] == "e027cbf8dea9fc2297ac91b9cd983346a44fb34f"
    assert components["web"]["commit"] == "e7b9a6384050c2c1a92dcec6aab41e9f0430be43"
    assert components["benchmarks"]["commit"] == "24751ea97a3e12d48ffb9f0438a4355b024e15d8"
    assert components["ui"] == {
        "artifacts": [],
        "commit": "406d94d70004f27459ef12347af1e6f0079ab6ac",
        "detail_versions": {"registry_latest_observed": "0.1.12"},
        "key": "ui",
        "name": "nirs4all-ui",
        "publication": "unavailable",
        "qualification": "locally_qualified_shared_tarball_registry_publication_hold",
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
        "SEC-001": "advanced_local_evidence_not_closed",
        "SOAK-001": "advanced_local_evidence_not_closed",
        "STU-006": "complete_local_code_external_release_hold",
        "UI-001": "complete_local_code_registry_publication_hold",
        "WEB-001": "complete_local_code_release_hold",
        "WEBREL-001": "complete_local_staging_publication_hold",
    }


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
        (("performance", "evidence_mode"), "qualified", "record-only"),
        (("performance", "threshold_passed"), True, "record-only"),
        (("work_item_states", "SEC-001"), "complete", "work-item states"),
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
