"""``n4a-cockpit`` — Typer CLI for the nirs4all release/health cockpit.

Commands:

* ``collect`` — build a reconciled :class:`~cockpit.model.Snapshot` from the
  inventory and write ``data/current.json`` (network unless ``--offline``).
* ``validate-targets`` — structurally validate ``ops/targets.yaml`` against the
  contract and the cockpit's consistency rules.
* ``summarize`` — print the summary block of a snapshot.
* ``status`` — print the package × registry matrix from a snapshot (rich table
  when available, plain text otherwise).
* ``admin run`` — preview/trigger a release workflow via ``gh`` (guarded).
* ``admin set-secret`` — set a GitHub secret from a file (never echoed).
* ``admin actions`` — manual-action checklist with auto-checks vs the snapshot.

The CLI is the *only* place wall-clock time enters the pipeline:
``generated_at`` is stamped here with ``datetime.now(timezone.utc).isoformat()``
and passed into the pure collection/reconcile layer.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from cockpit import reconcile
from cockpit import snapshot as snapshot_io
from cockpit import version as ver
from cockpit.model import (
    ActionsStats,
    Issues,
    RepoStats,
    SearchConsoleStats,
    SentryStatus,
    Snapshot,
    Targets,
    Totals,
    Visits,
    WorkflowHealth,
)

app = typer.Typer(
    add_completion=False,
    help="Release/health cockpit for the nirs4all ecosystem (aggregates, never reimplements).",
    no_args_is_help=True,
)
admin_app = typer.Typer(add_completion=False, help="Guarded gh-wrapping admin actions.", no_args_is_help=True)
app.add_typer(admin_app, name="admin")

DEFAULT_TARGETS = Path("ops/targets.yaml")
DEFAULT_CURRENT = Path("data/current.json")
DEFAULT_ACTIONS = Path("ops/manual-actions.yaml")

_STATE_COLORS = {
    "green": "green",
    "stale": "yellow",
    "pending": "magenta",
    "missing": "red",
    "broken": "red",
    "unknown": "blue",
    "excluded": "dim",
}

_GITHUB_SOURCE_FIELDS = (
    "latest_prod_tag",
    "latest_any_tag",
    "commit",
    "latest_prod_tag_at",
    "latest_release_at",
    "latest_version_at",
    "latest_version_source",
    "last_commit_at",
    "commits_ahead_of_latest_prod_tag",
)


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #


def _utc_now() -> str:
    """The one wall-clock stamp for the pipeline (UTC ISO-8601)."""
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 (3.10-compatible)


def _load_targets(path: Path) -> Targets:
    """Parse and validate ``ops/targets.yaml`` into :class:`Targets`."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Targets.model_validate(raw)


def _load_snapshot(path: Path) -> Snapshot:
    """Load and validate a ``current.json`` snapshot."""
    if not path.is_file():
        typer.secho(f"snapshot not found: {path} (run `collect` first)", fg="red", err=True)
        raise typer.Exit(code=2)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot.model_validate(raw)


def _find_package(targets: Targets, package_id: str):
    """Return the package with ``package_id`` or exit with a clear error."""
    for pkg in targets.packages:
        if pkg.id == package_id:
            return pkg
    known = ", ".join(p.id for p in targets.packages)
    typer.secho(f"unknown package {package_id!r} (known: {known})", fg="red", err=True)
    raise typer.Exit(code=2)


# --------------------------------------------------------------------------- #
# collect
# --------------------------------------------------------------------------- #


