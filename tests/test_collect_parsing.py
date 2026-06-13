"""Per-collector parsing tests, offline against captured fixtures.

Each collector reaches the network only through ``cockpit.http.get_json``; here
that single function is monkeypatched per module to replay a fixture body. We
then assert ``collect(name)`` extracts the right fields. This pins the
registry-specific traps from the Codex review without any HTTP:

* PyPI    — ``info.version`` is the published version.
* crates  — ``crate.max_version``; a 404 body yields no version.
* npm     — ``dist-tags.latest``; the downloads probe can answer HTTP 200 with
            an ``{"error": ...}`` body, which must degrade downloads to ``None``
            and never reddens the version verdict.
* r-univ  — ``Version: null`` for a present package sets ``broken=True`` with a
            ``200`` status (reconcile reads that as broken, not missing).
* cranlogs— ``downloads: 0`` at HTTP 200 is a real zero, not "missing".
"""

from __future__ import annotations

import pytest
from conftest import load_fixture

from cockpit.collect import cran, crates, npm, pypi, readthedocs, runiverse, visits


def _patch(monkeypatch, module, replies):
    """Make ``module.get_json`` return successive ``(status, body, error)`` replies.

    A list is consumed in call order (collectors that hit a version endpoint then
    a downloads endpoint pass two replies); a single tuple is reused for every
    call.
    """
    if isinstance(replies, tuple):
        replies = [replies]
    calls = {"i": 0}

    def _fake(url, headers=None, *, accept="application/json", max_retries=None):  # noqa: ARG001
        i = min(calls["i"], len(replies) - 1)
        calls["i"] += 1
        return replies[i]

    monkeypatch.setattr(module, "get_json", _fake)


@pytest.fixture(autouse=True)
def _reset_runiverse_index():
    """R-universe caches its package index in module globals; reset around tests."""
    runiverse._INDEX = None
    runiverse._INDEX_STATUS = 0
    runiverse._INDEX_ERROR = None
    yield
    runiverse._INDEX = None
    runiverse._INDEX_STATUS = 0
    runiverse._INDEX_ERROR = None


# --------------------------------------------------------------------------- #
# PyPI
# --------------------------------------------------------------------------- #


def test_pypi_extracts_info_version(monkeypatch) -> None:
    body = load_fixture("pypi_nirs4all.json")
    # version reply, then a (no-stats) downloads reply.
    _patch(monkeypatch, pypi, [(200, body, None), (404, None, "http 404")])
    out = pypi.collect("nirs4all")
    assert out["published_version"] == "0.9.4"
    assert out["http_status"] == 200
    assert out["error"] is None
    assert out["evidence"]["version_endpoint"].endswith("/nirs4all/json")


# --------------------------------------------------------------------------- #
# crates.io
# --------------------------------------------------------------------------- #


def test_crates_extracts_max_version(monkeypatch) -> None:
    body = load_fixture("crates_formats_ok_200.json")
    _patch(monkeypatch, crates, (200, body, None))
    out = crates.collect("nirs4all-formats")
    assert out["published_version"] == "0.3.1"
    assert out["http_status"] == 200


def test_crates_404_yields_no_version(monkeypatch) -> None:
    body = load_fixture("crates_dag-ml_404.json")
    _patch(monkeypatch, crates, (404, body, None))
    out = crates.collect("dag-ml")
    assert out["published_version"] is None
    assert out["http_status"] == 404


# --------------------------------------------------------------------------- #
# npm  (dist-tags + downloads error-at-200)
# --------------------------------------------------------------------------- #


def test_npm_extracts_dist_tags_latest(monkeypatch) -> None:
    version_body = load_fixture("npm_scoped_ok_200.json")
    # version OK, then a downloads endpoint answering 200 with an error body.
    error_body = load_fixture("npm_scoped_error_200.json")
    _patch(monkeypatch, npm, [(200, version_body, None), (200, error_body, None)])
    out = npm.collect("@nirs4all/formats-wasm")
    assert out["published_version"] == "0.3.1"
    # The %2F-encoded scope must survive into the endpoint.
    assert "%2F" in out["evidence"]["version_endpoint"]
    # Downloads degrade to None (unknown) on the error-200 body, never fabricated.
    assert out["downloads"]["last_month"] is None


def test_npm_error_body_at_200_does_not_become_a_version(monkeypatch) -> None:
    error_body = load_fixture("npm_scoped_error_200.json")
    # Both the version and downloads probes answer 200 with an error body.
    _patch(monkeypatch, npm, (200, error_body, None))
    out = npm.collect("@nirs4all/methods-wasm")
    assert out["published_version"] is None
    assert out["downloads"]["last_month"] is None


# --------------------------------------------------------------------------- #
# R-universe  (Version: null => broken; present version => parsed)
# --------------------------------------------------------------------------- #


def test_runiverse_extracts_version(monkeypatch) -> None:
    entry = load_fixture("runiverse_ok_200.json")
    _patch(monkeypatch, runiverse, (200, [entry], None))
    out = runiverse.collect("n4m")
    assert out["published_version"] == "0.99.0"
    assert out["broken"] is False
    assert out["http_status"] == 200


