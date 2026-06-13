"""GitHub collector: repo metadata, tags, releases, workflow runs, issues.

Uses the ambient ``GITHUB_TOKEN`` (``Authorization: Bearer ...``) when present
to lift the rate limit to 5000/h; anonymous calls still work at 60/h. Every
function returns plain data and never raises on an API error — failures surface
as ``None``/empty results so a partial collect still produces a snapshot.

Design choices required by the review:

* issues use ``/repos/{o}/{r}/issues?state=open`` (NOT the Search API, capped at
  30/min) and exclude pull requests, which that endpoint otherwise mixes in;
* the default branch is read from ``/repos/{o}/{r}`` and never hardcoded to
  ``main`` — local working checkouts of ``dag-ml*`` sit on feature branches;
* both lightweight tags and GitHub Releases are collected (the tag is the source
  of a release; the Release object carries per-asset ``download_count``).
"""

from __future__ import annotations

import os
import re
from typing import Any

from ..http import get_json

API = "https://api.github.com"


def _headers() -> dict[str, str]:
    headers = {"X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(url: str) -> tuple[int, Any | None, str | None]:
    return get_json(url, headers=_headers(), accept="application/vnd.github+json")


def default_branch(owner: str, repo: str) -> str | None:
    """Return the repo's default branch, or ``None`` if the repo is unreachable."""
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}")
    if status == 200 and isinstance(body, dict):
        return body.get("default_branch")
    return None


def tags(owner: str, repo: str) -> list[str]:
    """Return all tag names (newest first as GitHub orders them), paginated."""
    names: list[str] = []
    page = 1
    while True:
        url = f"{API}/repos/{owner}/{repo}/tags?per_page=100&page={page}"
        status, body, _error = _get(url)
        if status != 200 or not isinstance(body, list) or not body:
            break
        names.extend(t.get("name") for t in body if isinstance(t, dict) and t.get("name"))
        if len(body) < 100:
            break
        page += 1
    return names


def releases(owner: str, repo: str) -> list[dict[str, Any]]:
    """Return release objects with tag, draft/prerelease flags, and asset downloads."""
    out: list[dict[str, Any]] = []
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}/releases?per_page=100")
    if status == 200 and isinstance(body, list):
        for rel in body:
            if not isinstance(rel, dict):
                continue
            assets = rel.get("assets") or []
            downloads = sum(a.get("download_count", 0) for a in assets if isinstance(a, dict))
            out.append(
                {
                    "tag_name": rel.get("tag_name"),
                    "draft": bool(rel.get("draft")),
                    "prerelease": bool(rel.get("prerelease")),
                    "published_at": rel.get("published_at"),
                    "asset_downloads": downloads,
                }
            )
    return out


def latest_release(owner: str, repo: str) -> dict[str, Any] | None:
    """Return the repo's ``latest`` (non-draft, non-prerelease) release, if any."""
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}/releases/latest")
    if status == 200 and isinstance(body, dict):
        assets = body.get("assets") or []
        return {
            "tag_name": body.get("tag_name"),
            "published_at": body.get("published_at"),
            "asset_downloads": sum(a.get("download_count", 0) for a in assets if isinstance(a, dict)),
        }
    return None


def repo_stats(owner: str, repo: str, *, with_traffic: bool = False) -> dict[str, Any]:
    """Collect public repo stats, and (only when ``with_traffic``) 14-day traffic.

    Public block (no auth): stars, forks, watchers, size, license, pushed_at,
    default_branch, and ``_open_issues_count`` (GitHub's count that mixes issues
    and PRs — the reconcile layer subtracts real issues to derive ``open_prs``).

    Traffic block: ``/traffic/views`` and ``/traffic/clones`` need a token with
    **push** access and expose semi-private analytics, so it is collected **only**
    when ``with_traffic=True`` (a local admin run) — never in the public/committed
    snapshot. Without push access the calls 403 and the fields stay ``None``.
    """
    out: dict[str, Any] = {
        "stars": None, "forks": None, "watchers": None, "size_kb": None,
        "language": None, "license": None, "pushed_at": None, "default_branch": None,
        "_open_issues_count": None,
        "traffic_views_14d": None, "traffic_views_uniques": None,
        "traffic_clones_14d": None, "traffic_clones_uniques": None,
        "traffic_available": False,
    }
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}")
    if status == 200 and isinstance(body, dict):
        lic = body.get("license")
        out.update(
            stars=body.get("stargazers_count"),
            forks=body.get("forks_count"),
            watchers=body.get("subscribers_count"),
            size_kb=body.get("size"),
            language=body.get("language"),
            license=(lic.get("spdx_id") if isinstance(lic, dict) else None),
            pushed_at=body.get("pushed_at"),
            default_branch=body.get("default_branch"),
            _open_issues_count=body.get("open_issues_count"),
        )

    if with_traffic:
        vstatus, vbody, _ = _get(f"{API}/repos/{owner}/{repo}/traffic/views")
        if vstatus == 200 and isinstance(vbody, dict):
            out["traffic_views_14d"] = vbody.get("count")
            out["traffic_views_uniques"] = vbody.get("uniques")
            out["traffic_available"] = True
        cstatus, cbody, _ = _get(f"{API}/repos/{owner}/{repo}/traffic/clones")
        if cstatus == 200 and isinstance(cbody, dict):
            out["traffic_clones_14d"] = cbody.get("count")
            out["traffic_clones_uniques"] = cbody.get("uniques")
            out["traffic_available"] = True
    return out