@app.command()
def collect(
    targets: Path = typer.Option(DEFAULT_TARGETS, "--targets", help="Inventory YAML."),
    out: Path = typer.Option(DEFAULT_CURRENT, "--out", help="Where to write current.json."),
    only: str | None = typer.Option(
        None, "--only", help="Comma-separated package ids to collect (default: all)."
    ),
    offline: bool = typer.Option(
        False, "--offline", help="Read only fixtures/cache; non-cached probes become 'unknown'."
    ),
    with_traffic: bool = typer.Option(
        False,
        "--with-traffic",
        help="Collect GitHub traffic (views/clones). Push-scoped + semi-private — "
        "LOCAL admin runs only, never the public/committed snapshot.",
    ),
) -> None:
    """Build a reconciled snapshot from the inventory and write ``current.json``."""
    targets_model = _load_targets(targets)
    only_ids = [p.strip() for p in only.split(",") if p.strip()] if only else None
    if only_ids and out.resolve() == DEFAULT_CURRENT.resolve():
        typer.secho(
            "refusing to write a partial --only snapshot to data/current.json; "
            "pass --out to an explicit scratch path instead",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=2)

    # Coverage is read from each repo's ``coverage.xml``, which is not always
    # present (CI shallow-clones a repo without it). Carry the last-known coverage
    # from the committed snapshot forward so a scan that lacks the artifact does
    # not flap the column back to "—".
    prior_coverage: dict[str, float] = {}
    prior_snapshot: dict | None = None
    if out.exists():
        try:
            prior_snapshot = json.loads(out.read_text(encoding="utf-8"))
            for p in prior_snapshot.get("packages", []):
                cov = (p.get("code_stats") or {}).get("coverage_pct")
                if cov is not None:
                    prior_coverage[p["repo"]] = cov
        except (OSError, ValueError):
            pass

    snap = reconcile.build_snapshot(
        targets_model,
        only=only_ids,
        offline=offline,
        with_traffic=with_traffic,
        generated_at=_utc_now(),
        run_id=os.environ.get("GITHUB_RUN_ID"),
    )
    for p in snap.packages:
        if p.code_stats and p.code_stats.coverage_pct is None and p.repo in prior_coverage:
            p.code_stats.coverage_pct = prior_coverage[p.repo]
    _carry_forward_public_signals(snap, prior_snapshot)

    snapshot_io.write_snapshot(snap, out)

    typer.secho(f"wrote {out}", fg="green")
    _print_summary(snap)


def _carry_forward_public_signals(snap: Snapshot, prior_snapshot: dict | None) -> None:
    """Keep token-backed or flaky public aggregates when a collect lacks them.

    Maintainer machines often have GitHub auth but not GoatCounter/Sentry tokens.
    A local refresh should not erase the last successful public counters from the
    committed snapshot; the CI collect job will replace them when its secrets are
    available. Registry download counters can also transiently disappear when a
    stats API rate-limits; keep the prior counters when the target is still
    published and the new collect has no counts.
    """
    if not prior_snapshot:
        return

    prior_visits = prior_snapshot.get("visits") or {}
    if not snap.visits.available and prior_visits.get("available") and _missing_public_signal_token(snap.visits.error):
        snap.visits = Visits.model_validate(prior_visits)

    prior_sentry = prior_snapshot.get("sentry") or {}
    if not snap.sentry.available and prior_sentry.get("available") and _missing_public_signal_token(snap.sentry.error):
        snap.sentry = SentryStatus.model_validate(prior_sentry)

    prior_search_console = prior_snapshot.get("search_console") or {}
    if (
        not snap.search_console.available
        and prior_search_console.get("available")
        and _missing_public_signal_token(snap.search_console.error)
    ):
        snap.search_console = SearchConsoleStats.model_validate(prior_search_console)

    _carry_forward_github_public_signals(snap, prior_snapshot)
    _carry_forward_target_downloads(snap, prior_snapshot)
    snap.totals = _compute_totals(snap)


def _carry_forward_github_public_signals(snap: Snapshot, prior_snapshot: dict) -> None:
    """Keep prior GitHub facts when a local collect loses them transiently."""
    prior_packages = {
        package.get("id"): package
        for package in prior_snapshot.get("packages", [])
        if isinstance(package, dict) and package.get("id")
    }

    for package in snap.packages:
        prior = prior_packages.get(package.id)
        if not prior:
            continue

        prior_source = prior.get("source") or {}
        source = package.source.model_dump()
        if (
            _source_missing_github_facts(source)
            and source.get("manifest_version") == prior_source.get("manifest_version")
        ):
            for field in _GITHUB_SOURCE_FIELDS:
                if source.get(field) is None and prior_source.get(field) is not None:
                    source[field] = prior_source[field]
            package.source = type(package.source).model_validate(source)
        elif _source_missing_github_facts(source):
            local_source = _local_git_source_facts(package.repo, source.get("manifest_version"))
            if local_source:
                source.update(local_source)
                package.source = type(package.source).model_validate(source)

        repo_stats_missing = _repo_stats_missing_public_facts((package.repo_stats or RepoStats()).model_dump())
        prior_repo_stats = prior.get("repo_stats") or {}
        if package.repo_stats and prior_repo_stats and repo_stats_missing:
            package.repo_stats = RepoStats.model_validate(prior_repo_stats)

        prior_actions_stats = prior.get("actions_stats") or {}
        if (
            package.actions_stats
            and prior_actions_stats
            and _actions_stats_missing_public_facts(package.actions_stats.model_dump())
        ):
            package.actions_stats = ActionsStats.model_validate(prior_actions_stats)

        prior_workflows = prior.get("workflows") or []
        _carry_forward_workflows(package, prior_workflows)

        prior_issues = prior.get("issues") or {}
        if prior_issues and repo_stats_missing:
            package.issues = Issues.model_validate(prior_issues)


