"""Persist a reconciled snapshot to ``data/current.json`` and the history log.

The day key for the history file comes from the snapshot's ``generated_at`` (or
an explicit override) — never from a fresh ``datetime.now()`` here — so the
written current state and its archived copy always agree on the date.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import Snapshot


def write_snapshot(snap: Snapshot, out_path: str | Path) -> Path:
    """Write ``snap`` to ``out_path`` (typically ``data/current.json``).

    The parent directory is created if needed. Returns the path written.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_dump(snap), encoding="utf-8")
    return out


def append_history(snap: Snapshot, history_dir: str | Path, generated_at: str) -> Path:
    """Write ``snap`` to ``<history_dir>/YYYY-MM-DD.json`` keyed by ``generated_at``.

    Args:
        snap: The snapshot to archive.
        history_dir: Directory for dated archives (typically ``data/history``).
        generated_at: The ISO timestamp whose date prefix names the file; pass
            ``snap.generated_at`` to keep current and history in lockstep.

    Returns:
        The history file path written (overwritten if the same day re-runs).
    """
    day = generated_at[:10]  # YYYY-MM-DD prefix of the ISO timestamp
    hdir = Path(history_dir)
    hdir.mkdir(parents=True, exist_ok=True)
    path = hdir / f"{day}.json"
    path.write_text(_dump(snap), encoding="utf-8")
    return path


def _dump(snap: Snapshot) -> str:
    public_exclude = {
        "packages": {
            "__all__": {
                "channel": True,
                "targets": {"__all__": {"channel": True}},
            }
        }
    }
    return json.dumps(snap.model_dump(mode="json", exclude=public_exclude), indent=2, ensure_ascii=False) + "\n"
