#!/usr/bin/env python3
"""Tests for filesystem-collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from filesystem_collector.scanner import default_roots, platform_default_root_plan


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
        assert event["wiki_targets"] == ["internal.knowledge.files"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["content_read"] is False
        assert set(manifest["platform_default_root_plan"]) == {"macos", "windows", "linux"}


def test_default_roots_cross_platform_plan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        for rel in (
            "Documents",
            "Desktop",
            "Downloads",
            "Library/Mobile Documents/com~apple~CloudDocs",
            "OneDrive",
            "Documents/OneDrive",
        ):
            (home / rel).mkdir(parents=True)

        macos = default_roots(home, system_name="Darwin")
        windows = default_roots(home, system_name="Windows")
        linux = default_roots(home, system_name="Linux")

        assert home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" in macos
        assert home / "OneDrive" in windows
        assert home / "Documents" / "OneDrive" in windows
        assert home / "OneDrive" not in linux

        plan = platform_default_root_plan(home)
        assert len(plan["macos"]) == 4
        assert len(plan["windows"]) == 5
        assert len(plan["linux"]) == 3


if __name__ == "__main__":
    test_collect_metadata_only()
    test_default_roots_cross_platform_plan()
    print("filesystem-collector tests passed.")
