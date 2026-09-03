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
    assert value["source"]["commit"] == "a3ea904799b84977bc3e5661a27799e7078f8430"
    assert value["architecture"]["studio_control_plane"] == "rust_only"
    assert [item["code"] for item in value["migration"]["exit_codes"]] == [0, 10, 20]
    assert value["methods_documentation"]["mapped_pages"] == "209/209"
    assert {row["status"] for row in value["capabilities"]} >= {
        "qualified_local",
        "qualified_bounded",
        "not_qualified",
        "fixture_only",
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
