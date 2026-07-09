"""Manual release actions — the human-only steps the cockpit can only surface.

``ops/manual-actions.yaml`` is the structured migration of ``RELEASE_ACTIONS.md``:
account fixes, tokens, web forms, and trusted-publisher setups the cockpit cannot
perform. For each action this module:

* loads the declaration (id / status / severity / title / manual_url / affects /
  secret_updates / after_done / auto_check);
* if an ``auto_check`` is present, reads ``data/current.json`` and decides whether
  the action is *resolved* — the named target on the named registry is published
  at the expected level (``expect: published`` means a non-empty published
  version with status ``green`` or ``stale``; ``expect: green`` additionally
  requires the target to be current);
* renders a checklist as plain text or Markdown.

This module owns no state machine and no network: resolution is a pure read of
the already-reconciled snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cockpit.model import Snapshot

_RESOLVED_STATES = {"green", "stale"}
"""Statuses that count as 'published' for an ``expect: published`` auto-check.

``stale`` still means *something is on the registry*, so the manual blocker (a
missing trusted publisher, an unverified email) is cleared even if a newer
version has not propagated yet.
"""


@dataclass
class ManualAction:
    """One parsed manual action plus its computed resolution against a snapshot."""

    id: str
    status: str
    severity: str
    title: str
    manual_url: str | None = None
    affects: list[str] = field(default_factory=list)
    secret_updates: list[dict] = field(default_factory=list)
    after_done: list[dict] = field(default_factory=list)
    auto_check: dict | None = None
    # Computed: None when no auto_check, else True/False, plus a human note.
    resolved: bool | None = None
    check_note: str | None = None


def load_actions(path: str | Path) -> list[ManualAction]:
    """Parse ``ops/manual-actions.yaml`` into :class:`ManualAction` records.

    Args:
        path: Path to the manual-actions YAML file.

    Returns:
        The list of actions in declaration order (resolution not yet computed).
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    actions: list[ManualAction] = []
    for entry in raw.get("actions", []):
        actions.append(
            ManualAction(
                id=entry["id"],
                status=entry.get("status", "todo"),
                severity=entry.get("severity", "info"),
                title=entry.get("title", entry["id"]),
                manual_url=entry.get("manual_url"),
                affects=list(entry.get("affects", [])),
                secret_updates=list(entry.get("secret_updates", [])),
                after_done=list(entry.get("after_done", [])),
                auto_check=entry.get("auto_check"),
            )
        )
    return actions


def _find_published(snapshot: Snapshot, registry: str, name: str) -> tuple[str | None, str | None]:
    """Return ``(status, published_version)`` for a target, or ``(None, None)``.

    Looks across every package's targets for an exact ``(registry, name)`` match.
    """
    for pkg in snapshot.packages:
        for target in pkg.targets:
            if target.registry == registry and target.name == name:
                return target.status, target.published_version
    return None, None


def evaluate(action: ManualAction, snapshot: Snapshot | None) -> None:
    """Compute ``action.resolved`` / ``action.check_note`` in place.

    With no ``auto_check`` or no snapshot, resolution stays ``None`` (unknown).
    For ``expect: published`` the action is resolved when the named target is on
    its registry at a ``green``/``stale`` status with a non-empty version.
    For ``expect: green`` the target must be current, not stale.

    Args:
        action: The action to annotate.
        snapshot: The reconciled snapshot, or ``None`` if unavailable.
    """
    check = action.auto_check
    if not check:
        action.resolved = None
        action.check_note = None
        return
    if snapshot is None:
        action.resolved = None
        action.check_note = "no snapshot available (run `collect` first)"
        return

    registry = check.get("registry")
    name = check.get("name")
    expect = check.get("expect", "published")
    status, published = _find_published(snapshot, registry, name)

    if status is None:
        action.resolved = False
        action.check_note = f"{registry}:{name} not found in snapshot"
        return

    if expect == "published":
        ok = status in _RESOLVED_STATES and bool(published)
        action.resolved = ok
        if ok:
            action.check_note = f"{registry}:{name} published {published} (status={status})"
        else:
            action.check_note = f"{registry}:{name} status={status} version={published or '—'}"
        return

    if expect == "green":
        ok = status == "green" and bool(published)
        action.resolved = ok
        if ok:
            action.check_note = f"{registry}:{name} current {published} (status=green)"
        else:
            action.check_note = f"{registry}:{name} status={status} version={published or '—'}"
        return

    # Unknown expectation kinds stay unresolved but are reported, not crashed.
    action.resolved = None
    action.check_note = f"unsupported auto_check.expect={expect!r}"


