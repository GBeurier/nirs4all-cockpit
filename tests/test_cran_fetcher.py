"""Exercise the read-only source fetcher with a fully offline GitHub stub."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = b"separate R SDK source fixture"


@pytest.mark.parametrize("bad_digest", [False, True])
def test_fetcher_uses_separate_r_sdk_and_verifies_its_digest(tmp_path: Path, bad_digest: bool) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh-calls.jsonl"
    gh = bin_dir / "gh"
    gh.write_text(f"#!{sys.executable}\n" + dedent('''
        import hashlib, json, os, sys
        from pathlib import Path
        args = sys.argv[1:]
        with Path(os.environ["FAKE_GH_LOG"]).open("a") as stream:
            stream.write(json.dumps(args) + "\\n")
        if args == ["auth", "status"]:
            raise SystemExit(0)
        repo = args[args.index("-R") + 1]
        if repo != "GBeurier/nirs4all-r":
            raise SystemExit(1)
        payload = b"separate R SDK source fixture"
        filename = "nirs4all_0.7.3.tar.gz"
        if args[:2] == ["release", "download"]:
            (Path(args[args.index("--dir") + 1]) / filename).write_bytes(payload)
        elif "tagName" in args:
            print("v0.7.3")
        elif args[-1] == ".assets[].name":
            print(filename)
        else:
            digest = "0" * 64 if os.environ["FAKE_GH_BAD_DIGEST"] == "1" else hashlib.sha256(payload).hexdigest()
            print("sha256:" + digest)
    '''))
    gh.chmod(0o700)
    out = tmp_path / "downloads"
    environment = {key: value for key, value in os.environ.items() if key not in {"GH_TOKEN", "GITHUB_TOKEN"}}
    environment.update(PATH=str(bin_dir) + os.pathsep + os.environ["PATH"], FAKE_GH_LOG=str(log),
                       FAKE_GH_BAD_DIGEST="1" if bad_digest else "0", N4A_OWNER="GBeurier")
    result = subprocess.run(["bash", str(ROOT / "scripts/fetch-cran-tarballs.sh"), str(out)],
                            cwd=tmp_path, env=environment, text=True, capture_output=True, check=False)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert any("GBeurier/nirs4all-r" in call for call in calls)
    assert not any("GBeurier/nirs4all-core" in call for call in calls)
    if bad_digest:
        assert result.returncode != 0 and "checksum mismatch" in result.stderr
        assert not (out / "SHA256SUMS").exists()
    else:
        assert result.returncode == 0, result.stderr
        assert (out / "nirs4all_0.7.3.tar.gz").read_bytes() == SOURCE
        assert hashlib.sha256(SOURCE).hexdigest() in (out / "SHA256SUMS").read_text()
        notes = (out / "CRAN-optional-comments.md").read_text()
        assert "not a CRAN-ready verdict" in notes
        assert "24,664,283" not in notes
