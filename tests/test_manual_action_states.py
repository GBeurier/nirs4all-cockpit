"""Manual completions and observed publication failures must stay distinct."""
from pathlib import Path

from cockpit.manual_actions import ManualAction, evaluate, is_pending, load_actions, public_payload, render_text
from cockpit.model import PackageSource, PackageStatus, Snapshot, TargetStatus

ROOT = Path(__file__).resolve().parents[1]


def test_old_studio_completion_does_not_complete_a_separate_manual_review() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops/manual-actions.yaml")}
    old = actions["studio-windows-rc-smoke"]
    current = ManualAction(
        id="separate-manual-review", status="blocked", severity="blocker", title="Separate manual review",
    )
    evaluate(old, None)
    evaluate(current, None)

    assert old.status == "done" and old.auto_check is None and old.resolved is None
    assert not is_pending(old)
    assert is_pending(current)
    payload = public_payload([old, current], None)
    assert payload["counts"] == {
        "total": 2, "pending": 1, "resolved": 1, "blockers": 1, "important": 0, "info": 0,
    }
    assert "[x] (BLOCKER) studio-windows-rc-smoke" in render_text([old])
    assert "[ ] (BLOCKER) separate-manual-review" in render_text([current])


def test_studio_publication_hold_is_completed_and_checked_against_the_release() -> None:
    actions = {action.id: action for action in load_actions(ROOT / "ops/manual-actions.yaml")}
    action = actions["studio-final-manual-na-review"]
    assert action.status == "done"
    assert action.auto_check == {"registry": "github-release", "name": "nirs4all-studio", "expect": "green"}
    snapshot = Snapshot(
        generated_at="2026-10-30T11:56:16Z", generator={}, summary={},
        packages=[PackageStatus(
            id="nirs4all-studio", repo="nirs4all-studio", source=PackageSource(), rollup="green",
            targets=[TargetStatus(registry="github-release", name="nirs4all-studio", status="green",
                                  published_version="0.15.4")],
        )],
    )
    evaluate(action, snapshot)
    assert action.resolved is True and not is_pending(action)


def test_negative_publication_check_overrides_an_old_done_declaration() -> None:
    action = ManualAction(
        id="publisher", status="done", severity="blocker", title="Old publisher setup",
        auto_check={"registry": "pypi", "name": "example", "expect": "published"},
    )
    snapshot = Snapshot(
        generated_at="2026-10-29T23:00:00Z", generator={}, summary={},
        packages=[PackageStatus(id="example", repo="example", source=PackageSource(), rollup="missing",
                                targets=[TargetStatus(registry="pypi", name="example", status="missing")])],
    )
    evaluate(action, snapshot)
    assert action.resolved is False and is_pending(action)
    assert public_payload([action], snapshot)["counts"]["blockers"] == 1
    assert "[ ] (BLOCKER) publisher" in render_text([action])


def test_unknown_automatic_check_is_not_hidden_by_a_done_declaration() -> None:
    action = ManualAction(
        id="publisher", status="done", severity="blocker", title="Old publisher setup",
        auto_check={"registry": "pypi", "name": "example", "expect": "published"},
    )
    evaluate(action, None)
    assert action.resolved is None and is_pending(action)
    assert public_payload([action], None)["counts"]["pending"] == 1