def test_runiverse_null_version_is_broken_not_missing(monkeypatch) -> None:
    entry = load_fixture("runiverse_version_null.json")
    _patch(monkeypatch, runiverse, (200, [entry], None))
    out = runiverse.collect("nirs4allformats")
    assert out["published_version"] is None
    assert out["broken"] is True
    # Present-but-failed must keep a 200 status so reconcile reads broken, not missing.
    assert out["http_status"] == 200


def test_runiverse_absent_package_is_missing(monkeypatch) -> None:
    entry = load_fixture("runiverse_ok_200.json")  # only n4m is present
    _patch(monkeypatch, runiverse, (200, [entry], None))
    out = runiverse.collect("not-in-universe")
    assert out["published_version"] is None
    assert out["broken"] is False
    assert out["http_status"] == 404  # absent => missing


# --------------------------------------------------------------------------- #
# cranlogs  (0 downloads at HTTP 200 is a real zero)
# --------------------------------------------------------------------------- #


def test_cranlogs_zero_is_real_zero_not_none(monkeypatch) -> None:
    dl_body = [load_fixture("cranlogs_zero.json")]
    # version endpoint 404 (not yet on CRAN), downloads endpoint 200 with 0.
    _patch(monkeypatch, cran, [(404, None, "http 404"), (200, dl_body, None)])
    out = cran.collect("n4m")
    assert out["published_version"] is None  # not on CRAN yet
    assert out["downloads"]["last_month"] == 0  # a real zero, not None
    assert out["downloads"]["last_month"] is not None


# --------------------------------------------------------------------------- #
# GoatCounter visits  (aggregate-only by default)
# --------------------------------------------------------------------------- #


def test_visits_default_does_not_fetch_or_return_pages(monkeypatch) -> None:
    urls = []

    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        urls.append(url)
        return 200, {"total": 12}, None

    monkeypatch.setattr(visits, "get_json", _fake)

    out = visits.collect(token="tok", ref_date="2026-06-12")

    assert out["available"] is True
    assert out["windows"]["30d"] == 12
    assert out["pages"] == []
    assert len(urls) == 4
    assert all("/stats/total" in url for url in urls)


def test_visits_include_pages_fetches_page_breakdown(monkeypatch) -> None:
    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        if "/stats/hits" in url:
            return 200, {
                "hits": [
                    {"path": "/io/", "title": "nirs4all IO", "count": 7},
                    {"path": "/formats/", "title": "nirs4all Formats", "count": 12},
                    {"path": "/empty-title/", "title": "   ", "count": 1},
                ]
            }, None
        return 200, {"total": 20}, None

    monkeypatch.setattr(visits, "get_json", _fake)

    out = visits.collect(token="tok", ref_date="2026-06-12", include_pages=True)

    assert out["available"] is True
    assert out["windows"]["total"] == 20
    assert [p["path"] for p in out["pages"]] == ["/formats/", "/io/", "/empty-title/"]
    assert out["pages"][0]["title"] == "nirs4all Formats"
    assert out["pages"][2]["title"] is None


def test_visits_drops_legacy_bare_root_path(monkeypatch) -> None:
    # The bare "/" bucket is pre-path-override legacy traffic; it must not appear
    # as an ecosystem page now that every site reports an explicit "/name" path.
    def _fake(url, headers=None, *, accept="application/json"):  # noqa: ARG001
        if "/stats/hits" in url:
            return 200, {
                "hits": [
                    {"path": "/", "title": "nirs4all-formats demo", "count": 23},
                    {"path": "/formats/", "title": "nirs4all Formats", "count": 5},
                ]
            }, None
        return 200, {"total": 28}, None

    monkeypatch.setattr(visits, "get_json", _fake)

    out = visits.collect(token="tok", ref_date="2026-06-12", include_pages=True)

    assert [p["path"] for p in out["pages"]] == ["/formats/"]


# --------------------------------------------------------------------------- #
# Read the Docs
# --------------------------------------------------------------------------- #


def test_readthedocs_project_default_version_built(monkeypatch) -> None:
    project = {
        "default_version": "latest",
        "urls": {"documentation": "https://nirs4all.readthedocs.io/en/latest/"},
    }
    version = {
        "active": True,
        "built": True,
        "urls": {"documentation": "https://nirs4all.readthedocs.io/en/latest/"},
    }
    _patch(monkeypatch, readthedocs, [(200, project, None), (200, version, None)])

    out = readthedocs.collect("nirs4all")

    assert out["published_version"] == "latest"
    assert out["http_status"] == 200
    assert out["broken"] is False
    assert out["evidence"]["version_endpoint"] == "https://nirs4all.readthedocs.io/en/latest/"


def test_readthedocs_default_version_not_built_is_broken(monkeypatch) -> None:
    project = {"default_version": "latest"}
    version = {"active": True, "built": False}
    _patch(monkeypatch, readthedocs, [(200, project, None), (200, version, None)])

    out = readthedocs.collect("nirs4all")

    assert out["published_version"] == "latest"
    assert out["http_status"] == 200
    assert out["broken"] is True
