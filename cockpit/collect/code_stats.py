"""Local source-code statistics: effective LOC, tests, coverage, languages.

GitHub exposes no true line count, so this is computed from the **local sibling
checkout** (``SIBLINGS_ROOT/<repo>``). When the checkout is absent (e.g. the
public CI cron has no siblings) the scan returns ``None`` and the field is simply
omitted from the snapshot.

* *Effective LOC* = ``loc_code`` = source lines that are neither blank nor a
  comment. Comments and blanks are tallied separately (line-comment tokens plus
  C-style ``/* */`` blocks and Python triple-quoted blocks — a heuristic, not a
  full parser).
* *Tests* are counted by language heuristic (``def test_*``, ``#[test]``,
  ``it(``/``test(``).
* *Coverage* is read from a Cobertura ``coverage.xml`` at the repo root when
  present, else ``None``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from .local_manifests import SIBLINGS_ROOT

# ext -> (language, line-comment prefixes, has C-style /* */ block, is Python)
_LANG: dict[str, tuple[str, tuple[str, ...], bool, bool]] = {
    ".py": ("Python", ("#",), False, True),
    ".pyi": ("Python", ("#",), False, True),
    ".rs": ("Rust", ("//",), True, False),
    ".ts": ("TypeScript", ("//",), True, False),
    ".tsx": ("TypeScript", ("//",), True, False),
    ".js": ("JavaScript", ("//",), True, False),
    ".jsx": ("JavaScript", ("//",), True, False),
    ".mjs": ("JavaScript", ("//",), True, False),
    ".c": ("C", ("//",), True, False),
    ".h": ("C/C++ header", ("//",), True, False),
    ".hpp": ("C++ header", ("//",), True, False),
    ".hh": ("C++ header", ("//",), True, False),
    ".cpp": ("C++", ("//",), True, False),
    ".cc": ("C++", ("//",), True, False),
    ".cxx": ("C++", ("//",), True, False),
    ".R": ("R", ("#",), False, False),
    ".r": ("R", ("#",), False, False),
    ".jl": ("Julia", ("#",), False, False),
    ".java": ("Java", ("//",), True, False),
    ".kt": ("Kotlin", ("//",), True, False),
    ".go": ("Go", ("//",), True, False),
    ".sh": ("Shell", ("#",), False, False),
    ".m": ("MATLAB/Octave", ("%", "#"), False, False),
}

_SKIP_DIRS = {
    "node_modules", "target", "dist", "build", ".venv", "venv", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", "site-packages", "vendor",
    "release", "coverage", ".tox", "_site", "pkg", ".cargo", ".next", "third_party",
}

_TEST_RE: dict[str, re.Pattern[str]] = {
    "Python": re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+test_\w*[ \t]*\(", re.MULTILINE),
    "Rust": re.compile(r"#\[(?:tokio::)?(?:test|rstest)\b"),
}
_JS_TEST_RE = re.compile(r"\b(?:it|test)\s*\(")


def scan(repo: str) -> dict | None:
    """Scan ``SIBLINGS_ROOT/<repo>`` for code stats, or ``None`` if absent."""
    root = SIBLINGS_ROOT / repo
    if not root.is_dir():
        return None

    loc_code = loc_comment = loc_blank = files = tests = 0
    by_language: dict[str, int] = {}

    for path in _iter_source_files(root):
        lang = _LANG.get(path.suffix)
        if lang is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files += 1
        code, comment, blank = _count_lines(text, lang)
        loc_code += code
        loc_comment += comment
        loc_blank += blank
        tests += _count_tests(lang[0], text)
        by_language[lang[0]] = by_language.get(lang[0], 0) + code

    return {
        "loc_code": loc_code,
        "loc_comment": loc_comment,
        "loc_blank": loc_blank,
        "loc_total": loc_code + loc_comment + loc_blank,
        "files": files,
        "tests": tests,
        "by_language": dict(sorted(by_language.items(), key=lambda kv: -kv[1])),
        "coverage_pct": _coverage(root),
        "source": "local-scan",
    }


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Yield files under ``root``, skipping hidden and vendored directories."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                    continue
                stack.append(entry)
            elif entry.is_file():
                yield entry


def _count_lines(text: str, lang: tuple[str, tuple[str, ...], bool, bool]) -> tuple[int, int, int]:
    """Return ``(code, comment, blank)`` line counts for one file (heuristic)."""
    _name, prefixes, has_block, is_python = lang
    code = comment = blank = 0
    in_block = False
    in_pydoc = False
    pydoc_delim = ""

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            blank += 1
            continue
        if in_block:
            comment += 1
            if "*/" in s:
                in_block = False
            continue
        if in_pydoc:
            comment += 1
            if pydoc_delim in s:
                in_pydoc = False
            continue
        if any(s.startswith(p) for p in prefixes):
            comment += 1
            continue
        if has_block and s.startswith("/*"):
            comment += 1
            if "*/" not in s:
                in_block = True
            continue
        if is_python and (s.startswith('"""') or s.startswith("'''")):
            delim = s[:3]
            comment += 1
            if delim not in s[3:]:
                in_pydoc = True
                pydoc_delim = delim
            continue
        code += 1
    return code, comment, blank


def _count_tests(language: str, text: str) -> int:
    """Best-effort test-function count for a file, by language."""
    pat = _TEST_RE.get(language)
    if pat is not None:
        return len(pat.findall(text))
    if language in ("TypeScript", "JavaScript"):
        return len(_JS_TEST_RE.findall(text))
    return 0


def _coverage(root: Path) -> float | None:
    """Parse a Cobertura ``coverage.xml`` line-rate into a percentage, if present."""
    cov = root / "coverage.xml"
    if not cov.is_file():
        return None
    try:
        node = ET.parse(cov).getroot()
    except (ET.ParseError, OSError):
        return None
    rate = node.get("line-rate")
    if rate is not None:
        try:
            return round(float(rate) * 100, 1)
        except ValueError:
            return None
    covered, valid = node.get("lines-covered"), node.get("lines-valid")
    if covered and valid:
        try:
            total = float(valid)
            return round(float(covered) / total * 100, 1) if total > 0 else None
        except ValueError:
            return None
    return None
