# Repository Guidelines

## Project Structure & Module Organization

This repository is a read-only release and health cockpit for the nirs4all ecosystem. Python source lives in `cockpit/`; the Typer entry point is `cockpit.cli:app`, exposed as `n4a-cockpit`. Registry and service collectors are under `cockpit/collect/`. The zero-build dashboard lives in `web/` and reads `data/current.json`. Operational inventory and manual actions live in `ops/`. Tests are in `tests/`, with API fixtures in `tests/fixtures/`.

## Build, Test, and Development Commands

- `python -m venv .venv && . .venv/bin/activate`: create a local environment.
- `pip install -e .[dev]`: install the package, pytest, and Ruff.
- `n4a-cockpit validate-targets ops/targets.yaml`: validate package inventory.
- `n4a-cockpit collect --offline`: build a snapshot using fixtures/cache only.
- `n4a-cockpit status`: show the current snapshot as a terminal table.
- `python -m http.server 8000`: serve the repo root, then open `http://localhost:8000/web/index.html`.
- `pytest -q`: run the offline test suite.
- `ruff check .`: run configured lint checks.

## Coding Style & Naming Conventions

Use Python 3.11 features where they simplify code. Follow Ruff settings in `pyproject.toml`: 120-character lines, `py311` target, and rules `E`, `F`, `I`, `UP`, and `B`. Use 4-space indentation, snake_case for modules/functions, PascalCase for classes and Pydantic models, and registry-specific module names such as `pypi.py` or `github_security.py`. Keep the frontend dependency-free vanilla HTML/CSS/JS.

## Testing Guidelines

Tests must remain offline. Collectors should reach external services through `cockpit.http.get_json` so tests can monkeypatch fixture responses. Name files `tests/test_<area>.py` and functions `test_<behavior>`. Add fixtures for registry edge cases such as HTTP-200 error payloads, 404s, null versions, and zero-download responses.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commits, often with scopes: `feat(targets): ...`, `fix(pages): ...`, `chore(collect): refresh data/current.json`. Keep commits focused and describe the behavior or data change. Pull requests should include a concise summary, linked issue when available, test results, and screenshots for dashboard UI changes.

## Security & Configuration Tips

Do not commit tokens or local admin snapshots. Public data belongs in `data/current.json`; push-scoped or semi-private signals belong only in gitignored `data/admin/snapshot.admin.json`. Prefer `GITHUB_TOKEN`, `GOATCOUNTER_TOKEN`, and `SENTRY_AUTH_TOKEN`; never print or store their values.

## Agent-Specific Instructions

The cockpit aggregates public registry, CI, issue, and stats signals; it should not reimplement package release logic from sibling repositories. Keep changes scoped and preserve the distinction between public and admin-only data.
