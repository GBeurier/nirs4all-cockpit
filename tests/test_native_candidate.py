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
    assert value["source"]["commit"] == "cd1627f60a0fba6acaa22b7b1d726846a2da40dc"
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
    assert value["work_item_states"] == {
        "API-004": "complete_local_native_full_transfer_plugin_finetune_refused",
        "API-005": "complete_local_by_executable_preflight_refusal",
        "CAP-001": "complete",
        "DAG-001": "complete_local_code_release_hold",
        "DOC-001": "complete_local_docs_release_hold",
        "PERF-002": "advanced_local_evidence_not_closed",
        "REL-003": "complete_local_code_release_hold",
        "SEC-001": "advanced_local_evidence_not_closed",
        "SOAK-001": "advanced_local_evidence_not_closed",
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
