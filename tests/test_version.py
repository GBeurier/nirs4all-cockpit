"""Tests for the pure version engine ``cockpit.version``.

This module is fully implemented in the repo, so every assertion here is
concrete: SemVer/PEP 440-aware comparison (never lexical), expected-version
derivation, the reconcile state machine, the ``source_ahead`` package signal,
and pre-release detection.
"""

from __future__ import annotations

import pytest

from cockpit import version as v

# --------------------------------------------------------------------------- #
# normalize
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("v1.2.3", "1.2.3"),
        ("V1.2.3", "1.2.3"),
        ("1.2.3", "1.2.3"),
        ("0.2.0a1", "0.2.0a1"),
        ("0.2.0.9000", "0.2.0.dev9000"),  # R-devel -> PEP 440 dev release
        ("v0.99.0", "0.99.0"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert v.normalize(raw) == expected


def test_normalize_unparseable_returns_stripped_raw() -> None:
    assert v.normalize("  not-a-version  ") == "not-a-version"


def test_is_version_rejects_non_version_strings() -> None:
    assert v.is_version("0.8.0") is True
    assert v.is_version("v0.8.0") is True
    assert v.is_version("2026-notes") is False


# --------------------------------------------------------------------------- #
# compare  (the load-bearing "never lexical" guarantee)
# --------------------------------------------------------------------------- #


def test_compare_is_numeric_not_lexical() -> None:
    # The canonical trap: lexically "0.9.9" > "0.9.10"; numerically it is not.
    assert v.compare("0.9.10", "0.9.9") == 1
    assert v.compare("0.9.9", "0.9.10") == -1


def test_compare_equal() -> None:
    assert v.compare("1.2.3", "v1.2.3") == 0


def test_compare_prerelease_below_release() -> None:
    assert v.compare("0.2.0a1", "0.2.0") == -1
    assert v.compare("0.2.0.9000", "0.2.0") == -1  # R-devel snapshot < base release


# --------------------------------------------------------------------------- #
# is_prerelease
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("ver", "expected"),
    [
        ("0.2.0a1", True),
        ("0.2.0b2", True),
        ("0.2.0rc1", True),
        ("0.2.0.9000", True),  # R-devel dev release counts as prerelease
        ("0.2.0", False),
        ("v0.99.0", False),
        ("1.0.0", False),
    ],
)
def test_is_prerelease(ver: str, expected: bool) -> None:
    assert v.is_prerelease(ver) is expected


# --------------------------------------------------------------------------- #
# derive_expected  +  source_ahead
# --------------------------------------------------------------------------- #


def test_derive_expected_prefers_prod_tag() -> None:
    assert v.derive_expected("0.9.5", "0.9.4") == "0.9.4"


def test_derive_expected_falls_back_to_manifest() -> None:
    assert v.derive_expected("0.9.5", None) == "0.9.5"


def test_derive_expected_none_when_nothing_known() -> None:
    assert v.derive_expected(None, None) is None


def test_source_ahead_true_when_manifest_bumped_past_tag() -> None:
    assert v.source_ahead("0.9.5", "0.9.4") is True


def test_source_ahead_false_when_tag_matches_or_leads() -> None:
    assert v.source_ahead("0.9.4", "0.9.4") is False
    assert v.source_ahead("0.9.4", "0.9.5") is False


def test_source_ahead_false_when_either_side_missing() -> None:
    assert v.source_ahead(None, "0.9.4") is False
    assert v.source_ahead("0.9.4", None) is False


# --------------------------------------------------------------------------- #
# classify  — the full state machine, one test per State
# --------------------------------------------------------------------------- #


def _classify(expected: str | None, published: str | None, **kw):
    base = dict(http_status=200, transient_error=False, excluded=False, planned=False)
    base.update(kw)
    return v.classify(expected, published, **base)


def test_classify_green_exact_match() -> None:
    assert _classify("0.9.4", "0.9.4") == "green"


def test_classify_green_when_published_ahead() -> None:
    # source-ahead is a flag, never a red target.
    assert _classify("0.9.4", "0.9.5") == "green"


def test_classify_green_when_no_expectation_but_published() -> None:
    assert _classify(None, "0.9.4") == "green"


def test_classify_stale_when_published_behind() -> None:
    assert _classify("0.9.4", "0.9.3") == "stale"


def test_classify_missing_on_404() -> None:
    assert _classify("0.9.4", None, http_status=404) == "missing"


def test_classify_missing_when_planned_and_nothing_published() -> None:
    assert _classify(None, None, http_status=200, planned=True) == "missing"


def test_classify_missing_when_expected_but_absent() -> None:
    assert _classify("0.9.4", None, http_status=200) == "missing"


def test_classify_broken_is_modeled_by_caller_via_transient_false_published_null() -> None:
    # NOTE / assumption: classify() itself returns no "broken" — per the frozen
    # docstring, a null Version / build failure is decided by the reconcile layer
    # (it passes published=None + a non-transient signal and overrides to broken).
    # Here we only assert classify never *invents* broken on its own.
    assert _classify("0.9.4", None, http_status=200) != "broken"


def test_classify_unknown_on_transient_error() -> None:
    assert _classify("0.9.4", None, transient_error=True) == "unknown"


def test_classify_unknown_on_429() -> None:
    assert _classify("0.9.4", None, http_status=429) == "unknown"


def test_classify_unknown_on_5xx() -> None:
    assert _classify("0.9.4", None, http_status=503) == "unknown"


def test_classify_excluded_wins_over_everything() -> None:
    assert _classify("0.9.4", None, http_status=404, excluded=True) == "excluded"
    assert _classify("0.9.4", "0.9.4", excluded=True) == "excluded"