def latest_release_fact(owner: str, repo: str) -> dict[str, Any]:
    """Probe the latest release, carrying the HTTP status for state classification.

    Unlike :func:`latest_release` (which collapses any non-200 to ``None``), this
    keeps the status so the reconcile layer can tell a genuine *no release yet*
    (404 → ``missing``) apart from a transport/rate-limit failure (status 0 / 5xx
    → ``unknown``).

    Returns:
        ``{"published_version", "http_status", "error", "asset_downloads"}``.
    """
    status, body, error = _get(f"{API}/repos/{owner}/{repo}/releases/latest")
    if status == 200 and isinstance(body, dict):
        all_release_downloads = sum(rel.get("asset_downloads", 0) for rel in releases(owner, repo))
        if all_release_downloads <= 0:
            assets = body.get("assets") or []
            all_release_downloads = sum(a.get("download_count", 0) for a in assets if isinstance(a, dict))
        return {
            "published_version": body.get("tag_name"),
            "http_status": 200,
            "error": None,
            "asset_downloads": all_release_downloads,
        }
    return {"published_version": None, "http_status": status, "error": error, "asset_downloads": None}


def pages_status(owner: str, repo: str) -> dict[str, Any]:
    """GitHub Pages site status: enabled?, html_url, build status, custom domain.

    ``GET /repos/{o}/{r}/pages`` → 200 when Pages is enabled (with ``html_url``
    and a ``status`` of ``built``/``building``/``errored``/``null``); 404 = no
    Pages site. Needs a token for private repos; public repos answer anonymously.
    """
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}/pages")
    if status == 200 and isinstance(body, dict):
        return {
            "available": True,
            "html_url": body.get("html_url"),
            "build_status": body.get("status"),
            "cname": body.get("cname"),
        }
    return {"available": False, "html_url": None, "build_status": None, "cname": None}


def release_asset_matches(owner: str, repo: str, pattern: str) -> bool:
    """Whether any asset on the repo's releases matches ``pattern`` (regex on name).

    Scans the most recent releases (one page). Used to detect a built-but-not-yet-
    published artifact — e.g. an R source tarball ``<pkg>_<ver>.tar.gz`` attached
    to a Release while the package is not on CRAN yet (a ``pending`` submission).
    """
    rx = re.compile(pattern)
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}/releases?per_page=20")
    if status == 200 and isinstance(body, list):
        for rel in body:
            if not isinstance(rel, dict):
                continue
            for asset in rel.get("assets") or []:
                if isinstance(asset, dict) and rx.search(asset.get("name", "")):
                    return True
    return False


def workflow_last_run(owner: str, repo: str, workflow_file: str) -> dict[str, Any] | None:
    """Return the most recent run of one workflow file (conclusion + sha + time).

    Args:
        owner: Repo owner.
        repo: Repo name.
        workflow_file: Workflow filename, e.g. ``release.yml``.

    Returns:
        ``{"file", "conclusion", "created_at", "head_sha"}`` for the newest run,
        or ``None`` if the workflow has never run / is unreachable.
    """
    url = f"{API}/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs?per_page=1"
    status, body, _error = _get(url)
    if status == 200 and isinstance(body, dict):
        runs = body.get("workflow_runs") or []
        if runs:
            run = runs[0]
            return {
                "file": workflow_file,
                "conclusion": run.get("conclusion"),
                "created_at": run.get("created_at"),
                "head_sha": run.get("head_sha"),
            }
    return {"file": workflow_file, "conclusion": None, "created_at": None, "head_sha": None}


def open_issues(owner: str, repo: str) -> dict[str, int]:
    """Count open *issues* (pull requests excluded) and how many are labelled bug.

    Uses the issues list endpoint (5000/h with a token) rather than Search
    Issues (30/min). The issues endpoint includes PRs, which carry a
    ``pull_request`` key, so those are filtered out.
    """
    open_count = 0
    bug_count = 0
    page = 1
    while True:
        url = f"{API}/repos/{owner}/{repo}/issues?state=open&per_page=100&page={page}"
        status, body, _error = _get(url)
        if status != 200 or not isinstance(body, list) or not body:
            break
        for item in body:
            if not isinstance(item, dict) or "pull_request" in item:
                continue
            open_count += 1
            labels = item.get("labels") or []
            names = {lbl.get("name", "").lower() for lbl in labels if isinstance(lbl, dict)}
            if "bug" in names:
                bug_count += 1
        if len(body) < 100:
            break
        page += 1
    return {"open": open_count, "bugs": bug_count}


