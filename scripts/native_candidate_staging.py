#!/usr/bin/env python3
"""Build or validate the shared Org/Cockpit native candidate snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(CHECKOUT_ROOT))

from cockpit.native_candidate import (  # noqa: E402
    CandidateError,
    build_projection,
    render,
    validate_projection,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--governance-repo", type=Path, required=True)
    build.add_argument("--governance-commit", required=True)
    build.add_argument("--workspace-root", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--projection", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            projection = build_projection(args.governance_repo, args.governance_commit, args.workspace_root)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(render(projection), encoding="utf-8", newline="\n")
            print(f"wrote unpublished NO-GO candidate projection: {args.out}")
        else:
            raw = json.loads(args.projection.read_text(encoding="utf-8"))
            validate_projection(raw)
            if args.projection.read_text(encoding="utf-8") != render(raw):
                raise CandidateError("candidate projection is not canonical")
            print(f"valid unpublished NO-GO candidate projection: {args.projection}")
    except (CandidateError, OSError, json.JSONDecodeError) as exc:
        print(f"candidate staging refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