def _source_missing_github_facts(source: dict) -> bool:
    return all(source.get(field) is None for field in _GITHUB_SOURCE_FIELDS)


def _repo_stats_missing_public_facts(repo_stats: dict) -> bool:
    return all(
        repo_stats.get(field) is None
        for field in ("stars", "forks", "watchers", "size_kb", "pushed_at", "default_branch")
    )


def _actions_stats_missing_public_facts(actions_stats: dict) -> bool:
    return (
        actions_stats.get("workflows") is None
        and actions_stats.get("total_runs") is None
        and actions_stats.get("success_rate") is None
        and not actions_stats.get("recent_total")
    )


def _carry_forward_workflows(package, prior_workflows: list[dict]) -> None:
    if not prior_workflows:
        return

    if not package.workflows:
        package.workflows = [WorkflowHealth.model_validate(workflow) for workflow in prior_workflows]
        return

    prior_by_file = {workflow.get("file"): workflow for workflow in prior_workflows if isinstance(workflow, dict)}
    merged = []
    for workflow in package.workflows:
        current = workflow.model_dump()
        prior = prior_by_file.get(current.get("file"))
        if prior and _workflow_missing_public_facts(current):
            current = {**current, **prior}
        merged.append(WorkflowHealth.model_validate(current))
    package.workflows = merged


def _workflow_missing_public_facts(workflow: dict) -> bool:
    return (
        workflow.get("conclusion") is None
        and workflow.get("created_at") is None
        and workflow.get("head_sha") is None
    )


def _local_git_source_facts(repo: str, manifest_version: str | None) -> dict | None:
    if manifest_version is None:
        return None

    repo_path = _local_repo_path(repo)
    if repo_path is None:
        return None

    tags = _git(repo_path, "tag", "--list", "--sort=-creatordate")
    if tags is None:
        return None

    candidates = [tag for tag in tags.splitlines() if ver.normalize(tag) == ver.normalize(manifest_version)]
    if not candidates:
        return None

    preferred = [f"v{manifest_version}", manifest_version]
    latest_prod_tag = next((tag for tag in preferred if tag in candidates), candidates[0])
    commit = _git(repo_path, "rev-parse", "HEAD")
    last_commit_at = _git(repo_path, "log", "-1", "--format=%cI", "HEAD")
    tagged_at = _git(repo_path, "log", "-1", "--format=%cI", latest_prod_tag)
    ahead_raw = _git(repo_path, "rev-list", f"{latest_prod_tag}..HEAD", "--count")
    try:
        ahead = int(ahead_raw) if ahead_raw is not None else None
    except ValueError:
        ahead = None

    return {
        "latest_prod_tag": latest_prod_tag,
        "latest_any_tag": latest_prod_tag,
        "expected_prod_version": latest_prod_tag,
        "commit": commit,
        "latest_prod_tag_at": tagged_at,
        "latest_version_at": tagged_at,
        "latest_version_source": "tag" if tagged_at else None,
        "last_commit_at": last_commit_at,
        "commits_ahead_of_latest_prod_tag": ahead,
    }


def _local_repo_path(repo: str) -> Path | None:
    for candidate in (Path.cwd().parent / repo, Path.cwd() / repo):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git(repo_path: Path, *args: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_path), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    return out.strip()


def _compute_totals(snap: Snapshot) -> Totals:
    totals = Totals(packages=len(snap.packages), repos=len({p.repo for p in snap.packages}))
    for package in snap.packages:
        totals.open_issues += package.issues.open
        if package.repo_stats:
            totals.stars += package.repo_stats.stars or 0
            totals.forks += package.repo_stats.forks or 0
            totals.watchers += package.repo_stats.watchers or 0
        if package.code_stats:
            totals.loc_code += package.code_stats.loc_code
            totals.loc_total += package.code_stats.loc_total
            totals.tests += package.code_stats.tests
            totals.files += package.code_stats.files
        if package.actions_stats and package.actions_stats.total_runs:
            totals.workflow_runs += package.actions_stats.total_runs
        for target in package.targets:
            totals.downloads_last_month += target.downloads.last_month or 0
    return totals


