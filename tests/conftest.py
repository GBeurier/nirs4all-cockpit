"""Shared test fixtures and helpers (offline only — no network).

Every test in this suite runs without touching the network. The collectors in
``cockpit.collect.*`` reach the network solely through ``cockpit.http.get_json``;
the tests monkeypatch that single seam in each collector module to replay the
captured JSON bodies under ``tests/fixtures/``. The version engine
(``cockpit.version``) and the pydantic contracts (``cockpit.model``) are pure and
are exercised directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Load a JSON fixture body from ``tests/fixtures/``."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def stub_get_json(monkeypatch, module, *, status: int, body, error=None):
    """Replace ``get_json`` inside a collector module with a fixed reply.

    Collectors call the name ``get_json`` imported into their own module
    namespace, so patching that attribute fully severs the network without any
    real HTTP. Returns the ``(status, body, error)`` tuple the real helper
    yields.
    """

    def _fake(url, headers=None, *, accept="application/json", max_retries=None):  # noqa: ARG001
        return status, body, error

    monkeypatch.setattr(module, "get_json", _fake)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def fixture():
    return load_fixture
