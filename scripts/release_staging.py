#!/usr/bin/env python3
"""Build or validate Cockpit's deterministic public R2 staging projection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cockpit.release_staging import StagingError, build_from_files, validate_projection, write_projection


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Build an R2 in-progress projection.")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--lock", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)

    validate = commands.add_parser("validate", help="Validate an existing projection against its inputs.")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--lock", type=Path, required=True)
    validate.add_argument("--projection", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "build":
            projection = build_from_files(args.manifest, args.lock)
            write_projection(projection, args.out)
            print(f"wrote deterministic {projection.phase} {projection.status} projection: {args.out}")
        else:
            validate_projection(args.manifest, args.lock, args.projection)
            print(f"valid deterministic R2 in_progress projection: {args.projection}")
    except StagingError as exc:
        print(f"release staging refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
