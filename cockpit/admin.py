"""Admin layer for nirs4all-cockpit — thin, guarded wrappers around the ``gh`` CLI.

The cockpit never publishes directly and never touches a registry token: it only
*orchestrates* GitHub via ``gh``. This module builds the exact ``gh`` command,
prints it for the operator to see, and runs it only behind the appropriate
guard rails:

* every operation refuses to run if ``gh auth status`` fails;
* ``--dry-run`` is the default for releases; a ``danger`` of ``publish`` /
  ``dangerous`` forces an explicit confirmation and prints the exact command
  *before* execution;
* an input not declared in the target's :class:`~cockpit.model.WorkflowRef` is
  refused (the inventory is the single source of truth for accepted inputs);
* a ``planned`` target (no workflow) yields a "pas de bouton de release" message;
* a ``trigger: tag`` workflow is *never* tag-pushed by the cockpit — the exact
  ``git tag`` / ``git push`` commands are printed for the operator to run by hand;
* ``set-secret`` only ever shells ``gh secret set NAME -R … < file``: it reads
  the secret from a file, never from a flag, never echoes it, never logs it.

Nothing here decides *state*; reconciliation and version logic live elsewhere.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from cockpit.model import Package, Target, WorkflowRef

OWNER = "GBeurier"
"""GitHub owner all ecosystem repos live under (``GBeurier/<repo>``)."""


class AdminError(RuntimeError):
    """Raised when an admin operation is refused by a guard rail."""


@dataclass
class AdminResult:
    """Outcome of an admin operation.

    ``command`` is the exact shell command (already quoted) that was previewed;
    ``executed`` says whether it was actually run; ``returncode`` is the process
    exit code when executed; ``messages`` carries human-facing guidance (manual
    ``git tag`` steps, confirmation prompts that were skipped, etc.).
    """

    command: str | None
    executed: bool
    returncode: int | None = None
    messages: list[str] = field(default_factory=list)


def _qualified_repo(repo: str) -> str:
    """Return the ``GBeurier/<repo>`` slug, accepting an already-qualified slug."""
    repo = repo.strip()
    if "/" in repo:
        return repo
    return f"{OWNER}/{repo}"


def gh_auth_ok() -> bool:
    """Return ``True`` if ``gh auth status`` reports an authenticated session.

    The check is read-only and never prints token material. Any failure to spawn
    ``gh`` (missing binary, non-zero exit) is treated as "not authenticated".
    """
    try:
        proc = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return proc.returncode == 0


def _require_auth() -> None:
    """Refuse to proceed unless ``gh`` is authenticated."""
    if not gh_auth_ok():
        raise AdminError(
            "gh is not authenticated (gh auth status failed). "
            "Run `gh auth login` before using admin commands."
        )


def find_target(package: Package, registry: str, name: str | None = None) -> Target:
    """Locate a single target in ``package`` by ``registry`` (and optional exact ``name``).

    Args:
        package: The package whose targets to search.
        registry: Registry key (``pypi``/``crates``/``npm``/``r-universe``/…).
        name: Exact registry name; required to disambiguate when a registry has
            several targets (e.g. multiple crates).

    Raises:
        AdminError: If no target matches, or the match is ambiguous and ``name``
            was not given.
    """
    matches = [t for t in package.targets if t.registry == registry and (name is None or t.name == name)]
    if not matches:
        hint = f"{registry}:{name}" if name else registry
        raise AdminError(f"no target {hint!r} in package {package.id!r}")
    if len(matches) > 1:
        names = ", ".join(t.name for t in matches)
        raise AdminError(
            f"ambiguous registry {registry!r} in package {package.id!r}: "
            f"pass an exact name (one of: {names})"
        )
    return matches[0]


def _coerce_input_value(value: object) -> str:
    """Render an input value as the string ``gh -f name=value`` expects."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _validate_inputs(wf: WorkflowRef, inputs: dict) -> dict[str, str]:
    """Validate ``inputs`` against the declared workflow inputs and coerce to strings.

    Only names declared in ``wf.inputs`` are accepted; an undeclared key is a hard
    error. ``choice`` inputs are checked against their declared ``options``.

    Raises:
        AdminError: On any undeclared input name or out-of-set choice value.
    """
    declared = {spec["name"]: spec for spec in wf.inputs if "name" in spec}
    out: dict[str, str] = {}
    for key, value in inputs.items():
        if key not in declared:
            allowed = ", ".join(declared) or "(none)"
            raise AdminError(
                f"input {key!r} is not declared for workflow {wf.file!r} "
                f"(declared inputs: {allowed})"
            )
        spec = declared[key]
        coerced = _coerce_input_value(value)
        if spec.get("type") == "choice":
            options = [str(o) for o in spec.get("options", [])]
            if options and coerced not in options:
                raise AdminError(
                    f"input {key!r}={coerced!r} is not a valid choice for "
                    f"workflow {wf.file!r} (options: {', '.join(options)})"
                )
        out[key] = coerced
    return out


