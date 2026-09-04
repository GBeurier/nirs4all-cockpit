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
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class StaticPageParser(HTMLParser):
    """Collect the small static contract needed before the browser smoke."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.links: list[str] = []
        self.json_ld: list[list[str]] = []
        self._active_json_ld: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        self.tags.append((tag, values))
        if tag == "html":
            self.lang = values.get("lang")
        for key in ("href", "src"):
            if values.get(key):
                self.links.append(values[key])
        if tag == "script" and values.get("type") == "application/ld+json":
            self._active_json_ld = []
            self.json_ld.append(self._active_json_ld)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._active_json_ld is not None:
            self._active_json_ld = None

    def handle_data(self, data: str) -> None:
        if self._active_json_ld is not None:
            self._active_json_ld.append(data)


def _validate_static_site() -> None:
    page = ROOT / "web" / "index.html"
    parser = StaticPageParser()
    parser.feed(page.read_text(encoding="utf-8"))
    parser.close()
    if parser.lang != "en":
        raise RuntimeError("dashboard html[lang] must be en")
    if sum(tag == "h1" for tag, _ in parser.tags) != 1 or sum(tag == "main" for tag, _ in parser.tags) != 1:
        raise RuntimeError("dashboard requires exactly one h1 and one main")
    descriptions = [
        attrs.get("content") for tag, attrs in parser.tags if tag == "meta" and attrs.get("name") == "description"
    ]
    canonicals = [attrs.get("href") for tag, attrs in parser.tags if tag == "link" and attrs.get("rel") == "canonical"]
    if len(descriptions) != 1 or not descriptions[0] or canonicals != ["https://cockpit.nirs4all.org/"]:
        raise RuntimeError("dashboard SEO description/canonical contract failed")
    if not parser.json_ld:
        raise RuntimeError("dashboard JSON-LD is missing")
    for payload in parser.json_ld:
        value = json.loads("".join(payload))
        if value.get("@context") != "https://schema.org":
            raise RuntimeError("dashboard JSON-LD must use schema.org")
    for raw_url in parser.links:
        parsed = urlsplit(raw_url)
        if parsed.scheme or parsed.netloc or raw_url.startswith("#") or raw_url.startswith("//"):
            continue
        relative = parsed.path.removeprefix("./")
        if not relative:
            continue
        if not (ROOT / "web" / relative).is_file():
            raise RuntimeError(f"missing dashboard asset: {raw_url}")
    sitemap = ET.parse(ROOT / "web" / "sitemap.xml")
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = {node.text for node in sitemap.findall(".//sm:loc", namespace)}
    if "https://cockpit.nirs4all.org/" not in urls:
        raise RuntimeError("dashboard sitemap omits canonical URL")


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
    raise RuntimeError("Chrome/Chromium not found. Install a browser or pass --chrome /path/to/chrome.")


def _timeout_seconds(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get("COCKPIT_DASHBOARD_SMOKE_TIMEOUT", "90")
    try:
        return max(10, int(raw))
    except ValueError:
        return 90


def _dump_dom(chrome: str, url: str, *, timeout: int) -> str:
    proc = subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",
            "--dump-dom",
            url,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chrome", help="Chrome/Chromium executable to use")
    parser.add_argument(
        "--timeout",
        type=int,
        help="Seconds to wait for headless Chrome before failing; defaults to COCKPIT_DASHBOARD_SMOKE_TIMEOUT or 90.",
    )
    args = parser.parse_args()

    _validate_static_site()

    chrome = _find_chrome(args.chrome)
    timeout = _timeout_seconds(args.timeout)
    with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as server:
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        dom = _dump_dom(chrome, f"http://127.0.0.1:{port}/web/index.html", timeout=timeout)

    manual_actions = json.loads((ROOT / "data" / "manual-actions.json").read_text(encoding="utf-8"))
    unresolved_action_ids = [action["id"] for action in manual_actions.get("actions", []) if not action.get("resolved")]

    required = [
        "nirs4all<b>·</b>cockpit",
        "Manual blockers",
        "nirs4all-formats",
        "nirs4all-ecosystem",
        "schema v1",
        "Release matrix",
        "Native R1/R2/R3 candidates",
        "Candidat produit strictement NO-GO",
        "SNV → Savitzky–Golay → PLS",
        "nirs4all-tools 0.0.7",
        "CUT-002 observability",
        "process-local and intentionally non-persistent",
        (
            "Closed locally, release held: API-001, API-004, API-005, CAP-001, DAG-001, DOC-001, "
            "GATE-001, REL-003, STU-006, UI-001, WEB-001, WEBREL-001"
        ),
        "Prepared but not closed: INST-001, RC-001",
        "Advanced but not closed: PERF-002, SOAK-001",
        "ROB-001: functional invalid-input and non-crash checks await final receipts",
        "Downloads",
        "Code &amp; Actions",
        *unresolved_action_ids,
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
