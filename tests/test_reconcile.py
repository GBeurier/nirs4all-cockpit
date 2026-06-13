"""Reconcile semantics, driven by monkeypatched collectors (offline).

The dedicated ``cockpit.reconcile`` module is not yet present in this checkout;
its contract, however, is fully determined by two pieces that *are* present and
frozen: the collector outputs (``published_version`` / ``downloads`` / the
r-universe ``broken`` flag / the ``http_status``) and the pure state machine
``cockpit.version.classify``. Reconcile is exactly their composition.

ASSUMPTION: ``reconcile`` will, per target, call the registry collector, then
feed ``classify(expected, published, http_status=..., transient_error=...,
excluded=..., planned=...)`` and, for an r-universe ``broken`` collector flag
(published is None at HTTP 200), override the ``missing`` verdict to
``broken``. Each test below reproduces that composition with the real collector
(network stubbed) so the four required scenarios are pinned now and will match
the module once it lands.
"""

from __future__ import annotations

import pytest
from conftest import load_fixture

from cockpit import version as v
from cockpit.collect import cran, crates, npm, readthedocs, runiverse
from cockpit.model import Package, Target
from cockpit.reconcile import _latest_any_tag, _latest_prod_tag, _reconcile_github_release


def _patch(monkeypatch, module, replies):
    if isinstance(replies, tuple):
        replies = [replies]
    calls = {"i": 0}

    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        i = min(calls["i"], len(replies) - 1)
        calls["i"] += 1
        return replies[i]

    monkeypatch.setattr(module, "get_json", _fake)


@pytest.fixture(autouse=True)
def _reset_runiverse_index():
    runiverse._INDEX = None
    runiverse._INDEX_STATUS = 0
    runiverse._INDEX_ERROR = None
    yield
    runiverse._INDEX = None
    runiverse._INDEX_STATUS = 0
    runiverse._INDEX_ERROR = None


def _reconcile_target(collected, *, expected, excluded=False, planned=False):
    """Reference reconcile of one target = collector facts + ``classify`` (+ broken).

    Mirrors the frozen contract: a present-but-failed r-universe build
    (``broken`` flag, published None at HTTP 200) overrides to ``broken``;
    otherwise the pure state machine decides.
    """
    published = collected.get("published_version")
    status = collected.get("http_status")
    transient = status == 0 and collected.get("error") is not None
    state = v.classify(
        expected,
        published,
        http_status=status,
        transient_error=transient,
        excluded=excluded,
        planned=planned,
    )
    if collected.get("broken") and published is None:
        state = "broken"
    return state


# --------------------------------------------------------------------------- #
# Scenario 1 — dag-ml crates: planned, nothing published => missing + planned
# --------------------------------------------------------------------------- #


def test_dagml_crate_planned_is_missing(monkeypatch) -> None:
    body = load_fixture("crates_dag-ml_404.json")
    _patch(monkeypatch, crates, (404, body, None))
    collected = crates.collect("dag-ml")
    assert collected["published_version"] is None
    # A planned crate that 404s reconciles as missing; the planned-ness is carried
    # separately on the target (TargetStatus.planned), not as a different status.
    state = _reconcile_target(collected, expected=None, planned=True)
    assert state == "missing"


# --------------------------------------------------------------------------- #
# Scenario 2 — npm scoped error-at-200: version ok, downloads unknown
# --------------------------------------------------------------------------- #


def test_npm_scoped_error_200_version_ok_downloads_unknown(monkeypatch) -> None:
    version_body = load_fixture("npm_scoped_ok_200.json")
    error_body = load_fixture("npm_scoped_error_200.json")
    _patch(monkeypatch, npm, [(200, version_body, None), (200, error_body, None)])
    collected = npm.collect("@nirs4all/formats-wasm")
    # Version is healthy...
    assert collected["published_version"] == "0.3.1"
    # ...downloads degrade to unknown (None), never a fabricated 0.
    assert collected["downloads"]["last_month"] is None
    # ...and the target reconciles green when the expected version matches.
    state = _reconcile_target(collected, expected="0.3.1")
    assert state == "green"


# --------------------------------------------------------------------------- #
# Scenario 3 — cranlogs 0 downloads: not "missing"
# --------------------------------------------------------------------------- #


def test_cranlogs_zero_does_not_force_missing(monkeypatch) -> None:
    version_body = {"Version": "0.99.0"}
    dl_body = [load_fixture("cranlogs_zero.json")]
    _patch(monkeypatch, cran, [(200, version_body, None), (200, dl_body, None)])
    collected = cran.collect("n4m")
    assert collected["downloads"]["last_month"] == 0  # real zero
    # Zero downloads must never reclassify a published package as missing.
    state = _reconcile_target(collected, expected="0.99.0")
    assert state == "green"
    assert state != "missing"


# --------------------------------------------------------------------------- #
# Scenario 4 — r-universe Version: null => broken
# --------------------------------------------------------------------------- #


def test_runiverse_null_version_reconciles_broken(monkeypatch) -> None:
    entry = load_fixture("runiverse_version_null.json")
    _patch(monkeypatch, runiverse, (200, [entry], None))
    collected = runiverse.collect("nirs4allformats")
    assert collected["broken"] is True
    assert collected["published_version"] is None
    # Present-but-failed build => broken, distinctly not missing.
    state = _reconcile_target(collected, expected="0.3.1")
    assert state == "broken"
    assert state != "missing"


# --------------------------------------------------------------------------- #
# Scenario 5 — Read the Docs: docs version is presence/build health, not SemVer
# --------------------------------------------------------------------------- #


def test_readthedocs_latest_is_green_without_semver_comparison(monkeypatch) -> None:
    project = {"default_version": "latest"}
    version = {"active": True, "built": True}
    _patch(monkeypatch, readthedocs, [(200, project, None), (200, version, None)])
    collected = readthedocs.collect("nirs4all")

    assert collected["published_version"] == "latest"
    state = v.classify(
        None,
        collected["published_version"],
        http_status=collected["http_status"],
        transient_error=False,
        excluded=False,
        planned=False,
    )

    assert state == "green"


# --------------------------------------------------------------------------- #
# Tag prefix handling — nirs4all-studio uses numeric tags, not v-prefixed tags
# --------------------------------------------------------------------------- #


def test_numeric_release_tags_can_be_declared_as_production_tags() -> None:
    tags = ["2026-notes", "0.9.0rc1", "0.8.0", "v9.9.9"]

    assert _latest_prod_tag(tags, "") == "0.8.0"
    assert _latest_any_tag(tags, "") == "0.9.0rc1"


def test_default_release_tags_still_require_v_prefix() -> None:
    tags = ["0.9.0", "v0.8.0"]

    assert _latest_prod_tag(tags) == "v0.8.0"


def test_github_release_asset_downloads_become_all_time_downloads(monkeypatch) -> None:
    from cockpit.collect import github

    monkeypatch.setattr(
        github,
        "latest_release_fact",
        lambda owner, repo: {  # noqa: ARG005
            "published_version": "0.8.0",
            "http_status": 200,
            "error": None,
            "asset_downloads": 42,
        },
    )
    pkg = Package(id="nirs4all-studio", repo="nirs4all-studio", targets=[])
    tgt = Target(registry="github-release", name="nirs4all-studio")

    status = _reconcile_github_release("GBeurier", pkg, tgt, "0.8.0", no_network=False)

    assert status.status == "green"
    assert status.downloads.total == 42
    assert status.downloads.windows["total"] == 42
    assert status.downloads.source == "github-release-assets"
