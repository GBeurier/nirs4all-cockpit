#!/usr/bin/env python3
"""Smoke-test the static dashboard with a real headless browser.

The cockpit dashboard is intentionally zero-build vanilla HTML/CSS/JS. This
script serves the repository root, opens ``web/index.html`` in Chrome, lets
``app.js`` fetch ``data/current.json`` and ``data/manual-actions.json``, then
asserts that key rendered sections appear in the final DOM.
"""

from __future__ import annotations

import argparse
import http.server
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler without noisy access logs."""

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _find_chrome(explicit: str | None) -> str:
    candidates = [
        explicit,
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return candidate
    raise RuntimeError(
        "Chrome/Chromium not found. Install a browser or pass --chrome /path/to/chrome."
    )


def _dump_dom(chrome: str, url: str) -> str:
    proc = subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--virtual-time-budget=5000",
            "--dump-dom",
            url,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chrome", help="Chrome/Chromium executable to use")
    args = parser.parse_args()

    chrome = _find_chrome(args.chrome)
    with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as server:
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        dom = _dump_dom(chrome, f"http://127.0.0.1:{port}/web/index.html")

    required = [
        "nirs4all<b>·</b>cockpit",
        "Manual blockers",
        "runiverse-dagml-data-rebuild",
        "nirs4all-formats",
        "nirs4all-ecosystem",
        "schema v1",
        "Release matrix",
        "Downloads",
        "Code &amp; Actions",
    ]
    missing = [fragment for fragment in required if fragment not in dom]
    if missing:
        print("dashboard smoke failed; missing rendered fragments:", file=sys.stderr)
        for fragment in missing:
            print(f"  - {fragment}", file=sys.stderr)
        return 1

    print(f"dashboard smoke OK via {Path(chrome).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
