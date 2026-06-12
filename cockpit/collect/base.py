"""Shared collector primitives: the :class:`Fetched` record and ``now_iso``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Fetched(BaseModel):
    """One observed value plus the audit trail of how it was fetched.

    A thin envelope returned by the lower helpers in a collector: it pairs the
    extracted ``value`` with the endpoint consulted, the HTTP status, the fetch
    timestamp, and any error string. ``error`` being non-``None`` does not imply
    ``value`` is ``None`` (e.g. a parsed-but-empty body) — callers inspect both.
    """

    value: Any | None = None
    endpoint: str | None = None
    http_status: int | None = None
    fetched_at: str
    error: str | None = None

    @classmethod
    def make(
        cls,
        value: Any | None,
        endpoint: str | None,
        http_status: int | None,
        error: str | None = None,
    ) -> Fetched:
        """Build a :class:`Fetched` stamped with the current time."""
        return cls(
            value=value,
            endpoint=endpoint,
            http_status=http_status,
            fetched_at=now_iso(),
            error=error,
        )