def build_run_command(repo: str, workflow_file: str, ref: str, inputs: dict[str, str]) -> list[str]:
    """Build the exact ``gh workflow run`` argv (no execution).

    Args:
        repo: Repo name or ``owner/repo`` slug.
        workflow_file: Workflow filename (e.g. ``release-npm.yml``).
        ref: Git ref the dispatch targets (branch or tag).
        inputs: Already-validated, string-valued dispatch inputs.

    Returns:
        The argv list, ready for :func:`subprocess.run` or :func:`shlex.join`.
    """
    argv = ["gh", "workflow", "run", workflow_file, "-R", _qualified_repo(repo), "--ref", ref]
    for key, value in inputs.items():
        argv += ["-f", f"{key}={value}"]
    return argv


def _tag_instructions(repo: str, ref: str) -> list[str]:
    """Human steps to cut a production tag by hand (the cockpit never tags)."""
    slug = _qualified_repo(repo)
    tag = ref if ref.startswith("v") else "vX.Y.Z"
    return [
        "This workflow is triggered by a tag — the cockpit does NOT create or push tags.",
        "Run these by hand once you have decided the version:",
        f"    git -C {repo} tag {tag}",
        f"    git -C {repo} push origin {tag}",
        f"(GitHub: pushing the tag to {slug} starts the release workflow.)",
    ]


def run_workflow(
    package: Package,
    registry: str,
    *,
    name: str | None = None,
    ref: str = "main",
    inputs: dict | None = None,
    dry_run: bool = True,
    publish: bool | None = None,
    confirm: bool = False,
    execute: bool = True,
) -> AdminResult:
    """Preview and (optionally) trigger a release workflow for one target.

    The function is the single choke point for releases. It:

    1. refuses unless ``gh`` is authenticated;
    2. refuses a ``planned`` target (no workflow) with a clear message;
    3. for a ``trigger: tag`` workflow, prints the manual ``git tag`` steps and
       never dispatches;
    4. validates ``inputs`` against the workflow's declared inputs;
    5. injects the publish gate (``--publish`` → the workflow's publish input)
       only when the inventory says the dispatch can publish;
    6. builds and prints the exact ``gh workflow run`` command, and executes it
       only when it is not a publish/dangerous op *or* ``confirm`` is set.

    Args:
        package: The package the target belongs to.
        registry: Registry key of the target.
        name: Exact registry name (to disambiguate multi-target registries).
        ref: Dispatch ref (branch or tag); default ``main``.
        inputs: Extra dispatch inputs (validated against the declaration).
        dry_run: When ``True`` (default), the publish input is forced off / the
            ``dry_run`` input forced on; the command is previewed, not run.
        publish: Tri-state publish intent for ``workflow_dispatch`` publishers.
            ``True`` flips the publish input on (requires ``confirm`` for a
            ``publish``/``dangerous`` workflow); ``None`` leaves it at default.
        confirm: Explicit confirmation required to actually publish.
        execute: When ``False``, only build/preview (used by the CLI dry-run path
            and by tests).

    Returns:
        An :class:`AdminResult` with the previewed command and execution outcome.
    """
    _require_auth()
    inputs = dict(inputs or {})
    messages: list[str] = []

    target = find_target(package, registry, name)

    # 2. planned / no workflow → no button.
    if target.workflow is None:
        if target.state == "planned":
            messages.append(
                f"{package.id}:{target.registry}:{target.name} is PLANNED — "
                "pas de bouton de release (no release workflow exists yet)."
            )
        else:
            messages.append(
                f"{package.id}:{target.registry}:{target.name} has no workflow — "
                "pas de bouton de release (manual/excluded target)."
            )
        return AdminResult(command=None, executed=False, messages=messages)

    wf = target.workflow

    # 3. tag-triggered → never dispatch; print manual git tag steps.
    if wf.trigger == "tag" and not wf.publishes_on_dispatch:
        messages += _tag_instructions(package.repo, ref)
        return AdminResult(command=None, executed=False, messages=messages)

    # Resolve the publish/dry-run gate into a concrete input value.
    publish_input = _publish_input_name(wf)
    if publish_input is not None:
        if dry_run:
            # dry-run forces the publish gate off (publish=false / dry_run=true).
            inputs.setdefault(publish_input, _safe_value(publish_input, publish=False))
        elif publish:
            inputs.setdefault(publish_input, _safe_value(publish_input, publish=True))

    declared_inputs = _validate_inputs(wf, inputs)

    will_publish = _will_publish(wf, declared_inputs, publish=publish, dry_run=dry_run)

    argv = build_run_command(package.repo, wf.file, ref, declared_inputs)
    command = shlex.join(argv)

    danger = wf.danger
    messages.append(f"Workflow: {wf.file} (trigger={wf.trigger}, danger={danger})")
    messages.append(f"Command: {command}")

    needs_confirm = will_publish or danger in ("publish", "dangerous")

    # Pure preview (CLI --dry-run, tests): print the exact command, never run it.
    if not execute:
        if needs_confirm:
            messages.append(
                "Preview only (not executed). This is a publish-capable workflow: "
                "re-run with --no-dry-run --publish and confirm to execute."
            )
        else:
            messages.append("Preview only (not executed).")
        return AdminResult(command=command, executed=False, messages=messages)

    # 6. publish / dangerous → require explicit confirmation before running.
    if needs_confirm and not confirm:
        messages.append(
            "REFUSED: this dispatch can publish and was not confirmed. "
            "Re-run with --no-dry-run --publish and confirm the prompt to execute."
        )
        return AdminResult(command=command, executed=False, messages=messages)

    if danger == "dangerous" and will_publish:
        messages.append("DANGEROUS DISPATCH: this dispatch publishes outright.")

    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.stdout.strip():
        messages.append(proc.stdout.strip())
    if proc.returncode != 0 and proc.stderr.strip():
        messages.append(proc.stderr.strip())
    return AdminResult(command=command, executed=True, returncode=proc.returncode, messages=messages)