def evaluate_all(actions: list[ManualAction], snapshot: Snapshot | None) -> list[ManualAction]:
    """Annotate every action with its resolution and return the same list."""
    for action in actions:
        evaluate(action, snapshot)
    return actions


def _mark(action: ManualAction) -> str:
    """Checkbox glyph for an action: done/resolved → ``x``, else open."""
    if action.status == "done" or action.resolved is True:
        return "x"
    return " "


def render_text(actions: list[ManualAction]) -> str:
    """Render the actions as a plain-text checklist."""
    lines: list[str] = ["Manual release actions:"]
    for action in actions:
        box = _mark(action)
        sev = action.severity.upper()
        lines.append(f"[{box}] ({sev}) {action.id}: {action.title}")
        if action.manual_url:
            lines.append(f"      url: {action.manual_url}")
        if action.affects:
            lines.append(f"      unblocks: {', '.join(action.affects)}")
        if action.secret_updates:
            secrets = ", ".join(f"{s['repo']}:{s['name']}" for s in action.secret_updates)
            lines.append(f"      secrets: {secrets}")
        if action.resolved is not None:
            verdict = "RESOLVED" if action.resolved else "PENDING"
            note = f" — {action.check_note}" if action.check_note else ""
            lines.append(f"      auto-check: {verdict}{note}")
        elif action.check_note:
            lines.append(f"      auto-check: UNKNOWN — {action.check_note}")
    return "\n".join(lines)


def render_markdown(actions: list[ManualAction]) -> str:
    """Render the actions as a Markdown checklist."""
    lines: list[str] = ["# Manual release actions", ""]
    for action in actions:
        box = _mark(action)
        title = f"[{action.title}]({action.manual_url})" if action.manual_url else action.title
        lines.append(f"- [{box}] **{action.id}** ({action.severity}) — {title}")
        if action.affects:
            lines.append(f"  - unblocks: {', '.join(f'`{a}`' for a in action.affects)}")
        if action.secret_updates:
            secrets = ", ".join(f"`{s['repo']}:{s['name']}`" for s in action.secret_updates)
            lines.append(f"  - secrets: {secrets}")
        if action.resolved is not None:
            verdict = "✅ resolved" if action.resolved else "⬜ pending"
            note = f" — {action.check_note}" if action.check_note else ""
            lines.append(f"  - auto-check: {verdict}{note}")
        elif action.check_note:
            lines.append(f"  - auto-check: ❔ unknown — {action.check_note}")
    return "\n".join(lines)


def public_payload(actions: list[ManualAction], snapshot: Snapshot | None) -> dict[str, Any]:
    """Return the public, non-secret manual-action payload for the dashboard."""
    pending = [action for action in actions if action.resolved is not True]
    resolved = [action for action in actions if action.resolved is True]
    counts = {
        "total": len(actions),
        "pending": len(pending),
        "resolved": len(resolved),
        "blockers": sum(1 for action in pending if action.severity == "blocker"),
        "important": sum(1 for action in pending if action.severity == "important"),
        "info": sum(1 for action in pending if action.severity == "info"),
    }
    return {
        "schema_version": 1,
        "snapshot_generated_at": snapshot.generated_at if snapshot is not None else None,
        "counts": counts,
        "actions": [
            {
                "id": action.id,
                "status": "done" if action.resolved is True else action.status,
                "declared_status": action.status,
                "severity": action.severity,
                "title": action.title,
                "manual_url": action.manual_url,
                "affects": action.affects,
                "after_done": action.after_done,
                "auto_check": action.auto_check,
                "resolved": action.resolved,
                "check_note": action.check_note,
            }
            for action in actions
        ],
    }


def checklist(
    actions_path: str | Path,
    snapshot: Snapshot | None,
    *,
    markdown: bool = False,
) -> str:
    """Load, evaluate against ``snapshot``, and render the manual-action checklist.

    Args:
        actions_path: Path to ``ops/manual-actions.yaml``.
        snapshot: Reconciled snapshot used for auto-checks (``None`` to skip).
        markdown: When ``True`` render Markdown, else plain text.

    Returns:
        The rendered checklist string.
    """
    actions = evaluate_all(load_actions(actions_path), snapshot)
    return render_markdown(actions) if markdown else render_text(actions)
