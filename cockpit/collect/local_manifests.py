"""Source-of-truth version reader (``manifest_version``).

Reads the in-repo version declaration named by a package's ``source_of_truth``.
The file is read **locally** when a sibling checkout exists under
``SIBLINGS_ROOT/<repo>``; otherwise it is fetched over **raw GitHub** at the
repo's *default branch* (resolved via :func:`github.default_branch`, never
hardcoded to ``main`` — local ``dag-ml*`` checkouts sit on work branches).

``SIBLINGS_ROOT`` defaults to the parent of this checkout (the sibling working
tree) and is overridable with ``N4A_SIBLINGS_ROOT`` — the CI cron sets it to a
directory of shallow clones so code/manifest stats work off the runner too.

Strategies (``source_of_truth.strategy``):

* ``python_attr``      — regex ``__version__ = "x.y.z"`` (attr name from config).
* ``python_pyproject`` — TOML ``[project].version``.
* ``c_header``         — regex ``N4M_PROJECT_VERSION_STRING "x.y.z"`` (attr name
  from config, used as the macro to match).
* ``cargo_workspace``  — TOML ``[workspace.package].version``.
* ``cargo_package``    — TOML ``[package].version``.
* ``r_description``    — ``Version:`` line of a DESCRIPTION file.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from ..http import get_json
from . import github

# Where sibling repo checkouts live. Default: the parent of this checkout (the
# working tree that holds the ecosystem repos side by side). Override with
# N4A_SIBLINGS_ROOT (the CI cron points it at its shallow-clone directory).
_DEFAULT_SIBLINGS_ROOT = Path(__file__).resolve().parents[3]
SIBLINGS_ROOT = Path(os.environ.get("N4A_SIBLINGS_ROOT", str(_DEFAULT_SIBLINGS_ROOT)))
RAW_BASE = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def read_manifest_version(
    *,
    owner: str,
    repo: str,
    strategy: str,
    path: str,
    attr: str | None = None,
) -> str | None:
    """Resolve a package's manifest version, locally or via raw GitHub.

    Returns ``None`` when the file is unreachable or the version cannot be
    extracted with the given strategy.
    """
    text = _read_text(owner=owner, repo=repo, path=path)
    if text is None:
        return None
    return _extract(strategy, text, attr)


def _read_text(*, owner: str, repo: str, path: str) -> str | None:
    local = SIBLINGS_ROOT / repo / path
    if local.is_file():
        try:
            return local.read_text(encoding="utf-8")
        except OSError:
            return None

    branch = github.default_branch(owner, repo) or "main"
    url = RAW_BASE.format(owner=owner, repo=repo, branch=branch, path=path)
    status, _body, _error = get_json(url, accept="text/plain")
    if status != 200:
        return None
    # raw GitHub returns text; get_json only parses JSON, so re-fetch the body
    # text via the same primitive is not possible — read directly with httpx.
    return _read_raw_text(url)


def _read_raw_text(url: str) -> str | None:
    import httpx

    from ..http import TIMEOUT_S, USER_AGENT

    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
            timeout=TIMEOUT_S,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    return resp.text


def _extract(strategy: str, text: str, attr: str | None) -> str | None:
    if strategy == "python_attr":
        name = attr or "__version__"
        m = re.search(rf"{re.escape(name)}\s*=\s*['\"]([^'\"]+)['\"]", text)
        return m.group(1) if m else None

    if strategy == "c_header":
        macro = attr or "N4M_PROJECT_VERSION_STRING"
        m = re.search(rf"#\s*define\s+{re.escape(macro)}\s+\"([^\"]+)\"", text)
        return m.group(1) if m else None

    if strategy == "r_description":
        m = re.search(r"^Version:\s*(.+?)\s*$", text, re.MULTILINE)
        return m.group(1) if m else None

    if strategy in ("python_pyproject", "cargo_workspace", "cargo_package"):
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return None
        if strategy == "python_pyproject":
            return (data.get("project") or {}).get("version")
        if strategy == "cargo_workspace":
            return ((data.get("workspace") or {}).get("package") or {}).get("version")
        if strategy == "cargo_package":
            return (data.get("package") or {}).get("version")

    return None