def _publish_input_name(wf: WorkflowRef) -> str | None:
    """Return the name of the input that gates publishing, if the workflow has one.

    Two conventions are in use in the inventory: a boolean ``publish`` input, and
    a string ``dry_run`` input. Either acts as the publish gate.
    """
    names = {spec.get("name") for spec in wf.inputs}
    if "publish" in names:
        return "publish"
    if "dry_run" in names:
        return "dry_run"
    return None


def _safe_value(input_name: str, *, publish: bool) -> str:
    """Map publish intent onto the gate input's string value.

    For a ``publish`` input the value mirrors intent (``true``/``false``); for a
    ``dry_run`` input it is inverted (publishing means ``dry_run=false``).
    """
    if input_name == "dry_run":
        return "false" if publish else "true"
    return "true" if publish else "false"


def _will_publish(
    wf: WorkflowRef,
    declared_inputs: dict[str, str],
    *,
    publish: bool | None,
    dry_run: bool,
) -> bool:
    """Decide whether the resolved dispatch will actually publish.

    A dispatch publishes when the workflow can publish on dispatch *and* the gate
    input resolves to "publish on" (``publish=true`` or ``dry_run=false``).
    """
    if not wf.publishes_on_dispatch:
        return False
    gate = _publish_input_name(wf)
    if gate is None:
        # publishes_on_dispatch with no gate input → dispatch publishes outright.
        return not dry_run if publish is None else bool(publish)
    value = declared_inputs.get(gate, _safe_value(gate, publish=bool(publish) and not dry_run))
    if gate == "dry_run":
        return value == "false"
    return value == "true"


def set_secret(repo: str, name: str, from_file: Path) -> AdminResult:
    """Set a GitHub Actions secret from a file via ``gh secret set`` (never echoed).

    The command shape is fixed: ``gh secret set NAME -R GBeurier/<repo>`` reading
    the value from ``from_file`` on stdin. The secret value is never read into
    Python, never logged, never passed as a flag, never stored under ``data/``.

    Args:
        repo: Repo name or ``owner/repo`` slug.
        name: Secret name (e.g. ``NPM_TOKEN``).
        from_file: Path to the file holding the secret value.

    Raises:
        AdminError: If ``gh`` is unauthenticated or the file is missing.

    Returns:
        An :class:`AdminResult`; ``command`` shows the safe command (the file path,
        never its contents).
    """
    _require_auth()
    from_file = Path(from_file)
    if not from_file.is_file():
        raise AdminError(f"secret source file not found: {from_file}")

    slug = _qualified_repo(repo)
    argv = ["gh", "secret", "set", name, "-R", slug]
    # Show what runs without ever revealing the value.
    command = f"{shlex.join(argv)} < {shlex.quote(str(from_file))}"
    messages = [
        f"Setting secret {name} on {slug} from {from_file} (value never displayed).",
        f"Command: {command}",
    ]

    with from_file.open("rb") as fh:
        proc = subprocess.run(argv, stdin=fh, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        messages.append(f"Secret {name} set on {slug}.")
    else:
        # gh prints diagnostics to stderr; the secret is not in it.
        if proc.stderr.strip():
            messages.append(proc.stderr.strip())
    return AdminResult(command=command, executed=True, returncode=proc.returncode, messages=messages)
