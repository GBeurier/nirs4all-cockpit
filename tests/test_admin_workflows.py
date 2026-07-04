from __future__ import annotations

import pytest

from cockpit import admin
from cockpit.model import WorkflowRef


def test_validate_inputs_rejects_missing_required_input() -> None:
    wf = WorkflowRef(
        file="release-unified.yml",
        trigger="workflow_dispatch",
        inputs=[{"name": "tag", "type": "string", "required": True}],
    )

    with pytest.raises(admin.AdminError, match="required input 'tag' is missing"):
        admin._validate_inputs(wf, {})


def test_validate_inputs_accepts_declared_required_input() -> None:
    wf = WorkflowRef(
        file="release-unified.yml",
        trigger="workflow_dispatch",
        inputs=[{"name": "tag", "type": "string", "required": True}],
    )

    assert admin._validate_inputs(wf, {"tag": "0.8.0"}) == {"tag": "0.8.0"}


def test_dry_run_publish_gate_uses_string_values_not_truthiness() -> None:
    wf = WorkflowRef(
        file="publish.yml",
        trigger="workflow_dispatch",
        publishes_on_dispatch=True,
        inputs=[{"name": "dry_run", "type": "string", "default": "true"}],
    )

    assert admin._safe_value("dry_run", publish=False) == "true"
    assert admin._safe_value("dry_run", publish=True) == "false"
    assert admin._will_publish(wf, {"dry_run": "true"}, publish=None, dry_run=True) is False
    assert admin._will_publish(wf, {"dry_run": "false"}, publish=True, dry_run=False) is True
