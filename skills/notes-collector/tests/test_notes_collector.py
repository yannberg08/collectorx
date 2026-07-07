#!/usr/bin/env python3
"""Tests for notes-collector event output."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "notes_api.py"


def test_obsidian_outputs_collectorx_events_without_full_content_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault = root / "vault"
        vault.mkdir()
        (vault / "investment.md").write_text("#复盘\n贵州茅台 估值和买入纪律\n", encoding="utf-8")
        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "obsidian",
                "--vault",
                str(vault),
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "notes" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        event = events[0]
        assert event["schema"] == "collectorx.event.v1"
        assert event["collector"] == "notes"
        assert event["kind"] == "note"
        assert event["data"]["source_app"] == "obsidian"
        assert event["data"]["content_preview"].startswith("#复盘")
        assert "content" not in event["data"]
        assert event["wiki_targets"] == ["internal.knowledge.notes"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_notes"] is False


if __name__ == "__main__":
    test_obsidian_outputs_collectorx_events_without_full_content_by_default()
    print("notes-collector tests passed.")
