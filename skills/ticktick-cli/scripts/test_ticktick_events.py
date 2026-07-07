#!/usr/bin/env python3
"""Tests for TickTick CollectorX event conversion."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "ticktick_events.py"


def test_ticktick_json_to_task_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "tasks.json"
        out = root / "out"
        source.write_text(
            json.dumps(
                [
                    {
                        "id": "task-1",
                        "projectId": "project-1",
                        "projectName": "投资研究",
                        "title": "复盘贵州茅台财报",
                        "content": "看现金流和估值",
                        "dueDate": "2026-07-09T10:00:00+08:00",
                        "status": 0,
                        "tags": ["投资"],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(source), "--out-dir", str(out), "--collected-at", "2026-07-08T01:10:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "ticktick" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        event = events[0]
        assert event["schema"] == "collectorx.event.v1"
        assert event["collector"] == "ticktick"
        assert event["kind"] == "task"
        assert event["data"]["title"] == "复盘贵州茅台财报"
        assert event["data"]["is_completed"] is False
        assert event["wiki_targets"] == ["internal.productivity.tasks"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_tasks"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"


if __name__ == "__main__":
    test_ticktick_json_to_task_events()
    print("ticktick event tests passed.")
