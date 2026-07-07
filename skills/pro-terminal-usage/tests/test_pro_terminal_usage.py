#!/usr/bin/env python3
"""Tests for pro-terminal-usage collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pro_terminal_usage.py"


def test_collect_terminal_workflow_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "wind_usage.json"
        csv_path = root / "ifind_watchlist.csv"
        html_path = root / "choice_workspace.html"
        out = root / "out"
        export.write_text(
            json.dumps(
                {
                    "usage": [
                        {
                            "terminal": "Wind",
                            "activity_type": "search",
                            "query": "半导体 ROE 估值",
                            "time": "2026-07-08T09:00:00+08:00",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "model_template",
                            "template_name": "DCF估值模板",
                            "symbols": ["NVDA.US", "00700.HK"],
                            "factors": "DCF, ROE, PE",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        csv_path.write_text(
            "terminal,activity_type,title,symbols,industries,time\n"
            "同花顺 iFinD,watchlist,港股互联网自选,\"00700.HK,09988.HK\",互联网,2026-07-08T10:00:00+08:00\n"
            "同花顺 iFinD,download,半导体财务指标导出,,半导体,2026-07-08T11:00:00+08:00\n",
            encoding="utf-8",
        )
        html_path.write_text(
            "<html><head><title>Choice 宏观看板</title>"
            "<meta name=\"application-name\" content=\"Choice\"></head>"
            "<body>工作区：宏观利率与汇率监控。</body></html>",
            encoding="utf-8",
        )
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
                "2026-07-08T04:30:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "pro-terminal-usage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 5
        assert {event["data"]["activity_type"] for event in events} == {"download", "model_template", "search", "watchlist", "workspace"}
        assert {event["data"]["terminal"] for event in events} == {"choice", "ifind", "wind"}
        watchlist = next(event for event in events if event["data"]["activity_type"] == "watchlist")
        assert watchlist["kind"] == "watchlist"
        assert watchlist["data"]["symbols"] == ["00700.HK", "09988.HK"]
        model = next(event for event in events if event["data"]["activity_type"] == "model_template")
        assert "PE" in model["data"]["factors"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_terminal_usage"] is False
        assert manifest["collection_readiness"]["license_boundary"] == "workflow_metadata_only"
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["licensed_content_mirrored"] is False
        assert evidence["generated_from"]["event_count"] == 5


if __name__ == "__main__":
    test_collect_terminal_workflow_exports()
    print("pro-terminal-usage tests passed.")