def open_pull_requests(owner: str, repo: str) -> dict[str, Any]:
    """Open PRs for a repo: total, drafts, ready, and a light per-PR list.

    Uses ``/repos/{o}/{r}/pulls?state=open`` (paginated). ``mergeable_state`` is
    intentionally *not* fetched (it needs one extra GET per PR); draft/labels/age
    are enough for the admin view.
    """
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{API}/repos/{owner}/{repo}/pulls?state=open&per_page=100&page={page}"
        status, body, _error = _get(url)
        if status != 200 or not isinstance(body, list) or not body:
            break
        for pr in body:
            if not isinstance(pr, dict):
                continue
            items.append(
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "draft": bool(pr.get("draft")),
                    "user": (pr.get("user") or {}).get("login"),
                    "created_at": pr.get("created_at"),
                    "labels": [
                        lbl.get("name") for lbl in (pr.get("labels") or []) if isinstance(lbl, dict)
                    ],
                }
            )
        if len(body) < 100:
            break
        page += 1
    drafts = sum(1 for p in items if p["draft"])
    return {"open": len(items), "draft": drafts, "ready": len(items) - drafts, "items": items}


def dependabot_alerts(owner: str, repo: str) -> dict[str, Any]:
    """Open Dependabot alert count + severity breakdown.

    Needs a token with security scope and Dependabot enabled on the repo; a
    403/404 (feature off / no access) yields ``available=False`` rather than an
    error state. Counts the first page (100) — enough for a health signal.
    """
    url = f"{API}/repos/{owner}/{repo}/dependabot/alerts?state=open&per_page=100"
    status, body, error = _get(url)
    if status == 200 and isinstance(body, list):
        by_severity: dict[str, int] = {}
        for alert in body:
            adv = alert.get("security_advisory") if isinstance(alert, dict) else None
            sev = adv.get("severity") if isinstance(adv, dict) else None
            if sev:
                by_severity[sev] = by_severity.get(sev, 0) + 1
        return {"available": True, "open": len(body), "by_severity": by_severity, "error": None}
    return {"available": False, "open": None, "by_severity": {}, "error": error or f"http {status}"}


def code_scanning_alerts(owner: str, repo: str) -> dict[str, Any]:
    """Open code-scanning alert count (``available=False`` if disabled / no access)."""
    url = f"{API}/repos/{owner}/{repo}/code-scanning/alerts?state=open&per_page=100"
    status, body, error = _get(url)
    if status == 200 and isinstance(body, list):
        return {"available": True, "open": len(body), "error": None}
    return {"available": False, "open": None, "error": error or f"http {status}"}


def pr_counts(owner: str, repo: str) -> dict[str, Any]:
    """Closed and merged PR totals via the Search API (one call each).

    ``/search/issues`` returns a ``total_count`` so a single request gives the
    full count without paginating. Search has its own 30/min budget; two calls
    per repo stays well under it.
    """
    base = f"{API}/search/issues?q=repo:{owner}/{repo}+is:pr"

    def _count(qualifier: str) -> int | None:
        status, body, _error = _get(f"{base}+{qualifier}&per_page=1")
        if status == 200 and isinstance(body, dict):
            return body.get("total_count")
        return None

    return {"closed": _count("is:closed"), "merged": _count("is:merged")}


def actions_stats(owner: str, repo: str) -> dict[str, Any]:
    """GitHub Actions activity: workflow count, total runs, recent success rate.

    ``total_runs`` is the all-time count; the success rate is computed over the
    most recent (up to 100) runs that have a conclusion, so it reflects current
    health rather than ancient history.
    """
    out: dict[str, Any] = {
        "workflows": None, "total_runs": None, "recent_total": 0,
        "recent_success": 0, "recent_failure": 0, "success_rate": None,
        "last_conclusion": None, "last_created_at": None,
    }

    wstatus, wbody, _ = _get(f"{API}/repos/{owner}/{repo}/actions/workflows?per_page=100")
    if wstatus == 200 and isinstance(wbody, dict):
        out["workflows"] = wbody.get("total_count")

    rstatus, rbody, _ = _get(f"{API}/repos/{owner}/{repo}/actions/runs?per_page=100")
    if rstatus == 200 and isinstance(rbody, dict):
        out["total_runs"] = rbody.get("total_count")
        runs = [r for r in (rbody.get("workflow_runs") or []) if isinstance(r, dict)]
        out["recent_total"] = len(runs)
        success = sum(1 for r in runs if r.get("conclusion") == "success")
        failure = sum(1 for r in runs if r.get("conclusion") == "failure")
        out["recent_success"] = success
        out["recent_failure"] = failure
        completed = success + failure
        if completed:
            out["success_rate"] = round(success / completed * 100, 1)
        if runs:
            out["last_conclusion"] = runs[0].get("conclusion")
            out["last_created_at"] = runs[0].get("created_at")
    return out