def _carry_forward_target_downloads(snap: Snapshot, prior_snapshot: dict) -> None:
    prior_targets = {
        (package.get("id"), target.get("registry"), target.get("name")): target
        for package in prior_snapshot.get("packages", [])
        for target in package.get("targets", [])
        if isinstance(target, dict)
    }

    for package in snap.packages:
        for target in package.targets:
            if _has_download_counts(target.downloads.model_dump()):
                continue
            prior_target = prior_targets.get((package.id, target.registry, target.name))
            if not prior_target or target.status not in {"green", "stale", "pending"}:
                continue
            prior_downloads = prior_target.get("downloads") or {}
            if _has_download_counts(prior_downloads):
                target.downloads = type(target.downloads).model_validate(prior_downloads)


def _has_download_counts(downloads: dict) -> bool:
    if any(downloads.get(key) is not None for key in ("last_day", "last_week", "last_month", "total")):
        return True
    windows = downloads.get("windows") or {}
    return any(value is not None for value in windows.values())


def _missing_public_signal_token(error: str | None) -> bool:
    """Whether a public aggregate is absent because this collect lacks secrets."""
    return (
        error is None
        or "no GOATCOUNTER_TOKEN" in error
        or "no SENTRY_AUTH_TOKEN" in error
        or "GOOGLE_SEARCH_CONSOLE" in error
        or "GOOGLE_APPLICATION_CREDENTIALS" in error
    )


# --------------------------------------------------------------------------- #
# validate-targets
# --------------------------------------------------------------------------- #


