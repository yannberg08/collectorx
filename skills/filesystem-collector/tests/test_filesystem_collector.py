#!/usr/bin/env python3
"""Tests for filesystem-collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "filesystem_query.py"


def test_collect_metadata_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "research.md").write_text("贵州茅台 估值笔记", encoding="utf-8")
        (root / "ignore.bin").write_bytes(b"xx")
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--root",
                str(root),
                "--out-dir",
                str(out),
                "--format",
                "json",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        lines = (out / "lake" / "filesystem" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["schema"] == "collectorx.event.v1"
        assert event["kind"] == "file"
        assert event["data"]["metadata_only"] is True
        assert event["data"]["content_read"] is False
        assert "content" not in event["data"]


if __name__ == "__main__":
    test_collect_metadata_only()
    print("filesystem-collector tests passed.")
