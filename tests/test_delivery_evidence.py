"""Public evidence must preserve provenance, platform limits and dated history."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_platform_totals_match_the_dated_package_records() -> None:
    evidence = json.loads((ROOT / "data/platform-evidence.json").read_text())
    audit = evidence["R_platform_audit"]
    totals: Counter[str] = Counter()
    assert len(audit["packages"]) == audit["package_count"]
    for package in audit["packages"]:
        assert package["run"]["conclusion"] == "success"
        rows = package["platforms"]
        assert len(rows) == package["binary_count"]
        assert Counter(row["classification"] for row in rows) == package["binary_classifications"]
        for row in rows:
            assert row["version"] == package["version"] and row["commit"] == package["R_source_sha"]
            if row["classification"] == "current_build_only":
                assert row["os"] == "wasm" and row.get("check") is None
            elif row["classification"] == "current_note":
                assert package["package"] == "nirs4allio" and row["check"] == "NOTE"
            else:
                assert row["check"] == "OK"
        totals.update(row["classification"] for row in rows)
    assert totals == audit["classification_totals"]
    assert sum(totals.values()) == audit["platform_records"]


def test_resolved_history_keeps_its_original_failure_dates() -> None:
    notices = json.loads((ROOT / "data/delivery-notices.json").read_text())["notices"]
    note = next(item for item in notices if item["id"] == "external-macos-preparation-failures-20261029")
    assert note["historical"] is True
    assert note["observed_at"] == note["evidence_observation_dates"]["formats_failure"]
    resolution = datetime.fromisoformat(note["resolved_at"])
    assert all(resolution > datetime.fromisoformat(value) for value in note["evidence_observation_dates"].values())
    assert "resolved" in note["title"].lower()


def test_public_delivery_files_contain_no_private_local_paths() -> None:
    def strings(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, str):
            yield value

    for name in ("platform-evidence.json", "delivery-notices.json"):
        data = json.loads((ROOT / "data" / name).read_text())
        assert all(not value.startswith(("/home/", "/mnt/", "D:\\")) for value in strings(data))
