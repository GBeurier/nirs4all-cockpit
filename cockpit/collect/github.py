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

import json
import os
import re
import signal
import subprocess
from typing import Any
from urllib.parse import quote

from ..http import get_json

API = "https://api.github.com"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


GH_TIMEOUT_S = _env_float("COCKPIT_GH_TIMEOUT", 8.0)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _headers() -> dict[str, str]:
    headers = {"X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(url: str) -> tuple[int, Any | None, str | None]:
    headers = _headers()
    status, body, error = get_json(url, headers=headers, accept="application/vnd.github+json")
    if status in (401, 403) and "Authorization" in headers:
        # A stale local token must not turn public GitHub endpoints into false
        # missing releases/tags. Retry anonymously; truly private endpoints will
        # still fail and be classified by the caller.
        anonymous = dict(headers)
        anonymous.pop("Authorization", None)
        retry_status, retry_body, retry_error = get_json(
            url,
            headers=anonymous,
            accept="application/vnd.github+json",
        )
        if retry_status not in (401, 403):
            return retry_status, retry_body, retry_error
    return status, body, error


def _gh_api_json(endpoint: str) -> Any | None:
    """Return ``gh api`` JSON for endpoints that require GitHub auth.

    GitHub Pages status returns 404 anonymously even for public repos. The
    cockpit's admin machine already uses ``gh`` for guarded release actions, so
    use it as a read-only fallback when direct HTTP lacks a valid token.
    """
    if _env_truthy("COCKPIT_DISABLE_GH_FALLBACK"):
        return None
    env = dict(os.environ)
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    try:
        proc = subprocess.Popen(
            ["gh", "api", endpoint],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        stdout, _stderr = proc.communicate(timeout=GH_TIMEOUT_S)
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            proc.kill()
        try:
            proc.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
        return None
    if proc.returncode != 0:
        return None
    try:
        body = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return body


def _gh_endpoint(url_or_endpoint: str) -> str:
    prefix = f"{API}/"
    if url_or_endpoint.startswith(prefix):
        return url_or_endpoint[len(prefix):]
    return url_or_endpoint


def default_branch(owner: str, repo: str) -> str | None:
    """Return the repo's default branch, or ``None`` if the repo is unreachable."""
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}")
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}")
        if isinstance(body, dict):
            status = 200
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
        if status != 200:
            body = _gh_api_json(f"repos/{owner}/{repo}/tags?per_page=100&page={page}")
            if isinstance(body, list):
                status = 200
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
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/releases?per_page=100")
        if isinstance(body, list):
            status = 200
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
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/releases/latest")
        if isinstance(body, dict):
            status = 200
    if status == 200 and isinstance(body, dict):
        assets = body.get("assets") or []
        return {
            "tag_name": body.get("tag_name"),
            "published_at": body.get("published_at"),
            "asset_downloads": sum(a.get("download_count", 0) for a in assets if isinstance(a, dict)),
        }
    return None


def commit_fact(owner: str, repo: str, ref: str) -> dict[str, Any] | None:
    """Return one commit's SHA and committer date for a branch, tag, or SHA ref."""
    ref_path = quote(ref, safe="")
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}/commits/{ref_path}")
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/commits/{ref_path}")
        if isinstance(body, dict):
            status = 200
    if status == 200 and isinstance(body, dict):
        commit = body.get("commit") if isinstance(body.get("commit"), dict) else {}
        committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        return {
            "sha": body.get("sha"),
            "committed_at": committer.get("date") or author.get("date"),
        }
    return None


def default_branch_commit(owner: str, repo: str) -> dict[str, Any] | None:
    """Return the latest commit fact on the repository default branch."""
    branch = default_branch(owner, repo) or "main"
    fact = commit_fact(owner, repo, branch)
    if fact is not None:
        fact["branch"] = branch
    return fact


