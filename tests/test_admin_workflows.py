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
