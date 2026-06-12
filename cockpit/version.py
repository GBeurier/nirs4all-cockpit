"""Pure version engine for nirs4all-cockpit (no network, no I/O).

Everything here is a pure function of its arguments: normalisation across the
version schemes the ecosystem mixes (``v``-prefixed git tags, SemVer, PEP 440,
R-devel ``x.y.z.9000``), version-aware comparison, and the reconcile state
machine that turns observed facts into a :data:`State`.

The state machine is the contract from the Codex review:

* Keep four version facts per package — ``manifest_version``,
  ``latest_prod_tag``, ``latest_any_tag``, ``published_version`` — and derive
  ``expected_prod_version`` = ``latest_prod_tag`` if present, else
  ``manifest_version``.
* Target status is exactly ``green | stale | missing | broken | unknown |
  excluded``. ``source_ahead`` is a *package flag*, never a status, and never
  reddens a prod target. ``planned`` is reconciled as ``missing`` by the caller
  and flagged separately.
* Comparison is always SemVer/PEP 440-aware via :mod:`packaging`, never lexical.
"""

from __future__ import annotations

import re

from packaging.version import InvalidVersion, Version

State = str  # one of: green | stale | missing | broken | unknown | excluded

# R-devel development suffix, e.g. "0.2.0.9000" → PEP 440 dev release "0.2.0.dev9000".
_R_DEVEL_RE = re.compile(r"^(\d+\.\d+\.\d+)\.(\d{4,})$")


def normalize(raw: str, scheme: str = "auto") -> str:
    """Normalise a raw version string to a canonical PEP 440 form.

    Handles a leading ``v`` (git tags), plain SemVer, PEP 440 (delegated to
    :mod:`packaging`), and the R-devel ``x.y.z.9000`` convention (mapped to a
    PEP 440 ``.devNNNN`` release so it sorts *before* its base release).

    Args:
        raw: The raw version string (e.g. ``"v1.2.3"``, ``"0.2.0a1"``,
            ``"0.2.0.9000"``).
        scheme: ``"auto"`` (default), ``"semver"``, ``"pep440"`` or
            ``"r_devel"``. ``"auto"`` tries R-devel detection then PEP 440.

    Returns:
        The canonical string form of the parsed version. If parsing fails the
        stripped raw string is returned unchanged.
    """
    s = raw.strip()
    if s.startswith(("v", "V")):
        s = s[1:]

    if scheme in ("auto", "r_devel"):
        m = _R_DEVEL_RE.match(s)
        if m:
            return str(Version(f"{m.group(1)}.dev{m.group(2)}"))
        if scheme == "r_devel":
            return s

    try:
        return str(Version(s))
    except InvalidVersion:
        return s


def is_prerelease(v: str) -> bool:
    """Return ``True`` if ``v`` is a pre-release or dev release.

    Pre-releases (``a``/``b``/``rc``) and dev releases (the R-devel mapping)
    both count, so an R-devel ``9000`` snapshot never satisfies a prod target.
    """
    try:
        parsed = Version(normalize(v))
    except InvalidVersion:
        return False
    return parsed.is_prerelease or parsed.is_devrelease


def compare(a: str, b: str) -> int:
    """Compare two versions, returning ``-1``, ``0`` or ``1``.

    Comparison is version-aware (via :mod:`packaging`), never lexical. If either
    side cannot be parsed as a version, the comparison falls back to a stable
    string comparison so the function never raises.
    """
    na, nb = normalize(a), normalize(b)
    try:
        va, vb = Version(na), Version(nb)
    except InvalidVersion:
        if na == nb:
            return 0
        return -1 if na < nb else 1
    if va == vb:
        return 0
    return -1 if va < vb else 1


def derive_expected(manifest: str | None, latest_prod_tag: str | None) -> str | None:
    """Derive the expected production version.

    The latest production tag wins when present (it is what a release actually
    shipped); otherwise the in-repo manifest version is the expectation.
    """
    if latest_prod_tag:
        return latest_prod_tag
    return manifest


def source_ahead(manifest: str | None, latest_prod_tag: str | None) -> bool:
    """Return ``True`` when the repo manifest is ahead of the latest prod tag.

    This is a package-level signal (an unreleased bump), surfaced as the
    ``source_ahead`` flag. It never reddens a prod target's status.
    """
    if manifest is None or latest_prod_tag is None:
        return False
    return compare(manifest, latest_prod_tag) > 0


def classify(
    expected: str | None,
    published: str | None,
    *,
    http_status: int | None,
    transient_error: bool,
    excluded: bool,
    planned: bool,
) -> State:
    """Reconcile observed facts for one target into a :data:`State`.

    Precedence, highest first:

    1. ``excluded`` → ``"excluded"`` (counted in summary, kept out of the
       roll-up, never turned green).
    2. ``transient_error`` or a 429/timeout/5xx (``http_status >= 500``) →
       ``"unknown"``.
    3. A 404 (or ``planned`` with nothing published) → ``"missing"``.
    4. Nothing published while a version was expected → ``"missing"``.
    5. ``published == expected`` → ``"green"``; ``published < expected`` →
       ``"stale"``; ``published > expected`` → ``"green"`` (source-ahead is a
       flag, never a red target).

    Args:
        expected: Expected production version (``derive_expected`` output).
        published: Version observed on the registry, or ``None`` if absent.
        http_status: HTTP status of the version probe, if any.
        transient_error: ``True`` for timeouts / parse failures / rate limits.
        excluded: ``True`` if the target is declared ``state: excluded``.
        planned: ``True`` if the target has no release workflow yet.

    Returns:
        The reconciled state for the target.
    """
    if excluded:
        return "excluded"

    if transient_error or http_status == 429 or (http_status is not None and http_status >= 500):
        return "unknown"

    if http_status == 404 or (planned and published is None):
        return "missing"

    if published is None:
        return "missing"

    if expected is None:
        # Something is published but we have no expectation to compare it to;
        # treat presence as healthy rather than fabricating a mismatch.
        return "green"

    cmp = compare(published, expected)
    if cmp < 0:
        return "stale"
    return "green"