def tag_fact(owner: str, repo: str, tag: str) -> dict[str, Any] | None:
    """Return tag date metadata, using tagger date for annotated tags when present."""
    tag_path = quote(tag, safe="")
    status, body, _error = _get(f"{API}/repos/{owner}/{repo}/git/ref/tags/{tag_path}")
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/git/ref/tags/{tag_path}")
        if isinstance(body, dict):
            status = 200
    if status == 200 and isinstance(body, dict):
        obj = body.get("object") if isinstance(body.get("object"), dict) else {}
        if obj.get("type") == "tag" and obj.get("url"):
            t_status, t_body, _ = _get(obj["url"])
            if t_status != 200:
                t_body = _gh_api_json(_gh_endpoint(obj["url"]))
                if isinstance(t_body, dict):
                    t_status = 200
            if t_status == 200 and isinstance(t_body, dict):
                tagger = t_body.get("tagger") if isinstance(t_body.get("tagger"), dict) else {}
                target = t_body.get("object") if isinstance(t_body.get("object"), dict) else {}
                return {
                    "tag": tag,
                    "tagged_at": tagger.get("date"),
                    "source": "annotated-tag",
                    "target_sha": target.get("sha"),
                }
        commit = commit_fact(owner, repo, tag)
        if commit is not None:
            return {
                "tag": tag,
                "tagged_at": commit.get("committed_at"),
                "source": "commit-tag",
                "target_sha": commit.get("sha"),
            }
    return None


def commits_ahead(owner: str, repo: str, base: str, head: str | None = None) -> int | None:
    """Return how many commits ``head`` is ahead of ``base`` using GitHub compare."""
    if not base:
        return None
    head_ref = head or default_branch(owner, repo) or "main"
    base_path = quote(base, safe="")
    head_path = quote(head_ref, safe="")
    url = f"{API}/repos/{owner}/{repo}/compare/{base_path}...{head_path}"
    status, body, _error = _get(url)
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/compare/{base_path}...{head_path}")
        if isinstance(body, dict):
            status = 200
    if status == 200 and isinstance(body, dict):
        ahead = body.get("ahead_by")
        return ahead if isinstance(ahead, int) else None
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
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}")
        if isinstance(body, dict):
            status = 200
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
    if status != 200:
        gh_body = _gh_api_json(f"repos/{owner}/{repo}/releases/latest")
        if isinstance(gh_body, dict):
            status, body, error = 200, gh_body, None
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
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/pages")
        if isinstance(body, dict):
            status = 200
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
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/releases?per_page=20")
        if isinstance(body, list):
            status = 200
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

    Release workflows commonly run from tags, not from the repository's default
    branch. The cockpit therefore reads the workflow's newest runs across refs
    and reports the newest concluded run, falling back to the newest in-progress
    run only when nothing has concluded yet.

    Args:
        owner: Repo owner.
        repo: Repo name.
        workflow_file: Workflow filename, e.g. ``release.yml``.

    Returns:
        ``{"file", "conclusion", "created_at", "head_sha"}`` for the newest run,
        or ``None`` if the workflow has never run / is unreachable.
    """
    if _env_truthy("COCKPIT_SKIP_WORKFLOW_PROBES"):
        return None
    url = f"{API}/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs?per_page=20"
    status, body, _error = _get(url)
    if status != 200:
        body = _gh_api_json(f"repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs?per_page=20")
        if isinstance(body, dict):
            status = 200
    if status == 200 and isinstance(body, dict):
        runs = body.get("workflow_runs") or []
        if runs:
            run = next((item for item in runs if item.get("conclusion") is not None), runs[0])
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

    Runs are filtered to the repo's default branch so the figures track the
    branch that matters (e.g. ``main``) rather than transient pull-request or
    Dependabot runs — a single failed PR run must not redden a green default
    branch. The branch is read from the API, never hardcoded.
    """
    out: dict[str, Any] = {
        "workflows": None, "total_runs": None, "recent_total": 0,
        "recent_success": 0, "recent_failure": 0, "success_rate": None,
        "last_conclusion": None, "last_created_at": None,
    }

    wstatus, wbody, _ = _get(f"{API}/repos/{owner}/{repo}/actions/workflows?per_page=100")
    if wstatus == 200 and isinstance(wbody, dict):
        out["workflows"] = wbody.get("total_count")

    branch = default_branch(owner, repo) or "main"
    rstatus, rbody, _ = _get(f"{API}/repos/{owner}/{repo}/actions/runs?branch={branch}&per_page=100")
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
        # The newest run on the branch may still be in progress (conclusion
        # null) — most visibly the cockpit's own ``collect`` run, which reads
        # this list while it is itself the newest run on ``main``. Report the
        # newest *concluded* run so the health badge reflects the last finished
        # CI result instead of a transient null.
        concluded = next((r for r in runs if r.get("conclusion") is not None), None)
        if concluded is not None:
            out["last_conclusion"] = concluded.get("conclusion")
            out["last_created_at"] = concluded.get("created_at")
        elif runs:
            out["last_created_at"] = runs[0].get("created_at")
    return out