@app.command("validate-targets")
def validate_targets(
    path: Path = typer.Argument(DEFAULT_TARGETS, help="Inventory YAML to validate."),
) -> None:
    """Validate the inventory against the contract and the consistency rules.

    Beyond the pydantic schema, it enforces:

    * unique ``(registry, name)`` per package;
    * a declared ``workflow`` for any ``danger: publish``/``dangerous`` target;
    * a mandatory ``reason`` on every ``excluded`` target;
    * no ``workflow`` on a ``planned`` target (planned = no button yet);
    * no ``workflow`` on a ``manual`` target (manual = human-only web/action board).

    Exits non-zero on the first batch of violations.
    """
    try:
        model = _load_targets(path)
    except ValidationError as exc:
        typer.secho(f"INVALID (schema): {path}", fg="red", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    errors: list[str] = []
    for pkg in model.packages:
        seen: set[tuple[str, str]] = set()
        for target in pkg.targets:
            key = (target.registry, target.name)
            if key in seen:
                errors.append(f"{pkg.id}: duplicate target {target.registry}:{target.name}")
            seen.add(key)

            if target.state == "excluded" and not target.reason:
                errors.append(f"{pkg.id}: excluded target {target.registry}:{target.name} has no reason")

            if target.state == "planned" and target.workflow is not None:
                errors.append(
                    f"{pkg.id}: planned target {target.registry}:{target.name} must not declare a workflow"
                )

            if target.state == "manual" and target.workflow is not None:
                errors.append(
                    f"{pkg.id}: manual target {target.registry}:{target.name} must not declare a workflow"
                )

            wf = target.workflow
            if wf is not None and wf.danger in ("publish", "dangerous") and not wf.file:
                errors.append(
                    f"{pkg.id}: {target.registry}:{target.name} danger={wf.danger} needs a workflow file"
                )

    if errors:
        typer.secho(f"INVALID: {path} ({len(errors)} problem(s))", fg="red", err=True)
        for err in errors:
            typer.echo(f"  - {err}", err=True)
        raise typer.Exit(code=1)

    n_pkg = len(model.packages)
    n_tgt = sum(len(p.targets) for p in model.packages)
    typer.secho(f"OK: {path} — {n_pkg} packages, {n_tgt} targets", fg="green")


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #


def _print_summary(snap: Snapshot) -> None:
    """Print the snapshot summary counts in canonical order."""
    order = ["green", "stale", "pending", "missing", "broken", "unknown", "excluded"]
    parts = [f"{state}={snap.summary.get(state, 0)}" for state in order]
    typer.echo(f"generated_at: {snap.generated_at}")
    typer.echo("summary: " + "  ".join(parts))
    v = snap.visits
    if v.available:
        w = v.windows
        pages = f" · {len(v.pages)} pages" if v.pages else ""
        typer.echo(f"visits: 30d={w.get('30d')} total={w.get('total')}{pages}")


@app.command()
def summarize(
    path: Path = typer.Argument(DEFAULT_CURRENT, help="Snapshot to summarize."),
) -> None:
    """Print the summary block of a snapshot."""
    _print_summary(_load_snapshot(path))


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #


@app.command()
def status(
    pkg: str | None = typer.Argument(None, help="Restrict to a single package id."),
    path: Path = typer.Option(DEFAULT_CURRENT, "--path", help="Snapshot to read."),
) -> None:
    """Print the package × registry status matrix from a snapshot."""
    snap = _load_snapshot(path)
    packages = [p for p in snap.packages if pkg is None or p.id == pkg]
    if not packages:
        typer.secho(f"package {pkg!r} not in snapshot", fg="red", err=True)
        raise typer.Exit(code=2)

    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        _status_plain(packages)
        return

    console = Console()
    for package in packages:
        flags = f" [{', '.join(package.flags)}]" if package.flags else ""
        table = Table(
            title=f"{package.id}  rollup={package.rollup}{flags}",
            show_lines=False,
        )
        table.add_column("registry")
        table.add_column("name")
        table.add_column("published")
        table.add_column("status")
        table.add_column("downloads", justify="right")
        for target in package.targets:
            color = _STATE_COLORS.get(target.status, "white")
            dl = target.downloads.last_month
            status = f"{target.status} (planned)" if target.planned else target.status
            table.add_row(
                target.registry,
                target.name,
                target.published_version or "—",
                f"[{color}]{status}[/{color}]",
                "—" if dl is None else str(dl),
            )
        console.print(table)


def _status_plain(packages) -> None:
    """Plain-text fallback for ``status`` when ``rich`` is unavailable."""
    for package in packages:
        flags = f" [{', '.join(package.flags)}]" if package.flags else ""
        typer.echo(f"\n{package.id}  rollup={package.rollup}{flags}")
        for target in package.targets:
            published = target.published_version or "—"
            dl = target.downloads.last_month
            dl_s = "—" if dl is None else str(dl)
            status = f"{target.status} (planned)" if target.planned else target.status
            typer.echo(
                f"  {target.registry:<14} {target.name:<28} {published:<12} "
                f"{status:<17} dl/mo={dl_s}"
            )


# --------------------------------------------------------------------------- #
# admin
# --------------------------------------------------------------------------- #


def _emit(result) -> None:
    """Print an :class:`~cockpit.admin.AdminResult`'s messages."""
    for msg in result.messages:
        typer.echo(msg)


def _parse_input_options(values: list[str] | None) -> dict[str, str]:
    """Parse repeated ``--input key=value`` options for workflow dispatch."""
    out: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            typer.secho(f"invalid --input {raw!r}: expected key=value", fg="red", err=True)
            raise typer.Exit(code=2)
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            typer.secho(f"invalid --input {raw!r}: key is empty", fg="red", err=True)
            raise typer.Exit(code=2)
        out[key] = value
    return out


@admin_app.command("run")
def admin_run(
    pkg: str = typer.Argument(..., help="Package id from the inventory."),
    registry: str = typer.Argument(..., help="Registry key (pypi/crates/npm/r-universe/...)."),
    name: str | None = typer.Option(None, "--name", help="Exact registry name (disambiguates)."),
    ref: str = typer.Option("main", "--ref", help="Dispatch ref (branch or tag)."),
    input_values: list[str] | None = typer.Option(
        None, "--input", "-i", help="Workflow dispatch input as key=value; repeat for multiple inputs."
    ),
    publish: bool = typer.Option(False, "--publish/--no-publish", help="Flip the publish gate on."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview only (default)."),
    targets: Path = typer.Option(DEFAULT_TARGETS, "--targets", help="Inventory YAML."),
) -> None:
    """Preview or trigger a release workflow for one target (guarded by ``gh``)."""
    from cockpit import admin

    package = _find_package(_load_targets(targets), pkg)

    confirm = publish and not dry_run
    if confirm and sys.stdin.isatty():
        typer.confirm(
            f"This will dispatch a PUBLISHING run of {pkg}:{registry} (ref={ref}). Continue?",
            abort=True,
        )

    try:
        result = admin.run_workflow(
            package,
            registry,
            name=name,
            ref=ref,
            inputs=_parse_input_options(input_values),
            dry_run=dry_run,
            publish=publish if publish else None,
            confirm=confirm,
            execute=not dry_run,
        )
    except admin.AdminError as exc:
        typer.secho(f"refused: {exc}", fg="red", err=True)
        raise typer.Exit(code=2) from exc

    _emit(result)
    if result.executed and result.returncode not in (0, None):
        raise typer.Exit(code=result.returncode)


@admin_app.command("set-secret")
def admin_set_secret(
    repo: str = typer.Argument(..., help="Repo name or owner/repo slug."),
    name: str = typer.Argument(..., help="Secret name (e.g. NPM_TOKEN)."),
    from_file: Path = typer.Option(..., "--from-file", help="File holding the secret value (never echoed)."),
) -> None:
    """Set a GitHub Actions secret from a file via ``gh secret set`` (never echoed)."""
    from cockpit import admin

    if sys.stdin.isatty():
        typer.confirm(f"Set secret {name} on {repo} from {from_file}?", abort=True)

    try:
        result = admin.set_secret(repo, name, from_file)
    except admin.AdminError as exc:
        typer.secho(f"refused: {exc}", fg="red", err=True)
        raise typer.Exit(code=2) from exc

    _emit(result)
    if result.returncode not in (0, None):
        raise typer.Exit(code=result.returncode)


@admin_app.command("collect")
def admin_collect(
    targets: Path = typer.Option(DEFAULT_TARGETS, "--targets", help="Inventory YAML."),
    out: Path = typer.Option(
        Path("data/admin/snapshot.admin.json"), "--out", help="Local-only admin snapshot path."
    ),
    only: str | None = typer.Option(None, "--only", help="Comma-separated package ids."),
) -> None:
    """Collect LOCAL-ONLY admin signals: traffic, open PRs, security alerts, Sentry.

    Writes a gitignored ``data/admin/snapshot.admin.json`` — never the public
    snapshot. Traffic needs a push-scoped token; Sentry needs ``SENTRY_AUTH_TOKEN``
    (both degrade gracefully when absent).
    """
    from cockpit import admin_collect as admin_collect_mod

    model = _load_targets(targets)
    only_ids = [p.strip() for p in only.split(",") if p.strip()] if only else None
    snap = admin_collect_mod.build_admin_snapshot(model, only=only_ids, generated_at=_utc_now())

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    typer.secho(f"wrote {out}  (LOCAL ONLY — gitignored, never deployed)", fg="yellow")

    s = snap.sentry
    typer.echo(f"sentry: available={s.available} unresolved={s.unresolved}" + (f" ({s.error})" if s.error else ""))
    for r in snap.repos:
        typer.echo(
            f"  {r.repo:28} PRs open={r.pulls.open} (draft {r.pulls.draft}) | "
            f"dependabot={r.security.dependabot_open} | "
            f"views14d={r.traffic.views_14d} clones14d={r.traffic.clones_14d}"
        )


@admin_app.command("actions")
def admin_actions(
    actions: Path = typer.Option(DEFAULT_ACTIONS, "--actions", help="Manual-actions YAML."),
    current: Path = typer.Option(DEFAULT_CURRENT, "--current", help="Snapshot for auto-checks."),
    md: bool = typer.Option(False, "--md", help="Render Markdown instead of plain text."),
    json_out: Path | None = typer.Option(None, "--json-out", help="Write public evaluated actions JSON."),
) -> None:
    """Render the manual-action checklist with auto-checks against the snapshot."""
    from cockpit import manual_actions

    snap = _load_snapshot(current) if current.is_file() else None
    evaluated = manual_actions.evaluate_all(manual_actions.load_actions(actions), snap)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = manual_actions.public_payload(evaluated, snap)
        json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        typer.secho(f"wrote {json_out}", fg="green")
        if not md:
            return
    typer.echo(manual_actions.render_markdown(evaluated) if md else manual_actions.render_text(evaluated))


if __name__ == "__main__":
    app()
