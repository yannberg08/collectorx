#!/usr/bin/env python3
"""Tests for meeting-artifacts collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "meeting_artifacts.py"


def test_collect_minutes_and_transcript_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        minutes = root / "roadshow.md"
        transcript = root / "meeting.vtt"
        out = root / "out"
        minutes.write_text("# 半导体公司路演纪要\n参会人：研究员A，基金经理B\n讨论财报、估值和风险点。\n", encoding="utf-8")
        transcript.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n今天讨论买入框架。\n", encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(root),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T01:20:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "meeting-artifacts" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 2
        assert {event["data"]["artifact_type"] for event in events} == {"minutes", "transcript"}
        assert all(event["collector"] == "meeting-artifacts" for event in events)
        assert all(event["kind"] == "note" for event in events)
        assert all(event["wiki_targets"] == ["internal.collaboration.meetings"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_meeting_minutes"] is False


if __name__ == "__main__":
    test_collect_minutes_and_transcript_events()
    print("meeting-artifacts tests passed.")
